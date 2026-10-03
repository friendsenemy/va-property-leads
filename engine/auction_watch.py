"""
Surplus funds / foreclosure alerts for King George County and its neighbours.

  python -m engine.auction_watch            # needs .cache/kg.sqlite (run engine.parcels first)
  python -m engine.auction_watch --no-fetch # rebuild from what is on disk; no network

Ported from md-property-leads engine2/auction_watch.py. Same architecture (feeds ->
match to the parcel record -> honest payoff range -> tier -> where the money is), with
Virginia's sources, law and names.

WHAT IS DIFFERENT IN VIRGINIA
  * Foreclosure is non-judicial. A substitute trustee advertises the sale and sells at
    the courthouse door; there is no court case and nobody publishes the hammer price.
    So "Auction Scheduled" comes from the trustees' own sale lists, and "Auction Sold"
    is only known when the county's parcel record shows title has moved.
  * A delinquent-tax sale IS judicial (Va. Code 58.1-3965 et seq.). King George's
    assessor writes those deeds as "<attorney> SPECIAL COMMISSIONER ON BEHALF OF
    <former owner>" with the price paid. That is the cleanest surplus signal the county
    publishes: former owner, price and date on one line. Stage TAX_SALE_SOLD.

FEEDS (each checked for robots.txt and terms; see docs/sources-and-terms.md)
  * Samuel I. White, P.C.   siwpc.net/AutoUpload/Sales.pdf   statewide list, one PDF
  * Cohn, Goldberg & Deutsch cgd-law.com/va/data/sales.csv   statewide list, one CSV
  * data/surplus/notices.csv   sales you typed in from a newspaper notice (borrower,
                               deed of trust date / book / page, original loan amount)
  * the King George parcel layer, already pulled nightly: special commissioner deeds,
    and title moving on a parcel that was on a trustee's list
  Not used, because their terms forbid it: the Virginia Press Association notice site,
  the Free Lance-Star, Glasser & Glasser, BWW (Aldridge Pite), Rosenberg, LOGS, Orlans,
  McCabe, Brock & Scott (personal, non-commercial use only).

THE ESTIMATE is a range, never one number.
  payoff  = the original deed-of-trust amount from the notice, amortised (best), or the
            owner's own purchase price x 95% amortised (fallback), plus ~12% arrears,
            bounded by the bidder's deposit where the trustee states one
  surplus = price paid (or assessed value, before the sale) minus that range
  STRONG only when the price clears the HIGH end by $25,000 and 1.3x. POSSIBLE at
  $10,000 over the middle. Residential, assessed $60,000 or more.
  A lead known only from a deed is a candidate: shown behind a toggle, never STRONG.

Outputs
  data/surplus/auctions.json         the live board
  data/surplus/auction-archive.json  sold more than 180 days ago
  data/surplus/auctions-seen.json    every sale ever seen on a list, with the owner and
                                     mailing address on record that day
  data/surplus/grantor-sample.json   how the assessor words trustee-like grantors
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import logging
import os
import re
import sqlite3

import requests

from engine import config, owner_parse, waterfront

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("auction_watch")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "surplus")
OUT_PATH, SEEN_PATH = os.path.join(OUT, "auctions.json"), os.path.join(OUT, "auctions-seen.json")
ARCHIVE_PATH = os.path.join(OUT, "auction-archive.json")
NOTICES_CSV = os.path.join(OUT, "notices.csv")
FORMER_CSV = os.path.join(OUT, "former-owners.csv")
RAW_DIR = os.path.join(ROOT, ".cache", "surplus")
DB = os.path.join(ROOT, ".cache", "kg.sqlite")

UA = {"User-Agent": "Mozilla/5.0 (compatible; va-property-leads/1.0; +https://github.com/friendsenemy/va-property-leads)"}
SIW_URL = "https://www.siwpc.net/AutoUpload/Sales.pdf"
CGD_URL = "https://cgd-law.com/va/data/sales.csv"

# King George and the jurisdictions around it. ZIP codes are how a list with no county
# column is placed; a ZIP can straddle a line, so the county is labelled "by ZIP".
TARGETS = {
    "King George": {"22485", "22448", "22451", "22481", "22526", "22544", "22547"},
    "Stafford": {"22554", "22556", "22405", "22406", "22412", "22430", "22463", "22471", "22545", "22555"},
    "Spotsylvania": {"22407", "22408", "22551", "22553", "22534", "22565"},
    "Fredericksburg": {"22401", "22402", "22403", "22404"},
    "Caroline": {"22427", "22428", "22514", "22535", "22538", "22546", "22552", "22580", "22501"},
    "Westmoreland": {"22443", "22469", "22488", "22520", "22529", "22558", "22577", "22581", "22442", "22524"},
}
ZIP_COUNTY = {z: c for c, zs in TARGETS.items() for z in zs}

KEEP_SOLD_DAYS = 180            # a sold lead stays on the live board this long, then moves to the archive
AWAIT_DEED_DAYS = 120           # after the sale date, how long to wait for the deed before dropping a scheduled sale

ASSUMED_LTV = 0.95
ASSUMED_RATE = 0.055
ARREARS_FACTOR = 0.12
OLD_LOAN_YEARS = 15
DEPOSIT_MULTIPLE = 10           # Va. Code 55.1-324(A)(2): deposit of up to 10% of the sale price
DEPOSIT_MIN_SIGNAL = 15000
STRONG_MIN_SURPLUS = 25000
POSSIBLE_MIN_SURPLUS = 10000
STRONG_MIN_RATIO = 1.30
MIN_ASSESSED = 60000

# Maryland measured 1,197 confirmed foreclosures: median price 75% of assessment, 12.5%
# above assessment, 1% above 130%. King George has too few confirmed sales to re-measure
# (see data/surplus/grantor-sample.json), so the Maryland figures stand as priors.
FORECLOSURE_MAX_TO_AV = 1.0
FORECLOSURE_HARD_MAX_TO_AV = 1.3
HAMMER_MAX_TO_AV, HAMMER_MIN_TO_AV = 8.0, 0.05      # outside this a recorded price is treated as a data error

REO_OWNER = re.compile(r"\b(BANK|SAVINGS|MORTGAGE|MTG|LENDING|LOAN|FEDERAL NATIONAL|FANNIE|FREDDIE|FEDERAL HOME|HUD|"
                       r"SECRETARY OF|VETERANS AFFAIRS|CREDIT UNION|SERVICING|NATIONSTAR|WELLS FARGO|DEUTSCHE|WILMINGTON|TRUST CO)\b")
ENTITY = re.compile(r"\b(LLC|L L C|INC|CORP|LTD|LP|LLP|HOLDINGS?|PROPERTIES|ASSOC|BANK|CHURCH|PARTNERS|HOMES|INVESTMENTS?)\b")
# How King George's assessor words these deeds (measured; see grantor-sample.json).
COMMISSIONER = re.compile(r"SPECIAL\s+COMMISSIONERS?", re.I)
ON_BEHALF = re.compile(r"\b(?:ON|OF)\s+BEHALF\s+OF\s+(.+)$", re.I)
TRUSTEE_SALE = re.compile(r"\bSUB(?:STITUTE)?\.?\s*TR(?:USTEES?|S)?\b|TRUSTEE'?S\s+DEED|FORECLOS", re.I)
FAMILY_TRUST = re.compile(r"\b(LIVING|REV(OCABLE)?|FAMILY|IRREV(OCABLE)?|DEED IN TRUST|TRUST DATED)\b", re.I)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _f(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def iso_date(s):
    """'11/17/2026', '2026-11-17', '11/17/2026 12:00 pm' -> '2026-11-17' or ''."""
    s = (s or "").strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
    else:
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
        if not m:
            return ""
        mo, d, y = (int(x) for x in m.groups())
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return ""


# --- the estimate (ported unchanged from the Maryland engine) -------------------

def remaining_balance(principal, rate, years_elapsed, term=30):
    if principal <= 0:
        return 0.0
    r, n = rate / 12.0, term * 12
    k = min(max(years_elapsed, 0) * 12, n)
    return principal * ((1 + r) ** n - (1 + r) ** k) / ((1 + r) ** n - 1)


def estimate_payoff(purchase_price, purchase_year, sale_year, deposit=None, assessed=0, mortgage=None, mortgage_year=None):
    """(low, mid, high, basis), or None when there is nothing to go on.
    mortgage / mortgage_year: the original deed-of-trust amount and year from the sale notice."""
    dep = deposit * DEPOSIT_MULTIPLE if deposit and deposit >= DEPOSIT_MIN_SIGNAL else None
    if mortgage and mortgage >= 10000:
        yrs = max(sale_year - (mortgage_year or purchase_year or sale_year), 0)
        base = remaining_balance(mortgage, ASSUMED_RATE, yrs) * (1 + ARREARS_FACTOR)
        if yrs <= OLD_LOAN_YEARS:
            return (base * 0.9, max(base, dep or 0) if dep and dep > base * 1.3 else base, max(base * 1.15, dep or 0),
                    "deed of trust amount in the sale notice")
        return (base, max(base, dep or base, 0.4 * assessed), max(dep or 0, 0.85 * assessed, base),
                "deed of trust amount in the sale notice (old loan, may have been modified)")
    model = None
    if purchase_price and purchase_price >= 20000 and purchase_year:
        yrs = max(sale_year - purchase_year, 0)
        model = (remaining_balance(purchase_price * ASSUMED_LTV, ASSUMED_RATE, yrs) * (1 + ARREARS_FACTOR), yrs)
    if model and model[1] <= OLD_LOAN_YEARS:
        m = model[0]
        if dep:
            mid = max(m, dep)
            return (min(m, dep) * 0.9, mid, mid * 1.15, "owner's purchase price + bidder's deposit")
        return (m * 0.85, m, m * 1.2, "owner's purchase price")
    if dep:
        return (dep * 0.8, dep, dep * 1.3, "bidder's deposit x10" + (" (purchase too old to model)" if model else ""))
    if model:
        lo = model[0]
        return (lo, max(lo, 0.5 * assessed), max(lo, 0.85 * assessed), "old purchase: the debt is a later loan, size unknown")
    return None


def tax_sale_costs(price, taxes_owed):
    """What comes off the top of a tax sale before the former owner: taxes, penalty,
    interest, the county's attorney fees and costs. (low, mid, high, basis)."""
    if taxes_owed:
        return (taxes_owed + 3000, taxes_owed * 1.25 + 5000, taxes_owed * 1.6 + 10000,
                f"${taxes_owed:,.0f} of taxes on the county's delinquent list, plus interest, attorney fees and costs")
    return (4000, max(8000, 0.10 * price), max(15000, 0.25 * price),
            "taxes not on file here: assumed 10-25% of the price for taxes, attorney fees and costs")


