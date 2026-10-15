"""
Distress signals: public agency records about a property (fire, vacancy, code
enforcement, demolition, blight, receivership), matched to the parcel and stacked on top
of whatever the parcel already carries (deceased owner, unpaid taxes, title defect).

  python -m engine.distress                 # daily: recent windows on every source, then match
  python -m engine.distress --full          # Sunday: walk every month back to 2020 (status changes on old cases)
  python -m engine.distress --match-only    # no network: re-match what is on disk

One property, many sources, no duplicates. Nothing here makes a new list of violations:
every signal is attached to an existing parcel by parcel id (when the portal gives one)
or by normalised street address inside the county, and the boards read it from there.

Sources are vendor-generic collectors driven by SITES below (filled from
docs/sources-and-terms.md, "Distress signals"): Tyler EnerGov Civic Access
(api/energov/search/search, the portal's own public search request, replayed exactly),
Accela Citizen Access (the public enforcement search form, posted as the browser posts
it), ArcGIS layers, and hand-entered rows in data/distress/manual.csv for sources that
only exist as a web page or a board agenda. Public lists only: no logins, no CAPTCHAs,
no tabs marked "must be a contact on this record". A restricted field is recorded as
restricted and asked for by FOIA (docs/foia-requests.md).

Points (additive to the existing score, open cases only; see config.DISTRESS_POINTS):
  FIRE 45, VACANT_NOTICE / DERELICT_STRUCTURE 40, RECEIVERSHIP / SPOT_BLIGHT 40,
  CODE_VIOLATIONS 25, DEMO_PERMIT 25, NUISANCE_CASE 20, REPEAT_CODE_CASES 20,
  ZONING_CASE 10, STACKED_SIGNALS 10.
A fire younger than 30 days is "cooling": shown, but flagged so nobody calls that week.
An old record never means the property is vacant or damaged today; the UI says so.

Output
  data/distress/signals.json       {"generated_at", "counts", "by_parcel": {"<county>:<pid>": [signal...]},
                                    "unmatched": [...], "ambiguous": [...]}
  data/distress/<portal>.json      every case the portal's public list showed, with first/last seen
                                   and a status history (so Escalated after In Progress is visible)
"""
import argparse
import csv
import datetime as dt
import hashlib
import html as htmlmod
import json
import logging
import os
import re
import sqlite3
import time

import requests

from engine import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("distress")

OUT = os.path.join(config.ROOT, "data", "distress")
SIGNALS = os.path.join(OUT, "signals.json")
MANUAL = os.path.join(OUT, "manual.csv")
UA = "Mozilla/5.0 (compatible; va-property-leads/1.0; +https://github.com/friendsenemy/va-property-leads)"
SLEEP = 1.0
PAGE = 100
HISTORY_START = dt.date(2020, 1, 1)
RECENT_DAYS = 60
COOLING_DAYS = 30
MAX_TIES = 3                        # an address shared by more parcels than this (condo, apartments) is ambiguous
MAX_PER_PARCEL = 12
REPEAT_MIN = 3                      # cases at one parcel since 2020 that make REPEAT_CODE_CASES

COUNTY_DBS = {"King George": os.path.join(config.ROOT, ".cache", "kg.sqlite"),
              "Westmoreland": os.path.join(config.ROOT, ".cache", "westmoreland.sqlite"),
              "Fauquier": os.path.join(config.ROOT, ".cache", "fauquier.sqlite")}

