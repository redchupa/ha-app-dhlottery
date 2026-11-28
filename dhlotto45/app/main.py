# -*- coding: utf-8 -*-
"""
Lotto 45 Add-on Main Application v2.13.0
Home Assistant Add-on for DH Lottery 6/45
v2.0.8 - Session keep-alive fix + retry path overhaul (full session reset on any error)
"""

import os
import asyncio
import logging
import random
import secrets
import time
from typing import Optional, Dict, List
from datetime import date, datetime, timezone, timedelta
from contextlib import asynccontextmanager

try:
    from zoneinfo import ZoneInfo
    _TZ_KST = ZoneInfo("Asia/Seoul")
except ImportError:
    _TZ_KST = timezone(timedelta(hours=9))
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from dh_lottery_client import DhLotteryClient, DhLotteryError, DhLotteryLoginError
import features as FT
import insights as IN
from dh_lotto_645 import DhLotto645, DhLotto645SelMode, DhLotto645Error, _rank_drawed_to_result
from dh_lotto_analyzer import DhLottoAnalyzer
from dh_mobile_api import DhMobileApiClient, DhMobileApiError
from dh_pension_browser import (
    DhPensionBrowser,
    DhPensionBrowserError,
    extra_ticket_warning,
    validate_manual_selection,
)
from dashboard_api import (
    ALLOWED_ACTIONS,
    CSRF_HEADER,
    LOTTO_ACTIONS,
    PENSION_ACTIONS,
    DashboardInputError,
    AliasLogFilter,
    configured_usernames,
    account_aliases,
    action_label,
    csrf_ok,
    is_ingress_client,
    judge_outcome,
    merge_prefs,
    normalize_prefs,
    normalize_lotto_manual,
    normalize_pension_manual,
    resolve_alias,
)
from dashboard_page import PAGE_TEMPLATE
from dh_pension_history import (
    build_round,
    group_rounds,
    result_style as pension_result_style,
    select_rounds,
    summarize,
)
from mqtt_discovery import MQTTDiscovery, publish_sensor_mqtt
from purchase_guard import (
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
)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
# 진단 리포트용 최근 로그(메모리만, 아이디 별칭 필터가 같이 걸린다)
_ring_log = FT.RingLogHandler(300)
_ring_log.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(_ring_log)

# Account data structure
class AccountData:
    def __init__(self, username: str, password: str, enabled: bool = True):
        self.username = username
        self.password = password
        self.enabled = enabled
        self.client: Optional[DhLotteryClient] = None
        self.lotto_645: Optional[DhLotto645] = None
        self.analyzer: Optional[DhLottoAnalyzer] = None
        self.pension: Optional[DhPensionBrowser] = None
        self.manual_numbers_state = "auto,auto,auto,auto,auto,auto"
        # 연금복권 수동 구매 입력(형식 "조,번호" 예: "1,123456"). 빈 값이면 미설정.
        self.pension_manual_state = ""
        self.update_task: Optional[asyncio.Task] = None
        # 구매 불가 시간대(토요일 20:00~일요일 06:00)에 이전 회차 당첨 결과 1회만 동기화
        self.prev_round_result_synced_when_unavailable: bool = False
        # 구매 불가 시간대에도 예치금·구매 내역을 한 번은 읽어 둔다(재시작 직후 화면이 비지 않게)
        self.closed_snapshot_done: bool = False
        # 사이드바 대시보드용: 마지막으로 발행한 센서 값 {entity_id: {state, attributes, ts}}
        self.sensor_cache: Dict[str, dict] = {}
        # 대시보드에서 실행한 마지막 구매 작업 상태
        self.last_action: Optional[dict] = None

APP_VERSION = "2.13.0"
FIXED_UPDATE_INTERVAL = 3600  # 센서 갱신 주기(초). v2.6.2 부터 설정 옵션 제거

# Configuration variables
config = {
    "accounts": [],
    # 로또6/45·연금복권720+·MQTT 는 항상 사용한다(v2.6.1 부터 설정 옵션 제거, 변경 불가).
    "enable_lotto645": True,
    "enable_pension720": True,
    "update_interval": clamp_update_interval(FIXED_UPDATE_INTERVAL),  # 고정(설정 불가)
    "use_mqtt": True,
    "ha_url": os.getenv("HA_URL", "http://supervisor/core"),
    "supervisor_token": os.getenv("SUPERVISOR_TOKEN", ""),
    "is_beta": os.getenv("IS_BETA", "false").lower() == "true",
}

# Global variables
accounts: Dict[str, AccountData] = {}
_last_purchase_time: Dict[tuple, float] = {}  # (username, button_id) -> timestamp, 중복 실행 방지
purchase_guard = InterAccountPurchaseGuard(cooldown_seconds=INTER_ACCOUNT_COOLDOWN_SECONDS)
pension_daily_tracker = DailyPensionPurchaseTracker(daily_limit=DAILY_PENSION_LIMIT)
mqtt_client: Optional[MQTTDiscovery] = None
event_loop: Optional[asyncio.AbstractEventLoop] = None


def install_log_alias_filter(usernames) -> None:
    """애드온 로그에서 실제 아이디를 Account_N 별칭으로 바꾼다(로그 공유 시 아이디 노출 방지).

    일부만 가린 표기(예: ab*****9)도 아이디 앞뒤 글자가 드러나므로 같은 별칭으로 바꾼다.
    """
    aliases = dict(account_aliases(usernames))
    masks = [mask_username(u) for u in usernames or []]
    for u, m in zip(usernames or [], masks):
        if m != u and masks.count(m) == 1:
            aliases[m] = aliases[u]
    f = AliasLogFilter(aliases)
    for handler in logging.getLogger().handlers:
        for old in [x for x in handler.filters if isinstance(x, AliasLogFilter)]:
            handler.removeFilter(old)
        handler.addFilter(f)


def load_accounts_from_env():
    """Load accounts from environment variables (최대 4계정 제한 적용)."""
    import json

    accounts_json = os.getenv("ACCOUNTS", "[]")
    try:
        accounts_list = json.loads(accounts_json)
        limited_accounts, dropped_count = enforce_account_limit(accounts_list, MAX_ACCOUNTS)
        if dropped_count > 0:
            logger.warning(
                f"최대 허용 계정 수({MAX_ACCOUNTS}개)를 초과했습니다 "
                f"({len(accounts_list)}개 설정됨). 상위 {MAX_ACCOUNTS}개 계정만 로드되며 "
                f"{dropped_count}개 계정은 무시됩니다."
            )
        config["accounts"] = limited_accounts
        logger.info(f"Loaded {len(limited_accounts)}/{MAX_ACCOUNTS} account(s) from configuration")

        for i, acc in enumerate(limited_accounts, 1):
            username = acc.get("username", "")
            enabled = acc.get("enabled", True)
            logger.info(f"  Account {i}: {mask_username(username)} (enabled: {enabled})")
    except Exception as e:
        logger.error(f"Failed to parse accounts from environment: {e}")
        config["accounts"] = []


# Helper Functions
def _safe_int(value) -> int:
    """Safe integer conversion"""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _parse_yyyymmdd(text: str) -> Optional[str]:
    """Convert YYYYMMDD to YYYY-MM-DD format"""
    if not text or not isinstance(text, str):
        return None
    text = text.strip()
    if len(text) != 8:
        return None
    try:
        year = int(text[0:4])
        month = int(text[4:6])
        day = int(text[6:8])
        d = date(year, month, day)
        return d.isoformat()
    except ValueError:
        return None


def _get_lotto645_item(data: dict) -> dict:
    """Extract lotto645 result data"""
    if not data:
        return {}
    if "_raw" in data:
        return data["_raw"]
    items = data.get("list", [])
    if items:
        return items[0]
    return data


def is_purchase_available_now() -> bool:
    """
    동행복권 구매 가능 시간(KST)이면 True.
    - 평일/일: 06:00~24:00 (구매 불가: 00:00~05:59)
    - 토요일: 06:00~20:00 (구매 불가: 20:00~06:00 = 20:00~23:59 + 00:00~05:59)
    """
    now = datetime.now(_TZ_KST)
    wd = now.weekday()  # 0=Mon .. 6=Sun
    minutes = now.hour * 60 + now.minute  # 06:00 = 360, 20:00 = 1200
    if minutes < 360:  # 00:00~05:59 모든 요일 구매 불가
        return False
    if wd == 5:  # 토요일: 20:00~06:00 구매 불가 → 20:00 이상이면 불가
        if minutes >= 1200:  # 20:00~23:59
            return False
    return True


def get_next_available_time() -> datetime:
    """
    다음 구매 가능 시간을 계산합니다.
    Returns: 다음 구매 가능 시간 (KST)
    """
    now = datetime.now(_TZ_KST)
    wd = now.weekday()  # 0=Mon .. 6=Sun
    minutes = now.hour * 60 + now.minute

    # 00:00~05:59 (모든 요일): 오늘 06:00
    if minutes < 360:
        next_time = now.replace(hour=6, minute=0, second=0, microsecond=0)
        return next_time

    # 토요일 20:00~23:59: 내일(일요일) 06:00
    if wd == 5 and minutes >= 1200:
        next_day = now + timedelta(days=1)
        next_time = next_day.replace(hour=6, minute=0, second=0, microsecond=0)
        return next_time

    # 현재 구매 가능한 경우 (이 함수가 호출되면 안 되지만 안전장치)
    return now


async def register_buttons_for_account(account: AccountData):
    """Register button entities for a specific account"""
    if not mqtt_client or not mqtt_client.connected:
        logger.warning(f"[BUTTON][{account.username}] MQTT not connected")
        return

    username = account.username
    logger.info(f"[BUTTON][{username}] Registering button entities")

    device_suffix = " (Beta)" if config.get("is_beta", False) else ""
    device_name = f"DH Lottery Addon{device_suffix} ({username})"
    device_id = f"dhlotto_addon_{username}"

    # Buttons
    buttons = [
        ("buy_auto_1", "로또 1게임 자동 구매", "mdi:ticket-confirmation"),
        ("buy_auto_5", "로또 5게임 자동 구매", "mdi:ticket-confirmation-outline"),
        ("buy_manual", "로또 1게임 수동 구매", "mdi:hand-pointing-right"),
        ("generate_random", "로또 랜덤 번호 생성", "mdi:dice-multiple"),
    ]
    if config.get("enable_pension720", True):
        buttons += [
            ("buy_pension_auto_1", "연금복권 1매 자동 구매", "mdi:cash"),
            ("buy_pension_auto_5", "연금복권 5매 자동 구매", "mdi:cash-multiple"),
            ("buy_pension_manual", "연금복권 1매 수동 구매", "mdi:hand-pointing-right"),
            ("diag_pension_manual", "연금복권 수동 UI 진단", "mdi:bug-check-outline"),
        ]
    for button_id, button_name, icon in buttons:
        button_topic = f"homeassistant/button/{mqtt_client.topic_prefix}_{username}_{button_id}/command"
        mqtt_client.publish_button_discovery(
            button_id=button_id,
            name=button_name,
            command_topic=button_topic,
            username=username,
            device_name=device_name,
            device_identifier=device_id,
            icon=icon,
        )

    # Input Text
    input_state_topic = f"homeassistant/text/{mqtt_client.topic_prefix}_{username}_manual_numbers/state"
    input_command_topic = f"homeassistant/text/{mqtt_client.topic_prefix}_{username}_manual_numbers/set"

    mqtt_client.publish_input_text_discovery(
        input_id="manual_numbers",
        name="로또 수동 구매 번호 (쉼표 구분, 자동은 auto)",
        state_topic=input_state_topic,
        command_topic=input_command_topic,
        username=username,
        device_name=device_name,
        device_identifier=device_id,
        icon="mdi:numeric",
        mode="text",
    )

    mqtt_client.client.publish(input_state_topic, account.manual_numbers_state or "auto,auto,auto,auto,auto,auto", qos=1, retain=True)

    # 연금복권 수동 구매 입력(조,번호). 로또 수동입력과 별도 엔티티로 혼동 방지.
    if config.get("enable_pension720", True):
        pm_state_topic = f"homeassistant/text/{mqtt_client.topic_prefix}_{username}_pension_manual/state"
        pm_command_topic = f"homeassistant/text/{mqtt_client.topic_prefix}_{username}_pension_manual/set"
        mqtt_client.publish_input_text_discovery(
            input_id="pension_manual",
            name="연금복권 수동 구매 번호 (조,번호 예: 1,123456)",
            state_topic=pm_state_topic,
            command_topic=pm_command_topic,
            username=username,
            device_name=device_name,
            device_identifier=device_id,
            icon="mdi:numeric",
            mode="text",
        )
        mqtt_client.client.publish(pm_state_topic, account.pension_manual_state or "", qos=1, retain=True)

    logger.info(f"[BUTTON][{username}] All buttons registered")


def on_button_command(client_mqtt, userdata, message):
    """Handle MQTT button commands"""
    try:
        topic = message.topic
        payload = message.payload.decode()

        logger.info(f"[MQTT] Received: topic={topic}, payload={payload}")

        parts = topic.split("/")
        if len(parts) < 3:
            return

        entity_id_full = parts[2]

        if not entity_id_full.startswith(mqtt_client.topic_prefix + "_"):
            return

        without_prefix = entity_id_full[len(mqtt_client.topic_prefix) + 1:]

        username = None
        for acc_username in accounts.keys():
            if without_prefix.startswith(acc_username + "_"):
                username = acc_username
                break

        if not username or username not in accounts:
            return

        account = accounts[username]

        # Input text (로또 수동번호 / 연금 수동번호 구분)
        if "/text/" in topic and "/set" in topic:
            text_id = without_prefix[len(username) + 1:]  # manual_numbers | pension_manual
            if text_id == "pension_manual":
                logger.info(f"[INPUT][{username}] Pension manual updated: {payload}")
                account.pension_manual_state = payload
                state_topic = f"homeassistant/text/{mqtt_client.topic_prefix}_{username}_pension_manual/state"
            else:
                logger.info(f"[INPUT][{username}] Manual numbers updated: {payload}")
                account.manual_numbers_state = payload
                state_topic = f"homeassistant/text/{mqtt_client.topic_prefix}_{username}_manual_numbers/state"
            client_mqtt.publish(state_topic, payload, qos=1, retain=True)
            return

        # Button
        button_suffix = without_prefix[len(username) + 1:]
        logger.info(f"[BUTTON][{username}] Button pressed: {button_suffix}")

        # Handle random number generation button
        if button_suffix == "generate_random":
            logger.info(f"[RANDOM][{username}] Generating random numbers")
            random_numbers = DhLottoAnalyzer.generate_random_numbers(6)
            random_str = ",".join(map(str, random_numbers))
            logger.info(f"[RANDOM][{username}] Generated: {random_str}")

            # Update manual_numbers_state
            account.manual_numbers_state = random_str

            # Publish to input_text state topic
            state_topic = f"homeassistant/text/{mqtt_client.topic_prefix}_{username}_manual_numbers/state"
            client_mqtt.publish(state_topic, random_str, qos=1, retain=True)

            logger.info(f"[RANDOM][{username}] Random numbers published to input text")
            return


        # 연금복권 수동 UI 진단 (구매 안 함, 안전)
        if button_suffix == "diag_pension_manual":
            if event_loop and event_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    execute_pension_diagnose(account), event_loop
                )
            return

        # 연금복권 수동 구매 (조,번호 입력값 사용) — 반드시 auto 분기보다 먼저 처리
        if button_suffix == "buy_pension_manual":
            if event_loop and event_loop.is_running():
                event_loop.call_soon_threadsafe(_start_action, account, "pension_manual", "button")
            return

        # 연금복권 자동 구매 버튼 라우팅 (buy_pension_auto_1 / buy_pension_auto_5)
        if button_suffix.startswith("buy_pension"):
            pension_action = "pension_auto_5" if button_suffix.endswith("_5") else "pension_auto_1"
            if event_loop and event_loop.is_running():
                event_loop.call_soon_threadsafe(_start_action, account, pension_action, "button")
            return

        lotto_action = {"buy_auto_1": "lotto_auto_1", "buy_auto_5": "lotto_auto_5",
                        "buy_manual": "lotto_manual"}.get(button_suffix)
        if event_loop and event_loop.is_running():
            if lotto_action:
                event_loop.call_soon_threadsafe(_start_action, account, lotto_action, "button")
            else:
                asyncio.run_coroutine_threadsafe(
                    execute_button_purchase(account, button_suffix),
                    event_loop
                )

    except Exception as e:
        logger.error(f"[MQTT] Error: {e}", exc_info=True)


async def _pension_latest_round() -> int:
    """연금복권 최신 추첨 회차를 모바일 조회 API로 가져온다(구매 회차 = +1 계산용)."""
    async with DhMobileApiClient() as mobile:
        draw = await mobile.async_get_pension_latest_draw()
    return _safe_int(draw.get("round_no"))


