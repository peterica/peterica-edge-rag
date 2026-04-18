#!/usr/bin/env bash
# APK를 HTTP로 서빙 — 폰 브라우저에서 다운로드 설치용
# Usage: ./scripts/serve-apk.sh [PORT]

set -e
cd "$(dirname "$0")/.."
source scripts/env.sh

PORT="${1:-8700}"

if [ ! -f "$APK_PATH" ]; then
    log_warn "APK 없음. 빌드부터..."
    ./gradlew assembleDebug
fi

# LAN IP 자동 감지
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "")

if [ -z "$LAN_IP" ]; then
    log_error "LAN IP를 찾을 수 없습니다."
    exit 1
fi

SIZE=$(du -h "$APK_PATH" | cut -f1)

echo ""
echo "================================================"
echo "  APK 배포 서버"
echo "================================================"
echo "  APK 크기  : $SIZE"
echo ""
echo "  폰에서 접속할 URL:"
echo ""
echo "    http://$LAN_IP:$PORT/app-debug.apk"
echo ""
echo "  (Safari/Chrome에서 위 URL 입력)"
echo "================================================"
echo ""
log_info "서버 시작 중... Ctrl+C로 종료"

# 서빙 디렉토리 설정
SERVE_DIR=$(mktemp -d)
cp "$APK_PATH" "$SERVE_DIR/app-debug.apk"
cd "$SERVE_DIR"

# Python HTTP 서버 기동 (바인드: 0.0.0.0)
python3 -m http.server "$PORT"
