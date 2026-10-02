"""
What does the Wayback Machine hold for the funeral homes that serve King George?

  python -m engine.wayback_survey     (run from GitHub Actions; archive.org is not
                                       reachable from every network)

Asks the Internet Archive's CDX index (its public API) which obituary pages it has
for each home, by year, and saves a few sample pages so a parser can be written
against the real markup. Writes data/obits/wayback-survey.json. This is a one-off
look, not a harvest: at most ~40 requests, 3 seconds apart.
"""
import collections
import html
import json
import os
import re
import time

import requests

from engine import config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "obits", "wayback-survey.json")
CDX = "https://web.archive.org/cdx/search/cdx"
DOMAINS = ["storkefuneralhome.com", "nashandslawfuneralhome.com", "nashandslaw.com", "nashslawfuneralhome.com",
           "covenantfuneralservice.com", "mullinsthompsonfredericksburg.com", "mullinsthompsonstafford.com",
           "foundandsons.com", "albennettandsonfuneralhome.com", "johnsonfuneralhomeva.com", "welchfuneralhomeva.com"]
OBIT = re.compile(r"obit|rem\.html|remembr|tribute|memorial|book-of-memories|/fh/obituaries|death-notice", re.I)
S = requests.Session()
S.headers["User-Agent"] = config.USER_AGENT


def get(url, **kw):
    for attempt in range(3):
        try:
            r = S.get(url, timeout=120, **kw)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(10 * (attempt + 1))
    return None


def text_of(page):
    t = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", page, flags=re.S)
    t = re.sub(r"<[^>]+>", "\n", t)
    return re.sub(r"\n\s*\n+", "\n", html.unescape(t)).strip()


def main():
    out = {}
    for d in DOMAINS:
        r = get(CDX, params={"url": d, "matchType": "domain", "fl": "timestamp,original",
                             "filter": "statuscode:200", "collapse": "urlkey", "limit": "20000"})
        time.sleep(3)
        if r is None:
            out[d] = {"error": "CDX not reachable"}
            continue
        rows = [l.split(" ", 1) for l in r.text.splitlines() if " " in l]
        diag = {"status": r.status_code, "bytes": len(r.text), "head": r.text[:200]}
        ob = [x for x in rows if OBIT.search(x[1]) and not re.search(r"\.(jpg|jpeg|png|gif|css|js|ico|svg|woff2?)(\?|$)", x[1], re.I)]
        pat = collections.Counter(re.sub(r"\d+", "N", re.sub(r"^https?://[^/]+", "", u).split("?")[0])[:60] +
                                  ("?" + "&".join(sorted(k.split("=")[0] for k in u.split("?", 1)[1].split("&"))) if "?" in u else "")
                                  for _t, u in ob)
        info = {"urls": len(rows), "obituary_like": len(ob), "cdx": diag,
                "by_capture_year": dict(sorted(collections.Counter(t[:4] for t, _u in ob).items())),
                "top_patterns": pat.most_common(15), "samples": []}
        # one sample page per top pattern (max 3), earliest and a middle capture
        picked = []
        for p, _n in pat.most_common(3):
            cands = [x for x in ob if re.sub(r"\d+", "N", re.sub(r"^https?://[^/]+", "", x[1]).split("?")[0])[:60] == p.split("?")[0]]
            if cands:
                picked.append(cands[len(cands) // 2])
        for t, u in picked:
            pg = get(f"https://web.archive.org/web/{t}id_/{u}")
            time.sleep(3)
            if pg is not None:
                info["samples"].append({"timestamp": t, "url": u, "html_head": pg.text[:1500], "text": text_of(pg.text)[:5000],
                                        "html_len": len(pg.text)})
        out[d] = info
        print(d, info["urls"], info["obituary_like"], info["by_capture_year"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)


if __name__ == "__main__":
    main()