def tier_for(value, est):
    lo, mid, hi = est
    surplus = (value - hi, value - mid, value - lo)
    if value - hi >= STRONG_MIN_SURPLUS and value >= hi * STRONG_MIN_RATIO:
        return "STRONG", surplus
    if value - mid >= POSSIBLE_MIN_SURPLUS:
        return "POSSIBLE", surplus
    return None, surplus


# --- where the money is ----------------------------------------------------------

def add_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def collection_window(kind, sale_date, today, order_date=None):
    """(code, note, deadline). A verdict by age, not a fact: the dashboard says so and
    asks for a two-minute human check."""
    if not sale_date:
        return None, None, None
    d = dt.date.fromisoformat(sale_date)
    days = (today - d).days
    if kind == "TAX":
        deadline = add_years(dt.date.fromisoformat(order_date) if order_date else d, 2)
        if today <= deadline:
            when = (f"The Clerk's report dates this case {order_date}; if that is the confirmation order, the deadline is {deadline.isoformat()}. "
                    "Confirm the date in the case file." if order_date else
                    "The confirmation is earlier than the deed date shown here, so the real deadline "
                    f"is earlier than {deadline.isoformat()}. Get the confirmation date from the case file.")
            return ("COURT_2YR", "A tax sale is a court case. The surplus is held by the Clerk of the King George Circuit Court, and the "
                    "former owner, heirs or assigns must petition for it within two years of the order confirming the sale "
                    "(Va. Code § 58.1-3967). After that it is paid to the county. " + when, deadline.isoformat())
        return ("PAID_TO_COUNTY", "More than two years since the deed. Unclaimed tax-sale surplus is paid to the county after two years "
                "from confirmation (§ 58.1-3967). After that the only route is a request to the Board of Supervisors, "
                "which may grant relief by ordinance but does not have to.", deadline.isoformat())
    if days < 183:
        return ("TRUSTEE_HOLDS", "Under six months since the sale. The trustee pays costs, the loan and junior liens, then the "
                "residue to the former owner (Va. Code § 55.1-324), and has six months to file an account with the "
                "Commissioner of Accounts (§ 64.2-1309). Any surplus is most likely still with the trustee. You are early.", None)
    if days < 730:
        return ("TRUSTEE_OR_COURT", "The trustee's account should now be on file with the Commissioner of Accounts for the Circuit Court "
                "where the deed of trust was recorded. It states the surplus and who was paid. If the owner could not be "
                "found, the trustee may have paid the money into the Circuit Court (§ 8.01-364).", None)
    return ("TREASURY_LIKELY", "Over two years. Money paid into court and unclaimed for a year goes to the Virginia Treasury "
            "(§ 8.01-602); money a trustee still holds is presumed abandoned after five years (§ 55.1-2514, our reading). "
            "Search the former owner's name at vamoneysearch.gov. The owner claims free. A finder may not contract for a "
            "fee until 36 months after the money reached the Treasury, and then no more than 10% (§ 55.1-2542).", None)


