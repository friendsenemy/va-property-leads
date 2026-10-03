"""
Unpaid real estate taxes from a county's published Open Tax List (Westmoreland).

  VAPL_COUNTY=westmoreland python -m engine.delinq_list              # fetch the county's current list, rebuild balances
  VAPL_COUNTY=westmoreland python -m engine.delinq_list --no-fetch   # rebuild from the lists already on file
  VAPL_COUNTY=westmoreland python -m engine.delinq_list --add list.pdf   # add a list the Treasurer sent you

Westmoreland's Treasurer publishes the whole delinquent real estate list as one PDF
(report TR501S, "OPEN TAX LIST"), linked from the Treasurer's page. One download
replaces a 25,000-request walk of the tax inquiry. Each list is parsed to
data/westmoreland/delinquency/lists/<date>.json and kept, so a parcel that is on the
list again months later can be told from one that was late once.

The newest list is the balance. A parcel not on it had nothing unpaid on that date.
Needs `pdftotext` (poppler-utils) for the column layout.
"""
import argparse
import datetime as dt
import json
import logging
import os
import re
import sqlite3
import subprocess

import requests

from engine import config, delinquency

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("delinq_list")

LISTS = os.path.join(delinquency.OUT, "lists")
TREASURER_PAGE = "https://www.westmoreland-county.org/186/Treasurers-Office"
KNOWN_LIST = "https://www.westmoreland-county.org/DocumentCenter/View/514/2025-RE-Delq-List"
UA = {"User-Agent": "Mozilla/5.0 (compatible; va-property-leads/1.0; +https://github.com/friendsenemy/va-property-leads)"}

_TICKET = re.compile(r"^(?P<left>.*?)\s+RE\s+(?P<year>(?:19|20)\d\d)\s+(?P<ticket>\d{6,})\s+(?P<tax>[\d,]*\.\d\d)\s+(?P<pen>[\d,]*\.\d\d)\s+"
                     r"(?P<int>[\d,]*\.\d\d)\s+(?P<total>[\d,]*\.\d\d)\s*(?P<status>.*)$")
_DATE = re.compile(r"CURRENT DATE:\s+(\d{1,2})/(\d{1,2})/(\d{4})")


def _n(v):
    return float(v.replace(",", "") or 0)


NAME_COLS = 37          # the name column; the map number starts to the right of it
_SKIP = re.compile(r"CURRENT DATE:|PEN & INT DATE:|^NAME\s+MAP#|^----|FINAL TOTAL|^\s*$")
_CSZ = re.compile(r"^(.*?)\s+([A-Z]{2})\s+(\d{5})(?:-\d{4})?$")


def parse(text):
    """-> (list date ISO, {map number without spaces: {name, map, tickets:[{year, ticket, total}], mail, status}})

    A block is one parcel: the first line carries the name and the map number, later lines
    carry more tickets on the right and the rest of the name and the mailing address on
    the left (the long February-style report prints the address; the summary does not)."""
    m = _DATE.search(text)
    listed = dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat() if m else ""
    out, cur = {}, None
    for line in text.splitlines():
        if _SKIP.search(line):
            continue
        t = _TICKET.match(line)
        left = (t.group("left") if t else re.sub(r"\s+TOTAL\s+[\d,.\s]+$", "", line)).rstrip()
        if t and left[:NAME_COLS].strip() and left[NAME_COLS:].strip():
            mapno = re.sub(r"\s+", " ", left[NAME_COLS:]).strip()
            cur = out.setdefault(mapno.replace(" ", ""), {"name": left[:NAME_COLS].strip(), "map": mapno, "tickets": [], "status": "", "lines": []})
        elif cur is None:
            continue
        elif left.strip() and len(left.rstrip()) <= NAME_COLS + 4:
            cur["lines"].append(re.sub(r"\s+", " ", left).strip())
        if t:
            cur["tickets"].append({"year": int(t.group("year")), "ticket": t.group("ticket"), "tax": _n(t.group("tax")), "total": _n(t.group("total"))})
            if t.group("status").strip():
                cur["status"] = t.group("status").strip()
    for r in out.values():
        lines, r["mail"] = r.pop("lines"), None
        if lines and _CSZ.match(lines[-1]):
            c = _CSZ.match(lines[-1])
            street = lines[-2] if len(lines) >= 2 else ""
            r["mail"] = {"addr": street, "city": c.group(1).strip(), "state": c.group(2), "zip": c.group(3)}
            extra = lines[:-2]
            if extra:
                r["name"] += " " + " ".join(extra)
    return listed, out


