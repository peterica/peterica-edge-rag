# Peterica Edge RAG — Android App

## 프로젝트 개요

Galaxy S23 Ultra에서 구동되는 온디바이스 RAG 챗봇.
Mac Mini 서버와 협력하여 블로그 지식 기반 질의응답을 제공한다.

## 빌드 전 준비

### 1. Android Studio에서 프로젝트 열기

`mobile/` 디렉토리를 Android Studio에서 Open.

### 2. 임베딩 모델 준비 (assets/)

Phase 1에서는 multilingual-e5-small-ko-v2 ONNX 모델을 사용한다.

```bash
# Mac에서 모델 export + 양자화
pip install optimum onnxruntime sentence-transformers

# ONNX export
optimum-cli export onnx --model dragonkue/multilingual-e5-small-ko-v2 ./e5-ko-v2-onnx/

# INT8 양자화
python -c "
from onnxruntime.quantization import quantize_dynamic, QuantType
quantize_dynamic('e5-ko-v2-onnx/model.onnx', 'model_int8.onnx', weight_type=QuantType.QInt8)
"

# assets에 복사
cp model_int8.onnx mobile/app/src/main/assets/model.onnx
cp e5-ko-v2-onnx/tokenizer.json mobile/app/src/main/assets/tokenizer.json
```

### 3. 서버 URL 설정

`app/build.gradle.kts`에서 `SERVER_URL`을 Mac Mini의 IP로 변경:

```kotlin
buildConfigField("String", "SERVER_URL", "\"http://<MAC_MINI_IP>:8600\"")
```

### 4. DB 동기화

앱 실행 후 우측 상단 "동기화" 버튼으로 Mac Mini에서 mobile.db 다운로드.
(서버가 실행 중이어야 함: `cd server && python main.py`)

## 아키텍처

```
MainActivity
 └─ ChatScreen (Compose UI)
     └─ ChatViewModel
         ├─ ChunkDatabase    — mobile.db 로드 (SQLite)
         ├─ VectorSearch     — brute-force cosine similarity
         ├─ EmbeddingEngine  — ONNX Runtime + e5-small-ko-v2
         ├─ LlmEngine        — LiteRT-LM + Gemma 4 E2B (TODO)
         └─ ServerApi         — Retrofit (fallback)
```

## 핵심 흐름

1. 앱 시작 → DB/임베딩/LLM 초기화
2. 사용자 질문 입력
3. "검색" → 로컬 임베딩 → brute-force 검색 → LLM 응답 (또는 컨텍스트 표시)
4. "서버" → Mac Mini /query 호출 → RAG 응답

## TODO

- [ ] ONNX 모델 export + assets 포함
- [ ] LiteRT-LM Gemma 4 E2B 실제 연동
- [ ] EmbeddingGemma 벤치마크 후 임베딩 모델 전환
- [ ] UI 개선 (마크다운 렌더링, 인용 링크)
