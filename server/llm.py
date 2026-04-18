"""Ollama chat API 클라이언트 — /query 응답 생성용"""

from __future__ import annotations

import httpx

from config import (
    OLLAMA_URL,
    SERVER_LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    LLM_TIMEOUT,
)


class LlmError(RuntimeError):
    """LLM 호출 실패 (Ollama 다운, 모델 미설치, 타임아웃 등)"""


async def chat_complete(
    system_prompt: str,
    user_message: str,
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
) -> str:
    """system+user 메시지를 Ollama /api/chat에 보내고 assistant 응답 텍스트만 반환.

    키워드 인자로 실험 시 모델/파라미터 override 가능 (None이면 config 기본값).
    """
    payload = {
        "model": model or SERVER_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {
            "temperature": temperature if temperature is not None else LLM_TEMPERATURE,
            "num_predict": max_tokens or LLM_MAX_TOKENS,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout or LLM_TIMEOUT) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        raise LlmError(f"Ollama 호출 실패: {e}") from e

    msg = data.get("message") or {}
    content = msg.get("content")
    if not content:
        raise LlmError(f"Ollama 응답에 content 없음: {data}")
    return content
