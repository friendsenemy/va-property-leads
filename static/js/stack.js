/* Stacked Distress tab: one row per owner, every signal side by side.
   Uses LeadTab and the helpers defined in tabs.js. */
const KIND = { DEATH: ["Death", "cls-E"], TAX: ["Taxes", "cls-C"], TITLE: ["Title", "cls-W"], CONDITION: ["Condition", "cls-X"] };

const StackApp = new LeadTab({
    prefix: "stack", url: VAPL.DATA + "combined/leads.json", lsKey: "va_stack_leads_local_v1" + VAPL.ns,
    emptyTitle: "Nothing stacked yet", emptyText: "This fills in as the nightly build and the Treasurer walk run.",
    columns: ["Priority", "Owner on Record", "Property", "Signals", "Death", "Taxes", "Assessed", "Bill Mailed To"],
    filters: [
        { id: "all", label: "All" },
        { id: "dt", label: "Death + unpaid taxes", test: (r) => r.signals.DEATH && r.signals.TAX },
        { id: "three", label: "3+ signals", test: (r) => r.signal_count >= 3 },
        { id: "two", label: "2+ signals", test: (r) => r.signal_count >= 2 },
        { id: "death", label: "Any death", test: (r) => !!r.signals.DEATH },
        { id: "tax", label: "Any unpaid taxes", test: (r) => !!r.signals.TAX },
        { id: "cond", label: "House in bad shape", test: (r) => !!r.signals.CONDITION },
    ],
    stats: (s) => [["Owners With Stacked Distress", s.leads, "yellow"], ["Death + Unpaid Taxes", s.death_and_tax, "pink"],
        ["Three or More Signals", s.three_plus, "purple"], ["Bad-Condition Notes", s.condition, "cyan"]],
    info: () => "One row per owner, every signal side by side: title, death, unpaid taxes, and the assessor's condition notes. Shown when two or more stack, or when the assessor notes a house as unsafe, abandoned, burned, unlivable or vacant. King George publishes no code-violation or fines list; the assessor's notes are the nearest free record.",
    searchText: (r) => `${r.owner} ${r.mail.city} ${r.mail.state} ${Object.values(r.signals).map((x) => x.label + " " + (x.remarks || "")).join(" ")} ${r.parcels.map((p) => p.address + " " + p.pin).join(" ")}`,
    title: (r) => r.owner,
    row: (r) => [
        `<span class="prio prio-${TitleApp.tier(r.priority)}">${r.priority}</span>`,
        `<span class="mono" style="font-size:0.8rem">${esc(r.owner)}</span>${r.care_of ? `<div class="sub">c/o ${esc(r.care_of)}</div>` : ""}`,
        `<div class="address">${esc((r.parcels.find((p) => p.address) || {}).address || "No street address (land)")}</div><div class="meta">${r.parcel_count > 1 ? r.parcel_count + " parcels" : esc(r.parcels[0].legal || "")}</div>`,
        r.kinds.map((k) => `<span class="cls ${KIND[k][1]}">${KIND[k][0]}</span>`).join(" ") +
            `<div class="sub">${esc([r.signals.TITLE && r.signals.TITLE.label, r.signals.CONDITION && r.signals.CONDITION.label].filter(Boolean).join(" · "))}</div>`,
        r.signals.DEATH ? `<span class="mono" style="white-space:nowrap">${esc(r.signals.DEATH.death_date || "—")}</span><div class="sub">${esc(r.signals.DEATH.decedent)} · ${esc(r.signals.DEATH.identity_confidence.toLowerCase())}</div>` : '<span class="sub">—</span>',
        r.signals.TAX ? `<span class="mono" style="color:var(--red)">${money(r.signals.TAX.past_due)}</span><div class="sub">${r.signals.TAX.payments_behind} payments behind${r.signals.TAX.sale_eligible ? " · sale-eligible" : ""}</div>` : '<span class="sub">—</span>',
        `<span class="value-cell">${money(r.total_value)}</span>`,
        `${esc(r.mail.city || "—")}${r.mail.state ? ", " + esc(r.mail.state) : ""}`,
    ],
    detail: (r, s) => {
        const g = r.signals, d = g.DEATH, t = g.TAX, c = g.CONDITION;
        return `
        <div class="detail-section">
            <h3>${r.signal_count} signal${r.signal_count > 1 ? "s" : ""} on this owner <span class="prio prio-${TitleApp.tier(r.priority)}" style="margin-left:8px">${r.priority}</span></h3>
            <div class="next-step"><b>Next step.</b> ${esc(s.next_step)}</div>
            <div class="verify">Each line below comes from a different public record and each can be wrong or out of date on its own. Verify before contact.</div>
        </div>
        ${g.TITLE ? `<div class="detail-section"><h3>Title</h3><div class="detail-row"><span class="label">Reads as</span><span class="value">${esc(g.TITLE.label)}</span></div></div>` : ""}
        ${d ? `<div class="detail-section"><h3>Death</h3>
            <div class="detail-row"><span class="label">Decedent</span><span class="value" style="font-weight:600">${esc(d.decedent)}${d.age ? ", " + d.age : ""}${d.place ? " · of " + esc(d.place) : ""}</span></div>
            <div class="detail-row"><span class="label">Died</span><span class="value mono">${esc(d.death_date || "—")}</span></div>
            <div class="detail-row"><span class="label">Identity</span><span class="value">${conf(d.identity_confidence)} ${esc(d.death_class)}${d.other_owners.length ? " · others on title: " + esc(d.other_owners.join("; ")) : ""}${d.obituary_url ? ` · <a style="color:var(--cyan-dim)" href="${esc(d.obituary_url)}" target="_blank" rel="noopener">obituary</a>` : ""}</span></div>
            ${(d.heirs || []).length ? `<div class="detail-row"><span class="label">Heirs on file</span><span class="value">${d.heirs.map(esc).join("<br>")}</span></div>` : ""}</div>` : ""}
        ${t ? `<div class="detail-section"><h3>Taxes — delinquent</h3>
            <div class="detail-row"><span class="label">Past due</span><span class="value mono" style="color:var(--red)">${money(t.past_due)}</span></div>
            <div class="detail-row"><span class="label">Payments behind</span><span class="value">${t.payments_behind} half-year installments · tax years ${t.years.join(", ")} · unpaid since ${esc(t.oldest_due)}</span></div>
            <div class="detail-row"><span class="label">Sale status</span><span class="value">${t.sale_eligible ? "Old enough for the county to sue to sell (Va. Code § 58.1-3965)" : "Not yet old enough for the county to sue"}</span></div>
            <div class="detail-row"><span class="label">Checked</span><span class="value">${esc(t.checked)} · Treasurer's inquiry</span></div></div>` : ""}
        ${c ? `<div class="detail-section"><h3>Condition — assessor's notes</h3>
            <div class="detail-row"><span class="label">Noted</span><span class="value">${esc(c.label)}</span></div>
            <div class="detail-row"><span class="label">Assessor wrote</span><span class="value mono" style="font-size:0.8rem">${esc(c.remarks)}</span></div>
            <div class="sub">Assessor's notes can be years old. They are not a code-enforcement record; the county publishes none.</div></div>` : ""}
        <div class="detail-section">
            <h3>Owner</h3>
            <div class="detail-row"><span class="label">On record</span><span class="value mono">${esc(r.owner)}</span></div>
            <div class="detail-row"><span class="label">Bill mailed to</span><span class="value">${esc(mailLine(r))}${r.care_of ? ` · c/o ${esc(r.care_of)}` : ""}</span></div>
        </div>
        <div class="detail-section"><h3>${r.parcel_count} parcel${r.parcel_count > 1 ? "s" : ""} · ${money(r.total_value)} assessed</h3>
            ${parcelTable(r.parcels, "<th>Assessor's remarks</th>", (p) => `<td class="sub">${esc(p.remarks || "")}</td>`)}</div>`;
    },
    csvHead: ["Priority", "Signals", "Owner", "Title", "Decedent", "Death Date", "Identity", "Past Due", "Payments Behind", "Unpaid Since", "Sale Eligible", "Condition", "Assessor Remarks", "Mail Address", "Mail City", "Mail State", "Mail Zip", "PIN", "Property", "Assessed", "Status", "Notes"],
    csvRow: (r, p) => {
        const g = r.signals;
        return [r.priority, r.kinds.join("+"), r.owner, g.TITLE ? g.TITLE.label : "", g.DEATH ? g.DEATH.decedent : "", g.DEATH ? g.DEATH.death_date : "", g.DEATH ? g.DEATH.identity_confidence : "",
            g.TAX ? g.TAX.past_due : "", g.TAX ? g.TAX.payments_behind : "", g.TAX ? g.TAX.oldest_due : "", g.TAX ? (g.TAX.sale_eligible ? "yes" : "no") : "", g.CONDITION ? g.CONDITION.label : "", p.remarks || "",
            r.mail.addr, r.mail.city, r.mail.state, r.mail.zip, `="${p.pin}"`, p.address, p.total_value];
    },
});
