/* Shared status + notes for every tab (ported from md-property-leads static/js/shared.js).
   Store: the Maryland tool's Google Sheet behind its Apps Script web app. Each save appends
   a row {ts, author, tab, id, label, status, notes}; the sheet is the full history, and the
   newest row per lead id is what the tabs show. Virginia rows use tab "va-<tab>" and id
   "va:<tab>:<lead id>". Each browser's localStorage stays as an offline copy. */
const SharedNotes = {
    url: (window.VAPL && window.VAPL.SHARED_NOTES_URL) || "",
    latest: {}, history: {}, loaded: false, error: null,
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
            this.latest = {}; this.history = {};
            for (const row of rows) {
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

    /* The modal footer: who-you-are box, note history, sync state. Called when a lead opens. */
    footer(id) {
        const who = document.getElementById("noteAuthor");
        if (who && !who.value) who.value = this.author();
        const hist = document.getElementById("noteHistory");
        if (hist) {
            const rows = (this.history[id] || []).filter((r) => (r.notes || "").trim() || r.status);
            hist.innerHTML = rows.slice(0, 12).map((r) => `<div class="note"><div class="who">${this.esc(r.author || "?")} · ${this.esc(this.fmt(r.ts))} · ${this.esc((r.status || "").toUpperCase())}</div>${this.esc(r.notes || "")}</div>`).join("");
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

    fmt(ts) { const d = new Date(ts); return isNaN(d) ? (ts || "") : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); },
    esc(s) { return s == null ? "" : String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); },
};
document.addEventListener("DOMContentLoaded", () => {
    const who = document.getElementById("noteAuthor");
    if (who) who.addEventListener("change", (e) => SharedNotes.setAuthor(e.target.value));
    SharedNotes.load();
});
