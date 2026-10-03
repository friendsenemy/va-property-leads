/* Surplus Funds tab: tax sales and foreclosure sales.
   Ported from md-property-leads static/js/surplus.js (the auction modal: Former Owner,
   "Has it been collected?", find-them links, copy-letter buttons, archive and deed-scan
   toggles), with Virginia's stages, law and links. Reads data/surplus/auctions.json;
   the archive loads only when its box is ticked. Uses LeadTab from tabs.js. */
const SURPLUS_STAGE = {
    TAX_SALE_SOLD:     { label: "Tax Sale Sold",     cls: "E", blurb: "Sold by a special commissioner in the county's delinquent-tax suit. What the buyer paid, less taxes, fees, costs and any liens, is owed to the former owner through the Circuit Court." },
    AUCTION_SOLD:      { label: "Auction Sold",      cls: "E", blurb: "Foreclosure sale by a substitute trustee, and title has moved. If the price beat what was owed, the trustee owes the difference to the former owner." },
    AUCTION_SCHEDULED: { label: "Auction Scheduled", cls: "C", blurb: "A substitute trustee has advertised a foreclosure sale. The owner still holds title and can sell or pay off until the hammer falls. There is no redemption afterwards." },
};
const sRange = (t) => t ? `${money(t[0])} to ${money(t[2])}` : "—";
const sDays = (d) => d ? Math.round((new Date(d + "T12:00:00") - Date.now()) / 86400000) : null;

