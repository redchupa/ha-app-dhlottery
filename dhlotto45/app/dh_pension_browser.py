"""
dh_pension_browser.py
연금복권720+ 자동 구매 (헤드리스 크로미움 / zendriver).

el.dhlottery.co.kr 의 구매 세션은 브라우저의 전체 JS·쿠키 핸드셰이크를 요구하므로
HTTP 클라이언트(aiohttp)로는 "로그인후 이용" 거부(E001)를 넘지 못한다. 그래서 구매 한
단계만 일회성 헤드리스 크로미움으로 처리한다. 센서·통계·조회는 기존 HTTP 경로를 그대로 쓴다.

경량화(참고: GCP e2-micro 1GB RAM 에서 동작하는 공개 구현):
- 구매 버튼을 누를 때만 크로미움을 띄우고, 끝나면 즉시 종료한다(상시 메모리 0).
- 폰트/미디어 요청을 CDP Fetch 로 차단한다(메모리·트래픽 절감).
- 최소 실행 플래그(--disable-dev-shm-usage 등)로 띄운다.

이 환경(개발 PC)에서는 dhlottery 도메인에 접근할 수 없으므로 실제 구매 검증은 배포된
애드온에서만 가능하다. 로컬에서는 모의 페이지로 자동화 로직을 단위 테스트한다
(URL·셀렉터를 생성자 인자로 주입할 수 있게 설계).
"""

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable, Optional

_LOGGER = logging.getLogger(__name__)

# 모바일 전용 구매 페이지: iframe 없이 전역 JS 함수만으로 동작해 자동화가 단순하다.
DEFAULT_LOGIN_URL = "https://www.dhlottery.co.kr/login"
DEFAULT_GAME_URL = "https://el.dhlottery.co.kr/game_mobile/pension720/game.jsp"

# 로그인 폼 셀렉터(여러 후보를 순서대로 시도해 사이트 변경에 견디게 함).
# dhlottery 로그인 페이지의 평문 아이디 필드는 inpUserId(HTTP 로그인도 동일 필드명 사용).
# 비밀번호 표시 필드명은 확실치 않아 포괄 셀렉터(type=password)까지 둔다.
ID_SELECTORS = (
    "#inpUserId",
    "input[name='inpUserId']",
    "#userId",
    "input[name='userId']",
)
PW_SELECTORS = (
    "#inpUserPswd",
    "#inpUserPswdEncn",
    "input[type='password']",
    "input[name='password']",
)
LOGIN_BTN_SELECTORS = (
    "#btnLogin",
    ".btn_common.lrg.blu",
    "a[onclick*='login']",
    "input[type='submit']",
    "button[type='submit']",
)

PENSION_PRICE = 1000  # 1매 1,000원
MAX_COUNT = 5

# 동행복권 로그인 페이지의 비밀번호 입력란은 maxlength="20" 이다. 브라우저 입력은
# 20자에서 잘려 로그인이 실패하므로(HTTP 로그인=로또는 전체를 보내 성공) 미리 막는다.
LOGIN_PW_MAXLEN = 20

# 로그인 버튼(login())은 RSA 공개키(rsa.n)가 AJAX 로 설정된 뒤에만 동작한다.
# 키가 없으면 rsa.encrypt() 가 TypeError 로 죽고 폼이 조용히 제출되지 않는다.
RSA_READY_JS = "(() => typeof rsa !== 'undefined' && !!rsa && rsa.n != null)()"


def validate_login_credentials(username, password):
    """브라우저 로그인 전 계정 값 검사(순수 함수). 문제가 있으면 DhPensionBrowserError.

    로그인 시도 자체를 하지 않으므로 실패 횟수(5회 잠금)를 소모하지 않는다.
    """
    if not str(username or "").strip():
        raise DhPensionBrowserError("로그인 실패: 아이디가 비어 있습니다")
    pw = password or ""
    if not pw:
        raise DhPensionBrowserError("로그인 실패: 비밀번호가 비어 있습니다")
    if len(pw) > LOGIN_PW_MAXLEN:
        raise DhPensionBrowserError(
            f"로그인 실패: 비밀번호가 {len(pw)}자입니다. 동행복권 웹 로그인 입력란은 "
            f"최대 {LOGIN_PW_MAXLEN}자까지만 받아 연금복권(브라우저 로그인)은 로그인할 수 "
            f"없습니다(로또는 다른 방식이라 동작). 동행복권 사이트에서 비밀번호를 "
            f"{LOGIN_PW_MAXLEN}자 이하로 변경한 뒤 애드온 설정도 바꿔 주세요."
        )


def is_login_success_url(url):
    """로그인 버튼 클릭 후 URL 로 성공 여부 판정(순수 함수).

    성공 시 /login/securityLoginCheck.do → /login/loginSuccess.do → /main 순으로 이동한다.
    loginSuccess.do 는 /login 경로 아래라 그 시점에도 성공으로 본다.
    비밀번호 만료 안내(/mbrsrvc/ExpryPswdNoti)도 인증은 성공한 상태다.
    """
    u = url or ""
    if not u or u.startswith("about:"):
        return False
    if "loginSuccess.do" in u or "ExpryPswdNoti" in u:
        return True
    return "/login" not in u


def validate_manual_selection(group, digits):
    """수동 선택값 유효성 검사 → (group:int, digits:str) 로 정규화.

    순수 함수(브라우저 불필요)라 단위 테스트가 쉽다. 잘못된 값이면
    DhPensionBrowserError 를 던진다.
    """
    try:
        # str 경유 정규화 → "1"·1 은 허용, 1.5·"1.5"·None·"x" 는 거부.
        g = int(str(group).strip())
    except (TypeError, ValueError):
        raise DhPensionBrowserError(
            f"조는 1~{MAX_COUNT} 정수여야 합니다 (입력: {group!r})"
        )
    if g < 1 or g > MAX_COUNT:
        raise DhPensionBrowserError(f"조는 1~{MAX_COUNT} 사이여야 합니다 (입력: {g})")
    d = str(digits).strip()
    if not (len(d) == 6 and d.isdigit()):
        raise DhPensionBrowserError(
            f"번호는 6자리 숫자여야 합니다 (입력: {digits!r})"
        )
    return g, d