# --- feeds -----------------------------------------------------------------------

def fetch(url, binary=False):
    r = requests.get(url, headers=UA, timeout=90)
    r.raise_for_status()
    return r.content if binary else r.text


_SIW_NOISE = {"VA", "Property Address", "Property City", "Sale Date", "Sale Time", "Sale Location(City)", "Firm File#", "Property Zip",
              "Foreclosure Sales Report"}


def parse_siw(pdf_bytes):
    """Samuel I. White's report: seven lines per sale (address, city, zip, date, time,
    place, file number), with a county line above the first sale in each county."""
    from pypdf import PdfReader
    lines = []
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        lines += [ln.strip() for ln in (page.extract_text() or "").splitlines() if ln.strip()]
    out, county, last_end = [], "", -1
    for i, ln in enumerate(lines):
        if not re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", ln) or i < 3 or i + 3 >= len(lines):
            continue
        if not re.fullmatch(r"\d{5}(-\d{4})?", lines[i - 1]) or not re.fullmatch(r"\d{1,2}:\d\d(:\d\d)?", lines[i + 1]):
            continue
        # Between the previous sale and this ZIP: [county line] address, city (the city can wrap
        # onto two lines, and a page break drops the report's header text in here too).
        # The address is the last line that starts with a number; the city is what follows it.
        between = lines[last_end + 1:i - 1]
        a = max((k for k, x in enumerate(between) if re.match(r"\d", x)), default=None)
        if a is None or a + 1 >= len(between):
            last_end = i + 3
            continue
        head = between[a - 1] if a >= 1 else ""
        if head and head not in _SIW_NOISE and re.fullmatch(r"(City of )?[A-Z][A-Za-z .'-]{2,28}", head):
            county = head
        last_end = i + 3
        out.append({"source": "Samuel I. White, P.C.", "source_url": SIW_URL, "county": re.sub(r"^City of ", "", county),
                    "address": between[a], "city": " ".join(between[a + 1:]), "zip": lines[i - 1][:5], "sale_date": iso_date(ln),
                    "sale_time": lines[i + 1][:5], "sale_place": lines[i + 2], "file_no": lines[i + 3], "trustee": "Samuel I. White, P.C."})
    return out


def parse_cgd(text):
    out = []
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        m = re.match(r"^(.*?),\s*VA\s+(\d{5})", row.get("City State ZIP", ""))
        if not m:
            continue
        when = row.get("Sale Date", "")
        t = re.search(r"(\d{1,2}:\d\d\s*[ap]m)", when, re.I)
        out.append({"source": "Cohn, Goldberg & Deutsch, LLC", "source_url": "https://cgd-law.com/va/", "county": ZIP_COUNTY.get(m.group(2), ""),
                    "county_by_zip": True, "address": row.get("Street Address", ""), "city": m.group(1), "zip": m.group(2),
                    "sale_date": iso_date(when), "sale_time": t.group(1) if t else "", "sale_place": "", "deposit": _f(row.get("Deposit")) or None,
                    "file_no": row.get("More Info", ""), "cancelled": row.get("Cancelled", "").upper().startswith("Y"),
                    "trustee": "Cohn, Goldberg & Deutsch, LLC"})
    return out


