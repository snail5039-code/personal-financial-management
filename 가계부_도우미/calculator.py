"""생활 계산기 - 더치페이/D-day/만 나이/근무일수. 외부 의존성 없는 순수 계산 함수만 모아둔다."""

import datetime


def _parse_date(date_str):
    return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()


def split_bill(total_amount, people_count):
    """총액을 인원수로 나눠 1인당 금액과 나머지를 계산한다."""
    per_person = total_amount // people_count
    remainder = total_amount - per_person * people_count
    return {"per_person": per_person, "remainder": remainder}


def dday(target_date):
    """오늘부터 target_date(YYYY-MM-DD)까지 남은(또는 지난) 일수."""
    diff = _parse_date(target_date) - datetime.datetime.now().date()
    return diff.days


def age(birth_date):
    """생년월일(YYYY-MM-DD) 기준 만 나이."""
    birth = _parse_date(birth_date)
    today = datetime.datetime.now().date()
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return years


def business_days(start_date, end_date):
    """start_date~end_date 사이의 평일(주말 제외) 일수. 공휴일은 고려하지 않는다."""
    start, end = _parse_date(start_date), _parse_date(end_date)
    if end < start:
        start, end = end, start
    count = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            count += 1
        d += datetime.timedelta(days=1)
    return count
