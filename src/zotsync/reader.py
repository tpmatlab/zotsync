"""Read-only access to a Zotero group via the Web API.

Nothing here writes to Zotero. The output is a list of `Reference`, a neutral
format consumed by the Notion steps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Iterable
from urllib.parse import unquote

# Item types that are not bibliographic references themselves.
NON_REFERENCE_TYPES = {"attachment", "note", "annotation"}

_DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)
_YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")


@dataclass
class Reference:
    key: str                      # Zotero key (stable within the library)
    version: int                  # item version (for incremental sync)
    item_type: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    publication: str = ""         # journal / book / event
    doi: str = ""                 # normalized: lowercase, no URL prefix
    url: str = ""
    abstract: str = ""
    tags: list[str] = field(default_factory=list)
    collections: list[str] = field(default_factory=list)  # nomes, com caminho "A / B"
    has_pdf: bool = False
    zotero_uri: str = ""          # zotero://select/groups/<id>/items/<key>
    date_modified: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_doi(raw: str | None) -> str:
    """Extract and normalize a DOI (accepts URLs, 'doi:' etc.). Empty if none."""
    if not raw:
        return ""
    m = _DOI_RE.search(raw.strip())
    if not m:
        return ""
    doi = m.group(0)
    for sep in ("?", "#"):          # tracking/query suffixes, e.g. ?utm_source=...
        doi = doi.split(sep, 1)[0]
    doi = unquote(doi).rstrip(".,;").lower()
    # Only strip a trailing ")" if it is stray punctuation; ASCE/ACI DOIs legitimately end in ")".
    while doi.endswith(")") and doi.count(")") > doi.count("("):
        doi = doi[:-1]
    return doi


def parse_year(date: str | None) -> int | None:
    if not date:
        return None
    m = _YEAR_RE.search(date)
    return int(m.group(1)) if m else None


def format_creator(c: dict) -> str:
    if c.get("name"):  # single-field creator (institution)
        return c["name"].strip()
    last, first = c.get("lastName", "").strip(), c.get("firstName", "").strip()
    return f"{last}, {first}" if last and first else (last or first)


def build_collection_paths(collections: Iterable[dict]) -> dict[str, str]:
    """Map collection key -> readable path ('Parent / Child')."""
    by_key = {c["key"]: c["data"] for c in collections}

    def path(key: str, seen: frozenset = frozenset()) -> str:
        data = by_key[key]
        parent = data.get("parentCollection")
        if parent and parent in by_key and parent not in seen:
            return f"{path(parent, seen | {key})} / {data['name']}"
        return data["name"]

    return {k: path(k) for k in by_key}


def normalize_items(
    raw_items: Iterable[dict],
    collection_paths: dict[str, str],
    group_id: int | str,
) -> list[Reference]:
    """Convert raw Zotero JSON into `Reference`, joining child PDFs."""
    raw_items = list(raw_items)

    parents_with_pdf = {
        it["data"]["parentItem"]
        for it in raw_items
        if it["data"].get("itemType") == "attachment"
        and it["data"].get("parentItem")
        and it["data"].get("contentType") == "application/pdf"
    }

    refs: list[Reference] = []
    for it in raw_items:
        d = it["data"]
        if d.get("itemType") in NON_REFERENCE_TYPES:
            continue
        # Trashed items carry `deleted`; skip them.
        if d.get("deleted"):
            continue

        # The DOI has its own field for most types; for some (e.g. preprint)
        # it may be in "extra" as "DOI: ...".
        doi = normalize_doi(d.get("DOI")) or normalize_doi(d.get("extra"))
        creators = [
            format_creator(c)
            for c in d.get("creators", [])
            if c.get("creatorType") in (None, "author", "editor", "contributor")
        ]
        refs.append(
            Reference(
                key=d["key"],
                version=d.get("version", it.get("version", 0)),
                item_type=d["itemType"],
                title=(d.get("title") or d.get("bookTitle") or "").strip(),
                authors=[c for c in creators if c],
                year=parse_year(d.get("date")),
                publication=(
                    d.get("publicationTitle")
                    or d.get("bookTitle")
                    or d.get("proceedingsTitle")
                    or d.get("repository")
                    or ""
                ).strip(),
                doi=doi,
                url=d.get("url", "").strip(),
                abstract=d.get("abstractNote", "").strip(),
                tags=sorted({t["tag"] for t in d.get("tags", []) if t.get("tag")}),
                collections=sorted(
                    collection_paths[k] for k in d.get("collections", []) if k in collection_paths
                ),
                has_pdf=d["key"] in parents_with_pdf,
                zotero_uri=f"zotero://select/groups/{group_id}/items/{d['key']}",
                date_modified=d.get("dateModified", ""),
            )
        )
    return refs


def fetch_group(
    group_id: int | str,
    api_key: str,
    collection_name: str | None = None,
    since_version: int | None = None,
) -> tuple[list[Reference], int]:
    """Download the whole group (paginated); return (references, library version).

    collection_name: if given, keep only items in that collection (or subcollections).
    since_version: if given, only items changed after that version (incremental sync).
    """
    from pyzotero import zotero  # late import: tests don't need the lib

    zot = zotero.Zotero(group_id, "group", api_key)
    kwargs = {"since": since_version} if since_version is not None else {}
    raw = zot.everything(zot.items(**kwargs))
    paths = build_collection_paths(zot.everything(zot.collections()))
    library_version = int(zot.last_modified_version())

    refs = normalize_items(raw, paths, group_id)
    if collection_name:
        refs = [
            r for r in refs
            if any(c == collection_name or c.startswith(collection_name + " / ") for c in r.collections)
        ]
    return refs, library_version
