#!/usr/bin/env python3
"""Prove the corrector's network is locked down (issue #2).

Run it INSIDE the corrector's network namespace (container/pod):
    docker compose exec corrector python scripts/egress_check.py
    kubectl exec deploy/corrector -- python scripts/egress_check.py

It checks that (a) the local vLLM IS reachable, and (b) a set of public internet endpoints
are NOT — i.e. a data-exfil path does not exist. Exit 0 only if egress is properly locked.
No dependencies; pure sockets + short timeouts.
"""
import os
import socket
import sys
from urllib.parse import urlparse

TIMEOUT = 3.0
# Endpoints that MUST be unreachable if egress is locked down (common exfil/telemetry targets).
PUBLIC = [("api.openai.com", 443), ("1.1.1.1", 443), ("8.8.8.8", 53), ("github.com", 443)]


def reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT):
            return True
    except Exception:
        return False


def main() -> int:
    base = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
    u = urlparse(base)
    vllm_host, vllm_port = u.hostname or "localhost", u.port or 8000

    print(f"vLLM dependency  {vllm_host}:{vllm_port}")
    vllm_ok = reachable(vllm_host, vllm_port)
    print(f"  {'OK  reachable (expected)' if vllm_ok else 'WARN not reachable — is vLLM up?'}")

    print("public internet  (should ALL be blocked):")
    leaked = []
    for host, port in PUBLIC:
        if reachable(host, port):
            leaked.append(f"{host}:{port}")
            print(f"  LEAK {host}:{port} is reachable  <-- egress NOT locked down")
        else:
            print(f"  BLOCKED {host}:{port}")

    print("-" * 60)
    if leaked:
        print(f"RESULT: EGRESS OPEN — {len(leaked)} public endpoint(s) reachable: {leaked}")
        print("Apply deploy/k8s/networkpolicy.yaml (k8s) or docker-compose.locked.yml (docker).")
        return 1
    print("RESULT: LOCKED DOWN — no public egress; only the local vLLM is reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
