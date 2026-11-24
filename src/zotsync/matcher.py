"""Pure matching and planning: Zotero references x Notion rows -> `Plan`.

No I/O. The plan only describes what *would* be filled/created; divergences in
fields that already have a value are never overwritten, they become `Issue`s.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from .notion_reader import NotionRow
from .reader import Reference, normalize_doi

NOTION_TEXT_LIMIT = 2000


# ---------- normalization ----------

def normalize_text(s: str | None) -> str:
    """Lowercase, no accents/punctuation, collapsed whitespace (newlines included)."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"[^0-9a-z]+", " ", s)
    return s.strip()


normalize_title = normalize_text


def same_instant(a: str, b: str) -> bool:
    """Compare ISO timestamps at second precision (Notion returns '.000+00:00', Zotero 'Z')."""
    def parse(s: str) -> datetime | None:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).replace(microsecond=0)
    pa, pb = parse(a), parse(b)
    return pa == pb if pa and pb else a == b


def canonical_doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}" if doi else ""


def authors_to_notion(authors: list[str]) -> tuple[str, bool]:
    """'Last, First' -> 'First Last', joined by '; '. Returns (text, truncated)."""
    out = []
    for a in authors:
        if "," in a:
            last, first = (x.strip() for x in a.split(",", 1))
            out.append(f"{first} {last}".strip())
        else:
            out.append(a.strip())
    text = "; ".join(out)
    if len(text) > NOTION_TEXT_LIMIT:
        return text[: NOTION_TEXT_LIMIT - 1] + "…", True
    return text, False


def categories_for(collections: list[str]) -> tuple[list[str], list[str]]:
    """'A' -> category A; 'A / B' -> category A and subcategory B."""
    cats: list[str] = []
    subs: list[str] = []
    for path in collections:
        parts = [p.strip() for p in path.split(" / ")]
        if parts[0] not in cats:
            cats.append(parts[0])
        if len(parts) > 1 and parts[-1] not in subs:
            subs.append(parts[-1])
    return cats, subs


# ---------- data ----------

@dataclass
class Issue:
    kind: str
    title: str
    detail: str = ""
    notion_url: str = ""
    zotero_uri: str = ""


@dataclass
class ZGroup:
    """One logical Zotero paper: all copies of a DOI merged (or a single no-DOI item)."""
    doi: str
    canonical: Reference
    members: list[Reference]
    collections: list[str]
    tags: list[str]


@dataclass
class Matched:
    row: NotionRow
    group: ZGroup
    method: str                                  # "doi" | "title"
    fills: dict[str, Any] = field(default_factory=dict)
    additions: dict[str, list[str]] = field(default_factory=dict)
    # Zotero values that differ from non-empty Notion values; applied only with --overwrite-bibliographic.
    conflicts: dict[str, Any] = field(default_factory=dict)


@dataclass
class NewRow:
    group: ZGroup
    title: str
    authors: str
    year: int | None
    journal: str
    doi_link: str
    category: list[str]
    subcategory: list[str]
    tag: list[str]
    zotero_uri: str = ""
    modified: str = ""
    read: bool = False
    checked: bool = False


@dataclass
class Plan:
    matched: list[Matched] = field(default_factory=list)
    new: list[NewRow] = field(default_factory=list)
    orphans: list[tuple[NotionRow, str]] = field(default_factory=list)   # (row, kind)
    duplicate_rows: list[tuple[str, list[NotionRow], ZGroup]] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    zotero_merged_dois: int = 0
    zotero_items: int = 0
    zotero_groups: int = 0


# ---------- grouping ----------

def group_zotero(refs: list[Reference]) -> list[ZGroup]:
    by_doi: dict[str, list[Reference]] = {}
    groups: list[ZGroup] = []
    for r in refs:
        if r.doi:
            by_doi.setdefault(r.doi, []).append(r)
        else:
            groups.append(ZGroup("", r, [r], sorted(r.collections), sorted(r.tags)))
    for doi, members in by_doi.items():
        canon = max(members, key=lambda m: m.version)
        groups.append(ZGroup(
            doi, canon, members,
            sorted({c for m in members for c in m.collections}),
            sorted({t for m in members for t in m.tags}),
        ))
    return groups


def _valid_options(values: list[str], title: str, zuri: str, issues: list[Issue], what: str) -> list[str]:
    ok = []
    for v in values:
        if "," in v:
            issues.append(Issue("invalid_option", title,
                                f"{what} '{v}' contains a comma and cannot become a Notion option (omitted).",
                                zotero_uri=zuri))
        else:
            ok.append(v)
    return ok


def _desired(group: ZGroup, title: str, issues: list[Issue]) -> dict[str, Any]:
    c = group.canonical
    authors, truncated = authors_to_notion(c.authors)
    if truncated:
        issues.append(Issue("authors_truncated", title,
                            f"Authors exceeds {NOTION_TEXT_LIMIT} characters and was truncated with '…'.",
                            zotero_uri=c.zotero_uri))
    cats, subs = categories_for(group.collections)
    z = c.zotero_uri
    return {
        "authors": authors,
        "year": c.year,
        "journal": c.publication,
        "doi_link": canonical_doi_url(group.doi),
        "category": _valid_options(cats, title, z, issues, "Category"),
        "subcategory": _valid_options(subs, title, z, issues, "Subcategory"),
        "tag": _valid_options(group.tags, title, z, issues, "Tag"),
    }


