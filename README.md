# Big Red Flags

Public figures named in the Epstein files and in other high-profile scandals, checked for college, Ivy League, fraternity/sorority and college society/club ties. Live site: **https://grmpyktn11.github.io/big-red-flags/**

- **Web** (`docs/index.html`, home page): full-screen network of people linked by the colleges, fraternities and clubs they share. Filters, search, shareable `#links`.
- **List** (`docs/list.html`): searchable table of every person.
- **Sources** (`docs/sources.html`): method, data sources, source links per person, exclusions.

Being named in these documents does not imply wrongdoing.

## Architecture

```
Wikipedia API ─┐
Wikidata SPARQL┼─► pipeline/run.py ─► docs/data/people.json ─┐
data/ (manual) ┘   (GitHub Action)    docs/data/graph.json   ├─► docs/*.html (static site, D3 in the browser)
                                      docs/data/excluded.json┘
```

No server and no database: a weekly GitHub Action runs the Python pipeline, commits JSON to `docs/data/`, and GitHub Pages serves `docs/`.

| Path | Role |
|---|---|
| `pipeline/run.py` | Orchestrates every step and writes the JSON |
| `pipeline/common.py` | HTTP: User-Agent, retries, 429 `Retry-After`, POST for long batches |
| `pipeline/scrape_names.py` | Parses the Wikipedia list of people named in the Epstein files |
| `pipeline/enrich.py` | Resolves titles, fetches pages and Wikidata facts, detects Ivy schools and fraternities |
| `pipeline/orgs.py` | Catalog of college societies/clubs and their text detection |
| `pipeline/member_lists.py` | Reverse lookup in Wikipedia member lists of fraternities, sororities, societies and clubs |
| `pipeline/graph.py` | Normalizes colleges and builds the network (`graph.json`) |
| `data/` | Manual inputs and corrections (see below) |
| `tests/test_pipeline.py` | Offline tests; the Action stops if any fail |
| `.github/workflows/update.yml` | Weekly/on-change pipeline run and commit |

### Pipeline steps

