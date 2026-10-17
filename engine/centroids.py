"""
One map point per parcel, for the aerial-imagery panel on every lead card.

  python -m engine.centroids                       (King George)
  VAPL_COUNTY=fauquier python -m engine.centroids  (any county the engine knows)

Reads the same county parcel layer as engine.waterfront (outlines, WGS84), takes a
point guaranteed to sit inside each lot (shapely's representative point, not the
centroid, which can fall outside an L-shaped or curved lot), and writes
data/<county>/centroids.json as {pid: [lat, lon]}. Lot lines rarely move, so this
runs weekly; the dashboard falls back to a free address lookup for anything missing.
"""
import json
import logging
import os

from engine import config, waterfront

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("centroids")

OUT = os.path.join(config.DATA_DIR, "centroids.json")


def run():
    outlines = waterfront.parcel_outlines(lambda x, y: (x, y))      # keep degrees: no projection needed for a point
    pts = {}
    for pid, g in outlines.items():
        if g.is_empty:
            continue
        p = g.representative_point()
        pts[str(pid)] = [round(p.y, 6), round(p.x, 6)]
    if len(pts) < 100:
        raise SystemExit(f"only {len(pts)} parcel points; refusing to overwrite {OUT}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(pts, open(OUT, "w"), separators=(",", ":"), sort_keys=True)
    log.info("%s parcel points -> %s", len(pts), OUT)
    return len(pts)


if __name__ == "__main__":
    run()
