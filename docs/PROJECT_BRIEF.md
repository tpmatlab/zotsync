# Project brief: Zotero ↔ Notion (PETR-PC bibliographic review)

Handover document. State as of **2026-11-21**. Read it in full before changing code.
User-facing chat stays in Brazilian Portuguese; code, comments and commit messages are in English.

## 1. Goal

Keep **a single source** for the bibliographic data of the cement paste review (Petrobras
project, TPMaT/UFSCar group), eliminating the double maintenance between a Zotero group and a
Notion database.

- **Zotero** is the source of truth for bibliographic data (authors, year, journal, DOI, collections, tags).
- **Notion** is the analytical layer of the review (Read, Checked, Priority, Results, Conclusions etc.),
  filled in by hand by the group. It is **never** overwritten by the sync.

Notero was evaluated and discarded: it does not map custom properties, does not recognize
existing rows (it would duplicate them), and its compatibility with Zotero groups is uncertain.

## 2. Systems and identifiers (none is a secret)

| Item | Value |
|---|---|
| Zotero group id | `6740929` |
| Notion database | "PETR-PC — Bibliographic Review" (workspace TPMaT-PETR-PC, dentro de Docs) |
| Notion database URL | https://app.notion.com/p/3c16be63f63f8050b3d8cab82bf098a7 |
| Notion data source id | `3c16be63-f63f-80c9-ab12-000b9bb2a0c1` |
| Notion database id | `3c16be63-f63f-8050-b3d8-cab82bf098a7` |

Secrets (never in code, never in the repository; environment variables / GitHub secrets, or a
git-ignored `.env` file, see `.env.example`):
`ZOTERO_API_KEY` (read-only), `ZOTERO_GROUP_ID`, `NOTION_TOKEN` (internal integration,
shared **only** with this database), `NOTION_DATA_SOURCE_ID`.

## 3. Ownership of each field (core rule)

| Notion property | Type | Owner | Sync rule |
|---|---|---|---|
| Paper title | title | Zotero | written **only when the row is created**; never changed afterwards |
| Authors | rich text | Zotero | format `First Last; First Last` (see §5) |
| Year | number | Zotero | fill if empty; divergence goes to the report |
| Journal | rich text | Zotero | same |
| DOI link | url | Zotero | canonical form `https://doi.org/<doi>`; see §6 |
| Zotero URI | text | Zotero | fill if empty; divergence goes to the report |
| Modified | date | Zotero | fill only if empty; divergence goes to the report; value = Zotero `dateModified` of the canonical item |
| Category | multi-select | Zotero | top-level collection; **union**, never removes existing values |
| Subcategory | multi-select | Zotero | child collection; **union**, never removes |
| Tag | multi-select | Zotero | mirrors the Zotero tags; **internal comment, no action** |
| Read, Checked | checkbox | Notion (human) | on new rows: **unchecked**; never touched afterwards |
| Priority, Cement Type, Type of modelling, Methods, Results, Conclusions, Notes / Key findings | various | Notion (human) | **never** touched |
| Added | created_time | system | read-only |

Schema notes: the `Type of modelling ` property has a **trailing space** in its name; `Category` has
the option `Mechanical Integraty` (misspelled, identical in Zotero: only rename on both sides together);
select option names **cannot contain a comma** in Notion.

## 3.1 Zotero collection mapping

Collection `A` → Category `A`. Collection `A / B` → Category `A` **and** Subcategory `B`.
Today the Zotero collections are: Modelling, XCT, TENCIM papers, Method of Analysis, Machine Learning,
T & P Effects, Mechanical Integraty, Concetual Basis, and the parent
`Numerical models for cement paste simulation` with children `Poromechanical models` and
`Continuum thermomechanical models`.

- The user will fix "Concetual Basis" → "Conceitual Basis" in Zotero before the next run (Notion already uses the correct spelling).
- The Category option `Numerical models for cement paste simulation` does **not exist yet** in Notion;
  the Notion API creates new options on write. The Subcategory options have already been created.
- Item in several collections → all the corresponding Categories/Subcategories.

## 4. Zotero export format (`zotsync.reader.Reference`)

`key, version, item_type, title, authors ("Last, First" or institutional name), year, publication,
doi (normalized), url, abstract, tags, collections ("Parent / Child" paths), has_pdf, zotero_uri,
date_modified`. The CLI writes `data/zotero_refs.json` with `library_version`, `group_id`, `items`.

## 5. Author conversion

Notion currently uses `First Last; First Last` (real example: `Giuseppe Sciumè; Murilo Henrique Moreira;
Stefano Dal Pont`). Zotero delivers `Last, First`. Convert by swapping around the comma; institutional
names (no comma) are kept as they are. Notion limit: 2000 characters per rich text chunk →
truncate with `…` and record it in the report.

## 6. Zotero ↔ Notion matching

Order of precedence (see skill `zotero-notion-match`):

1. **Normalized DOI** (skill `doi-normalization`).
2. **Normalized title** (lowercase, no punctuation/accents, collapsed spaces, line breaks → space)
   **only** for Notion rows without a usable DOI (Drive link, empty, DOI missing in Zotero).
3. No match → "new" (Zotero only) or "orphan" (Notion only). **An orphan is never deleted.**