# ---- what each source is (verified 2026-10-14; docs/sources-and-terms.md, "Distress signals").
# kind: energov_permits | accela | arcgis | active911 | agendas
SITES = {
    "fauquier-demolition": {
        "kind": "energov_permits", "county": "Fauquier", "source": "Fauquier County Civic Access: demolition permits",
        "api": "https://commdevpay.fauquiercounty.gov/energov_prod/selfservice/api", "template": "fauquier_search_template.json",
        "headers": {"tenantId": "1", "tenantName": "FauquierCountyVAProd", "Tyler-TenantUrl": "FauquierCountyVAProd"},
        "case_url": "https://commdevpay.fauquiercounty.gov/Energov_Prod/SelfService#/permit/{id}",
        # the four demolition permit types the portal lists (Residential Building, Residential Accessory, Commercial, Accessory C)
        "type_ids": ["3962f3cb-4559-42ae-b010-4803733fda8b_853da3fe-20f1-4335-b929-8efd4df2f193", "ad49c7e3-f579-4326-a51f-63d056d67058_853da3fe-20f1-4335-b929-8efd4df2f193",
                     "85f386a8-931c-47ef-b52d-74405d7698fe_853da3fe-20f1-4335-b929-8efd4df2f193", "f59a8ac2-29e2-41a4-b65d-b425674ec903_853da3fe-20f1-4335-b929-8efd4df2f193"],
        "signal_kind": "DEMO_PERMIT",
    },
    "king-george-fire-calls": {
        "kind": "active911", "county": "King George", "source": "King George Fire and Rescue: live CAD calls (county site)",
        "url": "https://access.active911.com/interface/js.php?r3vd471", "page": "https://www.kinggeorgecountyva.gov/774/Active-CAD-Calls",
    },
    "king-george-fire-2022": {
        "kind": "arcgis", "county": "King George", "source": "King George Fire & Rescue incidents 2022-23 (county GIS)",
        "url": "https://services2.arcgis.com/S8zMJrpz61FbvL5t/ArcGIS/rest/services/FireRescueIncidents2022/FeatureServer/0",
        "where": "USER_Natur IN ('STRUCFIREF','NSTRUCFIRE','APARTFIRF','BUILDFIRF','FIREEND')", "date_filter": False,
        "fields": {"case_number": "USER_Incid", "type": "USER_Natur", "status": "USER_Disp", "opened": "USER_DateT", "address": "USER_Addre"},
        "signal_kind": "FIRE", "static": True,
    },
    "westmoreland-agendas": {
        "kind": "agendas", "county": "Westmoreland", "source": "Westmoreland Board of Supervisors agendas and minutes (CivicClerk)",
        "list": "civicclerk", "tenant": "westmorelandcova",
    },
    "king-george-agendas": {
        "kind": "agendas", "county": "King George", "source": "King George Board of Supervisors agendas and minutes (AgendaCenter)",
        "list": "agendacenter", "base": "https://www.kinggeorgecountyva.gov",
    },
    "colonial-beach-agendas": {
        "kind": "agendas", "county": "Westmoreland", "source": "Town of Colonial Beach council agendas and minutes (AgendaCenter)",
        "list": "agendacenter", "base": "https://www.colonialbeachva.gov",
    },
}
AGENDA_WORDS = re.compile(r"derelict|spot blight|blighted|blight abatement|unsafe (?:structure|building)|condemn(?:ed|ation)|demolition order|order(?:ed)? (?:the )?demoli|"
                          r"demolish|unfit for (?:human )?habitation|nuisance abatement|15\.2-906|15\.2-907|36-49\.1", re.I)
AGENDA_NOISE = re.compile(r"prayer|invocation|scripture|psalm|zoning ordinance text|text amendment", re.I)
TAXMAP_RE = re.compile(r"(?:tax map|TM|parcel|GPIN|PIN)\s*(?:no\.?|#|number)?:?\s*([0-9]{1,3}[A-Z]?(?:[- ][0-9A-Z]{1,4}){1,5}|[0-9]{4}-[0-9]{2}-[0-9]{4}(?:-[0-9]{3})?)", re.I)
STREET_RE = re.compile(r"\b(\d{2,6})\s+((?:[A-Z][A-Za-z'.-]*\s+){1,4}(?:Road|Rd|Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Court|Ct|Lane|Ln|Way|Place|Pl|Terrace|Ter|Circle|Cir|Highway|Hwy|Trail|Trl|Loop|Point|Pt|Landing))\b")
FIRE_WORDS = re.compile(r"structure fire|house fire|dwelling fire|building fire|residential fire|fire -? ?(?:single|multi|residential|structure|dwelling|house|building)|working fire|chimney fire", re.I)
NOT_FIRE = re.compile(r"alarm|vehicle|brush|woods|grass|dumpster|trash|odor|smoke investigation|outside|illegal burn|controlled burn|ems|medical|accident|mva", re.I)

OPEN_WORDS = re.compile(r"open|progress|escalat|hold|pending|new|re-?open|active|cited|citation|notice|hearing|court|abat", re.I)
CLOSED_WORDS = re.compile(r"closed|complete|resolved|abated|void|cancel|dismiss|no violation|unfounded|duplicate|withdrawn|compliance|complied|expired|final", re.I)
CONFIRMED_WORDS = re.compile(r"escalat|citation|cited|correction notice|notice of violation|nov\b|in violation|hearing|court|summons|abatement order", re.I)
NUISANCE_RE = re.compile(r"grass|weed|trash|debris|junk|rubbish|litter|vehicle|rat|rodent|nuisance|overgrown|dumping|tall grass|inoperable", re.I)
VACANT_RE = re.compile(r"vacant|abandon|derelict|boarded|unsecured|open to the elements", re.I)
STRUCTURE_RE = re.compile(r"unsafe|condemn|collaps|structur|roof|fire|dilapidat|demoli|uninhabit|no (?:water|power|heat)|squat|building|property maintenance|housing|maintenance code|usbc|vmc|rental", re.I)
DEMO_RE = re.compile(r"demol|raze|tear ?down", re.I)
ZONING_RE = re.compile(r"zoning|land use|setback|sign", re.I)


