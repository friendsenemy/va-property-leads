"""
Dirt Deals (Virginia) — raw land a homebuilder would want once it is approved for houses.
Same play as the Maryland tool's Dirt Deals tab (Cody Bjugan's "LDP"): find off-market
acreage in a county's growth area, tie it up with a long due-diligence contract, then
assign it (or partner on entitlement) to a builder.

Virginia has no statewide sewer-tier map, so each county's own planning layers stand in:

  King George  Settlement Areas (the Comprehensive Plan's growth areas), Service Authority
               water/sewer areas, the water and sewer lines now being built (Canterbury /
               Circle / Courthouse / Hopyard, due 2026), the county's own list of parcels
               in the water-expansion area, zoning, approved subdivisions
  Fauquier     Service Districts (the growth areas, with the planned density), zoning,
               rezoning / preliminary-plat applications nearby, the Catlett-Calverton
               sewer project; conservation easements and ag-forestal districts are dropped
  Westmoreland no zoning or growth layer is published: distance to Colonial Beach and
               Montross stands in, and there is no year-built or sale data

Plus, for every county: new homes built nearby (year built), builders buying nearby
(owner names on recent sales), and the seller signals the tool already has (death match,
unpaid taxes, heirs / estate / et al on title, long-held, out of state).

  python -m engine.land_watch                 # all three counties
  python -m engine.land_watch --county fauquier

Writes <county data dir>/land/candidates.json for the "Dirt Deals" tab.
Needs shapely (requirements-geo.txt).
"""

import argparse
import json
import logging
import math
import os
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

import requests
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("land_watch")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KG = "https://services2.arcgis.com/S8zMJrpz61FbvL5t/arcgis/rest/services"
FQ = "https://services.arcgis.com/oAoeYJ1kqmAwcEC2/arcgis/rest/services"
WM = "https://services5.arcgis.com/uEb6ucnhLOwh4rfI/arcgis/rest/services"
UA = "va-property-leads/1.0 (+https://github.com/friendsenemy/va-property-leads)"

MIN_ACRES = 5.0
PER_COUNTY = 300                    # best N kept per county
THIS_YEAR = date.today().year
NEW_HOME_YEARS = 4                  # "new homes" = built in the last 4 years
NEARBY_MI = 1.5
BUILDER_MI = 2.0
SKIP_TYPES = {"GOVERNMENT", "CHURCH", "CEMETERY", "ASSOCIATION"}

COUNTIES = {
    "king-george": {"name": "King George", "dir": "data"},
    "westmoreland": {"name": "Westmoreland", "dir": "data/westmoreland"},
    "fauquier": {"name": "Fauquier", "dir": "data/fauquier"},
}

# Production and regional builders active in the Fredericksburg / Northern Neck / Fauquier market.
BUILDER_RE = re.compile(
    r"\b(NVR|RYAN HOMES|NV HOMES|LENNAR|D ?R HORTON|TOLL BROS|TOLL BROTHERS|STANLEY MARTIN|DAN RYAN|RICHMOND AMERICAN|"
    r"PULTE|CENTEX|DEL WEBB|KB HOME|BROOKFIELD|CHRISTOPHER CONSULTANTS|VAN METRE|WINCHESTER HOMES|CARUSO|"
    r"MERITAGE|SM HOMES|DRP|DREAM FINDERS|HOMES BY|BUILDERS|HOMEBUILD|CUSTOM HOMES|HOMES INC|HOMES LLC|HOMES LTD|"
    r"DEVELOPMENT (?:CORP|INC|LLC|CO|GROUP)|DEVELOPERS|LAND HOLDINGS|COMMUNITIES)\b")
NOT_BUILDER = re.compile(r"\b(TRUST|TRUSTEE|U/W|ESTATE|ENERGY|SOLAR|CHURCH)\b")


def is_builder(owner):
    o = (owner or "").upper()
    return bool(BUILDER_RE.search(o)) and not NOT_BUILDER.search(o)

# Rough homes per acre before roads, stormwater and setbacks (a first screen, not a yield study).
KG_ZONE_DENSITY = {"R1": 1.0, "R2": 2.0, "R3": 4.0, "A2": 0.5, "A1": 0.1, "A3": 0.1}


