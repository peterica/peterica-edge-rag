# 개발 스크립트

Android Studio 없이 커맨드라인으로 빌드 → 설치 → 디버깅.

## 사전 준비

### 1. 환경 변수 (이미 env.sh에서 자동 설정됨)

```bash
export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH=$ANDROID_HOME/platform-tools:$PATH
```

### 2. Galaxy S23 Ultra USB 디버깅 활성화

1. 설정 → 휴대전화 정보 → 소프트웨어 정보
2. "빌드 번호" 7번 연속 탭 → 개발자 모드 활성화
3. 설정 → 개발자 옵션 → "USB 디버깅" 켜기
4. USB 연결 → 폰에서 "USB 디버깅 허용" 팝업 → 허용

## 스크립트 목록

| 스크립트 | 용도 |
|---------|------|
| `env.sh` | 공통 환경 변수 (다른 스크립트에서 source) |
| `build.sh` | APK 빌드만 (기기 불필요) |
| `install.sh` | APK 설치 (`--clean`: 기존 앱 제거 후 설치) |
| `run.sh` | 빌드 → 설치 → 실행 → logcat 스트리밍 (원클릭) |
| `logcat.sh` | 앱 로그만 스트리밍 (`--error` / `--tag`) |
| `device.sh` | 기기 정보 + 앱 상태 점검 |

## 일반 워크플로우

### 최초 실행

```bash
cd mobile
./scripts/device.sh       # 기기 연결 확인
./scripts/run.sh --clean  # 빌드 + 설치 + 실행
```

### 코드 수정 후 반복

```bash
./scripts/run.sh          # 자동 재빌드 + 재설치 + 실행
```

### 디버깅

```bash
# 앱은 이미 실행 중인 상태에서
./scripts/logcat.sh            # 전체 앱 로그
./scripts/logcat.sh --error    # 에러/경고만
```

## 트러블슈팅

### `adb devices`가 비어있음

- USB 디버깅 확인
- USB 케이블이 데이터 전송 지원인지 확인 (충전 전용 케이블은 안 됨)
- 폰의 "USB 디버깅 허용" 팝업 확인
- `adb kill-server && adb start-server` 재시작

### 설치 실패 (INSTALL_FAILED_UPDATE_INCOMPATIBLE)

```bash
./scripts/install.sh --clean  # 기존 앱 제거 후 설치
```

### 앱 크래시

```bash
./scripts/logcat.sh --error
```

로그에서 `AndroidRuntime` 관련 스택트레이스 확인.
