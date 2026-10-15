# Water/sewer FOIA requests: shut-off and zero-usage service addresses

Filed October 2026 for the three Virginia lead counties. Purpose: a free list of likely-vacant
houses (service shut off, or active meter with no usage for 2+ billing periods) to match
against the parcel index (`data/distress/manual.csv`, kind `VACANT_NOTICE`).

## The two legal points, checked against the Code of Virginia (law.lis.virginia.gov, 2026-10-15)

**1. Non-residents.** § 2.2-3704(A): "all public records shall be open to citizens of the
Commonwealth, representatives of newspapers and magazines with circulation in the Commonwealth,
and representatives of radio and television stations broadcasting in or into the Commonwealth."
A Maryland resident has no enforceable right and cannot sue under § 2.2-3713 if ignored. Nothing
in FOIA forbids a public body from answering anyone it likes, and most Virginia utilities do.
King George County is the exception: its records portal (kinggeorgecounty.justfoia.com) asks
"Are you a Virginia Resident?" and will not submit without an attached proof of Virginia
residency, so the King George request goes through the Service Authority's general contact form
instead, as a voluntary request. The letters say plainly where the requester lives and ask the
body to respond as a matter of discretion.

**2. The utility-customer exemption.** § 2.2-3705.7(7) excludes from mandatory disclosure
"Customer account information of a public utility affiliated with a political subdivision of
the Commonwealth, including the customer's name and service address, but excluding the amount
of utility service provided and the amount of money charged or paid for such utility service."
Two things follow. The service address *is* inside the exemption, so a utility may withhold it.
The usage figure (zero consumption) is expressly *outside* it. The exemption is discretionary
("may be disclosed by the custodian in his discretion", § 2.2-3705.7 preamble), and the request
is worded to stay as far outside it as possible: no customer identities, a premises/parcel
identifier offered as a substitute for the street address, disconnected premises framed as
having no current customer, and an operations/GIS inactive-meter list accepted in place of
billing data. If a utility still withholds addresses, the fallback ask is parcel number +
status + usage, which is enough to match to the parcel index.

## Contacts found (2026-10-15)

| Utility | County | FOIA contact | How filed |
|---|---|---|---|
| King George County Service Authority | King George | Dan Hamilton, General Manager & FOIA contact, 540-775-2746; no email published; county FOIA Officer Jaclyn Fish, 540-775-9181 | Service Authority contact form (kinggeorgecountyva.gov FormCenter 175), reCAPTCHA; county JustFOIA portal requires Virginia-residency proof |
| Westmoreland County Public Utilities | Westmoreland | Donna L. Cogswell, FOIA Officer, County Administration, P.O. Box 1000, Montross, VA 22520, dcogswell@westmoreland-county.org, fax 804-493-0134 | Email |
| Town of Colonial Beach (water/sewer) | Westmoreland | Heather Oliver, Town Clerk & FOIA Officer, 315 Douglas Ave, P.O. Box 450, Colonial Beach, VA 22443, 804-224-7181, holiver@colonialbeachva.gov | Email (online form also exists: colonialbeachva.gov FormCenter 81) |
| Fauquier County Water & Sanitation Authority | Fauquier | Benjamin R. Shoemaker, 7172 Kennedy Road, Warrenton, VA 20187, 540-349-2092 x108, fax 540-347-7689, bshoemaker@fcwsa.org | Email |
| Town of Warrenton Public Utilities | Fauquier | Stephen Clough, FOIA Records Center, P.O. Box 341, Warrenton, VA 20188, 540-347-1101 | NextRequest portal (townofwarrentonva.nextrequest.com/requests/new), no account needed |

## The request (identical for every utility except the header)

> Re: Request for records under the Virginia Freedom of Information Act (Va. Code § 2.2-3700 et seq.)
>
> Dear [FOIA Officer],
>
> Under the Virginia Freedom of Information Act I request the following records of [Utility],
> as an Excel or CSV file sent by email to mrdustinray@gmail.com:
>
> 1. All residential water and/or sewer service addresses that are CURRENTLY shut off,
>    disconnected, inactive, vacant, or in final-bill status as of the date of your search,
>    regardless of when service stopped; and
> 2. All active residential accounts that recorded zero water usage in each of the last two or
>    more billing periods.
>
> For each record please include only: service address; tax map / parcel number (if your system
> keeps it); current service status; date service stopped (or the first zero-usage billing
> period); and the number of consecutive zero-usage billing periods.
>
> I am NOT requesting, and ask you to omit, customer names, phone numbers, email addresses,
> account numbers, balances, payment history, or any other billing or financial data. An existing
> report or a database export containing the fields above is fine; I do not ask you to create a
> new record, and I would rather receive the report your system already produces (for example an
> inactive-services, vacant-premises, or zero-consumption exception report, or an inactive-meter
> layer from your GIS or work-order system) than have staff build one.
>
> On § 2.2-3705.7(7): that exemption covers customer account information, including a customer's
> name and service address, but expressly excludes "the amount of utility service provided."
> Item 2 asks for the amount of service provided (none), and item 1 asks about premises that have
> no current customer at all. The exemption is in any case discretionary. If you conclude that
> the street address must be withheld for any record, please release that record with the tax
> map / parcel number or a premises or meter identifier in place of the address, together with
> the status, date, and usage fields, and release everything else. If any portion is withheld,
> please identify the volume and subject matter withheld and cite the specific Code of Virginia
> section relied on, as § 2.2-3704(B) requires, and redact under § 2.2-3704.01 rather than
> withhold whole records.
>
> Please provide the records in the electronic form in which they are kept (§ 2.2-3704(G)). If
> any charge will exceed $50, please send a cost estimate before doing the work (§ 2.2-3704(F)).
>
> I live in Maryland and buy and renovate houses in Virginia through Pages of Purpose LLC. I
> understand § 2.2-3704(A) gives the enforceable right of access to citizens of the Commonwealth,
> and I am not claiming to be one. FOIA does not prohibit you from releasing public records to
> anyone, and I respectfully ask that you exercise your discretion to respond to this request as
> you would to any Virginia resident. If you prefer to treat this as a routine records request
> outside FOIA, that is fine with me.
>
> Thank you for your time.
>
> Dustin Ray
> Pages of Purpose LLC
> 9945 Bowling Drive, Charlotte Hall, MD 20622
> mrdustinray@gmail.com

## When a response arrives

Convert each row to `data/distress/manual.csv` (`county,kind,date,address,zip,parcel,
case_number,status,source,url,detail`) with kind `VACANT_NOTICE`, date = service-stop date or
first zero-usage period, status = the utility's status word, source = the utility's name. The
daily distress run matches it to parcels; a utility shut-off alone is a 40-point signal.