def get(url, params, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=90)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            log.warning("retry %s: %s", url.split("/services/")[-1], e)
            time.sleep(3 * (i + 1))


def layer(base, name, fields="*", where="1=1"):
    """Every feature of a hosted layer as (attributes, shapely geometry in lon/lat)."""
    url = f"{base}/{name}/FeatureServer/0/query"
    out, off = [], 0
    while True:
        j = get(url, {"where": where, "outFields": fields, "returnGeometry": "true", "outSR": 4326,
                      "f": "geojson", "resultOffset": off, "resultRecordCount": 1000})
        feats = j.get("features", [])
        for f in feats:
            if f.get("geometry"):
                try:
                    out.append((f.get("properties") or {}, shape(f["geometry"])))
                except Exception:  # noqa: BLE001
                    pass
        if len(feats) < 1000:
            break
        off += 1000
    log.info("  %s: %d features", name, len(out))
    return out


class Index:
    """Point-in-polygon / nearest lookups over a list of (attrs, geom)."""
    def __init__(self, feats):
        self.feats = feats
        self.tree = STRtree([g for _, g in feats]) if feats else None

    def containing(self, pt):
        if not self.tree:
            return []
        return [self.feats[i][0] for i in self.tree.query(pt) if self.feats[i][1].contains(pt)]

    def within_mi(self, pt, mi):
        """[(attrs, miles)] for features within `mi` miles of the point."""
        if not self.tree:
            return []
        deg = mi / 53.0
        out = []
        for i in self.tree.query(pt.buffer(deg)):
            d = self.feats[i][1].distance(pt) * 60.0      # ~miles at this latitude
            if d <= mi:
                out.append((self.feats[i][0], round(d, 2)))
        return sorted(out, key=lambda x: x[1])


