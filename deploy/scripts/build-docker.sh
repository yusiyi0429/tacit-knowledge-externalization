#!/usr/bin/env bash
# 构建 linux/amd64 和/或 linux/arm64 镜像并导出离线 tar
# 用法:
#   bash deploy/scripts/build-docker.sh amd64
#   bash deploy/scripts/build-docker.sh arm64
#   bash deploy/scripts/build-docker.sh all
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ARCH="${1:-all}"
case "$ARCH" in
  amd64|x86_64|x86)
    bash "$SCRIPT_DIR/build-docker-amd64.sh"
    ;;
  arm64|aarch64|arm)
    bash "$SCRIPT_DIR/build-docker-arm64.sh"
    ;;
  all|both)
    bash "$SCRIPT_DIR/build-docker-amd64.sh"
    bash "$SCRIPT_DIR/build-docker-arm64.sh"
    ;;
  *)
    echo "用法: $0 {amd64|arm64|all}"
    exit 1
    ;;
esac
