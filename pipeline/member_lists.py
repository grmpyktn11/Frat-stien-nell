"""Reverse lookup: pull Wikipedia member lists and "notable members" sections for fraternities,
sororities, secret societies and clubs, then match them against our people.

Sources per org:
  - "List of <org> members/brothers/sisters/people" pages, when they exist
  - Wikipedia category "Lists of members of fraternities and sororities" (and similar)
  - The org's own article, restricted to sections about members/alumni
A match is a wikilink to one of our people inside those lists/sections. Lines mentioning
"honorary" are skipped. Each match keeps the list line as evidence.
"""
import re

from common import chunks, wp
from orgs import ORGS

GREEK_ORGS = [
    "Alpha Delta Phi", "Alpha Epsilon Pi", "Alpha Phi Alpha", "Alpha Phi Omega", "Alpha Sigma Phi", "Alpha Tau Omega",
    "Beta Theta Pi", "Chi Phi", "Chi Psi", "Delta Chi", "Delta Kappa Epsilon", "Delta Phi", "Delta Psi", "Delta Sigma Phi",
    "Delta Tau Delta", "Delta Upsilon", "Kappa Alpha Order", "Kappa Alpha Psi", "Kappa Alpha Society", "Kappa Delta Rho",
    "Kappa Sigma", "Lambda Chi Alpha", "Omega Psi Phi", "Phi Beta Sigma", "Phi Delta Theta", "Phi Gamma Delta",
    "Phi Kappa Psi", "Phi Kappa Sigma", "Phi Kappa Tau", "Phi Kappa Theta", "Phi Sigma Kappa", "Pi Kappa Alpha",
    "Pi Kappa Phi", "Pi Lambda Phi", "Psi Upsilon", "Sigma Alpha Epsilon", "Sigma Alpha Mu", "Sigma Chi", "Sigma Nu",
    "Sigma Phi", "Sigma Phi Epsilon", "Sigma Pi", "Tau Delta Phi", "Tau Epsilon Phi", "Tau Kappa Epsilon", "Theta Chi",
    "Theta Delta Chi", "Theta Xi", "Zeta Beta Tau", "Zeta Psi", "Phi Sigma Delta", "Lambda Theta Phi", "Kappa Kappa Psi",
    "Alpha Chi Omega", "Alpha Delta Pi", "Alpha Gamma Delta", "Alpha Kappa Alpha", "Alpha Omicron Pi", "Alpha Phi",
    "Alpha Xi Delta", "Chi Omega", "Delta Delta Delta", "Delta Gamma", "Delta Sigma Theta", "Delta Zeta", "Gamma Phi Beta",
    "Kappa Alpha Theta", "Kappa Delta", "Kappa Kappa Gamma", "Phi Mu", "Pi Beta Phi", "Sigma Delta Tau", "Sigma Kappa",
    "Zeta Phi Beta", "Zeta Tau Alpha", "Alpha Epsilon Phi", "Phi Sigma Sigma", "Delta Phi Epsilon", "Epsilon Theta",
]
# Society/club article titles on Wikipedia (org name in ORGS -> article title)
ORG_ARTICLES = {
    "Skull and Bones": "Skull and Bones", "Scroll and Key": "Scroll and Key", "Wolf's Head": "Wolf's Head Society",
    "Book and Snake": "Book and Snake", "Elihu": "Elihu (secret society)", "Berzelius": "Berzelius (secret society)",
    "Manuscript Society": "Manuscript Society", "St. Elmo": "St. Elmo Society", "Quill and Dagger": "Quill and Dagger",
    "Sphinx Head": "Sphinx Head", "Telluride House": "Telluride Association", "Casque and Gauntlet": "Casque and Gauntlet",
    "Sphinx (Dartmouth)": "Sphinx (senior society)", "Dragon (Dartmouth)": "Dragon Society (Dartmouth College)",
    "Green Key": "Green Key Society", "Friars Senior Society": "Friars Senior Society",
    "Sphinx Senior Society": "Sphinx Senior Society", "Philomathean Society": "Philomathean Society",
    "St. Anthony Hall": "St. Anthony Hall", "Seven Society": "Seven Society", "Cambridge Apostles": "Cambridge Apostles",
    "Porcellian Club": "Porcellian Club", "A.D. Club": "A.D. Club", "Fly Club": "Fly Club", "Spee Club": "Spee Club",
    "Owl Club": "Owl Club (Harvard)", "Phoenix-S K Club": "Phoenix-S K Club", "Fox Club": "Fox Club",
    "Delphic Club": "Delphic Club", "Hasty Pudding Club": "Hasty Pudding Club", "Signet Society": "Signet Society",
    "Harvard Society of Fellows": "Harvard Society of Fellows", "Ivy Club": "Ivy Club",
    "University Cottage Club": "University Cottage Club", "Tiger Inn": "Tiger Inn", "Cap and Gown Club": "Cap and Gown Club",
    "Colonial Club": "Colonial Club", "Cannon Club": "Cannon Dial Elm Club", "Charter Club": "Charter Club",
    "Quadrangle Club": "Quadrangle Club", "Terrace Club": "Terrace Club", "Tower Club": "Tower Club",
    "Cloister Inn": "Cloister Inn", "American Whig–Cliosophic Society": "American Whig–Cliosophic Society",
    "Bullingdon Club": "Bullingdon Club", "Piers Gaveston Society": "Piers Gaveston Society",
    "Oxford Union": "List of presidents of the Oxford Union", "Cambridge Union": "List of presidents of the Cambridge Union",
    "Pitt Club": "Pitt Club", "Footlights": "Footlights", "Harvard Lampoon": "Harvard Lampoon",
    "The Harvard Crimson": "The Harvard Crimson", "Harvard Law Review": "Harvard Law Review",
    "Yale Daily News": "Yale Daily News", "Yale Political Union": "Yale Political Union",
    "The Daily Princetonian": "The Daily Princetonian", "College Republicans": "College Republicans",
    "Young Americans for Freedom": "Young Americans for Freedom", "The Dartmouth Review": "The Dartmouth Review",
    "The Stanford Review": "The Stanford Review", "Phi Beta Kappa": "List of Phi Beta Kappa members",
}
ORG_INFO = {n: (k, s) for n, k, s, _ in ORGS}
MEMBER_SECTION_RE = re.compile(r"member|alumni|alumnae|brother|sister|people|notable|president|chair|editor|fellows|initiates", re.I)
LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
CATEGORY_CANDIDATES = [
    "Category:Lists of members of social fraternities and sororities",
    "Category:Lists of members of fraternities and sororities",
    "Category:Lists of fraternity and sorority members",
]


