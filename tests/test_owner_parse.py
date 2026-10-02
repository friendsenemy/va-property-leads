"""Run with: python -m pytest tests -q   (cases are real King George owner strings)."""
from engine import owner_parse as op
from engine import title_scan as ts

CASES = [
    # (LNAM, FNAM, type, subtype)
    ("ROBERT MILTON CURRY JR ESTATE", "", "ESTATE", "ESTATE"),
    ("NORRIS C W ESTATE", "", "ESTATE", "ESTATE"),
    ("ESTATE OF LEONARD BLAND", "ESTATE OF CAROLYN BLAND", "ESTATE", "ESTATE"),
    ("MORGAN LAWSON;HEIRS OF", "", "ESTATE", "HEIRS"),
    ("LEWIS RUTH ASHTON;LIFE ESTATE", "GARLAND SHIRLEY ET AL", "ESTATE", "LIFE_ESTATE"),
    ("SCRANAGE CHARLES R OR ANNIE M;L EST", "WARD ELAINE S", "ESTATE", "LIFE_ESTATE"),
    ("STAFFA DOTTIE R", "NEWSOME LINDA STAFFA EXEC", "ESTATE", "FIDUCIARY"),
    ("TAYLOR EVEREDA M ETAL", "", "ET_AL", ""),
    ("HART JOHN E ET ALS", "%GREGORY K HART", "ET_AL", ""),
    ("BROWN-CAMPBELL TRACY L", "ETALS", "ET_AL", ""),
    # surname collisions from the handoff: these are NOT churches / foundations
    ("JEFFERY A TEMPLE LIVING TRUST", "", "TRUST", ""),
    ("FOUNDATION PROPERTIES LLC", "", "BUSINESS", ""),
    ("CHURCH MICHAEL JOE OR SHEILA ANN", "", "INDIVIDUAL", ""),
    ("CHURCH MAC OR SMITH ROBYN", "", "INDIVIDUAL", ""),
    ("TEMPLE TERESA C", "", "INDIVIDUAL", ""),
    ("JOHNSON JAMES TEMPLE & PHYLLIS A", "", "INDIVIDUAL", ""),
    ("BISHOP JASON ANDREW", "", "INDIVIDUAL", ""),
    ("HEALEY THOMAS E OR HOA T", "", "INDIVIDUAL", ""),
    ("LAND BRIDGET", "", "INDIVIDUAL", ""),
    # real churches, including ones held by trustees
    ("TRUSTEES MT CARMEL BAPTIST CHURCH", "", "CHURCH", ""),
    ("TRUSTEES OF LITTLE ARK BAPTIST CH", "", "CHURCH", ""),
    ("ST PAUL'S EPISCOPAL CHURCH", "", "CHURCH", ""),
    ("KING GEORGE CHURCH OF CHRIST INC", "", "CHURCH", ""),
    ("WELCH FAMILY CEMETERY", "", "CEMETERY", ""),
    ("KING GEORGE COUNTY SCHOOL BOARD", "", "GOVERNMENT", ""),
    ("COMMONWEALTH OF VIRGINIA", "DEPT OF TRANSPORTATION", "GOVERNMENT", ""),
    ("PRESIDENTIAL LAKES POA", "", "ASSOCIATION", ""),
    ("NORTH RIDGE EST.PROP.OWNERS ASSOC", "", "ASSOCIATION", ""),   # "EST." here is "Estates"
    ("LILY PAD ESTATE LLC", "", "BUSINESS", ""),
    ("HARRUP REAL ESTATE LLC", "", "BUSINESS", ""),
    ("PINEVIEW LLC", "ET ALS", "ET_AL", ""),                         # taxonomy order: et al before LLC
    ("YAGLA JON JARVIS TR", "YAGLA MAXINE ALICE SCHUTTE TR", "TRUST", ""),
    ("ELLIS MISTY D OR JACKIE LEE", "", "INDIVIDUAL", ""),
    ("", "", "BLANK", ""),
]


def test_classify():
    for lnam, fnam, typ, sub in CASES:
        assert op.classify(lnam, fnam) == (typ, sub), (lnam, fnam, op.classify(lnam, fnam))


def names(lnam, fnam=""):
    return [p["name"] for p in op.split_people(lnam, fnam)]


