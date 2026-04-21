# 엣지에서 JSON 강제는 왜 역효과였나 — 2B 모델의 프롬프트 capacity 실측

ㅁ 들어가며

LLM이 답변할 때 **근거 인용을 반드시 붙이도록** 강제하려면 어떻게 해야 할까.

이 프로젝트의 RAG 시스템은 블로그 문서를 근거로 기술 질문에 답한다.
답변 품질보다 먼저 지켜야 할 것이 있다 — **어떤 문서 청크가 근거였는지**가 답변에 명시되는 것.
근거 없는 문장이 섞이거나 `[#1]` 같은 인용 표기를 모델이 빠뜨리면 **RAG 시스템의 계약이 깨진다**.

Mac Mini에서 돌리는 서버(Gemma 4, 4B)에서는 이 계약을 **JSON 스키마 강제**로 해결했다.
답변을 `{"sentences": [{"text": "...", "cite": [1]}]}` 형식으로만 쓰게 하면 인용 필드가 **구조적으로 존재**해야 한다 — 빠뜨릴 방법이 없다.
자연어 규칙(v1)이 못 지키던 "모든 문장에 인용"을 JSON 양식이 **구조로 강제**해준 것이다.
규칙 준수율 지표(CC)는 덤으로 0.57 → 0.89로 올랐지만, 핵심 목적은 **출력 형식 보장**이었다.

같은 프롬프트를 Galaxy S23 Ultra의 Gemma 4 E2B(2B)에 이식했다.
JSON 파싱은 서버에서처럼 완벽했다 — 형식 보장은 달성.
그런데 답변 내용이 `"Kubernetes 환경에서 graceful shutdown이란 [#1]."` — 질문을 그대로 반복하는 수준으로 축소됐다.

결론부터 말하면,
2B 모델은 용량이 작아서 "JSON 양식 맞추기 + 모든 규칙 챙기기"에 신경쓰다 "안전하게 짧게 답하기" 모드로 수렴했다.
큰 모델에서 통한 트릭이 작은 모델에선 반대로 작용할 수 있었다.

형식은 지켜졌지만 내용이 증발했다.
이 글은 그 하루의 실측 기록이다.

---

ㅁ 서버 v4 — 형식 계약을 JSON으로 강제한다

RAG 시스템에서 LLM 답변의 핵심 계약은 두 가지다.

1. **각 문장에 근거 청크 번호가 반드시 붙는다** — 사용자가 답의 출처를 추적할 수 있어야 한다
2. **근거가 없으면 답하지 않고 "문서에 근거 없음"만 반환한다** — 모델이 CONTEXT 밖 상식으로 답해버리면 RAG가 의미 없다

자연어로 규칙을 서술(v1)했을 때 두 계약이 자주 깨졌다.
LLM은 인용 번호를 빠뜨리거나, "일반적으로" 같은 추측 어휘로 CONTEXT 밖 내용을 섞어 답했다.

ㅇ v4 — JSON 스키마로 구조화

해법은 규칙을 **JSON 양식**으로 옮기는 것.

```
{
  "grounded": true | false,
  "sentences": [
    {"text": "문장", "cite": [1]}
  ]
}
```

이 프로젝트는 **프롬프트 지시**로만 강제했다 — 시스템 메시지에 "이 스키마로만 답하라"고 적는 방식.
양식을 지키면 `cite` 필드가 구조적으로 존재해야 해서 인용 누락이 막히고, `grounded: false`면 `sentences=[]`로 빈 배열이 반환돼 "근거 없음" 계약도 구조가 책임진다.
서버는 이 JSON을 파싱해 `문장 [#1].` 형식으로 재조립한다.

