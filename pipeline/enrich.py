"""Resolve names to Wikipedia/Wikidata and detect Cornell attendance + fraternity membership."""
import re

from common import chunks, sparql, wp

GREEK = (
    "Alpha|Beta|Gamma|Delta|Epsilon|Zeta|Eta|Theta|Iota|Kappa|Lambda|Mu|Nu|Xi|"
    "Omicron|Pi|Rho|Sigma|Tau|Upsilon|Phi|Chi|Psi|Omega"
)
GREEK_ORG_RE = re.compile(rf"\b(?:(?:{GREEK})\s+){{1,3}}(?:{GREEK})\b")
FRAT_WORD_RE = re.compile(r"\b(fraternity|fraternities|sorority|frat brother|pledged)\b", re.I)

# Academic honor / professional societies: Greek-lettered but not social frats.
HONOR_SOCIETIES = {
    "phi beta kappa", "alpha omega alpha", "tau beta pi", "phi kappa phi", "sigma xi",
    "eta kappa nu", "pi mu epsilon", "beta gamma sigma", "omicron delta kappa", "psi chi",
    "pi sigma alpha", "phi alpha theta", "golden key", "alpha lambda delta", "phi eta sigma",
    "sigma pi sigma", "pi tau sigma", "beta alpha psi", "alpha kappa delta", "phi sigma iota",
    "sigma delta pi", "delta phi alpha", "chi epsilon", "sigma tau delta", "kappa delta pi",
    "alpha sigma nu", "order of the coif", "sigma theta tau", "phi lambda upsilon",
    "alpha epsilon delta", "gamma sigma delta", "phi delta kappa", "pi kappa lambda",
}

# Ivy League schools. Patterns include their graduate/professional schools and
# avoid common false positives (British Columbia, Penn State, Britannia RNC Dartmouth, ...).
IVY = {
    "Brown": r"Brown University|Alpert Medical School",
    "Columbia": (
        r"Columbia (?:University|Law School|Business School|Journalism|Graduate School|"
        r"College(?! Chicago)|School of|Engineering)|Barnard College|Teachers College|"
        r"College of Physicians and Surgeons|Mailman School|School of International and Public Affairs"
    ),
    "Cornell": r"Cornell(?! College)",
    "Dartmouth": r"Dartmouth College|Tuck School|Geisel School|Dartmouth Medical|Thayer School",
    "Harvard": r"Harvard|Radcliffe College",
    "Penn": (
        r"University of Pennsylvania|Wharton School|the Wharton\b|Penn Law|Perelman School|"
        r"Annenberg School for Communication|\bUPenn\b"
    ),
    "Princeton": r"Princeton University|Princeton School of Public|Woodrow Wilson School",
    "Yale": r"Yale(?! Club)",
}
IVY_RE = {k: re.compile(v) for k, v in IVY.items()}

ATTEND = (
    r"(?:graduat\w*|attend\w*|studi\w*|enroll\w*|degree|alumn\w*|matriculat\w*|"
    r"B\.?A\.?|B\.?S\.?|M\.?B\.?A\.?|J\.?D\.?|Ph\.?D\.?|M\.?D\.?|LL\.?[BM]\.?|A\.?B\.?|"
    r"bachelor'?s?|master'?s?|doctorate|transferr\w*|dropped out|educated|admitted)"
)
ATTEND_BEFORE = rf"\b{ATTEND}\b[^;]{{0,90}}?"
ATTEND_AFTER = r"[^;]{0,20}?\b(?:graduate|alumn\w*|dropout|class of|degree)\b"
FACULTY_RE = re.compile(r"(professor|faculty|taught|lecturer|trustee|chair of|dean|fellow)", re.I)

EXCLUDE_DESC_RE = re.compile(r"\b(victim|survivor|accuser|abuse advocate)\b", re.I)
STAFF_CTX_RE = re.compile(
    r"Epstein'?s?\s+(personal\s+)?(assistant|pilot|housekeeper|butler|chef|employee|"
    r"house manager|driver|bodyguard|scheduler|secretary)",
    re.I,
)