def test_split_people():
    op.learn_names(["SMITH ROBERT L", "JONES ROBERT", "DOE ROBERT A", "KING JACKIE", "LEE JACKIE M", "CURRY ANN", "BLAND TOM", "HALL TERESA"] * 10)
    assert names("ELLIS MISTY D OR JACKIE LEE") == ["MISTY D ELLIS", "JACKIE LEE ELLIS"]
    assert names("TRUSLOW KENNETH L & PATRICIA F") == ["KENNETH L TRUSLOW", "PATRICIA F TRUSLOW"]
    assert names("SWANSON DANIEL L OR", "SWANSON ANNA") == ["DANIEL L SWANSON", "ANNA SWANSON"]
    assert names("MCDONOUGH JOHN M OR", "GERMAN DAWN") == ["JOHN M MCDONOUGH", "DAWN GERMAN"]
    assert names("BURGESS JOHN OR WEST-BURGESS VELDA") == ["JOHN BURGESS", "VELDA WEST-BURGESS"]
    assert names("SCHWENDEMAN ROBERT LEE OR TERESA", "ANN") == ["ROBERT LEE SCHWENDEMAN", "TERESA ANN SCHWENDEMAN"]
    assert names("LEWIS RUTH ASHTON;LIFE ESTATE", "GARLAND SHIRLEY ET AL") == ["RUTH ASHTON LEWIS", "SHIRLEY GARLAND"]
    assert names("ESTATE OF LEONARD BLAND", "ESTATE OF CAROLYN BLAND") == ["LEONARD BLAND", "CAROLYN BLAND"]
    assert names("ROBERT MILTON CURRY JR ESTATE") == ["ROBERT MILTON CURRY JR"]
    assert names("HART JOHN E ET ALS", "%GREGORY K HART") == ["JOHN E HART"]     # care-of is not an owner
    assert names("FOUNDATION PROPERTIES LLC") == []


def test_will_and_deed_refs():
    assert ts.parse_will_ref("1800/", "/262", 356, 539)[:3] == ("WB", "18", "262")
    assert ts.parse_will_ref("1313/", "/686", 0, 0)[:3] == ("WB", "13", "686")
    assert ts.parse_will_ref("6 06/", "/484", 0, 0)[:3] == ("WB", "6", "484")
    assert ts.parse_will_ref("WB20/", "/569", 346, 167)[:3] == ("WB", "20", "569")
    assert ts.parse_will_ref("LH00/", "/560", 0, 0)[0] == "LH"
    assert ts.parse_will_ref("415/", "/772", 415, 772)[0] == ""      # the deed typed into the will field
    assert ts.parse_will_ref(" ", " ", 0, 0)[0] == ""
    # A small DBOOK with no page is an instrument number, not an old deed book.
    assert ts.deed_ref(216, 0, 2023) == "Instr. 216 of 2023"
    assert ts.deed_ref(251, 131, 1993) == "DB 251 PG 131"
    assert ts.deed_ref(250001786, 0, 2025) == "Instr. 250001786"


def test_placeholder_sale_date_is_unknown():
    r = {"sale_year": 2023, "sale_month": 11, "sale_day": 23, "deed_book": 30, "deed_page": 155}
    assert not ts.sale_year_known(r)
    assert ts.sale_year_known(dict(r, sale_day=24))
    assert not ts.sale_year_known(dict(r, sale_year=1900, sale_month=1, sale_day=1))


def test_note_death():
    assert ts.note_death("JOYCE R DEBERNARD DOD 02/20/2024", 2026) == ("2024-02-20", 2)
    assert ts.note_death("STEVIE R GRAY SR DOD 06-18-2026", 2026) == ("2026-06-18", 0)
    assert ts.note_death("GRANTOR: SMITH JOHN", 2026) is None


def test_obituary_name_and_lede():
    from engine import obits
    n = obits.parse_name("Ann  Ellen  Lewis")
    assert (n["first"], n["middle"], n["last"]) == ("ANN", "ELLEN", "LEWIS")
    n = obits.parse_name("Col  Florentino  Carter")
    assert (n["first"], n["last"]) == ("FLORENTINO", "CARTER")
    n = obits.split_last({"first": "FRANCES", "middle": "", "last": "LOUISE OLIVER ENSMINGER"})
    assert (n["middle"], n["maiden"], n["last"]) == ("LOUISE", "OLIVER", "ENSMINGER")
    l = obits.parse_lede("Donna Marie Derry, 75, of Colonial Beach, Virginia, passed away on July 23, 2026.")
    assert (l["age"], l["place"], l["death_date"]) == (75, "Colonial Beach", "2026-07-23")
    l = obits.parse_lede("June Jahn, 78, of King George died Friday, June 26, 2026 at home.")
    assert (l["place"], l["death_date"]) == ("King George", "2026-06-26")


