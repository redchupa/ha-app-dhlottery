"""
dashboard_api.py
사이드바(Ingress) 대시보드의 보안·입력 검증 순수 함수. FastAPI/HA 의존성이 없어 단위 테스트가 쉽다.

보안 모델(구매 API):
1. Ingress 전용: 요청 출발지 IP 가 Supervisor Ingress 프록시(172.30.32.2)일 때만 허용.
   직접 포트(60099)로 들어온 요청은 헤더를 위조해도 출발지 IP 는 바꿀 수 없으므로 차단된다.
   Ingress 는 HA 로그인 세션을 검증한 뒤에만 프록시하므로 인증은 HA 가 담당한다.
2. CSRF: 페이지에 심은 프로세스별 비밀 토큰을 커스텀 헤더(X-DHL-CSRF)로 보내야 한다.
   커스텀 헤더는 교차 출처 요청에서 사전요청(preflight)을 강제하고, CORS 는 자격증명을
   허용하지 않으므로 다른 사이트는 HA 세션 쿠키를 실은 채 이 API 를 호출할 수 없다.
3. 입력 검증: 작업 종류는 허용 목록만, 수동 번호는 서버에서 다시 검증한다.
"""

import hmac
import logging

INGRESS_PROXY_IP = "172.30.32.2"
CSRF_HEADER = "X-DHL-CSRF"

LOTTO_ACTIONS = {
    "lotto_auto_1": ("buy_auto_1", "로또 1게임 자동", 1000),
    "lotto_auto_5": ("buy_auto_5", "로또 5게임 자동", 5000),
    "lotto_manual": ("buy_manual", "로또 1게임 수동", 1000),
}
PENSION_ACTIONS = {
    "pension_auto_1": (1, "연금복권 1매 자동", 1000),
    "pension_auto_5": (5, "연금복권 5매 자동", 5000),
    "pension_manual": (None, "연금복권 1매 수동", 1000),
}
ALLOWED_ACTIONS = set(LOTTO_ACTIONS) | set(PENSION_ACTIONS)
MAX_INPUT_LEN = 60


class DashboardInputError(ValueError):
    """대시보드 요청 값이 잘못됨(HTTP 400)."""


def account_aliases(usernames) -> dict:
    """실제 아이디를 숨기는 표시용 별칭. 설정 순서대로 {username: ("account_1", "Account_1")}.

    웹 UI·API 응답·구매 요청에는 별칭만 쓰고 실제 아이디는 내보내지 않는다.
    """
    return {u: (f"account_{i}", f"Account_{i}") for i, u in enumerate(usernames or [], start=1)}


def configured_usernames(account_configs, max_accounts: int) -> list:
    """init_clients 가 accounts 에 등록할 아이디 목록을 같은 규칙으로 미리 계산한다.

    아이디·비밀번호가 빈 항목과 중복 아이디는 건너뛰고, 최대 max_accounts 개까지.
    """
    out = []
    for acc in account_configs or []:
        if len(out) >= max_accounts:
            break
        if not isinstance(acc, dict):
            continue
        u = acc.get("username", "")
        if u and acc.get("password", "") and u not in out:
            out.append(u)
    return out


def resolve_alias(usernames, alias):
    """별칭(account_N) → 실제 username. 없으면 None."""
    for u, (aid, _label) in account_aliases(usernames).items():
        if aid == alias:
            return u
    return None


def is_ingress_client(client_host) -> bool:
    """요청 출발지가 Supervisor Ingress 프록시인지."""
    return (client_host or "") == INGRESS_PROXY_IP


def csrf_ok(expected: str, provided) -> bool:
    """CSRF 토큰 비교(상수 시간). 기대값이 비어 있으면 항상 거부."""
    if not expected or not isinstance(provided, str) or not provided:
        return False
    return hmac.compare_digest(expected.encode(), provided.encode())


