import datetime as dt

from engine import distress as d


def test_address_key_and_suffix_stripping():
    assert d.addr_key("13192 Laurel Ln, Apt 2") == ("13192", "LAUREL LN")
    assert d.strip_suffix(d.addr_key("13192 Laurel Lane")) == ("13192", "LAUREL")
    assert d.addr_key("PO Box 3") is None


def test_match_parcel_first_then_address_and_ambiguity():
    info = {1: {"total_value": 100}, 2: {"total_value": 50}, 3: {"total_value": 1}, 4: {"total_value": 1}, 5: {"total_value": 1}}
    by_addr = {("100", "OAK LN"): {1}, ("200", "ELM ST"): {2, 3, 4, 5}}
    by_pin = {"231": 2}
    idx = (by_addr, by_pin, info)
    assert d.match({"county": "King George", "parcel": "23-1", "address": "x"}, idx) == (2, "parcel")
    assert d.match({"county": "King George", "parcel": "", "street": "100 Oak Lane"}, idx) == (1, "address")
    assert d.match({"county": "King George", "parcel": "", "street": "200 Elm St"}, idx) == (None, "ambiguous")
    assert d.match({"county": "King George", "parcel": "", "street": "9 Nowhere Rd"}, idx) == (None, "unmatched")


def test_kinds_status_and_cooling():
    assert d.kind_of("Property Maintenance", "roof collapsing") == "CODE_VIOLATIONS"
    assert d.kind_of("Code Complaint", "tall grass and junk vehicle") == "NUISANCE_CASE"
    assert d.kind_of("Zoning", "sign without permit") == "ZONING_CASE"
    assert d.kind_of("Demolition Permit", "") == "DEMO_PERMIT"
    assert d.is_open("In Progress") and d.is_open("Escalated") and not d.is_open("Closed - Complied")
    today = dt.date(2026, 10, 14)
    s = d.to_signal({"county": "King George", "kind": "FIRE", "type": "FIRE", "status": "open", "opened": "2026-10-01", "case_number": "x", "source": "s"}, today)
    assert s["cooling"] and s["open"]
    s2 = d.to_signal({"county": "King George", "type": "Code Case", "status": "Citation Issued", "opened": "2026-08-01", "case_number": "y"}, today)
    assert s2["confirmed"] and s2["kind"] == "CODE_VIOLATIONS"


def test_flags_and_points_only_count_open_cases_once_per_kind():
    sigs = [{"kind": "CODE_VIOLATIONS", "open": True}, {"kind": "CODE_VIOLATIONS", "open": True}, {"kind": "FIRE", "open": True, "cooling": True},
            {"kind": "NUISANCE_CASE", "open": False}]
    flags, pts = d.flags_for(sigs)
    assert set(flags) == {"CODE_VIOLATIONS", "FIRE", "FIRE_COOLING", "STACKED_SIGNALS"} and pts == 25 + 45 + 10
