"""Write CLI. DRY-RUN by default: nothing is written without --apply.

    python -m zotsync.write_cli                       # prints what would change
    python -m zotsync.write_cli --apply --limit 5     # writes only the first 5 operations
    python -m zotsync.write_cli --apply --only creates --limit 2   # test page creation
    python -m zotsync.write_cli --apply               # writes everything planned

--overwrite-bibliographic also replaces non-empty Year/Journal/Authors with Zotero values
(off by default; conflicts are otherwise only reported by plan_cli).
Always re-reads Notion live before planning.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import load_env
from .matcher import build_plan
from .notion_reader import fetch_rows
from .notion_writer import apply_operations, build_operations, describe
from .plan_cli import load_refs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Apply the Zotero -> Notion plan (dry-run unless --apply).")
    p.add_argument("--zotero", default="data/zotero_refs.json", type=Path)
    p.add_argument("--apply", action="store_true", help="Actually write to Notion.")
    p.add_argument("--limit", type=int, help="Max operations to execute with --apply.")
    p.add_argument("--only", choices=["updates", "creates"], help="Restrict to one kind of operation.")
    p.add_argument("--overwrite-bibliographic", action="store_true",
                   help="Overwrite non-empty Year/Journal/Authors that diverge from Zotero.")
    args = p.parse_args(argv)
    load_env()

    token, ds = os.environ.get("NOTION_TOKEN"), os.environ.get("NOTION_DATA_SOURCE_ID")
    if not token or not ds:
        print("Set NOTION_TOKEN and NOTION_DATA_SOURCE_ID.", file=sys.stderr)
        return 2

    plan = build_plan(load_refs(args.zotero), fetch_rows(token, ds))
    ops = build_operations(plan, ds, args.overwrite_bibliographic)
    if args.only == "updates":
        ops.creates.clear()
    elif args.only == "creates":
        ops.updates.clear()
    if args.limit is not None:
        ops.updates = ops.updates[: args.limit]
        ops.creates = ops.creates[: max(args.limit - len(ops.updates), 0)]
    print(describe(ops))

    if not args.apply:
        print("\nDry-run: nothing was written. Use --apply (optionally --limit N) to write.")
        return 0

    done, errors = apply_operations(ops, token, args.limit)
    print(f"\nExecuted: {done} | Errors: {len(errors)}")
    for e in errors:
        print("  !", e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
