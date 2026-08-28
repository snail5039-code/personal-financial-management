"""도구 모음 - 도메인별 모듈을 모아 Gemini에 넘길 목록을 만든다.

도구를 새로 만들 때:
1. 알맞은 tools_*.py에 구현 함수와 스키마(dict)를 추가하고
2. 아래 REGISTRY의 해당 모듈 목록에 스키마 이름을 넣는다.

  tools_budget  거래 내역 · 예산 · 카테고리
  tools_todo    할일 (구글 할일 연동)
  tools_memo    메모
  tools_calc    생활 계산기
  tools_info    날씨 · 환율
"""

import tools_budget
import tools_calc
import tools_info
import tools_memo
import tools_todo
import undo

# 앱에서 카테고리 목록을 볼 때 쓴다.
get_categories = tools_budget.get_categories


# ---------------------------------------------------------------------------
# 되돌리기 - 어느 도메인이든 마지막 작업 한 건을 되돌린다.
# ---------------------------------------------------------------------------
def undo_last_action():
    """가장 최근에 실행된 거래/카테고리/할일/메모 작업 한 건을 되돌린다."""
    return undo.undo_last()


undo_last_action_tool = {
    "type": "function",
    "name": "undo_last_action",
    "description": (
        "가장 최근에 실행한 거래/카테고리 등록/수정/삭제, 할일 등록/완료/삭제(완료 항목 일괄 정리 포함), "
        "또는 메모 등록/삭제 작업을 한 번 되돌린다. 연속으로 두 번 호출해도 한 단계만 되돌리며, "
        "되돌릴 작업이 없으면 안내한다."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}


# 모듈별로 어떤 도구를 공개할지 모아둔다. 스키마 변수명은 항상 '<함수명>_tool'이다.
REGISTRY = {
    tools_budget: [
        "transaction_registration",
        "transaction_search",
        "transaction_Modification",
        "transaction_Delete",
        "transaction_Budget_Management",
        "transaction_Save_Json",
        "monthly_Transaction_History",
        "category_registration",
        "category_Modification",
        "category_Delete",
    ],
    tools_todo: [
        "todo_registration",
        "todo_search",
        "todo_complete",
        "todo_Delete",
        "todo_clear_completed",
    ],
    tools_memo: [
        "memo_add",
        "memo_search",
        "memo_Delete",
    ],
    tools_calc: [
        "calc_split_bill",
        "calc_dday",
        "calc_age",
        "calc_business_days",
    ],
    tools_info: [
        "weather_check",
        "exchange_rate_check",
    ],
}


def _collect():
    """REGISTRY를 훑어 스키마 목록과 이름→함수 매핑을 만든다."""
    schemas = []
    functions = {}
    for module, names in REGISTRY.items():
        for name in names:
            schemas.append(getattr(module, f"{name}_tool"))
            functions[name] = getattr(module, name)
    return schemas, functions


TOOLS, FUNCTION_MAP = _collect()

# 되돌리기는 특정 도메인에 속하지 않아 여기서 직접 등록한다.
TOOLS.append(undo_last_action_tool)
FUNCTION_MAP["undo_last_action"] = undo_last_action
