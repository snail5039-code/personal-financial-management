"""날씨 조회. wttr.in을 사용한다 (API 키 불필요, 무료)."""

import json
import urllib.parse
import urllib.request


def get_weather(city):
    """도시 이름으로 현재 날씨를 조회한다."""
    url = "https://wttr.in/" + urllib.parse.quote(city) + "?format=j1"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    current = data["current_condition"][0]
    return {
        "temperature_c": current["temp_C"],
        "feels_like_c": current["FeelsLikeC"],
        "humidity": current["humidity"],
        "description": current["weatherDesc"][0]["value"],
    }
