"""가계부 도우미 - Claude Code 스타일 CLI

이 폴더 안의 tools.py/storage.py(실제 로직)와 Gemini Interactions API 연동 로직을 쓰고,
그 위에 터미널 UI(rich)를 입힌 것이다. 기본_CLI 폴더와는 완전히 독립적인 사본이다.
"""

import datetime
import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

from dotenv import load_dotenv
from google import genai
from rich.align import Align
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

import tools

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(os.path.join(THIS_DIR, ".env"))

MODEL = "gemini-3.6-flash"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
console = Console()

TODAY = datetime.datetime.now().strftime("%Y-%m-%d")

SYSTEM_INSTRUCTION = (
    f"오늘 날짜는 {TODAY}입니다. 사용자가 '오늘', '어제', '이번 달'처럼 상대적인 날짜를 말하면 "
    "이 날짜를 기준으로 계산해서 도구 호출 시 날짜는 YYYY-MM-DD, 월은 YYYY-MM 형식으로 변환해서 넘기세요. "
    "당신은 개인 거래 내역/예산과 할일(구글 할일 연동)을 관리해주는 에이전트입니다."
)


def create_interaction(input_data, previous_interaction_id):
    return client.interactions.create(
        model=MODEL,
        input=input_data,
        previous_interaction_id=previous_interaction_id,
        tools=tools.TOOLS,
        store=True,
        system_instruction=SYSTEM_INSTRUCTION,
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
    return None


def execute_tool_call(step):
    """function_call 스텝을 실제로 실행하면서, 실행 과정을 CLI에 살짝 보여준다."""
    console.print(f"  [dim]● {step.name}({format_args(step.arguments)})[/dim]")

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
        "result": [
            {
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False),
            }
        ],
    }


MASCOT = "\n".join([
    " ▄▄▄▄▄ ",
    "█ ◕ ◕ █",
    "█  ω  █",
    " ▀▀▀▀▀ ",
])


def print_welcome():
    categories = ", ".join(tools.get_categories())

    console.rule("[bold]가계부 도우미[/bold]", style="cyan")
    console.print()
    console.print(Align.center(Text(MASCOT, style="bold yellow")))
    console.print(Align.center(Text("안녕하세요! 저는 '코이니'예요, 가계부 도우미가 도와드릴게요!", style="bold cyan")))
    console.print()

    console.print("자연어로 편하게 말씀해주세요.\n", style="bold")

    examples = [
        ("등록", "식비 예산 30만원으로 잡아줘 / 오늘 점심 만원 썼어"),
        ("검색", "이번 달 식비 내역 보여줘"),
        ("수정", "어제 그 거래 7천원으로 바꿔줘"),
        ("삭제", "방금 등록한 거 지워줘"),
        ("되돌리기", "방금 그거 취소해줘"),
        ("예산 조회", "지금 예산 얼마 남았어?"),
        ("JSON 저장", "이번 달 거래 내역 json으로 저장해줘"),
        ("월별 보고서", "8월 내역 정리해줘"),
        ("카테고리 관리", "차량 유지비 카테고리 추가해줘"),
        ("할일 관리", "우유 사야 돼 등록해줘 / 방금 그거 완료했어 / 완료된 거 정리해줘"),
    ]
    grid = Table.grid(padding=(0, 1, 0, 2))
    grid.add_column(style="cyan", no_wrap=True)
    grid.add_column(style="dim")
    for label, example in examples:
        grid.add_row(f"• {label}", example)
    console.print(grid)

    console.print(f"\n현재 카테고리: {categories}", style="dim")
    console.print("'도움말'로 이 안내를 다시 보고, '새 대화'로 대화를 초기화하고, '종료'로 끝냅니다.", style="dim italic")
    console.print()


def run():
    previous_interaction_id = load_previous_interaction_id()

    print_welcome()
    if previous_interaction_id:
        console.print("[dim]지난 대화를 이어서 기억하고 있어요. 새로 시작하려면 '새 대화'라고 말해주세요.[/dim]\n")

    while True:
        try:
            user_input = console.input("[bold cyan]›[/bold cyan] ")
            stripped = user_input.strip()

            if not stripped:
                continue
            if stripped == "종료":
                break
            if stripped in ("도움말", "help"):
                print_welcome()
                continue
            if stripped in ("새 대화", "초기화"):
                previous_interaction_id = None
                save_previous_interaction_id(None)
                console.print("[dim]대화를 새로 시작합니다.[/dim]\n")
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
                    console.print("[bold green]● 가계부 도우미[/bold green]")
                    console.print(Padding(Markdown(interaction.output_text or ""), (0, 0, 0, 2)))
                    break
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        console.print()

    console.print("[cyan]● 대화를 종료합니다. 안녕히 가세요![/cyan]")


if __name__ == "__main__":
    run()
