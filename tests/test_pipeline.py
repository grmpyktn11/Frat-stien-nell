import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "pipeline"))

from enrich import detect_ivy, detect_school, detect_frat, exclusion_reason  # noqa: E402
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
    assert r["status"] == "possible" and r["faculty"]


def test_harvard_professor_is_faculty_not_alumnus():
    r = detect_ivy(page("He received his PhD from Stanford University. He is a professor of genetics at Harvard Medical School."), {})
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
