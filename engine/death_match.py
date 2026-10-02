"""
Match obituaries against EVERY current owner name in the parcel index.

  python -m engine.death_match              # match, fetch exact dates for new matches
  python -m engine.death_match --no-fetch   # match only (no network)

Each person on a title is matched separately: "A OR B", "A & B" and ";" parties
are split first (engine.owner_parse.split_people). A decedent who is still the
owner of record today is the lead: nobody has moved title since the death.

Two confidences are kept apart, as in the Maryland tool:
  the death is certain (a published obituary);
  the IDENTITY (is this decedent the person on title?) is scored here.

Outputs
  data/obits/matches.json   HIGH and MEDIUM identity matches (the Death Leads tab)
  data/obits/low.json       name-only matches, never shown
  data/title/leads.json     matched Title Leads get an OBITUARY_MATCH flag and points
"""
import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import sqlite3

from engine import config, obits, owner_parse, title_scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("death_match")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "obits")
TITLE_LEADS = os.path.join(ROOT, "data", "title", "leads.json")

HIGH, MEDIUM = 75, 55
CLASS_LABEL = {
    "D1": "Sole owner on title has died",
    "D5": "Every owner on title has died",
    "D4": "One co-owner on title has died",
}
NEXT_STEP = {
    "D1": "An obituary matches the only owner on title, and the county still shows that person as owner. Read the obituary "
          "for the survivors. Check the Clerk's will book index under the decedent's name for a will, a qualification or "
          "a List of Heirs (Va. Code 64.2-509). If nothing was filed, the heirs own it by law and all of them must sign.",
    "D5": "Obituaries match every owner named on title. Nobody living is on the deed. The heirs of the last to die usually "
          "control the property; start from the later obituary's survivors.",
    "D4": "An obituary matches one of the owners. If the deed gave survivorship (the county's 'A OR B' usually means it "
          "did), the survivor owns it outright and only needs to record the death. If it did not, the decedent's share "
          "passed to heirs. Pull the deed to see which. The survivor is the person to talk to either way.",
}
REGION = {  # places an obituary may give for someone living in or next to the county
    "KING GEORGE", "KING GEORGE COUNTY", "DAHLGREN", "DOGUE", "JERSEY", "NINDE", "SEALSTON", "SHILOH", "OWENS",
    "FAIRVIEW BEACH", "EDGEHILL", "ROLLINS FORK", "PASSAPATANZY", "WEEDONVILLE", "IGO", "COMORN", "INDEX", "PORT CONWAY"}


def norm_place(p):
    return (p or "").upper().replace(" COUNTY", "").replace(".", "").strip()


def score(o, person, r, name_count, death_year):
    """Identity points and reasons for obituary o vs person on parcel r, or None if ruled out."""
    pts, why = 40, ["first and last name match"]
    om, pm = (o.get("middle") or ""), (person.get("middle") or "")
    om1, pm1 = om[:1], pm[:1]
    if om and pm:
        if om == pm and len(om) > 1:
            pts += 25
            why.append("full middle name matches")
        elif om1 == pm1 and (len(om) == 1 or len(pm) == 1 or om == pm):
            pts += 20
            why.append("middle initial matches")
        else:
            return None                              # different middle names: a different person
    os_, ps = o.get("suffix") or "", person.get("suffix") or ""
    if os_ and ps:
        if os_ == ps:
            pts += 10
            why.append(f"suffix {os_} matches")
        else:
            return None
    elif os_ or ps:
        pts -= 25
        why.append("one record has a Jr/Sr suffix and the other does not: this may be a parent or child of the same name")

    place, mail_city = norm_place(o.get("place")), norm_place(r["mail_city"])
    if place:
        if place == mail_city:
            pts += 25
            why.append(f"obituary says of {o['place']}; tax bill goes to {r['mail_city'].title()}")
        elif place in REGION and (mail_city in config.KG_CITIES or r["mail_zip"] in config.KG_ZIPS):
            pts += 20
            why.append(f"obituary says of {o['place']}; owner's mail is in the county")
        elif place in REGION:
            pts += 8
            why.append(f"obituary says of {o['place']}")
        elif mail_city in config.KG_CITIES:
            pts -= 10
            why.append(f"obituary says of {o['place']}, but the tax bill goes to a King George address")
    else:
        why.append("obituary gives no place of residence")

    if name_count == 1:
        pts += 10
        why.append("only owner in the county with this name")
    elif name_count > 2:
        pts -= 10
        why.append(f"{name_count} owners in the county share this name")

    sy, known = r["sale_year"], title_scan.sale_year_known(r)
    if known and death_year:
        if sy > death_year:
            return None                              # put on title after the death: not this person
        if r.get("owner_type") == "ESTATE" and r.get("owner_subtype") in ("ESTATE", "HEIRS") and sy < death_year - 1:
            return None                              # title already read "estate of" before this death: an earlier namesake
        if sy == death_year:
            pts -= 10
            why.append("title last changed in the year of death; it may already reflect the death")
        if o.get("age"):
            age_at_title = o["age"] - (death_year - sy)
            if age_at_title < 16:
                return None                          # too young to have taken title
            if age_at_title >= 25:
                pts += 5
                why.append(f"would have been about {age_at_title} when title was taken")
    return pts, why


