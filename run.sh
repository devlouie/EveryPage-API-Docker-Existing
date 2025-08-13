#!/usr/bin/env bash
set -euo pipefail

# Simple local Docker runner for EveryPage (stateless ResetData version)

IMAGE_NAME="everypage-pure:local"
CONTAINER_NAME="everypage-pure"
PORT="8000"

echo "[1/4] Checking Docker..."
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed or not on PATH." >&2
  exit 1
fi

echo "[2/4] Building image: ${IMAGE_NAME}"
docker build -t "${IMAGE_NAME}" .

echo "[3/4] Removing any existing container: ${CONTAINER_NAME}"
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
fi

echo "[4/4] Running container on port ${PORT}"
docker run -d \
  --name "${CONTAINER_NAME}" \
  -p "${PORT}:8000" \
  -e MAX_WORKERS="5" \
  -e PROCESS_TIMEOUT="90" \
  --restart unless-stopped \
  "${IMAGE_NAME}"

echo
echo "EveryPage is running at: http://localhost:${PORT}"
echo
echo "Usage examples (requires your ResetData key):"
echo "  1) Health check:"
echo "     curl -s -H 'x-resetdata-key: YOUR_RESETDATA_KEY' http://localhost:${PORT}/health | jq ."
echo
echo "  2) Process a document synchronously (returns final result):"
echo "     curl -s -X POST http://localhost:${PORT}/scan \\" 
echo "       -H 'x-resetdata-key: YOUR_RESETDATA_KEY' \\" 
echo "       -F 'file=@/absolute/path/to/document.pdf' \\" 
echo "       -F 'user_prompt=Convert this page to Markdown' \\" 
echo "       -F 'output_format=json' \\" 
echo "       -F 'use_meta_intelligence=false' | jq ."
echo
echo "Notes:"
echo "- Replace YOUR_RESETDATA_KEY with a valid token from ResetData."
echo "- No server-managed API key is required; the ResetData key is validated per request."
echo "- If you don't have jq installed, omit the '| jq .' part."
echo

