# Frat-stien-nell

Public figures named in the Epstein documents, checked for Ivy League education (Brown, Columbia, Cornell, Dartmouth, Harvard, Penn, Princeton, Yale) and fraternity membership. Results are shown on a static site in `docs/`: **Web** (`index.html`, the home page: a full-screen network of people linked by shared colleges and fraternities, with filters and search), **List** (`list.html`, the people table) and **Sources** (`sources.html`, the method plus source links for each person).

Being named in these documents does not imply wrongdoing.

## How it works

1. **Names** (`pipeline/scrape_names.py`): parses Wikipedia's [List of people named in the Epstein files](https://en.wikipedia.org/wiki/List_of_people_named_in_the_Epstein_files). That list covers flight logs, the contact book, court filings and the DOJ/Congressional releases, and only includes people who have Wikipedia articles. Each entry's text is tagged with document types.
2. **Filter** (`pipeline/run.py`): drops anything that isn't a person on Wikidata. It also drops victims, survivors and Epstein's staff, using `data/exclude.txt` plus an automatic description check. Removed names go to `docs/data/excluded.json`.
3. **Enrich** (`pipeline/enrich.py`):
   - **Ivy League** (per school, including graduate/professional schools such as Wharton, Harvard Law and Weill Cornell): *yes* if Wikidata *educated at* (P69) includes the school or the article has an alumni category for it. *Possible* if the article text places an attendance word (graduated, attended, B.A., PhD, …) near the school's name. Faculty, trustees and fellows are flagged separately as *(fac)*. The patterns avoid look-alikes such as British Columbia, Penn State, Cornell College and Britannia Royal Naval College, Dartmouth.
   - **Fraternity**: *yes* if Wikidata *member of* (P463) is a fraternity or sorority, or if a category names one. *Possible* if the article text mentions a fraternity or a Greek-letter organization. Honor societies (Phi Beta Kappa, etc.) are listed but not counted.
4. **Graph** (`pipeline/graph.py`): links people to the colleges and fraternities they share. Graduate schools are grouped under their parent university and secondary schools are dropped.
5. **Manual verification** (`data/overrides.json`): confirms or corrects hits by hand and marks them ✓ verified on the site.

## Run locally

```bash
pip install -r requirements.txt
python -m pytest -q tests
python pipeline/run.py          # writes docs/data/people.json + excluded.json
python -m http.server -d docs   # open http://localhost:8000
```

## Automation

`.github/workflows/update.yml` re-runs the pipeline weekly, on manual dispatch, and whenever `pipeline/` or `data/` changes. It commits the new `docs/data/`.

**Site:** Settings → Pages → *Deploy from a branch* → `main` / `docs`.

## Overrides format

```json
{
  "Person Name": {
    "schools": {"Harvard": {"status": "yes", "evidence": [{"source": "…", "text": "…", "url": "https://…"}]}},
    "frat":    {"status": "no",  "orgs": [], "evidence": []},
    "note": "optional",
    "verified": true
  }
}
```

Other files: `data/extra_names.txt` adds names, `data/exclude.txt` removes names, and `data/include.txt` overrides the automatic victim/staff filter.