def classify_purchase_failure(text):
    """doOrder 실패 시 화면/다이얼로그 텍스트로 사유를 분류 → (category, message, uncertain).

    여기서 잡는 사유들은 모두 '서버가 구매 전에 거부'한 신호라 **확정 미구매**
    (uncertain=False) 다. 분류 불가(unknown)일 때만 uncertain=True 로 올려 이중지출을
    막는다(서버에선 구매됐는데 UI만 못 받은 경우일 수 있으므로). 순수 함수 → 단위테스트.

    category: balance|soldout|limit|closed|empty|unknown
    """
    t = (text or "").strip()
    if any(k in t for k in ("예치금", "잔액 부족", "잔액이 부족", "충전해")):
        return (
            "balance",
            "예치금(잔액)이 부족해 구매되지 않았습니다. 예치금을 충전한 뒤 재시도하세요.",
            False,
        )
    if any(k in t for k in ("이미 판매", "판매가 완료", "판매완료", "판매 완료")):
        return (
            "soldout",
            "이미 판매 완료된 번호라 구매되지 않았습니다(다른 번호를 선택하세요).",
            False,
        )
    if any(k in t for k in ("한도", "구매제한", "1일 구매", "구입한도")):
        return (
            "limit",
            "구매 한도를 초과해 구매되지 않았습니다(연금복권 1회 10만원·1일 15만원 제한).",
            False,
        )
    if any(
        k in t
        for k in (
            "판매시간",
            "판매 시간",
            "마감",
            "판매종료",
            "판매가 종료",
            "시간이 아닙",
            "구매 가능한 시간",
            "점검",
            "중지",
        )
    ):
        return (
            "closed",
            "지금은 구매 가능 시간이 아닙니다(판매 마감·시간외·점검).",
            False,
        )
    if "선택" in t:  # "구매 번호를 선택해 주세요" = 장바구니가 비어 미구매
        return (
            "empty",
            "번호가 등록되지 않아 구매되지 않았습니다(매진·입력 문제 가능).",
            False,
        )
    return (
        "unknown",
        "구매 확정 응답을 확인하지 못했습니다. 실제로 구매됐을 수 있으니 "
        "동행복권 구매내역을 확인한 뒤 재시도하세요.",
        True,
    )


