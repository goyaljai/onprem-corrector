"""On-prem Policy-Compliance Guardrail API (generic, no-leak).

  POST /v1/policy/upload      -> index a policy/SOP .md into Chroma (RAG)
  POST /v1/corrector/analyze  -> judge one agent utterance -> corrections (verdict-only)
  GET  /healthz               -> liveness + vLLM reachability

Stack: NeMo Guardrails (orchestration + input rail) -> Chroma RAG (local embeddings)
-> Nemotron on vLLM (the judge). Talks ONLY to the local vLLM endpoint — no external
egress, which is the whole point (data residency).
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import time
import uuid
import zipfile

from fastapi import FastAPI, Request, Header, HTTPException, Query, Depends
from openai import OpenAI

from .schema import AnalyzeRequest, AnalyzeResponse, Observation, UploadResponse
from . import rag_index
from .rules import instant_lane, disclosure_anchors
from .judge import judge
from .audit import get_audit
from .auth import require, startup_notice, auth_configured

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "nemotron-nano-9b-v2")
POLICY_DIR = os.environ.get("POLICY_DIR", "./policy_store")
GUARDRAILS_DIR = os.path.join(os.path.dirname(__file__), "guardrails")
DOCS_ENABLED = os.environ.get("DOCS_ENABLED", "true").lower() != "false"

# --- OpenAPI / Swagger surface (issue #4): self-describing API, grouped by tag ---------
TAGS = [
    {"name": "compliance", "description": "Judge an agent utterance against the indexed policy (A/B/C verdicts, verdict-only)."},
    {"name": "policy", "description": "Manage the grounding policy/SOP and its derived anchors."},
    {"name": "audit", "description": "Tamper-evident audit trail — query, integrity verification, and stats (key-gated)."},
    {"name": "ops", "description": "Liveness and operational endpoints."},
]
app = FastAPI(
    title="On-prem Policy-Compliance Guardrail",
    version="0.2.0",
    description=(
        "A self-hosted, **zero-egress** compliance corrector for AI/human agents. Detects "
        "policy breaches (A), self-contradiction (B), and tone misses (C), grounded in *your* "
        "uploaded SOP, talking only to a **local** vLLM. Every decision is written to a "
        "**tamper-evident audit trail**.\n\n"
        "Explore live below, or fetch the machine spec at `/openapi.json`."
    ),
    openapi_tags=TAGS,
    contact={"name": "onprem-corrector", "url": "https://github.com/goyaljai/onprem-corrector"},
    license_info={"name": "MIT"},
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url="/redoc" if DOCS_ENABLED else None,
)
client = OpenAI(base_url=VLLM_BASE_URL, api_key="dummy")


def _corr_dicts(corrections) -> list:
    """Normalise Correction models (or dicts) to plain dicts for the audit record."""
    out = []
    for c in corrections:
        out.append(c.model_dump() if hasattr(c, "model_dump") else dict(c))
    return out

# NeMo Guardrails is loaded lazily/optionally so the service still runs if the
# rails config can't initialise — the deterministic input gate below is authoritative.
_rails = None
# Detect prompt-injection / jailbreak against the auditor + leaked CREDENTIAL VALUES.
# Deliberately does NOT match bare topical mentions ("never share your password", "your
# password is important") — only credential *assignments with a token-like value* and
# explicit injection verbs — so normal banking/clinical/support speech is never blocked.
# (Validated offline: blocks all adversarial injection/secret cases, 0 false positives.)
_SECRET_RE = re.compile(
    r"("
    r"ignore (all |the |your |previous )*(instruction|rule|prompt|polic|guideline|compliance)"
    r"|disregard (all |the |your |previous )*(instruction|rule|prompt|polic|guideline|compliance)"
    r"|forget (all |your |previous )*(instruction|rule)"
    r"|override (the |your )*(rule|polic|compliance|guardrail|instruction)"
    r"|you are now|act as (an?|the)|pretend (to|you)|system prompt|jailbreak"
    r"|do ?n[o']?t (flag|report|log|record|mention) (this|it|that|the)"
    r"|mark (this|the|it|his|her|their) .{0,25}(compliant|settled|approved|resolved|clean)"
    r"|sk-[A-Za-z0-9-]{12,}|ghp_[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{16,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{12,}|eyJ[A-Za-z0-9_-]{18,}\."
    r"|bearer\s+[A-Za-z0-9._-]{16,}"
    r"|(password|passwd|pwd|api[_ -]?key|secret|token|credential)s?\s*(is|are|:|=)\s*['\"]?(?=\S*[0-9!@#$%^&_\-])\S{6,}"
    r")", re.I)


def _get_rails():
    global _rails
    if _rails is None:
        try:
            from nemoguardrails import RailsConfig, LLMRails
            cfg = RailsConfig.from_path(GUARDRAILS_DIR)
            _rails = LLMRails(cfg)
            _rails.register_action(lambda query: rag_index.retrieve(query, 4), "retrieve_policy")
        except Exception as e:  # noqa
            _rails = False
            app.state.rails_error = str(e)
    return _rails


def _has_secrets(text: str) -> bool:
    return bool(_SECRET_RE.search(text or ""))


@app.on_event("startup")
def _startup():
    rag_index.init_store(POLICY_DIR)
    # DEFAULT POLICY: if nothing has been uploaded yet, index the bundled bank SOP so the
    # corrector is usable out-of-the-box — any consumer can call /v1/corrector/analyze with no
    # prior /v1/policy/upload. Uploading a new handbook/SOP simply replaces this default.
    try:
        _ver = rag_index.load_policy_meta().get("version")
        if not _ver or _ver == "none":   # empty index reports the string "none", not None
            default_sop = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample", "sop-handbook.md")
            if os.path.exists(default_sop):
                with open(default_sop, encoding="utf-8") as f:
                    rag_index.index_handbook(f.read(), f"v-default-{int(time.time())}")
    except Exception:
        pass  # never block startup on the default-load
    get_audit()      # initialise the audit chain (loads/creates _chain.json)
    startup_notice() # loud warning if the API is unauthenticated
    _get_rails()     # warm it


@app.get("/healthz", tags=["ops"], summary="Liveness + vLLM reachability + policy version")
def healthz():
    ok = True
    try:
        client.models.list()
    except Exception:
        ok = False
    meta = rag_index.load_policy_meta()
    return {"status": "ok" if ok else "degraded", "vllm": ok, "model": MODEL_NAME,
            "policy_version": meta.get("version"), "nemo_guardrails": bool(_get_rails())}


@app.post("/v1/policy/upload", response_model=UploadResponse, tags=["policy"],
          summary="Index a policy/SOP markdown (replaces the current policy) — admin only")
async def upload_policy(request: Request, _auth=Depends(require("admin"))):
    # Accept the raw policy markdown as the request body (text/plain OR application/json string).
    raw = (await request.body()).decode("utf-8")
    if raw[:1] == '"' and raw[-1:] == '"':  # tolerate a JSON-quoted string too
        try:
            import json as _json
            raw = _json.loads(raw)
        except Exception:
            pass
    prev = rag_index.load_policy_meta().get("version")
    version = f"v{int(time.time())}"
    n, prohibited, disclosures = rag_index.index_handbook(raw, version)
    # AUDIT: a policy change is a compliance-relevant event. Record version transition +
    # a hash of the policy body (not the body itself) so the change is provable, not bulky.
    get_audit().record("policy_upload", policy_version=version, model=MODEL_NAME,
                       extra={"prev_version": prev, "policy_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                              "chunks": n, "prohibited": len(prohibited), "disclosures": len(disclosures)})
    return UploadResponse(policy_version=version, chunks_indexed=n,
                          prohibited_phrases=len(prohibited), required_disclosures=len(disclosures))


@app.get("/v1/policy/anchors", tags=["policy"],
         summary="SOP-derived disclosure anchors + prohibited phrases (read-only, no LLM)")
def policy_anchors(_auth=Depends(require("caller"))):
    """Expose the SOP-derived disclosure ANCHORS (#35) so an external compliance check —
    e.g. the voice-copilot C1 identity matcher — can consume policy-grounded signals instead
    of a hardcoded phrase list. Read-only; no LLM. The anchors are exactly what the instant
    lane matches on, so C1 stays consistent with the corrector."""
    meta = rag_index.load_policy_meta()
    return {
        "policy_version": meta.get("version"),
        "disclosures": [
            {"text": d.get("text", ""), "anchors": disclosure_anchors(d)}
            for d in meta.get("disclosures", [])
        ],
        "prohibited_phrases": meta.get("prohibited", []),
    }


# ---- multi-document policy corpus (#5) ----
@app.post("/v1/policy/documents", response_model=UploadResponse, tags=["policy"],
          summary="Add/replace ONE named policy document (leaves other docs intact) — admin")
async def upsert_document(request: Request, name: str = Query(..., description="document name/id"),
                          _auth=Depends(require("admin"))):
    raw = (await request.body()).decode("utf-8")
    prev = rag_index.load_policy_meta().get("version")
    n, prohibited, disclosures = rag_index.index_document(name, raw)
    ver = rag_index.load_policy_meta().get("version")
    get_audit().record("policy_upload", policy_version=ver, model=MODEL_NAME,
                       extra={"prev_version": prev, "document": name,
                              "policy_sha256": hashlib.sha256(raw.encode()).hexdigest(), "chunks": n})
    return UploadResponse(policy_version=ver, chunks_indexed=n,
                          prohibited_phrases=len(prohibited), required_disclosures=len(disclosures))


@app.get("/v1/policy/documents", tags=["policy"], summary="List documents in the policy corpus")
def list_documents(_auth=Depends(require("caller"))):
    return {"policy_version": rag_index.load_policy_meta().get("version"),
            "documents": rag_index.list_documents()}


@app.delete("/v1/policy/documents/{name}", tags=["policy"],
            summary="Delete one document from the corpus — admin")
def delete_document(name: str, _auth=Depends(require("admin"))):
    if not rag_index.delete_document(name):
        raise HTTPException(status_code=404, detail=f"No such document: {name}")
    ver = rag_index.load_policy_meta().get("version")
    get_audit().record("policy_upload", policy_version=ver, model=MODEL_NAME,
                       extra={"deleted_document": name})
    return {"deleted": name, "policy_version": ver}


@app.post("/v1/policy/bulk", tags=["policy"],
          summary="Bulk-load a ZIP of .md documents (convert-everything-to-md) — admin")
async def bulk_upload(request: Request, _auth=Depends(require("admin"))):
    raw = await request.body()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Body must be a ZIP archive of .md files.")
    # DoS guards: bound entry count + per-entry and total DECOMPRESSED size (zip-bomb defense).
    MAX_ENTRIES, MAX_ENTRY, MAX_TOTAL = 500, 5_000_000, 50_000_000
    loaded, skipped, seen, total = [], [], set(), 0
    for info in zf.infolist():
        if info.is_dir() or not info.filename.lower().endswith((".md", ".markdown", ".txt")):
            continue
        if len(loaded) >= MAX_ENTRIES:
            skipped.append({"file": info.filename, "reason": "entry cap"}); continue
        if info.file_size > MAX_ENTRY or total + info.file_size > MAX_TOTAL:
            skipped.append({"file": info.filename, "reason": "size cap"}); continue
        # key on the sanitized FULL path (not basename) so security/x.md and refunds/x.md
        # don't collide and silently overwrite each other.
        doc = os.path.splitext(info.filename)[0].strip("/").replace("/", "__").replace("\\", "__")
        if doc in seen:
            skipped.append({"file": info.filename, "reason": "duplicate name"}); continue
        seen.add(doc)
        total += info.file_size
        n, _p, _d = rag_index.index_document(doc, zf.read(info).decode("utf-8", errors="replace"))
        loaded.append({"name": doc, "chunks": n})
    ver = rag_index.load_policy_meta().get("version")
    get_audit().record("policy_upload", policy_version=ver, model=MODEL_NAME,
                       extra={"bulk": True, "documents": [d["name"] for d in loaded], "skipped": len(skipped)})
    return {"policy_version": ver, "loaded": loaded, "skipped": skipped, "count": len(loaded)}


@app.post("/v1/corrector/analyze", response_model=AnalyzeResponse, tags=["compliance"],
          summary="Judge one agent utterance → corrections[] (A/B/C, verdict-only)")
def analyze(req: AnalyzeRequest, _auth=Depends(require("caller"))):
    t0 = time.time()
    meta = rag_index.load_policy_meta()

    # 1. input guardrail (deterministic fast path). Screen the utterance AND the context/
    # prior — both flow into the judge prompt, so an injection/secret there must be caught too.
    if _has_secrets(req.agent_utterance) or _has_secrets(req.context) or _has_secrets(req.prior_agent_claims or ""):
        latency = int((time.time()-t0)*1000)
        # store_mode="hashed": we KNOW this input carries a secret — never persist it in clear,
        # even under AUDIT_STORE_MODE=redacted/full (the redactor is not a perfect net).
        get_audit().record("input_block", policy_version=meta.get("version"), model=MODEL_NAME,
                           lanes=["input_guard"], latency_ms=latency,
                           utterance=req.agent_utterance, context=req.context,
                           prior=req.prior_agent_claims or "", extra={"blocked": True},
                           store_mode="hashed")
        return AnalyzeResponse(
            observations=[Observation(id=f"blk_{uuid.uuid4().hex[:6]}", category="input_guardrail",
                                      severity=3, observation="Input blocked by guardrail (possible secret/injection).",
                                      evidence=None)],
            corrections=[], rubric_projection=None,
            meta={"latency_ms": latency, "model": MODEL_NAME,
                  "policy_version": meta.get("version"), "lanes": ["input_guard"], "blocked": True})

    # 2. instant lane (deterministic, no LLM)
    corrections = instant_lane(req.agent_utterance, req.context, meta)

    # 3. RAG + LLM judge lane (on-prem Nemotron)
    lanes = ["instant"]
    judge_error = None
    try:
        # Retrieve policy using the LINE BEING JUDGED (not the whole transcript) so the
        # relevant rule isn't buried under greetings/customer chatter -> avoids silent misses.
        chunks = rag_index.retrieve(req.agent_utterance, req.top_k)
        corrections += judge(client, MODEL_NAME, req.agent_utterance, req.context,
                             req.prior_agent_claims or "", chunks)
        lanes.append("rag_judge")
    except Exception as e:  # never crash the caller's call — return what we have
        judge_error = str(e)

    latency = int((time.time()-t0)*1000)
    # AUDIT: persist the verdict to the tamper-evident chain BEFORE returning, so no decision
    # is ever unrecorded. Transcripts are scrubbed per AUDIT_STORE_MODE inside the audit layer.
    get_audit().record("analyze", policy_version=meta.get("version"), model=MODEL_NAME,
                       lanes=lanes, latency_ms=latency,
                       utterance=req.agent_utterance, context=req.context,
                       prior=req.prior_agent_claims or "", corrections=_corr_dicts(corrections))

    return AnalyzeResponse(
        observations=[], corrections=corrections, rubric_projection=None,
        meta={"latency_ms": latency, "model": MODEL_NAME,
              "policy_version": meta.get("version"), "lanes": lanes,
              "judge_error": judge_error})


# ------------------------------------------------------------------- audit trail (#1)
@app.get("/v1/audit", tags=["audit"], summary="Query recent audit records — admin only")
def audit_query(limit: int = Query(50, ge=1, le=1000), event: str | None = None,
                since_seq: int = 0, _auth=Depends(require("admin"))):
    return {"records": get_audit().query(limit=limit, event=event, since_seq=since_seq)}


@app.get("/v1/audit/verify", tags=["audit"],
         summary="Recompute the hash chain → integrity proof (ok / broken_at) — admin only")
def audit_verify(_auth=Depends(require("admin"))):
    return get_audit().verify()


@app.get("/v1/audit/stats", tags=["audit"], summary="Aggregate counts by event / gate / source — admin only")
def audit_stats(_auth=Depends(require("admin"))):
    return get_audit().stats()
