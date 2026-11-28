"""features.py 단위 테스트 (stdlib 만 사용). 실행: python -X utf8 test_features.py"""

import logging
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))

import features as F  # noqa: E402

PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


KST = F.KST

# ------------------------------------------------ settings
print("[normalize_settings]")
d = F.normalize_settings(None)
check(d["auto_buy"]["enabled"] is False and d["favorites"] == [] and d["notify"]["win"] is True, "기본값")
s = F.normalize_settings({
    "notify": {"service": "notify.mobile_app_phone", "win": False, "low_deposit_threshold": 12345, "x": 1},
    "favorites": [
        {"type": "lotto", "name": "생일\n번호", "numbers": "7, 1, 12, auto, auto, auto"},
        {"type": "lotto", "numbers": "1,1,2,3,4,5"},            # 중복 → 제외
        {"type": "pension", "group": 3, "digits": "012345", "id": "AbC1"},
        {"type": "pension", "group": 9, "digits": "012345"},     # 조 범위 밖 → 제외
        "bad",
    ],
    "auto_buy": {"enabled": True, "schedules": [
        {"action": "lotto_auto_5", "days": [5, 5, 1], "time": "09:30", "account": "all"},
        {"action": "lotto_manual", "days": [1], "time": "09:00"},     # 수동은 자동 구매 불가
        {"action": "pension_auto_1", "days": [], "time": "09:00"},     # 요일 없음
        {"action": "pension_auto_1", "days": [3], "time": "24:00"},    # 시각 오류
        {"action": "pension_auto_1", "days": [True, 3], "time": "07:05", "account": "account_2", "enabled": False},
    ]},
})
check(s["notify"]["service"] == "notify.mobile_app_phone" and s["notify"]["win"] is False, "notify 서비스·토글")
check(s["notify"]["low_deposit_threshold"] == 12000 and "x" not in s["notify"], "기준금액 천원 단위·미지원 키 제거")
check(F.normalize_settings({"notify": {"service": "persistent_notification.create"}})["notify"]["service"] == "", "notify. 외 서비스 거부")
check(F.normalize_settings({"notify": {"service": "notify.a;rm"}})["notify"]["service"] == "", "서비스 이름 문자 제한")
check(len(s["favorites"]) == 2, "즐겨찾기 유효한 것만")
check(s["favorites"][0]["numbers"] == "7,1,12,auto,auto,auto" and s["favorites"][0]["name"] == "생일 번호", "로또 즐겨찾기 정규화")
check(s["favorites"][1] == {"id": "abc1", "type": "pension", "name": "", "group": 3, "digits": "012345"}, "연금 즐겨찾기")
sch = s["auto_buy"]["schedules"]
check(len(sch) == 2 and sch[0]["days"] == [1, 5] and sch[0]["account"] == "all", "일정 정규화·무효 제외")
check(sch[1]["days"] == [3] and sch[1]["enabled"] is False and sch[1]["account"] == "account_2", "bool 요일 제외·비활성")
check(F.normalize_settings({"auto_buy": {"enabled": "true"}})["auto_buy"]["enabled"] is False, "마스터 스위치는 True 만")
many = F.normalize_settings({"favorites": [{"type": "lotto", "numbers": "1,2,3,4,5,%d" % (6 + i)} for i in range(20)]})
check(len(many["favorites"]) == F.FAV_MAX, "즐겨찾기 최대 개수")

print("[merge_settings]")
m = F.merge_settings(s, {"notify": {"purchase": False}, "auto_buy": {"enabled": False}})
check(m["notify"]["purchase"] is False and m["notify"]["service"] == "notify.mobile_app_phone", "notify 키 병합")
check(m["auto_buy"]["enabled"] is False and len(m["auto_buy"]["schedules"]) == 2, "auto_buy 병합(일정 유지)")
check(F.merge_settings(s, "bad") == s, "잘못된 변경 무시")

