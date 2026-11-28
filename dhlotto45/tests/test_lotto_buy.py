"""로또 구매 요청 재시도 규칙 테스트(가짜 서버, 실제 구매 없음).

실행: python -X utf8 test_lotto_buy.py
주문(execBuy.do)을 보낸 뒤 결과를 못 받은 경우(응답 지연·형식 오류)에는 같은 주문을 다시
보내면 이중 결제가 될 수 있다 → 재시도 금지. 주문 전 준비 실패·서버 연결 실패만 재시도한다.
"""

import asyncio
import datetime
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))

import aiohttp  # noqa: E402

import dh_lotto_645 as L  # noqa: E402

PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


class FixedKST(datetime.datetime):
    """판매 시간(수요일 낮)으로 고정."""

    @classmethod
    def now(cls, tz=None):
        return datetime.datetime(2026, 11, 25, 12, 0, tzinfo=tz)


L.datetime.datetime = FixedKST


class Resp:
    def __init__(self, payload=None, exc=None, text='{"ready_ip": "1.1.1.1"}'):
        self.payload, self.exc, self._text = payload, exc, text

    async def json(self, content_type="application/json"):
        if self.exc:
            raise self.exc
        return self.payload

    async def text(self):
        return self._text


class Session:
    def __init__(self, order_behaviours):
        self.order_behaviours = list(order_behaviours)
        self.orders = 0

    async def post(self, url, data=None, timeout=None):
        if "egovUserReadySocket" in url:
            return Resp()
        self.orders += 1
        b = self.order_behaviours.pop(0)
        if isinstance(b, BaseException):
            raise b
        return b


OK = {"result": {"resultCode": "100", "buyRound": "1252", "barCode1": "x", "barCode2": "x", "barCode3": "x",
                 "barCode4": "x", "barCode5": "x", "barCode6": "x", "issueDay": "2026/11/25", "issueTime": "12:00",
                 "arrGameChoiceNum": ["A|01|02|03|04|05|063"], "nBuyAmount": 1000, "weekDay": "수"}}


def make(order_behaviours):
    async def nothing(*a, **k):
        return None

    async def empty_list(*a, **k):
        return []

    async def balance():
        return SimpleNamespace(purchase_available=100000)

    client = SimpleNamespace(session=Session(order_behaviours), _async_ensure_main_mode_normal=nothing,
                             async_get_buy_list=empty_list, async_get_balance=balance)
    lotto = L.DhLotto645.__new__(L.DhLotto645)
    lotto.client = client

    async def latest():
        return 1251
    lotto.async_get_latest_round_no = latest
    return lotto, client.session


slots = [L.DhLotto645.Slot(mode=L.DhLotto645SelMode.AUTO, numbers=[])]


def run(behaviours):
    lotto, sess = make(behaviours)
    try:
        r = asyncio.run(lotto.async_buy(slots, max_games=1))
        return r, None, sess.orders
    except Exception as e:  # noqa: BLE001
        return None, e, sess.orders


print("[주문 후 결과를 못 받음 → 재시도 금지]")
for name, exc in [("응답 지연", asyncio.TimeoutError()), ("연결 끊김", aiohttp.ServerDisconnectedError()),
                  ("응답 읽기 실패", None)]:
    beh = [exc] if exc else [Resp(exc=ValueError("not json"))]
    r, e, n = run(beh + [Resp(OK)])
    check(n == 1, f"{name}: 주문 1번만 전송 ({n})")
    check(e is not None and "구매내역을 먼저 확인" in str(e), f"{name}: '구매됐을 수 있음' 안내")

r, e, n = run([Resp(payload="<html>")])
check(n == 1 and e is not None and "확인" in str(e), "HTML 등 예상 밖 응답도 재시도 안 함")

print("[연결 자체 실패 → 한 번 재시도]")
conn_err = aiohttp.ClientConnectorError(SimpleNamespace(ssl=None, host="x", port=443), OSError("refused"))
r, e, n = run([conn_err, Resp(OK)])
check(e is None and n == 2, f"연결 실패 뒤 재시도해서 성공 (주문 시도 {n}, 오류 {e})")
r, e, n = run([conn_err, conn_err])
check(n == 2 and e is not None and "cannot reach server" in str(e), "두 번 다 연결 실패면 중단")

print("[정상·거절]")
r, e, n = run([Resp(OK)])
check(e is None and n == 1, "정상 구매 1번")
r, e, n = run([Resp({"result": {"resultCode": "-1", "resultMsg": "한도 초과"}})])
check(n == 1 and e is not None and "한도 초과" in str(e), "서버가 거절하면 재시도 안 함")

print("[판매 시간]")


class SatNight(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime.datetime(2026, 11, 28, 20, 10, tzinfo=tz)  # 토 20:10


L.datetime.datetime = SatNight
r, e, n = run([Resp(OK)])
check(n == 0 and e is not None and "Saturday" in str(e), "토요일 20:00 이후 주문 안 보냄")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