def pdf_text(path):
    return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, check=True).stdout


def add_pdf(path, source):
    listed, rows = parse(pdf_text(path))
    if not listed or len(rows) < 50:
        raise RuntimeError(f"{path}: not read as an Open Tax List ({len(rows)} parcels, date '{listed}')")
    os.makedirs(LISTS, exist_ok=True)
    json.dump({"listed": listed, "source": source, "parcels": len(rows), "total_due": round(sum(t["total"] for r in rows.values() for t in r["tickets"]), 2),
               "rows": rows}, open(os.path.join(LISTS, listed + ".json"), "w"), separators=(",", ":"))
    log.info("list of %s: %s parcels with a balance", listed, len(rows))
    return listed


def fetch_current():
    """Find the list on the Treasurer's page (the document number changes when a new one is posted) and download it."""
    url = KNOWN_LIST
    try:
        html = requests.get(TREASURER_PAGE, headers=UA, timeout=60).text
        # the page links a personal-property list too; the real estate one has "RE" in its name
        m = (re.search(r'href="(/DocumentCenter/View/\d+/[^"]*(?:RE|Real)[^"]*Del(?:in)?q[^"]*)"', html, re.I)
             or re.search(r'href="(/DocumentCenter/View/\d+/[^"]*Del(?:in)?q[^"]*(?:RE|Real)[^"]*)"', html, re.I))
        if m:
            url = "https://www.westmoreland-county.org" + m.group(1)
    except requests.RequestException as e:
        log.warning("Treasurer's page not read (%s); trying the last known link", e)
    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    os.makedirs(os.path.join(config.ROOT, ".cache"), exist_ok=True)
    tmp = os.path.join(config.ROOT, ".cache", "wm-open-tax-list.pdf")
    open(tmp, "wb").write(r.content)
    return add_pdf(tmp, url)


def name_blank_parcels(con, lists):
    """The layer leaves the owner blank for the Town of Colonial Beach. Where the Treasurer
    bills such a parcel, take the name (and the mailing address, when the list prints one)
    from the tax list, and say where it came from."""
    from engine import owner_parse
    named = {}
    for l in lists:                                     # oldest first, so the newest name wins and any address survives
        for key, row in l["rows"].items():
            e = named.setdefault(key.upper(), {})
            e["name"] = row["name"]
            if row.get("mail"):
                e["mail"] = row["mail"]
    n = 0
    for pid, join in con.execute("SELECT pid, pin_nospace FROM parcels WHERE owner = ''").fetchall():
        e = named.get(join.upper())
        if not e:
            continue
        lnam = config._wm_owner(e["name"])
        otype, sub = owner_parse.classify(lnam, "")
        mail = e.get("mail") or {}
        con.execute("UPDATE parcels SET lnam=?, owner=?, owner_type=?, owner_subtype=?, mail_addr=?, mail_city=?, mail_state=?, mail_zip=?, remark2=? WHERE pid=?",
                    (lnam, owner_parse.owner_text(lnam, ""), otype, sub, mail.get("addr", ""), mail.get("city", ""), mail.get("state", ""),
                     int(mail["zip"]) if mail.get("zip", "").isdigit() else 0, "owner and mailing address from the Treasurer's tax list", pid))
        n += 1
    con.commit()
    return n


