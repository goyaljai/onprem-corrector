#!/usr/bin/env python3
"""Regression tests for the two critical bugs found in the pre-prod adversarial audit.

Run:  python scripts/test_bugfixes.py

Finding 1 — source-B self-contradiction must NOT be treated as grounded when the model
            fabricates/paraphrases quotes (app/grounding.py, used by judge to gate B).
Finding 2 — the audit redactor must mask secret shapes it previously leaked, and the
            input-block path must store the input hashed (app/audit.py).
GPU-free / stdlib-only.
"""
import importlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, FAIL = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
results = []
def check(name, cond):
    results.append(bool(cond))
    print(f"  [{PASS if cond else FAIL}] {name}")


def test_grounding():
    print("1. Finding 1 — quote grounding gates source B")
    from app.grounding import grounded
    t = "Agent: we never issue refunds under any circumstances."
    prior = "Worker earlier: your refund will be processed within 7 working days"
    check("real quote IS grounded", grounded("we never issue refunds", t) is True)
    check("real prior IS grounded", grounded("refund will be processed within 7 working days", prior) is True)
    check("FABRICATED quote is NOT grounded", grounded("we guarantee 20% returns", t + prior) is False)
    check("paraphrase (inserted word) is NOT grounded",
          grounded("i guarantee twenty percent", "i guarantee you twenty percent returns") is False)
    check("too-short quote is NOT grounded", grounded("ok", "ok sure thing") is False)


def _fresh_audit(mode="redacted"):
    d = tempfile.mkdtemp(prefix="bugfix_audit_")
    os.environ["AUDIT_DIR"] = d
    os.environ["AUDIT_STORE_MODE"] = mode
    os.environ["AUDIT_RETENTION_DAYS"] = "0"
    import app.audit as a
    importlib.reload(a)
    return a, a.AuditLog(d)


def test_redaction():
    print("2. Finding 2 — hardened redactor masks previously-leaked secrets")
    from app.audit import redact
    aws = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    cases = {
        "AWS secret w/ keyword": (f"our secret access key is {aws}", aws),
        "bare bearer token": ("Authorization: Bearer abcDEF0123456789ghiJKL", "abcDEF0123456789ghiJKL"),
        "PEM private key": ("-----BEGIN PRIVATE KEY-----\nMIIBVwIBADAN\n-----END PRIVATE KEY-----", "MIIBVwIBADAN"),
        "high-entropy token": (f"token {aws} end", aws),
    }
    for label, (text, leaked) in cases.items():
        out = redact(text)
        check(f"{label}: masked", leaked not in out and "REDACTED" in out)


def test_input_block_hashed():
    print("3. Finding 2 — input-block path stores the input HASHED (no plaintext)")
    a, audit = _fresh_audit(mode="redacted")
    secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    audit.record("input_block", utterance=f"secret access key is {secret}",
                 store_mode="hashed", extra={"blocked": True})
    rec = audit.query(limit=1)[0]
    blob = json.dumps(rec)
    check("plaintext secret absent", secret not in blob)
    check("stored as sha256", rec["input"]["utterance"].startswith("sha256:"))
    check("chain still verifies", a.AuditLog(os.environ["AUDIT_DIR"]).verify()["ok"] is True)


def test_prohibited_wordboundary():
    print("4. Finding 3 — prohibited match is word-boundary, not raw substring")
    from app.matching import prohibited_hit
    check("'pin' does NOT fire on 'typing'", prohibited_hit("pin", "I'm typing that in now") is False)
    check("'otp' does NOT fire on unrelated word", prohibited_hit("otp", "we will adopt a new plan") is False)
    check("'pin' DOES fire on 'your pin'", prohibited_hit("pin", "please tell me your pin") is True)
    check("suffix variant kept: 'arrest' -> 'arrested'", prohibited_hit("arrest", "you will be arrested") is True)
    check("multi-word phrase matches", prohibited_hit("we never issue refunds", "sorry, we never issue refunds here") is True)
    check("empty phrase never fires", prohibited_hit("", "anything") is False)


if __name__ == "__main__":
    for t in (test_grounding, test_redaction, test_input_block_hashed, test_prohibited_wordboundary):
        t()
    ok = all(results)
    print(f"\n{'ALL PASSED' if ok else 'SOME FAILED'} — {sum(results)}/{len(results)} checks")
    sys.exit(0 if ok else 1)
