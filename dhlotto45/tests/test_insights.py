"""럭키 랩(v2.12.0) 테스트: 운 지수·예산 가드·수령 도우미·공정성 검정·리포트·가계부·캘린더.

실행: python -X utf8 test_insights.py
실제 구매·네트워크 없음(가짜 계정, 가짜 HA 호출).
"""

import asyncio
import itertools
import json
import math
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
os.environ.setdefault("DHL_DATA_DIR", tempfile.mkdtemp(prefix="dhl_insight_"))

import features as F  # noqa: E402
import insights as I  # noqa: E402

PASS = 0
FAIL = 0
KST = I.KST


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


def buy(acct, game, rnd, n=1, ts=100, month="2026-11", amount=1000):
    return [{"key": f"{game}:{acct}:{rnd}:{i}:{ts}", "acct": acct, "kind": "buy", "game": game, "amount": amount,
             "round": rnd, "info": "", "month": month, "ts": ts} for i in range(n)]


def win(acct, game, rnd, info, amount, ts=200, month="2026-11", key=None):
    return {"key": key or f"{game}-win:{acct}:{rnd}:{info}:{amount}", "acct": acct, "kind": "win", "game": game,
            "amount": amount, "round": rnd, "info": info, "month": month, "ts": ts}


# ------------------------------------------------ rounds & dates
print("[회차·추첨일]")
check(I.draw_date("lotto", 1) == date(2002, 12, 7) and I.draw_date("lotto", 1252) == date(2026, 11, 28), "로또 회차 → 토요일 추첨일")
check(I.draw_date("pension", 344) == date(2026, 12, 3) and I.draw_date("pension", 344).weekday() == 3, "연금 회차 → 목요일 추첨일")
check(I.next_round("lotto", date(2026, 11, 28)) == 1252 and I.next_round("lotto", date(2026, 11, 29)) == 1253, "다음 추첨 회차")
check(I.draw_date("lotto", 0) is None and I.draw_date("lotto", "x") is None, "잘못된 회차")
check(I.is_resolved("lotto", 1252, date(2026, 11, 29)) and not I.is_resolved("lotto", 1252, date(2026, 11, 28)), "추첨 다음 날부터 결과 반영")

# ------------------------------------------------ probabilities
print("[확률]")
combos = math.comb(45, 6)
rank_combos = {1: 1, 2: 6, 3: math.comb(6, 5) * 39 - 6, 4: math.comb(6, 4) * math.comb(39, 2), 5: math.comb(6, 3) * math.comb(39, 3)}
check(combos == I.LOTTO_COMBOS and rank_combos == I.LOTTO_RANK_COMBOS, f"등수별 조합 수를 조합론으로 검증 ({rank_combos})")
check(abs(1 / I.P_LOTTO_ANY - 41.9567) < 0.001, "로또 아무 등수나 당첨될 확률 ≈ 1/41.96")
pension_ranks = [1 / 5 * 1e-6, 4 / 5 * 1e-6] + [10 ** -k - 10 ** -(k + 1) for k in range(1, 6)]
check(abs(sum(pension_ranks) - I.P_PENSION_ANY) < 1e-12, "연금복권 1~7등 확률 합 = 1/10")

# ------------------------------------------------ luck percentile (exact vs brute force)
print("[운 지수 계산]")


def brute(n1, p1, n2, p2, k):
    less = eq = 0.0
    for a in range(n1 + 1):
        pa = math.comb(n1, a) * p1 ** a * (1 - p1) ** (n1 - a)
        for b in range(n2 + 1):
            pb = math.comb(n2, b) * p2 ** b * (1 - p2) ** (n2 - b)
            if a + b < k:
                less += pa * pb
            elif a + b == k:
                eq += pa * pb
    return less + 0.5 * eq


ok = all(abs(I.luck_percentile(n1, 0.3, n2, 0.1, k) - brute(n1, 0.3, n2, 0.1, k)) < 1e-12
         for n1, n2, k in itertools.product((0, 3, 7), (0, 4, 9), (0, 1, 2, 5)))