# ------------------------------------------------ schedule
print("[due_schedules]")
sat = datetime(2026, 11, 28, 9, 30, 5, tzinfo=KST)   # 토요일
check(sat.weekday() == 5, "기준일 토요일")
due = F.due_schedules(s, sat, {})
check(len(due) == 1 and due[0][1] == f"{sch[0]['id']}:2026-11-28", "예약 시각에 실행")
check(F.due_schedules(s, sat, {due[0][1]: 1}) == [], "같은 날 두 번 실행 안 함")
check(F.due_schedules(s, sat + timedelta(minutes=11), {}) == [], "10분 창 지나면 실행 안 함")
check(F.due_schedules(s, sat - timedelta(minutes=1), {}) == [], "예약 전 실행 안 함")
check(F.due_schedules(s, sat + timedelta(days=1), {}) == [], "다른 요일 실행 안 함")
off = F.merge_settings(s, {"auto_buy": {"enabled": False}})
check(F.due_schedules(off, sat, {}) == [], "마스터 스위치 꺼짐")
check(F.schedule_targets({"account": "all"}, ["account_1", "account_2"]) == ["account_1", "account_2"], "전체 계정")
check(F.schedule_targets({"account": "account_2"}, ["account_1", "account_2"]) == ["account_2"], "지정 계정")
check(F.schedule_targets({"account": "account_9"}, ["account_1"]) == [], "없는 계정")
pd = F.prune_done({"a:2026-11-01": 1, "b:2026-11-27": 1}, sat.date())
check(list(pd) == ["b:2026-11-27"], "오래된 실행 기록 정리")

# ------------------------------------------------ ledger extraction
print("[ledger_items_from_sensor]")
it = F.ledger_items_from_sensor("account_1", "lotto45_game_1", "1, 2, 3, 4, 5, 6",
                                {"numbers": [6, 5, 4, 3, 2, 1], "round_no": 1200, "slot": "A"})
check(len(it) == 1 and it[0]["kind"] == "buy" and it[0]["key"] == "lotto:account_1:1200:A:1-2-3-4-5-6", "로또 구매")
check(F.ledger_items_from_sensor("account_1", "lotto45_game_1", "구매 내역 없음", {"numbers": [], "round_no": 0}) == [], "빈 슬롯")
prizes = {"round": 1200, 1: 2_000_000_000, 3: 1_500_000, 4: 50000, 5: 5000}
w = F.ledger_items_from_sensor("account_1", "lotto45_prev_game_2_result", "3등 당첨",
                               {"my_numbers": [1, 2, 3, 4, 5, 6], "round_no": 1200}, prizes)
check(len(w) == 1 and w[0]["kind"] == "win" and w[0]["amount"] == 1_500_000 and w[0]["rank"] == 3, "로또 3등(당첨금 반영)")
w5 = F.ledger_items_from_sensor("account_1", "lotto45_prev_game_2_result", "5등 당첨",
                                {"my_numbers": [1, 2, 3, 4, 5, 6], "round_no": 1100}, prizes)
check(w5[0]["amount"] == 5000, "다른 회차 5등은 고정 5천원")
w2 = F.ledger_items_from_sensor("account_1", "lotto45_prev_game_2_result", "2등 당첨",
                                {"my_numbers": [1, 2, 3, 4, 5, 6], "round_no": 1100}, prizes)
check(w2[0]["amount"] == 0, "회차 다른 2등은 금액 미상")
check(F.ledger_items_from_sensor("account_1", "lotto45_prev_game_2_result", "낙첨",
                                 {"my_numbers": [1, 2, 3, 4, 5, 6], "round_no": 1200}) == [], "낙첨 제외")
pen = F.ledger_items_from_sensor("account_2", "pension720_last_round", 2, {"round_no": 300, "games": [
    {"group": "1", "number": "123456", "result": "낙첨", "rank": 0, "win_amount": 0},
    {"group": "2", "number": "654321", "result": "7등 당첨", "rank": 7, "win_amount": 1000},
]})
check([x["kind"] for x in pen] == ["buy", "buy", "win"] and pen[2]["amount"] == 1000, "연금 구매·당첨")
check(F.ledger_items_from_sensor("account_2", "pension720_this_round", 1, {"round_no": 301, "games": [
    {"group": "1", "number": "111111", "result": "미추첨"}]})[0]["kind"] == "buy", "연금 미추첨은 구매만")
check(F.ledger_items_from_sensor("account_1", "lotto45_balance", 5000, {}) == [], "관계없는 센서")