def hav_mi(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


class Grid:
    def __init__(self, items, cell=0.03):
        self.cell, self.g = cell, defaultdict(list)
        for it in items:
            self.g[(int(it["lat"] / cell), int(it["lon"] / cell))].append(it)

    def near(self, lat, lon, mi):
        r = int(mi / 2.0) + 1
        ci, cj = int(lat / self.cell), int(lon / self.cell)
        out = []
        for i in range(ci - r, ci + r + 1):
            for j in range(cj - r, cj + r + 1):
                for it in self.g.get((i, j), []):
                    if hav_mi((lat, lon), (it["lat"], it["lon"])) <= mi:
                        out.append(it)
        return out


def load_json(path, default=None):
    try:
        with open(os.path.join(ROOT, path)) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def seller_signals(cdir):
    """pid -> {"distress": [...], "detail": [...], "title": [...]} from the boards the tool already builds."""
    out = defaultdict(lambda: {"distress": [], "detail": [], "title": []})
    comb = load_json(f"{cdir}/combined/leads.json", {"rows": []})
    for r in comb.get("rows", []):
        s = r.get("signals", {})
        for p in r.get("parcels", []):
            o = out[p.get("pid")]
            if "DEATH" in s:
                o["distress"].append("DEATH"); o["detail"].append(f"Owner death match: {s['DEATH'].get('label', '')}")
            if "TAX" in s:
                o["distress"].append("TAX"); o["detail"].append(f"Unpaid taxes: {s['TAX'].get('label', '')}")
            if "CONDITION" in s:
                o["distress"].append("CONDITION"); o["detail"].append(f"Assessor condition: {s['CONDITION'].get('label', '')}")
    for r in load_json(f"{cdir}/delinquency/leads.json", {"rows": []}).get("rows", []):
        for p in r.get("parcels", []):
            o = out[p.get("pid")]
            if "TAX" not in o["distress"]:
                o["distress"].append("TAX")
                o["detail"].append(f"Unpaid taxes: ${r.get('past_due', 0):,.2f} past due" + (" (tax-sale eligible)" if r.get("sale_eligible") else ""))
    for r in load_json(f"{cdir}/title/leads.json", {"rows": []}).get("rows", []):
        lab = r.get("class_label") or r.get("title_class") or ""
        for p in r.get("parcels", []):
            o = out[p.get("pid")]
            if lab and lab not in o["title"]:
                o["title"].append(lab)
    return out


# ------------------------------- county growth context -------------------------------

def kg_context():
    ctx = {
        "settle": Index(layer(KG, "Settlement_Areas", "Name,Acres")),
        "sa": Index(layer(KG, "ServiceAuthorityAreas", "Name,Type")),
        "zoning": Index(layer(KG, "Zoning", "Zoning")),
        "newlines": Index(layer(KG, "ProposedWaterExpansion", "Name,ExpCompDat") + layer(KG, "ProposedForceMain", "Name,ExpCompDat")),
        "subs": Index(layer(KG, "SUBDIVISIONS", "Sub_name,Status,YearsBuilt,NumberofVa,Sewer,Water")),
    }
    pins = set()
    for a, _ in layer(KG, "WaterExpansionProperties", "PIN"):
        pins.add(re.sub(r"\s+", "", a.get("PIN") or ""))
    ctx["water_exp_pins"] = pins
    return ctx


def fq_context():
    apps = layer(FQ, "Planning_Land_Development_Applications_WFL1", "PlanNumber,PlanType,PlanStatus,ApplicationDate,ProjectName")
    keep = []
    for a, g in apps:
        ts = a.get("ApplicationDate")
        yr = datetime.fromtimestamp(ts / 1000, timezone.utc).year if ts else 0
        if a.get("PlanType") in ("Rezoning", "Preliminary Plat") and yr >= THIS_YEAR - 6 and a.get("PlanStatus") not in ("Denied", "Withdrawn", "Voided"):
            a["_year"] = yr
            keep.append((a, g))
    return {
        "svc": Index(layer(FQ, "Service_Districts_DL", "SVCDISTRIC,DISTRICTNA")),
        "zoning": Index(layer(FQ, "Zoning_Districts_DL", "ZONECLASS")),
        "apps": Index(keep),
        "catcal": Index(layer(FQ, "CatCalSwrRemDistricts", "NAME")),
        "cons": Index(layer(FQ, "Conservation_Easements_DL", "EASEMENTTY")),
        "agfor": Index(layer(FQ, "Ag_Forestal_DL", "DISTRICTNA")),
    }


def wm_context():
    return {"towns": Index(layer(WM, "WesmoTowns", "NAME"))}


def density_from_text(t):
    """'LDR 1-3 UNITS PER ACRE' -> 2.0 ; 'LDR UP TO 1 DWL UNIT PER ACRE' -> 1.0 ; '1 UNIT PER 10 ACRES' -> 0.1"""
    t = (t or "").upper()
    m = re.search(r"1 UNIT PER (\d+) ACRES", t)
    if m:
        return 1 / float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|TO)\s*(\d+)\s*(?:DWL )?UNITS? PER ACRE", t)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2
    m = re.search(r"UP TO (\d+) DWL UNIT", t)
    if m:
        return float(m.group(1)) * 0.75
    if "MDR" in t:
        return 5.0
    if "HDR" in t:
        return 10.0
    return 0.0


