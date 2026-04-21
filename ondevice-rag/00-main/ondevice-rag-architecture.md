# 온디바이스 RAG 아키텍처

> 시스템을 구성하는 컴포넌트 경계와 데이터 흐름을 정의한다.
> 왜 이 구조를 택했는지는 case 문서에서 다룬다.

---

## 시스템 경계

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│  서버 (Mac Mini, 개발 전용)      │       │  클라이언트 (Android arm64)       │
│  ────────────────────────────   │       │  ────────────────────────────   │
│  FastAPI                         │       │  Kotlin + Jetpack Compose        │
│  sentence-transformers           │       │  onnxruntime (model + tokenizer) │
│  sqlite-vec                      │       │  sqlite (float32 BLOB)           │
│  Ollama (개발 LLM)               │       │  LiteRT-LM (Gemma 4 E2B)         │
│                                  │       │                                   │
│  엔드포인트                       │       │  주요 모듈                         │
│   /sync   (ETag 증분 배포)       │  ───▶ │   ServerApi     (HTTP + ETag)    │
│   /query  (서버 RAG 종합)        │       │   EmbeddingEngine (ONNX)         │
│   /search (top-K 반환)           │       │   VectorSearch  (brute-force)    │
│   /health (상태)                 │       │   LlmEngine     (LiteRT-LM)      │
│                                  │       │   ChunkDatabase (Room/sqlite)    │
└─────────────────────────────────┘       └─────────────────────────────────┘
         │                                            │
         └────────────── 동일 임베딩 모델 ─────────────┘
            dragonkue/multilingual-e5-small-ko-v2 (384d)
            서버: sentence-transformers / 폰: ONNX INT8
            → 같은 벡터 공간, DB 한 벌
```

---

## 데이터 흐름

### 빌드 타임 (서버)

```
wiki/*.md
   │  chunk.py
   ▼
청크 리스트 (text, doc_url, heading_path)
   │  ingest.py (sentence-transformers)
   ▼
server.db (sqlite-vec, HNSW 인덱스)
mobile.db (sqlite, float32 BLOB)
```

### 런타임 (폰, 오프라인)

```
사용자 쿼리
   │  EmbeddingEngine (tokenizer.onnx → model.onnx INT8)
   ▼
384차원 쿼리 벡터
   │  VectorSearch.cosine(all 93 chunks)
   ▼
top-K 청크 (K=3, distance ≤ 0.65)
   │  PromptBuilder (시스템 프롬프트 + 청크 + 질문)
   ▼
프롬프트
   │  LlmEngine (LiteRT-LM + Gemma 4 E2B)
   ▼
생성된 답변 문자열
   │  renderAnswer() — [#n] 인용 링크 치환
   ▼
UI (ChatScreen)
```

### 런타임 (서버 경로, 온라인일 때)

```
쿼리 → /query → 서버에서 임베딩 + 검색 + Ollama 생성 → 응답
```

폰 UI 토글로 local / server 모드를 전환.

---

## 컴포넌트 분담

### 서버 (개발 전용, 운영 필수 아님)

| 모듈 | 역할 |
|---|---|
| `chunk.py` | 마크다운 → 청크 |
| `embed_st.py` | sentence-transformers 임베딩 (모바일 DB용) |
| `embed.py` | Ollama 임베딩 (서버 DB용) |
| `ingest.py` | 전체 인제스트 파이프라인 |
| `db.py` | sqlite-vec 듀얼 DB |
| `rag.py` | 검색 + 시스템 프롬프트 조립 |
| `main.py` | FastAPI 엔드포인트 |

### 폰 (런타임 핵심)

| 모듈 | 역할 |
|---|---|
| `ServerApi` | `/sync` ETag 증분 배포, `/query` 서버 폴백 |
| `ChunkDatabase` | sqlite(float32 BLOB) 저장·조회 |
| `EmbeddingEngine` | tokenizer.onnx + model.onnx INT8 |
| `VectorSearch` | brute-force cosine top-K |
| `LlmEngine` | LiteRT-LM 어댑터 (Gemma 4 E2B) |
| `ChatViewModel` | 파이프라인 오케스트레이션 |
| `renderAnswer()` | `[#n]` 인용 링크 치환 |

---

## 동기화 (/sync)

- ETag 구성: `wiki_commit` + `chunker_version`
- 두 값 중 하나라도 변하면 ETag 변경 → 폰이 전체 DB 재다운로드
- 일치하면 304 → 캐시 유지
- **결과**: 블로그가 업데이트되거나 청크 로직이 변경되면 자동으로 폰이 최신 상태로 수렴. 변경 없으면 전송량 0.

---

## 폰 자산 배치

```
mobile/app/src/main/assets/
├── model.onnx           # 임베딩 모델 INT8 (113MB, git 제외)
├── tokenizer.onnx       # onnxruntime-extensions 그래프 (~5MB)
└── (LiteRT-LM 모델은 앱 내부 저장소에 외부 다운로드로 배치, ~2.4GB)
```

---

## 관련 case 문서

- 임베딩 모델 선택 근거: [../02-cases/embedding/embedding-benchmark-ko.md](../02-cases/embedding/embedding-benchmark-ko.md)
- 양자화 상세: [../02-cases/deployment/onnx-int8-quantization.md](../02-cases/deployment/onnx-int8-quantization.md)
- 폰 LLM 실기: [../02-cases/llm/gemma4-e2b-on-galaxy-s23.md](../02-cases/llm/gemma4-e2b-on-galaxy-s23.md)
- 프롬프트 전략: [../02-cases/llm/json-schema-prompt-failure-on-edge.md](../02-cases/llm/json-schema-prompt-failure-on-edge.md)