class DhPensionBrowserError(Exception):
    """연금복권 브라우저 구매 중 발생한 오류.

    uncertain=True 면 doOrder(구매 확정) 이후 결과 확인에 실패한 상태다.
    서버에서는 구매가 됐는데 UI 응답만 못 받았을 수 있으므로, 재시도 전에
    반드시 구매내역을 확인해야 한다(이중 지출 방지).
    """

    def __init__(self, message: str, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


class DhPensionBrowser:
    """헤드리스 크로미움으로 연금복권720+ 를 자동 구매한다."""

    def __init__(
        self,
        username: str,
        password: str,
        *,
        executable_path: Optional[str] = None,
        login_url: str = DEFAULT_LOGIN_URL,
        game_url: str = DEFAULT_GAME_URL,
        round_provider: Optional[Callable[[], Awaitable[int]]] = None,
        headless: bool = True,
        block_resources: bool = True,
        nav_timeout: float = 30.0,
        logger: Optional[logging.Logger] = None,
    ):
        self.username = username
        self.password = password
        self.executable_path = executable_path
        self.login_url = login_url
        self.game_url = game_url
        self.round_provider = round_provider
        self.headless = headless
        self.block_resources = block_resources
        self.nav_timeout = nav_timeout
        self._log = logger or _LOGGER
        self._lock = asyncio.Lock()  # 같은 계정 구매 직렬화(이중 지출 방지)

    # ------------------------------------------------------------------ public

    async def async_buy_auto(self, count: int = 1) -> dict:
        """연금복권 N매를 자동(조 지정 + 번호 자동)으로 구매한다.

        반환: {"round", "count", "amount", "numbers", "tickets"}
        실패 시 DhPensionBrowserError 발생.
        """
        if count < 1 or count > MAX_COUNT:
            raise DhPensionBrowserError(
                f"구매 매수는 1~{MAX_COUNT} 사이여야 합니다 (요청: {count})"
            )
        # 같은 계정에서 구매가 동시에 겹치지 않도록 직렬화
        async with self._lock:
            return await self._do_buy(count)

    async def async_buy_manual(self, group, digits) -> dict:
        """연금복권 1매를 수동(조 + 6자리 번호 지정)으로 구매한다.

        group: 조 1~5, digits: 6자리 숫자 문자열(예: '123456').
        핵심 안전장치: 팝업에 표시된 번호가 요청과 **정확히 일치**할 때만 구매를
        확정한다. 입력 UI 추정이 틀려 엉뚱한 번호가 잡히면 지출 없이 중단한다.
        매진/중복 번호면 doVerify 단계(구매 전)에서 감지해 중단한다.
        반환 구조는 async_buy_auto 와 동일(count=1).
        """
        g, d = validate_manual_selection(group, digits)
        async with self._lock:
            return await self._do_buy_manual(g, d)

    async def async_diagnose_manual(self, group=None, digits=None) -> dict:
        """수동 구매 UI 구조 진단. 구매(doOrder)는 하지 않으므로 안전(지출 0원).

        group+digits 를 주면 팝업 열기 → 조 선택 → 6자리 입력 → doVerify 까지 한 뒤
        그 시점 상태(표시/히든 번호·saleTicket·보이는 모달/팝업·다이얼로그·body 텍스트)를
        덤프한다. 매진 번호가 어떻게 거부되는지(매진 모달·장바구니 미등록) 파악용.
        group+digits 없으면 팝업만 열고 구조 덤프. 반환: {"dump", "stage"}.
        """
        if group is not None and digits is not None:
            group, digits = validate_manual_selection(group, digits)
        async with self._lock:
            return await self._do_diagnose(group, digits)

    # --------------------------------------------------------------- lifecycle

    async def _session(self, work):
        """브라우저 기동 → 핸들러 설치 → 로그인 → work(tab) → 종료(공용 수명주기).

        자동구매·수동구매·진단이 모두 이 경로를 공유한다. work(tab) 의 반환값을
        그대로 돌려준다.
        """
        # 브라우저를 띄우기 전에 계정 값부터 검사(로그인 실패 횟수 소모 방지)
        validate_login_credentials(self.username, self.password)
        try:
            import zendriver as zd  # 지연 import: 미설치 시 애드온 전체가 죽지 않도록
            import zendriver.cdp.fetch as cdp_fetch
            import zendriver.cdp.network as cdp_network
            import zendriver.cdp.page as cdp_page
        except Exception as e:  # noqa: BLE001
            raise DhPensionBrowserError(
                "zendriver(헤드리스 브라우저) 모듈을 불러올 수 없습니다. "
                f"애드온 이미지에 chromium/zendriver 설치 여부를 확인하세요: {e}"
            ) from e

        browser_args = [
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--renderer-process-limit=1",
            "--mute-audio",
        ]

        browser = None
        self._dialog_msgs = []  # 이번 세션에서 뜬 JS 다이얼로그 메시지(실패 사유 힌트)
        t0 = time.monotonic()
        try:
            self._log.info(
                f"[PENSION-BR] 브라우저 기동 (headless={self.headless}, "
                f"exe={self.executable_path or 'auto'})"
            )
            browser = await zd.start(
                headless=self.headless,
                sandbox=False,  # Docker/root 환경 → --no-sandbox
                browser_executable_path=self.executable_path,
                browser_args=browser_args,
            )
            tab = await browser.get("about:blank")

            await self._install_dialog_autoaccept(tab, cdp_page)
            if self.block_resources:
                await self._install_resource_blocking(
                    tab, cdp_fetch, cdp_network
                )

            await self._login(tab)
            return await work(tab)
        except DhPensionBrowserError:
            raise
        except Exception as e:  # noqa: BLE001
            raise DhPensionBrowserError(f"연금복권 작업 실패: {e}") from e
        finally:
            if browser is not None:
                # 멈춘 브라우저에서 stop() 이 영원히 매달리지 않도록 10초 제한.
                try:
                    await asyncio.wait_for(browser.stop(), timeout=10)
                except Exception:  # noqa: BLE001
                    pass
            self._log.debug(
                f"[PENSION-BR] 세션 종료 ({time.monotonic() - t0:.1f}s)"
            )

    async def _do_buy(self, count: int) -> dict:
        async def work(tab):
            t0 = time.monotonic()
            tickets = await self._purchase(tab, count)
            round_no = await self._resolve_round()
            amount = count * PENSION_PRICE
            numbers = ", ".join(
                f"{t['group']}조 {t['numbers']}" for t in tickets
            )
            self._log.info(
                f"[PENSION-BR] 자동구매 완료: {len(tickets)}매, {amount}원, "
                f"[{numbers}] ({time.monotonic() - t0:.1f}s)"
            )
            return {
                "round": round_no,
                "count": len(tickets),
                "amount": amount,
                "numbers": numbers,
                "tickets": tickets,
            }

        return await self._session(work)

    async def _do_buy_manual(self, group: int, digits: str) -> dict:
        async def work(tab):
            t0 = time.monotonic()
            ticket = await self._purchase_manual(tab, group, digits)
            round_no = await self._resolve_round()
            amount = PENSION_PRICE
            numbers = f"{ticket['group']}조 {ticket['numbers']}"
            self._log.info(
                f"[PENSION-BR] 수동구매 완료: {numbers}, {amount}원 "
                f"({time.monotonic() - t0:.1f}s)"
            )
            return {
                "round": round_no,
                "count": 1,
                "amount": amount,
                "numbers": numbers,
                "tickets": [ticket],
            }

        return await self._session(work)

    async def _do_diagnose(self, group=None, digits=None) -> dict:
        async def work(tab):
            await tab.get(self.game_url)
            ready = await self._wait_js(
                tab,
                "(() => typeof selNumberPopup === 'function')()",
                timeout=self.nav_timeout,
            )
            if not ready:
                href = await self._safe_eval(tab, "location.href") or ""
                raise DhPensionBrowserError(
                    f"구매 페이지 로딩 실패(selNumberPopup 미로드). url={href}"
                )
            await self._safe_eval(tab, "selNumberPopup()")
            await asyncio.sleep(0.8)
            stage = "popup_opened"
            if group and digits:
                # 조 선택
                await self._safe_eval(
                    tab,
                    '(() => { var l = document.querySelector('
                    f"'label[for=\"group_sel{group}\"]'"
                    '); if (l) { l.click(); return true; } '
                    'var r = document.getElementById('
                    f"'group_sel{group}'"
                    '); if (r) { r.checked = true; '
                    "r.dispatchEvent(new Event('change', {bubbles: true})); "
                    'return true; } return false; })()',
                )
                await asyncio.sleep(0.2)
                observed = await self._set_manual_digits(tab, digits)
                dialogs_before = len(self._dialog_msgs)
                for _ in range(3):
                    await self._safe_eval(tab, "doVerify()")
                    if await self._wait_ajax_idle(tab, timeout=15.0):
                        break
                await asyncio.sleep(0.8)
                new_dialogs = [m for m in self._dialog_msgs[dialogs_before:] if m]
                stage = (
                    f"entered_verified req={group}조{digits} observed={observed!r} "
                    f"verify_dialogs={new_dialogs}"
                )
            dump = await self._diag_dump(tab)
            self._log.info(f"[PENSION-BR][DIAG] stage={stage} dump={dump}")
            return {"dump": dump, "stage": stage}

        return await self._session(work)

    async def _diag_dump(self, tab) -> str:
        """현재 화면 상태를 폭넓게 덤프: 표시/히든 번호·saleTicket·보이는 모달/팝업·body."""
        js = r"""
        (() => {
          const selDisplay = Array.from(document.querySelectorAll('.win720_num .num_list .numdgroup'))
            .map(s => (s.innerText || '').replace(/[^0-9]/g, '')).join('');
          let hiddenNum = '';
          for (let i = 1; i <= 6; i++) { const el = document.getElementById('num' + i); if (el) hiddenNum += (el.value || ''); }
          const saleTicket = Array.from(document.querySelectorAll('.saleTicket li'))
            .map(li => (li.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 80)).slice(0, 20);
          const visiblePopups = Array.from(document.querySelectorAll('[class*="popup"],[id*="popup"],.modal,[class*="layer"],[class*="alert"]'))
            .filter(e => e.offsetParent !== null)
            .map(e => ({id: e.id, cls: e.className, txt: (e.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 500)}))
            .slice(0, 12);
          const bodyText = (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 2500);
          return JSON.stringify({selDisplay, hiddenNum, saleTicket, visiblePopups, bodyText});
        })()
        """
        res = await self._safe_eval(tab, js)
        if isinstance(res, str):
            return res[:9000]
        return str(res)[:9000]

    # ----------------------------------------------------------------- helpers

    async def _install_dialog_autoaccept(self, tab, cdp_page) -> None:
        """alert/confirm 다이얼로그를 자동 수락(doOrder 확인창, 로그인 실패 알림 등)."""
        try:
            async def _on_dialog(event):
                try:
                    self._dialog_msgs.append(getattr(event, "message", "") or "")
                except Exception:  # noqa: BLE001
                    pass
                try:
                    await tab.send(
                        cdp_page.handle_java_script_dialog(accept=True)
                    )
                except Exception:  # noqa: BLE001
                    pass

            tab.add_handler(cdp_page.JavascriptDialogOpening, _on_dialog)
            await tab.send(cdp_page.enable())
        except Exception as e:  # noqa: BLE001
            self._log.warning(f"[PENSION-BR] 다이얼로그 핸들러 설치 실패(계속): {e}")

    async def _install_resource_blocking(
        self, tab, cdp_fetch, cdp_network
    ) -> None:
        """폰트/미디어 요청만 가로채서 차단(경량화). 그 외 요청은 영향 없음."""
        try:
            RT = cdp_network.ResourceType
            blocked = {RT.FONT, RT.MEDIA}

            async def _on_paused(event):
                try:
                    if event.resource_type in blocked:
                        await tab.send(
                            cdp_fetch.fail_request(
                                event.request_id,
                                cdp_network.ErrorReason.BLOCKED_BY_CLIENT,
                            )
                        )
                    else:
                        await tab.send(
                            cdp_fetch.continue_request(event.request_id)
                        )
                except Exception:  # noqa: BLE001
                    pass

            patterns = [
                cdp_fetch.RequestPattern(resource_type=RT.FONT),
                cdp_fetch.RequestPattern(resource_type=RT.MEDIA),
            ]
            tab.add_handler(cdp_fetch.RequestPaused, _on_paused)
            await tab.send(cdp_fetch.enable(patterns=patterns))
            self._log.info("[PENSION-BR] 리소스 차단 활성(font/media)")
        except Exception as e:  # noqa: BLE001
            self._log.warning(f"[PENSION-BR] 리소스 차단 설치 실패(계속): {e}")

    async def _login(self, tab) -> None:
        self._log.info("[PENSION-BR] 로그인 페이지 이동")
        t0 = time.monotonic()
        await tab.get(self.login_url)

        # 폼이 렌더될 때까지 대기(페이지 로딩/late JS 대응). query_selector 는
        # 즉시 조회라 대기 없이 쓰면 폼 렌더 전에 None 이 난다.
        id_el = await self._wait_first(tab, ID_SELECTORS, self.nav_timeout)
        if id_el is None:
            diag = await self._page_diag(tab)
            raise DhPensionBrowserError(
                f"로그인 입력란(아이디)을 찾지 못했습니다 (페이지 구조 변경 가능). {diag}"
            )
        pw_el = await self._wait_first(tab, PW_SELECTORS, 5.0)
        if pw_el is None:
            diag = await self._page_diag(tab)
            raise DhPensionBrowserError(
                f"로그인 입력란(비밀번호)을 찾지 못했습니다. {diag}"
            )

        # RSA 공개키가 준비되기 전에 클릭하면 login() 이 조용히 실패한다(느린 기기·망).
        await self._ensure_rsa_ready(tab)

        # 아이디 저장 쿠키 등으로 미리 채워진 값이 있으면 뒤에 덧붙지 않도록 비운다.
        await self._safe_eval(
            tab,
            "(() => { document.querySelectorAll(\"#inpUserId, input[type='password']\")"
            ".forEach(e => { e.value = ''; }); return true; })()",
        )
        await id_el.send_keys(self.username)
        await pw_el.send_keys(self.password)

        # 입력값이 실제로 들어갔는지 확인(키 이벤트 누락·maxlength 잘림 감지).
        # JS value.length 는 UTF-16 단위라 같은 기준으로 비교한다.
        typed = await self._safe_eval(
            tab,
            "(() => { const i = document.querySelector('#inpUserId'); "
            "const p = document.querySelector('#inpUserPswdEncn') || "
            "document.querySelector(\"input[type='password']\"); "
            "return JSON.stringify({id: i ? i.value.length : -1, "
            "pw: p ? p.value.length : -1}); })()",
        )
        try:
            lens = json.loads(typed) if isinstance(typed, str) else {}
        except ValueError:
            lens = {}
        exp_id = len(self.username.encode("utf-16-le")) // 2
        exp_pw = len(self.password.encode("utf-16-le")) // 2
        got_id = lens.get("id", -1) if isinstance(lens, dict) else -1
        got_pw = lens.get("pw", -1) if isinstance(lens, dict) else -1
        # -1 = 필드를 못 찾음(사이트 구조 변경) → 이 검사만 건너뛰고 기존 흐름 유지
        if (got_id >= 0 and got_id != exp_id) or (got_pw >= 0 and got_pw != exp_pw):
            raise DhPensionBrowserError(
                "로그인 실패: 입력란에 아이디/비밀번호가 정상 입력되지 않았습니다 "
                f"(입력된 길이 id={got_id}/{exp_id}, pw={got_pw}/{exp_pw}). "
                "아이디는 영문·숫자만 허용되고, 비밀번호는 20자 이하여야 합니다."
            )

        btn = await self._wait_first(tab, LOGIN_BTN_SELECTORS, 5.0)
        if btn is None:
            raise DhPensionBrowserError("로그인 버튼을 찾지 못했습니다")
        await btn.click()

        # 로그인 성공 시 /login 을 벗어나거나 loginSuccess.do 에 도달한다
        # (실패 시 오류 안내와 함께 /login 에 머무름). 느린 기기를 고려해 넉넉히 대기.
        deadline = time.monotonic() + max(30.0, self.nav_timeout)
        ok = False
        while time.monotonic() < deadline:
            href = await self._safe_eval(tab, "location.href") or ""
            if is_login_success_url(href):
                ok = True
                break
            await asyncio.sleep(0.3)
        if not ok:
            reason = await self._login_failure_reason(tab)
            raise DhPensionBrowserError(
                "로그인 실패: 아이디/비밀번호 또는 추가 인증(캡차)을 확인하세요. "
                f"{reason}"
            )
        self._log.info(
            f"[PENSION-BR] 로그인 성공 ({time.monotonic() - t0:.1f}s)"
        )

    async def _ensure_rsa_ready(self, tab) -> None:
        """로그인 페이지의 RSA 공개키(rsa.n) 설정 완료를 기다린다.

        10초 안에 안 되면 페이지의 selectRsaModulus() 를 한 번 더 호출하고 다시 기다린다.
        """
        if await self._wait_js(tab, RSA_READY_JS, timeout=10.0):
            return
        self._log.warning("[PENSION-BR] RSA 공개키 미준비 → selectRsaModulus() 재요청")
        await self._safe_eval(
            tab,
            "(() => { if (typeof selectRsaModulus === 'function') "
            "{ selectRsaModulus(); return true; } return false; })()",
        )
        if await self._wait_js(tab, RSA_READY_JS, timeout=max(15.0, self.nav_timeout)):
            return
        diag = await self._page_diag(tab)
        raise DhPensionBrowserError(
            "로그인 실패: 로그인 보안키(RSA)를 받지 못했습니다. 네트워크가 느리거나 "
            f"동행복권 사이트 응답이 지연되고 있습니다. 잠시 후 재시도하세요. {diag}"
        )

    async def _login_failure_reason(self, tab) -> str:
        """로그인 실패 시 사이트가 보여준 사유(알림 모달·서버 오류문구)와 URL 을 수집."""
        js = r"""
        (() => {
          let serverMsg = '';
          const m = (document.documentElement.innerHTML || '')
            .match(/const\s+errorMessage\s*=\s*'([^']*)'/);
          if (m) serverMsg = m[1];
          const modals = Array.from(document.querySelectorAll(
              '[class*="alert"],[class*="modal"],[class*="popup"],[class*="layer"],[role="dialog"]'))
            .filter(e => e.offsetParent !== null)
            .map(e => (e.innerText || '').replace(/\s+/g, ' ').trim())
            .filter(t => t && t.length < 300);
          return JSON.stringify({url: location.href, serverMsg, modals: modals.slice(0, 3)});
        })()
        """
        info = await self._safe_eval(tab, js)
        dialogs = [m for m in getattr(self, "_dialog_msgs", []) if m][-3:]
        reason = f"사이트응답={info}"
        if dialogs:
            reason += f" 알림={dialogs}"
        self._log.warning(f"[PENSION-BR] 로그인 실패 상세: {reason}")
        return reason

    async def _purchase(self, tab, count: int) -> list:
        self._log.info(f"[PENSION-BR] 구매 페이지 이동: {self.game_url}")
        await tab.get(self.game_url)

        # 모바일 구매 페이지 핵심 함수 로드 대기
        ready = await self._wait_js(
            tab,
            "(() => typeof selNumberPopup === 'function')()",
            timeout=self.nav_timeout,
        )
        if not ready:
            # 로그인 세션이 넘어오지 않아 로그인 페이지로 튕긴 경우 포함
            href = await self._safe_eval(tab, "location.href") or ""
            if "login" in href:
                raise DhPensionBrowserError(
                    "구매 페이지에서 로그인 세션이 유지되지 않았습니다"
                )
            raise DhPensionBrowserError(
                "구매 페이지 로딩 실패(selNumberPopup 미로드)"
            )

        for idx in range(count):
            jo = (idx % MAX_COUNT) + 1
            await self._pick_one_line(tab, jo)
            self._log.info(f"[PENSION-BR] {idx + 1}/{count}매 선택 완료(조{jo})")

        # doOrder 전 예치금 확인(부족하면 지출 없이 중단).
        await self._ensure_balance(tab, count * PENSION_PRICE)

        # 구매 확정(확인 다이얼로그는 자동 수락). 여기가 "돌이킬 수 없는" 시작점.
        dialogs_before = len(self._dialog_msgs)
        self._log.info("[PENSION-BR] 구매 확정 요청(doOrder)")
        await self._safe_eval(tab, "doOrder()")

        # 티켓 렌더 대기 + 실패 시 사유 분류(예치금·한도·시간·매진 등 → 확정 미구매,
        # 분류 불가만 불확실 처리로 이중지출 방지).
        await self._confirm_order(tab, count, dialogs_before)

        tickets = await self._extract_tickets(tab)
        if len(tickets) < count:
            raise DhPensionBrowserError(
                f"구매는 되었으나 티켓 파싱 실패(기대 {count}매, 추출 {len(tickets)}매)"
            )
        return tickets[:count]

    async def _pick_one_line(self, tab, jo: int) -> None:
        """한 줄(한 조) 자동 선택: 팝업 열기 → 조 선택 → 자동번호 → 선택완료."""
        await self._safe_eval(tab, "selNumberPopup()")
        await asyncio.sleep(0.4)

        # 조 선택: 물리 클릭(Element.click)은 숨김/미렌더 요소의 좌표를 못 구해
        # "could not find position" 으로 실패한다(5매 구매 실패 원인). 페이지 내 JS
        # 클릭으로 수행(숨김 요소에도 동작)하고, 실패해도 doAuto 가 조를 자동 배정하므로
        # 치명적이지 않다.
        await self._safe_eval(
            tab,
            '(() => { var l = document.querySelector('
            f"'label[for=\"group_sel{jo}\"]'"
            '); if (l) { l.click(); return true; } '
            'var r = document.getElementById('
            f"'group_sel{jo}'"
            '); if (r) { r.checked = true; '
            "r.dispatchEvent(new Event('change', {bubbles: true})); return true; } "
            'return false; })()',
        )
        await asyncio.sleep(0.2)

        await self._safe_eval(tab, "doAuto()")
        await asyncio.sleep(0.5)

        # doVerify() AJAX 지연 대비: 최대 3회 재요청, 매번 로딩 사라짐 대기
        verified = False
        for attempt in range(1, 4):
            await self._safe_eval(tab, "doVerify()")
            if await self._wait_ajax_idle(tab, timeout=15.0):
                verified = True
                break
            self._log.warning(
                f"[PENSION-BR] 조{jo} doVerify 응답 지연({attempt}/3) 재요청"
            )
        if not verified:
            raise DhPensionBrowserError(
                f"조{jo} 번호확정(doVerify) 응답 없음 — 서버 지연/차단 의심"
            )
        await asyncio.sleep(0.2)

    # ------------------------------------------------------- manual purchase

    async def _purchase_manual(self, tab, group: int, digits: str) -> dict:
        """조 + 6자리 수동 구매(1매). 번호가 화면에 정확히 잡힐 때만 확정."""
        self._log.info(
            f"[PENSION-BR] 수동 구매 페이지 이동: {self.game_url} "
            f"(요청 {group}조 {digits})"
        )
        await tab.get(self.game_url)
        ready = await self._wait_js(
            tab,
            "(() => typeof selNumberPopup === 'function')()",
            timeout=self.nav_timeout,
        )
        if not ready:
            href = await self._safe_eval(tab, "location.href") or ""
            if "login" in href:
                raise DhPensionBrowserError(
                    "구매 페이지에서 로그인 세션이 유지되지 않았습니다"
                )
            raise DhPensionBrowserError("구매 페이지 로딩 실패(selNumberPopup 미로드)")

        confirmed = await self._pick_one_line_manual(tab, group, digits)
        if not confirmed:
            # 입력 UI 추정이 틀려 번호가 화면에 안 잡힌 상태 → 지출 없이 중단하고,
            # 팝업 구조를 함께 실어 보정에 쓴다.
            dump = await self._popup_dump(tab)
            raise DhPensionBrowserError(
                f"수동 번호({group}조 {digits})를 화면에서 설정/확인하지 못해 "
                f"구매를 중단했습니다(지출 없음). 수동입력 UI 보정용 진단: {dump}"
            )

        # doOrder 전 예치금 확인(부족하면 지출 없이 중단).
        await self._ensure_balance(tab, PENSION_PRICE)

        # 여기부터 돌이킬 수 없음(doOrder).
        dialogs_before = len(self._dialog_msgs)
        self._log.info(
            f"[PENSION-BR] 수동 구매 확정 요청(doOrder) {group}조 {digits}"
        )
        await self._safe_eval(tab, "doOrder()")

        # 티켓 렌더 대기 + 실패 사유 분류(예치금·한도·시간·매진·빈장바구니 → 확정
        # 미구매, 분류 불가만 불확실 처리).
        await self._confirm_order(tab, 1, dialogs_before)

        tickets = await self._extract_tickets(tab)
        match = next(
            (t for t in tickets if t["group"] == group and t["numbers"] == digits),
            None,
        )
        if match is None:
            # 구매는 확정됐는데 목록에서 요청 번호를 못 찾음 → 확인 요망(이중지출 방지).
            raise DhPensionBrowserError(
                f"구매 확정 후 번호 확인 실패(요청 {group}조 {digits}, 추출 "
                f"{[(t['group'], t['numbers']) for t in tickets]}). "
                "동행복권 구매내역을 확인하세요.",
                uncertain=True,
            )
        return match

    async def _pick_one_line_manual(self, tab, group: int, digits: str) -> bool:
        """팝업 열기 → 조 선택 → 6자리 수동 입력 → 표시 확인 → 번호확정.

        반환 True = '요청 번호가 화면에 정확히 잡히고 확정(doVerify)까지 성공'
        (= doOrder 해도 안전). 화면 번호가 요청과 다르면 False(중단).
        매진/중복·확정 실패는 예외.
        """
        await self._safe_eval(tab, "selNumberPopup()")
        await asyncio.sleep(0.5)

        # 조 선택(자동 경로와 동일한 JS 클릭).
        await self._safe_eval(
            tab,
            '(() => { var l = document.querySelector('
            f"'label[for=\"group_sel{group}\"]'"
            '); if (l) { l.click(); return true; } '
            'var r = document.getElementById('
            f"'group_sel{group}'"
            '); if (r) { r.checked = true; '
            "r.dispatchEvent(new Event('change', {bubbles: true})); return true; } "
            'return false; })()',
        )
        await asyncio.sleep(0.2)

        # 6자리 수동 입력 후, 팝업에 표시된 현재 번호를 읽어온다.
        observed = await self._set_manual_digits(tab, digits)
        if observed != digits:
            self._log.warning(
                f"[PENSION-BR] 수동 입력 확인 실패: 요청 {digits}, 관측 {observed!r}"
            )
            return False

        # 번호확정(doVerify): 매진/중복이면 서버가 알림으로 거부.
        dialogs_before = len(self._dialog_msgs)
        verified = False
        for attempt in range(1, 4):
            await self._safe_eval(tab, "doVerify()")
            if await self._wait_ajax_idle(tab, timeout=15.0):
                verified = True
                break
            self._log.warning(
                f"[PENSION-BR] {group}조 doVerify 응답 지연({attempt}/3) 재요청"
            )
        await asyncio.sleep(0.5)

        # 매진/중복 거부는 JS 다이얼로그가 아니라 '페이지 내 모달'(선택번호 조회 결과:
        # "이미 판매가 완료되었습니다" + 추천번호)로 뜬다(진단으로 확인). DOM을 우선
        # 확인하고, 보조로 JS 다이얼로그도 본다. 둘 다 doOrder(지출) 전이라 안전.
        soldout_dom, alts = await self._check_soldout(tab)
        new_dialogs = [m for m in self._dialog_msgs[dialogs_before:] if m]
        dlg_soldout = next(
            (
                m
                for m in new_dialogs
                if any(k in m for k in ("판매", "중복", "불가", "이미", "선택할"))
            ),
            None,
        )
        if soldout_dom or dlg_soldout:
            if alts:
                hint = f" 추천번호: {alts}"
            elif dlg_soldout:
                hint = f" ({dlg_soldout[:80]})"
            else:
                hint = ""
            raise DhPensionBrowserError(
                f"{group}조 {digits}는 이미 판매 완료된 번호라 구매할 수 없습니다."
                + hint
            )
        if not verified:
            raise DhPensionBrowserError(
                f"{group}조 {digits} 번호확정(doVerify) 응답 없음 — 서버 지연/차단 의심"
            )
        await asyncio.sleep(0.2)
        return True

    async def _check_soldout(self, tab):
        """doVerify 후 '이미 판매 완료' 모달이 떴는지 DOM에서 확인 → (bool, 추천번호문자열).

        매진 안내는 JS 다이얼로그가 아니라 보이는 모달(.popup_section 등)로 뜨고,
        추천 대안번호가 `.lotto720_popup_recomand_list`에 들어온다.
        """
        js = r"""
        (() => {
          const nodes = Array.from(document.querySelectorAll('.popup_section,.popup_content,[class*="recomand"],[class*="popup"]'))
            .filter(e => e.offsetParent !== null);
          for (const e of nodes) {
            const t = e.innerText || '';
            if (t.indexOf('판매가 완료') >= 0 || t.indexOf('이미 판매') >= 0 || t.indexOf('판매완료') >= 0) {
              const rec = document.querySelector('.lotto720_popup_recomand_list');
              const alts = rec ? (rec.innerText || '').replace(/\s+/g, ' ').trim() : '';
              return JSON.stringify({soldout: true, alts: alts});
            }
          }
          return JSON.stringify({soldout: false, alts: ''});
        })()
        """
        res = await self._safe_eval(tab, js)
        try:
            d = json.loads(res) if isinstance(res, str) else {}
            return bool(d.get("soldout")), str(d.get("alts") or "")
        except Exception:  # noqa: BLE001
            return False, ""

    async def _set_manual_digits(self, tab, digits: str) -> str:
        """6자리를 숫자버튼 순서 클릭으로 입력하고, 선택된 번호(6자리)를 읽어 반환.

        실제 모바일 팝업 구조(진단으로 확인): '2. 6자리 번호 선택' 영역의 숫자 버튼
        `.num_full_list .numsgroup`(1~9,0)을 **원하는 숫자 순서대로 클릭**하면 각 자리
        `.win720_num .num_list .sel1~6 .numdgroup`(및 히든 `num1`~`num6`)가 채워진다.
        성공 판정은 '읽은 번호 == 요청'으로만 하므로(오구매 방지), 어긋나면 호출부가
        지출 없이 중단한다. `resetNumber()`로 먼저 초기화한다.
        """
        d = "".join(c for c in str(digits) if c.isdigit())[:6]
        click_js = """
        (() => {
          try { if (typeof resetNumber === 'function') resetNumber(); } catch (e) {}
          const want = "%s";
          const btns = Array.from(document.querySelectorAll('.num_full_list .numsgroup'));
          const byDigit = {};
          btns.forEach(b => { const t = (b.innerText || '').replace(/[^0-9]/g, ''); if (t) byDigit[t] = b; });
          let clicked = 0;
          for (const ch of want) { const b = byDigit[ch]; if (b) { b.click(); clicked++; } }
          return clicked;
        })()
        """ % d
        await self._safe_eval(tab, click_js)
        await asyncio.sleep(0.4)
        read_js = """
        (() => {
          const disp = Array.from(document.querySelectorAll('.win720_num .num_list .numdgroup'))
            .map(s => (s.innerText || '').replace(/[^0-9]/g, '')).join('');
          if (disp && disp.length === 6) return disp;
          let hidden = '';
          for (let i = 1; i <= 6; i++) { const el = document.getElementById('num' + i); if (el) hidden += (el.value || ''); }
          return hidden;
        })()
        """
        res = await self._safe_eval(tab, read_js)
        return res if isinstance(res, str) else ""

    async def _popup_dump(self, tab) -> str:
        """번호선택 팝업의 DOM/입력요소/전역함수를 JSON 으로 덤프(진단용)."""
        js = r"""
        (() => {
          const pop = document.querySelector('.lotto720_popup') || document.querySelector('[class*="popup"]') || document.querySelector('[id*="popup"]') || document.body;
          const labels = Array.from(document.querySelectorAll('label[for]')).slice(0, 120).map(l => l.getAttribute('for'));
          const inputs = Array.from(document.querySelectorAll('input')).slice(0, 120).map(i => ({id: i.id, name: i.name, type: i.type, cls: i.className}));
          const fns = Object.getOwnPropertyNames(window).filter(n => { try { return /num|sel|auto|manual|verify|order|pick|group|buy/i.test(n) && typeof window[n] === 'function'; } catch (e) { return false; } }).slice(0, 80);
          const html = (pop ? pop.outerHTML : '').replace(/\s+/g, ' ').slice(0, 5000);
          return JSON.stringify({url: location.href, labels: labels, inputs: inputs, fns: fns, html: html});
        })()
        """
        res = await self._safe_eval(tab, js)
        if isinstance(res, str):
            return res[:8000]
        return str(res)[:8000]

    async def _read_balance(self, tab):
        """현재 페이지의 '보유중인 예치금' 금액(원)을 정수로 읽는다(실패 시 None)."""
        js = (
            r"(() => { const m = (document.body.innerText || '')"
            r".match(/예치금\s*([0-9,]+)\s*원/); "
            r"return m ? m[1].replace(/,/g, '') : ''; })()"
        )
        res = await self._safe_eval(tab, js)
        try:
            return int(res) if res else None
        except (TypeError, ValueError):
            return None

    async def _read_blocking_modal(self, tab) -> str:
        """현재 보이는 알림/모달 텍스트를 모아 반환(구매 실패 사유 분류용)."""
        js = r"""
        (() => {
          const nodes = Array.from(document.querySelectorAll('.popup_section,.popup_content,[class*="alert"],[class*="layer"],[class*="modal"],[class*="popup"]'))
            .filter(e => e.offsetParent !== null);
          const txt = nodes.map(e => (e.innerText || '').replace(/\s+/g, ' ').trim())
            .filter(Boolean).join(' | ');
          return txt.slice(0, 600);
        })()
        """
        res = await self._safe_eval(tab, js)
        return res if isinstance(res, str) else ""

    async def _confirm_order(self, tab, count: int, dialogs_before: int) -> None:
        """doOrder 후 티켓 렌더를 기다리고, 실패면 사유를 분류해 예외를 던진다.

        성공(saleTicket 티켓 count개 이상)하면 조용히 반환. 실패면 다이얼로그+보이는
        모달 텍스트를 모아 classify_purchase_failure 로 판정(확정 미구매는 uncertain=False,
        분류 불가만 uncertain=True). 자동·수동 구매가 공유한다.
        """
        done = await self._wait_js(
            tab,
            (
                "(() => document.querySelectorAll('.saleTicket li "
                ".lotto720_popup_group').length >= %d)()" % count
            ),
            timeout=30.0,
        )
        if done:
            return
        new_dialogs = [m for m in self._dialog_msgs[dialogs_before:] if m]
        last = new_dialogs[-1] if new_dialogs else ""
        modal = await self._read_blocking_modal(tab)
        text = (last + " " + modal).strip()
        _cat, message, uncertain = classify_purchase_failure(text)
        detail = f" (안내: {text[:120]})" if text else ""
        raise DhPensionBrowserError(message + detail, uncertain=uncertain)

    async def _ensure_balance(self, tab, amount: int) -> None:
        """doOrder 전에 예치금이 충분한지 확인(부족하면 지출 없이 중단)."""
        bal = await self._read_balance(tab)
        if bal is not None and bal < amount:
            raise DhPensionBrowserError(
                f"예치금이 부족합니다 (보유 {bal:,}원 < 필요 {amount:,}원). "
                "예치금을 충전한 뒤 재시도하세요."
            )

    async def _extract_tickets(self, tab) -> list:
        js = r"""
        (() => {
            const out = [];
            const lis = document.querySelectorAll('.saleTicket li');
            lis.forEach((li, idx) => {
                const g = li.querySelector('.lotto720_popup_group');
                if (!g) return;
                const group = parseInt(g.innerText);
                const m = li.innerText.match(/\d{6}/);
                const numbers = m ? m[0] : '';
                if (group > 0 && numbers.length === 6) {
                    out.push({no: idx + 1, group: group, numbers: numbers});
                }
            });
            return out;
        })()
        """
        res = await self._safe_eval(tab, js)
        return res if isinstance(res, list) else []

    # ---------------------------------------------------------- tiny utilities

    async def _find_first(self, tab, selectors):
        for sel in selectors:
            el = await tab.query_selector(sel)
            if el is not None:
                return el
        return None

    async def _wait_first(self, tab, selectors, timeout: float):
        """여러 셀렉터 중 하나가 나타날 때까지 폴링(최초 발견 요소 반환)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            el = await self._find_first(tab, selectors)
            if el is not None:
                return el
            await asyncio.sleep(0.3)
        return None

    async def _page_diag(self, tab) -> str:
        """실패 진단용: 현재 URL·제목·입력필드 id/name 를 수집(실 셀렉터 파악용)."""
        js = (
            "(() => { const ins = Array.from(document.querySelectorAll('input'))"
            ".slice(0, 20).map(i => i.id || i.name || i.type).filter(Boolean); "
            "return JSON.stringify({url: location.href, title: document.title, "
            "inputs: ins}); })()"
        )
        info = await self._safe_eval(tab, js)
        return f"페이지상태={info}"

    async def _safe_eval(self, tab, expr):
        try:
            return await tab.evaluate(expr)
        except Exception as e:  # noqa: BLE001
            self._log.debug(f"[PENSION-BR] eval 실패: {expr[:60]} -> {e}")
            return None

    async def _wait_js(self, tab, expr: str, timeout: float) -> bool:
        """expr(bool 반환 JS)가 참이 될 때까지 폴링."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            val = await self._safe_eval(tab, expr)
            if val:
                return True
            await asyncio.sleep(0.3)
        return False

    async def _wait_ajax_idle(self, tab, timeout: float) -> bool:
        expr = (
            "(() => { const e = document.querySelector('#ajax_loading'); "
            "return !e || e.offsetParent === null || "
            "getComputedStyle(e).display === 'none'; })()"
        )
        return await self._wait_js(tab, expr, timeout)

    async def _resolve_round(self) -> int:
        if self.round_provider is None:
            return 0
        try:
            latest = await self.round_provider()
            return int(latest) + 1 if latest else 0
        except Exception as e:  # noqa: BLE001
            self._log.warning(f"[PENSION-BR] 회차 조회 실패: {e}")
            return 0
