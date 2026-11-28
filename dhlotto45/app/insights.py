"""
insights.py (v2.12.0)
"럭키 랩" 기능의 순수 로직. FastAPI/HA 의존성이 없어 단위 테스트가 쉽다.

- 운 지수: 내 당첨 횟수가 확률상 상위 몇 %인지(이항분포 정확 계산, 추첨이 끝난 회차만)
- 월 예산 가드: 이번 달 지출 + 이번 구매가 예산을 넘으면 구매를 막는다
- 당첨금 수령 도우미: 회차 → 추첨일 → 지급기한(추정) D-day, 직접 수령이 필요한 당첨 리마인더
- 번호 공정성 검정: 카이제곱 적합도 검정(번호 쏠림이 우연 범위인지)
- 주간 리포트·토요일 마감 알림 문구
- 가계부(kr_ledger_kit) 연동 묶음
- 캘린더(.ics) 만들기: 추첨·판매 마감·정기 구매·수령 기한
"""

from __future__ import annotations

import hashlib
import math
import re
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

LOTTO_FIRST_DRAW = date(2002, 12, 7)     # 로또 6/45 제1회 (토)
PENSION_FIRST_DRAW = date(2020, 5, 7)    # 연금복권720+ 제1회 (목)

LOTTO_COMBOS = 8_145_060                  # C(45, 6)
LOTTO_RANK_COMBOS = {1: 1, 2: 6, 3: 228, 4: 11_115, 5: 182_780}
P_LOTTO_ANY = sum(LOTTO_RANK_COMBOS.values()) / LOTTO_COMBOS   # ≈ 1/41.96
P_LOTTO_FIRST = 1 / LOTTO_COMBOS
# 연금복권720+: 끝자리부터 1자리 이상 일치(7등) ~ 조+6자리(1등). 1~7등 확률의 합 = 1/10.
P_PENSION_ANY = 0.1

AUTO_CREDIT_LIMIT = 2_000_000             # 인터넷 구매 당첨금 중 예치금으로 자동 지급되는 상한(이하)
CLAIM_REMIND_DAYS = (30, 7, 1)
BUDGET_MAX = 1_000_000
PENDING_TTL = 3 * 3600                    # 구매 직후 원장 반영 전까지 지출로 셈하는 시간(초)
LUCK_GRADES = ((0.95, "legend"), (0.80, "lucky"), (0.20, "average"), (0.05, "unlucky"), (0.0, "rain"))

_RANK_RE = re.compile(r"([1-7])등")


# ---------------------------------------------------------------- rounds & dates
def draw_date(game: str, rnd) -> date | None:
    """회차의 추첨일(KST 날짜). 로또는 매주 토요일, 연금복권은 매주 목요일."""
    try:
        rnd = int(rnd)
    except (TypeError, ValueError):
        return None
    if rnd <= 0:
        return None
    base = LOTTO_FIRST_DRAW if game == "lotto" else PENSION_FIRST_DRAW
    return base + timedelta(days=7 * (rnd - 1))


def next_round(game: str, day: date) -> int:
    """day 당일 또는 그 뒤 첫 추첨 회차."""
    base = LOTTO_FIRST_DRAW if game == "lotto" else PENSION_FIRST_DRAW
    diff = (day - base).days
    if diff <= 0:
        return 1
    return diff // 7 + 1 + (1 if diff % 7 else 0)


def is_resolved(game: str, rnd, today: date) -> bool:
    """추첨이 끝나 결과가 반영됐을 회차(추첨 다음 날부터)."""
    d = draw_date(game, rnd)
    return d is not None and d + timedelta(days=1) <= today


