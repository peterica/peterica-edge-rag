"""검색 경로 A/B 비교 — sqlite-vec vs Python brute-force cosine.

배경:
  서버 프로덕션: `chunk_vec`(sqlite-vec vec0 virtual table, MATCH 쿼리)
  모바일 런타임: `chunk_embeddings`(일반 TABLE의 BLOB) + JVM 측 brute-force cosine
  P3-3에서 서버·모바일 모델을 e5-small-ko-v2(384d)로 통일하고 ingest가 두 경로에
  동일 벡터를 기록. 따라서 "같은 쿼리에 두 경로가 같은 top-k를 돌려주는가"를
  서버 파이썬에서 재현해 모바일 알고리즘의 정확성을 폰 실기 없이 검증한다.

사용 예:
  python -m scripts.search_ab
  python -m scripts.search_ab --queries scripts/retrieval_test_queries_extended.json \\
      --output /tmp/search_ab_extended.json

지표:
  top1_match      : 두 경로의 top-1 청크 id 일치
  top3_set_match  : 두 경로의 top-3 청크 id 집합 일치 (순서 무시)
  top3_rank_match : 두 경로의 top-3 청크 id 순서까지 일치
  max_dist_delta  : 동일 청크의 두 경로 거리 최대 차이 (float32 정밀도 감지)
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))

from db import get_server_db  # noqa: E402
from embed_st import embed_st  # noqa: E402
from config import SERVER_EMBED_MODEL  # noqa: E402


DIM = 384  # e5-small-ko-v2
TOP_K = 12


def blob_to_vec(blob: bytes) -> np.ndarray:
    """sqlite-vec용 binary blob → numpy float32 1D."""
    return np.frombuffer(blob, dtype=np.float32)


def load_brute_force_matrix(conn) -> tuple[np.ndarray, list[int]]:
    """chunk_embeddings에서 전체 벡터 로드 → (N, DIM) 행렬 + chunk_id 목록."""
    rows = conn.execute(
        "SELECT chunk_id, embedding FROM chunk_embeddings ORDER BY chunk_id"
    ).fetchall()
    ids = [r["chunk_id"] for r in rows]
    mat = np.stack([blob_to_vec(r["embedding"]) for r in rows])
    # L2 정규화 (e5는 이미 normalized지만 안전하게 재정규화)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms < 1e-12, 1.0, norms)
    return mat / norms, ids


def path_a_sqlite_vec(conn, qvec: np.ndarray, k: int) -> list[tuple[int, float]]:
    """프로덕션 경로: sqlite-vec MATCH."""
    blob = struct.pack(f"{len(qvec)}f", *qvec.tolist())
    rows = conn.execute(
        """
        SELECT chunk_id, distance
        FROM chunk_vec
        WHERE embedding MATCH ? AND k = ?
        ORDER BY distance
        """,
        (blob, k),
    ).fetchall()
    return [(r["chunk_id"], float(r["distance"])) for r in rows]


def path_b_brute_force(
    mat: np.ndarray, ids: list[int], qvec: np.ndarray, k: int
) -> list[tuple[int, float]]:
    """모바일 경로 재현: numpy brute-force cosine distance = 1 - dot(normalized)."""
    q = qvec / max(np.linalg.norm(qvec), 1e-12)
    sims = mat @ q  # (N,)
    dists = 1.0 - sims
    order = np.argsort(dists)[:k]
    return [(ids[i], float(dists[i])) for i in order]


def compare_one(query: str, mat, ids, conn, chunk_doc: dict) -> dict:
    qv_list = embed_st(SERVER_EMBED_MODEL, [query], is_query=True)[0]
    qvec = np.array(qv_list, dtype=np.float32)

    t0 = time.perf_counter()
    a = path_a_sqlite_vec(conn, qvec, TOP_K)
    t_a = time.perf_counter() - t0

    t0 = time.perf_counter()
    b = path_b_brute_force(mat, ids, qvec, TOP_K)
    t_b = time.perf_counter() - t0

    a_ids = [cid for cid, _ in a]
    b_ids = [cid for cid, _ in b]

    a_dist = {cid: d for cid, d in a}
    b_dist = {cid: d for cid, d in b}

    top1_match = a_ids[0] == b_ids[0]
    top3_set_match = set(a_ids[:3]) == set(b_ids[:3])
    top3_rank_match = a_ids[:3] == b_ids[:3]
    topk_set_match = set(a_ids) == set(b_ids)
    topk_rank_match = a_ids == b_ids

    # 공통 청크의 거리 차이
    common = set(a_ids) & set(b_ids)
    if common:
        max_dist_delta = max(abs(a_dist[c] - b_dist[c]) for c in common)
    else:
        max_dist_delta = None

    return {
        "q": query,
        "top1_a": {"cid": a_ids[0], "doc": chunk_doc.get(a_ids[0], "?"), "d": a_dist[a_ids[0]]},
        "top1_b": {"cid": b_ids[0], "doc": chunk_doc.get(b_ids[0], "?"), "d": b_dist[b_ids[0]]},
        "top3_a_ids": a_ids[:3],
        "top3_b_ids": b_ids[:3],
        "top1_match": top1_match,
        "top3_set_match": top3_set_match,
        "top3_rank_match": top3_rank_match,
        "topk_set_match": topk_set_match,
        "topk_rank_match": topk_rank_match,
        "max_dist_delta": max_dist_delta,
        "latency_a_ms": round(t_a * 1000, 2),
        "latency_b_ms": round(t_b * 1000, 2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queries",
        default=str(SERVER_DIR / "scripts/retrieval_test_queries_extended.json"),
    )
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    with open(args.queries, encoding="utf-8") as f:
        queries = json.load(f)

    conn = get_server_db()
    mat, ids = load_brute_force_matrix(conn)
    chunk_doc = {
        r["id"]: r["doc_path"]
        for r in conn.execute("SELECT id, doc_path FROM chunks").fetchall()
    }
    print(f"Loaded {mat.shape[0]} chunks into brute-force matrix (dim={mat.shape[1]})")
    print(f"Queries: {len(queries)}  (from {args.queries})")
    print()

    results = []
    for q in queries:
        r = compare_one(q["q"], mat, ids, conn, chunk_doc)
        r["category"] = q.get("category", "baseline")
        results.append(r)

    # 요약
    n = len(results)
    top1 = sum(r["top1_match"] for r in results)
    top3_set = sum(r["top3_set_match"] for r in results)
    top3_rank = sum(r["top3_rank_match"] for r in results)
    topk_set = sum(r["topk_set_match"] for r in results)
    topk_rank = sum(r["topk_rank_match"] for r in results)
    deltas = [r["max_dist_delta"] for r in results if r["max_dist_delta"] is not None]

    print(f"{'metric':20} {'pass':>6} {'/':>2} {'total':>5} {'rate':>7}")
    print(f"{'top1_match':20} {top1:>6} {'/':>2} {n:>5} {top1/n:>6.1%}")
    print(f"{'top3_set_match':20} {top3_set:>6} {'/':>2} {n:>5} {top3_set/n:>6.1%}")
    print(f"{'top3_rank_match':20} {top3_rank:>6} {'/':>2} {n:>5} {top3_rank/n:>6.1%}")
    print(f"{'topk_set_match':20} {topk_set:>6} {'/':>2} {n:>5} {topk_set/n:>6.1%}")
    print(f"{'topk_rank_match':20} {topk_rank:>6} {'/':>2} {n:>5} {topk_rank/n:>6.1%}")
    print()
    if deltas:
        print(f"거리값 최대 차이: mean={np.mean(deltas):.2e}  max={max(deltas):.2e}")
    mean_a = np.mean([r["latency_a_ms"] for r in results])
    mean_b = np.mean([r["latency_b_ms"] for r in results])
    print(f"지연(ms): path_a(sqlite-vec)={mean_a:.2f}  path_b(brute-force)={mean_b:.2f}")

    # 불일치 상세
    mismatches = [r for r in results if not r["topk_rank_match"]]
    if mismatches:
        print(f"\n=== topk rank 불일치 {len(mismatches)}건 ===")
        for r in mismatches:
            print(f"  [{r['category']}] {r['q'][:60]}")
            print(f"    A top3: {r['top3_a_ids']} → {r['top1_a']['doc']}")
            print(f"    B top3: {r['top3_b_ids']} → {r['top1_b']['doc']}")

    if args.output:
        Path(args.output).write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n결과 저장: {args.output}")


if __name__ == "__main__":
    main()
