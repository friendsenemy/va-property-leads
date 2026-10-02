/* Death Leads and Delinquent tabs. Both are a list of owner rows with a detail modal;
   LeadTab is the shared machinery, the two configs below say what each column shows. */
const esc = (s) => TitleApp.esc(s);
const money = (v) => (v != null && v !== "" && !isNaN(parseFloat(v))) ? "$" + parseFloat(v).toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—";

function parcelTable(parcels, extraHead, extraCell) {
    const gmaps = (p) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.address + ", King George County, VA")}`;
    return `<div class="ptable-wrap"><table class="ptable">
        <thead><tr><th>PIN</th><th>Property</th><th>Assessed</th><th>Last transfer</th><th>Deed / will reference</th>${extraHead || ""}</tr></thead>
        <tbody>${parcels.map((p) => `<tr>
            <td class="mono">${esc(p.parcel || p.pin)}<div><a href="${esc(p.card_url)}" target="_blank" rel="noopener">county card</a></div></td>
            <td>${p.address ? `<a href="${gmaps(p)}" target="_blank" rel="noopener">${esc(p.address)}</a>` : '<span class="sub">no street address</span>'}<div class="sub">${esc(p.legal || "")} · ${p.acres} ac${p.year_built ? ` · built ${p.year_built}` : ""}</div></td>
            <td class="mono">${money(p.total_value)}</td>
            <td class="mono">${TitleApp.transferText(p)}</td>
            <td class="mono">${esc(p.deed_ref || "—")}${p.will_ref ? `<div style="color:var(--purple)">${esc(p.will_ref)}</div>` : ""}</td>
            ${extraCell ? extraCell(p) : ""}
        </tr>`).join("")}</tbody></table></div>`;
}

class LeadTab {
    constructor(cfg) { Object.assign(this, cfg); this.rows = []; this.summary = null; this.local = {}; this.state = { search: "", filter: "all", page: 1, perPage: 25 }; }
    el(id) { return document.getElementById(this.prefix + id); }

    async init() {
        try { this.local = JSON.parse(localStorage.getItem(this.lsKey) || "{}"); } catch { this.local = {}; }
        try {
            const j = await fetch(`${this.url}?t=${Date.now()}`, { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
            this.summary = j.summary; this.rows = j.rows || [];
        } catch { this.rows = []; }
        this.rows.forEach((r) => { r._search = this.searchText(r).toLowerCase(); });
        this.el("Stats").innerHTML = this.summary ? this.stats(this.summary).map(([label, val, color]) =>
            `<div class="stat-card ${color}"><div class="stat-label">${label}</div><div class="stat-value">${val}</div></div>`).join("") : "";
        this.el("Info").textContent = this.summary ? this.info(this.summary) : "";
        this.el("Filters").innerHTML = this.filters.map((f, i) => `<button class="filter-btn ${i ? "" : "active"}" data-f="${f.id}">${f.label}</button>`).join("");
        this.el("Filters").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
            this.el("Filters").querySelectorAll("button").forEach((x) => x.classList.remove("active"));
            b.classList.add("active"); this.state.filter = b.dataset.f; this.state.page = 1; this.render();
        }));
        let t;
        this.el("Search").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { this.state.search = e.target.value.trim().toLowerCase(); this.state.page = 1; this.render(); }, 200); });
        this.el("Prev").addEventListener("click", () => { if (this.state.page > 1) { this.state.page--; this.render(); } });
        this.el("Next").addEventListener("click", () => { this.state.page++; this.render(); });
        this.el("Export").addEventListener("click", () => this.exportCsv());
        this.render();
    }

    statusOf(r) { return (this.local[r.id] && this.local[r.id].status) || "new"; }
    notesOf(r) { return (this.local[r.id] && this.local[r.id].notes) || ""; }

    filtered() {
        const f = this.filters.find((x) => x.id === this.state.filter);
        return this.rows.filter((r) => (!f || !f.test || f.test(r)) &&
            (!this.state.search || this.state.search.split(/\s+/).every((w) => r._search.includes(w))));
    }

    render() {
        const rows = this.filtered();
        const pages = Math.max(1, Math.ceil(rows.length / this.state.perPage));
        if (this.state.page > pages) this.state.page = pages;
        const start = (this.state.page - 1) * this.state.perPage;
        const page = rows.slice(start, start + this.state.perPage);
        this.el("Head").innerHTML = "<tr>" + this.columns.map((c) => `<th>${c}</th>`).join("") + "<th>Status</th></tr>";
        this.el("Body").innerHTML = page.map((r) => {
            const st = this.statusOf(r);
            return `<tr data-id="${esc(r.id)}">${this.row(r).map((c) => `<td>${c}</td>`).join("")}<td><span class="status-badge ${st}">${st.toUpperCase()}</span>${this.notesOf(r) ? '<span class="note-badge">✎</span>' : ""}</td></tr>`;
        }).join("");
        this.el("Body").querySelectorAll("tr").forEach((tr) => tr.addEventListener("click", () => this.open(tr.dataset.id)));
        this.el("Empty").style.display = page.length ? "none" : "block";
        this.el("Empty").innerHTML = `<div class="icon">${this.rows.length ? "🔎" : "🕊️"}</div><h3>${this.rows.length ? "No matches" : this.emptyTitle}</h3><p>${this.rows.length ? "Loosen the filter or the search." : this.emptyText}</p>`;
        this.el("PageInfo").textContent = rows.length ? `Showing ${start + 1}–${Math.min(start + this.state.perPage, rows.length)} of ${rows.length}` : "Nothing to show";
        this.el("Prev").disabled = this.state.page <= 1;
        this.el("Next").disabled = this.state.page >= pages;
    }

    open(id) {
        const r = this.rows.find((x) => x.id === id);
        if (!r) return;
        document.getElementById("modalTitle").textContent = this.title(r);
        document.getElementById("modalBody").innerHTML = this.detail(r, this.summary);
        const sel = document.getElementById("leadStatusSelect"), notes = document.getElementById("leadNotes");
        sel.value = this.statusOf(r); notes.value = this.notesOf(r);
        document.getElementById("saveLeadBtn").onclick = () => {
            this.local[r.id] = { status: sel.value, notes: notes.value, updated: new Date().toISOString() };
            try { localStorage.setItem(this.lsKey, JSON.stringify(this.local)); } catch {}
            document.getElementById("modalOverlay").classList.remove("active"); this.render();
        };
        document.getElementById("modalOverlay").classList.add("active");
    }

    exportCsv() {
        const q = (v) => { const s = String(v == null ? "" : v); return /^=".*"$/.test(s) ? s : `"${s.replace(/"/g, '""')}"`; };
        const lines = [this.csvHead.join(",")];
        this.filtered().forEach((r) => r.parcels.forEach((p) => lines.push(this.csvRow(r, p).concat([this.statusOf(r), this.notesOf(r)]).map(q).join(","))));
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" }));
        a.download = `kg-${this.prefix}-${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a); a.click(); a.remove();
    }
}

function taxBlock(r) {
    const d = r.delinquency;
    if (d) return `<div class="detail-section"><h3>Taxes — delinquent</h3>
        <div class="detail-row"><span class="label">Past due</span><span class="value mono" style="color:var(--red)">${money(d.past_due)}</span></div>
        <div class="detail-row"><span class="label">Payments behind</span><span class="value">${d.payments_behind} half-year installment${d.payments_behind === 1 ? "" : "s"} · tax years ${d.years.join(", ")} · unpaid since ${esc(d.oldest_due)}</span></div>
        <div class="detail-row"><span class="label">Sale status</span><span class="value">${d.sale_eligible ? "Old enough for the county to sue to sell (Va. Code § 58.1-3965)" : "Not yet old enough for the county to sue"}</span></div>
        <div class="detail-row"><span class="label">Checked</span><span class="value">${esc(d.checked)} · Treasurer's inquiry; confirm before calling</span></div></div>`;
    return `<div class="detail-section"><h3>Taxes</h3><div class="detail-row"><span class="label">Status</span><span class="value">${r.tax_checked
        ? `No prior-year balance as of ${esc(r.tax_checked)} (Treasurer's inquiry)` : "Not checked yet. The Treasurer walk reaches every parcel once a month."}</span></div></div>`;
}