def norm_title(t):
    t = re.sub(r"[_\s]+", " ", t).strip()
    return t[:1].upper() + t[1:] if t else t


def aliases_for(titles):
    """Map every redirect title (and the title itself) to our canonical person title."""
    out = {norm_title(t): t for t in titles}
    for batch in chunks(sorted(titles), 50):
        params = {"action": "query", "titles": "|".join(batch), "prop": "redirects", "rdlimit": "max", "rdnamespace": 0}
        while True:
            res = wp(params)
            for p in res.get("query", {}).get("pages", []):
                for r in p.get("redirects", []):
                    out[norm_title(r["title"])] = p["title"]
            if "continue" not in res:
                break
            params = {**params, **res["continue"]}
    return out


def list_titles_for(org):
    base = org.replace("–", "-")
    return [f"List of {base} {w}" for w in ("members", "brothers", "sisters", "people", "alumni")]


def existing(titles):
    """Return {requested: resolved} for titles that exist (following redirects)."""
    out = {}
    for batch in chunks(sorted(set(titles)), 50):
        batch = [t for t in batch if t and len(t) < 250 and not re.search(r"[\[\]{}<>|#]", t) and ":" not in t[:1]]
        if not batch:
            continue
        q = wp({"action": "query", "titles": "|".join(batch), "redirects": 1}).get("query", {})
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
        present = {p["title"] for p in q.get("pages", []) if not p.get("missing") and not p.get("invalid")}
        for t in batch:
            r = redir.get(norm.get(t, t), norm.get(t, t))
            if r in present:
                out[t] = r
    return out