function surplusPerson(name) {
    // "GRAY JAMES R & BRENDA J MILLS", "Carl Ashby Gibson" -> first person, as {first, last, full}
    if (!name) return null;
    const one = name.split(/\s+(?:&|AND|OR)\s+/i)[0].replace(/\b(TRUSTEE|TR|ET ?ALS?|JR|SR|II|III|IV)\b\.?/gi, " ").replace(/[^A-Za-z' -]/g, " ").trim().split(/\s+/);
    if (one.length < 2 || /\b(LLC|INC|CORP|TRUST|BANK|CHURCH)\b/i.test(name)) return null;
    const cap = (w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    // the county writes LAST FIRST; a deed note and a trustee's notice write FIRST LAST
    const lastFirst = name === name.toUpperCase() && !/BEHALF/.test(name);
    const first = cap(lastFirst ? one[1] : one[0]), last = cap(lastFirst ? one[0] : one[one.length - 1]);
    return { first, last, full: `${first} ${last}` };
}

function surplusLinks(r) {
    const p = surplusPerson(r.former_owner || r.owner_of_record), e = encodeURIComponent;
    const place = (r.mail || "").match(/,\s*([A-Za-z .]+?)\s+([A-Z]{2})\s+\d{5}/);
    const city = place ? place[1].trim() : (r.city || "King George"), st = place ? place[2] : "VA";
    const L = [];
    if (p) {
        L.push(`<a href="https://www.truepeoplesearch.com/results?name=${e(p.full)}&citystatezip=${e(city + " " + st)}" target="_blank" rel="noopener">TruePeopleSearch ↗</a>`);
        L.push(`<a href="https://www.fastpeoplesearch.com/name/${e((p.first + "-" + p.last).toLowerCase())}_${e(city.toLowerCase().replace(/\s+/g, "-") + "-" + st.toLowerCase())}" target="_blank" rel="noopener">FastPeopleSearch ↗</a>`);
        L.push(`<a href="https://www.google.com/search?q=${e(`"${p.full}" ${city} ${st}`)}" target="_blank" rel="noopener">Google ↗</a>`);
        L.push(`<a href="https://www.google.com/search?q=${e(`"${p.full}" obituary ${city} OR "King George" Virginia`)}" target="_blank" rel="noopener" title="If the former owner has died, the surplus belongs to the estate: Va. Code § 55.1-331">Obituary search ↗</a>`);
    } else if (r.former_owner) {
        L.push(`<a href="https://cis.scc.virginia.gov/EntitySearch/Index" target="_blank" rel="noopener">SCC entity search ↗</a>`);
    }
    L.push(`<a href="https://eapps.courts.state.va.us/ocis/landing" target="_blank" rel="noopener" title="Virginia's online case information. Its terms bar automated use, so this is a by-hand lookup: King George Circuit Court, civil, by the former owner's name">Circuit Court case info ↗</a>`);
    L.push(`<a href="https://www.vamoneysearch.gov/" target="_blank" rel="noopener" title="Virginia Treasury unclaimed property. Search the former owner's name; a result naming a court or a trustee as holder is this money">vamoneysearch.gov ↗</a>`);
    if (r.card_url) L.push(`<a href="${esc(r.card_url)}" target="_blank" rel="noopener">County card ↗</a>`);
    return L;
}

function surplusLetter(r) {
    const where = r.address ? `${r.address}${r.county ? ", " + r.county + " County" : ""}, Virginia` : `the land at tax map ${r.pin || ""} in ${r.county} County, Virginia`;
    const p = surplusPerson(r.former_owner);
    const amt = r.surplus_est ? `somewhere between ${money(r.surplus_est[0])} and ${money(r.surplus_est[2])}` : "a meaningful amount";
    const sig = "\n\nDustin Ray\nPages of Purpose LLC · Charlotte Hall, Maryland";
    if (r.stage === "TAX_SALE_SOLD") return `${p ? p.full : "To the former owner of " + where},

I am writing about ${where}, which was sold in the county's delinquent-tax case. The deed to the buyer is dated ${r.sale_date}${r.hammer ? ", and the price was " + money(r.hammer) : ""}.

Most people do not know this: when a tax sale brings in more than the taxes, fees and costs, the extra money does not go to the county or the buyer. It belongs to the former owner. By our estimate that could be ${amt}. The exact figure is in the court's file.

The money is held by the Clerk of the Circuit Court for ${r.county} County. It is not sent out on its own. The former owner, or the heirs, must ask the court for it, and Virginia law gives two years from the date the court confirmed the sale (Code of Virginia § 58.1-3967). After that it is paid to the county.

I am a real-estate buyer and I found this in public records. I am not asking you for anything. You can call the Clerk of the Circuit Court and ask about "surplus proceeds" in the tax sale of this property, and a Virginia attorney can file the request for you. If it would help, I will tell you what I found and where.${sig}`;
    if (r.stage === "AUCTION_SOLD") return `${p ? p.full : "To the former owner of " + where},

I am writing about ${where}, which was sold at a foreclosure sale on or about ${r.sale_date}${r.hammer ? " for " + money(r.hammer) : ""}.

Most people do not know this: when a foreclosure sale brings in more than what was owed on the loan, the extra money does not belong to the lender or the buyer. After the costs of sale, the loan and any other liens are paid, what is left belongs to the former owner (Code of Virginia § 55.1-324). By our estimate that could be ${amt}. The trustee's accounting gives the exact figure.

The trustee who held the sale must file that accounting with the Commissioner of Accounts for the Circuit Court. You can ask the trustee named in the sale notice for it directly${r.trustee ? " (" + r.trustee + ")" : ""}, or ask the Clerk of the Circuit Court how to see it.

I am a real-estate buyer and I found this in public records. I am not asking you for anything. If it would help, I will tell you what I found and where. A Virginia attorney can make the request for you.${sig}`;
    return `${p ? p.full : "To the owner of " + where},

A trustee's sale notice lists a foreclosure sale of ${where} for ${r.sale_date}${r.sale_time ? " at " + r.sale_time : ""}.

If that sale goes ahead, the house is sold at auction, usually for less than it is worth, and in Virginia there is no right to buy it back afterwards. If you sell it before the sale date, the loan is paid off at closing and the rest of the equity is yours.

I buy houses in ${r.county} County for cash and can close quickly, with no repairs, no showings and no fees. I will make a written offer you can take to anyone you trust, including an attorney or a housing counselor.

If you would rather keep the house, I will tell you that too. Either way it costs nothing to talk.${sig}`;
}

const SURPLUS_LAW = `<div class="law-box"><b>Virginia lawyer first.</b> Before any agreement with a former owner about surplus money, have a Virginia attorney read it. What the Code of Virginia says, as checked October 2026:
    <ul>
    <li><b>Who is owed.</b> After a trustee's sale: costs, taxes, the loan, junior liens, then “the residue of the proceeds shall be paid to the grantor or his assigns” (§ 55.1-324). After a tax sale: the former owner, heirs, devisees, successors or assigns, who carry the burden of proof (§ 58.1-3967).</li>
    <li><b>If the owner has died,</b> the surplus is paid to the personal representative of the estate (§ 55.1-331). Somebody has to qualify.</li>
    <li><b>An assignment only binds the trustee if the trustee has actual notice of it before paying out</b> (§ 55.1-324).</li>
    <li><b>Filing for someone else is practicing law.</b> Preparing or filing a court petition for another person without a license is a Class 1 misdemeanor (§ 54.1-3904). The owner hires the attorney.</li>
    <li><b>No fee up front from an owner-occupant in foreclosure.</b> Charging for foreclosure-avoidance help before it is fully performed is a prohibited practice, and any buy-back promise must be a written option with its terms and price (§ 59.1-200.1).</li>
    <li><b>Once money reaches the Treasury:</b> no finder agreement for 36 months, then a 10% cap; breaking it is a misdemeanor (§ 55.1-2542). The owner can always claim free.</li>
    <li><b>Buying houses:</b> assigning two or more purchase contracts in 12 months needs a real estate license (§ 54.1-2100). Closing in your own name does not.</li>
    </ul>
    We found no Virginia statute like Maryland's RP § 7-314 that sets a form for buying a surplus claim. That is an absence we looked for, not a clearance.</div>`;

const SurplusApp = new LeadTab({
    prefix: "surplus", url: "data/surplus/auctions.json", lsKey: "va_surplus_leads_local_v1",
    emptyTitle: "Nothing on the board", emptyText: "No tax sale or foreclosure sale in King George or the neighbouring counties clears the bar today.",
    columns: ["Stage", "Property", "Former Owner / Owner", "County", "Sale", "Price Paid", "Est. Surplus / Equity"],
    filters: [
        { id: "all", label: "All" },
        { id: "strong", label: "Strong", test: (r) => r.tier === "STRONG" },
        { id: "tax", label: "Tax Sale Sold", test: (r) => r.stage === "TAX_SALE_SOLD" },
        { id: "sold", label: "Auction Sold", test: (r) => r.stage === "AUCTION_SOLD" },
        { id: "sched", label: "Auction Scheduled", test: (r) => r.stage === "AUCTION_SCHEDULED" },
        { id: "verified", label: "Verified – still unclaimed", test: (r) => SurplusApp.statusOf(r) === "verified" },
    ],
    stats: (s) => [["Tax Sale Sold", s.tax_sale_sold, "pink"], ["Auction Sold", s.auction_sold, "yellow"],
        ["Auction Scheduled", s.scheduled, "cyan"], ["Strong", s.strong, "purple"]],
    info: (s) => `Checked ${TitleApp.fmtDT(s.generated_at)}. ${s.sales_listed_statewide} sales on the trustees' lists statewide, ${s.listed_in_target_counties} in King George and the five neighbouring jurisdictions. `
        + `${s.new_today} new today. Every figure is an estimate range; the status box records what a person found when they checked.`
        + (s.deed_scan_candidates ? ` ${s.deed_scan_candidates} deed-scan candidate(s) hidden; tick the box to see them.` : ""),
    searchText: (r) => `${r.former_owner} ${r.owner_of_record} ${r.buyer_on_record} ${r.address} ${r.city} ${r.county} ${r.pin} ${r.mail} ${r.tier} ${r.stage}`,
    title: (r) => `${r.address || "Tax map " + (r.pin || "")}${r.city ? ", " + r.city : ""} · ${r.former_owner || r.owner_of_record || r.county}`,

    afterInit() {
        const arc = document.getElementById("surplusArchive"), ds = document.getElementById("surplusDeedScan");
        ds.addEventListener("change", () => { this.state.page = 1; this.render(); });
        arc.addEventListener("change", async () => {
            if (arc.checked && !this._archiveLoaded) {
                this._archiveLoaded = true;
                try {
                    const j = await fetch(`data/surplus/auction-archive.json?t=${Date.now()}`, { cache: "no-store" }).then((x) => x.json());
                    (j.rows || []).forEach((a) => { a._search = this.searchText(a).toLowerCase(); this.rows.push(a); });
                } catch {}
            }
            this.state.page = 1; this.render();
        });
    },
    filtered() {
        const arc = document.getElementById("surplusArchive").checked, ds = document.getElementById("surplusDeedScan").checked;
        return LeadTab.prototype.filtered.call(this).filter((r) => (arc || !r.archive) && (ds || r.archive || !(r.from_deed && r.kind === "FORECLOSURE")));
    },

    row: (r) => {
        const m = SURPLUS_STAGE[r.stage], dd = sDays(r.sale_date);
        const chips = [
            r.tier === "STRONG" ? '<span class="chip chip-strong" title="The price (or assessed value) clears the high end of the estimated payoff by $25,000 and 1.3x">strong</span>' : "",
            r.tier === "POSSIBLE" ? '<span class="chip" title="Estimated $10,000 or more over the middle of the payoff range, or the evidence is thin">possible</span>' : "",
            r.tier === "UNCONFIRMED" ? '<span class="chip" style="opacity:.75" title="Known only from the county\'s deed note. Could be the lender reselling. The Clerk\'s index settles it">unconfirmed</span>' : "",
            r.tier === "UNRATED" ? '<span class="chip" style="opacity:.75" title="No parcel data for this county, so equity cannot be measured">not rated</span>' : "",
            r.court_balance && r.court_disbursed ? `<span class="chip chip-strong" title="The Clerk's own ledger shows this balance held for the former owner as of ${esc(r.court_as_of)}">clerk's balance</span>` : "",
            r.is_new && !r.archive ? '<span class="chip chip-strong" title="First seen today">new</span>' : "",
            r.archive ? `<span class="chip" title="Sold more than 180 days ago">archive · ${esc(r.archive_bucket || "")}</span>` : "",
            r.sale_date_passed ? '<span class="chip" title="The sale date has passed; the county does not show a new owner yet">awaiting deed</span>' : "",
            r.claim_deadline && r.collection_window === "COURT_2YR" ? `<span class="chip" title="Two years from the order confirming the sale; the real deadline is earlier than this">claim by ${esc(r.claim_deadline)}</span>` : "",
        ].join(" ");
        return [
            `<span class="cls cls-${m.cls}" title="${esc(m.blurb)}">${esc(m.label)}</span> ${chips}`,
            `<div class="address">${esc(r.address || "No street address (land)")}${r.city ? ", " + esc(r.city) : ""}</div><div class="meta">${r.pin ? "map " + esc(r.pin) : esc(r.zip || "")}${r.parcel_count > 1 ? ` · ${r.parcel_count} parcels` : ""}${r.year_built ? ` · built ${r.year_built}` : ""}</div>`,
            `<span class="mono" style="font-size:0.8rem">${esc(r.former_owner || r.owner_of_record || "—")}</span>${r.mail ? `<div class="sub">${esc(r.mail)}</div>` : ""}`,
            esc(r.county) + (r.county_by_zip ? '<div class="sub">by ZIP</div>' : ""),
            `<span class="mono">${esc(r.sale_date || "—")}</span>${r.stage === "AUCTION_SCHEDULED" && dd != null ? `<div class="sub">${dd >= 0 ? "in " + dd + " days" : -dd + " days ago"}</div>` : ""}`,
            `<span class="value-cell">${r.hammer ? money(r.hammer) : "—"}</span>${r.assessed_value ? `<div class="sub">assessed ${money(r.assessed_value)}</div>` : ""}`,
            r.surplus_est ? `<span class="mono" style="color:var(--green); font-weight:600">${money(r.surplus_est[1])}</span><div class="sub">${sRange(r.surplus_est)}</div>` : '<span class="sub">not estimated</span>',
        ];
    },

    detail: (r) => {
        const m = SURPLUS_STAGE[r.stage], sold = r.stage !== "AUCTION_SCHEDULED";
        const row = (label, value) => value ? `<div class="detail-row"><span class="label">${label}</span><span class="value">${value}</span></div>` : "";
        const parcels = (r.parcels || []).length > 1 ? row("Parcels in this deed", r.parcels.map((p) => `<a href="${esc(p.card_url)}" target="_blank" rel="noopener">${esc(p.pin)}</a> ${money(p.assessed_value)}`).join(" · ")) : "";
        return `
        <div class="detail-section">
            <h3>${esc(m.label)} ${r.tier ? `<span class="chip ${r.tier === "STRONG" ? "chip-strong" : ""}">${esc(r.tier.toLowerCase())}</span>` : ""}</h3>
            <div class="next-step">${esc(m.blurb)}</div>
            <div class="verify"><b>Why it is on the board.</b> ${esc(r.why || "")}</div>
        </div>
        <div class="detail-section">
            <h3>${sold ? "Former owner" : "Owner"}</h3>
            ${row("Name", `<span class="mono" style="font-weight:600">${esc(r.former_owner || r.owner_of_record || "not known: read the deed")}</span>${r.former_owner_source ? ` <span class="sub">${esc(r.former_owner_source)}</span>` : ""}`)}
            ${row("Mailing address", r.mail ? `${esc(r.mail)} <span class="sub">${esc(r.mail_source || (r.snapshot_date ? "county record on " + r.snapshot_date + ", before title moved" : ""))}</span>` : '<span class="sub">not on file: the county record now shows the buyer. Use the links below.</span>')}
            ${row("How title was held", esc(r.held_as || ""))}
            ${row("Borrower in the notice", r.borrower ? esc(r.borrower) : "")}
            ${row("Find them", surplusLinks(r).join(" · "))}
        </div>
        <div class="detail-section">
            <h3>The money <span class="sub">estimates, never a balance</span></h3>
            ${row(sold ? "Price paid" : "Assessed value", `<span class="mono">${money(sold ? r.hammer : r.assessed_value)}</span>${sold && r.assessed_value ? ` <span class="sub">assessed ${money(r.assessed_value)}</span>` : ""}`)}
            ${row(r.kind === "TAX" ? "Taxes, fees and costs" : "Estimated payoff", r.payoff_est ? `<span class="mono">${sRange(r.payoff_est)}</span> <span class="sub">${esc(r.payoff_basis || "")}</span>` : '<span class="sub">nothing on file to estimate from</span>')}
            ${row(sold ? "Estimated surplus" : "Estimated equity", r.surplus_est ? `<span class="mono" style="color:var(--green); font-weight:600">${sRange(r.surplus_est)}</span> <span class="sub">middle ${money(r.surplus_est[1])}</span>` : "")}
            ${row("Held by the Clerk", r.court_balance ? `<span class="mono" style="font-weight:600">${money(r.court_balance)}</span> <span class="sub">Circuit Court liabilities index, as of ${esc(r.court_as_of)}${r.court_disbursed ? "; taxes and costs paid out " + esc(r.court_disbursed) : "; taxes and costs not paid out yet"}</span>` : "")}
            ${row("Court case", r.case_number ? `<span class="mono">${esc(r.case_number)}</span> <span class="sub">King George Circuit Court, chancery</span>` : "")}
            ${row("Taxes on the county's list", r.taxes_owed ? `<span class="mono">${money(r.taxes_owed)}</span>` : "")}
            ${row("Bidder's deposit", r.deposit ? `<span class="mono">${money(r.deposit)}</span> <span class="sub">up to 10% of the price (§ 55.1-324)</span>` : "")}
            ${row("Deed of trust", [r.dot_date, r.dot_ref, r.original_amount ? "original amount " + money(r.original_amount) : ""].filter(Boolean).map(esc).join(" · "))}
            ${row("Owner's own purchase", r.purchase_year ? `${r.purchase_year}${r.purchase_price ? " · " + money(r.purchase_price) : ""}${r.purchase_deed ? " · " + esc(r.purchase_deed) : ""}` : "")}
        </div>
        <div class="detail-section">
            <h3>${sold ? "The sale" : "The scheduled sale"}</h3>
            ${row("Date", `<span class="mono">${esc(r.sale_date || "")}</span>${r.sale_time ? " " + esc(r.sale_time) : ""}${r.sale_place ? " · " + esc(r.sale_place) : ""} ${r.sale_date_kind ? `<span class="sub">${esc(r.sale_date_kind)}</span>` : ""}`)}
            ${row("Property", `${esc(r.address || "no street address")}${r.city ? ", " + esc(r.city) : ""} ${esc(r.zip || "")}${r.pin ? ` · map ${esc(r.pin)}` : ""}${r.legal ? `<div class="sub">${esc(r.legal)}</div>` : ""}`)}
            ${parcels}
            ${row("Buyer on record", r.buyer_on_record ? `<span class="mono">${esc(r.buyer_on_record)}</span>` : "")}
            ${row("Deed", [r.trustee_deed, r.grantor_note].filter(Boolean).map(esc).join(" · "))}
            ${row("Trustee", esc(r.trustee || ""))}
            ${row("Source", r.source_url ? `<a href="${esc(r.source_url)}" target="_blank" rel="noopener">${esc(r.source)}</a>${r.file_no ? " · file " + esc(r.file_no) : ""}` : esc(r.source || ""))}
            ${row("Assessor's remarks", esc(r.remarks || ""))}
        </div>
        ${sold ? `<div class="detail-section">
            <h3>Has it been collected?</h3>
            <div class="next-step">${esc(r.collection_note || "")}</div>
            <div class="verify"><b>This is a verdict by age, not a fact.</b> Nobody publishes whether surplus was paid. Two minutes settles it: ${r.kind === "TAX"
                ? "call the Clerk of the King George Circuit Court and ask whether surplus from the tax sale of this parcel is still held, and the date the sale was confirmed."
                : "ask the trustee for the accounting, or ask the Clerk how to see the Commissioner of Accounts' report on this sale; then search the former owner's name at vamoneysearch.gov."}
                Then set the status below to <b>Verified – money still unclaimed</b> or <b>Already paid out – dead</b>, so the next person does not check it again.</div>
        </div>` : ""}
        <div class="detail-section">
            <h3>${sold ? "Letter to the former owner" : "Letter to the owner"} <button class="btn" id="surplusCopyLetter" type="button" style="margin-left:8px">Copy letter</button></h3>
            <div class="letter-box" id="surplusLetterText">${esc(surplusLetter(r))}</div>
            <div class="sub">${r.mail ? "Mail to: " + esc(r.mail) : "No mailing address on file. Find one with the links above."}</div>
        </div>
        <div class="detail-section"><h3>The law</h3>${SURPLUS_LAW}</div>`;
    },

    afterOpen() {
        const b = document.getElementById("surplusCopyLetter");
        if (b) b.onclick = async () => {
            const text = document.getElementById("surplusLetterText").textContent;
            try { await navigator.clipboard.writeText(text); b.textContent = "Copied"; } catch { b.textContent = "Select the text and copy"; }
            setTimeout(() => { b.textContent = "Copy letter"; }, 2000);
        };
    },

    exportCsv() {
        const q = (v) => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
        const head = ["Stage", "Tier", "County", "Address", "City", "Zip", "Tax Map", "Former Owner / Owner", "Mailing Address", "Sale Date", "Price Paid", "Assessed",
            "Payoff Low", "Payoff High", "Surplus Low", "Surplus Mid", "Surplus High", "Where The Money Is", "Claim Deadline", "Buyer", "Source", "Why", "Status", "Notes"];
        const lines = [head.join(",")];
        this.filtered().forEach((r) => lines.push([SURPLUS_STAGE[r.stage].label, r.tier, r.county, r.address, r.city, r.zip, r.pin, r.former_owner || r.owner_of_record, r.mail,
            r.sale_date, r.hammer, r.assessed_value, r.payoff_est && r.payoff_est[0], r.payoff_est && r.payoff_est[2], r.surplus_est && r.surplus_est[0],
            r.surplus_est && r.surplus_est[1], r.surplus_est && r.surplus_est[2], r.collection_window, r.claim_deadline, r.buyer_on_record, r.source, r.why,
            this.statusOf(r), this.notesOf(r)].map(q).join(",")));
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" }));
        a.download = `kg-surplus-${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a); a.click(); a.remove();
    },
});
