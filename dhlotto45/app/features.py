"""
features.py
대시보드 확장 기능(v2.7.0)의 순수 로직. FastAPI/HA 의존성이 없어 단위 테스트가 쉽다.

- 설정(알림·즐겨찾기·정기 자동 구매) 검증/정규화
- 구매·당첨 원장(ledger): 센서 값에서 구매/당첨을 뽑아 중복 없이 기록 → 월별 통계, 새 당첨 알림
- 정기 자동 구매 일정 판정
- 진단 리포트용 로그 링버퍼와 민감정보 가림
"""

from __future__ import annotations

import collections
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from dashboard_api import (
    DashboardInputError,
    _clean_text,
    normalize_lotto_manual,
    normalize_pension_manual,
)

KST = timezone(timedelta(hours=9))

SETTINGS_FILE = "dashboard_settings.json"
LEDGER_FILE = "ledger.json"
STATE_FILE = "feature_state.json"
SETTINGS_MAX_BODY = 8192

FAV_MAX = 10
SCHED_MAX = 8
SCHED_WINDOW_MIN = 10          # 예약 시각부터 이 시간(분) 안에만 실행(늦게 켜져도 몰아서 사지 않음)
SCHED_ACTIONS = ("lotto_auto_1", "lotto_auto_5", "pension_auto_1", "pension_auto_5")
NOTIFY_SERVICE_RE = re.compile(r"^notify\.[a-z0-9_]{1,64}$")
_ID_RE = re.compile(r"^[a-z0-9]{1,12}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

LEDGER_MAX = 5000
LEDGER_MONTHS = 36
LOTTO_FIXED_PRIZE = {4: 50000, 5: 5000}
PRIZE_KEYS = ("first", "second", "third", "fourth", "fifth")

DEFAULT_SETTINGS = {
    "notify": {
        "persistent": True,          # HA 알림(종 모양)에 남기기
        "service": "",               # 추가 알림 서비스(예: notify.mobile_app_my_phone)
        "win": True,                 # 당첨 알림
        "purchase": True,            # 구매 결과 알림
        "low_deposit": True,         # 예치금 부족 알림
        "low_deposit_threshold": 5000,
    },
    "favorites": [],
    "auto_buy": {"enabled": False, "schedules": []},
}


def _new_id() -> str:
    return secrets.token_hex(4)


def _norm_id(value) -> str:
    v = str(value or "").lower()
    return v if _ID_RE.match(v) else _new_id()


def _norm_account(value, allow_all: bool) -> str:
    v = str(value or "")
    if allow_all and v == "all":
        return "all"
    if v.startswith("account_") and v[8:].isdigit() and len(v) <= 12:
        return v
    return "all" if allow_all else ""


def normalize_favorite(raw) -> dict | None:
    """즐겨찾기 1개 검증. 잘못되면 None."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type")
    name = _clean_text(raw.get("name"), 20)
    try:
        if kind == "lotto":
            numbers = normalize_lotto_manual(raw.get("numbers"))
            return {"id": _norm_id(raw.get("id")), "type": "lotto", "name": name, "numbers": numbers}
        if kind == "pension":
            gd = normalize_pension_manual(raw.get("group"), raw.get("digits"))
            g, d = gd.split(",")
            return {"id": _norm_id(raw.get("id")), "type": "pension", "name": name, "group": int(g), "digits": d}
    except DashboardInputError:
        return None
    return None


def normalize_schedule(raw) -> dict | None:
    """정기 자동 구매 일정 1개 검증. 자동 구매(1·5게임/매)만 허용, 잘못되면 None."""
    if not isinstance(raw, dict):
        return None
    action = raw.get("action")
    if action not in SCHED_ACTIONS:
        return None
    t = str(raw.get("time") or "")
    if not _TIME_RE.match(t):
        return None
    days = raw.get("days")
    if not isinstance(days, list):
        return None
    days = sorted({int(d) for d in days if isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6})
    if not days:
        return None
    return {
        "id": _norm_id(raw.get("id")),
        "name": _clean_text(raw.get("name"), 20),
        "enabled": raw.get("enabled") is not False,
        "account": _norm_account(raw.get("account"), allow_all=True),
        "action": action,
        "days": days,          # 0=월 … 6=일
        "time": t,             # KST HH:MM
    }


def normalize_settings(raw) -> dict:
    """저장/응답용 설정 정규화. 알 수 없는 키는 버리고 잘못된 값은 기본값/제외."""
    p = raw if isinstance(raw, dict) else {}
    n_in = p.get("notify") if isinstance(p.get("notify"), dict) else {}
    notify = dict(DEFAULT_SETTINGS["notify"])
    for key in ("persistent", "win", "purchase", "low_deposit"):
        if isinstance(n_in.get(key), bool):
            notify[key] = n_in[key]
    svc = str(n_in.get("service") or "").strip()
    notify["service"] = svc if NOTIFY_SERVICE_RE.match(svc) else ""
    thr = n_in.get("low_deposit_threshold")
    if isinstance(thr, (int, float)) and not isinstance(thr, bool):
        notify["low_deposit_threshold"] = max(0, min(1_000_000, int(thr) // 1000 * 1000))

    favorites = []
    for f in (p.get("favorites") if isinstance(p.get("favorites"), list) else [])[:FAV_MAX]:
        nf = normalize_favorite(f)
        if nf and nf["id"] not in {x["id"] for x in favorites}:
            favorites.append(nf)

    a_in = p.get("auto_buy") if isinstance(p.get("auto_buy"), dict) else {}
    schedules = []
    for s in (a_in.get("schedules") if isinstance(a_in.get("schedules"), list) else [])[:SCHED_MAX]:
        ns = normalize_schedule(s)
        if ns and ns["id"] not in {x["id"] for x in schedules}:
            schedules.append(ns)
    auto_buy = {"enabled": a_in.get("enabled") is True, "schedules": schedules}
    return {"notify": notify, "favorites": favorites, "auto_buy": auto_buy}


def merge_settings(current, change) -> dict:
    """현재 설정에 부분 변경을 덮어쓴 뒤 정규화. notify/auto_buy 는 키 단위 병합."""
    base = normalize_settings(current)
    if isinstance(change, dict):
        if isinstance(change.get("notify"), dict):
            base["notify"].update(change["notify"])
        if isinstance(change.get("favorites"), list):
            base["favorites"] = change["favorites"]
        if isinstance(change.get("auto_buy"), dict):
            base["auto_buy"].update(change["auto_buy"])
    return normalize_settings(base)


# ---------------------------------------------------------------- schedule
def due_schedules(settings, now_kst: datetime, done) -> list:
    """지금 실행할 일정 목록 [(schedule, run_key)]. 마스터 스위치가 꺼져 있으면 빈 목록.

    예약 시각 ~ +SCHED_WINDOW_MIN 분 사이에만, 일정·날짜당 한 번(run_key 로 중복 방지).
    """
    s = normalize_settings(settings)
    if not s["auto_buy"]["enabled"]:
        return []
    done = done or {}
    out = []
    for sch in s["auto_buy"]["schedules"]:
        if not sch["enabled"] or now_kst.weekday() not in sch["days"]:
            continue
        hh, mm = (int(x) for x in sch["time"].split(":"))
        start = now_kst.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if not (start <= now_kst < start + timedelta(minutes=SCHED_WINDOW_MIN)):
            continue
        key = f"{sch['id']}:{now_kst.date().isoformat()}"
        if key in done:
            continue
        out.append((sch, key))
    return out


def schedule_targets(schedule, aliases_in_order) -> list:
    """일정이 대상으로 하는 계정 별칭 목록(account_N)."""
    acc = schedule.get("account")
    if acc == "all":
        return list(aliases_in_order)
    return [a for a in aliases_in_order if a == acc]


def prune_done(done: dict, today) -> dict:
    """7일 지난 실행 기록 제거."""
    keep = {}
    cutoff = (today - timedelta(days=7)).isoformat()
    for k, v in (done or {}).items():
        d = str(k).rsplit(":", 1)[-1]
        if d >= cutoff:
            keep[k] = v
    return keep


# ---------------------------------------------------------------- ledger
def lotto_prizes_from_cache(cache) -> dict:
    """센서 캐시의 최신 회차 등수별 1게임 당첨금 → {"round": n, rank: amount}."""
    out = {"round": 0}
    try:
        out["round"] = int((cache.get("lotto645_round") or {}).get("state") or 0)
    except (TypeError, ValueError):
        out["round"] = 0
    for i, key in enumerate(PRIZE_KEYS, start=1):
        try:
            out[i] = int((cache.get(f"lotto645_{key}_prize") or {}).get("state") or 0)
        except (TypeError, ValueError):
            out[i] = 0
    return out


_LOTTO_GAME_RE = re.compile(r"^lotto45_(prev_)?game_([1-5])$")
_LOTTO_RESULT_RE = re.compile(r"^lotto45_(prev_)?game_([1-5])_result$")
_RANK_RE = re.compile(r"([1-5])등")


def _nums_key(numbers) -> str:
    try:
        return "-".join(str(int(n)) for n in sorted(int(x) for x in numbers))
    except (TypeError, ValueError):
        return ""


def ledger_items_from_sensor(alias: str, entity_id: str, state, attrs, prizes=None) -> list:
    """센서 1건에서 원장 항목(구매·당첨)을 뽑는다. 각 항목은 고유 key 로 중복 제거된다."""
    attrs = attrs if isinstance(attrs, dict) else {}
    items = []
    m = _LOTTO_GAME_RE.match(entity_id)
    if m:
        nums = _nums_key(attrs.get("numbers") or [])
        rnd = _safe_int(attrs.get("round_no"))
        if nums and rnd > 0:
            items.append({"key": f"lotto:{alias}:{rnd}:{attrs.get('slot') or '-'}:{nums}", "kind": "buy",
                          "game": "lotto", "amount": 1000, "round": rnd, "info": nums})
        return items
    m = _LOTTO_RESULT_RE.match(entity_id)
    if m:
        rk = _RANK_RE.search(str(state or ""))
        nums = _nums_key(attrs.get("my_numbers") or [])
        rnd = _safe_int(attrs.get("round_no"))
        if rk and "낙첨" not in str(state) and nums and rnd > 0:
            rank = int(rk.group(1))
            prizes = prizes or {}
            amount = LOTTO_FIXED_PRIZE.get(rank, 0)
            if prizes.get("round") == rnd and prizes.get(rank):
                amount = prizes[rank]
            items.append({"key": f"lotto-win:{alias}:{rnd}:{nums}", "kind": "win", "game": "lotto",
                          "amount": amount, "round": rnd, "info": f"{rank}등", "rank": rank})
        return items
    if entity_id in ("pension720_this_round", "pension720_last_round"):
        rnd = _safe_int(attrs.get("round_no"))
        for g in attrs.get("games") or []:
            if not isinstance(g, dict) or rnd <= 0:
                continue
            grp, num = str(g.get("group") or ""), str(g.get("number") or "")
            if not num:
                continue
            items.append({"key": f"pension:{alias}:{rnd}:{grp}:{num}", "kind": "buy", "game": "pension",
                          "amount": 1000, "round": rnd, "info": f"{grp}조 {num}"})
            result = str(g.get("result") or "")
            win_amt = _safe_int(g.get("win_amount"))
            rank = _safe_int(g.get("rank"))
            if (win_amt > 0 or rank > 0) and "낙첨" not in result and result not in ("", "-", "미추첨"):
                items.append({"key": f"pension-win:{alias}:{rnd}:{grp}:{num}", "kind": "win", "game": "pension",
                              "amount": win_amt, "round": rnd, "info": result or f"{rank}등",
                              "rank": rank})
    return items


def _safe_int(v) -> int:
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


class Ledger:
    """구매·당첨 원장. 항목 key 로 중복을 막고 오래된 항목은 정리한다."""

    def __init__(self, entries=None):
        self.entries = []
        self._keys = set()
        for e in entries or []:
            if isinstance(e, dict) and e.get("key") and e["key"] not in self._keys:
                self.entries.append(e)
                self._keys.add(e["key"])

    def add(self, alias: str, item: dict, now: datetime) -> bool:
        """새 항목이면 기록하고 True."""
        key = item.get("key")
        if not key or key in self._keys:
            return False
        entry = {
            "key": key, "acct": alias, "kind": item["kind"], "game": item["game"],
            "amount": int(item.get("amount") or 0), "round": int(item.get("round") or 0),
            "info": str(item.get("info") or "")[:40], "month": now.strftime("%Y-%m"),
            "ts": int(now.timestamp()),
        }
        self.entries.append(entry)
        self._keys.add(key)
        self.prune(now)
        return True

    def prune(self, now: datetime) -> None:
        cutoff = (now.replace(day=1) - timedelta(days=31 * LEDGER_MONTHS)).strftime("%Y-%m")
        kept = [e for e in self.entries if e.get("month", "") >= cutoff][-LEDGER_MAX:]
        if len(kept) != len(self.entries):
            self.entries = kept
            self._keys = {e["key"] for e in kept}

    def stats(self, now: datetime, months: int = 12, acct: str = "") -> dict:
        """최근 months 개월의 월별 지출·당첨금과 합계."""
        labels = []
        y, m = now.year, now.month
        for _ in range(months):
            labels.append(f"{y:04d}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        labels.reverse()
        rows = {lb: {"month": lb, "spend": 0, "win": 0, "lotto": 0, "pension": 0, "wins": 0} for lb in labels}
        total = {"spend": 0, "win": 0, "wins": 0, "tickets": 0}
        by_acct = {}
        for e in self.entries:
            if acct and e.get("acct") != acct:
                continue
            r = rows.get(e.get("month"))
            a = by_acct.setdefault(e.get("acct"), {"spend": 0, "win": 0})
            if e["kind"] == "buy":
                total["spend"] += e["amount"]
                total["tickets"] += 1
                a["spend"] += e["amount"]
                if r:
                    r["spend"] += e["amount"]
                    r[e["game"]] += e["amount"]
            else:
                total["win"] += e["amount"]
                total["wins"] += 1
                a["win"] += e["amount"]
                if r:
                    r["win"] += e["amount"]
                    r["wins"] += 1
        total["ratio"] = round(total["win"] / total["spend"] * 100, 1) if total["spend"] else 0.0
        since = min((e["month"] for e in self.entries), default="")
        recent_wins = [
            {k: e[k] for k in ("acct", "game", "amount", "round", "info", "ts")}
            for e in sorted((x for x in self.entries if x["kind"] == "win" and (not acct or x["acct"] == acct)),
                            key=lambda x: x["ts"], reverse=True)[:10]
        ]
        return {"months": [rows[lb] for lb in labels], "total": total, "by_account": by_acct,
                "since": since, "recent_wins": recent_wins}


# ---------------------------------------------------------------- notifications
def needs_low_deposit_alert(balance, threshold: int, today: str, last_alert_day) -> bool:
    """예치금이 기준보다 적고 오늘 아직 알리지 않았으면 True(하루 1회)."""
    try:
        bal = int(float(balance))
    except (TypeError, ValueError):
        return False
    return threshold > 0 and bal < threshold and last_alert_day != today


def win_message(label: str, item: dict) -> tuple:
    game = "로또 6/45" if item["game"] == "lotto" else "연금복권720+"
    amt = f" · {item['amount']:,}원" if item.get("amount") else " · 당첨금은 동행복권에서 확인하세요"
    jackpot = item.get("rank") == 1
    title = ("🏆 1등 당첨!" if jackpot else "🎉 복권 당첨") + f" ({label})"
    return title, f"{game} {item['round']}회 {item['info']}{amt}"


def purchase_message(label: str, action_label: str, status: str, message: str, source: str) -> tuple:
    src = {"schedule": "정기 자동 구매", "button": "버튼", "dashboard": "대시보드"}.get(source, source)
    if status == "success":
        return f"✅ 구매 완료 ({label})", f"{action_label} · {message} [{src}]"
    if status == "skipped":
        return f"⚠️ 구매 건너뜀 ({label})", f"{action_label} · {message} [{src}]"
    return f"❌ 구매 실패 ({label})", f"{action_label} · {message} [{src}]"


# ---------------------------------------------------------------- diagnostics
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IP_RE = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")
_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
_URL_CRED_RE = re.compile(r"(://)[^/\s:@]+:[^/\s@]+@")
_KEEP_IPS = {"127.0.0.1", "0.0.0.0"}


def scrub_text(text: str) -> str:
    """진단 리포트에서 이메일·IP·토큰·URL 속 계정을 가린다(아이디는 별칭 필터가 이미 치환)."""
    s = str(text or "")
    s = _URL_CRED_RE.sub(r"\1***:***@", s)
    s = _EMAIL_RE.sub("***@***", s)

    def ip(m):
        v = m.group(0)
        if v in _KEEP_IPS or v.startswith("172.30.32."):
            return v
        return "x.x.x." + m.group(4)[-1:]
    s = _IP_RE.sub(ip, s)
    s = _TOKEN_RE.sub("***", s)
    return s


class RingLogHandler(logging.Handler):
    """최근 로그 N줄을 메모리에만 보관(진단 리포트용). 디스크에 남기지 않는다."""

    def __init__(self, capacity: int = 300):
        super().__init__(level=logging.INFO)
        self.lines = collections.deque(maxlen=capacity)

    def emit(self, record) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:  # noqa: BLE001
            pass

    def tail(self, n: int = 150) -> list:
        return list(self.lines)[-n:]


def now_kst() -> datetime:
    return datetime.now(KST)
