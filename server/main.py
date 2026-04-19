"""FastAPI 서버 — /query (RAG 응답) + /sync (모바일 DB) + /search (검색 테스트)"""

from __future__ import annotations

import os
import sqlite3

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from auth import require_api_key
from config import MOBILE_DB_PATH, HOST, PORT
from db import get_meta
from rag import search_chunks, build_system_prompt, render_answer
from llm import chat_complete, LlmError

app = FastAPI(title="peterica-edge-rag", version="0.1.0")


class QueryRequest(BaseModel):
    question: str


class Citation(BaseModel):
    index: int
    doc_path: str
    heading: str | None


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    system_prompt: str  # 디버깅용, 프로덕션에서 제거 가능


class SearchResult(BaseModel):
    doc_path: str
    heading: str | None
    distance: float
    preview: str


@app.post("/query", dependencies=[Depends(require_api_key)])
async def query(req: QueryRequest) -> QueryResponse:
    """RAG 검색 → 시스템 프롬프트 → Ollama LLM 생성 → 응답"""
    chunks = await search_chunks(req.question)
    system_prompt = build_system_prompt(chunks)

    citations = [
        Citation(
            index=i + 1,
            doc_path=c["doc_path"],
            heading=c.get("heading"),
        )
        for i, c in enumerate(chunks)
    ]

    try:
        raw = await chat_complete(system_prompt, req.question)
    except LlmError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "error": str(e),
                "system_prompt": system_prompt,
                "citations": [c.model_dump() for c in citations],
            },
        )

    answer = render_answer(raw)

    return QueryResponse(
        answer=answer,
        citations=citations,
        system_prompt=system_prompt,
    )


@app.get("/search", dependencies=[Depends(require_api_key)])
async def search(q: str, k: int = 3) -> list[SearchResult]:
    """벡터 검색 테스트 엔드포인트 (LLM 없이 검색 결과만)"""
    chunks = await search_chunks(q)
    return [
        SearchResult(
            doc_path=c["doc_path"],
            heading=c.get("heading"),
            distance=c["distance"],
            preview=c["text"][:200],
        )
        for c in chunks[:k]
    ]


def _read_mobile_meta() -> dict:
    """mobile.db에서 sync 메타 정보 독립 커넥션으로 조회."""
    conn = sqlite3.connect(MOBILE_DB_PATH)
    try:
        wiki_commit = get_meta(conn, "wiki_commit") or "unknown"
        ingested_at = get_meta(conn, "ingested_at") or "unknown"
        # sync_etag 미존재(구 ingest) 시 wiki_commit으로 폴백
        sync_etag = get_meta(conn, "sync_etag") or wiki_commit
    finally:
        conn.close()
    size = os.path.getsize(MOBILE_DB_PATH) if os.path.exists(MOBILE_DB_PATH) else 0
    return {
        "wiki_commit": wiki_commit,
        "ingested_at": ingested_at,
        "sync_etag": sync_etag,
        "db_size_bytes": size,
    }


@app.get("/sync/meta", dependencies=[Depends(require_api_key)])
async def sync_meta() -> dict:
    """mobile.db 동기화 메타데이터 (다운로드 없이 클라이언트 캐시 검증용)."""
    return _read_mobile_meta()


@app.get("/sync", dependencies=[Depends(require_api_key)])
async def sync(if_none_match: str | None = Header(default=None)):
    """모바일 DB 파일 다운로드. sync_etag(wiki_commit+chunker_version) 기반 ETag/304 캐시 지원."""
    meta = _read_mobile_meta()
    # ETag = wiki commit + chunker version (청킹 로직 bump 시 강제 재다운로드)
    etag = f'"{meta["sync_etag"]}"'

    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers={"ETag": etag})

    return FileResponse(
        path=MOBILE_DB_PATH,
        media_type="application/octet-stream",
        filename="mobile.db",
        headers={"ETag": etag},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
