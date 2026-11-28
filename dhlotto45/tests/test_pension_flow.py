"""연금복권 구매 흐름 회귀 테스트(가짜 페이지, 실제 브라우저·구매 없음).

실행: python -X utf8 test_pension_flow.py
v2.11.2 제보: "1매 샀는데 2매가 결제됨". 원인 후보였던 번호확정(doVerify) 재호출을 막았는지,
그리고 완료 화면에 요청보다 많은 티켓이 보이면 숨기지 않고 경고하는지 검사한다.
"""

import asyncio
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..", "app")
sys.path.insert(0, APP)
os.environ.setdefault("DHL_DATA_DIR", tempfile.mkdtemp(prefix="dhl_pf_"))

import dh_pension_browser as B  # noqa: E402

PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


async def _no_sleep(*_a, **_k):
    return None


B.asyncio.sleep = _no_sleep  # 테스트 속도용(대기 생략)

# ------------------------------------------------ 1. source: doVerify called in one place only
print("[doVerify 호출 위치]")
src = open(os.path.join(APP, "dh_pension_browser.py"), encoding="utf-8").read()
calls = re.findall(r'_safe_eval\(\s*tab,\s*"doVerify\(\)"\s*\)', src)
check(len(calls) == 1, f"doVerify() 실제 호출은 한 곳뿐 ({len(calls)})")
body = src[src.index("async def _verify_once"):src.index("async def _confirm_order")]
check("for " not in body and "while " not in body, "_verify_once 안에 반복(재호출) 없음")


# ------------------------------------------------ 2. slow verify → stop before payment
class FakeBrowser(B.DhPensionBrowser):
    def __init__(self, idle_results, tickets=None):
        super().__init__("sampleid01", "pw")
        self.calls = []
        self.idle_results = list(idle_results)
        self.tickets = tickets or []
        self._dialog_msgs = []

    async def _safe_eval(self, tab, expr):
        self.calls.append(expr)
        if "typeof selNumberPopup" in expr:
            return True
        return None

    async def _wait_ajax_idle(self, tab, timeout):
        return self.idle_results.pop(0) if self.idle_results else True

    async def _wait_js(self, tab, expr, timeout):
        return True

    async def _ensure_balance(self, tab, amount):
        return None

    async def _confirm_order(self, tab, count, dialogs_before):
        return None

    async def _extract_tickets(self, tab):
        return list(self.tickets)

    async def _resolve_round(self):
        return 344


class FakeTab:
    async def get(self, url):
        return None


print("[응답이 늦을 때]")
fb = FakeBrowser(idle_results=[True, False])  # 앞선 요청 대기 OK, doVerify 응답은 끝내 안 옴
try:
    asyncio.run(fb._purchase(FakeTab(), 1))
    check(False, "늦으면 예외로 중단")
except B.DhPensionBrowserError as e:
    check("구매하지 않았습니다" in str(e) and "지출 없음" in str(e), "결제 전 중단 문구")
check(fb.calls.count("doVerify()") == 1, f"doVerify 는 한 번만 ({fb.calls.count('doVerify()')})")
check("doOrder()" not in fb.calls, "doOrder(결제) 호출 안 함")

print("[정상 1매]")
fb = FakeBrowser(idle_results=[], tickets=[{"no": 1, "group": 2, "numbers": "123456"}])
res = asyncio.run(fb._purchase(FakeTab(), 1))
check(len(res) == 1 and fb.calls.count("doVerify()") == 1 and fb.calls.count("doOrder()") == 1, "1매: verify 1회·order 1회")

print("[5매]")
fb = FakeBrowser(idle_results=[], tickets=[{"no": i, "group": i, "numbers": "12345%d" % i} for i in range(1, 6)])
res = asyncio.run(fb._purchase(FakeTab(), 5))
check(fb.calls.count("doVerify()") == 5 and fb.calls.count("doOrder()") == 1 and len(res) == 5, "5매: 줄마다 verify 1회")

print("[완료 화면에 더 많은 티켓]")
fb = FakeBrowser(idle_results=[], tickets=[{"no": 1, "group": 2, "numbers": "123456"}, {"no": 2, "group": 2, "numbers": "123456"}])


async def run_do_buy():
    async def fake_session(work):
        return await work(FakeTab())
    fb._session = fake_session
    return await fb._do_buy(1)


r = asyncio.run(run_do_buy())
check(r["count"] == 1 and len(r["extra_tickets"]) == 1, "요청분과 추가분을 나눠 돌려줌(숨기지 않음)")
w = B.extra_ticket_warning(1, r["extra_tickets"])
check("1매 외에 1매" in w and "구매내역" in w, "경고 문구")
check(B.extra_ticket_warning(1, []) == "", "추가분 없으면 경고 없음")
check("40초" in B.verify_timeout_message("조1"), "대기 시간 안내")

# ------------------------------------------------ 3. main: warning sensor + conservative daily count
print("[main 처리]")
import main as M  # noqa: E402

published = {}


async def fake_publish(account, entity_id, state, attributes=None):
    published[entity_id] = state


async def fake_refresh(account):
    return None


M.publish_sensor_for_account = fake_publish
M._refresh_pension_history_after_purchase = fake_refresh


class FakePension:
    async def async_buy_auto(self, count):
        return {"round": 344, "count": 1, "amount": 1000, "numbers": "2조 123456",
                "tickets": [{"group": 2, "numbers": "123456"}], "extra_tickets": [{"group": 2, "numbers": "654321"}]}


acc = M.AccountData("sampleid01", "pw")
acc.pension = FakePension()
M.accounts["sampleid01"] = acc
M.purchase_guard.reset()
M.pension_daily_tracker._counts.clear()
asyncio.run(M.execute_pension_purchase(acc, 1))
check(str(published.get("pension720_purchase_error", "")).startswith("⚠️") and "654321" in published["pension720_purchase_error"],
      "추가 티켓이 보이면 오류 센서에 경고(없음으로 지우지 않음)")
cnt = M.pension_daily_tracker.get_today_count("sampleid01")
check(cnt == 2, f"하루 한도는 화면에 보인 2매로 셈 ({cnt})")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
