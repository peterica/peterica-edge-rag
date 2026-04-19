"""/sync + /sync/meta E2E smoke test.

사용 예:
  python -m scripts.sync_smoke
  BASE_URL=http://localhost:8600 SERVER_API_KEY=testkey python -m scripts.sync_smoke

검증 케이스:
  1) GET /sync/meta          → wiki_commit 획득
  2) GET /sync (no ETag)     → 200 + body > 0 + ETag 헤더
  3) GET /sync (matching)    → 304 (body 없음)
  4) GET /sync (bad ETag)    → 200 + body > 0
"""

from __future__ import annotations

import os
import sys

import httpx


BASE_URL = os.getenv("BASE_URL", "http://localhost:8600")
API_KEY = os.getenv("SERVER_API_KEY", "")


def auth_headers() -> dict:
    return {"X-API-Key": API_KEY} if API_KEY else {}


def fail(msg: str) -> None:
    print(f"  ✗ {msg}")
    sys.exit(1)


def main() -> None:
    print(f"Target: {BASE_URL}")
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        # Case 1: meta 조회
        r = client.get("/sync/meta", headers=auth_headers())
        if r.status_code != 200:
            fail(f"[1/4] /sync/meta → {r.status_code}, body={r.text[:200]}")
        meta = r.json()
        for k in ("wiki_commit", "ingested_at", "db_size_bytes"):
            if k not in meta:
                fail(f"[1/4] meta에 '{k}' 누락: {meta}")
        commit = meta["wiki_commit"]
        print(f"  ✓ [1/4] /sync/meta  wiki_commit={commit[:12]}...  size={meta['db_size_bytes']:,}B")

        # Case 2: ETag 없이 /sync
        r = client.get("/sync", headers=auth_headers())
        if r.status_code != 200:
            fail(f"[2/4] /sync(no ETag) → {r.status_code}")
        body_len = len(r.content)
        if body_len == 0:
            fail(f"[2/4] /sync body 비어있음")
        etag = r.headers.get("etag", "")
        if commit not in etag:
            fail(f"[2/4] ETag에 commit 누락: etag={etag}")
        print(f"  ✓ [2/4] /sync (no ETag)  200  body={body_len:,}B  ETag={etag}")

        # Case 3: 일치 ETag → 304
        r = client.get("/sync", headers={**auth_headers(), "If-None-Match": etag})
        if r.status_code != 304:
            fail(f"[3/4] /sync(matching ETag) → {r.status_code} (304 기대)")
        if len(r.content) != 0:
            fail(f"[3/4] 304 응답에 body 존재: {len(r.content)}B")
        print(f"  ✓ [3/4] /sync (matching ETag)  304  body=0B")

        # Case 4: 잘못된 ETag → 200
        bad = '"deadbeef"'
        r = client.get("/sync", headers={**auth_headers(), "If-None-Match": bad})
        if r.status_code != 200:
            fail(f"[4/4] /sync(bad ETag) → {r.status_code}")
        if len(r.content) == 0:
            fail(f"[4/4] /sync(bad ETag) body 비어있음")
        print(f"  ✓ [4/4] /sync (bad ETag)  200  body={len(r.content):,}B")

    print("\nAll 4 cases passed.")


if __name__ == "__main__":
    main()