def action_label(action: str) -> tuple:
    """작업 → (표시 이름, 금액). 알 수 없으면 DashboardInputError."""
    if action in LOTTO_ACTIONS:
        _, label, amount = LOTTO_ACTIONS[action]
        return label, amount
    if action in PENSION_ACTIONS:
        _, label, amount = PENSION_ACTIONS[action]
        return label, amount
    raise DashboardInputError(f"알 수 없는 작업입니다: {action!r}")


def normalize_lotto_manual(text) -> str:
    """로또 수동 입력 '1,2,3,auto,auto,auto' 검증 → 정규화된 문자열.

    6칸, 각 칸은 1~45 정수 또는 auto, 숫자 중복 금지. 모두 auto 면 자동 1게임과 같다.
    """
    s = str(text or "").strip()
    if not s:
        raise DashboardInputError("로또 수동 번호를 입력하세요 (예: 1,7,12,auto,auto,auto)")
    if len(s) > MAX_INPUT_LEN:
        raise DashboardInputError("입력이 너무 깁니다")
    parts = [p.strip().lower() for p in s.split(",")]
    if len(parts) != 6:
        raise DashboardInputError(f"6칸을 쉼표로 구분해 입력하세요 (현재 {len(parts)}칸)")
    nums = []
    out = []
    for p in parts:
        if p == "auto":
            out.append("auto")
            continue
        if not p.isdigit():
            raise DashboardInputError(f"숫자 또는 auto 만 입력할 수 있습니다: {p!r}")
        n = int(p)
        if n < 1 or n > 45:
            raise DashboardInputError(f"번호는 1~45 사이여야 합니다: {n}")
        nums.append(n)
        out.append(str(n))
    if len(nums) != len(set(nums)):
        raise DashboardInputError("같은 번호를 두 번 입력했습니다")
    return ",".join(out)


def normalize_pension_manual(group, digits) -> str:
    """연금 수동 입력(조 1~5, 6자리 번호) 검증 → '조,번호' 문자열."""
    g = str(group if group is not None else "").strip()
    d = str(digits if digits is not None else "").strip()
    if not (g.isdigit() and 1 <= int(g) <= 5):
        raise DashboardInputError("조는 1~5 중에서 선택하세요")
    if not (len(d) == 6 and d.isdigit()):
        raise DashboardInputError("번호는 6자리 숫자로 입력하세요 (예: 123456)")
    return f"{int(g)},{d}"


def judge_outcome(error_entry, started_at: float, success_entry=None) -> tuple:
    """구매 작업 종료 후 결과 판정 → (status, message).

    구매 함수들은 결과를 센서로만 남기므로, 작업 시작 이후 갱신된 오류 센서를 본다.
    - 오류 센서가 시작 후 '없음' 이 아닌 값으로 갱신 → error
    - 오류 센서가 시작 후 '없음' 으로 갱신(성공 경로) → success
    - 갱신 없음 → skipped (15초 내 중복 요청·기능 꺼짐 등으로 실행 안 됨)
    """
    def fresh(entry):
        return isinstance(entry, dict) and float(entry.get("ts") or 0) >= started_at

    if fresh(error_entry):
        state = str(error_entry.get("state") or "")
        if state and state != "없음":
            return "error", state
        msg = "구매 완료"
        if fresh(success_entry):
            msg = f"구매 완료: {success_entry.get('state')}"
        return "success", msg
    return "skipped", "실행되지 않았습니다(15초 이내 중복 요청이거나 기능이 꺼져 있음). 로그를 확인하세요."


