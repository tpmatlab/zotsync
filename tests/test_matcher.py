from zotsync.matcher import authors_to_notion, build_plan, categories_for, normalize_title
from zotsync.notion_reader import NotionRow, parse_page
from zotsync.reader import Reference
from zotsync.report import render_todo


def ref(key, doi="", title="T", year=2020, pub="Cement and Concrete Research",
        authors=("Silva, Ana",), colls=(), tags=(), version=1):
    return Reference(key=key, version=version, item_type="journalArticle", title=title,
                     authors=list(authors), year=year, publication=pub, doi=doi,
                     collections=list(colls), tags=list(tags),
                     zotero_uri=f"zotero://select/groups/1/items/{key}")


def row(pid, title="", doi="", **kw):
    return NotionRow(page_id=pid, url=f"https://notion.so/{pid}", title=title, doi_link=doi, **kw)


def test_authors_and_categories():
    assert authors_to_notion(["Sciumè, Giuseppe", "Instituto X"]) == ("Giuseppe Sciumè; Instituto X", False)
    text, trunc = authors_to_notion(["Aaa, Bbb"] * 500)
    assert trunc and len(text) == 2000 and text.endswith("…")
    assert categories_for(["XCT", "Num / Poro", "Num / Cont"]) == (["XCT", "Num"], ["Poro", "Cont"])


def test_doi_match_fills_only_empty_and_reports_conflicts():
    refs = [ref("A", doi="10.1000/a", year=2020, pub="Cem Concr Res", colls=["XCT"], tags=["x"])]
    rows = [row("1", "t", "http://dx.doi.org/10.1000/A", year=2019, journal="Other Journal")]
    plan = build_plan(refs, rows)
    m = plan.matched[0]
    assert m.method == "doi"
    assert "year" not in m.fills and "journal" not in m.fills
    assert m.fills["authors"] == "Ana Silva"
    assert m.additions == {"category": ["XCT"], "tag": ["x"]}
    kinds = {i.kind for i in plan.issues}
    assert {"conflict_year", "conflict_journal"} <= kinds


def test_equal_after_normalization_is_not_a_conflict():
    refs = [ref("A", doi="10.1000/a", pub="Cement & Concrete Research")]
    rows = [row("1", "t", "https://doi.org/10.1000/a", year=2020, journal="cement concrete research",
                authors="ana silva")]
    assert build_plan(refs, rows).issues == []


def test_title_match_preserves_drive_link_and_suggests_doi():
    refs = [ref("A", doi="10.1000/a", title="Thermo-hygro model")]
    rows = [row("1", "Thermo hygro  model", "https://drive.google.com/file/d/xyz")]
    plan = build_plan(refs, rows)
    assert plan.matched[0].method == "title"
    assert "doi_link" not in plan.matched[0].fills
    assert [i.kind for i in plan.issues] == ["doi_suggestion"]


def test_duplicates_new_and_orphans_are_report_only():
    refs = [ref("A", doi="10.1000/a"), ref("B", doi="10.1000/b", tags=["Remover"])]
    rows = [row("1", "x", "10.1000/a"), row("2", "y", "https://doi.org/10.1000/a"), row("3")]
    plan = build_plan(refs, rows)
    assert not plan.matched and len(plan.duplicate_rows) == 1
    assert [n.group.doi for n in plan.new] == ["10.1000/b"]
    assert not plan.new[0].read and not plan.new[0].checked
    assert [k for _, k in plan.orphans] == ["empty"]
    todo = render_todo(plan, "2026-11-21")
    assert "- [ ]" in todo and "[Notion](https://notion.so/1)" in todo


def test_zotero_copies_are_merged_with_union():
    refs = [ref("A", doi="10.1000/a", colls=["XCT"], version=1), ref("B", doi="10.1000/a", colls=["Modelling"], version=2)]
    plan = build_plan(refs, [])
    assert len(plan.new) == 1 and plan.new[0].category == ["Modelling", "XCT"]
    assert plan.new[0].group.canonical.key == "B"


