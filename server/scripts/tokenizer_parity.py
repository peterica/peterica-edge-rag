"""Tokenizer parity: HF Fast (DJL 래핑) vs ONNX (ORT-extensions).

P2-16 Step 2. e5 프리픽스 포함 확장 쿼리 22건에 대해 input_ids byte-exact 일치 검증.
한 건이라도 어긋나면 P3-1에서 확보한 검색 경로 등가성이 무너짐 → Plan B 재자문 필요.

사용 예:
  python -m scripts.tokenizer_parity
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from onnxruntime_extensions import get_library_path
from transformers import AutoTokenizer


SERVER_DIR = Path(__file__).resolve().parent.parent
TOKENIZER_ONNX = SERVER_DIR / ".e5-ko-onnx/tokenizer.onnx"
QUERIES_JSON = SERVER_DIR / "scripts/retrieval_test_queries_extended.json"
MODEL_ID = "dragonkue/multilingual-e5-small-ko-v2"


def load_onnx_session():
    so = ort.SessionOptions()
    so.register_custom_ops_library(get_library_path())
    return ort.InferenceSession(str(TOKENIZER_ONNX), so, providers=["CPUExecutionProvider"])


def onnx_encode(sess, text: str) -> list[int]:
    out = sess.run(None, {"inputs": np.array([text])})
    # 출력 이름: tokens_cast, instance_indices, token_indices
    names = [o.name for o in sess.get_outputs()]
    tokens_idx = names.index("tokens_cast")
    return out[tokens_idx].tolist()


def main():
    if not TOKENIZER_ONNX.exists():
        print(f"tokenizer.onnx not found: {TOKENIZER_ONNX}", file=sys.stderr)
        sys.exit(2)

    print("Loading tokenizers...")
    hf = AutoTokenizer.from_pretrained(MODEL_ID)  # Fast (Rust, DJL과 동일 엔진)
    sess = load_onnx_session()
    print(f"  hf type: {type(hf).__name__}")
    print(f"  onnx outputs: {[o.name for o in sess.get_outputs()]}")

    with open(QUERIES_JSON, encoding="utf-8") as f:
        queries_data = json.load(f)
    queries = [q["q"] for q in queries_data]

    # e5 프리픽스 고려해 query/passage 두 가지로 생성
    samples: list[str] = []
    for q in queries:
        samples.append(f"query: {q}")
        # 대표 문서 청크 하나 추가 (passage 케이스 — 긴 한국어)
    samples.append("passage: Kubernetes는 컨테이너 오케스트레이션 시스템입니다. graceful shutdown은 SIGTERM 처리 후 일정 시간 내에 종료하는 패턴입니다.")
    samples.append("passage: What is Kubernetes graceful shutdown in English context?")

    n = len(samples)
    mismatches = []
    print(f"\nParity check: {n} samples")
    for i, text in enumerate(samples):
        hf_ids = hf.encode(text)  # default: with special tokens
        onnx_ids = onnx_encode(sess, text)
        match = hf_ids == onnx_ids
        tag = "✓" if match else "✗"
        preview = text[:50] + ("…" if len(text) > 50 else "")
        print(f"  [{tag}] len(hf)={len(hf_ids):3} len(onnx)={len(onnx_ids):3}  {preview}")
        if not match:
            mismatches.append({
                "text": text,
                "hf": hf_ids,
                "onnx": onnx_ids,
            })

    if mismatches:
        print(f"\n=== MISMATCH {len(mismatches)}/{n} ===")
        for m in mismatches[:3]:
            print(f"  text: {m['text']}")
            print(f"    hf   ({len(m['hf'])}): {m['hf'][:30]}...")
            print(f"    onnx ({len(m['onnx'])}): {m['onnx'][:30]}...")
            # 첫 diff 위치
            for j in range(min(len(m["hf"]), len(m["onnx"]))):
                if m["hf"][j] != m["onnx"][j]:
                    print(f"    first diff @ pos {j}: hf={m['hf'][j]} onnx={m['onnx'][j]}")
                    break
        sys.exit(1)

    print(f"\nAll {n} samples byte-exact match. Parity holds.")


if __name__ == "__main__":
    main()
