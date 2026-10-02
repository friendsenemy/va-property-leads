"""
Obituaries from Storke Funeral Home (King George, Colonial Beach, Bowling Green;
it also carries Nash & Slaw's). This is the only local obituary source whose
terms allow automated reading: no terms page, robots.txt allows everything, and
the site publishes an official obituary RSS feed. See docs/sources-and-terms.md.

  python -m engine.obits --daily       # RSS feed, 1 request: the 25 newest
  python -m engine.obits --backfill    # every listing page (~105 requests, one per 2 s)
  python -m engine.obits --details     # exact dates for name-matched obituaries only

Only facts are stored (name, dates, age, place, link) in data/obits/storke.json.
The obituary text is not copied; each record links to it.
"""
import argparse
import datetime as dt
import html
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET

import requests

from engine import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("obits")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "obits", "storke.json")

BASE = "https://storkefuneralhome.com/storke-funeral-home-obituaries/"
FEED = "https://storkefuneralhome.com/feed/storke-funeral-home-obituaries-xml/"
PAUSE_S = 2.0
SOURCE = "Storke Funeral Home"

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
_MON = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
_DATE = re.compile(rf"({_MON})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", re.I)
_TITLES = re.compile(r"(?:Col|Colonel|Dr|Rev|Reverend|Mr|Mrs|Ms|Miss|Sgt|Capt|Captain|Lt|Maj|Major|Cdr|Gen|Pastor|Deacon|Elder|Sister|Brother|Judge)\.?", re.I)
_SUFFIX = re.compile(r",?\s+(Jr|Sr|II|III|IV)\.?$", re.I)
_STATES = r"Virginia|VA|Va\.?|Maryland|MD|Md\.?|North Carolina|NC|Florida|FL|Pennsylvania|PA|West Virginia|WV|D\.?C\.?|South Carolina|SC|Delaware|DE|Georgia|GA|Tennessee|TN|Texas|TX|New York|NY"
_AGE_PLACE = re.compile(
    rf",?\s*(?:age\s+)?(?P<age>\d{{1,3}}),?\s+(?:a\s+(?:longtime\s+|lifelong\s+|long-time\s+)?resident\s+)?(?:formerly\s+)?of\s+"
    rf"(?P<place>[A-Z][A-Za-z.'\- ]{{1,40}}?)(?:,\s*(?P<state>{_STATES}))?[,.]?\s+(?=[a-z])", re.S)
_PLACE_ONLY = re.compile(rf"\bof\s+(?P<place>[A-Z][A-Za-z.'\- ]{{1,40}}?)(?:,\s*(?P<state>{_STATES}))?[,.]?\s+(?:passed|died|went|departed|entered|peacefully|was called|gained|transitioned)", re.S)
_AGE_ONLY = re.compile(r",\s*(?:age\s+)?(\d{2,3}),|\bat the age of (\d{2,3})\b|\baged? (\d{2,3})\b", re.I)


def session():
    s = requests.Session()
    s.headers["User-Agent"] = config.USER_AGENT
    return s


def _text(fragment):
    t = re.sub(r"<br\s*/?>|</p>", "\n", fragment, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"[ \t\r\f\v]+", " ", html.unescape(t)).strip()


def iso(month, day, year):
    m = MONTHS.get(month.lower().rstrip(".")) or next((v for k, v in MONTHS.items() if k.startswith(month.lower().rstrip(".")[:3])), None)
    try:
        return dt.date(int(year), m, int(day)).isoformat()
    except (TypeError, ValueError):
        return ""


def parse_name(title):
    """
    The site prints the name as 'First  Middle  Last' with a double space between
    the three parts, so the parts are unambiguous. Falls back to plain tokens.
    """
    raw = html.unescape(title).replace("\xa0", " ").strip()
    suffix = ""
    m = _SUFFIX.search(raw)
    if m:
        suffix, raw = m.group(1).upper(), raw[:m.start()]
    nick = re.findall(r"[\"“(']([A-Za-z .]+)[\"”)']", raw)
    raw = re.sub(r"[\"“(][^\"”)]*[\"”)]", " ", raw)
    parts = [p.strip() for p in re.split(r"\s{2,}", raw.strip()) if p.strip()]
    if len(parts) > 2 and _TITLES.fullmatch(parts[0]):
        parts = parts[1:]                                  # "Col  Florentino  Carter"
    maiden = ""
    if len(parts) >= 4:                                    # First  Middle  Maiden  Last
        first, middle, maiden, last = parts[0], " ".join(parts[1:-2]), parts[-2], parts[-1]
    elif len(parts) == 3:
        first, middle, last = parts
    elif len(parts) == 2:
        first, middle, last = parts[0], "", parts[1]
    else:
        toks = raw.split()
        if len(toks) > 2 and _TITLES.fullmatch(toks[0]):
            toks = toks[1:]
        if len(toks) < 2:
            return None
        first, middle, last = toks[0], " ".join(toks[1:-1]), toks[-1]
    m = _SUFFIX.search(" " + last)
    if m:
        suffix, last = m.group(1).upper(), (" " + last)[:m.start()].strip()
    clean = lambda s: re.sub(r"[^A-Za-z'\- ]", "", s).strip().upper()
    return {"first": clean(first), "middle": clean(middle), "last": clean(last), "suffix": suffix,
            "nickname": clean(nick[0]) if nick else "", "maiden": clean(maiden)}


