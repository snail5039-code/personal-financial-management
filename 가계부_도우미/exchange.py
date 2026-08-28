"""환율 조회. Frankfurter API를 사용한다 (API 키 불필요, 무료, ECB 기준 환율)."""

import json
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.frankfurter.app/latest"


def get_rate(base, target, amount=1):
    """base 통화 amount만큼을 target 통화로 환전한 금액을 조회한다."""
    params = urllib.parse.urlencode({"amount": amount, "from": base.upper(), "to": target.upper()})
    req = urllib.request.Request(f"{BASE_URL}?{params}", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"'{base}' 또는 '{target}'는 지원하지 않는 통화 코드입니다.")
        raise

    rate = data["rates"].get(target.upper())
    if rate is None:
        raise ValueError(f"'{target}' 통화는 지원하지 않습니다.")

    return {"base": base.upper(), "target": target.upper(), "amount": amount, "converted": rate, "date": data["date"]}