def norm_date(s):
    """'02/09/23  15:02' | '2026-10-01T..' | '10/1/2026' -> 'YYYY-MM-DD' or None."""
    s = (s or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if m:
        y = int(m.group(3))
        y = y + 2000 if y < 100 else y
        return f"{y:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def is_open(status):
    s = status or ""
    if CLOSED_WORDS.search(s):
        return False
    return bool(OPEN_WORDS.search(s)) or not s


def kind_of(ctype, text):
    t = f"{ctype} {text}"
    if DEMO_RE.search(ctype or ""):
        return "DEMO_PERMIT"
    if VACANT_RE.search(t):
        return "VACANT_NOTICE"
    if ZONING_RE.search(ctype or "") and not STRUCTURE_RE.search(t):
        return "ZONING_CASE"
    if STRUCTURE_RE.search(t):
        return "CODE_VIOLATIONS"
    if NUISANCE_RE.search(t):
        return "NUISANCE_CASE"
    return "CODE_VIOLATIONS" if re.search(r"code|violation|enforce|inspect", ctype or "", re.I) else "NUISANCE_CASE"


# ---------------------------------------------------------------- collectors

def windows(full, today=None):
    today = today or dt.date.today()
    if not full:
        return [(today - dt.timedelta(days=RECENT_DAYS), today)]
    out, cur = [], HISTORY_START
    while cur <= today:
        nxt = dt.date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        out.append((cur, min(nxt - dt.timedelta(days=1), today)))
        cur = nxt
    return out


def portal_path(key):
    return os.path.join(OUT, f"{key}.json")


def load_portal(key):
    p = portal_path(key)
    return json.load(open(p)) if os.path.exists(p) else {"cases": {}}


def save_portal(key, data):
    os.makedirs(OUT, exist_ok=True)
    json.dump(data, open(portal_path(key), "w"), separators=(",", ":"), ensure_ascii=False)


def merge_cases(data, key, recs, failed):
    """Keep every case ever seen; record status changes; never re-download what is unchanged."""
    now = now_iso()
    cases = data.setdefault("cases", {})
    new = changed = 0
    for rec in recs:
        if not rec.get("case_number"):
            continue
        k = f"{key}:{rec['case_number']}"
        old = cases.get(k)
        if old is None:
            rec["first_seen"] = now
            rec["status_history"] = [{"status": rec.get("status", ""), "seen": now}]
            cases[k] = rec
            new += 1
        else:
            if old.get("status") != rec.get("status"):
                old.setdefault("status_history", []).append({"status": rec.get("status", ""), "seen": now})
                changed += 1
            for f, v in rec.items():
                if v not in (None, ""):
                    old[f] = v
        cases[k]["last_seen"] = now
    mine = [c for c in cases.values()]
    data["meta"] = {"last_run": now, "failed": failed, "seen": len(recs), "new": new, "status_changed": changed,
                    "kept": len(mine), "open": sum(1 for c in mine if is_open(c.get("status")))}
    data["generated_at"] = now
    return data


def energov_search(site, frm, to):
    """Replay the Civic Access public search exactly as the page sends it (site['template'])."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json", **site.get("headers", {})})
    base = json.load(open(os.path.join(config.ROOT, "engine", site["template"])))
    out, page = [], 1
    while True:
        m = json.loads(json.dumps(base))
        m.update({"PageNumber": page, "PageSize": PAGE})
        m["CodeCaseCriteria"].update({"PageNumber": page, "PageSize": PAGE,
                                      "OpenedDateFrom": f"{frm.isoformat()}T05:00:00.000Z", "OpenedDateTo": f"{to.isoformat()}T05:00:00.000Z"})
        r = s.post(site["api"] + "/energov/search/search", data=json.dumps(m), timeout=90)
        r.raise_for_status()
        j = r.json()
        if not j.get("Success"):
            raise RuntimeError(j.get("ErrorMessage") or "search failed")
        res = j["Result"]
        items = res.get("EntityResults") or []
        for e in items:
            a = e.get("Address") or {}
            out.append({"case_number": e.get("CaseNumber"), "case_id": e.get("CaseId"), "type": e.get("CaseType") or "",
                        "status": e.get("CaseStatus") or "", "opened": (e.get("ApplyDate") or "")[:10] or None,
                        "closed": (e.get("CompleteDate") or e.get("FinalDate") or "")[:10] or None,
                        "address": (e.get("AddressDisplay") or a.get("FullAddress") or "").strip(),
                        "street": " ".join(x for x in (a.get("AddressLine1"), a.get("PreDirection"), a.get("AddressLine2"), a.get("StreetTypeName"), a.get("PostDirection")) if x).strip(),
                        "unit": a.get("UnitOrSuite") or "", "city": a.get("City") or "", "zip": (a.get("PostalCode") or "")[:5],
                        "parcel": (e.get("MainParcel") or "").strip(), "description": (e.get("ProjectName") or e.get("Description") or "")[:300],
                        "url": site["case_url"].format(id=e.get("CaseId")), "county": site["county"], "source": site["source"]})
        total = res.get("TotalPages") or 1
        if page >= total or not items:
            break
        page += 1
        time.sleep(SLEEP)
    return out


def _form(h):
    form = {}
    for m in re.finditer(r"<input([^>]*)>", h):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        if a.get("name") and a.get("type") in ("hidden", "text", "tel"):
            form[a["name"]] = htmlmod.unescape(a.get("value", ""))
    for m in re.finditer(r'<select name="([^"]+)"[^>]*>(.*?)</select>', h, re.S):
        sel = re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', m.group(2)) or re.search(r'<option[^>]*value="([^"]*)"', m.group(2))
        form[m.group(1)] = sel.group(1) if sel else ""
    return form


def _clean(c):
    return htmlmod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()


def accela_search(site, frm, to):
    """Post the public 'Search Enforcement Records' form as the browser does; walk the pager."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": site["home"]})
    h = s.get(site["home"], timeout=60).text
    form = _form(h)
    form["ctl00$PlaceHolderMain$generalSearchForm$txtGSStartDate"] = frm.strftime("%m/%d/%Y")
    form["ctl00$PlaceHolderMain$generalSearchForm$txtGSEndDate"] = to.strftime("%m/%d/%Y")
    target, out, pages = "ctl00$PlaceHolderMain$btnNewSearch", [], 0
    while True:
        form.update({"__EVENTTARGET": target, "__EVENTARGUMENT": ""})
        r = s.post(site["home"], data=form, timeout=120)
        r.raise_for_status()
        t = r.text
        hdr = re.findall(r'<tr class="ACA_TabRow_Header[^"]*".*?</tr>', t, re.S)
        cols = [_clean(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", hdr[0], re.S)] if hdr else []
        for row in re.findall(r'<tr class="ACA_TabRow_(?:Odd|Even)[^"]*".*?</tr>', t, re.S):
            rec = dict(zip(cols, [_clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]))
            m = re.search(r'href="([^"]*CapDetail\.aspx[^"]*)"', row)
            addr = rec.get("Address") or ""
            dm = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", rec.get("Date") or "")
            zm = re.search(r"\b(\d{5})(?:-\d{4})?\s*$", addr)
            out.append({"case_number": rec.get("Record Number") or rec.get("Case Number") or "", "type": rec.get("Record Type") or rec.get("Case Type") or "",
                        "status": rec.get("Status") or "", "opened": f"{dm.group(3)}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}" if dm else None,
                        "address": addr, "street": addr.split(",")[0].strip(), "zip": zm.group(1) if zm else "", "parcel": rec.get("Parcel") or "",
                        "description": (rec.get("Description") or "")[:300],
                        "url": (re.match(r"https://[^/]+", site["home"]).group(0) + htmlmod.unescape(m.group(1))) if m and m.group(1).startswith("/") else site["home"],
                        "county": site["county"], "source": site["source"]})
        nm = re.search(r"__doPostBack\(&#39;([^&]*)&#39;,&#39;&#39;\)\">Next &gt;", t)
        pages += 1
        if not nm or pages >= 400:
            break
        form, target = _form(t), nm.group(1)
        time.sleep(SLEEP)
    return out


def arcgis_rows(site, frm, to):
    """A public feature layer of cases/incidents: one request per window, fields mapped by site['fields']."""
    f = site["fields"]
    where = site.get("where", "1=1")
    if f.get("opened") and site.get("date_filter", True):
        where += f" AND {f['opened']} >= TIMESTAMP '{frm.isoformat()} 00:00:00' AND {f['opened']} <= TIMESTAMP '{to.isoformat()} 23:59:59'"
    out, offset = [], 0
    while True:
        r = requests.get(site["url"] + "/query", params={"where": where, "outFields": "*", "returnGeometry": "false", "resultOffset": offset,
                                                        "resultRecordCount": 1000, "f": "json"}, headers={"User-Agent": UA}, timeout=120)
        r.raise_for_status()
        j = r.json()
        feats = j.get("features", [])
        for x in feats:
            a = x["attributes"]
            def g(k):
                v = a.get(f.get(k, ""), "")
                return "" if v is None else v
            def d(k):
                v = g(k)
                if isinstance(v, (int, float)) and v > 10 ** 11:
                    return dt.datetime.fromtimestamp(v / 1000, dt.timezone.utc).date().isoformat()
                return norm_date(str(v)) if v else None
            out.append({"case_number": str(g("case_number") or a.get("OBJECTID")), "type": str(g("type")), "status": str(g("status")),
                        "opened": d("opened"), "closed": d("closed"), "address": str(g("address")).strip(), "street": str(g("address")).split(",")[0].strip(),
                        "zip": str(g("zip"))[:5], "parcel": str(g("parcel")).strip(), "description": str(g("description"))[:300],
                        "url": site.get("page", site["url"]), "county": site["county"], "source": site["source"]})
        offset += len(feats)
        if not feats or not j.get("exceededTransferLimit"):
            break
        time.sleep(SLEEP)
    return out


def energov_permits(site, frm, to):
    """Civic Access permit search (the portal's own request shape, captured), one type at a time."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json", **site.get("headers", {})})
    base = json.load(open(os.path.join(config.ROOT, "engine", site["template"])))
    out = []
    for tid in site["type_ids"]:
        page = 1
        while True:
            m = json.loads(json.dumps(base))
            m.update({"PageNumber": page, "PageSize": PAGE})
            m["PermitCriteria"].update({"PageNumber": page, "PageSize": PAGE, "PermitTypeId": tid,
                                        "ApplyDateFrom": f"{frm.isoformat()}T00:00:00", "ApplyDateTo": f"{to.isoformat()}T23:59:59"})
            r = s.post(site["api"] + "/energov/search/search", data=json.dumps(m), timeout=90)
            r.raise_for_status()
            j = r.json()
            if not j.get("Success"):
                raise RuntimeError(j.get("ErrorMessage") or "search failed")
            res = j["Result"]
            for e in res.get("EntityResults") or []:
                a = e.get("Address") or {}
                out.append({"case_number": e.get("CaseNumber"), "type": e.get("CaseType") or "", "status": e.get("CaseStatus") or "",
                            "opened": (e.get("ApplyDate") or "")[:10] or None, "closed": (e.get("CompleteDate") or e.get("FinalDate") or "")[:10] or None,
                            "issued": (e.get("IssueDate") or "")[:10] or None,
                            "address": (e.get("AddressDisplay") or a.get("FullAddress") or "").strip(), "street": (a.get("AddressLine1") or "").strip(),
                            "city": a.get("City") or "", "zip": (a.get("PostalCode") or "")[:5], "parcel": (e.get("MainParcel") or "").strip(),
                            "description": (e.get("Description") or e.get("ProjectName") or "")[:300], "url": site["case_url"].format(id=e.get("CaseId")),
                            "county": site["county"], "source": site["source"], "kind": site["signal_kind"]})
            if page >= (res.get("TotalPages") or 1) or not res.get("EntityResults"):
                break
            page += 1
            time.sleep(SLEEP)
        time.sleep(SLEEP)
    return out


def active911_rows(site, frm, to):
    """The county's live CAD feed: the last few alarms. Polled daily; every structure fire ever seen is kept."""
    t = requests.get(site["url"], headers={"User-Agent": UA}, timeout=60).text
    i = t.index("a91.data=")
    d, _ = json.JSONDecoder().raw_decode(t[i + 9:])
    out = []
    for a in d.get("alarms", []):
        desc = a.get("description") or ""
        if a.get("generic_title") != "Fire" or not FIRE_WORDS.search(desc) or NOT_FIRE.search(desc) or not a.get("address"):
            continue
        when = dt.datetime.fromtimestamp(a["stamp"], dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=-4)))
        out.append({"case_number": f"CAD-{a['id']}", "type": desc, "status": "dispatched", "opened": when.date().isoformat(), "closed": None,
                    "address": f"{a['address']}, {a.get('city') or ''}".strip(", "), "street": a["address"], "city": a.get("city") or "", "zip": "",
                    "parcel": "", "description": f"{desc} · dispatched {when.strftime('%Y-%m-%d %H:%M')}", "url": site["page"],
                    "county": site["county"], "source": site["source"], "kind": "FIRE"})
    return out