check(ok, "이항분포 두 개의 합 백분위 = 전수 계산과 일치")
seq = [I.luck_percentile(200, I.P_LOTTO_ANY, 50, I.P_PENSION_ANY, k) for k in range(0, 20)]
check(all(b > a for a, b in zip(seq, seq[1:])), "당첨이 많을수록 운 지수가 높다")
check(I.luck_percentile(5000, I.P_LOTTO_ANY, 5000, I.P_PENSION_ANY, 700) > 0.99, "큰 표본도 계산(오버플로 없음)")
check(I.luck_grade(0.97) == "legend" and I.luck_grade(0.5) == "average" and I.luck_grade(0.01) == "rain", "등급")

today = date(2026, 11, 29)
entries = (buy("account_1", "lotto", 1250, 5) + buy("account_1", "lotto", 1251, 5) + buy("account_1", "lotto", 1252, 5)
           + buy("account_1", "lotto", 1253, 5)                         # 아직 추첨 전 → 제외
           + buy("account_1", "pension", 343, 5) + buy("account_2", "lotto", 1252, 2)
           + [win("account_1", "lotto", 1251, "5등", 5000), win("account_1", "pension", 343, "7등", 1000)])
lk = I.luck_index(entries, today, "account_1")
check(lk["lotto_games"] == 15 and lk["pension_tickets"] == 5 and lk["wins"] == 2, f"추첨 끝난 회차만 셈 ({lk})")
check(abs(lk["expected"] - round(15 * I.P_LOTTO_ANY + 5 * 0.1, 2)) < 1e-9 and 0 < lk["percentile"] < 100, "기대 당첨·백분위")
check(lk["top_pct"] == round(max(0.1, 100 - lk["percentile"]), 1) or abs(lk["top_pct"] + lk["percentile"] - 100) < 0.11, "상위 % = 100 - 백분위")
check(lk["jackpot_years"] and lk["lotto_per_week"] == 5.0, "주 5게임이면 1등 기대 시점 계산")
check(lk["spend"] == 20000 and lk["win"] == 6000 and lk["ratio"] == 30.0, "추첨 끝난 회차 지출·환급률")
check(I.luck_index([], today)["percentile"] is None and I.luck_index(entries, today, "account_9")["grade"] == "none", "기록 없으면 계산 안 함")
weird = buy("account_3", "lotto", 1250, 1) + [win("account_3", "lotto", 1250, "5등", 5000, key=f"k{i}") for i in range(5)]
check(I.luck_index(weird, today, "account_3")["percentile"] <= 100, "당첨 수가 구매 수보다 많아도 안전")

# ------------------------------------------------ fairness
print("[공정성 검정]")
check(abs(I._gammaincc(1, 2.5) - math.exp(-2.5)) < 1e-12, "자유도 2: p = e^(-x/2)")
check(abs(I._gammaincc(22, 60.48 / 2) - 0.05) < 0.001, "자유도 44, χ²=60.48 → p≈0.05 (임계값표)")
check(abs(I._gammaincc(5, 3.0) - math.exp(-3) * sum(3 ** k / math.factorial(k) for k in range(5))) < 1e-12, "정수 a 닫힌 식과 일치")
u = I.chi_square_uniform([10] * 45)
check(u["chi2"] == 0 and u["p_value"] == 1.0 and u["verdict"] == "random", "완전 균등 → 무작위")
sk = I.chi_square_uniform([60] + [5] * 44)
check(sk["verdict"] == "skewed" and sk["p_value"] < 0.001, "한 번호만 쏠림 → 쏠림")
check(I.chi_square_uniform([]) is None and I.chi_square_uniform([0, 0]) is None and I.chi_square_uniform(["x"]) is None, "빈 입력")

