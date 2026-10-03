"""
Nightly pull of the King George County "Parcels" open-data layer.

  python -m engine.parcels                 # pull -> .cache/kg.sqlite + data/parcels.json
  python -m engine.parcels --max-pages 1   # smoke test

The layer is the county's CAMA table joined to parcel polygons: ~15,000 rows,
2,000 per page, 8 requests. Rows with PID 0 are right-of-way / water / "NoData"
polygons with no assessment record; multi-part parcels repeat the same PID. The
index keeps one row per PID > 0.

Outputs
  .cache/kg.sqlite         full index (not committed; rebuilt nightly)
  data/parcels.json        compact, one row per parcel, for the dashboard lookup
  data/parcels-meta.json   counts, source, timestamp
  data/owner-changes.json  owner / deed changes since the previous pull (the
                           snapshot diff that later proves a sale or transfer)
"""
import argparse
import datetime as dt
import json
import logging
import os
import re
import sqlite3
import sys
import time

import requests

from engine import config, owner_parse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("parcels")

ROOT = config.ROOT
DB_PATH = config.DB_PATH
DATA = config.DATA_DIR

INT_COLS = {"pid", "mail_zip", "site_num", "land_value", "impr_value", "total_value", "year_built",
            "dwellings", "deed_book", "deed_page", "sale_price", "sale_month", "sale_day", "sale_year"}
REAL_COLS = {"acres"}
COLS = list(config.FIELDS.values())

# Columns of data/parcels.json, in order.
COMPACT = ["pid", "pin", "owner", "care_of", "owner_type", "mail_addr", "mail_city", "mail_state", "mail_zip",
           "site_addr", "acres", "land_value", "impr_value", "total_value", "year_built", "cond",
           "deed_book", "deed_page", "will_book", "will_page", "sale_year", "sale_price", "note"]


def _s(v):
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def fetch_all(max_pages=None):
    """Page through the layer. Returns (rows, service_count)."""
    sess = requests.Session()
    sess.headers["User-Agent"] = config.USER_AGENT
    r = sess.get(config.PARCELS_URL + "/query",
                 params={"where": "1=1", "returnCountOnly": "true", "f": "json"}, timeout=60)
    r.raise_for_status()
    total = r.json()["count"]
    log.info("Service reports %s rows", f"{total:,}")
    rows, offset, page = [], 0, 0
    while True:
        params = {"where": "1=1", "outFields": config.SOURCE_FIELDS or ",".join(config.FIELDS), "returnGeometry": "false",
                  "orderByFields": "FID", "resultOffset": offset, "resultRecordCount": config.PAGE_SIZE, "f": "json"}
        for attempt in range(4):
            try:
                r = sess.get(config.PARCELS_URL + "/query", params=params, timeout=120)
                r.raise_for_status()
                j = r.json()
                if "error" in j:
                    raise RuntimeError(j["error"])
                break
            except Exception as e:  # noqa: BLE001 - retry any transport / service error
                if attempt == 3:
                    raise
                log.warning("page at offset %s failed (%s); retrying", offset, e)
                time.sleep(5 * (attempt + 1))
        feats = j.get("features", [])
        rows += [f["attributes"] for f in feats]
        offset += len(feats)
        page += 1
        log.info("page %s: %s rows (total %s)", page, len(feats), f"{len(rows):,}")
        if not feats or not j.get("exceededTransferLimit") or (max_pages and page >= max_pages):
            break
        time.sleep(config.REQUEST_PAUSE_S)
    return rows, total


def normalise(attrs):
    if config.ADAPT:
        attrs = config.ADAPT(attrs)
    out = {}
    for src, col in config.FIELDS.items():
        v = attrs.get(src)
        if col in INT_COLS:
            try:
                out[col] = int(v) if v not in (None, "", " ") else 0
            except (TypeError, ValueError):
                out[col] = 0
        elif col in REAL_COLS:
            try:
                out[col] = round(float(v), 3) if v is not None else 0.0
            except (TypeError, ValueError):
                out[col] = 0.0
        elif col == "pin":
            out[col] = (v or "").strip()          # keep the internal spaces: it is the Treasurer's key
        else:
            out[col] = _s(v)
    return out


def dedupe(raw_rows):
    """One row per PID > 0. Returns (parcels, stats)."""
    seen, parcels = set(), []
    non_parcel = 0
    for a in raw_rows:
        r = normalise(a)
        if not r["pid"]:
            non_parcel += 1
            continue
        if r["pid"] in seen:
            continue
        seen.add(r["pid"])
        parcels.append(r)
    parcels.sort(key=lambda r: r["pid"])
    return parcels, {"service_rows": len(raw_rows), "non_parcel_rows": non_parcel,
                     "duplicate_polygons": len(raw_rows) - non_parcel - len(parcels), "parcels": len(parcels)}