def growth(key, ctx, pt, pin):
    """-> dict(tier_group, tier, zoning, gen_zone, density, points, reasons, cautions, tags, drop)."""
    g = {"tier_group": "3", "tier": "", "zoning": "", "gen_zone": "", "density": 0.1, "points": 0,
         "reasons": [], "cautions": [], "tags": [], "drop": False}
    if key == "king-george":
        z = ctx["zoning"].containing(pt)
        g["zoning"] = (z[0].get("Zoning") if z else "") or ""
        st = ctx["settle"].containing(pt)
        big = {"Rappahannock River", "Potomac River"}       # the huge river-corridor polygons are not growth areas
        st = [s for s in st if s.get("Name") not in big]
        sa = ctx["sa"].containing(pt)
        lines = ctx["newlines"].within_mi(pt, 1.0)
        in_exp = pin in ctx["water_exp_pins"]
        if sa:
            t = sa[0].get("Type") or ""
            g["tier_group"] = "1"; g["tier"] = f"{sa[0].get('Name')} service area ({t.lower()})"
            g["points"] += 40 if "Sewer" in t else 30
            g["reasons"].append(f"+{40 if 'Sewer' in t else 30} inside the {sa[0].get('Name')} Service Authority area ({t.lower()})")
        if st:
            if g["tier_group"] != "1":
                g["tier_group"] = "2"; g["tier"] = f"{st[0].get('Name')} Settlement Area"
            g["points"] += 25
            g["reasons"].append(f"+25 inside the {st[0].get('Name')} Settlement Area (the county's planned growth area)")
        if lines:
            a, d = lines[0]
            g["points"] += 25 if d <= 0.5 else 15
            g["reasons"].append(f"+{25 if d <= 0.5 else 15} {d} mi from the new {a.get('Name')} line (due {a.get('ExpCompDat')})")
            if g["tier_group"] == "3":
                g["tier_group"] = "2"; g["tier"] = "Near a new water/sewer line"
        if in_exp:
            g["points"] += 15
            g["reasons"].append("+15 on the county's list of parcels in the water-expansion area")
            if g["tier_group"] == "3":
                g["tier_group"] = "2"; g["tier"] = "Water-expansion area"
        dens = KG_ZONE_DENSITY.get(g["zoning"], 0.1)
        if g["tier_group"] == "1" and dens < 1:
            dens = 1.0
        g["density"] = dens
        g["gen_zone"] = {"R1": "Residential", "R2": "Residential", "R3": "Residential (higher density)", "A1": "Agricultural",
                         "A2": "Agricultural / residential", "A3": "Agricultural", "C1": "Commercial", "C2": "Commercial", "I": "Industrial", "I1": "Industrial"}.get(g["zoning"], "")
        if g["zoning"].startswith("R"):
            g["points"] += 15; g["reasons"].append(f"+15 already zoned {g['zoning']} (residential)")
        elif g["zoning"] in ("A1", "A3") and g["tier_group"] != "3":
            g["tags"].append("NEEDS_REZONING"); g["cautions"].append(f"Zoned {g['zoning']} (agricultural): a subdivision would need rezoning")
        elif g["zoning"].startswith(("C", "I")):
            g["cautions"].append(f"Zoned {g['zoning']}: commercial/industrial, not a homebuilder parcel unless rezoned")
        subs = [(a, d) for a, d in ctx["subs"].within_mi(pt, NEARBY_MI) if (a.get("Status") or "").strip() in ("Approved", "Under Review")]
        if subs:
            act = [a for a, _ in subs if "?" in str(a.get("YearsBuilt") or "") or (a.get("Status") or "").strip() == "Under Review"]
            if act:
                g["points"] += 10
                g["reasons"].append(f"+10 active subdivision nearby: {', '.join(sorted({a.get('Sub_name') for a in act})[:3])}")
    elif key == "fauquier":
        if ctx["cons"].containing(pt):
            g["drop"] = True; return g
        z = ctx["zoning"].containing(pt)
        g["zoning"] = (z[0].get("ZONECLASS") if z else "") or ""
        if ctx["agfor"].containing(pt):
            g["cautions"].append("Inside an Agricultural & Forestal District (development limited while the district runs)")
            g["points"] -= 25
        sv = ctx["svc"].containing(pt)
        if sv:
            name, use = sv[0].get("SVCDISTRIC") or "", sv[0].get("DISTRICTNA") or ""
            nonres = re.search(r"INDUSTRIAL|BUSINESS|COMMERCIAL|GATEWAY|EMPLOYMENT|OFFICE|INSTITUTIONAL", use)
            g["tier_group"] = "1" if re.search(r"UNITS? PER ACRE|MIXED USE|RESIDENTIAL|TOWN CENTER|NEIGHBORHOOD", use) and not nonres else "2"
            g["tier"] = f"{name.title()} Service District · {use.title()}"
            g["gen_zone"] = use.title()
            dens = density_from_text(use)
            g["density"] = dens or 1.0
            if nonres:
                g["points"] += 10; g["density"] = 0.5
                g["cautions"].append(f"Planned use here is {use.lower()}: a builder of houses would need a plan amendment")
            elif re.search(r"OPEN SPACE|PARK|SCHOOL|FLOODPLAIN|GREENWAY", use) and not dens:
                g["cautions"].append(f"Planned use here is {use.lower()}")
                g["points"] += 5
            else:
                g["points"] += 45 if dens >= 1 else 30
                g["reasons"].append(f"+{45 if dens >= 1 else 30} inside the {name.title()} Service District, planned {use.lower()}")
        cc = ctx["catcal"].containing(pt)
        if cc:
            g["points"] += 15; g["reasons"].append(f"+15 inside the {cc[0].get('NAME', '').title()} sewer remediation district (public sewer project)")
            if g["tier_group"] == "3":
                g["tier_group"] = "2"; g["tier"] = "Catlett-Calverton sewer project area"
        if g["zoning"] in ("R-1", "R-2", "R-4", "PRD", "TH", "V", "RR-2"):
            g["points"] += 15; g["reasons"].append(f"+15 zoned {g['zoning']} (residential)")
        elif g["zoning"] in ("RA", "RC") and g["tier_group"] != "3":
            g["tags"].append("NEEDS_REZONING"); g["cautions"].append(f"Zoned {g['zoning']} (rural): a subdivision would need rezoning")
        elif g["zoning"] in ("RA", "RC"):
            g["density"] = 1 / 25 if g["zoning"] == "RA" else 1 / 10
        apps = ctx["apps"].within_mi(pt, NEARBY_MI)
        if apps:
            a, d = apps[0]
            g["points"] += 15
            g["reasons"].append(f"+15 {a.get('PlanType').lower()} filed {d} mi away ({a.get('_year')}): {a.get('ProjectName') or a.get('PlanNumber')}")
            if a.get("PlanType") == "Rezoning":
                g["tags"].append("RECENT_REZONING")
    else:   # westmoreland
        t = ctx["towns"].within_mi(pt, 3.0)
        if t:
            a, d = t[0]
            if d == 0:
                g["tier_group"] = "1"; g["tier"] = f"Inside the Town of {a.get('NAME')}"; g["points"] += 35; g["density"] = 2.0
                g["reasons"].append(f"+35 inside the Town of {a.get('NAME')} (town water and sewer likely)")
            else:
                g["tier_group"] = "2"; g["tier"] = f"{d} mi from {a.get('NAME')}"; g["points"] += 25 if d <= 1 else 12; g["density"] = 0.5
                g["reasons"].append(f"+{25 if d <= 1 else 12} {d} mi from the Town of {a.get('NAME')}")
        else:
            g["density"] = 0.2
        g["cautions"].append("Westmoreland publishes no zoning or growth map: confirm zoning with the county before calling a builder")
    return g


