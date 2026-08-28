"""거래 내역을 data/transactions.json 파일에 저장/불러오는 공용 헬퍼."""

import json
import os

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "transactions.json")

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
