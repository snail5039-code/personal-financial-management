"""파일 관리 도구 (검색/열기/읽기/복사/이동/이름변경/삭제).

이동·이름변경은 undo.py에 되돌리는 방법을 기록해서 undo_last_action으로 되돌릴 수 있다.
삭제는 완전히 지우지 않고 휴지통으로 보내서, 운영체제 자체의 복구 기능을 그대로 쓴다.
"""

import os
import shutil

import send2trash

import undo

# 시스템 전체를 훑지 않도록 검색 기본 범위를 사용자 홈 폴더로 한정한다.
DEFAULT_SEARCH_ROOT = os.path.expanduser("~")

# 훑어봐야 의미 없고 느리기만 한 폴더들.
SKIP_DIR_NAMES = {"node_modules", "__pycache__", "AppData", "$RECYCLE.BIN", "System Volume Information"}

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log", ".py", ".js", ".ts", ".html", ".css", ".yml", ".yaml"}


# ---------------------------------------------------------------------------
# 25. file_search
# ---------------------------------------------------------------------------
def file_search(query, path=None, limit=20):
    """파일 이름에 query가 포함된 파일을 path(기본: 사용자 홈 폴더) 아래에서 찾는다."""
    root = path or DEFAULT_SEARCH_ROOT
    if not os.path.isdir(root):
        return {"error": f"'{root}' 폴더를 찾을 수 없습니다."}

    query_lower = query.lower()
    matches = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".")]
        for filename in filenames:
            if query_lower in filename.lower():
                matches.append(os.path.join(dirpath, filename))
                if len(matches) >= limit:
                    return {
                        "count": len(matches),
                        "files": matches,
                        "message": f"{limit}건을 찾고 검색을 멈췄습니다. 더 구체적인 검색어면 좁혀집니다.",
                    }

    if not matches:
        return {"message": f"'{query}'가 포함된 파일을 '{root}' 아래에서 찾을 수 없습니다."}
    return {"count": len(matches), "files": matches}


file_search_tool = {
    "type": "function",
    "name": "file_search",
    "description": (
        "파일 이름에 검색어가 포함된 파일을 찾는다. path를 지정하지 않으면 사용자 홈 폴더 아래에서 "
        "찾고, 최대 20건까지만 보여준다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "파일 이름에서 찾을 검색어"},
            "path": {"type": "string", "description": "검색할 폴더 경로 (선택, 기본은 사용자 홈 폴더)"},
        },
        "required": ["query"],
    },
}


# ---------------------------------------------------------------------------
# 26. file_open
# ---------------------------------------------------------------------------
def file_open(path):
    """파일을 그 파일의 기본 프로그램으로 연다."""
    if not os.path.exists(path):
        return {"error": f"'{path}' 파일을 찾을 수 없습니다."}
    try:
        os.startfile(path)
    except OSError as e:
        return {"error": f"'{path}'를 열 수 없습니다: {e}"}
    return {"message": f"'{path}'를 열었습니다."}


file_open_tool = {
    "type": "function",
    "name": "file_open",
    "description": "파일을 그 파일의 기본 프로그램으로 연다.",
    "parameters": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "열 파일의 전체 경로"}},
        "required": ["path"],
    },
}


# ---------------------------------------------------------------------------
# 27. file_read_text
# ---------------------------------------------------------------------------
def file_read_text(path, max_chars=4000):
    """텍스트 계열 파일의 내용을 읽어온다. 너무 크면 앞부분만 잘린다."""
    if not os.path.exists(path):
        return {"error": f"'{path}' 파일을 찾을 수 없습니다."}

    ext = os.path.splitext(path)[1].lower()
    if ext not in TEXT_EXTENSIONS:
        return {"error": f"'{ext or '(확장자 없음)'}' 형식은 지원하지 않습니다. 텍스트 계열 파일만 읽을 수 있습니다."}

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars + 1)
    except OSError as e:
        return {"error": f"파일을 읽을 수 없습니다: {e}"}

    truncated = len(content) > max_chars
    return {"path": path, "content": content[:max_chars], "truncated": truncated}


file_read_text_tool = {
    "type": "function",
    "name": "file_read_text",
    "description": (
        "텍스트 계열 파일(.txt/.md/.csv/.json/.log/.py 등)의 내용을 읽어온다. 파일을 요약해달라는 "
        "요청에는 먼저 이 도구로 내용을 읽고 그 내용을 근거로 답한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "읽을 파일의 전체 경로"}},
        "required": ["path"],
    },
}