print("[Ledger]")
now = datetime(2026, 11, 28, 10, 0, tzinfo=KST)
L = F.Ledger()
check(L.add("account_1", it[0], now) is True and L.add("account_1", it[0], now) is False, "중복 제거")
L.add("account_1", w[0], now)
L.add("account_2", pen[0], now - timedelta(days=40))
L.add("account_2", pen[2], now - timedelta(days=40))
st = L.stats(now)
check(len(st["months"]) == 12 and st["months"][-1]["month"] == "2026-11", "12개월 라벨")
check(st["months"][-1]["spend"] == 1000 and st["months"][-1]["win"] == 1_500_000, "이번 달 집계")
check(st["months"][-2]["month"] == "2026-10" and st["months"][-2]["pension"] == 1000, "지난 달 연금")
check(st["total"]["spend"] == 2000 and st["total"]["win"] == 1_501_000 and st["total"]["ratio"] == 75050.0, "합계·회수율")
check(L.stats(now, acct="account_2")["total"]["spend"] == 1000, "계정별 집계")
check(st["recent_wins"][0]["amount"] == 1_500_000 and st["since"] == "2026-10", "최근 당첨·시작 월")
L2 = F.Ledger(L.entries)
check(L2.add("account_1", it[0], now) is False, "저장 후 다시 불러와도 중복 제거")
old = F.Ledger([{"key": "x", "acct": "a", "kind": "buy", "game": "lotto", "amount": 1000, "month": "2020-01", "ts": 0}])
old.prune(now)
check(old.entries == [], "36개월 지난 항목 정리")

# ------------------------------------------------ notify helpers
print("[notify]")
check(F.needs_low_deposit_alert(3000, 5000, "2026-11-28", None) is True, "부족 알림")
check(F.needs_low_deposit_alert(3000, 5000, "2026-11-28", "2026-11-28") is False, "하루 1회")
check(F.needs_low_deposit_alert(9000, 5000, "2026-11-28", None) is False, "충분")
check(F.needs_low_deposit_alert("x", 5000, "2026-11-28", None) is False, "잘못된 값")
check(F.needs_low_deposit_alert(0, 0, "2026-11-28", None) is False, "기준 0 = 끔")
t, b = F.win_message("Account_1", w[0])
check("Account_1" in t and "1200회 3등" in b and "1,500,000원" in b, "당첨 문구")
check(F.win_message("Account_1", dict(w[0], rank=1))[0].startswith("🏆"), "1등 문구")
check("당첨금은" in F.win_message("Account_1", w2[0])[1], "금액 미상 문구")
t, b = F.purchase_message("Account_2", "로또 1게임 자동", "error", "예치금 부족", "schedule")
check(t.startswith("❌") and "정기 자동 구매" in b, "구매 실패 문구")

# ------------------------------------------------ diagnostics
print("[scrub_text / RingLogHandler]")
raw = ("mqtt://user1:secretpw@203.0.113.7:1883 me@example.com 172.30.32.2 127.0.0.1 "
       "token=" + "A" * 40)
sc = F.scrub_text(raw)
check("secretpw" not in sc and "user1" not in sc and "***:***@" in sc, "URL 계정 가림")
check("example.com" not in sc and "203.0.113.7" not in sc and "x.x.x.7" in sc, "이메일·IP 가림")
check("172.30.32.2" in sc and "127.0.0.1" in sc and "A" * 40 not in sc, "내부 IP 유지·토큰 가림")
rh = F.RingLogHandler(capacity=3)
rh.setFormatter(logging.Formatter("%(message)s"))
lg = logging.getLogger("t_ring")
lg.propagate = False
lg.setLevel(logging.INFO)
lg.addHandler(rh)
for i in range(5):
    lg.info("line %d", i)
check(rh.tail() == ["line 2", "line 3", "line 4"], "링버퍼 최근 N줄")

# ------------------------------------------------ simulator
print("[simulate_lotto_numbers]")
sim_draws = [
    {"round_no": 1205, "numbers": [1, 2, 3, 4, 5, 6], "bonus": 7},          # 1등 (6개)
    {"round_no": 1204, "numbers": [1, 2, 3, 4, 5, 40], "bonus": 6},         # 2등 (5개 + 보너스)
    {"round_no": 1203, "numbers": [1, 2, 3, 4, 5, 41], "bonus": 42},        # 3등 (5개)
    {"round_no": 1202, "numbers": [1, 2, 3, 4, 41, 42], "bonus": 43},       # 4등 (4개)
    {"round_no": 1201, "numbers": [1, 2, 3, 41, 42, 43], "bonus": 44},      # 5등 (3개)
    {"round_no": 1200, "numbers": [10, 20, 30, 31, 32, 33], "bonus": 34},   # 낙첨
]
sr = F.simulate_lotto_numbers("1,2,3,4,5,6", sim_draws)
check(sr["checked_rounds"] == 6 and sr["total_spend"] == 6000, "시뮬 회차·지출 집계")
check(sr["best_rank"] == 1 and len(sr["hits"]) == 5, "1~5등 모두 적중")
check(all(sr["rank_counts"][str(r)] == 1 for r in range(1, 6)), "등수별 각 1회")
check(sr["total_win"] == 2_000_000_000 + 50_000_000 + 1_500_000 + 50_000 + 5_000, "추정 당첨금 합계")
# 반자동(고정 3개 이상) 허용, 2개 이하 거부
sr_semi = F.simulate_lotto_numbers("1,2,3,auto,auto,auto", sim_draws)
check(sr_semi["fixed_count"] == 3 and sr_semi["rank_counts"]["5"] == 5, "반자동 3고정 시뮬")
try:
    F.simulate_lotto_numbers("1,2,auto,auto,auto,auto", sim_draws)
    check(False, "고정 2개 이하는 거부돼야 함")
