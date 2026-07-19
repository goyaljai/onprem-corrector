#!/usr/bin/env python3
"""GPU-free unit tests for the tamper-evident audit trail (app/audit.py).

Run:  python scripts/test_audit.py
Proves: chain verifies · tampering is detected at the exact seq · deletion is detected ·
redaction masks PII · hashed mode keeps no plaintext · retention prunes old segments while
the retained window still verifies. No model / GPU / network needed.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fresh(mode="redacted", retention=0, **env):
    """Build an AuditLog on a fresh temp dir with the given config (env is read in __init__)."""
    d = tempfile.mkdtemp(prefix="audit_test_")
    os.environ["AUDIT_DIR"] = d
    os.environ["AUDIT_STORE_MODE"] = mode
    os.environ["AUDIT_RETENTION_DAYS"] = str(retention)
    for k, v in env.items():
        os.environ[k] = v
    import importlib
    import app.audit as auditmod
    importlib.reload(auditmod)          # re-read env
    return auditmod, auditmod.AuditLog(d), d


SAMPLE_CORR = [{"source": "A", "gate": "auto", "confidence": 1.0, "reason": "prohibited phrase",
                "quote_said": "tell me your otp", "cited_policy": "Security"}]

PASS, FAIL = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
results = []
def check(name, cond):
    results.append(cond)
    print(f"  [{PASS if cond else FAIL}] {name}")


def test_chain_ok():
    print("1. chain verifies after appends")
    _, a, _ = _fresh()
    for i in range(5):
        a.record("analyze", policy_version="v1", model="m", lanes=["instant"], latency_ms=10,
                 utterance=f"line {i}", context="ctx", corrections=SAMPLE_CORR)
    r = a.verify()
    check("verify ok", r["ok"] is True)
    check("checked all 5", r["checked"] == 5)
    check("seq 1..5", r["first_seq"] == 1 and r["last_seq"] == 5)


def test_tamper_detected():
    print("2. tampering a middle record is detected at its seq")
    mod, a, d = _fresh()
    for i in range(5):
        a.record("analyze", policy_version="v1", model="m", utterance=f"line {i}", corrections=SAMPLE_CORR)
    seg = a._chain["segments"][-1]["file"]
    path = os.path.join(d, seg)
    lines = open(path).read().splitlines()
    rec = json.loads(lines[2])            # seq 3
    rec["latency_ms"] = 99999             # alter content WITHOUT recomputing hash
    lines[2] = json.dumps(rec, separators=(",", ":"))
    open(path, "w").write("\n".join(lines) + "\n")
    r = mod.AuditLog(d).verify()          # reload + verify
    check("verify fails", r["ok"] is False)
    check("broken_at seq 3", r["broken_at"] == 3)


def test_deletion_detected():
    print("3. deleting a record breaks the chain link")
    mod, a, d = _fresh()
    for i in range(5):
        a.record("analyze", utterance=f"line {i}", corrections=SAMPLE_CORR)
    seg = a._chain["segments"][-1]["file"]
    path = os.path.join(d, seg)
    lines = open(path).read().splitlines()
    del lines[2]                          # drop seq 3
    open(path, "w").write("\n".join(lines) + "\n")
    r = mod.AuditLog(d).verify()
    check("verify fails", r["ok"] is False)
    check("detected as prev_hash mismatch", r["reason"] == "prev_hash mismatch")


def test_redaction():
    print("4. redacted mode masks PII / secrets in the stored transcript")
    _, a, _ = _fresh(mode="redacted")
    a.record("analyze", utterance="call me at 9876543210 or a@b.com, otp is 448291",
             context="card 4111 1111 1111 1111", corrections=SAMPLE_CORR)
    rec = a.query(limit=1)[0]
    blob = json.dumps(rec)
    check("phone masked", "9876543210" not in blob and "REDACTED:phone" in blob)
    check("email masked", "a@b.com" not in blob and "REDACTED:email" in blob)
    check("card masked", "4111 1111 1111 1111" not in blob)
    check("input sha256 still present (provable)", len(rec["input"]["sha256"]) == 64)


def test_hashed_mode():
    print("5. hashed mode keeps NO plaintext")
    _, a, _ = _fresh(mode="hashed")
    a.record("analyze", utterance="super secret sentence", corrections=SAMPLE_CORR)
    rec = a.query(limit=1)[0]
    check("utterance stored as hash", rec["input"]["utterance"].startswith("sha256:"))
    check("plaintext absent", "super secret sentence" not in json.dumps(rec))


def test_retention():
    print("6. retention prunes old segments; retained window still verifies")
    mod, a, d = _fresh(retention=7)
    # record today, then synthesise an OLD segment file + index entry and prune
    a.record("analyze", utterance="recent", corrections=SAMPLE_CORR)
    old_file = "audit-2000-01-01.jsonl"
    open(os.path.join(d, old_file), "w").write('{"seq":0,"hash":"x"}\n')
    a._chain["segments"].insert(0, {"date": "2000-01-01", "file": old_file, "first_seq": 0,
                                    "first_prev_hash": "0"*64, "last_seq": 0, "last_hash": "0"*64, "count": 1})
    from datetime import datetime, timezone
    a._prune(datetime.now(timezone.utc))
    check("old segment file removed", not os.path.exists(os.path.join(d, old_file)))
    check("pruned marker set", a._chain.get("pruned") is not None)
    check("retained window verifies", mod.AuditLog(d).verify()["ok"] is True)


if __name__ == "__main__":
    for t in (test_chain_ok, test_tamper_detected, test_deletion_detected,
              test_redaction, test_hashed_mode, test_retention):
        t()
    ok = all(results)
    print(f"\n{'ALL PASSED' if ok else 'SOME FAILED'} — {sum(results)}/{len(results)} checks")
    sys.exit(0 if ok else 1)
