"""대시보드 화면 자동 점검(헤드리스 Chrome) — 휴대폰·태블릿·PC 폭에서 쓰기 편한지 검사한다.

실행: python -X utf8 test_ui_layout.py
- 실제 앱(main.py)을 가짜 계정·센서로 띄운다. 구매 함수는 스텁이라 실제 구매·외부 통신이 없다.
- Chrome 또는 zendriver 가 없으면 건너뛴다. CI 에서는 REQUIRE_UI_TEST=1 로 반드시 실행한다.
"""

import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
DATA_DIR = tempfile.mkdtemp(prefix="dhl_ui_")
os.environ["DHL_DATA_DIR"] = DATA_DIR
REQUIRE = os.environ.get("REQUIRE_UI_TEST") == "1"

PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


def skip(msg):
    if REQUIRE:
        print("UI test required but unavailable:", msg)
        sys.exit(1)
    print("SKIP:", msg)
    sys.exit(0)


try:
    import zendriver as zd
    import zendriver.cdp.emulation as cdp_emu
    import zendriver.cdp.page as cdp_page
except Exception as e:  # noqa: BLE001
    skip(f"zendriver 없음 ({e})")

import main as M  # noqa: E402
import uvicorn  # noqa: E402


# ------------------------------------------------------------------ fake app state
async def _noop_buy(*a, **k):
    raise AssertionError("구매 함수가 호출되면 안 됨")


M.execute_button_purchase = _noop_buy
M.execute_pension_purchase = _noop_buy
M.execute_pension_manual_purchase = _noop_buy
M.config["use_mqtt"] = False
M.config["supervisor_token"] = ""
M._client_host = lambda req: "172.30.32.2"
M.is_purchase_available_now = lambda: True
_draws = [{"round_no": 1251 - k, "numbers": sorted({(k * 7 + j * 11) % 45 + 1 for j in range(6)} | set())[:6], "bonus": 7}
          for k in range(100)]
_draws = [d for d in _draws if len(d["numbers"]) == 6]


async def _fake_hist():
    return _draws


async def _fake_cum():
    return {n: 150 + n for n in range(1, 46)}


M._round_history = _fake_hist
M._cumulative_stats = _fake_cum


class _Client:
    logged_in = True


async def _seed():
    M._spawn = lambda coro: coro.close()  # 시드 중 알림 작업 생략
    for i, u in enumerate(("sampleid01", "sampleid02"), start=1):
        a = M.AccountData(u, "pw")
        a.lotto_645 = object()
        a.pension = object()
        a.client = _Client()
        M.accounts[u] = a
        P = M.publish_sensor_for_account
        await P(a, "lotto45_balance", 91250, {"purchase_available": 91250})
        await P(a, "lotto45_sync_status", "정상 동기화 완료", {})
        await P(a, "lotto45_weekly_purchase_count", 3, {"weekly_limit": 5})
        if i == 1:
            for k, g in enumerate([[4, 12, 18, 25, 37, 44], [1, 9, 22, 31, 38, 45], [7, 14, 21, 28, 35, 42]], start=1):
                await P(a, f"lotto45_game_{k}", ",".join(map(str, g)),
                        {"numbers": g, "round_no": 1252, "slot": "ABC"[k - 1], "mode": "auto"})
                await P(a, f"lotto45_game_{k}_result", "미추첨", {})
            await P(a, "pension720_this_round", 2, {"round_no": 344, "games": [
                {"group": "1", "number": "214427", "result": "미추첨"}, {"group": "3", "number": "752888", "result": "미추첨"}]})
            await P(a, "lotto645_winning_numbers", "x", {"numbers": [3, 11, 19, 27, 33, 42], "bonus": 8, "round": 1251})
            await P(a, "lotto45_hot_numbers", "x", {"numbers": [3, 11, 19, 27, 33, 42, 7, 14, 21, 45]})
            await P(a, "lotto45_cold_numbers", "x", {"numbers": [1, 2, 9, 16, 23, 30, 36, 39, 40, 44]})


