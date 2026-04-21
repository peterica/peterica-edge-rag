# 온디바이스 RAG 최소 구현 가이드

> 이 문서의 규칙: **결론 → 단계 → 체크리스트** 순서로만 읽힌다.
> 시행착오·비교 과정·회고는 담지 않는다. 근거는 각 단계의 case 링크로 위임한다.

---

## 결론

이 구조대로 따라 하면 **서버·네트워크 없이** 폰 안에서 마크다운 위키를 근거로 답하는 RAG가 돌아간다.

- 지식 원천: 마크다운 위키 (블로그·노트)
- 대상 기기: Android arm64 (예: Galaxy S23 Ultra)
- 품질 목표: 22 쿼리 평가에서 MRR ≥ 0.9, R@3 ≥ 1.0
- 응답 시간: 폰 LLM ~40초 / 벡터 검색 < 1ms

---

## 전체 파이프라인

```
[마크다운 위키]
      │  청크 분리 + 약한 청크 필터
      ▼
[청크 N개]
      │  서버에서 임베딩 (sentence-transformers)
      ▼
[float32 벡터 + 메타데이터]
      │  sqlite 단일 파일
      ▼
[mobile.db]
      │  /sync ETag로 폰에 다운로드
      ▼
[폰 내부 저장소]
      │  쿼리 임베딩 (ONNX INT8) + brute-force cosine
      ▼
[top-K 청크]
      │  LiteRT-LM 프롬프트 조립
      ▼
[Gemma 4 E2B 추론]
      │  문장별 [#n] 인용 렌더링
      ▼
[답변 + 근거 링크]
```

---

## 8단계 최소 구현 순서

각 단계는 **선택 결과**만 기록한다. 왜 그 선택을 했는지는 case 링크로.

### 1. 임베딩 모델 선택

- **선택**: `dragonkue/multilingual-e5-small-ko-v2` (384차원)
- **서버·폰 동일 모델**로 통일 (듀얼 모델 금지)
- 근거: [embedding/embedding-benchmark-ko.md](../02-cases/embedding/embedding-benchmark-ko.md)

### 2. 청크 분리 + 약한 청크 필터

- 헤딩 기반 청크 분리
- `moc/`, `entities/`, `concepts/` 경로의 연도 그룹·관련 포스트·주요 태그 헤딩 **제외**
- 최종 청크 수: 118 → 93 (21% 감소)
- 근거: [chunking/moc-entity-filter.md](../02-cases/chunking/moc-entity-filter.md)

### 3. 서버 임베딩 파이프라인 (개발 전용)

- 스택: FastAPI + `sentence-transformers` + sqlite-vec
- 산출물: `server.db` (개발용), `mobile.db` (폰 배포용)
- 엔드포인트: `/sync` (ETag 기반 증분 배포), `/query`, `/search`, `/health`

### 4. 임베딩 모델 경량화 (ONNX INT8)

- `optimum-cli export onnx` → `model.onnx` (448MB)
- `onnxruntime.quantize_dynamic` → 113MB (원본의 25%)
- 품질 검증: 한국어 5쿼리 cosine 0.97~0.98, Top-1 5/5 일치
- 근거: [deployment/onnx-int8-quantization.md](../02-cases/deployment/onnx-int8-quantization.md)

### 5. 토크나이저 동봉

- 선택: `onnxruntime-extensions`의 `SentencepieceTokenizer` → ONNX 그래프 내장 (`tokenizer.onnx`, ~5MB)
- 검증: HuggingFace Fast ↔ ONNX byte-exact parity **24/24**
- 근거: [deployment/tokenizer-onnx-embedding.md](../02-cases/deployment/tokenizer-onnx-embedding.md)

### 6. 폰 벡터 검색

- 선택: sqlite에 float32 BLOB 저장 + Kotlin에서 **brute-force cosine**
- 성능: 93청크 × 384차원 < 1ms
- 근거: [retrieval/brute-force-vs-sqlite-vec.md](../02-cases/retrieval/brute-force-vs-sqlite-vec.md)

### 7. 온디바이스 LLM

- 선택: **Gemma 4 E2B** on **LiteRT-LM** + Hexagon NPU
- 응답 시간: ~40초/쿼리 (Galaxy S23 Ultra)
- 배치: APK `assets/` 직접 동봉 (~2.4GB, git 제외)
- 근거: [llm/gemma4-e2b-on-galaxy-s23.md](../02-cases/llm/gemma4-e2b-on-galaxy-s23.md)

### 8. 프롬프트 전략

- 선택: **자연어 프롬프트 + 인용 지시** ("모든 문장에 [#n] 붙이기")
- 반려: JSON 스키마 강제 (2B 모델에서 답변이 "질문 제목 한 줄"로 붕괴)
- 파서·로그 인프라(`renderAnswer()`, raw/rendered 로그 훅)는 유지 → 상위 모델로 업그레이드 시 프롬프트 한 줄만 교체해 재활성
- 근거: [llm/json-schema-prompt-failure-on-edge.md](../02-cases/llm/json-schema-prompt-failure-on-edge.md)

---

## 선택 요약 표

| 단계 | 선택 | 반려한 대안 |
|---|---|---|
| 1. 임베딩 모델 | e5-small-ko-v2 (384d) | bge-m3(1024d), EmbeddingGemma(768d) |
| 2. 청크 필터 | MOC/entity 제외 | 전 청크 사용 |
| 3. 서버 스택 | FastAPI + sentence-transformers | Next.js + TypeScript |
| 4. 양자화 | ONNX INT8 Dynamic | Static, QAT |
| 5. 토크나이저 | onnxruntime-extensions (ONNX 그래프) | DJL, HF tokenizers Python/Rust |
| 6. 폰 벡터 검색 | brute-force cosine | sqlite-vec on Android |
| 7. 폰 LLM | Gemma 4 E2B + LiteRT-LM | 서버 의존 유지 |
| 8. 프롬프트 | 자연어 + 인용 지시 | JSON 스키마 강제 |

---

## 관련 문서

- 아키텍처 상세: [ondevice-rag-architecture.md](ondevice-rag-architecture.md)
- 구현 체크리스트: [ondevice-rag-checklist.md](ondevice-rag-checklist.md)
- 왜 온디바이스인가: [01-context/why-ondevice-rag.md](../01-context/why-ondevice-rag.md)
- Phase 0 리서치: [01-context/research-phase0.md](../01-context/research-phase0.md)
- 엣지 RAG 도구 지도: [01-context/edge-rag-tooling-map.md](../01-context/edge-rag-tooling-map.md)
