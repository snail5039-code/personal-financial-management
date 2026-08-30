"""커리마 트레이 앱 - 컴퓨터를 켜두는 동안 백그라운드에서 상주한다.

이 프로세스가 하는 일은 네 가지다:
1. data/schedule.json에 설정된 시각에 아침 뉴스 브리핑 알림을 보낸다
   ('아침 브리핑 8시로 바꿔줘'처럼 app.py 대화 중에 tools_schedule로 설정 가능)
2. 다운로드 폴더에 새 파일이 생기면 알림을 보낸다
3. "커리마"라고 부르면 듣고 명령을 처리한다 (voice_assistant.py, 트레이 메뉴에서 끄고 켤 수 있음)
4. 구글 캘린더 일정이 곧 시작하면 먼저 알려준다 (선제적 제안, 캘린더 연동이 돼 있어야 동작)

app.py(대화형 CLI)와는 별개 프로세스다. 트레이 아이콘에서 '커리마 열기'를 누르면 새 콘솔
창에서 app.py를 띄운다. Windows 시작 시 자동으로 뜨게 하려면 이 스크립트의 바로가기를
`shell:startup` 폴더에 넣으면 된다 (직접 만들어야 하는 설정이라 이 스크립트는 손대지 않는다).
"""

import datetime
import os
import shutil
import subprocess
import sys
import threading

import comtypes.client
import pystray
import pythoncom
import pyttsx3
from PIL import Image, ImageDraw
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from winotify import Notification, audio

# comtypes는 COM 타입라이브러리 래퍼 코드(pyttsx3가 쓰는 SAPI5 포함)를 보통 디스크에
# 캐시하는데, PyInstaller로 얼린 실행 파일 안에서는 그 캐시 위치에 못 쓸 수 있다(알려진
# 이슈). 매번 메모리에서 새로 만들게 해서 이 문제를 피한다 - 시작 속도에 미미한 영향만 있음.
comtypes.client.gen_dir = None

try:
    import app as kurima_app
    import google_calendar
    import tools_news
    import tools_schedule
    import voice_assistant
except Exception as e:
    # 이 프로세스는 콘솔 창 없이(또는 자동 시작으로) 뜰 수도 있어서, 여기서 실패하면 사용자가
    # 원인을 볼 방법이 없다 - 트레이 아이콘이 "떴다가 바로 사라지는" 원래 버그가 다시 벌어진다.
    # 메시지박스로 무조건 눈에 보이게 띄우고 종료한다 (GEMINI_API_KEY 미설정이 가장 흔한 원인).
    import ctypes

    ctypes.windll.user32.MessageBoxW(
        0, f"커리마를 시작할 수 없습니다.\n\n{e}", "커리마", 0x10
    )
    sys.exit(1)

# PyInstaller로 얼린 실행 파일 안에서는 __file__ 기반 경로가 exe가 실제로 있는 폴더를
# 가리키지 않는다 - sys.executable 기준으로 잡아야 data 폴더 등을 exe 옆에서 제대로 찾는다.
THIS_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
ASSISTANT_NAME = "커리마"

DOWNLOADS_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
CHECK_INTERVAL_SECONDS = 30
PROACTIVE_CHECK_INTERVAL_SECONDS = 60
# 브라우저가 다운로드 도중에 만드는 임시 파일 확장자. 이것들은 '다운로드 완료'가 아니라서 건너뛴다.
IN_PROGRESS_EXTENSIONS = (".crdownload", ".tmp", ".part", ".download")


def notify(title, message):
    # winotify는 기본이 무음 알림이라(set_audio를 안 부르면 계속 조용함), 효과음이 나도록 명시한다.
    n = Notification(
        app_id=ASSISTANT_NAME, title=title, msg=message, duration="long", icon=_ensure_icon_file()
    )
    n.set_audio(audio.Default, loop=False)
    n.show()


def speak(text):
    """텍스트를 한국어 음성으로 읽는다 (pyttsx3, 오프라인, 무료).

    pyttsx3의 Windows SAPI5 드라이버는 엔진 하나를 재사용해서 say()+runAndWait()를
    두 번째 부르면 멈추거나 실패하는 문제가 잘 알려져 있다. 그래서 호출마다 새 엔진을
    만들어 쓰고 버린다 (호출당 몇십 ms 정도만 더 든다).

    이 함수는 별도 스레드(음성 웨이크워드 루프)에서 반복 호출되는데, 그 스레드는 COM이
    자동으로 초기화돼 있지 않아서 어떤 호출에서는 되다가 어떤 호출에서는 "CoInitialize가
    호출되지 않았습니다" 오류로 조용히 실패하는 문제가 있었다. 매 호출마다 명시적으로
    COM을 초기화하고 끝나면 해제해서, 이 스레드의 COM 상태에 의존하지 않게 한다.
    """
    pythoncom.CoInitialize()
    try:
        engine = pyttsx3.init()
        for voice in engine.getProperty("voices"):
            if "KO-KR" in voice.id.upper():
                engine.setProperty("voice", voice.id)
                break
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    finally:
        pythoncom.CoUninitialize()