1. **Names**: Epstein-files names from [Wikipedia's list](https://en.wikipedia.org/wiki/List_of_people_named_in_the_Epstein_files), plus `data/extra_names.txt` and `data/scandals.json`.
2. **Resolve** each name to its Wikipedia article (redirects, disambiguation pages, search fallback).
3. **Fetch** article text, categories, description and Wikidata ID; query Wikidata for *human* (P31), *educated at* (P69), *member of* (P463) and *employer* (P108).
4. **Member lists**: match people against "List of … members" pages and "notable members" sections (first link on each line only; honorary members skipped).
5. **Filter** out non-people, victims/survivors, Epstein's staff and `data/exclude.txt` entries (logged to `excluded.json`).
6. **Detect**
   - **Ivy League** per school, grad schools included: *yes* from Wikidata or alumni categories; *possible* from an attendance word near the school's name. Honorary degrees, relatives' schooling and false claims are ignored. Faculty only from categories or Wikidata employer.
   - **Fraternities/sororities**: Wikidata, categories, member lists, or article text with a Greek-letter name plus membership wording. Chapter names and honor societies are not counted.
   - **Societies and clubs** (secret societies, final/eating clubs, student papers, political groups, honor societies): catalog in `orgs.py`, same rules plus a check that the person attended that school.
7. **Merge** in `data/overrides.json` and `data/manual_people.json` (these always win).
8. **Graph**: people link to shared colleges, fraternities and clubs; grad schools fold into the parent university; non-Ivy colleges appear only when 2+ people share them; only status *yes* becomes a link.

Statuses: **yes** (structured data or verified) · **possible** (text match, not on the map until confirmed) · **no** · **unknown** (researched, no source found).

## How to add or change things

Edit files in `data/` (or `pipeline/`), commit and push. The Action re-runs the pipeline and the site updates in a few minutes. Check the **Actions** tab; if a run fails, the error is saved to `docs/data/last_run.log`.

### Add a person from the Epstein files

Add their exact Wikipedia article title to `data/extra_names.txt`, with the document types after `|`:

```
Jane Doe (businesswoman) | flight logs, emails
```

### Add a person from another scandal

Add an entry to `data/scandals.json`:

```json
{"title": "Jane Doe (businesswoman)", "case": "Doe fraud case", "outcome": "Convicted of wire fraud (2024)"}
```

Use the Wikipedia title (check the article URL). Keep `outcome` to what is on the public record: conviction, guilty plea, resignation or firing.

### Add a person who has no Wikipedia article

Add a record to `data/manual_people.json`:

```json
{
  "name": "Jane Doe",
  "description": "Surgeon, Example Hospital",
  "education": ["Columbia University (MD)"],
  "schools": {"Columbia": {"status": "yes", "evidence": [
    {"source": "Hospital profile", "text": "MD, Columbia University", "url": "https://…"}]}},
  "school_sources": [{"source": "Hospital profile", "url": "https://…"}],
  "frat": {"status": "unknown"},
  "orgs": [],
  "note": "optional"
}
```

School keys: `Brown`, `Columbia`, `Cornell`, `Dartmouth`, `Harvard`, `Penn`, `Princeton`, `Yale`. Add `"faculty": true` for faculty/staff.

### Remove a person

Add their Wikipedia title and a reason to `data/exclude.txt`:

```
Jane Doe | private individual
```

If the automatic victim/staff filter removed someone by mistake, add them to `data/include.txt` the same way.

### Fix or confirm a result

Add an entry to `data/overrides.json`, keyed by the person's name exactly as it appears in `docs/data/people.json`. Every field is optional:

```json
"Jane Doe (businesswoman)": {
  "schools": {
    "Yale": {"status": "no", "faculty": false},
    "Cornell": {"status": "yes", "evidence": [{"source": "…", "text": "…", "url": "https://…"}]}
  },
  "frat": {"status": "yes", "orgs": ["Sigma Chi"],
           "evidence": [{"source": "…", "text": "…", "url": "https://…"}]},
  "orgs": [
    {"name": "Skull and Bones", "status": "yes"},
    {"name": "Cap and Dagger", "kind": "club", "school": "Bucknell", "status": "yes",
     "evidence": [{"source": "…", "text": "…", "url": "https://…"}]}
  ],
  "orgs_remove": ["The Harvard Crimson"],
  "note": "Shown on the site.",
  "verified": true
}
```

- `schools`: set `"status": "no"` to remove a wrong Ivy match, `"yes"` to confirm one.
- `frat.orgs` replaces the detected fraternity list.
- `orgs` adds a society/club or confirms a *possible* one (possible matches only appear on the map once set to `yes`). `kind` is one of `society`, `club`, `publication`, `political`, `honor`.
- `orgs_remove` drops wrongly detected orgs.
- `verified: true` shows the ✓ on the site.

To review new matches after a run, look in `docs/data/people.json` for `"status": "possible"`, then confirm or remove each one with an override.

### Track a new society or club

1. Add it to `ORGS` in `pipeline/orgs.py`: `(name, kind, school, regex)`, e.g.
   `("Book and Snake", "society", "Yale", r"Book and Snake")`.
   Use a specific regex; `school` limits matches to people who attended that school (`None` for any school).
2. If Wikipedia has an article with a members section, add it to `ORG_ARTICLES` in `pipeline/member_lists.py`: `"Book and Snake": "Book and Snake"`.
3. To add a fraternity or sorority, add its name to `GREEK_ORGS` in `pipeline/member_lists.py`. Its "List of … members" page is found automatically.

### Treat another grad school as part of its university, or hide a school

Edit `PARENTS` (grad school → university) or `SECONDARY_RE` (schools to drop, such as high schools) in `pipeline/graph.py`.

### Change the site

- Colors (light and dark): CSS variables at the top of `docs/assets/site.css`.
- Map (layout, filters, panels, search): `docs/index.html`.
- Table: `docs/list.html`. Method text: `docs/sources.html`.

No build step: edit and push. Site-only changes do not trigger the pipeline.

### Run it yourself

```bash
pip install -r requirements.txt
python -m pytest -q tests         # offline tests
python pipeline/run.py            # needs internet; writes docs/data/*.json
python -m http.server -d docs     # open http://localhost:8000
```

Or run it on GitHub without code changes: **Actions** → **Update data** → **Run workflow**.

## Automation

`.github/workflows/update.yml` runs every Monday at 06:17 UTC, on manual dispatch, and on any push that changes `pipeline/` or `data/`. It runs the tests, runs the pipeline, and commits `docs/data/` (or only `docs/data/last_run.log` if the run failed). GitHub Pages redeploys on each commit.

**Pages setup:** Settings → Pages → *Deploy from a branch* → `main` / `/docs`.
