"""X-API-Key 기반 간단 인증 — FastAPI Depends로 보호 엔드포인트에 부착.

- SERVER_API_KEY 환경변수가 비어 있으면 인증 비활성 (로컬 개발용).
- 설정된 경우 X-API-Key 헤더가 정확히 일치해야 통과.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from config import SERVER_API_KEY


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not SERVER_API_KEY:
        return  # 인증 비활성

    if x_api_key is None or not hmac.compare_digest(x_api_key, SERVER_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )
