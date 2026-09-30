"""Catalog of college societies and clubs (beyond Greek-letter fraternities).

Each entry: canonical name, kind, school, regex. Kinds:
  society     secret/senior societies (Skull and Bones, Quill and Dagger, ...)
  club        final clubs, eating clubs, dining/social clubs (Porcellian, Ivy Club, Bullingdon, ...)
  publication student newspapers, magazines, law reviews
  political   student political organizations and debating unions
  honor       academic honor societies (Phi Beta Kappa, ...): elected, not joined
"""
import re

ORGS = [
    # Yale senior societies
    ("Skull and Bones", "society", "Yale", r"Skull and Bones|\bBonesmen\b"),
    ("Scroll and Key", "society", "Yale", r"Scroll and Key"),
    ("Wolf's Head", "society", "Yale", r"Wolf'?s Head Society|\bWolf'?s Head\b"),
    ("Book and Snake", "society", "Yale", r"Book and Snake"),
    ("Elihu", "society", "Yale", r"Elihu (?:Club|Society)|\bElihu\b(?= senior society)"),
    ("Berzelius", "society", "Yale", r"Berzelius (?:Society|senior society)"),
    ("Manuscript Society", "society", "Yale", r"Manuscript Society"),
    ("St. Elmo", "society", "Yale", r"St\.? Elmo Society"),
    # Cornell, Dartmouth, Penn, others
    ("Quill and Dagger", "society", "Cornell", r"Quill and Dagger"),
    ("Sphinx Head", "society", "Cornell", r"Sphinx Head"),
    ("Telluride House", "club", "Cornell", r"Telluride (?:House|Association)"),
    ("Casque and Gauntlet", "society", "Dartmouth", r"Casque (?:and|&) Gauntlet"),
    ("Sphinx (Dartmouth)", "society", "Dartmouth", r"\bthe Sphinx\b.*Dartmouth|Dartmouth.*\bSphinx (?:society|senior society)"),
    ("Dragon (Dartmouth)", "society", "Dartmouth", r"Dragon (?:senior )?[Ss]ociety"),
    ("Green Key", "society", "Dartmouth", r"Green Key Society"),
    ("Friars Senior Society", "society", "Penn", r"Friars Senior Society"),
    ("Sphinx Senior Society", "society", "Penn", r"Sphinx Senior Society"),
    ("Philomathean Society", "society", "Penn", r"Philomathean Society"),
    ("St. Anthony Hall", "club", None, r"St\.? Anthony Hall|Delta Psi"),
    ("Seven Society", "society", "UVA", r"Seven Society"),
    ("Cambridge Apostles", "society", "Cambridge", r"Cambridge Apostles"),
    # Harvard final clubs and social clubs
    ("Porcellian Club", "club", "Harvard", r"Porcellian"),
    ("A.D. Club", "club", "Harvard", r"\bA\.?D\.? Club"),
    ("Fly Club", "club", "Harvard", r"\bFly Club"),
    ("Spee Club", "club", "Harvard", r"\bSpee Club|\bthe Spee\b"),
    ("Owl Club", "club", "Harvard", r"\bOwl Club"),
    ("Phoenix-S K Club", "club", "Harvard", r"Phoenix[- ]S\.? ?K"),
    ("Fox Club", "club", "Harvard", r"\bFox Club"),
    ("Delphic Club", "club", "Harvard", r"Delphic Club"),
    ("Hasty Pudding Club", "club", "Harvard", r"Hasty Pudding"),
    ("Signet Society", "club", "Harvard", r"Signet Society"),
    ("Harvard Society of Fellows", "honor", "Harvard", r"Harvard Society of Fellows|Society of Fellows at Harvard|Harvard's Society of Fellows"),
    # Princeton eating clubs
    ("Ivy Club", "club", "Princeton", r"\bIvy Club\b"),
    ("University Cottage Club", "club", "Princeton", r"Cottage Club"),
    ("Tiger Inn", "club", "Princeton", r"Tiger Inn"),
    ("Cap and Gown Club", "club", "Princeton", r"Cap and Gown"),
    ("Colonial Club", "club", "Princeton", r"Colonial Club"),
    ("Cannon Club", "club", "Princeton", r"Cannon (?:Dial )?Club"),
    ("Charter Club", "club", "Princeton", r"Charter Club"),
    ("Quadrangle Club", "club", "Princeton", r"Quadrangle Club"),
    ("Terrace Club", "club", "Princeton", r"Terrace Club"),
    ("Tower Club", "club", "Princeton", r"Tower Club"),
    ("Cloister Inn", "club", "Princeton", r"Cloister Inn"),
    ("American Whig–Cliosophic Society", "political", "Princeton", r"Whig[-–]Cliosophic|Whig-Clio"),
    # Oxford / Cambridge
    ("Bullingdon Club", "club", "Oxford", r"Bullingdon"),
    ("Piers Gaveston Society", "club", "Oxford", r"Piers Gaveston"),
    ("Gridiron Club (Oxford)", "club", "Oxford", r"Gridiron Club"),
    ("Oxford Union", "political", "Oxford", r"Oxford Union"),
    ("Cambridge Union", "political", "Cambridge", r"Cambridge Union"),
    ("Pitt Club", "club", "Cambridge", r"Pitt Club"),
    ("Footlights", "club", "Cambridge", r"Footlights"),
    ("Oxford University Conservative Association", "political", "Oxford", r"Oxford University Conservative Association|\bOUCA\b"),
    ("Oxford University Labour Club", "political", "Oxford", r"Oxford University Labour Club"),
    # Student publications
    ("The Harvard Crimson", "publication", "Harvard", r"Harvard Crimson(?! (?:football|basketball|men|women|hockey|baseball|rowing|crew|team|athletic|lacrosse|squash|soccer|track))"),
    ("Harvard Lampoon", "publication", "Harvard", r"Harvard Lampoon"),
    ("Harvard Advocate", "publication", "Harvard", r"Harvard Advocate"),
    ("Harvard Law Review", "publication", "Harvard", r"Harvard Law Review"),
    ("Yale Daily News", "publication", "Yale", r"Yale Daily News"),
    ("Yale Law Journal", "publication", "Yale", r"Yale Law Journal"),
    ("Yale Political Union", "political", "Yale", r"Yale Political Union"),
    ("The Daily Princetonian", "publication", "Princeton", r"Daily Princetonian"),
    ("Columbia Daily Spectator", "publication", "Columbia", r"Columbia (?:Daily )?Spectator"),
    ("Columbia Law Review", "publication", "Columbia", r"Columbia Law Review"),
    ("The Cornell Daily Sun", "publication", "Cornell", r"Cornell Daily Sun"),
    ("The Daily Pennsylvanian", "publication", "Penn", r"Daily Pennsylvanian"),
    ("The Dartmouth Review", "publication", "Dartmouth", r"Dartmouth Review"),
        ("Stanford Law Review", "publication", "Stanford", r"Stanford Law Review"),
    ("The Stanford Review", "publication", "Stanford", r"Stanford Review"),
    ("The Stanford Daily", "publication", "Stanford", r"Stanford Daily"),
    ("Georgetown Law Journal", "publication", "Georgetown", r"Georgetown Law Journal"),
    ("Duke Law Journal", "publication", "Duke", r"Duke Law Journal"),
    ("Michigan Law Review", "publication", "Michigan", r"Michigan Law Review"),
    ("Chicago Law Review", "publication", "Chicago", r"University of Chicago Law Review"),
    ("Cherwell", "publication", "Oxford", r"\bCherwell\b"),
    ("Isis magazine", "publication", "Oxford", r"\bIsis\b magazine|\bThe Isis\b"),
    # Student political organizations
    ("College Republicans", "political", None, r"College Republican"),
    ("College Democrats", "political", None, r"College Democrats"),
    ("Young Americans for Freedom", "political", None, r"Young Americans for Freedom"),
    ("Students for a Democratic Society", "political", None, r"Students for a Democratic Society"),
    # Honor societies (elected)
    ("Phi Beta Kappa", "honor", None, r"Phi Beta Kappa"),
    ("Alpha Omega Alpha", "honor", None, r"Alpha Omega Alpha"),
    ("Tau Beta Pi", "honor", None, r"Tau Beta Pi"),
    ("Order of the Coif", "honor", None, r"Order of the Coif"),
    ("Beta Gamma Sigma", "honor", None, r"Beta Gamma Sigma"),
    ("Omicron Delta Kappa", "honor", None, r"Omicron Delta Kappa"),
    ("Sigma Xi", "honor", None, r"Sigma Xi"),
    ("Phi Kappa Phi", "honor", None, r"Phi Kappa Phi"),
]
COMPILED = [(n, k, s, re.compile(rx)) for n, k, s, rx in ORGS]
SCHOOL_TOKENS = {
    "Yale": r"Yale", "Harvard": r"Harvard|Radcliffe", "Princeton": r"Princeton", "Cornell": r"Cornell",
    "Dartmouth": r"Dartmouth", "Penn": r"University of Pennsylvania|Wharton|\bPenn\b", "Oxford": r"Oxford",
    "Cambridge": r"Cambridge", "Stanford": r"Stanford", "Georgetown": r"Georgetown", "Duke": r"Duke",
    "Michigan": r"Michigan", "Chicago": r"University of Chicago", "UVA": r"University of Virginia",
}

