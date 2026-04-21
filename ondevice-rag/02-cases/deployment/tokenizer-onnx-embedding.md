# Case · 토크나이저를 ONNX 그래프에 내장하기

## 문제

임베딩은 모델 파일 하나로 끝나지 않는다.
**문자열 → 토큰 ID 변환**을 담당하는 토크나이저가 같이 필요하고, 서버와 폰이 **바이트 단위로 동일한** 토크나이저를 써야 한다.
조금만 달라도 벡터 공간이 어긋나 검색 품질이 무너진다.

문제 조건:
- 대상 플랫폼: Android arm64
- 요구: HuggingFace Fast 토크나이저와 **바이트 단위 동일한** 토큰 스트림
- 추가 네이티브 의존성을 최소화할 것 (APK 용량·빌드 복잡도)

## 초기 가정

1. HuggingFace Fast 토크나이저(Python·Rust 구현)를 안드로이드로 포팅할 수 있을 것
2. Java 생태계의 DJL(Deep Java Library) 토크나이저가 Android arm64에서 돌 것

## 실험/검증

### HuggingFace Fast 토크나이저

- 구현: Python(wrapper) + Rust(core)
- Android arm64에서 실행 경로 없음 — JVM에서 호출할 수 있는 바이너리 미배포
- 직접 Rust 크로스 컴파일 시도는 APK 빌드 파이프라인 복잡도가 급증
- **판정: 제외**

### DJL (Deep Java Library)

- Java 친화적 API, HuggingFace 토크나이저 Java 래퍼 제공
- 실측: **arm64 native 바이너리가 배포되지 않음** (x86_64 서버 환경만 공식 지원)
- 직접 빌드·패키징 경로는 있으나, 라이브러리 유지 부담이 큼
- **판정: 제외**

### onnxruntime-extensions SentencepieceTokenizer

- Microsoft가 배포하는 onnxruntime 확장. 토크나이저를 **ONNX 그래프 노드**로 표현 가능
- 모델과 **같은 런타임(onnxruntime)**에서 실행 → 별도 네이티브 의존성 0
- `tokenizer.onnx`로 빌드해 APK assets에 동봉 (~5MB)

### Byte-exact parity 검증

- 24개 한국어 쿼리를 HuggingFace Fast와 ONNX 토크나이저에 각각 통과시켜 토큰 ID 배열 비교
- 결과: **24/24 byte-exact 일치**
- 스크립트: `server/scripts/verify_onnx.py` (토크나이저 검증 경로 포함)

## 결과

| 항목 | 값 |
|---|---|
| tokenizer.onnx 크기 | ~5 MB |
| 추가 네이티브 의존성 | 없음 (onnxruntime으로 통합) |
| HF Fast ↔ ONNX parity | 24/24 |
| 모델 + 토크나이저 총 assets | 113 MB + 5 MB = **~118 MB** |

## 최종 선택

**`onnxruntime-extensions`의 SentencepieceTokenizer를 ONNX 그래프로 변환해 `tokenizer.onnx`로 APK에 동봉한다.**

- 폰에서 모델과 토크나이저 모두 onnxruntime이 구동
- 빌드 스크립트: `server/scripts/` 안 토크나이저 ONNX 변환 스크립트
- 배포 단위: `assets/model.onnx` + `assets/tokenizer.onnx` 세트

## 왜 이 선택이 최소 구현에 적합한가

1. **런타임 단일화**: 모델·토크나이저가 동일한 onnxruntime에서 돌아 추가 네이티브 모듈이 없다. APK 빌드가 복잡해지지 않는다.
2. **검증이 자동화 가능**: byte-exact parity 24/24는 서버·폰 토큰 스트림 일치를 기계적으로 보장. 검색 품질 회귀를 사전 차단.
3. **공식 지원 경로**: Microsoft가 유지하는 라이브러리라 upstream 이슈 대응이 가능.
4. **확장 시 대체가 명확**: 다국어 확장 등으로 더 큰 토크나이저가 필요하면 동일한 ONNX 그래프 빌드 파이프라인으로 교체만 하면 된다.
5. **숨어 있던 의존성을 드러냄**: 서버에선 `pip install`이 감추던 의존성(토크나이저 + 네이티브 바이너리)이 엣지에선 직접 배포 문제가 된다는 걸 구체적 파일 단위로 확정.

## 관련 문서

- 최소 구현 가이드: [../../00-main/ondevice-rag-minimal-guide.md](../../00-main/ondevice-rag-minimal-guide.md)
- 양자화 경로: [./onnx-int8-quantization.md](onnx-int8-quantization.md)
- 검증 스크립트: `server/scripts/verify_onnx.py`
