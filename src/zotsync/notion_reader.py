"""Read-only access to the Notion data source: pages -> `NotionRow`.

Nothing here writes to Notion. HTTP is isolated in `fetch_pages`; parsing is pure
so it can be tested with simulated responses.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

NOTION_VERSION = "2025-09-03"
API_BASE = "https://api.notion.com/v1"

# Property names are exact; "Type of modelling " (trailing space) is never read here.
P_TITLE = "Paper title"
P_AUTHORS = "Authors"
P_YEAR = "Year"
P_JOURNAL = "Journal"
P_DOI = "DOI link"
P_CATEGORY = "Category"
P_SUBCATEGORY = "Subcategory"
P_TAG = "Tag"
P_ZOTERO_URI = "Zotero URI"
P_MODIFIED = "Modified"
P_READ = "Read"
P_CHECKED = "Checked"


@dataclass
class NotionRow:
    page_id: str
    url: str = ""
    title: str = ""
    authors: str = ""
    year: int | None = None
    journal: str = ""
    doi_link: str = ""
    category: list[str] = field(default_factory=list)
    subcategory: list[str] = field(default_factory=list)
    tag: list[str] = field(default_factory=list)
    zotero_uri: str = ""
    modified: str = ""
    read: bool = False
    checked: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _text(prop: dict | None) -> str:
    if not prop:
        return ""
    parts = prop.get("title") or prop.get("rich_text") or []
    return "".join(p.get("plain_text", "") for p in parts).strip()


def _names(prop: dict | None) -> list[str]:
    if not prop:
        return []
    return [o["name"] for o in prop.get("multi_select") or [] if o.get("name")]


def _url_or_text(prop: dict | None) -> str:
    """Zotero URI may be a url or a rich-text property; accept both."""
    if not prop:
        return ""
    return (prop.get("url") or _text(prop) or "").strip()


def parse_page(page: dict) -> NotionRow:
    props: dict[str, Any] = page.get("properties", {})
    year = (props.get(P_YEAR) or {}).get("number")
    return NotionRow(
        page_id=page["id"],
        url=page.get("url", ""),
        title=_text(props.get(P_TITLE)),
        authors=_text(props.get(P_AUTHORS)),
        year=int(year) if year is not None else None,
        journal=_text(props.get(P_JOURNAL)),
        doi_link=((props.get(P_DOI) or {}).get("url") or "").strip(),
        category=_names(props.get(P_CATEGORY)),
        subcategory=_names(props.get(P_SUBCATEGORY)),
        tag=_names(props.get(P_TAG)),
        zotero_uri=_url_or_text(props.get(P_ZOTERO_URI)),
        modified=((props.get(P_MODIFIED) or {}).get("date") or {}).get("start") or "",
        read=bool((props.get(P_READ) or {}).get("checkbox")),
        checked=bool((props.get(P_CHECKED) or {}).get("checkbox")),
    )


def parse_pages(pages: Iterable[dict]) -> list[NotionRow]:
    return [parse_page(p) for p in pages if not p.get("in_trash") and not p.get("archived")]


def request(method: str, url: str, token: str, body: dict, retries: int = 5) -> dict:
    data = json.dumps(body).encode()
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(float(e.headers.get("Retry-After", 2 ** attempt)))
                continue
            raise
    raise RuntimeError("unreachable")


def fetch_pages(token: str, data_source_id: str) -> list[dict]:
    """Query every page of the data source (paginated). Read-only."""
    pages: list[dict] = []
    cursor: str | None = None
    while True:
        body: dict[str, Any] = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = request("POST", f"{API_BASE}/data_sources/{data_source_id}/query", token, body)
        pages.extend(resp.get("results", []))
        if not resp.get("has_more"):
            return pages
        cursor = resp.get("next_cursor")
        time.sleep(0.35)  # ~3 requests/s


def fetch_rows(token: str, data_source_id: str) -> list[NotionRow]:
    return parse_pages(fetch_pages(token, data_source_id))
