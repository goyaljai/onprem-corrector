"""LLM lane — the on-prem judge (replaces the OpenAI gpt-4o B/C detector).

One structured Nemotron call over the RETRIEVED policy context. `/no_think` keeps
the reasoning out of the output so we can parse strict JSON. Detects, grounded in
the policy:
  - policy_violation  -> source A (contradicts / unsupported-by / omits the SOP)
  - self_contradiction-> source B (contradicts the agent's OWN earlier words; needs both quotes)
  - tone              -> source C (robotic / missed strong emotion / overclaim)

100% on-prem: talks only to the local vLLM endpoint. No external egress.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import List

from openai import OpenAI

from .gate import compute_gate
from .schema import Correction

_KIND_SOURCE = {"policy_violation": "A", "self_contradiction": "B", "tone": "C"}
_VALID_STRATEGY = {"compliance_narration", "apologize_correct", "hedge", "hold_to_verify", "empathy_repair"}
_SEV = {"low", "medium", "high"}

SYS = "/no_think\nYou are a strict, terse call-compliance auditor. Output ONLY JSON."

PROMPT = """Judge the AGENT's latest line against the POLICY excerpts. Only flag issues you can ground in the policy or the transcript itself — do NOT invent external facts.

POLICY EXCERPTS:
{policy}

TRANSCRIPT (context):
{context}

AGENT'S OWN EARLIER STATEMENTS (for self-contradiction):
{prior}

AGENT'S LATEST LINE (judge this):
"{utterance}"

Return STRICT JSON, no prose:
{{"findings":[
  {{"kind":"policy_violation|self_contradiction|tone",
    "strategy":"compliance_narration|apologize_correct|hedge|hold_to_verify|empathy_repair",
    "severity":"low|medium|high",
    "confidence":0.0,
    "reason":"one sentence",
    "quote_said":"the agent's exact words or null",
    "quote_correct":"the correct version or null",
    "cited_policy":"the policy text this is grounded in or null",
    "suggested_line":"what the agent should say to fix it or null"}}
]}}
If nothing is wrong, return {{"findings":[]}}. For self_contradiction you MUST fill quote_said (agent's later words) and quote_correct (the earlier words), else do not emit it."""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"findings": []}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {"findings": []}


def _cap_tail(s: str, n: int) -> str:
    # keep the most-recent tail (latest turns matter most for a rolling window)
    return s if len(s) <= n else "…" + s[-n:]


def judge(client: OpenAI, model: str, utterance: str, context: str,
          prior_claims: str, policy_chunks: List[str]) -> List[Correction]:
    # Bound every input so the prompt always fits the model's context window.
    # Without this, a long transcript overflows max-model-len -> vLLM 400 -> the judge
    # lane silently no-ops (false negatives on long calls). Budgets are generous but hard.
    policy = ("\n---\n".join(policy_chunks))[:4000] if policy_chunks else "(no policy retrieved)"
    prompt = PROMPT.format(policy=policy,
                           context=_cap_tail(context, 6000) or "(none)",
                           prior=_cap_tail(prior_claims, 2000) or "(none)",
                           utterance=utterance[:2000])
    resp = client.chat.completions.create(
        model=model, temperature=0.0, max_tokens=700,
        messages=[{"role": "system", "content": SYS}, {"role": "user", "content": prompt}],
    )
    data = _extract_json(resp.choices[0].message.content or "")
    out: List[Correction] = []
    for f in data.get("findings", []):
        kind = f.get("kind")
        source = _KIND_SOURCE.get(kind)
        if not source:
            continue
        strategy = f.get("strategy")
        if strategy not in _VALID_STRATEGY:
            strategy = {"A": "compliance_narration", "B": "apologize_correct", "C": "hedge"}[source]
        sev = f.get("severity") if f.get("severity") in _SEV else "medium"
        try:
            conf = float(f.get("confidence", 0.5))
        except Exception:
            conf = 0.5
        # Normalize + HARD-CLAMP to [0,1]. Models frequently emit confidence as a
        # percentage (e.g. 95) or occasionally out of range. schema.Correction enforces
        # 0<=confidence<=1, so an unclamped value raises pydantic ValidationError — and
        # because that fires mid-loop it propagates out of judge(), sinking the ENTIRE
        # judge lane (all findings lost, silent false negatives). Never let one bad
        # number do that.
        if conf > 1.0:
            # >2 is clearly a percentage (e.g. 95 -> 0.95); a slight overshoot (1.0-2.0)
            # is just the model rounding past 1 -> clamp to 1.0, don't divide it to ~0.
            conf = conf / 100.0 if conf > 2.0 else 1.0
        conf = max(0.0, min(1.0, conf))
        qs, qc = f.get("quote_said"), f.get("quote_correct")
        if source == "B" and not (qs and qc):
            continue  # honesty rule: self-contradiction needs both quotes
        try:
            out.append(Correction(
                id=f"{source.lower()}_{kind}_{uuid.uuid4().hex[:6]}",
                source=source, strategy=strategy, confidence=conf, severity=sev,
                reason=f.get("reason", ""), quote_said=qs, quote_correct=qc,
                cited_policy=f.get("cited_policy"), suggested_line=f.get("suggested_line"),
                gate=compute_gate(source, conf, both_quotes=bool(qs and qc), deterministic=False),
            ))
        except Exception:
            # Defense in depth: a single malformed finding must not sink the whole lane —
            # skip just this one and keep the rest (graceful degradation, isolated).
            continue
    return out
