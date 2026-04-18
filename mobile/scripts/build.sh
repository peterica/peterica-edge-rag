#!/usr/bin/env bash
# Gradle 디버그 빌드
# Usage: ./scripts/build.sh

set -e
cd "$(dirname "$0")/.."
source scripts/env.sh

log_info "Gradle 빌드 시작..."
./gradlew assembleDebug

if [ -f "$APK_PATH" ]; then
    SIZE=$(du -h "$APK_PATH" | cut -f1)
    log_info "빌드 완료: $APK_PATH ($SIZE)"
else
    log_error "APK 생성 실패"
    exit 1
fi
