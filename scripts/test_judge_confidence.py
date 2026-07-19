"""Regression test for the judge-lane confidence bug.

Bug: the LLM sometimes emits confidence as a percentage (e.g. 95) or out of range.
schema.Correction enforces 0<=confidence<=1, so an unclamped value raised a pydantic
ValidationError mid-loop that propagated out of judge() and sank the ENTIRE judge lane
(all findings lost -> silent false negatives). The fix normalizes+clamps confidence and
isolates per-finding construction.

Run: <venv>/bin/python -m scripts.test_judge_confidence   (from the sop-corrector dir)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.judge import judge


class _Msg:
    def __init__(self, content): self.message = type("M", (), {"content": content})
class _Resp:
    def __init__(self, content): self.choices = [_Msg(content)]
class _FakeCompletions:
    def __init__(self, content): self._c = content
    def create(self, **kw): return _Resp(self._c)
class _FakeClient:
    def __init__(self, content): self.chat = type("C", (), {"completions": _FakeCompletions(content)})


def run(name, content, expect_min_corrections):
    client = _FakeClient(content)
    out = judge(client, "m", "the fee is 500", "ctx", "", ["policy: flat 250, never a percentage"])
    ok = len(out) >= expect_min_corrections
    confs_ok = all(0.0 <= c.confidence <= 1.0 for c in out)
    status = "PASS" if (ok and confs_ok) else "FAIL"
    print(f"  {status}  {name}: {len(out)} corrections, confs={[c.confidence for c in out]}")
    return ok and confs_ok


PERCENT = '{"findings":[{"kind":"policy_violation","strategy":"apologize_correct","severity":"high","confidence":95,"reason":"wrong fee","quote_said":"500","quote_correct":"250","cited_policy":"p","suggested_line":"s"}]}'
OUT_OF_RANGE = '{"findings":[{"kind":"policy_violation","strategy":"apologize_correct","severity":"high","confidence":1.4,"reason":"x","quote_said":"500","quote_correct":"250","cited_policy":"p","suggested_line":"s"}]}'
# One malformed finding (out-of-range conf) alongside a good one — the good one must survive.
MIXED = '{"findings":[{"kind":"policy_violation","strategy":"apologize_correct","severity":"high","confidence":250,"reason":"a","quote_said":"500","quote_correct":"250"},{"kind":"tone","strategy":"empathy_repair","severity":"low","confidence":0.6,"reason":"b","quote_said":null,"quote_correct":null}]}'
NEGATIVE = '{"findings":[{"kind":"tone","strategy":"empathy_repair","severity":"low","confidence":-0.3,"reason":"n","quote_said":null,"quote_correct":null}]}'

if __name__ == "__main__":
    results = [
        run("percentage confidence 95 -> 0.95 (was: whole lane crashed)", PERCENT, 1),
        run("out-of-range 1.4 -> clamp to 1.0, lane survives", OUT_OF_RANGE, 1),
        run("mixed batch: one bad conf must not sink the good finding", MIXED, 2),
        run("negative confidence -> clamped to 0, no crash", NEGATIVE, 1),
    ]
    print(f"\nRESULT: {'ALL PASS' if all(results) else 'FAIL'} ({sum(results)}/{len(results)})")
    sys.exit(0 if all(results) else 1)
