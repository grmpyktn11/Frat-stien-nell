"""Build the connection web: people linked to the colleges and fraternities they share.

Nodes: people, colleges/universities, fraternities/sororities.
Links: person -> institution (attended), person -> fraternity (member).
Graduate/professional schools are folded into their parent university
(Wharton -> University of Pennsylvania, Walsh School -> Georgetown). Secondary schools are
dropped. A non-Ivy college is kept only when two or more people share it, so every
college node is a real connection; Ivy schools and fraternities are always kept.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from enrich import IVY_RE  # noqa: E402

IVY_NAMES = {
    "Brown": "Brown University", "Columbia": "Columbia University", "Cornell": "Cornell University",
    "Dartmouth": "Dartmouth College", "Harvard": "Harvard University", "Penn": "University of Pennsylvania",
    "Princeton": "Princeton University", "Yale": "Yale University",
}

PARENTS = [
    (r"Walsh School of Foreign Service|Georgetown", "Georgetown University"),
    (r"Fletcher School|Tufts", "Tufts University"),
    (r"New York University|\bNYU\b|Tisch School|Stern School|Courant Institute", "New York University"),
    (r"Oxford", "University of Oxford"),
    (r"Cambridge", "University of Cambridge"),
    (r"Stanford", "Stanford University"),
    (r"Massachusetts Institute of Technology|\bMIT\b|Sloan School", "Massachusetts Institute of Technology"),
    (r"University of Chicago|Booth School", "University of Chicago"),
    (r"London School of Economics", "London School of Economics"),
    (r"Sciences Po|Paris Institute of Political Studies", "Sciences Po"),
    (r"University of California, Los Angeles|\bUCLA\b", "UCLA"),
    (r"Duke University|Duke Law", "Duke University"),
    (r"Northwestern|Kellogg School", "Northwestern University"),
]

SECONDARY_RE = re.compile(
    r"High School|Preparatory|Academy|Gordonstoun|Talented Youth|Colegio|Lycée|Gymnasium|"
    r"Hall School|Grammar School|Day School|Middle School|Elementary|School of the Arts|Center for Early|"
    r"Young Actors|Interlochen|Playhouse|Dulwich College|Aitchison College|Eton College|Harrow School|Winchester College",
    re.I,
)
HIGHER_SCHOOL_RE = re.compile(
    r"(Business|Law|Medical|Divinity|Graduate|Dental|Journalism|Engineering|Public|Management|"
    r"Government|Medicine|Nursing|Art|Arts|Music|Design) School|School of|Juilliard",
    re.I,
)


def canonical_institution(label):
    """Map an education label to a college/university name, or None for secondary schools."""
    label = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()
    if not label:
        return None
    for school, rx in IVY_RE.items():
        if rx.search(label):
            return IVY_NAMES[school]
    for pat, name in PARENTS:
        if re.search(pat, label):
            return name
    if SECONDARY_RE.search(label):
        return None
    if label.endswith("School") and not HIGHER_SCHOOL_RE.search(label):
        return None
    return label


def person_colleges(p):
    """Colleges a person attended (parent-university names), Ivy schools first."""
    insts = []
    for school, v in p.get("schools", {}).items():
        if v.get("status") in ("yes", "possible"):
            insts.append(IVY_NAMES[school])
    for label in p.get("education", []):
        c = canonical_institution(label)
        if c and c not in insts:
            insts.append(c)
    ivy = set(IVY_NAMES.values())
    return sorted(dict.fromkeys(insts), key=lambda x: (x not in ivy, insts.index(x)))


def load_cases(root=None):
    root = root or pathlib.Path(__file__).resolve().parent.parent
    f = root / "data" / "cases.json"
    return json.loads(f.read_text())["cases"] if f.exists() else []


def build_graph(people, cases=()):
    person_nodes, inst_members, frat_members, club_members = [], {}, {}, {}
    ivy_inst = set(IVY_NAMES.values())
    for p in people:
        insts = {i for i in person_colleges(p)
                 if not any(IVY_NAMES[s] == i and v.get("status") != "yes" for s, v in p.get("schools", {}).items())}
        frats = set(p["frat"].get("orgs", [])) if p["frat"].get("status") == "yes" else set()
        for o in p.get("orgs", []):
            if o.get("status") == "yes":
                club_members.setdefault(o["name"], {"kind": o["kind"], "school": o.get("school"), "m": set()})["m"].add(p["name"])
        for i in insts:
            inst_members.setdefault(i, set()).add(p["name"])
        for f in frats:
            frat_members.setdefault(f, set()).add(p["name"])
        person_nodes.append({"id": "p:" + p["name"], "type": "person", "label": re.sub(r"\s*\(.*\)$", "", p["name"]),
                             "name": p["name"], "description": p.get("description", ""), "url": p.get("url"),
                             "epstein": p.get("epstein", True), "cases": [c["case"] for c in p.get("cases", [])]})

    kept_inst = {i: m for i, m in inst_members.items() if len(m) >= 2 or i in ivy_inst}
    nodes, links = [], []
    for i, m in sorted(kept_inst.items()):
        nodes.append({"id": "i:" + i, "type": "college", "label": i, "ivy": i in ivy_inst, "count": len(m)})
        links += [{"source": "p:" + n, "target": "i:" + i, "kind": "college"} for n in sorted(m)]
    for f, m in sorted(frat_members.items()):
        nodes.append({"id": "f:" + f, "type": "frat", "label": f, "count": len(m)})
        links += [{"source": "p:" + n, "target": "f:" + f, "kind": "frat"} for n in sorted(m)]
    for c, info in sorted(club_members.items()):
        nodes.append({"id": "o:" + c, "type": "club", "kind": info["kind"], "school": info["school"],
                      "label": c, "count": len(info["m"])})
        links += [{"source": "p:" + n, "target": "o:" + c, "kind": "club"} for n in sorted(info["m"])]
    # Unnamed case nodes (e.g. "Cornell 7"): one node linked to the colleges/orgs involved.
    have = {n["id"] for n in nodes}
    case_nodes = []
    for c in cases:
        case_nodes.append({"id": c["id"], "type": "case", "label": c["label"], "badge": c.get("badge", ""),
                           "description": c.get("description", ""), "sources": c.get("sources", [])})
        for col in c.get("colleges", []):
            if "i:" + col not in have:
                nodes.append({"id": "i:" + col, "type": "college", "label": col, "ivy": col in ivy_inst, "count": 0})
                have.add("i:" + col)
            links.append({"source": c["id"], "target": "i:" + col, "kind": "college"})
        for fr in c.get("frats", []):
            if "f:" + fr not in have:
                nodes.append({"id": "f:" + fr, "type": "frat", "label": fr, "count": 0})
                have.add("f:" + fr)
            links.append({"source": c["id"], "target": "f:" + fr, "kind": "frat"})
    linked = {l["source"] for l in links if not l["source"].startswith("c:")}
    nodes = [n for n in person_nodes if n["id"] in linked] + case_nodes + nodes
    return {
        "nodes": nodes,
        "links": links,
        "counts": {
            "people_linked": len(linked),
            "people_unlinked": len(person_nodes) - len(linked),
            "colleges": len(kept_inst),
            "frats": len(frat_members),
            "clubs": len(club_members),
            "cases": len(case_nodes),
        },
    }


def main():
    out = pathlib.Path(__file__).resolve().parent.parent / "docs" / "data"
    people = json.loads((out / "people.json").read_text())["people"]
    g = build_graph(people, load_cases())
    (out / "graph.json").write_text(json.dumps(g, indent=1, ensure_ascii=False))
    print(json.dumps(g["counts"]))


if __name__ == "__main__":
    main()