const mailLine = (r) => [r.mail.addr, `${r.mail.city || ""}${r.mail.state ? ", " + r.mail.state : ""} ${r.mail.zip || ""}`].filter((x) => x && x.trim()).join(", ");
const conf = (c) => `<span class="prio prio-${c === "HIGH" ? "high" : "mid"}">${c}</span>`;

const DeathApp = new LeadTab({
    prefix: "death", url: "data/obits/matches.json", lsKey: "va_death_leads_local_v1",
    emptyTitle: "No obituary matches yet", emptyText: "The obituary match runs with the nightly job.",
    columns: ["Died", "Decedent", "Owner on Record", "Property", "Class", "Identity", "Assessed"],
    filters: [
        { id: "all", label: "All" },
        { id: "high", label: "High confidence", test: (r) => r.identity_confidence === "HIGH" },
        { id: "sole", label: "Sole or all owners died", test: (r) => r.death_class !== "D4" },
        { id: "stale", label: "Died 2+ years ago, title unchanged", test: (r) => r.years_since_death >= 2 },
        { id: "recent", label: "Last 12 months", test: (r) => r.years_since_death != null && r.years_since_death <= 1 },
        { id: "old", label: "Died before 2008 (federal record)", test: (r) => r.death_date && r.death_date < "2008" },
    ],
    stats: (s) => [["Owners Matched to a Death", s.matches, "pink"], ["High Identity Confidence", s.high, "yellow"],
        ["Sole / All Owners Died", (s.classes.D1 || 0) + (s.classes.D5 || 0), "purple"], ["Death Records on File", Number(s.obituaries).toLocaleString(), "cyan"]],
    info: (s) => "Death records: " + Object.entries(s.sources || {}).map(([k, v]) => `${k} (${Number(v.count).toLocaleString()}, ${v.from.slice(0, 4)}–${v.to.slice(0, 4)})`).join("; ") +
        `. Each person on a title is matched separately. Name-only matches (${s.low_hidden}) are not shown.`,
    searchText: (r) => `${r.decedent} ${r.owner} ${r.place} ${r.mail.city} ${r.class_label} ${r.parcels.map((p) => p.address + " " + p.pin).join(" ")}`,
    title: (r) => r.decedent,
    row: (r) => [
        `<span class="mono" style="white-space:nowrap">${esc(r.death_date || "date not parsed")}</span>${r.years_since_death != null ? `<div class="sub">${r.years_since_death} yrs ago</div>` : ""}`,
        `<b>${esc(r.decedent)}</b><div class="sub">${r.age ? "age " + r.age : ""}${r.place ? " · of " + esc(r.place) : ""}</div>`,
        `<span class="mono" style="font-size:0.8rem">${esc(r.owner)}</span>${r.other_owners.length ? `<div class="sub">also on title: ${esc(r.other_owners.join("; "))}</div>` : ""}`,
        `<div class="address">${esc((r.parcels.find((p) => p.address) || {}).address || "No street address (land)")}</div><div class="meta">${r.parcel_count > 1 ? r.parcel_count + " parcels" : esc(r.parcels[0].legal || "")}</div>`,
        `<span class="cls cls-E">${r.death_class}</span> <span class="sub">${esc(r.class_label)}</span>${r.title_class ? ` <span class="chip chip-strong">also ${r.title_class}</span>` : ""}`,
        conf(r.identity_confidence) + (r.delinquency ? `<div><span class="chip chip-strong">${money(r.delinquency.past_due)} past due</span></div>` : ""),
        `<span class="value-cell">${money(r.total_value)}</span>`,
    ],
    detail: (r, s) => `
        <div class="detail-section">
            <h3>${r.death_class} — ${esc(r.class_label)}</h3>
            <div class="next-step"><b>Next step.</b> ${esc(s.next_step[r.death_class])}</div>
            <div class="verify">The death is certain (a published record). Whether this is the same person as the owner on title is an inference from name, place and dates: <b>${r.identity_confidence}</b> confidence. Verify before contact, and be decent about it: this is someone's family.</div>
        </div>
        <div class="detail-section">
            <h3>Death record</h3>
            <div class="detail-row"><span class="label">Decedent</span><span class="value" style="font-weight:600">${esc(r.decedent)}${r.age ? `, ${r.age}` : ""}${r.place ? ` · of ${esc(r.place)}` : ""}</span></div>
            <div class="detail-row"><span class="label">Died</span><span class="value mono">${esc(r.death_date || "—")}${r.birth_date ? ` · born ${esc(r.birth_date)}` : ""}</span></div>
            <div class="detail-row"><span class="label">Source</span><span class="value">${esc(r.source)}${r.obituary_url ? ` · <a style="color:var(--cyan-dim)" href="${esc(r.obituary_url)}" target="_blank" rel="noopener">${/NUMIDENT/.test(r.source) ? "about this federal record (no survivors listed; look for the heirs in the Clerk's will books)" : "read the obituary (survivors are listed there)"}</a>` : ""}</span></div>
            ${(r.heirs || []).length ? `<div class="detail-row"><span class="label">Heirs on file</span><span class="value">${r.heirs.map(esc).join("<br>")}</span></div>` : ""}
            <div class="detail-row"><span class="label">Why it matches</span><span class="value"><ul class="reasons">${r.identity_reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></span></div>
        </div>
        <div class="detail-section">
            <h3>Owner on record</h3>
            <div class="detail-row"><span class="label">Title reads</span><span class="value mono">${esc(r.owner)}</span></div>
            <div class="detail-row"><span class="label">Matched person</span><span class="value">${esc(r.matched_owner)}${r.other_owners.length ? ` · others on title: ${esc(r.other_owners.join("; "))}` : ""}</span></div>
            <div class="detail-row"><span class="label">Bill mailed to</span><span class="value">${esc(mailLine(r))}</span></div>
        </div>
        ${taxBlock(r)}
        <div class="detail-section"><h3>${r.parcel_count} parcel${r.parcel_count > 1 ? "s" : ""} · ${money(r.total_value)} assessed</h3>${parcelTable(r.parcels)}</div>`,
    csvHead: ["Death Date", "Decedent", "Age", "Of", "Class", "Identity", "Owner On Record", "Other Owners", "Mail Address", "Mail City", "Mail State", "Mail Zip", "PIN", "Property", "Assessed", "Last Transfer", "Deed Ref", "Obituary", "Status", "Notes"],
    csvRow: (r, p) => [r.death_date, r.decedent, r.age, r.place, r.death_class, r.identity_confidence, r.owner, r.other_owners.join("; "), r.mail.addr, r.mail.city, r.mail.state, r.mail.zip, `="${p.pin}"`, p.address, p.total_value, p.sale_year_estimated ? "" : p.sale_year, p.deed_ref, r.obituary_url],
});

