/* Parcel Lookup tab: searches data/parcels.json (every assessed parcel). Loaded on first open. */
const LookupApp = {
    cols: {}, rows: [], hay: [],

    async init() {
        const info = document.getElementById("lookupInfo");
        info.textContent = "Loading the parcel index…";
        try {
            const j = await fetch(`data/parcels.json?t=${Date.now()}`, { cache: "no-store" }).then((r) => r.json());
            j.columns.forEach((c, i) => { this.cols[c] = i; });
            this.rows = j.rows;
            const c = this.cols;
            this.hay = this.rows.map((r) => `${r[c.owner]} ${r[c.care_of]} ${r[c.site_addr]} ${r[c.pin]} ${String(r[c.pin]).replace(/\s+/g, "")} ${r[c.mail_addr]} ${r[c.mail_city]}`.toLowerCase());
            info.textContent = `${this.rows.length.toLocaleString()} assessed parcels. This is a lookup, not a lead list.`;
        } catch {
            info.textContent = "The parcel index has not been built yet.";
            return;
        }
        let t;
        const input = document.getElementById("lookupSearch");
        input.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => this.search(input.value), 200); });
        if (input.value) this.search(input.value);
    },

    search(q) {
        const body = document.getElementById("lookupBody"), empty = document.getElementById("lookupEmpty");
        const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
        if (words.join("").length < 3) { body.innerHTML = ""; empty.style.display = "block"; return; }
        const c = this.cols, hits = [];
        for (let i = 0; i < this.rows.length && hits.length < 200; i++) {
            if (words.every((w) => this.hay[i].includes(w))) hits.push(this.rows[i]);
        }
        empty.style.display = hits.length ? "none" : "block";
        const e = TitleApp.esc;
        body.innerHTML = hits.map((r) => `<tr>
            <td class="name-cell" style="font-family:var(--font-mono); font-size:0.8rem">${e(r[c.owner])}${r[c.care_of] ? `<div class="sub">c/o ${e(r[c.care_of])}</div>` : ""}</td>
            <td class="property-cell"><div class="address">${e(r[c.site_addr] || "No street address")}</div><div class="meta">${r[c.acres]} ac${r[c.year_built] ? ` · built ${r[c.year_built]}` : ""}</div></td>
            <td class="mono"><a style="color:var(--cyan-dim)" href="https://gis.vgsi.com/kinggeorgecountyva/Parcel.aspx?Pid=${r[c.pid]}" target="_blank" rel="noopener">${e(r[c.pin])}</a></td>
            <td class="sub">${e(String(r[c.owner_type]).replace("_", " "))}</td>
            <td class="date-cell">${r[c.sale_year] && r[c.sale_year] !== 1900 ? r[c.sale_year] : "—"}</td>
            <td class="value-cell">$${Number(r[c.total_value]).toLocaleString()}</td>
            <td class="county-cell">${e(r[c.mail_addr])}<div class="sub">${e(r[c.mail_city])}, ${e(r[c.mail_state])}</div></td>
        </tr>`).join("");
        document.getElementById("lookupInfo").textContent = hits.length >= 200 ? "Showing the first 200 matches. Add another word to narrow it." : `${hits.length} match${hits.length === 1 ? "" : "es"}.`;
    },
};
