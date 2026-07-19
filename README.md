# onprem-corrector

**A self-hosted, no-leak compliance corrector for AI agents.** It watches an agent (voice or chat)
on a live conversation and flags — or fixes — when the agent breaks *your* policy: contradicts the
SOP, misses a mandatory disclosure, states a wrong fact, or uses prohibited language. Everything runs
**on your own hardware** — the customer transcript and your policy documents **never leave your
premises**.

> Built for regulated, data-resident deployments (DPDP, RBI, HIPAA, PCI-DSS). If your compliance or
> legal team won't let customer data round-trip to a US cloud LLM, this is the supervisor layer that
> keeps it in-house.

---

## Why on-prem

| | Cloud LLM "moderation" | **onprem-corrector** |
|---|---|---|
| Where the transcript goes | a third-party US API | **stays on your box** |
| Where your policy goes | uploaded to the vendor | **stays on your box** |
| Model | someone else's, opaque | **your own** (Nemotron / any vLLM-served model) |
| Grounding | the model's opinion | **your uploaded SOP** (RAG) |
| Egress | outbound to `api.openai.com` | **none** — talks only to a local vLLM |

It speaks the **OpenAI wire format** to a local **vLLM** endpoint — so "openai" is the protocol, not
the destination. `grep` the code: there is no `api.openai.com`.

## How it works — two lanes + an honest gate

```
POST /v1/corrector/analyze  { agent_utterance, context, prior_agent_claims? }
        │
        ├─ Instant lane  (deterministic, sub-ms, no LLM)
        │     prohibited-phrase hit · missing required disclosure   → source A
        │
        └─ RAG-judge lane  (your model via vLLM, one structured call)
              retrieve the relevant SOP passage, then classify:
              A policy contradiction · B self-contradiction (quoted) · C tone
        │
        └─ Gate:  deterministic-A → auto ·
                  LLM-derived A / B → auto ONLY if quoted + confidence ≥ 0.8, else propose ·
                  C → propose ·  < 0.5 → drop
```

It is **verdict-only**: it returns severity + a correction candidate; *your* app decides whether to
speak, display, or ignore. It never auto-acts on an unverified model judgment.

## Quickstart (Docker Compose)

You need a host with an NVIDIA GPU + the NVIDIA Container Toolkit, and the model weights on disk.

```bash
git clone https://github.com/goyaljai/onprem-corrector && cd onprem-corrector
MODEL_PATH=/abs/path/to/your-model docker compose -f deploy/docker-compose.yml up --build
# corrector API → http://localhost:5244   (vLLM → :8000)
```

No policy uploaded? It **auto-loads a bundled sample SOP** so the API works out-of-the-box. Then:

```bash
# check
curl localhost:5244/healthz

# ground it in YOUR policy (a markdown SOP) — replaces the default
curl -X POST localhost:5244/v1/policy/upload --data-binary @your-sop.md

# judge one agent utterance
curl -X POST localhost:5244/v1/corrector/analyze -H 'Content-Type: application/json' \
  -d '{"agent_utterance":"the late fee is 500 rupees","context":"Worker: the late fee is 500 rupees"}'
```

## API

| Endpoint | What it does |
|---|---|
| `GET /healthz` | liveness + identity (served model + policy version) |
| `POST /v1/policy/upload` | index a policy/SOP markdown (RAG + extract prohibited phrases & disclosures) |
| `POST /v1/corrector/analyze` | judge one agent utterance → `{observations, corrections[], rubric_projection}` |
| `GET /v1/policy/anchors` | the SOP-derived disclosure anchors (for an external identity/compliance check to reuse) |

Full request/response shapes: [`docs/API.md`](docs/API.md) *(see `deploy/README.md` for the contract)*.

## Deploy anywhere

Env-driven and model-server-agnostic — moving clouds changes config, not code. See
[`deploy/README.md`](deploy/README.md) for **Docker Compose, Kubernetes, and GCP / AWS / Azure**
recipes. Weights are **mounted or pulled at runtime, never baked into the image**.

## Bring your own policy

Any markdown SOP works. Mark **prohibited phrases** and **required disclosures** under the obvious
headings; add `| keywords: a, b, c` after a disclosure bullet to anchor it. See
[`sample/sop-handbook.md`](sample/sop-handbook.md) and the `packs/` (bank · hospital · IT) for
worked examples.

## Tests

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python scripts/test_judge_confidence.py            # GPU-free unit test
BASE=http://localhost:5244 python scripts/test_suite.py      # live acceptance (needs a running server)
BASE=http://localhost:5244 SOP=packs/bank.md TR=packs/bank.json python scripts/test_domain.py  # adversarial
```

## Stack

NeMo Guardrails · Chroma (local embeddings) · Nemotron-Nano-9B (or any vLLM-served model) · FastAPI.

## License

[MIT](LICENSE) © 2026 Jai Goyal.
