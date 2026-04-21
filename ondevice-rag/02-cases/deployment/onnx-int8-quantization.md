# 448MB가 113MB 되는 길 — ONNX INT8 양자화 실전

ㅁ 들어가며

엣지 RAG의 임베딩 모델은 폰 안에 들어가야 한다.
그런데 HuggingFace에서 받은 원본은 **448MB**다.
113MB에 맞춰야 APK 크기도 살고, 메모리도 산다.

이 글은 `multilingual-e5-small-ko-v2`를 ONNX INT8로 줄이고, 품질이 얼마나 보존되는지 재본 기록이다.
파이프라인은 네 단계. 코드는 거의 한 줄씩이다.

---

ㅁ 양자화가 하는 일 — float32 → int8

예전에 "LLM 양자화 & 로컬 추론 최적화"를 언젠가 제대로 다룰 주제로 적어둔 적이 있다 ([997](https://peterica.tistory.com/997)).
파라미터가 GPT-3의 10배로 뛰던 시대([762](https://peterica.tistory.com/762))의 반대편에, 이 글이 그 숙제를 실전으로 꺼내온다.

ㅇ 버리는 것과 지키는 것

> 양자화의 이론적 배경은 [LLM System Lab의 Quantization 토픽](https://llm-study-web.vercel.app/topic/quantization)에 더 깊게 정리해두었다. 이 글은 그 위에서 **실전 파이프라인**에 집중한다.

모델 파라미터는 기본적으로 **float32**로 저장된다.
한 숫자에 4바이트를 쓴다.
양자화는 이걸 **int8**(1바이트)로 압축한다 — 용량 1/4.

단순히 "0~255 범위로 잘라 넣기"는 아니다.
각 레이어의 가중치 범위를 측정해서 **scale**과 **zero point**로 매핑한다.
쉽게 말하면 — `scale`은 float 값을 INT8 범위(-128~127)에 **얼마나 압축할지**의 비율,
`zero point`는 float의 0이 **INT 축 위 어디에 놓이는지**의 기준점이다.
1바이트 정수 하나를 "원래 float의 근사치"로 되돌릴 수 있게.

→ 정보가 일부 **손실**된다.
하지만 자연어 임베딩은 **상대적 유사도**만 보존하면 되므로 손실이 뒤쪽까지 잘 이어지지 않는다.

ㅇ 동적 양자화 vs 정적 양자화

| 방식 | 가중치 | 활성화 | 필요한 것 |
|---|---|---|---|
| **Dynamic** | INT8 저장 | 추론 시 동적 계산 | 없음 — 한 줄로 끝 |
| **Static** | INT8 저장 | INT8 사전 계산 | calibration 데이터셋 |
| **QAT (훈련 중 양자화)** | INT8 | INT8 | 재학습 필요 |

이번에 쓴 건 **Dynamic**.
이유: calibration 데이터셋 준비 비용이 크고, 임베딩 모델은 **activation 분포가 비교적 고른** 편이라 정적까지 안 가도 품질이 유지된다.

---

ㅁ 실전 파이프라인 4단계

ㅇ 1. PyTorch → ONNX export

HuggingFace `optimum` CLI 한 줄로 끝.

```bash
optimum-cli export onnx \
  --model dragonkue/multilingual-e5-small-ko-v2 \
  --task feature-extraction \
  ./e5-ko-v2-onnx/
```

결과:
- `model.onnx` — **448MB** (float32)
- `tokenizer.json` — 16MB
- 메타 파일들 (config, tokenizer_config 등)

이 단계만으로도 이미 추론은 가능하다.
PyTorch 없이 ONNX Runtime만으로 돌릴 수 있어 **크로스 플랫폼 의존성**이 사라진다.

ㅇ 2. INT8 동적 양자화

Python 몇 줄.

```python
from onnxruntime.quantization import quantize_dynamic, QuantType

quantize_dynamic(
    model_input="e5-ko-v2-onnx/model.onnx",
    model_output="model_int8.onnx",
    weight_type=QuantType.QInt8,
)
```

결과: **112.6MB** (원본의 25%).

`weight_type`은 INT8/UINT8 둘 다 가능.
`QInt8`는 부호 있는 정수 — 음수 가중치가 있는 일반적인 선택.

ㅇ 3. 품질 검증

양자화로 얼마나 망가졌는지 실제로 재본다.
원본 모델과 INT8 모델을 같은 텍스트에 돌려 **cosine similarity**를 잰다.

```python
# 원본
ref = sentence_transformer.encode("query: 쿠버네티스 헬스체크")

# INT8 ONNX
onnx_vec = onnx_session.run(...)

# 두 벡터 사이 cosine
sim = cosine(ref, onnx_vec)  # 0.97~0.98
```

**0.97 이상이면 실용 OK**.
1.0에서 멀어진 만큼 두 벡터가 달라진 건 맞다.
하지만 검색은 **절대 거리가 아니라 상대 순위**로 동작한다 — 원본이 뽑는 Top-3 문서와 양자화 모델이 뽑는 Top-3 문서가 같은 순서로 나오면 사용자 경험은 구별되지 않는다.
0.97은 경험상 이 "순위 보존" 조건을 거의 항상 충족하는 값이다.

ㅇ 4. 모바일 assets 배치

Android 앱의 `assets/` 폴더에 두 파일을 넣는다.

```
mobile/app/src/main/assets/
├── model.onnx      (113MB)
└── tokenizer.onnx  (5MB, ORT-extensions)
```

> 토크나이저는 `tokenizer.json`(16MB) 대신 **ONNX 그래프로 변환**(5MB)해서 넣었다.
> 이유는 아래 "짚어볼 것들"에서 설명한다.

---

ㅁ 품질은 어디까지 떨어졌나

한국어 쿼리 5개로 검색 품질을 실제 측정했다.

| 쿼리 | 원본 Top-1 distance | INT8 Top-1 distance | 일치 |
|---|---|---|---|
| `쿠버네티스 헬스체크` | 0.412 | 0.415 | ✓ 동일 문서 |
| `APM 모니터링` | 0.337 | 0.340 | ✓ |
| `RAG 시스템` | 0.289 | 0.295 | ✓ |
| `graceful shutdown` | 0.356 | 0.361 | ✓ |
| `prometheus pull` | 0.421 | 0.427 | ✓ |

거리 값이 **0.003~0.006 증가**했지만 Top-1 문서는 모두 동일.
검색 품질 관점에서는 **사실상 무손실**에 가깝다.

---

ㅁ 짚어볼 것들

ㅇ 동적 양자화는 가중치만 — 활성화는 그대로다

"INT8 모델"이라고 하면 모든 연산이 8비트로 도는 것처럼 들린다.
하지만 동적 양자화는 **가중치만 INT8로 저장**하고, 실제 행렬곱은 INT8↔float 변환이 섞인다.
CPU에서는 작은 연산이라 큰 문제가 없지만, **NPU/GPU 가속이 필요할 땐 한계**가 된다.

→ 모바일 NPU를 최대 활용하려면 **정적 양자화**나 **QAT**로 가야 한다.
정적 양자화는 activation의 scale까지 **사전에 고정**해 추론 내내 INT8로만 돈다.
QAT(훈련 중 양자화)는 **훈련 때부터 양자화 오차를 학습에 반영**해 품질 손실을 더 줄인다.
둘 다 NPU가 **INT8 연산만 빠르게 처리하는 특성**에 맞춘 최적화다.
이번엔 CPU 추론이 목표라 동적이 충분했다.

ㅇ 토크나이저도 배포에 포함해야 한다 (함정 1)

모델만 양자화하면 끝이 아니다.
임베딩 전에 **텍스트를 토큰 ID로 바꾸는 토크나이저**가 필요하다.
`tokenizer.json`(16MB)은 HuggingFace 표준이지만, Android에서 쓰려면 별도 라이브러리(DJL 등)가 필요했다.

DJL이 Android arm64 네이티브 바이너리를 **공식 배포하지 않는다**는 사실을 뒤늦게 확인했다.
대안: `onnxruntime-extensions`의 `SentencepieceTokenizer`를 ONNX 그래프로 뽑아 **model.onnx 옆에 `tokenizer.onnx`로 동봉**.

→ 양자화 파이프라인의 출력물은 모델 하나가 아니라 **모델 + 토크나이저 세트**다.

ㅇ 품질 검증은 벤치마크가 아니라 "내 쿼리"로 한다

MTEB 같은 공개 벤치마크 점수는 참고용이다.
양자화 전후 **내가 실제로 쓸 쿼리**로 Top-1이 유지되는지 재보는 게 더 중요하다.
118 청크 규모에선 5~10개 대표 쿼리로도 충분히 의사결정할 수 있다.

→ "벤치마크 점수가 0.85에서 0.83으로 떨어졌다"보다 **"내 실제 쿼리 5개가 전부 같은 문서를 뽑는다"**가 더 믿음직하다.

ㅇ INT4, BF16, Matryoshka — 다음 선택지

INT8에서 멈출 이유는 없다.

| 선택 | 크기 | 품질 | 비용 |
|---|---|---|---|
| **INT4** | ~56MB | 약간 손실 더 | 도구는 성숙, 검증 필요 |
| **BF16** | ~224MB | 거의 무손실 | CPU 지원 고르지 않음 |
| **Matryoshka 차원 절단** | 비례 | 점진적 손실 | 모델이 지원해야 함 |

→ 앞으로 실험할 방향.
특히 Matryoshka는 **양자화와 차원 절단이 독립**이라 **둘을 곱해** 쓸 수 있다.

---

ㅁ 마무리

원본 448MB와 INT8 113MB는 **같은 지식을 담은 서로 다른 그릇**이다.
손실은 분명히 있지만, Top-1 검색 관점에서는 눈에 띄지 않는다.
덕분에 모델이 **주머니에 들어갔다.**

→ 양자화는 모델을 작게 만드는 게 아니라, **쓸모의 모양을 맞추는 과정**이다.

---

ㅁ 함께 보면 좋은 사이트

ㅇ 양자화 도구
- HuggingFace Optimum (ONNX export): https://huggingface.co/docs/optimum
- ONNX Runtime Quantization: https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html
- onnxruntime-extensions (tokenizer as ONNX): https://github.com/microsoft/onnxruntime-extensions

ㅇ 모델
- dragonkue/multilingual-e5-small-ko-v2: https://huggingface.co/dragonkue/multilingual-e5-small-ko-v2
- MTEB 벤치마크: https://huggingface.co/spaces/mteb/leaderboard

ㅇ 더 공부하기 — LLM System Lab
- Quantization (이론 심화): https://llm-study-web.vercel.app/topic/quantization
- Embedding: https://llm-study-web.vercel.app/topic/embedding
- Embedding Space (인터랙티브 Lab): https://llm-study-web.vercel.app/labs/embedding-space

ㅇ 연관된 이전 글 (양자화 흐름)
- LLM 파라미터가 커지던 시대: https://peterica.tistory.com/762
- RAG/Agent/Infra 엔지니어의 지식 정리법 (양자화 관심 주제로 등록): https://peterica.tistory.com/997

ㅇ 시리즈
- Mac Mini RAG 구축기: https://peterica.tistory.com/1064
- sqlite-vec 선택 이유: https://peterica.tistory.com/1065
- 맥미니 RAG를 넘어서 — 모바일 온디바이스 AI를 시작하다: https://peterica.tistory.com/1066
- 3트랙 병렬 리서치 — 쓰기 전에 물어봐야 하는 것들: https://peterica.tistory.com/1067
- 엣지 RAG의 AI 도구 지도 — 왜 Python이 접합점인가: https://peterica.tistory.com/1068
