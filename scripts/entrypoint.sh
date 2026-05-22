#!/bin/bash
# Tent OS 容器入口脚本
# 支持模式：all-in-one（默认）、worker <type>、server

set -e

MODE="${1:-all-in-one}"
CONFIG="${TENT_OS_CONFIG:-/app/config/tent_os.docker.yaml}"
DATA_DIR="${TENT_OS_DATA_DIR:-/app/data}"

echo "========================================"
echo "  Tent OS Container"
echo "  Mode: $MODE"
echo "  Config: $CONFIG"
echo "  Data Dir: $DATA_DIR"
echo "========================================"

# 确保数据目录存在
mkdir -p "$DATA_DIR"

# 等待 NATS 就绪（如果配置了 NATS）
NATS_URL="${TENT_OS_NATS_URL:-}"
if [ -n "$NATS_URL" ]; then
    # 从 nats://host:port 提取 host:port
    NATS_HOST=$(echo "$NATS_URL" | sed 's|nats://||')
    echo "Waiting for NATS at $NATS_HOST..."
    for i in {1..30}; do
        if nc -z "${NATS_HOST%%:*}" "${NATS_HOST##*:}" 2>/dev/null; then
            echo "NATS is ready"
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo "WARNING: NATS not available after 30s, continuing anyway..."
        fi
        sleep 1
    done
fi

case "$MODE" in
    all-in-one)
        echo "Starting Tent OS in all-in-one mode..."
        exec /usr/bin/supervisord -n -c /app/scripts/supervisord.conf
        ;;
    worker)
        WORKER_TYPE="${2:-}"
        if [ -z "$WORKER_TYPE" ]; then
            echo "Usage: worker <memory|governance|scheduler>"
            exit 1
        fi
        echo "Starting $WORKER_TYPE worker..."
        exec python -m tent_os.cli worker "$WORKER_TYPE" --config "$CONFIG"
        ;;
    server)
        echo "Starting API Server..."
        exec python -m tent_os.cli server --host 0.0.0.0 --port 8000 --config "$CONFIG"
        ;;
    run)
        echo "Starting Tent OS in single-process mode..."
        exec python -m tent_os.cli run --config "$CONFIG"
        ;;
    *)
        echo "Unknown mode: $MODE"
        echo "Usage: $0 {all-in-one|worker <type>|server|run}"
        exit 1
        ;;
esac
