"""Prohibited-phrase matching — stdlib-only so it is unit-testable without the model stack.

Bug this fixes: matching a prohibited phrase by raw substring makes a short token like
"pin" / "otp" / "cvv" false-fire on any word that merely CONTAINS it ("pin" ⊂ "typing",
"spinning"). Because source-A prohibited hits auto-fire, that's a wrong auto-correction on a
benign line.

Fix: anchor a word boundary at the START of the phrase. This kills mid-word matches
("typing") while still catching natural morphological variants at the end
("arrest" -> "arrested", "threaten" -> "threatening") — which an SOP author expects.
"""
from __future__ import annotations

import re


def prohibited_hit(phrase: str, text: str) -> bool:
    p = (phrase or "").lower().strip()
    if not p:
        return False
    # \b before the phrase; escape it so punctuation/spaces are literal. No end anchor so
    # suffixes still match (arrest->arrested), but a preceding word char blocks "typing"->pin.
    return re.search(r"\b" + re.escape(p), (text or "").lower()) is not None
