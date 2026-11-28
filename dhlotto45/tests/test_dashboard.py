"""
대시보드 보안·입력 검증 + 연금 회차 선택 단위 테스트 (stdlib-only).

실행: python dhlotto45/tests/test_dashboard.py   (종료코드 0=통과)
"""
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))

import dashboard_api as D  # noqa: E402
import dh_pension_history as H  # noqa: E402

PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


def expect_input_error(fn, label):
    global PASS, FAIL
    try:
        fn()
    except D.DashboardInputError:
        PASS += 1
        return
    except Exception as e:  # noqa: BLE001
        FAIL += 1
        print(f"  FAIL(wrong exc {type(e).__name__}): {label}")
        return
    FAIL += 1
    print("  FAIL(no raise):", label)


# ------------------------------------------------ ingress / csrf
print("[ingress / csrf]")
check(D.is_ingress_client("172.30.32.2") is True, "Ingress 프록시 IP 허용")
for bad in ("172.30.32.1", "203.0.113.10", "127.0.0.1", "", None, "172.30.32.20"):
    check(D.is_ingress_client(bad) is False, f"비Ingress 거부 {bad!r}")
check(D.csrf_ok("tok123", "tok123") is True, "CSRF 일치")
for bad in ("tok124", "", None, 123, "TOK123"):
    check(D.csrf_ok("tok123", bad) is False, f"CSRF 불일치 거부 {bad!r}")
check(D.csrf_ok("", "") is False, "기대 토큰 비면 거부")

# ------------------------------------------------ aliases
print("[aliases]")
al = D.account_aliases(["userA01", "userB02"])
check(al == {"userA01": ("account_1", "Account_1"), "userB02": ("account_2", "Account_2")}, "설정 순서 별칭")
check(D.resolve_alias(["userA01", "userB02"], "account_2") == "userB02", "별칭→아이디")
check(D.resolve_alias(["userA01"], "account_9") is None, "없는 별칭 None")
check(D.resolve_alias(["userA01"], "userA01") is None, "실제 아이디로는 조회 불가")

# ------------------------------------------------ actions
print("[actions]")
check(D.action_label("lotto_auto_5") == ("로또 5게임 자동", 5000), "로또 5게임 라벨/금액")
check(D.action_label("pension_auto_1") == ("연금복권 1매 자동", 1000), "연금 1매 라벨/금액")
for bad in ("diag_pension_manual", "buy_auto_1", "", "lotto_auto_99"):
    expect_input_error(lambda b=bad: D.action_label(b), f"허용목록 외 거부 {bad!r}")
check(D.ALLOWED_ACTIONS == {"lotto_auto_1", "lotto_auto_5", "lotto_manual",
                            "pension_auto_1", "pension_auto_5", "pension_manual"}, "허용 작업 6종")

# ------------------------------------------------ lotto manual
print("[normalize_lotto_manual]")
check(D.normalize_lotto_manual("1,2,3,4,5,6") == "1,2,3,4,5,6", "수동 6개")
check(D.normalize_lotto_manual(" 7, AUTO ,45,auto,auto,auto ") == "7,auto,45,auto,auto,auto", "반자동·대소문자·공백")
for bad in ("", None, "1,2,3", "1,2,3,4,5,6,7", "0,2,3,4,5,6", "1,2,3,4,5,46",
            "1,1,3,4,5,6", "a,2,3,4,5,6", "1.5,2,3,4,5,6", "-1,2,3,4,5,6", "1," * 40):
    expect_input_error(lambda b=bad: D.normalize_lotto_manual(b), f"로또 입력 거부 {str(bad)[:20]!r}")

# ------------------------------------------------ pension manual
print("[normalize_pension_manual]")
check(D.normalize_pension_manual("3", "012345") == "3,012345", "연금 3조 012345")
check(D.normalize_pension_manual(5, " 999999 ") == "5,999999", "정수 조·공백")
for g, d in (("0", "123456"), ("6", "123456"), ("x", "123456"), (None, "123456"),
             ("1", "12345"), ("1", "1234567"), ("1", "12a456"), ("1", None), ("1.0", "123456")):
    expect_input_error(lambda g=g, d=d: D.normalize_pension_manual(g, d), f"연금 입력 거부 {g!r},{d!r}")

