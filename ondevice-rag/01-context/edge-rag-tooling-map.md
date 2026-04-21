# 엣지 RAG의 AI 도구 지도 — 왜 Python이 접합점인가

ㅁ 들어가며

AI 시스템을 만들다 보면 같은 질문이 돌아온다.
**"어떤 도구를, 어떤 언어에서 쓰지?"**

특히 엣지 RAG처럼 추론·임베딩·양자화·프롬프트가 한 시스템 안에 섞이면 선택지가 많아 보이지만,
실제로 붙여보면 **도구가 사는 언어**가 먼저 결정을 내린다.

이 글은 엣지 RAG를 만들 때 필요한 AI 도구들을 정리하고, 왜 Python이 그 **접합점**이 되는지 보는 지도다.
서버 스택을 Next.js(TypeScript)에서 FastAPI(Python)로 옮긴 내 경험은 마지막에 증거로 붙인다.

---

ㅁ 엣지 RAG에 필요한 AI 도구 4 영역

엣지 RAG는 네 개의 컴포넌트로 나뉜다.
각 영역마다 표준에 가까운 도구가 몇 개 있고, 대부분 **같은 언어 생태계**에 산다.

ㅇ 추론 엔진 (Inference Runtime)

모델을 실제로 돌려 토큰을 내보내는 레이어.

| 도구 | 주 언어 | 특징 |
|---|---|---|
| `llama.cpp` | C/C++ | GGUF 포맷, CPU/GPU/Metal/Vulkan 다 지원 |
| `Ollama` | Go (서버) | llama.cpp 위의 관리자 — 모델 다운로드·스왑·API |
| `llama-cpp-python` | Python | llama.cpp 직접 바인딩, 프로세스 내장 |
| `LiteRT-LM` | C++ (Android NDK) | Google 온디바이스 런타임, `.litertlm` 포맷 |
| `vLLM`, `TGI` | Python | 서버 GPU 대용량 추론 (엣지 대상 아님) |

현업에서 쓰는 실용 경로는 둘 중 하나다.
- 개발·운영 편의: **Ollama** (서버 프로세스 + HTTP API)
- 타이트한 제어: **llama-cpp-python** (프로세스 내장)

둘 다 진입점은 **C++ 엔진**이고, 편한 바인딩은 **Python**에 있다.

ㅇ 임베딩 모델 (Embedding)

텍스트를 벡터로 바꾸는 레이어.

| 도구 | 주 언어 | 특징 |
|---|---|---|
| `sentence-transformers` | Python | HuggingFace 모델 로드·인코딩 표준 |
| `ONNX Runtime` | C++ core + 각 언어 바인딩 | 양자화 모델 고속 추론 |
| Ollama `/api/embed` | Go + REST | Ollama가 임베딩 모델도 관리 |
| `fastembed` | Python | ONNX 기반 경량 임베딩 래퍼 |

모델 자체는 **언어 독립**이지만, 실사용 파이프라인은 Python에서 시작되는 경우가 압도적으로 많다.

ㅇ 양자화 툴체인 (Quantization)

모델 크기를 줄이는 단계.

| 도구 | 주 언어 | 용도 |
|---|---|---|
| `optimum` (HuggingFace) | Python | PyTorch → ONNX export |
| `onnxruntime.quantization` | Python | 동적/정적 INT8 양자화 |
| `llama.cpp/quantize` | C++ | GGUF 포맷 양자화 (Q4_K_M 등) |
| `TensorFlow Lite Converter` | Python | LiteRT 포맷 변환 |

양자화는 **모델 제작 파이프라인** 영역이라 Python 쏠림이 가장 심하다.

ㅇ 프롬프트 템플릿 엔진 (Chat Template)

HuggingFace 모델은 `tokenizer_config.json`에 **Jinja2 기반 chat_template**을 담아 배포한다.
런타임에 이걸 렌더링해야 제대로 된 프롬프트가 된다.

| 도구 | 주 언어 | 용도 |
|---|---|---|
| `minja` | C++17 | llama.cpp 내장, 경량 Jinja2 서브셋 |
| `Jinja2` | Python | 원조 — sentence-transformers·transformers가 사용 |
| `nunjucks` | JavaScript | Jinja 계열, 완전 일치 X |

llama.cpp 기반 추론을 쓰면 자동으로 minja가 따라온다.
이걸 TypeScript에서 동일하게 쓰려면 nunjucks로 **다시 구현**해야 한다.

---