def _make_icon_image():
    """app.py의 실루엣 마스코트 도트맵(MASCOT_MAP)을 그대로 픽셀 그림으로 그린다.
    두 군데서 마스코트 모양을 따로 관리하면 어긋나기 쉬우니 app.py 걸 그대로 재사용한다."""
    rows = kurima_app.MASCOT_MAP
    cell = 4
    mascot_width = len(rows[0]) * cell
    mascot_height = len(rows) * cell

    # 정사각형이 아니면 트레이 아이콘으로 축소될 때 비율이 눌려 보이므로, 정사각형
    # 캔버스 가운데에 마스코트를 배치한다.
    size = max(mascot_width, mascot_height)
    offset_x = (size - mascot_width) // 2
    offset_y = (size - mascot_height) // 2

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char == " ":
                continue
            # B=몸통, 그 외(눈/가슴 화면)는 전부 어두운 색으로 뭉뚱그린다 - 이 크기에서는
            # 가슴 화면 속 글자(</>)까지 살릴 필요가 없다.
            color = kurima_app.MASCOT_COLOR if char == "B" else kurima_app.MASCOT_EYE_COLOR
            draw.rectangle(
                [
                    offset_x + x * cell,
                    offset_y + y * cell,
                    offset_x + x * cell + cell - 1,
                    offset_y + y * cell + cell - 1,
                ],
                fill=color,
            )

    # Windows 트레이는 64x64 크기에서 안정적으로 표시되는 걸 이미 확인했으니, 도트 느낌이
    # 살도록 NEAREST로 그 크기에 맞춘다(부드럽게 블러 처리되는 기본 리샘플링은 피한다).
    return img.resize((64, 64), Image.NEAREST)


_ICON_PATH = os.path.join(THIS_DIR, "data", "mascot_icon.png")
_icon_file_ready = False


def _ensure_icon_file():
    """winotify는 아이콘을 이미지 파일 경로로 받기 때문에, 마스코트 그림을 파일로 한 번 저장해둔다."""
    global _icon_file_ready
    if not _icon_file_ready:
        os.makedirs(os.path.dirname(_ICON_PATH), exist_ok=True)
        _make_icon_image().save(_ICON_PATH)
        _icon_file_ready = True
    return _ICON_PATH


# ---------------------------------------------------------------------------
# 아침 브리핑 스케줄러 - 별도 스레드에서 30초마다 시각을 확인한다.
# ---------------------------------------------------------------------------
def _send_morning_briefing():
    result = tools_news.news_briefing()
    items = result.get("items") if isinstance(result, dict) else None
    if not items:
        notify(f"{ASSISTANT_NAME} 아침 브리핑", "오늘의 뉴스를 가져오지 못했어요. 나중에 다시 시도합니다.")
        return

    first = items[0]
    rest = len(items) - 1
    message = f"[{first['category']}] {first['title']}"
    if rest > 0:
        message += f"\n그 외 {rest}건 — 커리마를 열어 확인하세요."
    notify(f"{ASSISTANT_NAME} 아침 브리핑", message)


