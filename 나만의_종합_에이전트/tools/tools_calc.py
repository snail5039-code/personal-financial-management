"""생활 계산기 도구 (더치페이 · D-day · 만 나이 · 근무일수)."""

from . import calculator


# ---------------------------------------------------------------------------
# 14. calc_split_bill / calc_dday / calc_age / calc_business_days
# ---------------------------------------------------------------------------
def calc_split_bill(total_amount, people_count):
    """총액을 인원수로 나눠 1인당 낼 금액을 계산한다 (더치페이)."""
    if people_count <= 0:
        return {"error": "인원수는 1명 이상이어야 합니다."}

    result = calculator.split_bill(total_amount, people_count)
    if result["remainder"]:
        message = (
            f"1인당 {result['per_person']:,}원씩 내고, {result['remainder']}원은 나눠떨어지지 않아 "
            "한두 명이 조금 더 부담해야 합니다."
        )
    else:
        message = f"1인당 {result['per_person']:,}원씩 내면 됩니다."
    return {**result, "total_amount": total_amount, "people_count": people_count, "message": message}


calc_split_bill_tool = {
    "type": "function",
    "name": "calc_split_bill",
    "description": "총액을 인원수로 나눠 더치페이 시 1인당 낼 금액을 계산한다.",
    "parameters": {
        "type": "object",
        "properties": {
            "total_amount": {"type": "number", "description": "나눌 총 금액"},
            "people_count": {"type": "integer", "description": "나눌 인원 수"},
        },
        "required": ["total_amount", "people_count"],
    },
}


def calc_dday(target_date):
    """오늘부터 target_date(YYYY-MM-DD)까지 남은(또는 지난) 일수를 계산한다."""
    try:
        days = calculator.dday(target_date)
    except ValueError:
        return {"error": "날짜 형식이 올바르지 않습니다. YYYY-MM-DD로 입력해주세요."}

    if days > 0:
        message = f"{target_date}까지 D-{days}일 남았습니다."
    elif days == 0:
        message = f"오늘이 {target_date}입니다 (D-Day)."
    else:
        message = f"{target_date}로부터 D+{-days}일 지났습니다."
    return {"target_date": target_date, "days": days, "message": message}


calc_dday_tool = {
    "type": "function",
    "name": "calc_dday",
    "description": "오늘부터 특정 날짜까지 남은(또는 지난) 일수를 D-day 형식으로 계산한다.",
    "parameters": {
        "type": "object",
        "properties": {
            "target_date": {"type": "string", "description": "기준 날짜 (YYYY-MM-DD)"},
        },
        "required": ["target_date"],
    },
}


def calc_age(birth_date):
    """생년월일(YYYY-MM-DD) 기준 만 나이를 계산한다."""
    try:
        result = calculator.age(birth_date)
    except ValueError:
        return {"error": "날짜 형식이 올바르지 않습니다. YYYY-MM-DD로 입력해주세요."}
    return {"birth_date": birth_date, "age": result, "message": f"만 나이는 {result}세입니다."}


calc_age_tool = {
    "type": "function",
    "name": "calc_age",
    "description": "생년월일로 만 나이를 계산한다.",
    "parameters": {
        "type": "object",
        "properties": {
            "birth_date": {"type": "string", "description": "생년월일 (YYYY-MM-DD)"},
        },
        "required": ["birth_date"],
    },
}


def calc_business_days(start_date, end_date):
    """start_date~end_date 사이의 평일(주말 제외) 일수를 계산한다. 공휴일은 반영하지 않는다."""
    try:
        count = calculator.business_days(start_date, end_date)
    except ValueError:
        return {"error": "날짜 형식이 올바르지 않습니다. YYYY-MM-DD로 입력해주세요."}
    return {
        "start_date": start_date,
        "end_date": end_date,
        "business_days": count,
        "message": f"{start_date}부터 {end_date}까지 평일은 {count}일입니다 (공휴일은 반영되지 않음).",
    }


calc_business_days_tool = {
    "type": "function",
    "name": "calc_business_days",
    "description": "두 날짜 사이의 평일(주말 제외) 일수를 계산한다. 공휴일은 반영하지 않는다.",
    "parameters": {
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "시작 날짜 (YYYY-MM-DD)"},
            "end_date": {"type": "string", "description": "끝 날짜 (YYYY-MM-DD)"},
        },
        "required": ["start_date", "end_date"],
    },
}


# ---------------------------------------------------------------------------
