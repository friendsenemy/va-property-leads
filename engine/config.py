"""Every tunable for the engine lives here.

One county per process. King George is the default; set the environment variable
VAPL_COUNTY=westmoreland to run the same engine for Westmoreland County. The county
block at the bottom of this file overrides what differs (endpoint, field adapter,
places, where the data goes).
"""
import hashlib
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = os.environ.get("VAPL_COUNTY", "king-george").strip().lower()

COUNTY = "King George"
STATE = "VA"
DATA_DIR = os.path.join(ROOT, "data")                     # King George's boards live at the top of data/
DB_PATH = os.path.join(ROOT, ".cache", "kg.sqlite")
OBITS_DIR = os.path.join(ROOT, "data", "obits")           # death sources are shared by every county
MIN_PARCELS = 10000                                       # refuse to overwrite the index with fewer than this
SOURCE_FIELDS = None                                      # None = ask the layer for the keys of FIELDS
ADAPT = None                                              # county hook: raw layer attributes -> FIELDS-shaped attributes
REGION_PLACES = set()                                     # extra places an obituary may give for a resident
HAS_TREASURER_WALK = True
MIN_PAST_DUE = 0                                          # smallest balance that makes a delinquent lead
NO_DEED_DATES = False                                     # True where the parcel record has no sale / transfer date

# King George County open data (ArcGIS Online). The item's licence is a warranty
# disclaimer only; anonymous query is enabled. See docs/sources-and-terms.md.
PARCELS_URL = ("https://services2.arcgis.com/S8zMJrpz61FbvL5t/arcgis/rest/services/"
               "Parcels/FeatureServer/0")
PAGE_SIZE = 2000
REQUEST_PAUSE_S = 1.0
USER_AGENT = "va-property-leads/1.0 (+https://github.com/friendsenemy/va-property-leads)"

# Source field -> column in the index. Only what the tool uses.
FIELDS = {
    "PID": "pid", "PIN": "pin", "PINNOSPACE": "pin_nospace", "PARCEL": "parcel",
    "LNAM": "lnam", "FNAM": "fnam",
    "ADD1": "mail_addr", "ADD2": "mail_addr2", "CITY": "mail_city", "STATE": "mail_state", "ZIP5": "mail_zip",
    "PHYSICALAD": "site_addr", "HSENUM": "site_num", "STRT": "site_street",
    "ACRE": "acres", "DESC1": "legal", "TOTLD": "land_value", "IMPRV": "impr_value", "TOTPR": "total_value",
    "YRBLT": "year_built", "COND": "cond", "DWELL": "dwellings", "REM1": "remark1", "REM2": "remark2",
    "DBOOK": "deed_book", "DPAGE": "deed_page", "WBOOK": "will_book", "WPAGE": "will_page",
    "GRNTR": "grantor_note", "SELLP": "sale_price", "MOSLD": "sale_month", "DASLD": "sale_day", "YRSLD": "sale_year",
    "GISPCLink": "card_url",
}

# Mailing cities that are inside King George County. Anything else in VA is
# "out of county"; any other state is "out of state".
KG_CITIES = {"KING GEORGE", "DAHLGREN", "DOGUE", "JERSEY", "NINDE", "ROLLINS FORK", "SEALSTON",
             "SHILOH", "OWENS", "PASSAPATANZY", "EDGEHILL", "WEEDONVILLE", "FAIRVIEW BEACH", "KING GEORGE COUNTY"}
KG_ZIPS = {22485, 22448, 22451, 22481, 22526, 22544, 22547}

# --- title signals ---------------------------------------------------------
# YRSLD/MOSLD/DASLD is the last ownership change the assessor recorded (deed, will
# or survivorship). Two values are fillers for "unknown", not real dates: the year
# 1900, and 11/23/2023 (147 parcels, mostly on the county's oldest deed books).
UNKNOWN_SALE_YEARS = {0, 1900}
PLACEHOLDER_SALE_DATES = {(2023, 11, 23)}
# DBOOK with a DPAGE is a deed book and page. The clerk moved to instrument numbers
# about 2006 (book ~620); after that DPAGE is 0 and DBOOK is the instrument number
# within the sale year. A small DBOOK is NOT by itself an old deed.
LAST_DEED_BOOK = 620
OLD_TITLE_YEARS = (40, 25, 12)          # S1 / S2 / S3 thresholds, years since last transfer
ASSESSOR_NOTE_RECENT_YEARS = 3          # an assessor death/will note this recent is its own lead

# Title weight by lead class (see README "Classes").
CLASS_WEIGHT = {
    "E1": 60,   # estate / deceased / executor on title
    "E2": 60,   # heirs on title
    "E3": 40,   # life estate
    "C1": 45,   # et al co-owners
    "W1": 45,   # list-of-heirs reference on the parcel
    "W2": 35,   # will-book reference on the parcel
    "N1": 40,   # assessor note records a death (DOD) on this parcel
    "N2": 30,   # assessor note: title passed by will
}
AGE_POINTS = ((40, 20), (25, 14), (12, 7))
ABSENTEE_POINTS = {"OUT_OF_STATE": 10, "OUT_OF_COUNTY": 7, "MAIL_DIFFERS": 5}
CARE_OF_POINTS = 6
POOR_COND_POINTS = 5
MULTI_PARCEL_POINTS = 4                 # owner group holds 2+ parcels


