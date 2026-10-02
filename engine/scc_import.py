"""
SCC entity status: looked up by hand, joined by the tool.

  python -m engine.scc_import

The Virginia SCC Clerk's Information System forbids crawling (robots.txt is
"Disallow: /" for everything but named search engines) and sells bulk data by
subscription, so nothing here touches it. Instead:

  data/scc/worklist.csv   written by this script: the entity owners most worth
                          looking up, best first (delinquent taxes, old title,
                          bill mailed out of state)
  data/scc/status.csv     you fill in: one line per entity you looked up at
                          https://cis.scc.virginia.gov/EntitySearch/Index
      entity,status,registered_agent,officers,checked
      status is what the SCC shows: ACTIVE, INACTIVE, CANCELLED, TERMINATED,
      REVOKED, DISSOLVED, PURGED, WITHDRAWN ...

An entity that is no longer active but still holds title is a stuck asset; its
officers and registered agent are the people to find. Those go on the Title
Leads board as class X1.
"""
import csv
import datetime as dt
import json
import logging
import os
import re
import sqlite3

from engine import title_scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scc_import")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "scc")
DEAD = {"CANCELLED", "CANCELED", "TERMINATED", "REVOKED", "DISSOLVED", "PURGED", "INACTIVE", "WITHDRAWN", "EXPIRED", "MERGED"}
ENTITY_TYPES = ("BUSINESS", "ASSOCIATION", "CHURCH")


def norm(name):
    n = re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper())
    n = re.sub(r"\b(THE|L L C|LLC|L C|LC|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def run(today=None):
    today = today or dt.date.today()
    os.makedirs(OUT, exist_ok=True)
    con = sqlite3.connect(title_scan.DB_PATH)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM parcels WHERE owner_type IN ('BUSINESS','ASSOCIATION','CHURCH')")]
    con.close()
    title_scan.learn_book_years(rows)
    bal_path = os.path.join(ROOT, "data", "delinquency", "balances.json")
    balances = json.load(open(bal_path))["rows"] if os.path.exists(bal_path) else {}

    status = {}
    spath = os.path.join(OUT, "status.csv")
    if os.path.exists(spath):
        with open(spath, newline="") as f:
            for row in csv.DictReader(l for l in f if l.strip() and not l.startswith("#")):
                if row.get("entity"):
                    status[norm(row["entity"])] = {k: (v or "").strip() for k, v in row.items()}
    else:
        open(spath, "w").write("# Fill in after looking an entity up at https://cis.scc.virginia.gov/EntitySearch/Index\n"
                               "entity,status,registered_agent,officers,checked\n")

    groups = {}
    for r in rows:
        g = groups.setdefault(norm(r["owner"]), {"owner": r["owner"], "type": r["owner_type"], "rows": []})
        g["rows"].append(r)

    work, leads = [], []
    for key, g in groups.items():
        rs = g["rows"]
        ys = [y for y in (title_scan.years_since(r, today.year) for r in rs) if y is not None]
        past = sum(balances.get(str(r["pid"]), {}).get("past_due", 0) for r in rs
                   if min(balances.get(str(r["pid"]), {}).get("years", [today.year])) < today.year)
        r0 = rs[0]
        ab = title_scan.absentee(r0)
        pts = (40 if past else 0) + (20 if ys and max(ys) >= 25 else 10 if ys and max(ys) >= 12 else 0) \
            + (15 if ab == "OUT_OF_STATE" else 8 if ab else 0) + (5 if all(not r["impr_value"] for r in rs) else 0)
        st = status.get(key)
        if st and st.get("status", "").upper() in DEAD:
            parcels = []
            for r in sorted(rs, key=lambda x: -x["total_value"]):
                _c, flags, detail = title_scan.scan_parcel(r, today.year)
                parcels.append(title_scan.parcel_view(r, flags, detail, today.year))
            leads.append({"owner": g["owner"], "status": st["status"].upper(), "registered_agent": st.get("registered_agent", ""),
                          "officers": st.get("officers", ""), "checked": st.get("checked", ""), "past_due": round(past, 2),
                          "parcels": parcels, "r0": {k: r0[k] for k in ("lnam", "fnam", "owner_type", "owner_subtype", "care_of", "mail_addr", "mail_addr2", "mail_city", "mail_state", "mail_zip")}})
        elif not st and pts >= 20:
            work.append((pts, g["owner"], g["type"], len(rs), sum(r["total_value"] for r in rs), round(past, 2),
                         max(ys) if ys else "", f'{r0["mail_city"]} {r0["mail_state"]}'))
    work.sort(key=lambda w: (-w[0], -w[4]))
    with open(os.path.join(OUT, "worklist.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["priority", "entity", "type", "parcels", "assessed", "taxes_past_due", "years_since_transfer", "bill_mailed_to"])
        w.writerows(work[:300])
    json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "rows": leads},
              open(os.path.join(OUT, "leads.json"), "w"), separators=(",", ":"))
    log.info("%s entity owners; %s looked up; %s no longer active and still on title; %s on the worklist",
             len(groups), len(status), len(leads), min(300, len(work)))
    return leads


if __name__ == "__main__":
    run()
