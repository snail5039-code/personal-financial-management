"""가계부 도우미 - Claude Code 스타일 CLI

이 폴더 안의 tools/ 패키지(실제 로직)와 Gemini Interactions API 연동 로직을 쓰고,
그 위에 터미널 UI(rich)를 입힌 것이다. 기본_CLI 폴더와는 완전히 독립적인 사본이다.
"""

import datetime
import itertools
import json
import os
import pathlib
import sys

# PyInstaller로 얼린 실행 파일 안에서는 __file__ 기반 경로가 exe가 실제로 있는 폴더를
# 가리키지 않는다 - sys.executable 기준으로 잡아야 .env/credentials.json/data를 exe
# 옆에서 제대로 찾는다. 소스로 바로 실행할 때(python app.py)는 지금까지와 동일하게 동작.
THIS_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

from dotenv import load_dotenv
from google import genai
from rich.align import Align
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

import agent_cli
import tools

# tray_app.py(콘솔 없는 백그라운드 앱)가 이 모듈을 불러올 때는 sys.stdout/stdin이 아예
# None이라 reconfigure() 자체가 없다 - 터미널이 실제로 있을 때만 인코딩을 맞춘다.
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stdin is not None:
    sys.stdin.reconfigure(encoding="utf-8")
load_dotenv(os.path.join(THIS_DIR, ".env"))

MODEL = "gemini-3.6-flash"

# 트레이 아이콘의 "커리마 열기"로 띄운 창은 Rich의 터미널 감지에 필요한 환경변수
# (WT_SESSION 등)가 부모 프로세스(트레이 앱)로부터 그대로 안 내려오는 경우가 있어서,
# 실제로는 트루컬러를 지원하는 터미널인데도 마스코트 배경색이 안 그려지는 문제가 있었다.
# 환경변수 감지에 의존하지 말고 트루컬러를 강제한다.
console = Console(color_system="truecolor", force_terminal=True, legacy_windows=False)

ASSISTANT_NAME = "커리마"


