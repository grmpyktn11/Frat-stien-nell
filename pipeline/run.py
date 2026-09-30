"""Full pipeline (Ivy League + fraternity): scrape names -> filter -> enrich -> apply manual overrides -> write docs/data/*.json"""
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from enrich import (  # noqa: E402
    IVY, detect_frat, detect_ivy, exclusion_reason, fetch_page, resolve_titles, wikidata_facts,
)
from graph import build_graph, person_colleges  # noqa: E402
from orgs import detect_orgs  # noqa: E402
from member_lists import existing, lookup  # noqa: E402
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


def merge_listed(rec, found):
    """Merge memberships found on Wikipedia member lists into frat/orgs."""
    for o in found:
        if o["kind"] == "fraternity":
            f = rec["frat"]
            if o["name"] not in f["orgs"]:
                f["orgs"].append(o["name"])
            f["status"] = "yes"
            f["evidence"] = (f.get("evidence") or []) + o["evidence"]
        else:
            cur = next((x for x in rec["orgs"] if x["name"] == o["name"]), None)
            if cur:
                cur["status"] = "yes"
                cur["evidence"] = o["evidence"] + cur["evidence"]
            else:
                rec["orgs"].append(o)


def apply_org_overrides(rec, ov):
    """Override format: "orgs": [{name, kind, school, status, evidence}] adds/updates; "orgs_remove": [names]."""
    drop = set(ov.get("orgs_remove", []))
    orgs = [o for o in rec["orgs"] if o["name"] not in drop]
    for o in ov.get("orgs", []):
        cur = next((x for x in orgs if x["name"] == o["name"]), None)
        if cur:
            cur.update(o)
        else:
            orgs.append({"evidence": [], "school": None, **o})
    rec["orgs"] = orgs


def main():
    exclude = read_list(DATA / "exclude.txt")
    force_include = read_list(DATA / "include.txt")
    extra = read_list(DATA / "extra_names.txt")
    overrides = json.loads((DATA / "overrides.json").read_text()) if (DATA / "overrides.json").exists() else {}

    entries, revid = get_entries()
    for e in entries:
        e["epstein"] = True
    for name, docs in extra.items():
        entries.append({"title": name, "context": docs, "epstein": True,
                        "documents": classify(docs) or [d.strip() for d in docs.split(",") if d.strip()]})
    scandals = json.loads((DATA / "scandals.json").read_text())["people"] if (DATA / "scandals.json").exists() else []
    for sc in scandals:
        entries.append({"title": sc["title"], "context": "", "documents": [], "epstein": False,
                        "case": {"case": sc["case"], "outcome": sc["outcome"]}})
    print(f"{len(entries)} raw entries from rev {revid} (+{len(scandals)} scandal entries)")

    search_context = {e["title"]: e["case"]["case"] for e in entries if e.get("case")}
    resolved = resolve_titles(sorted({e["title"] for e in entries}), search_context)
    by_title = {}
    unresolved = []
    unresolved_docs = {}
    for e in entries:
        t = resolved.get(e["title"])
        if not t:
            unresolved.append(e["title"])
            unresolved_docs[e["title"]] = e["documents"]
            continue
        m = by_title.setdefault(t, {"context": "", "documents": [], "epstein": False, "cases": []})
        m["context"] += " " + e["context"]
        m["documents"] = list(dict.fromkeys(m["documents"] + e["documents"]))
        m["epstein"] = m["epstein"] or e["epstein"]
        if e.get("case") and e["case"] not in m["cases"]:
            m["cases"].append(e["case"])

    pages = {}
    for i, t in enumerate(sorted(by_title)):
        pages[t] = fetch_page(t)
        if i % 25 == 0:
            print(f"  fetched {i}/{len(by_title)}")

    facts = wikidata_facts(sorted({p["qid"] for p in pages.values() if p["qid"]}))
    listed = lookup(set(pages), existing)
    print(f"member lists matched {len(listed)} people")

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
            "epstein": by_title[t]["epstein"],
            "cases": by_title[t]["cases"],
            "schools": detect_ivy(page, wd),
            "frat": detect_frat(page, wd),
            "orgs": detect_orgs(page, wd),
            "education": [e["label"] for e in wd.get("educated_at", [])],
            "verified": False,
        }
        merge_listed(rec, listed.get(t, []))
        ov = overrides.get(t)
        if ov:
            for school, sov in ov.get("schools", {}).items():
                rec["schools"].setdefault(school, {"status": "no", "faculty": False, "evidence": []}).update(sov)
            if "frat" in ov:
                rec["frat"].update(ov["frat"])
            apply_org_overrides(rec, ov)
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
            "epstein": True,
            "cases": [],
            "schools": {k: v for k, v in schools.items() if v["status"] != "no" or v["faculty"]},
            "frat": frat,
            "orgs": m.get("orgs", []),
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

    for p in people:
        p["colleges"] = person_colleges(p)

    OUT.mkdir(parents=True, exist_ok=True)
    meta = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": f"https://en.wikipedia.org/wiki/{SOURCE_PAGE}",
        "source_revision": revid,
        "counts": {
            "people": len(people),
            "epstein": sum(p["epstein"] for p in people),
            "scandal": sum(bool(p["cases"]) for p in people),
            "cornell": sum(p["schools"].get("Cornell", {}).get("status") == "yes" for p in people),
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
            "orgs_yes": sum(any(o["status"] == "yes" and o["kind"] != "honor" for o in p["orgs"]) for p in people),
            "orgs_possible": sum(any(o["status"] == "possible" for o in p["orgs"]) for p in people),
        },
    }
    (OUT / "people.json").write_text(json.dumps({"meta": meta, "people": people}, indent=1, ensure_ascii=False))
    (OUT / "graph.json").write_text(json.dumps(build_graph(people), indent=1, ensure_ascii=False))
    (OUT / "excluded.json").write_text(json.dumps({"excluded": excluded, "unresolved": unresolved}, indent=1, ensure_ascii=False))
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
