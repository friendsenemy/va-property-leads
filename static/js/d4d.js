/* Driving for Dollars tab (ported from the Maryland tool): properties Ray spotted on the road,
   each with the deep-dive research, the county parcel facts, imagery and the shared notes.
   Reads data/d4d/leads.json (written by engine/d4d_add.py) — one file for every Virginia
   county; each row carries its county. Notes use id "va:<county ns>d4d:<row id>". */
const D4DApp = {
    rows: [],
    state: { search: "", page: 1, perPage: 25 },
    VERDICT: { hot: ["HOT", "var(--red)"], warm: ["WARM", "var(--yellow)"], cold: ["COLD", "var(--cyan-dim)"], dead: ["DEAD", "var(--text-dim)"] },

    async init() {
        let t;
        document.getElementById("d4dSearch").addEventListener("input", (e) => {
            clearTimeout(t); t = setTimeout(() => { this.state.search = e.target.value.trim().toLowerCase(); this.state.page = 1; this.render(); }, 200);
        });
        document.getElementById("d4dPrev").addEventListener("click", () => { if (this.state.page > 1) { this.state.page--; this.render(); } });
        document.getElementById("d4dNext").addEventListener("click", () => { this.state.page++; this.render(); });
        document.addEventListener("vapl:notes-loaded", () => { if (this.rows.length) this.render(); });
        try {
            const r = await fetch(`data/d4d/leads.json?t=${Date.now()}`, { cache: "no-store" });
            if (!r.ok) throw new Error(r.status);
            this.rows = ((await r.json()).rows || []).map((x) => Object.assign(x, {
                _blob: [x.address, x.city, x.county, x.pin, x.owner, (x.owners || []).join(" "), x.headline].join(" ").toLowerCase(),
            }));
        } catch { this.rows = []; }
        document.getElementById("dstatTotal").textContent = this.rows.length;
        document.getElementById("dstatHot").textContent = this.rows.filter((r) => r.verdict === "hot" || r.verdict === "warm").length;
        this.render();
    },

    sid(r) { const c = VAPL.COUNTIES[r.county_key] || {}; return `va:${c.ns || ""}d4d:${r.id}`; },
    statusOf(r) { const s = SharedNotes.get(this.sid(r)); return (s && s.status) || "new"; },
    notesOf(r) { const s = SharedNotes.get(this.sid(r)); return (s && s.notes) || ""; },

    render() {
        const rows = this.rows.filter((r) => !this.state.search || this.state.search.split(/\s+/).every((w) => r._blob.includes(w)));
        const pages = Math.max(1, Math.ceil(rows.length / this.state.perPage));
        if (this.state.page > pages) this.state.page = pages;
        const start = (this.state.page - 1) * this.state.perPage;
        const page = rows.slice(start, start + this.state.perPage);
        document.getElementById("d4dEmpty").style.display = page.length ? "none" : "block";
        const tbody = document.getElementById("d4dBody");
        tbody.innerHTML = page.map((r) => {
            const st = this.statusOf(r), v = this.VERDICT[r.verdict] || [String(r.verdict || "—").toUpperCase(), "var(--text-secondary)"];
            return `<tr data-id="${this.esc(r.id)}">
                <td class="date-cell">${this.esc(r.spotted || "")}</td>
                <td class="property-cell"><div class="address">${this.esc(r.address || "No street address")}</div>
                    <div class="meta" style="font-family:var(--font-mono)">${this.esc(r.pin || "")} · ${this.esc(r.county)}</div></td>
                <td class="name-cell" style="font-size:0.78rem">${(r.owners && r.owners.length ? r.owners : [r.owner]).map((o) => this.esc(String(o || "").split(" (")[0])).join("<br>")}${this.notesOf(r) ? '<span class="note-badge" title="Has notes">✎</span>' : ""}</td>
                <td style="font-size:0.8rem; color:var(--text-secondary)">${this.esc(r.headline || "")}</td>
                <td class="value-cell">${this.money(r.total_value)}</td>
                <td><span style="font-family:var(--font-mono); font-weight:700; color:${v[1]}">${v[0]}</span></td>
                <td><span class="status-badge ${st}">${st.toUpperCase()}</span></td>
            </tr>`;
        }).join("");
        tbody.querySelectorAll("tr").forEach((tr) => tr.addEventListener("click", () => this.open(tr.dataset.id)));
        document.getElementById("d4dPageInfo").textContent = rows.length ? `Showing ${start + 1}–${Math.min(start + this.state.perPage, rows.length)} of ${rows.length}` : "No properties";
        document.getElementById("d4dPrev").disabled = this.state.page <= 1;
        document.getElementById("d4dNext").disabled = this.state.page >= pages;
    },

    open(id) {
        const r = this.rows.find((x) => x.id === id);
        if (!r) return;
        const row = (l, v) => v ? `<div class="detail-row"><span class="label">${l}</span><span class="value">${v}</span></div>` : "";
        const list = (xs) => (xs || []).length ? `<ul class="reasons">${xs.map((x) => `<li>${this.esc(x)}</li>`).join("")}</ul>` : "";
        const v = this.VERDICT[r.verdict] || [String(r.verdict || "").toUpperCase(), "var(--text-secondary)"];
        document.getElementById("modalTitle").textContent = `${r.address || r.pin} · ${r.county} County`;
        document.getElementById("modalBody").innerHTML = Aerial.insert(`
            <div class="detail-section">
                <h3>Driving for Dollars · spotted ${this.esc(r.spotted || "")} <span style="margin-left:8px; color:${v[1]}">${v[0]}</span></h3>
                <p style="font-size:0.9rem; line-height:1.5">${this.esc(r.headline || "")}</p>
            </div>
            <div class="detail-section">
                <h3>Title</h3>
                ${row("Owner on the county record", this.esc(r.owner))}
                ${row("Tax bill mailed to", this.esc(r.mailing))}
                ${row("Owners (research)", (r.owners || []).map((o) => this.esc(o)).join("<br>"))}
                ${row("Vesting", this.esc(r.vesting))}
                ${row("Deed", r.deed ? `<span style="font-family:var(--font-mono); font-size:0.82rem">${this.esc(r.deed)}</span>` : "")}
            </div>
            <div class="detail-section"><h3>What the research found</h3>${list(r.findings)}</div>
            <div class="detail-section"><h3>Next steps</h3>${list(r.next_steps)}</div>
            ${(r.sources || []).length ? `<div class="detail-section"><h3>Sources</h3>${list(r.sources)}</div>` : ""}`, r);
        Aerial.bind(document.getElementById("modalBody"));
        const sel = document.getElementById("leadStatusSelect"), notes = document.getElementById("leadNotes");
        sel.value = this.statusOf(r); notes.value = this.notesOf(r);
        SharedNotes.footer(this.sid(r));
        document.getElementById("saveLeadBtn").onclick = () => {
            SharedNotes.save("va-d4d", this.sid(r), sel.value, notes.value, `${r.address || r.pin}, ${r.county} (D4D)`);
            document.getElementById("modalOverlay").classList.remove("active"); this.render();
        };
        document.getElementById("modalOverlay").classList.add("active");
    },

    money(v) { const n = Number(v); return (v == null || v === "" || isNaN(n) || !n) ? "—" : "$" + Math.round(n).toLocaleString(); },
    esc(s) { return s == null ? "" : String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); },
};
