/* Title Leads tab. Reads data/title/summary.json and data/title/leads.json.
   One row is one owner (parcels listed inside). Status + notes live in localStorage. */
const TITLE_LS_KEY = "va_title_leads_local_v1";

const TitleApp = {
    summary: null,
    rows: [],
    local: {},
    extra: [],   // modal sections contributed by later layers (obituaries, delinquency, ...)
    state: { preset: "", search: "", minPriority: 0, status: "all", sort: "priority", dir: -1, page: 1, perPage: 25 },

    FLAGS: {
        ESTATE_IN_NAME: "Estate", HEIRS_IN_NAME: "Heirs of", LIFE_ESTATE: "Life Estate", EXECUTOR_IN_NAME: "Executor named",
        ET_AL: "Et Al", LIST_OF_HEIRS_REF: "List of Heirs ref", WILL_BOOK_REF: "Will Book ref",
        ASSESSOR_DOD_NOTE: "Death noted", ASSESSOR_WILL_NOTE: "Will noted",
        OLD_TITLE_40: "40+ yrs", OLD_TITLE_25: "25+ yrs", OLD_TITLE_12: "12+ yrs",
        OUT_OF_STATE: "Out of state", OUT_OF_COUNTY: "Out of county", MAIL_DIFFERS: "Mail ≠ site", CARE_OF: "C/O",
        VACANT_LAND: "No building", POOR_CONDITION: "Fair/poor cond.", SURVIVORSHIP_OR: "A or B",
    },
    STRONG: new Set(["ESTATE_IN_NAME", "HEIRS_IN_NAME", "LIFE_ESTATE", "EXECUTOR_IN_NAME", "LIST_OF_HEIRS_REF", "ASSESSOR_DOD_NOTE"]),

    async init() {
        this.loadLocal();
        this.bindEvents();
        try {
            const [s, l] = await Promise.all([
                fetch(`data/title/summary.json?t=${Date.now()}`, { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
                fetch(`data/title/leads.json?t=${Date.now()}`, { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
            ]);
            this.summary = s;
            this.rows = (l.rows || []).map((x) => this.decorate(x));
        } catch (e) {
            document.getElementById("titleEmpty").style.display = "block";
            document.getElementById("runInfo").textContent = "No scan data yet";
            return;
        }
        this.renderSummary();
        this.render();
    },

    decorate(r) {
        const p0 = r.parcels[0] || {};
        const best = r.parcels.find((p) => p.address) || p0;
        return Object.assign(r, {
            _addr: best.address || "",
            _years: r.oldest_transfer_years,
            _mail: `${r.mail.city || ""} ${r.mail.state || ""}`.trim(),
            _search: [r.owner, r.care_of, r.class_label, r.title_class, r.mail.addr, r.mail.city, r.mail.state,
                (r.people || []).join(" "), (r.flags || []).map((f) => this.FLAGS[f] || f).join(" "),
                r.parcels.map((p) => `${p.address} ${p.pin} ${p.parcel} ${p.legal} ${p.note} ${p.deed_ref} ${p.will_ref}`).join(" ")].join(" ").toLowerCase(),
        });
    },

    renderSummary() {
        const s = this.summary, c = s.classes || {};
        document.getElementById("tstatLeads").textContent = Number(s.leads || 0).toLocaleString();
        document.getElementById("tstatEstate").textContent = ((c.E1 || 0) + (c.E2 || 0)).toLocaleString();
        document.getElementById("tstatParcels").textContent = Number(s.lead_parcels || 0).toLocaleString();
        document.getElementById("tstatIndexed").textContent = Number(s.parcels_indexed || 0).toLocaleString();
        document.getElementById("runInfo").innerHTML = `Parcels pulled ${this.fmtDT(s.index_built_at)}<br>Scan ${this.fmtDT(s.generated_at)}`;
        document.getElementById("titleRunInfo").textContent =
            (s.class_order || []).filter((k) => c[k]).map((k) => `${k} ${s.class_labels[k]}: ${c[k]}`).join(" · ");
        const presets = document.getElementById("titlePresets");
        presets.innerHTML = `<button class="filter-btn active" data-preset="">All</button>` +
            (s.presets || []).map((p) => `<button class="filter-btn" data-preset="${p.id}">${this.esc(p.label)}</button>`).join("");
        presets.querySelectorAll(".filter-btn").forEach((b) => b.addEventListener("click", () => {
            presets.querySelectorAll(".filter-btn").forEach((x) => x.classList.remove("active"));
            b.classList.add("active"); this.state.preset = b.dataset.preset; this.state.page = 1; this.render();
        }));
    },

    loadLocal() { try { this.local = JSON.parse(localStorage.getItem(TITLE_LS_KEY) || "{}"); } catch { this.local = {}; } },
    saveLocal() { try { localStorage.setItem(TITLE_LS_KEY, JSON.stringify(this.local)); } catch {} },
    statusOf(r) { return (this.local[r.id] && this.local[r.id].status) || "new"; },
    notesOf(r) { return (this.local[r.id] && this.local[r.id].notes) || ""; },

    bindEvents() {
        let t;
        document.getElementById("titleSearch").addEventListener("input", (e) => {
            clearTimeout(t); t = setTimeout(() => { this.state.search = e.target.value.trim().toLowerCase(); this.state.page = 1; this.render(); }, 200);
        });
        const slider = document.getElementById("titleMinPriority");
        slider.addEventListener("input", () => {
            this.state.minPriority = parseInt(slider.value, 10) || 0;
            document.getElementById("titleMinPriorityVal").textContent = this.state.minPriority;
            this.state.page = 1; this.render();
        });
        document.querySelectorAll("#titleStatusFilters .filter-btn").forEach((b) => b.addEventListener("click", () => {
            document.querySelectorAll("#titleStatusFilters .filter-btn").forEach((x) => x.classList.remove("active"));
            b.classList.add("active"); this.state.status = b.dataset.status; this.state.page = 1; this.render();
        }));
        document.querySelectorAll("#titleTable th[data-sort]").forEach((th) => th.addEventListener("click", () => {
            const k = th.dataset.sort;
            if (this.state.sort === k) this.state.dir *= -1; else { this.state.sort = k; this.state.dir = k === "owner" || k === "mail" || k === "cls" ? 1 : -1; }
            this.render();
        }));
        document.getElementById("titlePrev").addEventListener("click", () => { if (this.state.page > 1) { this.state.page--; this.render(); } });
        document.getElementById("titleNext").addEventListener("click", () => { this.state.page++; this.render(); });
        document.getElementById("titleExport").addEventListener("click", () => this.exportCsv());
        const close = () => document.getElementById("modalOverlay").classList.remove("active");
        document.getElementById("modalClose").addEventListener("click", close);
        document.getElementById("modalOverlay").addEventListener("click", (e) => { if (e.target.id === "modalOverlay") close(); });
        document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    },

    filtered() {
        const st = this.state;
        const preset = st.preset && this.summary ? (this.summary.presets || []).find((p) => p.id === st.preset) : null;
        return this.rows.filter((r) => {
            if (r.priority < st.minPriority) return false;
            if (st.status !== "all" && this.statusOf(r) !== st.status) return false;
            if (preset) {
                if (preset.classes && !preset.classes.includes(r.title_class)) return false;
                if (preset.flag && !(r.flags || []).includes(preset.flag)) return false;
                if (preset.flags_any && !(r.flags || []).some((f) => preset.flags_any.includes(f))) return false;
            }
            if (st.search && !st.search.split(/\s+/).every((w) => r._search.includes(w))) return false;
            return true;
        });
    },

    sorted(rows) {
        const k = this.state.sort, d = this.state.dir;
        const order = (this.summary && this.summary.class_order) || [];
        const val = {
            priority: (r) => r.priority, owner: (r) => r.owner, cls: (r) => order.indexOf(r.title_class),
            years: (r) => (r._years == null ? -1 : r._years), value: (r) => r.total_value, mail: (r) => `${r.mail.state || ""} ${r.mail.city || ""}`,
        }[k];
        return rows.slice().sort((a, b) => {
            const x = val(a), y = val(b);
            if (x < y) return -1 * d; if (x > y) return 1 * d;
            return b.priority - a.priority || b.total_value - a.total_value;
        });
    },

    transferText(p) {
        if (p.sale_year && !p.sale_year_estimated) return `${p.sale_year} <span class="yrs">(${p.years_since_transfer}y)</span>`;
        if (p.sale_year_estimated) return `undated <span class="yrs">(old deed book)</span>`;
        return `<span class="yrs">not on record</span>`;
    },

    render() {
        const rows = this.sorted(this.filtered());
        const pages = Math.max(1, Math.ceil(rows.length / this.state.perPage));
        if (this.state.page > pages) this.state.page = pages;
        const start = (this.state.page - 1) * this.state.perPage;
        const page = rows.slice(start, start + this.state.perPage);
        const tbody = document.getElementById("titleBody");
        const empty = document.getElementById("titleEmpty");
        if (!page.length) {
            tbody.innerHTML = ""; empty.style.display = "block";
            if (this.rows.length) { document.getElementById("titleEmptyTitle").textContent = "No matches"; document.getElementById("titleEmptyText").textContent = "Loosen the preset, priority, or search."; }
        } else {
            empty.style.display = "none";
            tbody.innerHTML = page.map((r) => {
                const st = this.statusOf(r);
                const oldest = r.parcels.reduce((a, p) => ((p.years_since_transfer || -1) > (a.years_since_transfer || -1) ? p : a), r.parcels[0]);
                const more = r.parcel_count > 1 ? `${r.parcel_count} parcels · ${Number(r.acres).toLocaleString()} ac` : `${this.esc(r.parcels[0].legal || "")}`;
                return `<tr data-id="${this.esc(r.id)}">
                    <td><span class="prio prio-${this.tier(r.priority)}">${r.priority}</span></td>
                    <td class="name-cell" style="font-family:var(--font-mono); font-size:0.8rem">${this.esc(r.owner)}${r.care_of ? `<div class="sub">c/o ${this.esc(r.care_of)}</div>` : ""}${this.notesOf(r) ? '<span class="note-badge" title="Has notes">✎</span>' : ""}</td>
                    <td class="property-cell">
                        <div class="address">${this.esc(r._addr || "No street address (land)")}</div>
                        <div class="meta">${more}</div>
                    </td>
                    <td><span class="cls cls-${r.title_class[0]}" title="${this.esc(r.class_label)}">${r.title_class}</span> <span class="sub">${this.esc(r.class_label)}</span><div>${this.flagChips(r.flags)}</div></td>
                    <td class="date-cell">${this.transferText(oldest)}</td>
                    <td class="value-cell">$${Number(r.total_value).toLocaleString()}</td>
                    <td class="county-cell">${this.esc(r.mail.city || "—")}${r.mail.state ? `, ${this.esc(r.mail.state)}` : ""}</td>
                    <td><span class="status-badge ${st}">${st.toUpperCase()}</span></td>
                </tr>`;
            }).join("");
            tbody.querySelectorAll("tr").forEach((tr) => tr.addEventListener("click", () => this.open(tr.dataset.id)));
        }
        const total = rows.length;
        document.getElementById("titlePageInfo").textContent = total ? `Showing ${start + 1}–${Math.min(start + this.state.perPage, total)} of ${total} leads` : "No leads";
        document.getElementById("titlePrev").disabled = this.state.page <= 1;
        document.getElementById("titleNext").disabled = this.state.page >= pages;
    },

    open(id) {
        const r = this.rows.find((x) => x.id === id);
        if (!r) return;
        const money = (v) => (v != null && v !== "" && !isNaN(parseFloat(v))) ? "$" + parseFloat(v).toLocaleString() : "—";
        const mail = [r.mail.addr, r.mail.addr2, `${r.mail.city || ""}${r.mail.state ? ", " + r.mail.state : ""} ${r.mail.zip || ""}`].filter((x) => x && x.trim()).join(", ");
        const next = (this.summary.next_step || {})[r.title_class] || "";
        const gmaps = (p) => p.address ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.address + ", King George County, VA")}` : "";
        document.getElementById("modalTitle").textContent = r.owner;
        document.getElementById("modalBody").innerHTML = `
            <div class="detail-section">
                <h3>${r.title_class} — ${this.esc(r.class_label)} <span class="prio prio-${this.tier(r.priority)}" style="margin-left:8px">${r.priority}</span></h3>
                <div class="next-step"><b>Next step.</b> ${this.esc(next)}</div>
                <div class="verify">This row comes from the county's assessment record only. It shows how title reads, not who is alive, who the heirs are, or whether taxes are paid. Verify in the Clerk's records before contacting anyone.</div>
                <div style="margin-top:10px">${this.flagChips(r.flags)}</div>
                <ul class="reasons" style="margin-top:8px">${(r.reasons || []).map((x) => `<li>${this.esc(x)}</li>`).join("")}</ul>
            </div>
            <div class="detail-section">
                <h3>Owner</h3>
                <div class="detail-row"><span class="label">On record</span><span class="value" style="font-family:var(--font-mono)">${this.esc(r.owner_raw[0])}${r.owner_raw[1] ? `<br>${this.esc(r.owner_raw[1])}` : ""}</span></div>
                <div class="detail-row"><span class="label">Read as</span><span class="value">${this.esc(r.owner_type.replace("_", " "))}${r.owner_subtype ? " · " + this.esc(r.owner_subtype.replace("_", " ").toLowerCase()) : ""}${(r.people || []).length ? ` — ${r.people.map((x) => this.esc(x)).join("; ")}` : ""}</span></div>
                ${r.care_of ? `<div class="detail-row"><span class="label">Care of</span><span class="value">${this.esc(r.care_of)}</span></div>` : ""}
                <div class="detail-row"><span class="label">Bill mailed to</span><span class="value">${this.esc(mail || "—")}</span></div>
                ${r.note_dod ? `<div class="detail-row"><span class="label">Death noted</span><span class="value" style="font-family:var(--font-mono)">${this.esc(r.note_dod)} <span class="sub">(assessor's note)</span></span></div>` : ""}
            </div>
            ${this.extra.map((fn) => fn(r) || "").join("")}
            <div class="detail-section">
                <h3>${r.parcel_count} parcel${r.parcel_count > 1 ? "s" : ""} · ${money(r.total_value)} assessed · ${Number(r.acres).toLocaleString()} acres</h3>
                <div class="ptable-wrap"><table class="ptable">
                    <thead><tr><th>PIN</th><th>Property</th><th>Assessed</th><th>Last transfer</th><th>Deed / will reference</th><th>Assessor's note</th></tr></thead>
                    <tbody>${r.parcels.map((p) => `<tr>
                        <td class="mono">${this.esc(p.parcel || p.pin)}<div><a href="${this.esc(p.card_url)}" target="_blank" rel="noopener">county card</a></div></td>
                        <td>${p.address ? `<a href="${gmaps(p)}" target="_blank" rel="noopener">${this.esc(p.address)}</a>` : '<span class="sub">no street address</span>'}<div class="sub">${this.esc(p.legal || "")} · ${p.acres} ac${p.year_built ? ` · built ${p.year_built}` : ""}${p.cond ? ` · cond ${this.esc(p.cond)}` : ""}</div></td>
                        <td class="mono">${money(p.total_value)}<div class="sub">${money(p.land_value)} land</div></td>
                        <td class="mono">${this.transferText(p)}${p.sale_price ? `<div class="sub">${money(p.sale_price)}</div>` : ""}</td>
                        <td class="mono">${this.esc(p.deed_ref || "—")}${p.will_ref ? `<div style="color:var(--purple)">${this.esc(p.will_ref)}</div>` : ""}${p.will_ref_raw && !p.will_ref ? `<div class="sub">will field: ${this.esc(p.will_ref_raw)}</div>` : ""}</td>
                        <td class="sub">${this.esc(p.note || "")}</td>
                    </tr>`).join("")}</tbody>
                </table></div>
                <div class="sub" style="margin-top:8px">“DB / PG” is a deed book and page. “Instr.” is an instrument number within that year (the Clerk stopped using book and page about 2006). Type either into the Clerk's land-records search by hand.</div>
            </div>`;
        const sel = document.getElementById("leadStatusSelect"), notes = document.getElementById("leadNotes");
        sel.value = this.statusOf(r); notes.value = this.notesOf(r);
        document.getElementById("saveLeadBtn").onclick = () => {
            this.local[r.id] = { status: sel.value, notes: notes.value, updated: new Date().toISOString() };
            this.saveLocal(); document.getElementById("modalOverlay").classList.remove("active"); this.render();
        };
        document.getElementById("modalOverlay").classList.add("active");
    },

    exportCsv() {
        const rows = this.sorted(this.filtered());
        const H = ["Priority", "Class", "Class Label", "Owner", "Care Of", "Owner Type", "People", "Mail Address", "Mail City", "Mail State", "Mail Zip",
            "Signals", "Parcels", "Total Assessed", "Acres", "PIN", "Property Address", "Legal", "Parcel Assessed", "Year Built", "Last Transfer Year",
            "Years Since Transfer", "Sale Price", "Deed Ref", "Will Ref", "Death Noted", "Assessor Note", "County Card", "Status", "Notes"];
        const q = (v) => { const s = String(v == null ? "" : v); return /^=".*"$/.test(s) ? s : `"${s.replace(/"/g, '""')}"`; };
        const lines = [H.join(",")];
        rows.forEach((r) => r.parcels.forEach((p) => lines.push([
            r.priority, r.title_class, r.class_label, r.owner, r.care_of, r.owner_type, (r.people || []).join("; "), r.mail.addr, r.mail.city, r.mail.state, r.mail.zip,
            (r.flags || []).map((f) => this.FLAGS[f] || f).join("|"), r.parcel_count, r.total_value, r.acres, `="${p.pin}"`, p.address, p.legal, p.total_value, p.year_built,
            p.sale_year_estimated ? "" : p.sale_year, p.years_since_transfer, p.sale_price, p.deed_ref, p.will_ref || p.will_ref_raw, p.note_dod, p.note, p.card_url, this.statusOf(r), this.notesOf(r),
        ].map(q).join(","))));
        const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `kg-title-leads-${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    },

    tier(n) { return n >= 70 ? "high" : n >= 50 ? "mid" : "low"; },
    flagChips(flags) {
        return (flags || []).filter((f) => this.FLAGS[f]).map((f) => `<span class="chip ${this.STRONG.has(f) ? "chip-strong" : ""}">${this.FLAGS[f]}</span>`).join(" ");
    },
    fmtDT(s) { const d = new Date(s); return isNaN(d) ? (s || "") : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); },
    esc(s) { return s == null ? "" : String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); },
};
