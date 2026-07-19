# API

Base URL: `http://<host>:${API_PORT:-5244}`. Stateless; JSON in/out. On error the service returns a
well-formed empty body (or a 4xx/5xx) — it never crashes the caller.

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
