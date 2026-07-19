"""Confidence gate — mirrors lib/agent/corrector-gate.ts, adapted for the on-prem lane.

Thresholds preserved: AUTO=0.8, FLOOR=0.5.
  A (compliance/policy): deterministic instant-lane -> auto; LLM-grounded -> auto iff conf>=0.8, else propose.
  B (self-contradiction): auto iff BOTH quotes present AND conf>=0.8, else propose.
  C (tone/empathy):       never auto -> propose (drop below floor).
Below FLOOR -> drop. The honesty rule: never auto-correct when unsure.

We return the decision; we do NOT act on it (verdict-only — the bridge decides).
"""
from __future__ import annotations

AUTO = 0.8
FLOOR = 0.5


def compute_gate(source: str, confidence: float, *, both_quotes: bool = False, deterministic: bool = False) -> str:
    if confidence < FLOOR and not deterministic:
        return "drop"
    if source == "A":
        # Team invariant: ONLY deterministic-A auto-fires. An LLM-derived policy finding
        # is NOT deterministic and the model reports conf=1.0 indiscriminately, so it must
        # go to a human (propose) — auto-correcting on it risks "apologizing for being right".
        return "auto" if deterministic else "propose"
    if source == "B":
        return "auto" if (both_quotes and confidence >= AUTO) else "propose"
    return "propose"  # C
