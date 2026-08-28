"""가계부 도우미 - Claude Code 스타일 CLI

상위 폴더의 tools.py/storage.py(실제 로직)와 Gemini Interactions API 연동 로직은
main.py와 동일하고, 이 파일은 그 위에 터미널 UI(rich)만 새로 입힌 것이다.
"""

import datetime
import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from google import genai
from rich.align import Align
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

import tools

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

MODEL = "gemini-3.6-flash"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
console = Console()

TODAY = datetime.datetime.now().strftime("%Y-%m-%d")

SYSTEM_INSTRUCTION = (
    f"오늘 날짜는 {TODAY}입니다. 사용자가 '오늘', '어제', '이번 달'처럼 상대적인 날짜를 말하면 "
    "이 날짜를 기준으로 계산해서 도구 호출 시 날짜는 YYYY-MM-DD, 월은 YYYY-MM 형식으로 변환해서 넘기세요. "
    "당신은 개인 거래 내역과 예산을 관리해주는 에이전트입니다."
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


def format_args(args):
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


def execute_tool_call(step):
    """function_call 스텝을 실제로 실행하면서, 실행 과정을 CLI에 살짝 보여준다."""
    console.print(f"  [dim]● {step.name}({format_args(step.arguments)})[/dim]")

    func = tools.FUNCTION_MAP[step.name]
    result = func(**step.arguments)

    result_preview = json.dumps(result, ensure_ascii=False)
    if len(result_preview) > 90:
        result_preview = result_preview[:90] + "…"
    console.print(f"  [dim]  ⎿ {result_preview}[/dim]")

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

    mascot = Align.center(Text(MASCOT, style="bold yellow"))
    greeting = Align.center(Text("안녕하세요! 저는 '코이니'예요, 가계부 도우미가 도와드릴게요!", style="bold cyan"))

    body = Text()
    body.append("\n자연어로 편하게 말씀해주세요.\n\n", style="bold")
    examples = [
        ("등록", "식비 예산 30만원으로 잡아줘 / 오늘 점심 만원 썼어"),
        ("검색", "이번 달 식비 내역 보여줘"),
        ("수정", "어제 그 거래 7천원으로 바꿔줘"),
        ("삭제", "방금 등록한 거 지워줘"),
        ("예산 조회", "지금 예산 얼마 남았어?"),
        ("JSON 저장", "이번 달 거래 내역 json으로 저장해줘"),
        ("월별 보고서", "8월 내역 정리해줘"),
        ("카테고리 관리", "차량 유지비 카테고리 추가해줘"),
    ]
    for label, example in examples:
        body.append(f"  • {label:10s}", style="cyan")
        body.append(f" {example}\n", style="dim")
    body.append(f"\n현재 카테고리: {categories}\n", style="dim")
    body.append("'종료'를 입력하면 끝납니다.", style="dim italic")

    console.print(
        Panel(
            Group(mascot, greeting, body),
            title="[bold]가계부 도우미[/bold]",
            subtitle="[dim]Gemini Function Calling[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()


def run():
    previous_interaction_id = None

    print_welcome()

    while True:
        try:
            user_input = console.input("[bold cyan]›[/bold cyan] ")

            if not user_input.strip():
                continue
            if user_input.strip() == "종료":
                break

            with console.status("[dim]생각하는 중...[/dim]", spinner="dots"):
                interaction = create_interaction(user_input, previous_interaction_id)
            previous_interaction_id = interaction.id

            while True:
                call_steps = [s for s in interaction.steps if s.type == "function_call"]

                if call_steps:
                    function_results = [execute_tool_call(step) for step in call_steps]
                    with console.status("[dim]생각하는 중...[/dim]", spinner="dots"):
                        interaction = create_interaction(function_results, interaction.id)
                    previous_interaction_id = interaction.id
                else:
                    console.print(
                        Panel(
                            Markdown(interaction.output_text or ""),
                            title="[bold green]가계부 도우미[/bold green]",
                            border_style="green",
                            padding=(0, 2),
                        )
                    )
                    break
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        console.print()

    console.print(Panel("대화를 종료합니다. 안녕히 가세요!", border_style="cyan"))


if __name__ == "__main__":
    run()
