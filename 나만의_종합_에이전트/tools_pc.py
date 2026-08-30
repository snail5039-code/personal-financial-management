"""PC 제어 도구 (앱 실행/종료, 볼륨, 화면 잠금).

app_close처럼 저장 안 된 작업을 날릴 수 있는 동작은 tools.CONFIRM_MESSAGES에 등록해서
app.py가 실행 전에 터미널에서 사용자 확인을 받는다.
"""

import ctypes
import os

import psutil
from pycaw.utils import AudioUtilities


def _volume_interface():
    return AudioUtilities.GetSpeakers().EndpointVolume


# ---------------------------------------------------------------------------
# 21. app_launch
# ---------------------------------------------------------------------------
def app_launch(target):
    """앱이나 파일을 실행한다. PATH에 등록된 실행 파일 이름 또는 전체 경로를 받는다."""
    try:
        os.startfile(target)
    except OSError as e:
        return {"error": f"'{target}'를 실행할 수 없습니다: {e}. 정확한 실행 파일 이름이나 전체 경로를 알려주세요."}
    return {"message": f"'{target}'를 실행했습니다."}


app_launch_tool = {
    "type": "function",
    "name": "app_launch",
    "description": (
        "앱이나 파일을 실행한다. 실행 파일 이름('notepad', 'calc', 'chrome', 'code' 등 PATH에 "
        "등록된 이름) 또는 전체 경로를 받는다. 한글로 부르는 흔한 앱 이름은 알맞은 실행 파일/명령으로 "
        "바꿔서 넘긴다 (예: '메모장'→notepad, '계산기'→calc, '크롬'→chrome, '브이에스코드'→code). "
        "실행에 실패하면 정확한 경로를 알려달라고 요청한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "실행할 프로그램 이름 또는 파일 경로"},
        },
        "required": ["target"],
    },
}


# ---------------------------------------------------------------------------
# 22. app_close
# ---------------------------------------------------------------------------
def _process_name(p):
    try:
        return (p.info.get("name") or "").lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def app_close(name):
    """이름이 일치하는 프로세스를 전부 종료한다. 저장 안 된 작업이 사라질 수 있어 확인을 거친다."""
    target = name.strip().lower()
    variants = {target, target if target.endswith(".exe") else target + ".exe"}

    all_procs = list(psutil.process_iter(["pid", "name"]))
    matched = [p for p in all_procs if _process_name(p) in variants]
    if not matched:
        # 정확히 일치하는 게 없으면 이름에 포함되는 것까지 넓혀서 찾는다 (예: 'discord' -> 'Discord.exe').
        matched = [p for p in all_procs if target in _process_name(p)]

    if not matched:
        return {"message": f"'{name}' 프로세스를 찾을 수 없습니다. 이미 꺼져 있을 수 있습니다."}

    closed, failed = [], []
    for p in matched:
        try:
            p.terminate()
            closed.append(_process_name(p))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            failed.append(_process_name(p))

    message = f"'{name}' 관련 프로세스 {len(closed)}개를 종료했습니다."
    if failed:
        message += f" {len(failed)}개는 권한 문제로 종료하지 못했습니다."
    return {"message": message, "closed": closed}


app_close_tool = {
    "type": "function",
    "name": "app_close",
    "description": (
        "이름이 일치하는 프로세스를 전부 종료한다. 같은 이름의 프로세스가 여러 개면 전부 종료한다 "
        "(일렉트론 앱 등은 보통 여러 개 떠 있다). 저장되지 않은 작업이 사라질 수 있어 실행 전 "
        "사용자 확인을 거친다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "종료할 프로그램 이름 (예: 'Discord', 'chrome')"},
        },
        "required": ["name"],
    },
}


# ---------------------------------------------------------------------------
# 23. volume_set / volume_mute
# ---------------------------------------------------------------------------
def volume_set(percent):
    """시스템 볼륨을 0~100 사이 값으로 설정한다."""
    percent = max(0, min(100, percent))
    try:
        _volume_interface().SetMasterVolumeLevelScalar(percent / 100, None)
    except Exception as e:
        return {"error": f"볼륨을 설정할 수 없습니다: {e}"}
    return {"message": f"볼륨을 {percent}%로 설정했습니다."}


volume_set_tool = {
    "type": "function",
    "name": "volume_set",
    "description": "시스템 볼륨을 0~100 사이 값으로 설정한다.",
    "parameters": {
        "type": "object",
        "properties": {
            "percent": {"type": "integer", "description": "설정할 볼륨 (0~100)"},
        },
        "required": ["percent"],
    },
}


def volume_mute(mute=True):
    """시스템 음소거를 켜거나 끈다."""
    try:
        _volume_interface().SetMute(1 if mute else 0, None)
    except Exception as e:
        return {"error": f"음소거 설정을 바꿀 수 없습니다: {e}"}
    return {"message": "음소거했습니다." if mute else "음소거를 해제했습니다."}


volume_mute_tool = {
    "type": "function",
    "name": "volume_mute",
    "description": "시스템 음소거를 켜거나 끈다.",
    "parameters": {
        "type": "object",
        "properties": {
            "mute": {"type": "boolean", "description": "true면 음소거, false면 음소거 해제 (기본 true)"},
        },
        "required": [],
    },
}


# ---------------------------------------------------------------------------
# 24. lock_screen
# ---------------------------------------------------------------------------
def lock_screen():
    """화면을 잠근다 (Windows 잠금 화면으로 전환). 로그인하면 그대로 돌아온다."""
    try:
        ctypes.windll.user32.LockWorkStation()
    except Exception as e:
        return {"error": f"화면을 잠글 수 없습니다: {e}"}
    return {"message": "화면을 잠갔습니다."}


lock_screen_tool = {
    "type": "function",
    "name": "lock_screen",
    "description": "지금 화면을 잠근다 (Windows 잠금 화면으로 전환).",
    "parameters": {"type": "object", "properties": {}, "required": []},
}
