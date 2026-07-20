# Corrector API image — the FastAPI service (NeMo Guardrails + Chroma RAG + Nemotron client).
# vLLM runs as a SEPARATE container (official vllm/vllm-openai image); this image NEVER bakes
# model weights (17GB+) — they are mounted into the vLLM container instead.
#
# Build context = the REPO ROOT (so it can COPY app/ + sample/ + requirements.txt):
#   docker build -f deploy/Dockerfile -t onprem-corrector:latest .
# (docker-compose sets context: .. so this is handled for you.)
FROM python:3.10-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# curl for the HEALTHCHECK; libgomp1 is REQUIRED by onnxruntime (chromadb's default
# MiniLM embedder) — python:3.10-slim omits it, so `import chromadb` would crash at runtime
# with "libgomp.so.1: cannot open shared object file".
RUN apt-get update && apt-get install -y --no-install-recommends curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app
COPY sample ./sample
# egress_check.py / gen_sbom.py / test_* usable via `docker exec` (no inline comment on COPY!)
COPY scripts ./scripts

# Config via env (see ../.env.example). In compose/k8s the corrector reaches vLLM by
# service name; POLICY_DIR is a mounted volume so the index survives restarts.
ENV VLLM_BASE_URL=http://vllm:8000/v1 \
    MODEL_NAME=nemotron-nano-9b-v2 \
    POLICY_DIR=/data/policy_store \
    AUDIT_DIR=/data/audit_store \
    API_PORT=5244

EXPOSE 5244
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -sf "http://localhost:${API_PORT}/healthz" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${API_PORT}"]
