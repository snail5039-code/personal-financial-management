"""뉴스 조회. 연합뉴스(경제)·전자신문(IT) RSS를 쓴다 (API 키 불필요, 무료).

구글 뉴스 RSS는 실제 기사 주소 대신 구글 리다이렉트 링크를 주고 description도
제목을 반복할 뿐이라 요약에 못 쓴다. 두 매체는 링크가 실제 기사 주소이고
description에 실제 기사 요약문(리드 문단)이 들어있어서 헤드라인·주소·요약을
한 번에 가져올 수 있다.
"""

import urllib.request
import xml.etree.ElementTree as ET

FEED_URLS = {
    "economy": "https://www.yna.co.kr/rss/economy.xml",
    "it": "http://rss.etnews.com/03.xml",
}


def _fetch_feed(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = resp.read()

    root = ET.fromstring(data)
    items = root.findall("./channel/item")[:limit]
    return [
        {
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "summary": (item.findtext("description") or "").strip(),
        }
        for item in items
    ]


def get_economy_news(limit=3):
    """연합뉴스 경제 헤드라인을 최신순으로 가져온다 (제목·주소·요약문 포함)."""
    return _fetch_feed(FEED_URLS["economy"], limit)


def get_it_news(limit=2):
    """전자신문 IT/통신 헤드라인을 최신순으로 가져온다 (제목·주소·요약문 포함)."""
    return _fetch_feed(FEED_URLS["it"], limit)