def manual_notices():
    """Sales typed in by hand from a newspaper notice: data/surplus/notices.csv."""
    if not os.path.exists(NOTICES_CSV):
        return []
    out = []
    for row in csv.DictReader(open(NOTICES_CSV, newline="", encoding="utf-8")):
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        if not row.get("address") or not iso_date(row.get("sale_date")):
            continue
        z = row.get("zip", "")[:5]
        out.append({"source": "Sale notice entered by hand", "source_url": row.get("source_url", ""),
                    "county": row.get("county") or ZIP_COUNTY.get(z, ""), "address": row["address"], "city": row.get("city", ""), "zip": z,
                    "sale_date": iso_date(row["sale_date"]), "sale_time": row.get("sale_time", ""), "sale_place": row.get("sale_place", ""),
                    "borrower": row.get("borrower", ""), "dot_date": iso_date(row.get("dot_date")), "dot_ref": row.get("dot_ref", ""),
                    "original_amount": _f(row.get("original_amount")) or None, "deposit": _f(row.get("deposit")) or None,
                    "trustee": row.get("trustee", ""), "result_price": _f(row.get("result_price")) or None,
                    "result_buyer": row.get("result_buyer", ""), "note": row.get("note", ""), "file_no": row.get("file_no", ""),
                    "cancelled": row.get("cancelled", "").upper().startswith("Y"), "manual": True})
    return out


def lot_id(l):
    key = l.get("file_no") or f"{l['address']}|{l['zip']}|{l['sale_date']}"
    src = re.sub(r"\W+", "", l["source"].split(",")[0].lower())[:12]
    return f"{src}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"


def fetch_lots(do_fetch=True):
    """Every scheduled sale in the target counties, from every allowed list."""
    os.makedirs(RAW_DIR, exist_ok=True)
    lots, status = [], {}
    for name, url, binary, parse in (("siw", SIW_URL, True, parse_siw), ("cgd", CGD_URL, False, parse_cgd)):
        raw_path = os.path.join(RAW_DIR, name + (".pdf" if binary else ".csv"))
        try:
            if do_fetch:
                body = fetch(url, binary)
                open(raw_path, "wb" if binary else "w").write(body)
            else:
                body = open(raw_path, "rb" if binary else "r").read()
            got = parse(body)
            mine = [l for l in got if l["county"] in TARGETS or ZIP_COUNTY.get(l["zip"])]
            for l in mine:
                if l["county"] not in TARGETS:
                    l["county"], l["county_by_zip"] = ZIP_COUNTY[l["zip"]], True
            status[name] = {"ok": True, "statewide": len(got), "in_target_counties": len(mine)}
            log.info("%s: %s sales statewide, %s in the target counties", name, len(got), len(mine))
            if not got:
                log.warning("%s parsed to zero sales: the format may have changed", name)
            lots += mine
        except Exception as e:  # noqa: BLE001
            status[name] = {"ok": False, "error": str(e)[:200]}
            log.warning("%s not read: %s", name, e)
    man = manual_notices()
    status["manual"] = {"ok": True, "in_target_counties": len(man)}
    lots += man
    for l in lots:
        l["lot_id"] = lot_id(l)
    return lots, status


# --- the parcel record -----------------------------------------------------------

_SUFFIX = {"STREET", "ST", "ROAD", "RD", "AVENUE", "AVE", "DRIVE", "DR", "COURT", "CT", "LANE", "LN", "PLACE", "PL", "CIRCLE", "CIR",
           "HIGHWAY", "HWY", "PARKWAY", "PKWY", "BOULEVARD", "BLVD", "TERRACE", "TER", "WAY", "TRAIL", "TRL", "LOOP", "RUN"}


def street_key(addr):
    """'13192 Laurel Ln' -> ('13192', 'LAUREL'). The county writes addresses without the suffix."""
    t = re.sub(r"[^A-Z0-9 ]", " ", (addr or "").upper().split(",")[0]).split()
    if not t or not t[0].isdigit():
        return None
    words = [w for w in t[1:] if w not in ("APT", "UNIT", "LOT")]
    while len(words) > 1 and words[-1] in _SUFFIX:
        words.pop()
    return t[0], " ".join(words)


def load_parcels():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM parcels")]
    con.close()
    return rows


def transfer_date(p):
    y, m, d = p.get("sale_year") or 0, p.get("sale_month") or 0, p.get("sale_day") or 0
    if y in config.UNKNOWN_SALE_YEARS or (y, m, d) in config.PLACEHOLDER_SALE_DATES:
        return ""
    try:
        return dt.date(int(y), int(m) or 1, int(d) or 1).isoformat()
    except (TypeError, ValueError):
        return ""


def mail_of(p):
    line2 = " ".join(str(x) for x in (p.get("mail_city") or "", p.get("mail_state") or "") if x).strip()
    z = str(p.get("mail_zip") or "").strip()
    return ", ".join(x for x in ((p.get("mail_addr") or "").strip(), (line2 + (" " + z if z and z != "0" else "")).strip()) if x)


def deed_ref(p):
    b, pg = p.get("deed_book") or 0, p.get("deed_page") or 0
    if not b:
        return ""
    return f"DB {b} PG {pg}" if pg else f"Instr. {b} of {p.get('sale_year') or '?'}"


def held_as(owner, owner_type="", subtype=""):
    o = (owner or "").upper()
    if owner_type == "ESTATE":
        return {"HEIRS": "Heirs on title", "LIFE_ESTATE": "Life estate", "FIDUCIARY": "Executor / fiduciary on title"}.get(subtype, "Estate on title")
    if owner_type == "ET_AL" or re.search(r"\bET ?ALS?\b", o):
        return "Several owners (et al): every one of them has a share"
    if owner_type == "TRUST" or re.search(r"\bTR(USTEES?)?\b", o):
        return "Held in a trust: the trustee signs, the beneficiaries are owed"
    if ENTITY.search(o):
        return "Held by a company"
    if re.search(r"\bOR\b", o):
        return "Two owners with survivorship (\"OR\"): if one has died the other owns it all"
    if "&" in o or re.search(r"\bAND\b", o):
        return "Two or more owners: each has a share"
    return "One owner"


