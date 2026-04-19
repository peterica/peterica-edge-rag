"""SQLite + sqlite-vec 데이터베이스 관리 (서버/모바일 듀얼 DB)"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import sqlite_vec

from config import SERVER_DB_PATH, MOBILE_DB_PATH, SERVER_EMBED_DIM, MOBILE_EMBED_DIM


def _init_db(db_path: str, embed_dim: int) -> sqlite3.Connection:
    """DB 초기화: 디렉토리 생성 + 테이블 + sqlite-vec 로드"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    conn.execute("PRAGMA journal_mode=WAL")
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_path TEXT NOT NULL,
            title TEXT,
            heading TEXT,
            ord INTEGER NOT NULL,
            text TEXT NOT NULL,
            tags TEXT,
            source_hash TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_path);
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vec USING vec0(
            chunk_id INTEGER PRIMARY KEY,
            embedding float[{embed_dim}] distance_metric=cosine
        );
        -- 모바일용: sqlite-vec 확장 없이 읽기 가능한 일반 테이블 (BLOB = float32 LE)
        CREATE TABLE IF NOT EXISTS chunk_embeddings (
            chunk_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    return conn


_server_db: sqlite3.Connection | None = None
_mobile_db: sqlite3.Connection | None = None


def get_server_db() -> sqlite3.Connection:
    global _server_db
    if _server_db is None:
        _server_db = _init_db(SERVER_DB_PATH, SERVER_EMBED_DIM)
    return _server_db


def get_mobile_db() -> sqlite3.Connection:
    global _mobile_db
    if _mobile_db is None:
        _mobile_db = _init_db(MOBILE_DB_PATH, MOBILE_EMBED_DIM)
    return _mobile_db


def reset_db(conn: sqlite3.Connection):
    """테이블 데이터 전체 삭제 (ingest 재실행 시)"""
    conn.execute("DELETE FROM chunk_vec")
    conn.execute("DELETE FROM chunk_embeddings")
    conn.execute("DELETE FROM chunks")
    conn.commit()


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None
