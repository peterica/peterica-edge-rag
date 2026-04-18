# Peterica Blog Chat — Hybrid AI System PRD

> 작성일: 2026-04-16
> 상태: Phase 0 검증 완료 (v3)
> 검토자: PL (Claude)

---

## 1. 목적

맥미니 기반 local-first RAG 시스템과  
모바일 온디바이스 AI를 결합하여  
**"개인 지식 기반 AI 시스템"을 구축한다.**

---

## 2. 시스템 개요

### 구성

- Mac Mini (`http://localhost:8600`)
    - RAG 서버 (wiki + embedding + LLM)
    - 지식 저장 및 응답 생성
    - 듀얼 임베딩 파이프라인 (서버 + 모바일 DB 생성)

- Mobile (Android / Galaxy S23 Ultra)
    - 온디바이스 임베딩 + 로컬 검색
    - 온디바이스 LLM (Gemma 4 E2B)
    - 서버 fallback

### 디바이스 스펙

| 항목 | Mac Mini | Galaxy S23 Ultra |
|------|----------|-----------------|
| 역할 | RAG 서버, 고품질 LLM | 엣지 검색, 경량 LLM |
| SoC | Apple M1/M2 | Snapdragon 8 Gen 2 (SM8550) |
| RAM | 16GB+ | 12GB |
| 가용 메모리 (AI) | ~10GB | ~8GB |

---

## 3. 핵심 구조

```text
[Mobile - Galaxy S23 Ultra]
질문 입력
 ├─ 로컬 경로:
 │   → 임베딩 모델 (쿼리 임베딩)
 │   → SQLite 로컬 검색 (top-k)
 │   → Gemma 4 E2B (답변 생성)
 │
 └─ 서버 경로 (fallback):
     → Mac Mini REST API 요청
         ↓
     [Mac Mini]
     → bge-m3 (쿼리 임베딩)
     → sqlite-vec 검색 + context 구성
     → minja (prompt 생성)
     → LLM 실행 (llama.cpp / Ollama)
     → 응답 반환
```

### 전환 로직

| 조건 | 동작 |
|------|------|
| 네트워크 불가 | 로컬 경로 강제 |
| 네트워크 가용 + 사용자 "서버 요청" | 서버 경로 |
| 로컬 검색 결과 없음 (distance > 임계값) | 서버 fallback 제안 |

> MVP에서는 **사용자 수동 선택** 방식. 자동 전환은 이후 확장.

---

## 4. 핵심 컴포넌트

### 4.1 Prompt Layer — minja