def snapshot(p):
    return {"pid": p["pid"], "owner": p["owner"], "mail": mail_of(p), "held_as": held_as(p["owner"], p.get("owner_type"), p.get("owner_subtype")),
            "transfer": transfer_date(p), "price": p.get("sale_price") or 0, "deed": deed_ref(p), "taken": dt.date.today().isoformat()}


def residential(p):
    return (p.get("impr_value") or 0) > 0 and (p.get("year_built") or 0) > 0


def former_overrides():
    """data/surplus/former-owners.csv: what is known about an owner before title moved
    (mailing address, taxes owed), keyed by parcel id. Filled by hand or from a county list."""
    out = {}
    if os.path.exists(FORMER_CSV):
        for row in csv.DictReader(open(FORMER_CSV, newline="", encoding="utf-8")):
            if (row.get("pid") or "").strip().isdigit():
                out[int(row["pid"])] = {k: (v or "").strip() for k, v in row.items()}
    return out


def changes_log():
    """pid -> the newest owner change the nightly pull recorded (old owner, old mailing address)."""
    path = os.path.join(ROOT, "data", "owner-changes.json")
    out = {}
    if os.path.exists(path):
        try:
            for c in json.load(open(path)):
                if c.get("change") == "OWNER" and c["pid"] not in out:
                    out[c["pid"]] = c
        except (ValueError, TypeError, KeyError):
            pass
    return out


def base_row(p):
    return {"pid": p["pid"], "pin": (p.get("parcel") or p.get("pin") or "").strip(), "card_url": p.get("card_url") or "",
            "county": "King George", "address": p.get("site_addr") or "", "legal": p.get("legal") or "", "acres": p.get("acres"),
            "assessed_value": p.get("total_value") or 0, "impr_value": p.get("impr_value") or 0, "year_built": p.get("year_built") or None,
            "residential": residential(p), "remarks": " | ".join(x for x in (p.get("remark1"), p.get("remark2")) if x),
            "water": waterfront.of(p)}


# --- stages ----------------------------------------------------------------------

def scheduled_row(lot, p, seen_entry, today):
    """A sale on a trustee's list whose date has not passed (or passed without a deed yet)."""
    past = lot["sale_date"] < today.isoformat()
    row = {**lot, "stage": "AUCTION_SCHEDULED", "kind": "FORECLOSURE", "confirmed_by_notice": True, "from_deed": False,
           "sale_date_passed": past, "hammer": lot.get("result_price")}
    reasons = []
    if not p:
        row.update({"tier": "UNRATED", "payoff_est": None, "surplus_est": None, "assessed_value": None, "owner_of_record": lot.get("borrower") or "",
                    "former_owner": lot.get("borrower") or "", "mail": "", "held_as": ""})
        reasons.append("outside King George, or not matched to a parcel: no assessed value to measure equity against"
                       if lot["county"] != "King George" else "address not matched to a King George parcel: check the tax map by hand")
        row["why"] = "; ".join(reasons)
        return row
    snap = seen_entry.get("snap") or snapshot(p)
    row.update(base_row(p))
    row.update({"owner_of_record": snap["owner"], "former_owner": lot.get("borrower") or snap["owner"], "mail": snap["mail"],
                "held_as": snap["held_as"], "purchase_price": snap["price"] or None, "purchase_year": int(snap["transfer"][:4]) if snap["transfer"] else None,
                "purchase_deed": snap["deed"], "snapshot_date": snap["taken"]})
    av = row["assessed_value"]
    sale_year = int(lot["sale_date"][:4])
    est4 = estimate_payoff(snap["price"], row["purchase_year"], sale_year, lot.get("deposit"), av,
                           mortgage=lot.get("original_amount"), mortgage_year=int(lot["dot_date"][:4]) if lot.get("dot_date") else None)
    row["payoff_est"], row["payoff_basis"] = ([round(x) for x in est4[:3]], est4[3]) if est4 else (None, None)
    tier, surplus = (None, None)
    if est4 and av:
        tier, surplus = tier_for(av, est4[:3])
        lo, mid, hi = est4[:3]
        reasons.append(f"assessed {av:,.0f} vs estimated payoff {mid:,.0f} to {hi:,.0f} ({est4[3]})" if tier
                       else f"assessed value at or below the estimated payoff ({est4[3]}): little equity on paper")
    else:
        reasons.append("no purchase price, deposit or loan amount to estimate the payoff from")
    if tier == "STRONG" and ENTITY.search(snap["owner"].upper()):
        tier = "POSSIBLE"
        reasons.append("owner is a company: the person behind it is the contact")
    if not row["residential"]:
        tier = None
        reasons.append("no dwelling on the parcel")
    if av < MIN_ASSESSED:
        tier = None
        reasons.append("below the residential value floor")
    if past:
        reasons.append("the sale date has passed and the county record does not show a new owner yet: the deed takes weeks, "
                       "or the sale was postponed or cancelled")
    row.update({"tier": tier, "surplus_est": [round(x) for x in surplus] if surplus else None, "why": "; ".join(reasons)})
    return row