class AliasLogFilter(logging.Filter):
    """로그 메시지 속 실제 아이디를 Account_N 으로 치환하는 logging 필터.

    너무 짧은 아이디(4자 미만)는 다른 글자를 잘못 바꿀 수 있어 치환하지 않는다.
    긴 아이디부터 바꿔 한 아이디가 다른 아이디의 일부일 때도 안전하게 처리한다.
    """

    def __init__(self, aliases: dict):
        super().__init__()
        self._pairs = sorted(
            ((u, label) for u, (_aid, label) in (aliases or {}).items() if u and len(u) >= 4),
            key=lambda p: len(p[0]),
            reverse=True,
        )

    def scrub(self, text: str) -> str:
        for u, label in self._pairs:
            if u in text:
                text = text.replace(u, label)
        return text

    def filter(self, record) -> bool:
        if not self._pairs:
            return True
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        new = self.scrub(msg)
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = self.scrub(record.exc_text)
        if new != msg:
            record.msg, record.args = new, None
        return True


# ---------------------------------------------------------------- dashboard prefs
# 대시보드 개인화 설정(테마·언어·카드 표시/순서 등). /data 에 저장해 기기 간 동기화한다.
THEMES = (
    "system", "light", "dark", "ha-blue",                                 # 기본
    "jackpot-gold", "clover", "lucky-red", "golden-pig", "lotto-pop",     # 행운
    "neon-draw", "aurora", "galaxy",                                      # 밤하늘·미래
)
CARD_IDS = ("summary", "buy", "favorites", "lotto_current", "lotto_prev", "pension_current", "pension_prev",
            "winning", "stats", "auto")
LUCKY_MESSAGE_MAX = 40

DEFAULT_PREFS = {
    "theme": "system",
    "lang": "ko",
    "density": "comfortable",     # comfortable | compact
    "ball_style": "glossy",       # glossy | flat
    "effects": True,              # 당첨 축하·반짝임 애니메이션
    "show_hero": True,            # 상단 행운 배너
    "lucky_message": "",          # 나만의 행운 문구(비우면 기본 문구 순환)
    "default_account": "",        # account_N (비우면 첫 계정)
    "card_order": list(CARD_IDS),
    "hidden_cards": [],
}


def _clean_text(value, limit: int) -> str:
    """제어문자 제거 + 공백 정리 + 길이 제한(표시용 문자열)."""
    # 줄바꿈·탭 등 공백 제어문자는 띄어쓰기로, 나머지 제어문자는 제거
    s = "".join(" " if ch.isspace() else ch for ch in str(value or "") if ch.isprintable() or ch.isspace())
    return " ".join(s.split())[:limit]


def normalize_prefs(raw) -> dict:
    """저장/응답용 설정 정규화. 알 수 없는 키는 버리고 잘못된 값은 기본값으로 바꾼다."""
    p = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULT_PREFS)
    out["card_order"] = list(CARD_IDS)
    out["hidden_cards"] = []
    if p.get("theme") in THEMES:
        out["theme"] = p["theme"]
    if p.get("lang") in ("ko", "en"):
        out["lang"] = p["lang"]
    if p.get("density") in ("comfortable", "compact"):
        out["density"] = p["density"]
    if p.get("ball_style") in ("glossy", "flat"):
        out["ball_style"] = p["ball_style"]
    for key in ("effects", "show_hero"):
        if isinstance(p.get(key), bool):
            out[key] = p[key]
    out["lucky_message"] = _clean_text(p.get("lucky_message"), LUCKY_MESSAGE_MAX)
    acc = str(p.get("default_account") or "")
    out["default_account"] = acc if (acc.startswith("account_") and acc[8:].isdigit() and len(acc) <= 12) else ""
    order = p.get("card_order")
    if isinstance(order, list):
        seen = []
        for c in order:
            if c in CARD_IDS and c not in seen:
                seen.append(c)
        out["card_order"] = seen + [c for c in CARD_IDS if c not in seen]
    hidden = p.get("hidden_cards")
    if isinstance(hidden, list):
        out["hidden_cards"] = [c for c in CARD_IDS if c in hidden]
    return out


def merge_prefs(current, change) -> dict:
    """현재 설정에 부분 변경을 덮어쓴 뒤 정규화."""
    base = normalize_prefs(current)
    if isinstance(change, dict):
        base.update({k: v for k, v in change.items() if k in DEFAULT_PREFS})
    return normalize_prefs(base)