async def execute_pension_purchase(account: AccountData, count: int):
    """연금복권720+ 자동 구매를 실행한다 (1매 또는 5매)."""
    username = account.username
    button_id = f"buy_pension_auto_{count}"
    logger.info(f"[PENSION][{username}] Starting purchase: {count} ticket(s)")

    # 버튼 중복 실행 방지: 동일 계정+버튼 15초 이내 재호출 시 스킵
    key = (username, button_id)
    now = time.monotonic()
    if key in _last_purchase_time and (now - _last_purchase_time[key]) < 15:
        logger.warning(f"[PENSION][{username}] Ignored duplicate press: {button_id} (within 15s)")
        return
    _last_purchase_time[key] = now

    if not account.pension:
        logger.error(f"[PENSION][{mask_username(username)}] Pension720 not enabled")
        return

    reason = _budget_block_reason(account, count * 1000)
    if reason:
        logger.warning(f"[PENSION][{mask_username(username)}] 월 예산 초과로 구매 안 함")
        await publish_sensor_for_account(account, "pension720_purchase_error", reason[:255], {
            "error": reason, "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류", "icon": "mdi:wallet-outline",
        })
        return

    # 1일 구매 상한선(Hard Limit) 검증 (오구매/예치금 소진 방지)
    try:
        pension_daily_tracker.check_allowed(username, count)
    except PurchaseGuardError as e:
        logger.warning(f"[PENSION][{mask_username(username)}] Blocked by daily hard limit: {e}")
        await publish_sensor_for_account(account, "pension720_purchase_error", str(e)[:255], {
            "error": str(e),
            "daily_limit": DAILY_PENSION_LIMIT,
            "today_count": pension_daily_tracker.get_today_count(username),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:shield-alert",
        })
        return

    try:
        purchase_guard.acquire(username)
    except PurchaseCooldownError as e:
        logger.warning(f"[PENSION][{mask_username(username)}] Blocked by inter-account cooldown: {e}")
        await publish_sensor_for_account(account, "pension720_purchase_error", str(e)[:255], {
            "error": str(e),
            "remaining_seconds": round(e.remaining_seconds, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:timer-sand",
        })
        return

    purchase_attempted = False
    try:
        # 헤드리스 브라우저가 구매 시작 시 자체 로그인하므로 HTTP 선로그인은 불필요.
        # 브라우저가 멈춰도 버튼이 영원히 매달리지 않도록 전체 타임아웃(180s)을 건다.
        purchase_attempted = True
        _note_spend(account, count * 1000)
        result = await asyncio.wait_for(
            account.pension.async_buy_auto(count), timeout=180
        )
        extra = result.get("extra_tickets") or []
        # 하루 한도는 보수적으로: 화면에 더 보인 티켓까지 센다
        pension_daily_tracker.record_purchase(username, result.get("count", count) + len(extra))
        round_label = f"{result['round']}회" if result['round'] else "최신회차"
        logger.info(
            f"[PENSION][{mask_username(username)}] Success! round {result['round']}, "
            f"{result['count']} ticket(s), {result['amount']} KRW"
        )
        await publish_sensor_for_account(
            account, "pension720_last_purchase",
            f"{round_label} {result['count']}매 ({result['numbers']})",
            {
                "round": result["round"],
                "count": result["count"],
                "amount": result["amount"],
                "numbers": result["numbers"],
                "friendly_name": "연금복권 최근 구매",
                "icon": "mdi:cash-check",
            },
        )
        # 성공 시 과거 오류 센서 해제. 요청보다 많은 티켓이 보이면 경고로 남긴다(숨기지 않음).
        warn = extra_ticket_warning(count, extra)
        if warn:
            logger.error(f"[PENSION][{mask_username(username)}] {warn}")
        await publish_sensor_for_account(account, "pension720_purchase_error", warn or "없음", {
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:alert" if warn else "mdi:cart-check",
        })
        await _refresh_pension_history_after_purchase(account)
    except asyncio.TimeoutError:
        # 180초 안에 안 끝남 = 구매 도중일 수 있음(이중 지출 위험) → 확인 요망.
        msg = ("구매 시간 초과(180초): 브라우저가 응답하지 않습니다. 구매가 진행됐을 수 "
               "있으니 동행복권 구매내역을 확인한 뒤 재시도하세요.")
        logger.error(f"[PENSION][{username}] Timeout — {msg}")
        await publish_sensor_for_account(account, "pension720_purchase_error", ("⚠️ " + msg)[:255], {
            "error": "timeout", "uncertain": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:alert",
        })
    except DhPensionBrowserError as e:
        # uncertain=True 면 doOrder 이후 확인 실패 → 실제 구매됐을 수 있음.
        uncertain = getattr(e, "uncertain", False)
        prefix = "⚠️ 확인필요: " if uncertain else ""
        logger.error(f"[PENSION][{username}] Purchase failed (uncertain={uncertain}): {e}")
        await publish_sensor_for_account(account, "pension720_purchase_error", (prefix + str(e))[:255], {
            "error": str(e), "uncertain": uncertain,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:alert" if uncertain else "mdi:cart-alert",
        })
    except Exception as e:
        logger.error(f"[PENSION][{username}] Purchase failed: {e}", exc_info=True)
        await publish_sensor_for_account(account, "pension720_purchase_error", str(e)[:255], {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:cart-alert",
        })
    finally:
        purchase_guard.release(username, record_cooldown=purchase_attempted)


async def _refresh_pension_history_after_purchase(account: AccountData):
    """구매 성공 직후 연금 구매내역 센서를 갱신한다(다음 주기까지 기다리지 않도록).

    HTTP 세션으로 원장을 조회하므로 필요하면 재로그인한다. 실패해도 구매 결과에는 영향 없음.
    """
    try:
        if account.client and not account.client.logged_in:
            await account.client.async_login()
        await publish_pension_history_sensors(account)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[PENSION-HIST][{mask_username(account.username)}] 구매 후 내역 갱신 실패: {e}")


def _parse_pension_manual(text):
    """'조,번호' 입력을 (조_raw, 번호_raw) 로 분해. 형식 오류면 ValueError.

    구분자는 쉼표 우선, 없으면 공백. 숫자 유효성은 validate_manual_selection 담당.
    """
    s = (text or "").strip()
    if not s:
        raise ValueError(
            "연금복권 수동 구매 번호가 비어 있습니다. '조,번호' 형식으로 "
            "입력하세요 (예: 1,123456)"
        )
    parts = [p.strip() for p in s.split(",")] if "," in s else s.split()
    if len(parts) != 2:
        raise ValueError(
            f"형식 오류: '조,번호'로 입력하세요 (예: 1,123456). 입력값: {text!r}"
        )
    return parts[0], parts[1]


async def execute_pension_manual_purchase(account: AccountData):
    """연금복권720+ 수동 번호(조,번호) 1매 구매. 입력은 account.pension_manual_state."""
    username = account.username
    button_id = "buy_pension_manual"
    logger.info(f"[PENSION][{username}] Starting MANUAL purchase")

    key = (username, button_id)
    now = time.monotonic()
    if key in _last_purchase_time and (now - _last_purchase_time[key]) < 15:
        logger.warning(f"[PENSION][{username}] Ignored duplicate press: {button_id} (within 15s)")
        return
    _last_purchase_time[key] = now

    if not account.pension:
        logger.error(f"[PENSION][{username}] Pension720 not enabled")
        return

    # 입력 파싱·검증은 브라우저 기동 전에(잘못된 입력이면 즉시 알림, 돈·시간 낭비 방지).
    try:
        g_raw, d_raw = _parse_pension_manual(account.pension_manual_state)
        group, digits = validate_manual_selection(g_raw, d_raw)
    except (ValueError, DhPensionBrowserError) as e:
        logger.error(f"[PENSION][{username}] Manual input invalid: {e}")
        await publish_sensor_for_account(account, "pension720_purchase_error", ("입력오류: " + str(e))[:255], {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:form-textbox",
        })
        return

    reason = _budget_block_reason(account, 1000)
    if reason:
        logger.warning(f"[PENSION][{mask_username(username)}] 월 예산 초과로 수동 구매 안 함")
        await publish_sensor_for_account(account, "pension720_purchase_error", reason[:255], {
            "error": reason, "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류", "icon": "mdi:wallet-outline",
        })
        return

    # 1일 구매 상한선(Hard Limit) 검증 (오구매/예치금 소진 방지)
    try:
        pension_daily_tracker.check_allowed(username, 1)
    except PurchaseGuardError as e:
        logger.warning(f"[PENSION][{mask_username(username)}] Manual blocked by daily hard limit: {e}")
        await publish_sensor_for_account(account, "pension720_purchase_error", str(e)[:255], {
            "error": str(e),
            "daily_limit": DAILY_PENSION_LIMIT,
            "today_count": pension_daily_tracker.get_today_count(username),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:shield-alert",
        })
        return

    try:
        purchase_guard.acquire(username)
    except PurchaseCooldownError as e:
        logger.warning(f"[PENSION][{mask_username(username)}] Blocked by inter-account cooldown: {e}")
        await publish_sensor_for_account(account, "pension720_purchase_error", str(e)[:255], {
            "error": str(e),
            "remaining_seconds": round(e.remaining_seconds, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:timer-sand",
        })
        return

    purchase_attempted = False
    try:
        purchase_attempted = True
        _note_spend(account, 1000)
        result = await asyncio.wait_for(
            account.pension.async_buy_manual(group, digits), timeout=180
        )
        extra = result.get("extra_tickets") or []
        pension_daily_tracker.record_purchase(username, result.get("count", 1) + len(extra))
        round_label = f"{result['round']}회" if result['round'] else "최신회차"
        logger.info(f"[PENSION][{mask_username(username)}] Manual success! {result['numbers']}")
        await publish_sensor_for_account(
            account, "pension720_last_purchase",
            f"{round_label} 수동 1매 ({result['numbers']})",
            {
                "round": result["round"],
                "count": result["count"],
                "amount": result["amount"],
                "numbers": result["numbers"],
                "mode": "manual",
                "friendly_name": "연금복권 최근 구매",
                "icon": "mdi:cash-check",
            },
        )
        warn = extra_ticket_warning(1, extra)
        if warn:
            logger.error(f"[PENSION][{mask_username(username)}] {warn}")
        await publish_sensor_for_account(account, "pension720_purchase_error", warn or "없음", {
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:alert" if warn else "mdi:cart-check",
        })
        await _refresh_pension_history_after_purchase(account)
    except asyncio.TimeoutError:
        msg = ("수동 구매 시간 초과(180초): 브라우저가 응답하지 않습니다. 구매가 진행됐을 수 "
               "있으니 동행복권 구매내역을 확인한 뒤 재시도하세요.")
        logger.error(f"[PENSION][{username}] Manual timeout — {msg}")
        await publish_sensor_for_account(account, "pension720_purchase_error", ("⚠️ " + msg)[:255], {
            "error": "timeout", "uncertain": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:alert",
        })
    except DhPensionBrowserError as e:
        uncertain = getattr(e, "uncertain", False)
        prefix = "⚠️ 확인필요: " if uncertain else ""
        logger.error(f"[PENSION][{username}] Manual purchase failed (uncertain={uncertain}): {e}")
        await publish_sensor_for_account(account, "pension720_purchase_error", (prefix + str(e))[:255], {
            "error": str(e), "uncertain": uncertain,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:alert" if uncertain else "mdi:cart-alert",
        })
    except Exception as e:
        logger.error(f"[PENSION][{username}] Manual purchase failed: {e}", exc_info=True)
        await publish_sensor_for_account(account, "pension720_purchase_error", str(e)[:255], {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:cart-alert",
        })
    finally:
        purchase_guard.release(username, record_cooldown=purchase_attempted)


async def execute_pension_diagnose(account: AccountData):
    """수동 구매 UI 구조 진단(구매 안 함, 안전). 덤프를 센서(attribute)·로그로 노출."""
    username = account.username
    key = (username, "diag_pension_manual")
    now = time.monotonic()
    if key in _last_purchase_time and (now - _last_purchase_time[key]) < 15:
        logger.warning(f"[PENSION][{username}] Ignored duplicate diag press (within 15s)")
        return
    _last_purchase_time[key] = now

    if not account.pension:
        logger.error(f"[PENSION][{username}] Pension720 not enabled")
        return

    # 수동번호가 입력돼 있으면 조+번호까지 넣고 doVerify 까지 진단(구매 안 함).
    g = d = None
    try:
        g_raw, d_raw = _parse_pension_manual(account.pension_manual_state)
        g, d = validate_manual_selection(g_raw, d_raw)
    except Exception:
        g = d = None  # 입력 없거나 형식 오류 → 팝업 구조만 진단

    logger.info(f"[PENSION][{username}] Manual UI diagnose start (num={g}조{d})")
    try:
        result = await asyncio.wait_for(
            account.pension.async_diagnose_manual(g, d), timeout=120
        )
        dump = result.get("dump", "")
        stage = result.get("stage", "")
        logger.info(f"[PENSION][{username}] DIAG stage={stage} dump >>> {dump}")
        await publish_sensor_for_account(account, "pension720_manual_diag", "완료", {
            "dump": dump,
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 수동 UI 진단",
            "icon": "mdi:bug-check",
        })
    except Exception as e:
        logger.error(f"[PENSION][{username}] Diagnose failed: {e}", exc_info=True)
        await publish_sensor_for_account(account, "pension720_manual_diag", ("실패: " + str(e))[:255], {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "연금복권 수동 UI 진단",
            "icon": "mdi:bug",
        })


async def execute_button_purchase(account: AccountData, button_id: str):
    """Execute purchase for account. 수동 1게임은 정확히 1장만 구매."""
    username = account.username
    logger.info(f"[PURCHASE][{username}] Starting purchase: {button_id}")

    # 버튼 중복 실행 방지: 동일 계정+버튼 15초 이내 재호출 시 스킵
    key = (username, button_id)
    now = time.monotonic()
    if key in _last_purchase_time and (now - _last_purchase_time[key]) < 15:
        logger.warning(f"[PURCHASE][{username}] Ignored duplicate press: {button_id} (within 15s)")
        return

    if not account.lotto_645:
        logger.error(f"[PURCHASE][{username}] Lotto 645 not enabled")
        return

    # 1) 수동 입력 로컬 검증 (형식 오류 시 쿨다운을 불필요하게 소모하지 않음)
    manual_slots = None
    if button_id == "buy_manual":
        manual_numbers_text = account.manual_numbers_state
        if not manual_numbers_text:
            await publish_purchase_error(account, "Please enter manual numbers")
            return

        try:
            parts = [p.strip() for p in manual_numbers_text.split(",")]
            if len(parts) != 6:
                await publish_purchase_error(account, f"Must provide 6 values (got {len(parts)})")
                return

            manual_numbers = []
            auto_count = 0

            for part in parts:
                if part.lower() == "auto":
                    auto_count += 1
                else:
                    try:
                        num = int(part)
                        if num <= 0 or num >= 46:
                            await publish_purchase_error(account, f"Numbers must be 1-45 (got {num})")
                            return
                        manual_numbers.append(num)
                    except ValueError:
                        await publish_purchase_error(account, f"Invalid input: {part}")
                        return

            if len(manual_numbers) != len(set(manual_numbers)):
                await publish_purchase_error(account, "Duplicate numbers")
                return

            if auto_count == 0:
                mode = DhLotto645SelMode.MANUAL
                final_numbers = sorted(manual_numbers)
            elif auto_count == 6:
                mode = DhLotto645SelMode.AUTO
                final_numbers = []
            else:
                mode = DhLotto645SelMode.SEMI_AUTO
                final_numbers = sorted(manual_numbers)

            manual_slots = [DhLotto645.Slot(mode=mode, numbers=final_numbers)]  # 수동 1게임 = 1슬롯

        except Exception as e:
            await publish_purchase_error(account, f"Error: {str(e)}")
            return

    reason = _budget_block_reason(account, 1000 if button_id in ("buy_manual", "buy_auto_1") else WEEKLY_LOTTO_LIMIT * 1000)
    if reason:
        logger.warning(f"[PURCHASE][{mask_username(username)}] 월 예산 초과로 구매 안 함")
        await publish_purchase_error(account, reason)
        return

    # 2) 다중 계정 동시 구매 차단 및 계정 간 20초 쿨다운 검사
    try:
        purchase_guard.acquire(username)
    except PurchaseCooldownError as e:
        logger.warning(f"[PURCHASE][{username}] Blocked by inter-account cooldown: {e}")
        await publish_purchase_error(account, str(e))
        return

    purchase_attempted = False
    try:
        if button_id == "buy_manual":
            slots = manual_slots
        else:
            if button_id == "buy_auto_5":
                buy_list = await account.client.async_get_buy_list('LO40')
                weekly_count = calculate_weekly_bought_count(buy_list)
                if weekly_count >= 1:
                    await publish_purchase_error(
                        account,
                        "5게임 자동 구매는 이번 주 미구매 시에만 가능합니다. (이미 구매: {}장)".format(weekly_count),
                    )
                    return
                count = WEEKLY_LOTTO_LIMIT
            else:
                count = 1  # buy_auto_1
            slots = [DhLotto645.Slot(mode=DhLotto645SelMode.AUTO, numbers=[]) for _ in range(count)]

        max_games = 1 if button_id in ("buy_manual", "buy_auto_1") else WEEKLY_LOTTO_LIMIT  # 1계정 주간 최대 5게임
        logger.info(f"[PURCHASE][{username}] Executing: {len(slots)} game(s)")
        purchase_attempted = True
        _note_spend(account, len(slots) * 1000)
        result = await account.lotto_645.async_buy(slots, max_games=max_games)

        logger.info(f"[PURCHASE][{username}] Success! Round: {result.round_no}")
        _last_purchase_time[(username, button_id)] = time.monotonic()
        # 구매 후 구매정보 조회까지 완료한 뒤 20초 쿨다운이 시작되도록 락 유지 상태에서 갱신
        await update_sensors_for_account(account)

    except DhLotto645Error as e:
        # 주간 한도 등 예상 가능한 구매 오류: 트레이스백 없이 로그 후 MQTT 센서로 전달
        logger.warning(f"[PURCHASE][{username}] Purchase rejected: {e}")
        await publish_purchase_error(account, str(e))
    except Exception as e:
        logger.error(f"[PURCHASE][{username}] Failed: {e}", exc_info=True)
        await publish_purchase_error(account, str(e))
    finally:
        purchase_guard.release(username, record_cooldown=purchase_attempted)


async def publish_purchase_error(account: AccountData, error_message: str):
    """Publish purchase error"""
    error_data = {
        "error": error_message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "friendly_name": "로또 구매 오류",
        "icon": "mdi:alert-circle",
    }
    await publish_sensor_for_account(account, "lotto45_purchase_error", error_message[:255], error_data)


async def init_account(account: AccountData) -> bool:
    """Initialize account"""
    username = account.username

    if not account.enabled:
        logger.info(f"[INIT][{username}] Account disabled")
        return False

    try:
        logger.info(f"[INIT][{username}] Initializing...")
        account.client = DhLotteryClient(account.username, account.password)
        await account.client.async_login()

        if config["enable_lotto645"]:
            account.lotto_645 = DhLotto645(account.client)
            account.analyzer = DhLottoAnalyzer(account.client)
        if config.get("enable_pension720", True):
            account.pension = DhPensionBrowser(
                account.username,
                account.password,
                executable_path=os.getenv("CHROMIUM_PATH") or None,
                round_provider=_pension_latest_round,
            )

        logger.info(f"[INIT][{username}] Success")
        return True
    except Exception as e:
        logger.error(f"[INIT][{username}] Failed: {e}", exc_info=True)
        return False


async def init_clients():
    """Initialize all clients"""
    global mqtt_client

    load_accounts_from_env()
    # accounts 는 아래 루프에서 채워지므로 설정 목록으로 미리 별칭 필터를 건다
    # (대시보드와 같은 순서·같은 건너뛰기 규칙 → Account_N 번호 일치).
    install_log_alias_filter(configured_usernames(config["accounts"], MAX_ACCOUNTS))

    if not config["accounts"]:
        logger.error("No accounts configured")
        return False

    success_count = 0
    for acc_config in config["accounts"]:
        if len(accounts) >= MAX_ACCOUNTS:
            logger.warning(f"최대 허용 계정 수({MAX_ACCOUNTS}개)에 도달하여 추가 계정 초기화를 중단합니다.")
            break
        username = acc_config.get("username", "")
        password = acc_config.get("password", "")
        enabled = acc_config.get("enabled", True)

        if not username or not password:
            continue
        if username in accounts:
            logger.warning(f"[INIT][{username}] Duplicate username skipped")
            continue

        account = AccountData(username, password, enabled)
        accounts[username] = account

        if await init_account(account):
            success_count += 1

    logger.info(f"Initialized {success_count}/{len(accounts)} account(s)")
    try:
        restored = _load_sensor_cache()
        if restored:
            logger.info(f"[CACHE] 지난 센서 값 {restored}개를 불러왔습니다(새로 조회되면 갱신)")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[CACHE] 지난 센서 값을 불러오지 못했습니다: {e}")

    # MQTT
    if config["use_mqtt"]:
        logger.info("Initializing MQTT...")

        client_id_suffix = "_beta" if config["is_beta"] else ""
        mqtt_client = MQTTDiscovery(
            mqtt_url=os.getenv("MQTT_URL") or "mqtt://core-mosquitto:1883",
            username=os.getenv("MQTT_USERNAME"),
            password=os.getenv("MQTT_PASSWORD"),
            client_id_suffix=client_id_suffix,
        )

        # 연결·재연결될 때마다 버튼 등록·명령 구독·센서 재발행(_mqtt_on_ready). 처음에 브로커가 아직
        # 안 떠 있어도(HA 재부팅) 백그라운드 재시도로 연결되면 그때 자동으로 설정된다.
        mqtt_client.on_ready = _mqtt_ready_from_thread
        if mqtt_client.connect(wait=10):
            logger.info("MQTT connected")
        else:
            logger.warning(
                "MQTT 브로커에 아직 연결되지 않았습니다. 연결되면 센서·버튼이 자동으로 만들어집니다. "
                "Mosquitto broker 애드온이 실행 중인지, MQTT 통합이 추가돼 있는지 확인하세요."
            )

    return success_count > 0


SENSOR_CACHE_FILE = "sensor_cache.json"
_cache_save_task = None


def _account_key(username: str) -> str:
    """캐시 파일의 계정 키(실제 아이디 대신 해시)."""
    import hashlib
    return hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]


def _save_sensor_cache() -> None:
    """마지막 센서 값을 /data 에 저장(재시작 직후에도 대시보드가 비지 않게)."""
    data = {
        _account_key(u): {k: v for k, v in a.sensor_cache.items() if k not in _DASHBOARD_EXCLUDED_SENSORS}
        for u, a in accounts.items()
    }
    _write_json(SENSOR_CACHE_FILE, {"v": 1, "saved": time.time(), "accounts": data})


def _load_sensor_cache() -> int:
    """저장된 센서 값을 계정 캐시에 채운다. 채운 항목 수 반환."""
    raw = _read_json(SENSOR_CACHE_FILE, {})
    saved = raw.get("accounts") if isinstance(raw, dict) else None
    if not isinstance(saved, dict):
        return 0
    n = 0
    for u, a in accounts.items():
        cached = saved.get(_account_key(u))
        if not isinstance(cached, dict):
            continue
        for k, v in cached.items():
            if isinstance(v, dict) and "state" in v and k not in a.sensor_cache:
                a.sensor_cache[k] = v
                n += 1
    return n


def _schedule_cache_save() -> None:
    """센서가 바뀌면 30초 뒤 한 번 저장(잦은 디스크 쓰기 방지)."""
    global _cache_save_task
    if _cache_save_task is not None and not _cache_save_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def later():
        await asyncio.sleep(30)
        try:
            _save_sensor_cache()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[CACHE] 저장 실패: {e}")

    _cache_save_task = loop.create_task(later())


def _mqtt_ready_from_thread() -> None:
    """paho 스레드에서 불림 → 이벤트 루프에서 설정 작업 실행."""
    if event_loop and event_loop.is_running():
        asyncio.run_coroutine_threadsafe(_mqtt_on_ready(), event_loop)


_mqtt_ready_lock = asyncio.Lock()


async def _mqtt_on_ready() -> None:
    """MQTT 연결(재연결) 직후: 버튼·입력 엔티티 등록, 명령 구독, 마지막 센서 값 재발행."""
    if not mqtt_client or not mqtt_client.connected:
        return
    async with _mqtt_ready_lock:
        mqtt_client.client.on_message = on_button_command
        for account in accounts.values():
            if not account.enabled:
                continue
            if config["enable_lotto645"] and account.client and account.client.logged_in:
                await register_buttons_for_account(account)
            button_ids = ["buy_auto_1", "buy_auto_5", "buy_manual", "generate_random"]
            text_ids = ["manual_numbers"]
            if config.get("enable_pension720", True):
                button_ids += ["buy_pension_auto_1", "buy_pension_auto_5", "buy_pension_manual", "diag_pension_manual"]
                text_ids.append("pension_manual")
            for button_id in button_ids:
                mqtt_client.subscribe(f"homeassistant/button/{mqtt_client.topic_prefix}_{account.username}_{button_id}/command")
            for text_id in text_ids:
                mqtt_client.subscribe(f"homeassistant/text/{mqtt_client.topic_prefix}_{account.username}_{text_id}/set")
            # 끊겨 있던 동안의 값을 HA 에 바로 반영
            for entity_id, item in list(account.sensor_cache.items()):
                try:
                    await publish_sensor_mqtt(mqtt_client=mqtt_client, entity_id=entity_id, state=item.get("state"),
                                              username=account.username, attributes=item.get("attributes") or {})
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"[MQTT] 재발행 실패 {entity_id}: {e}")
        logger.info(f"[MQTT] 연결 후 설정 완료(구독 {len(mqtt_client.subscriptions)}개, 계정 {len(accounts)}개)")