# ------------------------------------------------ budget
print("[월 예산]")
now = datetime(2026, 11, 29, 12, 0, tzinfo=KST)
led = buy("account_1", "lotto", 1252, 5, ts=int(now.timestamp()) - 3600) + buy("account_1", "lotto", 1240, 3, month="2026-08")
check(I.budget_status(led, [], "account_1", now, 0, 5000)["blocked"] is False, "예산 0 = 끄기")
b = I.budget_status(led, [], "account_1", now, 10000, 5000)
check(b["used"] == 5000 and b["left"] == 5000 and not b["blocked"] and b["pct"] == 50, "이번 달만 셈 · 정확히 예산까지는 허용")
b = I.budget_status(led, [], "account_1", now, 10000, 6000)
check(b["blocked"] and "10,000원" in b["reason"], "예산 넘으면 막고 이유 안내")
pend = [{"acct": "account_1", "month": "2026-11", "ts": now.timestamp() - 60, "cost": 5000}]
check(I.budget_status(led, pend, "account_1", now, 10000, 1000)["blocked"], "원장에 아직 안 잡힌 방금 구매도 셈")
led2 = led + buy("account_1", "lotto", 1253, 5, ts=int(now.timestamp()))   # 구매 후 원장 갱신
check(I.budget_status(led2, pend, "account_1", now, 10000, 0)["used"] == 10000, "원장에 반영되면 대기분은 이중으로 안 셈")
old = [{"acct": "account_1", "month": "2026-11", "ts": now.timestamp() - I.PENDING_TTL - 1, "cost": 5000}]
check(I.budget_status(led, old, "account_1", now, 10000, 5000)["blocked"] is False, "오래된 대기분은 만료")
check(I.budget_status(led, pend, "account_2", now, 10000, 5000)["used"] == 0, "계정별로 따로")
check(I.normalize_budget(12345) == 12000 and I.normalize_budget(-5) == 0 and I.normalize_budget(True) == 0
      and I.normalize_budget(9_999_999) == I.BUDGET_MAX and I.normalize_budget("1000") == 0, "예산 값 정규화")

# ------------------------------------------------ settings
print("[설정]")
d = F.normalize_settings(None)
check(d["budget"] == {"monthly": 0} and d["household"] == {"enabled": False}, "새 설정 기본값")
check(d["notify"]["weekly_report"] is False and d["notify"]["deadline_reminder"] is False and d["notify"]["claim_reminder"] is True, "새 알림 기본값")
m = F.merge_settings(d, {"budget": {"monthly": 30500, "x": 1}, "household": {"enabled": "yes"}, "notify": {"weekly_report": True}})
check(m["budget"] == {"monthly": 30000} and m["household"]["enabled"] is False and m["notify"]["weekly_report"] is True, "부분 변경·정규화")
check(F.merge_settings(m, {"household": {"enabled": True}})["budget"]["monthly"] == 30000, "다른 키는 유지")

# ------------------------------------------------ claims
print("[당첨금 수령 도우미]")
wins = [win("account_1", "lotto", 1250, "3등", 1_500_000), win("account_1", "lotto", 1251, "1등", 2_000_000_000),
        win("account_2", "pension", 340, "2등", 0), win("account_2", "lotto", 1000, "5등", 5000),
        win("account_1", "lotto", 1252, "3등", 0)]
cl = I.claims(wins, today)
by = {(c["game"], c["round"]): c for c in cl}
check(by[("lotto", 1250)]["action"] == "auto" and by[("lotto", 1251)]["action"] == "visit", "200만원 이하 자동 지급 · 초과 직접 수령")
check(by[("pension", 340)]["action"] == "visit" and by[("lotto", 1252)]["action"] == "visit", "연금 1·2등, 금액 모르는 3등 이상 → 직접 수령")
check(("lotto", 1000) not in by, "기한이 한참 지난 당첨은 목록에서 제외")
c1 = by[("lotto", 1251)]
check(c1["deadline"] == "2027-11-22" and c1["days_left"] == (date(2027, 11, 22) - today).days, "지급기한 = 추첨일 + 1년, 일요일이면 월요일")
# 보도된 실제 지급기한으로 규칙 검증(동행복권 미수령 당첨금 안내·언론 보도)
check(I.claim_deadline(I.draw_date("lotto", 1196)) == date(2026, 11, 2), "1196회(2025-11-01 추첨) 기한 2026-11-02(월)")
check(I.claim_deadline(I.draw_date("lotto", 1203)) == date(2026, 12, 21), "1203회(2025-12-20 추첨) 기한 2026-12-21(월)")
check(I.claim_deadline(I.draw_date("lotto", 1159)) == date(2026, 2, 16), "1159회(2025-02-15 추첨) 2026-02-16(월) — 설 연휴는 화면 안내로")
check(I.claim_deadline(date(2026, 12, 3)) == date(2027, 12, 3), "평일이면 그대로(연금 목요일 추첨)")
check(all(I.claim_deadline(I.draw_date("lotto", r)).weekday() < 5 for r in range(1100, 1300)), "기한은 항상 평일")
M_ = I.claim_method
check(M_("lotto", 1, 2_000_000_000) == "bank_hq" and M_("lotto", 2, 55_000_000) == "bank_branch", "로또 1등 본점 · 2등 지점")
check(M_("lotto", 3, 2_100_000) == "bank_branch" and M_("lotto", 3, 1_266_451) == "auto" and M_("lotto", 3, 0) == "bank_branch", "로또 3등: 200만원 기준(금액 모르면 지점)")
check(M_("lotto", 4, 50000) == "auto" and M_("lotto", 5, 5000) == "auto", "로또 4·5등 예치금 자동")
check(M_("pension", 1, 0) == "online_claim" and M_("pension", 2, 0) == "online_claim" and M_("pension", 0, 0, "보너스") == "online_claim", "연금 1·2등·보너스: 사이트 지급 신청")
check(M_("pension", 3, 1_000_000) == "auto" and M_("pension", 7, 1000) == "auto", "연금 3~7등 예치금 자동")
check(by[("pension", 340)]["how"] == "online_claim" and by[("lotto", 1251)]["how"] == "bank_hq", "목록에 수령 방법 포함")
check([c["action"] for c in cl][:3] == ["visit", "visit", "visit"], "직접 수령을 먼저")
check(I._add_year(date(2024, 2, 29)) == date(2025, 2, 28), "윤년 2월 29일")

