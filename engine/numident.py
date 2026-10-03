"""
Deaths 1988-2007 from the Social Security NUMIDENT death files at the National Archives.

  python -m engine.numident                 # King George ZIP codes (about 2,000 records)
  python -m engine.numident --neighbors     # also Colonial Beach and the Fredericksburg ZIPs

NARA publishes the NUMIDENT (Record Group 47, National Archives Identifier 12004494) as
a public-use, public-domain series and lets anyone search it in Access to Archival
Databases (AAD) by residence ZIP code and export the result as CSV. There is no login,
no robots.txt and no clause on automated use; archives.gov asks crawlers for a
10-second delay, which is what this uses. This is a one-time pull: the series ends in
2007 and does not change.

What the file is, and is not:
  - one row per death SSA verified; first / middle / last name, dates of birth and
    death, and the ZIP code of the person's residence on SSA's records;
  - the residence ZIP is essentially empty before 1988, so coverage here is 1988-2007;
  - NARA says 10-30% of deaths (those reported only by a state) are not in the public
    file, and about a quarter of records have no ZIP. Absence proves nothing.

Social Security numbers are in NARA's export. They are dropped on read and never
written anywhere.

Output: data/obits/numident.json, in the same shape as the obituary files, so the
death matcher scores each one against every owner on title.
"""
import argparse
import csv
import datetime as dt
import html
import io
import json
import logging
import os
import re
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("numident")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "obits", "numident.json")
AAD = "https://aad.archives.gov/aad/"
# AAD refuses clients with no browser-style prefix; this is the standard self-identifying form.
UA = "Mozilla/5.0 (compatible; va-property-leads/1.0; +https://github.com/friendsenemy/va-property-leads)"
PAUSE_S = 10
DEATH_FILES = range(3400, 3409)          # nine files, split by surname initial (A-B ... U-Z)
SOURCE = "Social Security NUMIDENT death file (National Archives)"

KG_ZIPS = {"22485": "King George", "22448": "Dahlgren", "22451": "Dogue", "22481": "Jersey",
           "22526": "Ninde", "22544": "Rollins Fork", "22547": "Sealston"}
NEIGHBOR_ZIPS = {"22443": "Colonial Beach", "22401": "Fredericksburg", "22405": "Fredericksburg",
                 "22406": "Fredericksburg", "22407": "Fredericksburg", "22408": "Fredericksburg"}


class Aad:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.last = 0.0

    def get(self, path, **kw):
        wait = PAUSE_S - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(4):
            try:
                r = self.s.get(AAD + path, timeout=120, **kw)
                self.last = time.time()
                if r.status_code == 200:
                    return r
                log.warning("%s -> HTTP %s", path[:60], r.status_code)
            except requests.RequestException as e:
                log.warning("%s -> %s", path[:60], e)
            time.sleep(30 * (attempt + 1))
        raise RuntimeError("AAD not reachable")

    def form(self, file_id):
        """The search form of one death file: its hidden fields and the id of the ZIP field."""
        t = self.get(f"fielded-search.jsp?dt={file_id}&tf=F&cat=GP22&bc=,sl").text
        hidden = dict(re.findall(r'<input type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', t))
        zip_id = None
        for fid in sorted(set(re.findall(r"nfo_(\d+)", t))):
            j = t.find(f'name="nfo_{fid}"')
            before = t[max(0, j - 400):j]
            before = before[:before.rfind("<")]                  # drop the opening of the <input> tag itself
            label = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", before)))
            if label.rstrip().endswith("RESIDENCE ZIP CODE"):
                zip_id = fid
        if not zip_id or "sc" not in hidden:
            raise RuntimeError(f"file {file_id}: search form not understood; the site has changed")
        return hidden, zip_id

    def search(self, file_id, hidden, zip_id, zips):
        """Run a residence-ZIP search. Returns (query string, match count, download id)."""
        q = (f"dt={file_id}&sc={hidden['sc']}&cat=GP22&tf=F&bc=,sl,fd&nfo_{zip_id}={hidden['nfo_' + zip_id]}"
             f"&op_{zip_id}=1&txt_{zip_id}=" + "+".join(z + "*" for z in zips))
        for _ in range(12):
            t = self.get("display-partial-records.jsp?" + q).text
            if "Please Wait" not in t:
                break
        else:
            raise RuntimeError("search did not finish")
        m, d = re.search(r"mtch=(\d+)", t), re.search(r"[?&]dl=(\d+)", t)
        if not m:
            return q, 0, None                       # no records for these ZIPs in this file
        return q, int(m.group(1)), d.group(1) if d else None

    def download(self, q, count, dl):
        self.get(f"popup-download.jsp?{q}&mtch={count}&dl={dl}")
        return self.get(f"download-results?ft=R&{q}&mtch={count}&dl={dl}").text


