"""Dry-run CLI: compares data/zotero_refs.json with the Notion database and writes reports.

Read-only on both sides. Needs NOTION_TOKEN and NOTION_DATA_SOURCE_ID in the environment
(unless --notion-snapshot is given, which reuses a previously saved snapshot).

    python -m zotsync.plan_cli [--zotero data/zotero_refs.json] [--out reports]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from .config import load_env
from .matcher import build_plan
from .notion_reader import NotionRow, fetch_rows
from .reader import Reference
from .report import render_csv, render_summary, render_todo


def load_refs(path: Path) -> list[Reference]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Reference(**it) for it in data["items"]]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Dry-run: match Zotero export against Notion and write reports.")
    p.add_argument("--zotero", default="data/zotero_refs.json", type=Path)
    p.add_argument("--out", default="reports", type=Path)
    p.add_argument("--notion-snapshot", type=Path,
                   help="Reuse a saved Notion snapshot (JSON) instead of querying the API.")
    p.add_argument("--save-notion-snapshot", type=Path,
                   help="Save the Notion rows read from the API (e.g. data/notion_rows.json).")
    args = p.parse_args(argv)
    load_env()

    if args.notion_snapshot:
        rows = [NotionRow(**r) for r in json.loads(args.notion_snapshot.read_text(encoding="utf-8"))]
    else:
        token, ds = os.environ.get("NOTION_TOKEN"), os.environ.get("NOTION_DATA_SOURCE_ID")
        if not token or not ds:
            print("Set NOTION_TOKEN and NOTION_DATA_SOURCE_ID.", file=sys.stderr)
            return 2
        rows = fetch_rows(token, ds)
        if args.save_notion_snapshot:
            args.save_notion_snapshot.parent.mkdir(parents=True, exist_ok=True)
            args.save_notion_snapshot.write_text(
                json.dumps([r.to_dict() for r in rows], ensure_ascii=False, indent=2), encoding="utf-8")

    plan = build_plan(load_refs(args.zotero), rows)
    today = date.today().isoformat()

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "todo_conflicts.md").write_text(render_todo(plan, today), encoding="utf-8")
    (args.out / "summary.md").write_text(render_summary(plan, today), encoding="utf-8")
    (args.out / "matches.csv").write_text(render_csv(plan), encoding="utf-8")

    print(render_summary(plan, today))
    print(f"Reports in {args.out}/ (dry-run: nothing was written to Notion).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