asyncio.run(_seed())
# 럭키 랩 카드가 게이지·수령 도우미까지 모두 그리도록 원장을 채운다(추첨 끝난 회차 + 직접 수령 당첨)
_led = [{"key": f"seed:{r}:{i}", "acct": "account_1", "kind": "buy", "game": "lotto", "amount": 1000, "round": r,
         "info": "", "month": M.FT.now_kst().strftime("%Y-%m"), "ts": 1} for r in range(1240, 1250) for i in range(5)]
_led += [{"key": "seed-win:1", "acct": "account_1", "kind": "win", "game": "lotto", "amount": 5000, "round": 1245,
          "info": "5등", "month": M.FT.now_kst().strftime("%Y-%m"), "ts": 2},
         {"key": "seed-win:2", "acct": "account_1", "kind": "win", "game": "lotto", "amount": 2_500_000_000, "round": 1248,
          "info": "1등", "month": M.FT.now_kst().strftime("%Y-%m"), "ts": 3}]
M._ledger = M.FT.Ledger(_led)
with open(os.path.join(DATA_DIR, "dashboard_settings.json"), "w", encoding="utf-8") as _f:
    json.dump({"favorites": [
        {"type": "lotto", "name": "지난주 번호", "numbers": "3,11,19,27,33,42"},
        {"type": "lotto", "name": "반자동", "numbers": "7,14,auto,auto,auto,auto"},
        {"type": "pension", "name": "", "group": 2, "digits": "571903"}], "budget": {"monthly": 30000}}, _f, ensure_ascii=False)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


PORT = _free_port()
_server = uvicorn.Server(uvicorn.Config(M.app, host="127.0.0.1", port=PORT, log_level="warning", lifespan="off"))
threading.Thread(target=_server.run, daemon=True).start()
for _ in range(100):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1)
        break
    except Exception:  # noqa: BLE001
        time.sleep(0.1)
else:
    skip("테스트 서버가 뜨지 않음")
URL = f"http://127.0.0.1:{PORT}/"

