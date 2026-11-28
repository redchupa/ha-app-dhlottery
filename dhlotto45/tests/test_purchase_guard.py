# -*- coding: utf-8 -*-
"""
계정 수 제한(최대 4계정), 1계정 주간 5게임 한도, 다중 계정 간 20초 구매 쿨다운 단위 테스트.

실행: python dhlotto45/tests/test_purchase_guard.py   (종료코드 0=통과)
"""

import asyncio
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(HERE, "..", "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from datetime import date  # noqa: E402
from purchase_guard import (  # noqa: E402
    DAILY_PENSION_LIMIT,
    INTER_ACCOUNT_COOLDOWN_SECONDS,
    MAX_ACCOUNTS,
    MIN_UPDATE_INTERVAL_SECONDS,
    WEEKLY_LOTTO_LIMIT,
    DailyPensionPurchaseTracker,
    InterAccountPurchaseGuard,
    PurchaseCooldownError,
    PurchaseGuardError,
    calculate_weekly_bought_count,
    clamp_update_interval,
    compute_poll_delay,
    enforce_account_limit,
    mask_username,
    validate_weekly_lotto_purchase,
)


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestAccountLimit(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(MAX_ACCOUNTS, 4)
        self.assertEqual(WEEKLY_LOTTO_LIMIT, 5)
        self.assertEqual(INTER_ACCOUNT_COOLDOWN_SECONDS, 20.0)

    def test_empty_and_within_limit(self):
        self.assertEqual(enforce_account_limit([]), ([], 0))
        self.assertEqual(enforce_account_limit(None), ([], 0))

        accs = [{"username": f"user{i}", "password": "pw"} for i in range(1, 5)]
        limited, dropped = enforce_account_limit(accs)
        self.assertEqual(len(limited), 4)
        self.assertEqual(dropped, 0)
        self.assertEqual([a["username"] for a in limited], ["user1", "user2", "user3", "user4"])

    def test_exceeding_max_accounts_truncated_to_4(self):
        accs = [{"username": f"user{i}", "password": "pw"} for i in range(1, 7)]
        limited, dropped = enforce_account_limit(accs)
        self.assertEqual(len(limited), 4)
        self.assertEqual(dropped, 2)
        self.assertEqual([a["username"] for a in limited], ["user1", "user2", "user3", "user4"])


class TestWeeklyLottoLimit(unittest.TestCase):
    def test_calculate_weekly_bought_count(self):
        items = [
            {"ltWnResult": "미추첨", "prchsQty": 2},
            {"ltWnResult": "미추첨", "prchsQty": "1"},
            {"ltWnResult": "낙첨", "prchsQty": 5},
            {"ltWnResult": "5등 당첨", "prchsQty": 5},
            {"ltWnResult": "미추첨", "prchsQty": None},
            {"ltWnResult": "미추첨", "prchsQty": "bad"},
        ]
        self.assertEqual(calculate_weekly_bought_count(items), 3)
        self.assertEqual(calculate_weekly_bought_count([]), 0)
        self.assertEqual(calculate_weekly_bought_count(None), 0)

    def test_validate_weekly_lotto_purchase_normal(self):
        self.assertEqual(validate_weekly_lotto_purchase(0, 5), 5)
        self.assertEqual(validate_weekly_lotto_purchase(0, 1), 1)
        self.assertEqual(validate_weekly_lotto_purchase(3, 1), 1)
        # 이미 3게임 구매한 상태에서 5게임 요청 시 잔여 2게임으로 제한되어 총 5게임을 넘지 않음
        self.assertEqual(validate_weekly_lotto_purchase(3, 5), 2)
        self.assertEqual(validate_weekly_lotto_purchase(4, 5), 1)

    def test_validate_weekly_lotto_purchase_blocks_over_limit(self):
        with self.assertRaises(PurchaseGuardError):
            validate_weekly_lotto_purchase(5, 1)
        with self.assertRaises(PurchaseGuardError):
            validate_weekly_lotto_purchase(6, 1)
        with self.assertRaises(PurchaseGuardError):
            validate_weekly_lotto_purchase(0, 0)
        with self.assertRaises(PurchaseGuardError):
            validate_weekly_lotto_purchase(0, 6)


class TestInterAccountCooldownGuard(unittest.TestCase):
    def test_blocks_concurrent_purchase_between_accounts(self):
        clock = FakeClock(100.0)
        guard = InterAccountPurchaseGuard(cooldown_seconds=20.0, clock=clock)

        guard.acquire("account_a")
        self.assertEqual(guard.active_username, "account_a")

        # A 진행 중 B 동시 시도 -> 즉시 차단 (마스킹된 아이디 포함)
        with self.assertRaises(PurchaseCooldownError) as ctx_b:
            guard.acquire("account_b")
        self.assertIn("ac******a", str(ctx_b.exception))

        # A 진행 중 A 중복 시도 -> 즉시 차단
        with self.assertRaises(PurchaseCooldownError):
            guard.acquire("account_a")

        guard.release("account_a", record_cooldown=True)
        self.assertIsNone(guard.active_username)

    def test_enforces_20_second_cooldown_after_completion(self):
        clock = FakeClock(200.0)
        guard = InterAccountPurchaseGuard(cooldown_seconds=20.0, clock=clock)

        guard.acquire("account_a")
        # A 구매 + 구매정보 조회에 3초 소요 가정
        clock.advance(3.0)
        guard.release("account_a", record_cooldown=True)  # 완료 시각: 203.0

        # 완료 직후 (0초 경과) B 시도 -> 차단 (약 20초 남음)
        self.assertAlmostEqual(guard.get_remaining_cooldown("account_b"), 20.0, places=3)
        self.assertEqual(guard.get_remaining_cooldown("account_a"), 0.0)
        with self.assertRaises(PurchaseCooldownError) as ctx0:
            guard.acquire("account_b")
        self.assertAlmostEqual(ctx0.exception.remaining_seconds, 20.0, places=3)

        # 19.5초 경과 -> 여전히 차단
        clock.advance(19.5)
        self.assertAlmostEqual(guard.get_remaining_cooldown("account_b"), 0.5, places=3)
        with self.assertRaises(PurchaseCooldownError) as ctx1:
            guard.acquire("account_b")
        self.assertAlmostEqual(ctx1.exception.remaining_seconds, 0.5, places=3)

        # 정확히 20.0초 경과 -> B 허용!
        clock.advance(0.5)
        self.assertEqual(guard.get_remaining_cooldown("account_b"), 0.0)
        guard.acquire("account_b")
        self.assertEqual(guard.active_username, "account_b")
        guard.release("account_b", record_cooldown=True)

        # 이제 B 완료 직후 A 시도 -> 다시 20초 차단
        with self.assertRaises(PurchaseCooldownError):
            guard.acquire("account_a")

        clock.advance(20.0)
        guard.acquire("account_a")
        guard.release("account_a", record_cooldown=True)

    def test_release_without_recording_cooldown_does_not_block_other_account(self):
        clock = FakeClock(500.0)
        guard = InterAccountPurchaseGuard(cooldown_seconds=20.0, clock=clock)

        guard.acquire("account_a")
        guard.release("account_a", record_cooldown=False)

        # 로컬 검증 실패 등으로 쿨다운 미기록 시 B 즉시 허용
        guard.acquire("account_b")
        guard.release("account_b", record_cooldown=True)


class TestMainIntegrationWithGuard(unittest.IsolatedAsyncioTestCase):
    async def test_load_accounts_from_env_caps_at_4(self):
        import main

        six_accounts = [
            {"username": f"u{i}", "password": f"p{i}", "enabled": True}
            for i in range(1, 7)
        ]
        with patch.dict(os.environ, {"ACCOUNTS": json.dumps(six_accounts)}):
            main.load_accounts_from_env()
        self.assertEqual(len(main.config["accounts"]), 4)
        self.assertEqual([a["username"] for a in main.config["accounts"]], ["u1", "u2", "u3", "u4"])

    async def test_execute_button_purchase_enforces_20s_cooldown_after_query(self):
        import main

        clock = FakeClock(1000.0)
        test_guard = InterAccountPurchaseGuard(cooldown_seconds=20.0, clock=clock)

        acc_a = main.AccountData("acc_a", "pw_a", True)
        acc_b = main.AccountData("acc_b", "pw_b", True)

        buy_started = asyncio.Event()
        allow_query_finish = asyncio.Event()

        async def slow_update_sensors(account):
            if account.username == "acc_a":
                buy_started.set()
                await allow_query_finish.wait()
                # 구매정보 조회에 2초 걸렸다고 가정
                clock.advance(2.0)

        for acc in (acc_a, acc_b):
            acc.client = SimpleNamespace(
                logged_in=True,
                async_get_buy_list=AsyncMock(return_value=[]),
            )
            acc.lotto_645 = SimpleNamespace(
                async_buy=AsyncMock(return_value=SimpleNamespace(round_no=1200)),
            )

        errors = []

        async def capture_error(account, msg):
            errors.append((account.username, msg))

        with (
            patch.object(main, "purchase_guard", test_guard),
            patch.object(main, "_last_purchase_time", {}),
            patch.object(main, "update_sensors_for_account", side_effect=slow_update_sensors),
            patch.object(main, "publish_purchase_error", side_effect=capture_error),
        ):
            # 1) A 구매 시작 (구매 완료 후 구매정보 조회 단계에서 잠시 대기)
            task_a = asyncio.create_task(main.execute_button_purchase(acc_a, "buy_auto_1"))
            await buy_started.wait()

            # 2) A가 아직 구매정보 조회 중일 때 B 동시 구매 시도 -> 차단되어야 함
            await main.execute_button_purchase(acc_b, "buy_auto_1")
            self.assertEqual(acc_b.lotto_645.async_buy.await_count, 0)
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0][0], "acc_b")
            self.assertIn("동시 구매", errors[0][1])

            # 3) A 구매 + 구매정보 조회 완료
            allow_query_finish.set()
            await task_a
            self.assertEqual(acc_a.lotto_645.async_buy.await_count, 1)

            # 4) A 완료 후 10초 뒤 B 구매 시도 -> 20초 미경과로 차단
            clock.advance(10.0)
            await main.execute_button_purchase(acc_b, "buy_auto_1")
            self.assertEqual(acc_b.lotto_645.async_buy.await_count, 0)
            self.assertEqual(len(errors), 2)
            self.assertIn("20초", errors[1][1])

            # 5) 추가 10초 경과(총 20초) -> B 구매 성공!
            clock.advance(10.0)
            await main.execute_button_purchase(acc_b, "buy_auto_1")
            self.assertEqual(acc_b.lotto_645.async_buy.await_count, 1)

    async def test_dh_lotto_645_weekly_limit_blocks_when_5_bought(self):
        from dh_lotto_645 import DhLotto645, DhLotto645Error, DhLotto645SelMode

        fake_client = SimpleNamespace(
            _async_ensure_main_mode_normal=AsyncMock(),
            async_get_buy_list=AsyncMock(
                return_value=[{"ltWnResult": "미추첨", "prchsQty": 5}]
            ),
            async_get_balance=AsyncMock(return_value=SimpleNamespace(purchase_available=50000)),
        )
        lotto = DhLotto645(fake_client)

        # 구매 가능 시간대(평일 12:00)로 고정
        class FixedDateTime(__import__("datetime").datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 24, 12, 0, 0)

        with patch("dh_lotto_645.datetime.datetime", FixedDateTime):
            with self.assertRaises(DhLotto645Error) as ctx:
                await lotto.async_buy([DhLotto645.Slot(mode=DhLotto645SelMode.AUTO)])
            self.assertIn("주간 구매 한도(5게임)", str(ctx.exception))


