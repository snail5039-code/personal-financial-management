"""Gemini Function Calling 기반 개인 거래/예산 관리 에이전트 (Interactions API 버전, 기본 CLI).

client.interactions.create()가 대화를 서버 사이드에 저장하고(store=True),
previous_interaction_id로 이어서 대화를 이어간다. while 루프로 사용자 입력을 받아
Gemini에게 보내고, function_call 스텝이 나오면 이 폴더 안의 tools.py의 실제 함수를 실행한 뒤
결과를 다시 Gemini에게 돌려줘서 최종 자연어 응답을 받는다.

이 폴더는 여기서 개발을 멈추고 더 이상 갱신하지 않는다 (더 다듬는 건 ../가계부_도우미/app.py 쪽에서 계속됨).
tools.py/storage.py/.env는 가계부_도우미 폴더와 완전히 독립적인 사본이다.
"""

import datetime
import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

from dotenv import load_dotenv
from google import genai

import tools

# Windows 콘솔 기본 인코딩(cp949)에서 한글이 깨지는 것을 방지
sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(os.path.join(THIS_DIR, ".env"))

MODEL = "gemini-3.6-flash"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

TODAY = datetime.datetime.now().strftime("%Y-%m-%d")

SYSTEM_INSTRUCTION = (
    f"오늘 날짜는 {TODAY}입니다. 사용자가 '오늘', '어제', '이번 달'처럼 상대적인 날짜를 말하면 "
    "이 날짜를 기준으로 계산해서 도구 호출 시 날짜는 YYYY-MM-DD, 월은 YYYY-MM 형식으로 변환해서 넘기세요. "
    "당신은 개인 거래 내역과 예산을 관리해주는 에이전트입니다."
)


def create_interaction(input_data, previous_interaction_id):
    """Gemini Interactions API로 한 턴을 생성한다. tools.py의 dict 스키마를 그대로 tools에 넘긴다."""
    return client.interactions.create(
        model=MODEL,
        input=input_data,
        previous_interaction_id=previous_interaction_id,
        tools=tools.TOOLS,
        store=True,
        system_instruction=SYSTEM_INSTRUCTION,
    )


def execute_tool_call(step):
    """Gemini가 요청한 function_call 스텝을 tools.py의 실제 함수로 실행하고,
    다시 Gemini에게 돌려줄 function_result 형태로 만든다."""
    func = tools.FUNCTION_MAP[step.name]
    result = func(**step.arguments)

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


def print_intro():
    categories = ", ".join(tools.get_categories())
    print("=" * 50)
    print("가계부 관리 에이전트입니다.")
    print("번호 없이 자연어로 편하게 말씀해주세요. 예시:")
    print("  - 예산/거래 등록 : '식비 예산 30만원으로 잡아줘', '오늘 점심 만원 썼어'")
    print("  - 검색           : '이번 달 식비 내역 보여줘'")
    print("  - 수정           : '어제 그 거래 7천원으로 바꿔줘'")
    print("  - 삭제           : '방금 등록한 거 지워줘'")
    print("  - 예산 조회      : '지금 예산 얼마 남았어?'")
    print("  - JSON 저장      : '이번 달 거래 내역 json으로 저장해줘'")
    print("  - 월별 보고서    : '8월 내역 정리해줘'")
    print("  - 카테고리 관리  : '차량 유지비 카테고리 추가해줘', '의류비를 옷값으로 이름 바꿔줘'")
    print(f"  (현재 카테고리: {categories})")
    print("'종료'를 입력하면 끝납니다.")
    print("=" * 50)
    print()


def financial_agent():
    previous_interaction_id = None

    print_intro()

    while True:
        user_input = input("사용자 : ").strip()

        if not user_input:
            print("가계부 도우미 : 내용을 입력해주세요.")
            print()
            continue

        if user_input == "종료":
            break

        interaction = create_interaction(user_input, previous_interaction_id)
        previous_interaction_id = interaction.id

        while True:
            function_results = [
                execute_tool_call(step)
                for step in interaction.steps
                if step.type == "function_call"
            ]

            if function_results:
                interaction = create_interaction(function_results, interaction.id)
                previous_interaction_id = interaction.id
            else:
                print(f"가계부 도우미 : {interaction.output_text}")
                break

        print()


if __name__ == "__main__":
    financial_agent()
