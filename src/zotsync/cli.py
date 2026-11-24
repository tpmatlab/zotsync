"""CLI: read the Zotero group and write local JSON (nothing is written to Zotero).

Usage:
    export ZOTERO_API_KEY=...        # a read-only key is enough (or put it in .env)
    export ZOTERO_GROUP_ID=1234567
    python -m zotsync.cli --out data/zotero_refs.json [--collection "Cement pastes"]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from .config import load_env
from .reader import fetch_group


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Export references from a Zotero group (read-only).")
    p.add_argument("--out", default="data/zotero_refs.json", type=Path)
    p.add_argument("--collection", help="Filter by collection (includes subcollections).")
    p.add_argument("--since", type=int, help="Only items changed after this library version.")
    args = p.parse_args(argv)
    load_env()

    api_key, group_id = os.environ.get("ZOTERO_API_KEY"), os.environ.get("ZOTERO_GROUP_ID")
    if not api_key or not group_id:
        print("Set ZOTERO_API_KEY and ZOTERO_GROUP_ID.", file=sys.stderr)
        return 2

    refs, version = fetch_group(group_id, api_key, args.collection, args.since)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {"library_version": version, "group_id": group_id, "items": [r.to_dict() for r in refs]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    no_doi = sum(1 for r in refs if not r.doi)
    dup = [d for d, n in Counter(r.doi for r in refs if r.doi).items() if n > 1]
    print(f"{len(refs)} references | library version: {version} -> {args.out}")
    print(f"no DOI: {no_doi} | duplicate DOIs: {len(dup)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
