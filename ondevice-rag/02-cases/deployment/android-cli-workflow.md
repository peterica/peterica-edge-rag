# Android CLI 개발 — Gradle · ADB · Logcat만으로 완주하기

ㅁ 들어가며

서버 개발자는 터미널에서 산다.
그런데 Android 앱을 만든다고 하면 보통 **Android Studio부터 깔자**는 이야기가 돌아온다.

꼭 그래야 하나.
빌드·설치·로그만 있으면 앱은 돌아간다.
그리고 이 세 가지는 모두 **커맨드라인 도구**에 있다.

이 글은 Android Studio 없이 앱을 만드는 실전 경로를 정리한다.
DevOps에 익숙한 엔지니어가 첫 Android 프로젝트에 접근할 때 가장 짧은 길이기도 하다.

---

ㅁ 필요한 것은 다섯 가지

Android 개발에 필수인 도구는 의외로 적다.

| 도구 | 용할 |
|---|---|
| **JDK 17+** | Gradle·Android 빌드 런타임 |
| **Android SDK** | platform, build-tools, 플랫폼 JAR |
| **platform-tools (adb)** | 기기 연결·설치·로그 |
| **Gradle 8.x** | 빌드 오케스트레이션 |
| **터미널·에디터** | (IDE 아님) |

설치도 단순하다. macOS 기준.

```bash
brew install --cask android-commandlinetools
brew install --cask android-platform-tools
brew install openjdk@17 gradle
```

환경 변수 한 줄.

```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
```

**이게 전부다.** 추가로 받을 SDK 플랫폼·빌드툴은 Gradle이 알아서 다운로드한다.

---

ㅁ 커맨드라인 워크플로우 4단계

ㅇ 1. 프로젝트 세팅

Gradle 기반 Android 프로젝트는 표준 파일 세 개면 시작된다.

```
mobile/
├── settings.gradle.kts   # 프로젝트 모듈 선언
├── build.gradle.kts      # 루트 빌드 설정 (plugin 선언)
├── gradle.properties     # JVM args, AndroidX 설정
└── app/
    ├── build.gradle.kts              # 앱 모듈 빌드
    └── src/main/
        ├── AndroidManifest.xml
        ├── java/com/peterica/edgerag/MainActivity.kt
        └── res/values/themes.xml
```

`local.properties`에 SDK 경로만 적어두면 이식성까지 확보된다.

```
sdk.dir=/Users/<name>/Library/Android/sdk
```

ㅇ 2. Gradle wrapper 생성 (1회)

시스템 Gradle 대신 **프로젝트 전용 Gradle**을 고정한다. 재현성 확보가 목적.

```bash
cd mobile
gradle wrapper --gradle-version 8.11.1
```

이후 빌드는 `gradle` 대신 `./gradlew`를 쓴다.
팀이 다른 기기에서 빌드해도 같은 Gradle 버전이 보장된다.

ㅇ 3. 디버그 APK 빌드

한 줄이다.

```bash
./gradlew assembleDebug
```

첫 빌드는 플랫폼·빌드툴 다운로드가 섞여 2~3분 걸린다.
이후 캐시된 빌드는 수십 초.
산출물은 `app/build/outputs/apk/debug/app-debug.apk`.

ㅇ 4. 설치 + 실행 + 로그

기기 연결 확인, 설치, 실행, 로그 — 각각 한 줄.

```bash
adb devices                                         # 기기 목록
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.peterica.edgerag/.MainActivity
adb logcat --pid=$(adb shell pidof -s com.peterica.edgerag)
```

이 네 줄이 **Android Studio의 "Run" 버튼**과 동일한 일을 한다.

---

ㅁ 개발 스크립트로 묶기

매번 저 네 줄을 치지 않는다.
**한 번의 명령으로 끝나도록** 셸 스크립트로 묶는다.

| 스크립트 | 하는 일 |
|---|---|
| `device.sh` | 기기 연결 + 모델·API 레벨·메모리 표시 |
| `build.sh` | `./gradlew assembleDebug` 감싼 빌드 |
| `install.sh` | `adb install -r`. `--clean`이면 uninstall 후 |
| `run.sh` | 빌드→설치→앱 기동→`logcat --pid` 스트리밍 (원클릭) |
| `logcat.sh` | 앱 프로세스만 / `--error` / `--tag` 옵션 |
| `serve-apk.sh` | ADB 불가 환경 대비, APK HTTP 서빙 + 폰에서 다운로드 |

전체 개발 사이클이 이렇게 단순해진다.