near = [dict(c1, days_left=25), dict(by[("pension", 340)], days_left=5, key="p340")]
due = I.claim_reminders_due(near, {})
check(sorted(s for _c, s in due) == [7, 30], f"가장 가까운 단계 하나씩 ({due})")
sent = {}
for c, s in due:
    sent = I.mark_claim_sent(sent, c, s, 1)
check(I.claim_reminders_due(near, sent) == [], "보낸 단계는 다시 안 보냄")
check(f"p340:30" in sent, "D-5 에 처음 알리면 D-30 단계도 보낸 것으로")
check(I.claim_reminders_due([dict(c1, days_left=200)], {}) == [] and I.claim_reminders_due([dict(c1, days_left=-1)], {}) == [], "멀거나 지난 기한은 알림 없음")
title, body = I.claim_message("Account_1", dict(c1, days_left=7), 7)
check("D-7" in title and "Account_1" in title and "2027-11-22" in body and "본점" in body and "공휴일" in body
      and "추정" not in body and "sampleid" not in body, "리마인더 문구(기한·수령처·휴무일 규칙)")

# ------------------------------------------------ weekly report & deadline reminder
print("[주간 리포트·마감 알림]")
labels = {"account_1": "Account_1", "account_2": "Account_2"}
title, body = I.weekly_report(entries + wins, labels, today, {"account_1": 50000}, [], now)
check("1252회" in title and "Account_1" in body and "Account_2" in body, f"회차·계정 별칭 ({title})")
check("로또 1252회 5게임" in body and "이번 달" in body and "운 지수" in body, "리포트 내용")
check("직접 수령이 필요한 당첨" in body, "수령 필요 당첨 안내")
rows = [{"aid": "account_1", "label": "Account_1", "weekly_count": 0, "logged_in": True},
        {"aid": "account_2", "label": "Account_2", "weekly_count": "3", "logged_in": True},
        {"aid": "account_3", "label": "Account_3", "weekly_count": 0, "logged_in": False}]
check(I.accounts_missing_lotto(rows, {}) == ["Account_1"], "안 산 로그인 계정만")
sch = {"auto_buy": {"enabled": True, "schedules": [{"enabled": True, "action": "lotto_auto_5", "days": [5], "time": "09:00", "account": "account_1"}]}}
check(I.accounts_missing_lotto(rows, sch) == [], "토요일 정기 자동 구매가 있으면 제외")
sch["auto_buy"]["schedules"][0]["time"] = "21:00"
check(I.accounts_missing_lotto(rows, sch) == ["Account_1"], "마감 뒤 일정은 대상 아님")
sch["auto_buy"]["enabled"] = False
sch["auto_buy"]["schedules"][0]["time"] = "09:00"
check(I.accounts_missing_lotto(rows, sch) == ["Account_1"], "자동 구매가 꺼져 있으면 알림")
sat = datetime(2026, 11, 28, 18, 30, tzinfo=KST)
check(I.in_window(sat, 5, 18) and not I.in_window(sat, 6, 18) and not I.in_window(sat, 5, 19) and I.in_window(sat, None, 18, 0, 60), "시간 창")

