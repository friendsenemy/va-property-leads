from engine import config, delinq_list

FEB = """CURRENT DATE:     2/02/2026                                 OPEN TAX LIST                                                    PAGE    1
NAME                                   MAP#                                 TYPE YEAR       TICKET    TAX OWED   PENALTY DUE   INTEREST DUE   TOTAL DUE           STATUS
----                                   ----                                 ---- ----       ------    --------   -----------   ------------   ---------           ------


AASEBY ERNEST ARDELL                    39B   2        1                     RE   2025   533440001      28.56          2.86            .79       32.21


587 SALISBURY PARK ROAD
HAGUE VA                       22469


ABBOTT SONYA, CHARLES JOHNSON &         21            39B                    RE   2025   533480001     919.36         91.94          25.28    1,036.58
ROBERT JOHNSON                                                               RE   2024   382710001     919.36         91.94         126.41    1,137.71
186 LEES MILL RD
                                                                                           TOTAL     1,838.72        183.88         151.69    2,174.29
GATES NC                       27937                                         RE   2023   111110001     100.00         10.00           5.00      115.00
"""


def test_open_tax_list_blocks_tickets_and_addresses():
    listed, rows = delinq_list.parse(FEB)
    assert listed == "2026-02-02" and set(rows) == {"39B21", "2139B"}
    a = rows["2139B"]
    assert a["name"] == "ABBOTT SONYA, CHARLES JOHNSON & ROBERT JOHNSON"
    # a ticket printed beside the city line belongs to the same parcel, not to a parcel called "GATES NC"
    assert [t["year"] for t in a["tickets"]] == [2025, 2024, 2023] and round(sum(t["total"] for t in a["tickets"]), 2) == 2289.29
    assert a["mail"] == {"addr": "186 LEES MILL RD", "city": "GATES", "state": "NC", "zip": "27937"}
    assert rows["39B21"]["mail"]["city"] == "HAGUE"


def test_westmoreland_owner_names_are_put_in_the_engines_form():
    assert config._wm_owner("DOVE, SAVANNAH R") == "DOVE SAVANNAH R"
    assert config._wm_owner("ESTATE OF NICHOLS, MAY F") == "ESTATE OF NICHOLS MAY F"
    assert config._wm_owner("BYRD HOWARD, ROBERT HUNTER & ET ALS") == "BYRD HOWARD; ROBERT HUNTER & ET ALS"


def test_westmoreland_adapter_keeps_unnamed_parcels_and_reads_the_deed_reference():
    a = config.adapt_westmoreland({"PARCELJOIN": "3776", "PARCEL_ID_": "37 76", "MAP_ID": "37-76", "NAME1": "WOOD, CHARLES B & DANA R", "ACCT_NO": "3946",
                                   "MAIL_ADDR1": "15884 RICHMOND RD", "MAIL_ADDR3": "CALLAO", "MAIL_ADDR4": "VA", "ZIP": "22435",
                                   "DEED_PAGE": "DB 988 PG 782", "ACREAGE": "19.851 AC", "F911_ADDR1": "62", "F911_ROAD": "DARL CIRCLE"})
    assert a["LNAM"] == "WOOD CHARLES B & DANA R" and (a["DBOOK"], a["DPAGE"]) == (988, 782) and a["PHYSICALAD"] == "62 DARL CIRCLE" and a["ACRE"] == "19.851"
    blank = config.adapt_westmoreland({"PARCELJOIN": "3A315C24", "PARCEL_ID_": "3A3 1 5C 24", "NAME1": " "})
    assert blank["PID"] > 0 and blank["LNAM"] == ""
    assert config.adapt_westmoreland({"PARCELJOIN": " "}) == {"PID": 0}
