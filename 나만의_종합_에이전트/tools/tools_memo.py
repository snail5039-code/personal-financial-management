"""메모 도구. 데이터는 memo_storage.py(data/memos.json)에 저장한다."""

import datetime

from . import memo_storage
from . import undo


def _save_snapshot(data):
    snapshot = undo.copy_of(data)
    undo.record(lambda: memo_storage.save_data(snapshot))


# ---------------------------------------------------------------------------
# 13. memo_add / memo_search / memo_Delete
# ---------------------------------------------------------------------------
def memo_add(text, tags=None):
    """짧은 메모를 저장한다. tags는 쉼표로 구분된 문자열."""
    data = memo_storage.load_data()
    _save_snapshot(data)

    memo = {
        "id": data["next_id"],
        "text": text,
        "tags": [t.strip() for t in tags.split(",") if t.strip()] if tags else [],
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    data["memos"].append(memo)
    data["next_id"] += 1
    memo_storage.save_data(data)
    return {"message": "메모를 저장했습니다.", "id": memo["id"], "text": memo["text"]}


memo_add_tool = {
    "type": "function",
    "name": "memo_add",
    "description": "짧은 메모를 저장한다.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "메모 내용"},
            "tags": {"type": "string", "description": "쉼표로 구분한 태그 (선택, 예: '아이디어,장보기')"},
        },
        "required": ["text"],
    },
}


def memo_search(query=None, tag=None):
    """메모를 조회한다. query가 있으면 내용에 포함된 메모만, tag가 있으면 해당 태그가 붙은 메모만 필터링한다."""
    data = memo_storage.load_data()
    memos = data["memos"]

    if query is not None:
        memos = [m for m in memos if query in m["text"]]
    if tag is not None:
        memos = [m for m in memos if tag in m["tags"]]

    if not memos:
        return {"message": "일치하는 메모를 찾을 수 없습니다."}
    return memos


memo_search_tool = {
    "type": "function",
    "name": "memo_search",
    "description": "저장된 메모를 조회한다. query/tag는 모두 선택 입력이며 입력된 조건만 적용해 필터링한다.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "메모 내용에서 찾을 검색어 (선택)"},
            "tag": {"type": "string", "description": "찾을 태그 (선택)"},
        },
        "required": [],
    },
}


def memo_Delete(id=None, query=None):
    """id 또는 내용 검색어로 찾은 메모를 삭제한다."""
    data = memo_storage.load_data()

    if id is not None:
        target = next((m for m in data["memos"] if m["id"] == id), None)
        if target is None:
            return {"message": f"id {id}에 해당하는 메모를 찾을 수 없습니다."}
    else:
        if not query:
            return {"message": "id가 없으면 검색어(query)가 있어야 메모를 찾을 수 있습니다."}
        candidates = [m for m in data["memos"] if query in m["text"]]
        if not candidates:
            return {"message": "일치하는 메모를 찾을 수 없습니다."}
        if len(candidates) > 1:
            return {
                "message": "조건에 맞는 메모가 여러 건이라 하나로 특정할 수 없습니다. 더 구체적으로 말씀해주세요.",
                "candidates": candidates,
            }
        target = candidates[0]

    _save_snapshot(data)
    data["memos"].remove(target)
    memo_storage.save_data(data)
    return {"message": f"메모('{target['text']}')를 삭제했습니다."}


memo_Delete_tool = {
    "type": "function",
    "name": "memo_Delete",
    "description": (
        "메모를 삭제한다. id를 알고 있으면 id로, 모르면 query(내용 부분 일치)로 찾아 삭제한다. "
        "조건에 맞는 메모가 여러 건이면 더 구체적인 정보를 요청한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "삭제할 메모의 id"},
            "query": {"type": "string", "description": "id를 모를 때 내용으로 찾기 위한 검색어"},
        },
        "required": [],
    },
}


# ---------------------------------------------------------------------------