One DOI = one Notion row. If Zotero has several copies of the same DOI (9 cases today), use the
**union** of collections/tags and pick a canonical item (the one with the highest `version`).

Notion rows with a Google Drive link in the "DOI link" field: **do not overwrite** the link (it keeps
the PDF access); if they match by title, only fill Authors/Year/Journal and report the suggested DOI.

## 7. Data state (measured on 2026-11-21)

- Zotero: 160 items → **151 unique DOIs**; 9 duplicated DOIs (copies in different collections, 2 without collection); 1 item with tag `Remover`; 55 with PDF.
- Notion: **143 rows**; 138 with something in "DOI link"; only 1 row had Authors/Journal; 57 with Year; 57 with Results; 15 Checked.
- Match by DOI: **109 Zotero DOIs already exist in Notion** (111 rows; 2 DOIs appear in 2 Notion rows: `10.1016/j.cemconres.2010.03.014` and `10.1016/j.cemconres.2022.106776`).
- **42 DOIs only in Zotero** (become new rows, with Read/Checked unchecked).
- **32 Notion rows with no DOI match**: 20 with a Drive link, 5 completely empty (no title), 7 with a DOI/link that is not in Zotero (e.g. Chinese journals, ASCE `…0003624`, an onepetro link).
- "DOI link" formats in Notion are heterogeneous: `https://doi.org/…`, `http://dx.doi.org/…`, `doi.org/…` without scheme,
  `doi.org/ 10.…` with a space, `…?utm_source=chatgpt.com`, bare DOI `10.xxxx/…`.
- At least one paper appears in two rows (one with Drive, another with DOI), e.g. "Thermo-hygro-chemical model of concrete".

## 8. Decisions already made by the user

1. Category comes from the Zotero top-level collections; **Subcategory** (new column, multi-select) comes from the child collections.
2. The spelling "Concetual Basis" will be fixed in Zotero by the user.
3. **Tag** column (new, multi-select) in Notion = Zotero tags; it is an internal comment; **no automatic action** (including for `Remover`).
4. The 42 new rows are created with **Read** and **Checked** unchecked.
5. The script must run **without depending on Claude** (own Notion token; scheduled GitHub Action).
6. Already done in Notion (2026-11-21): `Subcategory` and `Tag` columns created.

## 9. Open questions (assume the indicated default and flag it to the user)

| Question | Safe default |
|---|---|
| Zotero/Notion divergence in already-filled Year/Journal | **do not overwrite**; list in the report; optional `--overwrite-bibliographic` flag |
| Category/Subcategory on existing rows | **union** (only add) |
| Add a `Zotero URI` (text) column in Notion for stable identity | recommended; **ask for confirmation** before changing the schema |
| Completely empty rows (5) | report; **do not delete** |
| Duplicate rows in Notion (same DOI) | report; **do not merge** |

## 10. Roadmap

Steps 2–4 are implemented: `notion_reader`, matcher/report (`python -m zotsync.plan_cli`) and
`notion_writer` (`python -m zotsync.write_cli` with `--apply`, `--limit`, `--only`,
`--overwrite-bibliographic`). Secrets can live in a git-ignored `.env` (see `.env.example`);
environment variables take precedence.

| # | Step | Done when |
|---|---|---|
| 0 | Read Zotero → JSON, overview notebook | ✅ done |
| 1 | User merges duplicates in Zotero and fixes "Concetual Basis"; runs the fetch again | new `zotero_refs.json`, no DOIs with a truncated `)` |
| 2 | `notion_reader.py`: reads all rows of the data source (paginated) into Python structures | test with mocked responses |
| 3 | `matcher.py` + `report.py`: DOI→title matching, CSV/Markdown report (matched, new, orphans, duplicates, conflicts) | **dry-run**, nothing written; user reviews |
| 4 | `notion_writer.py`: fill Zotero-owned fields on matched rows; create the new ones; explicit `--apply` | dry-run by default; tests cover "never touches human fields" |
| 5 | Autonomous run: GitHub Action (cron + manual), secrets, report as artifact | first real run with report |
| 6 | (optional) `Zotero URI` column; rename "Mechanical Integraty" on both sides | user decision |

## 11. Known pitfalls

- **Trailing-parenthesis bug in DOIs** (fixed on 2026-11-21): ASCE/ACI DOIs legitimately end in `)`, e.g.:
  `10.1061/(asce)0733-9399(1994)120:12(2519)`. Only strip a trailing `)` if it is unbalanced.
- Notion API version 2025-09-03+: pages are created with parent `data_source_id`; check the current
  documentation before writing. Average limit ~3 requests/s; handle 429 with *backoff*.
- Notion "url" values: validate that they start with `http`.
- Claude's environment could not reach `api.zotero.org`; the fetch runs on the user's machine/CI.
- `Type of modelling ` with a trailing space; `Numerial` (misspelled) is an existing option: do not "fix" without asking.

## 12. Development conventions

Python ≥ 3.10, `src/zotsync/`, tests in `tests/` (`pytest`), no network in tests (mocked responses),
pure functions for normalization/matching, I/O isolated in thin modules. Every command that writes to
Notion has `--apply` and first prints a summary of what would change. Small commits, in English.
