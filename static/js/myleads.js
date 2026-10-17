/* My Leads (ported from the Maryland tool): a simple CRM over the shared notes sheet.
   Only the leads someone chose to work show here: "+ Add to My Leads" or a follow-up date on
   any card, or "+ Add a lead" for something not in the tool. Plain notes don't add a lead.
   Covers every Virginia county; a lead from another county opens after switching to it.
   Nothing new is stored: it reads/writes the same sheet SharedNotes uses (ids "va:…"). */
const vaCloseModal = () => { document.getElementById("modalOverlay").classList.remove("active"); if (typeof MyLeadsApp !== "undefined") MyLeadsApp.setPin(null); };
const MyLeadsApp = {
    state: { search: "", status: "mine", when: "all", page: 1, perPage: 30 },
    STATUS: {
        pursuing: "Working it", working: "Working it", hot: "Hot", new: "New", contacted: "Contacted", followup: "Follow up",
        verified: "Verified", paid: "Paid out / dead", dead: "Dead / pass", closed: "Closed",
    },
    DONE: ["dead", "paid", "closed"],
    ADDED: "Added to My Leads", REMOVED: "Removed from My Leads",
    TAB_NAME: { "va-title": "Title Leads", "va-d4d": "Driving for Dollars", "va-surplus": "Surplus Funds", "va-stack": "Stacked Distress",
        "va-death": "Death Leads", "va-delinq": "Delinquent", "va-myleads": "Added by hand" },
    APPS: () => ({ title: TitleApp, death: DeathApp, delinq: DelinqApp, stack: StackApp, surplus: SurplusApp, d4d: D4DApp }),
    /* "va:fq:title:123" -> {key:"fauquier", name:"Fauquier", tab:"title", lead:"123"} */
    parse(id) {
        const m = /^va:((?:wm|fq):)?([a-z0-9]+):(.+)$/.exec(String(id || ""));
        if (!m) return null;
        const ns = m[1] || "", hit = Object.entries(VAPL.COUNTIES).find(([, c]) => c.ns === ns);
        return { ns, tab: m[2], lead: m[3], key: m[2] === "surplus" ? "" : (hit ? hit[0] : ""), name: m[2] === "surplus" ? "" : (hit ? hit[1].name : "") };
    },
    started: false,

    init() {
        if (this.started) { this.render(); return; }
        this.started = true;
        let t;
        document.getElementById("mlSearch").addEventListener("input", (e) => {
            clearTimeout(t); t = setTimeout(() => { this.state.search = e.target.value.trim().toLowerCase(); this.state.page = 1; this.render(); }, 200);
        });
        document.getElementById("mlStatus").addEventListener("change", (e) => { this.state.status = e.target.value; this.state.page = 1; this.render(); });
        document.getElementById("mlWhen").addEventListener("change", (e) => { this.state.when = e.target.value; this.state.page = 1; this.render(); });
        document.getElementById("mlPrev").addEventListener("click", () => { if (this.state.page > 1) { this.state.page--; this.render(); } });
        document.getElementById("mlNext").addEventListener("click", () => { this.state.page++; this.render(); });
        document.getElementById("mlRefresh").addEventListener("click", async () => { await SharedNotes.load(); this.render(); });
        document.getElementById("mlAddBtn").addEventListener("click", () => this.openAdd());
        document.addEventListener("vapl:notes-loaded", () => this.render());
        // re-draw whenever you come back to this tab (adds made on other tabs show right away)
        const tab = document.querySelector('button.view-tab[data-view="myleads"]');
        if (tab) tab.addEventListener("click", () => this.render());
        this.render();
    },

    leads() {
        return Object.entries(SharedNotes.history).map(([k, rows]) => {
            const latest = rows[0];
            // prefer a label that carries an address (has a digit) over a generic one like "Guy estate"
            const labelRow = rows.find((r) => /\d/.test(r.label || "") && /[a-z]{3}/i.test(r.label || "")) || rows.find((r) => (r.label || "").trim()) || latest;
            const noteRow = rows.find((r) => (r.notes || "").trim() && !/^(Added to My Leads|Status changed to )/.test(r.notes.trim())) || latest;
            return {
                key: k, rows, latest, status: latest.status || "new", tab: latest.tab || "",
                tabs: [...new Set(rows.map((r) => r.tab).filter(Boolean))], where: (this.parse(latest.id) || {}).name || "",
                label: (labelRow.label || "").trim() || k, lastNote: (noteRow.notes || "").trim(),
                // "last touch" = last real note, not the add/remove bookkeeping rows
                ts: (rows.find((r) => !/^(Added to My Leads|Removed from My Leads)/.test((r.notes || "").trim())) || latest).ts,
                who: (rows.find((r) => !/^(Added to My Leads|Removed from My Leads)/.test((r.notes || "").trim())) || latest).author || "",
                inList: this.membership(rows), followUp: latest.status === "followup" ? this.fuDate(rows) : "",
                blob: rows.map((r) => `${r.label} ${r.notes} ${r.id}`).join(" ").toLowerCase(),
            };
        }).sort((a, b) => String(b.ts).localeCompare(String(a.ts)));
    },

    /* In My Leads only if someone put it there: the newest add/remove event decides.
       Add = "+ Add to My Leads", a follow-up date, status "Working it", or the add-a-lead form.
       Remove = "Remove from My Leads", or marking it Dead / Closed. Plain notes don't count. */
    membership(rows) {
        for (const r of rows) {
            const n = (r.notes || "").trim(), st = r.status || "";
            if (n.startsWith(this.REMOVED) || this.DONE.includes(st)) return false;
            if (n.startsWith(this.ADDED) || /^FOLLOW UP: /.test(n) || r.tab === "va-myleads" || ["pursuing", "working", "followup"].includes(st)) return true;
        }
        return false;
    },
    fuDate(rows) {
        for (const r of rows) { const m = /^FOLLOW UP: (\d{4}-\d{2}-\d{2})/.exec((r.notes || "").trim()); if (m) return m[1]; }
        return "";
    },
    today() { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); },
    fuLabel(d) {
        if (!d) return "";
        const t = this.today(), dt = new Date(d + "T12:00:00");
        const nice = dt.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
        return d < t ? `OVERDUE · ${nice}` : d === t ? `TODAY` : nice;
    },

    render() {
        if (!document.getElementById("mlBody")) return;
        const all = this.leads(), now = Date.now();
        const age = (l) => (now - new Date(l.ts).getTime()) / 864e5;
        const done = (l) => this.DONE.includes(l.status);
        const mine = all.filter((l) => l.inList), t = this.today();
        document.getElementById("mlstatTotal").textContent = mine.length;
        document.getElementById("mlstatHot").textContent = mine.filter((l) => l.followUp && l.followUp <= t).length;
        document.getElementById("mlstatWeek").textContent = mine.filter((l) => l.followUp && l.followUp > t).length;
        document.getElementById("mlstatStale").textContent = mine.filter((l) => !l.followUp && age(l) > 7).length;

        const s = this.state, maxAge = { today: 1, week: 7, month: 30 }[s.when];
        let rows = all.filter((l) => {
            if (s.status === "mine" && !l.inList) return false;
            if (s.status === "due" && !(l.inList && l.followUp && l.followUp <= t)) return false;
            if (s.status === "upcoming" && !(l.inList && l.followUp)) return false;
            if (s.status === "stale" && !(l.inList && !l.followUp && age(l) > 7)) return false;
            if (s.status === "notmine" && l.inList) return false;
            if (!["all", "mine", "due", "upcoming", "stale", "notmine"].includes(s.status) && l.status !== s.status) return false;
            if (maxAge && age(l) > maxAge) return false;
            return !s.search || s.search.split(/\s+/).every((w) => l.blob.includes(w));
        });
        // follow-ups first (overdue, today, soonest), then everything else by last touch
        if (s.status !== "notmine" && s.status !== "all") rows = rows.slice().sort((a, b) => (a.followUp || "9999").localeCompare(b.followUp || "9999") || String(b.ts).localeCompare(String(a.ts)));
        const pages = Math.max(1, Math.ceil(rows.length / s.perPage));
        if (s.page > pages) s.page = pages;
        const start = (s.page - 1) * s.perPage, page = rows.slice(start, start + s.perPage);
        document.getElementById("mlEmpty").style.display = page.length ? "none" : "block";
        const tTop = this.today();
        const body = document.getElementById("mlBody");
        body.innerHTML = page.map((l) => `<tr data-k="${this.esc(l.key)}">
            <td class="date-cell" title="${this.esc(SharedNotes.fmt(l.ts))}">${this.esc(this.ago(l.ts))}<div class="meta">${this.esc(l.who)}</div></td>
            <td class="property-cell"><div class="address">${this.esc(l.label)}</div>
                <div class="meta">${this.esc([l.where ? l.where + " County" : "", l.tabs.map((t) => this.TAB_NAME[t] || t).join(" · ")].filter(Boolean).join(" · "))}</div></td>
            <td><span class="status-badge ${this.esc(l.status)}">${this.esc((this.STATUS[l.status] || l.status).toUpperCase())}</span>${l.inList ? "" : '<div class="meta" style="margin-top:4px">not in My Leads</div>'}</td>
            <td style="font-family:var(--font-mono); font-size:0.78rem; white-space:nowrap; color:${l.followUp && l.followUp <= tTop ? "var(--red, #ff453a)" : "var(--yellow)"}">${this.esc(this.fuLabel(l.followUp))}</td>
            <td style="font-size:0.8rem; color:var(--text-secondary); max-width:520px">${this.esc(l.lastNote.slice(0, 220))}${l.lastNote.length > 220 ? "…" : ""}</td>
            <td style="text-align:center; font-family:var(--font-mono)">${l.rows.length}</td>
        </tr>`).join("");
        body.querySelectorAll("tr").forEach((tr) => tr.addEventListener("click", () => this.open(tr.dataset.k)));
        document.getElementById("mlPageInfo").textContent = rows.length ? `Showing ${start + 1}–${Math.min(start + s.perPage, rows.length)} of ${rows.length}` : "No leads";
        document.getElementById("mlPrev").disabled = s.page <= 1;
        document.getElementById("mlNext").disabled = s.page >= pages;
        const sync = document.getElementById("mlSync");
        if (sync) sync.textContent = SharedNotes.error ? "Could not reach the shared notes sheet" : (SharedNotes.loaded ? "" : "Loading notes…");
    },

    open(k) {
        const l = this.leads().find((x) => x.key === k);
        if (!l) return;
        const pid = this.parse(l.rows[0].id), canOpen = !!(pid && this.APPS()[pid.tab]);
        document.getElementById("modalBody").innerHTML = `
            <div class="detail-section">
                <h3>My Leads · <span class="status-badge ${this.esc(l.status)}">${this.esc((this.STATUS[l.status] || l.status).toUpperCase())}</span></h3>
                <div class="detail-row"><span class="label">Property</span><span class="value" style="font-weight:600">${this.esc(l.label)}</span></div>
                <div class="detail-row"><span class="label">ID</span><span class="value" style="font-family:var(--font-mono)">${this.esc(l.rows[0].id)}</span></div>
                <div class="detail-row"><span class="label">In My Leads</span><span class="value">${l.inList ? "Yes" : "No"}${l.followUp ? ` · follow up <b>${this.esc(this.fuLabel(l.followUp))}</b>` : ""}</span></div>
                <div class="detail-row"><span class="label">Found in</span><span class="value">${this.esc([l.where ? l.where + " County" : "", l.tabs.map((t) => this.TAB_NAME[t] || t).join(" · ")].filter(Boolean).join(" · "))}</span></div>
                <div class="detail-row"><span class="label">Last touched</span><span class="value">${this.esc(SharedNotes.fmt(l.ts))} (${this.esc(this.ago(l.ts))}) by ${this.esc(l.who)}</span></div>
                ${canOpen ? `<div style="margin-top:10px"><button class="btn btn-primary" id="mlOpenCard">Open the full research card →</button></div>` : ""}
            </div>
            <div class="detail-section"><h3>Everything we've noted (${l.rows.length}, newest first)</h3>
                <div class="note-history">${l.rows.map((r) => SharedNotes.noteCard(r, this.TAB_NAME[r.tab] || r.tab || "")).join("")}</div>
            </div>`;
        const btn = document.getElementById("mlOpenCard");
        if (btn) btn.onclick = () => this.openCard(l);
        document.getElementById("noteHistory").innerHTML = "";
        const sel = document.getElementById("leadStatusSelect"), notes = document.getElementById("leadNotes");
        sel.value = l.status; if (sel.value !== l.status) sel.value = "new";
        notes.value = ""; notes.placeholder = "Add a new note (what happened, what's next). Change the status above if it moved.";
        SharedNotes.paintSync();
        this.setPin(l.rows[0].id, l);
        document.getElementById("saveLeadBtn").onclick = async () => {
            const text = notes.value.trim();
            if (!text && sel.value === l.status) { vaCloseModal(); return; }
            await SharedNotes.save(l.tab || "va-myleads", l.rows[0].id, sel.value, text || `Status changed to ${this.STATUS[sel.value] || sel.value}`, l.label);
            vaCloseModal(); this.render();
        };
        document.getElementById("modalOverlay").classList.add("active");
    },

    /* Jump to the tab the lead came from and open its full card there (switching county first if needed). */
    async openCard(l) {
        vaCloseModal();
        const p = this.parse(l.rows[0].id);
        if (!p) return;
        if (p.key && p.key !== VAPL.key) {
            try { sessionStorage.setItem("vapl_open", l.rows[0].id); } catch {}
            location.href = `?county=${p.key}#${p.tab}`;
            return;
        }
        await this.openIn(p.tab, p.lead);
    },
    async openIn(tab, lead) {
        const btn = document.querySelector(`button.view-tab[data-view="${tab}"]`), app = this.APPS()[tab];
        if (!btn || !app) return;
        btn.click();
        const wait = async (fn) => { for (let i = 0; i < 100 && !fn(); i++) await new Promise((r) => setTimeout(r, 150)); return fn(); };
        await wait(() => app.rows && app.rows.length);
        const r = (app.rows || []).find((x) => String(x.id) === String(lead));
        if (r) app.open(r.id); else alert("That lead isn't on this tab's list anymore (it may have dropped off). Its notes are all still in My Leads.");
    },

    /* "+ Add a lead" form: for something not in any tab (VA house, a tip, a referral). */
    openAdd() {
        document.getElementById("modalBody").innerHTML = `
            <div class="detail-section"><h3>Add a lead to My Leads</h3>
                <p style="font-size:0.85rem; color:var(--text-secondary)">For anything worth pursuing that isn't already a card in the tool. (For a card that's already here, open it and press <b>+ Add to My Leads</b>.)</p>
                <div class="ml-form">
                    <label>Property address *<input id="mlfAddr" placeholder="1234 Ridge Rd, King George VA 22485"></label>
                    <label>Account / parcel # (if you have it)<input id="mlfId" placeholder="Tax map / PIN, e.g. 26 4 B"></label>
                    <label>Owner(s)<input id="mlfOwner" placeholder="Owner or heirs"></label>
                    <label>Where it came from<input id="mlfSrc" placeholder="Neighbor tip, driving, referral, Zillow…"></label>
                    <label>Follow up on (optional)<input type="date" id="mlfFu"></label>
                </div>
            </div>`;
        document.getElementById("noteHistory").innerHTML = "";
        const sel = document.getElementById("leadStatusSelect"), notes = document.getElementById("leadNotes");
        sel.value = "pursuing"; notes.value = ""; notes.placeholder = "What makes it worth pursuing, who to contact, next step.";
        SharedNotes.paintSync(); this.setPin(null);
        document.getElementById("saveLeadBtn").onclick = async () => {
            const v = (id) => document.getElementById(id).value.trim();
            const addr = v("mlfAddr");
            if (!addr) { document.getElementById("mlfAddr").focus(); return; }
            const id = `va:${VAPL.ns}myleads:` + (v("mlfId") || ("ML-" + addr.toUpperCase().replace(/[^A-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40)));
            const label = addr + (v("mlfOwner") ? ` (${v("mlfOwner")})` : "");
            const fu = v("mlfFu");
            const text = [fu ? `FOLLOW UP: ${fu}` : this.ADDED, v("mlfSrc") ? `Source: ${v("mlfSrc")}` : "", notes.value.trim()].filter(Boolean).join("\n");
            await SharedNotes.save("va-myleads", id, fu ? "followup" : sel.value, text, label);
            vaCloseModal(); this.render();
        };
        document.getElementById("modalOverlay").classList.add("active");
    },

    /* The "+ Add to My Leads" button in every card's footer. Shown only for cards that use
       the shared notes (SharedNotes.footer sets the current id); it marks the lead
       "pursuing" through that tab's own Save, so tab, id and label stay exactly right. */
    setPin(id, lead) {
        const box = document.getElementById("mlActions");
        if (!box) return;
        box.style.display = id ? "inline-flex" : "none";
        if (!id) return;
        const rows = SharedNotes.history[id] || [];
        const inList = this.membership(rows), fu = (rows[0] || {}).status === "followup" ? this.fuDate(rows) : "";
        const add = document.getElementById("pinLeadBtn"), rem = document.getElementById("unpinLeadBtn");
        const date = document.getElementById("fuDate"), fuBtn = document.getElementById("fuBtn");
        add.style.display = inList ? "none" : ""; rem.style.display = inList ? "" : "none";
        date.value = fu || ""; date.min = this.today();
        const sel = () => document.getElementById("leadStatusSelect"), notes = () => document.getElementById("leadNotes");
        // the note box is pre-filled with the last note on most cards; only keep it if it was edited
        const typed = () => { const v = notes().value.trim(), prev = ((SharedNotes.get(id) || {}).notes || "").trim(); return v && v !== prev ? v : ""; };
        const go = (status, first) => {
            const t = typed();
            if (status) sel().value = status;
            notes().value = t ? `${first}\n${t}` : first;
            document.getElementById("saveLeadBtn").click();
        };
        add.onclick = () => go(null, this.ADDED);
        rem.onclick = () => go(null, this.REMOVED);
        fuBtn.onclick = () => { if (!date.value) { date.focus(); date.showPicker && date.showPicker(); return; } go("followup", `FOLLOW UP: ${date.value}`); };
    },

    ago(ts) {
        const m = (Date.now() - new Date(ts).getTime()) / 6e4;
        if (isNaN(m)) return "";
        if (m < 60) return `${Math.max(1, Math.round(m))} min ago`;
        if (m < 1440) return `${Math.round(m / 60)} hr ago`;
        const d = Math.round(m / 1440);
        return d === 1 ? "yesterday" : `${d} days ago`;
    },
    esc(s) { return s == null ? "" : String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); },
};

// Every card that uses shared notes calls SharedNotes.footer(id) when it opens: show the My Leads buttons there.
(() => {
    const orig = SharedNotes.footer.bind(SharedNotes);
    SharedNotes.footer = (id) => { orig(id); MyLeadsApp.setPin(id); };
    // hide them whenever the card closes, however it closes
    document.addEventListener("DOMContentLoaded", () => {
        const ov = document.getElementById("modalOverlay");
        if (ov) new MutationObserver(() => { if (!ov.classList.contains("active")) MyLeadsApp.setPin(null); }).observe(ov, { attributes: true, attributeFilter: ["class"] });
        // a lead from another county: the page reloaded on that county; open the card now
        let pend = ""; try { pend = sessionStorage.getItem("vapl_open") || ""; sessionStorage.removeItem("vapl_open"); } catch {}
        const p = pend && MyLeadsApp.parse(pend);
        if (p) setTimeout(() => MyLeadsApp.openIn(p.tab, p.lead), 300);
    });
})();
