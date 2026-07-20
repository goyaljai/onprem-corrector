# API

Base URL: `http://<host>:${API_PORT:-5244}`. Stateless; JSON in/out. On error the service returns a
well-formed empty body (or a 4xx/5xx) — it never crashes the caller.

**Explore it live:** interactive **Swagger UI** at [`/docs`](/docs), **ReDoc** at [`/redoc`](/redoc), and
the machine-readable spec at [`/openapi.json`](/openapi.json) (endpoints grouped by tag: `compliance`,
`policy`, `audit`, `ops`). Disable with `DOCS_ENABLED=false` for locked-down deployments.

**Auth (issue #2).** If `API_KEYS` / `ADMIN_API_KEY` are configured, send `X-API-Key: <key>`.
Roles: **caller** → `POST /v1/corrector/analyze`, `GET /v1/policy/anchors`; **admin** (⊇ caller) →
`POST /v1/policy/upload`, `GET /v1/audit*`. Responses: `401` missing/invalid key, `403` valid key but
wrong role, `429` rate-limited, `503` if `AUTH_REQUIRED=true` but no keys set. `GET /healthz` is always
open (liveness). No keys configured ⇒ **open mode** (loud startup warning).

## `GET /healthz`
```json
{ "status": "ok", "vllm": true, "model": "nemotron-nano-9b-v2",
  "policy_version": "v1784388408", "nemo_guardrails": true }
```

## `POST /v1/policy/upload`
Index a policy/SOP markdown into the RAG store (replaces the current policy).
- **Body:** raw markdown (`Content-Type: text/plain`).
- **Response:** `{ "policy_version", "chunks_indexed", "prohibited_phrases", "required_disclosures" }`

The uploader extracts, for the deterministic instant lane: bullets under a heading matching
`/prohibit|banned|never say/i` (prohibited phrases) and `/required|mandatory|must (state|disclose)/i`
(required disclosures; optional `| keywords: a, b, c` suffix per bullet).

## `POST /v1/corrector/analyze`
Judge one agent utterance against the indexed policy.

**Request**
```json
{
  "agent_utterance": "the late fee is 500 rupees, that's 5 percent of your balance",
  "context": "Worker: My name is Priya from Meridian Bank...\nCustomer: why a late fee?",
  "prior_agent_claims": "Worker (earlier): refund within 7 working days",
  "top_k": 4
}
```

**Response**
```json
{
  "observations": [ { "id", "category", "severity" (1-5), "observation", "evidence" } ],
  "corrections": [
    {
      "source": "A" | "B" | "C",              // A=policy/compliance, B=self-contradiction, C=tone
      "strategy": "compliance_narration" | "apologize_correct" | "hedge" | "hold_to_verify" | "empathy_repair",
      "confidence": 0.0,                        // 0..1
      "severity": "low" | "medium" | "high",
      "reason": "…",
      "quote_said": "…" | null,
      "quote_correct": "…" | null,
      "cited_policy": "…" | null,
      "suggested_line": "…" | null,
      "gate": "auto" | "propose" | "drop"       // auto = deterministic; else LLM-derived
    }
  ],
  "rubric_projection": { "empathy", "de_escalation", "resolution", "clarity" (0-10), "overall_score" } | null,
  "meta": { "latency_ms", "model", "policy_version", "lanes": ["instant","rag_judge"] }
}
```

**Gate semantics** — deterministic-A → `auto`; LLM-derived A and B → `auto` only with both quotes AND
confidence ≥ 0.8, else `propose`; C → `propose`; below 0.5 → `drop`. It is **verdict-only**: your app
decides whether to act.

## `GET /v1/policy/anchors`
Expose the SOP-derived disclosure **anchors** (read-only, no LLM) so an external identity/compliance
check can consume policy-grounded signals instead of a hardcoded phrase list.
```json
{ "policy_version": "v…",
  "disclosures": [ { "text": "Identity: …", "anchors": ["acme bank", "my name is", "this is"] } ],
  "prohibited_phrases": ["tell me your otp"] }
```

## Default policy
If nothing has been uploaded, the service **auto-loads a bundled sample SOP** on startup, so
`/analyze` and `/anchors` work out-of-the-box. `POST /v1/policy/upload` replaces it.

## Audit trail (tamper-evident)
Every `analyze` verdict, `policy_upload`, and `input_block` is written to an **append-only,
hash-chained** log (`sha256(prev_hash + record)`), verifiable **offline**. Transcripts are scrubbed
per `AUDIT_STORE_MODE` (`redacted` default · `hashed` · `full`); retention prunes whole old segments
(`AUDIT_RETENTION_DAYS`). The read endpoints below require the `X-API-Key` header matching
`AUDIT_API_KEY` — **if that env is unset the audit read API returns 403** (safe default).

### `GET /v1/audit?limit=&event=&since_seq=`
Recent audit records (newest-trimmed to `limit`). `event` ∈ `analyze|policy_upload|input_block`.
```json
{ "records": [ {
  "seq": 12, "ts": "2026-07-19T15:30:00.123Z", "event": "analyze",
  "policy_version": "v-default-…", "model": "nemotron-nano-9b-v2",
  "lanes": ["instant","rag_judge"], "latency_ms": 2296,
  "input": { "utterance": "the late fee is [REDACTED:…]", "sha256": "…64hex…" },
  "corrections": [ { "source": "A", "gate": "auto", "confidence": 1.0, "reason": "…" } ],
  "outcome": { "n_corrections": 1, "sources": ["A"], "gates": {"auto":1}, "blocked": false },
  "prev_hash": "…64hex…", "hash": "…64hex…" } ] }
```

### `GET /v1/audit/verify`
Recompute the whole retained chain → integrity proof.
```json
{ "ok": true, "checked": 12, "first_seq": 1, "last_seq": 12, "head_hash": "…", "pruned": null }
// on tampering: { "ok": false, "broken_at": 7, "reason": "content altered", "checked": 6 }
```

### `GET /v1/audit/stats`
`{ "records", "last_seq", "by_event", "by_gate", "by_source", "pruned" }` — feeds a compliance dashboard.
