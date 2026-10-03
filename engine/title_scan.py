"""
Title scan: every parcel in the index -> the Title Leads board.

  python -m engine.title_scan

Reads .cache/kg.sqlite (built by engine.parcels) and writes

  data/title/leads.json     the board: one row per owner group, opportunities only
  data/title/watch.json     held back: old title + absentee individuals / trusts with
                            no death or delinquency record yet (never shown)
  data/title/summary.json   counts, class legend, run info

A lead is an owner, not a parcel: parcels with the same owner text and mailing
address are one row with the parcels listed under it.

Classes (title is the county's own record; nothing here is inferred from a
death file):
  E1 estate / deceased / executor named on title
  E2 "heirs of" on title
  E3 life estate on title
  C1 et al / et als co-owners
  W1 List of Heirs reference on the parcel (WBOOK "LH")
  W2 will-book reference on the parcel
  N1 assessor's note records a death (DOD) on this parcel in the last few years
  N2 assessor's note says title passed by will in the last few years
"""
import datetime as dt
import hashlib
import json
import logging
import os
import re
import sqlite3

from engine import config, owner_parse
from engine import waterfront

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("title_scan")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = config.DB_PATH
OUT = os.path.join(config.DATA_DIR, "title")

CLASS_LABEL = {
    "E1": "Estate on title",
    "E2": "Heirs on title",
    "E3": "Life estate on title",
    "C1": "Et al co-owners",
    "W1": "List of Heirs on file",
    "W2": "Title passed by will",
    "N1": "Death noted by assessor",
    "N2": "Will noted by assessor",
}
CLASS_ORDER = ["E1", "E2", "E3", "C1", "W1", "W2", "N1", "N2"]

NEXT_STEP = {
    "E1": "The county still shows a decedent's estate as owner. Look for a qualified executor or administrator in the "
          "King George Circuit Court Clerk's will books (probate can also be in the county where the person lived). "
          "A List of Heirs (Va. Code 64.2-509) is recorded in the will book only if someone qualified or probated a "
          "will; if nobody did, there is none and the heirs take by law. Confirm who can sign before you call anyone.",
    "E2": "Title reads 'heirs of'. Nobody has put the heirs' own names on record. Check the will book index under the "
          "decedent for a List of Heirs or a real-estate affidavit (64.2-510). Every heir has to sign a deed; one heir "
          "cannot sell alone.",
    "E3": "A life tenant holds the property for life and named remaindermen take after. The life tenant may be living. "
          "Do not treat this as a death lead until a death is confirmed; if the life tenant has died the remaindermen "
          "own it outright and usually have not updated the record.",
    "C1": "Several co-owners, usually family who inherited. The current deed lists all of them; pull it by the deed "
          "reference shown. Any one owner can be the way in, but all must sign to sell the whole.",
    "W1": "The parcel carries a List of Heirs reference. That document names the heirs and their addresses as of the "
          "date of death. Pull it from the will book and page shown.",
    "W2": "Title came by will (will book and page shown). Read the will for who took the property; the name on the "
          "tax record may be a devisee who has since died or moved.",
    "N1": "The assessor recorded a date of death on this parcel and moved title to the survivor or devisee. Title is "
          "likely clean. This is a recent-loss lead: be respectful, and verify the note against the deed or will first.",
    "N2": "The assessor notes this parcel passed by will recently. The devisee may not want the property. Verify the "
          "will reference before contacting.",
}

_DOD = re.compile(r"\bDOD\s*:?\s*(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})|\bDOD\s*:?\s*(\d{4})\b")
_NOTE_WILL = re.compile(r"\bWILL\b(?!IAM)", re.I)
_NOTE_DEATH = re.compile(r"\bDEATH\s+CERT|\bDECEASED\b|\bDIED\b|\bDOD\b", re.I)


