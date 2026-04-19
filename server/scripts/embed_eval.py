"""임베딩 모델 검색 품질 벤치마크 — bge-m3 / embeddinggemma / e5-small-ko-v2 비교.

사용 예:
  python -m scripts.embed_eval --output /tmp/embed_eval.json

지표:
  Recall@1: top-1 청크가 정답 문서에 속하는가
  Recall@3: top-3 중 정답 문서 청크가 있는가
  MRR:      첫 정답 청크의 역순위 평균 (1/rank, 미발견=0)
  EmbedLat: 쿼리+corpus 임베딩 총 시간(초)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))

from embed import embed as embed_ollama  # noqa: E402
from embed_st import embed_st as embed_st_fn  # noqa: E402
from config import SERVER_DB_PATH  # noqa: E402


MODELS = [
    {"name": "bge-m3", "backend": "ollama", "dim": 1024},
    {"name": "embeddinggemma:300m", "backend": "ollama", "dim": 768},
    {"name": "dragonkue/multilingual-e5-small-ko-v2", "backend": "st", "dim": 384},
]


def load_chunks() -> list[dict]:
    db = sqlite3.connect(SERVER_DB_PATH)
    db.row_factory = sqlite3.Row
    rows = db.execute("SELECT id, doc_path, heading, text FROM chunks").fetchall()
    db.close()
    return [dict(r) for r in rows]


def normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms < 1e-12, 1.0, norms)
    return matrix / norms


async def embed_batch(model_name: str, backend: str, texts: list[str], is_query: bool) -> list[list[float]]:
    if backend == "ollama":
        # Ollama는 query/passage 구분 없이 단일 API
        # bge-m3는 자체 prefix 없음, embeddinggemma는 Matryoshka 기본 768
        return await embed_ollama(model_name, texts)
    if backend == "st":
        return embed_st_fn(model_name, texts, is_query=is_query)
    raise ValueError(f"unknown backend: {backend}")


def compute_metrics(
    qvecs: np.ndarray,
    cvecs: np.ndarray,
    chunk_docs: list[str],
    queries: list[dict],
) -> dict:
    sim = normalize(qvecs) @ normalize(cvecs).T  # (Q, C)
    order = np.argsort(-sim, axis=1)  # 내림차순 top-k 인덱스

    r1 = 0
    r3 = 0
    mrr_sum = 0.0
    per_q = []
    for qi, q in enumerate(queries):
        relevant = set(q["relevant_docs"])
        ranks = order[qi]
        top1_doc = chunk_docs[ranks[0]]
        top3_docs = [chunk_docs[i] for i in ranks[:3]]

        hit1 = top1_doc in relevant
        hit3 = any(d in relevant for d in top3_docs)
        # MRR: 첫 relevant의 위치
        rr = 0.0
        for rank, idx in enumerate(ranks, start=1):
            if chunk_docs[idx] in relevant:
                rr = 1.0 / rank
                break

        r1 += int(hit1)
        r3 += int(hit3)
        mrr_sum += rr
        per_q.append({
            "q": q["q"],
            "expected": list(relevant),
            "top1": top1_doc,
            "top3": top3_docs,
            "hit1": hit1,
            "hit3": hit3,
            "rr": round(rr, 3),
        })

    n = len(queries)
    return {
        "recall_at_1": r1 / n,
        "recall_at_3": r3 / n,
        "mrr": mrr_sum / n,
        "per_query": per_q,
    }


async def eval_model(model: dict, chunks: list[dict], queries: list[dict]) -> dict:
    chunk_texts = [c["text"] for c in chunks]
    chunk_docs = [c["doc_path"] for c in chunks]
    query_texts = [q["q"] for q in queries]

    print(f"\n=== {model['name']} (dim={model['dim']}, {model['backend']}) ===", flush=True)

    t0 = time.perf_counter()
    cvecs = await embed_batch(model["name"], model["backend"], chunk_texts, is_query=False)
    t_chunks = time.perf_counter() - t0

    t0 = time.perf_counter()
    qvecs = await embed_batch(model["name"], model["backend"], query_texts, is_query=True)
    t_queries = time.perf_counter() - t0

    cvecs_np = np.array(cvecs, dtype=np.float32)
    qvecs_np = np.array(qvecs, dtype=np.float32)

    metrics = compute_metrics(qvecs_np, cvecs_np, chunk_docs, queries)
    metrics["chunks_s"] = round(t_chunks, 2)
    metrics["queries_s"] = round(t_queries, 2)
    metrics["embed_total_s"] = round(t_chunks + t_queries, 2)

    print(f"  chunks embed: {t_chunks:.2f}s | queries embed: {t_queries:.2f}s")
    print(f"  R@1={metrics['recall_at_1']:.3f}  R@3={metrics['recall_at_3']:.3f}  MRR={metrics['mrr']:.3f}")
    for pq in metrics["per_query"]:
        tag = "✓" if pq["hit1"] else ("~" if pq["hit3"] else "✗")
        print(f"    [{tag}] rr={pq['rr']:.2f}  {pq['q'][:55]}")
    return metrics


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queries",
        default=str(SERVER_DIR / "scripts/retrieval_test_queries.json"),
    )
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    with open(args.queries, encoding="utf-8") as f:
        queries = json.load(f)
    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunks, {len(queries)} queries")

    results: list[dict] = []
    for model in MODELS:
        r = await eval_model(model, chunks, queries)
        r["model"] = model["name"]
        r["dim"] = model["dim"]
        r["backend"] = model["backend"]
        results.append(r)

    print("\n=== SUMMARY ===")
    hdr = f"{'model':45} {'dim':>5} {'R@1':>7} {'R@3':>7} {'MRR':>7} {'embed_s':>9}"
    print(hdr)
    for r in results:
        print(
            f"{r['model'][:45]:45} {r['dim']:5} "
            f"{r['recall_at_1']:7.3f} {r['recall_at_3']:7.3f} "
            f"{r['mrr']:7.3f} {r['embed_total_s']:9.2f}"
        )

    if args.output:
        Path(args.output).write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n결과 저장: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
