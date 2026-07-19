#!/usr/bin/env python3
"""E2E test of GET /v1/policy/anchors (#35).

The corrector exposes its SOP-derived disclosure anchors so an external compliance check
(e.g. the voice-copilot C1 identity matcher) can consume POLICY-GROUNDED signals instead of
a hardcoded phrase list. Read-only; no GPU needed. Verifies explicit + derived anchors.

Run: BASE=http://127.0.0.1:5244 python3 scripts/test_anchors_endpoint.py
"""
import json, os, sys, urllib.request

BASE = os.environ.get("BASE", "http://localhost:5244")
POLICY = """# Anchor Endpoint Test SOP

## Required Disclosures
- Identity: the agent must state their name and that they are calling from Acme Bank. | keywords: acme bank, my name is, this is
- Purpose: the agent must state the reason for the call before discussing account details.

## Prohibited Phrases
- tell me your otp
"""

def req(path, data=None, text=False):
    kw = {}
    if data is not None:
        kw["data"] = data.encode() if text else json.dumps(data).encode()
        kw["headers"] = {"Content-Type": "text/plain" if text else "application/json"}
    with urllib.request.urlopen(urllib.request.Request(BASE + path, **kw), timeout=60) as r:
        return json.loads(r.read())

fails = []
def check(name, cond, got=None):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  got={got}"))
    if not cond: fails.append(name)

req("/v1/policy/upload", POLICY, text=True)
a = req("/v1/policy/anchors")
by = {d["text"].split(":")[0].strip().lower(): d["anchors"] for d in a["disclosures"]}

check("two disclosures exposed", len(a["disclosures"]) == 2, a["disclosures"])
check("explicit identity anchors (from `| keywords:`)",
      set(by.get("identity", [])) == {"acme bank", "my name is", "this is"}, by.get("identity"))
check("derived purpose anchors present (no explicit keywords)",
      "reason" in by.get("purpose", []) and "account" in by.get("purpose", []), by.get("purpose"))
check("prohibited phrase exposed", "tell me your otp" in a["prohibited_phrases"], a["prohibited_phrases"])

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
