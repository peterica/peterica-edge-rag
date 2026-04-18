#!/usr/bin/env bash
# 공통 환경 변수 — 모든 스크립트에서 source로 로드
# Usage: source "$(dirname "$0")/env.sh"

export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"

PKG="com.peterica.edgerag"
APK_PATH="app/build/outputs/apk/debug/app-debug.apk"
ACTIVITY="$PKG/.MainActivity"

# 색상 (로그 가독성)
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

check_device() {
    local devices
    devices=$(adb devices | tail -n +2 | grep -v "^$" | wc -l | tr -d ' ')
    if [ "$devices" -eq 0 ]; then
        log_error "폰이 연결되지 않았습니다. USB 디버깅을 확인하세요."
        log_info "adb devices 로 연결 상태 확인 가능합니다."
        exit 1
    fi
    log_info "연결된 기기: $(adb devices | tail -n +2 | grep -v '^$' | awk '{print $1}')"
}
