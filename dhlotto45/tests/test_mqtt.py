"""MQTT 연결·재연결 처리 테스트(가짜 paho 클라이언트, 실제 브로커 불필요).

실행: python -X utf8 test_mqtt.py
- 재연결 때 버튼 명령 구독이 복구되는지
- 인증 실패 사유가 사람이 읽을 수 있게 남는지(같은 오류 반복 기록 안 함)
- MQTT 가 끊겨 있는 동안 REST 로 실제 아이디가 든 엔티티를 만들지 않는지
- 재연결 후 마지막 센서 값·수동 번호가 그대로 다시 발행되는지
"""

import asyncio
import logging
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
os.environ.setdefault("DHL_DATA_DIR", tempfile.mkdtemp(prefix="dhl_mqtt_"))

import mqtt_discovery as MD  # noqa: E402

PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


class FakeClient:
    def __init__(self):
        self.subs, self.pubs = [], []
        self.on_message = None

    def subscribe(self, topic):
        self.subs.append(topic)

    def publish(self, topic, payload, qos=0, retain=False):
        self.pubs.append((topic, payload, retain))

        class R:
            rc = 0
        return R()


class CaptureLog(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


cap = CaptureLog()
logging.getLogger("mqtt_discovery").addHandler(cap)

# ------------------------------------------------ MQTTDiscovery callbacks
print("[연결·재연결 콜백]")
m = MD.MQTTDiscovery("mqtt://core-mosquitto:1883")
check((m.broker, m.port) == ("core-mosquitto", 1883), "주소 파싱")
fc = FakeClient()
m.client = fc
m.subscribe("t/a")
check(fc.subs == [] and "t/a" in m.subscriptions, "끊긴 상태에서는 기억만")
ready = []
m.on_ready = lambda: ready.append(1)
m._on_connect(fc, None, {}, 0)
check(m.connected and fc.subs == ["t/a"] and ready == [1], "연결되면 구독 복구 + on_ready 호출")
m._on_disconnect(fc, None, 1)
check(not m.connected, "끊김 반영")
fc.subs.clear()
m.subscribe("t/b")
m._on_connect(fc, None, {}, 0)
check(sorted(fc.subs) == ["t/a", "t/b"] and ready == [1, 1], "재연결 때 모든 구독 다시 + on_ready 다시")

cap.records.clear()
m._on_connect(fc, None, {}, 5)
m._on_connect(fc, None, {}, 5)
errs = [r for r in cap.records if "연결 실패" in r]
check(not m.connected and "인증 거부" in m.last_error, "rc=5 사유")
check(len(errs) == 1 and "mqtt_username" in errs[0], "같은 오류는 한 번만 기록 + 해결 안내 포함")
m._on_connect(fc, None, {}, 4)
check("아이디 또는 비밀번호" in m.last_error, "rc=4 사유")
m._on_connect(fc, None, {}, 0)
check(m.last_error == "" and m.connected, "성공하면 오류 초기화")


class RC:
    value = 3


m._on_connect(fc, None, {}, RC())
check("사용할 수 없음" in m.last_error, "paho ReasonCode 객체도 처리")

# ------------------------------------------------ main: on_ready and fallback
print("[main 연동]")
import main as M  # noqa: E402

calls = []


async def fake_publish(**kw):
    calls.append(kw)
    return True


M.publish_sensor_mqtt = fake_publish


class Logged:
    logged_in = True


acc = M.AccountData("sampleid01", "pw")
acc.client = Logged()
acc.lotto_645 = object()
acc.manual_numbers_state = "1,2,3,auto,auto,auto"
acc.pension_manual_state = "3,123456"
acc.sensor_cache = {"lotto45_balance": {"state": 5000, "attributes": {"friendly_name": "예치금"}, "ts": 1}}
M.accounts.clear()
M.accounts["sampleid01"] = acc

mc = MD.MQTTDiscovery("mqtt://core-mosquitto:1883")
mc.client = FakeClient()
mc.connected = True
M.mqtt_client = mc


async def run_ready():
    await M._mqtt_on_ready()


asyncio.run(run_ready())
subs = mc.subscriptions
check(any(s.endswith("sampleid01_buy_auto_1/command") for s in subs), "로또 버튼 명령 구독")
check(any(s.endswith("sampleid01_buy_pension_manual/command") for s in subs), "연금 버튼 명령 구독")
check(any(s.endswith("sampleid01_manual_numbers/set") for s in subs), "수동 번호 입력 구독")
check(mc.client.on_message is M.on_button_command, "명령 처리기 연결")
check(any(c["entity_id"] == "lotto45_balance" and c["state"] == 5000 for c in calls), "마지막 센서 값 재발행")
texts = {t: p for t, p, _r in mc.client.pubs if t.endswith("/state") and "/text/" in t}
check(any(v == "1,2,3,auto,auto,auto" for v in texts.values()), "재등록 때 입력해 둔 수동 번호 유지(auto 로 덮어쓰지 않음)")
check(any(v == "3,123456" for v in texts.values()), "연금 수동 번호 유지")

# 끊긴 상태: REST 로 따로 만들지 않음
mc.connected = False
rest_called = []


class FakeSession:
    def __init__(self, *a, **k):
        rest_called.append(1)


import aiohttp  # noqa: E402

orig = aiohttp.ClientSession
aiohttp.ClientSession = FakeSession
M.config["supervisor_token"] = "x"
try:
    asyncio.run(M.publish_sensor_for_account(acc, "lotto45_sync_status", "동기화 완료", {"friendly_name": "동기화"}))
finally:
    aiohttp.ClientSession = orig
check(rest_called == [], "MQTT 끊김 중에는 REST 엔티티를 만들지 않음")
check(acc.sensor_cache["lotto45_sync_status"]["state"] == "동기화 완료", "값은 캐시에 보관(재연결 때 재발행)")


# ------------------------------------------------ v2.11.3: closed-hours snapshot, cache, masked IDs
print("[구매 불가 시간 조회·캐시·가린 아이디]")
M.accounts.clear()
a1 = M.AccountData("sampleid01", "pw")
a1.client = Logged()
a1.sensor_cache = {"lotto45_balance": {"state": 91250, "attributes": {}, "ts": 1.0},
                   "pension720_this_round": {"state": 5, "attributes": {"round_no": 344, "games": []}, "ts": 1.0}}
M.accounts["sampleid01"] = a1
M._save_sensor_cache()
txt = open(os.path.join(os.environ["DHL_DATA_DIR"], "sensor_cache.json"), encoding="utf-8").read()
check("sampleid01" not in txt and "91250" in txt, "캐시 파일에 실제 아이디 없음(해시 키)")
a1.sensor_cache = {"lotto45_balance": {"state": 100, "attributes": {}, "ts": 9.0}}  # 새로 조회된 값
n = M._load_sensor_cache()
check(n == 1 and a1.sensor_cache["lotto45_balance"]["state"] == 100, "새 값은 덮어쓰지 않음")
check(a1.sensor_cache["pension720_this_round"]["state"] == 5, "지난 구매 내역 복원")

buf = []


class _H(logging.Handler):
    def emit(self, record):
        buf.append(record.getMessage())


root = logging.getLogger()
h = _H()
root.addHandler(h)
M.install_log_alias_filter(["sampleid01", "sampleid02"])
logging.getLogger("t_mask").warning("[DASH][%s] 구매 요청 · %s", M.mask_username("sampleid01"), "sampleid02")
root.removeHandler(h)
last = buf[-1] if buf else ""
check("[DASH][Account_1]" in last and "Account_2" in last and "sa*" not in last, f"가린 아이디도 별칭으로 ({last})")

calls = []
state = {"available": False, "sleeps": 0}


async def fake_update(account, force=False):
    calls.append(force)


async def fake_prev(account):
    calls.append("prev")


async def fake_sleep(_s):
    state["sleeps"] += 1
    if state["sleeps"] >= 4:
        raise asyncio.CancelledError()


M.update_sensors_for_account = fake_update
M.update_prev_round_result_sensors_for_account = fake_prev
M.is_purchase_available_now = lambda: state["available"]
orig_sleep = M.asyncio.sleep
M.asyncio.sleep = fake_sleep
try:
    a1.closed_snapshot_done = False
    asyncio.run(M.background_tasks_for_account(a1))
finally:
    M.asyncio.sleep = orig_sleep
check(calls.count(True) == 1 and calls.count("prev") == 1, f"구매 불가 시간: 읽기 전용 조회 1번 + 지난 회차 1번 ({calls})")
check(a1.closed_snapshot_done is True, "조회 완료 표시")

calls.clear()
state["sleeps"] = 0
a1.closed_snapshot_done = False


async def fake_update_logout(account, force=False):
    calls.append(force)
    account.client.logged_in = False   # 로그인 실패 상황


M.update_sensors_for_account = fake_update_logout
M.asyncio.sleep = fake_sleep
try:
    asyncio.run(M.background_tasks_for_account(a1))
finally:
    M.asyncio.sleep = orig_sleep
check(a1.closed_snapshot_done is False and calls.count(True) >= 2, f"로그인 실패면 완료로 표시하지 않고 다음 주기에 재시도 ({calls})")
a1.client.logged_in = True

calls.clear()
state.update(available=True, sleeps=0)
a1.closed_snapshot_done = True
M.update_sensors_for_account = fake_update
M.asyncio.sleep = fake_sleep
try:
    asyncio.run(M.background_tasks_for_account(a1))
finally:
    M.asyncio.sleep = orig_sleep
check(calls and all(c is False for c in calls), f"판매 시간에는 평소 조회(강제 아님) ({calls})")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
