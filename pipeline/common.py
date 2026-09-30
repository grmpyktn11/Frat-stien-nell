"""Shared HTTP helpers for Wikipedia / Wikidata access."""
import time

import requests

UA = "BigRedFlags/1.0 (https://github.com/grmpyktn11/Frat-stien-nell) python-requests"
WP_API = "https://en.wikipedia.org/w/api.php"
WD_SPARQL = "https://query.wikidata.org/sparql"

_session = requests.Session()
_session.headers.update({"User-Agent": UA})


def get_json(url, params, retries=6, pause=0.15, post=False):
    for attempt in range(retries):
        try:
            r = (_session.post(url, data=params, timeout=60) if post
                 else _session.get(url, params=params, timeout=60))
            if r.status_code == 429:
                time.sleep(min(60, float(r.headers.get("Retry-After", 5) or 5)))
                raise requests.HTTPError("HTTP 429")
            if r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            time.sleep(pause)
            return r.json()
        except (requests.RequestException, ValueError):
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 2)


def wp(params):
    base = {"format": "json", "formatversion": "2"}
    base.update(params)
    # Long title batches exceed URL limits; queries are read-only so POST is safe.
    return get_json(WP_API, base, post=len(str(params.get("titles", ""))) > 1500)


def sparql(query):
    return get_json(WD_SPARQL, {"query": query, "format": "json"}, pause=1.0)


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]