def run(keys):
    for key in keys:
        meta = COUNTIES[key]
        cdir = meta["dir"]
        log.info("=== %s", meta["name"])
        pj = load_json(f"{cdir}/parcels.json")
        cols = pj["columns"]
        rows = [dict(zip(cols, r)) for r in pj["rows"]]
        cent = load_json(f"{cdir}/centroids.json", {})
        for r in rows:
            c = cent.get(str(r["pid"]))
            r["lat"], r["lon"] = (c[0], c[1]) if c else (None, None)
        ctx = {"king-george": kg_context, "fauquier": fq_context, "westmoreland": wm_context}[key]()
        signals = seller_signals(cdir)

        new_homes = Grid([r for r in rows if r["lat"] and (r.get("year_built") or 0) >= THIS_YEAR - NEW_HOME_YEARS])
        builders = Grid([r for r in rows if r["lat"] and (r.get("sale_year") or 0) >= THIS_YEAR - NEW_HOME_YEARS
                         and is_builder(r.get("owner"))])

        scanned, qualified, out = 0, 0, []
        for r in rows:
            try:
                ac = float(r.get("acres") or 0)
            except (TypeError, ValueError):
                ac = 0
            if ac < MIN_ACRES or not r["lat"] or r.get("owner_type") in SKIP_TYPES:
                continue
            owner = (r.get("owner") or "").upper()
            if is_builder(owner):
                continue                                   # a builder already owns it
            scanned += 1
            pt = Point(r["lon"], r["lat"])
            pin = re.sub(r"\s+", "", r.get("pin") or "")
            g = growth(key, ctx, pt, pin)
            if g["drop"]:
                continue
            reasons, cautions, tags = list(g["reasons"]), list(g["cautions"]), list(g["tags"])
            dev = g["points"]
            impr = float(r.get("impr_value") or 0)
            if impr < 50000:
                tags.append("RAW_LAND"); dev += 10; reasons.append("+10 raw land (little or no building value)")
            nh = new_homes.near(r["lat"], r["lon"], NEARBY_MI) if key != "westmoreland" else []
            if nh:
                pts = 20 if len(nh) >= 15 else 12 if len(nh) >= 5 else 6
                dev += pts; tags.append("NEW_HOMES_NEARBY"); reasons.append(f"+{pts} {len(nh)} homes built within {NEARBY_MI} mi in the last {NEW_HOME_YEARS} years")
            bn = builders.near(r["lat"], r["lon"], BUILDER_MI) if key != "westmoreland" else []
            bnames = sorted({(b.get("owner") or "")[:32] for b in bn})[:5]
            if bnames:
                dev += 15; tags.append("BUILDER_BUYING_NEARBY"); reasons.append(f"+15 builders bought within {BUILDER_MI} mi: {', '.join(bnames[:3])}")
            if g["tier_group"] == "3":
                if dev < 45:
                    continue                               # rural, not enough pointing at growth
                dev -= 15
                cautions.append("Outside every growth area and planned utility line: wells and septic, a harder sell to a builder")
            qualified += 1
            sell = 0
            sy = r.get("sale_year") or 0
            if sy and THIS_YEAR - sy >= 25:
                tags.append("LONG_HELD"); sell += 10; reasons.append(f"+10 held since {sy}")
            elif sy and THIS_YEAR - sy <= 2:
                tags.append("RECENT_SALE"); cautions.append(f"Sold in {sy}: the owner just paid market price")
            st = (r.get("mail_state") or "").upper()
            if st and st != "VA":
                tags.append("OUT_OF_STATE"); sell += 10; reasons.append(f"+10 tax bill mailed out of state ({st})")
            sg = signals.get(r["pid"], {"distress": [], "detail": [], "title": []})
            if sg["title"] or r.get("owner_type") in ("ESTATE", "ET_AL"):
                tags.append("MESSY_TITLE"); sell += 15
                reasons.append(f"+15 title: {', '.join(sg['title']) or r.get('owner_type').replace('_', ' ').lower()}")
            dist = sorted(set(sg["distress"]))
            sell += 15 * len(dist)
            if r.get("water"):
                tags.append("WATERFRONT")
            dens = g["density"] or 0.1
            lots = int(ac * dens * 0.7) if dens else 0         # 30% off for roads, stormwater, setbacks
            score = max(0, min(100, round(dev * 0.6 + sell)))
            out.append({
                "account": f"{key}:{r['pid']}", "pid": r["pid"], "county_key": key, "county": meta["name"],
                "pin": r.get("pin"), "address": r.get("site_addr") or "", "city": "", "zip": "",
                "acres": round(ac, 2), "tier_group": g["tier_group"], "tier": g["tier"], "zoning": g["zoning"], "gen_zone": g["gen_zone"],
                "rough_lots": lots, "new_homes_nearby": len(nh), "builders_nearby": bnames,
                "owner": r.get("owner"), "owner2": r.get("care_of") or "",
                "mail": ", ".join(x for x in (r.get("mail_addr"), r.get("mail_city"), r.get("mail_state"), str(r.get("mail_zip") or "")) if x),
                "mail_state": st, "transfer_date": str(sy or ""), "sale_price": r.get("sale_price"),
                "land_value": r.get("land_value"), "impr_value": r.get("impr_value"),
                "deed": f"{r.get('deed_book')}/{r.get('deed_page')}" if r.get("deed_book") else "",
                "tags": sorted(set(tags), key=tags.index), "distress": dist, "distress_detail": sg["detail"], "title_flags": sg["title"],
                "reasons": reasons, "cautions": cautions, "dev_score": dev, "score": score,
                "lat": r["lat"], "lon": r["lon"], "water_name": r.get("water") if isinstance(r.get("water"), str) else "",
            })
        out.sort(key=lambda x: -x["score"])
        kept = out[:PER_COUNTY]
        dest = os.path.join(ROOT, cdir, "land", "candidates.json")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w") as f:
            json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "county": meta["name"], "min_acres": MIN_ACRES,
                       "scanned": scanned, "qualified": qualified, "rows_written": len(kept),
                       "tier_counts": dict(Counter(x["tier_group"] for x in kept)), "rows": kept}, f, separators=(",", ":"))
        log.info("%s: %d parcels of %s+ ac scanned, %d qualified, %d written", meta["name"], scanned, MIN_ACRES, qualified, len(kept))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", choices=list(COUNTIES))
    a = ap.parse_args()
    run([a.county] if a.county else list(COUNTIES))
