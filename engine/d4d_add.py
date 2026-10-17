"""
Driving for Dollars (Virginia): add or update a property Ray spotted on the road.

  python -m engine.d4d_add king-george "26 4 B" research.json
  python -m engine.d4d_add fauquier 6969-33-1234-000 research.json

Arguments: the county key (king-george | westmoreland | fauquier), the tax map / PIN as
the county prints it (or the parcel's internal id), and a research JSON:
  {"spotted": "2026-10-17", "verdict": "warm", "headline": "...", "owners": ["..."],
   "vesting": "...", "deed": "DB 123 PG 45 ...", "findings": ["..."], "next_steps": ["..."],
   "sources": ["..."]}
Parcel facts (address, owner, mailing address, values, acres, deed reference) come from the
county parcel index the tool already builds (data/<county>/parcels.json), so the card
matches the county record. Writes data/d4d/leads.json, one row per county + parcel.
"""
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "d4d", "leads.json")
COUNTIES = {"king-george": ("King George", "data"), "westmoreland": ("Westmoreland", "data/westmoreland"),
            "fauquier": ("Fauquier", "data/fauquier")}


def norm(s):
    return re.sub(r"\s+", "", str(s or "")).upper()


def parcel(county_key, ref):
    name, d = COUNTIES[county_key]
    j = json.load(open(os.path.join(ROOT, d, "parcels.json")))
    c = {k: i for i, k in enumerate(j["columns"])}
    want = norm(ref)
    hit = next((r for r in j["rows"] if norm(r[c["pin"]]) == want), None) \
        or next((r for r in j["rows"] if str(r[c["pid"]]) == str(ref).strip()), None)
    if not hit:
        raise SystemExit(f"{county_key}: no parcel {ref!r} in {d}/parcels.json")
    g = lambda k: hit[c[k]] if k in c else None
    deed = f"DB {g('deed_book')} PG {g('deed_page')}" if g("deed_book") else ""
    mailing = ", ".join(x for x in (g("care_of") and f"c/o {g('care_of')}", g("mail_addr"),
                                     f"{g('mail_city') or ''} {g('mail_state') or ''} {g('mail_zip') or ''}".strip()) if x)
    return {
        "id": f"{county_key}-{g('pid')}", "county_key": county_key, "county": name,
        "pid": g("pid"), "pin": g("pin"), "parcel": g("pin"),
        "address": g("site_addr") or "", "owner": g("owner"), "owner_type": g("owner_type"), "mailing": mailing,
        "acres": g("acres"), "land_value": g("land_value"), "impr_value": g("impr_value"), "total_value": g("total_value"),
        "year_built": g("year_built"), "cond": g("cond"), "deed_ref": deed,
        "will_ref": f"WB {g('will_book')} PG {g('will_page')}" if g("will_book") else "",
        "sale_year": g("sale_year"), "sale_price": g("sale_price"), "note": g("note"), "water": g("water"),
    }


def run(county_key, ref, research_path):
    if county_key not in COUNTIES:
        raise SystemExit(f"county must be one of {', '.join(COUNTIES)}")
    row = parcel(county_key, ref)
    row.update(json.load(open(research_path)))
    row["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    data = json.load(open(OUT)) if os.path.exists(OUT) else {"rows": []}
    data["rows"] = [r for r in data["rows"] if r.get("id") != row["id"]] + [row]
    data["rows"].sort(key=lambda r: (r.get("spotted") or "", r.get("id")), reverse=True)
    data["generated_at"] = row["updated"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w"), indent=1)
    print(f"{row['id']} {row['address'] or row['pin']}, {row['county']} -> {OUT} ({len(data['rows'])} rows)")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3])
