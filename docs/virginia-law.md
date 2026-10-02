# Virginia law this tool is built on

Every point below was read from the Code of Virginia at law.lis.virginia.gov on
2026-10-01 (current text). This is a working note for building the tool, not legal
advice. Thresholds in § 58.1-3975 and § 58.1-3970.1 were amended in 2023–2026;
re-read them each year.

## Tax sales (Title 58.1, Chapter 39, Article 4)

| Point | What the Code says | Section |
|---|---|---|
| Virginia sells the property, not a lien | The locality files a **complaint** in circuit court "to subject the real estate to the lien for such delinquent taxes"; the court "may appoint a special commissioner to sell the properties and execute the necessary deeds". The sale must be confirmed by the court. | 58.1-3965, 58.1-3967, 58.1-3969 |
| When the locality may start | Taxes "delinquent on December 31 following the second anniversary of the date on which such taxes have become due". First anniversary for condemned / nuisance / derelict / blighted property, and (on a court finding) for property assessed at $100,000 or less. | 58.1-3965(A) |
| Notice before suit | Mailed notice at least 30 days before filing, to the owner's last known address and the property address; a list published in a newspaper at least 30 days before suit. The notice must say a payment agreement of up to 72 months can be requested. | 58.1-3965(A) |
| Redemption | The owner "or his heirs, devisees, successors, and assigns, shall have the right to redeem such real estate **prior to the date set for a judicial sale**" by paying taxes, penalties, interest, costs and an attorney fee. No right to redeem after the sale appears in the article. | 58.1-3974, 58.1-3965(B) |
| The sale can be paused without full payment | The treasurer "may suspend any action for sale" on an installment agreement of up to 72 months. Discretionary. On default the sale proceeds without new notice. | 58.1-3965(C)–(E) |
| After-sale risk that is not redemption | A party served by publication may petition for rehearing "only for good cause shown, and only within 90 days of entry of the confirmation of sale". | 58.1-3967 |
| Non-judicial sale of small parcels | Taxes delinquent on Dec 31 after the **third** anniversary, and: assessed at $15,000 or less; or $15,000–$30,000 with no deed of trust and unimproved ≤ 1 acre / unbuildable / condemned / nuisance / derelict / blighted; or $30,000–$40,000 in a redevelopment zone, unimproved, ≤ 0.5 acre. The owner may redeem before the sale date. | 58.1-3975 |
| Surplus | "The former owner and his heirs, devisees, successors, or assigns ... shall be entitled to the surplus"; the claimant carries the burden of proof. If unclaimed "within two years after the date of confirmation of such sale" the clerk pays it **to the county, city or town** — not to state unclaimed property. Non-judicial sales: two years from the sale date, then the general fund. | 58.1-3967, 58.1-3975(K) |
| Locality can take the parcel instead of auctioning it | The locality may buy at the sale, or petition to have the parcel conveyed to itself, a land bank or a nonprofit when assessed at $125,000 or less and taxes/liens exceed set percentages of value. | 58.1-3970, 58.1-3970.1 |
| Delinquent list | The treasurer **must make** the delinquent lists within 60 days of fiscal year end; publishing them is **optional** ("may cause the lists ... to be published"). | 58.1-3921, 58.1-3924 |

What this means for the board: the window to buy from a delinquent owner is from the
30-day notice until the day before the sale. After the sale the only thing left for the
former owner is the surplus, and that claim dies two years after confirmation.

## Death, heirs and probate

| Point | What the Code says | Section |
|---|---|---|
| List of Heirs | "Every personal representative of a decedent, whether the decedent died testate or intestate, shall, at the time of his qualification, and every proponent of a will where there is no qualification" furnish a list of heirs under oath. It goes to the clerk where they qualify **and** to the circuit court clerk where any of the estate's real estate lies. "The clerk shall record the list of heirs **in the will book** and index the list in the name of the decedent and the heirs." If nobody qualifies within 30 days, an heir of an intestate decedent *may* file one. | 64.2-509 |
| Real-estate affidavit | Optional; intestate decedents only; any person with an interest in the real estate may record it. It describes the real estate and gives "the names and last known addresses of the decedent's heirs at law". Recorded as wills are recorded. | 64.2-510 |
| Who handles probate | "The circuit courts shall have jurisdiction of the probate of wills"; the clerk "may admit wills to probate, appoint and qualify executors, administrators". Venue follows the decedent's residence, so a King George parcel can be probated elsewhere. | 64.2-443, 64.2-444 |
| Death records | Death records become public 25 years after the death. A basic online death index (name, date, locality) is public from receipt. | 32.1-271(D), (H) |
| Church property | Unincorporated churches may hold land through trustees appointed by the circuit court on the church's application; churches may also hold property through a corporation or an ecclesiastical officer. | 57-7.1, 57-8, 57-16, 57-16.1 |
| FOIA | Rights run to "citizens of the Commonwealth" and in-state media. A Maryland resident has no statutory right to a response. | 2.2-3700, 2.2-3704 |

## Where the handoff brief was wrong

1. **A List of Heirs is not a land-records filing triggered by owning real estate.** It is
   filed at qualification or probate and recorded in the will book. No qualification and
   no probate means no list. That is exactly the case the tool is built to find.
2. **Publishing the delinquent list is optional**, not required. King George does not post one.
3. **Surplus is governed by 58.1-3967**, not 58.1-3969, and unclaimed surplus goes to the
   locality after two years.
4. **"Only by paying in full" is too strong.** A treasurer's installment agreement can suspend the sale.
5. **The pleading is a complaint**, not a bill in equity.
6. **Surplus-recovery fees:** nothing in 58.1-3967 caps them. The 10% cap and 36-month
   wait in § 55.1-2542 apply to property delivered to the state unclaimed-property
   administrator, which tax-sale surplus is not. Whether another statute (consumer
   protection, unauthorized practice of law) reaches a surplus-recovery agreement was not
   checked. Get a Virginia lawyer's answer before offering anything beyond pointing an
   owner at the clerk.
7. **FOIA** will not work for an out-of-state requester.
