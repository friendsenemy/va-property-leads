"""
Which parcels touch water.

  python -m engine.waterfront                           # King George
  VAPL_COUNTY=westmoreland python -m engine.waterfront  # Westmoreland

Measured from the map, not from anyone's description: each parcel's outline (the same
county layer the rest of the tool reads) against the Census Bureau's TIGER/Line "area
water" polygons for the county (public domain). A parcel is waterfront when its boundary
comes within 15 metres of a river, bay, tidal creek, or a lake or pond of two acres or
more. Frontage is the length of the parcel's boundary inside that band.

It changes only when parcels are split or merged, so this runs by hand or once a month,
not nightly. Output: <county data>/waterfront.json, read by every board.

What it cannot see: a creek too narrow for the Census to draw as an area, marsh between
the lot and open water, and bluff height. "Waterfront" here means the lot line reaches
the water's mapped edge, nothing more.

Needs shapely and pyshp (requirements-geo.txt).
"""
import datetime as dt
import io
import json
import logging
import math
import os
import time
import zipfile

import requests

from engine import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("waterfront")

OUT = os.path.join(config.DATA_DIR, "waterfront.json")
FIPS = {"king-george": "51099", "westmoreland": "51193", "fauquier": "51061"}
TIGER = "https://www2.census.gov/geo/tiger/TIGER2024/AREAWATER/tl_2024_{fips}_areawater.zip"
NEAR_M = 15                 # a lot line this close to the water's mapped edge counts as touching it
MIN_POND_M2 = 8094          # two acres: smaller ponds are farm ponds, not waterfront
MIN_FRONT_FT = 20           # less boundary than this inside the band is a corner clipping the buffer
KIND = {"H2030": "lake or pond", "H2040": "reservoir", "H2051": "bay or estuary", "H2053": "ocean", "H3010": "river or creek",
        "H3013": "river or creek", "H3020": "canal"}
ID_FIELD = {"king-george": "PID", "westmoreland": "PARCELJOIN", "fauquier": "VisionPID"}


def projector(lat0):
    """Degrees -> metres on a local flat grid. Good to well under a metre across one county."""
    kx, ky = 111320.0 * math.cos(math.radians(lat0)), 110540.0
    return lambda x, y: (x * kx, y * ky)


_ABBR = {"Riv": "River", "Crk": "Creek", "Lk": "Lake", "Pd": "Pond", "Br": "Branch", "Swp": "Swamp", "Cv": "Cove", "Hbr": "Harbor", "Rsvr": "Reservoir", "Pt": "Point"}


def spell_out(name):
    """'Potomac Riv' -> 'Potomac River', 'Lk Monroe' -> 'Lake Monroe'."""
    return " ".join(_ABBR.get(w, w) for w in name.split())


def water_polygons(fips, proj):
    import shapefile
    from shapely.geometry import shape
    from shapely.ops import transform
    cache = os.path.join(config.ROOT, ".cache", f"areawater_{fips}.zip")
    if not os.path.exists(cache):
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        r = requests.get(TIGER.format(fips=fips), headers={"User-Agent": config.USER_AGENT}, timeout=120)
        r.raise_for_status()
        open(cache, "wb").write(r.content)
    z = zipfile.ZipFile(cache)
    base = [n for n in z.namelist() if n.endswith(".shp")][0][:-4]
    sf = shapefile.Reader(shp=io.BytesIO(z.read(base + ".shp")), dbf=io.BytesIO(z.read(base + ".dbf")), shx=io.BytesIO(z.read(base + ".shx")))
    out = []
    for sr in sf.iterShapeRecords():
        rec = sr.record.as_dict()
        mtfcc, name, area = rec.get("MTFCC", ""), (rec.get("FULLNAME") or "").strip(), float(rec.get("AWATER") or 0)
        name = spell_out(name)
        if mtfcc not in KIND:
            continue
        if mtfcc in ("H2030", "H2040") and area < MIN_POND_M2:
            continue
        g = transform(lambda x, y, z=None: proj(x, y), shape(sr.shape.__geo_interface__))
        if not g.is_valid:
            g = g.buffer(0)
        out.append({"geom": g, "name": name, "kind": KIND[mtfcc], "area": area})
    return out


