# zotero-notion-sync

Step 1: **read-only** fetch of a Zotero group → local JSON.
Step 2 (to do): push that JSON to the Notion database.

## Setup

    pip install -r requirements.txt
    export ZOTERO_API_KEY=...      # zotero.org/settings/keys (permission: read-only)
    export ZOTERO_GROUP_ID=...     # number in the group URL: zotero.org/groups/<ID>/...

## Usage

    PYTHONPATH=src python -m zotsync.cli --out data/zotero_refs.json
    PYTHONPATH=src python -m zotsync.cli --collection "Review cimento"
    PYTHONPATH=src python -m zotsync.cli --since 1234   # incremental

The printed summary shows how many references have no DOI and how many DOIs
are repeated — useful to decide the join key with Notion before step 2.

## Dry-run against Notion (read-only)

Secrets: copy `.env.example` to `.env` (git-ignored) and fill it in; environment
variables that are already set take precedence.

    python -m zotsync.plan_cli --save-notion-snapshot data/notion_rows.json
    python -m zotsync.plan_cli --notion-snapshot data/notion_rows.json   # offline, reuses the snapshot

Writes to `reports/` (git-ignored): `todo_conflicts.md` (checklist for Obsidian),
`summary.md` and `matches.csv`. Nothing is written to Notion.

## Writing to Notion (dry-run by default)

    python -m zotsync.write_cli                     # only shows what would change
    python -m zotsync.write_cli --apply --limit 5   # writes only the first 5 operations
    python -m zotsync.write_cli --apply             # writes everything
    # optional: --overwrite-bibliographic replaces diverging Year/Journal/Authors

Only fills empty fields, unions Category/Subcategory/Tag and creates new rows (Read/Checked
unchecked). Never touches human-owned fields and never deletes pages.

## Tests (offline)

    PYTHONPATH=src pytest -q

## Notes

- Planned join key: normalized DOI; fallback = Zotero key.
- `fetch_group` downloads everything in one paginated call (items + collections) and links
  PDFs to their parent items locally, without one request per item.
- The API key never goes in the code or the repository.

## For whoever continues (Copilot or a person)

Read `docs/PROJECT_BRIEF.md` (context, rules, decisions, roadmap) and `AGENTS.md`.
Copilot instructions: `.github/copilot-instructions.md`; skills in `.github/skills/`.
Install: `pip install -e ".[dev]"` and `pytest -q`.