# ---------------------------------------------------------------------------
# 28. file_copy
# ---------------------------------------------------------------------------
def file_copy(source, destination):
    """파일을 복사한다. 원본은 그대로 남는다. 대상 위치에 같은 이름의 파일이 있으면 거부한다."""
    if not os.path.exists(source):
        return {"error": f"'{source}' 파일을 찾을 수 없습니다."}
    if os.path.isdir(destination):
        destination = os.path.join(destination, os.path.basename(source))
    if os.path.exists(destination):
        return {"error": f"'{destination}'에 이미 파일이 있습니다. 다른 이름을 알려주세요."}

    try:
        shutil.copy2(source, destination)
    except OSError as e:
        return {"error": f"복사에 실패했습니다: {e}"}
    return {"message": f"'{source}'를 '{destination}'로 복사했습니다.", "destination": destination}


file_copy_tool = {
    "type": "function",
    "name": "file_copy",
    "description": "파일을 복사한다. 원본은 그대로 남는다. 대상 위치에 같은 이름의 파일이 있으면 거부한다.",
    "parameters": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "복사할 파일의 전체 경로"},
            "destination": {"type": "string", "description": "복사될 위치 (폴더 또는 새 파일 경로)"},
        },
        "required": ["source", "destination"],
    },
}


# ---------------------------------------------------------------------------
# 29. file_move
# ---------------------------------------------------------------------------
def file_move(source, destination):
    """파일을 다른 위치로 이동한다. 되돌리기를 지원한다."""
    if not os.path.exists(source):
        return {"error": f"'{source}' 파일을 찾을 수 없습니다."}
    if os.path.isdir(destination):
        destination = os.path.join(destination, os.path.basename(source))
    if os.path.exists(destination):
        return {"error": f"'{destination}'에 이미 파일이 있습니다. 다른 이름을 알려주세요."}

    try:
        shutil.move(source, destination)
    except OSError as e:
        return {"error": f"이동에 실패했습니다: {e}"}

    undo.record(lambda src=source, dst=destination: shutil.move(dst, src))
    return {"message": f"'{source}'를 '{destination}'로 이동했습니다.", "destination": destination}


file_move_tool = {
    "type": "function",
    "name": "file_move",
    "description": (
        "파일을 다른 위치로 이동한다. 대상 위치에 같은 이름의 파일이 있으면 거부한다. "
        "실행 전 사용자 확인을 거친다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "이동할 파일의 전체 경로"},
            "destination": {"type": "string", "description": "이동할 위치 (폴더 또는 새 파일 경로)"},
        },
        "required": ["source", "destination"],
    },
}


# ---------------------------------------------------------------------------
# 30. file_rename
# ---------------------------------------------------------------------------
def file_rename(path, new_name):
    """파일 이름을 바꾼다. 되돌리기를 지원한다."""
    if not os.path.exists(path):
        return {"error": f"'{path}' 파일을 찾을 수 없습니다."}
    new_path = os.path.join(os.path.dirname(path), new_name)
    if os.path.exists(new_path):
        return {"error": f"'{new_name}' 이름의 파일이 이미 있습니다."}

    try:
        os.rename(path, new_path)
    except OSError as e:
        return {"error": f"이름 변경에 실패했습니다: {e}"}

    undo.record(lambda old=path, new=new_path: os.rename(new, old))
    return {"message": f"'{path}'를 '{new_path}'로 이름을 바꿨습니다.", "new_path": new_path}


file_rename_tool = {
    "type": "function",
    "name": "file_rename",
    "description": (
        "파일 이름을 바꾼다. 같은 폴더에 이미 그 이름의 파일이 있으면 거부한다. "
        "실행 전 사용자 확인을 거친다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "이름을 바꿀 파일의 전체 경로"},
            "new_name": {"type": "string", "description": "새 파일 이름 (경로 없이 이름만)"},
        },
        "required": ["path", "new_name"],
    },
}


# ---------------------------------------------------------------------------
# 31. file_delete
# ---------------------------------------------------------------------------
def file_delete(path):
    """파일을 완전히 지우지 않고 휴지통으로 보낸다."""
    if not os.path.exists(path):
        return {"error": f"'{path}' 파일을 찾을 수 없습니다."}
    try:
        send2trash.send2trash(path)
    except Exception as e:
        return {"error": f"휴지통으로 보내지 못했습니다: {e}"}
    return {"message": f"'{path}'를 휴지통으로 보냈습니다. 필요하면 휴지통에서 복구할 수 있습니다."}


file_delete_tool = {
    "type": "function",
    "name": "file_delete",
    "description": (
        "파일을 삭제한다. 완전히 지우지 않고 휴지통으로 보내서 필요하면 복구할 수 있다. "
        "실행 전 사용자 확인을 거친다."
    ),
    "parameters": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "삭제할 파일의 전체 경로"}},
        "required": ["path"],
    },
}