# Membership wording that must appear in the same sentence.
MEMBER_RE = re.compile(
    r"\b(member|members|joined|elected|tapped|inducted|initiated|belonged|president|chairman|chair|"
    r"editor|editor-in-chief|co-?founded|founded|founder|wrote for|writer for|columnist|reporter for|"
    r"staff of|served on|served as|was in|was part of|secretary of|treasurer of|pledged)\b",
    re.I,
)
# Sentences about other people or later-life roles are skipped.
SKIP_RE = re.compile(
    r"\b(?:his|her|their|\w+'s)\s+(?:father|mother|wife|husband|son|daughter|brother|sister|"
    r"grandfather|grandmother|uncle|aunt|cousin)\b|\bhonorary\b|\bspoke (?:at|to)\b|\baddressed\b|"
    r"\bdebated at\b|\binvited\b|\bspeech\b|\bguest\b|\bprotest",
    re.I,
)
KIND_LABEL = {"society": "Secret / senior society", "club": "Club", "publication": "Student publication",
              "political": "Student political group", "honor": "Honor society"}


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[a-z0-9)]{2}[.!?])\s+(?=[A-Z\"(])|\n+", text) if s.strip()]


def detect_orgs(page, wd):
    """Return list of {name, kind, school, status, evidence[]} for college societies/clubs."""
    found = {}

    def add(name, kind, school, status, ev):
        o = found.setdefault(name, {"name": name, "kind": kind, "school": school, "status": status, "evidence": []})
        if status == "yes":
            o["status"] = "yes"
        if ev not in o["evidence"] and len(o["evidence"]) < 3:
            o["evidence"].append(ev)

    wd_url = f"https://www.wikidata.org/wiki/{page['qid']}" if page.get("qid") else None
    background = " ".join([e["label"] for e in wd.get("educated_at", [])] + page.get("categories", []))

    def school_ok(school, sentence):
        """The club's school must appear in the sentence or in the person's education/categories."""
        if not school:
            return True
        tok = SCHOOL_TOKENS.get(school, school)
        return bool(re.search(tok, sentence) or re.search(tok, background))
    for m in wd.get("member_of", []):
        for name, kind, school, rx in COMPILED:
            if rx.search(m["label"]):
                add(name, kind, school, "yes", {"source": "Wikidata (member of)", "text": m["label"], "url": wd_url})
    for c in page.get("categories", []):
        for name, kind, school, rx in COMPILED:
            if rx.search(c) and re.search(r"members|people|alumni|presidents|editors|writers|staff|fellows", c, re.I):
                add(name, kind, school, "yes", {"source": "Wikipedia category", "text": c, "url": page["url"]})
    for s in sentences(page.get("text", "")):
        if SKIP_RE.search(s) or not MEMBER_RE.search(s):
            continue
        for name, kind, school, rx in COMPILED:
            if rx.search(s) and school_ok(school, s):
                add(name, kind, school, "possible", {"source": "Wikipedia article text", "text": s[:400], "url": page["url"]})
    return list(found.values())
