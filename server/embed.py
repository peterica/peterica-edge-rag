"""Ollama 임베딩 API 클라이언트"""

import httpx
import struct

from config import OLLAMA_URL


async def embed(model: str, texts: list[str]) -> list[list[float]]:
    """Ollama /api/embed 호출 → 임베딩 벡터 리스트 반환"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": model, "input": texts},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


async def embed_one(model: str, text: str) -> list[float]:
    """단일 텍스트 임베딩"""
    vecs = await embed(model, [text])
    return vecs[0]


def vec_to_blob(vec: list[float]) -> bytes:
    """float 리스트 → sqlite-vec용 binary blob"""
    return struct.pack(f"{len(vec)}f", *vec)
