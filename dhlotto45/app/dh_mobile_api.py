"""동행복권 모바일 조회 API 클라이언트.

공식 앱(복똑방)이 사용하는 모바일 서버(ma.dhlottery.co.kr)의 공개 조회
엔드포인트를 호출한다. 로그인이 필요 없는 조회 전용이므로 기존 로그인
세션(DhLotteryClient)과 분리된 별도 세션을 사용한다.

- /api/*          : {resultCode, resultMessage, data} 래퍼로 감싼 JSON
- /maShare/*.dat  : 래퍼 없는 raw JSON

주의: ma.dhlottery.co.kr 은 앱 전용 서버라 일부 네트워크(사내/개발 DNS)에서
도메인이 해석되지 않을 수 있다. 정상 인터넷 환경(HA 호스트 등)에서는 문제없다.
"""

import logging
from typing import Any, Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

MA_LOTTERY_URL = "https://ma.dhlottery.co.kr"

# 공식 앱이 보내는 것과 유사한 모바일 User-Agent
_DEFAULT_UA = "Dalvik/2.1.0 (Linux; U; Android 14)"


class DhMobileApiError(Exception):
    """모바일 조회 API 예외 클래스입니다."""


class DhMobileApiClient:
    """ma.dhlottery.co.kr 조회 전용 클라이언트입니다."""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """외부 세션을 주입하거나, 없으면 내부에서 생성합니다."""
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> "DhMobileApiClient":
        self._ensure_session()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": _DEFAULT_UA,
                    "Accept": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15, connect=10),
            )
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """내부에서 생성한 세션만 종료합니다."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get_json(self, path: str) -> Any:
        """경로를 GET 하여 JSON으로 반환합니다."""
        session = self._ensure_session()
        url = f"{MA_LOTTERY_URL}{path}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise DhMobileApiError(
                        f"[ERROR] Mobile API request failed: {resp.status} {resp.reason} ({path})"
                    )
                # 서버가 text/plain 으로 내려주는 .dat 도 있으므로 content_type 검사를 끈다.
                return await resp.json(content_type=None)
        except DhMobileApiError:
            raise
        except Exception as ex:
            raise DhMobileApiError(f"[ERROR] Mobile API request error ({path}): {ex}") from ex

    @staticmethod
    def _unwrap(payload: Any) -> Any:
        """/api/* 응답의 {resultCode, data} 래퍼를 벗겨 data 를 반환합니다."""
        if isinstance(payload, dict) and "resultCode" in payload:
            code = str(payload.get("resultCode"))
            if code != "200":
                raise DhMobileApiError(
                    f"[ERROR] Mobile API result not OK: {code} {payload.get('resultMessage')}"
                )
            return payload.get("data")
        return payload

    async def async_get_cumulative_number_stats(self) -> dict[int, int]:
        """로또6/45 번호별 전체 누적 출현 횟수를 조회합니다.

        Returns:
            {1: 171, 2: 157, ..., 45: 175} 형태의 번호→누적 출현 횟수 딕셔너리.
        """
        data = self._unwrap(await self._get_json("/api/stats/lt645/no"))
        row = (data or {}).get("list", {}) if isinstance(data, dict) else {}
        stats: dict[int, int] = {}
        for num in range(1, 46):
            value = row.get(f"wnNo{num}")
            stats[num] = int(value) if isinstance(value, (int, float, str)) and str(value).strip() != "" else 0
        return stats

    async def async_get_latest_draw(self) -> dict[str, Any]:
        """로또6/45 최신 회차 당첨 상세를 조회합니다.

        Returns:
            {round_no, numbers[6], bonus, sale_amount, rank_result{...}, ...}
        """
        raw = await self._get_json(
            "/maShare/json/lotto645/draw/lotto645_draw_last.dat"
        )
        raw = self._unwrap(raw) if isinstance(raw, dict) and "resultCode" in raw else raw
        if not isinstance(raw, dict):
            raise DhMobileApiError("[ERROR] Unexpected latest-draw payload shape.")

        numbers = [int(n) for n in str(raw.get("wnNo", "")).split(",") if n.strip().isdigit()]
        bonus_raw = str(raw.get("bnsWnNo", "")).strip()
        return {
            "round_no": raw.get("ltEpsd"),
            "numbers": numbers,
            "bonus": int(bonus_raw) if bonus_raw.isdigit() else None,
            "sale_amount": raw.get("ntslAmt"),
            "draw_date": raw.get("espdRflYmd"),
            "claim_expiry_date": raw.get("wngsGiveExpryYmd"),
            "rank_result": raw.get("rflRslt", {}),
            "raw": raw,
        }

    async def async_get_pension_latest_draw(self) -> dict[str, Any]:
        """연금복권720+ 최신 회차 당첨 정보를 조회합니다.

        연금복권은 당첨번호가 '조(1자리) + 6자리 번호' 형식(예: "3668912" = 3조 668912)이며,
        보너스는 6자리 번호만 비교합니다. 등위가 1~7등으로 로또와 다르고 금액 필드가 없습니다.

        Returns:
            {round_no, group, number, winning_number_display, bonus,
             sale_amount, draw_date, rank_winners{1..7}, bonus_winners, first_store, raw}
        """
        raw = await self._get_json(
            "/maShare/json/pd720/draw/lp720_draw_last.dat"
        )
        raw = self._unwrap(raw) if isinstance(raw, dict) and "resultCode" in raw else raw
        if not isinstance(raw, dict):
            raise DhMobileApiError("[ERROR] Unexpected pension-draw payload shape.")

        wnno = str(raw.get("wnNo", "")).strip()
        group = wnno[0] if len(wnno) == 7 and wnno.isdigit() else None
        number = wnno[1:] if len(wnno) == 7 and wnno.isdigit() else wnno
        bonus = str(raw.get("bnsWnNo", "")).strip()
        rfl = raw.get("rflRslt", {}) if isinstance(raw.get("rflRslt"), dict) else {}
        return {
            "round_no": raw.get("ltEpsd"),
            "group": int(group) if group else None,
            "number": number,
            "winning_number_display": (f"{group}조 {number}" if group else wnno),
            "bonus": bonus,
            "sale_amount": raw.get("ntslAmt"),
            "draw_date": raw.get("espdRflYmd"),
            "claim_expiry_date": raw.get("wngsGiveExpryYmd"),
            "rank_winners": {i: rfl.get(f"rnk{i}WnNope") for i in range(1, 8)},
            "bonus_winners": rfl.get("bnsWnNope"),
            "first_store": rfl.get("rnk1WnShp"),
            "raw": raw,
        }

    async def async_get_round_history(self, count: int = 50) -> list[dict[str, Any]]:
        """로또6/45 회차별 당첨번호 이력을 최신 회차부터 조회합니다.

        Args:
            count: 가져올 회차 수 (최신순). 서버 totalCount 범위로 자동 제한.

        Returns:
            [{round_no, numbers[6], bonus, draw_date}, ...] (최신 회차가 먼저).
        """
        count = max(1, int(count))
        data = self._unwrap(
            await self._get_json(
                f"/api/stats/lt645/noEpsd?pageNum=1&recordCountPerPage={count}"
            )
        )
        rows = (data or {}).get("list", []) if isinstance(data, dict) else []
        history: list[dict[str, Any]] = []
        for row in rows:
            try:
                numbers = [int(row[f"tm{i}WnNo"]) for i in range(1, 7)]
            except (KeyError, TypeError, ValueError):
                continue
            bonus = row.get("bnsWnNo")
            history.append(
                {
                    "round_no": row.get("ltEpsd"),
                    "numbers": numbers,
                    "bonus": int(bonus) if isinstance(bonus, (int, str)) and str(bonus).strip().isdigit() else None,
                    "draw_date": row.get("ltRflYmd"),
                }
            )
        return history
