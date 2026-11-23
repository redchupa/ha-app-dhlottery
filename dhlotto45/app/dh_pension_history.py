"""
dh_pension_history.py
연금복권720 구매 원장(LP72, selectMyLotteryledger.do) 가공 순수 함수.

HA/네트워크 의존성이 없어 단위 테스트가 가능하다. main.py 의
publish_pension_history_sensors 와 당첨 알림 로직이 공유한다.

원장 아이템 주요 필드:
- ltEpsd(int): 회차
- gmInfo(str): "조:번호" (예 "1:901948")
- ltWnResult(str): 당첨결과("미추첨" | "낙첨" | 등수/당첨 표기)
- wnRnk: 당첨 등수(미추첨/낙첨이면 None/0)
- ltWnAmt: 당첨금(원). 연금 1등 등 연금형은 0/None 일 수 있음
- eltOrdrDt(str): 구매일, epsdRflDt(str): 추첨일
"""

NOT_DRAWN = ("미추첨", "-", "")


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def group_rounds(items):
    """원장 아이템을 회차(ltEpsd)별로 묶는다. 반환: {round_no: [items]}."""
    rounds: dict = {}
    for it in items or []:
        r = _safe_int(it.get("ltEpsd"))
        if r > 0:
            rounds.setdefault(r, []).append(it)
    return rounds


def build_round(items_for_round):
    """한 회차의 게임 목록과 당첨 집계를 만든다.

    반환: (games, win_count, total_win_amount)
    games: [{"no","group","number","result","rank","win_amount"}]
    당첨 판정: 추첨됨(미추첨/공백 아님) + "낙첨" 아님 + (당첨금>0 또는 등수>0).
    """
    games, win_count, total_win = [], 0, 0
    for idx, it in enumerate(items_for_round or [], start=1):
        gm = str(it.get("gmInfo") or "")
        grp, num = gm.split(":", 1) if ":" in gm else ("", gm)
        result = (str(it.get("ltWnResult") or "")).strip() or "-"
        rank = it.get("wnRnk")
        amt = _safe_int(it.get("ltWnAmt"))
        drawn = result not in NOT_DRAWN
        # 당첨 판정: 추첨 반영 + '낙첨/등외' 아님 + (당첨금>0 | 등수>0 | 결과에 '당첨' 표기).
        # rank/amt 가 비어도 결과 텍스트가 '…당첨'이면 당첨으로 본다(실데이터 검증 전 보수적 확장).
        is_win = (
            drawn
            and "낙첨" not in result
            and "등외" not in result
            and (amt > 0 or _safe_int(rank) > 0 or "당첨" in result)
        )
        if is_win:
            win_count += 1
            total_win += amt
        games.append({
            "no": idx,
            "group": grp,
            "number": num,
            "result": result,
            "rank": rank,
            "win_amount": amt,
        })
    return games, win_count, total_win


def is_drawn(games) -> bool:
    """회차 게임 중 하나라도 추첨 결과가 반영됐는지."""
    return any(g["result"] not in NOT_DRAWN for g in (games or []))


def summarize(round_no: int, games, win_count: int, total_win: int) -> str:
    """지난 회차 결과 요약 문자열(알림/대시보드용)."""
    if not games:
        return "지난 회차 구매 내역 없음"
    if not is_drawn(games):
        return f"{round_no}회 {len(games)}매 구매 (추첨 대기)"
    if win_count > 0:
        return f"{round_no}회 {len(games)}매 중 당첨 {win_count}매 · {total_win:,}원"
    return f"{round_no}회 {len(games)}매 모두 낙첨"