def sentences_with(text, pattern):
    sents = re.split(r"(?<=[a-z0-9)]{2}[.!?])\s+(?=[A-Z\"(])|\n+", text)
    return [s.strip() for s in sents if re.search(pattern, s)]


def canonical_org(name):
    return re.sub(r"\s+", " ", name).strip()


def is_honor(org):
    return org.lower() in HONOR_SOCIETIES


def resolve_titles(titles):
    """Map raw title -> resolved canonical title (or None) using redirects, then search fallback."""
    out = {}
    for batch in chunks(titles, 50):
        data = wp({"action": "query", "titles": "|".join(batch), "redirects": 1})
        q = data["query"]
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
        missing = {p["title"] for p in q["pages"] if p.get("missing") or p.get("invalid")}
        for t in batch:
            t2 = norm.get(t, t)
            t3 = redir.get(t2, t2)
            out[t] = None if t3 in missing else t3
    for t, v in out.items():
        if v is None:
            clean = re.sub(r"^(Dr|Sir|Lord|Lady|Prof)\.?\s+", "", t)
            res = wp({"action": "query", "list": "search", "srsearch": clean, "srlimit": 1})
            hits = res["query"]["search"]
            surname = clean.split()[-1].lower() if clean.split() else ""
            if hits and surname and surname in hits[0]["title"].lower():
                out[t] = hits[0]["title"]
    return out


def fetch_page(title):
    data = wp({
        "action": "query", "titles": title, "redirects": 1,
        "prop": "pageprops|categories|extracts|description|info",
        "ppprop": "wikibase_item", "cllimit": "max", "clshow": "!hidden",
        "explaintext": 1, "exsectionformat": "plain", "inprop": "url",
    })
    p = data["query"]["pages"][0]
    return {
        "title": p["title"],
        "url": p.get("fullurl", "https://en.wikipedia.org/wiki/" + p["title"].replace(" ", "_")),
        "qid": p.get("pageprops", {}).get("wikibase_item"),
        "description": p.get("description", ""),
        "categories": [c["title"].removeprefix("Category:") for c in p.get("categories", [])],
        "text": p.get("extract", ""),
    }


def wikidata_facts(qids):
    facts = {q: {"human": False, "educated_at": [], "member_of": []} for q in qids}
    for batch in chunks(qids, 80):
        values = " ".join(f"wd:{q}" for q in batch)
        query = f"""
        SELECT ?item ?isHuman ?edu ?eduLabel ?mem ?memLabel ?memTypeLabel WHERE {{
          VALUES ?item {{ {values} }}
          BIND(EXISTS {{ ?item wdt:P31 wd:Q5 }} AS ?isHuman)
          OPTIONAL {{ ?item wdt:P69 ?edu. }}
          OPTIONAL {{ ?item wdt:P463 ?mem. OPTIONAL {{ ?mem wdt:P31 ?memType. }} }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}"""
        for row in sparql(query)["results"]["bindings"]:
            q = row["item"]["value"].rsplit("/", 1)[-1]
            f = facts[q]
            f["human"] = f["human"] or row["isHuman"]["value"] == "true"
            if "edu" in row:
                e = {"id": row["edu"]["value"].rsplit("/", 1)[-1], "label": row["eduLabel"]["value"]}
                if e not in f["educated_at"]:
                    f["educated_at"].append(e)
            if "mem" in row:
                mid = row["mem"]["value"].rsplit("/", 1)[-1]
                existing = next((m for m in f["member_of"] if m["id"] == mid), None)
                if not existing:
                    existing = {"id": mid, "label": row["memLabel"]["value"], "types": []}
                    f["member_of"].append(existing)
                t = row.get("memTypeLabel", {}).get("value")
                if t and t not in existing["types"]:
                    existing["types"].append(t)
    return facts


