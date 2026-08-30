"""메모를 data/memos.json 파일에 저장/불러오는 공용 헬퍼."""

import json
import os
import sys

# PyInstaller로 얼린 실행 파일 안에서는 __file__ 기반 경로가 exe가 실제로 있는 폴더를
# 가리키지 않는다 - sys.executable 기준으로 잡아야 data를 exe 옆에서 제대로 찾는다.
_THIS_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(__file__)
DATA_PATH = os.path.join(_THIS_DIR, "data", "memos.json")


def load_data():
    if not os.path.exists(DATA_PATH):
        return {"memos": [], "next_id": 1}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
