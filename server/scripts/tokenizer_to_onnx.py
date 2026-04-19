"""e5-small-ko-v2 HF tokenizer → ONNX 변환 스모크.

배경:
  DJL HuggingFaceTokenizer가 Android arm64 native를 배포하지 않아 (P2-15)
  모바일에서 `libtokenizers.so` 로드 실패. onnxruntime-extensions로 tokenizer를
  ONNX 그래프에 내장하면 ORT 단일 런타임으로 전처리 가능 (P2-16).

사용 예:
  python -m scripts.tokenizer_to_onnx

산출물:
  .e5-ko-onnx/tokenizer.onnx  (ORT-extensions 사용)

주의:
  - 기존 model.onnx(INT8 quantized)와 **별도 session**으로 체이닝 (merge 금지)
  - tokenizer.onnx는 string ops라 INT8 quantize 금지
  - 실제 Android 통합은 Step 3에서
"""

from __future__ import annotations

import sys
from pathlib import Path

import onnx
from transformers import XLMRobertaTokenizer
from onnxruntime_extensions import gen_processing_models


# dragonkue/multilingual-e5-small-ko-v2는 XLM-RoBERTa-base에서 한국어로 fine-tune.
# Fine-tune은 vocab을 확장/수정하지 않으므로 xlm-roberta-base의 sentencepiece.bpe.model이 동일.
# AutoTokenizer가 dragonkue repo에서는 sentencepiece.bpe.model을 찾지 못해 Fast로 fallback되므로
# 원본 base 모델에서 slow 토크나이저(vocab_file=.bpe.model 경로 가진)를 직접 로드.
BASE_SPM_REPO = "xlm-roberta-base"
OUT_DIR = Path(__file__).resolve().parent.parent / ".e5-ko-onnx"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading XLM-R slow tokenizer (sentencepiece.bpe.model) from: {BASE_SPM_REPO}")
    tok = XLMRobertaTokenizer.from_pretrained(BASE_SPM_REPO)
    print(f"  type: {type(tok).__name__}")
    print(f"  vocab_file: {tok.vocab_file}")
    print(f"  vocab_size: {tok.vocab_size}")
    print(f"  model_max_length: {tok.model_max_length}")

    print("\nGenerating ONNX preprocessing graph...")
    pre_model, post_model = gen_processing_models(
        tok,
        pre_kwargs={"WITH_DEFAULT_INPUTS": True, "CAST_TOKEN_ID": True},
    )

    if pre_model is None:
        print("FATAL: pre-processing model generation returned None", file=sys.stderr)
        sys.exit(2)

    out_path = OUT_DIR / "tokenizer.onnx"
    onnx.save(pre_model, str(out_path))
    size_kb = out_path.stat().st_size / 1024
    print(f"\nSaved: {out_path}  ({size_kb:,.1f} KB)")

    # 그래프 구조 요약
    g = pre_model.graph
    print(f"\nGraph summary:")
    print(f"  inputs:  {[(i.name, _shape(i)) for i in g.input]}")
    print(f"  outputs: {[(o.name, _shape(o)) for o in g.output]}")
    print(f"  nodes:   {len(g.node)}")
    op_types = sorted({n.op_type for n in g.node})
    print(f"  op_types: {op_types}")


def _shape(tensor):
    try:
        dims = tensor.type.tensor_type.shape.dim
        return [d.dim_value if d.dim_value else (d.dim_param or "?") for d in dims]
    except Exception:
        return "?"


if __name__ == "__main__":
    main()