_PARTICLES = {"VAN", "VON", "DE", "DEL", "DELA", "LA", "LE", "ST", "MC", "DI", "DA", "DER", "DEN", "O"}


def split_last(rec):
    """'LOUISE OLIVER ENSMINGER' in the last-name slot -> middle LOUISE, maiden OLIVER, last ENSMINGER."""
    toks = rec["last"].split()
    if len(toks) < 2:
        return rec
    keep = [toks[-1]]
    rest = toks[:-1]
    while rest and rest[-1] in _PARTICLES:
        keep.insert(0, rest.pop())
    rec["last"] = " ".join(keep)
    if rest and not rec.get("middle"):
        rec["middle"] = rest.pop(0)
    if rest and not rec.get("maiden"):
        rec["maiden"] = " ".join(rest)
    return rec


def parse_lede(text):
    """Age, place and death date from the first lines of the obituary."""
    out = {"age": None, "place": "", "state": "", "death_date": ""}
    lede = text[:600]
    m = _AGE_PLACE.search(lede)
    if m:
        out["age"] = int(m.group("age"))
        out["place"], out["state"] = m.group("place").strip(" ,."), (m.group("state") or "").strip(".")
    else:
        m = _PLACE_ONLY.search(lede)
        if m:
            out["place"], out["state"] = m.group("place").strip(" ,."), (m.group("state") or "").strip(".")
        a = _AGE_ONLY.search(lede)
        if a:
            out["age"] = int(next(g for g in a.groups() if g))
    if out["age"] is not None and not 0 < out["age"] < 115:
        out["age"] = None
    d = re.search(r"(?:passed|died|went|departed|entered|called|transitioned|gained|left)[^.]{0,120}?" + _DATE.pattern, lede, re.I | re.S)
    if d:
        out["death_date"] = iso(d.group(1), d.group(2), d.group(3))
    return out


def parse_listing(page_html):
    """Listing page -> records (25 per page)."""
    out = []
    for block in re.split(r'<div class="wpfh_obit">', page_html)[1:]:
        m = re.search(r'class="wpfh_obit_title"><a href="[^"]*\?id=(\d+)">(.*?)</a>', block, re.S)
        if not m:
            continue
        name = parse_name(re.sub(r"<[^>]+>", "", m.group(2)))
        if not name:
            continue
        body = re.search(r'class="wpfh_obit_date">.*?</p>(.*?)</div>', block, re.S)
        rec = dict(name, id=int(m.group(1)), url=f"{BASE}?id={m.group(1)}", source=SOURCE, birth_date="")
        rec.update(parse_lede(_text(body.group(1)) if body else ""))
        out.append(rec)
    return out


def parse_detail(page_html):
    """Exact dates from the page header, plus age and place from the full first paragraph."""
    out = {}
    m = re.search(r"<title>\s*Remembering\s+(.*?)\s*\|", page_html, re.S)
    if m:
        out["_name"] = parse_name(m.group(1))
    head = re.search(rf"({_MON})\s+(\d{{1,2}}),\s+(\d{{4}})\s*(?:&#8211;|–|-)\s*({_MON})\s+(\d{{1,2}}),\s+(\d{{4}})", page_html, re.I)
    if head:
        out["birth_date"] = iso(head.group(1), head.group(2), head.group(3))
        out["death_date"] = iso(head.group(4), head.group(5), head.group(6))
    c = re.search(r'class="wpfh-obituary-content">(.*?)</div>', page_html, re.S)
    if c:
        lede = parse_lede(_text(c.group(1)))
        for k in ("age", "place", "state"):
            if lede[k]:
                out[k] = lede[k]
        if not out.get("death_date") and lede["death_date"]:
            out["death_date"] = lede["death_date"]
    return out