ㅁ 왜 모든 도구가 Python에 모이는가

위 표를 펼쳐놓고 보면 패턴이 한눈에 들어온다.
**"진짜 엔진은 C/C++, 쓸 만한 바인딩은 Python"** 이다.

ㅇ 연구 커뮤니티의 공용어

LLM·임베딩 모델의 **원본 학습 코드**가 PyTorch다.
논문·튜토리얼·모델 카드가 Python으로 나온다.
연구에서 응용으로 내려올 때, 가장 짧은 경로가 Python을 거친다.

ㅇ 바인딩이 Python 우선으로 만들어진다

`llama.cpp`, `ONNX Runtime`, `TFLite` — 모두 C/C++ 코어다.
하지만 공식 examples과 튜토리얼은 **Python**이 먼저 등장한다.
TypeScript, Go, Rust 바인딩은 **존재해도 늦게 따라온다.**

ㅇ 데이터 과학 파이프라인의 유산

청킹·전처리·실험 로깅·벤치마크 — 전통적으로 Python이 강한 영역이다.
엣지 RAG의 `ingest` 단계는 이 계열과 사실상 구분되지 않는다.
pandas, numpy가 없는 데이터 파이프라인이 얼마나 불편한지는 한 번만 해보면 안다.

→ Python은 **AI 도구의 접합점**이다.
"최고의 언어"라서가 아니라, **"도구가 먼저 살러 들어온 곳"** 이라서.

---

ㅁ 포팅이 증명한 것 — Next.js → FastAPI

이 구조를 머리로만 알기보다 직접 겪어보는 게 빨랐다.
기존 Mac Mini RAG는 Next.js + TypeScript + AI SDK로 돌고 있었다.
엣지 RAG 서버를 새로 만들면서 FastAPI(Python)로 갈아탔다.

ㅇ 1:1 포팅 가능

핵심 모듈 6개를 옮기는 데 큰 저항이 없었다.

| 원본 (TS) | 이식 (Python) | 역할 |
|---|---|---|
| `lib/chunk.ts` | `server/chunk.py` | 마크다운 파싱 + h1-h3 청킹 |
| `lib/embed.ts` | `server/embed.py` | Ollama `/api/embed` 호출 |
| `lib/db.ts` | `server/db.py` | SQLite + sqlite-vec |
| `lib/rag.ts` | `server/rag.py` | top-k 검색 + 시스템 프롬프트 |
| `scripts/ingest.ts` | `server/ingest.py` | 위키 → 청크 → 임베딩 → DB |
| `app/api/chat/route.ts` | `server/main.py` | `/query` `/search` `/sync` |

`async/await`, 타입 힌팅, `dataclass`는 TypeScript interface와 거의 대응된다.
벡터 DB 스키마(`sqlite-vec`)는 언어 독립이라 그대로 썼다.

ㅇ 바꾸지 않았다면 치러야 했을 비용

만약 Next.js를 유지했다면:
- `llama-cpp-python` 직접 호출 → Python 서브프로세스 + IPC
- `optimum` 양자화 → 빌드 단계에만 Python 붙이고 런타임은 TS
- `minja` chat_template 렌더링 → `nunjucks`로 재구현 + 템플릿 호환성 테스트

**각 도구마다 브릿지 한 겹씩이 쌓인다.**
이주 비용보다 잔류 비용이 커진 지점이 Python 전환의 손익분기점이었다.

---

ㅁ 듀얼 임베딩 파이프라인 — 이 스택에서만 가능했던 설계

서버 이식이 끝난 뒤 하나 더 했다.
**임베딩을 두 번 돌리는 구조.**

ㅇ 왜 두 개의 DB인가

서버와 모바일은 서로 다른 임베딩 모델을 쓴다.
- 서버: `bge-m3` (1024차원, 큰 모델)
- 모바일: `e5-small-ko-v2` (384차원, 한국어 검증된 경량)

같은 질문이라도 다른 벡터 공간에서 검색해야 한다.
그래서 **같은 위키 문서를 두 모델로 각각 임베딩**해 `server.db`, `mobile.db`를 만든다.
폰은 `GET /sync`로 자기 DB만 받아간다.

ㅇ 순차 실행이 해법

맥미니는 8GB RAM이다.
두 모델을 동시에 올리면 OS·IDE와 충돌한다.

Ollama가 기본으로 **"한 번에 한 모델만 메모리에 올리고, 다음 요청에 스왑"** 이라 이 문제가 설계 시점에서 사라진다.
`ingest.py`는 bge-m3 → 전부 처리 → 스왑 → e5 → 전부 처리.
총 20초 이내.

