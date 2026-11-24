"""Notion writer. Payload builders are pure; `apply_plan` is the only code that writes.

Safety invariants (enforced by `_check_payload` and tests):
  * only properties in WRITABLE_UPDATE / WRITABLE_CREATE are ever sent;
  * human-owned fields are never sent (Read/Checked only on page creation, unchecked);
  * "Paper title" is only sent on creation;
  * existing multi-select values are always kept (union);
  * pages are never deleted, archived or merged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .matcher import Matched, NewRow, Plan
from .notion_reader import (
    API_BASE, P_AUTHORS, P_CATEGORY, P_CHECKED, P_DOI, P_JOURNAL, P_READ, P_SUBCATEGORY,
    P_MODIFIED, P_TAG, P_TITLE, P_YEAR, P_ZOTERO_URI, request,
)

WRITABLE_UPDATE = {P_MODIFIED, P_AUTHORS, P_YEAR, P_JOURNAL, P_DOI, P_ZOTERO_URI, P_CATEGORY, P_SUBCATEGORY, P_TAG}
WRITABLE_CREATE = WRITABLE_UPDATE | {P_TITLE, P_READ, P_CHECKED}
# Zotero-owned bibliographic fields that --overwrite-bibliographic may replace.
OVERWRITABLE = {"authors", "year", "journal"}

_PROP_NAME = {"authors": P_AUTHORS, "year": P_YEAR, "journal": P_JOURNAL,
              "doi_link": P_DOI, "zotero_uri": P_ZOTERO_URI, "modified": P_MODIFIED}


def _rich(text: str) -> dict:
    return {"rich_text": [{"type": "text", "text": {"content": text}}]}


def _value(field_name: str, value: Any) -> dict:
    if field_name == "year":
        return {"number": int(value)}
    if field_name == "modified":
        return {"date": {"start": value}}
    if field_name == "doi_link":
        if not str(value).startswith("http"):
            raise ValueError("DOI link must start with http")
        return {"url": value}
    return _rich(str(value))


def _multi(names: list[str]) -> dict:
    return {"multi_select": [{"name": n} for n in names]}


def _check_payload(props: dict, allowed: set[str]) -> None:
    extra = set(props) - allowed
    if extra:
        raise ValueError(f"refusing to write non-writable properties: {sorted(extra)}")


def build_update(m: Matched, overwrite_bibliographic: bool = False) -> dict:
    """Properties to PATCH on an existing page ({} when nothing to do)."""
    props: dict[str, Any] = {}
    for k, v in m.fills.items():
        props[_PROP_NAME[k]] = _value(k, v)
    if overwrite_bibliographic:
        for k, v in m.conflicts.items():
            if k in OVERWRITABLE:
                props[_PROP_NAME[k]] = _value(k, v)
    for attr, name in (("category", P_CATEGORY), ("subcategory", P_SUBCATEGORY), ("tag", P_TAG)):
        add = m.additions.get(attr)
        if add:
            props[name] = _multi(list(getattr(m.row, attr)) + add)
    _check_payload(props, WRITABLE_UPDATE)
    return props


def build_create(n: NewRow, data_source_id: str) -> dict:
    props: dict[str, Any] = {
        P_TITLE: {"title": [{"type": "text", "text": {"content": n.title}}]},
        P_READ: {"checkbox": False},
        P_CHECKED: {"checkbox": False},
    }
    for k in ("authors", "journal", "year", "doi_link", "zotero_uri", "modified"):
        v = getattr(n, k)
        if v not in (None, ""):
            props[_PROP_NAME[k]] = _value(k, v)
    for attr, name in (("category", P_CATEGORY), ("subcategory", P_SUBCATEGORY), ("tag", P_TAG)):
        if getattr(n, attr):
            props[name] = _multi(getattr(n, attr))
    _check_payload(props, WRITABLE_CREATE)
    return {"parent": {"type": "data_source_id", "data_source_id": data_source_id}, "properties": props}


@dataclass
class Operations:
    updates: list[tuple[Matched, dict]] = field(default_factory=list)
    creates: list[tuple[NewRow, dict]] = field(default_factory=list)


def build_operations(plan: Plan, data_source_id: str, overwrite_bibliographic: bool = False) -> Operations:
    ops = Operations()
    for m in plan.matched:
        props = build_update(m, overwrite_bibliographic)
        if props:
            ops.updates.append((m, props))
    seen: set[str] = set()
    for n in plan.new:
        if n.group.doi:
            if n.group.doi in seen:   # never create two rows for one DOI
                continue
            seen.add(n.group.doi)
        ops.creates.append((n, build_create(n, data_source_id)))
    return ops


def describe(ops: Operations) -> str:
    lines = [f"Updates: {len(ops.updates)} | Creations: {len(ops.creates)}"]
    for m, props in ops.updates:
        title = " ".join((m.row.title or m.group.canonical.title).split())
        lines.append(f"  ~ {title}: {', '.join(sorted(props))}")
    for n, _ in ops.creates:
        lines.append(f"  + {' '.join(n.title.split())}")
    return "\n".join(lines)


def apply_operations(ops: Operations, token: str, limit: int | None = None) -> tuple[int, list[str]]:
    """Execute operations. Returns (done, errors). Errors never include secrets."""
    done, errors = 0, []
    budget = limit if limit is not None else len(ops.updates) + len(ops.creates)
    for m, props in ops.updates:
        if budget <= 0:
            break
        budget -= 1
        try:
            request("PATCH", f"{API_BASE}/pages/{m.row.page_id}", token, {"properties": props})
            done += 1
        except Exception as e:  # keep going; report at the end
            errors.append(f"update {m.row.page_id}: {e}")
    for n, body in ops.creates:
        if budget <= 0:
            break
        budget -= 1
        try:
            request("POST", f"{API_BASE}/pages", token, body)
            done += 1
        except Exception as e:
            errors.append(f"create {n.title[:60]!r}: {e}")
    return done, errors
