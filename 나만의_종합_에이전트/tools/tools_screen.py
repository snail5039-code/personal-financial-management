"""화면 인식 도구. 스크린샷을 찍어 Gemini에게 직접 보여준다.

app.py의 execute_tool_call이 이 도구의 결과에 file_path가 있으면 이미지 콘텐츠를 붙여서
같은 턴 안에서 Gemini가 화면을 직접 "보고" 답하게 한다. 별도 OCR 엔진 없이 Gemini의
멀티모달 입력을 그대로 쓴다.
"""

import datetime
import os
import sys

from PIL import ImageGrab

# PyInstaller로 얼린 실행 파일 안에서는 __file__ 기반 경로가 exe가 실제로 있는 폴더를
# 가리키지 않는다 - sys.executable 기준으로 잡아야 data를 exe 옆에서 제대로 찾는다.
_THIS_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(__file__))
SCREENSHOT_DIR = os.path.join(_THIS_DIR, "data", "screenshots")


# ---------------------------------------------------------------------------
# 20. screen_capture
# ---------------------------------------------------------------------------
def screen_capture():
    """지금 화면을 캡처한다. 캡처한 이미지는 이 도구 호출 직후 Gemini에게 그대로 보여진다."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(SCREENSHOT_DIR, f"screen_{timestamp}.png")

    try:
        image = ImageGrab.grab()
        image.save(filepath, "PNG")
    except Exception as e:
        return {"error": f"화면 캡처에 실패했습니다: {e}"}

    return {"message": "화면을 캡처했습니다.", "file_path": filepath}


screen_capture_tool = {
    "type": "function",
    "name": "screen_capture",
    "description": (
        "지금 화면을 캡처해서 직접 본다. 화면에 뭐가 떠 있는지, 오류 메시지가 뭔지, 화면 속 표나 "
        "글자 내용을 확인해달라는 요청에 이 도구를 쓴다. 캡처한 화면은 이 도구 호출 직후 바로 "
        "보여지므로, 다시 요청하지 말고 그 화면 내용을 근거로 답한다."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}
