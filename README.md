<div align="center">

# 🛡️ onprem-corrector

### Your data stays sovereign. Your agents stay compliant.

**A self-hosted, zero-egress compliance corrector for AI (and human) agents.** It listens on a live
conversation and catches — or fixes — the moment an agent breaks **your** policy. Runs entirely on
**your** hardware, on **your** model, grounded in **your** SOP. The customer transcript and your
policy documents **never leave your premises.**

![data](https://img.shields.io/badge/data-sovereign-blueviolet) ![egress](https://img.shields.io/badge/egress-none-brightgreen) ![license](https://img.shields.io/badge/license-MIT-green) ![python](https://img.shields.io/badge/python-3.10+-blue) ![deploy](https://img.shields.io/badge/deploy-Docker%20%C2%B7%20K8s%20%C2%B7%20GCP%2FAWS%2FAzure-orange)

</div>

---

## 🌐 Data sovereignty first

This exists because **your customer data is yours** — it should not have to leave your building to be
monitored. Regulators increasingly *require* it (India's **DPDP**, **RBI** data-localisation, **HIPAA**,
**PCI-DSS**, the EU **AI Act**), and it's simply good practice: the transcripts of your customers'
worst moments should not become another company's training data.

> *"Firms ought to be capable of cost-effectively building tailored models and leveraging proprietary
> data, **while preventing that data from leaving their systems.** It can't be that there are only two
> companies in the world with token capital, and everybody else is renting it."*
> — **Satya Nadella**, CEO, Microsoft

onprem-corrector is exactly that for the compliance/supervisor layer: **a tailored model on your own
hardware, grounded in your own policy, with nothing leaving your systems.**

## What is this?

Every AI voice/chat agent on a regulated call — banking, healthcare, insurance, telecom, support —
can quietly say the wrong thing: quote the wrong fee, skip a mandatory disclosure, contradict itself,
or leak/solicit a credential. **onprem-corrector is the independent supervisor that watches for
exactly that**, grounded in *your* Standard Operating Procedure, and returns a structured verdict your
app can act on in real time.

The catch with the obvious alternative — piping every transcript to a cloud "moderation" LLM — is
**data residency**. Under DPDP / RBI / HIPAA / PCI-DSS you often *cannot* let customer data round-trip
to a third-party US API. This is the piece that keeps it in-house: **your model, your box, your data.**

## Why it's different

| | Cloud LLM moderation | **onprem-corrector** |
|---|---|---|
| Customer transcript | → a third-party US API | **stays on your box** |
| Your policy | uploaded to the vendor | **stays on your box** |
| The model | someone else's, opaque | **your own** (Nemotron, Llama, Qwen… any vLLM model) |
| Grounding | the model's opinion | **your uploaded SOP** (retrieval-augmented) |
| Network egress | outbound to `api.openai.com` | **none** — talks only to a local vLLM |
| Trust model | "trust the vendor" | auditable: `grep` the code, watch the egress |

It speaks the **OpenAI wire format** to a *local* vLLM endpoint — "openai" is the protocol, not the
destination. There is no `api.openai.com` anywhere.

## Architecture

```mermaid
flowchart LR
  A["your agent app<br/>(voice / chat)"] -->|POST /v1/corrector/analyze| C
  subgraph BOX["your infrastructure — nothing leaves"]
    subgraph C["onprem-corrector (FastAPI)"]
      G["NeMo Guardrails<br/>input rail"] --> I["Instant lane<br/>(deterministic, sub-ms)"]
      G --> J["RAG-judge<br/>(retrieve SOP → classify)"]
      I --> GATE["honest gate<br/>auto / propose / drop"]
      J --> GATE
    end
    P[("your SOP<br/>(Chroma RAG)")] --- J
    V["vLLM<br/>your model on your GPU"] --- J
  end
  GATE -->|corrections[]| A
```

**Two lanes, one honest gate:**
- **Instant lane** — deterministic, sub-millisecond, no LLM: prohibited-phrase hits + missing required
  disclosures → **source A**.
- **RAG-judge** — one structured call to *your* model: retrieve the relevant SOP passage, then classify
  a policy contradiction (**A**), a self-contradiction with quotes (**B**), or a tone miss (**C**).
- **Gate** — deterministic-A auto-fires; an LLM judgment auto-fires *only* when it's quoted and
  high-confidence, otherwise it's `propose` (a human/your-app confirms). It **never** auto-acts on an
  unverified model guess. **Verdict-only** — you decide whether to speak, display, or log.

## What we built (highlights)

- 🔒 **Zero-egress by design** — customer data + policy stay local; only a local vLLM is called.
- 📚 **Policy-grounded, not vibes** — every verdict is retrieved from *your* uploaded SOP (RAG), with a citation.
- ⚡ **Two-speed detection** — sub-ms deterministic rules + a single grounded LLM call; the gate keeps LLM guesses honest.
- 🧯 **Safe by construction** — verdict-only, confidence-gated, quote-required for auto-actions; graceful degradation (bounded inputs, per-finding isolation) so one bad response never sinks the batch.
- 🧾 **Tamper-evident audit trail** — every verdict/policy-change is hash-chained (append-only), PII-redacted, retention-configurable, and verifiable **offline** (`GET /v1/audit/verify` pin-points any tampering). Compliance evidence, not a promise.
- 📖 **Self-describing API** — interactive Swagger UI at `/docs`, ReDoc at `/redoc`, spec at `/openapi.json`.
- 📦 **Runs out-of-the-box** — ships a default sample SOP and auto-loads it, so `/analyze` works before you upload anything.
- ☁️ **Deploy anywhere** — Docker Compose · Kubernetes · GCP / AWS / Azure recipes; weights mounted or pulled at runtime, never baked into an image; no secrets in the repo.
- ✅ **Proven** — bundled adversarial packs (bank · hospital · IT) with planted mistakes; a GPU-free unit test; verified end-to-end on H100.

## 60-second quickstart

Needs a host with an NVIDIA GPU + the NVIDIA Container Toolkit. **No weights to stage** — vLLM pulls
the (ungated) model from Hugging Face on first start and `tensor-parallel-size` auto-detects your GPU
count. Bare GPU VM? See [`deploy/README.md`](deploy/README.md) for the one-time host setup (driver +
Docker + toolkit), verified on a fresh GCP 2× L4 box.

```bash
git clone https://github.com/goyaljai/onprem-corrector && cd onprem-corrector
docker compose -f deploy/docker-compose.yml up --build      # pulls model on first run (~17GB, cached)
# corrector API → http://localhost:5244   (vLLM → :8000)

curl localhost:5244/healthz                                  # it's already serving a default SOP
```
Air-gapped? Mount local weights instead — see Option B in [`deploy/README.md`](deploy/README.md).

No GPU handy? You can still run the **GPU-free unit test** (`python scripts/test_judge_confidence.py`)
and read `docs/API.md`.

## Use it from your app — one HTTP call

Whatever your agent just said, POST it with the recent context:

```python
import requests
r = requests.post("http://localhost:5244/v1/corrector/analyze", json={
    "agent_utterance": "the late fee is 500 rupees, that's 5 percent of your balance",
    "context": "Worker: My name is Priya from Meridian Bank...\nCustomer: why a late fee?",
    "prior_agent_claims": "Worker (earlier): refund within 7 working days",  # for self-contradiction
})
for c in r.json()["corrections"]:
    # source A/B/C, gate = auto|propose|drop, quote_said/quote_correct, suggested_line
    if c["gate"] == "auto":
        speak(c["suggested_line"])     # your app decides — verdict-only
    else:
        show_to_supervisor(c)
```

```bash
curl -X POST localhost:5244/v1/corrector/analyze -H 'Content-Type: application/json' \
  -d '{"agent_utterance":"the late fee is 500 rupees","context":"Worker: the late fee is 500 rupees"}'
```

## 🔧 Make it yours — reuse for any use case

The service is **domain-agnostic**: it knows nothing hard-coded about banking. Everything comes from
the SOP you give it. To adapt it to *your* product:

1. **Write your SOP as markdown.** Put your rules under the obvious headings — mark **prohibited
   phrases** (`## Prohibited Phrases`) and **required disclosures** (`## Required Disclosures`, add
   `| keywords: a, b, c` to anchor each). See [`sample/sop-handbook.md`](sample/sop-handbook.md) and the
   worked [`packs/`](packs/) (bank · hospital · IT).
2. **Upload it** (replaces the default): `curl -X POST :5244/v1/policy/upload --data-binary @your-sop.md`
3. **Call `/v1/corrector/analyze`** from your agent loop with the latest line + context. Map the
   `corrections[]` onto your UI / voice / audit log (contract in [`docs/API.md`](docs/API.md)).
4. **Swap the model** if you like — point `VLLM_BASE_URL` at any OpenAI-compatible vLLM serving any
   model (Nemotron, Llama, Qwen, Mistral…). No code change.

That's it — **new domain = new SOP, not new code.** Healthcare intake, insurance mis-selling, telecom
KYC, IT-support MFA policy, legal disclaimers… if it has an SOP, it works.

## API (summary)

| Endpoint | What it does |
|---|---|
| `GET /healthz` | liveness + served model + policy version |
| `POST /v1/policy/upload` | index your SOP markdown (RAG + extract phrases/disclosures) |
| `POST /v1/corrector/analyze` | judge one utterance → `{observations, corrections[], rubric_projection}` |
| `GET /v1/policy/anchors` | SOP-derived disclosure anchors (reuse them in your own identity checks) |
| `GET /v1/audit` · `/verify` · `/stats` | tamper-evident audit trail — query, integrity proof, stats (key-gated) |
| `GET /docs` · `/redoc` · `/openapi.json` | interactive **Swagger UI** / ReDoc / machine spec — the API describes itself |

Full request/response shapes → [`docs/API.md`](docs/API.md), or just open **`/docs`** on a running instance.

## Deploy anywhere

Env-driven and model-server-agnostic — moving clouds changes config, not code. Docker Compose,
Kubernetes, and **GCP / AWS / Azure** recipes are in [`deploy/README.md`](deploy/README.md). Weights
are **never baked into the image** — mounted or pulled at runtime.

## Test it

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python scripts/test_judge_confidence.py                                    # GPU-free unit test
BASE=http://localhost:5244 python scripts/test_suite.py                    # live acceptance (10 cases)
BASE=http://localhost:5244 SOP=packs/bank.md TR=packs/bank.json python scripts/test_domain.py  # adversarial (10)
```

## Stack

NeMo Guardrails · Chroma (local ONNX embeddings) · Nemotron-Nano-9B / any vLLM-served model · FastAPI · Python 3.10+.

## License

[MIT](LICENSE) © 2026 Jai Goyal — use it, ship it, sell it. Contributions welcome.