def parse_will_ref(will_book, will_page, deed_book, deed_page):
    """Return (kind, book, page, raw). kind is 'LH', 'WB' or ''."""
    raw_b, raw_p = (will_book or "").strip().strip("/").strip(), (will_page or "").strip().strip("/").strip()
    if not raw_b:
        return "", "", "", ""
    raw = f"{raw_b}/{raw_p}"
    if "LH" in raw_b.upper():
        return "LH", "", raw_p, raw
    digits = re.sub(r"\D", "", raw_b)
    if not digits:
        return "", "", "", raw
    # The same numbers as the deed reference is a deed typed into the will field.
    try:
        if int(digits) == int(deed_book or 0) and int(raw_p or 0) == int(deed_page or 0) and int(deed_book or 0):
            return "", "", "", raw
    except ValueError:
        pass
    if len(digits) == 4 and (digits[2:] == "00" or digits[:2] == digits[2:]):
        book = str(int(digits[:2]))                     # "1800" and "1313" are will books 18 and 13
    elif len(digits) == 3 and digits[0] == digits[2] and " " in raw_b:
        book = digits[0]                                # "6 06"
    elif len(digits) <= 2:
        book = str(int(digits))
    else:
        return "", "", "", raw                          # 3+ digits: not a will book number
    return "WB", book, raw_p, raw


def deed_ref(deed_book, deed_page, sale_year):
    """Human reference for the land-records search."""
    if deed_page:
        return f"DB {deed_book} PG {deed_page}" if deed_book else f"PG {deed_page} (book not on record)"
    if not deed_book:
        return ""
    if deed_book >= 100000000:
        return f"Instr. {deed_book}"
    if sale_year:
        return f"Instr. {deed_book} of {sale_year}"
    return f"Instr. {deed_book}"


# The assessor's own field notes (REM1/REM2). King George publishes no code-violation
# list; these notes are where an unsafe-structure finding or an abandoned house shows
# up in free public data. "REDTAG" is NOT a violation here: it is the assessor's own
# reminder to revisit unfinished construction, so it is deliberately not a signal. (label, strong) per pattern; phrases are chosen
# so "FIREPLACE", "FIRE DEPT", "POOR TERRAIN", "VACANT LOT" and "UNFINISHED ATTIC" miss.
_CONDITION = [
    (re.compile(r"\bUNSAFE\s+STRUCT|\bCONDEMNED?\b(?<!FP'S CONDEMNED)"), "Unsafe / condemned", True),
    (re.compile(r"\bABANDON"), "Abandoned", True),
    (re.compile(r"\bBOARDED"), "Boarded up", True),
    (re.compile(r"\bUNLIV|\bNOT\s+LIVABLE|\bUNINHAB|\bIN\s+RUIN"), "Unlivable", True),
    (re.compile(r"(?:DWL|DWELLING|HOUSE|ROOF|MH|HOME)[^|]{0,25}\b(?:COLLA[PS]+ED|FALLING\s+DOWN)|\bFALLING\s+DOWN"), "Collapsed / falling down", True),
    (re.compile(r"\bGUTTED|(?:DWL|DWELLING|HOUSE|HOME|MH)\s+BURN(?:ED|DED)(?!.*REPLACED)|\bBURNED\s+DOWN|\bFIRE\s+DAMAGE"), "Burned / gutted", True),
    (re.compile(r"\bVACANT\s+(?:SINCE|\d+\s+YEARS?|MANY|UNLIV)|\bAPPEARS\s+VACANT|\bDWL\s+VAC\b|\bNOT\s+LIVED\s+IN|\bUNOCCUPIED"), "Vacant house", True),
    (re.compile(r"\bDISREPAIR|\bDETERIORAT|\bVERY\s+POOR|\bPOOR\s+COND|\bROUGH\s+SHAPE|\bNEEDS\s+(?:REPAIRS?|WORK|MAINT|NEW\s+ROOF|ROOF)|\bROOF\s+LEAK|\bWATER\s+DAMAGE|\bSTRUCTURAL\s+DAMAGE|\bMOLD\b"), "Poor condition", False),
    (re.compile(r"\bOVER\s?GROW"), "Overgrown", False),
    (re.compile(r"\bJUNK\b"), "Junk on site", False),
]