# ============================== Westmoreland County ==============================
# The county's open "PARCELS" layer carries owner, mailing address, deed book/page and
# the tax-map number, and nothing else: no values, no sale date or price, no grantor,
# no will reference, no year built. Everything that needs those stays blank here, and
# the boards say so. Unpaid taxes come from the Treasurer's own Open Tax List (a PDF the
# county publishes), not from a parcel-by-parcel walk.
_WM_DEED = re.compile(r"(?:D[BN]|BD)?\s*#?\s*(\d{1,4})\s*(?:/|P[GF]?\.?|PAGE)?\s*#?\s*(\d{1,5})", re.I)


def _wm_owner(name):
    """'DOVE, SAVANNAH R' -> 'DOVE SAVANNAH R' (the county's LAST, FIRST); a comma later in
    the line separates people, which King George writes as ';'."""
    name = re.sub(r"\s+", " ", name or "").strip()
    m = re.match(r"^((?:ESTATE OF |EST OF )?[A-Z'\-]+),\s*(.*)$", name)
    if m:
        name = f"{m.group(1)} {m.group(2)}"
    name = re.sub(r"\bLIFE\s+EST(?:ATE)?\b(?=\s*\S)", "LIFE ESTATE;", name)       # words after "LIFE ESTATE" are the remaindermen
    return name.replace(",", ";")


def adapt_westmoreland(a):
    g = lambda k: re.sub(r"\s+", " ", str(a.get(k) or "")).strip()
    join = g("PARCELJOIN")
    owner = _wm_owner(g("NAME1"))
    if not join:
        return {"PID": 0}                                   # roads, water, unnamed slivers
    # A parcel with a map number and no owner is kept: the layer leaves the owner blank for
    # nearly all of the Town of Colonial Beach, and the Treasurer's tax list names them.
    book, page = 0, 0
    m = _WM_DEED.search(g("DEED_PAGE"))
    if m:
        book, page = int(m.group(1)), int(m.group(2))
    acres = re.match(r"[\d.]+", g("ACREAGE"))
    site = g("F911_ADDR2") or g("F911_ADDR1")
    if site.isdigit() and g("F911_ROAD"):                   # some rows keep the house number and the road apart
        site = f"{site} {g('F911_ROAD')}"
    elif site.isdigit():
        site = ""
    num = re.match(r"\d+", site)
    return {
        # no stable numeric id is published, so one is derived from the tax-map number
        "PID": int(hashlib.sha1(join.encode()).hexdigest()[:8], 16) % 2_000_000_000 or 1,
        "PIN": (a.get("PARCEL_ID_") or "").strip(), "PINNOSPACE": join, "PARCEL": g("MAP_ID") or g("PARCEL_ID_"),
        "LNAM": owner, "FNAM": " ".join(x for x in (_wm_owner(g("NAME2")), _wm_owner(g("NAME3"))) if x),
        "ADD1": g("MAIL_ADDR1"), "ADD2": g("MAIL_ADDR2"), "CITY": g("MAIL_ADDR3"), "STATE": g("MAIL_ADDR4")[:2], "ZIP5": g("ZIP")[:5],
        "PHYSICALAD": site, "HSENUM": num.group(0) if num else "", "STRT": site[len(num.group(0)):].strip() if num else site,
        "ACRE": acres.group(0) if acres else None, "DESC1": " · ".join(x for x in (g("AREA"), g("LOT_COVER"), "treasurer acct " + g("ACCT_NO") if g("ACCT_NO") not in ("", "0") else "") if x),
        "DBOOK": book, "DPAGE": page, "GRNTR": "", "REM1": g("DEED_PAGE") if not m else "", "REM2": "",
        "GISPCLink": "https://eservices.westmoreland-county.org/applications/ViewPropertyCards/webform1.aspx",
    }


if KEY == "westmoreland":
    COUNTY = "Westmoreland"
    PARCELS_URL = "https://services5.arcgis.com/uEb6ucnhLOwh4rfI/arcgis/rest/services/PARCELS/FeatureServer/0"
    DATA_DIR = os.path.join(ROOT, "data", "westmoreland")
    DB_PATH = os.path.join(ROOT, ".cache", "westmoreland.sqlite")
    MIN_PARCELS = 18000
    SOURCE_FIELDS = "*"
    ADAPT = adapt_westmoreland
    HAS_TREASURER_WALK = False
    KG_CITIES = {"MONTROSS", "COLONIAL BEACH", "HAGUE", "KINSALE", "OLDHAMS", "COLES POINT", "MOUNT HOLLY", "MT HOLLY", "OAK GROVE",
                 "SANDY POINT", "STRATFORD", "TEMPLEMANS", "ZACATA", "LERTY", "BALDWIN", "TUCKER HILL", "WESTMORELAND"}
    KG_ZIPS = {22443, 22469, 22488, 22520, 22529, 22558, 22577, 22581, 22442, 22524}
    REGION_PLACES = set(KG_CITIES) | {"WESTMORELAND COUNTY", "NOMINI", "MACHODOC", "LEEDSTOWN", "POTOMAC BEACH", "ERICA"}
    LAST_DEED_BOOK = 0                  # no sale dates in the layer, so a deed book cannot be turned into a year
    NO_DEED_DATES = True
    MIN_PAST_DUE = 150                  # the list carries hundreds of balances of a few dollars
elif KEY != "king-george":
    raise SystemExit(f"unknown county '{KEY}': use king-george or westmoreland")
