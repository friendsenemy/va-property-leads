"""
Stacked distress: one row per owner, every independent signal side by side.

  python -m engine.combined        (run by engine.build_board, after the other boards)

Signals, each from a different public record:
  TITLE      how the county's title reads (estate, heirs, life estate, et al, will)
  DEATH      an obituary or clerk filing matched to an owner still on title
  TAX        prior-year taxes unpaid (Treasurer's inquiry)
  CONDITION  the assessor's field notes: unsafe structure, abandoned, boarded up,
             burned, unlivable, vacant house, poor condition, overgrown

King George County publishes no code-violation or fines list. The assessor's notes
are the nearest free public record; "unsafe structure per county" or "abandoned,
windows boarded up" is written there when the assessor sees it.

An owner is shown when two or more signals stack, or when a single strong
condition note stands alone. data/combined/leads.json feeds the Stacked tab.
"""
import datetime as dt
import json
import logging
import os
import sqlite3

from engine import config, title_scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("combined")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(config.DATA_DIR, "combined")

NEXT_STEP = ("More than one public record points at this owner. Work the strongest fact first: a death tells you who to "
             "find (survivors in the obituary, heirs by law); unpaid taxes tell you how much time there is (the county may "
             "sue once a bill is two years old, and there is no redemption after the sale date); a condition note tells you "
             "what the house is. Confirm the tax balance on the Treasurer's site and the title in the Clerk's records "
             "before you contact anyone.")


def _load(path, key="rows"):
    p = os.path.join(config.DATA_DIR, path[5:])          # paths are written "data/..."; the county decides where data is
    return json.load(open(p))[key] if os.path.exists(p) else []


def run(today=None):
    today = today or dt.date.today()
    con = sqlite3.connect(title_scan.DB_PATH)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM parcels")]
    con.close()
    title_scan.learn_book_years(rows)

    owners = {}

    def slot(owner, mail_addr):
        return owners.setdefault((owner, (mail_addr or "").upper()), {"signals": {}, "parcels": {}})

    for l in _load("data/title/leads.json"):
        o = slot(l["owner"], l["mail"]["addr"])
        o["signals"]["TITLE"] = {"label": f'{l["title_class"]} {l["class_label"]}', "points": {"E1": 40, "E2": 40, "X1": 35}.get(l["title_class"], 28)}
        o["meta"] = {"owner_type": l["owner_type"], "care_of": l["care_of"], "mail": l["mail"]}
        for p in l["parcels"]:
            o["parcels"][p["pid"]] = p
    for m in _load("data/obits/matches.json"):
        o = slot(m["owner"], m["mail"]["addr"])
        cur = o["signals"].get("DEATH")
        pts = 40 if m["identity_confidence"] == "HIGH" else 25
        if not cur or pts > cur["points"]:
            o["signals"]["DEATH"] = {"label": f'{m["decedent"].title()} died {m["death_date"] or "(date not parsed)"}', "points": pts,
                                     "decedent": m["decedent"], "death_date": m["death_date"], "age": m["age"], "place": m["place"],
                                     "identity_confidence": m["identity_confidence"], "death_class": m["death_class"],
                                     "obituary_url": m["obituary_url"], "other_owners": m["other_owners"], "heirs": m.get("heirs", [])}
        o.setdefault("meta", {"owner_type": m["owner_type"], "care_of": m["care_of"], "mail": m["mail"]})
        for p in m["parcels"]:
            o["parcels"].setdefault(p["pid"], p)
    for d in _load("data/delinquency/leads.json"):
        o = slot(d["owner"], d["mail"]["addr"])
        o["signals"]["TAX"] = {"label": f'${d["past_due"]:,.2f} past due, {d["payments_behind"]} payments behind, since {d["oldest_due"]}',
                               "points": 40 if d["sale_eligible"] or d["delinquency_class"] == "P1" else 25,
                               "past_due": d["past_due"], "payments_behind": d["payments_behind"], "years": d["years"],
                               "oldest_due": d["oldest_due"], "sale_eligible": d["sale_eligible"], "delinquency_class": d["delinquency_class"],
                               "checked": d["parcels"][0]["checked"]}
        o.setdefault("meta", {"owner_type": d["owner_type"], "care_of": d["care_of"], "mail": d["mail"]})
        for p in d["parcels"]:
            o["parcels"].setdefault(p["pid"], p)
    # condition notes: every parcel in the county, not only those already on a board
    for r in rows:
        notes = title_scan.condition_notes(r)
        if not notes or r["owner_type"] in ("GOVERNMENT", "CEMETERY"):
            continue
        strong = any(st for _l, st in notes)
        key = (r["owner"], r["mail_addr"].upper())
        if key not in owners and not strong:
            continue                                   # a soft note alone is not a lead
        o = slot(r["owner"], r["mail_addr"])
        labels = sorted({l for l, _st in notes})
        cur = o["signals"].get("CONDITION")
        pts = 30 if strong else 15
        if not cur or pts > cur["points"]:
            o["signals"]["CONDITION"] = {"label": ", ".join(labels), "points": pts, "strong": strong,
                                         "remarks": " | ".join(x for x in (r["remark1"], r["remark2"]) if x)}
        elif cur:
            cur["label"] = ", ".join(sorted(set(cur["label"].split(", ")) | set(labels)))
        o.setdefault("meta", {"owner_type": r["owner_type"], "care_of": r["care_of"],
                              "mail": {"addr": r["mail_addr"], "city": r["mail_city"], "state": r["mail_state"], "zip": r["mail_zip"] or None}})
        if r["pid"] not in o["parcels"]:
            c, flags, detail = title_scan.scan_parcel(r, today.year)
            o["parcels"][r["pid"]] = title_scan.parcel_view(r, flags, detail, today.year)

    leads = []
    for (owner, _mail), o in owners.items():
        sig = o["signals"]
        if len(sig) < 2 and not (sig.get("CONDITION", {}).get("strong")):
            continue
        parcels = sorted(o["parcels"].values(), key=lambda p: -p["total_value"])
        pts = min(100, sum(s["points"] for s in sig.values()) + (10 if len(sig) >= 3 else 0))
        leads.append({
            "id": "c" + str(parcels[0]["pid"]), "priority": pts, "signal_count": len(sig),
            "kinds": [k for k in ("DEATH", "TAX", "TITLE", "CONDITION") if k in sig], "signals": sig,
            "owner": owner, "owner_type": o["meta"]["owner_type"], "care_of": o["meta"]["care_of"], "mail": o["meta"]["mail"],
            "parcel_count": len(parcels), "total_value": sum(p["total_value"] for p in parcels), "parcels": parcels,
        })
    leads.sort(key=lambda l: (-l["signal_count"], -l["priority"], -l["total_value"]))
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    summary = {"generated_at": now, "leads": len(leads),
               "three_plus": sum(1 for l in leads if l["signal_count"] >= 3),
               "death_and_tax": sum(1 for l in leads if "DEATH" in l["signals"] and "TAX" in l["signals"]),
               "condition": sum(1 for l in leads if "CONDITION" in l["signals"]),
               "condition_strong_alone": sum(1 for l in leads if l["signal_count"] == 1),
               "next_step": NEXT_STEP}
    os.makedirs(OUT, exist_ok=True)
    json.dump({"summary": summary, "rows": leads}, open(os.path.join(OUT, "leads.json"), "w"), separators=(",", ":"))
    log.info("stacked: %s", {k: v for k, v in summary.items() if k not in ("next_step", "generated_at")})
    return summary


if __name__ == "__main__":
    run()
