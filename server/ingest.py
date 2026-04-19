"""듀얼 임베딩 ingest 스크립트

위키 마크다운 → 청킹 → bge-m3 + EmbeddingGemma 임베딩 → server.db + mobile.db
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from chunk import parse_markdown, chunk_section
from db import get_server_db, get_mobile_db, reset_db, set_meta
from embed import embed, vec_to_blob
from embed_st import embed_st
from config import (
    WIKI_DIR,
    SERVER_EMBED_MODEL,
    SERVER_EMBED_BACKEND,
    MOBILE_EMBED_MODEL,
    MOBILE_EMBED_BACKEND,
)


def get_wiki_commit(wiki_dir: str) -> str:
    """위키 저장소의 HEAD 커밋 해시. git 실패 시 'unknown' 반환."""
    try:
        out = subprocess.run(
            ["git", "-C", wiki_dir, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return out.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"

BATCH_SIZE = 32


def walk_md(wiki_dir: str) -> list[Path]:
    """재귀적으로 .md 파일 수집"""
    return sorted(Path(wiki_dir).rglob("*.md"))


async def ingest_model(
    model: str,
    conn,
    embed_dim: int,
    all_chunks: list[dict],
    label: str,
    backend: str = "ollama",  # ollama | sentence-transformers
):
    """단일 모델로 전체 청크를 임베딩하여 DB에 저장"""
    reset_db(conn)

    # 청크 메타데이터 삽입
    for c in all_chunks:
        cursor = conn.execute(
            """INSERT INTO chunks(doc_path, title, heading, ord, text, tags, source_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (c["doc_path"], c["title"], c["heading"], c["ord"],
             c["text"], c["tags"], c["source_hash"]),
        )
        c[f"{label}_id"] = cursor.lastrowid
    conn.commit()

    # 배치 임베딩
    texts = [c["text"] for c in all_chunks]
    total = 0
    t0 = time.time()

    for i in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[i : i + BATCH_SIZE]
        batch_chunks = all_chunks[i : i + BATCH_SIZE]
        if backend == "sentence-transformers":
            vecs = embed_st(model, batch_texts, is_query=False)
        else:
            vecs = await embed(model, batch_texts)

        for c, v in zip(batch_chunks, vecs):
            blob = vec_to_blob(v)
            cid = c[f"{label}_id"]
            conn.execute(
                "INSERT INTO chunk_vec(chunk_id, embedding) VALUES (?, ?)",
                (cid, blob),
            )
            conn.execute(
                "INSERT INTO chunk_embeddings(chunk_id, embedding) VALUES (?, ?)",
                (cid, blob),
            )
        total += len(batch_texts)

    conn.commit()
    elapsed = time.time() - t0
    print(f"  [{label}] {model} ({backend}): {total} chunks, {embed_dim}dim, {elapsed:.1f}s")


async def main():
    wiki_dir = WIKI_DIR
    if not Path(wiki_dir).exists():
        print(f"WIKI_DIR not found: {wiki_dir}", file=sys.stderr)
        sys.exit(1)

    files = walk_md(wiki_dir)
    print(f"found {len(files)} markdown files under {wiki_dir}")

    # Step 1: 파싱 + 청킹
    all_chunks: list[dict] = []
    for fp in files:
        raw = fp.read_text(encoding="utf-8")
        rel = str(fp.relative_to(wiki_dir))
        fallback = fp.stem
        parsed = parse_markdown(raw, fallback)
        tags = json.dumps(parsed.frontmatter.get("tags", []))
        source_hash = hashlib.sha1(raw.encode()).hexdigest()

        ord_idx = 0
        for sec in parsed.sections:
            for chunk_text in chunk_section(sec["heading"], sec["body"]):
                all_chunks.append({
                    "doc_path": rel,
                    "title": parsed.title,
                    "heading": sec["heading"],
                    "ord": ord_idx,
                    "text": chunk_text,
                    "tags": tags,
                    "source_hash": source_hash,
                })
                ord_idx += 1

    print(f"parsed {len(all_chunks)} chunks from {len(files)} files")

    # Step 2: 듀얼 임베딩 (순차)
    from config import SERVER_EMBED_DIM, MOBILE_EMBED_DIM

    print(f"\n--- Server DB ({SERVER_EMBED_MODEL}) ---")
    await ingest_model(
        SERVER_EMBED_MODEL, get_server_db(), SERVER_EMBED_DIM, all_chunks, "server",
        backend=SERVER_EMBED_BACKEND,
    )

    print(f"\n--- Mobile DB ({MOBILE_EMBED_MODEL}) ---")
    await ingest_model(
        MOBILE_EMBED_MODEL, get_mobile_db(), MOBILE_EMBED_DIM, all_chunks, "mobile",
        backend=MOBILE_EMBED_BACKEND,
    )

    wiki_commit = get_wiki_commit(wiki_dir)
    ingested_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for conn in (get_server_db(), get_mobile_db()):
        set_meta(conn, "wiki_commit", wiki_commit)
        set_meta(conn, "ingested_at", ingested_at)
    print(f"\nMeta: wiki_commit={wiki_commit[:12]}... ingested_at={ingested_at}")
    print("Done. server.db + mobile.db generated.")


if __name__ == "__main__":
    asyncio.run(main())