def condition_notes(r):
    """[(label, strong)] from the assessor's remarks and condition code."""
    text = f'{r.get("remark1") or ""} | {r.get("remark2") or ""}'.upper()
    out = [(label, strong) for rx, label, strong in _CONDITION if rx.search(text) and not (label.startswith("Unsafe") and "FP'S CONDEMNED" in text)]
    if r.get("cond") in ("P", "D") and not any(l == "Poor condition" for l, _ in out):
        out.append(("Assessor rates the building poor", False))
    return out


def absentee(r):
    """'OUT_OF_STATE' | 'OUT_OF_COUNTY' | 'MAIL_DIFFERS' | ''."""
    st = r["mail_state"].upper()
    city = r["mail_city"].upper()
    if st and st != "VA":
        return "OUT_OF_STATE"
    if not city and not r["mail_addr"]:
        return ""
    if city not in config.KG_CITIES and r["mail_zip"] not in config.KG_ZIPS:
        return "OUT_OF_COUNTY"
    # In county: an improved parcel whose bill goes to a different street number.
    if r["site_num"] and r["impr_value"] and not re.match(r"\s*(P\.?\s?O\.?\s*BOX|RT|ROUTE|RR)\b", r["mail_addr"].upper()):
        m = re.match(r"\s*(\d+)", r["mail_addr"])
        if m and int(m.group(1)) != r["site_num"]:
            return "MAIL_DIFFERS"
    return ""


_BOOK_YEAR = {}