def parcel_outlines(proj):
    """(parcel id, polygon in metres) for every parcel, outlines simplified to about two metres."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    idf = ID_FIELD[config.KEY]
    sess = requests.Session()
    sess.headers["User-Agent"] = config.USER_AGENT
    offset, out = 0, {}
    while True:
        params = {"where": "1=1", "outFields": idf, "returnGeometry": "true", "outSR": 4326, "geometryPrecision": 6,
                  "maxAllowableOffset": 0.00002, "orderByFields": "FID", "resultOffset": offset, "resultRecordCount": config.PAGE_SIZE, "f": "json"}
        j = None
        for attempt in range(4):
            try:
                r = sess.get(config.PARCELS_URL + "/query", params=params, timeout=180)
                r.raise_for_status()
                j = r.json()
                if "error" in j:
                    raise RuntimeError(j["error"])
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 3:
                    raise
                log.warning("geometry page at %s failed (%s); retrying", offset, e)
                time.sleep(5 * (attempt + 1))
        feats = j.get("features", [])
        for f in feats:
            rings = (f.get("geometry") or {}).get("rings") or []
            raw = f["attributes"].get(idf)
            if not rings or raw in (None, "", 0, " "):
                continue
            if config.KEY == "westmoreland":
                pid = config.ADAPT({"PARCELJOIN": raw})["PID"]
            elif config.KEY == "fauquier":
                pid = config.FQ_PID_BASE + int(raw) if str(raw).strip().isdigit() else 0
            else:
                pid = int(raw)
            polys = []
            for ring in rings:
                if len(ring) >= 4:
                    p = Polygon([proj(x, y) for x, y in ring])
                    polys.append(p if p.is_valid else p.buffer(0))
            if polys and pid:
                g = unary_union(polys)
                out[pid] = unary_union([out[pid], g]) if pid in out else g      # multi-part parcels
        offset += len(feats)
        log.info("outlines: %s", offset)
        if not feats or not j.get("exceededTransferLimit"):
            break
        time.sleep(config.REQUEST_PAUSE_S)
    return out


def run():
    from shapely.strtree import STRtree
    lat0 = 38.2
    proj = projector(lat0)
    water = water_polygons(FIPS[config.KEY], proj)
    log.info("%s water bodies (rivers, creeks, bays, ponds of 2+ acres)", len(water))
    tree = STRtree([w["geom"] for w in water])
    parcels = parcel_outlines(proj)
    rows = {}
    for pid, g in parcels.items():
        best = None
        for i in tree.query(g.buffer(NEAR_M)):
            w = water[int(i)]
            if g.distance(w["geom"]) > NEAR_M:
                continue
            band = g.boundary.intersection(w["geom"].buffer(NEAR_M)).length
            # the two side lines run through the band as well; take them off so this reads as shoreline
            front_ft = max(band - 2 * NEAR_M, band * 0.5) * 3.28084
            if front_ft < MIN_FRONT_FT:
                continue
            cand = {"water": w["name"] or ("unnamed " + w["kind"]), "kind": w["kind"], "frontage_ft": int(round(front_ft, -1)), "_rank": (bool(w["name"]), w["area"])}
            if not best or cand["_rank"] > best["_rank"]:
                front_total = (best["frontage_ft"] if best else 0)
                best = dict(cand, frontage_ft=max(cand["frontage_ft"], front_total))
        if best:
            best.pop("_rank")
            rows[str(pid)] = best
    names = {}
    for r in rows.values():
        names[r["water"]] = names.get(r["water"], 0) + 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "county": config.COUNTY,
               "method": f"parcel outline within {NEAR_M} m of a Census TIGER/Line 2024 area-water polygon (ponds under 2 acres ignored); "
                         f"frontage is the boundary length inside that band, to the nearest 10 ft",
               "parcels_measured": len(parcels), "waterfront": len(rows), "by_water": dict(sorted(names.items(), key=lambda kv: -kv[1])),
               "rows": dict(sorted(rows.items(), key=lambda kv: int(kv[0])))}, open(OUT, "w"), separators=(",", ":"))
    log.info("%s of %s parcels are waterfront; top waters: %s", len(rows), len(parcels), list(names.items())[:0] or sorted(names.items(), key=lambda kv: -kv[1])[:8])


_CACHE = None
_SAYS = __import__("re").compile(r"\b(?:WATER|RIVER|CREEK|LAKE|BAY)\s?FRONT\b|\bFRONTS?\s+(?:ON\s+)?(?:THE\s+)?(?:RIVER|CREEK|POTOMAC|RAPPAHANNOCK)\b|\bTOUCHES\s+(?:LAKE|RIVER|CREEK)\b")
_SAYS_NOT = __import__("re").compile(r"\bNOT\s+(?:ON\s+)?(?:WATER|RIVER)\s?FRONT\b|\bNO\s+WATER\s?FRONT\b|\bNON[- ]WATER\s?FRONT\b")


def load():
    """pid (int) -> {water, kind, frontage_ft}; empty when the file has not been built."""
    global _CACHE
    if _CACHE is None:
        _CACHE = {int(k): v for k, v in json.load(open(OUT))["rows"].items()} if os.path.exists(OUT) else {}
    return _CACHE


def of(r):
    """Waterfront verdict for one parcel row: measured from the map first, then the
    assessor's own remark where the county publishes one. None when neither says so."""
    w = load().get(r["pid"])
    text = f"{r.get('remark1') or ''} {r.get('remark2') or ''} {r.get('legal') or ''}".upper()
    if w:
        return dict(w, source="map")
    if _SAYS.search(text) and not _SAYS_NOT.search(text):
        return {"water": "", "kind": "assessor's note", "frontage_ft": None, "source": "assessor"}
    return None


if __name__ == "__main__":
    run()
