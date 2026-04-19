"""RAG 검색 + 시스템 프롬프트 생성 (peterica-blog-chat lib/rag.ts 포팅)"""

from __future__ import annotations

import json
import re

from db import get_server_db
from embed import embed_one, vec_to_blob
from embed_st import embed_st
from prompts import build_system_prompt_v4
from config import (
    SERVER_EMBED_MODEL,
    SERVER_EMBED_BACKEND,
    TOP_K,
    RAG_DISTANCE_MAX,
    RAG_MIN_K,
    RAG_MAX_K,
)


async def search_chunks(query: str) -> list[dict]:
    """쿼리 임베딩 → sqlite-vec cosine 검색 → 필터링 → top-k 반환"""
    db = get_server_db()
    if SERVER_EMBED_BACKEND == "sentence-transformers":
        # e5 계열은 query/passage 프리픽스 비대칭이 필수 — is_query=True 강제
        qv = embed_st(SERVER_EMBED_MODEL, [query], is_query=True)[0]
    else:
        qv = await embed_one(SERVER_EMBED_MODEL, query)
    blob = vec_to_blob(qv)

    rows = db.execute(
        """
        SELECT c.id, c.doc_path, c.title, c.heading, c.ord, c.text, c.tags, v.distance
        FROM chunk_vec v
        JOIN chunks c ON c.id = v.chunk_id
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (blob, TOP_K),
    ).fetchall()

    # doc_path 중복 제거 (출처 다양성)
    seen: set[str] = set()
    unique: list[dict] = []
    for r in rows:
        d = dict(r)
        if d["doc_path"] in seen:
            continue
        seen.add(d["doc_path"])
        unique.append(d)

    # distance 임계값 필터링
    passing = [r for r in unique if r["distance"] <= RAG_DISTANCE_MAX]

    # MIN_K 보장
    source = passing if len(passing) >= RAG_MIN_K else unique[:RAG_MIN_K]

    return source[:RAG_MAX_K]


def build_system_prompt(chunks: list[dict]) -> str:
    """검색된 청크로 시스템 프롬프트 구성 (v4: JSON 구조화 출력 + 주제 매칭 검사).

    벤치마크 근거로 v4 + gemma4:e4b-it 조합을 채택
    (CC=0.889, SR=0, CorrectRefuse=1.0). 자세한 비교는 PROGRESS.md 세션 로그 참조.
    """
    return build_system_prompt_v4(chunks)


def render_answer(raw: str) -> str:
    """LLM이 반환한 JSON 스키마 응답을 사람 가독 텍스트로 렌더.

    - grounded=false  → "문서에 근거 없음"
    - grounded=true   → "문장1 [#c]. 문장2 [#c][#c]." 형식
    - JSON 파싱 실패 → 원문 그대로 반환 (폴백)
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return raw

    if not data.get("grounded", False):
        return "문서에 근거 없음"

    parts: list[str] = []
    for s in data.get("sentences", []):
        text = (s.get("text") or "").strip()
        cites = s.get("cite") or []
        if not text:
            continue
        trailing = ""
        while text and text[-1] in ".?!":
            trailing = text[-1] + trailing
            text = text[:-1]
        if not trailing:
            trailing = "."
        cite_str = "".join(f"[#{c}]" for c in cites)
        parts.append(f"{text.rstrip()} {cite_str}{trailing}".strip())

    return " ".join(parts) if parts else "문서에 근거 없음"
