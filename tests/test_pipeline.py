import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "pipeline"))

from enrich import detect_ivy, detect_school, detect_frat, exclusion_reason  # noqa: E402
from graph import build_graph, canonical_institution  # noqa: E402
from orgs import detect_orgs  # noqa: E402
from scrape_names import parse_wikitext  # noqa: E402

HEADING_STYLE = """Intro text.
== A ==
=== [[Woody Allen]] ===
Allen appears in photographs and emails released by the House Oversight Committee.<ref>x</ref>
=== Dr. Stephen Alexander ===
Named in court documents and a deposition.
== B ==
* [[Steve Bannon]] – text messages and emails
== See also ==
* [[Jeffrey Epstein]]
"""

BULLET_STYLE = """== A–C ==
* '''[[Doug Band]]''', Clinton aide – flight logs and emails
* [[Bill Clinton|William J. Clinton]] – flight logs (16+ trips)
== References ==
* [[Not A Person]]
"""

TABLE_STYLE = """{| class="wikitable"
! Name !! Role !! Source
|-
| [[Glenn Dubin]] || Hedge fund manager || flight records, testimony
|-
| [[Leon Black]] || Investor || JPMorgan suspicious activity report
|}
"""


def titles(wt):
    return [e["title"] for e in parse_wikitext(wt)]


def test_heading_layout():
    es = parse_wikitext(HEADING_STYLE)
    assert [e["title"] for e in es] == ["Woody Allen", "Dr. Stephen Alexander", "Steve Bannon"]
    assert "House Oversight" in es[0]["context"]


def test_bullet_layout():
    assert titles(BULLET_STYLE) == ["Doug Band", "Bill Clinton"]


def test_table_layout():
    assert titles(TABLE_STYLE) == ["Glenn Dubin", "Leon Black"]


def page(text="", cats=(), desc="", qid="Q1"):
    return {"title": "X", "url": "https://en.wikipedia.org/wiki/X", "qid": qid,
            "description": desc, "categories": list(cats), "text": text}


def test_school_wikidata_yes():
    r = detect_school(page(), {"educated_at": [{"id": "Q49115", "label": "Cornell University"}]}, "Cornell")
    assert r["status"] == "yes"


def test_school_text_possible_and_faculty():
    r = detect_school(page("He graduated from Cornell in 1970. Later he taught as a professor at Cornell."), {}, "Cornell")
    assert r["status"] == "possible" and not r["faculty"]
    r = detect_school(page(), {"employer": [{"id": "Q1", "label": "Cornell University"}]}, "Cornell")
    assert r["faculty"] and r["status"] == "no"


def test_harvard_professor_is_faculty_not_alumnus():
    r = detect_ivy(page("He received his PhD from Stanford University. He is a professor of genetics at Harvard Medical School."), {})
    assert "Harvard" not in r
    r = detect_ivy(page(cats=["Harvard Medical School faculty"]), {})
    assert r["Harvard"]["status"] == "no" and r["Harvard"]["faculty"]


def test_wharton_and_law_categories():
    r = detect_ivy(page(cats=["Wharton School of the University of Pennsylvania alumni", "Yale Law School alumni"]), {})
    assert r["Penn"]["status"] == "yes" and r["Yale"]["status"] == "yes"


def test_false_positives():
    txt = ("He attended the University of British Columbia and Britannia Royal Naval College, Dartmouth. "
           "He graduated from Pennsylvania State University and Cornell College.")
    assert detect_ivy(page(txt), {}) == {}


def test_multiple_ivies_text():
    r = detect_ivy(page("She earned a B.A. from Brown University and an MBA from Columbia Business School."), {})
    assert r["Brown"]["status"] == "possible" and r["Columbia"]["status"] == "possible"


def test_no_ivy():
    assert detect_ivy(page("He went to Stanford."), {}) == {}


def test_frat_honor_society_not_counted():
    r = detect_frat(page("He was elected to Phi Beta Kappa."), {})
    assert r["status"] == "no" and r["honor_societies"] == ["Phi Beta Kappa"]


def test_frat_text_possible():
    r = detect_frat(page("At Penn he was a brother of Zeta Beta Tau."), {})
    assert r["status"] == "possible" and r["orgs"] == ["Zeta Beta Tau"]


def test_frat_wikidata_yes():
    wd = {"member_of": [{"id": "Q1", "label": "Delta Kappa Epsilon", "types": ["fraternity"]}]}
    r = detect_frat(page(), wd)
    assert r["status"] == "yes" and r["orgs"] == ["Delta Kappa Epsilon"]


def test_exclusion():
    assert exclusion_reason(page(desc="American sex trafficking survivor"), "")
    assert exclusion_reason(page("Jane Doe is an American who worked as Epstein's assistant."), "")
    assert exclusion_reason(page(desc="Microsoft co-founder"), "Gates met Epstein's assistant.") is None
    assert exclusion_reason(page(desc="American businessman"), "flight logs") is None