# ------------------------------------------------------------------ in-page measurements
METRICS_JS = r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !e.closest('[hidden]'); };
  const small = [], taps = [], inputs = [];
  document.querySelectorAll('body *').forEach((e) => {
    if (!vis(e)) return;
    const own = Array.from(e.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
    if (own) { const fs = parseFloat(getComputedStyle(e).fontSize); if (fs < 11) small.push((e.className || e.tagName) + ':' + fs); }
  });
  document.querySelectorAll('button, input, select, textarea, a[href]').forEach((e) => {
    if (!vis(e) || e.closest('#modal') || e.type === 'checkbox' || e.type === 'file') return;
    const r = e.getBoundingClientRect();
    if (r.height < 36) taps.push((e.className || e.tagName) + ':' + Math.round(r.height));
    if (e.matches('input:not([type=checkbox]):not([type=file]), select, textarea')) {
      const fs = parseFloat(getComputedStyle(e).fontSize); if (fs < 16) inputs.push((e.id || e.className || e.tagName) + ':' + fs);
    }
  });
  const collapsed = Array.from(document.querySelectorAll('[data-card]')).map((c) => {
    const b = c.querySelector('.card-head'), body = c.querySelector('.card-body');
    return { id: c.dataset.card, expanded: b && b.getAttribute('aria-expanded'), hidden: body ? body.hidden : null };
  });
  // 번호 공이 세로로 쌓이거나(좁게 눌림) 연금 티켓이 줄바꿈되면 표시 문제
  const squeezed = [];
  document.querySelectorAll('.main, .numlist, .hero-balls, .preview').forEach((m) => {
    if (!vis(m)) return;
    const tops = new Set(Array.from(m.querySelectorAll(':scope > .ball')).filter(vis).map((b) => Math.round(b.getBoundingClientRect().top)));
    if (tops.size > 2) squeezed.push((m.closest('[data-card]') || m).getAttribute('data-card') + ':' + tops.size + 'rows');
  });
  document.querySelectorAll('.ticket').forEach((tk) => { if (vis(tk) && tk.getBoundingClientRect().height > 44) squeezed.push('ticket:' + Math.round(tk.getBoundingClientRect().height)); });
  const header = document.querySelector('header').getBoundingClientRect().height;
  return JSON.stringify({
    w: innerWidth, overflow: document.documentElement.scrollWidth > innerWidth + 1,
    small: small.slice(0, 15), taps: taps.slice(0, 20), inputs: inputs.slice(0, 10), squeezed: squeezed.slice(0, 10),
    qnav: getComputedStyle(document.getElementById('qnav')).display,
    header: header / innerHeight, collapsed,
    broken: Array.from(document.images).filter((i) => i.complete && i.naturalWidth === 0).map((i) => i.src),
    csp: window.__csp || [], cards: document.querySelectorAll('[data-card]').length,
  });
})()
"""


async def _eval(tab, js):
    v = await tab.evaluate(js)
    return json.loads(v) if isinstance(v, str) else v


async def _wait(tab, js, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if await tab.evaluate(js):
            return True
        await asyncio.sleep(0.2)
    return False


async def run():
    # 느린 CI 기기에서는 Chrome 기동이 zendriver 기본 대기(약 2.5초)보다 오래 걸린다 → 애드온과 같은 연결 대기 + 1회 재시도
    from dh_pension_browser import browser_connect_kwargs
    browser, last_err = None, None
    for _attempt in range(2):
        try:
            browser = await zd.start(headless=True, sandbox=False, browser_args=["--disable-gpu", "--disable-dev-shm-usage"],
                                     **browser_connect_kwargs(zd))
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            await asyncio.sleep(3)
    if browser is None:
        skip(f"Chrome 을 띄울 수 없음 ({last_err})")
    try:
        sizes = [("phone-small", 360, 740, True), ("phone", 390, 844, True), ("tablet", 768, 1024, False), ("desktop", 1280, 800, False)]
        for name, w, hgt, mobile in sizes:
            print(f"[{name} {w}x{hgt}]")
            try:  # 크기마다 기본 설정에서 시작
                os.remove(os.path.join(DATA_DIR, "dashboard_prefs.json"))
            except OSError:
                pass
            tab = await browser.get("about:blank", new_tab=True)
            await tab.send(cdp_emu.set_device_metrics_override(width=w, height=hgt, device_scale_factor=1, mobile=mobile))
            await tab.send(cdp_page.add_script_to_evaluate_on_new_document(
                source="window.__csp=[];document.addEventListener('securitypolicyviolation',e=>window.__csp.push(e.violatedDirective+' '+e.blockedURI))"))
            await tab.get(URL)
            check(await _wait(tab, "document.querySelectorAll('[data-card]').length >= 8"), f"{name}: 카드 표시")
            await asyncio.sleep(0.8)
            m = await _eval(tab, METRICS_JS)
            check(not m["overflow"], f"{name}: 가로 스크롤 없음")
            check(not m["small"], f"{name}: 11px 미만 글자 없음 {m['small']}")
            check(not m["broken"], f"{name}: 깨진 이미지 없음 {m['broken']}")
            check(not m["squeezed"], f"{name}: 번호·티켓이 눌려서 세로로 쌓이지 않음 {m['squeezed']}")
            check(not m["csp"], f"{name}: CSP 위반 없음 {m['csp']}")
            lab = await _eval(tab, "JSON.stringify((() => { const c = document.querySelector('[data-card=insight]'); if (!c) return null;"
                              " const g = c.querySelector('.gauge > i'); return { luck: !!c.querySelector('.luck b'),"
                              " gauges: c.querySelectorAll('.gauge').length, visit: c.querySelectorAll('.claim.visit').length,"
                              " fill: g ? g.style.width : '', ics: Array.from(c.querySelectorAll('button')).some(b => b.textContent.indexOf('.ics') >= 0),"
                              " wide: c.scrollWidth > c.clientWidth + 1 }; })())")
            check(lab and lab["luck"] and lab["gauges"] == 2 and lab["visit"] == 1 and lab["fill"].endswith("%") and lab["ics"],
                  f"{name}: 럭키 랩 카드(운 지수·예산 게이지·수령 기한·캘린더) {lab}")
            check(lab and not lab["wide"], f"{name}: 럭키 랩 카드가 화면 폭 안에 들어감")
            defaults = {"receipt", "winning", "numstats", "stats", "auto"}
            states = {c["id"]: c for c in m["collapsed"]}
            check(all(states[i]["expanded"] == "false" and states[i]["hidden"] for i in defaults if i in states),
                  f"{name}: 자주 안 쓰는 카드는 접힌 상태")
            check(all(c["expanded"] == "true" and not c["hidden"] for c in m["collapsed"] if c["id"] not in defaults),
                  f"{name}: 나머지 카드는 펼친 상태")
            if mobile:
                check(not m["taps"], f"{name}: 터치 영역 36px 이상 {m['taps']}")
                check(not m["inputs"], f"{name}: 입력칸 16px 이상(iOS 확대 방지) {m['inputs']}")
                check(m["qnav"] == "flex", f"{name}: 빠른 이동 바 표시")
                check(m["header"] <= 0.3, f"{name}: 상단 바가 화면의 30% 이하 ({m['header']:.2f})")
            else:
                check(m["qnav"] == "none", f"{name}: PC 에서는 빠른 이동 바 숨김")

            if name == "phone":
                # 접힌 카드 펼치기 → 화면 반영 + 설정 저장
                await tab.evaluate("document.querySelector('[data-card=numstats] .card-head').click()")
                ok = await _wait(tab, "(() => { const c = document.querySelector('[data-card=numstats]');"
                                      " return c && c.querySelector('.card-head').getAttribute('aria-expanded') === 'true'"
                                      " && !c.querySelector('.card-body').hidden && document.querySelectorAll('.heat .cell').length === 45; })()")
                check(ok, "phone: 번호 통계 펼치면 히트맵 45칸 표시")
                saved = False
                for _ in range(30):
                    try:
                        with open(os.path.join(DATA_DIR, "dashboard_prefs.json"), encoding="utf-8") as f:
                            saved = "numstats" not in json.load(f).get("collapsed_cards", [])
                    except (OSError, ValueError):
                        saved = False
                    if saved:
                        break
                    await asyncio.sleep(0.2)
                check(saved, "phone: 펼친 상태가 설정에 저장됨")
                # 구매 카드의 수동 입력은 접혀 있다가 펼치면 보임
                hidden_before = await tab.evaluate("document.getElementById('lotto-manual').offsetParent === null")
                await tab.evaluate("document.querySelector('[aria-controls=fold-lotto-manual]').click()")
                shown = await _wait(tab, "document.getElementById('lotto-manual').offsetParent !== null")
                check(hidden_before and shown, "phone: 수동 번호 입력은 펼쳤을 때만 보임")
                m2 = await _eval(tab, METRICS_JS)
                check(not m2["overflow"] and not m2["taps"] and not m2["inputs"] and not m2["small"],
                      f"phone: 펼친 뒤에도 레이아웃 정상 {m2['taps']} {m2['inputs']} {m2['small']}")
            # 모든 카드·접힌 구역을 펼쳐도 화면이 깨지지 않는지(통계·용지·자동 구매·알림 설정 포함)
            await tab.evaluate("document.querySelectorAll('.card-head[aria-expanded=false]').forEach(b => b.click())")
            await asyncio.sleep(0.6)
            for _ in range(3):
                await tab.evaluate("document.querySelectorAll('.fold-btn[aria-expanded=false]').forEach(b => b.click())")
                await asyncio.sleep(0.4)
            all_open = await _wait(tab, "document.querySelectorAll('.card-head[aria-expanded=false], .fold-btn[aria-expanded=false]').length === 0")
            check(all_open, f"{name}: 모든 카드·구역 펼치기")
            m3 = await _eval(tab, METRICS_JS)
            check(not m3["overflow"] and not m3["small"] and not m3["csp"] and not m3["broken"] and not m3["squeezed"],
                  f"{name}: 전부 펼친 상태도 정상 {m3['small']} {m3['csp']} {m3['squeezed']}")
            if mobile:
                check(not m3["taps"] and not m3["inputs"], f"{name}: 전부 펼친 상태 터치·입력 크기 {m3['taps']} {m3['inputs']}")
            await tab.close()
    finally:
        try:
            await asyncio.wait_for(browser.stop(), timeout=10)
        except Exception:  # noqa: BLE001
            pass


asyncio.run(run())
_server.should_exit = True
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
