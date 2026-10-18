/* Shared status + notes for every tab (ported from md-property-leads static/js/shared.js).
   Store: the Maryland tool's Google Sheet behind its Apps Script web app. Each save appends
   a row {ts, author, tab, id, label, status, notes}; the sheet is the full history, and the
   newest row per lead id is what the tabs show. Virginia rows use tab "va-<tab>" and id
   "va:<tab>:<lead id>". Each browser's localStorage stays as an offline copy. */
const SharedNotes = {
    url: (window.VAPL && window.VAPL.SHARED_NOTES_URL) || "",
    latest: {}, history: {}, worksheets: {}, loaded: false, error: null,   // worksheets: "<id>#ws" -> newest deal-worksheet row
    enabled() { return !!this.url; },

    // Same key as the Maryland dashboard: both live on one site, so the name is typed once.
    author() { try { return localStorage.getItem("mdpl_author") || ""; } catch { return ""; } },
    setAuthor(v) { try { localStorage.setItem("mdpl_author", (v || "").trim()); } catch {} },

    async load() {
        if (!this.enabled()) { this.loaded = true; return; }
        try {
            const r = await fetch(`${this.url}?t=${Date.now()}`, { cache: "no-store" });
            const j = await r.json();
            const rows = (j.rows || []).filter((x) => String(x.id || "").startsWith("va:"))
                .sort((a, b) => String(b.ts).localeCompare(String(a.ts)));
            this.latest = {}; this.history = {}; this.worksheets = {};
            for (const row of rows) {
                if (/#ws$/.test(String(row.id))) { if (!this.worksheets[row.id]) this.worksheets[row.id] = row; continue; }   // deal worksheets: own store
                (this.history[row.id] = this.history[row.id] || []).push(row);
                if (!this.latest[row.id]) this.latest[row.id] = row;
            }
            this.loaded = true; this.error = null;
        } catch (e) { this.loaded = true; this.error = String(e); }
        document.dispatchEvent(new CustomEvent("vapl:notes-loaded"));
        this.paintSync();
    },

    get(id) { return this.latest[id] || null; },

    async save(tab, id, status, notes, label) {
        const row = { ts: new Date().toISOString(), author: this.author() || "unknown", tab, id, label: label || "", status, notes };
        this.latest[id] = row;
        (this.history[id] = this.history[id] || []).unshift(row);
        if (!this.enabled()) return true;
        try {
            // a plain-text body keeps the request "simple", so Apps Script needs no CORS preflight
            const r = await fetch(this.url, { method: "POST", body: JSON.stringify(row) });
            const j = await r.json().catch(() => ({}));
            if (j && j.ok === false) throw new Error(j.error || "save rejected");
            this.error = null; this.paintSync("Saved for everyone");
            return true;
        } catch (e) { this.error = String(e); this.paintSync(); return false; }
    },

    /* Deal worksheet (static/js/worksheet.js): one JSON row per save under "<id>#ws", tab "va-worksheet".
       Never touches latest/history, so it can't change a lead's status or show in My Leads. */
    async saveWorksheet(wsId, json, label) {
        const row = { ts: new Date().toISOString(), author: this.author() || "unknown", tab: "va-worksheet", id: wsId, label: label || "", status: "", notes: json };
        this.worksheets[wsId] = row;
        if (!this.enabled()) return false;
        try {
            const r = await fetch(this.url, { method: "POST", body: JSON.stringify(row) });
            const j = await r.json().catch(() => ({}));
            if (j && j.ok === false) throw new Error(j.error || "save rejected");
            return true;
        } catch (e) { this.error = String(e); return false; }
    },

    /* The modal footer: who-you-are box, note history, sync state. Called when a lead opens. */
    footer(id) {
        const who = document.getElementById("noteAuthor");
        if (who && !who.value) who.value = this.author();
        const hist = document.getElementById("noteHistory");
        if (hist) {
            const rows = (this.history[id] || []).filter((r) => (r.notes || "").trim() || r.status);
            hist.innerHTML = rows.slice(0, 12).map((r) => this.noteCard(r)).join("");
        }
        this.paintSync();
    },

    paintSync(msg) {
        const el = document.getElementById("noteSync");
        if (!el) return;
        if (!this.enabled()) { el.className = "note-sync"; el.textContent = "Notes are saved in this browser only"; return; }
        if (this.error) { el.className = "note-sync err"; el.textContent = "Could not reach the shared sheet. Saved here; others will not see it until it reconnects"; return; }
        el.className = "note-sync on"; el.textContent = msg || "Shared: everyone sees these";
    },

    /* One note as a readable card: date / who / status header, then the text broken into
       labeled lines (OWNER:, HEIRS:, Next:, (1), (a) ...), phones and emails clickable,
       long notes folded behind "Show more". Works on old run-on notes and new line-broken ones. */
    noteCard(r, extra) {
        const text = String(r.notes || "").trim();
        const st = (r.status || "").toLowerCase();
        const label = (typeof MyLeadsApp !== "undefined" && MyLeadsApp.STATUS[st]) || st;
        const head = `<div class="nc-head"><span class="nc-date">${this.esc(this.fmt(r.ts))}</span>`
            + `<span class="nc-who">${this.esc(r.author || "?")}</span>`
            + (st ? `<span class="status-badge ${this.esc(st)} nc-st">${this.esc(String(label).toUpperCase())}</span>` : "")
            + (extra ? `<span class="nc-tab">${this.esc(extra)}</span>` : "") + `</div>`;
        if (/^(Added to My Leads|Removed from My Leads|Status changed to )/.test(text) && text.length < 120)
            return `<div class="note nc nc-mini">${head}<div class="nc-mini-t">${this.esc(text)}</div></div>`;
        const m = /^FOLLOW UP: (\d{4}-\d{2}-\d{2})\s*([\s\S]*)$/.exec(text);
        const fu = m ? `<div class="nc-fu">📅 Follow up ${this.esc(new Date(m[1] + "T12:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }))}</div>` : "";
        const body = this.formatNote(m ? m[2] : text);
        const long = (m ? m[2] : text).length > 450;
        return `<div class="note nc">${head}${fu}`
            + (body ? `<div class="nc-body${long ? " nc-fold" : ""}">${body}</div>` : "")
            + (long ? `<button type="button" class="nc-more" onclick="const b=this.previousElementSibling;b.classList.toggle('open');this.textContent=b.classList.contains('open')?'Show less':'Show more'">Show more</button>` : "")
            + `</div>`;
    },

    formatNote(text) {
        let t = String(text || "").trim();
        if (!t) return "";
        if (!/\n/.test(t)) {
            // old run-on notes: break before labels and enumerations
            t = t.replace(/\s+(?=\((?:\d{1,2}|[a-h])\)\s)/g, "\n")
                 .replace(/([.;!?)]|\d)\s+(?=[A-Z][A-Z0-9'&\/.\-]+(?:\s+[A-Z0-9][A-Z0-9'&\/.\-]+)*(?:,\s*\d+)?(?:\s*\([^)\n]{0,60}\))?\s*:\s)/g, "$1\n")
                 .replace(/([.;])\s+(?=(?:Next|Play|Angle|Pitch|Phones?|Contacts?|Heirs|Owners?|Deed|Title|Taxes|Tax sale|Liens?|Risks?|Clouds?|Status|Verdict|Occupancy|Sources?|Emails?|To do|Still open|Value|Exits?|Decision maker)\b[^.:\n]{0,30}:\s)/gi, "$1\n");
        }
        const kw = /^(Next|Play|Angle|Pitch|Phones?|Contacts?|Heirs|Owners?|Deed|Title|Taxes|Tax sale|Liens?|Risks?|Clouds?|Status|Verdict|Occupancy|Sources?|Emails?|To do|Still open|Value|Exits?|Decision maker)\b/i;
        const link = (h) => h
            .replace(/(\(\d{3}\)\s?\d{3}-\d{4}|\b\d{3}-\d{3}-\d{4}\b)/g, (p) => `<a href="tel:${p.replace(/\D/g, "")}">${p}</a>`)
            .replace(/\b([\w.+-]+@[\w-]+\.[\w.]+)\b/g, '<a href="mailto:$1">$1</a>');
        return t.split(/\n+/).map((line) => {
            line = line.trim();
            if (!line) return "";
            let bullet = "", rest = line;
            const en = /^(\((?:\d{1,2}|[a-h])\)|[-•*])\s+/.exec(rest);
            if (en) { bullet = en[1]; rest = rest.slice(en[0].length); }
            const lm = /^([^:]{2,70}?):\s+([\s\S]+)$/.exec(rest);
            let html;
            if (lm && !/[.!?]\s/.test(lm[1]) && (lm[1] === lm[1].toUpperCase() || kw.test(lm[1])))
                html = `<span class="nk">${this.esc(lm[1])}</span> ${link(this.esc(lm[2]))}`;
            else html = link(this.esc(rest));
            const cls = bullet ? "nl nl-b" : "nl";
            const mark = bullet && /^[-•*]$/.test(bullet) ? "" : (bullet ? `<span class="nb">${this.esc(bullet)}</span>` : "");
            return `<div class="${cls}">${mark}${html}</div>`;
        }).join("");
    },

    fmt(ts) { const d = new Date(ts); return isNaN(d) ? (ts || "") : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); },
    esc(s) { return s == null ? "" : String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); },
};
document.addEventListener("DOMContentLoaded", () => {
    const who = document.getElementById("noteAuthor");
    if (who) who.addEventListener("change", (e) => SharedNotes.setAuthor(e.target.value));
    SharedNotes.load();
});
