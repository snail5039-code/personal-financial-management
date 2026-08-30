"""할일 도구 (구글 할일 연동).

등록/완료/삭제한 항목은 같은 계정의 구글 할일 앱에도 바로 반영된다.
"""

import google_tasks
import undo


# ---------------------------------------------------------------------------
# 12. todo_registration / todo_search / todo_complete / todo_Delete
#     (구글 할일과 연동 - 등록/완료/삭제한 항목이 폰의 구글 할일 앱에도 바로 반영된다)
# ---------------------------------------------------------------------------
def _todo_error_message(e):
    if isinstance(e, google_tasks.GoogleTasksNotConfigured):
        return str(e)
    return f"구글 할일 서비스 호출에 실패했습니다: {e}"


def _restore_task(item):
    """삭제한 할일을 같은 내용으로 되살린다. 완료 상태였으면 완료로 되돌린다."""
    task = google_tasks.insert_task(
        item["title"],
        notes=item.get("notes"),
        due=(item.get("due") or "")[:10] or None,
    )
    if item.get("status") == "completed":
        google_tasks.complete_task(task["id"])


def _find_todo_by_query(query):
    """제목에 query가 포함되는 미완료 할일을 모두 찾는다."""
    return [t for t in google_tasks.list_tasks(show_completed=False) if query in t.get("title", "")]


def todo_registration(title, notes=None, due=None):
    """구글 할일에 새 항목을 등록한다. 등록하면 폰의 구글 할일 앱에도 바로 나타난다."""
    try:
        task = google_tasks.insert_task(title, notes=notes, due=due)
        # 등록을 되돌리는 건 삭제.
        undo.record(lambda task_id=task["id"]: google_tasks.delete_task(task_id))
    except Exception as e:
        return {"error": _todo_error_message(e)}
    return {"message": f"'{title}' 할일을 등록했습니다.", "id": task["id"], "title": task["title"]}


todo_registration_tool = {
    "type": "function",
    "name": "todo_registration",
    "description": "구글 할일 목록에 새 항목을 등록한다. 등록한 항목은 사용자 폰의 구글 할일 앱에도 바로 나타난다.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "할일 제목"},
            "notes": {"type": "string", "description": "할일에 대한 부가 설명 (선택)"},
            "due": {"type": "string", "description": "마감일 (YYYY-MM-DD, 선택)"},
        },
        "required": ["title"],
    },
}


def todo_search(query=None, include_completed=False):
    """할일 목록을 조회한다. query가 있으면 제목에 포함된 항목만 필터링한다."""
    try:
        tasks = google_tasks.list_tasks(show_completed=include_completed)
    except Exception as e:
        return {"error": _todo_error_message(e)}

    if query:
        tasks = [t for t in tasks if query in t.get("title", "")]
    if not tasks:
        return {"message": "일치하는 할일을 찾을 수 없습니다."}

    return [
        {
            "id": t["id"],
            "title": t["title"],
            "notes": t.get("notes", ""),
            "due": t.get("due", "")[:10],
            "completed": t.get("status") == "completed",
        }
        for t in tasks
    ]


todo_search_tool = {
    "type": "function",
    "name": "todo_search",
    "description": "구글 할일 목록을 조회한다. query를 주면 제목에 그 텍스트가 포함된 항목만 보여준다.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "할일 제목에서 찾을 검색어 (선택)"},
            "include_completed": {
                "type": "boolean",
                "description": "true면 완료된 항목도 함께 보여준다. 기본은 미완료 항목만 조회.",
            },
        },
        "required": [],
    },
}


def todo_complete(id=None, query=None):
    """id 또는 제목 검색어로 찾은 할일을 완료 처리한다."""
    try:
        if id is None:
            if not query:
                return {"message": "id가 없으면 검색어(query)가 있어야 할일을 찾을 수 있습니다."}
            matches = _find_todo_by_query(query)
            if not matches:
                return {"message": "일치하는 할일을 찾을 수 없습니다."}
            if len(matches) > 1:
                return {
                    "message": "조건에 맞는 할일이 여러 건이라 하나로 특정할 수 없습니다. 더 구체적으로 말씀해주세요.",
                    "candidates": [{"id": t["id"], "title": t["title"]} for t in matches],
                }
            id = matches[0]["id"]
        task = google_tasks.complete_task(id)
        # 완료를 되돌리는 건 다시 미완료로.
        undo.record(lambda task_id=id: google_tasks.uncomplete_task(task_id))
    except Exception as e:
        return {"error": _todo_error_message(e)}
    return {"message": f"'{task['title']}' 할일을 완료 처리했습니다."}