def to_records(csv_text, places):
    out = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        last, first = row.get("LAST NAME", ""), row.get("FIRST NAME", "")
        if not last or not first or set(last) <= {"Z"}:      # Z-filled rows are masked by NARA
            continue
        try:
            dy, dm, dd = int(row["DATE OF DEATH (YEAR)"]), int(row["DATE OF DEATH (MONTH)"] or 0), int(row["DATE OF DEATH (DAY)"] or 0)
        except (KeyError, ValueError):
            continue
        death = f"{dy:04d}-{dm or 1:02d}-{dd or 1:02d}"
        birth, age = "", None
        try:
            by, bm, bd = int(row["DATE OF BIRTH (YEAR)"]), int(row["DATE OF BIRTH (MONTH)"] or 0), int(row["DATE OF BIRTH (DAY)"] or 0)
            birth = f"{by:04d}-{bm or 1:02d}-{bd or 1:02d}"
            age = dy - by - ((dm, dd) < (bm, bd))
        except (KeyError, ValueError):
            pass
        z = row.get("RESIDENCE ZIP CODE", "")[:5]
        # NOTE: the SSN and "other number" columns are deliberately not read.
        out.append({"id": re.sub(r"\W", "", f"{last}{first}{row.get('MIDDLE NAME', '')[:1]}{death}{birth}"),
                    "first": first.upper(), "middle": row.get("MIDDLE NAME", "").upper(), "last": last.upper(),
                    "suffix": row.get("SUFFIX NAME", "").upper().strip("."), "death_date": death, "birth_date": birth,
                    "age": age if age is not None and 0 <= age < 120 else None,
                    "place": places.get(z, ""), "zip": z, "url": "https://aad.archives.gov/aad/series-description.jsp?s=5057&cat=GP22",
                    "source": SOURCE})
    return out


WESTMORELAND_ZIPS = {"22443": "Colonial Beach", "22469": "Hague", "22488": "Kinsale", "22520": "Montross", "22529": "Oldhams",
                     "22558": "Stratford", "22577": "Sandy Point", "22581": "Zacata", "22442": "Coles Point", "22524": "Mount Holly"}


def run(neighbors=False, county="king-george"):
    global KG_ZIPS, OUT
    if county == "westmoreland":                 # same pull, Westmoreland's ZIP codes, its own file in the shared folder
        KG_ZIPS, OUT = WESTMORELAND_ZIPS, os.path.join(ROOT, "data", "obits", "numident-westmoreland.json")
    places = dict(KG_ZIPS, **(NEIGHBOR_ZIPS if neighbors else {}))
    aad, recs = Aad(), {}
    if os.path.exists(OUT):
        recs = {r["id"]: r for r in json.load(open(OUT))["rows"]}
    for file_id in DEATH_FILES:
        hidden, zip_id = aad.form(file_id)
        groups = [list(KG_ZIPS)] + ([[z] for z in NEIGHBOR_ZIPS] if neighbors else [])
        while groups:
            zips = groups.pop(0)
            q, count, dl = aad.search(file_id, hidden, zip_id, zips)
            if count > 1000 and len(zips) > 1:
                groups = [[z] for z in zips] + groups          # over the export cap: one ZIP at a time
                continue
            if count > 1000:
                log.warning("file %s ZIP %s has %s records, over the 1,000 export cap; skipped", file_id, zips, count)
                continue
            if not count or not dl:
                continue
            rows = to_records(aad.download(q, count, dl), places)
            for r in rows:
                recs[r["id"]] = r
            log.info("file %s %s: %s matches, %s usable (%s on file)", file_id, "+".join(zips), count, len(rows), len(recs))
    rows = sorted(recs.values(), key=lambda r: (r["death_date"], r["last"], r["first"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(json.dumps({"source": SOURCE, "pulled": dt.date.today().isoformat(), "count": len(rows),
                            "note": "Public-use federal record. SSNs are not stored."})[:-1] + ',"rows":[\n')
        f.write(",\n".join(json.dumps(r, separators=(",", ":")) for r in rows))
        f.write("\n]}\n")
    log.info("%s NUMIDENT deaths on file", len(rows))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--neighbors", action="store_true")
    ap.add_argument("--county", default="king-george", choices=["king-george", "westmoreland"])
    a = ap.parse_args()
    run(a.neighbors, a.county)
