# Code violations, unsafe structures and liens: what exists and how to ask

King George County does not publish a list of code violations, unsafe-structure
orders, blight findings or nuisance liens. Checked 2026-10-01: the county website
has no such page, and none of the 131 layers in the county's open-data service is a
code-enforcement or permit layer.

What the tool uses instead, for free:

- **The assessor's field notes** on every parcel (`REM1` / `REM2` in the Parcels layer).
  The assessor writes down what they see: "DWL ABANDONED & IN VERY POOR COND, WINDOWS
  ARE BOARDED UP", "UNSAFE STRUCTURE PER CO. 5/19/09", "DWL BURNED LATE 2017",
  "VACANT SINCE 2013 - VERY OVERGROWN". These feed the **Condition** signal on the
  Stacked Distress tab. They can be years old, and they are not an enforcement record.
- **"REDTAG" is not a violation** in these notes. It is the assessor's reminder to come
  back to unfinished construction, so it is ignored.
- **Unpaid taxes** from the Treasurer. Under Va. Code § 58.1-3965 the county may sue a
  year earlier on a parcel with a condemned structure, a nuisance, a derelict building
  or declared blight, so those parcels reach a tax sale sooner.

## Asking the county for the real list

The records exist in the Department of Community Development (Building, and Planning
& Zoning). Virginia's FOIA gives a right to them only to Virginia citizens and
in-state media (Va. Code § 2.2-3704), so a request from Maryland is a courtesy
request; many offices answer anyway, and a Virginia partner or attorney can make it
as of right. Ask for a list, not copies of files, to keep it free.

> To: King George County Department of Community Development
>
> I am asking for a current list of properties with an open case in any of the
> following categories, with the property address or tax map number, the date the
> case was opened, and its status:
>
> 1. structures declared unsafe or unfit for occupancy, or ordered demolished;
> 2. properties declared blighted, derelict or a public nuisance;
> 3. open zoning or property-maintenance violations (tall grass, inoperable
>    vehicles, trash and debris);
> 4. any lien the county has recorded for abatement or demolition costs.
>
> An export from your case-tracking system or a spreadsheet is ideal. If the records
> exist only as individual files, please tell me and I will narrow the request.
>
> Thank you,
> [name, phone, email]

When the list arrives, put it in `data/violations/import.csv`
(`pin,address,type,opened,status,note`) and tell Claude; it becomes a fifth signal on
the Stacked Distress tab.