def _ensure_gemini_api_key():
    """처음 설치한 사용자를 위한 최초 설정 - .env에 키가 없으면 터미널에서 직접 물어보고 저장한다.

    tray_app.py처럼 터미널 입력을 받을 수 없는 곳에서 app 모듈을 불러올 때(터미널이 없거나
    stdin이 연결 안 된 백그라운드 프로세스)는 사용자에게 물어볼 방법이 없으니, 대신 원인이
    분명한 예외를 던져서 호출한 쪽(tray_app.py)이 알아서 안내하게 한다.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key

    if not sys.stdin.isatty():
        raise RuntimeError(
            "GEMINI_API_KEY가 설정돼 있지 않습니다. 먼저 'python app.py'를 터미널에서 직접 "
            "실행해서 Gemini API 키를 등록해주세요."
        )

    console.print(f"\n[bold]{ASSISTANT_NAME}[/bold]를 처음 실행하시는군요! Gemini API 키가 필요해요.")
    console.print("무료로 발급받으려면: https://aistudio.google.com/apikey\n")
    while not key:
        key = console.input("발급받은 Gemini API 키를 붙여넣어주세요 > ").strip()

    env_path = os.path.join(THIS_DIR, ".env")
    with open(env_path, "a", encoding="utf-8") as f:
        f.write(f"GEMINI_API_KEY={key}\n")
    os.environ["GEMINI_API_KEY"] = key
    console.print("[green]저장했습니다. 다음부터는 다시 안 물어봐요.[/green]\n")
    return key


client = genai.Client(api_key=_ensure_gemini_api_key())


def build_system_instruction():
    """호출 시점의 오늘 날짜를 반영해 시스템 지시문을 새로 만든다.

    모듈 로드 시 한 번만 고정하면 자정을 넘겨 오래 켜둔 세션에서 '오늘/어제' 해석이 하루씩 밀리므로,
    매 호출마다 새로 만든다.
    """
    now = datetime.datetime.now()
    today = now.strftime("%Y-%m-%d")
    now_time = now.strftime("%H:%M")
    base = (
        f"당신의 이름은 '{ASSISTANT_NAME}'입니다. 지금은 {today} {now_time}입니다. "
        "사용자가 '오늘', '어제', '이번 달'처럼 상대적인 날짜나 '15분 후', '지금부터 1시간 뒤'처럼 "
        "상대적인 시각을 말하면 이 날짜/시각을 기준으로 계산해서 도구 호출 시 날짜는 YYYY-MM-DD, "
        "월은 YYYY-MM, 일정 시각은 YYYY-MM-DDTHH:MM:SS 형식으로 변환해서 넘기세요. "
        "거래를 등록/수정할 때 금액(amount)의 부호에 주의하세요: 지출(돈이 나가는 것)은 양수로, "
        "수입이나 환불처럼 예산에 다시 채워지는 금액은 음수로 등록해야 남은 예산이 올바르게 계산됩니다. "
        "news_briefing으로 받은 각 뉴스 항목에는 summary(실제 기사 요약문)가 이미 들어있으니, "
        "사용자가 방금 보여준 뉴스 중 하나를 더 자세히 알려달라거나 요약해달라고 하면 "
        "news_briefing을 다시 부르지 말고 대화에 이미 있는 summary를 바탕으로 답하세요. "
        "screen_capture를 호출하면 그 즉시 지금 화면 이미지가 당신에게 보여지니, 화면 내용을 묻는 "
        "질문에는 이 도구로 직접 보고 답하고 사용자에게 설명해달라고 되묻지 마세요. "
        "app_close/file_move/file_rename/file_delete/calendar_add_event처럼 되돌리기 어려운 도구는 "
        "호출하면 사용자에게 터미널(또는 음성 웨이크워드 중이면 음성)으로 직접 y/n 확인을 받은 뒤에 "
        "실행되니, 미리 괜찮은지 되묻지 말고 그냥 호출하세요. 사용자가 취소하면 결과에 그렇게 나타납니다. "
        "Gmail은 읽기 전용입니다 (메일 발송/삭제는 지원하지 않음). 구글 캘린더는 조회뿐 아니라 "
        "일정 추가(calendar_add_event)도 지원하지만, 일정 수정/삭제는 아직 지원하지 않습니다. "
        "credentials.json이 아직 없으면 도구 결과에 안내 문구가 오니 그대로 사용자에게 전달하세요. "
        "자동 아침 브리핑은 이 대화창이 아니라 별도로 띄워둔 트레이 앱(tray_app.py)이 그 시각에 "
        "윈도우 알림으로 보내는 것입니다. set_briefing_time/set_briefing_enabled는 시각/켜짐 여부만 "
        "바꾸는 것이고, 트레이 앱이 실행 중이어야 실제로 알림이 온다는 걸 사용자에게 알려주세요. "
        "local_search는 반드시 index_local_documents로 색인을 먼저 만들어야 결과가 나옵니다. "
        "색인은 문서·바탕화면 폴더를 전부 훑고 임베딩 API를 호출해서 시간이 걸리고 비용도 드니, "
        "사용자가 색인을 요청하면 시간이 좀 걸릴 수 있다고 미리 알려주고 호출하세요. "
        "당신은 개인 거래 내역/예산, 할일(구글 할일 연동), 메모를 관리하고 생활 계산(더치페이/D-day/만나이/근무일수), "
        "날씨, 환율, 경제/IT 뉴스 브리핑, PC 상태(CPU/메모리/디스크/네트워크), 클립보드, 화면 인식, "
        "PC 제어(앱 실행/종료, 볼륨, 화면 잠금), 파일 관리(검색/열기/읽기/복사/이동/이름변경/삭제), "
        "Gmail 조회, 구글 캘린더 일정 조회/추가, 자동 아침 브리핑 시각 설정, 로컬 문서 의미 기반 검색까지 "
        "도와주는 개인비서 에이전트입니다."
    )

    # 스킬은 이름 + 한 줄 설명만 여기 붙인다. 본문은 모델이 필요할 때 read_skill로 직접
    # 읽어간다(tools/tools_skill.py 참고). skills/ 폴더가 없거나 비어 있으면 빈 문자열이
    # 와서 지금까지와 완전히 동일하게 동작한다.
    skills = tools.skills_summary_for_prompt()
    if skills:
        return base + "\n\n" + skills
    return base


def create_interaction(input_data, previous_interaction_id):
    return client.interactions.create(
        model=MODEL,
        input=input_data,
        previous_interaction_id=previous_interaction_id,
        tools=tools.TOOLS,
        store=True,
        system_instruction=build_system_instruction(),
    )


SESSION_PATH = os.path.join(THIS_DIR, "data", "session.json")


def load_previous_interaction_id():
    """지난 실행에서 남겨둔 previous_interaction_id를 불러온다 (없거나 손상되면 None)."""
    if not os.path.exists(SESSION_PATH):
        return None
    try:
        with open(SESSION_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("previous_interaction_id")
    except (json.JSONDecodeError, OSError):
        return None


def save_previous_interaction_id(interaction_id):
    os.makedirs(os.path.dirname(SESSION_PATH), exist_ok=True)
    with open(SESSION_PATH, "w", encoding="utf-8") as f:
        json.dump({"previous_interaction_id": interaction_id}, f)


def safe_create_interaction(input_data, previous_interaction_id):
    """previous_interaction_id가 만료/무효화됐을 경우 새 대화로 한 번 재시도한다."""
    try:
        return create_interaction(input_data, previous_interaction_id)
    except Exception:
        if previous_interaction_id is None:
            raise
        console.print("[dim]이전 대화를 이어갈 수 없어 새로 시작합니다.[/dim]")
        return create_interaction(input_data, None)


def format_args(args):
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


CATEGORY_COLORS = ["green", "blue", "magenta", "yellow", "cyan", "red", "bright_green", "bright_blue"]


def category_style(category):
    """카테고리 이름마다 항상 같은 색이 나오도록 해시로 색을 고정 배정한다."""
    return CATEGORY_COLORS[hash(category) % len(CATEGORY_COLORS)]


def format_amount(amount):
    text = f"{amount:,}원"
    style = "red" if amount < 0 else "green"
    return Text(text, style=style)


def flat_table():
    """테두리 없는 표.

    창을 줄이면 터미널이 이미 출력된 줄을 다시 접는데, 테두리가 있으면 프레임이
    어긋나 크게 깨져 보인다. 테두리를 없애면 접혀도 그냥 줄바꿈으로만 보인다.
    """
    return Table(show_header=True, header_style="bold", box=None, pad_edge=False)


def render_search_table(results):
    table = flat_table()
    table.add_column("카테고리", no_wrap=True)
    table.add_column("날짜", no_wrap=True)
    table.add_column("금액", justify="right", no_wrap=True)
    for tx in results:
        table.add_row(
            Text(tx["category"], style=category_style(tx["category"])),
            tx["date"],
            format_amount(tx["amount"]),
        )
    return table


def render_usage_bar(percent, over_budget, width=12):
    """예산 사용률(%)을 직접 문자열로 그린 막대로 보여준다."""
    filled = min(round(percent / 100 * width), width) if percent > 0 else 0
    bar = "█" * filled + "░" * (width - filled)
    style = "red" if over_budget else "green"
    return Text(f"{bar} {percent:3.0f}%", style=style)


def over_budget_caption(results):
    """예산을 넘긴 카테고리가 있으면 경고 문구를, 없으면 None을 준다."""
    names = [r["category"] for r in results if r["remaining_amount"] < 0]
    return f"⚠ 예산 초과: {', '.join(names)}" if names else None


# 테두리 없는 예산 표가 잘리지 않고 들어가는 최소 폭.
BUDGET_TABLE_MIN_WIDTH = 64


def render_budget_columns(results):
    """폭이 넉넉할 때 쓰는 가로 표."""
    table = flat_table()
    table.add_column("카테고리", no_wrap=True)
    table.add_column("예산", justify="right", no_wrap=True)
    table.add_column("사용금액", justify="right", no_wrap=True)
    table.add_column("남은돈", justify="right", no_wrap=True)
    table.add_column("사용률", width=17, no_wrap=True)

    for row in results:
        over_budget = row["remaining_amount"] < 0
        category_cell = Text(
            ("⚠ " if over_budget else "") + row["category"],
            style="bold red" if over_budget else category_style(row["category"]),
        )
        percent = (row["used_amount"] / row["budget"] * 100) if row["budget"] else 0

        table.add_row(
            category_cell,
            f"{row['budget']:,}원",
            format_amount(row["used_amount"]),
            format_amount(row["remaining_amount"]),
            render_usage_bar(percent, over_budget),
        )

    caption = over_budget_caption(results)
    if caption:
        table.caption = caption
        table.caption_style = "bold red"

    return table


def render_budget_stacked(results):
    """폭이 좁을 때 쓰는 세로 목록. 한 줄이 35칸을 넘지 않아 창을 줄여도 접히지 않는다."""
    body = Text()
    for index, row in enumerate(results):
        over_budget = row["remaining_amount"] < 0
        percent = (row["used_amount"] / row["budget"] * 100) if row["budget"] else 0

        if index:
            body.append("\n")
        body.append(
            ("⚠ " if over_budget else "") + row["category"],
            style="bold red" if over_budget else category_style(row["category"]),
        )
        body.append("  ")
        body.append_text(render_usage_bar(percent, over_budget, width=10))
        body.append(f"\n  예산 {row['budget']:,}원", style="dim")
        body.append(f" · 사용 {row['used_amount']:,}원\n", style="dim")
        body.append("  남은돈 ")
        body.append_text(format_amount(row["remaining_amount"]))
        body.append("\n")

    caption = over_budget_caption(results)
    if caption:
        body.append(f"\n{caption}", style="bold red")

    return body


def render_budget_table(results):
    if console.width >= BUDGET_TABLE_MIN_WIDTH:
        return render_budget_columns(results)
    return render_budget_stacked(results)


def render_spending_share_chart(results):
    """카테고리별 지출이 전체 지출에서 차지하는 비중을 막대그래프로 보여준다."""
    spent = [(r["category"], max(r["used_amount"], 0)) for r in results]
    total = sum(amount for _, amount in spent)
    if total <= 0:
        return None

    # 막대까지 합친 줄이 창 폭을 넘지 않도록 좁을 때는 막대를 줄인다.
    bar_width = 20 if console.width >= 46 else 10
    body = Text()
    body.append("카테고리별 지출 비중\n", style="dim")
    for category, amount in sorted(spent, key=lambda x: x[1], reverse=True):
        share = amount / total
        filled = round(share * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        style = category_style(category)
        body.append(f"  {category:8s} ", style=style)
        body.append(f"{bar} ", style=style)
        body.append(f"{share * 100:4.1f}%\n", style="dim")

    return body


def render_todo_table(results):
    table = flat_table()
    table.add_column("완료", no_wrap=True, width=4)
    table.add_column("할일")
    table.add_column("마감일", no_wrap=True)
    for t in results:
        check = Text("✔", style="green") if t["completed"] else Text("・", style="dim")
        title_style = "dim strike" if t["completed"] else category_style(t["title"])
        table.add_row(check, Text(t["title"], style=title_style), t["due"])
    return table


def render_memo_table(results):
    table = flat_table()
    table.add_column("메모")
    table.add_column("태그", no_wrap=True)
    table.add_column("등록일", no_wrap=True)
    for m in results:
        table.add_row(m["text"], ", ".join(m["tags"]), m["created_at"])
    return table


def render_news_table(items):
    table = flat_table()
    table.add_column("분류", no_wrap=True, width=4)
    table.add_column("헤드라인")
    for item in items:
        style = "blue" if item["category"] == "경제" else "magenta"
        headline = Text(item["title"])
        if item.get("link"):
            headline.append("\n" + item["link"], style="dim underline")
        table.add_row(Text(item["category"], style=style), headline)
    return table


def render_tool_result(name, result):
    """검색/예산 조회 결과는 표로, 예산 전체 조회는 지출 비중 차트도 함께 보여준다. 해당 없으면 None."""
    if name == "transaction_search" and isinstance(result, list) and result:
        return render_search_table(result)
    if name == "transaction_Budget_Management":
        if isinstance(result, list) and result:
            chart = render_spending_share_chart(result)
            table = render_budget_table(result)
            return Group(table, chart) if chart else table
        if isinstance(result, dict) and "remaining_amount" in result:
            return render_budget_table([result])
    if name == "todo_search" and isinstance(result, list) and result:
        return render_todo_table(result)
    if name == "memo_search" and isinstance(result, list) and result:
        return render_memo_table(result)
    if name == "news_briefing" and isinstance(result, dict) and result.get("items"):
        return render_news_table(result["items"])
    return None


def _result_content(name, result):
    """function_result에 실을 콘텐츠 목록을 만든다.

    보통은 텍스트(JSON) 하나뿐이지만, screen_capture처럼 file_path를 내놓는 도구는
    이미지도 같이 실어서 Gemini가 같은 턴 안에서 화면을 직접 보게 한다.
    """
    content = [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
    if name == "screen_capture" and isinstance(result, dict) and result.get("file_path"):
        # SDK가 str은 이미 인코딩된 base64로 취급해 그대로 흘려보낸다. pathlib.Path(os.PathLike)를
        # 넘겨야 파일을 읽어 실제로 base64 인코딩한다.
        image_path = pathlib.Path(result["file_path"])
        content.append({"type": "image", "data": image_path, "mime_type": "image/png"})
    return content


def _confirm_risky_action(message):
    """위험한 동작을 실행하기 전에 터미널에서 y/n으로 확인받는다."""
    console.print(Padding(Text(f"⚠ {message}", style="bold yellow"), (0, 0, 0, 2)))
    answer = console.input("  [bold yellow]진행할까요? (y/N) › [/bold yellow]").strip().lower()
    return answer in ("y", "yes", "네", "응", "ㅇ", "어")


def execute_tool_call(step):
    """function_call 스텝을 실제로 실행하면서, 실행 과정을 CLI에 살짝 보여준다.

    저장 안 된 작업을 날리거나 파일을 옮기고 지우는 등 되돌리기 어려운 도구는
    tools.CONFIRM_MESSAGES에 등록돼 있으면 실행 전에 사용자 확인을 먼저 받는다.
    """
    console.print(f"  [dim]● {step.name}({format_args(step.arguments)})[/dim]")

    confirm_message = tools.CONFIRM_MESSAGES.get(step.name)
    if confirm_message and not _confirm_risky_action(confirm_message(step.arguments)):
        result = {"message": "사용자가 취소해서 실행하지 않았습니다."}
        console.print("  [dim]  ⎿ 취소됨[/dim]")
        return {
            "type": "function_result",
            "name": step.name,
            "call_id": step.id,
            "result": _result_content(step.name, result),
        }

    func = tools.FUNCTION_MAP[step.name]
    result = func(**step.arguments)

    result_preview = json.dumps(result, ensure_ascii=False)
    if len(result_preview) > 90:
        result_preview = result_preview[:90] + "…"
    console.print(f"  [dim]  ⎿ {result_preview}[/dim]")

    table = render_tool_result(step.name, result)
    if table is not None:
        console.print(table)

    return {
        "type": "function_result",
        "name": step.name,
        "call_id": step.id,
        "result": _result_content(step.name, result),
    }


MASCOT_COLOR = "#c1654a"
MASCOT_EYE_COLOR = "#000000"

# 마스코트를 '선'이 아니라 '면'으로 그린다. 글자 대신 배경색을 칠해야 이미지처럼
# 꽉 찬 실루엣이 나온다.
#   B=몸통, 공백=투명(배경 그대로), K=검정(눈), S=가슴 화면, 그 외 문자=화면 속 글자
MASCOT_MAP = [
    "         BB          ",
    "         BB          ",
    "   BBBBBBBBBBBBBBB   ",
    "   BBBBBBBBBBBBBBB   ",
    " BBBBBKBBBBBBBKBBBBB ",
    " BBBBBKKBBBBBKKBBBBB ",
    " BBBBBBKBBBBBKBBBBBB ",
    "   BBBBBBKKKBBBBBB   ",
    "   BBBBBBBBBBBBBBB   ",
    "   BBSSSSSSSSSSSBB   ",
    "   BBSSSS</>SSSSBB   ",
    "   BBSSSSSSSSSSSBB   ",
    "   BBBBBBBBBBBBBBB   ",
    "    BBBB     BBBB    ",
    "    BBBB     BBBB    ",
]


def render_mascot():
    body = f"on {MASCOT_COLOR}"
    dark = f"{MASCOT_EYE_COLOR} on {MASCOT_EYE_COLOR}"          # 눈: 검게 파낸 칸
    screen_text = f"{MASCOT_COLOR} on {MASCOT_EYE_COLOR}"        # 가슴 화면 속 </>

    mascot = Text()
    for row_index, row in enumerate(MASCOT_MAP):
        if row_index:
            mascot.append("\n")
        # 같은 스타일이 이어지면 한 번에 붙여야 색 코드가 셀마다 반복되지 않는다.
        for char, group in itertools.groupby(row):
            run = "".join(group)
            if char == "B":
                mascot.append(" " * len(run), style=body)
            elif char == " ":
                mascot.append(run)
            elif char == "K":
                mascot.append(" " * len(run), style=dark)
            elif char == "S":
                mascot.append(" " * len(run), style=dark)
            else:
                mascot.append(run, style=screen_text)
    return mascot

HELP_SECTIONS = [
    ("가계부", [
        ("등록", "식비 예산 30만원으로 잡아줘 / 오늘 점심 만원 썼어"),
        ("검색", "이번 달 식비 내역 보여줘"),
        ("수정", "어제 그 거래 7천원으로 바꿔줘"),
        ("삭제", "방금 등록한 거 지워줘"),
        ("되돌리기", "방금 그거 취소해줘"),
        ("예산 조회", "지금 예산 얼마 남았어?"),
        ("JSON 저장", "이번 달 거래 내역 json으로 저장해줘"),
        ("월별 보고서", "8월 내역 정리해줘"),
        ("카테고리 관리", "차량 유지비 카테고리 추가해줘"),
    ]),
    ("할일", [
        ("등록", "우유 사야 돼 등록해줘"),
        ("완료", "방금 그거 완료했어"),
        ("정리", "완료된 거 정리해줘"),
        ("되돌리기", "방금 그거 취소해줘"),
    ]),
    ("메모", [
        ("등록", "발표자료 아이디어 메모해줘, 태그는 아이디어로"),
        ("조회", "아이디어 태그 메모 보여줘"),
        ("삭제", "그 메모 지워줘"),
    ]),
    ("생활 계산기", [
        ("더치페이", "3만원 4명이서 더치페이하면 얼마씩?"),
        ("D-day", "크리스마스까지 며칠 남았어?"),
        ("만나이", "2000년 1월 1일생 만나이 얼마야?"),
        ("근무일수", "8월 1일부터 8월 31일까지 평일 며칠이야?"),
    ]),
    ("날씨/환율", [
        ("날씨", "서울 날씨 어때?"),
        ("환율", "100달러면 원화로 얼마야?"),
    ]),
    ("뉴스", [
        ("오늘의 뉴스", "경제 3개 + IT 2개 헤드라인·주소를 보여준다 (제목·링크·요약문 포함)"),
        ("자유 질문", "IT 뉴스만 보여줘 / 경제 뉴스 3개만 보여줘"),
        ("후속 질문", "방금 그 뉴스 요약해서 내용 알려줘"),
    ]),
    ("PC 상태", [
        ("전체 확인", "컴퓨터 왜 느린지 확인해줘"),
        ("특정 지표", "지금 메모리 얼마나 쓰고 있어?"),
    ]),
    ("클립보드", [
        ("읽기", "방금 복사한 내용 뭐야? / 이거 번역해줘"),
        ("쓰기", "이 내용 클립보드에 복사해줘"),
    ]),
    ("화면 인식", [
        ("화면 확인", "지금 화면 오류가 뭐야?"),
        ("내용 정리", "화면에 있는 표 정리해줘"),
    ]),
    ("PC 제어", [
        ("앱 실행/종료", "메모장 열어줘 / 디스코드 꺼줘"),
        ("볼륨", "볼륨 30으로 낮춰줘 / 음소거해줘"),
        ("화면 잠금", "화면 잠가줘"),
    ]),
    ("파일 관리", [
        ("검색", "지난주에 만든 pdf 찾아줘"),
        ("열기/읽기", "그 파일 열어줘 / 내용 요약해줘"),
        ("복사/이동/이름변경", "바탕화면으로 옮겨줘 / 이름을 보고서로 바꿔줘"),
        ("삭제", "그 파일 지워줘 (휴지통으로 이동, 확인 후 실행)"),
    ]),
    ("메일", [
        ("검색", "오늘 온 메일 보여줘 / 안 읽은 메일 있어?"),
        ("읽기", "그 메일 내용 요약해줘"),
    ]),
    ("일정", [
        ("오늘 일정", "오늘 일정 뭐 있어?"),
        ("기간 조회", "이번 주 일정 정리해줘"),
        ("메일+일정", "오늘 중요한 메일하고 일정 정리해줘"),
        ("선제적 알림", "회의 알림 15분 전으로 바꿔줘 / 일정 알림 꺼줘"),
        ("참고", "일정 알림은 tray_app.py가 켜져 있어야 실제로 옵니다 (기본 10분 전)"),
    ]),
    ("자동 브리핑", [
        ("시각 변경", "아침 브리핑 8시로 바꿔줘"),
        ("끄기/켜기", "아침 브리핑 꺼줘 / 다시 켜줘"),
        ("참고", "tray_app.py를 따로 실행해둬야 실제로 알림이 옵니다 (커리마 안이 아니라 별도 트레이 앱)"),
    ]),
    ("로컬 문서 검색", [
        ("색인", "내 문서 자료 색인해줘 (문서·바탕화면 폴더, 처음 한 번 필요)"),
        ("검색", "예전에 정리한 K-means 자료 찾아줘"),
        ("참고", "파일 이름이 아니라 내용을 이해해서 찾습니다. 색인할 때 Gemini API를 호출해 시간이 걸릴 수 있어요"),
    ]),
    ("음성 웨이크워드", [
        ("부르기", "\"커리마\"라고 부르면 삐 소리 후 명령을 들어요"),
        ("끄기/켜기", "트레이 아이콘 우클릭 → 음성 인식 체크 해제/설정"),
        ("참고", "여기서 하는 게 아니라 tray_app.py를 켜둬야 동작합니다. 앱 강제종료·파일삭제처럼 확인이 필요한 건 음성으로 실행 안 하고 커리마를 열라고 안내해요"),
    ]),
]


def _example_grid(items):
    grid = Table.grid(padding=(0, 1, 0, 2))
    grid.add_column(style="cyan", no_wrap=True)
    grid.add_column(style="dim")
    for label, example in items:
        grid.add_row(f"• {label}", example)
    return grid


def _resolve_help_section(text):
    """메뉴 번호(1,2,3...) 또는 카테고리 이름과 정확히 일치할 때만 해당 섹션을 찾는다."""
    if text.isdigit():
        index = int(text) - 1
        return HELP_SECTIONS[index] if 0 <= index < len(HELP_SECTIONS) else None
    return next((section for section in HELP_SECTIONS if section[0] == text), None)


def print_help_section(section):
    name, items = section
    console.rule(f"[bold]{name}[/bold]", style="cyan")
    console.print(_example_grid(items))
    if name == "가계부":
        console.print(f"\n현재 카테고리: {', '.join(tools.get_categories())}", style="dim")
    console.print()


def print_welcome():
    """처음 켰을 때 보여주는 짧은 인사말.

    카테고리가 15개까지 늘어나서 매번 전부 나열하면 부담스럽다. 처음엔 몇 가지 예시만
    보여주고, 전체 목록은 '도움말'을 직접 쳤을 때만(print_menu) 보여주기로 분리했다.
    """
    console.rule(f"[bold]{ASSISTANT_NAME}[/bold]", style="cyan")
    console.print()
    console.print(Align.center(render_mascot()))
    console.print(Align.center(Text(f"안녕하세요! 저는 '{ASSISTANT_NAME}'예요, 필요한 걸 편하게 말씀해주세요!", style="bold cyan")))
    console.print()

    console.print("예를 들면 이런 걸 물어볼 수 있어요:\n", style="bold")
    console.print(_example_grid([
        ("가계부", "오늘 점심 만원 썼어"),
        ("일정", "오늘 일정 뭐 있어?"),
        ("PC 상태", "컴퓨터 왜 느린지 확인해줘"),
    ]))

    console.print("\n'도움말'이라고 하면 할 수 있는 것 전체를 볼 수 있어요.", style="dim")
    console.print("'새 대화'로 대화를 초기화하고, '종료'로 끝냅니다.", style="dim italic")
    console.print()


def print_menu():
    """'도움말'을 치면 보여주는 전체 카테고리 목록. 번호나 이름을 입력하면 그 카테고리의 자세한 예시가 나온다."""
    console.rule(f"[bold]{ASSISTANT_NAME} — 할 수 있는 것[/bold]", style="cyan")
    console.print()
    console.print("번호나 이름을 입력하면 자세한 사용법을 보여드려요.\n", style="bold")

    menu = Table.grid(padding=(0, 1, 0, 2))
    menu.add_column(style="cyan", no_wrap=True)
    menu.add_column()
    for i, (name, _) in enumerate(HELP_SECTIONS, start=1):
        menu.add_row(f"{i}.", name)
    console.print(menu)

    console.print("\n물론 메뉴를 거치지 않고 바로 자연어로 말씀하셔도 됩니다.", style="dim")
    console.print("'클로드 모드' / '코덱스 모드'로 코딩용 AI에게 직접 물어볼 수 있어요.", style="dim")
    console.print()


AGENT_WORKDIR = os.getcwd()


AGENT_COMMANDS = [
    ("쓰기 허용", "파일을 직접 고칠 수 있게 함 (기본은 읽기 전용)"),
    ("쓰기 잠금", "다시 읽기 전용으로"),
    ("모델 <이름>", "쓸 모델 지정 (예: 모델 opus)"),
    ("사용량", "이 대화에서 쓴 토큰·비용 보기"),
    ("한도", "구독 한도(5시간·주간) 확인 — CLI를 잠깐 띄웁니다"),
    ("새 대화", "기억 초기화하고 처음부터"),
    ("로그인", "계정 로그인 (브라우저가 열림)"),
    ("상태", "로그인 상태 확인"),
    ("도움말", "이 목록 다시 보기"),
    ("나가기", "커리마로 돌아가기"),
]


def print_agent_help(agent_key):
    agent = agent_cli.AGENTS[agent_key]
    grid = Table.grid(padding=(0, 1, 0, 2))
    grid.add_column(style="cyan", no_wrap=True)
    grid.add_column(style="dim")
    for command, description in AGENT_COMMANDS:
        grid.add_row(f"• {command}", description)
    console.print(grid)
    console.print(
        f"\n그 외에 입력하는 말은 전부 {agent['label']}에게 질문으로 전달됩니다.",
        style="dim italic",
    )
    console.print(f"쓸 수 있는 모델 예: {', '.join(agent['model_examples'])}", style="dim italic")
    console.print()


def enter_agent_mode(agent_key):
    """외부 CLI 모드로 들어갈 때의 안내를 보여준다."""
    agent = agent_cli.AGENTS[agent_key]
    console.rule(f"[bold]{agent['label']} 모드[/bold]", style=agent["style"])
    console.print(
        f"입력하시는 말이 {agent['label']}에게 전달되고, 답변이 여기 표시됩니다.",
        style=agent["style"],
    )
    console.print("앞선 질문을 기억하므로 이어서 물어보셔도 됩니다.\n", style=agent["style"])
    # 이 CLI들은 파일을 읽고 고칠 수 있으므로 어느 폴더에서 도는지 분명히 알린다.
    console.print(f"작업 폴더  {AGENT_WORKDIR}", style="dim")
    console.print("권한      읽기 전용 (파일을 고치지 않습니다)\n", style="dim")
    print_agent_help(agent_key)


# 로그인이 풀렸을 때 CLI가 내는 문구들. 감지되면 로그인하라고 안내한다.
AUTH_ERROR_HINTS = ("authenticate", "login", "unauthorized", "oauth", "expired", "로그인")


def run_agent_login(agent_key):
    agent = agent_cli.AGENTS[agent_key]
    console.print(f"[dim]{agent['label']} 로그인 절차를 시작합니다. 브라우저에서 직접 로그인해주세요.[/dim]\n")
    result = agent_cli.login(agent_key)
    console.print()
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]\n")
    else:
        console.print(f"[green]{result['output']}[/green]\n")


def print_agent_status(agent_key):
    agent = agent_cli.AGENTS[agent_key]
    result = agent_cli.auth_status(agent_key)
    body = result.get("error") or result["output"]
    console.print(f"[bold {agent['style']}]● {agent['label']} 계정 상태[/bold {agent['style']}]")
    console.print(Padding(Text(body, style="dim"), (0, 0, 0, 2)))
    console.print()


def new_agent_session(allow_write=False, model=None):
    return {
        "id": agent_cli.new_session_id(),
        "started": False,
        "allow_write": allow_write,
        "model": model,
        # 이 대화에서 쓴 누적량. CLI가 사용량을 줄 때만 쌓인다.
        "calls": 0,
        "cost_usd": 0.0,
        "output_tokens": 0,
        "last": None,
    }


def _format_tokens(count):
    return f"{count / 1000:.1f}k" if count >= 1000 else str(count)


def _short_model(name):
    """프롬프트에 넣기 좋게 줄인다 (claude-opus-5 -> opus-5)."""
    return name.removeprefix("claude-") if name else name


def current_model_label(session):
    """실제로 쓰인 모델을 우선 보여준다.

    지정하지 않으면 CLI가 알아서 고르기 때문에, 한 번이라도 답을 받았으면
    그때 실제로 쓰인 모델이 지정값보다 정확하다.
    """
    used = (session["last"] or {}).get("model")
    if used:
        return _short_model(used)
    if session["model"]:
        return session["model"]
    return None


def agent_prompt(agent_mode, session):
    agent = agent_cli.AGENTS[agent_mode]
    parts = [p for p in (current_model_label(session),) if p]
    if session["allow_write"]:
        parts.append("쓰기")

    suffix = f"[{'·'.join(parts)}]" if parts else ""
    # 쓰기가 켜져 있으면 색까지 바꿔서 모르고 쓰는 일이 없게 한다.
    style = "yellow" if session["allow_write"] else agent["style"]
    return f"[bold {style}]{agent_mode}{suffix} ›[/bold {style}] "


def print_agent_usage(agent_key, session):
    agent = agent_cli.AGENTS[agent_key]
    console.print(f"[bold {agent['style']}]● 사용량[/bold {agent['style']}]")

    # 사용량을 아예 안 주는 CLI라면 그 사실부터 밝힌다.
    # (안 그러면 질문을 했는데도 "내역이 없다"고 나와 오해하기 쉽다.)
    if not agent["json_output"]:
        console.print(
            Padding(
                Text(
                    f"{agent['label']}는 토큰·비용 정보를 주지 않아 여기서 집계할 수 없습니다.\n"
                    f"'한도'를 입력하면 {agent['label']}를 직접 띄워 확인할 수 있어요.",
                    style="dim",
                ),
                (0, 0, 0, 2),
            )
        )
        console.print()
        return

    if not session["calls"]:
        console.print(Padding(Text("아직 질문한 내역이 없습니다.", style="dim"), (0, 0, 0, 2)))
        console.print()
        return

    grid = Table.grid(padding=(0, 1, 0, 2))
    grid.add_column(style="cyan", no_wrap=True)
    grid.add_column()

    last = session["last"]
    if last:
        grid.add_row("모델", last["model"])
        window = last.get("context_window")
        if window:
            share = last["sent_tokens"] / window * 100
            grid.add_row(
                "컨텍스트",
                f"{_format_tokens(last['sent_tokens'])} / {_format_tokens(window)} ({share:.1f}%)",
            )
    grid.add_row("질문 수", f"{session['calls']}회")
    grid.add_row("생성 토큰", _format_tokens(session["output_tokens"]))
    grid.add_row("누적 비용", f"${session['cost_usd']:.4f}")
    console.print(Padding(grid, (0, 0, 0, 2)))

    # 5시간/주간 한도는 비대화형 호출로는 못 받아온다. '한도'로 우회한다.
    console.print(
        Padding(
            Text("구독 한도(5시간·주간)는 여기서 못 봅니다. '한도'를 입력하면 확인할 수 있어요.",
                 style="dim italic"),
            (1, 0, 0, 2),
        )
    )
    console.print()


def show_agent_limits(agent_key):
    """플랜 한도를 보려고 CLI를 대화형으로 잠깐 띄운다."""
    agent = agent_cli.AGENTS[agent_key]
    command = agent["limit_command"]
    if command:
        console.print(
            f"[dim]{agent['label']}를 띄웁니다. [bold]{command}[/bold] 를 입력해 한도를 확인하고, "
            f"끝나면 종료해서 커리마로 돌아오세요.[/dim]\n"
        )
    else:
        # 명령어를 확실히 모르면 아는 척하지 않는다.
        console.print(
            f"[dim]{agent['label']}를 띄웁니다. 한도를 보는 명령은 확인되지 않아서, "
            f"'/'를 눌러 명령 목록에서 찾아보세요. 끝나면 종료하면 커리마로 돌아옵니다.[/dim]\n"
        )
    result = agent_cli.run_interactive(agent_key)
    console.print()
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]\n")
    else:
        console.print(f"[dim]{result['output']}[/dim]\n")


def ask_agent_and_print(agent_key, prompt, session):
    """session은 대화 상태(id/권한/모델/누적 사용량)를 담는다."""
    agent = agent_cli.AGENTS[agent_key]
    with console.status(f"[dim]{agent['label']}에게 물어보는 중...[/dim]", spinner="dots"):
        result = agent_cli.ask_agent(
            agent_key,
            prompt,
            cwd=AGENT_WORKDIR,
            session_id=session["id"],
            is_first=not session["started"],
            allow_write=session["allow_write"],
            model=session["model"],
        )

    if "error" in result:
        # 첫 호출이 실패했으면 세션 id를 새로 뽑는다. 클로드는 --session-id를 한 번 쓰면
        # 그 호출이 실패했더라도 id를 점유해버려서, 같은 id로 첫 호출을 다시 하면
        # "Session ID ... is already in use"로 계속 막힌다. 로그인 전에 한 번 물어봐서
        # 실패하고, 로그인한 뒤 다시 물어보는 흔한 흐름이 정확히 여기 걸렸다.
        if not session["started"]:
            session["id"] = agent_cli.new_session_id()
        console.print(f"[bold red]● {agent['label']} 오류[/bold red]")
        console.print(Padding(Text(result["error"], style="red"), (0, 0, 0, 2)))
        if any(hint in result["error"].lower() for hint in AUTH_ERROR_HINTS):
            console.print(Padding(Text("'로그인'이라고 입력하면 바로 로그인할 수 있어요.", style="yellow"), (0, 0, 0, 2)))
        console.print()
        return

    session["started"] = True
    # 코덱스처럼 CLI가 자기 세션 id를 알려주면, 다음 질문은 그 id로 정확히 이어간다.
    if result.get("cli_session_id"):
        session["id"] = result["cli_session_id"]

    console.print(f"[bold {agent['style']}]● {agent['label']}[/bold {agent['style']}]")
    console.print(Padding(Markdown(result["output"]), (0, 0, 0, 2)))

    stats = result.get("stats")
    if stats:
        session["calls"] += 1
        session["cost_usd"] += stats["cost_usd"]
        session["output_tokens"] += stats["output_tokens"]
        session["last"] = stats
        summary = (
            f"{stats['model']} · 컨텍스트 {_format_tokens(stats['sent_tokens'])}"
            f" · ${stats['cost_usd']:.4f} · {stats['duration_ms'] / 1000:.1f}초"
        )
        console.print(Padding(Text(summary, style="dim"), (0, 0, 0, 2)))
    console.print()


def run():
    previous_interaction_id = load_previous_interaction_id()
    agent_mode = None
    agent_session = None

    print_welcome()
    if previous_interaction_id:
        console.print("[dim]지난 대화를 이어서 기억하고 있어요. 새로 시작하려면 '새 대화'라고 말해주세요.[/dim]\n")

    while True:
        try:
            if agent_mode:
                user_input = console.input(agent_prompt(agent_mode, agent_session))
            else:
                user_input = console.input("[bold cyan]›[/bold cyan] ")
            stripped = user_input.strip()

            if not stripped:
                continue
            if stripped == "종료":
                break

            if agent_mode:
                if stripped in ("나가기", "돌아가기"):
                    console.print(f"[dim]{ASSISTANT_NAME}로 돌아왔습니다.[/dim]\n")
                    agent_mode = None
                    agent_session = None
                    continue
                if stripped == "로그인":
                    run_agent_login(agent_mode)
                    continue
                if stripped in ("상태", "로그인 상태"):
                    print_agent_status(agent_mode)
                    continue
                if stripped in ("도움말", "help"):
                    print_agent_help(agent_mode)
                    continue
                if stripped == "사용량":
                    print_agent_usage(agent_mode, agent_session)
                    continue
                if stripped in ("한도", "플랜"):
                    show_agent_limits(agent_mode)
                    continue
                if stripped in ("새 대화", "초기화"):
                    agent_session = new_agent_session(
                        agent_session["allow_write"], agent_session["model"]
                    )
                    console.print("[dim]새 대화로 시작합니다.[/dim]\n")
                    continue
                if stripped == "모델" or stripped.startswith("모델 "):
                    model = stripped[len("모델"):].strip()
                    if not model:
                        current = agent_session["model"] or "기본값"
                        examples = ", ".join(agent_cli.AGENTS[agent_mode]["model_examples"])
                        console.print(f"[dim]현재 모델: {current} (예: {examples})[/dim]\n")
                        continue
                    # 모델도 세션 시작 때 정해지므로 대화를 새로 연다.
                    agent_session = new_agent_session(agent_session["allow_write"], model)
                    console.print(f"[green]모델을 '{model}'(으)로 바꿨습니다.[/green]")
                    console.print("[dim]새 대화로 시작합니다.[/dim]\n")
                    continue
                if stripped in ("쓰기 허용", "쓰기허용"):
                    # 코덱스는 권한이 세션 시작 때 고정돼서, 대화를 새로 열어야 실제로 반영된다.
                    agent_session = new_agent_session(True, agent_session["model"])
                    console.print(
                        "[bold yellow]⚠ 이제 파일을 직접 수정합니다. "
                        "되돌리려면 git을 쓰세요 (git diff / git checkout -- .)[/bold yellow]"
                    )
                    console.print("[dim]권한이 바뀌어 새 대화로 시작합니다.[/dim]\n")
                    continue
                if stripped in ("쓰기 잠금", "쓰기잠금", "읽기 전용"):
                    agent_session = new_agent_session(False, agent_session["model"])
                    console.print("[green]읽기 전용으로 돌아왔습니다.[/green]")
                    console.print("[dim]권한이 바뀌어 새 대화로 시작합니다.[/dim]\n")
                    continue
                ask_agent_and_print(agent_mode, stripped, agent_session)
                continue

            entered = next(
                (key for key in agent_cli.AGENTS if stripped in (f"{key} 모드", key)),
                None,
            )
            if entered:
                if not agent_cli.is_available(entered):
                    console.print(
                        f"[red]{agent_cli.AGENTS[entered]['label']} CLI가 설치돼 있지 않아 쓸 수 없습니다.[/red]\n"
                    )
                    continue
                agent_mode = entered
                agent_session = new_agent_session()
                enter_agent_mode(entered)
                continue

            if stripped in ("도움말", "help"):
                print_menu()
                continue
            if stripped in ("새 대화", "초기화"):
                previous_interaction_id = None
                save_previous_interaction_id(None)
                console.print("[dim]대화를 새로 시작합니다.[/dim]\n")
                continue

            section = _resolve_help_section(stripped)
            if section:
                print_help_section(section)
                continue

            console.rule(style="grey50")

            with console.status("[dim]생각하는 중...[/dim]", spinner="dots"):
                interaction = safe_create_interaction(user_input, previous_interaction_id)
            previous_interaction_id = interaction.id
            save_previous_interaction_id(previous_interaction_id)

            while True:
                call_steps = [s for s in interaction.steps if s.type == "function_call"]

                if call_steps:
                    function_results = [execute_tool_call(step) for step in call_steps]
                    with console.status("[dim]생각하는 중...[/dim]", spinner="dots"):
                        interaction = safe_create_interaction(function_results, interaction.id)
                    previous_interaction_id = interaction.id
                    save_previous_interaction_id(previous_interaction_id)
                else:
                    console.print(f"[bold green]● {ASSISTANT_NAME}[/bold green]")
                    console.print(Padding(Markdown(interaction.output_text or ""), (0, 0, 0, 2)))
                    break
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        console.print()

    console.print("[cyan]● 대화를 종료합니다. 안녕히 가세요![/cyan]")


if __name__ == "__main__":
    run()