# ---------- planning ----------

def build_plan(refs: list[Reference], rows: list[NotionRow]) -> Plan:
    plan = Plan(zotero_items=len(refs))
    groups = group_zotero(refs)
    plan.zotero_groups = len(groups)
    plan.zotero_merged_dois = sum(1 for g in groups if len(g.members) > 1)

    row_doi = {r.page_id: normalize_doi(r.doi_link) for r in rows}
    rows_by_doi: dict[str, list[NotionRow]] = {}
    rows_by_title: dict[str, list[NotionRow]] = {}
    for r in rows:
        if row_doi[r.page_id]:
            rows_by_doi.setdefault(row_doi[r.page_id], []).append(r)
        elif r.title:
            rows_by_title.setdefault(normalize_title(r.title), []).append(r)

    used: set[str] = set()

    for g in groups:
        title = g.canonical.title
        zuri = g.canonical.zotero_uri
        found: list[NotionRow] = []
        method = ""
        if g.doi and g.doi in rows_by_doi:
            found, method = rows_by_doi[g.doi], "doi"
        else:
            key = normalize_title(title)
            if key and key in rows_by_title:
                found, method = rows_by_title[key], "title"

        if not found:
            issues: list[Issue] = plan.issues
            d = _desired(g, title, issues)
            plan.new.append(NewRow(g, title, d["authors"], d["year"], d["journal"],
                                   d["doi_link"], d["category"], d["subcategory"], d["tag"],
                                   g.canonical.zotero_uri, g.canonical.date_modified))
            continue

        for r in found:
            used.add(r.page_id)

        if len(found) > 1:
            plan.duplicate_rows.append((method, found, g))
            for r in found:
                plan.issues.append(Issue(
                    "duplicate_notion", r.title or title,
                    f"{len(found)} Notion rows match the same "
                    f"{'DOI ' + g.doi if method == 'doi' else 'title'}; nothing was planned for them.",
                    r.url, zuri))
            continue

        row = found[0]
        m = Matched(row, g, method)
        d = _desired(g, title, plan.issues)
        label = row.title or title

        if d["authors"]:
            if not row.authors:
                m.fills["authors"] = d["authors"]
            elif normalize_text(row.authors) != normalize_text(d["authors"]):
                m.conflicts["authors"] = d["authors"]
                plan.issues.append(Issue("conflict_authors", label,
                                         f"Notion: {row.authors} | Zotero: {d['authors']}", row.url, zuri))
        if d["year"] is not None:
            if row.year is None:
                m.fills["year"] = d["year"]
            elif row.year != d["year"]:
                m.conflicts["year"] = d["year"]
                plan.issues.append(Issue("conflict_year", label,
                                         f"Notion: {row.year} | Zotero: {d['year']}", row.url, zuri))
        if d["journal"]:
            if not row.journal:
                m.fills["journal"] = d["journal"]
            elif normalize_text(row.journal) != normalize_text(d["journal"]):
                m.conflicts["journal"] = d["journal"]
                plan.issues.append(Issue("conflict_journal", label,
                                         f"Notion: {row.journal} | Zotero: {d['journal']}", row.url, zuri))
        if d["doi_link"]:
            if not row.doi_link:
                m.fills["doi_link"] = d["doi_link"]
            elif method == "title":
                plan.issues.append(Issue("doi_suggestion", label,
                                         f"Current link preserved: {row.doi_link} | Suggested DOI: {d['doi_link']}",
                                         row.url, zuri))
        zmod = g.canonical.date_modified
        if zmod:
            if not row.modified:
                m.fills["modified"] = zmod
            elif not same_instant(row.modified, zmod):
                plan.issues.append(Issue("conflict_modified", label,
                                         f"Notion: {row.modified} | Zotero: {zmod}", row.url, zuri))
        member_uris = {x.zotero_uri for x in g.members}
        if not row.zotero_uri:
            m.fills["zotero_uri"] = zuri
        elif row.zotero_uri not in member_uris:
            plan.issues.append(Issue("conflict_zotero_uri", label,
                                     f"Notion: {row.zotero_uri} | Zotero: {zuri}", row.url, zuri))
        for prop in ("category", "subcategory", "tag"):
            missing = [v for v in d[prop] if v not in getattr(row, prop)]
            if missing:
                m.additions[prop] = missing
        plan.matched.append(m)

    for r in rows:
        if r.page_id in used:
            continue
        if not r.title and not r.doi_link:
            kind = "empty"
        elif r.doi_link and not row_doi[r.page_id]:
            kind = "no_doi_link"      # e.g. Google Drive link
        else:
            kind = "not_in_zotero"
        plan.orphans.append((r, kind))
        plan.issues.append(Issue(
            "orphan_" + kind, r.title or "(no title)",
            r.doi_link or "", r.url))

    return plan
