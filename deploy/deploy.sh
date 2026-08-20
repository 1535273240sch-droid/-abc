#!/usr/bin/env bash
set -eo pipefail

PROJECT_ROOT="/root/abc-project"
BACKEND_DIR="${PROJECT_ROOT}/backend"
VENV_PYTHON="${BACKEND_DIR}/.venv/bin/python3"
VENV_PYTEST="${BACKEND_DIR}/.venv/bin/pytest"
HEALTH_URL="http://127.0.0.1:8000/health"

echo "=================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Enterprise Quant Deployment..."
echo "=================================================="

cd "${PROJECT_ROOT}"

# 1. Pre-deployment sanity tests
echo "==> Running pre-deployment validation tests..."
if [ -f "${VENV_PYTEST}" ]; then
    "${VENV_PYTEST}" "${BACKEND_DIR}/tests/test_fixes.py" "${BACKEND_DIR}/tests/test_persistence.py" -q
    echo "? Sanity tests passed."
else
    echo "? Virtual environment pytest not found, skipping pre-test."
fi

# 2. Restart backend service gracefully
echo "==> Restarting quant systemd service..."
systemctl restart quant

# 3. Post-deployment health verification
echo "==> Verifying service health..."
MAX_RETRIES=10
RETRY_COUNT=0
HEALTHY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    sleep 1
    if curl -s -f "${HEALTH_URL}" > /dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for service to become healthy... (${RETRY_COUNT}/${MAX_RETRIES})"
done

if [ "$HEALTHY" = true ]; then
    echo "? Health check passed at ${HEALTH_URL}"
    echo "=================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Deployment completed successfully!"
    echo "=================================================="
    exit 0
else
    echo "? ERROR: Service failed health check after restart!" >&2
    systemctl status quant --no-pager >&2
    exit 1
fi
