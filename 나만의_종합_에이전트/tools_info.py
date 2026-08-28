"""조회 도구 (날씨 · 환율). 둘 다 API 키 없이 쓰는 무료 서비스를 부른다."""

import exchange
import weather


# ---------------------------------------------------------------------------
# 15. weather_check
# ---------------------------------------------------------------------------
def weather_check(city):
    """도시 이름으로 현재 날씨를 조회한다."""
    try:
        info = weather.get_weather(city)
    except Exception as e:
        return {"error": f"날씨 조회에 실패했습니다: {e}"}

    message = (
        f"{city} 현재 {info['description']}, 기온 {info['temperature_c']}°C"
        f"(체감 {info['feels_like_c']}°C), 습도 {info['humidity']}%"
    )
    return {"city": city, **info, "message": message}


weather_check_tool = {
    "type": "function",
    "name": "weather_check",
    "description": "도시 이름으로 현재 날씨(기온/체감온도/습도/날씨 상태)를 조회한다.",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "날씨를 조회할 도시 이름 (예: 'Seoul', 'Busan')"},
        },
        "required": ["city"],
    },
}


# ---------------------------------------------------------------------------
# 16. exchange_rate_check
# ---------------------------------------------------------------------------
def exchange_rate_check(base, target, amount=1):
    """base 통화 amount만큼을 target 통화로 환전하면 얼마인지 조회한다 (예: USD -> KRW)."""
    try:
        result = exchange.get_rate(base, target, amount)
    except Exception as e:
        return {"error": f"환율 조회에 실패했습니다: {e}"}

    message = f"{result['date']} 기준 {result['amount']} {result['base']} = {result['converted']:,} {result['target']}"
    return {**result, "message": message}


exchange_rate_check_tool = {
    "type": "function",
    "name": "exchange_rate_check",
    "description": (
        "한 통화(base)의 금액을 다른 통화(target)로 환전하면 얼마인지 조회한다. "
        "통화는 ISO 코드로 입력한다 (예: USD, KRW, JPY, EUR)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "base": {"type": "string", "description": "환전할 기준 통화 코드 (예: 'USD')"},
            "target": {"type": "string", "description": "바꿀 대상 통화 코드 (예: 'KRW')"},
            "amount": {"type": "number", "description": "환전할 금액 (기본값 1)"},
        },
        "required": ["base", "target"],
    },
}
