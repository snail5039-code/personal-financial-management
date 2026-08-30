"""구글 API 공용 인증 헬퍼.

credentials.json(Google Cloud Console에서 발급받은 OAuth 클라이언트)이 있어야 동작한다.
서비스마다 필요한 권한만 따로 요청하려고 토큰을 서비스별 파일에 나눠 저장한다 — 예를 들어
할일에 쓰는 토큰과 메일에 쓰는 토큰을 분리해두면, 메일 기능을 나중에 꺼도 할일 권한에는
영향이 없다. 각 서비스는 처음 쓸 때 브라우저가 열려 그 서비스에 필요한 권한만 동의를 받고,
이후에는 저장된 토큰으로 자동 재인증한다.
"""

import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# PyInstaller로 얼린 실행 파일 안에서는 __file__ 기반 경로가 exe가 실제로 있는 폴더를
# 가리키지 않는다 - sys.executable 기준으로 잡아야 credentials.json/token을 exe 옆에서
# 제대로 찾는다.
THIS_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(THIS_DIR, "credentials.json")


class GoogleServiceNotConfigured(Exception):
    """credentials.json이 없어서 구글 API를 쓸 수 없을 때."""


def get_service(api_name, api_version, scopes, token_filename, label):
    """token_filename에 저장된 토큰으로 인증해서 googleapiclient 서비스 객체를 만든다."""
    token_path = os.path.join(THIS_DIR, "data", token_filename)

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise GoogleServiceNotConfigured(
                    f"{label} 기능이 아직 설정되지 않았습니다. Google Cloud Console에서 받은 "
                    f"OAuth 클라이언트 파일을 '{CREDENTIALS_PATH}' 경로에 저장한 뒤 다시 시도해주세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, scopes)
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build(api_name, api_version, credentials=creds)