def sold_row(lot, p, seen_entry, today, changes, former):
    """A sale that was on a trustee's list, and the parcel has since changed hands."""
    snap = seen_entry["snap"]
    row = {**lot, **base_row(p), "stage": "AUCTION_SOLD", "kind": "FORECLOSURE", "confirmed_by_notice": True, "from_deed": False}
    buyer, price, moved = p["owner"], p.get("sale_price") or 0, transfer_date(p)
    price = lot.get("result_price") or price
    row.update({"buyer_on_record": buyer, "trustee_deed": deed_ref(p), "deed_date": moved, "grantor_note": p.get("grantor_note") or "",
                "owner_of_record": None, "former_owner": lot.get("borrower") or snap["owner"], "mail": snap["mail"], "held_as": snap["held_as"],
                "purchase_price": snap["price"] or None, "purchase_year": int(snap["transfer"][:4]) if snap["transfer"] else None,
                "purchase_deed": snap["deed"], "snapshot_date": snap["taken"], "hammer": price or None})
    av = row["assessed_value"]
    reasons, tier, surplus = [], None, None
    sale_year = int(lot["sale_date"][:4])
    est4 = estimate_payoff(snap["price"], row["purchase_year"], sale_year, lot.get("deposit"), av,
                           mortgage=lot.get("original_amount"), mortgage_year=int(lot["dot_date"][:4]) if lot.get("dot_date") else None)
    row["payoff_est"], row["payoff_basis"] = ([round(x) for x in est4[:3]], est4[3]) if est4 else (None, None)
    if moved and moved < lot["sale_date"]:
        return None, "title moved before the sale date: the owner sold it themselves, so there is no surplus"
    if REO_OWNER.search(buyer.upper()):
        return None, "the lender took the property back (a credit bid): no surplus"
    if not price:
        reasons.append("title has moved since the sale but the county has not recorded a price: read the trustee's deed for the bid")
        tier = "POSSIBLE" if av >= MIN_ASSESSED and row["residential"] else None
    elif av and not (HAMMER_MIN_TO_AV * av <= price <= HAMMER_MAX_TO_AV * av):
        return None, f"recorded price {price:,.0f} against assessed {av:,.0f} is not believable: data error"
    elif est4:
        tier, surplus = tier_for(price, est4[:3])
        lo, mid, hi = est4[:3]
        reasons.append(f"price paid {price:,.0f} vs estimated payoff {mid:,.0f} to {hi:,.0f} ({est4[3]})" if tier
                       else f"price paid at or below the estimated payoff ({est4[3]}): likely no surplus")
    else:
        reasons.append("no purchase price, deposit or loan amount to estimate the payoff from")
        tier = "POSSIBLE" if av and price >= 0.85 * av and price >= 150000 else None
    note = (p.get("grantor_note") or "").upper()
    if tier and not TRUSTEE_SALE.search(note):
        # A trustee listed it and title then moved, but the county's note does not say
        # "trustee": the owner may have sold it to a buyer in the weeks around the sale.
        if tier == "STRONG":
            tier = "POSSIBLE"
        reasons.append("the county's note on the new deed does not name a trustee: confirm in the Clerk's index that it is a "
                       "trustee's deed and not a sale by the owner (an owner's sale leaves no surplus)")
    if tier and not row["residential"]:
        tier, _ = None, reasons.append("no dwelling on the parcel")
    if tier and av < MIN_ASSESSED:
        tier, _ = None, reasons.append("below the residential value floor")
    if not tier:
        return None, "; ".join(reasons)
    row.update({"tier": tier, "surplus_est": [round(x) for x in surplus] if surplus else None, "why": "; ".join(reasons),
                "sale_date_kind": "auction date from the trustee's list"})
    return row, None