```bash
./scripts/device.sh       # 기기 확인
./scripts/run.sh          # 빌드 + 설치 + 실행 + 로그
./scripts/logcat.sh --error   # 에러만 필터
```

`run.sh` 하나면 코드 수정 → 재빌드 → 재설치 → 로그까지 **한 흐름**으로 끝난다.
IDE의 "Run" 버튼과 다른 점은 **과정이 전부 보인다**는 것뿐이다.

---

ㅁ 짚어볼 것들

ㅇ Android Studio가 필요한 순간은 따로 있다

IDE 없이 못 하는 건 **레이아웃 미리보기**와 **APK Analyzer**다.
Compose 프리뷰는 `@Preview`를 쓰려면 IDE 렌더링 엔진이 필요하다.
단, 실기 기기 테스트로 대체 가능하다.
APK 내부 구조 분석(dex 분포, 리소스 크기)은 IDE의 분석 도구가 편하지만, CLI로 `apkanalyzer`라는 별도 도구가 있다.

→ IDE의 **시각화 기능**이 필요한 순간에만 켜면 된다. 항상 띄울 이유는 없다.

ㅇ Gradle wrapper의 재현성 가치

시스템 Gradle 버전이 각자 다르면 빌드 결과도 미세하게 달라질 수 있다.
wrapper는 **프로젝트가 자기 Gradle 버전을 포함**하는 구조라, CI·협업·재현 빌드에 결정적이다.
한 번 생성하면 `gradle/wrapper/` 폴더와 `./gradlew` 스크립트가 생기고, 이후 모두가 이걸 쓴다.

→ 팀 프로젝트가 아니어도 **미래의 나를 위해** wrapper부터 만든다.

ㅇ 의존성 충돌 디버깅은 CLI가 오히려 편하다

Gradle 의존성 트리는 `./gradlew app:dependencies`로 평문 출력된다.
충돌·중복 JAR은 `./gradlew app:dependencyInsight --dependency <이름>`으로 추적한다.
IDE의 GUI 트리뷰보다 **grep·less와 섞어 쓸 수 있는 평문**이 종종 더 빠르다.

→ 서버 로그 분석 습관이 그대로 **빌드 디버깅에도 작동**한다.

ㅇ 도구 선택은 "익숙함"이 아니라 "문제"가 한다

Android Studio는 GUI 중심 워크플로우에 최적화된 도구다.
모바일 UI·레이아웃을 **시각적으로 설계**하는 작업이라면 IDE가 빠르다.
하지만 서버처럼 **빌드→배포→로그 사이클**만 돌리는 작업에는 CLI가 더 자연스럽다.

→ 익숙한 도구를 새 문제에 억지로 맞추지 말고, 문제의 성질에 맞는 도구를 쓴다.
Android Studio는 **필수가 아니라 선택**이다.

---

ㅁ 마무리

도구는 익숙함이 만드는 것이 아니다.
**문제가 도구를 선택**한다.

서버에서 터미널로 일하던 엔지니어가 모바일에서도 같은 흐름을 쓸 수 있다는 건, 그만큼 Android 생태계가 **CLI 친화적으로 성숙했다**는 뜻이기도 하다.

→ 도구의 경계는 우리가 만든 것이지, 기술이 만든 것이 아니다.

---

ㅁ 함께 보면 좋은 사이트

ㅇ 공식 도구
- Android Command Line Tools: https://developer.android.com/tools/sdkmanager
- ADB Reference: https://developer.android.com/tools/adb
- Gradle User Guide: https://docs.gradle.org/current/userguide/userguide.html
- apkanalyzer: https://developer.android.com/tools/apkanalyzer

ㅇ 더 공부하기 — LLM System Lab
- LLM 시스템 학습 트랙: https://llm-study-web.vercel.app/learn

ㅇ 시리즈
- Mac Mini RAG 구축기: https://peterica.tistory.com/1064
- sqlite-vec 선택 이유: https://peterica.tistory.com/1065
- 맥미니 RAG를 넘어서 — 모바일 온디바이스 AI를 시작하다: https://peterica.tistory.com/1066
- 3트랙 병렬 리서치 — 쓰기 전에 물어봐야 하는 것들: https://peterica.tistory.com/1067
- 엣지 RAG의 AI 도구 지도 — 왜 Python이 접합점인가: https://peterica.tistory.com/1068
- 448MB가 113MB 되는 길 — ONNX INT8 양자화 실전: https://peterica.tistory.com/1069
