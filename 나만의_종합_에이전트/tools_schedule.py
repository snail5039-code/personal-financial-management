"""자동 아침 브리핑 · 회의 선제 알림 설정 도구.

여기서 바꾸는 건 설정 파일(data/schedule.json)뿐이다. 실제로 그 시각에 알림을 보내거나
캘린더를 확인해서 미리 알려주는 건 별도로 띄워둔 tray_app.py가 이 파일을 주기적으로
읽어서 하므로, 트레이 앱이 켜져 있어야 실제로 작동한다.
"""

import json
import os
import re
import sys

# PyInstaller로 얼린 실행 파일 안에서는 __file__ 기반 경로가 exe가 실제로 있는 폴더를
# 가리키지 않는다 - sys.executable 기준으로 잡아야 data를 exe 옆에서 제대로 찾는다.
_THIS_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(__file__)
SCHEDULE_PATH = os.path.join(_THIS_DIR, "data", "schedule.json")
DEFAULT_SCHEDULE = {
    "briefing_time": "09:00",
    "enabled": True,
    "meeting_reminder_enabled": True,
    "meeting_reminder_minutes": 10,
}

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _load():
    if not os.path.exists(SCHEDULE_PATH):
        return dict(DEFAULT_SCHEDULE)
    try:
        with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SCHEDULE)
    for key, value in DEFAULT_SCHEDULE.items():
        data.setdefault(key, value)
    return data


def _save(data):
    os.makedirs(os.path.dirname(SCHEDULE_PATH), exist_ok=True)
    with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 34. get_briefing_schedule / set_briefing_time / set_briefing_enabled
# ---------------------------------------------------------------------------
def get_briefing_schedule():
    """지금 설정된 아침 브리핑 시각과 켜짐/꺼짐 상태를 확인한다."""
    return _load()


get_briefing_schedule_tool = {
    "type": "function",
    "name": "get_briefing_schedule",
    "description": (
        "자동 아침 브리핑이 몇 시에 오는지, 켜져 있는지 확인한다. "
        "커리마 트레이 앱(tray_app.py)이 실행 중이어야 실제로 알림이 온다."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}


def set_briefing_time(time):
    """아침 브리핑 시각을 HH:MM(24시간제) 형식으로 바꾼다."""
    if not TIME_PATTERN.match(time):
        return {"error": "시간은 HH:MM 형식(00:00~23:59)으로 알려주세요."}

    data = _load()
    data["briefing_time"] = time
    _save(data)
    return {
        "message": f"아침 브리핑 시각을 {time}로 설정했습니다. 트레이 앱이 켜져 있어야 실제로 알림이 옵니다.",
        "briefing_time": time,
    }


set_briefing_time_tool = {
    "type": "function",
    "name": "set_briefing_time",
    "description": "자동 아침 브리핑 시각을 바꾼다. 예: '아침 브리핑 8시로 바꿔줘' → time='08:00'.",
    "parameters": {
        "type": "object",
        "properties": {
            "time": {"type": "string", "description": "브리핑 시각 (HH:MM, 24시간제, 예: '08:00')"},
        },
        "required": ["time"],
    },
}


def set_briefing_enabled(enabled):
    """자동 아침 브리핑 알림을 켜거나 끈다."""
    data = _load()
    data["enabled"] = enabled
    _save(data)
    return {"message": "자동 아침 브리핑을 켰습니다." if enabled else "자동 아침 브리핑을 껐습니다."}


set_briefing_enabled_tool = {
    "type": "function",
    "name": "set_briefing_enabled",
    "description": "자동 아침 브리핑 알림을 켜거나 끈다.",
    "parameters": {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean", "description": "true면 켜기, false면 끄기"},
        },
        "required": ["enabled"],
    },
}


# ---------------------------------------------------------------------------
# 37. set_meeting_reminder_minutes / set_meeting_reminder_enabled
# ---------------------------------------------------------------------------
def set_meeting_reminder_minutes(minutes):
    """구글 캘린더 일정 시작 몇 분 전에 미리 알려줄지 설정한다."""
    if not isinstance(minutes, int) or not (1 <= minutes <= 120):
        return {"error": "1~120분 사이로 알려주세요."}

    data = _load()
    data["meeting_reminder_minutes"] = minutes
    _save(data)
    return {
        "message": f"일정 시작 {minutes}분 전에 알려드리도록 설정했습니다. 트레이 앱이 켜져 있어야 실제로 알림이 옵니다.",
        "meeting_reminder_minutes": minutes,
    }


set_meeting_reminder_minutes_tool = {
    "type": "function",
    "name": "set_meeting_reminder_minutes",
    "description": "구글 캘린더 일정이 시작하기 몇 분 전에 미리 알려줄지 설정한다 (1~120분).",
    "parameters": {
        "type": "object",
        "properties": {
            "minutes": {"type": "integer", "description": "일정 시작 몇 분 전에 알릴지 (1~120)"},
        },
        "required": ["minutes"],
    },
}


def set_meeting_reminder_enabled(enabled):
    """캘린더 일정 선제 알림을 켜거나 끈다."""
    data = _load()
    data["meeting_reminder_enabled"] = enabled
    _save(data)
    return {"message": "일정 선제 알림을 켰습니다." if enabled else "일정 선제 알림을 껐습니다."}


set_meeting_reminder_enabled_tool = {
    "type": "function",
    "name": "set_meeting_reminder_enabled",
    "description": "구글 캘린더 일정이 시작하기 전에 미리 알려주는 기능을 켜거나 끈다.",
    "parameters": {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean", "description": "true면 켜기, false면 끄기"},
        },
        "required": ["enabled"],
    },
}
