"""Instant lane — deterministic, NO LLM (source A).

Two checks, both grounded in the uploaded policy's extracted rule lists:
  1. prohibited-phrase hit in the agent's utterance   -> apologize_correct
  2. a required disclosure absent from the transcript  -> compliance_narration

High precision by construction (substring / anchor match), so source A auto-fires
safely. Runs in well under a millisecond — this is what keeps the LLM lane rare.
"""
from __future__ import annotations

import re
from typing import List

from .matching import prohibited_hit
from .schema import Correction

# Fallback anchor for identity-style disclosures when the policy gives no keywords.
_IDENTITY_ANCHOR = re.compile(
    r"(my name is|this is \w+|calling from|on behalf of|i am \w+ from|representing)", re.I
)
_STOP = {"the", "a", "an", "your", "you", "must", "state", "and", "or", "to", "of", "is", "be", "that"}


def _disclosure_satisfied(context_lc: str, disc: dict) -> bool:
    kws = disc.get("keywords") or []
    if kws:
        return any(k in context_lc for k in kws)
    text = disc.get("text", "").lower()
    if any(w in text for w in ("identity", "name", "who you are", "identify")):
        return bool(_IDENTITY_ANCHOR.search(context_lc))
    # derive content keywords from the rule text; satisfied if any appears
    words = [w for w in re.findall(r"[a-z]{4,}", text) if w not in _STOP]
    return any(w in context_lc for w in words) if words else True


def disclosure_anchors(disc: dict) -> List[str]:
    """The lexical anchors a disclosure is matched on — EXPOSED so an external check (e.g.
    the compliance C1 identity matcher, #35) can consume POLICY-GROUNDED signals instead of a
    hardcoded phrase list. Explicit `| keywords:` if given; else a canonical identity set;
    else the content words derived from the rule text (mirrors _disclosure_satisfied)."""
    kws = disc.get("keywords") or []
    if kws:
        return [k.strip().lower() for k in kws if k.strip()]
    text = disc.get("text", "").lower()
    if any(w in text for w in ("identity", "name", "who you are", "identify")):
        return ["my name is", "this is", "calling from", "on behalf of", "representing"]
    return [w for w in re.findall(r"[a-z]{4,}", text) if w not in _STOP]


def instant_lane(agent_utterance: str, context: str, policy_meta: dict) -> List[Correction]:
    out: List[Correction] = []
    ctx_lc = (context + "\n" + agent_utterance).lower()

    for i, phrase in enumerate(policy_meta.get("prohibited", [])):
        if prohibited_hit(phrase, agent_utterance):   # word-boundary match (not raw substring)
            out.append(Correction(
                id=f"a_prohibited_{i}",
                source="A", strategy="apologize_correct",
                confidence=1.0, severity="high",
                reason=f"Agent used a prohibited phrase: “{phrase}”.",
                quote_said=agent_utterance, quote_correct=None,
                cited_policy=f"Prohibited: {phrase}",
                suggested_line="Retract that and rephrase without the prohibited language; if it caused alarm, briefly apologize.",
                gate="auto",
            ))

    for i, disc in enumerate(policy_meta.get("disclosures", [])):
        if not _disclosure_satisfied(ctx_lc, disc):
            out.append(Correction(
                id=f"a_omission_{i}",
                source="A", strategy="compliance_narration",
                confidence=1.0, severity="medium",
                reason=f"Required disclosure not yet made: {disc.get('text','')}",
                quote_said=None, quote_correct=None,
                cited_policy=disc.get("text", ""),
                suggested_line=f"In your next turn, naturally satisfy this requirement: {disc.get('text','')}",
                gate="auto",
            ))
    return out
