# VA Property Leads

Public-record lead generator for **King George County, Virginia**, built the same way as
[md-property-leads](https://github.com/friendsenemy/md-property-leads): scheduled GitHub
Actions read free public records and commit JSON; a static dashboard on GitHub Pages
reads it. No server, no paid data, no credentials in the repo.

**Dashboard:** https://pagesofpurposellc.com/va-property-leads/

## What runs, and when

| Workflow | Schedule | What it does |
|---|---|---|
| `nightly-parcels.yml` | every night, 3:17 AM ET | Parcels layer (8 requests) → SQLite; new obituaries from the Storke RSS feed (1 request); tax-sale notices (1 request, Mondays); then every board is rebuilt and committed |
| `monthly-delinquency.yml` | first six nights of the month, 12:30 AM ET | Treasurer balance for every parcel. Each night takes the parcels not checked in the last 20 days, oldest first (one request, then a 1.5 s pause), so a missed night is made up by the next |

Nothing needs starting by hand. When a run ends with parcels still unchecked it starts the next run itself, so the first full pass runs back to back until the county is done. Both workflows have a Run button on the Actions tab if
you want them sooner; the delinquency one has a **priority** mode that rechecks only
parcels already on a board (about an hour).

The nightly build also runs when you push one of the hand-edited files below.

## The five tabs

| Tab | Source | A row is |
|---|---|---|
| **Stacked Distress** | all of the below, joined by owner | an owner with two or more signals (death, unpaid taxes, title, the assessor's condition notes), or a house the assessor notes as unsafe, abandoned, burned, unlivable or vacant |
| **Title Leads** | the county parcel record | an owner whose title reads as an estate, heirs, life estate, et al, or carries a will / death note |
| **Death Leads** | obituaries matched to every owner name | a person who has died and is still the owner of record |
| **Delinquent** | Treasurer's inquiry | an owner with a prior year's taxes unpaid |
| **Parcel Lookup** | the full parcel index | search only; not a lead list |

A banner appears on every tab when the county's collection counsel lists a King George
tax sale. Watch states are never shown: old title with no death or delinquency behind it,
name-only obituary matches, and owners who are only late on the current bill.

## Files you edit by hand

Nothing here needs a login in the repo. Edit the file on GitHub, commit, and the board
rebuilds.

| File | What goes in it |
|---|---|
| `data/obits/manual.csv` | A death you found anywhere: `last,first,middle,suffix,death_date,age,place,url` |
| `data/obits/<name>.json` | Any other obituary source. A list of records, or `{"rows": [...]}`. Each needs a first and last name (`first`/`last`, `first_name`/`last_name`, or a `full_name`); `death_date` or `date_of_death` in any common date format; optionally `middle`, `age`, `place` or `city`, `url`. Every file in the folder is matched. |
| `data/heirs/import.csv` | A List of Heirs or heirship affidavit from the Clerk's index (searched by hand; the Clerk's agreement bars automated access). The heirs you type in show on the matched lead. |
| `data/scc/status.csv` | SCC status of a company you looked up. `data/scc/worklist.csv` lists which ones are worth looking up first. Inactive + still on title becomes an **X1** lead. |
| `data/sales/parcels.csv` | Tax map numbers from a King George tax-sale PDF (the PDF itself is not fetched) |

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

Obituary matches and unpaid taxes add to a title lead's priority (`OBITUARY_MATCH`,
`TAX_DELINQUENT`, `TAX_SALE_ELIGIBLE`).

**Held back, never shown:** individuals and trusts whose only signals are a 40-year-old
title and a tax bill mailed elsewhere (`data/title/watch.json`). When the Treasurer walk
finds a prior year unpaid on one of them it goes on the Delinquent tab as **P1**, the
profile of a death nobody reported.

## Death Leads: how identity is scored

The death is a published fact. Whether the decedent is the person on title is scored:
first and last name must match; a conflicting middle name or suffix rules it out; a
matching middle initial, the obituary's town matching the mailing address, and a name
that only one owner in the county has all add points; a title taken after the death, or
before the person was 16, rules it out. **High** is 75+, **Medium** 55–74, and anything
lower is not shown. Classes: **D1** sole owner died, **D5** every owner died, **D4** one
co-owner died.

Obituaries come from Storke Funeral Home (King George's own; archive from November 2018).
Legacy.com and the Free Lance-Star refuse automated clients and forbid them in their
terms, so they are not fetched; see `docs/sources-and-terms.md`.

## Delinquent: what the classes mean

**T1** the oldest unpaid bill is old enough that the county may sue to sell (December 31
after the second anniversary of its due date, Va. Code § 58.1-3965). **T2** a prior year
is unpaid but not yet that old. **P1** as above. The Treasurer's account number is the
parcel's `PID`; rows from before an account number was re-used are dropped by matching
the map number.

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
| `engine/obits.py` | Storke obituaries: RSS daily, listing-page backfill, facts only |
| `engine/death_match.py` | obituaries and clerk filings vs every owner name → `data/obits/matches.json` |
| `engine/delinquency.py` | Treasurer walk and join → `data/delinquency/` |
| `engine/sale_notices.py` | tax-sale counsel's auction page → `data/sales/notices.json` |
| `engine/scc_import.py`, `engine/heirs_import.py` | join what you looked up by hand |
| `engine/build_board.py` | runs all of the above in order from what is on disk |
| `engine/config.py` | endpoint, field map, every weight and threshold |
| `guide.html` | the field guide: what each tab means, a real case for each, what to check and what to say |
| `index.html`, `static/` | the dashboard; status and notes are stored in your browser |
| `engine/combined.py` | joins every signal by owner → `data/combined/leads.json` |
| `docs/code-enforcement-request.md` | why there is no violations feed, what stands in for it, and the request to send the county |
| `docs/virginia-law.md` | the Code of Virginia sections this is built on, with what was verified |
| `docs/sources-and-terms.md` | every source, what its terms allow, and what is deliberately not automated |

## Run locally

```bash
pip install -r requirements.txt
python -m engine.parcels        # 8 requests, ~15 seconds
python -m engine.build_board    # title scan + death match + delinquency join
python -m http.server 8000      # open http://localhost:8000
python -m pytest tests -q
```

Property records are public. This tool reads how title is recorded; it does not know who
is alive, who the heirs are, or what is owed. Verify in the Clerk's records before you
contact anyone.