> 더 엄격한 강제 — LLM이 **토큰 생성 단계에서** 스키마를 벗어나지 못하도록 막는 기법 — 은 오픈소스 생태계가 성숙해 있다.
> Ollama의 `format: "json"` 모드, [llama.cpp GBNF grammar](https://github.com/ggerganov/llama.cpp/blob/master/grammars/README.md), [Outlines](https://github.com/dottxt-ai/outlines), [Guidance](https://github.com/guidance-ai/guidance) 등.
> 프롬프트 지시는 "모델이 따르기로 선택했을 때만 성립"하는 계약이고, grammar-level 강제는 "구조적으로 벗어날 수 없는" 계약이다.
> 이 프로젝트는 전자로 충분했고 — 적어도 4B 서버에서는.

ㅇ 품질 지표는 덤으로 올랐다

목표는 형식 계약이었지만, 22개 쿼리로 측정한 결과 규칙 준수율도 같이 상승했다.

| 프롬프트 | CC(규칙 준수율) | SR(스키마 위반율) | CorrectRefuse |
|---|---|---|---|
| v1 (자연어) | 0.57 | — | 0.89 |
| v4 (JSON)   | **0.89** | **0.00** | **1.00** |

CC 32p, CorrectRefuse 11p 개선.
**양식을 지키려는 힘이 규칙을 자동으로 지키게 한 결과**다 — 형식 보장과 품질 향상이 한 묶음으로 따라왔다.
v4 JSON은 서버의 기본 프롬프트로 채택됐다.

---

ㅁ 엣지로 이식했다

같은 프롬프트를 폰의 `ChatViewModel.localSearch()`에 붙였다.
서버의 `rag.render_answer` 파서도 Kotlin으로 포팅했다.

ㅇ 이식한 것

- 시스템 프롬프트: 서버 `build_system_prompt_v4` 본문을 Kotlin `buildString`으로 그대로 복제
- 파서: `org.json.JSONObject`로 ```json``` 펜스 제거 + 스키마 파싱 + `[#n]` 재부착 + 구두점 보존 + **파싱 실패 시 원문 폴백**

ㅇ 폴백이 있는 이유

2B 모델이 JSON 스키마를 지키지 못할 수도 있다고 가정했다.
그 경우 화면에 파싱 에러를 보여주는 건 사용자 경험 회귀다.
`JSONException`을 잡으면 raw 문자열을 그대로 반환하도록 했다.
**안전망**은 실험 전에 쳐놓는다.

---

ㅁ 그런데 답변이 축소됐다

같은 쿼리 "쿠버네티스에서 graceful shutdown이란?"으로 두 버전을 재봤다.

ㅇ B-1 (자연어 v4-lite-v2)

> Kubernetes 환경에서 graceful shutdown은 애플리케이션이 정상적으로 종료될 수 있도록 하는 것을 의미합니다 [#1].
> 이는 애플리케이션이 요청을 처리하고 현재 작업을 완료한 후 안전하게 종료되도록 보장합니다 [#1].

2문장.
CONTEXT의 핵심을 요약하고, 인용을 문장마다 붙이고, 추측 어휘가 없다.

ㅇ P2-18 (v4 JSON)

LLM이 실제로 뱉은 raw JSON.

```json
{
  "grounded": true,
  "sentences": [
    { "text": "Kubernetes 환경에서 graceful shutdown이란", "cite": [1] }
  ]
}
```

파서가 통과시킨 rendered.

> Kubernetes 환경에서 graceful shutdown이란 [#1].

한 문장.
**질문 제목을 그대로 반복**했다.

JSON 파싱은 100점.
답변 내용은 0점에 가깝다.

---

ㅁ 원인 분석 — capacity의 경제학

2B 모델은 4B의 절반 크기다.
"절반"이 의미하는 건 단순히 파라미터 수가 아니라, **한 응답에 쓸 수 있는 주의(attention) 여유**다.

v4 JSON 프롬프트는 동시에 여러 지시를 쌓는다.

1. 질문의 토픽을 한 단어로 추출하라
2. 각 CONTEXT 블록에 그 토픽이 등장하는지 확인하라
3. 등장하면 `grounded: true`, 아니면 `false`
4. JSON 양식을 정확히 지켜라
5. `text` 필드 안엔 `[#n]` 표기를 넣지 말라
6. 추측 어휘 금지
7. 외부 지식 금지
8. 실제 내용을 담으라

4B는 이 8개를 모두 챙기면서도 **내용**에 쓸 capacity가 남는다.
2B는 남지 않는다.
"안전하게 짧게"가 위험을 최소화하는 전략이 된다.
질문 제목을 그대로 반복하는 것은 — 모델 입장에선 — **가장 안전한 답**이다.

ㅇ 다른 각도

B-1 자연어 프롬프트는 JSON 양식 부담이 없다.
규칙 6개(인용, 길이, OOD, 외부지식 금지, 추측 금지)로 끝.
같은 capacity에서 **내용**에 더 많은 여유가 남는다.

결과적으로 2B 모델엔 자연어가 더 적합했다.

> 이 경험은 "작은 모델일수록 프롬프트의 **제약 총량**을 줄여야 한다"는 경험칙을 처음으로 실측으로 확인한 순간이었다.

---

ㅁ 롤백 전략 — 인프라는 남긴다

결론은 시스템 프롬프트를 B-1(자연어)로 되돌리는 것.
하지만 **모든 것을 되돌리지는 않았다**.

ㅇ 남긴 것

- `renderAnswer()` 파서 — raw가 JSON이 아니면 원문 그대로 통과 (폴백 동작)
- `Log.i("localSearch raw/rendered")` — 향후 품질 관찰용 훅

ㅇ 바꾼 것

- 시스템 프롬프트만 v4 JSON → v4-lite-v2 (자연어)

이 비대칭 롤백이 중요한 이유가 있다.
언젠가 모바일에 4B 모델을 올릴 수 있게 되면 — 혹은 더 효율적인 양자화가 나오면 — 프롬프트 문자열 하나만 다시 바꾸면 v4 JSON이 살아난다.
파서와 로그는 하드웨어가 따라올 때까지 **슬리핑 인프라**로 대기한다.

실패한 실험을 **완전히 지우는 대신 비가역 부분만 되돌리는** 습관은 대부분의 롤백보다 싸다.

---

ㅁ 짚어볼 것들

ㅇ "서버에서 통한 게 엣지에서도 통한다"는 가정의 위험

이 가정이 값비싼 이유는, 실험하기 전엔 **확신**처럼 보이기 때문이다.
서버에서 CC 32p 상승은 놀라운 결과였다.
"이걸 폰에서도 쓰면 같은 이득"이라는 추론은 **자연스러워 보인다**.

자연스러워 보인다는 것이 함정이다.
모델 크기가 절반이면 **같은 프롬프트가 모델에게 전혀 다른 task**로 느껴진다.

→ 배포 전에 실측 한 번이 어렵더라도, 배포 후에 "왜 이게 이모양이지"를 추적하는 건 더 비싸다.

ㅇ 지표는 분리해야 한다 — 기술 성공 ≠ 품질 성공

이번 실험의 한 줄 요약은 **"JSON 파싱률 100%, 답변 품질 회귀"**다.
한 지표만 봤다면 성공으로 기록됐을 실험이다.

- **기술 지표**: JSON validity, 파싱 성공률, schema 준수율
- **품질 지표**: 답변 길이, 핵심 키워드 포함, CONTEXT 활용도, 사용자 체감

두 지표는 **독립적**이다.
둘 중 하나만 통과한 결과를 "성공"으로 부르지 않는 규율이 필요하다.

ㅇ 작은 모델에게 준 제약은 **capacity 예산**이다

이번 경험의 일반 법칙화.

큰 모델은 프롬프트 제약이 **품질 방어벽**이다 — 제약이 많을수록 규칙 위반이 줄어든다.
작은 모델은 프롬프트 제약이 **capacity 세금**이다 — 제약이 많을수록 내용이 얇아진다.

→ 2B 모델은 "핵심 규칙 3~5개"만 남겨야 한다.
JSON 스키마 + step-by-step 검토 + 예시 + 금지 어휘 같은 복합 구조는 **용량 초과**다.

ㅇ 자연어 vs 구조화 — 이분법이 아니다

B-1(자연어)과 P2-18(JSON) 사이엔 **중간 지점**이 있을 수 있다.

- 자연어로 규칙만 주되, 문장 형식만 고정 ("각 문장은 [#n]으로 끝난다")
- 출력 앞머리에 매우 짧은 structural header ("PLAN: ... ANSWER: ...")

작은 모델의 capacity 예산 안에서 **구조화의 이득**만 뽑아오는 절충안을 찾는 실험이 다음 과제다.

---

ㅁ 마무리

같은 프롬프트가 두 모델에서 반대로 작동했다.
문제는 프롬프트가 아니라 **모델이 가진 생각의 여유**였다.

→ 프롬프트 엔지니어링은 모델 용량이라는 **숨은 변수**를 늘 전제에 두어야 한다.

서버의 성공이 엣지의 성공을 보장하지 않는다는 것을, 이번에 한 편의 실패 실험으로 배웠다.
롤백은 패배가 아니라, 잘못된 가정을 지우고 **맞는 곳으로 되돌아가는** 행위다.

---

ㅁ 함께 보면 좋은 사이트

ㅇ Structured output — LLM에 JSON을 강제하는 오픈소스

- Ollama format 파라미터 (서버측 JSON 모드): https://github.com/ollama/ollama/blob/main/docs/api.md#request-json-mode
- llama.cpp GBNF grammar (토큰 생성 단계 강제): https://github.com/ggerganov/llama.cpp/blob/master/grammars/README.md
- Outlines (Python, structured generation): https://github.com/dottxt-ai/outlines
- Guidance (Microsoft, constrained generation): https://github.com/guidance-ai/guidance
- jsonformer: https://github.com/1rgs/jsonformer

ㅇ 프롬프트 엔지니어링

- Anthropic prompt engineering guide: https://docs.anthropic.com/claude/docs/introduction-to-prompt-design
- Self-consistency & chain-of-thought 원리: https://arxiv.org/abs/2203.11171

ㅇ 온디바이스 LLM

- Gemma on LiteRT-LM: https://ai.google.dev/edge/litert/models/gemma
- Gemma 4 E2B model card: https://huggingface.co/google/gemma-3n-E2B-it

ㅇ 더 공부하기 — LLM System Lab

- Prompt Engineering (규칙 vs 구조화): https://llm-study-web.vercel.app/topic/prompt-engineering
- Model Capacity (파라미터와 행동의 관계): https://llm-study-web.vercel.app/topic/model-capacity
- RAG Pipeline (프롬프트 + 검색의 결합): https://llm-study-web.vercel.app/topic/rag-pipeline

ㅇ 연관된 이전 글

- Mac Mini RAG 구축기: https://peterica.tistory.com/1064
- 엣지 RAG의 AI 도구 지도 (v4 JSON 프롬프트 설계): https://peterica.tistory.com/1068