def test_identity_score():
    from engine import death_match as dm
    r = {"mail_city": "KING GEORGE", "mail_zip": 22485, "sale_year": 1990, "sale_month": 5, "sale_day": 1}
    o = {"middle": "LEE", "suffix": "", "place": "King George", "age": 78}
    assert dm.score(o, {"middle": "L", "suffix": ""}, r, 1, 2026)[0] >= dm.HIGH
    assert dm.score(o, {"middle": "MATTHEW", "suffix": ""}, r, 1, 2026) is None        # different middle name
    assert dm.score(o, {"middle": "", "suffix": "JR"}, r, 1, 2026)[0] < dm.score(o, {"middle": "", "suffix": ""}, r, 1, 2026)[0]
    assert dm.score(o, {"middle": "L", "suffix": ""}, dict(r, sale_year=2027), 1, 2026) is None   # titled after the death
    assert dm.score(dict(o, age=40), {"middle": "L", "suffix": ""}, dict(r, sale_year=1995), 1, 2026) is None  # age 9 at title


def test_delinquency_rules():
    import datetime as dt
    from engine import delinquency as d
    assert d.sale_eligible_on("2023-12-05") == dt.date(2025, 12, 31)
    assert d.sale_eligible_on("2024-06-05") == dt.date(2026, 12, 31)
    rows = [{"year": 2001, "ticket": "1", "seq": "1", "due": "2001-06-05", "name": "OLD OWNER", "map": "23A577", "balance": 50.0},
            {"year": 2023, "ticket": "2", "seq": "2", "due": "2023-12-05", "name": "DOE JOHN", "map": "33105", "balance": 300.0},
            {"year": 2026, "ticket": "3", "seq": "2", "due": "2026-12-07", "name": "DOE JOHN", "map": "33105", "balance": 400.0}]
    s = d.summarise(rows, "33105", dt.date(2026, 10, 1))
    assert s["past_due"] == 300.0 and s["years"] == [2023] and s["sale_eligible"] and s["not_yet_due"] == 400.0
    assert s["tickets"] == 2                                       # the re-used account's old rows are dropped


def test_sale_notice_parser():
    from engine import sale_notices as sn
    page = ('<h2>Public Auctions for Tax Delinquent Real Estate</h2><p><a href="/assets/x/KG.pdf">NOTICE OF JUDICIAL SALE OF REAL ESTATE IN '
            'KING GEORGE COUNTY</a></p><p>Friday, November 6, 2026 at 11:00 A.M.</p><p><a href="https://bid.forsaleatauction.biz/bid/1">bid</a></p>'
            '<h2>News &amp; Insights</h2>')
    n = sn.parse_notices(page)
    assert len(n) == 1 and n[0]["locality"] == "King George" and n[0]["sale_date"] == "2026-11-06" and n[0]["list_pdf"].endswith("KG.pdf")


def test_suffix_after_semicolon_and_namesakes():
    from engine import death_match as dm
    assert names("WEBER ROBERT F;JR") == ["ROBERT F WEBER JR"]
    r = {"mail_city": "KING GEORGE", "mail_zip": 22485, "sale_year": 2013, "sale_month": 5, "sale_day": 1}
    assert dm.score({"middle": "F", "suffix": "SR", "place": "King George", "age": 80}, {"middle": "F", "suffix": "JR"}, r, 1, 2025) is None
    heirs = dict(r, sale_year=1969, owner_type="ESTATE", owner_subtype="HEIRS")
    assert dm.score({"middle": "V", "suffix": "", "place": "King George", "age": 70}, {"middle": "", "suffix": ""}, heirs, 1, 2024) is None


def test_numident_rows_drop_ssn():
    from engine import numident
    text = ('"SOCIAL SECURITY NUMBER","FIRST NAME","MIDDLE NAME","LAST NAME","SUFFIX NAME","DATE OF BIRTH (MONTH)","DATE OF BIRTH (DAY)",'
            '"DATE OF BIRTH (YEAR)","OTHER NUMBER","RESIDENCE ZIP CODE","DATE OF DEATH (MONTH)","DATE OF DEATH (DAY)","DATE OF DEATH (YEAR)"\n'
            '"123456789","CAROLYN","S","BRYANT","","02","10","1928","987654321","224851234","07","14","1999"\n')
    rows = numident.to_records(text, numident.KG_ZIPS)
    assert len(rows) == 1 and rows[0]["death_date"] == "1999-07-14" and rows[0]["age"] == 71 and rows[0]["place"] == "King George"
    assert "123456789" not in str(rows) and "987654321" not in str(rows)
