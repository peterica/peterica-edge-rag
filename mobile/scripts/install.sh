#!/usr/bin/env bash
# APK 설치 (기기 연결 필수)
# Usage: ./scripts/install.sh [--clean]

set -e
cd "$(dirname "$0")/.."
source scripts/env.sh

check_device

if [ ! -f "$APK_PATH" ]; then
    log_warn "APK 없음. 빌드부터 실행합니다..."
    ./gradlew assembleDebug
fi

if [ "$1" = "--clean" ]; then
    log_info "기존 앱 제거 중..."
    adb uninstall "$PKG" 2>/dev/null || log_warn "제거할 앱 없음"
fi

log_info "설치 중... (~200MB, 1-2분 소요)"
adb install -r "$APK_PATH"
log_info "설치 완료"