def deed_rows(parcels, today, former, changes):
    """What the county's own record shows without any sale list: special commissioner
    deeds (tax sales), and deeds whose note names a substitute trustee or a foreclosure."""
    out, sample = [], {}
    groups = {}
    for p in parcels:
        note = (p.get("grantor_note") or "").strip()
        if not note:
            continue
        up = note.upper()
        if re.search(r"TRUST|\bTR\b|TRS\b|SUB|FORECLOS|COMMISSIONER|SHERIFF|RECEIVER|BANK|MORTGAGE|AUCTION", up):
            sample[up] = sample.get(up, 0) + 1
        moved = transfer_date(p)
        if not moved:
            continue
        if COMMISSIONER.search(note):
            m = ON_BEHALF.search(note)
            who = re.sub(r"\s+", " ", re.split(r",\s*-", m.group(1))[0]).strip(" ,-") if m else ""
            groups.setdefault(("TAX", who.upper(), moved[:7], p.get("sale_price") or 0, p["owner"]), []).append(p)
        elif TRUSTEE_SALE.search(note) and not FAMILY_TRUST.search(note):
            groups.setdefault(("FC", note.upper(), moved, p.get("sale_price") or 0, p["owner"]), []).append(p)
    for (kind, who, _when, price, buyer), ps in groups.items():
        ps.sort(key=lambda x: -(x.get("total_value") or 0))
        p = ps[0]
        moved = max(transfer_date(x) for x in ps)
        av = sum(x.get("total_value") or 0 for x in ps)
        row = base_row(p)
        ov = next((former[x["pid"]] for x in ps if x["pid"] in former), {})
        ch = next((changes[x["pid"]] for x in ps if x["pid"] in changes), {})
        row.update({"lot_id": f"deed-{p['pid']}-{moved}", "assessed_value": av, "parcel_count": len(ps),
                    "parcels": [{"pid": x["pid"], "pin": (x.get("parcel") or x.get("pin") or "").strip(), "address": x.get("site_addr") or "",
                                 "legal": x.get("legal") or "", "assessed_value": x.get("total_value") or 0, "card_url": x.get("card_url") or ""} for x in ps],
                    "sale_date": moved, "sale_date_kind": "deed date on the county record; the sale itself was earlier", "deed_date": moved,
                    "hammer": price or None, "buyer_on_record": buyer, "trustee_deed": deed_ref(p), "grantor_note": p.get("grantor_note") or "",
                    "owner_of_record": None, "from_deed": True, "confirmed_by_notice": False,
                    "source": "King George parcel record", "source_url": p.get("card_url") or "",
                    "mail": ", ".join(x for x in (ov.get("mail_addr"), " ".join(y for y in (ov.get("mail_city"), ov.get("mail_state"), ov.get("mail_zip")) if y)) if x)
                            or ch.get("old_mail", ""),
                    "mail_source": ov.get("source", "") if ov.get("mail_addr") else ("county record before the deed" if ch.get("old_mail") else "")})
        reasons = []
        if kind == "TAX":
            taxes = _f(ov.get("taxes_owed")) or None
            row.update({"stage": "TAX_SALE_SOLD", "kind": "TAX", "former_owner": ov.get("former_owner") or who.title() or ch.get("old_owner", ""),
                        "former_owner_source": "named in the special commissioner's deed note", "taxes_owed": taxes,
                        "held_as": held_as(ov.get("former_owner") or who)})
            if not price:
                continue
            est = tax_sale_costs(price, taxes)
            bal, as_of = _f(ov.get("court_balance")), ov.get("court_as_of", "")
            row.update({"case_number": ov.get("case_number", ""), "court_balance": bal or None, "court_as_of": as_of,
                        "court_disbursed": ov.get("court_disbursed", ""), "court_order_date": ov.get("court_order_date", "")})
            if bal and ov.get("court_disbursed"):
                # The Clerk's own ledger, after the taxes and costs were paid out: this IS the surplus on that date.
                row["payoff_est"], row["payoff_basis"] = [round(price - bal)] * 3, f"paid out of the sale by the Clerk on {ov['court_disbursed']}"
                surplus = (bal, bal, bal)
                tier = "STRONG" if bal >= STRONG_MIN_SURPLUS else "POSSIBLE" if bal >= POSSIBLE_MIN_SURPLUS else None
                if not tier:
                    continue
                reasons.append(f"the Clerk's liabilities index of {as_of} shows {bal:,.2f} held in case {ov.get('case_number')}, after "
                               f"{price - bal:,.0f} was paid out. That is the surplus on that date, not an estimate")
            else:
                row["payoff_est"], row["payoff_basis"] = [round(x) for x in est[:3]], est[3]
                tier, surplus = tier_for(price, est[:3])
                if not tier:
                    continue
                reasons.append(f"sold for {price:,.0f}; about {est[1]:,.0f} comes off first ({est[3]})")
                if bal:
                    reasons.append(f"the Clerk's liabilities index of {as_of} shows the full {bal:,.2f} still held in case {ov.get('case_number')}: "
                                   "taxes and costs had not been paid out yet, so the surplus is less than that")
            if av and price > 3 * av and not (bal and ov.get("court_disbursed")):
                # a tax sale rarely brings several times the assessment: could be a typo, or one price for more land
                tier = "POSSIBLE"
                reasons.append(f"the recorded price is {price / av:.1f}x the assessed value: read the deed to confirm the price before relying on it")
            reasons.append("any deed of trust or judgment lien on the property is also paid before the former owner: check the land records")
            if len(ps) > 1:
                reasons.append(f"one deed, {len(ps)} parcels: the price is for all of them")
        else:
            row.update({"stage": "AUCTION_SOLD", "kind": "FORECLOSURE", "former_owner": ch.get("old_owner", ""),
                        "former_owner_source": "county record before the deed" if ch.get("old_owner") else "",
                        "held_as": held_as(ch.get("old_owner", "")) if ch.get("old_owner") else "", "payoff_est": None, "payoff_basis": None})
            if REO_OWNER.search(buyer.upper()) or not price or av < MIN_ASSESSED or not residential(p):
                continue
            ratio = price / av if av else 0
            if ratio > FORECLOSURE_HARD_MAX_TO_AV:
                continue                     # only 1% of real foreclosures sell this far above assessment
            tier, surplus = "UNCONFIRMED", None
            reasons.append("deed-only evidence: the county's note mentions a trustee or a foreclosure sale. It may be the "
                           "trustee's deed, or the lender reselling afterwards (then this price is not the bid and there is no surplus here)")
            reasons.append(f"price {price:,.0f} is {ratio:.0%} of assessed; no loan on file to estimate against")
        row.update({"tier": tier, "surplus_est": [round(x) for x in surplus] if surplus else None, "why": "; ".join(reasons)})
        out.append(row)
    top = sorted(sample.items(), key=lambda kv: -kv[1])[:200]
    doc = ({"generated_at": now_iso(), "note": "How the assessor words trustee-like grantor notes, so the patterns are tuned to "
               "what King George actually writes. Special commissioner deeds (tax sales) are worded 'X SPECIAL COMMISSIONER ON BEHALF OF "
               "<former owner>'. Substitute-trustee deeds are rarely labelled; most trust wording here is family living trusts.",
               "special_commissioner_deeds": sum(n for k, n in sample.items() if "COMMISSIONER" in k),
               "substitute_trustee_or_foreclosure_notes": sum(n for k, n in sample.items() if TRUSTEE_SALE.search(k) and not FAMILY_TRUST.search(k)),
               "top_trust_like_grantor_notes": top})
    return out, doc


# --- build -----------------------------------------------------------------------

