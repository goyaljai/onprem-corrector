#!/usr/bin/env python3
"""Thorough LIVE test of the multi-document RAG corpus (#5).

Exercises the corpus end-to-end against a running corrector:
  bulk-load a ZIP of docs · list · cite-by-document · merged anchors across docs ·
  update ONE doc in isolation · delete ONE doc in isolation (stale chunks gone) ·
  back-compat single upload replaces the whole corpus.

Usage: BASE=http://localhost:5244 ADMIN_KEY=admin-key KEY=caller-key python scripts/test_rag_corpus.py
"""
import io, json, os, sys, urllib.request, urllib.error, zipfile

BASE = os.environ.get("BASE", "http://localhost:5244")
KEY = os.environ.get("KEY", "")
ADMIN_KEY = os.environ.get("ADMIN_KEY", KEY)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS, FAIL = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(f"  [{PASS if cond else FAIL}] {name}" + (f"  ({detail})" if (detail and not cond) else ""))


def req(method, path, data=None, admin=False, raw=False, ctype="application/json"):
    hdrs = {"Content-Type": ctype}
    k = ADMIN_KEY if admin else KEY
    if k:
        hdrs["X-API-Key"] = k
    if data is None:
        body = None
    elif raw:
        body = data if isinstance(data, bytes) else data.encode()
    else:
        body = json.dumps(data).encode()
    r = urllib.request.Request(BASE + path, data=body, method=method, headers=hdrs)
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.load(resp)


def analyze(utt, ctx="", prior=None):
    return req("POST", "/v1/corrector/analyze", {"agent_utterance": utt, "context": ctx, "prior_agent_claims": prior})


def cited_docs(r):
    return " ".join((c.get("cited_policy") or "") for c in r.get("corrections", [])).lower()


def main():
    # build a zip of the sample policy corpus in-memory
    pol_dir = os.path.join(HERE, "sample", "policies")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for fn in sorted(os.listdir(pol_dir)):
            if fn.endswith(".md"):
                z.write(os.path.join(pol_dir, fn), fn)
    zbytes = buf.getvalue()

    print("1. bulk-load ZIP of the sample corpus")
    res = req("POST", "/v1/policy/bulk", zbytes, admin=True, raw=True, ctype="application/zip")
    names = {d["name"] for d in res.get("loaded", [])}
    check("bulk loaded security+refunds+disclosures", {"security", "refunds", "disclosures"} <= names, str(names))

    print("2. list documents")
    docs = req("GET", "/v1/policy/documents")["documents"]
    dnames = {d["name"] for d in docs}
    check("list shows all 3 docs", {"security", "refunds", "disclosures"} <= dnames, str(dnames))

    print("3. merged anchors across docs (prohibited from security + refunds)")
    anch = req("GET", "/v1/policy/anchors")
    proh = " ".join(anch.get("prohibited_phrases", [])).lower()
    check("security prohibited present", "otp" in proh)
    check("refunds prohibited present", "never issue refunds" in proh)

    print("4. cite-by-document: wrong MAD should cite the refunds doc")
    r = analyze("The Minimum Amount Due is just 2 percent of your total.",
                "Agent: This is Priya from Meridian Bank, recorded for compliance.\nCustomer: minimum?")
    check("A fired", any(c["source"] == "A" for c in r.get("corrections", [])))
    check("citation references 'refunds' doc", "refunds" in cited_docs(r) or "[refunds]" in json.dumps(r).lower(),
          cited_docs(r)[:80])

    print("5. update ONE doc in isolation (bump refunds), others untouched")
    before = {d["name"]: d["version"] for d in req("GET", "/v1/policy/documents")["documents"]}
    req("POST", "/v1/policy/documents?name=refunds",
        "# Refunds Policy\nRefunds now take 10 working days.\n## Prohibited Phrases\n- we never issue refunds",
        admin=True, raw=True, ctype="text/plain")
    after = {d["name"]: d["version"] for d in req("GET", "/v1/policy/documents")["documents"]}
    check("refunds version changed", before.get("refunds") != after.get("refunds"))
    check("security version unchanged", before.get("security") == after.get("security"))

    print("6. delete ONE doc in isolation (disclosures), stale rules gone")
    req("DELETE", "/v1/policy/documents/disclosures", admin=True)
    docs2 = {d["name"] for d in req("GET", "/v1/policy/documents")["documents"]}
    check("disclosures removed", "disclosures" not in docs2)
    check("security + refunds remain", {"security", "refunds"} <= docs2, str(docs2))
    anch2 = req("GET", "/v1/policy/anchors")
    dtexts = " ".join(d.get("text", "") for d in anch2.get("disclosures", [])).lower()
    check("deleted doc's disclosure (grievance/nodal) no longer present", "nodal officer" not in dtexts)

    print("7. delete a missing doc -> 404")
    try:
        req("DELETE", "/v1/policy/documents/does_not_exist", admin=True)
        check("404 on missing doc", False)
    except urllib.error.HTTPError as e:
        check("404 on missing doc", e.code == 404)

    print("7b. bulk with same-basename files in different folders must NOT collide")
    cbuf = io.BytesIO()
    with zipfile.ZipFile(cbuf, "w") as z:
        z.writestr("security/policy.md", "# Prohibited Phrases\n- collide alpha")
        z.writestr("refunds/policy.md", "# Prohibited Phrases\n- collide beta")
    cres = req("POST", "/v1/policy/bulk", cbuf.getvalue(), admin=True, raw=True, ctype="application/zip")
    cnames = {d["name"] for d in cres.get("loaded", [])}
    check("both same-basename docs kept as distinct", len(cnames) == 2, str(cnames))

    print("8. back-compat: single upload REPLACES the whole corpus with 'default'")
    sop = open(os.path.join(HERE, "sample", "sop-handbook.md")).read()
    req("POST", "/v1/policy/upload", sop, admin=True, raw=True, ctype="text/plain")
    docs3 = {d["name"] for d in req("GET", "/v1/policy/documents")["documents"]}
    check("corpus replaced by single 'default'", docs3 == {"default"}, str(docs3))

    ok = all(results)
    print(f"\n{'ALL PASSED' if ok else 'SOME FAILED'} — {sum(results)}/{len(results)} checks")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
