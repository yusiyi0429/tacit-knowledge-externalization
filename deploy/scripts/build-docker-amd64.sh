#!/usr/bin/env bash
# 构建 linux/amd64 镜像并导出离线 tar（Linux/macOS）
# 脚本位于 deploy/scripts/，构建上下文为项目根目录
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

IMAGE_NAME="tacit-knowledge-externalization"
PLATFORM="linux/amd64"
PLATFORM_SLUG="amd64"
DATE_TAG="$(date +%Y%m%d-%H%M)"
UTC_NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

APP_VERSION="${APP_VERSION:-}"
if [[ -z "$APP_VERSION" && -f VERSION ]]; then
  APP_VERSION="$(grep -v '^#' VERSION | head -1 | tr -d '[:space:]')"
fi
[[ -n "$APP_VERSION" ]] || { echo "VERSION 为空"; exit 1; }

VERSION_TAG="${APP_VERSION}-${PLATFORM_SLUG}-${DATE_TAG}"
TAR_FILE="${DEPLOY_DIR}/${IMAGE_NAME}-${VERSION_TAG}.tar"
TAR_LATEST="${DEPLOY_DIR}/tacit-knowledge-externalization-amd64.tar"
MANIFEST="${DEPLOY_DIR}/${IMAGE_NAME}-${VERSION_TAG}.manifest.json"

echo "=== AMD64 镜像构建 ==="
echo "APP_VERSION=$APP_VERSION"
echo "IMAGE_TAG=$VERSION_TAG"

docker buildx build --platform "$PLATFORM" \
  --build-arg "APP_VERSION=$APP_VERSION" \
  --build-arg "IMAGE_VERSION=$VERSION_TAG" \
  --build-arg "BUILD_DATE=$UTC_NOW" \
  --build-arg "APP_PLATFORM=$PLATFORM" \
  -t "${IMAGE_NAME}:${VERSION_TAG}" \
  -t "${IMAGE_NAME}:${APP_VERSION}-amd64" \
  -f docker/Dockerfile \
  --load "$ROOT"

docker save -o "$TAR_FILE" \
  "${IMAGE_NAME}:${VERSION_TAG}" \
  "${IMAGE_NAME}:${APP_VERSION}-amd64"
cp -f "$TAR_FILE" "$TAR_LATEST"

cat > "$MANIFEST" <<EOF
{
  "app_name": "$IMAGE_NAME",
  "app_version": "$APP_VERSION",
  "image": "${IMAGE_NAME}:${VERSION_TAG}",
  "image_version": "$VERSION_TAG",
  "platform": "$PLATFORM",
  "built_at_utc": "$UTC_NOW",
  "tar_file": "$(basename "$TAR_FILE")",
  "compose_image_line": "image: ${IMAGE_NAME}:${VERSION_TAG}"
}
EOF

echo "完成: $TAR_FILE"
echo "清单: $MANIFEST"
