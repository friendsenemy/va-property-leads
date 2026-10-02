# VA Property Leads

Public-record lead generator for **King George County, Virginia**, built the same way as
[md-property-leads](https://github.com/friendsenemy/md-property-leads): scheduled GitHub
Actions read free public records and commit JSON; a static dashboard on GitHub Pages
reads it. No server, no paid data, no credentials in the repo.

**Dashboard:** https://pagesofpurposellc.com/va-property-leads/

## What runs, and when

| Workflow | Schedule | What it does |
|---|---|---|
| `nightly-parcels.yml` | every night, 3:17 AM ET | Pulls the county's Parcels open-data layer (8 requests) into SQLite, classifies every owner, runs the title scan, commits `data/parcels.json` and `data/title/` |

Everything can also be run by hand from the Actions tab.

## Title Leads: what is on the board

The board shows **owners**, not parcels. A row is one owner (same name and mailing
address) with every parcel they hold listed inside it. Only opportunities are shown.

| Class | Meaning | Source field |
|---|---|---|
| **E1** Estate on title | Owner text names an estate, a decedent or an executor | `LNAM` / `FNAM` |
| **E2** Heirs on title | Owner text says "heirs of" | `LNAM` / `FNAM` |
| **E3** Life estate on title | A life tenant with remaindermen. The life tenant may be alive. | `LNAM` / `FNAM` |
| **C1** Et al co-owners | "ET AL", "ETALS": several owners, usually family who inherited | `LNAM` / `FNAM` |
| **W1** List of Heirs on file | The parcel's will field points at a List of Heirs | `WBOOK` = `LH` |
| **W2** Title passed by will | The parcel carries a will book and page | `WBOOK` / `WPAGE` |
| **N1** Death noted by assessor | The assessor's note on the parcel records a date of death in the last 3 years | `GRNTR` ("... DOD 02/20/2024") |
| **N2** Will noted by assessor | The assessor's note says the parcel passed by will in the last 3 years | `GRNTR` |

Priority is the class weight plus: years since the last recorded transfer (12 / 25 / 40+),
tax bill mailed out of state or out of the county, a care-of line, a building the
assessor rates fair or poor, and more than one parcel. Every point is listed in the lead.
Weights are in `engine/config.py`.

**Held back, never shown:** individuals and trusts whose only signals are a 40-year-old
title and a tax bill mailed elsewhere (`data/title/watch.json`). They go on the board
when a death or a delinquency record supports them.

## Three things about the county's data that are easy to get wrong

1. **A small deed-book number is not an old deed.** `DBOOK` with a `DPAGE` is a deed book
   and page. About 2006 (book ~620) the Clerk switched to instrument numbers; after that
   `DPAGE` is 0 and `DBOOK` is the instrument number within the sale year. "DBOOK 216,
   DPAGE 0, sold 2023" is instrument 216 of 2023. Of 3,006 polygon rows with `DBOOK`
   under 300, 1,169 are recent instruments. Title age comes from the sale date.
2. **11/23/2023 and 1900 are filler sale dates.** 147 parcels carry 11/23/2023, mostly on
   the county's oldest deed books. Those are treated as undated, and the deed book gives
   the era.
3. **The layer has 15,056 rows but 14,435 parcels.** 291 rows are right-of-way, water and
   "NoData" polygons with no assessment record (these are the "blank owner" rows), and
   330 are extra polygons of multi-part parcels.

## Owner types

Every owner is put in exactly one type, first match wins: estate family → et al → trust →
church → cemetery → government → association → business → individual. Organisations are
matched on phrases, never on a bare word: `JEFFERY A TEMPLE LIVING TRUST` is a trust,
`FOUNDATION PROPERTIES LLC` is a business, `CHURCH MICHAEL JOE` is a person. Two named
exceptions to the order: trustees *of a church* are a church, and a bank's trust company
is a business. The raw owner text is kept on every row. `tests/test_owner_parse.py` holds
the real strings that drove each rule.

"A OR B" (Virginia's survivorship shorthand), "A & B" and ";" are split and each person
is kept separately for the death match.

## Files

| Path | |
|---|---|
| `engine/parcels.py` | nightly pull → `.cache/kg.sqlite` (not committed) + `data/parcels.json` + `data/owner-changes.json` (owner / deed changes since the last pull) |
| `engine/owner_parse.py` | owner taxonomy and name splitting |
| `engine/title_scan.py` | signals, classes, scoring → `data/title/` |
| `engine/config.py` | endpoint, field map, every weight and threshold |
| `index.html`, `static/` | the dashboard; status and notes are stored in your browser |
| `docs/virginia-law.md` | the Code of Virginia sections this is built on, with what was verified |
| `docs/sources-and-terms.md` | every source, what its terms allow, and what is deliberately not automated |

## Run locally

```bash
pip install -r requirements.txt
python -m engine.parcels        # 8 requests, ~15 seconds
python -m engine.title_scan
python -m http.server 8000      # open http://localhost:8000
python -m pytest tests -q
```

Property records are public. This tool reads how title is recorded; it does not know who
is alive, who the heirs are, or what is owed. Verify in the Clerk's records before you
contact anyone.
