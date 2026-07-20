"""Policy ingestion + retrieval (the RAG lane) — MULTI-DOCUMENT corpus.

Real enterprises don't have one SOP file — they have a security policy, a refunds policy, a
KYC guide, per-product disclosures… This stores a **corpus of named markdown documents**:
add / update / delete each independently; retrieval spans them all; every retrieved chunk is
tagged with its source document so verdicts cite *which* policy. Prohibited-phrase and
disclosure extraction is merged across documents.

Everything runs on-prem: Chroma's default embedder is a local MiniLM ONNX model, persisted
to disk so the index survives restarts.

Concurrency: index/delete and the policy_meta.json read/write are guarded by a lock, and the
metadata file is written atomically (tmp + os.replace) so a concurrent `analyze` never reads
a half-written file (which previously could 500 or yield an empty-policy false-negative).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import List, Tuple

import chromadb
from chromadb.utils import embedding_functions

_COLLECTION = "policy"
_EMBED = embedding_functions.DefaultEmbeddingFunction()  # local MiniLM ONNX, cached on disk

_client = None
_persist_dir = None
_lock = threading.RLock()          # serialize corpus mutations + meta writes
DEFAULT_DOC = "default"


def init_store(persist_dir: str) -> None:
    global _client, _persist_dir
    os.makedirs(persist_dir, exist_ok=True)
    _persist_dir = persist_dir
    _client = chromadb.PersistentClient(path=persist_dir)


def _collection():
    return _client.get_or_create_collection(_COLLECTION, embedding_function=_EMBED)


# --- chunking ----------------------------------------------------------------

def _chunk(md: str, max_chars: int = 800) -> List[str]:
    """Heading-aware paragraph chunks; prepend the nearest heading for context."""
    lines = md.splitlines()
    heading = ""
    buf: List[str] = []
    chunks: List[str] = []

    def flush():
        if buf:
            body = "\n".join(buf).strip()
            if body:
                chunks.append((f"{heading}\n{body}" if heading else body).strip())
            buf.clear()

    for ln in lines:
        if ln.startswith("#"):
            flush()
            heading = ln.lstrip("#").strip()
            continue
        buf.append(ln)
        if sum(len(x) for x in buf) > max_chars and ln.strip() == "":
            flush()
    flush()
    out: List[str] = []
    for c in chunks:
        if len(c) <= max_chars * 1.5:
            out.append(c)
        else:
            for piece in re.split(r"(?<=[.!?])\s+", c):
                if piece.strip():
                    out.append(piece.strip())
    return [c for c in out if c]


# --- policy-rule extraction (for the instant lane) ---------------------------

def _bullets_under(md: str, heading_re: str) -> List[str]:
    out, capture = [], False
    for ln in md.splitlines():
        if ln.startswith("#"):
            capture = bool(re.search(heading_re, ln, re.I))
            continue
        if capture:
            m = re.match(r"\s*[-*]\s+(.*)", ln)
            if m:
                out.append(m.group(1).strip())
    return out


def _extract_rules(md: str) -> Tuple[List[str], List[dict]]:
    prohibited = _bullets_under(md, r"prohibit|banned|never say")
    disclosures = []
    for b in _bullets_under(md, r"required|mandatory|must (state|disclose)|disclosure"):
        kw = re.search(r"keywords?:\s*(.+)$", b, re.I)
        keywords = [k.strip().lower() for k in kw.group(1).split(",")] if kw else []
        text = re.sub(r"\|?\s*keywords?:.*$", "", b, flags=re.I).strip()
        disclosures.append({"text": text, "keywords": keywords})
    return prohibited, disclosures


# --- metadata (atomic) -------------------------------------------------------

def _meta_path() -> str:
    return os.path.join(_persist_dir or ".", "policy_meta.json")


def _read_meta() -> dict:
    p = _meta_path()
    try:
        with open(p) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        # missing OR mid-write/corrupt -> safe empty policy (never raise into the request path)
        return {"version": "none", "documents": {}, "prohibited": [], "disclosures": []}


def _write_meta(meta: dict) -> None:
    p = _meta_path()
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(meta, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)   # atomic: a concurrent reader sees either the old or the new file


def _rebuild_merged(meta: dict) -> None:
    """Recompute the corpus-wide prohibited/disclosures from all documents."""
    prohibited, seen, disclosures = [], set(), []
    for doc in meta.get("documents", {}).values():
        for ph in doc.get("prohibited", []):
            if ph.lower() not in seen:
                seen.add(ph.lower()); prohibited.append(ph)
        disclosures.extend(doc.get("disclosures", []))
    meta["prohibited"] = prohibited
    meta["disclosures"] = disclosures


# --- public API --------------------------------------------------------------

def index_document(name: str, md: str, version: str | None = None) -> Tuple[int, List[str], List[dict]]:
    """Add or REPLACE a single named document in the corpus (other docs untouched)."""
    import hashlib
    name = (name or DEFAULT_DOC).strip() or DEFAULT_DOC
    with _lock:
        col = _collection()
        # replace this doc's chunks only
        try:
            col.delete(where={"doc_name": name})
        except Exception:
            pass
        chunks = _chunk(md)
        ver = version or f"v{int(time.time())}"
        if chunks:
            col.add(
                ids=[f"{name}-{ver}-{i}" for i in range(len(chunks))],
                documents=chunks,
                metadatas=[{"doc_name": name, "version": ver, "idx": i} for i in range(len(chunks))],
            )
        prohibited, disclosures = _extract_rules(md)
        meta = _read_meta()
        meta.setdefault("documents", {})[name] = {
            "version": ver, "sha256": hashlib.sha256(md.encode()).hexdigest(),
            "chunks": len(chunks), "prohibited": prohibited, "disclosures": disclosures,
        }
        meta["version"] = ver          # corpus version bumps on any change
        _rebuild_merged(meta)
        _write_meta(meta)
        return len(chunks), prohibited, disclosures


def delete_document(name: str) -> bool:
    """Remove one document from the corpus. Returns True if it existed."""
    with _lock:
        col = _collection()
        try:
            col.delete(where={"doc_name": name})
        except Exception:
            pass
        meta = _read_meta()
        existed = name in meta.get("documents", {})
        meta.get("documents", {}).pop(name, None)
        meta["version"] = f"v{int(time.time())}"
        _rebuild_merged(meta)
        _write_meta(meta)
        return existed


def list_documents() -> List[dict]:
    meta = _read_meta()
    return [{"name": n, "version": d.get("version"), "sha256": d.get("sha256"),
             "chunks": d.get("chunks"), "prohibited": len(d.get("prohibited", [])),
             "disclosures": len(d.get("disclosures", []))}
            for n, d in meta.get("documents", {}).items()]


def index_handbook(md: str, version: str) -> Tuple[int, List[str], List[dict]]:
    """Back-compat single-file upload = REPLACE the whole corpus with one `default` document.

    Metadata is swapped in a SINGLE atomic write at the end — we never persist an empty
    interim policy, so a concurrent `analyze` can't observe a momentarily-blank corpus and
    return a false-negative 'clean' on a real breach."""
    import hashlib
    with _lock:
        try:
            _client.delete_collection(_COLLECTION)   # wipe every document
        except Exception:
            pass
        col = _collection()
        chunks = _chunk(md)
        ver = version or f"v{int(time.time())}"
        if chunks:
            col.add(ids=[f"{DEFAULT_DOC}-{ver}-{i}" for i in range(len(chunks))],
                    documents=chunks,
                    metadatas=[{"doc_name": DEFAULT_DOC, "version": ver, "idx": i} for i in range(len(chunks))])
        prohibited, disclosures = _extract_rules(md)
        meta = {"version": ver, "documents": {DEFAULT_DOC: {
            "version": ver, "sha256": hashlib.sha256(md.encode()).hexdigest(),
            "chunks": len(chunks), "prohibited": prohibited, "disclosures": disclosures}}}
        _rebuild_merged(meta)
        _write_meta(meta)              # ONE atomic swap old-corpus -> new-corpus
        return len(chunks), prohibited, disclosures


def retrieve(query: str, k: int = 4) -> List[str]:
    col = _collection()
    if col.count() == 0:
        return []
    res = col.query(query_texts=[query], n_results=min(k, col.count()),
                    include=["documents", "metadatas"])
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0] or [{}] * len(docs)
    # tag each chunk with its source document so the judge can cite WHICH policy
    return [f"[{(m or {}).get('doc_name', 'policy')}] {d}" for d, m in zip(docs, metas)]


def load_policy_meta() -> dict:
    return _read_meta()
