"""구글 캘린더 연동 (조회 + 일정 추가).

google_tasks.py와 별개 토큰 파일(data/google_calendar_token.json)을 쓴다.
calendar.events 스코프는 일정(이벤트) 읽기/쓰기만 허용하고 캘린더 자체의 설정(공유 등)은
건드릴 수 없어서, 필요한 만큼만 권한을 요청하려고 이걸 쓴다.
"""

from . import google_auth

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TIMEZONE = "Asia/Seoul"

_service = None


def _get_service():
    global _service
    if _service is None:
        _service = google_auth.get_service(
            "calendar", "v3", SCOPES, "google_calendar_token.json", "구글 캘린더"
        )
    return _service


def list_events(start_date, end_date, limit=20):
    """start_date~end_date(YYYY-MM-DD, 한국 시간 기준) 사이의 일정을 시작 시각순으로 가져온다."""
    service = _get_service()
    time_min = f"{start_date}T00:00:00+09:00"
    time_max = f"{end_date}T23:59:59+09:00"

    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            timeZone=TIMEZONE,
            maxResults=limit,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = []
    for e in result.get("items", []):
        start = e.get("start", {})
        end = e.get("end", {})
        events.append(
            {
                "id": e["id"],
                "title": e.get("summary", "(제목 없음)"),
                # 시간이 있는 일정은 dateTime, 종일 일정은 date만 온다.
                "start": start.get("dateTime", start.get("date")),
                "end": end.get("dateTime", end.get("date")),
                "all_day": "date" in start and "dateTime" not in start,
                "location": e.get("location", ""),
            }
        )
    return events


def create_event(title, start_iso, end_iso, location=""):
    """start_iso~end_iso(YYYY-MM-DDTHH:MM:SS, 한국 시간 기준) 사이의 일정을 새로 만든다."""
    service = _get_service()
    body = {
        "summary": title,
        "start": {"dateTime": start_iso, "timeZone": TIMEZONE},
        "end": {"dateTime": end_iso, "timeZone": TIMEZONE},
    }
    if location:
        body["location"] = location

    event = service.events().insert(calendarId="primary", body=body).execute()
    return {
        "id": event["id"],
        "title": event.get("summary", title),
        "start": event["start"].get("dateTime"),
        "end": event["end"].get("dateTime"),
    }


def delete_event(event_id):
    service = _get_service()
    service.events().delete(calendarId="primary", eventId=event_id).execute()
