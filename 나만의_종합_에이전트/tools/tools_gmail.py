"""Gmail 도구 (읽기 전용). 메일 발송/삭제는 지원하지 않는다."""

from google_api import google_auth
from google_api import google_gmail


def _error_message(e):
    if isinstance(e, google_auth.GoogleServiceNotConfigured):
        return str(e)
    return f"Gmail 서비스 호출에 실패했습니다: {e}"


# ---------------------------------------------------------------------------
# 32. email_search / email_read
# ---------------------------------------------------------------------------
def email_search(query=None, limit=10):
    """받은 메일함에서 최근 메일을 검색한다. query로 Gmail 검색 문법을 그대로 쓸 수 있다."""
    try:
        emails = google_gmail.list_recent_emails(query=query, limit=limit)
    except Exception as e:
        return {"error": _error_message(e)}

    if not emails:
        return {"message": "조건에 맞는 메일을 찾을 수 없습니다."}
    return {"count": len(emails), "emails": emails}


email_search_tool = {
    "type": "function",
    "name": "email_search",
    "description": (
        "받은 메일함에서 최근 메일을 검색한다. query에 Gmail 검색 문법을 그대로 쓸 수 있다 "
        "(오늘 온 메일: 'newer_than:1d', 안 읽은 메일: 'is:unread', 중요 표시: 'is:important', "
        "특정 발신자: 'from:이메일주소'). 여러 조건은 공백으로 이어붙인다 (예: 'is:unread newer_than:1d'). "
        "query를 생략하면 최근 메일을 그대로 가져온다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Gmail 검색 문법 검색어 (선택)"},
            "limit": {"type": "integer", "description": "가져올 최대 개수 (기본 10)"},
        },
        "required": [],
    },
}


def email_read(message_id):
    """메일 하나의 본문 내용을 읽어온다."""
    try:
        return google_gmail.get_email_content(message_id)
    except Exception as e:
        return {"error": _error_message(e)}


email_read_tool = {
    "type": "function",
    "name": "email_read",
    "description": (
        "메일 하나의 본문 내용을 읽어온다. email_search로 받은 목록에서 특정 메일을 요약하거나 "
        "자세히 알려달라는 요청에 쓴다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message_id": {"type": "string", "description": "email_search로 받은 메일의 id"},
        },
        "required": ["message_id"],
    },
}