def write_sqlite(parcels, path=DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    decl = ", ".join(f"{c} {'INTEGER' if c in INT_COLS else 'REAL' if c in REAL_COLS else 'TEXT'}" for c in COLS)
    con.execute(f"CREATE TABLE parcels ({decl}, owner TEXT, care_of TEXT, owner_type TEXT, owner_subtype TEXT, PRIMARY KEY (pid))")
    con.executemany(
        f"INSERT INTO parcels VALUES ({','.join('?' * (len(COLS) + 4))})",
        [[r[c] for c in COLS] + [r["owner"], r["care_of"], r["owner_type"], r["owner_subtype"]] for r in parcels])
    con.execute("CREATE INDEX ix_pin ON parcels(pin)")
    con.execute("CREATE INDEX ix_owner ON parcels(owner)")
    con.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
    con.execute("INSERT INTO meta VALUES ('built_at', ?)", (dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),))
    con.commit()
    con.close()
    os.replace(tmp, path)


def enrich(parcels):
    for r in parcels:
        r["owner"] = owner_parse.owner_text(r["lnam"], r["fnam"])
        co = owner_parse.care_of(r["fnam"])
        if not co:
            m = re.search(r"\s(?:C/O|%)\s?(.*)$", owner_parse.clean(r["lnam"]))
            co = m.group(1).strip() if m else ""
        r["care_of"] = co
        r["owner_type"], r["owner_subtype"] = owner_parse.classify(r["lnam"], r["fnam"])
        site = r["site_addr"]
        r["site_addr"] = "" if (not site or site.startswith("0 ") or "UNASSIGNED" in site) else site
    return parcels


def compact_row(r):
    row = []
    for c in COMPACT:
        v = r["grantor_note"] if c == "note" else r[c]
        row.append(v)
    return row


def diff_owners(prev_path, parcels, today):
    """Owner or deed reference changed since the last committed snapshot."""
    if not os.path.exists(prev_path):
        return []
    try:
        prev = json.load(open(prev_path))
        cols = prev["columns"]
        idx = {c: i for i, c in enumerate(cols)}
        old = {row[idx["pid"]]: row for row in prev["rows"]}
    except Exception as e:  # noqa: BLE001
        log.warning("previous snapshot unreadable (%s); no diff this run", e)
        return []
    out = []
    for r in parcels:
        o = old.get(r["pid"])
        if not o:
            out.append({"date": today, "pid": r["pid"], "pin": r["pin"], "change": "NEW_PARCEL", "new_owner": r["owner"]})
            continue
        if o[idx["owner"]] != r["owner"] or o[idx["deed_book"]] != r["deed_book"] or o[idx["deed_page"]] != r["deed_page"]:
            out.append({"date": today, "pid": r["pid"], "pin": r["pin"], "site_addr": r["site_addr"],
                        "change": "OWNER" if o[idx["owner"]] != r["owner"] else "DEED_REF",
                        "old_owner": o[idx["owner"]], "new_owner": r["owner"],
                        # where the previous owner's tax bill went: the only place this survives a sale
                        "old_mail": ", ".join(str(o[idx[c]]) for c in ("mail_addr", "mail_city", "mail_state", "mail_zip") if o[idx[c]]),
                        "old_deed": [o[idx["deed_book"]], o[idx["deed_page"]]], "new_deed": [r["deed_book"], r["deed_page"]],
                        "sale_year": r["sale_year"], "sale_price": r["sale_price"], "note": r["grantor_note"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--from-json", help="use a saved raw pull instead of the network (tests)")
    args = ap.parse_args()

    if args.from_json:
        raw = json.load(open(args.from_json))
        total = len(raw)
    else:
        raw, total = fetch_all(args.max_pages)
    if not args.max_pages and len(raw) != total:
        log.error("pulled %s rows but the service reports %s; refusing to overwrite the index", len(raw), total)
        sys.exit(1)

    parcels, stats = dedupe(raw)
    if not args.max_pages and stats["parcels"] < config.MIN_PARCELS:
        log.error("only %s parcels after dedupe; refusing to overwrite the index", stats["parcels"])
        sys.exit(1)
    enrich(parcels)
    write_sqlite(parcels)

    now = dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()
    os.makedirs(DATA, exist_ok=True)
    snap = os.path.join(DATA, "parcels.json")
    changes = diff_owners(snap, parcels, today) if not args.max_pages else []
    if changes:
        cpath = os.path.join(DATA, "owner-changes.json")
        log_ = json.load(open(cpath)) if os.path.exists(cpath) else []
        log_ = (changes + log_)[:5000]
        json.dump(log_, open(cpath, "w"), indent=0, separators=(",", ":"))
    log.info("%s owner/deed changes since the last snapshot", len(changes))

    if not args.max_pages:
        with open(snap, "w") as f:
            f.write('{"columns":' + json.dumps(COMPACT) + ',"rows":[\n')
            f.write(",\n".join(json.dumps(compact_row(r), separators=(",", ":")) for r in parcels))
            f.write("\n]}\n")
        types = {}
        for r in parcels:
            types[r["owner_type"]] = types.get(r["owner_type"], 0) + 1
        meta = dict(stats, generated_at=now.isoformat(timespec="seconds"), source=config.PARCELS_URL,
                    county=config.COUNTY, state=config.STATE, owner_types=types, changes_this_run=len(changes))
        json.dump(meta, open(os.path.join(DATA, "parcels-meta.json"), "w"), indent=1)
    log.info("index: %s", stats)


if __name__ == "__main__":
    main()
