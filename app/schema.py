"""Typed contract for the on-prem policy-guardrail service.

Vocabulary is deliberately GENERIC (policy / agent_utterance / context) so the
framework is reusable for any agent + any policy domain. The OUTPUT profile
mirrors the voice-copilot `lib/agent/corrector-schema.ts` (source A/B/C +
strategy) so it drops straight into that bridge's gate — a thin adapter maps it.

Discipline carried over from the team's OpenAI Structured-Outputs work:
every field is ALWAYS present; optionality is expressed as `... | None`
(never omitted). This keeps strict JSON-schema parsers happy on both ends.
"""
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

# --- generic input -----------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """One agent turn to check against the indexed policy. Stateless."""
    agent_utterance: str = Field(..., description="The agent line that just completed — the thing to check now.")
    context: str = Field("", description="Rolling transcript window ('Agent:'/'Customer:' lines) for grounding.")
    prior_agent_claims: Optional[str] = Field(None, description="The agent's OWN earlier statements — grounds self-contradiction.")
    prior_context: Optional[str] = Field(None, description="Optional prior-call memory.")
    top_k: int = Field(4, ge=1, le=12, description="How many policy passages to retrieve.")

# --- output profile (mirrors corrector-schema) -------------------------------

Source = Literal["A", "B", "C"]          # A=policy/compliance, B=self-contradiction, C=tone/empathy
Strategy = Literal[
    "compliance_narration", "apologize_correct", "hedge", "hold_to_verify", "empathy_repair",
]
Severity = Literal["low", "medium", "high"]
Gate = Literal["auto", "propose", "drop"]

class Correction(BaseModel):
    id: str
    source: Source
    strategy: Strategy
    confidence: float = Field(..., ge=0.0, le=1.0)
    severity: Severity
    reason: str
    quote_said: Optional[str] = None        # the agent's actual words (groundable) — required for source B
    quote_correct: Optional[str] = None      # the correct version to state
    cited_policy: Optional[str] = None       # the retrieved policy text / rule id this is grounded in
    suggested_line: Optional[str] = None     # what the agent should say to rectify
    gate: Gate                               # computed, NOT acted on (verdict-only)

class Observation(BaseModel):
    id: str
    category: str
    severity: int = Field(1, ge=1, le=5)
    observation: str
    evidence: Optional[str] = None

class AnalyzeResponse(BaseModel):
    observations: List[Observation] = Field(default_factory=list)
    corrections: List[Correction] = Field(default_factory=list)
    rubric_projection: Optional[dict] = None
    meta: dict = Field(default_factory=dict)   # {latency_ms, model, policy_version, lanes:[...]}

    @classmethod
    def empty(cls, **meta) -> "AnalyzeResponse":
        """Well-formed empty body — the caller no-ops this turn, never crashes."""
        return cls(observations=[], corrections=[], rubric_projection=None, meta=meta)

class UploadResponse(BaseModel):
    policy_version: str
    chunks_indexed: int
    prohibited_phrases: int
    required_disclosures: int
