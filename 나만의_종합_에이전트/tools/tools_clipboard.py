"""클립보드 읽기/쓰기 도구."""

import pyperclip


# ---------------------------------------------------------------------------
# 19. clipboard_read / clipboard_write
# ---------------------------------------------------------------------------
def clipboard_read():
    """지금 클립보드에 들어있는 텍스트를 읽어온다."""
    try:
        text = pyperclip.paste()
    except Exception as e:
        return {"error": f"클립보드를 읽을 수 없습니다: {e}"}

    if not text:
        return {"message": "클립보드가 비어 있습니다."}
    return {"text": text}


clipboard_read_tool = {
    "type": "function",
    "name": "clipboard_read",
    "description": "지금 클립보드에 복사돼 있는 텍스트를 읽어온다. '방금 복사한 거' 같은 요청에 쓴다.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}


def clipboard_write(text):
    """텍스트를 클립보드에 복사한다."""
    try:
        pyperclip.copy(text)
    except Exception as e:
        return {"error": f"클립보드에 쓸 수 없습니다: {e}"}
    return {"message": "클립보드에 복사했습니다."}


clipboard_write_tool = {
    "type": "function",
    "name": "clipboard_write",
    "description": "주어진 텍스트를 클립보드에 복사한다. 사용자가 결과를 어딘가에 붙여넣고 싶어할 때 쓴다.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "클립보드에 복사할 텍스트"},
        },
        "required": ["text"],
    },
}
