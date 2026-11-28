# -*- coding: utf-8 -*-
"""
구매 및 계정 보안 가드레일 모듈.

- 최대 계정 수 제한 (기본 4개)
- 1계정당 로또 6/45 주간 최대 구매 수량 제한 (5게임 = 5,000원)
- 1계정당 연금복권 720+ 1일 최대 구매 상한선 (기본 5매 = 5,000원, 오구매 방지)
- 다중 계정 간 동시 구매 방지 및 계정 간 20초 쿨다운 강제
- 폴링 최소 주기(1800초) 강제 및 랜덤 지터(Jitter) 적용
- 로그용 아이디 마스킹
"""

from __future__ import annotations

import math
import random
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
    _TZ_KST = ZoneInfo("Asia/Seoul")
except ImportError:
    _TZ_KST = timezone(timedelta(hours=9))

MAX_ACCOUNTS = 4
WEEKLY_LOTTO_LIMIT = 5
DAILY_PENSION_LIMIT = 5
INTER_ACCOUNT_COOLDOWN_SECONDS = 20.0
MIN_UPDATE_INTERVAL_SECONDS = 1800
POLL_JITTER_MAX_SECONDS = 120.0


class PurchaseGuardError(Exception):
    """구매/계정 가드레일 위반 예외."""


class PurchaseCooldownError(PurchaseGuardError):
    """다중 계정 동시 구매 또는 계정 간 쿨다운 미충족 예외."""

    def __init__(self, message: str, remaining_seconds: float = 0.0):
        super().__init__(message)
        self.remaining_seconds = max(0.0, float(remaining_seconds))


def mask_username(username: Optional[str]) -> str:
    """로그 출력용으로 계정 아이디 일부를 마스킹한다."""
    if not username:
        return "***"
    text = str(username)
    length = len(text)
    if length == 1:
        return "*"
    if length == 2:
        return text[0] + "*"
    if length <= 4:
        return text[:2] + "*" * (length - 2)
    return text[:2] + "*" * (length - 3) + text[-1]


def clamp_update_interval(
    interval: int,
    min_interval: int = MIN_UPDATE_INTERVAL_SECONDS,
) -> int:
    """서버 부하 방지를 위해 폴링 주기를 최소값(기본 1800초) 이상으로 강제한다."""
    try:
        val = int(interval)
    except (ValueError, TypeError):
        val = min_interval
    return max(min_interval, val)


def compute_poll_delay(
    base_interval: int,
    max_jitter: float = POLL_JITTER_MAX_SECONDS,
    rand_fn: Callable[[float, float], float] = random.uniform,
) -> float:
    """최소 주기가 보장된 폴링 간격에 랜덤 지터(0 ~ max_jitter초)를 더한다."""
    base = clamp_update_interval(base_interval)
    jitter = max(0.0, float(rand_fn(0.0, max_jitter))) if max_jitter > 0 else 0.0
    return float(base) + jitter


def enforce_account_limit(
    accounts_list: Optional[List[dict]],
    max_accounts: int = MAX_ACCOUNTS,
) -> Tuple[List[dict], int]:
    """설정된 계정 목록을 최대 허용 개수(기본 4개)로 제한한다."""
    if not accounts_list:
        return [], 0
    if max_accounts <= 0:
        return [], len(accounts_list)

    if len(accounts_list) <= max_accounts:
        return list(accounts_list), 0

    limited = list(accounts_list[:max_accounts])
    dropped = len(accounts_list) - max_accounts
    return limited, dropped


def calculate_weekly_bought_count(history_items: Optional[List[dict]]) -> int:
    """구매 내역(LO40) 중 이번 주 미추첨 구매 게임 수 합계를 안전하게 계산한다."""
    if not history_items:
        return 0
    total = 0
    for item in history_items:
        if not isinstance(item, dict):
            continue
        if item.get("ltWnResult") != "미추첨":
            continue
        raw_qty = item.get("prchsQty", 0)
        try:
            qty = int(raw_qty) if raw_qty is not None else 0
        except (ValueError, TypeError):
            qty = 0
        if qty > 0:
            total += qty
    return total


def validate_weekly_lotto_purchase(
    already_bought: int,
    requested_games: int,
    max_weekly: int = WEEKLY_LOTTO_LIMIT,
) -> int:
    """1계정당 주간 최대 5게임(5,000원) 한도를 검증하고 실제 구매 가능 수량을 반환한다."""
    if requested_games <= 0:
        raise PurchaseGuardError("[ERROR] 구매할 게임 수가 1게임 이상이어야 합니다.")
    if requested_games > max_weekly:
        raise PurchaseGuardError(
            f"[ERROR] 1회 최대 {max_weekly}게임까지만 구매할 수 있습니다."
        )
    if already_bought < 0:
        already_bought = 0
    if already_bought >= max_weekly:
        raise PurchaseGuardError(
            f"[ERROR] 주간 구매 한도({max_weekly}게임)에 도달했습니다. 다음 주에 다시 구매해주세요."
        )

    remaining = max_weekly - already_bought
    return min(requested_games, remaining)


def _today_kst() -> date:
    return datetime.now(_TZ_KST).date()