def _briefing_loop(stop_event):
    last_sent_date = None
    while not stop_event.is_set():
        try:
            schedule = tools_schedule.get_briefing_schedule()
            now = datetime.datetime.now()
            today = now.strftime("%Y-%m-%d")
            if (
                schedule["enabled"]
                and now.strftime("%H:%M") == schedule["briefing_time"]
                and last_sent_date != today
            ):
                _send_morning_briefing()
                last_sent_date = today
        except Exception:
            pass  # 한 번의 실패로 백그라운드 루프 자체가 죽으면 안 된다.

        stop_event.wait(CHECK_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# 다운로드 폴더 감시
# ---------------------------------------------------------------------------
class _DownloadHandler(FileSystemEventHandler):
    def _notify_if_complete(self, path, is_directory):
        if is_directory:
            return
        if path.endswith(IN_PROGRESS_EXTENSIONS):
            return
        notify(f"{ASSISTANT_NAME} 다운로드 완료", os.path.basename(path))

    def on_created(self, event):
        self._notify_if_complete(event.src_path, event.is_directory)

    def on_moved(self, event):
        # 크롬 계열 브라우저는 '파일명.crdownload'로 받다가 완료되면 최종 파일명으로
        # 이름을 바꾼다(rename). 이건 on_created가 아니라 on_moved로 잡힌다.
        self._notify_if_complete(event.dest_path, event.is_directory)


def _start_download_watch():
    if not os.path.isdir(DOWNLOADS_DIR):
        return None
    observer = Observer()
    observer.schedule(_DownloadHandler(), DOWNLOADS_DIR, recursive=False)
    observer.start()
    return observer


# ---------------------------------------------------------------------------
# 선제적 제안 - 곧 시작하는 캘린더 일정을 먼저 알려준다.
# ---------------------------------------------------------------------------
def _check_upcoming_events(lead_minutes, notified_event_ids):
    now = datetime.datetime.now().astimezone()
    window_end_date = (now + datetime.timedelta(minutes=lead_minutes)).strftime("%Y-%m-%d")

    try:
        events = google_calendar.list_events(now.strftime("%Y-%m-%d"), window_end_date)
    except Exception:
        return  # 캘린더 연동이 아직 안 됐거나 호출에 실패함 - 조용히 넘어가고 다음 주기에 다시 시도한다.

    for event in events:
        if event.get("all_day") or event["id"] in notified_event_ids:
            continue
        start = event.get("start")
        if not start:
            continue
        try:
            start_dt = datetime.datetime.fromisoformat(start)
        except ValueError:
            continue

        minutes_until = (start_dt - now).total_seconds() / 60
        if 0 <= minutes_until <= lead_minutes:
            notify(
                f"{ASSISTANT_NAME} 일정 알림",
                f"'{event['title']}'이(가) {round(minutes_until)}분 후 시작합니다.",
            )
            notified_event_ids.add(event["id"])


def _proactive_loop(stop_event):
    notified_event_ids = set()
    while not stop_event.is_set():
        try:
            schedule = tools_schedule.get_briefing_schedule()
            if schedule.get("meeting_reminder_enabled", True):
                lead_minutes = schedule.get("meeting_reminder_minutes", 10)
                _check_upcoming_events(lead_minutes, notified_event_ids)
        except Exception:
            pass  # 한 번의 실패로 백그라운드 루프 자체가 죽으면 안 된다.

        stop_event.wait(PROACTIVE_CHECK_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# 트레이 아이콘 · 메뉴
# ---------------------------------------------------------------------------
def _open_kurima(icon, item):
    # 얼린 실행 파일에서는 sys.executable이 tray_app 자신(KurimaTray.exe)이고 app.py도
    # 없다 - 같은 폴더의 Kurima.exe(app.py를 빌드한 결과물)를 직접 띄운다. 소스로 실행
    # 중이면(python tray_app.py) 지금까지처럼 python으로 app.py를 실행한다.
    if getattr(sys, "frozen", False):
        command = [os.path.join(THIS_DIR, "Kurima.exe")]
    else:
        command = [sys.executable, os.path.join(THIS_DIR, "app.py")]

    # CREATE_NEW_CONSOLE만 쓰면 예전 방식 콘솔(conhost)이 뜰 때가 있는데, 거기서는
    # 마스코트가 쓰는 트루컬러 배경색이 안 그려져서 실루엣이 안 보인다. Windows
    # Terminal(wt.exe)이 깔려 있으면 그걸로 열어서 제대로 보이게 한다.
    wt_path = shutil.which("wt.exe")
    if wt_path:
        subprocess.Popen([wt_path, "-d", THIS_DIR] + command)
    else:
        subprocess.Popen(command, cwd=THIS_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE)


def run():
    stop_event = threading.Event()
    voice_enabled = threading.Event()
    voice_enabled.set()  # 기본 켜짐

    observer = _start_download_watch()
    threading.Thread(target=_briefing_loop, args=(stop_event,), daemon=True).start()
    threading.Thread(target=_proactive_loop, args=(stop_event,), daemon=True).start()
    threading.Thread(
        target=voice_assistant.run_loop,
        args=(stop_event, voice_enabled, notify, speak),
        daemon=True,
    ).start()

    def _quit(icon, item):
        stop_event.set()
        if observer:
            observer.stop()
        icon.stop()

    def _toggle_voice(icon, item):
        if voice_enabled.is_set():
            voice_enabled.clear()
        else:
            voice_enabled.set()

    icon = pystray.Icon(
        "kurima",
        _make_icon_image(),
        ASSISTANT_NAME,
        menu=pystray.Menu(
            pystray.MenuItem(f"{ASSISTANT_NAME} 열기", _open_kurima, default=True),
            pystray.MenuItem(
                '음성 인식 ("커리마"라고 불러보세요)',
                _toggle_voice,
                checked=lambda item: voice_enabled.is_set(),
            ),
            pystray.MenuItem("종료", _quit),
        ),
    )
    notify(ASSISTANT_NAME, '백그라운드에서 실행 중입니다. "커리마"라고 불러보세요!')
    icon.run()


if __name__ == "__main__":
    run()
