/* Dirt Deals tab — raw land a homebuilder would want once approved (Cody Bjugan's LDP play),
   the same tab as the Maryland tool. Data: <county>/land/candidates.json, written weekly by
   engine/land_watch.py. Virginia has no statewide sewer-tier map, so each county's own growth
   layers stand in: King George Settlement Areas, Service Authority water/sewer areas and the
   water and sewer lines being built now; Fauquier Service Districts with their planned density,
   zoning and nearby rezonings; Westmoreland distance to Colonial Beach and Montross.
   Notes key: va:<ns>land:<pid>, so each county's notes stay apart. */
const LandApp = {
    rows: [], meta: {},
    state: { search: "", tier: "", minAcres: 0, seller: false, water: false, hideRezone: false, distress: "",
             sort: "score", dir: -1, page: 1, perPage: 25 },

    TIER_LABEL: { "1": "Utilities / growth now", "2": "Growth area · utilities coming", "3": "Rural · well and septic", "": "—" },
    TAG_LABEL: {
        RAW_LAND: "Raw land", NEW_HOMES_NEARBY: "New homes nearby", BUILDER_BUYING_NEARBY: "Builders buying nearby",
        LONG_HELD: "Long-held", OUT_OF_STATE: "Out of state", MESSY_TITLE: "Messy title", WATERFRONT: "Waterfront",
        RECENT_REZONING: "Rezoning filed nearby", NEEDS_REZONING: "Needs rezoning", RECENT_SALE: "Recently sold",
    },
    SELLER_TAGS: ["LONG_HELD", "OUT_OF_STATE", "MESSY_TITLE"],
    DISTRESS_LABEL: { DEATH: "Owner died / estate", TAX: "Unpaid taxes", CONDITION: "Assessor condition note" },

    async init() {
        this.bindEvents();
        document.addEventListener("vapl:notes-loaded", () => { if (this.rows.length) this.render(); });
        try {
            const r = await fetch(`${VAPL.DATA}land/candidates.json?t=${Date.now()}`, { cache: "no-store" });
            if (!r.ok) throw new Error(r.status);
            const j = await r.json();
            this.meta = j;
            this.rows = (j.rows || []).map((x) => this.decorate(x));
        } catch { this.rows = []; }
        this.stats();
        this.render();
    },

    decorate(r) {
        r.id = String(r.pid);
        r.pin_show = String(r.pin || "").trim().replace(/\s+/g, " ");
        r._seller = r.tags.some((t) => this.SELLER_TAGS.includes(t));
        r.distress = r.distress || []; r.distress_detail = r.distress_detail || [];
        r._blob = [r.address, r.county, r.owner, r.owner2, r.pin, r.zoning, r.gen_zone, r.tier, r.deed, r.mail]
            .filter(Boolean).join(" ").toLowerCase();
        return r;
    },

    sid(r) { return `va:${VAPL.ns}land:${r.pid}`; },
    statusOf(r) { const s = SharedNotes.get(this.sid(r)); return (s && s.status) || "new"; },
    notesOf(r) { const s = SharedNotes.get(this.sid(r)); return (s && s.notes) || ""; },

    stats() {
        const rs = this.rows;
        document.getElementById("lstatTotal").textContent = rs.length.toLocaleString();
        document.getElementById("lstatTier2").textContent = rs.filter((r) => r.tier_group === "1" || r.tier_group === "2").length.toLocaleString();
        document.getElementById("lstatSeller").textContent = rs.filter((r) => r._seller).length.toLocaleString();
        const dz = rs.filter((r) => r.distress.length);
        document.getElementById("lstatDistress").textContent = dz.length.toLocaleString();
        const cnt = {}; dz.forEach((r) => r.distress.forEach((c) => { cnt[c] = (cnt[c] || 0) + 1; }));
        document.getElementById("lstatDistressSub").textContent = Object.entries(cnt).sort((a, b) => b[1] - a[1])
            .map(([c, n]) => `${n} ${this.DISTRESS_LABEL[c] || c}`).join(" · ");
        document.getElementById("lstatAcres").textContent = Math.round(rs.reduce((n, r) => n + (r.acres || 0), 0)).toLocaleString();
        const m = this.meta, info = document.getElementById("landRunInfo");
        info.innerHTML = rs.length
            ? `<b>${rs.length.toLocaleString()}</b> best parcels kept from <b>${(m.scanned || 0).toLocaleString()}</b> ${this.esc(VAPL.county.name)} parcels of ${m.min_acres || 5}+ acres`
              + ` (${(m.qualified || 0).toLocaleString()} passed the growth screen)${m.generated_at ? ` · updated ${this.esc(this.fmtDT(m.generated_at))}` : ""}`
              + (VAPL.key === "westmoreland" ? ` · <span style="color:var(--yellow)">Westmoreland publishes no zoning, growth map, year built or sales, so this county is scored on distance to the towns and seller signals only</span>` : "")
            : "";
    },

    bindEvents() {
        let t;
        document.getElementById("landSearch").addEventListener("input", (e) => {
            clearTimeout(t); t = setTimeout(() => { this.state.search = e.target.value.trim().toLowerCase(); this.state.page = 1; this.render(); }, 200);
        });
        const on = (id, fn) => document.getElementById(id).addEventListener("change", (e) => { fn(e.target); this.state.page = 1; this.render(); });
        on("landTier", (el) => { this.state.tier = el.value; });
        on("landAcres", (el) => { this.state.minAcres = Number(el.value) || 0; });
        on("landSeller", (el) => { this.state.seller = el.checked; });
        on("landDistress", (el) => { this.state.distress = el.value; });
        on("landWater", (el) => { this.state.water = el.checked; });
        on("landHideRezone", (el) => { this.state.hideRezone = el.checked; });
        document.querySelectorAll("#landTable th[data-sort]").forEach((th) => th.addEventListener("click", () => {
            const k = th.dataset.sort;
            this.state.dir = this.state.sort === k ? -this.state.dir : -1;
            this.state.sort = k; this.render();
        }));
        document.getElementById("landPrev").addEventListener("click", () => { if (this.state.page > 1) { this.state.page--; this.render(); } });
        document.getElementById("landNext").addEventListener("click", () => { this.state.page++; this.render(); });
        document.getElementById("landExport").addEventListener("click", () => this.exportCSV());
    },

    filtered() {
        const s = this.state, words = s.search ? s.search.split(/\s+/) : [];
        return this.rows.filter((r) =>
            (!s.tier || r.tier_group === s.tier)
            && (r.acres || 0) >= s.minAcres
            && (!s.seller || r._seller)
            && (!s.distress || (s.distress === "ANY" ? r.distress.length > 0 : s.distress === "MULTI" ? r.distress.length >= 2 : r.distress.includes(s.distress)))
            && (!s.water || r.tags.includes("WATERFRONT"))
            && (!s.hideRezone || !r.tags.includes("NEEDS_REZONING"))
            && words.every((w) => r._blob.includes(w)));
    },

    sorted(rows) {
        const k = this.state.sort, d = this.state.dir;
        const val = (r) => ({ score: r.score, acres: r.acres, lots: r.rough_lots, homes: r.new_homes_nearby }[k]);
        return rows.slice().sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * d || b.score - a.score; });
    },

    scoreColor(n) { return n >= 85 ? "var(--green)" : n >= 70 ? "var(--cyan)" : n >= 55 ? "var(--yellow)" : "var(--text-secondary)"; },
    tierColor(g) { return g === "1" ? "var(--green)" : g === "2" ? "var(--cyan)" : "var(--text-secondary)"; },

    chips(r) {
        const dz = r.distress.map((c) => `<span style="display:inline-block; font-size:0.66rem; padding:1px 6px; margin:2px 3px 0 0; border:1px solid var(--red); background:rgba(255,80,80,0.12); color:var(--red); border-radius:10px; font-weight:600">⚠ ${this.esc(this.DISTRESS_LABEL[c] || c)}</span>`).join("");
        return dz + r.tags.map((t) => {
            const warn = ["NEEDS_REZONING", "RECENT_SALE"].includes(t), sell = this.SELLER_TAGS.includes(t);
            const c = warn ? "var(--red)" : sell ? "var(--yellow)" : t === "WATERFRONT" ? "var(--cyan)" : "var(--text-dim)";
            return `<span style="display:inline-block; font-size:0.66rem; padding:1px 6px; margin:2px 3px 0 0; border:1px solid ${c}; color:${c}; border-radius:10px">${this.esc(this.TAG_LABEL[t] || t)}</span>`;
        }).join("");
    },

    render() {
        const rows = this.sorted(this.filtered());
        const pages = Math.max(1, Math.ceil(rows.length / this.state.perPage));
        if (this.state.page > pages) this.state.page = pages;
        const start = (this.state.page - 1) * this.state.perPage;
        const page = rows.slice(start, start + this.state.perPage);
        const tbody = document.getElementById("landBody"), empty = document.getElementById("landEmpty");
        if (!page.length) {
            tbody.innerHTML = ""; empty.style.display = "block";
            if (this.rows.length) {
                document.getElementById("landEmptyTitle").textContent = "No matches";
                document.getElementById("landEmptyText").textContent = "Loosen the filters or the search.";
            }
        } else {
            empty.style.display = "none";
            tbody.innerHTML = page.map((r) => {
                const st = this.statusOf(r);
                return `<tr data-id="${this.esc(r.id)}">
                    <td style="font-family:var(--font-mono); font-weight:700; font-size:1.05rem; color:${this.scoreColor(r.score)}">${r.score}</td>
                    <td class="property-cell">
                        <div class="address">${this.esc(r.address || "(no street address)")}</div>
                        <div class="meta" style="font-family:var(--font-mono)">Tax map ${this.esc(r.pin_show)}${r.deed ? ` · Deed ${this.esc(r.deed)}` : ""}</div>
                        <div>${this.chips(r)}</div>
                    </td>
                    <td class="name-cell" style="font-family:var(--font-mono); font-size:0.76rem">${this.esc(r.owner || "—")}${r.mail_state && r.mail_state !== "VA" ? ` <span style="color:var(--yellow)">(${this.esc(r.mail_state)})</span>` : ""}${this.notesOf(r) ? '<span class="note-badge" title="Has notes">✎</span>' : ""}</td>
                    <td class="value-cell" style="font-family:var(--font-mono)">${(r.acres || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                    <td style="font-size:0.76rem">
                        <div style="color:${this.tierColor(r.tier_group)}">${this.esc(r.tier || this.TIER_LABEL[r.tier_group || ""])}</div>
                        <div style="color:var(--text-dim)">${r.zoning ? `Zoned ${this.esc(r.zoning)}` : "zoning n/a"}</div>
                    </td>
                    <td style="font-family:var(--font-mono); font-size:0.76rem">${r.rough_lots ? "~" + r.rough_lots.toLocaleString() : "—"}</td>
                    <td style="font-size:0.74rem">${r.new_homes_nearby ? `${r.new_homes_nearby} new homes` : "—"}${r.builders_nearby && r.builders_nearby.length ? `<div style="color:var(--green)">${this.esc(r.builders_nearby.slice(0, 2).join(", "))}</div>` : ""}</td>
                    <td><span class="status-badge ${st}">${st.toUpperCase()}</span></td>
                </tr>`;
            }).join("");
            tbody.querySelectorAll("tr").forEach((tr) => tr.addEventListener("click", () => this.open(tr.dataset.id)));
        }
        const total = rows.length;
        document.getElementById("landPageInfo").textContent = total
            ? `Showing ${start + 1}–${Math.min(start + this.state.perPage, total)} of ${total.toLocaleString()} parcels` : "No parcels";
        document.getElementById("landPrev").disabled = this.state.page <= 1;
        document.getElementById("landNext").disabled = this.state.page >= pages;
    },

    row(label, value, style) {
        return `<div class="detail-row"><span class="label">${label}</span><span class="value"${style ? ` style="${style}"` : ""}>${value}</span></div>`;
    },

    open(id) {
        const r = this.rows.find((x) => x.id === id);
        if (!r) return;
        const cn = `${r.county} County Virginia`;
        const g = (q) => `https://www.google.com/search?q=${encodeURIComponent(q)}`;
        const growthHelp = {
            "king-george": "King George's growth areas are its Settlement Areas; public water and sewer is run by the King George Service Authority. The Canterbury / Circle / Courthouse / Hopyard lines are scheduled for 2026: confirm the date with the Service Authority.",
            "fauquier": "Fauquier puts houses only in its Service Districts (Warrenton, Bealeton, Remington, Catlett, Marshall, New Baltimore, Midland, Calverton). The planned density comes from that district's plan; water and sewer come from the Fauquier County Water and Sanitation Authority.",
            "westmoreland": "Westmoreland publishes no zoning or growth map online. Call county Planning & Community Development for the zoning, and the Town of Colonial Beach or Montross about extending town water and sewer.",
        }[r.county_key] || "";
        document.getElementById("modalTitle").textContent = `${r.address || "Tax map " + r.pin_show} · ${r.acres} ac · ${r.county} County`;
        document.getElementById("modalBody").innerHTML = Aerial.insert(`
            <div class="detail-section">
                <h3>Why It Scored <span style="color:${this.scoreColor(r.score)}">${r.score}</span>
                    <span style="font-size:0.75rem; color:var(--text-dim); font-weight:400">· development side alone: ${r.dev_score}</span></h3>
                <ul style="margin:6px 0 0 18px; font-size:0.84rem; line-height:1.6">${r.reasons.map((x) => `<li>${this.esc(x)}</li>`).join("")}</ul>
                ${r.cautions.length ? `<div style="margin-top:10px; padding:8px 10px; border:1px solid var(--yellow); border-radius:var(--radius); font-size:0.8rem; line-height:1.5">
                    <b style="color:var(--yellow)">Check before you call</b>
                    <ul style="margin:4px 0 0 18px">${r.cautions.map((x) => `<li>${this.esc(x)}</li>`).join("")}</ul></div>` : ""}
            </div>
            ${r.distress.length ? `<div class="detail-section">
                <h3 style="color:var(--red)">Distress Stack <span style="font-size:0.75rem; color:var(--text-dim); font-weight:400">· ${r.distress.length} signal${r.distress.length > 1 ? "s" : ""}</span></h3>
                <ul style="margin:6px 0 0 18px; font-size:0.84rem; line-height:1.6">${r.distress_detail.map((x) => `<li>${this.esc(x)}</li>`).join("")}</ul>
                <div style="margin-top:6px; font-size:0.76rem; color:var(--text-dim)">Death matches come from obituaries and death indexes: confirm with the obituary and the Circuit Court will/probate index before calling.</div>
            </div>` : ""}
            <div class="detail-section">
                <h3>Look It Up</h3>
                ${this.row("Tax map / PIN", this.esc(r.pin_show), "font-family:var(--font-mono); font-weight:600")}
                ${this.row("Address", this.esc(r.address || "(no street address)"))}
                ${this.row("Deed book / page", this.esc(r.deed || "—"), "font-family:var(--font-mono)")}
                ${this.row("County", this.esc(r.county), "color:var(--purple)")}
            </div>
            <div class="detail-section">
                <h3>Development Check</h3>
                ${this.row("Acres", (r.acres || 0).toLocaleString(), "font-family:var(--font-mono)")}
                ${this.row("Growth area", `${this.esc(r.tier || "Not in a growth area")} <span style="color:var(--text-dim)">— ${this.esc(this.TIER_LABEL[r.tier_group || ""])}</span>`)}
                ${this.row("Zoning", this.esc(r.zoning || "Not published"), "font-family:var(--font-mono)")}
                ${r.gen_zone ? this.row("Planned / zoning use", this.esc(r.gen_zone)) : ""}
                ${this.row("Rough yield", r.rough_lots ? `~${r.rough_lots.toLocaleString()} homes <span style="color:var(--text-dim)">(gross guess before roads, stormwater and setbacks are engineered)</span>` : "—")}
                ${this.row("New homes within 1.5 mi", r.new_homes_nearby ? `${r.new_homes_nearby} built in the last 4 years` : (r.county_key === "westmoreland" ? "Not published in Westmoreland" : "None found"))}
                ${this.row("Builders buying nearby", r.builders_nearby && r.builders_nearby.length ? this.esc(r.builders_nearby.join(", ")) : "None found")}
                ${this.row("Assessed land / buildings", `${this.money(r.land_value)} / ${this.money(r.impr_value)}`, "font-family:var(--font-mono)")}
            </div>
            <div class="detail-section">
                <h3>Seller Side</h3>
                ${this.row("Owner", this.esc(r.owner || "—") + (r.owner2 ? `<br>${this.esc(r.owner2)}` : ""), "font-family:var(--font-mono); color:var(--yellow)")}
                ${this.row("Tax bill mailed to", this.esc(r.mail || "—") + (r.mail_state && r.mail_state !== "VA" ? ` <b style="color:var(--yellow)">(out of state)</b>` : ""), "font-family:var(--font-mono); font-size:0.8rem")}
                ${this.row("Last sale", `${this.esc(r.transfer_date || "—")}${r.sale_price ? ` · ${this.money(r.sale_price)}` : ""}`, "font-family:var(--font-mono)")}
                ${r.title_flags && r.title_flags.length ? this.row("Title flags", this.esc(r.title_flags.join(", ")), "color:var(--red); font-size:0.78rem") : ""}
            </div>
            <div class="detail-section">
                <h3>How to Work It</h3>
                <ol style="margin:4px 0 0 18px; font-size:0.83rem; line-height:1.6">
                    <li><b>Confirm the growth story.</b> ${this.esc(growthHelp)}
                        <a href="${g(cn + " zoning map GIS")}" target="_blank" rel="noopener">zoning map ↗</a> ·
                        <a href="${g(cn + " comprehensive plan water sewer service area")}" target="_blank" rel="noopener">comprehensive plan ↗</a></li>
                    <li><b>Ask a builder what they'd pay.</b> Call the land acquisition manager at a builder active nearby
                        (<a href="${g("homebuilder land acquisition " + cn)}" target="_blank" rel="noopener">find them ↗</a>) with the tax map number and acreage. They will tell you fast whether they want it.</li>
                    <li><b>Tie it up long.</b> Contract with a long due-diligence and closing period, contingent on approvals, small earnest money, and the right to assign.</li>
                    <li><b>Assign it or partner on entitlement.</b> Assign the contract to the builder for a fee, or bring in a developer to fund engineering and rezoning and split the lift.</li>
                </ol>
            </div>`, r);
        Aerial.bind(document.getElementById("modalBody"));
        const sel = document.getElementById("leadStatusSelect"), notes = document.getElementById("leadNotes");
        sel.value = this.statusOf(r); notes.value = this.notesOf(r);
        SharedNotes.footer(this.sid(r));
        document.getElementById("saveLeadBtn").onclick = () => {
            SharedNotes.save("va-land", this.sid(r), sel.value, notes.value, `Tax map ${r.pin_show}, ${r.county} — ${r.acres} ac${r.owner ? " — " + r.owner : ""} (Dirt Deals)`);
            document.getElementById("modalOverlay").classList.remove("active"); this.render();
        };
        document.getElementById("modalOverlay").classList.add("active");
    },

    exportCSV() {
        const rows = this.sorted(this.filtered());
        if (!rows.length) { alert("Nothing to export with the current filters."); return; }
        const H = ["Score", "Dev Score", "Tax Map / PIN", "Deed", "Address", "County", "Acres", "Growth Area", "Zoning", "Planned Use",
            "Rough Homes", "New Homes Nearby", "Builders Nearby", "Owner", "Care Of", "Mailing", "Mail State", "Last Sale", "Sale Price",
            "Land Value", "Building Value", "Distress", "Title Flags", "Tags", "Cautions", "Lat", "Lon", "Status", "Notes"];
        const q = (v) => { const s = String(v == null ? "" : v); return /^=".*"$/.test(s) ? s : `"${s.replace(/"/g, '""')}"`; };
        const lines = [H.join(",")];
        rows.forEach((r) => lines.push([r.score, r.dev_score, `="${r.pin_show}"`, r.deed, r.address, r.county, r.acres, r.tier, r.zoning, r.gen_zone,
            r.rough_lots, r.new_homes_nearby, (r.builders_nearby || []).join("; "), r.owner, r.owner2, r.mail, r.mail_state, r.transfer_date, r.sale_price,
            r.land_value, r.impr_value, r.distress_detail.join(" | "), (r.title_flags || []).join("; "), r.tags.map((t) => this.TAG_LABEL[t] || t).join("; "),
            r.cautions.join(" | "), r.lat, r.lon, this.statusOf(r), this.notesOf(r)].map(q).join(",")));
        const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `va-${VAPL.key}-dirt-deals-${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    },

    money(v) { const n = Number(v); return (v == null || v === "" || isNaN(n) || !n) ? "—" : "$" + Math.round(n).toLocaleString(); },
    fmtDT(s) { const d = new Date(s); return isNaN(d) ? (s || "") : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); },
    esc(s) { return s == null ? "" : String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); },
};
