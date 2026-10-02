# Sources and what their terms allow

Rule for this repo: a scheduled job only touches a source whose terms and robots.txt do
not forbid automated use. Everything below was read on 2026-10-01. "Silent" means no
terms page exists and robots.txt does not disallow the path; those are used at a low,
polite rate.

## Used by scheduled jobs

| Source | What we take | Terms | How often |
|---|---|---|---|
| King George County open data, **Parcels** layer (`services2.arcgis.com/S8zMJrpz61FbvL5t/.../Parcels/FeatureServer/0`) | The whole assessment table: owner, mailing address, values, deed and will references | **Allowed.** The item's licence is a warranty disclaimer only ("provided all GIS data for informational purposes only"). Anonymous query is enabled; it is the official API. | Nightly, 8 requests |
| **Storke Funeral Home** (King George, Colonial Beach, Bowling Green; includes Nash & Slaw) | Obituary name, dates, text | **Silent, permissive.** No terms page; robots.txt is `Disallow:` (empty). The site publishes an official obituary RSS feed. Archive starts November 2018. | Daily (RSS, 1 request). One-time backfill of ~2,700 pages at one request every 2 seconds. |
| King George **Treasurer Real Estate Public Inquiry** (`eservices.kinggeorgecountyva.gov`) | Balance due per parcel | **Silent.** The click-through statement is an SSN / liability disclaimer with no clause on automated or commercial use; no robots.txt. | Monthly, in four nightly shards; one request per parcel, then a 1.5 s pause |
| **National Archives, NUMIDENT death files** (AAD search, `aad.archives.gov`) | Deaths 1988-2007 with a King George residence ZIP: name, dates of birth and death, ZIP. SSNs are dropped. | **Allowed.** Public-use federal record, use unrestricted; no login, no robots.txt, no clause on automated use. Paced at archives.gov's requested 10-second crawl delay. | Once (the series ends in 2007) |
| **Sands Anderson PC** tax-sale page (King George's collection counsel) | Upcoming King George auctions | **Silent, permissive for HTML.** robots.txt disallows PDFs and search, so only the HTML page is read. | Weekly, 1 request |

## Not automated, and why

| Source | Verdict | What the tool does instead |
|---|---|---|
| **Legacy.com** | Forbidden: "you may not ... access the Services with any robot, spider, web crawler, extraction software, or any other automated process". It also returns 403 to an ordinary, honestly identified client. | Not fetched. Deaths read there by hand go in `data/obits/manual.csv`. |
| **The Free Lance-Star** (fredericksburg.com) | Forbidden: "Use automated scripts to collect information from ... the Site". Its obituaries redirect to Legacy.com. | Not used. |
| **Covenant Funeral Service**, **Welch Funeral Home**, **Tribute Archive** (Tribute Technology) | Forbidden: no "robot, spider, scraper, crawler or other automated means ... without our express written permission". | Not used. |
| **Mullins & Thompson** (Dignity Memorial) | Forbidden. | Not used. |
| **Found and Sons** | No terms, but the site sits behind a Cloudflare bot challenge. Getting past a bot challenge is not something this tool does. | Not used. |
| **SmallTownPapers** (King George Journal archive) | Forbidden: no "computer programs that automatically download or export Content", and no commercial use without a licence. | By hand; this is the best manual source for 2008-2017. |
| **Virginia death index** (VDH via Ancestry), **FamilySearch** | Login and terms that bar automated use. | Per-lead lookups by hand. |
| **Public Death Master File** (2013 copy on archive.org) | Reachable, but it has no ZIP or state, so matching would be on name alone against the whole country. | Not used: too many false matches. |
| **Find a Grave**, **BillionGraves**, **Echovita** | Forbidden. | Per-lead lookups by hand only. |
| **Virginia SCC Clerk's Information System** | robots.txt is `Disallow: /` for everything but named search engines; bulk data is a paid subscription. | Each LLC / corporation lead carries a link to look the entity up by hand. `engine/scc_import.py` parses what you paste back. |
| **Virginia courts case information (OCIS 2.0)** | Forbidden: no "automated scripting against the system". | Not used. |
| **Circuit Court Clerk land records (Secure Remote Access)** | Subscription agreement bars bulk and automated access. | By hand on top leads; `engine/heirs_import.py` parses a pasted index result. |
| **vamoneysearch.gov** | No terms found, but the search is protected by a bot check. | By hand. |

## Other obituary data

The matcher reads every file in `data/obits/`. This repo does not contain code to get
past a site's bot block; data from any other source can be dropped in as a file.