# ------------------------------------------------ judge_outcome
print("[judge_outcome]")
t0 = 1000.0
check(D.judge_outcome({"state": "예치금 부족", "ts": 1001}, t0) == ("error", "예치금 부족"), "오류 센서 갱신 → error")
st, msg = D.judge_outcome({"state": "없음", "ts": 1002}, t0, {"state": "344회 1매 (1조 123456)", "ts": 1001})
check(st == "success" and "1조 123456" in msg, "없음 + 구매센서 → success 메시지")
check(D.judge_outcome({"state": "없음", "ts": 1002}, t0, {"state": "old", "ts": 10})[1] == "구매 완료", "오래된 구매센서는 메시지 미사용")
check(D.judge_outcome({"state": "예전 오류", "ts": 999}, t0)[0] == "skipped", "시작 전 갱신 → skipped")
check(D.judge_outcome(None, t0)[0] == "skipped", "센서 없음 → skipped")

# ------------------------------------------------ AliasLogFilter
print("[AliasLogFilter]")
flt = D.AliasLogFilter(D.account_aliases(["sampleid01", "sampleid02", "abc"]))
rec = logging.LogRecord("x", logging.INFO, __file__, 1, "[PENSION][%s] buy topic=dhlotto_%s_btn", ("sampleid01", "sampleid02"), None)
flt.filter(rec)
m = rec.getMessage()
check("sampleid01" not in m and "sampleid02" not in m and "Account_1" in m and "Account_2" in m, "로그 아이디 치환")
rec2 = logging.LogRecord("x", logging.INFO, __file__, 1, "abc short id kept", None, None)
flt.filter(rec2)
check(rec2.getMessage() == "abc short id kept", "4자 미만 아이디는 치환 안 함")
flt2 = D.AliasLogFilter(D.account_aliases(["user1", "user12"]))
rec3 = logging.LogRecord("x", logging.INFO, __file__, 1, "a=user12 b=user1", None, None)
flt2.filter(rec3)
check(rec3.getMessage() == "a=Account_2 b=Account_1", "부분 겹치는 아이디(긴 것 먼저)")
try:
    raise ValueError("login failed for sampleid01")
except ValueError:
    rec4 = logging.LogRecord("x", logging.ERROR, __file__, 1, "err", None, sys.exc_info())
flt.filter(rec4)
check("sampleid01" not in (rec4.exc_text or "") and "Account_1" in (rec4.exc_text or ""), "트레이스백 아이디 치환")

# ------------------------------------------------ pension select_rounds / result_style
print("[select_rounds / result_style]")
rounds = {344: [1], 343: [1], 341: [1]}
check(H.select_rounds(rounds, 343) == (344, 343), "현재=최신+1, 이전=최신 추첨회차")
check(H.select_rounds({342: [1]}, 343) == (344, 342), "이번 미구매·지난주 미구매 → 이전=구매한 최근 추첨회차")
check(H.select_rounds({344: [1]}, 343) == (344, 0), "이전 구매 없음 → 0")
check(H.select_rounds({}, 343) == (344, 0), "구매 없음 → 현재만")
check(H.select_rounds({344: [1], 343: [1]}, 0) == (344, 343), "최신회차 모름 → 구매순서 대체")
check(H.select_rounds({}, 0) == (0, 0), "모두 없음")
check(H.result_style("미추첨") == ("mdi:clock-outline", "grey"), "미추첨 회색")
check(H.result_style("낙첨")[1] == "red", "낙첨 빨강")
check(H.result_style("1등 당첨")[1] == "gold", "1등 금색")
check(H.result_style("7등 당첨")[1] == "green", "7등 초록")
check(H.result_style("보너스 당첨")[1] == "green", "보너스 초록")
check(H.result_style(None)[1] == "grey", "None 회색")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