class DailyPensionPurchaseTracker:
    """연금복권720+ 1계정당 1일 최대 구매 상한선(Hard Limit) 추적기.

    자동화 루프 버그 등으로 예치금이 한 번에 소진되는 사고를 방지한다.
    """

    def __init__(
        self,
        daily_limit: int = DAILY_PENSION_LIMIT,
        date_fn: Callable[[], date] = _today_kst,
    ):
        self.daily_limit = int(daily_limit)
        self._date_fn = date_fn
        self._counts: Dict[Tuple[str, date], int] = {}

    def get_today_count(self, username: str) -> int:
        return self._counts.get((username, self._date_fn()), 0)

    def check_allowed(self, username: str, requested_count: int) -> None:
        if requested_count <= 0:
            raise PurchaseGuardError("[ERROR] 구매 매수는 1매 이상이어야 합니다.")
        if requested_count > self.daily_limit:
            raise PurchaseGuardError(
                f"[ERROR] 연금복권 1회/1일 최대 구매 상한선({self.daily_limit}매, "
                f"{self.daily_limit * 1000:,}원)을 초과했습니다. (요청: {requested_count}매)"
            )
        today_count = self.get_today_count(username)
        if today_count + requested_count > self.daily_limit:
            remaining = max(0, self.daily_limit - today_count)
            raise PurchaseGuardError(
                f"[ERROR] 연금복권 1일 구매 상한선({self.daily_limit}매, "
                f"{self.daily_limit * 1000:,}원)을 초과합니다. "
                f"(금일 구매: {today_count}매, 잔여: {remaining}매, 요청: {requested_count}매)"
            )

    def record_purchase(self, username: str, count: int) -> int:
        today = self._date_fn()
        # 오래된 날짜 항목 정리
        stale_keys = [k for k in self._counts if k[1] < today]
        for k in stale_keys:
            del self._counts[k]
        key = (username, today)
        new_total = self._counts.get(key, 0) + max(0, int(count))
        self._counts[key] = new_total
        return new_total

    def reset(self) -> None:
        self._counts.clear()


class InterAccountPurchaseGuard:
    """다중 계정 동시 구매 차단 및 계정 간 쿨다운(기본 20초) 보안 가드."""

    def __init__(
        self,
        cooldown_seconds: float = INTER_ACCOUNT_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.cooldown_seconds = float(cooldown_seconds)
        self._clock = clock
        self._active_username: Optional[str] = None
        self._last_completed_username: Optional[str] = None
        self._last_completed_at: Optional[float] = None

    @property
    def active_username(self) -> Optional[str]:
        return self._active_username

    @property
    def last_completed_username(self) -> Optional[str]:
        return self._last_completed_username

    @property
    def last_completed_at(self) -> Optional[float]:
        return self._last_completed_at

    def acquire(self, username: str) -> None:
        """계정의 구매 시작 권한을 획득한다. 위반 시 PurchaseCooldownError 발생."""
        now = self._clock()

        if self._active_username is not None:
            if self._active_username == username:
                raise PurchaseCooldownError(
                    "현재 해당 계정의 구매가 이미 진행 중입니다. 완료 후 다시 시도해 주세요.",
                    remaining_seconds=self.cooldown_seconds,
                )
            masked_active = mask_username(self._active_username)
            raise PurchaseCooldownError(
                f"다중 계정 동시 구매가 제한되어 있습니다. "
                f"다른 계정({masked_active}) 구매 완료 후 "
                f"{int(self.cooldown_seconds)}초 뒤에 다시 시도해 주세요.",
                remaining_seconds=self.cooldown_seconds,
            )

        if (
            self._last_completed_username is not None
            and self._last_completed_username != username
            and self._last_completed_at is not None
        ):
            elapsed = now - self._last_completed_at
            if elapsed < self.cooldown_seconds:
                remaining = self.cooldown_seconds - elapsed
                remaining_ceil = max(1, math.ceil(remaining))
                masked_prev = mask_username(self._last_completed_username)
                raise PurchaseCooldownError(
                    f"다중 계정 연속 구매 제한: 다른 계정({masked_prev}) "
                    f"구매 후 {int(self.cooldown_seconds)}초 간격이 필요합니다. "
                    f"약 {remaining_ceil}초 후 다시 시도해 주세요.",
                    remaining_seconds=remaining,
                )

        self._active_username = username

    def release(self, username: str, record_cooldown: bool = True) -> None:
        """구매(및 구매 정보 조회) 종료 후 락을 해제하고 필요 시 쿨다운 기준 시각을 기록한다."""
        if self._active_username == username:
            self._active_username = None
        if record_cooldown:
            self._last_completed_username = username
            self._last_completed_at = self._clock()

    def get_remaining_cooldown(self, username: str) -> float:
        """해당 계정이 구매 가능해지기까지 남은 대기 시간(초)을 반환한다. 즉시 가능하면 0.0."""
        if self._active_username is not None:
            return self.cooldown_seconds
        if (
            self._last_completed_username is not None
            and self._last_completed_username != username
            and self._last_completed_at is not None
        ):
            elapsed = self._clock() - self._last_completed_at
            if elapsed < self.cooldown_seconds:
                return max(0.0, self.cooldown_seconds - elapsed)
        return 0.0

    def reset(self) -> None:
        """테스트 및 재초기화용 상태 리셋."""
        self._active_username = None
        self._last_completed_username = None
        self._last_completed_at = None
