# AGENTS.md

Project: sync a Zotero group (read-only) into a structured Notion database for a bibliographic review.

**Read `docs/PROJECT_BRIEF.md` first.** It holds the schema, field ownership, matching rules, decisions and roadmap.

## Hard rules

1. Never write to Zotero. Never delete, archive or merge Notion pages.
2. Never modify human-owned Notion fields (Read, Checked, Priority, Cement Type, Type of modelling, Methods, Results, Conclusions, Notes / Key findings). On new rows, Read and Checked are created unchecked.
3. Every command that writes to Notion is dry-run by default and requires `--apply`.
4. No secrets in code, logs, notebooks or commits. Use `ZOTERO_API_KEY`, `ZOTERO_GROUP_ID`, `NOTION_TOKEN`, `NOTION_DATA_SOURCE_ID` from the environment.
5. Match by normalized DOI first, then normalized title (only for Notion rows without a usable DOI). Never create a second row for a DOI that already exists.
6. If a requirement is ambiguous or touches the Notion schema, ask the user instead of guessing.

## Language

Talk to the user in Brazilian Portuguese. Code, comments, docstrings and commit messages in English.

## Commands

```
pip install -e ".[dev]"
pytest -q
python -m zotsync.cli --out data/zotero_refs.json     # needs ZOTERO_* env vars
```
