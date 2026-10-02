"""Every tunable for the King George County, Virginia engine lives here."""

COUNTY = "King George"
STATE = "VA"

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
