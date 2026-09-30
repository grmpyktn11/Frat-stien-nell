"""Extract candidate names from Wikipedia's 'List of people named in the Epstein files'.

The list article only includes notable people (those with Wikipedia articles),
which is the public-figure filter. Entries may be section headings, bullet
items, or table rows; all three layouts are handled.
"""
import re

from common import wp

SOURCE_PAGE = "List_of_people_named_in_the_Epstein_files"

# Keyword -> document category shown on the site.
DOC_TYPES = [
    ("Flight logs", r"flight log|flight manifest|flight record|lolita express|flew on|jet travel"),
    ("Black book", r"black book|little black book|contact book|address book|phone book|contact list"),
    ("Court documents", r"court document|unsealed|deposition|testimony|giuffre|lawsuit|court record|affidavit"),
    ("DOJ / Congressional release", r"department of justice|\bdoj\b|house oversight|epstein files|epstein files transparency|released by|release of"),
    ("Emails", r"\bemails?\b|correspondence"),
    ("Birthday book", r"birthday book"),
    ("Photographs", r"photograph|pictured"),
    ("Financial records", r"suspicious activity report|jpmorgan|payment|wire transfer|bank record|donation"),
]

LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
HEADING_RE = re.compile(r"^(={2,6})\s*(.*?)\s*\1\s*$")
SKIP_HEADINGS = {"see also", "references", "notes", "external links", "further reading", "bibliography", "sources"}


def strip_markup(s):
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = LINK_RE.sub(lambda m: m.group(0).split("|")[-1].strip("[]"), s)
    s = re.sub(r"'{2,}", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


def first_link(s):
    m = LINK_RE.search(s)
    return m.group(1).strip() if m else None


def classify(text):
    t = text.lower()
    return [label for label, pat in DOC_TYPES if re.search(pat, t)]


def parse_wikitext(wikitext):
    """Return list of {title, context} candidate entries (unresolved)."""
    lines = wikitext.splitlines()
    entries = []
    current = None  # entry being built from a heading
    stop = False
    for line in lines:
        h = HEADING_RE.match(line)
        if h:
            text = h.group(2)
            plain = strip_markup(text)
            if plain.lower() in SKIP_HEADINGS:
                stop = True
            if stop:
                current = None
                continue
            # Single-letter / range headings like "A", "A–C" are index headings.
            if len(plain) <= 3 or re.fullmatch(r"[A-Z]\s*[–-]\s*[A-Z]", plain):
                current = None
                continue
            current = {"title": first_link(text) or plain, "context": ""}
            entries.append(current)
            continue
        if stop:
            continue
        stripped = line.strip()
        # Bullet entries: "* [[Name]] – description"
        if re.match(r"^[*#]", stripped) and current is None:
            link = first_link(stripped)
            if link and stripped.lstrip("*# ").startswith(("[[", "'''[[", "''[[")):
                entries.append({"title": link, "context": strip_markup(stripped)})
            continue
        # Table rows: "| [[Name]] || ..." – first cell link
        if stripped.startswith("|") and not stripped.startswith(("|-", "|}", "|+")) and current is None:
            first_cell = re.split(r"\|\|", stripped.lstrip("| "), maxsplit=1)[0]
            link = first_link(first_cell)
            if link:
                entries.append({"title": link, "context": strip_markup(stripped)})
            continue
        if current is not None:
            current["context"] += " " + line
    for e in entries:
        e["context"] = strip_markup(e["context"])[:4000]
    return entries


def fetch_source_wikitext():
    data = wp({"action": "parse", "page": SOURCE_PAGE, "prop": "wikitext|revid", "redirects": 1})
    return data["parse"]["wikitext"], data["parse"]["revid"]


def get_entries():
    wikitext, revid = fetch_source_wikitext()
    entries = parse_wikitext(wikitext)
    for e in entries:
        e["documents"] = classify(e["context"])
    return entries, revid


if __name__ == "__main__":
    entries, revid = get_entries()
    print(f"revision {revid}: {len(entries)} candidate entries")
    for e in entries[:20]:
        print(" -", e["title"], e["documents"])