def run(fetch=True, today=None):
    today = today or dt.date.today()
    con = sqlite3.connect(title_scan.DB_PATH)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM parcels ORDER BY pid")]
    con.close()
    owner_parse.learn_names(r["owner"] for r in rows)
    title_scan.learn_book_years(rows)

    # every person on every title
    by_name, group_people, name_owners = {}, {}, {}
    for r in rows:
        people = owner_parse.split_people(r["lnam"], r["fnam"])
        key = (r["owner"], r["mail_addr"].upper(), str(r["mail_zip"]))
        group_people.setdefault(key, people)
        for p in people:
            by_name.setdefault((p["last"], p["first"]), []).append((p, r, key))
            name_owners.setdefault((p["last"], p["first"]), set()).add((key[0], p["middle"][:1]))
    log.info("%s parcels, %s distinct owner names to match", len(rows), len(by_name))

    recs = obits.load()
    extra = obits.load_extra()
    recs.update(extra)
    for o in recs.values():                              # a typo'd year on the source page is not a death date
        d = o.get("death_date") or ""
        if d and not ("1990-01-01" <= d <= today.isoformat()):
            o["death_date"] = ""
    log.info("%s obituaries on file (%s from other files in data/obits/)", len(recs), len(extra))

    def candidates():
        hits = {}
        for o in recs.values():
            firsts = {o["first"]} | ({o["nickname"]} if o.get("nickname") else set())
            lasts = {o["last"]} | ({o["maiden"]} if o.get("maiden") and " " not in o["maiden"] else set())
            for last in lasts:
                for first in firsts:
                    if (last, first) in by_name:
                        hits.setdefault(o["id"], []).extend(by_name[(last, first)])
        return hits

    hits = candidates()
    if fetch:
        need = [i for i in sorted((i for i in hits if isinstance(i, int)), reverse=True) if not recs[i].get("detail")]
        if need:
            storke = {i: r for i, r in recs.items() if isinstance(i, int)}
            obits.details(storke, need)
            obits.save(storke)

    matches, low = {}, []
    for oid, cands in hits.items():
        o = recs[oid]
        dy = int(o["death_date"][:4]) if o.get("death_date") else None
        for person, r, key in cands:
            n = len({m for (_own, m) in name_owners[(person["last"], person["first"])]} | {""}) - 1
            n_owners = len({own for (own, _m) in name_owners[(person["last"], person["first"])]})
            res = score(o, person, r, n_owners, dy)
            if not res:
                continue
            pts, why = res
            if o["last"] != person["last"]:
                pts -= 15
                why.append("matched on the maiden name in the obituary")
            mk = (oid, key)
            m = matches.get(mk)
            if not m:
                m = matches[mk] = {"o": o, "key": key, "person": person, "pts": pts, "why": why, "rows": []}
            if pts > m["pts"]:
                m["pts"], m["why"], m["person"] = pts, why, person
            if r["pid"] not in {x["pid"] for x in m["rows"]}:
                m["rows"].append(r)

    # which owner groups have which people matched (for D1 / D4 / D5)
    dead_by_group = {}
    for (oid, key), m in matches.items():
        if m["pts"] >= MEDIUM:
            dead_by_group.setdefault(key, set()).add(m["person"]["name"])

    out = []
    for (oid, key), m in matches.items():
        o, pts = m["o"], m["pts"]
        conf = "HIGH" if pts >= HIGH else "MEDIUM" if pts >= MEDIUM else "LOW"
        people = group_people[key]
        r0 = m["rows"][0]
        n_people = max(1, len(people))
        dead = dead_by_group.get(key, set())
        etal = r0["owner_type"] == "ET_AL" or "ET_AL" in title_scan.scan_parcel(r0, today.year)[1]
        if n_people == 1 and not etal:
            cls = "D1"
        elif len(dead) >= n_people and not etal:
            cls = "D5"
        else:
            cls = "D4"
        parcels = []
        for r in sorted(m["rows"], key=lambda x: -x["total_value"]):
            c, flags, detail = title_scan.scan_parcel(r, today.year)
            parcels.append(dict(title_scan.parcel_view(r, flags, detail, today.year), title_class=c))
        death = o.get("death_date") or ""
        yrs = round((today - dt.date.fromisoformat(death)).days / 365.25, 1) if death else None
        row = {
            "id": hashlib.sha1(f"{oid}|{'|'.join(key)}".encode()).hexdigest()[:12],
            "identity_confidence": conf, "identity_points": min(100, pts), "identity_reasons": m["why"],
            "death_class": cls, "class_label": CLASS_LABEL[cls],
            "decedent": " ".join(x for x in (o["first"], o.get("middle"), o["last"], o.get("suffix")) if x),
            "death_date": death, "birth_date": o.get("birth_date") or "", "age": o.get("age"),
            "place": ", ".join(x for x in (o.get("place"), o.get("state")) if x),
            "years_since_death": yrs, "obituary_url": o.get("url", ""), "source": o["source"], "heirs": o.get("heirs", []),
            "matched_owner": m["person"]["name"],
            "owner": key[0], "owner_type": r0["owner_type"], "care_of": r0["care_of"],
            "people": [p["name"] for p in people],
            "other_owners": [p["name"] for p in people if p["name"] != m["person"]["name"]],
            "mail": {"addr": r0["mail_addr"], "city": r0["mail_city"], "state": r0["mail_state"], "zip": r0["mail_zip"] or None},
            "parcel_count": len(parcels), "total_value": sum(p["total_value"] for p in parcels),
            "title_class": next((p["title_class"] for p in parcels if p["title_class"]), ""),
            "parcels": parcels,
        }
        (low if conf == "LOW" else out).append(row)
    out.sort(key=lambda x: (x["death_date"] or "0"), reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    dates = sorted(o["death_date"] for o in recs.values() if o.get("death_date"))
    summary = {
        "generated_at": now, "obituaries": len(recs), "source": obits.SOURCE, "other_sources": len(extra),
        "coverage_from": dates[0] if dates else "", "coverage_to": dates[-1] if dates else "",
        "matches": len(out), "high": sum(1 for x in out if x["identity_confidence"] == "HIGH"),
        "medium": sum(1 for x in out if x["identity_confidence"] == "MEDIUM"), "low_hidden": len(low),
        "classes": {c: sum(1 for x in out if x["death_class"] == c) for c in CLASS_LABEL},
        "class_labels": CLASS_LABEL, "next_step": NEXT_STEP,
    }
    os.makedirs(OUT, exist_ok=True)
    json.dump({"summary": summary, "rows": out}, open(os.path.join(OUT, "matches.json"), "w"), separators=(",", ":"))
    json.dump({"generated_at": now, "note": "Name-only matches. Not shown.",
               "rows": [{k: x[k] for k in ("decedent", "death_date", "place", "owner", "identity_points", "obituary_url")} for x in low]},
              open(os.path.join(OUT, "low.json"), "w"), separators=(",", ":"))

    # annotate the Title Leads board
    if os.path.exists(TITLE_LEADS):
        tl = json.load(open(TITLE_LEADS))
        best = {}
        for x in out:
            k = (x["owner"], x["mail"]["addr"].upper())
            if k not in best or x["identity_points"] > best[k]["identity_points"]:
                best[k] = x
        n = 0
        for lead in tl["rows"]:
            x = best.get((lead["owner"], lead["mail"]["addr"].upper()))
            lead["flags"] = [f for f in lead["flags"] if f != "OBITUARY_MATCH"]
            lead["reasons"] = [s for s in lead["reasons"] if "obituary" not in s]
            lead.pop("obituary", None)
            if x:
                add = 15 if x["identity_confidence"] == "HIGH" else 8
                lead["flags"].append("OBITUARY_MATCH")
                lead["priority"] = min(100, title_scan.score(lead["title_class"], lead["flags"], lead["parcel_count"])[0] + add)
                lead["reasons"].append(f"+{add} obituary matches {x['matched_owner'].title()} ({x['identity_confidence'].lower()} identity confidence)")
                lead["obituary"] = {k: x[k] for k in ("decedent", "death_date", "age", "place", "obituary_url", "identity_confidence", "matched_owner")}
                n += 1
        tl["rows"].sort(key=lambda l: (-l["priority"], -l["total_value"], l["owner"]))
        json.dump(tl, open(TITLE_LEADS, "w"), separators=(",", ":"))
        log.info("%s Title Leads carry an obituary match", n)
    log.info("matches: %s", {k: summary[k] for k in ("matches", "high", "medium", "low_hidden", "classes")})
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    run(fetch=not ap.parse_args().no_fetch)