def parse_feed(xml_text):
    out = []
    root = ET.fromstring(xml_text.encode("utf-8"))
    for item in root.iter("item"):
        g = lambda tag: (item.findtext(tag) or "").strip()
        m = re.search(r"\?id=(\d+)", g("link"))
        if not m or not g("last_name"):
            continue
        up = lambda s: re.sub(r"[^A-Za-z'\- ]", "", s).strip().upper()
        last, suffix = g("last_name"), ""
        sm = _SUFFIX.search(" " + last)
        if sm:
            suffix, last = sm.group(1).upper(), (" " + last)[:sm.start()].strip()

        def rss_date(s):
            d = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", s)
            return iso(d.group(2), d.group(1), d.group(3)) if d and int(d.group(3)) > 1850 else ""
        rec = {"first": up(g("first_name")), "middle": up(g("middle_name")), "last": up(last), "suffix": suffix, "nickname": "",
               "maiden": up(g("maiden_name")), "id": int(m.group(1)), "url": f"{BASE}?id={m.group(1)}", "source": SOURCE,
               "birth_date": rss_date(g("birth_date"))}
        lede = parse_lede(_text(g("description")))
        rec.update(lede)
        rec["death_date"] = rss_date(g("death_date")) or lede["death_date"]
        out.append(rec)
    return out


def load():
    if os.path.exists(STORE):
        return {r["id"]: split_last(r) for r in json.load(open(STORE))["rows"]}
    return {}


def load_extra():
    """
    Obituaries from anywhere else, keyed 'file:id'.

    data/obits/manual.csv   one line per death you found by hand:
        last,first,middle,suffix,death_date,age,place,url
        (death_date as YYYY-MM-DD; only last and first are required)
    data/obits/*.json       any other file shaped like storke.json:
        {"rows": [{"id", "first", "middle", "last", "suffix", "death_date", "age", "place", "url", "source"}]}
    """
    import csv
    import glob
    out = {}
    d = os.path.dirname(STORE)
    mpath = os.path.join(d, "manual.csv")
    if os.path.exists(mpath):
        with open(mpath, newline="") as f:
            for n, row in enumerate(csv.DictReader(l for l in f if l.strip() and not l.startswith("#")), 1):
                up = lambda k: (row.get(k) or "").strip().upper()
                if not up("last") or not up("first"):
                    continue
                age = (row.get("age") or "").strip()
                out[f"manual:{n}"] = {"id": f"manual:{n}", "first": up("first"), "middle": up("middle"), "last": up("last"),
                                      "suffix": up("suffix").strip("."), "nickname": "", "maiden": "",
                                      "death_date": (row.get("death_date") or "").strip(), "birth_date": "",
                                      "age": int(age) if age.isdigit() else None, "place": (row.get("place") or "").strip(),
                                      "state": "", "url": (row.get("url") or "").strip(), "source": "Entered by hand", "detail": True}
    for path in sorted(glob.glob(os.path.join(d, "*.json"))):
        name = os.path.basename(path)[:-5]
        if name in ("storke", "matches", "low"):
            continue
        try:
            doc = json.load(open(path))
            items = doc if isinstance(doc, list) else (doc.get("rows") or doc.get("obituaries") or doc.get("leads") or [])
            for r in items:
                r = normalise_foreign(r)
                if not r.get("last") or not r.get("first"):
                    continue
                key = f"{name}:{r.get('id')}"
                rec = {"middle": "", "suffix": "", "nickname": "", "maiden": "", "death_date": "", "birth_date": "",
                       "age": None, "place": "", "state": "", "url": "", "source": name}
                rec.update(r)
                for k in ("first", "middle", "last", "suffix", "nickname", "maiden"):
                    rec[k] = str(rec.get(k) or "").upper().strip()
                rec["id"], rec["detail"] = key, True
                out[key] = split_last(rec)
        except Exception as e:  # noqa: BLE001
            log.warning("could not read %s: %s", path, e)
    return out


_ALIASES = {"first": ("first_name", "firstName"), "last": ("last_name", "lastName"), "middle": ("middle_name", "middleName"),
            "death_date": ("date_of_death", "deathDate", "dod"), "birth_date": ("date_of_birth", "birthDate", "dob"),
            "place": ("city", "primaryLocation", "location", "residence"), "url": ("obituary_url", "obituaryUrl", "link"),
            "id": ("obituaryId", "obituary_id", "key")}