const DelinqApp = new LeadTab({
    prefix: "delinq", url: "data/delinquency/leads.json", lsKey: "va_delinq_leads_local_v1",
    emptyTitle: "No delinquency data yet", emptyText: "The Treasurer walk runs over four nights at the start of each month.",
    columns: ["Priority", "Owner on Record", "Property", "Class", "Behind", "Past Due", "Assessed", "Bill Mailed To"],
    filters: [
        { id: "all", label: "All" },
        { id: "elig", label: "Sale-eligible", test: (r) => r.sale_eligible },
        { id: "profile", label: "Unreported-death profile", test: (r) => r.delinquency_class === "P1" },
        { id: "title", label: "Also a title lead", test: (r) => !!r.title_class },
        { id: "entity", label: "Companies / associations / churches", test: (r) => ["BUSINESS", "ASSOCIATION", "CHURCH"].includes(r.owner_type) },
    ],
    stats: (s) => [["Delinquent Owners", s.leads, "yellow"], ["Sale-Eligible (2+ yrs)", s.classes.T1 || 0, "pink"],
        ["Unreported-Death Profile", s.classes.P1 || 0, "purple"], ["Parcels Checked", `${Number(s.parcels_checked).toLocaleString()} / ${Number(s.parcels_in_county).toLocaleString()}`, "cyan"]],
    info: (s) => `Treasurer's Real Estate Public Inquiry, last checked ${s.last_checked || "—"}. Owners with only the current bill late are not shown. ${money(s.past_due_total)} past due across the list. Balances move daily: confirm on the Treasurer's site before you call.`,
    searchText: (r) => `${r.owner} ${r.treasurer_name} ${r.mail.city} ${r.mail.state} ${r.class_label} ${r.parcels.map((p) => p.address + " " + p.pin).join(" ")}`,
    title: (r) => r.owner,
    row: (r) => [
        `<span class="prio prio-${TitleApp.tier(r.priority)}">${r.priority}</span>`,
        `<span class="mono" style="font-size:0.8rem">${esc(r.owner)}</span>${r.name_differs ? `<div class="sub">Treasurer bills: ${esc(r.treasurer_name)}</div>` : ""}`,
        `<div class="address">${esc((r.parcels.find((p) => p.address) || {}).address || "No street address (land)")}</div><div class="meta">${r.parcel_count > 1 ? r.parcel_count + " parcels" : esc(r.parcels[0].legal || "")}</div>`,
        `<span class="cls cls-${r.delinquency_class === "P1" ? "W" : r.sale_eligible ? "E" : "C"}">${r.delinquency_class}</span> <span class="sub">${esc(r.class_label)}</span>${r.title_class ? ` <span class="chip chip-strong">also ${r.title_class}</span>` : ""}`,
        `<span class="mono">${r.payments_behind} payment${r.payments_behind === 1 ? "" : "s"}</span><div class="sub">tax years ${r.years[0]}${r.years.length > 1 ? "–" + r.years[r.years.length - 1] : ""} · unpaid since ${esc(r.oldest_due)}</div>`,
        `<span class="mono" style="color:var(--red)">${money(r.past_due)}</span>`,
        `<span class="value-cell">${money(r.total_value)}</span>`,
        `${esc(r.mail.city || "—")}${r.mail.state ? ", " + esc(r.mail.state) : ""}`,
    ],
    detail: (r, s) => `
        <div class="detail-section">
            <h3>${r.delinquency_class} — ${esc(r.class_label)} <span class="prio prio-${TitleApp.tier(r.priority)}" style="margin-left:8px">${r.priority}</span></h3>
            <div class="next-step"><b>Next step.</b> ${esc(s.next_step[r.delinquency_class])}</div>
            <div class="verify">Balances are the Treasurer's as of ${esc(r.parcels[0].checked)} and can be paid any day. In Virginia the property itself is sold and there is no redemption after the sale date, so the window is before the auction.</div>
        </div>
        <div class="detail-section">
            <h3>Owner</h3>
            <div class="detail-row"><span class="label">GIS owner</span><span class="value mono">${esc(r.owner)}</span></div>
            <div class="detail-row"><span class="label">Treasurer bills</span><span class="value mono">${esc(r.treasurer_name || "—")}${r.name_differs ? ' <span class="chip chip-strong">differs from GIS</span>' : ""}</span></div>
            <div class="detail-row"><span class="label">Bill mailed to</span><span class="value">${esc(mailLine(r))}${r.care_of ? ` · c/o ${esc(r.care_of)}` : ""}</span></div>
            <div class="detail-row"><span class="label">Past due</span><span class="value mono" style="color:var(--red)">${money(r.past_due)}</span></div>
            <div class="detail-row"><span class="label">Payments behind</span><span class="value">${r.payments_behind} half-year installment${r.payments_behind === 1 ? "" : "s"} unpaid (bills are due each June and December) · tax years ${r.years.join(", ")}</span></div>
            <div class="detail-row"><span class="label">Unpaid since</span><span class="value mono">${esc(r.oldest_due)}</span></div>
            <div class="detail-row"><span class="label">Sale status</span><span class="value">${r.sale_eligible ? "Old enough for the county to sue to sell (Va. Code § 58.1-3965). No King George sale is listed by counsel today unless the banner at the top says so." : "Not yet old enough for the county to sue."}</span></div>
            ${r.not_yet_due ? `<div class="detail-row"><span class="label">Billed, not yet due</span><span class="value mono">${money(r.not_yet_due)}</span></div>` : ""}
        </div>
        <div class="detail-section"><h3>${r.parcel_count} parcel${r.parcel_count > 1 ? "s" : ""} · ${money(r.total_value)} assessed</h3>
            ${parcelTable(r.parcels, "<th>Past due</th>", (p) => `<td class="mono" style="color:var(--red)">${money(p.past_due)}<div class="sub">${p.payments_behind} payments · ${p.years[0]}${p.years.length > 1 ? "–" + p.years[p.years.length - 1] : ""}${p.sale_eligible ? " · sale-eligible" : ` · eligible after ${esc(p.sale_eligible_on)}`}</div></td>`)}
        </div>`,
    csvHead: ["Priority", "Class", "Owner", "Treasurer Name", "Past Due", "Payments Behind", "Unpaid Years", "Oldest Due", "Sale Eligible", "Mail Address", "Mail City", "Mail State", "Mail Zip", "PIN", "Property", "Assessed", "Parcel Past Due", "Checked", "Status", "Notes"],
    csvRow: (r, p) => [r.priority, r.delinquency_class, r.owner, r.treasurer_name, r.past_due, r.payments_behind, r.years.join(" "), r.oldest_due, r.sale_eligible ? "yes" : "no", r.mail.addr, r.mail.city, r.mail.state, r.mail.zip, `="${p.pin}"`, p.address, p.total_value, p.past_due, p.checked],
});
