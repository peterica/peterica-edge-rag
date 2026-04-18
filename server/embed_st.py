"""sentence-transformers 기반 임베딩 (Ollama에 없는 모델용)

Phase 1: multilingual-e5-small-ko-v2 (384dim) — 모바일 DB 생성용
"""

from sentence_transformers import SentenceTransformer

_model_cache: dict[str, SentenceTransformer] = {}


def get_model(model_id: str) -> SentenceTransformer:
    """모델 로드 (캐시)"""
    if model_id not in _model_cache:
        _model_cache[model_id] = SentenceTransformer(model_id)
    return _model_cache[model_id]


def embed_st(model_id: str, texts: list[str], is_query: bool = False) -> list[list[float]]:
    """sentence-transformers 임베딩 (e5 계열 프리픽스 자동 적용)"""
    model = get_model(model_id)
    prefix = "query: " if is_query else "passage: "
    prefixed = [f"{prefix}{t}" for t in texts]
    vectors = model.encode(prefixed, normalize_embeddings=True, batch_size=32)
    return vectors.tolist()