# ------------------------------------------------ household ledger
print("[가계부 연동]")
items = (buy("account_1", "lotto", 1253, 5) + buy("account_1", "pension", 344, 2) + buy("account_1", "lotto", 1100, 3)
         + [win("account_1", "lotto", 1252, "5등", 5000), win("account_1", "pension", 343, "7등", 0)])
pl = I.household_payloads(items, labels, today)
kinds = sorted((p["kind"], p["amount"]) for p in pl)
check(kinds == [("expense", 2000), ("expense", 5000), ("income", 5000)], f"회차별 묶음·옛 회차·0원 제외 ({kinds})")
check(all(p["merchant"] == "동행복권" and p["category"] == "복권" and p["account"] == "Account_1" for p in pl), "가계부 필드")
check(any("1253회 5게임" in p["memo"] for p in pl) and not any("sampleid" in p["memo"] for p in pl), "메모에 별칭만")

# ------------------------------------------------ calendar
print("[캘린더]")
sched = [{"id": "abc", "enabled": True, "action": "lotto_auto_5", "days": [0, 5], "time": "09:55", "account": "all"},
         {"id": "off", "enabled": False, "action": "pension_auto_1", "days": [3], "time": "07:00", "account": "account_1"}]
ics = I.build_ics(today, now, schedules=sched, action_labels={"lotto_auto_5": "로또 자동 5게임, 이번 주"},
                  labels=labels, claim_list=cl)
lines = ics.split("\r\n")
check(ics.endswith("\r\n") and lines[0] == "BEGIN:VCALENDAR" and "END:VCALENDAR" in lines, "CRLF·달력 구조")
check(ics.count("BEGIN:VEVENT") == ics.count("END:VEVENT") == 8 + 8 + 1 + 3, f"추첨 16 + 일정 1 + 수령 기한 3 ({ics.count('BEGIN:VEVENT')})")
check(all(len(x.encode("utf-8")) <= 75 for x in lines), "한 줄 75옥텟 이하로 접기")
unfolded = ics.replace("\r\n ", "")
check("RRULE:FREQ=WEEKLY;BYDAY=MO,SA" in unfolded and "로또 자동 5게임\\, 이번 주" in unfolded, "반복 일정·쉼표 이스케이프")
check("DTSTART:20261205T110000Z" in unfolded, "판매 마감 토 20:00 KST = 11:00 UTC")
check("DTSTART:20261130T005500Z" in unfolded and "DTEND:20261130T010500Z" in unfolded, "정기 구매 09:55 → +10분(시간 넘김)")
check("TRIGGER:-P30D" in unfolded and "DTSTART;VALUE=DATE:20271122" in unfolded and "추정" not in unfolded, "수령 기한 종일 일정 + 알림")
again = I.build_ics(today, now, schedules=sched, labels=labels, claim_list=cl)
uid = lambda x: [ln for ln in x.replace("\r\n ", "").split("\r\n") if ln.startswith("UID:claim")]
check(uid(ics) == uid(again) and len(uid(ics)) == 3, "UID 가 매번 같다(캘린더 중복 방지)")
check("sampleid" not in ics, "캘린더에 실제 아이디 없음")

# ------------------------------------------------ main integration (fake HA, no purchases)
print("[애드온 연동]")
import main as M  # noqa: E402


class Logged:
    logged_in = True


M.accounts.clear()
a1 = M.AccountData("sampleid01", "pw")
a1.client = Logged()
M.accounts["sampleid01"] = a1
M._ledger = F.Ledger([])
M._feature_state = {}
posts = []


async def fake_post(path, payload):
    posts.append((path, payload))
    return True