이 구조는 Ollama가 Python에서 HTTP API로 노출되기 때문에 가능했다.
**도구가 공유 프로세스로 돌아주니 내 서버가 모델을 독점하지 않는다.**

---

ㅁ 짚고 넘어갈 기술 고민

ㅇ 언어 선택은 "도구의 중력"을 따른다

"익숙한 언어"가 아니라 **"도구가 사는 언어"** 를 먼저 본다.
프레임워크는 대체재가 많지만, 추론 엔진·양자화 툴체인은 대체재가 적다.

→ **대체 불가능한 쪽에 언어를 맞춘다.**

ㅇ 웹 레이어와 추론 엔진은 다른 레이어다

"FastAPI로 LLM을 돌린다"는 말은 정확하지 않다.
FastAPI는 HTTP 채널이고, 추론은 `llama-cpp-python`이나 Ollama가 담당한다.

→ 한 언어 안에서도 **역할이 나뉜다.** 성능 튜닝 지점을 찾으려면 어느 레이어가 느린지 먼저 본다.

---

ㅁ 생각해 볼 것들

ㅇ Python 쏠림이 영원할까

`transformers.js`가 TypeScript에 자리 잡고 있다.
Rust의 `candle`이 엣지에서 자라는 중이다.
언젠가 **AI 도구가 여러 언어에 자리 잡는 시대**가 올 수 있다.

→ 그 시점에는 "도구가 사는 곳" 기준이 흔들린다.
지금은 Python이 명확한 답일 뿐.

ㅇ Python 안에서도 선택지는 갈린다 — Ollama vs llama-cpp-python

추론 레이어의 두 옵션이다.
- `llama-cpp-python`: 모델을 프로세스 안에 올림 → 빠름, 메모리 독점
- `Ollama`: 별도 서버 프로세스, 여러 앱이 공유 → 오버헤드 있지만 효율적

→ **같은 생태계 안에서도 "공유 vs 전용"이 설계 기준**이 된다.
리소스 환경(8GB냐 64GB냐)이 이 선택을 뒤집는다.

---

ㅁ 마무리

엣지 RAG를 쪼개서 보면 각 영역에 표준 도구가 한두 개씩 있다.
그 도구들을 이어 붙이면 **언어가 자동으로 결정**된다.

Python이 엣지 AI의 접합점이 된 건 우연이 아니다.
연구 커뮤니티·바인딩 우선순위·데이터 파이프라인 유산이 이 한 언어에 쌓였기 때문이다.

→ 기술은 선택이 아니라 **지도**다. 도구가 사는 곳에 따라 길이 이미 나 있다.

---

ㅁ 함께 보면 좋은 사이트

ㅇ 추론 엔진
- llama.cpp: https://github.com/ggml-org/llama.cpp
- Ollama: https://ollama.com/
- llama-cpp-python: https://github.com/abetlen/llama-cpp-python
- LiteRT (구 TFLite): https://ai.google.dev/edge/litert

ㅇ 임베딩 & 양자화
- sentence-transformers: https://sbert.net/
- ONNX Runtime: https://onnxruntime.ai/
- HuggingFace Optimum: https://huggingface.co/docs/optimum

ㅇ 프롬프트 & 템플릿
- minja (llama.cpp 내장 Jinja2): https://github.com/google/minja

ㅇ 임베딩 모델
- BAAI/bge-m3: https://huggingface.co/BAAI/bge-m3
- dragonkue/multilingual-e5-small-ko-v2: https://huggingface.co/dragonkue/multilingual-e5-small-ko-v2

ㅇ 더 공부하기 — LLM System Lab
- RAG Pipeline: https://llm-study-web.vercel.app/topic/rag-pipeline
- Embedding: https://llm-study-web.vercel.app/topic/embedding
- Quantization: https://llm-study-web.vercel.app/topic/quantization
- Prompt Engineering: https://llm-study-web.vercel.app/topic/prompt-engineering

ㅇ 이전 글
- Mac Mini RAG 구축기: https://peterica.tistory.com/1064
- sqlite-vec 선택 이유: https://peterica.tistory.com/1065
- 맥미니 RAG를 넘어서 — 모바일 온디바이스 AI를 시작하다: https://peterica.tistory.com/1066
- 3트랙 병렬 리서치 — 쓰기 전에 물어봐야 하는 것들: https://peterica.tistory.com/1067
