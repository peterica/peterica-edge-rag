"""INT8 ONNX 모델 품질 검증 — 원본 Python 모델과 비교"""

import numpy as np
import onnxruntime as ort
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

MODEL_ID = "dragonkue/multilingual-e5-small-ko-v2"
ONNX_PATH = ".e5-ko-onnx/model_int8.onnx"

TEST_QUERIES = [
    "쿠버네티스에서 헬스 체크는 어떻게 하나요?",
    "메트릭 수집 방법이 궁금합니다",
    "RAG가 뭔가요?",
]


def embed_onnx(session, tokenizer, text: str) -> np.ndarray:
    """ONNX로 임베딩 생성 + mean pooling + L2 정규화"""
    enc = tokenizer(f"query: {text}", return_tensors="np", truncation=True, max_length=512)
    outputs = session.run(None, {
        "input_ids": enc["input_ids"].astype(np.int64),
        "attention_mask": enc["attention_mask"].astype(np.int64),
    })
    token_embeddings = outputs[0][0]  # [seq, 384]
    mask = enc["attention_mask"][0]
    mask_expanded = np.expand_dims(mask, -1).astype(np.float32)
    sum_embeddings = (token_embeddings * mask_expanded).sum(axis=0)
    sum_mask = mask_expanded.sum()
    pooled = sum_embeddings / max(sum_mask, 1e-9)
    norm = np.linalg.norm(pooled)
    return pooled / norm if norm > 0 else pooled


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


print("원본 모델 로드 중...")
st_model = SentenceTransformer(MODEL_ID)

print("INT8 ONNX 모델 로드 중...")
session = ort.InferenceSession(ONNX_PATH)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

print("\n임베딩 비교:")
print(f"{'쿼리':<35} | {'유사도':>8} | {'ONNX dim'}")
print("-" * 65)

for q in TEST_QUERIES:
    ref = st_model.encode(f"query: {q}", normalize_embeddings=True)
    onnx_vec = embed_onnx(session, tokenizer, q)
    sim = cosine(ref, onnx_vec)
    status = "✓" if sim > 0.98 else "⚠" if sim > 0.90 else "✗"
    print(f"{q[:33]:<35} | {sim:>8.4f} | {len(onnx_vec)} {status}")

print("\n품질 기준: cosine 유사도 > 0.98 = INT8 양자화가 원본과 거의 동일")
