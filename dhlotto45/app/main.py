# -*- coding: utf-8 -*-
"""
Lotto 45 Add-on Main Application v2.4.10
Home Assistant Add-on for DH Lottery 6/45
v2.0.8 - Session keep-alive fix + retry path overhaul (full session reset on any error)
"""

import os
import asyncio
import logging
import random
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
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from dh_lottery_client import DhLotteryClient, DhLotteryError, DhLotteryLoginError
from dh_lotto_645 import DhLotto645, DhLotto645SelMode, DhLotto645Error, _rank_drawed_to_result
from dh_lotto_analyzer import DhLottoAnalyzer
from dh_mobile_api import DhMobileApiClient, DhMobileApiError
from dh_pension_browser import (
    DhPensionBrowser,
    DhPensionBrowserError,
    validate_manual_selection,
)
from dh_pension_history import group_rounds, build_round, summarize
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

# Configuration variables
config = {
    "accounts": [],
    "enable_lotto645": os.getenv("ENABLE_LOTTO645", "true").lower() == "true",
    "enable_pension720": os.getenv("ENABLE_PENSION720", "true").lower() == "true",
    "update_interval": clamp_update_interval(int(os.getenv("UPDATE_INTERVAL", "3600"))),
    "use_mqtt": os.getenv("USE_MQTT", "false").lower() == "true",
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
    
    mqtt_client.client.publish(input_state_topic, "auto,auto,auto,auto,auto,auto", qos=1, retain=True)

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
        mqtt_client.client.publish(pm_state_topic, "", qos=1, retain=True)

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
                asyncio.run_coroutine_threadsafe(
                    execute_pension_manual_purchase(account), event_loop
                )
            return

        # 연금복권 자동 구매 버튼 라우팅 (buy_pension_auto_1 / buy_pension_auto_5)
        if button_suffix.startswith("buy_pension"):
            pension_count = 5 if button_suffix.endswith("_5") else 1
            if event_loop and event_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    execute_pension_purchase(account, pension_count),
                    event_loop
                )
            return

        if event_loop and event_loop.is_running():
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
        result = await asyncio.wait_for(
            account.pension.async_buy_auto(count), timeout=180
        )
        pension_daily_tracker.record_purchase(username, result.get("count", count))
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
        # 성공 시 과거 오류 센서 해제
        await publish_sensor_for_account(account, "pension720_purchase_error", "없음", {
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:cart-check",
        })
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
        result = await asyncio.wait_for(
            account.pension.async_buy_manual(group, digits), timeout=180
        )
        pension_daily_tracker.record_purchase(username, result.get("count", 1))
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
        await publish_sensor_for_account(account, "pension720_purchase_error", "없음", {
            "friendly_name": "연금복권 구매 오류",
            "icon": "mdi:cart-check",
        })
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
    
    # MQTT
    if config["use_mqtt"]:
        logger.info("Initializing MQTT...")
        
        client_id_suffix = "_beta" if config["is_beta"] else ""
        mqtt_client = MQTTDiscovery(
            mqtt_url=os.getenv("MQTT_URL", "mqtt://homeassistant.local:1883"),
            username=os.getenv("MQTT_USERNAME"),
            password=os.getenv("MQTT_PASSWORD"),
            client_id_suffix=client_id_suffix,
        )
        
        if mqtt_client.connect():
            logger.info("MQTT connected")
            
            # Only register buttons for successfully logged in accounts
            for account in accounts.values():
                if account.enabled and config["enable_lotto645"] and account.client and account.client.logged_in:
                    await register_buttons_for_account(account)
                elif account.enabled and (not account.client or not account.client.logged_in):
                    logger.warning(f"[BUTTON][{account.username}] Skipping button registration - not logged in")
            
            # Subscribe to button commands for ALL logged-in accounts
            if accounts:
                # Set callback once
                mqtt_client.client.on_message = on_button_command
                
                # Subscribe to each account's buttons
                for account in accounts.values():
                    if account.enabled and account.client and account.client.logged_in:
                        button_ids = ["buy_auto_1", "buy_auto_5", "buy_manual", "generate_random"]
                        if config.get("enable_pension720", True):
                            button_ids += [
                                "buy_pension_auto_1", "buy_pension_auto_5",
                                "buy_pension_manual", "diag_pension_manual",
                            ]

                        # Subscribe to button commands
                        for button_id in button_ids:
                            command_topic = f"homeassistant/button/{mqtt_client.topic_prefix}_{account.username}_{button_id}/command"
                            mqtt_client.client.subscribe(command_topic)
                            logger.info(f"[MQTT] Subscribed: {command_topic}")

                        # Subscribe to input_text (로또 수동번호 + 연금 수동번호)
                        text_ids = ["manual_numbers"]
                        if config.get("enable_pension720", True):
                            text_ids.append("pension_manual")
                        for text_id in text_ids:
                            input_command_topic = f"homeassistant/text/{mqtt_client.topic_prefix}_{account.username}_{text_id}/set"
                            mqtt_client.client.subscribe(input_command_topic)
                            logger.info(f"[MQTT] Subscribed: {input_command_topic}")
                
                logger.info(f"[MQTT] Subscribed to {len([a for a in accounts.values() if a.enabled and a.client and a.client.logged_in])} account(s)")
        else:
            logger.warning("MQTT connection failed")
            mqtt_client = None
    
    return success_count > 0


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
    
    logger.info("Starting v2.4.10 Multi-Account...")
    
    event_loop = asyncio.get_running_loop()
    await init_clients()
    
    tasks = []
    for account in accounts.values():
        if account.enabled:
            task = asyncio.create_task(background_tasks_for_account(account))
            account.update_task = task
            tasks.append(task)
    
    logger.info("Started")
    
    yield
    
    logger.info("Shutting down...")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await cleanup_clients()


