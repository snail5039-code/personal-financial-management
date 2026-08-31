"""도구 모음 - 도메인별 모듈을 모아 Gemini에 넘길 목록을 만든다.

도구를 새로 만들 때:
1. 알맞은 tools_*.py에 구현 함수와 스키마(dict)를 추가하고
2. 아래 REGISTRY의 해당 모듈 목록에 스키마 이름을 넣는다.

  tools_budget    거래 내역 · 예산 · 카테고리
  tools_todo      할일 (구글 할일 연동)
  tools_memo      메모
  tools_calc      생활 계산기
  tools_info      날씨 · 환율
  tools_news      경제 · IT 뉴스
  tools_system    PC 상태 (CPU·메모리·디스크·네트워크)
  tools_clipboard 클립보드
  tools_screen    화면 인식 (스크린샷 + Gemini vision)
  tools_pc        PC 제어 (앱 실행/종료, 볼륨, 화면 잠금)
  tools_file      파일 관리 (검색/열기/읽기/복사/이동/이름변경/삭제)
  tools_gmail     Gmail (읽기 전용)
  tools_calendar  구글 캘린더 (조회 + 일정 추가)
  tools_schedule  자동 아침 브리핑 시각 설정 (실제 알림은 tray_app.py가 보냄)
  tools_local     로컬 문서 의미 기반 검색 (RAG) - 문서/바탕화면 폴더

도구가 저장 안 된 작업을 날리거나(앱 강제종료) 파일을 옮기고 지우는 등 되돌리기 어려우면,
아래 CONFIRM_MESSAGES에 등록해서 app.py가 실행 전에 터미널에서 사용자 확인을 받게 한다.
"""

from . import tools_budget
from . import tools_calc
from . import tools_calendar
from . import tools_clipboard
from . import tools_file
from . import tools_gmail
from . import tools_info
from . import tools_local
from . import tools_memo
from . import tools_news
from . import tools_pc
from . import tools_schedule
from . import tools_screen
from . import tools_system
from . import tools_todo
from . import undo

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
    tools_news: [
        "news_briefing",
    ],
    tools_system: [
        "system_status",
    ],
    tools_clipboard: [
        "clipboard_read",
        "clipboard_write",
    ],
    tools_screen: [
        "screen_capture",
    ],
    tools_pc: [
        "app_launch",
        "app_close",
        "volume_set",
        "volume_mute",
        "lock_screen",
    ],
    tools_file: [
        "file_search",
        "file_open",
        "file_read_text",
        "file_copy",
        "file_move",
        "file_rename",
        "file_delete",
    ],
    tools_gmail: [
        "email_search",
        "email_read",
    ],
    tools_calendar: [
        "calendar_search",
        "calendar_add_event",
    ],
    tools_schedule: [
        "get_briefing_schedule",
        "set_briefing_time",
        "set_briefing_enabled",
        "set_meeting_reminder_minutes",
        "set_meeting_reminder_enabled",
    ],
    tools_local: [
        "index_local_documents",
        "local_search",
    ],
}


# 실행 전 사용자 확인이 필요한 도구. 값은 호출 인자(dict)를 받아 확인 문구를 만드는 함수다.
# app.py의 execute_tool_call이 실제 실행 직전에 이 문구로 y/n을 묻는다.
CONFIRM_MESSAGES = {
    "app_close": lambda args: (
        f"'{args.get('name')}' 프로그램을 강제 종료합니다. 저장 안 된 작업이 있으면 사라질 수 있어요."
    ),
    "file_move": lambda args: f"'{args.get('source')}'를 '{args.get('destination')}'(으)로 이동합니다.",
    "file_rename": lambda args: f"'{args.get('path')}'의 이름을 '{args.get('new_name')}'(으)로 바꿉니다.",
    "file_delete": lambda args: f"'{args.get('path')}'를 휴지통으로 보냅니다.",
    "calendar_add_event": lambda args: (
        f"'{args.get('title')}' 일정을 {args.get('start_datetime')}에 구글 캘린더에 추가합니다."
    ),
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
