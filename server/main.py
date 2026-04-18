"""FastAPI 서버 — /query (RAG 응답) + /sync (모바일 DB) + /search (검색 테스트)"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from auth import require_api_key
from config import MOBILE_DB_PATH, HOST, PORT
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


@app.get("/sync", dependencies=[Depends(require_api_key)])
async def sync():
    """모바일 DB 파일 다운로드"""
    return FileResponse(
        path=MOBILE_DB_PATH,
        media_type="application/octet-stream",
        filename="mobile.db",
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
