"""거래 내역을 data/transactions.json 파일에 저장/불러오는 공용 헬퍼."""

import json
import os
import sys

# PyInstaller로 얼린 실행 파일 안에서는 __file__ 기반 경로가 exe가 실제로 있는 폴더를
# 가리키지 않는다 - sys.executable 기준으로 잡아야 data를 exe 옆에서 제대로 찾는다.
_THIS_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(__file__))
DATA_PATH = os.path.join(_THIS_DIR, "data", "transactions.json")

DEFAULT_CATEGORIES = ["식비", "필요 지출", "의류비", "운동", "일상생활", "기타"]


def load_data():
    """저장된 거래 내역, 예산, 카테고리 목록을 불러온다. 파일이 없으면 기본 구조를 반환한다."""
    if not os.path.exists(DATA_PATH):
        return {
            "transactions": [],
            "budgets": {},
            "next_id": 1,
            "categories": list(DEFAULT_CATEGORIES),
        }
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("categories", list(DEFAULT_CATEGORIES))
    return data


def save_data(data):
    """거래 내역과 예산 정보를 파일에 저장한다."""
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