def build(today=None):
    """Lists on file -> balances.json / state.json in the shape the delinquency join already reads.

    The county posts two kinds of list: the full one (every unpaid year) and a single-year
    one. So each tax year is taken from the newest list that covers that year, and a parcel
    is only carried if it is on the newest list at all: a parcel that has since dropped off
    has paid."""
    today = today or dt.date.today()
    files = sorted(f for f in os.listdir(LISTS) if f.endswith(".json")) if os.path.isdir(LISTS) else []
    if not files:
        log.warning("no tax list on file")
        return
    lists = [json.load(open(os.path.join(LISTS, f))) for f in files]
    newest = lists[-1]
    for l in lists:
        l["years"] = {t["year"] for r in l["rows"].values() for t in r["tickets"]}
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    filled = name_blank_parcels(con, lists)
    named_total = con.execute("SELECT COUNT(*) FROM parcels WHERE remark2 LIKE 'owner and mailing address from the Treasurer%'").fetchone()[0]
    by_map = {r["pin_nospace"].upper(): dict(r) for r in con.execute("SELECT pid, pin, pin_nospace FROM parcels")}
    con.close()
    balances, unmatched = {}, 0
    for key, row in newest["rows"].items():
        p = by_map.get(key.upper())
        if not p:
            unmatched += 1
            continue
        tickets = [dict(t, as_of=newest["listed"]) for t in row["tickets"]]
        older_as_of = ""
        for l in reversed(lists[:-1]):                  # years the newest list does not cover, from the newest list that does
            for t in l["rows"].get(key, {}).get("tickets", []):
                if t["year"] not in newest["years"] and t["year"] not in {x["year"] for x in tickets if x["as_of"] != l["listed"]}:
                    tickets.append(dict(t, as_of=l["listed"]))
                    older_as_of = l["listed"]
        years = sorted({t["year"] for t in tickets})
        oldest_due = f"{years[0]}-12-05"                 # the sale-eligible date depends only on the year the bill fell due
        eligible_on = delinquency.sale_eligible_on(oldest_due)
        balances[str(p["pid"])] = {
            "tickets": len(tickets), "name": row["name"], "not_yet_due": 0,
            "past_due": round(sum(t["total"] for t in tickets), 2), "oldest_due": oldest_due, "years": years,
            "installments": len(tickets), "sale_eligible": eligible_on < today, "sale_eligible_on": eligible_on.isoformat(),
            "pid": p["pid"], "pin": p["pin"], "checked": newest["listed"], "status": row.get("status", ""),
            "older_years_as_of": older_as_of, "also_listed": [l["listed"] for l in lists[:-1] if key in l["rows"]],
            "source": f"Treasurer's Open Tax List of {newest['listed']}"}
    state = {str(p["pid"]): newest["listed"] for p in by_map.values()}
    delinquency.save(balances, state)
    json.dump({"newest": newest["listed"], "newest_covers_years": sorted(newest["years"]), "source": newest["source"],
               "lists_on_file": [{"listed": l["listed"], "parcels": l["parcels"], "years": [min(l["years"]), max(l["years"])], "total_due": l["total_due"]} for l in lists],
               "parcels_on_newest": newest["parcels"], "matched_to_a_parcel": len(balances), "not_matched": unmatched,
               "blank_owners_named_from_the_list": named_total},
              open(os.path.join(delinquency.OUT, "list-meta.json"), "w"), indent=1)
    log.info("balances as of %s: %s parcels matched, %s not matched; %s blank owners named from the lists", newest["listed"], len(balances), unmatched, filled)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--add", help="a TR501S Open Tax List PDF to add to the lists on file")
    a = ap.parse_args()
    if a.add:
        add_pdf(a.add, "supplied by the Treasurer's office")
    elif not a.no_fetch:
        try:
            fetch_current()
        except Exception as e:  # noqa: BLE001
            log.warning("current list not fetched: %s", e)
    build()