def learn_book_years(rows):
    """
    Deed book -> approximate year, learned from parcels whose sale date is real.
    Used only for parcels whose sale date is a filler: the book number then gives
    the era of the deed. Made monotone so an early book never dates later than a
    later book.
    """
    buckets = {}
    for r in rows:
        if r["deed_page"] and 0 < r["deed_book"] < config.LAST_DEED_BOOK and sale_year_known(r) and r["sale_year"] <= 2007:
            buckets.setdefault(r["deed_book"] // 25, []).append(r["sale_year"])
    med = {b: sorted(v)[len(v) // 2] for b, v in buckets.items() if len(v) >= 5}
    _BOOK_YEAR.clear()
    running = 2007
    for b in range(config.LAST_DEED_BOOK // 25, -1, -1):
        if b in med:
            running = min(running, med[b])
        _BOOK_YEAR[b] = running


def sale_year_known(r):
    y = r["sale_year"]
    return bool(y) and y not in config.UNKNOWN_SALE_YEARS and (y, r["sale_month"], r["sale_day"]) not in config.PLACEHOLDER_SALE_DATES


def transfer_year(r):
    """(year, estimated?) of the last recorded transfer, or (None, False)."""
    if sale_year_known(r):
        return r["sale_year"], False
    if r["deed_page"] and 0 < r["deed_book"] < config.LAST_DEED_BOOK and _BOOK_YEAR:
        return _BOOK_YEAR.get(r["deed_book"] // 25), True
    return None, False


def years_since(r, this_year):
    y, _ = transfer_year(r)
    if not y or y > this_year:
        return None
    return this_year - y


def note_death(note, this_year):
    """(iso_date_or_year, years_ago) for a DOD in the assessor's note, else None."""
    best = None
    for m in _DOD.finditer(note or ""):
        if m.group(4):
            y, iso = int(m.group(4)), m.group(4)
        else:
            mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000 if y <= this_year % 100 else 1900
            if not (1 <= mo <= 12 and 1 <= d <= 31):
                continue
            iso = f"{y:04d}-{mo:02d}-{d:02d}"
        if 1900 < y <= this_year and (best is None or iso > best[0]):
            best = (iso, this_year - y)
    return best


def scan_parcel(r, this_year):
    """Return (class or '', flags, detail dict) for one parcel."""
    flags, detail = [], {}
    typ, sub = r["owner_type"], r["owner_subtype"]
    note = r["grantor_note"]
    if typ == "ESTATE":
        flags.append({"ESTATE": "ESTATE_IN_NAME", "HEIRS": "HEIRS_IN_NAME", "LIFE_ESTATE": "LIFE_ESTATE",
                      "FIDUCIARY": "EXECUTOR_IN_NAME"}[sub])
    if typ == "ET_AL" or re.search(r"\bET\s?ALS?\b", r["owner"]):
        flags.append("ET_AL")
    kind, book, page, raw = parse_will_ref(r["will_book"], r["will_page"], r["deed_book"], r["deed_page"])
    if kind == "LH":
        flags.append("LIST_OF_HEIRS_REF")
        detail["will_ref"] = f"List of Heirs, will book page {page}" if page else "List of Heirs"
    elif kind == "WB":
        flags.append("WILL_BOOK_REF")
        detail["will_ref"] = f"WB {book} PG {page}" if page and page != "0" else f"WB {book}"
    if raw:
        detail["will_ref_raw"] = raw
    is_grantor_line = note.upper().startswith("GRANTOR")
    dod = note_death(note, this_year)
    if dod:
        detail["note_dod"] = dod[0]
        if dod[1] <= config.ASSESSOR_NOTE_RECENT_YEARS:
            flags.append("ASSESSOR_DOD_NOTE")
    elif not is_grantor_line and _NOTE_WILL.search(note):
        ys = years_since(r, this_year)
        if ys is not None and ys <= config.ASSESSOR_NOTE_RECENT_YEARS:
            flags.append("ASSESSOR_WILL_NOTE")
    if is_grantor_line and re.search(r"\bESTATE\b|\bEST OF\b|\bHEIRS\b|\bEXEC", note.upper()) and "REAL ESTATE" not in note.upper():
        detail["bought_from_estate"] = True

    ys = years_since(r, this_year)
    if ys is not None:
        for thr in config.OLD_TITLE_YEARS:
            if ys >= thr:
                flags.append(f"OLD_TITLE_{thr}")
                break
    ab = absentee(r)
    if ab:
        flags.append(ab)
    if r["care_of"]:
        flags.append("CARE_OF")
    if not r["impr_value"]:
        flags.append("VACANT_LAND")
    if r["cond"] in ("P", "F", "D"):
        flags.append("POOR_CONDITION")
    notes = condition_notes(r)
    if notes:
        flags.append("CONDITION_STRONG" if any(st for _l, st in notes) else "CONDITION_NOTE")
        detail["condition"] = [l for l, _st in notes]
    if typ == "INDIVIDUAL" and re.search(r"\sOR\s", r["owner"]):
        flags.append("SURVIVORSHIP_OR")

    cls = ""
    f = set(flags)
    # Organisations are not title leads on text alone (an LLC "ET ALS" is a company).
    person_owned = typ in ("ESTATE", "ET_AL", "TRUST", "INDIVIDUAL")
    if f & {"ESTATE_IN_NAME", "EXECUTOR_IN_NAME"}:
        cls = "E1"
    elif "HEIRS_IN_NAME" in f:
        cls = "E2"
    elif "LIFE_ESTATE" in f:
        cls = "E3"
    elif "ET_AL" in f and typ == "ET_AL" and not re.search(r"\bL\.?L\.?C\b|\bINC\b", r["owner"]):
        cls = "C1"
    elif "LIST_OF_HEIRS_REF" in f and person_owned:
        cls = "W1"
    elif "WILL_BOOK_REF" in f and person_owned:
        cls = "W2"
    elif "ASSESSOR_DOD_NOTE" in f and person_owned:
        cls = "N1"
    elif "ASSESSOR_WILL_NOTE" in f and person_owned:
        cls = "N2"
    return cls, flags, detail


def score(cls, flags, n_parcels):
    pts, reasons = 0, []
    w = config.CLASS_WEIGHT[cls]
    pts += w
    reasons.append(f"+{w} {CLASS_LABEL[cls]}")
    f = set(flags)
    for thr, p in config.AGE_POINTS:
        if f"OLD_TITLE_{thr}" in f:
            pts += p
            reasons.append(f"+{p} no recorded transfer in {thr}+ years")
            break
    for k, p in config.ABSENTEE_POINTS.items():
        if k in f:
            pts += p
            reasons.append(f"+{p} " + {"OUT_OF_STATE": "tax bill mailed out of state", "OUT_OF_COUNTY": "tax bill mailed out of the county",
                                       "MAIL_DIFFERS": "tax bill mailed to a different address"}[k])
            break
    if "CARE_OF" in f:
        pts += config.CARE_OF_POINTS
        reasons.append(f"+{config.CARE_OF_POINTS} bill goes care of someone else")
    if "CONDITION_STRONG" in f:
        pts += 12
        reasons.append("+12 assessor's notes: unsafe, abandoned, burned, unlivable or vacant house")
    elif "POOR_CONDITION" in f or "CONDITION_NOTE" in f:
        pts += config.POOR_COND_POINTS
        reasons.append(f"+{config.POOR_COND_POINTS} assessor rates or notes the building in poor shape")
    if n_parcels > 1:
        pts += config.MULTI_PARCEL_POINTS
        reasons.append(f"+{config.MULTI_PARCEL_POINTS} same owner holds {n_parcels} parcels")
    return min(100, pts), reasons


def parcel_view(r, flags, detail, this_year):
    return {
        "pid": r["pid"], "pin": r["pin"], "parcel": r["parcel"],
        "address": r["site_addr"], "legal": r["legal"], "acres": r["acres"],
        "land_value": r["land_value"], "impr_value": r["impr_value"], "total_value": r["total_value"],
        "year_built": r["year_built"] or None, "cond": r["cond"],
        "sale_year": transfer_year(r)[0], "sale_year_estimated": transfer_year(r)[1],
        "sale_price": r["sale_price"] or None,
        "years_since_transfer": years_since(r, this_year),
        "deed_ref": deed_ref(r["deed_book"], r["deed_page"], r["sale_year"] if sale_year_known(r) else 0),
        "will_ref": detail.get("will_ref", ""), "will_ref_raw": detail.get("will_ref_raw", ""),
        "note": r["grantor_note"], "note_dod": detail.get("note_dod", ""),
        "condition": detail.get("condition", []),
        "remarks": " | ".join(x for x in (r.get("remark1"), r.get("remark2")) if x),
        "flags": flags, "card_url": r["card_url"],
        "water": waterfront.of(r),
    }


def run(db_path=DB_PATH, out_dir=OUT, today=None):
    today = today or dt.date.today()
    this_year = today.year
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM parcels ORDER BY pid")]
    built_at = con.execute("SELECT v FROM meta WHERE k='built_at'").fetchone()[0]
    con.close()
    owner_parse.learn_names(r["owner"] for r in rows)
    learn_book_years(rows)

    groups, watch = {}, []
    class_parcels = {}
    for r in rows:
        cls, flags, detail = scan_parcel(r, this_year)
        if not cls:
            f = set(flags)
            if r["owner_type"] in ("INDIVIDUAL", "TRUST") and "OLD_TITLE_40" in f and \
                    (f & {"OUT_OF_STATE", "OUT_OF_COUNTY", "MAIL_DIFFERS", "CARE_OF"}):
                watch.append({"pid": r["pid"], "pin": r["pin"], "owner": r["owner"], "sale_year": r["sale_year"],
                              "mail": f'{r["mail_addr"]}, {r["mail_city"]} {r["mail_state"]}', "flags": flags,
                              "total_value": r["total_value"]})
            continue
        class_parcels[cls] = class_parcels.get(cls, 0) + 1
        key = (r["owner"], r["mail_addr"].upper(), str(r["mail_zip"]))
        g = groups.setdefault(key, {"rows": [], "classes": set(), "flags": set()})
        g["rows"].append((r, flags, detail, cls))
        g["classes"].add(cls)
        g["flags"].update(flags)

    leads = []
    for (owner, mail_addr, _zip), g in groups.items():
        cls = next(c for c in CLASS_ORDER if c in g["classes"])
        r0 = g["rows"][0][0]
        parcels = [parcel_view(r, fl, de, this_year) for r, fl, de, _ in g["rows"]]
        parcels.sort(key=lambda p: -p["total_value"])
        # group flags: age and condition from the oldest / worst parcel
        flags = sorted(g["flags"])
        for thr in config.OLD_TITLE_YEARS:                    # keep only the strongest age flag
            if f"OLD_TITLE_{thr}" in g["flags"]:
                flags = [x for x in flags if not x.startswith("OLD_TITLE_") or x == f"OLD_TITLE_{thr}"]
                break
        pts, reasons = score(cls, flags, len(parcels))
        people = owner_parse.split_people(r0["lnam"], r0["fnam"])
        ys = [p["years_since_transfer"] for p in parcels if p["years_since_transfer"] is not None]
        lead = {
            "id": hashlib.sha1(f"{owner}|{mail_addr}|{_zip}".encode()).hexdigest()[:12],
            "priority": pts, "reasons": reasons,
            "title_class": cls, "class_label": CLASS_LABEL[cls],
            "owner": owner, "owner_raw": [r0["lnam"], r0["fnam"]],
            "owner_type": r0["owner_type"], "owner_subtype": r0["owner_subtype"],
            "care_of": r0["care_of"],
            "people": [p["name"] for p in people],
            "mail": {"addr": r0["mail_addr"], "addr2": r0["mail_addr2"], "city": r0["mail_city"],
                     "state": r0["mail_state"], "zip": r0["mail_zip"] or None},
            "flags": flags,
            "parcel_count": len(parcels),
            "total_value": sum(p["total_value"] for p in parcels),
            "acres": round(sum(p["acres"] for p in parcels), 2),
            "oldest_transfer_years": max(ys) if ys else None,
            "note_dod": max((p["note_dod"] for p in parcels), default=""),
            "parcels": parcels,
        }
        leads.append(lead)
    leads.sort(key=lambda l: (-l["priority"], -l["total_value"], l["owner"]))

    classes = {}
    for l in leads:
        classes[l["title_class"]] = classes.get(l["title_class"], 0) + 1
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    summary = {
        "generated_at": now, "index_built_at": built_at, "county": config.COUNTY, "state": config.STATE,
        "parcels_indexed": len(rows), "leads": len(leads), "lead_parcels": sum(l["parcel_count"] for l in leads),
        "classes": classes, "class_parcels": class_parcels, "class_labels": CLASS_LABEL, "class_order": CLASS_ORDER,
        "next_step": NEXT_STEP, "watch_hidden": len(watch),
        "presets": [
            {"id": "estate", "label": "Estate / heirs on title", "classes": ["E1", "E2"]},
            {"id": "etal", "label": "Et al co-owners", "classes": ["C1"]},
            {"id": "life", "label": "Life estate", "classes": ["E3"]},
            {"id": "will", "label": "Will / List of Heirs reference", "classes": ["W1", "W2"]},
            {"id": "note", "label": "Death or will noted by assessor", "classes": ["N1", "N2"]},
            {"id": "old", "label": "No transfer in 40+ years", "flag": "OLD_TITLE_40"},
            {"id": "absentee", "label": "Bill mailed elsewhere", "flags_any": ["OUT_OF_STATE", "OUT_OF_COUNTY", "MAIL_DIFFERS", "CARE_OF"]},
        ],
    }
    os.makedirs(out_dir, exist_ok=True)
    json.dump({"generated_at": now, "rows": leads}, open(os.path.join(out_dir, "leads.json"), "w"), separators=(",", ":"))
    json.dump({"generated_at": now, "note": "Held back from the board until a death or delinquency record supports them.",
               "rows": watch}, open(os.path.join(out_dir, "watch.json"), "w"), separators=(",", ":"))
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w"), indent=1)
    log.info("%s leads over %s parcels; classes %s; %s held on watch", len(leads), summary["lead_parcels"], classes, len(watch))
    return summary


if __name__ == "__main__":
    run()
