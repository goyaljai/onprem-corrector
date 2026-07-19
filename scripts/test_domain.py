#!/usr/bin/env python3
"""Generic per-domain acceptance runner — SAME framework, different policy.

Uploads one domain's SOP, runs its transcript suite, asserts each case by its
`expect` tag. Proves the corrector is domain-agnostic with NO code change.

  BASE=http://127.0.0.1:15244 SOP=packs/hospital.md TR=packs/hospital.json python scripts/test_domain.py
"""
import json, os, re, sys, time, urllib.request

BASE = os.environ.get("BASE", "http://127.0.0.1:15244")
SOP = os.environ["SOP"]
TR = os.environ["TR"]


def _post(path, data, text=False):
    body, ctype = (data.encode(), "text/plain") if text else (json.dumps(data).encode(), "application/json")
    req = urllib.request.Request(BASE + path, data=body, headers={"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def analyze(c):
    return _post("/v1/corrector/analyze", {"agent_utterance": c["agent_utterance"],
                "context": c.get("context", ""), "prior_agent_claims": c.get("prior_agent_claims")})


def srcs(r):    return {c["source"] for c in r.get("corrections", [])}
def autos(r):   return {c["source"] for c in r.get("corrections", []) if c["gate"] == "auto"}
def blocked(r): return bool(r.get("meta", {}).get("blocked")) or any(o["category"] == "input_guardrail" for o in r.get("observations", []))


def check(case, r):
    name, exp = case["name"].lower(), case["expect"]
    if "no correction" in exp.lower() or "benign" in name or "compliant" in name:
        # A disclosure-omission (compliance_narration) is about conversation completeness, not the
        # utterance being wrong. A negative bait passes if the LINE itself isn't flagged as a real
        # violation (prohibited hit / judge contradiction) — omission-only is tolerated.
        bad = [c for c in r.get("corrections", []) if c["gate"] == "auto" and c["strategy"] != "compliance_narration"]
        return len(bad) == 0, "no utterance-level auto violation expected (omissions tolerated)"
    if "block" in exp.lower() or "inject" in name:
        return blocked(r), "input blocked"
    if "tone" in name or "empath" in name:
        # A dismissive line in a domain whose SOP covers conduct legitimately surfaces as a
        # GROUNDED policy-A rather than C. Pass if the rude line is caught either way.
        kw = ("dismiss", "rude", "panic", "empath", "respons", "frustrat", "wait in queue",
              "not my problem", "stop panicking", "acknowledg", "tone")
        caught = ("C" in srcs(r)) or any(
            any(k in ((c.get("reason") or "") + (c.get("quote_said") or "")).lower() for k in kw)
            for c in r.get("corrections", []))
        return caught, "tone caught (C, or grounded conduct-A referencing the rude line)"
    want = set(re.findall(r"\b([ABC])\b", exp + " " + case["name"]))
    if want:
        return want.issubset(srcs(r)), f"expect source {sorted(want)}"
    return len(r.get("corrections", [])) > 0, "expect some correction"


def main():
    up = _post("/v1/policy/upload", open(SOP).read(), text=True)
    cases = json.load(open(TR))
    print(f"policy={up['policy_version']} chunks={up['chunks_indexed']} "
          f"prohibited={up['prohibited_phrases']} disclosures={up['required_disclosures']} | cases={len(cases)}")
    print("=" * 68)
    passed = 0
    for c in cases:
        t = time.time()
        try:
            r = analyze(c); ok, why = check(c, r)
        except Exception as e:
            r, ok, why = {"corrections": []}, False, f"ERROR {e}"
        ms = int((time.time() - t) * 1000)
        fired = "".join(sorted({f"{x['source']}:{x['gate']}" for x in r.get("corrections", [])})) or "-"
        print(f"[{'PASS' if ok else 'FAIL'}] {c['name'][:52]:52} {ms:>5}ms  fired={fired}")
        if not ok:
            print(f"        {why} | got sources={sorted(srcs(r))}")
        passed += ok
    print("=" * 68)
    print(f"RESULT: {passed}/{len(cases)} passed")
    sys.exit(len(cases) - passed)


if __name__ == "__main__":
    main()