def _pdf_text(b):
    from pypdf import PdfReader
    import io
    try:
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(b)).pages)
    except Exception:  # noqa: BLE001
        return ""


def agenda_files(site, frm, to):
    """-> [(file id, meeting date ISO, title, url)] for the window."""
    H = {"User-Agent": UA}
    out = []
    if site["list"] == "civicclerk":
        j = requests.get(f"https://{site['tenant']}.api.civicclerk.com/v1/Events", headers=H, timeout=60,
                         params={"$filter": f"startDateTime ge {frm.isoformat()}T00:00:00Z and startDateTime le {to.isoformat()}T23:59:59Z",
                                 "$orderby": "startDateTime desc", "$top": 200}).json()
        for e in j.get("value", []):
            if "Supervisors" not in (e.get("categoryName") or ""):
                continue
            for f in e.get("publishedFiles") or []:
                out.append((f"cc-{f['fileId']}", e["startDateTime"][:10], f"{e['eventName']}: {f.get('name') or f.get('type')}",
                            f"https://{site['tenant']}.api.civicclerk.com/v1/Meetings/GetMeetingFileStream(fileId={f['fileId']},plainText=false)"))
    else:
        seen = set()
        for word in ("derelict", "blight", "unsafe structure", "condemned", "demolition"):
            t = requests.get(site["base"] + "/AgendaCenter/Search/", headers=H, timeout=60,
                             params={"term": word, "CIDs": "all", "startDate": frm.strftime("%m/%d/%Y"), "endDate": to.strftime("%m/%d/%Y"), "dateRange": "", "dateSelector": ""}).text
            for path in re.findall(r'href="(/AgendaCenter/ViewFile/(?:Agenda|Minutes)/_(\d{8})-\d+)"', t):
                if path[0] in seen:
                    continue
                seen.add(path[0])
                d8 = path[1]
                out.append((path[0].rsplit("/", 1)[-1] + ("-A" if "/Agenda/" in path[0] else "-M"), f"{d8[4:]}-{d8[:2]}-{d8[2:4]}",
                            ("Agenda " if "/Agenda/" in path[0] else "Minutes ") + d8, site["base"] + path[0]))
            time.sleep(SLEEP)
    return out