def test_parse_page():
    page = {"id": "p", "url": "u", "properties": {
        "Paper title": {"title": [{"plain_text": "Hi"}]},
        "Year": {"number": 2001},
        "DOI link": {"url": "https://doi.org/10.1000/a"},
        "Category": {"multi_select": [{"name": "XCT"}]},
        "Read": {"checkbox": True}}}
    r = parse_page(page)
    assert (r.title, r.year, r.category, r.read, r.checked) == ("Hi", 2001, ["XCT"], True, False)
    assert normalize_title("Ação\nTérmica!") == "acao termica"


def test_zotero_uri_filled_when_empty_and_conflict_when_foreign(tmp_path):
    refs = [ref("A", doi="10.1000/a")]
    empty = build_plan(refs, [row("1", "t", "10.1000/a")])
    assert empty.matched[0].fills["zotero_uri"] == "zotero://select/groups/1/items/A"
    ok = build_plan(refs, [row("1", "t", "10.1000/a", zotero_uri="zotero://select/groups/1/items/A")])
    assert "zotero_uri" not in ok.matched[0].fills and not ok.issues
    bad = build_plan(refs, [row("1", "t", "10.1000/a", zotero_uri="zotero://select/groups/1/items/Z")])
    assert [i.kind for i in bad.issues] == ["conflict_zotero_uri"]


def test_load_env_does_not_override_and_ignores_unknown(tmp_path, monkeypatch):
    from zotsync.config import load_env
    f = tmp_path / ".env"
    f.write_text("NOTION_TOKEN=abc\nZOTERO_GROUP_ID='1'\nOTHER=x\n# c\n")
    monkeypatch.setenv("ZOTERO_GROUP_ID", "keep")
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    assert load_env(f) == ["NOTION_TOKEN"]
    import os
    assert os.environ["ZOTERO_GROUP_ID"] == "keep" and "OTHER" not in os.environ
    monkeypatch.delenv("NOTION_TOKEN")


def test_writer_never_touches_human_fields_and_keeps_existing_options():
    from zotsync.notion_writer import WRITABLE_CREATE, build_create, build_operations, build_update
    refs = [ref("A", doi="10.1000/a", year=2020, colls=["XCT"], tags=["x"]),
            ref("B", doi="10.1000/b", colls=["Num / Poro"])]
    rows = [row("1", "t", "10.1000/a", year=2019, journal="Other", category=["Old"])]
    plan = build_plan(refs, rows)
    m = plan.matched[0]
    upd = build_update(m)
    assert "Year" not in upd and "Journal" not in upd and "Paper title" not in upd
    assert [o["name"] for o in upd["Category"]["multi_select"]] == ["Old", "XCT"]
    forced = build_update(m, overwrite_bibliographic=True)
    assert forced["Year"] == {"number": 2020} and "Paper title" not in forced
    create = build_create(plan.new[0], "ds")
    assert create["parent"] == {"type": "data_source_id", "data_source_id": "ds"}
    props = create["properties"]
    assert props["Read"] == {"checkbox": False} and props["Checked"] == {"checkbox": False}
    assert set(props) <= WRITABLE_CREATE
    assert not ({"Priority", "Cement Type", "Methods", "Results", "Conclusions"} & set(props))
    ops = build_operations(plan, "ds")
    assert len(ops.updates) == 1 and len(ops.creates) == 1


def test_modified_filled_when_empty_and_conflict_when_different():
    r = ref("A", doi="10.1000/a")
    r.date_modified = "2026-11-20T20:52:29Z"
    empty = build_plan([r], [row("1", "t", "10.1000/a")])
    assert empty.matched[0].fills["modified"] == "2026-11-20T20:52:29Z"
    same = build_plan([r], [row("1", "t", "10.1000/a", modified="2026-11-20T20:52:29.000+00:00")])
    assert "modified" not in same.matched[0].fills and not [i for i in same.issues if i.kind == "conflict_modified"]
    diff = build_plan([r], [row("1", "t", "10.1000/a", modified="2026-01-01T00:00:00.000+00:00")])
    assert "conflict_modified" in [i.kind for i in diff.issues] and "modified" not in diff.matched[0].fills
    from zotsync.notion_writer import build_update
    assert build_update(empty.matched[0])["Modified"] == {"date": {"start": "2026-11-20T20:52:29Z"}}
