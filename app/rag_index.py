"""Policy ingestion + retrieval (the RAG lane).

Chunk an uploaded policy/SOP markdown, embed locally (no egress), store in Chroma.
Also extracts two machine-usable lists for the deterministic instant lane:
  - prohibited phrases  (bullets under a heading matching /prohibit|banned|never say/i)
  - required disclosures (bullets under a heading matching /required|mandatory|must (state|disclose)/i)

Everything runs on-prem: Chroma's default embedder is a local MiniLM ONNX model,
persisted to disk (Lustre) so the index survives compute-node churn.
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Tuple

import chromadb
from chromadb.utils import embedding_functions

_COLLECTION = "policy"
_EMBED = embedding_functions.DefaultEmbeddingFunction()  # local MiniLM ONNX, cached on disk

_client = None
_persist_dir = None


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
    # split any oversized chunk on sentence-ish boundaries
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
        # optional "text | keywords: a, b" convention; else derive keywords from the text
        kw = re.search(r"keywords?:\s*(.+)$", b, re.I)
        keywords = [k.strip().lower() for k in kw.group(1).split(",")] if kw else []
        text = re.sub(r"\|?\s*keywords?:.*$", "", b, flags=re.I).strip()
        disclosures.append({"text": text, "keywords": keywords})
    return prohibited, disclosures


# --- public API --------------------------------------------------------------

def index_handbook(md: str, version: str) -> Tuple[int, List[str], List[dict]]:
    col = _collection()
    # wipe old policy so re-upload is a clean replace
    try:
        _client.delete_collection(_COLLECTION)
    except Exception:
        pass
    col = _collection()
    chunks = _chunk(md)
    if chunks:
        col.add(
            ids=[f"{version}-{i}" for i in range(len(chunks))],
            documents=chunks,
            metadatas=[{"version": version, "idx": i} for i in range(len(chunks))],
        )
    prohibited, disclosures = _extract_rules(md)
    meta = {"version": version, "prohibited": prohibited, "disclosures": disclosures}
    with open(os.path.join(_persist_dir, "policy_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return len(chunks), prohibited, disclosures


def retrieve(query: str, k: int = 4) -> List[str]:
    col = _collection()
    if col.count() == 0:
        return []
    res = col.query(query_texts=[query], n_results=min(k, col.count()))
    return res.get("documents", [[]])[0]


def load_policy_meta() -> dict:
    p = os.path.join(_persist_dir or ".", "policy_meta.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"version": "none", "prohibited": [], "disclosures": []}
