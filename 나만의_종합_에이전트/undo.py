"""되돌리기(undo) 공용 저장소.

가장 최근 작업 한 건을 '되돌리는 방법' 자체로 기억한다. 각 도메인은 작업을
하기 직전에 record()로 되돌리는 함수를 넘겨두기만 하면 되고, 이쪽은 그게
가계부인지 메모인지 할일인지 알 필요가 없다.
"""

import copy

_undo_action = None


def copy_of(data):
    """저장소 데이터를 스냅샷으로 떠둔다 (나중에 그대로 되돌려 쓰기 위해)."""
    return copy.deepcopy(data)


def record(action):
    """되돌리는 함수를 기억한다. 직전에 기억해둔 것은 버린다(한 단계만 지원)."""
    global _undo_action
    _undo_action = action


def undo_last():
    """가장 최근에 기억해둔 작업을 한 번 되돌린다."""
    global _undo_action

    if _undo_action is None:
        return {"message": "되돌릴 작업이 없습니다."}

    action = _undo_action
    _undo_action = None
    try:
        action()
    except Exception as e:
        return {"error": f"되돌리는 중 오류가 발생했습니다: {e}"}
    return {"message": "방금 작업을 되돌렸습니다."}
