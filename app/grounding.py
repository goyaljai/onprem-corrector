"""Quote grounding — verify a model-supplied quote actually appears in the transcript.

Isolated (stdlib-only) so it is unit-testable without the model/pydantic stack. Used by the
judge to stop a fabricated self-contradiction (source B) from auto-firing: the LLM reports
confidence=1.0 indiscriminately, so a "you contradicted yourself" auto-correction must be
backed by quotes that are really present, not hallucinated.
"""
from __future__ import annotations

import re


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def grounded(quote: str, haystack: str, min_len: int = 8) -> bool:
    """True only if `quote` appears (whitespace/case-normalized) in `haystack`.
    Too-short quotes can't be meaningfully verified → treated as ungrounded."""
    q = normalize(quote)
    if len(q) < min_len:
        return False
    return q in normalize(haystack)