M._ha_post = fake_post
M._write_json(F.SETTINGS_FILE, F.merge_settings(None, {"budget": {"monthly": 3000}}))
check(M._budget_block_reason(a1, 3000) == "" and "예산" in M._budget_block_reason(a1, 4000), "예산 가드: 넘으면 사유")
M._note_spend(a1, 3000)
check("예산" in M._budget_block_reason(a1, 1000), "방금 구매가 예산에 바로 반영")
check(M._budget_block_reason(a1, 0) == "" and M._budget_block_reason(None, 1000) == "", "0원·계정 없음은 통과")
M._pending_spend.clear()
M._write_json(F.SETTINGS_FILE, F.merge_settings(None, {"budget": {"monthly": 0}}))
check(M._budget_block_reason(a1, 999000) == "", "예산 꺼지면 제한 없음")

src = open(os.path.join(HERE, "..", "app", "main.py"), encoding="utf-8").read()
for fn in ("async def execute_pension_purchase", "async def execute_pension_manual_purchase", "async def execute_button_purchase"):
    body_src = src[src.index(fn):]
    body_src = body_src[:body_src.index("purchase_guard.acquire")]
    check("_budget_block_reason(" in body_src, f"{fn.split()[-1]}: 구매 전에 예산 확인")
check(src.count("        _note_spend(account, ") == 3, "세 구매 경로 모두 지출 대기분 기록")
check("return _budget_block_reason(account, amount)" in src, "정기 자동 구매도 예산 확인")

# household queue: disabled → nothing, enabled → one grouped call per round
M._household_queue.clear()
M._queue_household(buy("account_1", "lotto", 1253, 5))
check(M._household_queue == [], "가계부 꺼져 있으면 쌓지 않음")
M._write_json(F.SETTINGS_FILE, F.merge_settings(None, {"household": {"enabled": True}}))


async def run_household():
    orig = M.asyncio.sleep

    async def no_sleep(_s):
        return None
    M.asyncio.sleep = no_sleep
    try:
        M._queue_household(buy("account_1", "lotto", 1253, 5))
        await M._household_task
    finally:
        M.asyncio.sleep = orig


M.FT.now_kst = lambda: now
asyncio.run(run_household())
hh = [p for p in posts if p[0] == "services/kr_ledger/add_transaction"]
check(len(hh) == 1 and hh[0][1]["amount"] == 5000 and hh[0][1]["kind"] == "expense", f"회차별 한 번에 기록 ({hh})")

# insight tick: weekly report on Sunday 09:xx once; claim reminder once a day
M._write_json(F.SETTINGS_FILE, F.merge_settings(None, {"notify": {"weekly_report": True, "claim_reminder": True}}))
M._ledger = F.Ledger(entries + [win("account_1", "lotto", 1251, "1등", 2_000_000_000)])
sunday = datetime(2026, 11, 29, 10, 5, tzinfo=KST)
M.FT.now_kst = lambda: sunday.replace(hour=9)
published = []


async def fake_publish(account, entity_id, state, attributes=None):
    published.append((entity_id, state, attributes))


M.publish_sensor_for_account = fake_publish
posts.clear()
M._insight_pub_at = -1e9
asyncio.run(M._insight_tick())
asyncio.run(M._insight_tick())
notes = [p for p in posts if p[0] == "services/persistent_notification/create"]
weekly = [p for p in notes if "주간 리포트" in p[1]["title"]]
check(len(weekly) == 1, f"주간 리포트는 한 번만 ({[p[1]['title'] for p in notes]})")
check(any(p[0] == "events/dhlotto45_weekly_report" for p in posts), "주간 리포트 이벤트")
check({e for e, _s, _a in published} >= {"lotto45_luck_index", "lotto45_month_spend", "lotto45_claim_deadline"}, "인사이트 센서 발행")
check(all("sampleid" not in json.dumps(p[1], ensure_ascii=False) for p in posts), "알림·이벤트에 실제 아이디 없음")
M.FT.now_kst = lambda: sunday
posts.clear()
asyncio.run(M._insight_tick())
claim_notes = [p for p in posts if "수령" in p[1].get("title", "")]
check(claim_notes == [], "1년 가까이 남은 기한은 리마인더 없음")
snap = M._insight_snapshot()
check(snap["accounts"][0]["label"] == "Account_1" and "sampleid" not in json.dumps(snap, ensure_ascii=False), "인사이트 응답에 별칭만")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