app = FastAPI(title="Lotto 45 Multi", version="2.4.10", lifespan=lifespan)

# CORS: 모바일 앱 및 외부/Ingress 접근 지원
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Ingress-Request"],
)


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

    # 회차(ltEpsd)별 그룹핑 → 이번/지난 회차 센서로 발행(집계는 dh_pension_history).
    rounds = group_rounds(items)
    ordered = sorted(rounds.keys(), reverse=True)
    this_round = ordered[0] if ordered else 0
    last_round = ordered[1] if len(ordered) > 1 else 0

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


async def update_sensors_for_account(account: AccountData):
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

    # 구매 불가 시간대 체크 (최우선)
    if not is_purchase_available_now():
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
    
    # REST API fallback
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


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Main page. Ingress 경유 시 배지 표시."""
    accounts_html = "<ul>"
    for username, account in accounts.items():
        status = "✅" if account.client and account.client.logged_in else "❌"
        enabled = "✅" if account.enabled else "❌"
        accounts_html += f"<li><strong>{username}</strong>: {status} (Enabled: {enabled})</li>"
    accounts_html += "</ul>"
    ingress_badge = (
        '<span style="background:#0d47a1;color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">Ingress</span>'
        if is_ingress_request(request) else ""
    )
    return f"""
    <!DOCTYPE html>
    <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Lotto 45 v2.4.10</title>
            <style>
                body {{ font-family: Arial; margin: 40px; }}
                .info {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <h1>🎰 Lotto 45 <span style="color:#666;">v2.4.10 Multi-Account</span> {ingress_badge}</h1>
            <div class="info">
                <h2>Accounts ({len(accounts)})</h2>
                {accounts_html}
            </div>
            <ul>
                <li><a href="health">Health Check</a></li>
                <li><a href="accounts">Accounts</a></li>
            </ul>
        </body>
    </html>
    """


@app.get("/api/ingress")
async def api_ingress(request: Request):
    """현재 요청이 Home Assistant Ingress 경유인지 반환 (모바일/외부 연동 시 참고)."""
    return {"ingress": is_ingress_request(request)}


@app.get("/health")
async def health(request: Request):
    """Health check. Ingress 경유 접근 시 ingress: true 포함."""
    accounts_status = {}
    logged_in_count = 0

    for username, account in accounts.items():
        is_logged_in = bool(account.client and getattr(account.client, "logged_in", False))
        if is_logged_in:
            logged_in_count += 1
        accounts_status[username] = {
            "logged_in": is_logged_in,
            "enabled": account.enabled,
            "status": "✅ Active" if is_logged_in else "❌ Login Failed",
        }

    # 계정이 없으면 ok (초기 상태), 있으면 최소 1개 로그인 시 ok
    status = "ok" if (len(accounts) == 0 or logged_in_count > 0) else "degraded"

    return {
        "status": status,
        "version": "2.4.10",
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
    for username, account in accounts.items():
        result.append({
            "username": username,
            "enabled": account.enabled,
            "logged_in": account.client.logged_in if account.client else False,
        })
    return {"accounts": result}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=60099, log_level="info")