def _add_year(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:          # 2월 29일
        return d.replace(year=d.year + 1, day=28)


def _rank_of(entry: dict) -> int:
    if isinstance(entry.get("rank"), int) and entry["rank"] > 0:
        return entry["rank"]
    m = _RANK_RE.search(str(entry.get("info") or ""))
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------- luck index
def _binom_pmf(n: int, p: float, kmax: int) -> list:
    """이항분포 확률 P(X=k), k=0..min(n,kmax). 로그로 계산해 큰 n 에서도 안전."""
    out = []
    if n <= 0:
        return [1.0]
    lp, lq = math.log(p), math.log1p(-p)
    lg_n = math.lgamma(n + 1)
    for k in range(min(n, kmax) + 1):
        out.append(math.exp(lg_n - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * lp + (n - k) * lq))
    return out


def luck_percentile(n1: int, p1: float, n2: int, p2: float, k: int) -> float:
    """T = Bin(n1,p1) + Bin(n2,p2) 일 때 mid-p 백분위 P(T<k) + ½·P(T=k). 0~1, 클수록 운이 좋다."""
    a, b = _binom_pmf(n1, p1, k), _binom_pmf(n2, p2, k)
    less = eq = 0.0
    for i, pa in enumerate(a):
        if pa == 0.0:
            continue
        for j, pb in enumerate(b):
            s = i + j
            if s < k:
                less += pa * pb
            elif s == k:
                eq += pa * pb
            else:
                break
    return max(0.0, min(1.0, less + 0.5 * eq))


def luck_grade(pct: float) -> str:
    for th, name in LUCK_GRADES:
        if pct >= th:
            return name
    return "rain"


def luck_index(entries, today: date, acct: str = "") -> dict:
    """추첨이 끝난 회차의 구매·당첨으로 운 지수를 계산한다."""
    n_l = k_l = n_p = k_p = 0
    spend = win = 0
    lotto_rounds = set()
    for e in entries or []:
        if acct and e.get("acct") != acct:
            continue
        game, rnd = e.get("game"), e.get("round")
        if game not in ("lotto", "pension") or not is_resolved(game, rnd, today):
            continue
        if e.get("kind") == "buy":
            spend += int(e.get("amount") or 0)
            if game == "lotto":
                n_l += 1
                lotto_rounds.add(int(rnd))
            else:
                n_p += 1
        elif e.get("kind") == "win":
            win += int(e.get("amount") or 0)
            if game == "lotto":
                k_l += 1
            else:
                k_p += 1
    games = n_l + n_p
    out = {
        "games": games, "lotto_games": n_l, "pension_tickets": n_p,
        "wins": k_l + k_p, "lotto_wins": k_l, "pension_wins": k_p,
        "expected": round(n_l * P_LOTTO_ANY + n_p * P_PENSION_ANY, 2),
        "spend": spend, "win": win, "ratio": round(win / spend * 100, 1) if spend else 0.0,
        "percentile": None, "top_pct": None, "grade": "none", "jackpot_years": None,
    }
    if not games:
        return out
    # 당첨 기록은 구매보다 많을 수 없다(가져오기 데이터 등 이상치 보호)
    k = min(k_l, n_l) + min(k_p, n_p)
    pct = luck_percentile(n_l, P_LOTTO_ANY, n_p, P_PENSION_ANY, k)
    out["percentile"] = round(pct * 100, 1)
    out["top_pct"] = round(max(0.1, (1 - pct) * 100), 1)
    out["grade"] = luck_grade(pct)
    if n_l and lotto_rounds:
        weeks = max(lotto_rounds) - min(lotto_rounds) + 1
        per_week = n_l / weeks
        out["lotto_per_week"] = round(per_week, 2)
        out["jackpot_years"] = int(round(LOTTO_COMBOS / per_week / 52.18))
    return out


# ---------------------------------------------------------------- monthly budget
def normalize_budget(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, min(BUDGET_MAX, int(value) // 1000 * 1000))


def month_spend(entries, acct: str, month: str) -> int:
    return sum(int(e.get("amount") or 0) for e in entries or []
               if e.get("kind") == "buy" and e.get("acct") == acct and e.get("month") == month)


def prune_pending(pending, now_ts: float) -> list:
    return [p for p in pending or [] if isinstance(p, dict) and now_ts - float(p.get("ts") or 0) < PENDING_TTL]


def budget_status(entries, pending, acct: str, now: datetime, budget: int, cost: int = 0) -> dict:
    """이번 달 사용액(원장 + 원장에 아직 안 잡힌 방금 구매)과 예산 판정."""
    month = now.strftime("%Y-%m")
    spent = month_spend(entries, acct, month)
    last_buy = max((int(e.get("ts") or 0) for e in entries or [] if e.get("kind") == "buy" and e.get("acct") == acct),
                   default=0)
    extra = sum(int(p.get("cost") or 0) for p in prune_pending(pending, now.timestamp())
                if p.get("acct") == acct and p.get("month") == month and float(p.get("ts") or 0) > last_buy)
    used = spent + extra
    out = {"month": month, "budget": budget, "used": used, "left": None, "pct": None, "blocked": False, "reason": ""}
    if budget <= 0:
        return out
    out["left"] = budget - used
    out["pct"] = min(100, round(used / budget * 100))
    if cost > 0 and used + cost > budget:
        out["blocked"] = True
        out["reason"] = (f"이번 달 예산 {budget:,}원을 넘어 구매하지 않았습니다 "
                         f"(이번 달 {used:,}원 · 이번 구매 {cost:,}원). 대시보드 ⏰ 설정에서 예산을 바꿀 수 있습니다.")
    return out


# ---------------------------------------------------------------- prize claims
def claims(entries, today: date, acct: str = "") -> list:
    """당첨 기록 → 지급기한(추정)과 수령 방법. 직접 수령(visit)이 필요한 것을 먼저, 기한 순으로."""
    out = []
    for e in entries or []:
        if e.get("kind") != "win" or (acct and e.get("acct") != acct):
            continue
        game = e.get("game")
        d = draw_date(game, e.get("round"))
        if d is None:
            continue
        deadline = _add_year(d)
        left = (deadline - today).days
        if left < -30:
            continue
        rank, amount, info = _rank_of(e), int(e.get("amount") or 0), str(e.get("info") or "")
        if game == "lotto":
            visit = amount > AUTO_CREDIT_LIMIT or (amount == 0 and 0 < rank <= 3)
        else:
            visit = rank in (1, 2) or "보너스" in info or amount > AUTO_CREDIT_LIMIT
        out.append({"key": e.get("key"), "acct": e.get("acct"), "game": game, "round": int(e.get("round") or 0),
                    "info": info, "amount": amount, "rank": rank, "draw_date": d.isoformat(),
                    "deadline": deadline.isoformat(), "days_left": left, "action": "visit" if visit else "auto"})
    out.sort(key=lambda c: (c["action"] != "visit", c["days_left"]))
    return out


def claim_reminders_due(claim_list, sent) -> list:
    """보낼 수령 리마인더 [(claim, stage)]. 한 번에 한 단계만(가장 가까운 단계), 보낸 단계 이상은 모두 보낸 것으로."""
    sent = sent or {}
    out = []
    for c in claim_list or []:
        if c["action"] != "visit" or c["days_left"] < 0:
            continue
        stages = [s for s in CLAIM_REMIND_DAYS if c["days_left"] <= s]
        if not stages:
            continue
        stage = min(stages)
        if f"{c['key']}:{stage}" in sent:
            continue
        out.append((c, stage))
    return out


def mark_claim_sent(sent: dict, claim: dict, stage: int, ts: int) -> dict:
    sent = dict(sent or {})
    for s in CLAIM_REMIND_DAYS:
        if s >= stage:
            sent[f"{claim['key']}:{s}"] = ts
    if len(sent) > 300:
        sent = dict(sorted(sent.items(), key=lambda kv: kv[1])[-300:])
    return sent


def claim_message(label: str, c: dict, stage: int) -> tuple:
    game = "로또 6/45" if c["game"] == "lotto" else "연금복권720+"
    amt = f" {c['amount']:,}원" if c["amount"] else ""
    title = f"💰 당첨금 수령 D-{c['days_left']} ({label})"
    body = (f"{game} {c['round']}회 {c['info']}{amt} — 지급기한(추정) {c['deadline']}. "
            "직접 수령이 필요한 당첨입니다: 신분증을 챙겨 수령처를 방문하세요. "
            "정확한 기한·수령처는 동행복권 '당첨금 지급 안내'를 확인하세요.")
    return title, body


# ---------------------------------------------------------------- fairness (chi-square)
def _gammaincc(a: float, x: float) -> float:
    """정규화 상부 불완전 감마함수 Q(a, x) (Numerical Recipes 방식)."""
    if x <= 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1:
        ap, s = a, 1.0 / a
        d = s
        for _ in range(1000):
            ap += 1
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-15:
                break
        return max(0.0, min(1.0, 1.0 - s * math.exp(-x + a * math.log(x) - gln)))
    tiny = 1e-300
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    hh = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = d if abs(d) > tiny else tiny
        c = b + an / c
        c = c if abs(c) > tiny else tiny
        d = 1 / d
        de = d * c
        hh *= de
        if abs(de - 1) < 1e-15:
            break
    return max(0.0, min(1.0, math.exp(-x + a * math.log(x) - gln) * hh))


def chi_square_uniform(counts) -> dict | None:
    """번호별 출현 횟수가 '모든 번호 같은 확률'과 맞는지 카이제곱 적합도 검정."""
    try:
        counts = [int(c) for c in counts]
    except (TypeError, ValueError):
        return None
    n, k = sum(counts), len(counts)
    if k < 2 or n <= 0:
        return None
    e = n / k
    chi2 = sum((c - e) ** 2 / e for c in counts)
    df = k - 1
    p = _gammaincc(df / 2, chi2 / 2)
    return {"chi2": round(chi2, 2), "df": df, "p_value": round(p, 4), "expected": round(e, 2),
            "samples": n, "verdict": "random" if p >= 0.05 else "skewed", "reliable": e >= 5}


# ---------------------------------------------------------------- weekly report & reminders
def round_summary(entries, acct: str, game: str, rnd: int) -> dict:
    buys = [e for e in entries or [] if e.get("acct") == acct and e.get("game") == game
            and e.get("round") == rnd and e.get("kind") == "buy"]
    wins = [e for e in entries or [] if e.get("acct") == acct and e.get("game") == game
            and e.get("round") == rnd and e.get("kind") == "win"]
    return {"games": len(buys), "wins": [{"info": w.get("info"), "amount": int(w.get("amount") or 0)} for w in wins],
            "won": sum(int(w.get("amount") or 0) for w in wins)}


def weekly_report(entries, labels: dict, today: date, budgets: dict, pending=(), now: datetime | None = None) -> tuple:
    """일요일 아침 주간 리포트(제목, 본문). labels: {account_N: Account_N}."""
    now = now or datetime.combine(today, datetime.min.time(), KST)
    lotto_r = next_round("lotto", today) - 1           # 가장 최근에 추첨된 로또 회차
    pen_r = next_round("pension", today) - 1
    lines = []
    for aid, label in labels.items():
        lo = round_summary(entries, aid, "lotto", lotto_r)
        pe = round_summary(entries, aid, "pension", pen_r)
        parts = []
        if lo["games"]:
            res = ", ".join(f"{w['info']}" + (f" {w['amount']:,}원" if w["amount"] else "") for w in lo["wins"]) or "낙첨"
            parts.append(f"로또 {lotto_r}회 {lo['games']}게임 → {res}")
        if pe["games"]:
            res = f"당첨 {len(pe['wins'])}매 {pe['won']:,}원" if pe["wins"] else "낙첨"
            parts.append(f"연금 {pen_r}회 {pe['games']}매 → {res}")
        b = budget_status(entries, pending, aid, now, int(budgets.get(aid) or 0))
        if b["budget"]:
            parts.append(f"이번 달 {b['used']:,}/{b['budget']:,}원")
        else:
            parts.append(f"이번 달 {b['used']:,}원")
        lk = luck_index(entries, today, aid)
        if lk["top_pct"] is not None:
            parts.append(f"운 지수 상위 {lk['top_pct']}%")
        lines.append(f"• {label}: " + " · ".join(parts))
    visit = [c for c in claims(entries, today) if c["action"] == "visit" and c["days_left"] >= 0]
    if visit:
        c = visit[0]
        lines.append(f"💰 직접 수령이 필요한 당첨 {len(visit)}건 — 가장 가까운 기한 {c['deadline']} (D-{c['days_left']})")
    title = f"📬 DH Lotto 주간 리포트 · 로또 {lotto_r}회"
    return title, "\n".join(lines) or "이번 주 기록이 없습니다."


def accounts_missing_lotto(account_rows, settings: dict) -> list:
    """토요일 마감 알림 대상: 이번 주 로또를 안 샀고, 토요일 정기 자동 구매도 없는 계정 라벨.

    account_rows: [{"aid", "label", "weekly_count", "logged_in"}]
    """
    ab = (settings or {}).get("auto_buy") or {}
    covered_all = False
    covered = set()
    if ab.get("enabled"):
        for s in ab.get("schedules") or []:
            if s.get("enabled") and str(s.get("action", "")).startswith("lotto") and 5 in (s.get("days") or []) \
                    and str(s.get("time", "99:99")) < "20:00":
                if s.get("account") == "all":
                    covered_all = True
                else:
                    covered.add(s.get("account"))
    out = []
    for r in account_rows:
        if not r.get("logged_in") or covered_all or r.get("aid") in covered:
            continue
        try:
            cnt = int(r.get("weekly_count") or 0)
        except (TypeError, ValueError):
            cnt = 0
        if cnt == 0:
            out.append(r.get("label"))
    return out


def in_window(now: datetime, weekday: int | None, hh: int, mm: int = 0, minutes: int = 60) -> bool:
    """now(KST) 가 지정 요일 hh:mm ~ +minutes 사이인지. weekday=None 이면 매일."""
    if weekday is not None and now.weekday() != weekday:
        return False
    start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return start <= now < start + timedelta(minutes=minutes)


# ---------------------------------------------------------------- household ledger (kr_ledger_kit)
def household_payloads(items, labels: dict, today: date) -> list:
    """새 원장 항목 → kr_ledger.add_transaction 호출 데이터. 회차·계정·종류별로 묶고, 최근 회차만(과거 기록 폭주 방지)."""
    groups = {}
    for it in items or []:
        game, rnd, kind = it.get("game"), int(it.get("round") or 0), it.get("kind")
        d = draw_date(game, rnd)
        if d is None or d < today - timedelta(days=8) or kind not in ("buy", "win"):
            continue
        g = groups.setdefault((it.get("acct"), game, rnd, kind), {"amount": 0, "count": 0, "infos": []})
        g["amount"] += int(it.get("amount") or 0)
        g["count"] += 1
        if kind == "win" and it.get("info"):
            g["infos"].append(str(it["info"]))
    out = []
    for (aid, game, rnd, kind), g in sorted(groups.items(), key=lambda kv: str(kv[0])):
        if g["amount"] <= 0:
            continue
        label = labels.get(aid, aid)
        name = "로또 6/45" if game == "lotto" else "연금복권720+"
        unit = "게임" if game == "lotto" else "매"
        if kind == "buy":
            memo = f"{name} {rnd}회 {g['count']}{unit} ({label})"
        else:
            memo = f"{name} {rnd}회 당첨 {', '.join(g['infos'][:5])} ({label})"
        out.append({"amount": g["amount"], "kind": "expense" if kind == "buy" else "income",
                    "merchant": "동행복권", "category": "복권", "memo": memo[:120], "account": label})
    return out


# ---------------------------------------------------------------- calendar (.ics)
def _ics_escape(text: str) -> str:
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r", "").replace("\n", "\\n"))


def _fold(line: str) -> list:
    """RFC 5545: 한 줄 75옥텟 이하로 접기(UTF-8 글자를 자르지 않는다)."""
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > (75 if not out else 74):
            out.append(cur)
            cur, size = "", 0
        cur += ch
        size += n
    out.append(cur)
    return [out[0]] + [" " + x for x in out[1:]]


def _utc(d: date, hh: int, mm: int) -> str:
    dt = datetime(d.year, d.month, d.day, hh, mm, tzinfo=KST).astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _utc_plus(d: date, hh: int, mm: int, minutes: int) -> str:
    dt = datetime(d.year, d.month, d.day, hh, mm, tzinfo=KST) + timedelta(minutes=minutes)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


_DAY_CODES = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


def build_ics(today: date, now_utc: datetime, *, lotto: bool = True, pension: bool = True, weeks: int = 8,
              schedules=(), action_labels: dict | None = None, labels: dict | None = None, claim_list=()) -> str:
    """추첨·판매 마감·정기 자동 구매·당첨금 수령 기한을 담은 캘린더 파일."""
    action_labels, labels = action_labels or {}, labels or {}
    stamp = now_utc.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ev = []

    def event(uid, summary, desc, start, end=None, all_day=False, rrule=None, alarms=()):
        lines = ["BEGIN:VEVENT", f"UID:{uid}@dhlotto45", f"DTSTAMP:{stamp}"]
        if all_day:
            lines.append(f"DTSTART;VALUE=DATE:{start}")
        else:
            lines.append(f"DTSTART:{start}")
            if end:
                lines.append(f"DTEND:{end}")
        if rrule:
            lines.append(f"RRULE:{rrule}")
        lines += [f"SUMMARY:{_ics_escape(summary)}", f"DESCRIPTION:{_ics_escape(desc)}"]
        for trig in alarms:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:{trig}", f"DESCRIPTION:{_ics_escape(summary)}",
                      "END:VALARM"]
        lines.append("END:VEVENT")
        ev.extend(lines)

    if lotto:
        r0 = next_round("lotto", today)
        for i in range(weeks):
            r = r0 + i
            d = draw_date("lotto", r)
            event(f"lotto-{r}", f"🎱 로또 6/45 {r}회 · 판매 마감 20:00", "추첨 20:35 (KST) · 결과는 추첨 후 대시보드에 반영됩니다.",
                  _utc(d, 20, 0), _utc(d, 20, 45), alarms=("-PT2H",))
    if pension:
        r0 = next_round("pension", today)
        for i in range(weeks):
            r = r0 + i
            d = draw_date("pension", r)
            event(f"pension-{r}", f"🎟️ 연금복권720+ {r}회 추첨", "추첨 19:05 (KST)", _utc(d, 19, 5), _utc(d, 19, 35))
    for s in schedules or []:
        if not s.get("enabled") or not s.get("days"):
            continue
        hh, mm = (int(x) for x in str(s.get("time", "09:00")).split(":"))
        first = today
        while first.weekday() not in s["days"]:
            first += timedelta(days=1)
        who = "모든 계정" if s.get("account") == "all" else labels.get(s.get("account"), s.get("account"))
        what = action_labels.get(s.get("action"), s.get("action"))
        days = ",".join(_DAY_CODES[d] for d in s["days"])
        event(f"auto-{s.get('id')}", f"⏰ 정기 자동 구매 · {what}", f"대상: {who} · 대시보드 ⏰ 에서 바꿀 수 있습니다.",
              _utc(first, hh, mm), _utc_plus(first, hh, mm, 10),
              rrule=f"FREQ=WEEKLY;BYDAY={days}")
    for c in claim_list or []:
        if c.get("action") != "visit" or c.get("days_left", -1) < 0:
            continue
        game = "로또" if c["game"] == "lotto" else "연금복권"
        who = labels.get(c.get("acct"), c.get("acct"))
        dl = date.fromisoformat(c["deadline"])
        event("claim-" + hashlib.sha1(str(c["key"]).encode("utf-8")).hexdigest()[:16], f"💰 당첨금 수령 기한(추정) · {who} {game} {c['round']}회 {c['info']}",
              "신분증을 챙겨 수령처를 방문하세요. 정확한 기한·수령처는 동행복권 '당첨금 지급 안내'를 확인하세요.",
              dl.strftime("%Y%m%d"), all_day=True, alarms=("-P30D", "-P7D", "-P1D"))
    head = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DH Lotto 45//Lucky Lab//KO", "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH", "X-WR-CALNAME:DH Lotto 45", "X-WR-TIMEZONE:Asia/Seoul"]
    out = []
    for line in head + ev + ["END:VCALENDAR"]:
        out.extend(_fold(line))
    return "\r\n".join(out) + "\r\n"
