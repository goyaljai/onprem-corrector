"""API authentication / authorization + rate limiting.

Why this exists
---------------
Before this, EVERY endpoint was open — including `POST /v1/policy/upload`, so anyone who
could reach the port could silently replace the compliance policy with a blank one and
**blind the guardrail** (a wide-open kill switch). InfoSec hard-blocks on that. This adds
role-based API-key auth in front of the sensitive endpoints, plus best-effort rate limiting.

Design (turnkey / SaaS-style)
-----------------------------
* Two roles via env: **caller** (`API_KEYS`, comma-separated) may call `/analyze`; **admin**
  (`ADMIN_API_KEY`, comma-separated) may do everything (admin ⊇ caller): upload policy, read
  the audit trail. The legacy `AUDIT_API_KEY` still works as an admin key (back-compat).
* Header: `X-API-Key: <key>`.
* **Open mode** — if NO keys are configured the service still runs (zero-config demo) but logs
  a loud startup warning. Set `AUTH_REQUIRED=true` to refuse unauthenticated access in prod.
* **Rate limit** — `RATE_LIMIT_PER_MIN` (0 = off): per-identity sliding-window, in-memory,
  best-effort (a shared store is needed across replicas — documented).

The decision logic (`evaluate`) is pure/stdlib so it is unit-testable without FastAPI; only
`require()` (the dependency) imports FastAPI, lazily. Keys are compared in constant time,
never logged.
"""
from __future__ import annotations

import hmac
import os
import sys
import threading
import time


def _parse(env: str) -> set:
    return {k.strip() for k in os.environ.get(env, "").split(",") if k.strip()}


ADMIN_KEYS = _parse("ADMIN_API_KEY")
CALLER_KEYS = _parse("API_KEYS")
_AUDIT_KEY = os.environ.get("AUDIT_API_KEY", "").strip()   # legacy → treated as an admin key
if _AUDIT_KEY:
    ADMIN_KEYS.add(_AUDIT_KEY)
AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "false").lower() == "true"
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MIN", "0") or 0)

_ALL_ADMIN = ADMIN_KEYS
_ALL_CALLER = CALLER_KEYS | ADMIN_KEYS   # admin can do anything a caller can


def auth_configured() -> bool:
    return bool(ADMIN_KEYS or CALLER_KEYS)


def startup_notice():
    """Print a prominent warning if the API is unprotected (called at app startup)."""
    if not auth_configured():
        msg = ("[SECURITY] No API keys configured — the API is UNAUTHENTICATED. "
               "Set API_KEYS / ADMIN_API_KEY (and optionally AUTH_REQUIRED=true) for production.")
        print("\n" + "=" * 78 + f"\n{msg}\n" + "=" * 78 + "\n", file=sys.stderr, flush=True)


def _key_in(key: str, allowed: set) -> bool:
    # constant-time membership (avoid timing oracles on the key)
    return any(hmac.compare_digest(key, a) for a in allowed)


# ------------------------------------------------------------------- rate limiter
_hits: dict = {}
_rl_lock = threading.Lock()


def _rate_ok(identity: str) -> bool:
    if RATE_LIMIT <= 0:
        return True
    now = time.time()
    with _rl_lock:
        window = [t for t in _hits.get(identity, []) if now - t < 60.0]
        if len(window) >= RATE_LIMIT:
            _hits[identity] = window
            return False
        window.append(now)
        _hits[identity] = window
        return True


# ------------------------------------------------------------------- pure decision
def evaluate(key: str | None, role: str = "caller") -> dict:
    """Pure authz decision. Returns {"ok":True,"identity":...} or
    {"ok":False,"status":<int>,"detail":<str>}. No FastAPI — unit-testable."""
    allowed = _ALL_ADMIN if role == "admin" else _ALL_CALLER
    if not auth_configured():
        if AUTH_REQUIRED:
            return {"ok": False, "status": 503,
                    "detail": "AUTH_REQUIRED=true but no API keys are configured."}
        identity = "anon"
    else:
        key = (key or "").strip()
        if not key:
            return {"ok": False, "status": 401, "detail": "Missing X-API-Key."}
        if not _key_in(key, allowed):
            if role == "admin" and _key_in(key, _ALL_CALLER):
                return {"ok": False, "status": 403, "detail": "Admin key required for this endpoint."}
            return {"ok": False, "status": 401, "detail": "Invalid X-API-Key."}
        identity = "admin" if _key_in(key, _ALL_ADMIN) else "caller"
    if not _rate_ok(identity + ":" + role):
        return {"ok": False, "status": 429, "detail": f"Rate limit exceeded ({RATE_LIMIT}/min)."}
    return {"ok": True, "identity": identity, "role": role}


# ------------------------------------------------------------------- FastAPI dependency
def require(role: str = "caller"):
    """FastAPI dependency factory. `role` ∈ {"caller","admin"}."""
    from fastapi import Header, HTTPException   # lazy: keep module import FastAPI-free

    def _dep(x_api_key: str | None = Header(default=None)):
        r = evaluate(x_api_key, role)
        if not r["ok"]:
            raise HTTPException(status_code=r["status"], detail=r["detail"])
        return {"role": r["role"], "identity": r["identity"]}

    return _dep
