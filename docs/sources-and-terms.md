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
| **Westmoreland County "PARCELS" layer** (`services5.arcgis.com/uEb6ucnhLOwh4rfI/.../PARCELS/FeatureServer/0`) | Owner, mailing address, deed book and page, tax-map number for 27,000 parcels | **Allowed.** The county's own GIS app; its splash is a liability disclaimer only, nothing on automated or bulk use; anonymous query is enabled. | Nightly, 14 requests |
| **Westmoreland Treasurer's Open Tax List** (PDF linked from `westmoreland-county.org/186/Treasurers-Office`) | Every parcel with unpaid real estate tax: name, map number, year, tax, penalty, interest | **Allowed.** A document the county publishes for the public; robots.txt disallows only admin, search and map pages. | Mondays, 2 requests |
| **Census Bureau TIGER/Line 2024 "area water"** (`www2.census.gov/geo/tiger/TIGER2024/AREAWATER/`) | Water polygons for each county, used to find waterfront parcels | **Allowed.** U.S. government work, public domain. | By hand, one file per county |
| **Samuel I. White, P.C.** sale list (`siwpc.net/AutoUpload/Sales.pdf`) | Scheduled foreclosure sales statewide: address, city, ZIP, sale date, time and place, firm file number | **Allowed.** robots.txt: "User-agent: * Allow: /". The report's own header: "Users of this information agree they will assume sole reliance for its use." The site's terms page loads its text by script and could not be read; nothing found that bars automated reading. | One request, weekday mornings |
| **Cohn, Goldberg & Deutsch, LLC** Virginia list (`cgd-law.com/va/data/sales.csv`) | Scheduled sales: address, ZIP, bidder's deposit, sale date, cancelled flag | **Allowed.** robots.txt disallows only `/wp-admin/`; no terms page; the list is offered for download, "as a courtesy to its users for informational purposes only". | One request, weekday mornings |
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
| **Virginia Press Association notices** (publicnoticevirginia.com) | Forbidden: "You may not engage in any screen scraping, database scraping, or spidering", with liquidated damages per notice. | By hand. This is where the full notice text is: borrower, deed of trust date and book/page, original loan amount. Type what you read into `data/surplus/notices.csv`. |
| **Brock & Scott, PLLC** sale list | Terms allow copying only for "personal, noncommercial use, absent the prior written approval". A lead tool for a home-buying business is commercial. | Not automated. It lists King George, Stafford, Spotsylvania, Caroline and Westmoreland sales by county; read it by hand and enter sales in `notices.csv`, or ask the firm for written approval and it can be added. |
| **Glasser & Glasser** | Forbidden: no "deep-link", "page-scrape", "robot", "spider". (It is the one list that prints the original principal.) | By hand. |
| **BWW Law Group / Aldridge Pite**, **Rosenberg & Associates**, **McCabe Weisberg & Conway**, **McMichael Taylor Gray** | Each list sits behind an "I agree" page whose terms say it "may not be downloaded, copied, published, transmitted". | By hand. |
| **LOGS Legal Group / PFC of Virginia** | Terms bar "unwanted communication" with owners or occupants. | Not used. |
| **Atlantic Law Group / Orlans** | Behind a bot challenge. | Not used. |
| **Auction.com**, **Xome**, **Hubzu**, **Harvey West** | robots.txt or terms forbid automated access. | Not used. |
| **Equity Trustees**, **Surety Trustees**, **Commonwealth Trustees** | No sale list of their own was found; they are the substitute-trustee names used by the firms above. | n/a |
| **Find a Grave**, **BillionGraves**, **Echovita** | Forbidden. | Per-lead lookups by hand only. |
| **Virginia SCC Clerk's Information System** | robots.txt is `Disallow: /` for everything but named search engines; bulk data is a paid subscription. | Each LLC / corporation lead carries a link to look the entity up by hand. `engine/scc_import.py` parses what you paste back. |
| **Virginia courts case information (OCIS 2.0)** | Forbidden: no "automated scripting against the system". | Not used. |
| **Circuit Court Clerk land records (Secure Remote Access)** | Subscription agreement bars bulk and automated access. | By hand on top leads; `engine/heirs_import.py` parses a pasted index result. |
| **vamoneysearch.gov** | No terms could be read, and the search is protected by a bot check (Cloudflare Turnstile). | By hand; every surplus lead links to it. |

## Other obituary data

The matcher reads every file in `data/obits/`. This repo does not contain code to get
past a site's bot block; data from any other source can be dropped in as a file.
