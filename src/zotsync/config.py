"""Minimal .env loader (no dependency). Real environment variables always win."""
from __future__ import annotations

import os
from pathlib import Path

ALLOWED = {"ZOTERO_API_KEY", "ZOTERO_GROUP_ID", "NOTION_TOKEN", "NOTION_DATA_SOURCE_ID"}


def load_env(path: Path | str = ".env") -> list[str]:
    """Load KEY=VALUE lines for known keys into os.environ. Returns the names set (never values)."""
    p = Path(path)
    if not p.is_file():
        return []
    loaded = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip().strip("'\"")
        if key in ALLOWED and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
