#!/usr/bin/env bash
# 빌드 → 설치 → 앱 실행 → logcat 스트리밍
# Usage: ./scripts/run.sh [--clean]

set -e
cd "$(dirname "$0")/.."
source scripts/env.sh

check_device

# 빌드
log_info "빌드 중..."
./gradlew assembleDebug

# 설치
if [ "$1" = "--clean" ]; then
    adb uninstall "$PKG" 2>/dev/null || true
fi
log_info "설치 중..."
adb install -r "$APK_PATH"

# logcat 클리어
adb logcat -c

# 앱 실행
log_info "앱 실행 중: $ACTIVITY"
adb shell am start -n "$ACTIVITY"

sleep 2

# logcat 스트리밍 (앱 프로세스만)
log_info "logcat 스트리밍 시작 (Ctrl+C로 종료)"
echo "----------------------------------------"
PID=$(adb shell pidof -s "$PKG" 2>/dev/null || echo "")
if [ -n "$PID" ]; then
    adb logcat --pid="$PID" -v time
else
    log_warn "앱 프로세스를 찾을 수 없음. 태그 기반 필터로 전환"
    adb logcat -v time "EdgeRag:*" "AndroidRuntime:E" "*:S"
fi