class TestSecurityHardening(unittest.TestCase):
    def test_mask_username(self):
        self.assertEqual(mask_username(""), "***")
        self.assertEqual(mask_username(None), "***")
        self.assertEqual(mask_username("a"), "*")
        self.assertEqual(mask_username("ab"), "a*")
        self.assertEqual(mask_username("abcd"), "ab**")
        self.assertEqual(mask_username("redchupa"), "re*****a")

    def test_clamp_update_interval_and_jitter(self):
        self.assertEqual(MIN_UPDATE_INTERVAL_SECONDS, 1800)
        self.assertEqual(clamp_update_interval(60), 1800)
        self.assertEqual(clamp_update_interval(3600), 3600)
        self.assertEqual(clamp_update_interval("invalid"), 1800)

        delay = compute_poll_delay(60, max_jitter=120.0, rand_fn=lambda a, b: 45.5)
        self.assertAlmostEqual(delay, 1845.5)

    def test_daily_pension_hard_limit(self):
        current_day = [date(2026, 11, 23)]
        tracker = DailyPensionPurchaseTracker(
            daily_limit=DAILY_PENSION_LIMIT,
            date_fn=lambda: current_day[0],
        )

        tracker.check_allowed("user_a", 5)
        tracker.record_purchase("user_a", 3)
        self.assertEqual(tracker.get_today_count("user_a"), 3)

        # 잔여 2매: 1매는 허용, 3매는 차단
        tracker.check_allowed("user_a", 2)
        with self.assertRaises(PurchaseGuardError):
            tracker.check_allowed("user_a", 3)

        # 다른 계정은 독립 카운트
        tracker.check_allowed("user_b", 5)

        # 다음 날로 넘어가면 자동 리셋
        current_day[0] = date(2026, 11, 24)
        self.assertEqual(tracker.get_today_count("user_a"), 0)
        tracker.check_allowed("user_a", 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
