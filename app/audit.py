"""Tamper-evident audit trail (append-only, hash-chained JSONL).

Why this exists
---------------
A compliance guardrail that keeps no record is unsellable to a regulated buyer — the
first thing their Compliance/Legal team asks is "show me the immutable record of every
decision." This module makes every verdict (and policy change, and input-block) durable
and **tamper-evident**: each record embeds the hash of the previous one, so altering or
deleting any past record breaks the chain in a way `verify()` detects and pin-points —
and it can be verified **offline** (air-gap friendly, no external service).

Design
------
* Storage: append-only JSONL, one **daily segment** file `audit-YYYY-MM-DD.jsonl`, plus a
  small `_chain.json` index (last seq/hash + per-segment first/last seq & hash).
* Chain:  hash = sha256(prev_hash + "\n" + canonical_json(record_without_hash)).
  Genesis prev_hash = 64 zeros. Optional HMAC signature (`AUDIT_HMAC_KEY`) adds
  authenticity on top of integrity.
* Privacy: transcripts are scrubbed per `AUDIT_STORE_MODE` — `redacted` (PII masked,
  default), `hashed` (only sha256 of the text kept), or `full`. A raw-input SHA is always
  stored so an exact input can still be *proven* later without keeping the plaintext.
* Retention: whole expired segments are pruned (`AUDIT_RETENTION_DAYS`); a `pruned`
  marker preserves chain-verifiability of the retained window.
* Optional DB sink: JSONL stays the source of truth; a SQLite mirror can be enabled
  (`AUDIT_DB=sqlite:///path`) for easy querying — best-effort, never authoritative.

Regulation-agnostic on purpose: retention and redaction are configuration, not a single
regulator baked in.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
from datetime import datetime, timezone

try:
    import fcntl  # POSIX advisory file lock — cross-process safety on one host
except Exception:  # pragma: no cover - non-POSIX
    fcntl = None

GENESIS = "0" * 64


# ---------------------------------------------------------------------------- redaction
# Mask obvious PII + credential values so the stored transcript can't itself become a leak.
# Deliberately conservative (few false positives); tune per deployment.
_REDACTORS = [
    # PEM private-key blocks first (multiline, greedy within the block)
    (re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.S), "[REDACTED:pem]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED:email]"),
    (re.compile(r"\b(?:\+?\d[ -]?){10,15}\b"), "[REDACTED:phone]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[REDACTED:card]"),           # card-like digit runs
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[REDACTED:pan]"),            # India PAN shape
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED:ssn]"),
    # known token prefixes + Bearer tokens
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{12,}=*"), "[REDACTED:bearer]"),
    (re.compile(r"(sk-[A-Za-z0-9-]{12,}|ghp_[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{16,}"
                r"|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{12,}"
                r"|eyJ[A-Za-z0-9_-]{18,}\.[A-Za-z0-9_-]+)"), "[REDACTED:secret]"),
    # keyword -> value within a few tokens (not just immediately adjacent), catches
    # "our secret access key is wJalrXUtn…" that the old adjacency rule missed
    (re.compile(r"(?i)\b(password|passwd|pwd|api[_ -]?key|secret(?:[_ ]?access[_ ]?key)?|"
                r"access[_ ]?key|token|credential|otp|cvv|pin)s?\b[\s:=]*(?:\w+\s+){0,3}['\"]?"
                r"(?=\S*[A-Za-z0-9])\S{6,}"), "[REDACTED:credential]"),
    # generic high-entropy token: long base64/hex-ish run (AWS secret keys, opaque tokens).
    # Require mixed case + a digit WITHIN the base64 charset (not \w — that stops at '/').
    (re.compile(r"(?<![A-Za-z0-9+/])(?=[A-Za-z0-9+/]*[A-Z])(?=[A-Za-z0-9+/]*[a-z])"
                r"(?=[A-Za-z0-9+/]*\d)[A-Za-z0-9+/]{32,}={0,2}(?![A-Za-z0-9+/])"), "[REDACTED:highentropy]"),
]


def redact(text: str) -> str:
    out = text or ""
    for rx, repl in _REDACTORS:
        out = rx.sub(repl, out)
    return out


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _canonical(obj) -> str:
    # Deterministic serialization so the same record always hashes identically.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class AuditLog:
    def __init__(self, directory: str | None = None):
        self.dir = directory or os.environ.get("AUDIT_DIR", "./audit_store")
        self.enabled = os.environ.get("AUDIT_ENABLED", "true").lower() != "false"
        self.mode = os.environ.get("AUDIT_STORE_MODE", "redacted").lower()   # redacted|hashed|full
        self.retention_days = int(os.environ.get("AUDIT_RETENTION_DAYS", "0") or 0)  # 0 = forever
        self.fail_closed = os.environ.get("AUDIT_FAIL_CLOSED", "false").lower() == "true"
        self._hmac_key = (os.environ.get("AUDIT_HMAC_KEY") or "").encode() or None
        self._lock = threading.RLock()
        self._chain_path = os.path.join(self.dir, "_chain.json")
        self._sink = _make_sink(os.environ.get("AUDIT_DB", ""))
        if self.enabled:
            os.makedirs(self.dir, exist_ok=True)
            self._chain = self._load_chain()

    # ---- state -------------------------------------------------------------
    def _load_chain(self) -> dict:
        if os.path.exists(self._chain_path):
            with open(self._chain_path, encoding="utf-8") as f:
                return json.load(f)
        return {"last_seq": 0, "last_hash": GENESIS, "segments": [], "pruned": None}

    def _save_chain(self):
        tmp = self._chain_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._chain, f)
        os.replace(tmp, self._chain_path)  # atomic index update

    # ---- scrub per mode ----------------------------------------------------
    def _scrub(self, text: str, mode: str | None = None):
        m = mode or self.mode
        if not text:
            return text
        if m == "full":
            return text
        if m == "hashed":
            return "sha256:" + _sha256(text)
        return redact(text)  # default

    def _scrub_correction(self, c: dict, mode: str | None = None) -> dict:
        c = dict(c)
        for k in ("quote_said", "quote_correct", "reason", "suggested_line"):
            if c.get(k):
                c[k] = self._scrub(c[k], mode)
        return c

    # ---- write -------------------------------------------------------------
    def record(self, event: str, *, policy_version=None, model=None, lanes=None,
               latency_ms=None, utterance="", context="", prior="",
               corrections=None, extra=None, store_mode=None) -> dict | None:
        """Append one audit record. Returns the stored record (or None if disabled).

        `store_mode` overrides AUDIT_STORE_MODE for THIS record (e.g. the input-block path
        forces "hashed" because it already knows the input carries a secret).

        Raises only when AUDIT_FAIL_CLOSED=true; otherwise write errors are swallowed so a
        storage hiccup never takes down the request path ("the corrector should never die"),
        at the documented cost of a possible gap (which `verify` will surface)."""
        if not self.enabled:
            return None
        try:
            with self._lock:
                return self._append(event, policy_version, model, lanes, latency_ms,
                                    utterance, context, prior, corrections or [], extra or {},
                                    store_mode)
        except Exception:
            if self.fail_closed:
                raise
            return None

    def _append(self, event, policy_version, model, lanes, latency_ms,
                utterance, context, prior, corrections, extra, store_mode=None) -> dict:
        mode = store_mode or self.mode
        now = datetime.now(timezone.utc)
        seq = self._chain["last_seq"] + 1
        prev_hash = self._chain["last_hash"]
        raw_input = "".join([utterance or "", context or "", prior or ""])

        body = {
            "seq": seq,
            "ts": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
            "event": event,
            "policy_version": policy_version,
            "model": model,
            "lanes": lanes,
            "latency_ms": latency_ms,
            "store_mode": mode,
            "input": {
                "utterance": self._scrub(utterance, mode),
                "context": self._scrub(context, mode),
                "prior_agent_claims": self._scrub(prior, mode),
                "sha256": _sha256(raw_input),   # always present -> provable input match
            },
            "corrections": [self._scrub_correction(c, mode) for c in corrections],
            "outcome": {
                "n_corrections": len(corrections),
                "sources": sorted({c.get("source") for c in corrections if c.get("source")}),
                "gates": _count(corrections, "gate"),
                "blocked": bool(extra.get("blocked")),
            },
            "prev_hash": prev_hash,
        }
        if extra:
            body["meta"] = {k: v for k, v in extra.items() if k != "blocked"}

        h = _sha256(prev_hash + "\n" + _canonical(body))
        record = dict(body)
        record["hash"] = h
        if self._hmac_key:
            record["sig"] = hmac.new(self._hmac_key, h.encode(), hashlib.sha256).hexdigest()

        self._write_line(now, seq, prev_hash, h, record)
        self._chain["last_seq"] = seq
        self._chain["last_hash"] = h
        self._save_chain()
        if self._sink:
            try:
                self._sink.write(record)
            except Exception:
                pass  # sink is a best-effort mirror, never authoritative
        if self.retention_days:
            self._prune(now)
        return record

    def _write_line(self, now, seq, prev_hash, h, record):
        date = now.strftime("%Y-%m-%d")
        fname = f"audit-{date}.jsonl"
        path = os.path.join(self.dir, fname)
        seg = self._chain["segments"][-1] if self._chain["segments"] else None
        if seg is None or seg["date"] != date:
            # new daily segment; its first record links to the previous segment's last hash
            seg = {"date": date, "file": fname, "first_seq": seq,
                   "first_prev_hash": prev_hash, "last_seq": seq, "last_hash": h, "count": 0}
            self._chain["segments"].append(seg)
        with open(path, "a", encoding="utf-8") as f:
            if fcntl:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(_canonical(record) + "\n")
            f.flush()
            os.fsync(f.fileno())
            if fcntl:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        seg["last_seq"] = seq
        seg["last_hash"] = h
        seg["count"] += 1

    # ---- retention ---------------------------------------------------------
    def _prune(self, now):
        cutoff = now.date().toordinal() - self.retention_days
        kept, pruned_last = [], self._chain.get("pruned")
        for seg in self._chain["segments"]:
            seg_ord = datetime.strptime(seg["date"], "%Y-%m-%d").date().toordinal()
            if seg_ord < cutoff:
                try:
                    os.remove(os.path.join(self.dir, seg["file"]))
                except FileNotFoundError:
                    pass
                pruned_last = {"through_seq": seg["last_seq"], "through_hash": seg["last_hash"]}
            else:
                kept.append(seg)
        if len(kept) != len(self._chain["segments"]):
            self._chain["segments"] = kept
            self._chain["pruned"] = pruned_last
            self._save_chain()

    # ---- read / verify -----------------------------------------------------
    def _iter_records(self):
        for seg in self._chain["segments"]:
            path = os.path.join(self.dir, seg["file"])
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield json.loads(line)

    def query(self, limit=50, event=None, since_seq=0) -> list:
        out = []
        for rec in self._iter_records():
            if event and rec.get("event") != event:
                continue
            if rec.get("seq", 0) <= since_seq:
                continue
            out.append(rec)
        return out[-limit:]

    def stats(self) -> dict:
        by_event, by_gate, by_source = {}, {}, {}
        n = 0
        for rec in self._iter_records():
            n += 1
            by_event[rec.get("event")] = by_event.get(rec.get("event"), 0) + 1
            for g, c in (rec.get("outcome", {}).get("gates") or {}).items():
                by_gate[g] = by_gate.get(g, 0) + c
            for s in rec.get("outcome", {}).get("sources") or []:
                by_source[s] = by_source.get(s, 0) + 1
        return {"records": n, "last_seq": self._chain["last_seq"],
                "by_event": by_event, "by_gate": by_gate, "by_source": by_source,
                "pruned": self._chain.get("pruned")}

    def verify(self) -> dict:
        """Recompute the whole retained chain. Returns ok + the first break (if any)."""
        expected_prev = GENESIS
        pruned = self._chain.get("pruned")
        if pruned:
            expected_prev = pruned["through_hash"]  # retained window starts after a prune
        checked, first_seq, last_seq = 0, None, None
        for rec in self._iter_records():
            stored_hash = rec.get("hash")
            body = {k: v for k, v in rec.items() if k not in ("hash", "sig")}
            if rec.get("prev_hash") != expected_prev:
                return {"ok": False, "broken_at": rec.get("seq"), "reason": "prev_hash mismatch",
                        "checked": checked}
            recomputed = _sha256(rec.get("prev_hash", "") + "\n" + _canonical(body))
            if recomputed != stored_hash:
                return {"ok": False, "broken_at": rec.get("seq"), "reason": "content altered",
                        "checked": checked}
            if self._hmac_key and rec.get("sig"):
                good = hmac.new(self._hmac_key, stored_hash.encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(good, rec["sig"]):
                    return {"ok": False, "broken_at": rec.get("seq"), "reason": "bad signature",
                            "checked": checked}
            expected_prev = stored_hash
            checked += 1
            first_seq = first_seq if first_seq is not None else rec.get("seq")
            last_seq = rec.get("seq")
        return {"ok": True, "checked": checked, "first_seq": first_seq, "last_seq": last_seq,
                "head_hash": self._chain["last_hash"], "pruned": pruned}


def _count(items, key):
    out = {}
    for it in items:
        v = it.get(key)
        if v:
            out[v] = out.get(v, 0) + 1
    return out


# ------------------------------------------------------------------ optional sqlite sink
def _make_sink(dsn: str):
    if not dsn:
        return None
    if dsn.startswith("sqlite:///"):
        return _SqliteSink(dsn[len("sqlite:///"):])
    return None  # other DSNs (postgres…) can be added; JSONL remains the source of truth


class _SqliteSink:
    def __init__(self, path):
        import sqlite3
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS audit("
                         "seq INTEGER PRIMARY KEY, ts TEXT, event TEXT, policy_version TEXT,"
                         "n_corrections INTEGER, hash TEXT, record TEXT)")
        self._db.commit()

    def write(self, rec):
        self._db.execute("INSERT OR REPLACE INTO audit VALUES(?,?,?,?,?,?,?)",
                         (rec["seq"], rec["ts"], rec["event"], rec.get("policy_version"),
                          rec["outcome"]["n_corrections"], rec["hash"], _canonical(rec)))
        self._db.commit()


# module-level singleton, initialised by the app
_audit: AuditLog | None = None


def get_audit() -> AuditLog:
    global _audit
    if _audit is None:
        _audit = AuditLog()
    return _audit
