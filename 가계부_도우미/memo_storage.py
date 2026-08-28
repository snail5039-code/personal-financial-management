"""메모를 data/memos.json 파일에 저장/불러오는 공용 헬퍼."""

import json
import os

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "memos.json")


def load_data():
    if not os.path.exists(DATA_PATH):
        return {"memos": [], "next_id": 1}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
