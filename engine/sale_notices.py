"""
Judicial tax-sale notices for King George County.

  python -m engine.sale_notices

King George's delinquent real estate is collected by Sands Anderson PC (Treasurer
FAQ, item 16). The firm lists upcoming auctions on one HTML page. This reads that
page once a week and records any notice that names King George.

The parcel list for a sale is a PDF, and the firm's robots.txt disallows PDFs, so
the PDF is NOT fetched: the notice carries its link for you to open. Type the tax
map numbers from it into data/sales/parcels.csv (one PIN per line, with the sale
date) and the next run joins them to the board.

In Virginia the property itself is sold and the owner's right to redeem ends
before the sale date (Va. Code 58.1-3974), so a listed parcel is a lead only
until the auction.
"""
import csv
import datetime as dt
import html
import json
import logging
import os
import re
import sqlite3

import requests

from engine import config, title_scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("sale_notices")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "sales")
PAGE = "https://www.sandsanderson.com/services/delinquent-real-estate-tax-collection"
_DATE = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})")
MONTHS = "January February March April May June July August September October November December".split()


def parse_notices(page):
    """Every auction notice on the page: locality, date, links."""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    i = t.find("Public Auctions for Tax Delinquent Real Estate")
    if i < 0:
        return None
    j = t.find("News &amp; Insights", i)
    seg = t[i:j if j > 0 else i + 20000]
    # keep link targets while flattening to text
    seg = re.sub(r'<a[^>]*href="([^"]+)"[^>]*>', lambda m: f" [[{html.unescape(m.group(1))}]] ", seg)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", seg)))
    # a notice starts at an all-capitals heading such as "NOTICE OF JUDICIAL SALE OF REAL ESTATE IN X COUNTY"
    starts = [m.start() for m in re.finditer(r"(?:NOTICE OF|PUBLIC)\b[A-Z ,&-]{10,160}?(?:COUNTY|CITY OF [A-Z]+|TOWN OF [A-Z]+)", text)]
    # the heading is itself the link to the sale list, so its [[href]] sits just before it
    for k, st in enumerate(starts):
        m = re.search(r"\[\[[^\]]*\]\]\s*$", text[max(0, st - 400):st])
        if m:
            starts[k] = max(0, st - 400) + m.start()
    out = []
    for k, st in enumerate(starts):
        part = text[st:starts[k + 1] if k + 1 < len(starts) else len(text)]
        head = re.sub(r"\[\[.*?\]\]", " ", part)
        m = re.search(r"(?:IN|OF)\s+((?:[A-Z]+\s){1,3})COUNTY|(?:CITY|TOWN) OF ((?:[A-Z]+\s?){1,3})", head[:220])
        d = _DATE.search(head)
        links = re.findall(r"\[\[(.*?)\]\]", part)
        out.append({
            "locality": (m.group(1) or m.group(2)).strip().title() if m else "",
            "heading": re.sub(r"\s+", " ", head)[:140].strip(),
            "sale_date": f"{d.group(3)}-{MONTHS.index(d.group(1)) + 1:02d}-{int(d.group(2)):02d}" if d else "",
            "list_pdf": next(("https://www.sandsanderson.com" + l if l.startswith("/") else l for l in links if l.lower().endswith(".pdf")), ""),
            "bid_url": next((l for l in links if "forsaleatauction" in l), ""),
        })
    return out


def run(today=None):
    today = today or dt.date.today()
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "notices.json")
    store = json.load(open(path)) if os.path.exists(path) else {"notices": []}
    r = requests.get(PAGE, headers={"User-Agent": config.USER_AGENT}, timeout=60)
    r.raise_for_status()
    found = parse_notices(r.text)
    if found is None:
        log.error("auction section not found; the page layout has changed")
        found = []
    kg = [n for n in found if "king george" in (n["locality"] + " " + n["heading"]).lower()]
    known = {(n["sale_date"], n["list_pdf"]) for n in store["notices"]}
    for n in kg:
        if (n["sale_date"], n["list_pdf"]) not in known:
            n["first_seen"] = today.isoformat()
            store["notices"].append(n)
    store.update({"checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "source": PAGE,
                  "localities_listed": sorted({n["locality"] for n in found if n["locality"]}),
                  "king_george_upcoming": [n for n in store["notices"] if n["sale_date"] >= today.isoformat()]})

    # parcels typed in by hand from the sale PDF
    ppath = os.path.join(OUT, "parcels.csv")
    listed = []
    if os.path.exists(ppath) and os.path.exists(title_scan.DB_PATH):
        con = sqlite3.connect(title_scan.DB_PATH)
        con.row_factory = sqlite3.Row
        by_pin = {re.sub(r"[\s\-]", "", r["pin"]).upper(): dict(r) for r in con.execute("SELECT * FROM parcels")}
        con.close()
        with open(ppath, newline="") as f:
            for row in csv.DictReader(l for l in f if l.strip() and not l.startswith("#")):
                pin = re.sub(r"[\s\-]", "", row.get("pin") or "").upper()
                p = by_pin.get(pin)
                if p and (row.get("sale_date") or "") >= today.isoformat():
                    listed.append({"pid": p["pid"], "pin": p["pin"], "owner": p["owner"], "site_addr": p["site_addr"],
                                   "total_value": p["total_value"], "sale_date": row.get("sale_date"), "note": row.get("note", "")})
    store["listed_parcels"] = listed
    json.dump(store, open(path, "w"), indent=1)
    if not os.path.exists(ppath):
        open(ppath, "w").write("# Tax map numbers from the sale PDF, typed in by hand. One parcel per line.\n# sale_date is YYYY-MM-DD.\npin,sale_date,note\n")
    log.info("%s notices on the page (%s); King George upcoming: %s; listed parcels joined: %s",
             len(found), ", ".join(store["localities_listed"]) or "none", len(store["king_george_upcoming"]), len(listed))
    return store


if __name__ == "__main__":
    run()
