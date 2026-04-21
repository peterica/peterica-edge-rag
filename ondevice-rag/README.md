# 온디바이스 RAG

> 서버·네트워크 없이 폰 안에서 내 마크다운 지식을 근거로 답하는 RAG.
> 이 문서 묶음은 그 구조를 **재현 가능한 형태**로 정리한 허브다.

---

## 🚀 가장 먼저 읽을 것

**[00-main/ondevice-rag-minimal-guide.md](00-main/ondevice-rag-minimal-guide.md)**

결론 → 파이프라인 → 8단계 선택 결과만 담은 **설계 문서**.
여기만 읽어도 구현이 시작된다.

---

## 📑 목차

- [프로젝트 한 줄 소개](#프로젝트-한-줄-소개)
- [8단계 네비게이션](#8단계-네비게이션)
- [문서 지도](#문서-지도)
- [추천 읽기 순서](#추천-읽기-순서)
- [핵심 선택 요약](#핵심-선택-요약)

---

## 프로젝트 한 줄 소개

- **무엇**: Galaxy S23 Ultra + Mac Mini로 구성한 **오프라인 온디바이스 RAG**
- **지식 원천**: 블로그·위키 마크다운 93 청크
- **목적**: "내 기계가 내 지식을 안다"를 최소 구현으로 증명
- **이 폴더의 목적**: 선택 결과(main) + 선택 근거(case) + 맥락(context)을 분리해 **다른 사람이 재현 가능하게** 만든다

---

## 8단계 네비게이션

| # | 단계 | 선택 | 근거 (case) |
|---|---|---|---|
| 1 | 임베딩 모델 선택 | e5-small-ko-v2 (384d) | [embedding-benchmark-ko](02-cases/embedding/embedding-benchmark-ko.md) |
| 2 | 청크 분리 + 약한 청크 필터 | MOC/entity 제외, 118 → 93 | [moc-entity-filter](02-cases/chunking/moc-entity-filter.md) |
| 3 | 서버 임베딩 파이프라인 | FastAPI + sentence-transformers | *(main만 참조)* |
| 4 | 임베딩 모델 경량화 | ONNX INT8 (448MB → 113MB) | [onnx-int8-quantization](02-cases/deployment/onnx-int8-quantization.md) |
| 5 | 토크나이저 동봉 | onnxruntime-extensions (ONNX 그래프) | [tokenizer-onnx-embedding](02-cases/deployment/tokenizer-onnx-embedding.md) |
| 6 | 폰 벡터 검색 | sqlite + brute-force cosine (<1ms) | [brute-force-vs-sqlite-vec](02-cases/retrieval/brute-force-vs-sqlite-vec.md) |
| 7 | 온디바이스 LLM | Gemma 4 E2B on LiteRT-LM (~40s) | [gemma4-e2b-on-galaxy-s23](02-cases/llm/gemma4-e2b-on-galaxy-s23.md) |
| 8 | 프롬프트 전략 | 자연어 + 인용 지시 (JSON 강제 반려) | [json-schema-prompt-failure-on-edge](02-cases/llm/json-schema-prompt-failure-on-edge.md) |

→ 선택의 전체 요약 표는 [minimal-guide](00-main/ondevice-rag-minimal-guide.md#선택-요약-표)에 있다.

---

## 문서 지도

| 폴더 | 역할 |
|---|---|
| [`00-main/`](./00-main/) | 최소 구현 가이드 — 결론과 단계만 담은 설계 문서 |
| [`01-context/`](./01-context/) | 왜 이 작업을 했는지 — 배경·리서치·도구 지도 |
| [`02-cases/`](./02-cases/) | 선택 근거와 실험 — 문제/가정/결과/최종 선택 |

---

## 추천 읽기 순서

### 🏃 빠르게 재현하려는 사람

1. [minimal-guide](00-main/ondevice-rag-minimal-guide.md) — 8단계 선택 결과
2. [architecture](00-main/ondevice-rag-architecture.md) — 컴포넌트 경계
3. [checklist](00-main/ondevice-rag-checklist.md) — 검증 항목

### 🔎 왜 이런 선택을 했는지 알고 싶은 사람

1. [why-ondevice-rag](01-context/why-ondevice-rag.md) — 출발점
2. [embedding-benchmark-ko](02-cases/embedding/embedding-benchmark-ko.md) — 측정이 설계를 뒤집은 지점
3. [json-schema-prompt-failure-on-edge](02-cases/llm/json-schema-prompt-failure-on-edge.md) — 서버→엣지 이식 실패
4. [onnx-int8-quantization](02-cases/deployment/onnx-int8-quantization.md) — 배포 가능한 크기로

### 🧭 전체 여정을 보고 싶은 사람

1. [why-ondevice-rag](01-context/why-ondevice-rag.md)
2. [research-phase0](01-context/research-phase0.md)
3. [edge-rag-tooling-map](01-context/edge-rag-tooling-map.md)

---

## 핵심 선택 요약

| 레이어 | 선택 |
|---|---|
| 임베딩 | `multilingual-e5-small-ko-v2` INT8 (384차원) |
| 벡터 검색 (폰) | sqlite + float32 BLOB + brute-force cosine |
| 배포 | ONNX INT8 (113MB) + `tokenizer.onnx` (ONNX 그래프 내장) |
| LLM (폰) | Gemma 4 E2B on LiteRT-LM + Hexagon NPU |
| 프롬프트 | 자연어 + `[#n]` 인용 지시 (JSON 스키마 강제 반려) |
| 동기화 | `/sync` ETag (`wiki_commit` + `chunker_version`) |

→ 상세: [minimal-guide](00-main/ondevice-rag-minimal-guide.md) · [architecture](00-main/ondevice-rag-architecture.md)