def agenda_rows(site, frm, to, cache):
    """Board agendas and minutes read for derelict / blight / unsafe-structure / demolition actions.
    A hit is a paragraph with one of those phrases AND a street address or tax-map number; each
    becomes a DERELICT_STRUCTURE (or SPOT_BLIGHT) candidate. Files already read are not fetched again."""
    out = []
    for fid, when, title, url in agenda_files(site, frm, to):
        key = f"{site['county']}|{fid}"
        if key in cache:
            text = cache[key]
        else:
            try:
                b = requests.get(url, headers={"User-Agent": UA}, timeout=120).content
                text = _pdf_text(b) if b[:4] == b"%PDF" else ""
            except requests.RequestException:
                text = ""
            cache[key] = text
            time.sleep(SLEEP)
        if not text:
            continue
        for para in re.split(r"\n\s*\n|(?<=\.)\s*\n", text):
            p = re.sub(r"\s+", " ", para).strip()
            if len(p) < 30 or not AGENDA_WORDS.search(p) or AGENDA_NOISE.search(p):
                continue
            kind = "SPOT_BLIGHT" if re.search(r"spot blight|36-49", p, re.I) else "DERELICT_STRUCTURE"
            addrs = [f"{n} {s}" for n, s in STREET_RE.findall(p)]
            maps = [m for m in TAXMAP_RE.findall(p)]
            for ref, is_map in [(a, False) for a in addrs] + [(m, True) for m in maps]:
                out.append({"case_number": hashlib.sha1(f"{fid}|{ref}".encode()).hexdigest()[:10], "type": "Board action: " + kind.replace("_", " ").title(),
                            "status": "on the agenda", "opened": when, "closed": None, "address": "" if is_map else ref, "street": "" if is_map else ref,
                            "zip": "", "parcel": ref if is_map else "", "description": p[:300], "url": url, "county": site["county"],
                            "source": f"{site['source']}: {title}", "kind": kind, "agenda": True})
    return out