def normalise_foreign(r):
    """Accept the field names other tools use (the Maryland scraper's, common export shapes)."""
    r = dict(r)
    for want, others in _ALIASES.items():
        if not r.get(want):
            r[want] = next((r[o] for o in others if r.get(o)), r.get(want) or "")
    if not r.get("first") and r.get("full_name" if "full_name" in r else "fullName"):
        n = parse_name(str(r.get("full_name") or r.get("fullName")))
        if n:
            r.update({k: v for k, v in n.items() if v})
    for k in ("death_date", "birth_date"):                 # any common date shape -> YYYY-MM-DD
        v = str(r.get(k) or "").strip()
        if v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            m = _DATE.search(v)
            m2 = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", v)
            m3 = re.match(r"(\d{4})-(\d{2})-(\d{2})", v)
            r[k] = iso(m.group(1), m.group(2), m.group(3)) if m else \
                (f"{m2.group(3)}-{int(m2.group(1)):02d}-{int(m2.group(2)):02d}" if m2 else (m3.group(0) if m3 else ""))
    if isinstance(r.get("place"), (list, dict)):
        r["place"] = ""
    r["place"] = re.sub(r",\s*(VA|Virginia|MD|Maryland)\.?$", "", str(r.get("place") or "")).strip()
    try:
        r["age"] = int(r["age"]) if str(r.get("age") or "").strip().isdigit() else None
    except (TypeError, ValueError):
        r["age"] = None
    if not r.get("id"):
        r["id"] = re.sub(r"\W+", "", f"{r.get('last')}{r.get('first')}{r.get('death_date')}")
    return r


def save(recs):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    rows = sorted(recs.values(), key=lambda r: -r["id"])
    with open(STORE, "w") as f:
        f.write('{"source":"%s","updated_at":"%s","count":%d,"rows":[\n' % (
            SOURCE, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), len(rows)))
        f.write(",\n".join(json.dumps(r, separators=(",", ":"), sort_keys=True) for r in rows))
        f.write("\n]}\n")


def merge(recs, new):
    added = 0
    for r in new:
        split_last(r)
        old = recs.get(r["id"])
        if not old:
            recs[r["id"]] = r
            added += 1
        else:                                   # keep anything already learned from the detail page
            for k, v in r.items():
                if v and not old.get(k):
                    old[k] = v
    return added


def daily(recs):
    r = session().get(FEED, timeout=60)
    r.raise_for_status()
    added = merge(recs, parse_feed(r.text))
    log.info("feed: %s new obituaries", added)
    return added


def backfill(recs, max_pages=400):
    s, added, page = session(), 0, 1
    seen_pages = set()
    while page <= max_pages:
        r = s.get(BASE, params={"f": "obits", "pagenum": page}, timeout=60)
        r.raise_for_status()
        items = parse_listing(r.text)
        ids = tuple(i["id"] for i in items)
        if not items or ids in seen_pages:       # past the end the site repeats the last page
            break
        seen_pages.add(ids)
        added += merge(recs, items)
        if page % 10 == 0:
            log.info("page %s: %s obituaries so far", page, len(recs))
        page += 1
        time.sleep(PAUSE_S)
    log.info("backfill: %s pages, %s new, %s total", page - 1, added, len(recs))
    return added


def details(recs, ids, limit=400):
    """Exact birth/death dates for the given obituary ids (name-matched ones only)."""
    s, n, fails = session(), 0, 0
    for i in ids:
        r = recs.get(i)
        if not r or r.get("detail"):
            continue
        if n >= limit:
            log.info("detail limit %s reached; the rest wait for the next run", limit)
            break
        try:
            resp = s.get(BASE, params={"id": i}, timeout=60)
        except requests.RequestException as e:
            fails += 1
            log.warning("obituary %s not fetched (%s)", i, e)
            if fails > 10:
                break
            time.sleep(15)
            continue
        if resp.status_code == 200:
            d = parse_detail(resp.text)
            d.pop("_name", None)
            r.update({k: v for k, v in d.items() if v})
            r["detail"] = True
        n += 1
        if n % 50 == 0:
            save(recs)                      # keep progress if the run is cut short
        time.sleep(PAUSE_S)
    log.info("details: fetched %s pages", n)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--max-pages", type=int, default=400)
    args = ap.parse_args()
    recs = load()
    if args.backfill:
        backfill(recs, args.max_pages)
    if args.daily or not args.backfill:
        daily(recs)
    save(recs)


if __name__ == "__main__":
    main()