todo_complete_tool = {
    "type": "function",
    "name": "todo_complete",
    "description": (
        "할일을 완료 처리한다. id를 알고 있으면 id로, 모르면 query(제목 부분 일치)로 찾아 완료 처리한다. "
        "조건에 맞는 할일이 여러 건이면 더 구체적인 정보를 요청한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "완료 처리할 할일의 id"},
            "query": {"type": "string", "description": "id를 모를 때 제목으로 찾기 위한 검색어"},
        },
        "required": [],
    },
}


def todo_Delete(id=None, query=None):
    """id 또는 제목 검색어로 찾은 할일을 삭제한다."""
    try:
        if id is None:
            if not query:
                return {"message": "id가 없으면 검색어(query)가 있어야 할일을 찾을 수 있습니다."}
            matches = _find_todo_by_query(query)
            if not matches:
                return {"message": "일치하는 할일을 찾을 수 없습니다."}
            if len(matches) > 1:
                return {
                    "message": "조건에 맞는 할일이 여러 건이라 하나로 특정할 수 없습니다. 더 구체적으로 말씀해주세요.",
                    "candidates": [{"id": t["id"], "title": t["title"]} for t in matches],
                }
            target = matches[0]
        else:
            target = google_tasks.get_task(id)
            if target is None:
                return {"message": f"id {id}에 해당하는 할일을 찾을 수 없습니다."}

        google_tasks.delete_task(target["id"])
        # 삭제를 되돌리는 건 같은 내용으로 다시 만드는 것.
        # (구글 API가 완전한 복구를 지원하지 않아 id는 새로 부여된다.)
        undo.record(lambda item=dict(target): _restore_task(item))
    except Exception as e:
        return {"error": _todo_error_message(e)}
    return {"message": f"'{target['title']}' 할일을 삭제했습니다."}


todo_Delete_tool = {
    "type": "function",
    "name": "todo_Delete",
    "description": (
        "할일을 삭제한다. id를 알고 있으면 id로, 모르면 query(제목 부분 일치)로 찾아 삭제한다. "
        "조건에 맞는 할일이 여러 건이면 더 구체적인 정보를 요청한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "삭제할 할일의 id"},
            "query": {"type": "string", "description": "id를 모를 때 제목으로 찾기 위한 검색어"},
        },
        "required": [],
    },
}


def todo_clear_completed():
    """완료 처리된 할일을 모두 삭제해서 목록을 정리한다."""
    try:
        completed = [t for t in google_tasks.list_tasks(show_completed=True) if t.get("status") == "completed"]
    except Exception as e:
        return {"error": _todo_error_message(e)}

    if not completed:
        return {"message": "완료된 할일이 없습니다."}

    # 도중에 하나가 실패해도 이미 지운 것들은 되돌릴 수 있어야 하므로,
    # 하나씩 지우면서 실제로 지운 것만 따로 기록해둔다.
    deleted = []
    failure = None
    for t in completed:
        try:
            google_tasks.delete_task(t["id"])
        except Exception as e:
            failure = e
            break
        deleted.append(t)

    if deleted:
        # 정리를 되돌리는 건 지운 것들을 완료 상태 그대로 되살리는 것.
        undo.record(lambda items=[dict(t) for t in deleted]: [_restore_task(i) for i in items])

    if failure is not None:
        return {
            "error": f"{_todo_error_message(failure)} ({len(deleted)}/{len(completed)}건 삭제 후 중단했습니다.)"
        }
    return {"message": f"완료된 할일 {len(deleted)}건을 삭제했습니다."}


todo_clear_completed_tool = {
    "type": "function",
    "name": "todo_clear_completed",
    "description": "완료 처리된 할일을 모두 삭제해서 목록을 정리한다. 완료된 항목이 없으면 안내한다.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


# ---------------------------------------------------------------------------
