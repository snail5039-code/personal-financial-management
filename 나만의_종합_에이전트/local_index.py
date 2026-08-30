"""로컬 문서 색인 및 의미 기반 검색 (RAG).

문서(.txt/.md/.pdf/.docx)를 문단 단위로 잘라 Gemini 임베딩으로 벡터화해서 저장해두고,
질문이 오면 같은 방식으로 벡터화해서 코사인 유사도가 가장 가까운 조각을 찾아 돌려준다.
파일이 마지막 색인 이후 바뀌지 않았으면(수정 시각 비교) 다시 임베딩하지 않아서 API 호출과
시간을 아낀다. 청크는 여러 개를 한 번에 묶어서 보내(배치) 호출 수를 더 줄인다.
"""

import json
import os
import sys

import numpy as np
from dotenv import load_dotenv
from google import genai
from pypdf import PdfReader
import docx

# PyInstaller로 얼린 실행 파일 안에서는 __file__ 기반 경로가 exe가 실제로 있는 폴더를
# 가리키지 않는다 - sys.executable 기준으로 잡아야 .env/data를 exe 옆에서 제대로 찾는다.
THIS_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(THIS_DIR, ".env"))

INDEX_PATH = os.path.join(THIS_DIR, "data", "local_index.json")

EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150
BATCH_SIZE = 20
SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
SKIP_DIR_NAMES = {"node_modules", "__pycache__", "$RECYCLE.BIN"}

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def default_search_dirs():
    """색인 대상 기본 폴더 - 자료가 가장 많이 모여있는 문서·바탕화면."""
    home = os.path.expanduser("~")
    return [os.path.join(home, "Documents"), os.path.join(home, "Desktop")]


def _extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".txt", ".md"):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        if ext == ".pdf":
            reader = PdfReader(path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if ext == ".docx":
            document = docx.Document(path)
            return "\n".join(p.text for p in document.paragraphs)
    except Exception:
        return ""
    return ""


def _chunk_text(text):
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_CHARS
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def _iter_documents(roots):
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".")]
            for filename in filenames:
                if os.path.splitext(filename)[1].lower() in SUPPORTED_EXTENSIONS:
                    yield os.path.join(dirpath, filename)


def _load_index():
    if not os.path.exists(INDEX_PATH):
        return {"files": {}, "chunks": []}
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"files": {}, "chunks": []}


def _save_index(index):
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)


def _embed_batch(texts, task_type):
    client = _get_client()
    embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        result = client.models.embed_content(
            model=EMBED_MODEL,
            contents=batch,
            config={"task_type": task_type, "output_dimensionality": EMBED_DIM},
        )
        embeddings.extend(e.values for e in result.embeddings)
    return embeddings


def build_index(extra_dirs=None):
    """문서를 훑어 색인을 만들거나 갱신한다. 마지막 색인 이후 안 바뀐 파일은 건너뛴다."""
    roots = default_search_dirs() + list(extra_dirs or [])
    index = _load_index()
    known_files = index["files"]
    chunks = list(index["chunks"])

    updated_files = 0
    skipped_files = 0
    failed_files = []
    seen_paths = set()

    for path in _iter_documents(roots):
        seen_paths.add(path)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue

        if path in known_files and known_files[path]["mtime"] == mtime:
            skipped_files += 1
            continue

        text = _extract_text(path)
        pieces = _chunk_text(text)
        if not pieces:
            failed_files.append(path)
            continue

        try:
            vectors = _embed_batch(pieces, "RETRIEVAL_DOCUMENT")
        except Exception:
            failed_files.append(path)
            continue

        chunks = [c for c in chunks if c["path"] != path]
        for piece, vector in zip(pieces, vectors):
            chunks.append({"path": path, "text": piece, "embedding": vector})

        known_files[path] = {"mtime": mtime}
        updated_files += 1

    removed = [p for p in known_files if p not in seen_paths]
    for p in removed:
        known_files.pop(p, None)
    if removed:
        chunks = [c for c in chunks if c["path"] not in removed]

    _save_index({"files": known_files, "chunks": chunks})

    return {
        "updated_files": updated_files,
        "skipped_files": skipped_files,
        "removed_files": len(removed),
        "failed_files": failed_files,
        "total_chunks": len(chunks),
    }


def search(query, top_k=5):
    """색인된 청크 중 query와 의미가 가까운 것을 코사인 유사도 기준으로 상위 top_k개 돌려준다."""
    index = _load_index()
    chunks = index["chunks"]
    if not chunks:
        return []

    query_vector = np.array(_embed_batch([query], "RETRIEVAL_QUERY")[0])
    query_norm = np.linalg.norm(query_vector)

    scored = []
    for chunk in chunks:
        vector = np.array(chunk["embedding"])
        denom = query_norm * np.linalg.norm(vector)
        score = float(np.dot(query_vector, vector) / denom) if denom else 0.0
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"path": c["path"], "text": c["text"], "score": round(score, 3)}
        for score, c in scored[:top_k]
    ]
