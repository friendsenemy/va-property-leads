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
