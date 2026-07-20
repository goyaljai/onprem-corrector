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

## Option A — Docker Compose (single host), zero-prep (DEFAULT)
Clone → up. vLLM **pulls the model from Hugging Face** on first start (Nemotron-Nano-9B is ungated —
no token) and caches it; `tensor-parallel-size` **auto-detects your GPU count** (1 GPU → TP=1,
2 GPUs → TP=2, unchanged). Nothing to stage.
```bash
# 1) build the corrector image with the CLASSIC builder (works on stock docker.io — no buildx needed)
docker build -f deploy/Dockerfile -t onprem-corrector:latest .
# 2) bring the stack up; vLLM pulls the model on first start, corrector reuses the image above
docker compose -f deploy/docker-compose.yml up -d
# corrector → http://localhost:5244 · vLLM → http://localhost:8000
# first `up` downloads ~17GB of weights (cached in the `hfcache` volume for next time)
```
> Stock Debian `docker.io` ships neither the compose v2 plugin nor a recent buildx. Install the
> compose plugin once (see the host-setup appendix), and pre-build with `docker build` as above to
> sidestep the buildx requirement.
Knobs (all optional): `MODEL_ID` (HF repo), `MODEL_NAME` (served id), `MAX_LEN`, `TP` (pin instead of
auto-detect), `HF_TOKEN` (only for *gated* models).

## Option B — air-gapped / offline: mount weights you already have (zero egress)
No network path to Hugging Face? Stage the weights on disk and mount them — the model layer makes
**no outbound connection at all**:
```bash
MODEL_PATH=/abs/path/to/weights \
  docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.mount.yml up
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

## Security (issue #2) — lock it down for production

Turnkey-open by default (zero-config demo), hard by configuration. Four layers:

**1. API auth (role-based keys).** Set keys and the sensitive endpoints require `X-API-Key`.
**Put them in `deploy/.env`, not an inline shell prefix** — an inline `VAR=val docker compose
up` only applies to *that one command*; any later `docker compose up` (even one that only
targets a different service, like re-recreating Caddy) re-reads the compose file against
whatever's in your shell right then, and can silently recreate the corrector **without** the
keys, reverting it to open mode with no error. A `.env` file is picked up automatically by
every `docker compose` invocation, so the keys can't be dropped by a later command:
```bash
printf "API_KEYS=caller-key\nADMIN_API_KEY=admin-key\n" > deploy/.env
docker compose -f deploy/docker-compose.yml up -d
# /v1/corrector/analyze  -> any caller/admin key   (401 without)
# /v1/policy/upload, /v1/audit* -> admin key only  (403 with a caller key)
```
`AUTH_REQUIRED=true` refuses all traffic unless a key is configured+sent. `RATE_LIMIT_PER_MIN=N`
caps per-identity request rate. With no keys set the API is **open** and logs a loud startup warning.

**2. Enforced zero-egress.** Make "no data leaves" a control, not a promise:
- **k8s:** `kubectl apply -f deploy/k8s/networkpolicy.yaml` (default-deny egress; allow only DNS + vLLM).
- **docker:** add the internal-network overlay — the corrector gets no route to the internet:
  ```bash
  docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.locked.yml up -d
  docker compose exec corrector python scripts/egress_check.py   # -> LOCKED DOWN
  ```

**3. TLS.** The app itself speaks plain HTTP, so **by default its port is bound to
`127.0.0.1` only** (same-host access works; the network cannot reach it in plaintext). For
network access, terminate TLS with the bundled Caddy overlay instead of widening that bind:
```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.tls.yml up -d
curl -sk https://localhost:8443/healthz     # -k: self-signed cert by default
```
Self-signed out of the box (`deploy/Caddyfile`, `tls internal`) — Caddy mints the cert from
its **own offline local CA**, no internet call, which keeps the zero-egress story intact. The
Caddyfile names the host explicitly (`localhost:8443`) rather than a bare `:8443` — a hostless
address makes Caddy treat cert issuance as on-demand-per-SNI, which it refuses without extra
config, and every handshake fails with a TLS `internal_error` alert. If clients reach this box
by a different hostname or IP, add it as another comma-separated address in `deploy/Caddyfile`.

Have a public domain pointed at this box? Swap in `deploy/Caddyfile.acme.example` for a real,
publicly-trusted Let's Encrypt cert (that path *does* call out to Let's Encrypt — a deliberate,
opt-in exception, not the default). Only set `BIND_HOST=0.0.0.0` if you deliberately want the
plaintext port network-reachable (e.g. you're terminating TLS somewhere else upstream).

**How a client actually calls it, end to end:**
```
your app/service  ──HTTPS (X-API-Key)──▶  Caddy :8443 (TLS termination, self-signed or ACME)
                                              │  reverse_proxy, same docker network
                                              ▼
                                        corrector :5244 (plaintext, loopback-only —
                                        unreachable from the network directly)
```
```python
import requests
requests.post("https://<host>:8443/v1/corrector/analyze",
               headers={"X-API-Key": "caller-key"},
               json={"agent_utterance": "...", "context": "..."},
               verify=False)   # self-signed: verify=False, OR pin/import Caddy's local root CA
                                # (copy it out: docker cp deploy-caddy-1:/data/caddy/pki/authorities/local/root.crt .)
```
For a real (publicly-trusted) cert instead of `verify=False`, use the ACME/Let's Encrypt path
above — then standard TLS verification just works, no special client config needed.

**4. Supply chain.** Generate a CycloneDX SBOM and scan it; sign the image:
```bash
docker compose exec corrector python scripts/gen_sbom.py > sbom.json   # then: grype sbom:sbom.json
cosign sign <registry>/onprem-corrector:latest                          # provenance for the image
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

# 3) Docker Compose v2 plugin (docker.io does NOT ship it) — install system-wide
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -sSL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
sudo docker compose version                  # -> Docker Compose version v2.x
```

**Gotchas:** Debian 13 uses `/etc/apt/sources.list.d/debian.sources` (deb822) — edit that to add
`contrib non-free`; a minimal image lacks `gpg` (install `gnupg`); a container's CUDA must be **≤**
the host driver's CUDA (driver 550 → CUDA 12.4).

## Notes
- **No secrets in the repo or the image.** The vLLM `api_key` is a literal `"dummy"` (it points at your box). An optional `HF_TOKEN` is passed via env, never committed.
- **Weights are yours to supply.** This repo documents *how*; it never ships or downloads them for you.