def build(do_fetch=True, today=None):
    today = today or dt.date.today()
    os.makedirs(OUT, exist_ok=True)
    parcels = load_parcels()
    by_key = {}
    for p in parcels:
        k = street_key(p.get("site_addr"))
        if k:
            by_key.setdefault(k, []).append(p)
    by_pid = {p["pid"]: p for p in parcels}
    former, changes = former_overrides(), changes_log()
    seen = json.load(open(SEEN_PATH))["lots"] if os.path.exists(SEEN_PATH) else {}

    lots, status = fetch_lots(do_fetch)
    listed_now = set()
    for lot in lots:
        if lot.get("cancelled"):
            continue
        listed_now.add(lot["lot_id"])
        e = seen.setdefault(lot["lot_id"], {"first_seen": now_iso()})
        e["last_seen"], e["lot"] = today.isoformat(), lot
        if lot["county"] == "King George" and "snap" not in e:
            cand = by_key.get(street_key(lot["address"]) or ("", ""), [])
            if len(cand) == 1:
                e["snap"] = snapshot(cand[0])
            elif cand:
                e["ambiguous"] = [c["pid"] for c in cand]

    rows, dropped = [], {}
    for lid, e in seen.items():
        lot = dict(e["lot"], lot_id=lid)
        age = (today - dt.date.fromisoformat(lot["sale_date"])).days
        snap = e.get("snap")
        p = by_pid.get(snap["pid"]) if snap else None
        row = None
        if p and age >= 0 and p["owner"] != snap["owner"]:
            row, why = sold_row(lot, p, e, today, changes, former)
            if not row:
                dropped[lid] = why
                continue
        elif lid in listed_now and age <= 0:
            row = scheduled_row(lot, p, e, today)
        elif age > 0 and p and age <= AWAIT_DEED_DAYS and e.get("last_seen", "") >= lot["sale_date"]:
            row = scheduled_row(lot, p, e, today)      # sale day came with the listing still up; waiting for the deed
        elif lid not in listed_now and age <= 0:
            dropped[lid] = "taken off the trustee's list before the sale date: cancelled, postponed, reinstated or paid off"
            continue
        else:
            continue
        if not row.get("tier"):
            dropped[lid] = row.get("why", "below the bar")
            continue
        row["first_seen"] = e["first_seen"]
        row["ambiguous_match"] = bool(e.get("ambiguous"))
        rows.append(row)

    confirmed_pids = {r["pid"] for r in rows if r.get("pid") and r["stage"] == "AUCTION_SOLD"}
    from_deeds, sample = deed_rows(parcels, today, former, changes)
    json.dump(sample, open(os.path.join(OUT, "grantor-sample.json"), "w"), indent=1)
    for r in from_deeds:
        if r["pid"] in confirmed_pids:
            continue
        e = seen.setdefault(r["lot_id"], {"first_seen": now_iso(), "lot": {"sale_date": r["sale_date"], "county": "King George", "address": r["address"],
                                                                         "zip": "", "source": r["source"], "deed_only": True}})
        r["first_seen"] = e["first_seen"]
        rows.append(r)

    for r in rows:
        r["id"] = "surplus:" + r["lot_id"]
        r["is_new"] = r["first_seen"][:10] == today.isoformat()
        sold = r["stage"] != "AUCTION_SCHEDULED"
        win, note, deadline = collection_window(r["kind"], r["sale_date"], today, r.get("court_order_date") or None) if sold else (None, None, None)
        r.update({"collection_window": win, "collection_note": note, "claim_deadline": deadline})
        r["archive"] = bool(sold and (today - dt.date.fromisoformat(r["sale_date"])).days > KEEP_SOLD_DAYS)
        if r["archive"]:
            r["archive_bucket"] = ("Court window: still claimable" if win == "COURT_2YR" else "Paid to the county" if win == "PAID_TO_COUNTY"
                                   else "Likely at the Treasury" if win == "TREASURY_LIKELY" else "Trustee or court")
    rank = {"STRONG": 0, "POSSIBLE": 1, "UNCONFIRMED": 2, "UNRATED": 3}
    rows.sort(key=lambda r: (rank.get(r["tier"], 9), -(r["surplus_est"][1] if r.get("surplus_est") else 0), r.get("sale_date") or ""))
    live, archive = [r for r in rows if not r["archive"]], [r for r in rows if r["archive"]]
    counts = {"listed_in_target_counties": len(lots), "kept": len(live), "archive": len(archive), "below_bar_or_dropped": len(dropped),
              "strong": sum(r["tier"] == "STRONG" for r in live), "new_today": sum(r["is_new"] for r in live),
              "scheduled": sum(r["stage"] == "AUCTION_SCHEDULED" for r in live), "auction_sold": sum(r["stage"] == "AUCTION_SOLD" for r in live),
              "tax_sale_sold": sum(r["stage"] == "TAX_SALE_SOLD" for r in live),
              "deed_scan_candidates": sum(1 for r in live if r["from_deed"] and r["kind"] == "FORECLOSURE")}
    summary = dict(counts, generated_at=now_iso(), sales_listed_statewide=sum(v.get("statewide", 0) for v in status.values()),
                   feeds_ok=all(v.get("ok") for v in status.values()))
    json.dump({"generated_at": now_iso(), "summary": summary, "counts": counts, "feeds": status, "dropped": dropped,
               "note": "Estimates, not balances. A payoff is never published; these are ranges from the notice, the owner's purchase and the deposit.",
               "rows": live}, open(OUT_PATH, "w"), separators=(",", ":"))
    json.dump({"generated_at": now_iso(), "note": "Sold more than 180 days ago. Bucketed by where the money is likely to be, by age.",
               "rows": archive}, open(ARCHIVE_PATH, "w"), separators=(",", ":"))
    json.dump({"lots": seen}, open(SEEN_PATH, "w"), separators=(",", ":"), sort_keys=True)
    log.info("surplus board: %s", counts)
    return live


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    build(do_fetch=not ap.parse_args().no_fetch)
