"""ONNX 모델 INT8 양자화 + 모바일 assets 배치"""

import shutil
from pathlib import Path
from onnxruntime.quantization import quantize_dynamic, QuantType

SRC = Path(".e5-ko-onnx")
OUT = Path(".e5-ko-onnx/model_int8.onnx")
ASSETS = Path("../mobile/app/src/main/assets")

print("INT8 양자화 중...")
quantize_dynamic(
    model_input=str(SRC / "model.onnx"),
    model_output=str(OUT),
    weight_type=QuantType.QInt8,
)

orig_mb = (SRC / "model.onnx").stat().st_size / 1024 / 1024
int8_mb = OUT.stat().st_size / 1024 / 1024
print(f"원본: {orig_mb:.1f}MB → INT8: {int8_mb:.1f}MB ({int8_mb/orig_mb*100:.0f}%)")

ASSETS.mkdir(parents=True, exist_ok=True)
shutil.copy(OUT, ASSETS / "model.onnx")
shutil.copy(SRC / "tokenizer.json", ASSETS / "tokenizer.json")

print(f"\nassets에 배치 완료:")
for f in ASSETS.iterdir():
    mb = f.stat().st_size / 1024 / 1024
    print(f"  {f.name}: {mb:.1f}MB")
