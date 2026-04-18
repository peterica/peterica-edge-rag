# peterica-edge-rag: 프로젝트 리서치 및 의사결정 문서

> 작성일: 2026-04-16
> 상태: 리서치 완료 / 의사결정 대기

---

## 1. 프로젝트 목표

갤럭시 S23 Ultra에서 구동 가능한 온디바이스 RAG 시스템 구축.
peterica-blog-wiki의 블로그 글을 지식 기반으로 활용하여, 인터넷 연결 없이도 질의응답이 가능한 엣지 AI 챗봇을 만든다.

### 배경

- 기존 `peterica-blog-chat` 프로젝트에서 Mac Mini 기반 RAG 챗봇을 운영 중
- 이번에는 모바일 디바이스(Galaxy S23 Ultra)에서 임베딩 + 생성을 시도
- 참고 자료: [Gemma 4 Edge 블로그](https://developers.googleblog.com/bring-state-of-the-art-agentic-skills-to-the-edge-with-gemma-4/)

---

## 2. 기존 시스템 분석 (peterica-blog-chat)

### 아키텍처

```
[블로그 위키 .md 파일들]
    ↓ scripts/ingest.ts
[청킹] h1-h3 기준, ~800자 세그먼트
    ↓
[임베딩] Ollama + BGE-M3 (1024차원), 배치 32
    ↓
[저장] SQLite + sqlite-vec (WAL 모드)
    ↓ (런타임)
[쿼리 임베딩] → cosine 유사도 검색 (TOP_K=6 → 필터링 → MAX_K=3)
    ↓
[시스템 프롬프트 구성] 인용 규칙 포함
    ↓
[LLM 생성] Ollama(exaone3.5:7.8b) 또는 Claude Sonnet 4.6
    ↓
[스트리밍 응답] Next.js + AI SDK v6 + useChat
```

### 핵심 스펙

| 항목 | 값 |
|------|-----|
| 프레임워크 | Next.js 15 (App Router) |
| 임베딩 모델 | BGE-M3 (1024차원) |
| 임베딩 제공 | Ollama (`/api/embed`) |
| 벡터 저장소 | SQLite + sqlite-vec |
| 생성 모델 (dev) | exaone3.5:7.8b (Ollama) |
| 생성 모델 (prod) | Claude Sonnet 4.6 (Anthropic API) |
| 데이터 규모 | 18개 위키 문서, 118개 청크 |
| 유사도 거리 임계값 | cosine distance ≤ 0.65 |
| 최종 컨텍스트 청크 수 | 최대 3개 |
| 인용 방식 | `[#n]` 토큰 기반 강제 인용 |

### 재사용 가능한 자산

- **청킹 로직** (`lib/chunk.ts`): 마크다운 헤딩 기반 분할 → 그대로 활용 가능
- **위키 데이터** (`peterica-blog-wiki/wiki/`): 동일 소스
- **인용 시스템**: 프롬프트 규칙 재활용 가능
- **DB 스키마**: chunks + chunk_vec 구조 참고

---

## 3. Gemma 4 Edge 모델 분석

### 모델 라인업

| 모델 | 실효 파라미터 | 총 파라미터 (PLE 포함) | 컨텍스트 | 모달리티 |
|------|-------------|---------------------|---------|---------|
| **E2B** | 2.3B | 5.1B | 128K | 텍스트, 이미지, 오디오, 비디오 |
| **E4B** | ~4B | ~8-9B (추정) | 128K | 텍스트, 이미지, 오디오, 비디오 |
| 26B A4B | 26B | - | 256K | 텍스트, 이미지 |
| 31B | 31B | - | 256K | 텍스트, 이미지 |

### PLE (Per-Layer Embeddings)

각 디코더 레이어마다 개별 임베딩을 갖는 기법. 2.3B 활성 파라미터로 5.1B급 표현력을 달성.
**주의: 이것은 내부 아키텍처 최적화이며, 외부에서 사용 가능한 벡터 임베딩 API가 아니다.**

### 모바일 성능

| 항목 | 수치 |
|------|------|
| E2B 양자화 메모리 | ~1.5GB 이하 (4bit), ~500MB (공격적 양자화) |
| E4B 양자화 메모리 | ~1.5GB (4bit) |
| E2B vs E4B 속도 | E2B가 3배 빠름 |
| 이전 세대 대비 | 4배 빠른 추론 |
| 배터리 소비 | 이전 모델 대비 60% 절감 |
| Qualcomm NPU 기준 | 3,700 prefill + 31 decode tokens/s |

### Galaxy S23 Ultra 호환성

- SoC: Snapdragon 8 Gen 2
- RAM: 12GB
- E2B (~1.5GB) + 임베딩 모델 (~80MB) = **~1.6GB → 12GB RAM 내 충분** 

### 핵심 발견: Gemma 4는 임베딩 모델이 아니다

Gemma 4는 **인과적 언어 모델(causal LM)** 으로, 유사도 검색용 벡터 임베딩을 직접 생성할 수 없다.
온디바이스 RAG에서 Gemma 4는 **생성(Generation) 역할**만 담당하며,
검색(Retrieval)을 위해서는 **별도의 임베딩 모델**이 필요하다.

---

## 4. 온디바이스 배포 도구

| 도구 | 용도 |
|------|------|
| **LiteRT-LM** | 온디바이스 추론 런타임 (TFLite 후속) |
| **Google AI Edge SDK** | Android/iOS GenAI 라이브러리 |
| **AICore Developer Preview** | Android 시스템 레벨 AI 추론 서비스 |
| **Google AI Edge Gallery** | 코드 없이 온디바이스 모델 실험 앱 |
| **Ollama** | `ollama run gemma4:e2b` (데스크톱 테스트용) |

---

## 5. 의사결정 필요 사항

### Decision 1: 임베딩 전략

#### 옵션 A — 사전 임베딩 (Pre-computed)

```
[Mac Mini] BGE-M3로 전체 위키 임베딩 → DB 파일 생성
    ↓ (파일 전송)
[Galaxy S23 Ultra] DB 파일 로드 → 쿼리 임베딩만 온디바이스
```

| 장점 | 단점 |
|------|------|
| 고품질 임베딩 (BGE-M3 1024차원) | 쿼리 임베딩에도 임베딩 모델 필요 |
| 폰의 연산 부담 최소화 | 위키 업데이트 시 Mac에서 재임베딩 필요 |
| 기존 인프라 활용 가능 | 완전한 오프라인 독립이 아님 |

#### 옵션 B — 완전 온디바이스 (Fully On-Device)

```
[Galaxy S23 Ultra]
  경량 임베딩 모델 (all-MiniLM-L6-v2 ~80MB)
  + Gemma 4 E2B (~1.5GB)
  + SQLite 벡터 DB
  모든 처리를 폰에서 수행
```

| 장점 | 단점 |
|------|------|
| 완전 오프라인 독립 | 임베딩 품질 저하 (384차원 vs 1024차원) |
| 위키 업데이트도 폰에서 가능 | 총 메모리 ~1.6GB (여유 있음) |
| 진정한 엣지 AI | 임베딩 모델 추가 관리 필요 |

#### 옵션 C — 하이브리드

```
[Mac Mini] BGE-M3로 사전 임베딩 → DB 전송
[Galaxy S23 Ultra] 경량 임베딩 모델로 쿼리 임베딩 → DB 검색 → Gemma 4 생성
```

| 장점 | 단점 |
|------|------|
| 문서 임베딩은 고품질 유지 | 문서 벡터 ↔ 쿼리 벡터 모델 불일치 |
| 쿼리는 온디바이스 처리 | 모델 불일치로 검색 정확도 저하 가능 |

> **권장**: 옵션 A 또는 B. 옵션 C는 임베딩 모델 불일치로 검색 품질이 떨어질 수 있음.

---

### Decision 2: 앱 형태

#### 옵션 A — Android 네이티브 (Kotlin)

| 장점 | 단점 |
|------|------|
| GPU/NPU 직접 접근 | Android 개발 경험 필요 |
| Google AI Edge SDK 네이티브 통합 | 코드베이스가 기존 프로젝트와 완전 분리 |
| 최적 성능 | 개발 기간 길어짐 |

#### 옵션 B — 로컬 서버 + 웹앱 (Termux 등)

```
[Termux on Galaxy S23 Ultra]
  Node.js / Python 서버
  + Ollama (ARM 빌드) 또는 llama.cpp
  + SQLite
  → localhost:PORT 에서 웹 UI 제공
```

| 장점 | 단점 |
|------|------|
| 기존 Next.js 코드 재활용 가능 | Termux 환경 제약 |
| 웹 기반 UI | 성능이 네이티브 대비 떨어짐 |
| 빠른 프로토타이핑 | 백그라운드 실행 제한 |

#### 옵션 C — Flutter / React Native 크로스플랫폼

| 장점 | 단점 |
|------|------|
| iOS 확장 가능 | 네이티브 AI 라이브러리 브릿지 필요 |
| 웹 기술 활용 | 추가 프레임워크 학습 |

---

### Decision 3: 임베딩 모델 선택 (온디바이스 시)

| 모델 | 차원 | 크기 | 언어 | 비고 |
|------|------|------|------|------|
| all-MiniLM-L6-v2 | 384 | ~80MB | 다국어 (영어 중심) | 가장 경량 |
| multilingual-e5-small | 384 | ~470MB | 다국어 | 한국어 지원 우수 |
| BGE-M3 (양자화) | 1024 | ~600MB+ | 다국어 | 기존과 동일 모델, 무거움 |
| gte-small | 384 | ~67MB | 영어 중심 | 초경량 |

> 한국어 블로그 기반이므로 **다국어 지원**이 중요한 선택 기준.

---

### Decision 4: 벡터 저장소

| 옵션 | 장점 | 단점 |
|------|------|------|
| SQLite + sqlite-vec | 기존과 동일, 단일 파일 | ARM 빌드 필요 |
| USearch (usearch) | 경량, ARM 지원 | 새로운 의존성 |
| FAISS Lite | 검증된 라이브러리 | 모바일 빌드 복잡 |
| 인메모리 (brute-force) | 118개 청크면 충분 | 확장성 없음 |

> 118개 청크 규모에서는 brute-force 코사인 유사도도 충분히 빠름 (< 1ms).

---

## 6. Galaxy S23 Ultra 리소스 예산

```
총 RAM: 12GB
- OS + 기본 앱:        ~4GB
- 사용 가능:           ~8GB
- Gemma 4 E2B (4bit): ~1.5GB
- 임베딩 모델:         ~0.1-0.6GB
- SQLite DB:           ~1MB (118 청크)
- 앱 런타임:           ~0.5GB
────────────────────────────────
- 총 예상 사용:        ~2.1-2.6GB
- 여유:               ~5.4-5.9GB ✓ 충분
```

---

## 7. 다음 단계

의사결정 완료 후:

1. [ ] Decision 1~4 확정
2. [ ] 프로젝트 구조 설계
3. [ ] 개발 환경 세팅 (Mac Mini에서 개발, Galaxy S23 Ultra에서 테스트)
4. [ ] 임베딩 파이프라인 구현
5. [ ] 온디바이스 추론 환경 구성
6. [ ] UI 구현
7. [ ] 통합 테스트

---

## 참고 자료

- [Gemma 4 Edge 블로그](https://developers.googleblog.com/bring-state-of-the-art-agentic-skills-to-the-edge-with-gemma-4/)
- [Hugging Face - google/gemma-4-E2B](https://huggingface.co/google/gemma-4-E2B)
- [Google AI Edge SDK](https://ai.google.dev/edge)
- [Google AI Edge Gallery](https://github.com/nicholasgasior/google-ai-edge-gallery)
- [LiteRT-LM](https://ai.google.dev/edge/litert)
- [sqlite-vec](https://github.com/asg017/sqlite-vec)
- 기존 프로젝트: `peterica-blog-chat`