except F.DashboardInputError:
    check(True, "고정 2개 이하 거부")

# ------------------------------------------------ number_stats (v2.10.0)
print("[number_stats]")
draws = [
    {"round_no": 1252, "numbers": [1, 2, 3, 4, 5, 6], "bonus": 7},
    {"round_no": 1251, "numbers": [1, 10, 20, 30, 40, 45], "bonus": 2},
    {"round_no": 1250, "numbers": [1, 11, 21, 31, 41, 44], "bonus": 3},
    {"round_no": 1249, "numbers": [9, 9]},                          # 잘못된 회차 → 건너뜀
]
ns = F.number_stats(draws, {1: 200, "2": 150}, window=3)
by = {x["n"]: x for x in ns["numbers"]}
check(ns["window"] == 3 and ns["latest_round"] == 1252 and ns["expected"] == 0.4, "범위·최신 회차·기대값")
check(by[1]["count"] == 3 and by[1]["gap"] == 0 and by[1]["total"] == 200, "1번: 3회·최근·누적")
check(by[2]["count"] == 1 and by[2]["total"] == 150, "보너스는 세지 않음·문자열 키 누적")
check(by[45]["gap"] == 1 and by[44]["gap"] == 2 and by[8]["gap"] is None and by[8]["count"] == 0, "미출현 기간")
check(ns["hot"][0] == 1 and ns["max_count"] == 3 and len(ns["hot"]) == 6, "가장 많이 나온 번호")
check(ns["absent"][0]["gap"] is None and len(ns["absent"]) == 6, "장기 미출현(범위 내 미출현 우선)")
check(F.number_stats([], None)["window"] == 0 and F.number_stats([], None)["max_count"] == 0, "데이터 없음")
check(F.number_stats(draws, None, window=1)["window"] == 1, "범위 제한")

# ------------------------------------------------ ledger export / import (v2.10.0)
print("[ledger export/import]")
good = {"key": "lotto:account_1:1252:A:1-2-3-4-5-6", "acct": "account_1", "kind": "buy", "game": "lotto",
        "amount": 1000, "round": 1252, "info": "=HYPERLINK(\"x\")", "month": "2026-11", "ts": 1795800000}
bad_list = [
    dict(good, key="evil:account_1:x"),                 # 알 수 없는 key 형식
    dict(good, acct="sampleid01"),                      # 별칭이 아닌 계정
    dict(good, kind="refund"),
    dict(good, amount=True),                            # bool 거부
    dict(good, amount=-5),
    dict(good, month="2026-13"),
    {"key": "lotto:account_1:x"},                       # 필드 누락
    "bad",
]
ok, skipped = F.validate_ledger_entries({"entries": [good] + bad_list})
check(len(ok) == 1 and skipped == len(bad_list), "유효 항목만 통과")
check(F.validate_ledger_entries([good])[0][0]["key"] == good["key"], "목록 형식도 허용")
try:
    F.validate_ledger_entries({"x": 1}); check(False, "entries 없으면 오류")
except F.DashboardInputError:
    check(True, "entries 없으면 오류")
L3 = F.Ledger()
now3 = datetime(2026, 11, 28, 10, 0, tzinfo=KST)
check(L3.merge(ok, now3) == 1 and L3.merge(ok, now3) == 0, "가져오기 병합·중복 제외")
csv_text = F.ledger_to_csv(L3.entries, {"account_1": "Account_1"})
lines = csv_text.strip().splitlines()
check(lines[0] == "date,month,account,game,kind,amount,round,info" and "Account_1" in lines[1], "CSV 헤더·계정 라벨")
check("'=HYPERLINK" in lines[1], "CSV 수식 주입 방지")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
