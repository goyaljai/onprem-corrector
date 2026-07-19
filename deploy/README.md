# Deploying onprem-corrector (Docker · Kubernetes · GCP · AWS · Azure)

Env-driven, model-server-agnostic. The corrector talks to any **OpenAI-compatible vLLM** endpoint,
so moving clouds changes config, not code. **Model weights are never baked into an image and never
shipped in this repo** — you provide them at run time (mount a directory, or let vLLM pull from
Hugging Face).

## What you need
- A host/node with an **NVIDIA GPU** (≥1× A100/H100-class for Nemotron-Nano-9B) + drivers.
- **NVIDIA Container Toolkit** (Docker) or the **NVIDIA device plugin** (Kubernetes).
- The model weights — a local directory (mount) or Hugging Face access (pull).

## Two containers
1. **vLLM** (`vllm/vllm-openai`) — serves your model on `:8000`, OpenAI-compatible.
2. **corrector** (this repo's `deploy/Dockerfile`) — the FastAPI API on `:5244`, calls vLLM by service name.

## Option A — Docker Compose (single host), weights mounted (default)
```bash
MODEL_PATH=/abs/path/to/nemotron-nano-9b-v2 \
  docker compose -f deploy/docker-compose.yml up --build
# corrector → http://localhost:5244 · vLLM → http://localhost:8000
# 2 GPUs?  add  TP=2 GPUS=2
```

## Option B — no local weights (fresh cloud box): pull from Hugging Face at runtime
Point vLLM at a HF repo instead of mounting a path (downloads on first start; needs egress and, for
gated models, an `HF_TOKEN`):
```yaml
# deploy/docker-compose.hf.yml (overlay)
services:
  vllm:
    command: >
      --model <org/model> --served-model-name ${MODEL_NAME}
      --trust-remote-code --max-model-len 16384 --port 8000
    volumes: []
    environment: { HUGGING_FACE_HUB_TOKEN: "${HF_TOKEN}" }
```
```bash
HF_TOKEN=hf_xxx docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.hf.yml up
```

## Per-cloud instance recipes (then run Option A or B)
| Cloud | Instance | GPU | Notes |
|---|---|---|---|
| **GCP** | `a2-highgpu-1g` / `a3-highgpu` | A100 / H100 | Deep Learning VM image ships the toolkit; attach an SSD for weights |
| **AWS** | `g5.*` (A10G) / `p5.*` (H100) | A10G / H100 | DLAMI has drivers + toolkit; stage weights on instance store or EBS |
| **Azure** | `NC A100 v4` / `ND H100 v5` | A100 / H100 | NVIDIA GPU-Optimized image; mount a data disk for weights |
| **Bare metal / on-prem** | any NVIDIA box | A100/H100/L40S | install the Container Toolkit; this is the primary target |

On each: ensure the toolkit is present (preinstalled on the images above), put the weights on a fast
disk (or use Option B), then `docker compose up`.

## Option C — Kubernetes
`deploy/k8s/corrector.yaml` — Deployments + Services for `vllm` and `corrector`, a ConfigMap, and a
`model-weights` PVC. Requires a **GPU node pool** + the **NVIDIA device plugin**.
```bash
# 1) preload the model-weights PVC out-of-band, OR switch the vllm volume to the
#    HF-pull initContainer variant (commented in the manifest).
# 2) build + push the corrector image to your registry, set it in the manifest:
docker build -f deploy/Dockerfile -t <registry>/corrector:latest . && docker push <registry>/corrector:latest
kubectl apply -f deploy/k8s/corrector.yaml
kubectl port-forward svc/corrector 5244:5244
```

## Reaching it from another container (e.g. your app/bridge)
A container's `127.0.0.1` is its own loopback, not the host. If your app runs in a *separate*
container and the corrector is on the host, reach it via `host.docker.internal` and add
`extra_hosts: ["host.docker.internal:host-gateway"]` to your app's service. If both are in the same
compose project, just use the service name: `http://corrector:5244`.

## Verify (any option)
```bash
curl -s localhost:5244/healthz
curl -s -X POST localhost:5244/v1/policy/upload --data-binary @../sample/sop-handbook.md
curl -s -X POST localhost:5244/v1/corrector/analyze -H 'Content-Type: application/json' \
  -d '{"agent_utterance":"the late fee is 500 rupees","context":"..."}'
```

## Appendix — GCP GPU VM host setup from scratch (verified on 2× L4, Debian 13)

A bare GCP GPU VM has the GPU but **no driver, no Docker, no toolkit**. Do this once, then run
Option A/B above. (Verified on a `g2` VM with 2× NVIDIA L4, Debian 13 / trixie.)

```bash
# 0) confirm the GPU is attached (works even with no driver)
lspci | grep -i nvidia                       # -> NVIDIA ... [L4]  (×2)

# 1) NVIDIA driver — Debian 13 keeps apt components in deb822 format
sudo sed -i '/^Components:/ s/$/ contrib non-free non-free-firmware/' /etc/apt/sources.list.d/debian.sources
sudo apt-get update
sudo apt-get install -y linux-headers-cloud-amd64 build-essential dkms nvidia-driver nvidia-smi gnupg
sudo modprobe nvidia && nvidia-smi           # -> 2× NVIDIA L4, driver 550.x

# 2) Docker + NVIDIA Container Toolkit (so a container can see the GPU)
sudo apt-get install -y docker.io && sudo systemctl enable --now docker
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
sudo docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi -L   # must list both GPUs
```

**Gotchas:** Debian 13 uses `/etc/apt/sources.list.d/debian.sources` (deb822) — edit that to add
`contrib non-free`; a minimal image lacks `gpg` (install `gnupg`); a container's CUDA must be **≤**
the host driver's CUDA (driver 550 → CUDA 12.4).

## Notes
- **No secrets in the repo or the image.** The vLLM `api_key` is a literal `"dummy"` (it points at your box). An optional `HF_TOKEN` is passed via env, never committed.
- **Weights are yours to supply.** This repo documents *how*; it never ships or downloads them for you.