def category_lists():
    found = []
    for cat in CATEGORY_CANDIDATES:
        try:
            res = wp({"action": "query", "list": "categorymembers", "cmtitle": cat, "cmlimit": "max", "cmnamespace": 0})
        except Exception:
            continue
        found += [m["title"] for m in res.get("query", {}).get("categorymembers", [])]
    return found


def wikitext(title):
    try:
        return wp({"action": "parse", "page": title, "prop": "wikitext", "redirects": 1})["parse"]["wikitext"]
    except Exception:
        return ""


def member_lines(text, whole_page):
    """Yield lines from member sections (or the whole page for dedicated list pages)."""
    keep = whole_page
    for line in text.splitlines():
        h = re.match(r"^(=+)\s*(.*?)\s*\1\s*$", line)
        if h:
            if not whole_page:
                keep = bool(MEMBER_SECTION_RE.search(h.group(2)))
            if re.search(r"see also|references|notes|external links|further reading|bibliography", h.group(2), re.I):
                keep = False
            continue
        if keep:
            yield line


def clean_line(line):
    s = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", line)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = LINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), s)
    s = re.sub(r"'{2,}|<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip(" *#|-")


def org_for_list_title(title):
    m = re.match(r"List of (.+?) (members|brothers|sisters|people|alumni|presidents)\b", title)
    return m.group(1).strip() if m else None


def lookup(person_titles):
    """person_titles: set of our people's Wikipedia titles.
    Returns {person_title: [ {name, kind, school, evidence} ]}."""
    alias = aliases_for(person_titles)
    sources = []  # (org_name, kind, school, page_title, whole_page)
    greek_lists = existing([t for g in GREEK_ORGS for t in list_titles_for(g)])
    for req, real in greek_lists.items():
        org = org_for_list_title(req)
        sources.append((org, "fraternity", None, real, True))
    for t in category_lists():
        org = org_for_list_title(t)
        if org and not any(s[3] == t for s in sources):
            sources.append((org, "fraternity" if org in GREEK_ORGS or re.search(r"[ΑΒΓΔ]|Alpha|Beta|Gamma|Delta|Sigma|Kappa|Phi|Chi|Psi|Omega|Theta|Tau|Pi\b", org) else "club", None, t, True))
    greek_articles = existing(GREEK_ORGS)
    for req, real in greek_articles.items():
        sources.append((req, "fraternity", None, real, False))
    art = existing(list(ORG_ARTICLES.values()))
    for org, title in ORG_ARTICLES.items():
        if title in art:
            kind, school = ORG_INFO.get(org, ("club", None))
            whole = title.startswith("List of")
            sources.append((org, kind, school, art[title], whole))
    extra = existing([t for org in ORG_ARTICLES for t in list_titles_for(org)])
    for req, real in extra.items():
        org = org_for_list_title(req)
        kind, school = ORG_INFO.get(org, ("club", None))
        sources.append((org, kind, school, real, True))

    # Gather candidate links per source, resolve them in bulk, keep those that are our people.
    per_source = []
    for org, kind, school, title, whole in sources:
        text = wikitext(title)
        hits = []
        for line in member_lines(text, whole):
            if re.search(r"honorary|honoris", line, re.I):
                continue
            # Only the line's first person link counts: later links are usually context
            # ("attorney to President Bill Clinton", "daughter of Donald Trump").
            m = LINK_RE.search(line)
            if m:
                target = m.group(1).strip()
                if norm_title(target) in alias and not re.search(r"\b(?:son|daughter|wife|husband|father|mother|brother|sister) of\b", line[:m.start()], re.I):
                    hits.append((target, line))
        per_source.append((org, kind, school, title, hits))
    out = {}
    for org, kind, school, title, hits in per_source:
        for target, line in hits:
            t = alias.get(norm_title(target))
            if t in person_titles:
                rec = out.setdefault(t, {})
                if org not in rec:
                    rec[org] = {"name": org, "kind": kind, "school": school, "status": "yes", "evidence": [{
                        "source": f"Wikipedia: {title}", "text": clean_line(line)[:300],
                        "url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")}]}
    return {k: list(v.values()) for k, v in out.items()}
