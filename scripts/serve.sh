#!/usr/bin/env bash
# Start the policy-guardrail API (assumes vLLM is already serving on :8000).
set -e
cd "$(dirname "$0")/.."
export PATH=/cm/shared/apps/uv:$PATH
uv venv .venv --python 3.10 2>/dev/null || true
source .venv/bin/activate
uv pip install -q -r requirements.txt
export VLLM_BASE_URL=${VLLM_BASE_URL:-http://localhost:8000/v1}
export MODEL_NAME=${MODEL_NAME:-nemotron-nano-9b-v2}
export POLICY_DIR=${POLICY_DIR:-/raid/scratch/tmp/$USER/policy_store}
exec uvicorn app.main:app --host 0.0.0.0 --port ${API_PORT:-5244}