[google/minja](https://github.com/google/minja): llama.cpp에 내장된 **header-only C++17 Jinja2 구현체**.

| 항목 | 내용 |
|------|------|
| 역할 | HuggingFace 모델의 chat_template을 런타임에 렌더링 |
| 크기 | ~2,500 LoC, 의존성: nlohmann::json만 |
| 지원 | if/elif/else, for, set, macro, filter 등 Jinja2 서브셋 |
| 연동 | llama.cpp `--jinja` 플래그로 활성화 |

선택 근거:
- llama.cpp 기반 추론을 서버/모바일 모두 사용 → 프롬프트 엔진 통일
- 모델별 chat template을 하드코딩 없이 처리 가능
- 모델 교체 시 코드 변경 최소화 (template만 교체)

주의사항:
- prompt injection 보호 없음 (내부 시스템이므로 수용)
- 일부 모델 template과 비호환 사례 존재 (Gemma 2, Qwen 2.5 등 — 사전 검증 필요)

---

### 4.2 RAG Layer (Mac Mini)

- wiki 데이터 (peterica-blog-wiki)
- embedding: bge-m3 (1024차원, Ollama)
- sqlite-vec 기반 cosine 유사도 검색
- context 주입 + 인용 규칙

> 기존 `peterica-blog-chat`의 RAG 파이프라인을 FastAPI로 재구성.

---

### 4.3 Execution Layer

| 환경 | LLM | 추론 엔진 | 메모리 |
|------|-----|----------|--------|
| Mac Mini | exaone3.5:7.8b 또는 기타 | llama.cpp / Ollama | ~6GB |
| Mobile | **Gemma 4 E2B** (2.3B, 4bit 양자화) | LiteRT-LM | ~1.5GB |

Gemma 4 E2B 선택 근거:
- 실효 2.3B 파라미터, PLE로 5.1B급 표현력
- 4bit 양자화 시 ~1.5GB → S23 Ultra 12GB RAM 내 여유
- 128K 토큰 컨텍스트 → RAG 컨텍스트 주입에 충분
- 네이티브 tool calling 지원
- Apache 2.0 라이센스
- LiteRT-LM 공식 지원 (Google AI Edge)

---

### 4.4 Mobile Layer

- **임베딩**: 단계적 접근 (아래 섹션 11 참고)
- **벡터 검색**: SQLite 로컬 DB (사전 동기화)
- **LLM**: Gemma 4 E2B via LiteRT-LM
- **서버 fallback**: REST API (`/query`)

---

## 5. 기능 정의 (MVP)

### 5.1 모바일

- 텍스트 입력 (Compose UI)
- 로컬 임베딩 검색 → 결과 리스트 표시
- 로컬 LLM 응답 (Gemma 4 E2B)
- "서버에 질문" 버튼 (Mac Mini fallback)
- 오프라인 상태 표시

### 5.2 서버 (Mac Mini)

- `POST /query`
    - 입력: `{ "question": "..." }`
    - 처리:
        - bge-m3 임베딩 → sqlite-vec 검색
        - context 구성 (top-k 청크)
        - minja prompt 렌더링
        - LLM 실행
    - 출력: `{ "answer": "...", "citations": [...] }`

- `GET /sync`
    - 출력: 최신 임베딩 DB 파일 (모바일 동기화용)

---

## 6. 핵심 요구사항

### 6.1 재현성

- prompt template 고정 (minja 기반)
- 동일 입력 → 유사 결과 유지
- 모델별 template 버전 관리

### 6.2 분리

- 데이터(JSON) vs 프롬프트 분리
- 모바일 vs 서버 역할 분리
- 임베딩 모델 vs 생성 모델 분리

### 6.3 확장성

- 모델 교체 가능 (minja template 교체만으로)
- mobile / server 독립 확장
- 임베딩 모델 교체 시 DB 재생성만 필요

---

## 7. 성장 관점 핵심 포인트

이 시스템은 기능 개발이 아니라:

- LLM 비결정성 통제
- prompt → 시스템 구조화
- RAG → 운영 구조
- 모바일 → 실행 위치 설계
- **임베딩 → 벡터 검색 파이프라인 이해**
- **엣지 AI → 리소스 제약 하 설계**

을 학습하기 위한 구조다.

---

## 8. 성공 기준

- [ ] 모바일에서 오프라인 문서 검색 가능
- [ ] 모바일 로컬 LLM 응답 생성 가능 (Gemma 4 E2B)
- [ ] 서버 RAG 응답 정상 동작
- [ ] prompt template 교체 가능
- [ ] 모델 변경 시 코드 수정 최소화
- [ ] 모바일 ↔ 서버 동일 질문에 유사한 검색 결과

---

## 9. 한 줄 정의

"개인 지식을 기반으로,  
모바일과 서버가 협력하는 AI 시스템"

---

## 10. 사용 기술

### 10.1 Server (Mac Mini)

| 항목 | 기술 | 비고 |
|------|------|------|
| Backend | FastAPI | llama.cpp Python 바인딩, minja 연동 용이 |
| LLM | llama.cpp / Ollama | 로컬 추론 |
| Embedding (서버) | bge-m3 (1024차원) | 기존 blog-chat과 동일 |
| Embedding (모바일 DB 생성) | embeddinggemma:300m (Ollama) | 듀얼 파이프라인 |
| Vector DB | sqlite-vec | cosine 유사도 검색 |
| Prompt Engine | minja (llama.cpp 내장) | Jinja2 호환 C++17 |
| Data | markdown 기반 wiki | peterica-blog-wiki |

> **서버 스택 변경 근거 (Next.js → FastAPI):**
> 기존 blog-chat은 Next.js(TS)로 AI SDK를 활용했으나, 이번 프로젝트는
> llama.cpp 기반 추론 + minja 프롬프트 엔진이 핵심이므로
> Python 바인딩(llama-cpp-python)과의 통합이 자연스러운 FastAPI를 선택.
> 또한 임베딩 파이프라인(ingest)도 Python 생태계(sentence-transformers, ONNX)가 풍부.

---

### 10.2 Mobile (Android)

| 항목 | 기술 | 비고 |
|------|------|------|
| Language | Kotlin | Android 네이티브 |
| UI | Jetpack Compose | 선언형 UI |
| On-device LLM | Gemma 4 E2B (4bit) | LiteRT-LM, ~1.5GB |
| Embedding | 단계적 접근 (섹션 11 참고) | Phase 1: e5-ko → Phase 2: EmbeddingGemma |
| Vector Search | SQLite (로컬) | 사전 동기화 DB |
| Networking | Retrofit / Ktor | 서버 fallback용 |

---

### 10.3 공통

| 항목 | 기술 |
|------|------|
| Data Format | JSON (messages, context, query) |
| Protocol | REST API (`/query`, `/sync`) |
| Prompt Template | Jinja 스타일 (minja) |
| Version Control | Git |

---

### 10.4 확장 (선택)

| 항목 | 기술 | 우선순위 |
|------|------|---------|
| STT | Android SpeechRecognizer | 낮음 |
| TTS | Android TextToSpeech | 낮음 |
| Tool API | 날씨 / 뉴스 외부 API | 낮음 |
| NPU 최적화 | Qualcomm AI Engine / NNAPI | 중간 |

---

## 11. 온디바이스 임베딩 모델 — 단계적 접근

> Phase 0 검증 결과, EmbeddingGemma-300M의 한국어 품질이 미검증 상태.
> 한국어 블로그 RAG에서 검색 품질이 핵심이므로, **검증된 모델 우선 → 벤치마크 후 전환** 전략을 채택.

### 전략: 2단계 임베딩 모델 마이그레이션

```
Phase 1 (MVP): multilingual-e5-small-ko-v2
  → 한국어 검색 품질 검증됨 (nDCG@10 평균 0.693)
  → ONNX Runtime Mobile 배포
  → 384차원, ~30MB (INT8)

Phase 2 (벤치마크 후): EmbeddingGemma-300M
  → 자체 한국어 테스트셋으로 품질 비교
  → e5-ko-v2 대비 동등 이상이면 마이그레이션
  → LiteRT 배포, SM8550 전용 TFLite (184MB)
  → Matryoshka 차원 최적화 (768 → 256 등)
```

### 모델 비교 (Phase 0 검증 결과)

| 항목 | multilingual-e5-small-ko-v2 | EmbeddingGemma-300M |
|------|---------------------------|---------------------|
| 파라미터 | 117M | 308M |
| 차원 | 384 (고정) | 128-768 (Matryoshka) |
| 모바일 크기 | ~30MB (INT8 ONNX, 직접 빌드) | 184MB (SM8550 TFLite) |
| 런타임 메모리 | ~50-80MB (추정) | ~110MB (CPU) / ~224MB (NPU) |
| 한국어 검증 | **검증됨** — 7개 벤치마크, nDCG@10 평균 0.693 | **미검증** — 100+ 언어 지원, 한국어 전용 벤치 없음 |
| 모바일 런타임 | ONNX Runtime Mobile | LiteRT (SM8550 최적화) |
| 토크나이저 | XLM-RoBERTa | SentencePiece (Gemma 계열) |
| Android 라이브러리 | `onnxruntime-android:1.24.3` | `litert:1.4.0` + `litert-gpu:1.4.0` |
| ONNX 빌드 필요 | 직접 export + quantize | 불필요 (Google 제공) |

### 한국어 벤치마크 상세 (e5-small-ko-v2)

| 벤치마크 | ko-v2 (118M) | e5-small base (118M) | bge-m3 (560M) |
|----------|-------------|---------------------|---------------|
| Ko-StrategyQA | 0.769 | 0.752 | 0.794 |
| AutoRAGRetrieval | 0.856 | 0.801 | 0.830 |
| MIRACLRetrieval | 0.633 | 0.612 | 0.701 |
| PublicHealthQA | 0.772 | 0.737 | 0.804 |
| BelebeleRetrieval | 0.930 | 0.905 | 0.932 |
| MrTidyRetrieval | 0.541 | 0.560 | 0.647 |
| XPQARetrieval | 0.347 | 0.330 | 0.361 |
| **평균** | **0.693** | **0.671** | **0.724** |

> 118M 모델이 278M e5-base보다 한국어에서 우수. bge-m3(560M) 대비 ~4% 차이.

### 듀얼 임베딩 파이프라인 (Mac Mini)

```text
[Mac Mini - Ollama]
ingest 스크립트 실행
 ├─ Step 1: bge-m3로 전체 청크 임베딩 → server.db (1024차원)
 └─ Step 2: embeddinggemma:300m으로 전체 청크 임베딩 → mobile.db (768차원)
                                                      (또는 e5-ko-v2로 384차원)

성능: 118 청크 × 2모델 = ~15-20초
메모리: ~2.5-3.0GB (16GB Mac Mini에서 여유 ~8GB)
```

Ollama로 양쪽 모델 순차 실행. 모델 스왑 ~2-3초, 전체 ingest ~20초 이내.

### 제외 모델

| 모델 | 제외 사유 |
|------|----------|
| all-MiniLM-L6-v2 | **영어 전용** — 한국어 텍스트에서 저품질 (HF 공식 경고) |
| BGE-M3 | 543MB (INT8) — 모바일에서 과도한 크기 |
| gte-multilingual-base | 305-350MB — EmbeddingGemma와 유사 크기이나 칩 최적화 없음 |

---

## 12. Phase 0 검증 결과

> 실행일: 2026-04-16 / 검증 방법: 3트랙 병렬 리서치

### Track A: Gemma 4 E2B 모바일 구동

| 항목 | 결과 |
|------|------|
| **판정** | **GO — showstopper 없음** |
| 모델 포맷 | `.litertlm` (2.58GB) |
| 즉시 테스트 | Google AI Edge Gallery (Play Store) |
| 개발 통합 | `com.google.ai.edge.litertlm:litertlm-android` (Maven) |
| 메모리 | ~1.5GB 런타임 |
| 추론 속도 | 12-20 tok/s (CPU, S23 Ultra 추정) |
| GPU delegate | **Snapdragon 8 Gen 2에서 버그 있음** → CPU fallback 권장 |
| 대안 | llama.cpp GGUF Q4_K_M (3.11GB), Termux 또는 JNI |
| 최소 API | Android 8.0 (API 26) — S23 Ultra는 API 34 ✓ |

Kotlin 통합 코드:
```kotlin
val engineConfig = EngineConfig(
    modelPath = "/path/to/model.litertlm",
    backend = Backend.CPU()  // GPU는 Qualcomm 이슈로 CPU 권장
)
val engine = Engine(engineConfig)
engine.initialize()
engine.createConversation().use { conversation ->
    conversation.sendMessage("질문 텍스트")
}
```

### Track B: EmbeddingGemma-300M 모바일 배포

| 항목 | 결과 |
|------|------|
| **판정** | **GO (조건부 — 한국어 품질 미검증)** |
| SM8550 전용 TFLite | **존재** — `litert-community/embeddinggemma-300m` |
| 파일 크기 | 184MB (seq256), 190MB (seq512) |
| 런타임 메모리 | ~110MB (CPU) / ~224MB (NPU) |
| 추론 속도 | <200ms/query (추정, S25 Ultra 기준 NPU: 7.8ms) |
| 토크나이저 | DJL HuggingFace Tokenizers (`ai.djl.huggingface:tokenizers:0.25.0`) |
| 한국어 품질 | **미검증** — 자체 벤치마크 필요 |
| 대안 (Phase 1) | multilingual-e5-small-ko-v2 (ONNX, 한국어 검증됨) |
| Google RAG SDK | `com.google.ai.edge.localagents:localagents-rag:0.1.0` 존재 |

### Track C: 듀얼 임베딩 파이프라인 (Mac Mini)

| 항목 | 결과 |
|------|------|
| **판정** | **GO — 완전 실현 가능** |
| 방법 | Ollama로 bge-m3 + embeddinggemma:300m 순차 실행 |
| 메모리 | ~2.5-3.0GB 합산 (16GB에서 여유 ~8GB) |
| 소요 시간 | 118 청크 × 2모델 = ~15-20초 |
| DB 구조 | 별도 파일 분리 (server.db + mobile.db) |
| 모바일 DB 크기 | ~550KB (768dim) 또는 ~350KB (256dim) |
| /sync 엔드포인트 | FastAPI FileResponse 5줄로 충분 |
| 압축 필요 | 불필요 (~550KB는 JPEG 1장보다 작음) |

---

## 13. 리소스 예산 (Galaxy S23 Ultra)

```
총 RAM: 12GB
─────────────────────────────────────
OS + 기본 앱:                  ~4.0GB
─────────────────────────────────────
Gemma 4 E2B (LiteRT-LM):     ~1.5GB
임베딩 모델:
  Phase 1 (e5-ko-v2 ONNX):   ~0.08GB
  Phase 2 (EmbeddingGemma):   ~0.11-0.22GB
SQLite DB:                     ~0.001GB (118 청크)
앱 런타임 (Kotlin + Compose):  ~0.3GB
─────────────────────────────────────
AI 총 사용:                    ~1.9-2.1GB
여유:                          ~5.9-6.1GB ✓
```

---

## 14. 데이터 동기화

### MVP: 수동 동기화

```text
[Mac Mini]
ingest 스크립트 실행
 → bge-m3로 서버 DB 생성 (server.db)
 → 모바일 임베딩 모델로 모바일 DB 생성 (mobile.db)
 → GET /sync 엔드포인트로 mobile.db 제공

[Mobile]
앱 내 "동기화" 버튼
 → /sync에서 mobile.db 다운로드 (~550KB)
 → 로컬 SQLite 교체
```

### 향후 확장

- 위키 변경 감지 (git hash 비교) → 자동 재임베딩
- 변경된 청크만 incremental 업데이트

---

## 15. 확정된 의사결정

| # | 항목 | 결정 | 근거 |
|---|------|------|------|
| D1 | 모바일 임베딩 모델 | **단계적: e5-ko-v2 → EmbeddingGemma** | 한국어 검증 우선, 벤치마크 후 전환 |
| D2 | 모바일 LLM | **Gemma 4 E2B** | Phase 0 Track A: GO |
| D3 | 서버 스택 | **FastAPI** | llama.cpp Python 바인딩 통합 |
| D4 | 데이터 동기화 | **MVP: GET /sync (수동)** | ~550KB, 압축 불필요 |
| D5 | 오프라인 전환 | **MVP: 사용자 수동 선택** | 자동은 이후 확장 |
| D6 | Matryoshka 차원 | **768dim 시작 → 벤치마크 후 축소** | EmbeddingGemma 도입 시 결정 |
| D7 | 모바일 벡터 검색 | **brute-force cosine** | 118 청크 → <1ms, sqlite-vec ARM 빌드 불필요 |
| D8 | 듀얼 임베딩 방식 | **Ollama 순차 실행** | ~20초, 메모리 여유 |
| D9 | DB 구조 | **별도 파일 (server.db + mobile.db)** | 동기화 간결, 불필요 데이터 전송 방지 |
| D10 | GPU delegate | **CPU fallback** | Snapdragon 8 Gen 2 GPU delegate 버그 |

---

## 16. 개발 로드맵

### Phase 0: 리스크 검증 — ✅ 완료

- [x] Track A: Gemma 4 E2B 모바일 구동 가능성 → GO
- [x] Track B: EmbeddingGemma-300M 모바일 배포 → GO (조건부)
- [x] Track C: 듀얼 임베딩 파이프라인 → GO
- [ ] S23 Ultra 실기 테스트 (AI Edge Gallery)

### Phase 1: Server (Mac Mini - FastAPI)

- [ ] 프로젝트 구조 생성
- [ ] FastAPI + Ollama 연동
- [ ] bge-m3 기반 RAG 파이프라인 (blog-chat에서 포팅)
- [ ] 듀얼 임베딩 ingest 스크립트
- [ ] /query, /sync API
- [ ] 서버 단독 동작 검증

### Phase 2: Mobile (Android - Kotlin)

- [ ] Android 프로젝트 스캐폴딩 (Compose)
- [ ] LiteRT-LM + Gemma 4 E2B 통합
- [ ] ONNX Runtime + e5-small-ko-v2 임베딩
- [ ] 로컬 SQLite 검색 (brute-force cosine)
- [ ] 서버 fallback (/query)
- [ ] DB 동기화 (/sync)

### Phase 3: 통합 + 최적화

- [ ] 모바일 ↔ 서버 검색 결과 비교
- [ ] EmbeddingGemma 한국어 벤치마크
- [ ] 벤치마크 결과에 따른 임베딩 모델 마이그레이션
- [ ] Matryoshka 차원 최적화
- [ ] 인용 시스템 통합

---

## 17. 참고 자료

### 모델

- [Gemma 4 Edge 블로그](https://developers.googleblog.com/bring-state-of-the-art-agentic-skills-to-the-edge-with-gemma-4/)
- [google/gemma-4-E2B](https://huggingface.co/google/gemma-4-E2B)
- [litert-community/gemma-4-E2B-it-litert-lm](https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm) — LiteRT-LM 모델 파일
- [unsloth/gemma-4-E2B-it-GGUF](https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF) — llama.cpp GGUF 양자화
- [google/embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m)
- [litert-community/embeddinggemma-300m](https://huggingface.co/litert-community/embeddinggemma-300m) — SM8550 전용 TFLite
- [dragonkue/multilingual-e5-small-ko-v2](https://huggingface.co/dragonkue/multilingual-e5-small-ko-v2)
- [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)

### 도구

- [google/minja](https://github.com/google/minja) — llama.cpp 내장 Jinja2 C++17 구현
- [LiteRT-LM Android](https://ai.google.dev/edge/litert-lm/android) — 모바일 LLM 가이드
- [LiteRT (구 TFLite)](https://ai.google.dev/edge/litert)
- [Google AI Edge Gallery](https://play.google.com/store/apps/details?id=com.google.ai.edge.gallery) — Play Store
- [Google AI Edge SDK](https://ai.google.dev/edge)
- [Google AI Edge RAG SDK](https://github.com/google-ai-edge/ai-edge-apis/tree/main/examples/rag)
- [ONNX Runtime Mobile](https://onnxruntime.ai/docs/tutorials/mobile/deploy-android.html)
- [sqlite-vec](https://github.com/asg017/sqlite-vec)
- [DJL HuggingFace Tokenizers](https://mvnrepository.com/artifact/ai.djl.huggingface/tokenizers)

### 기존 프로젝트

- `peterica-blog-chat` — Mac Mini RAG 챗봇 (Next.js + AI SDK v6)
- `peterica-blog-wiki` — 블로그 위키 데이터 소스

### 논문

- [BGE M3-Embedding](https://arxiv.org/html/2402.03216v3)
- [EmbeddingGemma](https://arxiv.org/abs/2509.20354)