def test_heading_uses_body_link_for_disambiguated_name():
    wt = """== C ==
=== David Copperfield ===
{{Main|David Copperfield (illusionist)}}
Named in testimony.
=== Bill Clinton ===
{{Main|Relationship of Bill Clinton and Jeffrey Epstein}}
Flight logs.
=== George Church ===
[[George Church (geneticist)|George Church]], a Harvard professor, attended dinners.
"""
    assert titles(wt) == ["David Copperfield (illusionist)", "Bill Clinton", "George Church (geneticist)"]


def test_ivy_false_positive_patterns():
    txt = ("Ariely was born while his father was studying for an MBA at Columbia University. "
           "In 2015, Kamen received an honorary Doctor of Engineering degree from Yale University. "
           "Black is married to Debra Ressler, a 1976 Barnard College graduate. "
           "He was admitted as a preparator at Princeton University in 1975.")
    assert detect_ivy(page(txt), {}) == {}
    r = detect_ivy(page("After her graduate work at Harvard, Randall held professorships at MIT and Princeton University."), {})
    assert r["Harvard"]["status"] == "possible"
    assert "Princeton" not in r
    assert detect_ivy(page(), {"educated_at": [{"id": "Q1", "label": "Yale-China Chinese Language Center"}]}) == {}


def test_frat_false_positive_patterns():
    txt = ("Musk pledged $1 billion of funding. The prize goes to whoever does the most for fraternity between nations. "
           "Upon assuming office, Bryan pledged to fill his cabinet.")
    assert detect_frat(page(txt), {})["status"] == "no"
    wd = {"member_of": [{"id": "Q1", "label": "Phi Beta Kappa Society", "types": ["honor society"]},
                        {"id": "Q2", "label": "Kappa Beta Phi", "types": ["organization", "honor society"]}]}
    r = detect_frat(page(), wd)
    assert r["status"] == "no" and len(r["honor_societies"]) == 2


def test_canonical_institution():
    assert canonical_institution("The Wharton School") == "University of Pennsylvania"
    assert canonical_institution("Walsh School of Foreign Service") == "Georgetown University"
    assert canonical_institution("Columbia University College of Physicians and Surgeons (MD)") == "Columbia University"
    assert canonical_institution("Harvard Business School") == "Harvard University"
    assert canonical_institution("Stuyvesant High School") is None
    assert canonical_institution("Middlesex School") is None
    assert canonical_institution("Phillips Academy") is None
    assert canonical_institution("SUNY Binghamton (BA)") == "SUNY Binghamton"


def test_build_graph_links_shared_colleges_and_frats():
    def person(name, edu, orgs=()):
        return {"name": name, "education": edu, "schools": {},
                "frat": {"status": "yes" if orgs else "no", "orgs": list(orgs)}}
    g = build_graph([
        person("A", ["Stanford University"], ["Sigma Chi"]),
        person("B", ["Stanford Graduate School of Business"]),
        person("C", ["Tulane University"]),
        person("D", ["Yale Law School"]),
    ])
    ids = {n["id"] for n in g["nodes"]}
    assert "i:Stanford University" in ids and "f:Sigma Chi" in ids and "i:Yale University" in ids
    assert "i:Tulane University" not in ids and "p:C" not in ids
    assert g["counts"]["people_linked"] == 3


def test_false_claims_ignored():
    txt = "Oppenheimer reported that Seckel cultivated a false image of himself as a graduate from Cornell."
    assert detect_ivy(page(txt), {}) == {}


def test_relatives_and_chapters():
    txt = ("Madoff had two sons: Mark, a graduate of Michigan, and Andrew, a 1988 graduate of the Wharton School. "
           "Another great-grandfather graduated from Yale University. His aunt was dean of Columbia University Mailman School.")
    assert detect_ivy(page(txt), {}) == {}
    r = detect_frat(page("He served as president of the Zeta Phi chapter of the Beta Theta Pi fraternity."), {})
    assert r["orgs"] == ["Beta Theta Pi"]
    r = detect_frat(page("NPR identifies the street address of the Sigma Chi fraternity house as the location."), {})
    assert r["status"] == "no"


def test_detect_orgs():
    txt = ("At Yale he was tapped for Skull and Bones. He later spoke at the Oxford Union. "
           "He played for the Harvard Crimson football team as a member. "
           "He was a member of the Tower Club in Dallas. "
           "He was editor-in-chief of the Yale Law Journal.")
    names = {o["name"]: o for o in detect_orgs(page(txt), {"educated_at": [{"id": "Q1", "label": "Yale University"}]})}
    assert set(names) == {"Skull and Bones", "Yale Law Journal"}
    assert names["Skull and Bones"]["kind"] == "society" and names["Skull and Bones"]["status"] == "possible"
    r = detect_orgs(page(cats=["Members of Skull and Bones"]), {})
    assert r[0]["status"] == "yes"