COLLECT = {"energov": energov_search, "accela": accela_search, "arcgis": arcgis_rows, "energov_permits": energov_permits, "active911": active911_rows}


AGENDA_CACHE = os.path.join(config.ROOT, ".cache", "agenda-text.json")


def collect(full=False, only=None):
    status = {}
    cache = json.load(open(AGENDA_CACHE)) if os.path.exists(AGENDA_CACHE) else {}
    for key, site in SITES.items():
        if only and key not in only:
            continue
        data, recs, failed = load_portal(key), [], False
        if site.get("static") and data.get("cases"):
            status[key] = data.get("meta", {})
            continue                                    # a fixed historical layer: read once
        wins = windows(full)
        if site["kind"] == "active911":
            wins = wins[-1:]                            # the feed only ever shows the last few calls
        if site["kind"] == "energov_permits" and full:
            # a demolition type has well under 100 permits a year, so yearly windows (paged) are enough
            wins = [(dt.date(y, 1, 1), min(dt.date(y, 12, 31), dt.date.today())) for y in range(HISTORY_START.year, dt.date.today().year + 1)]
        if site["kind"] == "agendas":
            wins = [(wins[0][0] if full else dt.date.today() - dt.timedelta(days=548), dt.date.today())]
        for frm, to in wins:
            try:
                if site["kind"] == "agendas":
                    rows = agenda_rows(site, frm, to, cache)
                else:
                    rows = COLLECT[site["kind"]](site, frm, to)
                log.info("%s %s..%s: %s records", key, frm, to, len(rows))
                recs += rows
            except Exception as e:  # noqa: BLE001
                failed = True
                log.warning("%s %s..%s failed: %s", key, frm, to, e)
            time.sleep(SLEEP)
        if site["kind"] == "arcgis" and site.get("signal_kind"):
            for r in recs:
                r["kind"] = site["signal_kind"]
        data = merge_cases(data, key, recs, failed)
        os.makedirs(os.path.dirname(AGENDA_CACHE), exist_ok=True)
        json.dump(cache, open(AGENDA_CACHE, "w"))
        if full and not failed:
            data["last_full_sweep"] = now_iso()
        save_portal(key, data)
        status[key] = data["meta"]
        log.info("%s: %s", key, data["meta"])
    return status


# ---------------------------------------------------------------- manual rows

