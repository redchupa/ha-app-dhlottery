"""
연금복권 순수 로직 단위 테스트 (브라우저/네트워크 불필요).

실행: python dhlotto45/tests/test_pension.py   (종료코드 0=통과)
의존성 없는 stdlib-only 러너라 어디서든 돈다. CI/배포 전 회귀 방지용.

검증 대상(순수 함수만 — zendriver 등은 지연 import라 모듈 import 자체는 안전):
- dh_pension_browser.validate_manual_selection : 수동 조/번호 입력 검증
- dh_pension_browser.classify_purchase_failure : 구매 실패 사유 분류(+안전속성)
- dh_pension_history.*                          : 구매내역 집계·당첨 판정
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))

from dh_pension_browser import (  # noqa: E402
    DhPensionBrowserError,
    classify_purchase_failure,
    is_login_success_url,
    validate_login_credentials,
    validate_manual_selection,
)
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


def expect_raise(fn, label):
    global PASS, FAIL
    try:
        fn()
    except DhPensionBrowserError:
        PASS += 1
        return
    except Exception as e:  # noqa: BLE001
        FAIL += 1
        print(f"  FAIL(wrong exc {type(e).__name__}): {label}")
        return
    FAIL += 1
    print("  FAIL(no raise):", label)


# ------------------------------------------------ validate_manual_selection
print("[validate_manual_selection]")
check(validate_manual_selection(1, "123456") == (1, "123456"), "정상 1/123456")
check(validate_manual_selection("5", "000000") == (5, "000000"), "문자열 조·0패딩")
check(validate_manual_selection(3, " 654321 ") == (3, "654321"), "번호 공백 트림")
check(validate_manual_selection(2, 123456) == (2, "123456"), "정수 번호 허용")
for bad_g in (0, 6, -1, 99, "x", None, 1.5):
    expect_raise(lambda g=bad_g: validate_manual_selection(g, "123456"), f"조 거부 {bad_g!r}")
for bad_d in ("12345", "1234567", "12a456", "", "abcdef", "12 456", None):
    expect_raise(lambda d=bad_d: validate_manual_selection(1, d), f"번호 거부 {bad_d!r}")

# ------------------------------------------------ validate_login_credentials
print("[validate_login_credentials]")
check(validate_login_credentials("user01", "a" * 20) is None, "비밀번호 20자 허용")
check(validate_login_credentials("user01", "p@ss!word#1") is None, "특수문자 허용")
expect_raise(lambda: validate_login_credentials("user01", "a" * 21), "비밀번호 21자 거부")
expect_raise(lambda: validate_login_credentials("user01", ""), "빈 비밀번호 거부")
expect_raise(lambda: validate_login_credentials("user01", None), "None 비밀번호 거부")
expect_raise(lambda: validate_login_credentials("", "pw"), "빈 아이디 거부")
expect_raise(lambda: validate_login_credentials("  ", "pw"), "공백 아이디 거부")
try:
    validate_login_credentials("user01", "a" * 25)
except DhPensionBrowserError as e:
    check("25자" in str(e) and "20자" in str(e), "21자+ 메시지에 길이 안내")

# ------------------------------------------------ is_login_success_url
print("[is_login_success_url]")
B = "https://www.dhlottery.co.kr"
check(is_login_success_url(B + "/main") is True, "/main 성공")
check(is_login_success_url(B + "/mypage/home") is True, "/mypage 성공")
check(is_login_success_url(B + "/login/loginSuccess.do") is True, "loginSuccess.do 성공")
check(is_login_success_url(B + "/mbrsrvc/ExpryPswdNoti") is True, "비번만료 안내 성공")
check(is_login_success_url(B + "/login") is False, "/login 머무름 실패")
check(is_login_success_url(B + "/login/securityLoginCheck.do") is False, "로그인체크 중 실패")
check(is_login_success_url("about:blank") is False, "about:blank 실패")
check(is_login_success_url("") is False, "빈 URL 실패")
check(is_login_success_url(None) is False, "None URL 실패")

# ------------------------------------------------ classify_purchase_failure
print("[classify_purchase_failure]")


def cls(t):
    return classify_purchase_failure(t)


# 카테고리 매핑
check(cls("예치금이 부족합니다.")[0] == "balance", "예치금부족→balance")
check(cls("잔액이 부족합니다")[0] == "balance", "잔액부족→balance")
check(cls("예치금을 충전해 주세요")[0] == "balance", "충전→balance")
check(cls("선택하신 번호는 이미 판매가 완료되었습니다.")[0] == "soldout", "매진→soldout")
check(cls("판매완료된 번호입니다")[0] == "soldout", "판매완료→soldout")
check(cls("구매 한도를 초과하였습니다")[0] == "limit", "한도초과→limit")
check(cls("1일 구매한도를 초과했습니다")[0] == "limit", "1일한도→limit")
check(cls("1회 구입한도는 10만원입니다")[0] == "limit", "구입한도→limit")
check(cls("판매시간이 아닙니다")[0] == "closed", "판매시간→closed")
check(cls("지금은 구매 가능한 시간이 아닙니다")[0] == "closed", "구매가능시간외→closed")
check(cls("판매가 마감되었습니다")[0] == "closed", "마감→closed")
check(cls("서비스 점검중입니다")[0] == "closed", "점검→closed")
check(cls("구매 번호를 선택해 주세요")[0] == "empty", "번호선택→empty")

# 안전 속성: 확정 미구매 카테고리는 모두 uncertain=False
for t in [
    "예치금이 부족합니다",
    "이미 판매가 완료되었습니다",
    "구매 한도 초과",
    "판매시간이 아닙니다",
    "구매 번호를 선택해 주세요",
]:
    check(cls(t)[2] is False, f"확정미구매 uncertain=False: {t[:10]}")

# 안전 속성(핵심): 분류 불가는 반드시 uncertain=True (이중지출 방지)
for t in ["", "   ", "서버 오류가 발생했습니다", "알 수 없는 응답", "ERROR 500", "???"]:
    r = cls(t)
    check(r[0] == "unknown" and r[2] is True, f"불명확→uncertain=True: {t[:12]!r}")

# 우선순위: 예치금이 먼저(동시 등장 시)
check(cls("예치금 부족 및 한도 관련 안내")[0] == "balance", "예치금 우선")
# 반환 형식
_c, _m, _u = cls("")
check(isinstance(_m, str) and _m != "", "message 비어있지 않음")

# ------------------------------------------------ dh_pension_history._safe_int
print("[dh_pension_history._safe_int]")
check(H._safe_int("5") == 5, "'5'→5")
check(H._safe_int("") == 0, "''→0")
check(H._safe_int(None) == 0, "None→0")
check(H._safe_int("abc") == 0, "'abc'→0")
check(H._safe_int(7) == 7, "7→7")
check(H._safe_int(None, 99) == 99, "default 99")

# ------------------------------------------------ group_rounds
print("[group_rounds]")
items = [
    {"ltEpsd": "338", "gmInfo": "1:111111"},
    {"ltEpsd": "338", "gmInfo": "2:222222"},
    {"ltEpsd": "337", "gmInfo": "3:333333"},
    {"ltEpsd": "0", "gmInfo": "x"},     # 무효 회차 제외
    {"gmInfo": "no round"},               # 회차 없음 제외
]
g = H.group_rounds(items)
check(set(g.keys()) == {338, 337}, "회차 키 {338,337}")
check(len(g[338]) == 2 and len(g[337]) == 1, "회차별 건수")
check(H.group_rounds([]) == {}, "빈 입력→{}")
check(H.group_rounds(None) == {}, "None→{}")

# ------------------------------------------------ build_round (당첨 판정)
print("[build_round]")
# 미추첨
games, w, tot = H.build_round([{"gmInfo": "1:123456", "ltWnResult": "미추첨"}])
check(w == 0 and tot == 0 and H.is_drawn(games) is False, "미추첨: win0·undrawn")
check(games[0]["group"] == "1" and games[0]["number"] == "123456", "gmInfo 파싱")
# 낙첨
games, w, tot = H.build_round([{"gmInfo": "1:123456", "ltWnResult": "낙첨"}])
check(w == 0 and H.is_drawn(games) is True, "낙첨: win0·drawn")
# 당첨(금액)
games, w, tot = H.build_round(
    [{"gmInfo": "2:654321", "ltWnResult": "7등 당첨", "ltWnAmt": "5000", "wnRnk": 7}]
)
check(w == 1 and tot == 5000, "당첨(금액): win1·5000")
# 당첨(등수만, 금액 0 — 연금형 월지급)
games, w, tot = H.build_round(
    [{"gmInfo": "1:777777", "ltWnResult": "1등", "ltWnAmt": 0, "wnRnk": 1}]
)
check(w == 1 and tot == 0, "당첨(등수만): win1·0원")
# 당첨(결과 텍스트만, rank/amt 미기입) — 확장된 휴리스틱
games, w, tot = H.build_round(
    [{"gmInfo": "3:888888", "ltWnResult": "2등 당첨", "wnRnk": None, "ltWnAmt": None}]
)
check(w == 1, "당첨(텍스트만): win1")
# 등외 제외
games, w, tot = H.build_round([{"gmInfo": "1:999999", "ltWnResult": "등외"}])
check(w == 0 and H.is_drawn(games) is True, "등외: win0·drawn")
# 콜론 없는 gmInfo
games, _, _ = H.build_round([{"gmInfo": "123456", "ltWnResult": "미추첨"}])
check(games[0]["group"] == "" and games[0]["number"] == "123456", "콜론없음 파싱")
# 혼합(당첨1 + 낙첨1)
games, w, tot = H.build_round([
    {"gmInfo": "1:111111", "ltWnResult": "7등 당첨", "ltWnAmt": "5000", "wnRnk": 7},
    {"gmInfo": "2:222222", "ltWnResult": "낙첨"},
])
check(w == 1 and tot == 5000 and len(games) == 2, "혼합: win1·2게임")
# 빈 결과(ltWnResult 없음)→ '-' → 미추첨 취급
games, w, _ = H.build_round([{"gmInfo": "1:111111"}])
check(games[0]["result"] == "-" and w == 0 and H.is_drawn(games) is False, "결과없음→미추첨")

# ------------------------------------------------ is_drawn / summarize
print("[is_drawn / summarize]")
check(H.is_drawn([]) is False, "is_drawn 빈→False")
check(H.is_drawn(None) is False, "is_drawn None→False")
check(H.summarize(338, [], 0, 0) == "지난 회차 구매 내역 없음", "summarize 빈")
und = H.build_round([{"gmInfo": "1:111111", "ltWnResult": "미추첨"}])[0]
check("추첨 대기" in H.summarize(338, und, 0, 0), "summarize 추첨대기")
wgames = H.build_round(
    [{"gmInfo": "1:111111", "ltWnResult": "7등 당첨", "ltWnAmt": "5000", "wnRnk": 7}]
)[0]
s = H.summarize(338, wgames, 1, 5000)
check("당첨 1매" in s and "5,000" in s, "summarize 당첨")
lgames = H.build_round([{"gmInfo": "1:111111", "ltWnResult": "낙첨"}])[0]
check("모두 낙첨" in H.summarize(338, lgames, 0, 0), "summarize 낙첨")

# ------------------------------------------------ result
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
