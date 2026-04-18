#!/usr/bin/env bash
# 앱 logcat만 스트리밍 (앱이 이미 실행 중일 때)
# Usage:
#   ./scripts/logcat.sh          # 기본: 앱 프로세스 로그
#   ./scripts/logcat.sh --error  # 에러만
#   ./scripts/logcat.sh --tag    # EdgeRag 태그만

set -e
cd "$(dirname "$0")/.."
source scripts/env.sh

check_device

PID=$(adb shell pidof -s "$PKG" 2>/dev/null || echo "")

case "${1:-}" in
    --error)
        log_info "에러/경고만 스트리밍"
        if [ -n "$PID" ]; then
            adb logcat --pid="$PID" -v time *:W
        else
            adb logcat -v time AndroidRuntime:E "$PKG:W" "*:S"
        fi
        ;;
    --tag)
        log_info "EdgeRag 태그만 스트리밍"
        adb logcat -v time "EdgeRag:*" "*:S"
        ;;
    *)
        if [ -z "$PID" ]; then
            log_warn "앱 실행 중 아님. 전체 로그 스트리밍"
            adb logcat -v time
        else
            log_info "앱 로그 스트리밍 (PID=$PID)"
            adb logcat --pid="$PID" -v time
        fi
        ;;
esac