def manual_rows():
    """data/distress/manual.csv: county,kind,date,address,zip,parcel,case_number,status,source,url,detail
    for sources that are only a web page, a press release or a board agenda."""
    if not os.path.exists(MANUAL):
        return []
    out = []
    for r in csv.DictReader(open(MANUAL, newline="", encoding="utf-8")):
        r = {(k or "").strip(): (v or "").strip() for k, v in r.items()}
        if not r.get("county") or not r.get("kind") or not (r.get("address") or r.get("parcel")):
            continue
        out.append({"case_number": r.get("case_number") or hashlib.sha1(f"{r['county']}|{r.get('address')}|{r.get('date')}|{r['kind']}".encode()).hexdigest()[:10],
                    "type": r["kind"], "status": r.get("status") or "open", "opened": r.get("date") or None, "closed": None,
                    "address": r.get("address", ""), "street": r.get("address", "").split(",")[0].strip(), "zip": r.get("zip", "")[:5],
                    "parcel": r.get("parcel", ""), "description": r.get("detail", ""), "url": r.get("url", ""),
                    "county": r["county"], "source": r.get("source") or "entered by hand", "kind": r["kind"].upper(), "manual": True})
    return out


# ---------------------------------------------------------------- matching

_SUF = {"STREET": "ST", "ROAD": "RD", "AVENUE": "AVE", "DRIVE": "DR", "COURT": "CT", "LANE": "LN", "PLACE": "PL", "CIRCLE": "CIR", "HIGHWAY": "HWY",
        "BOULEVARD": "BLVD", "TERRACE": "TER", "TRAIL": "TRL", "PARKWAY": "PKWY", "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}
_NOISE = re.compile(r"\b(APT|UNIT|STE|SUITE|LOT|BLDG|FL|#)\b.*$")


def addr_key(a):
    """'13192 Laurel Ln, Apt 2' -> ('13192', 'LAUREL LN'). The county layers write the suffix
    inconsistently, so a second key without the suffix is tried too."""
    t = _NOISE.sub("", re.sub(r"[^A-Z0-9 ]", " ", (a or "").upper().split(",")[0])).split()
    if not t or not t[0].isdigit():
        return None
    words = [_SUF.get(w, w) for w in t[1:]]
    return t[0], " ".join(words)


def strip_suffix(k):
    if not k:
        return None
    w = k[1].split()
    while len(w) > 1 and w[-1] in set(_SUF.values()):
        w.pop()
    return k[0], " ".join(w)


def county_index(county):
    path = COUNTY_DBS[county]
    if not os.path.exists(path):
        return {}, {}, {}
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    by_addr, by_pin, info = {}, {}, {}
    for r in con.execute("SELECT pid, pin, pin_nospace, parcel, site_addr, owner, mail_zip, total_value FROM parcels"):
        info[r["pid"]] = dict(r)
        for k in (addr_key(r["site_addr"]), strip_suffix(addr_key(r["site_addr"]))):
            if k:
                by_addr.setdefault(k, set()).add(r["pid"])
        for pin in (r["pin"], r["pin_nospace"], r["parcel"]):
            if pin:
                by_pin[re.sub(r"[^A-Z0-9]", "", str(pin).upper())] = r["pid"]
    con.close()
    return by_addr, by_pin, info


def match(case, idx):
    """-> (pid, how) | (None, 'ambiguous'|'unmatched'). Parcel id first, then address inside the county."""
    by_addr, by_pin, info = idx
    if case.get("parcel"):
        p = re.sub(r"[^A-Z0-9]", "", case["parcel"].upper())
        if p in by_pin:
            return by_pin[p], "parcel"
        if case["county"] == "Fauquier" and p.isdigit() and (config.FQ_PID_BASE + int(p)) in info:
            return config.FQ_PID_BASE + int(p), "parcel"
    k = addr_key(case.get("street") or case.get("address"))
    cands = set()
    for kk in (k, strip_suffix(k)):
        if kk and kk in by_addr:
            cands = by_addr[kk]
            break
    if not cands:
        return None, "unmatched"
    if len(cands) == 1:
        return next(iter(cands)), "address"
    if len(cands) > MAX_TIES:
        return None, "ambiguous"
    # a few parcels share the address (a lot split): take the one with a house, else the biggest
    best = max(cands, key=lambda p: (info[p]["total_value"] or 0))
    return best, "address-nearest"


def to_signal(case, today):
    kind = case.get("kind") or kind_of(case.get("type", ""), case.get("description", ""))
    open_ = is_open(case.get("status"))
    d0 = norm_date(case.get("opened")) or ""
    case["opened"] = d0 or None
    age = (today - dt.date.fromisoformat(d0)).days if d0 else None
    if kind == "FIRE":
        open_ = age is not None and age <= 730           # a fire counts for two years, then it is history
    elif case.get("agenda"):
        open_ = age is not None and age <= 548           # a board action counts for 18 months
    elif kind == "DEMO_PERMIT":
        open_ = bool(re.search(r"issued|applied|pending|in review|approved|active", case.get("status", ""), re.I)) and (age is None or age <= 730)
    confirmed = bool(CONFIRMED_WORDS.search(case.get("status", "") + " " + case.get("type", "")))
    complaint = bool(re.search(r"complaint", case.get("type", ""), re.I)) and not confirmed
    d = case.get("opened") or ""
    cooling = kind == "FIRE" and d and (today - dt.date.fromisoformat(d[:10])).days < COOLING_DAYS
    return {"kind": kind, "open": open_, "confirmed": confirmed, "complaint": complaint, "cooling": cooling,
            "date": d or None, "closed": case.get("closed"), "case_number": case.get("case_number"), "type": case.get("type"),
            "status": case.get("status"), "source": case.get("source"), "url": case.get("url"), "address": case.get("address"),
            "description": case.get("description") or "", "county": case["county"]}


def build(today=None):
    today = today or dt.date.today()
    cases = []
    for key in SITES:
        cases += list(load_portal(key).get("cases", {}).values())
    cases += manual_rows()
    idx = {c: county_index(c) for c in COUNTY_DBS}
    by_parcel, unmatched, ambiguous, how_counts = {}, [], [], {}
    per_parcel_cases = {}
    for c in cases:
        if c["county"] not in idx:
            continue
        pid, how = match(c, idx[c["county"]])
        how_counts[how] = how_counts.get(how, 0) + 1
        sig = to_signal(c, today)
        sig["match"] = how
        if pid is None:
            (ambiguous if how == "ambiguous" else unmatched).append({k: sig[k] for k in ("county", "address", "kind", "case_number", "source", "date")})
            continue
        key = f"{c['county']}:{pid}"
        per_parcel_cases.setdefault(key, []).append(sig)
    for key, sigs in per_parcel_cases.items():
        sigs.sort(key=lambda s: s["date"] or "", reverse=True)
        code = [s for s in sigs if s["kind"] in ("CODE_VIOLATIONS", "NUISANCE_CASE", "ZONING_CASE", "VACANT_NOTICE") and (s["date"] or "9999") >= "2020"]
        out = list(sigs)
        if len(code) >= REPEAT_MIN:
            out.insert(0, {"kind": "REPEAT_CODE_CASES", "open": True, "confirmed": False, "complaint": False, "cooling": False,
                           "date": code[0]["date"], "case_number": "", "type": "", "status": "", "source": code[0]["source"], "url": code[0]["url"],
                           "address": code[0]["address"], "county": code[0]["county"], "match": code[0]["match"],
                           "description": f"{len(code)} code cases at this parcel since 2020: " + ", ".join(f"{s['case_number']} ({s['status']})" for s in code[:6])})
        by_parcel[key] = out[:MAX_PER_PARCEL]
    open_kinds = {k: len({s["kind"] for s in v if s["open"]}) for k, v in by_parcel.items()}
    counts = {"cases": len(cases), "matched": sum(len(v) for v in by_parcel.values()), "parcels_with_signals": len(by_parcel),
              "parcels_with_open_signals": sum(1 for k, v in by_parcel.items() if any(s["open"] for s in v)),
              "unmatched": len(unmatched), "ambiguous": len(ambiguous), "matched_by": how_counts,
              "stacked_2plus": sum(1 for n in open_kinds.values() if n >= 2), "stacked_3plus": sum(1 for n in open_kinds.values() if n >= 3),
              "by_county": {c: sum(1 for k in by_parcel if k.startswith(c + ":")) for c in COUNTY_DBS},
              "by_kind": {}}
    for v in by_parcel.values():
        for s in v:
            counts["by_kind"][s["kind"]] = counts["by_kind"].get(s["kind"], 0) + 1
    os.makedirs(OUT, exist_ok=True)
    json.dump({"generated_at": now_iso(), "counts": counts, "sources": {k: load_portal(k).get("meta", {}) for k in SITES},
               "note": "Signals are attached to parcels by parcel id or by street address inside the county. Only open cases score. "
                       "An old record never means the property is vacant or damaged today.",
               "by_parcel": by_parcel, "unmatched": unmatched[:500], "ambiguous": ambiguous[:500]},
              open(SIGNALS, "w"), separators=(",", ":"), ensure_ascii=False)
    log.info("signals: %s", counts)
    return counts


# ---------------------------------------------------------------- read side (boards)

_CACHE = None


def load():
    """'<county>:<pid>' -> [signals]. Read once per process."""
    global _CACHE
    if _CACHE is None:
        _CACHE = json.load(open(SIGNALS))["by_parcel"] if os.path.exists(SIGNALS) else {}
    return _CACHE


def of(pid, county=None):
    return load().get(f"{county or config.COUNTY}:{pid}") or []


def flags_for(sigs):
    """Flags and points from a parcel's signals: open cases only, one flag per kind, +10 when 2+ kinds."""
    kinds, flags = set(), []
    for s in sigs:
        if not s.get("open"):
            continue
        k = s["kind"]
        if k in config.DISTRESS_POINTS and k not in kinds:
            kinds.add(k)
            flags.append(k)
        if k == "FIRE" and s.get("cooling"):
            flags.append("FIRE_COOLING")
    if len(kinds) >= 2:
        flags.append("STACKED_SIGNALS")
    pts = sum(config.DISTRESS_POINTS[k] for k in kinds) + (config.DISTRESS_POINTS["STACKED_SIGNALS"] if len(kinds) >= 2 else 0)
    return flags, pts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--match-only", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    if not a.match_only:
        collect(a.full, set(a.only.split(",")) if a.only else None)
    build()
