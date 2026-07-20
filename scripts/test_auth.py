#!/usr/bin/env python3
"""GPU-free unit tests for API auth/authz + rate limiting (app/auth.py).

Run:  python scripts/test_auth.py
Proves: open-mode allows but AUTH_REQUIRED refuses · missing/invalid key -> 401 ·
caller key can't hit admin routes (403) · admin ⊇ caller · legacy AUDIT_API_KEY = admin ·
rate limit -> 429. Pure logic (evaluate), no FastAPI / network needed.
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, FAIL = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
results = []
def check(name, cond):
    results.append(cond)
    print(f"  [{PASS if cond else FAIL}] {name}")


def load(**env):
    for k in ("API_KEYS", "ADMIN_API_KEY", "AUDIT_API_KEY", "AUTH_REQUIRED", "RATE_LIMIT_PER_MIN"):
        os.environ.pop(k, None)
    os.environ.update({k: v for k, v in env.items()})
    import app.auth as a
    return importlib.reload(a)


def test_open_mode():
    print("1. open mode (no keys) allows, AUTH_REQUIRED refuses")
    a = load()
    check("caller allowed (anon)", a.evaluate(None, "caller")["ok"] is True)
    check("admin allowed (anon)", a.evaluate(None, "admin")["ok"] is True)
    a = load(AUTH_REQUIRED="true")
    r = a.evaluate(None, "caller")
    check("AUTH_REQUIRED -> 503", r["ok"] is False and r["status"] == 503)


def test_roles():
    print("2. role-based keys (caller vs admin)")
    a = load(API_KEYS="caller1,caller2", ADMIN_API_KEY="admin1")
    check("no key -> 401", a.evaluate(None, "caller")["status"] == 401)
    check("unknown key -> 401", a.evaluate("nope", "caller")["status"] == 401)
    check("caller key on caller -> ok", a.evaluate("caller1", "caller")["ok"] is True)
    r = a.evaluate("caller1", "admin")
    check("caller key on ADMIN route -> 403", r["ok"] is False and r["status"] == 403)
    check("admin key on admin -> ok (identity admin)",
          a.evaluate("admin1", "admin") == {"ok": True, "identity": "admin", "role": "admin"})
    check("admin key on caller -> ok (admin superset)", a.evaluate("admin1", "caller")["ok"] is True)


def test_legacy_audit_key():
    print("3. legacy AUDIT_API_KEY behaves as an admin key")
    a = load(AUDIT_API_KEY="legacy-audit")
    check("audit key on admin -> ok", a.evaluate("legacy-audit", "admin")["ok"] is True)
    check("random key on admin -> 401", a.evaluate("x", "admin")["status"] == 401)


def test_rate_limit():
    print("4. rate limit -> 429 after N/min")
    a = load(API_KEYS="k", RATE_LIMIT_PER_MIN="3")
    oks = [a.evaluate("k", "caller")["ok"] for _ in range(3)]
    fourth = a.evaluate("k", "caller")
    check("first 3 allowed", all(oks))
    check("4th -> 429", fourth["ok"] is False and fourth["status"] == 429)


if __name__ == "__main__":
    for t in (test_open_mode, test_roles, test_legacy_audit_key, test_rate_limit):
        t()
    ok = all(results)
    print(f"\n{'ALL PASSED' if ok else 'SOME FAILED'} — {sum(results)}/{len(results)} checks")
    sys.exit(0 if ok else 1)
