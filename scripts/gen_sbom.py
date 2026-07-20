#!/usr/bin/env python3
"""Generate a CycloneDX SBOM (Software Bill of Materials) of the running dependencies.

Why: enterprise security review + supply-chain hygiene needs a machine-readable inventory
of exactly what's installed (name + version) so it can be scanned for CVEs. Standard format
so `grype sbom.json`, Dependency-Track, etc. consume it directly.

Run:  python scripts/gen_sbom.py > sbom.json
No third-party deps — reads installed distributions via importlib.metadata.
"""
import json
import sys

try:
    from importlib import metadata as im
except Exception:  # pragma: no cover
    import importlib_metadata as im  # type: ignore


def main():
    components = []
    for dist in sorted(im.distributions(), key=lambda d: (d.metadata.get("Name") or "").lower()):
        name = dist.metadata.get("Name")
        version = dist.version
        if not name:
            continue
        components.append({
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{name.lower()}@{version}",
        })
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "onprem-corrector"}},
        "components": components,
    }
    json.dump(sbom, sys.stdout, indent=2)
    print(file=sys.stderr)
    print(f"SBOM: {len(components)} components (CycloneDX 1.5)", file=sys.stderr)


if __name__ == "__main__":
    main()