async def cleanup_clients():
    """Cleanup"""
    global mqtt_client

    if mqtt_client:
        try:
            mqtt_client.disconnect()
        except:
            pass

    for account in accounts.values():
        if account.client:
            try:
                await account.client.close()
            except:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle"""
    global event_loop

    logger.info(f"Starting v{APP_VERSION} Multi-Account...")

    event_loop = asyncio.get_running_loop()
    await init_clients()

    tasks = []
    for account in accounts.values():
        if account.enabled:
            task = asyncio.create_task(background_tasks_for_account(account))
            account.update_task = task
            tasks.append(task)

    tasks.append(asyncio.create_task(auto_buy_loop()))
    logger.info("Started")

    yield

    logger.info("Shutting down...")
    try:
        _save_sensor_cache()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[CACHE] 종료 시 저장 실패: {e}")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await cleanup_clients()


app = FastAPI(title="Lotto 45 Multi", version=APP_VERSION, lifespan=lifespan)

# CORS: 모바일 앱 및 외부/Ingress 접근 지원
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # 자격증명(쿠키) 허용 안 함: 다른 사이트가 사용자의 HA 세션으로 이 API 를 부르거나
    # 응답을 읽지 못하게 한다(allow_origins="*" + credentials 는 출처를 그대로 반사해 위험).
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Ingress-Request"],
)


# 대시보드 이미지(최적화된 WebP). 상대 경로(static/…)라 Ingress 에서도 그대로 동작한다.
from fastapi.staticfiles import StaticFiles  # noqa: E402

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


def is_ingress_request(request: Request) -> bool:
    """Home Assistant Ingress 경유 접근 여부 (Supervisor가 설정하는 헤더로 판단)"""
    return (
        request.headers.get("X-Remote-User-Id") is not None
        or request.headers.get("X-Remote-User-Name") is not None
    )


async def background_tasks_for_account(account: AccountData):
    """Background tasks. 구매 불가 시간대에는 전체 동기화 스킵, 이전 회차 당첨 결과만 1회 동기화.

    서버 부하 분산을 위해 초기 대기 및 폴링 주기에 랜덤 지터(Jitter)를 적용한다.
    """
    username = account.username
    masked = mask_username(username)

    if not account.client or not account.client.logged_in:
        logger.warning(f"[BG][{masked}] Skipping background task - not logged in")
        return

    await asyncio.sleep(random.uniform(5.0, 30.0))
    was_purchase_available = True

    while True:
        try:
            purchase_available_now = is_purchase_available_now()
            if not purchase_available_now:
                was_purchase_available = False
                # 연금은 이 시간에도 팔리고, 재시작 직후엔 화면이 비어 있으므로 예치금·구매 내역을 한 번 읽는다.
                if not account.closed_snapshot_done:
                    try:
                        await update_sensors_for_account(account, force=True)
                        account.closed_snapshot_done = bool(account.client and account.client.logged_in)
                        if account.closed_snapshot_done:
                            logger.info(f"[BG][{masked}] 구매 불가 시간 — 예치금·구매 내역을 한 번 조회했습니다(읽기 전용)")
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"[BG][{masked}] 구매 불가 시간 조회 실패(다음 주기에 재시도): {e}")
                # 구매 불가 시간대: 이전 회차 당첨 결과 1회만 동기화 (추첨 후 바로 확인용)
                if not account.prev_round_result_synced_when_unavailable:
                    try:
                        await update_prev_round_result_sensors_for_account(account)
                        account.prev_round_result_synced_when_unavailable = True
                        logger.info(f"[BG][{masked}] Prev-round result sync done (once per unavailable period)")
                    except Exception as e:
                        logger.warning(f"[BG][{masked}] Prev-round result sync failed: {e}")
                else:
                    logger.info(f"[BG][{masked}] Skipping sync (purchase unavailable time, KST)")
                await asyncio.sleep(compute_poll_delay(config["update_interval"]))
                continue
            # 구매 가능 시간대: 플래그 리셋, 전체 동기화
            if not was_purchase_available:
                account.prev_round_result_synced_when_unavailable = False
                account.closed_snapshot_done = False
            was_purchase_available = True
            await update_sensors_for_account(account)
            await asyncio.sleep(compute_poll_delay(config["update_interval"]))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[BG][{masked}] Error: {e}", exc_info=True)
            await asyncio.sleep(60)


def _ltwn_result_to_icon_color(ltwn_result: str) -> tuple[str, str]:
    """selectMyLotteryledger API의 ltWnResult를 아이콘/색상으로 매핑."""
    if not ltwn_result:
        return "mdi:circle-outline", "grey"
    r = ltwn_result.strip()
    if "1등" in r:
        return "mdi:trophy", "gold"
    if "2등" in r:
        return "mdi:medal", "silver"
    if "3등" in r:
        return "mdi:medal-outline", "bronze"
    if "4등" in r:
        return "mdi:currency-krw", "blue"
    if "5등" in r:
        return "mdi:cash", "green"
    if "낙첨" in r:
        return "mdi:close-circle-outline", "red"
    return "mdi:clock-outline", "grey"


async def update_prev_round_result_sensors_for_account(account: AccountData):
    """
    이전 회차(추첨 완료 회차) 구매내역 및 당첨결과 센서만 동기화.
    lotto645TicketDetail.do의 game_dtl[].rank + drawed 기반 결과 사용.
    구매 불가 시간대(토요일 20:00~일요일 06:00)에 1회만 호출.
    """
    username = account.username
    if not config["enable_lotto645"] or not account.lotto_645:
        return

    if not account.client:
        return
    if not account.client.logged_in:
        try:
            await account.client.async_login()
        except Exception as e:
            logger.warning(f"[PREV_ROUND][{username}] Login failed: {e}")
            return

    try:
        prev_round_no, history = await account.lotto_645.async_get_prev_drawn_round_and_history()
        if prev_round_no == 0 or not history:
            await publish_sensor_for_account(account, "lotto45_prev_round", 0, {
                "friendly_name": "로또 구매 회차 (이전)",
                "icon": "mdi:counter",
            })
            for i in range(1, 6):
                await publish_sensor_for_account(account, f"lotto45_prev_game_{i}", "구매 내역 없음", {
                    "slot": "-", "슬롯": "-", "mode": "-", "선택": "-",
                    "numbers": [], "round_no": 0, "result": "-",
                    "friendly_name": f"로또 구매 게임 {i} (이전)", "icon": f"mdi:numeric-{i}-box-outline",
                })
                await publish_sensor_for_account(account, f"lotto45_prev_game_{i}_result", "구매 내역 없음", {
                    "round_no": 0, "my_numbers": [], "winning_numbers": [], "bonus_number": 0,
                    "matching_count": 0, "bonus_match": False, "rank": 0, "result": "구매 내역 없음", "color": "grey",
                    "friendly_name": f"로또 구매 게임 {i} (이전) 결과", "icon": "mdi:circle-outline",
                })
            return

        await publish_sensor_for_account(account, "lotto45_prev_round", prev_round_no, {
            "friendly_name": "로또 구매 회차 (이전)",
            "icon": "mdi:counter",
        })

        all_games: list[dict] = []
        for purchase in history:
            for gd in purchase.game_details:
                all_games.append({
                    "game": gd["game"],
                    "round_no": purchase.round_no,
                    "result": _rank_drawed_to_result(gd["rank"], gd["drawed"]),
                })
                if len(all_games) >= 5:
                    break
            if len(all_games) >= 5:
                break

        winning_data = await account.lotto_645.async_get_round_info(prev_round_no)

        for i in range(1, 6):
            if i <= len(all_games):
                game_info = all_games[i - 1]
                game = game_info["game"]
                round_no = game_info["round_no"]
                ltwn_result = game_info["result"] or "낙첨"
                numbers_str = ", ".join(map(str, game.numbers))
                result_icon, result_color = _ltwn_result_to_icon_color(ltwn_result)

                await publish_sensor_for_account(account, f"lotto45_prev_game_{i}", numbers_str, {
                    "slot": game.slot,
                    "슬롯": game.slot,
                    "mode": str(game.mode),
                    "선택": str(game.mode),
                    "numbers": game.numbers,
                    "round_no": round_no,
                    "result": ltwn_result,
                    "friendly_name": f"로또 구매 게임 {i} (이전)",
                    "icon": f"mdi:numeric-{i}-box-multiple",
                })
                await publish_sensor_for_account(account, f"lotto45_prev_game_{i}_result", ltwn_result, {
                    "round_no": round_no,
                    "my_numbers": game.numbers,
                    "winning_numbers": winning_data.numbers,
                    "bonus_number": winning_data.bonus_num,
                    "result": ltwn_result,
                    "color": result_color,
                    "friendly_name": f"로또 구매 게임 {i} (이전) 결과",
                    "icon": result_icon,
                })
            else:
                await publish_sensor_for_account(account, f"lotto45_prev_game_{i}", "구매 내역 없음", {
                    "slot": "-", "슬롯": "-", "mode": "-", "선택": "-",
                    "numbers": [], "round_no": 0, "result": "-",
                    "friendly_name": f"로또 구매 게임 {i} (이전)",
                    "icon": f"mdi:numeric-{i}-box-outline",
                })
                await publish_sensor_for_account(account, f"lotto45_prev_game_{i}_result", "구매 내역 없음", {
                    "round_no": 0, "my_numbers": [], "winning_numbers": [], "bonus_number": 0,
                    "matching_count": 0, "bonus_match": False, "rank": 0, "result": "구매 내역 없음", "color": "grey",
                    "friendly_name": f"로또 구매 게임 {i} (이전) 결과",
                    "icon": "mdi:circle-outline",
                })

        logger.info(f"[PREV_ROUND][{username}] Prev-round sensors updated (round {prev_round_no}, games: {len(all_games)})")
    except Exception as e:
        logger.warning(f"[PREV_ROUND][{username}] Failed: {e}", exc_info=True)


async def publish_statistics_sensors(account: AccountData):
    """로그인 없이 가능한 통계 센서(Hot/Cold·최다출현)를 발행한다.

    모바일 조회 API(ma.dhlottery.co.kr)만 사용하므로 로그인 상태나 구매
    가능 시간대와 무관하게 동작한다.
    """
    username = account.username
    if not (config["enable_lotto645"] and account.analyzer):
        return
    try:
        hot_cold_data = await account.analyzer.async_get_hot_cold_numbers(recent_rounds=20)

        # Hot numbers sensor
        hot_numbers_str = ", ".join(map(str, hot_cold_data.hot_numbers))
        await publish_sensor_for_account(account, "lotto45_hot_numbers", hot_numbers_str, {
            "numbers": hot_cold_data.hot_numbers,
            "friendly_name": "로또 통계: 가장 많이 나온 번호 10개 (최근 20회)",
            "icon": "mdi:fire",
        })

        # Cold numbers sensor
        cold_numbers_str = ", ".join(map(str, hot_cold_data.cold_numbers))
        await publish_sensor_for_account(account, "lotto45_cold_numbers", cold_numbers_str, {
            "numbers": hot_cold_data.cold_numbers,
            "friendly_name": "로또 통계: 가장 적게 나온 번호 10개 (최근 20회)",
            "icon": "mdi:snowflake",
        })

        # Most frequent numbers sensor
        top_freq_str = "전체 누적: " + ", ".join([f"{nf.number}번({nf.count}번 출현)" for nf in hot_cold_data.most_frequent[:5]])
        await publish_sensor_for_account(account, "lotto45_most_frequent_numbers", top_freq_str, {
            "top_5": [{"number": nf.number, "count": nf.count, "percentage": nf.percentage}
                     for nf in hot_cold_data.most_frequent[:5]],
            "friendly_name": "로또 통계: 가장 많이 나온 번호 5개 (전체 누적)",
            "icon": "mdi:chart-bar",
        })

        logger.info(f"[SENSOR][{username}] Hot/Cold numbers updated")
    except Exception as e:
        logger.warning(f"[SENSOR][{username}] Failed to update hot/cold numbers: {e}")


async def publish_lottery_result_sensors(account: AccountData):
    """최신 회차 당첨 결과 센서(당첨번호·판매액·등수별 당첨금)를 발행한다.

    모바일 조회 API(ma.dhlottery.co.kr)의 최신 추첨 데이터만 사용하므로 로그인
    상태나 구매 가능 시간대와 무관하게 동작한다.
    """
    username = account.username
    if not config["enable_lotto645"]:
        return
    try:
        async with DhMobileApiClient() as mobile:
            draw = await mobile.async_get_latest_draw()

        round_no = _safe_int(draw.get("round_no"))
        numbers = draw.get("numbers") or []
        bonus_number = _safe_int(draw.get("bonus"))
        rank = draw.get("rank_result") or {}

        # Round number
        await publish_sensor_for_account(account, "lotto645_round", round_no, {
            "friendly_name": "로또 회차",
            "icon": "mdi:counter",
        })

        # Individual numbers
        for i in range(1, 7):
            num = numbers[i - 1] if i - 1 < len(numbers) else None
            await publish_sensor_for_account(account, f"lotto645_number{i}", _safe_int(num), {
                "friendly_name": f"로또 번호 {i}",
                "icon": f"mdi:numeric-{i}-circle",
            })

        # Bonus
        await publish_sensor_for_account(account, "lotto645_bonus", bonus_number, {
            "friendly_name": "로또 보너스 번호",
            "icon": "mdi:star-circle",
        })

        # Combined winning numbers
        winning_text = f"Round {round_no}: {', '.join(map(str, numbers))} + {bonus_number}"
        await publish_sensor_for_account(account, "lotto645_winning_numbers", winning_text, {
            "numbers": numbers,
            "bonus": bonus_number,
            "round": round_no,
            "friendly_name": "로또 당첨 번호",
            "icon": "mdi:trophy-award",
        })

        # Draw date
        draw_date = _parse_yyyymmdd(draw.get("draw_date"))
        if draw_date:
            await publish_sensor_for_account(account, "lotto645_draw_date", draw_date, {
                "friendly_name": "로또 추첨일",
                "icon": "mdi:calendar",
                "device_class": "date",
            })

        # Total sales
        await publish_sensor_for_account(account, "lotto645_total_sales", _safe_int(draw.get("sale_amount")), {
            "friendly_name": "로또 총 판매액",
            "unit_of_measurement": "KRW",
            "icon": "mdi:cash-multiple",
        })

        # 1st-5th prizes
        for r in range(1, 6):
            await publish_sensor_for_account(
                account,
                f"lotto645_{['first','second','third','fourth','fifth'][r-1]}_prize",
                _safe_int(rank.get(f"rnk{r}WnAmt")),
                {
                    "friendly_name": f"로또 {r}등 당첨금",
                    "unit_of_measurement": "KRW",
                    "total_amount": _safe_int(rank.get(f"rnk{r}SumWnAmt")),
                    "winners": _safe_int(rank.get(f"rnk{r}WnNope")),
                    "icon": ["mdi:trophy", "mdi:medal", "mdi:medal-outline", "mdi:currency-krw", "mdi:cash"][r - 1],
                },
            )

        logger.info(f"[SENSOR][{username}] Lottery result sensors updated (round {round_no})")
    except Exception as e:
        logger.warning(f"[SENSOR][{username}] Failed to fetch lotto results: {e}")


async def publish_pension_result_sensors(account: AccountData):
    """연금복권720+ 최신 회차 당첨 결과 센서를 발행한다.

    모바일 조회 API(ma.dhlottery.co.kr)만 사용하므로 로그인 상태나 구매 가능
    시간대와 무관하게 동작한다. enable_pension720 옵션으로 켜고 끈다.
    """
    username = account.username
    if not config.get("enable_pension720", True):
        return
    try:
        async with DhMobileApiClient() as mobile:
            draw = await mobile.async_get_pension_latest_draw()

        round_no = _safe_int(draw.get("round_no"))
        rank_winners = draw.get("rank_winners") or {}

        # 회차
        await publish_sensor_for_account(account, "pension720_round", round_no, {
            "friendly_name": "연금복권 회차",
            "icon": "mdi:counter",
        })

        # 당첨번호 (조 + 6자리)
        await publish_sensor_for_account(account, "pension720_winning_number", draw.get("winning_number_display"), {
            "group": draw.get("group"),
            "number": draw.get("number"),
            "bonus": draw.get("bonus"),
            "rank_winners": {str(k): v for k, v in rank_winners.items()},
            "bonus_winners": draw.get("bonus_winners"),
            "round": round_no,
            "friendly_name": "연금복권 당첨번호",
            "icon": "mdi:trophy-award",
        })

        # 보너스 번호 (6자리)
        await publish_sensor_for_account(account, "pension720_bonus_number", draw.get("bonus"), {
            "friendly_name": "연금복권 보너스 번호",
            "icon": "mdi:star-circle",
        })

        # 추첨일
        pension_draw_date = _parse_yyyymmdd(draw.get("draw_date"))
        if pension_draw_date:
            await publish_sensor_for_account(account, "pension720_draw_date", pension_draw_date, {
                "friendly_name": "연금복권 추첨일",
                "icon": "mdi:calendar",
                "device_class": "date",
            })

        # 총 판매액
        await publish_sensor_for_account(account, "pension720_total_sales", _safe_int(draw.get("sale_amount")), {
            "friendly_name": "연금복권 총 판매액",
            "unit_of_measurement": "KRW",
            "icon": "mdi:cash-multiple",
        })

        # 1등 당첨자 수
        await publish_sensor_for_account(account, "pension720_rank1_winners", _safe_int(rank_winners.get(1)), {
            "friendly_name": "연금복권 1등 당첨자 수",
            "unit_of_measurement": "명",
            "icon": "mdi:account-group",
        })

        # 1등 배출점
        await publish_sensor_for_account(account, "pension720_first_store", draw.get("first_store"), {
            "friendly_name": "연금복권 1등 배출점",
            "icon": "mdi:store",
        })

        logger.info(f"[SENSOR][{username}] Pension720 result sensors updated (round {round_no})")
    except Exception as e:
        logger.warning(f"[SENSOR][{username}] Failed to fetch pension720 results: {e}")


PENSION_SLOT_SENSORS = 5


async def _publish_pension_slot_sensors(account: AccountData, prefix: str, label: str, round_no: int, games: list):
    """연금 매별 센서 pension720_game_{1..5} / pension720_prev_game_{1..5} 발행."""
    total = len(games or [])
    for i in range(1, PENSION_SLOT_SENSORS + 1):
        if i <= total:
            g = games[i - 1]
            icon, color = pension_result_style(g.get("result"))
            state = f"{g.get('group')}조 {g.get('number')}" if g.get("group") else str(g.get("number"))
            attrs = {
                "round_no": round_no,
                "group": g.get("group"),
                "number": g.get("number"),
                "result": g.get("result"),
                "rank": g.get("rank"),
                "win_amount": g.get("win_amount", 0),
                "color": color,
                "total_in_round": total,
                "friendly_name": f"연금 구매 {i} ({label})",
                "icon": icon,
            }
        else:
            state = "구매 내역 없음"
            attrs = {
                "round_no": round_no, "group": "", "number": "", "result": "-",
                "rank": None, "win_amount": 0, "color": "grey", "total_in_round": total,
                "friendly_name": f"연금 구매 {i} ({label})",
                "icon": f"mdi:numeric-{i}-box-outline",
            }
        await publish_sensor_for_account(account, f"{prefix}_{i}", state, attrs)


async def publish_pension_history_sensors(account: AccountData):
    """연금복권720 구매 내역 센서(로그인 필요, www 원장 selectMyLotteryledger.do, ltGdsCd=LP72).

    연금은 주 최대 100매라 게임별 센서 N개는 비효율적이다. 회차(ltEpsd)별로 묶어
    '이번 회차/지난 회차' 센서 2개의 games 배열 속성에 전체 내역을 담고, 대시보드
    카드(마크다운)가 그 배열을 표로 렌더한다. 지난 회차 센서는 당첨 집계(win_count·
    total_win_amount·result_summary)를 포함해 추첨 후 당첨 알림 자동화의 소스가 된다.
    """
    username = account.username
    if not config.get("enable_pension720", True):
        return
    if not account.client or not account.client.logged_in:
        return
    try:
        items = await account.client.async_get_buy_list("LP72", days=14)
    except Exception as e:
        logger.warning(f"[PENSION-HIST][{username}] 조회 실패: {e}")
        return

    # 회차(ltEpsd)별 그룹핑 → 현재(판매 중)/이전(추첨 완료) 회차 센서로 발행.
    # 기준 회차는 로또와 같다: 현재 = 최신 추첨 회차 + 1, 이전 = 추첨 완료 회차 중 구매가 있는 최근 회차.
    rounds = group_rounds(items)
    latest_drawn = _safe_int(account.sensor_cache.get("pension720_round", {}).get("state"))
    if latest_drawn <= 0:
        try:
            latest_drawn = await _pension_latest_round()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[PENSION-HIST][{username}] 최신 회차 조회 실패(구매 회차 순서로 대체): {e}")
            latest_drawn = 0
    this_round, last_round = select_rounds(rounds, latest_drawn)

    g_this, _, _ = build_round(rounds.get(this_round, []))
    await publish_sensor_for_account(account, "pension720_this_round", len(g_this), {
        "round_no": this_round, "games": g_this,
        "friendly_name": "연금 이번 회차 구매", "unit_of_measurement": "매", "icon": "mdi:ticket",
    })

    g_last, wc_last, tw_last = build_round(rounds.get(last_round, []))
    summary = summarize(last_round, g_last, wc_last, tw_last)
    await publish_sensor_for_account(account, "pension720_last_round", len(g_last), {
        "round_no": last_round, "games": g_last,
        "win_count": wc_last, "total_win_amount": tw_last, "result_summary": summary,
        "friendly_name": "연금 지난 회차 결과", "unit_of_measurement": "매", "icon": "mdi:trophy-outline",
    })

    await publish_sensor_for_account(account, "pension720_recent_count", len(items), {
        "friendly_name": "연금 최근 구매 건수 (14일)", "unit_of_measurement": "건", "icon": "mdi:history",
    })

    # 로또의 '구매 게임 N (현재/이전)' 과 같은 형태의 매별 센서(각 5개).
    # 한 회차에 5매를 넘게 사면 앞의 5매만 개별 센서로, 전체는 위 회차 센서 games 속성에 있다.
    await _publish_pension_slot_sensors(account, "pension720_game", "현재", this_round, g_this)
    await _publish_pension_slot_sensors(account, "pension720_prev_game", "이전", last_round, g_last)

    # 추첨 후 당첨 필드 구조 검증용(최초 당첨 발생 시 ltWnResult/wnRnk/ltWnAmt 확인)
    try:
        import json as _json
        if g_last:
            logger.info(
                f"[PENSION-HIST][{username}] last_round {last_round} "
                f"sample={_json.dumps(g_last[:2], ensure_ascii=False)[:400]}"
            )
    except Exception:
        pass
    logger.info(
        f"[PENSION-HIST][{username}] 이번 {this_round}회 {len(g_this)}매 / "
        f"지난 {last_round}회 {len(g_last)}매(당첨 {wc_last})"
    )


async def update_sensors_for_account(account: AccountData, force: bool = False):
    """계정의 센서를 갱신한다.

    통계·최다출현 등 로그인이 필요 없는 조회 센서는 항상 먼저 발행하고,
    잔액·구매내역 등 로그인이 필요한 센서는 로그인 성공 시에만 발행한다.
    구매 불가 시간대에는 로그인/구매 API 호출을 건너뛴다.
    """
    username = account.username

    # 통계·당첨결과 센서는 로그인이 필요 없으므로(모바일 조회 API) 항상 먼저 발행한다.
    await publish_statistics_sensors(account)
    await publish_lottery_result_sensors(account)
    await publish_pension_result_sensors(account)

    # 구매 불가 시간대 체크 (최우선). force=True 면 읽기 전용 조회를 그대로 진행한다.
    if not force and not is_purchase_available_now():
        now_kst = datetime.now(_TZ_KST)
        next_available = get_next_available_time()
        time_until_available = next_available - now_kst
        hours = int(time_until_available.total_seconds() // 3600)
        minutes = int((time_until_available.total_seconds() % 3600) // 60)

        logger.info(f"[SENSOR][{username}] Purchase unavailable time (KST). Next sync at {next_available.strftime('%H:%M')}")

        # 사용자에게 상태 알림 센서 발행
        await publish_sensor_for_account(account, "lotto45_sync_status", "구매 불가 시간 (동기화 대기 중)", {
            "status": "waiting",
            "reason": "구매 불가능 시간대",
            "current_time_kst": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
            "next_available_time": next_available.strftime("%Y-%m-%d %H:%M:%S"),
            "time_until_available": f"{hours}시간 {minutes}분 후",
            "available_hours": {
                "평일/일요일": "06:00-24:00",
                "토요일": "06:00-20:00"
            },
            "friendly_name": "동기화 상태",
            "icon": "mdi:sleep",
        })

        return

    # 로그인 확인 및 재로그인 시도
    if not account.client or not account.client.logged_in:
        logger.warning(f"[SENSOR][{username}] Not logged in, attempting login...")
        try:
            await account.client.async_login()
            logger.info(f"[SENSOR][{username}] Re-login successful")
        except Exception as e:
            now_kst = datetime.now(_TZ_KST)
            msg = str(e)[:255]
            logger.error(f"[SENSOR][{username}] Login failed: {e}")

            # 로그인 오류 센서
            await publish_sensor_for_account(account, "lotto45_login_error", msg, {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "friendly_name": "로그인 오류",
                "icon": "mdi:account-alert",
            })

            # 동기화 상태 센서 (재로그인 실패)
            await publish_sensor_for_account(account, "lotto45_sync_status", "동기화 실패 (재로그인 필요)", {
                "status": "relogin_failed",
                "error": msg,
                "error_time": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                "retry_in": f"{config['update_interval'] // 60}분 후",
                "action_required": "애드온 재시작 또는 계정 정보 확인 필요",
                "friendly_name": "동기화 상태",
                "icon": "mdi:login-variant",
            })

            logger.warning(f"[SENSOR][{username}] Skipping sensor update due to login failure")
            return

    try:
        logger.info(f"[SENSOR][{username}] Updating sensors...")

        # 로그인 정상 → 과거 로그인/구매 오류 센서 해제 (실제 실패 시 아래에서 다시 표시됨)
        await publish_sensor_for_account(account, "lotto45_login_error", "없음", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "로그인 오류",
            "icon": "mdi:account-check",
        })
        await publish_sensor_for_account(account, "lotto45_purchase_error", "없음", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "로또 구매 오류",
            "icon": "mdi:cart-check",
        })

        # Balance
        balance = await account.client.async_get_balance()
        await publish_sensor_for_account(account, "lotto45_balance", balance.deposit, {
            "purchase_available": balance.purchase_available,
            "reservation_purchase": balance.reservation_purchase,
            "withdrawal_request": balance.withdrawal_request,
            "this_month_accumulated": balance.this_month_accumulated_purchase,
            "unit_of_measurement": "KRW",
            "friendly_name": "예치금",
            "icon": "mdi:wallet",
        })

        # Purchase time info
        await publish_sensor_for_account(account, "lotto45_purchase_available_time",
            "weekdays: 06:00-24:00, saturday: 06:00-20:00, sunday: 06:00-24:00", {
            "weekdays": "06:00-24:00",
            "saturday": "06:00-20:00",
            "sunday": "06:00-24:00",
            "friendly_name": "로또 구매 가능 시간",
            "icon": "mdi:clock-time-eight",
        })

        # (당첨 결과 센서 lotto645_* 는 publish_lottery_result_sensors() 로 분리되어
        #  함수 앞부분에서 로그인 여부와 무관하게 발행된다.)
        if config["enable_lotto645"] and account.analyzer:
            # Purchase history - GAME SENSORS HERE!
            try:
                history = await account.lotto_645.async_get_buy_history_this_week()
                latest_round_no = await account.lotto_645.async_get_latest_round_no()
                current_round = latest_round_no + 1  # 아직 추첨 안 된 회차 = 현재 판매 중

                # Collect games (max 5) - 현재 회차(current_round) 구매만 표시
                all_games = []
                if history:
                    latest_purchase = history[0]

                    games_info = [{
                        "slot": g.slot,
                        "mode": str(g.mode),
                        "numbers": g.numbers
                    } for g in latest_purchase.games]

                    await publish_sensor_for_account(account, "lotto45_latest_purchase", latest_purchase.round_no, {
                        "round_no": latest_purchase.round_no,
                        "barcode": latest_purchase.barcode,
                        "result": latest_purchase.result,
                        "games": games_info,
                        "games_count": len(latest_purchase.games),
                        "friendly_name": "로또 최근 구매 회차",
                        "icon": "mdi:receipt-text",
                    })

                    # 현재 회차 구매만 필터: round_no == current_round (이전 회차는 prev_game에 표시)
                    for purchase in history:
                        if purchase.round_no != current_round:
                            continue
                        for gd in purchase.game_details:
                            all_games.append({
                                'game': gd['game'],
                                'round_no': purchase.round_no,
                                'result': _rank_drawed_to_result(gd['rank'], gd['drawed']),
                            })
                            if len(all_games) >= 5:
                                break
                        if len(all_games) >= 5:
                            break
                else:
                    # No purchase history
                    logger.info(f"[SENSOR][{username}] No purchase history in the last week")

                logger.info(f"[SENSOR][{username}] Publishing 5 game sensors (current_round={current_round}, filled: {len(all_games)})")
                weekly_purchase_count = 0

                # 구매 게임 (현재): 최근 5게임 구매내역 및 결과 표시
                for i in range(1, 6):
                    if i <= len(all_games):
                        game_info = all_games[i - 1]
                        game = game_info["game"]
                        round_no = game_info["round_no"]
                        numbers_str = ", ".join(map(str, game.numbers))
                        await publish_sensor_for_account(account, f"lotto45_game_{i}", numbers_str, {
                            "slot": game.slot,
                            "슬롯": game.slot,
                            "mode": str(game.mode),
                            "선택": str(game.mode),
                            "numbers": game.numbers,
                            "round_no": round_no,
                            "result": game_info["result"],
                            "friendly_name": f"로또 구매 게임 {i} (현재)",
                            "icon": f"mdi:numeric-{i}-box-multiple",
                        })
                        try:
                            ltwn_result = game_info["result"] or "미추첨"
                            if round_no > latest_round_no:
                                weekly_purchase_count += 1
                            result_icon, result_color = _ltwn_result_to_icon_color(ltwn_result)
                            winning_numbers_check = []
                            bonus_number_check = 0
                            if round_no <= latest_round_no:
                                winning_data = await account.lotto_645.async_get_round_info(round_no)
                                winning_numbers_check = winning_data.numbers
                                bonus_number_check = winning_data.bonus_num
                            await publish_sensor_for_account(account, f"lotto45_game_{i}_result", ltwn_result, {
                                "round_no": round_no,
                                "my_numbers": game.numbers,
                                "winning_numbers": winning_numbers_check,
                                "bonus_number": bonus_number_check,
                                "result": ltwn_result,
                                "color": result_color,
                                "friendly_name": f"로또 구매 게임 {i} (현재) 결과",
                                "icon": result_icon,
                            })
                        except Exception as e:
                            logger.warning(f"[SENSOR][{username}] Failed to check game {i}: {e}")
                            await publish_sensor_for_account(account, f"lotto45_game_{i}_result", "Check Failed", {
                                "round_no": round_no,
                                "my_numbers": game.numbers,
                                "error": str(e),
                                "friendly_name": f"로또 구매 게임 {i} (현재) 결과",
                                "icon": "mdi:alert-circle-outline",
                            })
                    else:
                        await publish_sensor_for_account(account, f"lotto45_game_{i}", "구매 내역 없음", {
                            "slot": "-",
                            "슬롯": "-",
                            "mode": "-",
                            "선택": "-",
                            "numbers": [],
                            "round_no": 0,
                            "result": "-",
                            "friendly_name": f"로또 구매 게임 {i} (현재)",
                            "icon": f"mdi:numeric-{i}-box-outline",
                        })
                        await publish_sensor_for_account(account, f"lotto45_game_{i}_result", "구매 내역 없음", {
                            "round_no": 0,
                            "my_numbers": [],
                            "winning_numbers": [],
                            "bonus_number": 0,
                            "matching_count": 0,
                            "bonus_match": False,
                            "rank": 0,
                            "result": "구매 내역 없음",
                            "color": "grey",
                            "friendly_name": f"로또 구매 게임 {i} (현재) 결과",
                            "icon": "mdi:circle-outline",
                        })
                # weekly_purchase_count는 위 루프에서 round_no > latest_round_no일 때 이미 증가됨

                # 이전 회차(추첨 완료) 구매내역: selectMyLotteryledger ltWnResult 직접 사용
                try:
                    prev_round_no, prev_history = await account.lotto_645.async_get_prev_drawn_round_and_history()
                    prev_round_games = []
                    for purchase in prev_history:
                        for gd in purchase.game_details:
                            prev_round_games.append({
                                "game": gd["game"],
                                "round_no": purchase.round_no,
                                "result": _rank_drawed_to_result(gd["rank"], gd["drawed"]),
                            })
                            if len(prev_round_games) >= 5:
                                break
                        if len(prev_round_games) >= 5:
                            break
                    await publish_sensor_for_account(account, "lotto45_prev_round", prev_round_no, {
                        "friendly_name": "로또 구매 회차 (이전)",
                        "icon": "mdi:counter",
                    })
                    if prev_round_no > 0:
                        winning_data_prev = await account.lotto_645.async_get_round_info(prev_round_no)
                        for i in range(1, 6):
                            if i <= len(prev_round_games):
                                gp = prev_round_games[i - 1]
                                g = gp["game"]
                                rn = gp["round_no"]
                                ltwn = gp["result"] or "낙첨"
                                nums_str = ", ".join(map(str, g.numbers))
                                ri, rc = _ltwn_result_to_icon_color(ltwn)
                                await publish_sensor_for_account(account, f"lotto45_prev_game_{i}", nums_str, {
                                    "slot": g.slot, "슬롯": g.slot, "mode": str(g.mode), "선택": str(g.mode),
                                    "numbers": g.numbers, "round_no": rn, "result": ltwn,
                                    "friendly_name": f"로또 구매 게임 {i} (이전)", "icon": f"mdi:numeric-{i}-box-multiple",
                                })
                                await publish_sensor_for_account(account, f"lotto45_prev_game_{i}_result", ltwn, {
                                    "round_no": rn, "my_numbers": g.numbers,
                                    "winning_numbers": winning_data_prev.numbers,
                                    "bonus_number": winning_data_prev.bonus_num,
                                    "result": ltwn, "color": rc,
                                    "friendly_name": f"로또 구매 게임 {i} (이전) 결과", "icon": ri,
                                })
                            else:
                                await publish_sensor_for_account(account, f"lotto45_prev_game_{i}", "구매 내역 없음", {
                                    "slot": "-", "슬롯": "-", "mode": "-", "선택": "-",
                                    "numbers": [], "round_no": 0, "result": "-",
                                    "friendly_name": f"로또 구매 게임 {i} (이전)", "icon": f"mdi:numeric-{i}-box-outline",
                                })
                                await publish_sensor_for_account(account, f"lotto45_prev_game_{i}_result", "구매 내역 없음", {
                                    "round_no": 0, "my_numbers": [], "winning_numbers": [], "bonus_number": 0,
                                    "matching_count": 0, "bonus_match": False, "rank": 0, "result": "구매 내역 없음", "color": "grey",
                                    "friendly_name": f"로또 구매 게임 {i} (이전) 결과", "icon": "mdi:circle-outline",
                                })
                    else:
                        for i in range(1, 6):
                            await publish_sensor_for_account(account, f"lotto45_prev_game_{i}", "구매 내역 없음", {
                                "slot": "-", "슬롯": "-", "mode": "-", "선택": "-",
                                "numbers": [], "round_no": 0, "result": "-",
                                "friendly_name": f"로또 구매 게임 {i} (이전)", "icon": f"mdi:numeric-{i}-box-outline",
                            })
                            await publish_sensor_for_account(account, f"lotto45_prev_game_{i}_result", "구매 내역 없음", {
                                "round_no": 0, "my_numbers": [], "winning_numbers": [], "bonus_number": 0,
                                "matching_count": 0, "bonus_match": False, "rank": 0, "result": "구매 내역 없음", "color": "grey",
                                "friendly_name": f"로또 구매 게임 {i} (이전) 결과", "icon": "mdi:circle-outline",
                            })
                except Exception as e:
                    logger.warning(f"[SENSOR][{username}] Prev-round sensors failed: {e}")

                # Weekly purchase count
                weekly_limit = 5
                remaining_count = max(0, weekly_limit - weekly_purchase_count)

                await publish_sensor_for_account(account, "lotto45_weekly_purchase_count", weekly_purchase_count, {
                    "weekly_limit": weekly_limit,
                    "remaining": remaining_count,
                    "friendly_name": "로또 주간 구매 횟수",
                    "unit_of_measurement": "games",
                    "icon": "mdi:ticket-confirmation" if remaining_count > 0 else "mdi:close-circle",
                })

                logger.info(f"[SENSOR][{username}] Weekly: {weekly_purchase_count}/{weekly_limit}")

            except Exception as e:
                logger.warning(f"[SENSOR][{username}] Failed purchase history: {e}")


        # Purchase Statistics (Total Winning)
        if config["enable_lotto645"] and account.analyzer:
            try:
                stats = await account.analyzer.async_get_purchase_statistics(days=365)

                await publish_sensor_for_account(account, "lotto45_total_winning", stats.total_winning_amount, {
                    "total_purchase": stats.total_purchase_amount,
                    "total_purchase_count": stats.total_purchase_count,
                    "total_winning_count": stats.total_winning_count,
                    "win_rate": stats.win_rate,
                    "roi": stats.roi,
                    "rank_distribution": stats.rank_distribution,
                    "unit_of_measurement": "KRW",
                    "friendly_name": "로또 총 당첨금 (최근 1년)",
                    "icon": "mdi:trophy-variant",
                })

                logger.info(f"[SENSOR][{username}] Purchase statistics updated (winning: {stats.total_winning_amount} KRW, ROI: {stats.roi}%)")

            except Exception as e:
                logger.warning(f"[SENSOR][{username}] Failed to update purchase statistics: {e}")

        # 연금복권 구매 내역 (로그인 필요)
        if config.get("enable_pension720", True):
            await publish_pension_history_sensors(account)

        # Winning Probability Sensors
        if config["enable_lotto645"]:
            try:
                # Calculate probabilities (fixed values based on combinatorics)
                # Total combinations: C(45, 6) = 8,145,060
                total_combinations = 8145060

                # 1st prize: 6 numbers match = 1 / 8,145,060
                prob_1st = (1 / total_combinations) * 100
                await publish_sensor_for_account(account, "lotto645_probability_rank1", f"{prob_1st:.7f}", {
                    "probability_decimal": prob_1st,
                    "probability_fraction": "1/8,145,060",
                    "unit_of_measurement": "%",
                    "friendly_name": "로또 1등 당첨 확률",
                    "icon": "mdi:trophy",
                })

                # 2nd prize: 5 numbers + bonus = 6 / 8,145,060
                prob_2nd = (6 / total_combinations) * 100
                await publish_sensor_for_account(account, "lotto645_probability_rank2", f"{prob_2nd:.7f}", {
                    "probability_decimal": prob_2nd,
                    "probability_fraction": "6/8,145,060",
                    "unit_of_measurement": "%",
                    "friendly_name": "로또 2등 당첨 확률",
                    "icon": "mdi:medal",
                })

                # 3rd prize: 5 numbers = 234 / 8,145,060
                prob_3rd = (234 / total_combinations) * 100
                await publish_sensor_for_account(account, "lotto645_probability_rank3", f"{prob_3rd:.5f}", {
                    "probability_decimal": prob_3rd,
                    "probability_fraction": "234/8,145,060",
                    "unit_of_measurement": "%",
                    "friendly_name": "로또 3등 당첨 확률",
                    "icon": "mdi:medal-outline",
                })

                # 4th prize: 4 numbers = 11,115 / 8,145,060
                prob_4th = (11115 / total_combinations) * 100
                await publish_sensor_for_account(account, "lotto645_probability_rank4", f"{prob_4th:.4f}", {
                    "probability_decimal": prob_4th,
                    "probability_fraction": "11,115/8,145,060",
                    "unit_of_measurement": "%",
                    "friendly_name": "로또 4등 당첨 확률",
                    "icon": "mdi:currency-krw",
                })

                # 5th prize: 3 numbers = 185,220 / 8,145,060
                prob_5th = (185220 / total_combinations) * 100
                await publish_sensor_for_account(account, "lotto645_probability_rank5", f"{prob_5th:.3f}", {
                    "probability_decimal": prob_5th,
                    "probability_fraction": "185,220/8,145,060",
                    "unit_of_measurement": "%",
                    "friendly_name": "로또 5등 당첨 확률",
                    "icon": "mdi:cash",
                })

                logger.info(f"[SENSOR][{username}] Winning probabilities updated")

            except Exception as e:
                logger.warning(f"[SENSOR][{username}] Failed to update winning probabilities: {e}")

        # Update time
        now = datetime.now(timezone.utc).isoformat()
        now_kst = datetime.now(_TZ_KST)
        await publish_sensor_for_account(account, "lotto45_last_update", now, {
            "friendly_name": "마지막 업데이트",
            "icon": "mdi:clock-check-outline",
        })

        # 동기화 상태 센서 (정상)
        await publish_sensor_for_account(account, "lotto45_sync_status", "정상 동기화 완료", {
            "status": "success",
            "last_sync_time": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
            "next_sync_in": f"{config['update_interval'] // 60}분 후",
            "friendly_name": "동기화 상태",
            "icon": "mdi:check-circle",
        })

        logger.info(f"[SENSOR][{username}] Updated successfully")

    except DhLotteryLoginError as e:
        if account.client:
            account.client.logged_in = False
        msg = str(e)[:255]
        now_kst = datetime.now(_TZ_KST)

        # 로그인 오류 센서
        await publish_sensor_for_account(account, "lotto45_login_error", msg, {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "로그인 오류",
            "icon": "mdi:account-alert",
        })

        # 동기화 상태 센서 (로그인 실패)
        await publish_sensor_for_account(account, "lotto45_sync_status", "동기화 실패 (로그인 오류)", {
            "status": "login_error",
            "error": msg,
            "error_time": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
            "retry_in": f"{config['update_interval'] // 60}분 후",
            "friendly_name": "동기화 상태",
            "icon": "mdi:alert-circle",
        })

        logger.warning(f"[SENSOR][{username}] Login/API failed: {e}")

    except DhLotteryError as e:
        if account.client:
            account.client.logged_in = False
        msg = str(e)[:255]
        now_kst = datetime.now(_TZ_KST)

        # API 오류 센서
        await publish_sensor_for_account(account, "lotto45_login_error", msg, {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "friendly_name": "로그인/API 오류",
            "icon": "mdi:account-alert",
        })

        # 동기화 상태 센서 (API 실패)
        await publish_sensor_for_account(account, "lotto45_sync_status", "동기화 실패 (API 오류)", {
            "status": "api_error",
            "error": msg,
            "error_time": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
            "retry_in": f"{config['update_interval'] // 60}분 후",
            "friendly_name": "동기화 상태",
            "icon": "mdi:alert-circle",
        })

        logger.warning(f"[SENSOR][{username}] Update failed (API): {e}")

    except Exception as e:
        msg = str(e)[:255]
        now_kst = datetime.now(_TZ_KST)

        # 동기화 상태 센서 (알 수 없는 오류)
        await publish_sensor_for_account(account, "lotto45_sync_status", "동기화 실패 (알 수 없는 오류)", {
            "status": "unknown_error",
            "error": msg,
            "error_time": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
            "retry_in": f"{config['update_interval'] // 60}분 후",
            "friendly_name": "동기화 상태",
            "icon": "mdi:alert-circle",
        })

        logger.error(f"[SENSOR][{username}] Update failed: {e}", exc_info=True)


async def publish_sensor_for_account(account: AccountData, entity_id: str, state, attributes: dict = None):
    """Publish sensor"""
    username = account.username
    # 대시보드가 MQTT/HA 를 거치지 않고 바로 읽을 수 있도록 마지막 값을 보관한다.
    account.sensor_cache[entity_id] = {
        "state": state,
        "attributes": attributes or {},
        "ts": time.time(),
    }
    _schedule_cache_save()
    # 원장(구매·당첨 기록)·당첨/예치금 알림
    _observe_sensor(account, entity_id, state, attributes or {})

    if config["use_mqtt"] and mqtt_client and mqtt_client.connected:
        try:
            success = await publish_sensor_mqtt(
                mqtt_client=mqtt_client,
                entity_id=entity_id,
                state=state,
                username=username,
                attributes=attributes
            )
            if success:
                return
        except Exception as e:
            logger.error(f"[SENSOR][{username}] MQTT error: {e}")

    # MQTT 를 쓰는데 잠시 끊긴 경우: REST 로 따로 만들지 않는다(실제 아이디가 든 중복 엔티티가 생김).
    # 값은 sensor_cache 에 남아 있고, 다시 연결되면 _mqtt_on_ready 가 한꺼번에 재발행한다.
    if mqtt_client is not None:
        return

    # REST API fallback (MQTT 클라이언트가 아예 없을 때만)
    import aiohttp

    if not config["supervisor_token"]:
        return

    addon_entity_id = f"addon_{username}_{entity_id}"
    url = f"{config['ha_url']}/api/states/sensor.{addon_entity_id}"
    headers = {
        "Authorization": f"Bearer {config['supervisor_token']}",
        "Content-Type": "application/json",
    }
    data = {
        "state": state,
        "attributes": attributes or {},
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers, ssl=False) as resp:
                if resp.status not in [200, 201]:
                    logger.error(f"[SENSOR][{username}] REST failed: {resp.status}")
    except Exception as e:
        logger.error(f"[SENSOR][{username}] REST error: {e}")


# 프로세스별 CSRF 토큰(재시작 시 바뀜). 대시보드 페이지에 심어 구매 요청 헤더로 돌려받는다.
DASHBOARD_CSRF_TOKEN = secrets.token_urlsafe(32)
# 대시보드 응답에서 뺄 센서(큰 진단 덤프 등)
_DASHBOARD_EXCLUDED_SENSORS = {"pension720_manual_diag"}
_dashboard_tasks: set = set()  # 실행 중 구매 작업 참조 보관(GC 방지)


def _aliases() -> dict:
    return account_aliases(list(accounts.keys()))


def _alias_text(value):
    """밖으로 내보내는 문자열에서 실제 아이디(와 일부만 가린 표기)를 Account_N 으로 바꾼다."""
    if not isinstance(value, str) or not value:
        return value
    for u, (_aid, label) in _aliases().items():
        if len(u) >= 4:
            value = value.replace(u, label)
            m = mask_username(u)
            if m != u:
                value = value.replace(m, label)
    return value


def _client_host(request: Request) -> str:
    return request.client.host if request.client else ""


def _require_ingress(request: Request) -> None:
    """구매·내역 API 는 HA Ingress(로그인된 HA 사용자) 경유만 허용."""
    if not is_ingress_client(_client_host(request)):
        raise HTTPException(status_code=403, detail="Home Assistant 사이드바(Ingress)에서만 사용할 수 있습니다.")


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """사이드바 대시보드(구매 내역 조회 + 구매 버튼). 데이터는 api/dashboard 에서 받는다."""
    import json as _json
    nonce = secrets.token_urlsafe(16)
    # 직접 포트 접근에는 개인 설정을 내보내지 않는다(기본값만).
    prefs = _load_prefs() if is_ingress_client(_client_host(request)) else normalize_prefs({})
    # <script type=application/json> 안에 넣으므로 <, >, & 를 유니코드 이스케이프해 태그 탈출을 막는다.
    prefs_json = (
        _json.dumps(prefs, ensure_ascii=False)
        .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )
    html = (
        PAGE_TEMPLATE.replace("__NONCE__", nonce)
        .replace("__CSRF__", DASHBOARD_CSRF_TOKEN)
        .replace("__VERSION__", APP_VERSION)
        .replace("__THEME__", prefs["theme"])  # 허용 목록 값만 저장됨
        .replace("__PREFS_JSON__", prefs_json)
    )
    csp = (
        "default-src 'none'; "
        f"script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
        "connect-src 'self'; img-src 'self' data:; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
    )
    headers = dict(_SECURITY_HEADERS)
    headers["Content-Security-Policy"] = csp
    return HTMLResponse(content=html, headers=headers)


@app.get("/api/dashboard")
async def api_dashboard(request: Request):
    """대시보드 데이터. 실제 아이디 대신 Account_N 별칭만 내보낸다."""
    _require_ingress(request)
    aliases = _aliases()
    out = []
    for username, account in accounts.items():
        aid, label = aliases[username]
        sensors = {
            k: {"state": _alias_text(v.get("state")), "attributes": v.get("attributes") or {}, "ts": v.get("ts")}
            for k, v in account.sensor_cache.items()
            if k not in _DASHBOARD_EXCLUDED_SENSORS
        }
        out.append({
            "id": aid,
            "label": label,
            "enabled": account.enabled,
            "logged_in": bool(account.client and getattr(account.client, "logged_in", False)),
            "cooldown_remaining": round(purchase_guard.get_remaining_cooldown(username), 1),
            "manual_numbers": account.manual_numbers_state,
            "pension_manual": account.pension_manual_state,
            "last_action": ({**account.last_action, "message": _alias_text(account.last_action.get("message"))}
                            if account.last_action else None),
            "sensors": sensors,
        })
    actions = {}
    for action in sorted(ALLOWED_ACTIONS):
        label, amount = action_label(action)
        actions[action] = {"label": label, "amount": amount}
    return JSONResponse(
        {
            "version": APP_VERSION,
            "lotto_enabled": bool(config["enable_lotto645"]),
            "pension_enabled": bool(config.get("enable_pension720", True)),
            "purchase_available": is_purchase_available_now(),
            "cooldown_seconds": int(INTER_ACCOUNT_COOLDOWN_SECONDS),
            "mqtt_connected": bool(mqtt_client and mqtt_client.connected),
            "mqtt_error": (mqtt_client.last_error if mqtt_client else "MQTT 클라이언트 없음")[:200],
            "actions": actions,
            "accounts": out,
        },
        headers=_SECURITY_HEADERS,
    )


DATA_DIR = os.getenv("DHL_DATA_DIR", "/data")
PREFS_FILE = "dashboard_prefs.json"
_PREFS_MAX_BODY = 4096
_prefs_lock = asyncio.Lock()


def _prefs_path() -> str:
    return os.path.join(DATA_DIR, PREFS_FILE)


def _load_prefs() -> dict:
    import json as _json
    try:
        with open(_prefs_path(), encoding="utf-8") as f:
            return normalize_prefs(_json.load(f))
    except FileNotFoundError:
        return normalize_prefs({})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[DASH] 설정 파일을 읽지 못해 기본값 사용: {e}")
        return normalize_prefs({})


def _save_prefs(prefs: dict) -> None:
    """원자적 저장(임시파일 → replace)으로 쓰기 도중 꺼져도 파일이 깨지지 않게 한다."""
    import json as _json
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = _prefs_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        _json.dump(prefs, f, ensure_ascii=False)
    os.replace(tmp, _prefs_path())


@app.get("/api/prefs")
async def api_get_prefs(request: Request):
    """대시보드 개인화 설정(테마·언어·카드 구성). 모든 기기에서 같은 설정을 쓴다."""
    _require_ingress(request)
    return JSONResponse(_load_prefs(), headers=_SECURITY_HEADERS)


@app.put("/api/prefs")
async def api_put_prefs(request: Request):
    """설정 부분 변경. Ingress 전용 + CSRF 헤더 필수, 값은 허용 목록으로 정규화."""
    _require_ingress(request)
    if not csrf_ok(DASHBOARD_CSRF_TOKEN, request.headers.get(CSRF_HEADER)):
        raise HTTPException(status_code=403, detail="보안 토큰이 올바르지 않습니다. 페이지를 새로고침하세요.")
    raw = await request.body()
    if len(raw) > _PREFS_MAX_BODY:
        raise HTTPException(status_code=413, detail="설정 데이터가 너무 큽니다.")
    import json as _json
    try:
        change = _json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="요청 형식이 올바르지 않습니다.")
    if not isinstance(change, dict):
        raise HTTPException(status_code=400, detail="요청 형식이 올바르지 않습니다.")
    async with _prefs_lock:
        prefs = merge_prefs(_load_prefs(), change)
        try:
            _save_prefs(prefs)
        except OSError as e:
            logger.error(f"[DASH] 설정 저장 실패: {e}")
            raise HTTPException(status_code=500, detail="설정을 저장하지 못했습니다.")
    return JSONResponse(prefs, headers=_SECURITY_HEADERS)


def _sync_manual_text(username: str, text_id: str, value: str) -> None:
    """대시보드에서 바꾼 수동 번호를 HA text 엔티티에도 반영."""
    if mqtt_client and mqtt_client.connected:
        topic = f"homeassistant/text/{mqtt_client.topic_prefix}_{username}_{text_id}/state"
        try:
            mqtt_client.client.publish(topic, value, qos=1, retain=True)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[DASH] 수동 번호 MQTT 동기화 실패: {e}")


async def _run_dashboard_action(account: AccountData, action: str, label: str, source: str = "dashboard") -> None:
    """구매 작업 실행(대시보드·MQTT 버튼·정기 자동 구매 공용) → account.last_action 에 결과 기록.

    끝나면 HA 이벤트(dhlotto45_purchase)와 구매 알림을 보낸다.
    """
    started = time.time()
    account.last_action = {"action": action, "label": label, "status": "running", "message": "", "started": started, "finished": None}
    try:
        if action in LOTTO_ACTIONS:
            await execute_button_purchase(account, LOTTO_ACTIONS[action][0])
            err_key, ok_key = "lotto45_purchase_error", "lotto45_latest_purchase"
        elif action == "pension_manual":
            await execute_pension_manual_purchase(account)
            err_key, ok_key = "pension720_purchase_error", "pension720_last_purchase"
        else:
            await execute_pension_purchase(account, PENSION_ACTIONS[action][0])
            err_key, ok_key = "pension720_purchase_error", "pension720_last_purchase"
        status, message = judge_outcome(
            account.sensor_cache.get(err_key), started, account.sensor_cache.get(ok_key)
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"[DASH][{mask_username(account.username)}] {action} 실패: {e}", exc_info=True)
        status, message = "error", str(e)[:255]
    account.last_action = {
        "action": action, "label": label, "status": status, "message": message,
        "started": started, "finished": time.time(),
    }
    logger.info(f"[DASH][{mask_username(account.username)}] {action} → {status}: {message[:120]} ({source})")
    _spawn(_after_purchase(_alias_of(account.username)[1], action, label, status, message, source))


def _start_action(account: AccountData, action: str, source: str):
    """구매 작업을 백그라운드로 시작. 같은 계정 작업이 진행 중이면 None."""
    if account.last_action and account.last_action.get("status") == "running":
        logger.warning(f"[DASH][{mask_username(account.username)}] {action} 건너뜀: 이전 구매 진행 중 ({source})")
        return None
    label, _amount = action_label(action)
    account.last_action = {"action": action, "label": label, "status": "running", "message": "",
                           "started": time.time(), "finished": None}
    task = asyncio.create_task(_run_dashboard_action(account, action, label, source))
    _dashboard_tasks.add(task)
    task.add_done_callback(_dashboard_tasks.discard)
    return task


@app.post("/api/purchase")
async def api_purchase(request: Request):
    """대시보드 구매 요청. Ingress 전용 + CSRF 헤더 필수. 실행은 백그라운드, 결과는 api/dashboard 로 확인."""
    _require_ingress(request)
    if not csrf_ok(DASHBOARD_CSRF_TOKEN, request.headers.get(CSRF_HEADER)):
        raise HTTPException(status_code=403, detail="보안 토큰이 올바르지 않습니다. 페이지를 새로고침한 뒤 다시 시도하세요.")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="요청 형식이 올바르지 않습니다.")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="요청 형식이 올바르지 않습니다.")

    action = str(body.get("action") or "")
    username = resolve_alias(list(accounts.keys()), str(body.get("account") or ""))
    account = accounts.get(username) if username else None
    if account is None or not account.enabled:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    try:
        label, _amount = action_label(action)
        if action in LOTTO_ACTIONS:
            if not config["enable_lotto645"] or not account.lotto_645:
                raise DashboardInputError("로또 기능이 꺼져 있거나 로그인되지 않았습니다.")
            if not is_purchase_available_now():
                raise DashboardInputError("지금은 로또 구매 불가 시간입니다 (매일 00:00~06:00, 토요일은 20:00부터).")
        elif not config.get("enable_pension720", True) or not account.pension:
            raise DashboardInputError("연금복권 기능이 꺼져 있습니다.")
        if action == "lotto_manual":
            value = normalize_lotto_manual(body.get("numbers"))
            account.manual_numbers_state = value
            _sync_manual_text(username, "manual_numbers", value)
        elif action == "pension_manual":
            value = normalize_pension_manual(body.get("group"), body.get("digits"))
            account.pension_manual_state = value
            _sync_manual_text(username, "pension_manual", value)
    except DashboardInputError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if account.last_action and account.last_action.get("status") == "running":
        raise HTTPException(status_code=409, detail="이 계정의 이전 구매가 아직 진행 중입니다.")
    reason = _budget_block_reason(account, action_label(action)[1])
    if reason:
        raise HTTPException(status_code=400, detail=reason)

    ha_user = request.headers.get("X-Remote-User-Name") or "?"
    logger.info(f"[DASH][{mask_username(username)}] 구매 요청: {action} (HA 사용자: {ha_user})")
    # 진행 중 표시를 먼저 기록해 연속 클릭(409)을 즉시 막는다.
    account.last_action = {"action": action, "label": label, "status": "running", "message": "",
                           "started": time.time(), "finished": None}
    task = asyncio.create_task(_run_dashboard_action(account, action, label))
    _dashboard_tasks.add(task)
    task.add_done_callback(_dashboard_tasks.discard)
    return JSONResponse({"accepted": True, "action": action, "label": label}, status_code=202, headers=_SECURITY_HEADERS)


_sim_history_cache: dict = {"ts": 0.0, "draws": []}
_sim_history_lock = asyncio.Lock()
_SIM_CACHE_TTL = 3600.0


@app.post("/api/relogin")
async def api_relogin(request: Request):
    """단일 계정 원클릭 재로그인(세션 갱신). 애드온 전체 재시작 없이 세션을 복구한다."""
    _require_ingress(request)
    if not csrf_ok(DASHBOARD_CSRF_TOKEN, request.headers.get(CSRF_HEADER)):
        raise HTTPException(status_code=403, detail="보안 토큰이 올바르지 않습니다. 페이지를 새로고침하세요.")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="요청 형식이 올바르지 않습니다.")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="요청 형식이 올바르지 않습니다.")

    username = resolve_alias(list(accounts.keys()), str(body.get("account") or ""))
    account = accounts.get(username) if username else None
    if account is None or not account.enabled:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    reason, status = _relogin_block_reason(account)
    if reason:
        raise HTTPException(status_code=status, detail=reason)

    _relogin_busy.add(username)
    _relogin_last[username] = time.monotonic()
    try:
        if account.client is None:
            ok = await init_account(account)
            if not ok:
                raise DhLotteryLoginError("계정 초기화/로그인에 실패했습니다.")
        else:
            await account.client.async_login()
        await update_sensors_for_account(account)
        logger.info(f"[DASH][{mask_username(username)}] 원클릭 재로그인 성공")
        return JSONResponse({"ok": True, "logged_in": True}, headers=_SECURITY_HEADERS)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[DASH][{mask_username(username)}] 원클릭 재로그인 실패: {e}")
        # 응답에는 실제 아이디가 섞이지 않게 별칭으로 바꾼다(로그 필터는 응답에 적용되지 않음).
        msg = FT.scrub_text(str(e).replace(username, _alias_of(username)[1]))[:180]
        raise HTTPException(status_code=500, detail=f"재로그인 실패: {msg}")
    finally:
        _relogin_busy.discard(username)


# 재로그인 연타로 동행복권 로그인 실패 잠금(5회)에 걸리지 않도록 계정당 간격을 둔다.
RELOGIN_MIN_INTERVAL = 60.0
_relogin_last: Dict[str, float] = {}
_relogin_busy: set = set()


def _relogin_block_reason(account: "AccountData") -> tuple:
    """재로그인을 막아야 하면 (사유, HTTP 상태), 아니면 ("", 0)."""
    username = account.username
    if username in _relogin_busy:
        return "이미 로그인 중입니다. 잠시만 기다려 주세요.", 409
    if account.last_action and account.last_action.get("status") == "running":
        return "이 계정의 구매가 진행 중이라 지금은 재로그인할 수 없습니다.", 409
    if not is_purchase_available_now():
        return "지금은 동행복권 점검·구매 불가 시간이라 로그인하지 않습니다 (06:00 이후 자동으로 다시 로그인).", 409
    wait = RELOGIN_MIN_INTERVAL - (time.monotonic() - _relogin_last.get(username, -1e9))
    if wait > 0:
        return f"로그인 실패 잠금을 막기 위해 {int(wait) + 1}초 후에 다시 시도하세요.", 429
    return "", 0


@app.get("/api/simulate")
async def api_simulate(request: Request, numbers: str = "", rounds: int = 50):
    """즐겨찾기/수동 번호 과거 당첨 시뮬레이션 (최근 최대 100회차 캐시 사용)."""
    _require_ingress(request)
    rounds = max(10, min(100, int(rounds)))
    try:
        # 입력 형식 선검증 (네트워크 호출 전)
        FT.simulate_lotto_numbers(numbers, [])
    except DashboardInputError as e:
        raise HTTPException(status_code=400, detail=str(e))

    draws = await _round_history()

    try:
        result = FT.simulate_lotto_numbers(numbers, draws[:rounds])
    except DashboardInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(result, headers=_SECURITY_HEADERS)


async def _round_history() -> list:
    """최근 100회차 당첨번호(최신순). 1시간 메모리 캐시, 실패 시 502."""
    now = time.monotonic()
    if _sim_history_cache["draws"] and (now - _sim_history_cache["ts"]) <= _SIM_CACHE_TTL:
        return _sim_history_cache["draws"]
    async with _sim_history_lock:
        now = time.monotonic()
        if not _sim_history_cache["draws"] or (now - _sim_history_cache["ts"]) > _SIM_CACHE_TTL:
            try:
                async with DhMobileApiClient() as mobile:
                    fetched = await mobile.async_get_round_history(100)
                _sim_history_cache["draws"] = fetched
                _sim_history_cache["ts"] = time.monotonic()
            except Exception as e:  # noqa: BLE001
                raise HTTPException(status_code=502, detail=f"과거 당첨번호를 불러오지 못했습니다: {str(e)[:120]}")
        return _sim_history_cache["draws"]


_cum_stats_cache: dict = {"ts": 0.0, "stats": {}}
_CUM_CACHE_TTL = 6 * 3600.0


async def _cumulative_stats() -> dict:
    """번호별 전체 누적 출현 횟수(6시간 캐시). 실패해도 빈 값으로 계속한다."""
    now = time.monotonic()
    if _cum_stats_cache["stats"] and (now - _cum_stats_cache["ts"]) <= _CUM_CACHE_TTL:
        return _cum_stats_cache["stats"]
    try:
        async with DhMobileApiClient() as mobile:
            _cum_stats_cache["stats"] = await mobile.async_get_cumulative_number_stats()
            _cum_stats_cache["ts"] = time.monotonic()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[NUMSTATS] 누적 통계 조회 실패(생략): {e}")
    return _cum_stats_cache["stats"]


@app.get("/api/number-stats")
async def api_number_stats(request: Request, rounds: int = 50):
    """번호 통계 심화: 최근 N회(10~100) 번호별 출현 횟수·미출현 기간 + 전체 누적."""
    _require_ingress(request)
    rounds = max(10, min(100, int(rounds)))
    draws = await _round_history()
    data = FT.number_stats(draws, await _cumulative_stats(), rounds)
    nums = data.get("numbers") or []
    data["fairness"] = {
        "window": IN.chi_square_uniform([x.get("count") or 0 for x in nums]) if nums else None,
        "total": IN.chi_square_uniform([x.get("total") or 0 for x in nums]) if nums and all(x.get("total") for x in nums) else None,
    }
    return JSONResponse(data, headers=_SECURITY_HEADERS)


@app.get("/api/insights")
async def api_insights(request: Request):
    """럭키 랩: 운 지수·이번 달 예산·당첨금 수령 기한(애드온이 본 기록 기준)."""
    _require_ingress(request)
    return JSONResponse(_insight_snapshot(), headers=_SECURITY_HEADERS)


@app.get("/api/household/status")
async def api_household_status(request: Request):
    """가계부(kr_ledger_kit) 통합이 설치되어 있는지."""
    _require_ingress(request)
    return JSONResponse({"available": await _household_available()}, headers=_SECURITY_HEADERS)


def _calendar_body() -> str:
    now = FT.now_kst()
    settings = _load_settings()
    sched = settings["auto_buy"]["schedules"] if settings["auto_buy"]["enabled"] else []
    return IN.build_ics(now.date(), now, lotto=bool(config["enable_lotto645"]),
                        pension=bool(config.get("enable_pension720", True)), schedules=sched,
                        action_labels={a: action_label(a)[0] for a in FT.SCHED_ACTIONS}, labels=_labels(),
                        claim_list=IN.claims(_get_ledger().entries, now.date()))


@app.get("/api/calendar.ics")
async def api_calendar(request: Request):
    """추첨·판매 마감·정기 자동 구매·당첨금 수령 기한 캘린더(.ics) 내려받기."""
    _require_ingress(request)
    from fastapi.responses import Response
    headers = dict(_SECURITY_HEADERS)
    headers["Content-Disposition"] = 'attachment; filename="dhlotto45.ics"'
    return Response(content=_calendar_body(), media_type="text/calendar; charset=utf-8", headers=headers)


CALENDAR_USER = "dhlotto"
_calendar_fetch = {"at": 0.0}


def _calendar_secret(rotate: bool = False) -> str:
    """HA Remote calendar 가 쓰는 캘린더 주소 비밀번호(/data 에 보관, 처음 쓸 때 만든다)."""
    st = _state()
    s = st.get("calendar_secret")
    if rotate or not isinstance(s, str) or len(s) < 20:
        s = secrets.token_urlsafe(18)
        st["calendar_secret"] = s
        _save_state()
    return s


@app.get("/calendar.ics")
async def calendar_feed(request: Request):
    """HA Remote calendar 통합용 구독 주소(Basic 인증). HA 가 하루 한 번 가져가 캘린더에 표시한다."""
    from fastapi.responses import Response
    if not IN.basic_auth_ok(request.headers.get("Authorization"), CALENDAR_USER, _calendar_secret()):
        headers = dict(_SECURITY_HEADERS)
        headers["WWW-Authenticate"] = 'Basic realm="DH Lotto 45"'
        return Response(status_code=401, content="authentication required", headers=headers)
    _calendar_fetch["at"] = time.time()
    st = _state()
    st["calendar_fetch_at"] = int(_calendar_fetch["at"])
    _save_state()
    return Response(content=_calendar_body(), media_type="text/calendar; charset=utf-8", headers=_SECURITY_HEADERS)


def _calendar_feed_info() -> dict:
    import socket
    last = _calendar_fetch["at"] or float(_state().get("calendar_fetch_at") or 0)
    return {"url": f"http://{socket.gethostname()}:60099/calendar.ics", "username": CALENDAR_USER,
            "password": _calendar_secret(), "last_fetch": int(last) or None}


@app.get("/api/calendar/feed")
async def api_calendar_feed(request: Request):
    """HA 캘린더 연결 정보(주소·아이디·비밀번호·마지막으로 가져간 시각). Ingress 전용."""
    _require_ingress(request)
    return JSONResponse(_calendar_feed_info(), headers=_SECURITY_HEADERS)


@app.post("/api/calendar/feed/rotate")
async def api_calendar_feed_rotate(request: Request):
    """캘린더 주소 비밀번호 새로 만들기. Ingress + CSRF."""
    _require_ingress(request)
    _require_csrf(request)
    _calendar_secret(rotate=True)
    _calendar_fetch["at"] = 0.0
    st = _state()
    st.pop("calendar_fetch_at", None)
    _save_state()
    logger.warning("[CALENDAR] 캘린더 주소 비밀번호를 새로 만들었습니다(HA Remote calendar 비밀번호도 바꿔야 함)")
    return JSONResponse(_calendar_feed_info(), headers=_SECURITY_HEADERS)


_calendar_nudge_at = -1e9


async def _nudge_ha_calendar() -> None:
    """HA 에 연결된 DH Lotto 캘린더를 바로 새로 가져오게 한다(정기 구매 일정 변경·새 당첨 직후)."""
    global _calendar_nudge_at
    if time.monotonic() - _calendar_nudge_at < 60 or not _calendar_fetch["at"] and not _state().get("calendar_fetch_at"):
        return
    _calendar_nudge_at = time.monotonic()
    states = await _ha_get("states")
    ids = [s.get("entity_id") for s in states or [] if isinstance(s, dict)
           and str(s.get("entity_id", "")).startswith("calendar.")
           and "dh lotto" in str((s.get("attributes") or {}).get("friendly_name", "")).lower()]
    if ids:
        await _ha_post("services/homeassistant/update_entity", {"entity_id": ids})


# ================================================================ v2.7.0 확장 기능
# 알림·HA 이벤트, 구매/당첨 원장(통계), 즐겨찾기·정기 자동 구매 설정, 진단 리포트.
_feature_lock = asyncio.Lock()
_ledger: Optional["FT.Ledger"] = None
_feature_state: Optional[dict] = None
_bg_tasks: set = set()


def _data_path(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def _read_json(name: str, default):
    import json as _json
    try:
        with open(_data_path(name), encoding="utf-8") as f:
            return _json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[FEAT] {name} 읽기 실패(기본값 사용): {e}")
        return default


def _write_json(name: str, obj) -> None:
    """원자적 저장(임시파일 → replace)."""
    import json as _json
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = _data_path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        _json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, _data_path(name))


def _load_settings() -> dict:
    return FT.normalize_settings(_read_json(FT.SETTINGS_FILE, {}))


def _get_ledger() -> "FT.Ledger":
    global _ledger
    if _ledger is None:
        raw = _read_json(FT.LEDGER_FILE, [])
        _ledger = FT.Ledger(raw if isinstance(raw, list) else [])
    return _ledger


def _state() -> dict:
    global _feature_state
    if _feature_state is None:
        raw = _read_json(FT.STATE_FILE, {})
        _feature_state = raw if isinstance(raw, dict) else {}
    return _feature_state


def _save_state() -> None:
    try:
        _write_json(FT.STATE_FILE, _state())
    except OSError as e:
        logger.warning(f"[FEAT] 상태 저장 실패: {e}")


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _alias_of(username: str) -> tuple:
    return _aliases().get(username, ("account_0", "Account_?"))


def _observe_sensor(account: AccountData, entity_id: str, state, attributes: dict) -> None:
    """센서 발행마다 호출: 구매·당첨을 원장에 기록하고 새 당첨·예치금 부족을 알린다."""
    try:
        aid, label = _alias_of(account.username)
        items = FT.ledger_items_from_sensor(
            aid, entity_id, state, attributes, FT.lotto_prizes_from_cache(account.sensor_cache)
        )
        if items:
            led, now, new_wins, changed = _get_ledger(), FT.now_kst(), [], False
            fresh = []
            for it in items:
                if led.add(aid, it, now):
                    changed = True
                    fresh.append(dict(it, acct=aid))
                    if it["kind"] == "win":
                        new_wins.append(it)
            if fresh:
                _queue_household(fresh)
            if changed:
                try:
                    _write_json(FT.LEDGER_FILE, led.entries)
                except OSError as e:
                    logger.warning(f"[FEAT] 원장 저장 실패: {e}")
            for it in new_wins:
                logger.info(f"[WIN][{label}] {it['game']} {it['round']}회 {it['info']} {it['amount']:,}원")
                _spawn(_notify_win(label, it))
            if new_wins:
                _spawn(_nudge_ha_calendar())
        if entity_id == "lotto45_balance":
            _spawn(_check_low_deposit(aid, label, state))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[FEAT] 센서 관찰 실패: {e}")


async def _ha_post(path: str, payload: dict) -> bool:
    """HA Core API 호출(Supervisor 토큰). 실패해도 예외를 내지 않는다."""
    if not config["supervisor_token"]:
        return False
    import aiohttp
    url = f"{config['ha_url']}/api/{path}"
    headers = {"Authorization": f"Bearer {config['supervisor_token']}", "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 300:
                    logger.warning(f"[NOTIFY] {path} 실패: HTTP {resp.status}")
                    return False
                return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[NOTIFY] {path} 실패: {e}")
        return False


def _notification_id(tag: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9_]", "_", tag.lower())[:120]


async def notify_user(title: str, message: str, tag: str = "dhlotto45") -> bool:
    """설정에 따라 HA 알림(persistent_notification)과 추가 notify 서비스로 보낸다."""
    n = _load_settings()["notify"]
    ok = False
    if n["persistent"]:
        ok = await _ha_post("services/persistent_notification/create",
                            {"title": title, "message": message, "notification_id": _notification_id(tag)}) or ok
    if n["service"]:
        ok = await _ha_post("services/notify/" + n["service"].split(".", 1)[1],
                            {"title": title, "message": message}) or ok
    return ok


async def fire_event(event_type: str, data: dict) -> None:
    """자동화용 HA 이벤트. 계정은 별칭(Account_N)만 담는다."""
    await _ha_post(f"events/{event_type}", data)


async def _notify_win(label: str, item: dict) -> None:
    await fire_event("dhlotto45_win", {"account": label, "game": item["game"], "round": item["round"],
                                       "result": item["info"], "amount": item["amount"]})
    if _load_settings()["notify"]["win"]:
        title, msg = FT.win_message(label, item)
        await notify_user(title, msg, f"dhlotto45_win_{item['key']}")


async def _check_low_deposit(aid: str, label: str, balance) -> None:
    n = _load_settings()["notify"]
    thr = n["low_deposit_threshold"]
    if not n["low_deposit"]:
        return
    st = _state()
    key = f"low_deposit:{aid}"
    today = FT.now_kst().date().isoformat()
    if not FT.needs_low_deposit_alert(balance, thr, today, st.get(key)):
        return
    st[key] = today
    _save_state()
    bal = int(float(balance))
    await fire_event("dhlotto45_low_deposit", {"account": label, "balance": bal, "threshold": thr})
    await notify_user(f"💸 예치금 부족 ({label})",
                      f"예치금 {bal:,}원 — 알림 기준 {thr:,}원보다 적습니다. 구매 전에 충전하세요.",
                      f"dhlotto45_low_{aid}")


async def _after_purchase(acc_label: str, action: str, label: str, status: str, message: str, source: str) -> None:
    await fire_event("dhlotto45_purchase", {"account": acc_label, "action": action, "label": label,
                                            "status": status, "message": message[:200], "source": source})
    if _load_settings()["notify"]["purchase"]:
        title, msg = FT.purchase_message(acc_label, label, status, message[:200], source)
        await notify_user(title, msg, f"dhlotto45_purchase_{acc_label}")


# ---------------------------------------------------------------- v2.12.0 럭키 랩: 예산·가계부·리포트
_pending_spend: list = []          # 구매 직후 원장에 잡히기 전까지의 지출 [{acct, month, ts, cost}]
_household_queue: list = []
_household_task = None
_insight_pub_at = -1e9          # 부팅 직후(monotonic 이 작을 때)도 첫 회는 바로 발행
INSIGHT_PUBLISH_SECONDS = 600


def _budget_block_reason(account: Optional[AccountData], cost: int) -> str:
    """월 예산을 넘는 구매면 사유 문자열. 예산이 꺼져 있으면 빈 문자열."""
    if account is None or cost <= 0:
        return ""
    budget = _load_settings()["budget"]["monthly"]
    if budget <= 0:
        return ""
    aid, _label = _alias_of(account.username)
    st = IN.budget_status(_get_ledger().entries, _pending_spend, aid, FT.now_kst(), budget, cost)
    return st["reason"]


def _note_spend(account: AccountData, cost: int) -> None:
    global _pending_spend
    aid, _label = _alias_of(account.username)
    now = FT.now_kst()
    _pending_spend = IN.prune_pending(_pending_spend, now.timestamp())
    _pending_spend.append({"acct": aid, "month": now.strftime("%Y-%m"), "ts": now.timestamp(), "cost": int(cost)})


def _labels() -> dict:
    return {aid: lb for aid, lb in _aliases().values()}


def _queue_household(items: list) -> None:
    """새 구매·당첨을 가계부(kr_ledger_kit)로 보낼 대기열에 넣는다(90초 모아서 회차별로 한 번에)."""
    global _household_task
    try:
        if not _load_settings()["household"]["enabled"]:
            return
    except Exception:  # noqa: BLE001
        return
    _household_queue.extend(items)
    if _household_task is None or _household_task.done():
        _household_task = asyncio.get_event_loop().create_task(_flush_household())


async def _flush_household() -> None:
    await asyncio.sleep(90)
    items = list(_household_queue)
    _household_queue.clear()
    payloads = IN.household_payloads(items, _labels(), FT.now_kst().date())
    sent = 0
    for pl in payloads:
        if await _ha_post("services/kr_ledger/add_transaction", pl):
            sent += 1
    if payloads:
        logger.info(f"[HOUSEHOLD] 가계부(kr_ledger)에 {sent}/{len(payloads)}건 기록")


async def _ha_get(path: str):
    """HA Core API GET(Supervisor 토큰). 실패하면 None."""
    if not config["supervisor_token"]:
        return None
    import aiohttp
    url = f"{config['ha_url']}/api/{path}"
    headers = {"Authorization": f"Bearer {config['supervisor_token']}"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status >= 300:
                    return None
                return await resp.json(content_type=None)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[HA] GET {path} 실패: {e}")
        return None


async def _household_available() -> bool:
    services = await _ha_get("services")
    if not isinstance(services, list):
        return False
    for d in services:
        if isinstance(d, dict) and d.get("domain") == "kr_ledger":
            return "add_transaction" in (d.get("services") or {})
    return False


def _insight_snapshot(today=None) -> dict:
    """대시보드 인사이트 카드·센서·리포트가 함께 쓰는 계산 결과."""
    now = FT.now_kst()
    today = today or now.date()
    entries = _get_ledger().entries
    settings = _load_settings()
    budget = settings["budget"]["monthly"]
    labels = _labels()
    rows = []
    for username in accounts:
        aid, label = _alias_of(username)
        rows.append({"id": aid, "label": label, "luck": IN.luck_index(entries, today, aid),
                     "budget": IN.budget_status(entries, _pending_spend, aid, now, budget)})
    claim_list = IN.claims(entries, today)
    for c in claim_list:
        c["label"] = labels.get(c["acct"], c["acct"])
    return {"today": today.isoformat(), "accounts": rows, "all": {"luck": IN.luck_index(entries, today)},
            "claims": claim_list, "budget_monthly": budget, "household": settings["household"]["enabled"],
            "probabilities": {"lotto_any": round(IN.P_LOTTO_ANY, 6), "pension_any": IN.P_PENSION_ANY,
                              "lotto_first": IN.LOTTO_COMBOS}}


async def _publish_insight_sensors(snap: dict) -> None:
    by_id = {r["id"]: r for r in snap["accounts"]}
    for username, account in accounts.items():
        aid, _label = _alias_of(username)
        r = by_id.get(aid)
        if not r:
            continue
        lk, bd = r["luck"], r["budget"]
        if lk["percentile"] is not None:
            await publish_sensor_for_account(account, "lotto45_luck_index", lk["percentile"], {
                "top_pct": lk["top_pct"], "grade": lk["grade"], "games": lk["games"], "wins": lk["wins"],
                "expected_wins": lk["expected"], "jackpot_years": lk["jackpot_years"],
                "unit_of_measurement": "%", "friendly_name": "운 지수(백분위)", "icon": "mdi:clover",
            })
        await publish_sensor_for_account(account, "lotto45_month_spend", bd["used"], {
            "month": bd["month"], "budget": bd["budget"], "left": bd["left"], "pct": bd["pct"],
            "unit_of_measurement": "KRW", "friendly_name": "이번 달 복권 지출", "icon": "mdi:cash-register",
        })
        mine = [c for c in snap["claims"] if c["acct"] == aid and c["action"] == "visit" and c["days_left"] >= 0]
        await publish_sensor_for_account(account, "lotto45_claim_deadline",
                                         f"D-{mine[0]['days_left']}" if mine else "없음", {
            "deadline": mine[0]["deadline"] if mine else None, "count": len(mine),
            "claims": [{k: c[k] for k in ("game", "round", "info", "amount", "deadline", "days_left")} for c in mine[:5]],
            "friendly_name": "당첨금 수령 기한", "icon": "mdi:calendar-alert",
        })


async def _insight_tick() -> None:
    """30초마다: 인사이트 센서(10분 간격)·주간 리포트·토요일 마감 알림·수령 리마인더."""
    global _insight_pub_at
    now = FT.now_kst()
    if time.monotonic() - _insight_pub_at >= INSIGHT_PUBLISH_SECONDS:
        _insight_pub_at = time.monotonic()
        await _publish_insight_sensors(_insight_snapshot())
    settings = _load_settings()
    n = settings["notify"]
    st = _state()
    today = now.date().isoformat()
    if n["weekly_report"] and IN.in_window(now, 6, 9) and st.get("weekly_report") != today:
        st["weekly_report"] = today
        _save_state()
        budgets = {aid: settings["budget"]["monthly"] for aid in _labels()}
        title, body = IN.weekly_report(_get_ledger().entries, _labels(), now.date(), budgets, _pending_spend, now)
        body = "\n".join(FT.safe_notify_text(line, 300) for line in body.splitlines())
        await fire_event("dhlotto45_weekly_report", {"title": title})
        await notify_user(title, body, "dhlotto45_weekly")
    if n["deadline_reminder"] and config["enable_lotto645"] and IN.in_window(now, 5, 18) \
            and st.get("deadline_reminder") != today:
        st["deadline_reminder"] = today
        _save_state()
        rows = []
        for username, account in accounts.items():
            aid, label = _alias_of(username)
            rows.append({"aid": aid, "label": label,
                         "weekly_count": (account.sensor_cache.get("lotto45_weekly_purchase_count") or {}).get("state"),
                         "logged_in": bool(account.enabled and account.lotto_645 and account.client
                                           and account.client.logged_in)})
        missing = IN.accounts_missing_lotto(rows, settings)
        if missing:
            await notify_user("⏰ 로또 판매 마감 2시간 전",
                              f"{', '.join(missing)}: 이번 주 로또를 아직 사지 않았어요. 판매는 오늘 20:00에 마감됩니다.",
                              "dhlotto45_deadline")
    if n["claim_reminder"] and IN.in_window(now, None, 10, 0, 12 * 60) and st.get("claim_check") != today:
        st["claim_check"] = today
        sent = st.get("claim_sent") if isinstance(st.get("claim_sent"), dict) else {}
        labels = _labels()
        for c, stage in IN.claim_reminders_due(IN.claims(_get_ledger().entries, now.date()), sent):
            title, body = IN.claim_message(labels.get(c["acct"], c["acct"]), c, stage)
            await notify_user(title, FT.safe_notify_text(body, 400), f"dhlotto45_claim_{c['round']}")
            sent = IN.mark_claim_sent(sent, c, stage, int(time.time()))
        st["claim_sent"] = sent
        _save_state()


# ---------------------------------------------------------------- 정기 자동 구매
def _auto_buy_block_reason(account: Optional[AccountData], action: str, amount: int) -> str:
    """자동 구매 전 추가 안전 점검. 막아야 하면 사유 문자열.

    주간 5게임·연금 하루 한도·계정 간 20초·15초 중복 방지는 구매 함수가 그대로 검사한다.
    """
    if account is None or not account.enabled:
        return "계정이 없거나 꺼져 있습니다"
    if account.last_action and account.last_action.get("status") == "running":
        return "다른 구매가 진행 중입니다"
    if action.startswith("lotto"):
        if not account.lotto_645 or not (account.client and account.client.logged_in):
            return "로또 로그인이 되어 있지 않습니다"
        if not is_purchase_available_now():
            return "로또 판매 시간이 아닙니다 (매일 00:00~06:00, 토요일은 20:00부터)"
    elif not account.pension:
        return "연금복권 구매를 쓸 수 없습니다 (chromium 미설치 기기)"
    avail = (account.sensor_cache.get("lotto45_balance") or {}).get("attributes", {}).get("purchase_available")
    try:
        if avail is not None and int(float(avail)) < amount:
            return f"예치금이 부족합니다 (구매 가능 {int(float(avail)):,}원, 필요 {amount:,}원)"
    except (TypeError, ValueError):
        pass
    return _budget_block_reason(account, amount)


async def _auto_buy_tick() -> None:
    settings = _load_settings()
    if not settings["auto_buy"]["enabled"]:
        return
    now = FT.now_kst()
    st = _state()
    done = st.get("auto_done") if isinstance(st.get("auto_done"), dict) else {}
    due = FT.due_schedules(settings, now, done)
    if not due:
        return
    aliases = _aliases()
    order = [aliases[u][0] for u in accounts]
    for sch, key in due:
        # 실행 전에 먼저 기록: 도중에 재시작돼도 같은 날 두 번 사지 않는다.
        done[key] = int(time.time())
        st["auto_done"] = FT.prune_done(done, now.date())
        _save_state()
        label, amount = action_label(sch["action"])
        targets = FT.schedule_targets(sch, order)
        logger.info(f"[AUTO] 일정 {sch['name'] or sch['id']} 실행: {label} → {', '.join(targets) or '대상 없음'}")
        for i, aid in enumerate(targets):
            username = resolve_alias(list(accounts.keys()), aid)
            account = accounts.get(username) if username else None
            acc_label = _alias_of(username)[1] if username else aid
            reason = _auto_buy_block_reason(account, sch["action"], amount)
            if reason:
                logger.warning(f"[AUTO][{acc_label}] {label} 건너뜀: {reason}")
                await _after_purchase(acc_label, sch["action"], label, "skipped", reason, "schedule")
                continue
            task = _start_action(account, sch["action"], "schedule")
            if task is not None:
                await task
            if i < len(targets) - 1:
                await asyncio.sleep(INTER_ACCOUNT_COOLDOWN_SECONDS + 5)


async def auto_buy_loop() -> None:
    """30초마다 정기 자동 구매 일정을 확인한다(마스터 스위치가 켜졌을 때만 동작)."""
    await asyncio.sleep(20)
    while True:
        try:
            await _auto_buy_tick()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.error(f"[AUTO] 일정 처리 오류: {e}", exc_info=True)
        try:
            await _insight_tick()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.error(f"[INSIGHT] 처리 오류: {e}", exc_info=True)
        await asyncio.sleep(30)


# ---------------------------------------------------------------- API
async def _read_json_body(request: Request, limit: int) -> dict:
    raw = await request.body()
    if len(raw) > limit:
        raise HTTPException(status_code=413, detail="데이터가 너무 큽니다.")
    import json as _json
    try:
        body = _json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="요청 형식이 올바르지 않습니다.")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="요청 형식이 올바르지 않습니다.")
    return body


def _require_csrf(request: Request) -> None:
    if not csrf_ok(DASHBOARD_CSRF_TOKEN, request.headers.get(CSRF_HEADER)):
        raise HTTPException(status_code=403, detail="보안 토큰이 올바르지 않습니다. 페이지를 새로고침하세요.")


@app.get("/api/settings")
async def api_get_settings(request: Request):
    """알림·즐겨찾기·정기 자동 구매 설정."""
    _require_ingress(request)
    return JSONResponse(_load_settings(), headers=_SECURITY_HEADERS)


@app.put("/api/settings")
async def api_put_settings(request: Request):
    """설정 부분 변경. Ingress 전용 + CSRF 필수, 값은 허용 목록으로 정규화."""
    _require_ingress(request)
    _require_csrf(request)
    change = await _read_json_body(request, FT.SETTINGS_MAX_BODY)
    async with _feature_lock:
        before = _load_settings()
        settings = FT.merge_settings(before, change)
        try:
            _write_json(FT.SETTINGS_FILE, settings)
        except OSError as e:
            logger.error(f"[FEAT] 설정 저장 실패: {e}")
            raise HTTPException(status_code=500, detail="설정을 저장하지 못했습니다.")
    if before["auto_buy"] != settings["auto_buy"]:
        _spawn(_nudge_ha_calendar())
    if before["auto_buy"]["enabled"] != settings["auto_buy"]["enabled"]:
        ha_user = request.headers.get("X-Remote-User-Name") or "?"
        logger.warning(f"[AUTO] 정기 자동 구매 {'켜짐' if settings['auto_buy']['enabled'] else '꺼짐'} "
                       f"(일정 {len(settings['auto_buy']['schedules'])}개, HA 사용자: {ha_user})")
    return JSONResponse(settings, headers=_SECURITY_HEADERS)


@app.get("/api/stats")
async def api_stats(request: Request, account: str = ""):
    """구매·당첨 통계(애드온이 본 기록 기준, 최근 12개월)."""
    _require_ingress(request)
    acct = account if (account.startswith("account_") and account[8:].isdigit() and len(account) <= 12) else ""
    data = _get_ledger().stats(FT.now_kst(), 12, acct)
    labels = {aid: lb for aid, lb in _aliases().values()}
    data["labels"] = labels
    return JSONResponse(data, headers=_SECURITY_HEADERS)


_LEDGER_IMPORT_MAX_BODY = 2 * 1024 * 1024
_notify_test_at = -1e9


@app.get("/api/ledger/export")
async def api_ledger_export(request: Request, format: str = "csv"):
    """원장(구매·당첨 기록) 내려받기: csv(엑셀용) 또는 json(가져오기용 백업)."""
    _require_ingress(request)
    import json as _json
    from fastapi.responses import Response
    entries = list(_get_ledger().entries)
    stamp = FT.now_kst().strftime("%Y%m%d")
    if format == "json":
        body = _json.dumps({"app": "dhlotto45", "version": APP_VERSION, "entries": entries}, ensure_ascii=False)
        media, name = "application/json; charset=utf-8", f"dhlotto45-ledger-{stamp}.json"
    else:
        labels = {aid: lb for aid, lb in _aliases().values()}
        body = "\ufeff" + FT.ledger_to_csv(entries, labels)
        media, name = "text/csv; charset=utf-8", f"dhlotto45-ledger-{stamp}.csv"
    headers = dict(_SECURITY_HEADERS)
    headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return Response(content=body.encode("utf-8"), media_type=media, headers=headers)


@app.post("/api/ledger/import")
async def api_ledger_import(request: Request):
    """JSON 백업 가져오기. Ingress + CSRF 필수, 항목마다 형식 검증 후 key 기준으로 합친다."""
    _require_ingress(request)
    _require_csrf(request)
    body = await _read_json_body(request, _LEDGER_IMPORT_MAX_BODY)
    try:
        entries, skipped = FT.validate_ledger_entries(body)
    except DashboardInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    async with _feature_lock:
        led = _get_ledger()
        added = led.merge(entries, FT.now_kst())
        try:
            _write_json(FT.LEDGER_FILE, led.entries)
        except OSError as e:
            logger.error(f"[FEAT] 원장 저장 실패: {e}")
            raise HTTPException(status_code=500, detail="기록을 저장하지 못했습니다.")
    logger.info(f"[FEAT] 원장 가져오기: 추가 {added}건, 건너뜀 {skipped}건")
    return JSONResponse({"added": added, "skipped": skipped, "total": len(led.entries)}, headers=_SECURITY_HEADERS)


@app.post("/api/notify-test")
async def api_notify_test(request: Request):
    """현재 알림 설정으로 테스트 알림 1건 보내기."""
    _require_ingress(request)
    _require_csrf(request)
    global _notify_test_at
    if time.monotonic() - _notify_test_at < 10:
        raise HTTPException(status_code=429, detail="테스트 알림은 10초에 한 번만 보낼 수 있습니다.")
    _notify_test_at = time.monotonic()
    ok = await notify_user("🔔 DH Lotto 45 테스트 알림", "알림 설정이 정상입니다.", "dhlotto45_test")
    return JSONResponse({"ok": ok}, headers=_SECURITY_HEADERS)


async def _chromium_version() -> str:
    exe = os.getenv("CHROMIUM_PATH") or ""
    if not exe:
        return "없음"
    try:
        proc = await asyncio.create_subprocess_exec(exe, "--version", stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
        return out.decode(errors="replace").strip() or exe
    except Exception as e:  # noqa: BLE001
        return f"{exe} (버전 확인 실패: {type(e).__name__})"


async def _build_diagnostics() -> str:
    import platform
    try:
        from importlib.metadata import version as _ver
        zd_ver = _ver("zendriver")
    except Exception:  # noqa: BLE001
        zd_ver = "미설치"
    now = FT.now_kst()
    lines = [
        f"DH Lotto 45 v{APP_VERSION} 진단 리포트 · {now.strftime('%Y-%m-%d %H:%M')} KST",
        f"- 기기: {platform.machine()} · Python {platform.python_version()}",
        f"- zendriver {zd_ver} · chromium {await _chromium_version()}",
        f"- MQTT: {'연결됨' if (mqtt_client and mqtt_client.connected) else '연결 안 됨'}"
        f"{(' · ' + mqtt_client.last_error) if (mqtt_client and mqtt_client.last_error) else ''}"
        f" · 인증 {'아이디 사용' if os.getenv('MQTT_USERNAME') else '없음'}",
        f"- 로또 판매 시간: {'예' if is_purchase_available_now() else '아니오'}",
    ]
    s = _load_settings()
    lines.append(f"- 정기 자동 구매: {'켜짐' if s['auto_buy']['enabled'] else '꺼짐'} · 일정 {len(s['auto_buy']['schedules'])}개"
                 f" · 즐겨찾기 {len(s['favorites'])}개 · 추가 알림 서비스 {'있음' if s['notify']['service'] else '없음'}")
    aliases = _aliases()
    for username, account in accounts.items():
        _aid, label = aliases[username]
        c = account.sensor_cache
        def sv(key):
            return (c.get(key) or {}).get("state", "-")
        la = account.last_action or {}
        lines.append(
            f"- {label}: 사용 {'예' if account.enabled else '아니오'} · 로그인 "
            f"{'정상' if (account.client and account.client.logged_in) else '안 됨'} · 연금 구매 "
            f"{'가능' if account.pension else '불가'} · 예치금 {sv('lotto45_balance')} · 동기화 {sv('lotto45_sync_status')}"
        )
        for key, nm in (("lotto45_login_error", "로그인 오류"), ("lotto45_purchase_error", "로또 오류"),
                        ("pension720_purchase_error", "연금 오류")):
            v = sv(key)
            if v not in ("-", "없음", None):
                lines.append(f"    {nm}: {v}")
        if la:
            lines.append(f"    마지막 구매: {la.get('label')} → {la.get('status')} {str(la.get('message') or '')[:160]}")
    lines.append("")
    lines.append("--- 최근 로그 ---")
    lines.extend(_ring_log.tail(150))
    return FT.scrub_text(_alias_text("\n".join(lines)))


@app.get("/api/diagnostics")
async def api_diagnostics(request: Request):
    """문의용 진단 리포트(아이디는 Account_N, IP·이메일·토큰은 가림)."""
    _require_ingress(request)
    return JSONResponse({"text": await _build_diagnostics()}, headers=_SECURITY_HEADERS)


@app.get("/api/ingress")
async def api_ingress(request: Request):
    """현재 요청이 Home Assistant Ingress 경유인지 반환 (모바일/외부 연동 시 참고)."""
    return {"ingress": is_ingress_request(request)}


@app.get("/health")
async def health(request: Request):
    """Health check. Ingress 경유 접근 시 ingress: true 포함."""
    accounts_status = {}
    logged_in_count = 0

    aliases = _aliases()
    for username, account in accounts.items():
        is_logged_in = bool(account.client and getattr(account.client, "logged_in", False))
        if is_logged_in:
            logged_in_count += 1
        accounts_status[aliases[username][1]] = {
            "logged_in": is_logged_in,
            "enabled": account.enabled,
            "status": "✅ Active" if is_logged_in else "❌ Login Failed",
        }

    # 계정이 없으면 ok (초기 상태), 있으면 최소 1개 로그인 시 ok
    status = "ok" if (len(accounts) == 0 or logged_in_count > 0) else "degraded"

    return {
        "status": status,
        "version": APP_VERSION,
        "ingress": is_ingress_request(request),
        "accounts": accounts_status,
        "total_accounts": len(accounts),
        "max_accounts": MAX_ACCOUNTS,
        "weekly_lotto_limit": WEEKLY_LOTTO_LIMIT,
        "daily_pension_limit": DAILY_PENSION_LIMIT,
        "min_update_interval": MIN_UPDATE_INTERVAL_SECONDS,
        "inter_account_cooldown_seconds": int(INTER_ACCOUNT_COOLDOWN_SECONDS),
        "logged_in_accounts": logged_in_count,
        "failed_accounts": len(accounts) - logged_in_count,
    }


@app.get("/accounts")
async def list_accounts():
    """List accounts"""
    result = []
    aliases = _aliases()
    for username, account in accounts.items():
        result.append({
            "account": aliases[username][1],  # 실제 아이디 대신 Account_N
            "enabled": account.enabled,
            "logged_in": account.client.logged_in if account.client else False,
        })
    return {"accounts": result}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=60099, log_level="info")
