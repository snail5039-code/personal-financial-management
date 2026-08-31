"""뉴스 도구 (경제 · IT). API 키 없이 쓰는 무료 서비스(연합뉴스 · 전자신문 RSS)를 부른다."""

from . import news


# ---------------------------------------------------------------------------
# 17. news_briefing
# ---------------------------------------------------------------------------
def news_briefing(count=5):
    """경제 뉴스와 IT 뉴스 헤드라인을 섞어서 가져온다. 경제:IT를 대략 3:2 비율로 나눈다.
    각 항목에는 title(제목)·link(원문 주소)·summary(실제 기사 요약문)가 들어있다."""
    economy_count = max(1, round(count * 0.6))
    it_count = max(1, count - economy_count)

    try:
        economy = news.get_economy_news(limit=economy_count)
        it = news.get_it_news(limit=it_count)
    except Exception as e:
        return {"error": f"뉴스 조회에 실패했습니다: {e}"}

    items = [{"category": "경제", **a} for a in economy] + [{"category": "IT", **a} for a in it]
    if not items:
        return {"message": "가져올 수 있는 뉴스가 없습니다."}

    return {"count": len(items), "items": items}


news_briefing_tool = {
    "type": "function",
    "name": "news_briefing",
    "description": (
        "경제 뉴스와 IT 뉴스 헤드라인을 섞어서 가져온다. count를 지정하지 않으면 "
        "경제 3개 + IT 2개, 총 5개를 가져온다. 각 항목은 title(제목)·link(실제 기사 주소)·"
        "summary(기사 요약문)를 포함하므로, 사용자가 이 중 특정 뉴스를 더 자세히 알려달라거나 "
        "요약해달라고 하면 이 도구를 다시 부르지 말고 이미 받은 summary를 바탕으로 답한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "가져올 헤드라인 총 개수 (기본 5개). 경제:IT를 대략 3:2 비율로 나눠 가져온다.",
            },
        },
        "required": [],
    },
}
