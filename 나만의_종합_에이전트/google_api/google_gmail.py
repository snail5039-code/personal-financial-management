"""Gmail 연동 (읽기 전용). 메일 발송/삭제는 지원하지 않는다.

google_tasks.py와 별개 토큰 파일(data/google_gmail_token.json)을 쓴다. 같은 credentials.json을
재사용하지만, 필요한 권한(gmail.readonly)만 따로 동의받아서 할일 권한과 섞이지 않는다.
"""

import base64

from . import google_auth

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

_service = None


def _get_service():
    global _service
    if _service is None:
        _service = google_auth.get_service("gmail", "v1", SCOPES, "google_gmail_token.json", "Gmail")
    return _service


def _extract_plain_text(payload):
    """메일 본문(MIME) 구조를 훑어 첫 번째 text/plain 파트를 base64 디코딩해서 돌려준다."""
    body_data = (payload.get("body") or {}).get("data")
    if payload.get("mimeType") == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    for part in payload.get("parts") or []:
        text = _extract_plain_text(part)
        if text:
            return text
    return ""


def list_recent_emails(query=None, limit=10):
    """받은 메일함에서 최근 메일 목록을 가져온다. query에 Gmail 검색 문법을 그대로 쓸 수 있다."""
    service = _get_service()
    result = service.users().messages().list(userId="me", q=query or "", maxResults=limit).execute()

    emails = []
    for ref in result.get("messages", []):
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=ref["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        emails.append(
            {
                "id": msg["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", "(제목 없음)"),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
                "unread": "UNREAD" in msg.get("labelIds", []),
            }
        )
    return emails


def get_email_content(message_id, max_chars=4000):
    """메일 하나의 본문 내용을 읽어온다."""
    service = _get_service()
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    body = _extract_plain_text(msg["payload"]) or msg.get("snippet", "")

    return {
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", "(제목 없음)"),
        "date": headers.get("Date", ""),
        "content": body[:max_chars],
    }
