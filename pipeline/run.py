"""Full pipeline (Ivy League + fraternity): scrape names -> filter -> enrich -> apply manual overrides -> write docs/data/*.json"""
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from enrich import (  # noqa: E402
    IVY, detect_frat, detect_ivy, exclusion_reason, fetch_page, resolve_titles, wikidata_facts,
)
from graph import build_graph  # noqa: E402
from scrape_names import SOURCE_PAGE, classify, get_entries  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs" / "data"


def read_list(path):
    """Lines of 'Title | note'; '#' comments allowed."""
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                name, _, note = line.partition("|")
                out[name.strip()] = note.strip()
    return out


def main():
    exclude = read_list(DATA / "exclude.txt")
    force_include = read_list(DATA / "include.txt")
    extra = read_list(DATA / "extra_names.txt")
    overrides = json.loads((DATA / "overrides.json").read_text()) if (DATA / "overrides.json").exists() else {}

    entries, revid = get_entries()
    for name, docs in extra.items():
        entries.append({"title": name, "context": docs, "documents": classify(docs) or [d.strip() for d in docs.split(",") if d.strip()]})
    print(f"{len(entries)} raw entries from rev {revid}")

    resolved = resolve_titles(sorted({e["title"] for e in entries}))
    by_title = {}
    unresolved = []
    unresolved_docs = {}
    for e in entries:
        t = resolved.get(e["title"])
        if not t:
            unresolved.append(e["title"])
            unresolved_docs[e["title"]] = e["documents"]
            continue
        m = by_title.setdefault(t, {"context": "", "documents": []})
        m["context"] += " " + e["context"]
        m["documents"] = list(dict.fromkeys(m["documents"] + e["documents"]))

    pages = {}
    for i, t in enumerate(sorted(by_title)):
        pages[t] = fetch_page(t)
        if i % 25 == 0:
            print(f"  fetched {i}/{len(by_title)}")

    facts = wikidata_facts(sorted({p["qid"] for p in pages.values() if p["qid"]}))

    people, excluded = [], []
    for t, page in sorted(pages.items()):
        wd = facts.get(page["qid"], {})
        if t in exclude:
            excluded.append({"name": t, "reason": exclude[t] or "manual exclude list"})
            continue
        if page["qid"] and not wd.get("human"):
            excluded.append({"name": t, "reason": "not a person (Wikidata)"})
            continue
        reason = None if t in force_include else exclusion_reason(page, by_title[t]["context"])
        if reason:
            excluded.append({"name": t, "reason": reason})
            continue
        rec = {
            "name": t,
            "url": page["url"],
            "qid": page["qid"],
            "description": page["description"],
            "documents": by_title[t]["documents"],
            "schools": detect_ivy(page, wd),
            "frat": detect_frat(page, wd),
            "education": [e["label"] for e in wd.get("educated_at", [])],
            "verified": False,
        }
        ov = overrides.get(t)
        if ov:
            for school, sov in ov.get("schools", {}).items():
                rec["schools"].setdefault(school, {"status": "no", "faculty": False, "evidence": []}).update(sov)
            if "frat" in ov:
                rec["frat"].update(ov["frat"])
            if "note" in ov:
                rec["note"] = ov["note"]
            rec["verified"] = ov.get("verified", True)
        rec["schools"] = {k: v for k, v in rec["schools"].items() if v["status"] != "no" or v.get("faculty")}
        people.append(rec)

    # Hand-researched records for names without a Wikipedia article.
    manual_path = DATA / "manual_people.json"
    manual = json.loads(manual_path.read_text())["people"] if manual_path.exists() else []
    have = {p["name"] for p in people}
    for m in manual:
        if m["name"] in have or m["name"] in exclude:
            continue
        schools = {k: {"status": v.get("status", "no"), "faculty": v.get("faculty", False), "evidence": v.get("evidence", [])}
                   for k, v in m.get("schools", {}).items()}
        frat = {"status": "no", "orgs": [], "honor_societies": [], "evidence": []}
        frat.update(m.get("frat", {}))
        src = m.get("school_sources", [])
        docs = next((d for k, d in unresolved_docs.items() if k == m["name"] or m["name"] in k.split(" and ")
                     or f'{m["name"].split()[0]} ' in k and m["name"].split()[-1] in k), [])
        people.append({
            "name": m["name"],
            "url": (src[0]["url"] if src else None),
            "qid": None,
            "description": m.get("description", ""),
            "documents": docs,
            "schools": {k: v for k, v in schools.items() if v["status"] != "no" or v["faculty"]},
            "frat": frat,
            "education": m.get("education", []),
            "education_sources": src,
            "note": m.get("note", ""),
            "verified": True,
            "manual": True,
        })
    for u in unresolved:
        if u in exclude:
            excluded.append({"name": u, "reason": exclude[u] or "manual exclude list"})
    covered = {p["name"] for p in people}
    unresolved = [u for u in unresolved if u not in covered and u not in exclude
                  and not any(n in u for n in covered)]

    OUT.mkdir(parents=True, exist_ok=True)
    meta = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": f"https://en.wikipedia.org/wiki/{SOURCE_PAGE}",
        "source_revision": revid,
        "counts": {
            "people": len(people),
            "excluded": len(excluded),
            "unresolved": len(unresolved),
            "ivy_yes": sum(any(v["status"] == "yes" for v in p["schools"].values()) for p in people),
            "ivy_possible": sum(
                any(v["status"] == "possible" for v in p["schools"].values())
                and not any(v["status"] == "yes" for v in p["schools"].values())
                for p in people
            ),
            "by_school": {
                s: {st: sum(p["schools"].get(s, {}).get("status") == st for p in people) for st in ("yes", "possible")}
                for s in IVY
            },
            "frat_yes": sum(p["frat"]["status"] == "yes" for p in people),
            "frat_possible": sum(p["frat"]["status"] == "possible" for p in people),
        },
    }
    (OUT / "people.json").write_text(json.dumps({"meta": meta, "people": people}, indent=1, ensure_ascii=False))
    (OUT / "graph.json").write_text(json.dumps(build_graph(people), indent=1, ensure_ascii=False))
    (OUT / "excluded.json").write_text(json.dumps({"excluded": excluded, "unresolved": unresolved}, indent=1, ensure_ascii=False))
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
