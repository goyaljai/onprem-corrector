#!/usr/bin/env python3
"""End-to-end test of the DISCLOSURE-ANCHOR flow (the corrector's instant lane).

A "required disclosure" in a policy becomes lexical *anchors*: either explicit
(`| keywords: ...`) or derived from the disclosure sentence. On analyze, the instant lane
fires a source-A "missing disclosure" correction iff none of that disclosure's anchors
appear in the transcript window. This exercises both anchor sources + present/absent +
alternate phrasing, end to end against a LIVE corrector.

Run: BASE=http://127.0.0.1:15244 python3 scripts/test_anchors.py
"""
import json, os, sys, urllib.request

BASE = os.environ.get("BASE", "http://localhost:5244")

POLICY = """# Anchor Test SOP

## Required Disclosures
- Identity: the agent must state their name and that they are calling from Acme Bank. | keywords: acme bank, my name is, this is
- Purpose: the agent must state the reason for the call before discussing account details.
"""

def _post(path, data, text=False):
    body = data.encode() if text else json.dumps(data).encode()
    ctype = "text/plain" if text else "application/json"
    req = urllib.request.Request(BASE + path, data=body, headers={"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

def omissions(utterance, context):
    """Return the set of disclosure omissions fired (by cited policy keyword)."""
    resp = _post("/v1/corrector/analyze", {"agent_utterance": utterance, "context": context})
    out = []
    for c in resp.get("corrections", []):
        if c.get("source") == "A" and c.get("id", "").startswith("a_omission"):
            cp = (c.get("cited_policy") or "").lower()
            out.append("identity" if "identity" in cp else "purpose" if "purpose" in cp else cp[:20])
    return set(out), resp

fails = []
def check(name, cond, got=None):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  got={got}"))
    if not cond: fails.append(name)

up = _post("/v1/policy/upload", POLICY, text=True)
print("upload:", json.dumps(up), "\n" + "=" * 66)

# 1) both disclosures absent -> both anchors miss -> 2 omissions
o, _ = omissions("The interest rate is 8 percent.", "Worker: The interest rate is 8 percent.")
check("both missing -> identity+purpose omissions", o == {"identity", "purpose"}, o)

# 2) explicit-keyword anchor present (identity) -> only purpose omission
o, _ = omissions("The interest rate is 8 percent.",
                 "Worker: My name is Priya from Acme Bank. The interest rate is 8 percent.")
check("explicit identity anchor present -> only purpose fires", o == {"purpose"}, o)

# 3) derived anchor present (purpose: 'account'/'call...') + identity -> 0 omissions
o, _ = omissions("The interest rate is 8 percent.",
                 "Worker: This is Priya from Acme Bank, calling about your loan account. The rate is 8 percent.")
check("derived purpose anchor + identity present -> no omissions", o == set(), o)

# 4) alternate identity phrasing ('this is X from Acme Bank') still satisfies identity
o, _ = omissions("The interest rate is 8 percent.",
                 "Worker: This is Ravi from Acme Bank. The interest rate is 8 percent.")
check("alt identity phrasing satisfies identity -> only purpose fires", o == {"purpose"}, o)

print("\n" + ("ALL ANCHOR TESTS PASSED" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