def detect_school(page, wd, school):
    rx = IVY_RE[school]
    evidence, status, faculty = [], "no", False
    wd_url = f"https://www.wikidata.org/wiki/{page['qid']}" if page["qid"] else None
    for e in wd.get("educated_at", []):
        if rx.search(e["label"]):
            status = "yes"
            evidence.append({"source": "Wikidata (educated at)", "text": e["label"], "url": wd_url})
    for c in page["categories"]:
        if rx.search(c):
            if re.search(r"alumni|graduates", c, re.I):
                status = "yes"
                evidence.append({"source": "Wikipedia category", "text": c, "url": page["url"]})
            elif re.search(r"faculty|trustees|fellows|staff", c, re.I):
                faculty = True
                evidence.append({"source": "Wikipedia category", "text": c, "url": page["url"]})
    attend_rx = re.compile(rf"{ATTEND_BEFORE}(?:{rx.pattern})|(?:{rx.pattern}){ATTEND_AFTER}", re.I)
    for s in sentences_with(page["text"], rx.pattern):
        if attend_rx.search(s):
            if status == "no":
                status = "possible"
            evidence.append({"source": "Wikipedia article text", "text": s[:400], "url": page["url"]})
        elif FACULTY_RE.search(s):
            faculty = True
            evidence.append({"source": "Wikipedia article text (faculty/other)", "text": s[:400], "url": page["url"]})
    return {"status": status, "faculty": faculty, "evidence": evidence[:5]}


def detect_ivy(page, wd):
    """Return {school: result} for every Ivy with any signal (attendance or faculty)."""
    out = {}
    for school in IVY:
        r = detect_school(page, wd, school)
        if r["status"] != "no" or r["faculty"]:
            out[school] = r
    return out


def detect_frat(page, wd):
    orgs, honors, evidence, status = [], [], [], "no"
    wd_url = f"https://www.wikidata.org/wiki/{page['qid']}" if page["qid"] else None
    for m in wd.get("member_of", []):
        types = " ".join(m["types"]).lower()
        label = m["label"]
        greek = GREEK_ORG_RE.fullmatch(label.strip()) or GREEK_ORG_RE.match(label)
        if is_honor(label):
            honors.append(label)
        elif "fraternit" in types or "sororit" in types or "greek" in types or greek:
            status = "yes"
            orgs.append(label)
            evidence.append({"source": "Wikidata (member of)", "text": f"{label} ({', '.join(m['types'])})", "url": wd_url})
    for c in page["categories"]:
        match = GREEK_ORG_RE.search(c)
        if match and not is_honor(match.group(0)) or re.search(r"fraternit|sororit", c, re.I):
            status = "yes"
            if match:
                orgs.append(canonical_org(match.group(0)))
            evidence.append({"source": "Wikipedia category", "text": c, "url": page["url"]})
    for s in sentences_with(page["text"], rf"{FRAT_WORD_RE.pattern}|{GREEK_ORG_RE.pattern}"):
        found = [canonical_org(x) for x in GREEK_ORG_RE.findall(s)]
        social = [o for o in found if not is_honor(o)]
        honors += [o for o in found if is_honor(o)]
        if social or FRAT_WORD_RE.search(s):
            if status == "no":
                status = "possible"
            orgs += social
            evidence.append({"source": "Wikipedia article text", "text": s[:400], "url": page["url"]})
    dedup = lambda xs: list(dict.fromkeys(xs))
    return {"status": status, "orgs": dedup(orgs), "honor_societies": dedup(honors), "evidence": evidence[:6]}


def exclusion_reason(page, entry_context):
    if EXCLUDE_DESC_RE.search(page["description"]):
        return f"description: {page['description']}"
    lead = page["text"][:600]
    if EXCLUDE_DESC_RE.search(lead) and re.search(r"Epstein", lead):
        return "article lead describes a victim/survivor"
    if STAFF_CTX_RE.search(entry_context) or STAFF_CTX_RE.search(lead):
        return "described as Epstein staff"
    return None
