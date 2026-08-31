"""로컬 문서 검색(RAG) 도구. 문서·바탕화면 폴더의 파일을 미리 색인해두고 내용 기반으로 찾는다.

파일 이름으로 찾는 file_search와 달리, 여기는 뜻이 비슷한 내용을 찾는다. 색인은
자동으로 되지 않고 index_local_documents를 부를 때만 만들어지거나 갱신된다 (색인할 때마다
Gemini 임베딩 API를 호출하므로 비용/시간이 들기 때문에 필요할 때만 명시적으로 돌린다).
"""

from . import local_index


# ---------------------------------------------------------------------------
# 35. index_local_documents / local_search
# ---------------------------------------------------------------------------
def index_local_documents():
    """문서·바탕화면 폴더의 문서를 훑어 검색용 색인을 만들거나 최신 상태로 갱신한다."""
    try:
        result = local_index.build_index()
    except Exception as e:
        return {"error": f"색인에 실패했습니다: {e}"}

    message = (
        f"{result['updated_files']}개 파일을 새로 색인했습니다 "
        f"(변경 없어 건너뛴 파일 {result['skipped_files']}개, 총 조각 {result['total_chunks']}개)."
    )
    if result["failed_files"]:
        message += f" {len(result['failed_files'])}개 파일은 내용을 읽지 못해 건너뛰었습니다."
    return {"message": message, **result}


index_local_documents_tool = {
    "type": "function",
    "name": "index_local_documents",
    "description": (
        "문서·바탕화면 폴더의 파일(.txt/.md/.pdf/.docx)을 훑어 의미 기반 검색용 색인을 만들거나 "
        "최신 상태로 갱신한다. local_search를 쓰기 전에 한 번 실행해야 하고, 파일을 추가·수정한 "
        "뒤 다시 실행하면 바뀐 파일만 새로 처리해서 빠르다. 시간이 좀 걸릴 수 있다고 미리 안내한다."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}


def local_search(query):
    """색인된 로컬 문서에서 query와 의미가 비슷한 부분을 찾는다."""
    try:
        results = local_index.search(query)
    except Exception as e:
        return {"error": f"검색에 실패했습니다: {e}"}

    if not results:
        return {
            "message": (
                "색인된 문서가 없거나 관련된 내용을 찾을 수 없습니다. "
                "먼저 index_local_documents로 색인해주세요."
            )
        }
    return {"results": results}


local_search_tool = {
    "type": "function",
    "name": "local_search",
    "description": (
        "색인해둔 로컬 문서(문서·바탕화면 폴더의 .txt/.md/.pdf/.docx)에서 질문과 의미가 비슷한 "
        "내용을 찾아 그 조각들을 돌려준다. 파일 이름이 아니라 내용 기반 검색이므로, 찾은 조각을 "
        "근거로 사용자 질문에 답한다. 색인이 안 돼 있으면 먼저 index_local_documents를 호출해야 한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "찾고 싶은 내용에 대한 질문이나 키워드"},
        },
        "required": ["query"],
    },
}
