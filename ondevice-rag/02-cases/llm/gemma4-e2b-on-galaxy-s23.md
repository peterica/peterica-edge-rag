# 갤럭시 S23 Gemma 4 테스트 — 온디바이스 LLM이 돌아간 기록

ㅁ 들어가며

이 프로젝트는 코드를 쓰기 전에 **사전 검증 단계**를 먼저 돌렸다.
세 트랙(모바일 LLM·임베딩·서버 파이프라인)을 병렬로 확인했고, 모두 "돌아간다"는 답이 나왔다 ([자세한 경과](https://peterica.tistory.com/1067)).
하지만 마지막 질문 하나가 남아 있었다.

**"S23 Ultra에서 Gemma 4 E2B가 정말 사람 쓸 만한 수준으로 돌까?"**

문서와 벤치마크로 "가능하다"는 답은 나왔다.
하지만 **응답 속도·한국어 품질·발열** 같은 건 실기에서만 드러난다.
이 글은 Galaxy S23 Ultra에서 Gemma 4 E2B를 실제로 돌려본 기록이다.

두 경로로 확인했다 — **AI Edge Gallery** (Google 공식 체험 앱)와 **LiteRT-LM 직접 연동** (자작 앱).
각각 다른 정보를 준다.

---

ㅁ AI Edge Gallery로 먼저 확인

ㅇ 가장 빠른 실기 경로

자작 앱을 만들기 전에, Google이 Play Store에 올린 `AI Edge Gallery` 앱으로 **즉시** 확인할 수 있다.

- Play Store 검색 → 설치
- 앱 내에서 `Gemma 4 E2B` 선택 → 모델 다운로드 (~2.5GB)
- 채팅 UI에서 바로 질문

이 경로의 장점은 **모델이 내 코드 문제로 안 돈다는 가능성을 차단**한다는 것.
Google 공식 앱에서 돌면 기기 자체는 OK라는 뜻이다.

ㅇ 한국어 DevOps 쿼리 4종 테스트

블로그 주제(DevOps·인프라)에 맞는 쿼리로 재봤다.
CPU backend 기준.

| # | 질문 | 응답 시간 | 품질 |
|---|---|---|---|
| 1 | Kubernetes의 Liveness Probe와 Readiness Probe 차이점 | **41.7s** | 한국어 정상, 개념 정확 |
| 2 | Prometheus pull 방식 메트릭 수집의 장단점 | **54.8s** | 긴 설명, 구조적 |
| 3 | RAG 시스템에서 임베딩 품질이 검색 결과에 미치는 영향 | **59.0s** | 전문 용어 정확 |
| 4 | 컨테이너 오케스트레이션에서 헬스 체크의 중요성 | **44.2s** | 실무 맥락 파악 |

**4/4 정상 응답.** 한국어 품질은 쓸 만했다.
다만 응답 시간은 **문장당 40~60초** — "대화형"보다는 "질의응답" 용도.

발열은 있었지만 쓰로틀링 단계까지는 안 갔다.
배터리는 쿼리 4개에 **약 3~5%** 감소.

---

ㅁ LiteRT-LM 직접 연동

Gallery 앱에서 돌아가는 건 확인했지만, **내 앱에 통합**하려면 직접 연동이 필요하다.

ㅇ Maven 의존성 한 줄

2026년 4월 기준, LiteRT-LM Android 라이브러리가 공식 Maven에 올라와 있다.

```kotlin
// app/build.gradle.kts
implementation("com.google.ai.edge.litertlm:litertlm-android:latest.release")
```

`latest.release`로 고정한 이유는 아직 초기 버전이라 패치가 자주 뜨기 때문.
프로덕션에서는 고정 버전으로 바꾸는 편이 안전하다.

ㅇ Kotlin 초기화 코드

```kotlin
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.Backend

val config = EngineConfig(
    modelPath = modelFile.absolutePath,
    backend = Backend.CPU(),   // GPU 이슈로 CPU 고정
)
val engine = Engine(config)
engine.initialize()   // ~10초 소요
```

초기화가 **약 10초** 걸린다.
앱 기동 시 `Dispatchers.IO` 코루틴으로 백그라운드에서 로드하고, UI는 `State.LOADING`을 표시한다.

ㅇ Backend.CPU()를 고른 이유

`Backend.GPU()` 옵션도 있지만 Snapdragon 8 Gen 2(SM8550)에서 **GPU delegate에 알려진 이슈**가 있어 초기화 실패 혹은 추론 오류가 관찰됐다.
CPU로도 12~20 tok/s가 나오기 때문에 실용에는 충분했다.
NPU 경로는 별도 SDK(Qualcomm AI Engine Direct)가 필요하고 범용성이 떨어져 이번에는 제외.

ㅇ 모델 파일 배치 — scoped storage의 함정

Android 11+ 의 **scoped storage** 정책 때문에 모델 파일 경로에 주의가 필요했다.

```
❌ context.getExternalFilesDir(...)   → native open()에서 PERMISSION_DENIED
✅ context.filesDir                    → 앱 내부 저장소, JNI open() 허용
```

외부 저장소는 **fuse mount**로 노출되는데, LiteRT-LM 같은 네이티브 코드가 직접 `open()`으로 접근하면 막힌다.
해결: 외부 저장소를 **스테이징**(adb push 편의)으로만 쓰고, 앱 시작 시 **internal filesDir로 복사**.

```kotlin
private fun ensureModelFile() {
    if (modelFile.exists()) return
    val src = stagingFile  // external
    if (!src.exists()) return
    src.copyTo(modelFile, overwrite = false)
    src.delete()
}
```

한 번 복사되면 끝. 이후 실행은 바로 internal에서 로드한다.

---

ㅁ 짚어볼 것들

ㅇ 이번 작업은 리서치와 본질적으로 다르다

사전 리서치는 "공식 문서 + 벤치마크"로 "가능하다"는 답을 냈다.
실기에서 드러난 것들은 전혀 다른 축이다.

- **GPU delegate 이슈** — 모델 연산을 GPU로 위임하는 경로가 Snapdragon 8 Gen 2에서 초기화 실패. 칩별 호환성 문제라 공식 문서에는 명시돼 있지 않다
- **Scoped storage의 native open 함정** — Android 11+의 저장소 정책이 네이티브 `open()`을 막아, 외부 저장소의 모델 파일을 내부 저장소로 복사해야 로드 가능
- **응답 시간 체감** — 공식 벤치마크의 tok/s 숫자보다, **한 쿼리를 기다리는 40초의 느낌**이 실사용을 결정한다
- **발열·배터리** — 쿼리 4개에 3~5% 배터리 소비. **얼마나 연속으로 쓸 수 있는가**는 숫자가 아닌 체감 영역

→ 리서치는 **"가능한가"** 를 답하고, 실기는 **"어떻게 쓸 만한가"** 를 답한다.
둘은 교체 불가능하다.

ㅇ GPU delegate 회피는 "일시 비용"인가 "지속 비용"인가
지금 CPU로 충분하지만, **미래의 모델이 더 커지면** GPU/NPU가 필요해질 것이다.
Snapdragon GPU delegate 이슈는 **언젠가 고쳐진다**.
그때까지는 CPU 경로가 "디폴트"로 유지된다.

→ **일시 비용이지만 지속될 수 있다.** 설계에서 "CPU 전용 경로"를 1급 시민으로 두는 게 안전하다.


ㅇ Scoped storage는 AI 배포의 새 변수다

전통적으로 파일 배포는 APK 내장이 기본이었다.
하지만 2.5GB 모델을 APK에 넣으면 Play Store 업로드 제한(150MB 초과 시 Dynamic Delivery 필수)에 걸린다.
결국 **런타임 다운로드 → internal filesDir 배치**가 유일한 경로.

→ AI 모델 배포는 **"설치"가 아니라 "다운로드 + 이동"** 이라는 두 단계 모델.
앱 설계 초반부터 이 흐름을 고려해야 한다.

---

ㅁ 마무리

Gemma 4 E2B가 내 S23 Ultra에서 40초에 답변을 내놓을 때, 한 가지 감정은 분명했다.
**주머니 속에서 LLM이 돈다는 것이 여전히 비현실처럼 느껴진다.**

2020년대 초만 해도 "서버 없이 LLM?"은 농담이었다.
몇 년 만에 **2.5GB 모델이 한국어 DevOps 질문에 답하는 시대**가 왔다.
이 변화는 앞으로 더 빨라질 것이다.

→ 엣지 AI는 "작은 버전의 서버 AI"가 아니라, **다른 사용 방식의 AI**다.
응답 속도·오프라인·프라이버시가 한 덩어리로 묶이는 새로운 UX 공간.

---

ㅁ 함께 보면 좋은 사이트

ㅇ 공식 도구
- Google AI Edge Gallery (Play Store에서 "Google AI Edge Gallery" 검색)
- Google AI Edge Gallery (GitHub): https://github.com/google-ai-edge/gallery
- LiteRT-LM Android: https://ai.google.dev/edge/litert-lm/android
- litert-community/gemma-4-E2B-it-litert-lm: https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm

ㅇ 더 공부하기 — LLM System Lab
- Quantization (모델 경량화): https://llm-study-web.vercel.app/topic/quantization
- Batching (추론 처리량 최적화): https://llm-study-web.vercel.app/topic/batching
- KV Cache (추론 속도의 핵심): https://llm-study-web.vercel.app/topic/kv-cache

ㅇ 시리즈
- Mac Mini RAG 구축기: https://peterica.tistory.com/1064
- sqlite-vec 선택 이유: https://peterica.tistory.com/1065
- 맥미니 RAG를 넘어서 — 모바일 온디바이스 AI를 시작하다: https://peterica.tistory.com/1066
- 3트랙 병렬 리서치 — 쓰기 전에 물어봐야 하는 것들: https://peterica.tistory.com/1067
- 엣지 RAG의 AI 도구 지도 — 왜 Python이 접합점인가: https://peterica.tistory.com/1068
- 448MB가 113MB 되는 길 — ONNX INT8 양자화 실전: https://peterica.tistory.com/1069
