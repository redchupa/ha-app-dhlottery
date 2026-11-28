"""보안 회귀 테스트: API 보호 규칙·화면 코드 금지 패턴·재로그인 보호를 기계적으로 검사한다.

실행: python -X utf8 test_security.py
새 API 를 추가할 때 Ingress/CSRF 검사를 빠뜨리면 이 테스트가 실패한다.
"""

import ast
import asyncio
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..", "app")
sys.path.insert(0, APP)

PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


# ------------------------------------------------ 1. API routes
print("[API 보호 규칙]")
src = open(os.path.join(APP, "main.py"), encoding="utf-8").read()
tree = ast.parse(src)
PUBLIC_GET = {"/", "/health", "/accounts", "/api/ingress"}  # 별칭·상태만 내보내는 공개 경로
routes = []
for node in tree.body:
    if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
        for d in node.decorator_list:
            if (isinstance(d, ast.Call) and getattr(d.func, "attr", "") in ("get", "post", "put", "delete", "patch")
                    and getattr(d.func.value, "id", "") == "app"):
                routes.append((d.func.attr, d.args[0].value, ast.get_source_segment(src, node)))
check(len(routes) >= 15, f"라우트 수집 ({len(routes)}개)")
for method, path, body in routes:
    ingress = "_require_ingress(request)" in body
    csrf = "_require_csrf(request)" in body or "csrf_ok(DASHBOARD_CSRF_TOKEN" in body
    if method != "get":
        check(ingress and csrf, f"{method.upper()} {path}: Ingress + CSRF 필수")
    elif path not in PUBLIC_GET:
        check(ingress, f"GET {path}: Ingress 필수")
for method, path, body in routes:
    if path in PUBLIC_GET and path != "/":
        check("password" not in body and ".username" not in body.replace("aliases[username]", ""),
              f"공개 경로 {path}: 비밀번호·실제 아이디를 내보내지 않음")
check("allow_credentials=False" in src, "CORS 자격증명 비허용")

# ------------------------------------------------ 2. dashboard page
print("[대시보드 화면 코드]")
import dashboard_page as P  # noqa: E402

page = P.PAGE_TEMPLATE
script = page.split('<script nonce="__NONCE__">')[1].split("</script>")[0]
for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "setTimeout(\"", "setInterval(\""):
    check(bad not in script, f"금지 API 없음: {bad}")
check(not re.search(r"\bstyle:\s*\"", script), "인라인 style 속성 없음(CSP 차단 대상)")
html_part = page.split("<script")[0] + page.split("</script>")[-1]
check(not re.search(r"\son[a-z]+\s*=", html_part), "HTML 인라인 이벤트 속성 없음")
tags = re.findall(r"<(?:script|style)\b[^>]*>", page)
check(tags and all('nonce="__NONCE__"' in tg for tg in tags), f"모든 script/style 에 nonce ({len(tags)}개)")
check(not re.search(r"https?://(?!www\.w3\.org)", script), "외부 주소로 요청하지 않음(상대 경로만)")

csp = src[src.index("default-src 'none'"):src.index("frame-ancestors 'self'")]
check("'unsafe-inline'" not in csp and "'unsafe-eval'" not in csp, "CSP 에 unsafe-inline/unsafe-eval 없음")
check("script-src 'nonce-" in csp and "style-src 'nonce-" in csp, "CSP nonce 사용")

# ------------------------------------------------ 3. re-login guard
print("[재로그인 보호]")
import tempfile  # noqa: E402
os.environ.setdefault("DHL_DATA_DIR", tempfile.mkdtemp(prefix="dhl_sec_"))
import main as M  # noqa: E402

acc = M.AccountData("sampleid01", "pw")
M.accounts["sampleid01"] = acc
M.is_purchase_available_now = lambda: True
check(M._relogin_block_reason(acc) == ("", 0), "처음에는 허용")
M._relogin_last["sampleid01"] = time.monotonic()
r, st = M._relogin_block_reason(acc)
check(st == 429 and "초 후" in r, "60초 안 재시도 차단")
M._relogin_last.clear()
M._relogin_busy.add("sampleid01")
check(M._relogin_block_reason(acc)[1] == 409, "로그인 진행 중 차단")
M._relogin_busy.clear()
acc.last_action = {"status": "running"}
check(M._relogin_block_reason(acc)[1] == 409, "구매 진행 중 차단")
acc.last_action = None
M.is_purchase_available_now = lambda: False
check(M._relogin_block_reason(acc)[1] == 409, "점검·구매 불가 시간 차단")
M.is_purchase_available_now = lambda: True

# ------------------------------------------------ 4. text sanitizing
print("[문구 정리]")
import features as F  # noqa: E402

t = F.safe_notify_text('<img src=x onerror=alert(1)>오류\n\t메시지' + "가" * 400, 50)
check("<" not in t and ">" not in t and "\n" not in t and len(t) <= 50, "알림 문구 꺾쇠·제어문자 제거")
check("<" not in F.purchase_message("Account_1", "x", "error", "<b>실패</b>", "button")[1], "구매 알림 문구 정리")
scr = F.scrub_text("mqtt://u:p@203.0.113.9:1883 a@b.com " + "Z" * 40)
check("p@" not in scr and "203.0.113.9" not in scr and "a@b.com" not in scr and "Z" * 40 not in scr, "진단 리포트 가림")


# ------------------------------------------------ 5. real IDs never leave the add-on
print("[실제 아이디 가림]")
M.accounts.clear()
M.accounts["sampleid01"] = M.AccountData("sampleid01", "pw")
msg = M._alias_text("로그인 실패: sampleid01 / " + M.mask_username("sampleid01") + " 확인")
check("sampleid01" not in msg and "sa*" not in msg and msg.count("Account_1") == 2, f"응답·진단 문구의 아이디 → 별칭 ({msg})")
check(M._alias_text(None) is None and M._alias_text(5) == 5, "문자열 아닌 값은 그대로")
route_src = src[src.index("async def api_dashboard"):src.index("DATA_DIR = ")]
check("_alias_text(v.get(\"state\"))" in route_src and "_alias_text(account.last_action" in route_src,
      "대시보드 응답 문구에 별칭 적용")
check("FT.scrub_text(_alias_text(" in src, "진단 리포트에 별칭 적용")

# ------------------------------------------------ 6. purchase code: no blind resend after sending an order
print("[주문 재전송 금지]")
lsrc = open(os.path.join(APP, "dh_lotto_645.py"), encoding="utf-8").read()
order = lsrc[lsrc.index("execBuy.do") - 1500:lsrc.index("execBuy.do") + 2500]
check("uncertain_order_message" in order and "ClientConnectorError" in order, "로또 주문 후 실패는 재시도 안 함(연결 실패만)")
psrc = open(os.path.join(APP, "dh_pension_browser.py"), encoding="utf-8").read()
check(len(re.findall(r'"doVerify\(\)"', psrc)) == 1 and psrc.count('"doOrder()"') == 2, "연금 doVerify 1곳·doOrder 자동/수동 각 1곳")
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
