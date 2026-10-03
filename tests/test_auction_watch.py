import datetime as dt

from engine import auction_watch as a

TODAY = dt.date(2026, 10, 3)


def parcel(**kw):
    p = {"pid": 1, "pin": "1 1", "parcel": "1-1", "owner": "DOE JOHN A OR JANE B", "owner_type": "INDIVIDUAL", "owner_subtype": "",
         "mail_addr": "100 OAK LN", "mail_city": "KING GEORGE", "mail_state": "VA", "mail_zip": 22485, "site_addr": "100 OAK",
         "legal": "LOT 1", "acres": 1.0, "total_value": 300000, "impr_value": 220000, "year_built": 1995, "deed_book": 300, "deed_page": 0,
         "sale_year": 2018, "sale_month": 5, "sale_day": 1, "sale_price": 150000, "grantor_note": "GRANTOR: SMITH", "remark1": "", "remark2": "", "card_url": ""}
    p.update(kw)
    return p


def lot(**kw):
    l = {"lot_id": "x-1", "source": "Test", "source_url": "", "county": "King George", "address": "100 Oak Ln", "city": "King George",
         "zip": "22485", "sale_date": "2026-11-17", "sale_time": "12:00 pm", "trustee": "T"}
    l.update(kw)
    return l


def test_cgd_rows_and_cancelled_flag():
    text = ("Street Address;City State ZIP;Deposit;Sale Date;More Info;Cancelled\n"
            "2825 Mountain View Road;Stafford, VA 22556;$7000.00;11/17/2026 12:00 pm;462808;NO\n"
            "1 Main St;King George, VA 22485;$20000.00;12/01/2026 11:00 am;1;YES\n")
    rows = a.parse_cgd(text)
    assert rows[0]["county"] == "Stafford" and rows[0]["sale_date"] == "2026-11-17" and rows[0]["deposit"] == 7000 and not rows[0]["cancelled"]
    assert rows[1]["county"] == "King George" and rows[1]["cancelled"]


def test_street_key_drops_the_suffix_like_the_county_does():
    assert a.street_key("13192 Laurel Ln") == ("13192", "LAUREL")
    assert a.street_key("16287 Dickinsons Corner Drive") == ("16287", "DICKINSONS CORNER")
    assert a.street_key("PO Box 3") is None


def test_estimate_is_a_range_and_strong_needs_the_high_end():
    lo, mid, hi, basis = a.estimate_payoff(150000, 2018, 2026)
    assert lo < mid < hi and "purchase" in basis
    assert a.tier_for(hi + 30000, (lo, mid, hi))[0] == "STRONG" if hi + 30000 >= hi * 1.3 else True
    assert a.tier_for(mid + 12000, (lo, mid, hi))[0] == "POSSIBLE"
    assert a.tier_for(mid, (lo, mid, hi))[0] is None
    # the notice's own loan amount wins over the purchase-price fallback
    assert "sale notice" in a.estimate_payoff(150000, 2018, 2026, mortgage=240000, mortgage_year=2021)[3]


def test_scheduled_sale_uses_the_owner_snapshot():
    p = parcel()
    row = a.scheduled_row(lot(), p, {"snap": a.snapshot(p)}, TODAY)
    assert row["stage"] == "AUCTION_SCHEDULED" and row["tier"] == "STRONG"
    assert row["mail"].startswith("100 OAK LN") and "survivorship" in row["held_as"]
    assert a.scheduled_row(lot(county="Stafford"), None, {}, TODAY)["tier"] == "UNRATED"


def test_sold_lead_keeps_the_former_owner_and_drops_owner_sales_and_credit_bids():
    before = parcel()
    e = {"snap": a.snapshot(before)}
    after = parcel(owner="BUYER LLC", sale_year=2026, sale_month=11, sale_day=20, sale_price=260000, grantor_note="SUBSTITUTE TRUSTEE")
    row, why = a.sold_row(lot(), after, e, dt.date(2026, 12, 20), {}, {})
    assert row and row["former_owner"] == "DOE JOHN A OR JANE B" and row["buyer_on_record"] == "BUYER LLC" and row["tier"] == "STRONG"
    # the county's note does not say trustee: never strong
    row, _ = a.sold_row(lot(), parcel(owner="BUYER LLC", sale_year=2026, sale_month=11, sale_day=20, sale_price=260000), e, dt.date(2026, 12, 20), {}, {})
    assert row["tier"] == "POSSIBLE"
    # the owner sold before the sale date: no surplus
    assert a.sold_row(lot(), parcel(owner="NEW OWNER", sale_year=2026, sale_month=11, sale_day=1, sale_price=290000), e, TODAY, {}, {})[0] is None
    # the lender took it back
    assert a.sold_row(lot(), parcel(owner="SECRETARY OF VETERANS AFFAIRS", sale_year=2026, sale_month=11, sale_day=20, sale_price=1000), e, TODAY, {}, {})[0] is None


def test_special_commissioner_deed_is_a_tax_sale_and_family_trusts_are_not_foreclosures():
    ps = [parcel(pid=8391, owner="5406 CHATTERTON LANE LLC", sale_year=2026, sale_month=6, sale_day=23, sale_price=165000, total_value=120000, impr_value=0,
                 grantor_note="MARGARET F HARDY SPECIAL COMMISSIONER ON BEHALF OF SANDRA FLOURANCE"),
          parcel(pid=2, owner="DOE JOHN", sale_year=2026, sale_month=5, sale_day=1, sale_price=400000, grantor_note="BOSTJANICK FAMILY LIVING TRUST")]
    rows, sample = a.deed_rows(ps, TODAY, {8391: {"mail_addr": "6027 27TH ST N", "mail_city": "ARLINGTON", "mail_state": "VA", "mail_zip": "22207", "taxes_owed": "1466.29", "source": "x"}}, {})
    assert len(rows) == 1 and sample["special_commissioner_deeds"] == 1
    r = rows[0]
    assert r["stage"] == "TAX_SALE_SOLD" and r["former_owner"] == "Sandra Flourance" and r["tier"] == "STRONG" and r["surplus_est"][0] > 150000
    assert "ARLINGTON" in r["mail"]
    # a price several times the assessment is kept, but never strong until the deed is read
    ps[0]["total_value"] = 26100
    assert a.deed_rows(ps, TODAY, {}, {})[0][0]["tier"] == "POSSIBLE"


def test_tax_sale_window_is_two_years_then_the_county():
    assert a.collection_window("TAX", "2026-06-23", TODAY)[::2] == ("COURT_2YR", "2028-06-23")
    assert a.collection_window("TAX", "2023-06-23", TODAY)[0] == "PAID_TO_COUNTY"
    assert a.collection_window("FORECLOSURE", "2026-08-01", TODAY)[0] == "TRUSTEE_HOLDS"
    assert a.collection_window("FORECLOSURE", "2025-08-01", TODAY)[0] == "TRUSTEE_OR_COURT"
    assert a.collection_window("FORECLOSURE", "2022-08-01", TODAY)[0] == "TREASURY_LIKELY"
