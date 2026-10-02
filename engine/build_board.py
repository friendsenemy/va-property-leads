"""
Build everything the dashboard reads, in order, from what is on disk.

  python -m engine.build_board                 # no network except new obituary details
  python -m engine.build_board --no-fetch      # no network at all

  1. title scan            data/title/        (owner text, will refs, assessor notes)
  2. clerk filings         data/heirs/import.csv -> data/obits/clerk-filings.json
  3. SCC entity status     data/scc/status.csv -> X1 leads on the title board
  4. death match           obituaries + clerk filings vs every owner name
  5. delinquency join      Treasurer balances on file -> flags, P1 profile, Delinquent tab
  6. stacked signals       every owner with two or more of title / death / tax / condition

Needs .cache/kg.sqlite, so run engine.parcels first.
"""
import argparse
import hashlib
import json
import os

from engine import combined, death_match, delinquency, heirs_import, scc_import, title_scan

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
X1_LABEL = "Entity no longer active (SCC)"
X1_NEXT = ("The State Corporation Commission shows this company or association as no longer active, and it still holds "
           "title. Nobody can sign for a dead entity without reinstating it or winding it up. The registered agent and "
           "officers you recorded are the people to find; they, or their heirs, are who you deal with.")
X1_WEIGHT = 55


def add_entity_leads(entity_leads):
    lpath, spath = (os.path.join(title_scan.OUT, n) for n in ("leads.json", "summary.json"))
    tl, summary = json.load(open(lpath)), json.load(open(spath))
    for e in entity_leads:
        r0, parcels = e["r0"], e["parcels"]
        flags = sorted({f for p in parcels for f in p["flags"]} | {"ENTITY_INACTIVE"})
        pts = min(100, X1_WEIGHT + (15 if e["past_due"] else 0) + (10 if "OUT_OF_STATE" in flags else 0) + (10 if "OLD_TITLE_25" in flags or "OLD_TITLE_40" in flags else 0))
        ys = [p["years_since_transfer"] for p in parcels if p["years_since_transfer"] is not None]
        tl["rows"].append({
            "id": hashlib.sha1(("x1|" + e["owner"]).encode()).hexdigest()[:12], "priority": pts,
            "reasons": [f"+{X1_WEIGHT} SCC status {e['status']} (looked up by hand {e['checked'] or 'date not recorded'})"],
            "title_class": "X1", "class_label": X1_LABEL, "owner": e["owner"], "owner_raw": [r0["lnam"], r0["fnam"]],
            "owner_type": r0["owner_type"], "owner_subtype": r0["owner_subtype"], "care_of": r0["care_of"],
            "people": [x.strip() for x in (e["registered_agent"] + ";" + e["officers"]).split(";") if x.strip()],
            "mail": {"addr": r0["mail_addr"], "addr2": r0["mail_addr2"], "city": r0["mail_city"], "state": r0["mail_state"], "zip": r0["mail_zip"] or None},
            "flags": flags, "parcel_count": len(parcels), "total_value": sum(p["total_value"] for p in parcels),
            "acres": round(sum(p["acres"] for p in parcels), 2), "oldest_transfer_years": max(ys) if ys else None,
            "note_dod": "", "parcels": parcels,
        })
    tl["rows"].sort(key=lambda l: (-l["priority"], -l["total_value"], l["owner"]))
    summary["class_labels"]["X1"] = X1_LABEL
    summary["next_step"]["X1"] = X1_NEXT
    if "X1" not in summary["class_order"]:
        summary["class_order"].append("X1")
    if entity_leads:
        summary["classes"]["X1"] = len(entity_leads)
        summary["presets"].append({"id": "entity", "label": "Inactive company on title", "classes": ["X1"]})
    summary["leads"] = len(tl["rows"])
    summary["lead_parcels"] = sum(l["parcel_count"] for l in tl["rows"])
    json.dump(tl, open(lpath, "w"), separators=(",", ":"))
    json.dump(summary, open(spath, "w"), indent=1)


def run(fetch=True):
    title_scan.run()
    heirs_import.run()
    add_entity_leads(scc_import.run())
    death_match.run(fetch=fetch)
    delinquency.join()
    combined.run()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    run(fetch=not ap.parse_args().no_fetch)
