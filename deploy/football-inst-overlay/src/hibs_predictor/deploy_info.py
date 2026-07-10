"""Deploy metadata for /api/ping and evidence since-deploy windows."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


def _deploy_root() -> Path:
    explicit = (os.getenv("DEPLOY_PATH") or os.getenv("HOME") or "").strip()
    if explicit:
        return Path(explicit)
    return Path(__file__).resolve().parents[2]


def _read_deploy_revision(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    except OSError:
        pass
    return out


def gather_deploy_info() -> Dict[str, Any]:
    root = _deploy_root()
    rev = _read_deploy_revision(root / ".deploy-revision")
    domain = (os.getenv("HIBS_DOMAIN") or rev.get("domain") or "hibs-bet.co.uk").strip()
    production_url = (os.getenv("HIBS_PRODUCTION_URL") or f"https://{domain}").strip()
    if not production_url.startswith("http"):
        production_url = f"https://{production_url}"

    revision = rev.get("revision") or (os.getenv("HIBS_DEPLOY_REVISION") or "").strip()
    if not revision:
        revision = "unknown"

    return {
        "service": rev.get("service") or "hibs-bet",
        "revision": revision,
        "deployed_at": rev.get("deployed_at") or "",
        "deploy_host": rev.get("deploy_host") or (os.getenv("DEPLOY_HOST") or "").strip(),
        "repo_root": str(root),
        "production_url": production_url,
    }
