"""구글 할일(Google Tasks) API 연동.

credentials.json(Google Cloud Console에서 발급받은 OAuth 클라이언트)이 있어야 동작한다.
최초 호출 시 브라우저가 열려 구글 로그인 동의를 한 번 거치고, 이후에는
data/google_token.json에 저장된 토큰으로 자동 재인증한다.
"""

import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# PyInstaller로 얼린 실행 파일 안에서는 __file__ 기반 경로가 exe가 실제로 있는 폴더를
# 가리키지 않는다 - sys.executable 기준으로 잡아야 credentials.json/token을 exe 옆에서
# 제대로 찾는다.
THIS_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(THIS_DIR, "credentials.json")
TOKEN_PATH = os.path.join(THIS_DIR, "data", "google_token.json")
SCOPES = ["https://www.googleapis.com/auth/tasks"]

TASKLIST = "@default"

_service = None


class GoogleTasksNotConfigured(Exception):
    """credentials.json이 없어서 구글 할일 기능을 쓸 수 없을 때."""


def _get_service():
    global _service
    if _service is not None:
        return _service

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise GoogleTasksNotConfigured(
                    "구글 할일 기능이 아직 설정되지 않았습니다. Google Cloud Console에서 받은 "
                    f"OAuth 클라이언트 파일을 '{CREDENTIALS_PATH}' 경로에 저장한 뒤 다시 시도해주세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    _service = build("tasks", "v1", credentials=creds)
    return _service


def list_tasks(show_completed=False):
    """할일 목록을 가져온다. show_completed가 True면 완료된 항목도 포함한다."""
    service = _get_service()
    result = (
        service.tasks()
        .list(tasklist=TASKLIST, showCompleted=show_completed, showHidden=show_completed)
        .execute()
    )
    return result.get("items", [])


def get_task(task_id):
    """id로 할일 하나를 가져온다. 없으면 None."""
    service = _get_service()
    try:
        return service.tasks().get(tasklist=TASKLIST, task=task_id).execute()
    except HttpError:
        return None


def insert_task(title, notes=None, due=None):
    """새 할일을 등록한다. due는 'YYYY-MM-DD' 형식."""
    service = _get_service()
    body = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = f"{due}T00:00:00.000Z"
    return service.tasks().insert(tasklist=TASKLIST, body=body).execute()


def complete_task(task_id):
    """할일을 완료 상태로 바꾼다."""
    service = _get_service()
    return service.tasks().patch(
        tasklist=TASKLIST, task=task_id, body={"status": "completed"}
    ).execute()


def uncomplete_task(task_id):
    """할일을 다시 미완료 상태로 되돌린다 (완료 처리 되돌리기용)."""
    service = _get_service()
    return service.tasks().patch(
        tasklist=TASKLIST, task=task_id, body={"status": "needsAction"}
    ).execute()


def delete_task(task_id):
    """할일을 삭제한다."""
    service = _get_service()
    service.tasks().delete(tasklist=TASKLIST, task=task_id).execute()
