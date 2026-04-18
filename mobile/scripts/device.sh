#!/usr/bin/env bash
# 기기 정보 + 앱 상태 점검
# Usage: ./scripts/device.sh

set -e
cd "$(dirname "$0")/.."
source scripts/env.sh

log_info "기기 목록:"
adb devices
echo ""

check_device

log_info "기기 정보:"
echo "  모델: $(adb shell getprop ro.product.model)"
echo "  Android: $(adb shell getprop ro.build.version.release) (API $(adb shell getprop ro.build.version.sdk))"
echo "  SoC: $(adb shell getprop ro.board.platform)"
echo ""

log_info "앱 설치 상태:"
if adb shell pm list packages | grep -q "$PKG"; then
    VERSION=$(adb shell dumpsys package "$PKG" | grep versionName | head -1 | awk -F= '{print $2}')
    echo "  설치됨 (버전: $VERSION)"

    PID=$(adb shell pidof -s "$PKG" 2>/dev/null || echo "")
    if [ -n "$PID" ]; then
        echo "  실행 중 (PID: $PID)"
    else
        echo "  미실행"
    fi
else
    log_warn "앱 미설치 — ./scripts/install.sh 로 설치"
fi
echo ""

log_info "메모리 상태:"
adb shell cat /proc/meminfo | head -3
