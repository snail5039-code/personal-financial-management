"""구글 캘린더 도구 (조회 + 일정 추가)."""

import google_auth
import google_calendar
import undo


def _error_message(e):
    if isinstance(e, google_auth.GoogleServiceNotConfigured):
        return str(e)
    return f"구글 캘린더 호출에 실패했습니다: {e}"


# ---------------------------------------------------------------------------
# 33. calendar_search
# ---------------------------------------------------------------------------
def calendar_search(start_date, end_date):
    """start_date~end_date(YYYY-MM-DD) 사이의 구글 캘린더 일정을 조회한다."""
    try:
        events = google_calendar.list_events(start_date, end_date)
    except Exception as e:
        return {"error": _error_message(e)}

    if not events:
        return {"message": f"{start_date}~{end_date} 사이에 일정이 없습니다."}
    return {"count": len(events), "events": events}


calendar_search_tool = {
    "type": "function",
    "name": "calendar_search",
    "description": (
        "지정한 날짜 범위의 구글 캘린더 일정을 조회한다. 오늘 일정만 보려면 start_date와 "
        "end_date를 오늘 날짜로 똑같이 준다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "조회 시작 날짜 (YYYY-MM-DD)"},
            "end_date": {"type": "string", "description": "조회 끝 날짜 (YYYY-MM-DD)"},
        },
        "required": ["start_date", "end_date"],
    },
}


# ---------------------------------------------------------------------------
# 34. calendar_add_event
# ---------------------------------------------------------------------------
def calendar_add_event(title, start_datetime, end_datetime, location=None):
    """구글 캘린더에 새 일정을 추가한다. 되돌리기(undo)로 방금 추가한 일정을 지울 수 있다."""
    try:
        event = google_calendar.create_event(title, start_datetime, end_datetime, location or "")
    except Exception as e:
        return {"error": _error_message(e)}

    undo.record(lambda: google_calendar.delete_event(event["id"]))
    return {"message": f"'{event['title']}' 일정을 추가했습니다.", "event": event}


calendar_add_event_tool = {
    "type": "function",
    "name": "calendar_add_event",
    "description": (
        "구글 캘린더에 새 일정을 추가한다. 사용자가 말한 상대적인 시각('지금부터 15분 후' 등)은 "
        "현재 시각을 기준으로 계산해서 start_datetime/end_datetime을 절대 시각으로 변환해 넘긴다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "일정 제목"},
            "start_datetime": {
                "type": "string",
                "description": "일정 시작 시각 (YYYY-MM-DDTHH:MM:SS, 한국 시간 기준)",
            },
            "end_datetime": {
                "type": "string",
                "description": "일정 종료 시각 (YYYY-MM-DDTHH:MM:SS, 한국 시간 기준). "
                "사용자가 길이를 안 말했으면 시작 시각 30분 뒤로 잡는다.",
            },
            "location": {"type": "string", "description": "장소 (선택)"},
        },
        "required": ["title", "start_datetime", "end_datetime"],
    },
}
