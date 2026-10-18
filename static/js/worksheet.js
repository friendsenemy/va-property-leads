/* VIRGINIA version (ported from md-property-leads static/js/worksheet.js; Virginia rules in VA_RULES below).
   Deal worksheet for every lead card: PETITO note template, Owners & Liens sheet, Deal calculator.
   Built from the curative-title playbook (Tim Bender / Ellis San Jose / Logan Fullmer):
     - PETITO = Property, Equity, Title, Interested parties, Threats, Opportunity.
     - Ownership map (who owns what share, alive?, where they stand) + lien stack (every lien,
       book/page or case #, what it attaches to, status) before any offer.
     - Deal math: as-is value minus every cost of cure, minus Ray's target profit = what can be
       paid to owners; each owner's offer by share, with a staged deposit/balance plan.
   Storage: the same shared notes sheet. Each lead's worksheet is one JSON row saved under the id
   "<lead id>#ws" (tab "va-worksheet"; lead ids already start "va:"). SharedNotes keeps those rows out of the lead's note history
   and out of My Leads, so they never change a lead's status. A localStorage copy is kept too. */
/* Virginia law constants used by the lien-buy check. Each one cites the Code of Virginia section;
   confirm with a Virginia title attorney before relying on any of them for a purchase. */
const VA_RULES = {
    judgmentRate: 6,              // § 6.2-302 judgment rate, unless the judgment states a contract rate
    circuitYears: 20,             // § 8.01-251(A): circuit court judgment, 20 years from entry
    gdcYears: 10,                 // § 8.01-251(A)/(B): general district court judgment, 10 years (can be extended)
    dotAfterMaturityYears: 20,    // § 8.01-241: deed of trust lien unenforceable 20 yrs after the last payment falls due
    rentsYears: 5,                // § 8.01-462: court orders a sale only if 5 years of rents won't pay the judgment
};

const Worksheet = {
    id: null,           // current lead id (set when any card opens)
    data: null,         // working copy while the panel is open
    section: "owners",

    OWNER_STAGES: ["Not contacted", "Talking", "Offer made", "Signed", "Holdout", "Won't sell", "Can't find"],
    LIFE: ["Alive", "Deceased", "Unknown"],
    LIEN_TYPES: ["Mortgage / deed of trust", "Judgment", "County taxes", "Municipal / water / sewer", "IRS lien", "VA state tax",
        "Medicaid estate claim", "HOA / condo", "Code / abatement", "Mechanic's lien", "Child support", "Reverse mortgage (HECM)", "Other"],
    LIEN_STATUS: ["Open", "Negotiating", "Pay at closing", "Released", "Expired?", "Settled", "Not ours (wrong person)"],
    LIVE_LIEN: ["Open", "Negotiating", "Pay at closing", "Expired?"],

    blank() {
        return {
            v: 1, owners: [], liens: [],
            calc: { value: "", sellPct: 8, taxes: "", liensOverride: "", estates: 0, perEstate: 3000, legal: "", survey: "",
                cleanup: "", holdMonths: 4, holdPerMonth: 300, closing: "", target: 50000, depositPct: 10 },
        };
    },

    /* ---------- storage ---------- */
    wsKey(id) { return String(id) + "#ws"; },
    load(id) {
        let d = null;
        const row = SharedNotes.worksheets && SharedNotes.worksheets[this.wsKey(id)];
        if (row) { try { d = JSON.parse(row.notes); d._ts = row.ts; d._who = row.author; } catch {} }
        if (!d) { try { d = JSON.parse(localStorage.getItem("vapl_ws_" + this.wsKey(id)) || "null"); } catch {} }
        const b = this.blank();
        if (!d) return b;
        return Object.assign(b, d, { calc: Object.assign(b.calc, d.calc || {}) });
    },
    async save() {
        if (!this.id || !this.data) return;
        const d = Object.assign({}, this.data); delete d._ts; delete d._who;
        const json = JSON.stringify(d);
        try { localStorage.setItem("vapl_ws_" + this.wsKey(this.id), json); } catch {}
        const ok = await SharedNotes.saveWorksheet(this.wsKey(this.id), json, this.label());
        this.data._ts = new Date().toISOString(); this.data._who = SharedNotes.author() || "you";
        this.flash(ok ? "Saved for everyone" : "Saved in this browser — shared sheet unreachable");
    },

    /* ---------- lead facts pulled from whatever tab the card came from ---------- */
    facts(id) {
        // find the row behind this shared id in whichever tab owns it (Title, D4D, Death, Delinquent, Stack, Surplus)
        const apps = [];
        if (typeof TitleApp !== "undefined") apps.push(TitleApp);
        if (typeof D4DApp !== "undefined") apps.push(D4DApp);
        if (typeof DeathApp !== "undefined") apps.push(DeathApp);
        if (typeof DelinqApp !== "undefined") apps.push(DelinqApp);
        if (typeof StackApp !== "undefined") apps.push(StackApp);
        if (typeof SurplusApp !== "undefined") apps.push(SurplusApp);
        let r = null;
        for (const app of apps) {
            if (!app || !app.rows || typeof app.sid !== "function") continue;
            r = app.rows.find((x) => { try { return app.sid(x) === id; } catch { return false; } });
            if (r) break;
        }
        r = r || {};
        const ps = r.parcels && r.parcels.length ? r.parcels : [r];
        const p = ps.find((x) => x.address) || ps[0] || {};
        const num = (v) => { const n = parseFloat(String(v == null ? "" : v).replace(/[$,]/g, "")); return isNaN(n) ? null : n; };
        const last = SharedNotes.get(id) || {};
        const flags = new Set([...(r.flags || []), ...(p.flags || [])]);
        const total = num(r.total_value) || ps.reduce((a, x) => a + (num(x.total_value) || 0), 0) || num(p.assessed_value) || null;
        const mailState = r.mail && r.mail.state ? String(r.mail.state).toUpperCase() : "";
        const absentee = flags.has("OUT_OF_STATE") || flags.has("OUT_OF_COUNTY") || flags.has("MAIL_DIFFERS") || flags.has("CARE_OF");
        const building = ps.some((x) => (num(x.impr_value) || 0) > 0 || x.year_built);
        const dq = r.delinquency || {};
        return {
            id,
            account: ps.map((x) => x.parcel || x.pin).filter(Boolean).join(", ") || r.pin || id,
            address: [p.address, p.city].filter(Boolean).join(", ") || r.address || last.label || "",
            owner: r.owner || r.name || "",
            type: [p.legal || "", ps.length > 1 ? `${ps.length} parcels` : "", +p.year_built > 0 ? `built ${p.year_built}` : "", (r.acres || p.acres) ? `${r.acres || p.acres} ac` : ""].filter(Boolean).join(", "),
            assessed: total,
            deed: ps.map((x) => [x.deed_ref, x.will_ref ? "Will " + x.will_ref : ""].filter(Boolean).join(" ")).filter(Boolean).join("; "),
            taxFace: num(dq.past_due),
            taxStatus: dq.past_due ? `unpaid ${(dq.years || []).join(", ")}${dq.sale_eligible ? " — eligible for a tax sale suit" : ""}` : "",
            outOfState: mailState && mailState !== "VA" ? mailState : "",
            // Virginia records have no owner-occupancy code: treat "bill mailed to the property, with a building" as likely lived in
            occupied: building && !absentee,
            occupiedNote: "VA records have no owner-occupancy code; mail goes to the site and there's a building",
            stack: (r._stack || []).join(", "),
            vesting: r.owner_type || "",
            spouses: /\b(&|AND|ET UX|ETUX|H\/W|HUSBAND|WIFE)\b/i.test(r.owner || "") || r.owner_subtype === "TBE",
        };
    },
    label() { const f = this.facts(this.id); return f.address ? `${f.address} — worksheet` : `${this.id} worksheet`; },

    /* ---------- toolbar in the lead modal ---------- */
    mountToolbar() {
        if (document.getElementById("wsBar")) return;
        const ta = document.getElementById("leadNotes");
        if (!ta) return;
        const bar = document.createElement("div");
        bar.id = "wsBar"; bar.className = "ws-bar"; bar.style.display = "none";
        bar.innerHTML = `<button type="button" class="btn ws-btn" id="wsPetito" title="Insert a PETITO lead-note outline, pre-filled from this card">📋 PETITO note</button>
            <button type="button" class="btn ws-btn" id="wsOwners" title="Who owns what share, alive?, contact stage; every lien and its status">👥 Owners &amp; Liens</button>
            <button type="button" class="btn ws-btn" id="wsCalc" title="Value minus costs of cure minus your target profit = what you can pay each owner">🧮 Deal Calculator</button>
            <span class="ws-sum" id="wsSum"></span>`;
        ta.parentNode.insertBefore(bar, ta);
        document.getElementById("wsPetito").onclick = () => this.insertPetito();
        document.getElementById("wsOwners").onclick = () => this.openPanel("owners");
        document.getElementById("wsCalc").onclick = () => this.openPanel("calc");

        const ov = document.createElement("div");
        ov.id = "wsOverlay"; ov.className = "modal-overlay ws-overlay";
        ov.innerHTML = `<div class="modal ws-modal"><div class="modal-header"><h2 id="wsTitle">Deal Worksheet</h2>
            <button class="modal-close" id="wsClose" title="Close (changes are kept until you leave the card)">✕</button></div>
            <div class="ws-tabs"><button type="button" data-s="owners">👥 Owners</button><button type="button" data-s="liens">🧾 Liens</button><button type="button" data-s="calc">🧮 Deal Calculator</button></div>
            <div class="modal-body" id="wsBody"></div>
            <div class="modal-footer"><div class="note-row" style="justify-content:flex-end">
                <span class="note-sync" id="wsSync" style="margin-right:auto"></span>
                <button type="button" class="btn" id="wsToNote" title="Put a short summary into the note box (then press Save on the card)">↧ Summary into note</button>
                <button type="button" class="btn btn-primary" id="wsSave">Save worksheet</button>
            </div></div></div>`;
        document.body.appendChild(ov);
        ov.addEventListener("click", (e) => { if (e.target.id === "wsOverlay") this.closePanel(); });
        document.getElementById("wsClose").onclick = () => this.closePanel();
        ov.querySelectorAll(".ws-tabs button").forEach((b) => b.onclick = () => { this.read(); this.section = b.dataset.s; this.render(); });
        document.getElementById("wsSave").onclick = async () => { this.read(); await this.save(); const m = document.getElementById("wsSync").textContent; this.render(); this.flash(m); this.paintSummary(); };
        document.getElementById("wsToNote").onclick = () => { this.read(); this.noteSummaryInto(); this.closePanel(); };
        // Escape closes only the worksheet when it's open (capture phase, before the card's handler)
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && ov.classList.contains("active")) { e.stopImmediatePropagation(); this.closePanel(); }
        }, true);
    },

    setLead(id) {
        this.mountToolbar();
        this.id = id || null;
        this.data = null;
        const bar = document.getElementById("wsBar");
        if (bar) bar.style.display = id ? "flex" : "none";
        if (id) this.paintSummary();
    },

    paintSummary() {
        const el = document.getElementById("wsSum");
        if (!el || !this.id) return;
        const d = this.data || this.load(this.id);
        const s = this.ownerStats(d), m = this.math(d);
        const bits = [];
        if (d.owners.length) bits.push(`${d.owners.length} owner${d.owners.length === 1 ? "" : "s"} · ${this.pct(s.signed)} signed`);
        const live = d.liens.filter((l) => this.LIVE_LIEN.includes(l.status)).length;
        if (d.liens.length) bits.push(`${live} open lien${live === 1 ? "" : "s"}`);
        if (m.value) bits.push(`max to owners ${this.money(m.maxToOwners)}`);
        el.textContent = bits.join(" · ");
    },

    /* ---------- PETITO note ---------- */
    insertPetito() {
        const f = this.facts(this.id), d = this.data || this.load(this.id), m = this.math(d);
        const owners = d.owners.length
            ? d.owners.map((o) => `${o.name || "?"}${o.relation ? ` (${o.relation})` : ""} ${o.share ? this.pct(this.n(o.share)) : "?%"} — ${(o.life || "Unknown").toUpperCase()}${o.contact ? ", " + o.contact : ""} — ${o.stage || "Not contacted"}`).join("; ")
            : `${f.owner || "?"} — ALIVE?/DEAD? (obit, Find a Grave, Register of Wills)`;
        const liens = d.liens.filter((l) => this.LIVE_LIEN.includes(l.status));
        const lienTxt = liens.length ? liens.map((l) => `${l.type}${l.holder ? " " + l.holder : ""}${l.ref ? " [" + l.ref + "]" : ""}${l.amount ? " " + this.money(this.n(l.amount)) : ""} ${l.status}`).join("; ") : "";
        const lines = [
            `ID: ${f.account}${f.address ? " / " + f.address : ""}${f.deed ? " / " + f.deed : ""}`,
            `P (Property): ${f.type || "type?"}; vacant? ${f.occupied ? "LIKELY LIVED IN (tax bill goes to the property) — skip if occupied" : "check"}; flood zone / Chesapeake Bay Preservation Area?`,
            m.value
                ? `E (Equity): as-is ${this.money(m.value)}; taxes ${this.money(m.taxes)}; liens ${this.money(m.liens)}; costs to cure ${this.money(m.cure)}; spread ${this.money(m.net)}; max to owners ${this.money(m.maxToOwners)} at ${this.money(m.target)} target profit`
                : `E (Equity): as-is ${f.assessed ? "~" + this.money(f.assessed) + " assessed (check comps)" : "?"}; taxes ${f.taxFace ? this.money(f.taxFace) : "?"}; liens ?; spread ? (open the Deal Calculator)`,
            `T (Title): vesting ${f.vesting || "?"}; owner of record ${f.owner || "?"}; clouds: ${lienTxt || "?"}`,
            `I (Interested parties): ${owners}${f.outOfState ? ` [owner mail goes out of state: ${f.outOfState}]` : ""}`,
            `TH (Threats): ${f.taxStatus ? "taxes " + f.taxStatus + "; " : ""}tax sale suit filed (circuit court)? bankruptcy (PACER)? judgments on owners/heirs (judgment lien docket, OCIS)? Medicaid (DMAS) claim? occupants? capacity?`,
            `O (Opportunity): `,
            `VERDICT: GO / PARK / KILL — `,
            `NEXT: `,
        ];
        const ta = document.getElementById("leadNotes");
        const prev = (SharedNotes.get(this.id) || {}).notes || "";
        const cur = ta.value.trim();
        ta.value = (cur && cur !== prev.trim() ? cur + "\n\n" : "") + lines.join("\n");
        ta.focus();
        const at = ta.value.indexOf("O (Opportunity): ") + "O (Opportunity): ".length;
        try { ta.setSelectionRange(at, at); } catch {}
    },

    /* ---------- panel ---------- */
    openPanel(section) {
        if (!this.id) return;
        if (!this.data) this.data = this.load(this.id);
        this.section = section;
        const f = this.facts(this.id);
        if (this.data.calc.value === "" && f.assessed) this.data.calc.value = Math.round(f.assessed);
        if (this.data.calc.taxes === "" && f.taxFace) this.data.calc.taxes = Math.round(f.taxFace);
        document.getElementById("wsTitle").textContent = `Deal Worksheet — ${f.address || this.id}`;
        this.render();
        document.getElementById("wsOverlay").classList.add("active");
    },
    closePanel() {
        this.read();
        document.getElementById("wsOverlay").classList.remove("active");
        this.paintSummary();
    },
    flash(msg) { const el = document.getElementById("wsSync"); if (el) { el.className = "note-sync on"; el.textContent = msg; } },

    render() {
        const d = this.data;
        document.querySelectorAll("#wsOverlay .ws-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.s === this.section));
        const body = document.getElementById("wsBody");
        body.innerHTML = this.section === "owners" ? this.ownersHtml(d) : this.section === "liens" ? this.liensHtml(d) : this.calcHtml(d);
        const sync = document.getElementById("wsSync");
        sync.className = "note-sync"; sync.textContent = d._ts ? `Last saved ${SharedNotes.fmt(d._ts)} by ${d._who || "?"}` : "Not saved yet";
        body.querySelectorAll("[data-add]").forEach((b) => b.onclick = () => {
            this.read();
            if (b.dataset.add === "owner") d.owners.push({ name: "", relation: "", share: "", life: "Alive", contact: "", stage: "Not contacted", price: "", note: "" });
            else d.liens.push({ type: "Judgment", holder: "", ref: "", amount: "", date: "", rate: String(VA_RULES.judgmentRate), attaches: "Property", status: "Open", payoff: "", note: "" });
            this.render();
        });
        body.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => {
            this.read();
            const [list, i] = b.dataset.del.split(":");
            d[list].splice(+i, 1); this.render();
        });
        body.querySelectorAll("[data-even]").forEach((b) => b.onclick = () => {
            this.read();
            const n = d.owners.length; if (!n) return;
            d.owners.forEach((o) => o.share = +(100 / n).toFixed(4)); this.render();
        });
        // live recompute on the calculator
        if (this.section === "calc") body.querySelectorAll("input,select").forEach((el) => el.addEventListener("input", () => { this.read(); this.paintCalc(); }));
        if (this.section !== "calc") body.querySelectorAll("input,select").forEach((el) => el.addEventListener("change", () => { this.read(); this.paintTotals(); if (this.section === "liens") this.paintBuy(); }));
        const go = document.getElementById("wsPasteGo");
        if (go) go.onclick = () => {
            this.read();
            const n = this.importCaseSearch(document.getElementById("wsPasteCS").value);
            this.pasteOpen = true; this.render(); this.pasteOpen = false;
            const msg = document.getElementById("wsPasteMsg");
            if (msg) msg.textContent = n.added ? `Added ${n.added} case${n.added === 1 ? "" : "s"} (skipped ${n.skipped} that aren't money claims or are already listed). Open each case: was a judgment entered? amount? renewed? satisfied? same person?` : `Nothing added — ${n.skipped} row${n.skipped === 1 ? "" : "s"} were criminal/traffic/family/plaintiff cases or already listed.`;
        };
        if (this.section === "calc") this.paintCalc(); else this.paintTotals();
        if (this.section === "liens") this.paintBuy();
    },

    /* read every field in the open section back into this.data */
    read() {
        const d = this.data; if (!d) return;
        const body = document.getElementById("wsBody"); if (!body) return;
        body.querySelectorAll("[data-f]").forEach((el) => {
            const [list, i, key] = el.dataset.f.split(":");
            if (list === "calc") d.calc[key] = el.value;
            else if (d[list] && d[list][+i]) d[list][+i][key] = el.value;
        });
    },

    sel(path, opts, val) { return `<select data-f="${path}">${opts.map((o) => `<option${o === val ? " selected" : ""}>${this.esc(o)}</option>`).join("")}</select>`; },
    inp(path, val, ph, cls) { return `<input data-f="${path}" value="${this.esc(val == null ? "" : val)}" placeholder="${this.esc(ph || "")}"${cls ? ` class="${cls}"` : ""}>`; },

    ownersHtml(d) {
        const rows = d.owners.map((o, i) => `<div class="ws-card">
            <div class="ws-grid">
                <label>Name ${this.inp(`owners:${i}:name`, o.name, "Paul D. Hood Jr.")}</label>
                <label>Relation / role ${this.inp(`owners:${i}:relation`, o.relation, "son, heir of grandson, co-owner…")}</label>
                <label>Share % ${this.inp(`owners:${i}:share`, o.share, "25", "ws-num")}</label>
                <label>Alive? ${this.sel(`owners:${i}:life`, this.LIFE, o.life)}</label>
                <label>Where / phone ${this.inp(`owners:${i}:contact`, o.contact, "Clarksville TN · (931) …")}</label>
                <label>Stage ${this.sel(`owners:${i}:stage`, this.OWNER_STAGES, o.stage)}</label>
                <label>Price agreed / paid $ ${this.inp(`owners:${i}:price`, o.price, "", "ws-num")}</label>
                <label class="ws-wide">Note ${this.inp(`owners:${i}:note`, o.note, "evidence of death, obit link, who they listen to, capacity concerns…")}</label>
            </div>
            <button type="button" class="ws-del" data-del="owners:${i}" title="Remove this owner">✕</button></div>`).join("");
        return `<div class="ws-help">Ownership map: every person who holds (or may hold) a share. A deceased owner's share goes to <b>their</b> heirs — add each heir as their own row with the fraction they inherit (Virginia intestacy, Va. Code § 64.2-200 et seq.). Call the most disconnected, smallest owner first.</div>
            ${rows || '<div class="ws-empty">No owners yet.</div>'}
            <div class="ws-actions"><button type="button" class="btn" data-add="owner">+ Add owner / heir</button>
            ${d.owners.length > 1 ? '<button type="button" class="btn" data-even="1">Split shares evenly</button>' : ""}</div>
            <div class="ws-totals" id="wsTotals"></div>`;
    },

    liensHtml(d) {
        const rows = d.liens.map((l, i) => `<div class="ws-card">
            <div class="ws-grid">
                <label>Type ${this.sel(`liens:${i}:type`, this.LIEN_TYPES, l.type)}</label>
                <label>Holder ${this.inp(`liens:${i}:holder`, l.holder, "Capital One, county, HUD…")}</label>
                <label>Book/page or case # ${this.inp(`liens:${i}:ref`, l.ref, "EWS 1234/56 · C-08-CV-24-000123")}</label>
                <label>Amount of record $ ${this.inp(`liens:${i}:amount`, l.amount, "", "ws-num")}</label>
                <label>Date entered / recorded ${this.inp(`liens:${i}:date`, l.date, "2014-06-30")}</label>
                <label>Interest % / yr ${this.inp(`liens:${i}:rate`, l.rate, "6 (VA judgment rate) or the contract rate", "ws-num")}</label>
                <label>Attaches to ${this.inp(`liens:${i}:attaches`, l.attaches, "Property, or one heir's share")}</label>
                <label>Status ${this.sel(`liens:${i}:status`, this.LIEN_STATUS, l.status)}</label>
                <label>Est. payoff $ ${this.inp(`liens:${i}:payoff`, l.payoff, "what it will really cost", "ws-num")}</label>
                <label class="ws-wide">Note ${this.inp(`liens:${i}:note`, l.note, "renewed? right person? SOL? release demand sent? settle %…")}</label>
            </div>
            <div class="ws-buy" data-buy="${i}"></div>
            <button type="button" class="ws-del" data-del="liens:${i}" title="Remove this lien">✕</button></div>`).join("");
        return `<div class="ws-help">Lien stack: treat every lien as a claim, not a fact. Check: right person? docketed in <b>this</b> county's circuit court judgment lien docket (§ 8.01-458)? still enforceable (VA circuit judgments 20 yrs, GDC 10 yrs — § 8.01-251; can be extended)? released under a misspelled name? attaches to the property or only one owner's share? Run judgments on the decedent <b>and</b> every heir. Taxes go in the calculator, not here — unless it's a separate municipal or water bill.</div>
            <details class="ws-paste"${this.pasteOpen ? " open" : ""}><summary>📥 Paste OCIS / judgment-lien docket results (search each owner and heir by name in OCIS 2.0 or the clerk\'s judgment index, select the results, copy, paste here)</summary>
                <textarea id="wsPasteCS" placeholder="Case Number  Name  Party Type  Court  Case Type  Case Status  Filing Date  Case Caption …"></textarea>
                <button type="button" class="btn" id="wsPasteGo">Add cases as liens</button> <span class="ws-totals" id="wsPasteMsg"></span>
            </details>
            ${rows || '<div class="ws-empty">No liens yet.</div>'}
            <div class="ws-actions"><button type="button" class="btn" data-add="lien">+ Add lien / cloud</button></div>
            <div class="ws-totals" id="wsTotals"></div>`;
    },

    paintTotals() {
        const el = document.getElementById("wsTotals"); if (!el) return;
        const d = this.data;
        if (this.section === "owners") {
            const s = this.ownerStats(d);
            const warn = d.owners.length && Math.abs(s.total - 100) > 0.5 ? ` <span class="ws-bad">shares add to ${this.pct(s.total)}, not 100%</span>` : "";
            el.innerHTML = d.owners.length ? `${d.owners.length} owner${d.owners.length === 1 ? "" : "s"} · ${this.pct(s.signed)} signed · ${s.dead} deceased · ${s.holdouts} holdout${s.holdouts === 1 ? "" : "s"} · paid/agreed ${this.money(s.paid)}${warn}${d.owners.length > 5 ? ' <span class="ws-warn">more than 5 owners — the playbook says the deal needs a big spread</span>' : ""}` : "";
        } else {
            const live = d.liens.filter((l) => this.LIVE_LIEN.includes(l.status));
            const rec = live.reduce((a, l) => a + (this.n(l.amount) || 0), 0), pay = live.reduce((a, l) => a + (this.n(l.payoff) || this.n(l.amount) || 0), 0);
            el.innerHTML = d.liens.length ? `${live.length} still live · ${this.money(rec)} of record · ${this.money(pay)} expected payoff (used by the calculator)` : "";
        }
    },

    calcHtml(d) {
        const c = d.calc, liveLiens = this.liensPayoff(d);
        const f = (k, label, ph, help) => `<label>${label} ${this.inp(`calc:0:${k}`, c[k], ph, "ws-num")}${help ? `<small>${help}</small>` : ""}</label>`;
        return `<div class="ws-help">Price is the risk control. Use the AS-IS value (never ARV), budget every cost of cure, set your profit first — what's left is the most you can pay all owners combined. Benchmarks: buy at 10–50¢ on the dollar; skip under ~$30–40K value; aim for $40–50K+ profit.</div>
            <div class="ws-grid ws-calc">
                ${f("value", "As-is value $", "150000", "assessed is a start; check comps")}
                ${f("sellPct", "Selling costs %", "8", "commission + seller closing")}
                ${f("taxes", "Back taxes, all jurisdictions $", "", "county + town + water/front-foot")}
                ${f("liensOverride", "Liens payoff $", String(liveLiens || ""), `from Liens tab: ${this.money(liveLiens)} (leave blank to use it)`)}
                ${f("estates", "Deaths to document (#)", "1", "each death in the chain")}
                ${f("perEstate", "Cost per death $", "3000", "list of heirs / affidavit; more if a PR must qualify")}
                ${f("legal", "Attorney / quiet title / partition $", "", "uncontested QT ~$1.5–5K")}
                ${f("survey", "Survey $", "", "infill ~$500–800; rural $15K+")}
                ${f("cleanup", "Trash-out / repairs $", "", "")}
                ${f("holdMonths", "Months to hold", "4", "~120 days is the goal")}
                ${f("holdPerMonth", "Holding $/month", "300", "insurance, utilities, mowing")}
                ${f("closing", "Recordation / closing $", "", "VA recordation tax on your buy deeds (sellers pay grantor tax)")}
                ${f("target", "Your target profit $", "50000", "")}
                ${f("depositPct", "Deposit at signing %", "10", "balance at milestones / resale")}
            </div>
            <div id="wsCalcOut"></div>`;
    },

    liensPayoff(d) { return d.liens.filter((l) => this.LIVE_LIEN.includes(l.status)).reduce((a, l) => a + (this.n(l.payoff) || this.n(l.amount) || 0), 0); },

    math(d) {
        const c = d.calc, n = (k) => this.n(c[k]) || 0;
        const value = n("value");
        const sell = value * n("sellPct") / 100;
        const taxes = n("taxes");
        const liens = c.liensOverride !== "" && c.liensOverride != null && !isNaN(parseFloat(c.liensOverride)) ? n("liensOverride") : this.liensPayoff(d);
        const cure = n("estates") * n("perEstate") + n("legal") + n("survey") + n("cleanup") + n("holdMonths") * n("holdPerMonth") + n("closing");
        const net = value - sell - taxes - liens - cure;
        const target = n("target");
        const maxToOwners = Math.max(0, net - target);
        const allIn = maxToOwners + taxes + liens + cure;
        return { value, sell, taxes, liens, cure, net, target, maxToOwners, allIn, cents: value ? allIn / value : 0, depositPct: n("depositPct") };
    },

    paintCalc() {
        const el = document.getElementById("wsCalcOut"); if (!el) return;
        const d = this.data, m = this.math(d), s = this.ownerStats(d);
        const flags = [];
        if (m.value && m.value < 40000) flags.push(["bad", "Value under ~$40K — Logan won't touch these even free (same work as a big deal)."]);
        if (m.value && m.net - m.target < 0) flags.push(["bad", `Costs + your profit exceed the value by ${this.money(m.target - m.net)}. Lower the target or walk.`]);
        if (m.value && m.net < 40000) flags.push(["warn", "Total spread under $40K — thin for a curative deal."]);
        if (d.owners.length > 5) flags.push(["warn", `${d.owners.length} owners — odds that everyone signs drop fast; needs a big spread.`]);
        if (m.value && m.cents > 0.5) flags.push(["warn", `All-in is ${Math.round(m.cents * 100)}¢ on the dollar — the playbook range is 10–50¢.`]);
        if (s.dead && d.calc.estates < 1) flags.push(["warn", "A deceased owner is listed but no heirship / estate cost is budgeted."]);
        const unsigned = d.owners.filter((o) => o.stage !== "Signed");
        const paidSigned = d.owners.filter((o) => o.stage === "Signed").reduce((a, o) => a + (this.n(o.price) || 0), 0);
        const left = Math.max(0, m.maxToOwners - paidSigned);
        const ownerRows = d.owners.map((o) => {
            const sh = this.n(o.share) || 0;
            const retail = m.value * sh / 100;
            // ceiling = this owner's share of what all owners can be paid; money saved on cheap signers stays
            // as the cushion for heirs you haven't found yet, it is NOT handed to the remaining owners
            let offer = o.stage === "Signed" ? (this.n(o.price) || 0) : Math.min(m.maxToOwners * sh / 100, left);
            const floor = offer > 0 && offer < 1000;
            const dep = Math.round(offer * m.depositPct / 100);
            return `<tr><td>${this.esc(o.name || "?")}<div class="meta">${this.esc(o.stage || "")}${o.life === "Deceased" ? " · deceased (estate)" : ""}</div></td>
                <td>${this.pct(sh)}</td><td>${this.money(retail)}</td>
                <td><b>${this.money(offer)}</b>${floor ? ' <span class="ws-warn" title="Pay at least ~$1,000 per interest so it isn\'t attacked as a gift">min $1K</span>' : ""}</td>
                <td>${o.stage === "Signed" ? "—" : `${this.money(dep)} now + ${this.money(offer - dep)} at clear title / resale`}</td></tr>`;
        }).join("");
        // what a holdout is worth: if everyone else is signed, the holdout blocks the whole remaining spread
        const hold = d.owners.filter((o) => o.stage === "Holdout");
        const holdTxt = hold.length && m.value ? `<div class="ws-note">Holdout math: ${hold.map((o) => this.esc(o.name || "?")).join(", ")} block${hold.length === 1 ? "s" : ""} a ${this.money(m.net)} spread. Paying the owners who haven't signed up to ~${this.money(Math.max(0, m.net - m.target - paidSigned))} combined still hits your target — usually cheaper than a 6–9 month partition (~$15–30K if it settles).</div>` : "";
        el.innerHTML = `<div class="ws-out">
                <div><span>Value</span><b>${this.money(m.value)}</b></div>
                <div><span>− Selling costs</span><b>${this.money(m.sell)}</b></div>
                <div><span>− Back taxes</span><b>${this.money(m.taxes)}</b></div>
                <div><span>− Liens payoff</span><b>${this.money(m.liens)}</b></div>
                <div><span>− Costs to cure &amp; hold</span><b>${this.money(m.cure)}</b></div>
                <div class="ws-line"><span>= Spread before buying shares</span><b>${this.money(m.net)}</b></div>
                <div><span>− Your target profit</span><b>${this.money(m.target)}</b></div>
                <div class="ws-line ws-big"><span>Most you can pay ALL owners</span><b>${this.money(m.maxToOwners)}</b></div>
                <div><span>All-in (owners + taxes + liens + cure)</span><b>${this.money(m.allIn)} · ${m.value ? Math.round(m.cents * 100) + "¢ on the $" : ""}</b></div>
            </div>
            ${flags.map(([k, t]) => `<div class="ws-flag ws-${k}">${k === "bad" ? "⛔" : "⚠️"} ${this.esc(t)}</div>`).join("")}
            ${d.owners.length ? `<h4 class="ws-h4">Offer by share${paidSigned ? ` (signed owners: ${this.money(paidSigned)} already committed)` : ""}</h4>
            <table class="ws-table"><thead><tr><th>Owner</th><th>Share</th><th>Share of retail</th><th>Max offer</th><th>Staged plan</th></tr></thead><tbody>${ownerRows}</tbody></table>
            <div class="ws-note">These are ceilings, not opening numbers. Quote each heir a NET number by share (never one flat price to everyone), keep room for heirs you haven't found yet, and answer value questions honestly.</div>` : '<div class="ws-note">Add owners on the Owners tab to get an offer for each share.</div>'}
            ${holdTxt}`;
    },

    /* ---------- Lien-buy play (Logan / Ellis): buy an old lien on a non-homestead property at a
       discount, record the assignment, send an honest demand, then collect at a sale/refi/estate
       or enforce (judgment: writ of execution + sheriff's sale; DOT: foreclosure). ---------- */
    accrued(l) {
        const amt = this.n(l.amount), rate = this.n(l.rate), dt = l.date ? new Date(/^\d{4}-\d{2}-\d{2}$/.test(l.date) ? l.date + "T12:00:00" : l.date) : null;
        if (!amt || !dt || isNaN(dt)) return null;
        const yrs = Math.max(0, (Date.now() - dt.getTime()) / 31557600000);
        return { yrs, bal: amt * (1 + (rate || 0) / 100 * yrs), dt };   // simple interest (VA post-judgment interest is simple, § 6.2-302 — verify)
    },
    paintBuy() {
        const d = this.data, f = this.facts(this.id), m = this.math(d);
        const ownersN = d.owners.length || ((f.owner || "").split(/\s*\/\s*|\s+&\s+|\s+AND\s+/i).filter(Boolean).length);
        const spouses = /&|\bAND\b|\bET UX\b|\bH\/W\b|\bHUSBAND|\bWIFE/i.test(f.owner || "") || /entiret/i.test(f.vesting || "");
        document.querySelectorAll("#wsBody [data-buy]").forEach((el) => {
            const i = +el.dataset.buy, l = d.liens[i];
            if (!l || !["Judgment", "Mortgage / deed of trust", "HOA / condo", "Mechanic's lien", "Other"].includes(l.type)) { el.innerHTML = ""; return; }
            const a = this.accrued(l);
            const warn = [], good = [];
            if (f.occupied) warn.push("Looks lived-in (building on it and the tax bill goes to the property) — skip (Ray's no-occupied rule; VA homestead exemption § 34-4 and tenancy-by-the-entirety protection also bite).");
            else good.push("Tax bill goes elsewhere — looks absentee / not lived in (confirm with a drive-by).");
            if (l.type === "Judgment" && spouses) warn.push("Looks like spouses on title. If they hold as tenants by the entirety and the judgment is against only one spouse, it can't be enforced against this property.");
            if (l.type === "Judgment" && ownersN > 1) warn.push("More than one owner: a judgment attaches only to the debtor's own share.");
            if (["Released", "Settled", "Not ours (wrong person)"].includes(l.status)) warn.push(`Status is "${l.status}" — nothing to buy.`);
            let expTxt = "";
            if (a && l.type === "Judgment") {
                const gdc = /^GV|general district|\bGDC\b/i.test((l.ref || "") + " " + (l.note || ""));
                const life = gdc ? VA_RULES.gdcYears : VA_RULES.circuitYears;
                const exp = new Date(a.dt); exp.setFullYear(exp.getFullYear() + life);
                const left = (exp - Date.now()) / 31557600000;
                expTxt = left > 0 ? `${life}-yr ${gdc ? "GDC" : "circuit"} judgment runs to ${exp.toLocaleDateString("en-US")} (${left.toFixed(1)} yrs left) unless extended` : `PAST ${life} years (${exp.toLocaleDateString("en-US")}) — worthless unless it was extended (§ 8.01-251, check the docket)`;
                if (left <= 0) warn.push("Judgment may be expired — confirm an extension before paying anything.");
                else if (left < 1.5) warn.push("Judgment expires soon — the holder may sell cheap, but you'd need to extend or enforce fast.");
                warn.push(`Virginia sells land for a judgment only through a creditor's bill in circuit court, and only if ${VA_RULES.rentsYears} years of rents won't pay it (§ 8.01-462). Expect a lawsuit, not a quick sheriff's sale.`);
            }
            if (a && l.type === "Mortgage / deed of trust") warn.push(`Check the note's maturity date: a deed of trust can't be enforced ${VA_RULES.dotAfterMaturityYears} years after the last payment was due (§ 8.01-241). Inside that, Virginia foreclosure is by trustee's sale without court.`);
            // equity behind this lien: value minus taxes minus liens recorded earlier (lower index = senior, as listed)
            const senior = d.liens.slice(0, i).filter((x) => this.LIVE_LIEN.includes(x.status)).reduce((s2, x) => s2 + (this.n(x.payoff) || this.n(x.amount) || 0), 0);
            const val = m.value || f.assessed || 0;
            const cover = val - (m.taxes || f.taxFace || 0) - senior;
            const bal = a ? a.bal : this.n(l.amount);
            if (bal && val) { if (cover >= bal) good.push(`Equity covers it: ${this.money(cover)} behind it vs ${this.money(bal)} owed.`); else warn.push(`Equity behind it (${this.money(cover)}) is less than the ${this.money(bal)} owed — only partly secured.`); }
            const lo = bal ? bal * 0.05 : 0, hi = bal ? bal * (a && a.yrs > 7 ? 0.15 : 0.3) : 0;
            el.innerHTML = bal ? `<div class="ws-buy-h">💰 Lien-buy check</div>
                <div class="ws-buy-row">${a ? `${this.money(this.n(l.amount))} from ${a.dt.toLocaleDateString("en-US")}${/\bfiled \d/.test(l.note || "") ? " (OCIS filing date — swap in the judgment date)" : ""} at ${this.n(l.rate) || 0}%/yr → <b>~${this.money(a.bal)} owed now</b> (${a.yrs.toFixed(1)} yrs)` : `<b>${this.money(bal)}</b> of record — add the date and rate to see what's owed now`}${expTxt ? ` · ${expTxt}` : ""}</div>
                <div class="ws-buy-row">Opening offer to the holder: ~${this.money(lo)}–${this.money(hi)} (old, non-paying claims trade at ~5–30¢; ~10¢ on judgments 8+ yrs old)</div>
                ${good.map((t) => `<div class="ws-buy-ok">✓ ${this.esc(t)}</div>`).join("")}${warn.map((t) => `<div class="ws-buy-bad">⚠ ${this.esc(t)}</div>`).join("")}` : "";
        });
    },

    /* Parse pasted Virginia OCIS 2.0 results or a circuit-court judgment lien docket into lien rows.
       The format varies by screen, so this is forgiving: every line (or run of lines) that carries a
       VA civil case number starts a record; criminal / traffic / juvenile cases are skipped. */
    importCaseSearch(text) {
        const raw = String(text || "").split(/\r?\n/).map((x) => x.replace(/\t+/g, "  ").trim()).filter(Boolean);
        const caseRe = /\b((?:GV|CL|CJ|GJ|JD|CH|LD|CM|SC)\d{2}[-]?\d{4,7}(?:-\d{2})?)\b/i;
        const skipRe = /\b(?:GC|GT|CR|JA|JJ|GM)\d{2}[-]?\d{4,7}/i;
        const blocks = [];
        for (const ln of raw) {
            if (caseRe.test(ln) || skipRe.test(ln)) blocks.push([ln]);
            else if (blocks.length) blocks[blocks.length - 1].push(ln);
        }
        let added = 0, skipped = 0;
        const have = new Set(this.data.liens.map((l) => (l.ref || "").trim().toUpperCase()));
        for (const b of blocks) {
            const all = b.join("  ");
            const m = all.match(caseRe);
            if (!m || (skipRe.test(b[0]) && !caseRe.test(b[0]))) { skipped++; continue; }
            const num = m[1].toUpperCase();
            const T = all.toLowerCase();
            if (have.has(num) || /criminal|traffic|infraction|misdemeanor|felony|custody|visitation|divorce|protective order|support|adoption|name change|expunge|unlawful detainer|detinue/.test(T)) { skipped++; continue; }
            const isPl = /\bplaintiff\b|\bpetitioner\b/i.test(all) && !/\bdefendant\b|\brespondent\b/i.test(all);
            if (isPl) { skipped++; continue; }   // the owner is suing someone — not a lien on them
            const dates = all.match(/\b\d{1,2}\/\d{1,2}\/\d{4}\b/g) || [];
            const jd = (all.match(/judgment(?: date)?[:\s]+(\d{1,2}\/\d{1,2}\/\d{4})/i) || [])[1] || "";
            const when = jd || dates[0] || "";
            const iso = when ? (() => { const [mm, dd, yy] = when.split("/"); return `${yy}-${mm.padStart(2, "0")}-${dd.padStart(2, "0")}`; })() : "";
            const amt = (all.match(/\$\s?([\d,]+(?:\.\d{2})?)/) || [])[1] || "";
            const vs = all.match(/([A-Z0-9&.,' -]{3,80}?)\s+(?:v\.?|vs\.?)\s+([A-Z0-9&.,' -]{3,80})/i);
            const plaintiff = vs ? vs[1].replace(caseRe, "").replace(/^\W+|\W+$/g, "").trim() : "";
            const debtor = vs ? vs[2].replace(/\s{2,}.*/, "").trim() : "";
            let ltype = "Judgment";
            if (/delinquent tax|tax sale|§ ?58\.1-39|real estate tax/.test(T)) ltype = "County taxes";
            else if (/foreclos|deed of trust/.test(T)) ltype = "Mortgage / deed of trust";
            else if (/mechanic/.test(T)) ltype = "Mechanic's lien";
            else if (/commonwealth|department of taxation/.test(T) && /tax/.test(T)) ltype = "VA state tax";
            const court = /^GV/i.test(num) || /general district/i.test(all) ? "General District Court" : "Circuit Court";
            const released = /satisf|released|paid in full|marked paid/i.test(all);
            this.data.liens.push({
                type: ltype, holder: plaintiff, ref: num, amount: amt.replace(/,/g, ""), date: iso,
                rate: ltype === "Judgment" ? String(VA_RULES.judgmentRate) : "",
                attaches: `${debtor || "debtor"} — property only if it's this owner and it's docketed in this county`,
                status: released ? "Released" : "Open", payoff: "",
                note: `${court} · ${when ? (jd ? "judgment " : "filed ") + when : "no date in paste"}. ${ltype === "County taxes" ? "Delinquent-tax suit (§ 58.1-3965) — get the payoff from the treasurer and the sale date from the special commissioner." : "Open the case: judgment entered? date + amount? docketed in this county's judgment lien docket? extended? satisfied? Same person (DOB / middle name / address)?"}`,
            });
            have.add(num); added++;
        }
        return { added, skipped };
    },

    ownerStats(d) {
        let total = 0, signed = 0, dead = 0, holdouts = 0, paid = 0;
        for (const o of d.owners) {
            const sh = this.n(o.share) || 0; total += sh;
            if (o.stage === "Signed") { signed += sh; paid += this.n(o.price) || 0; }
            if (o.life === "Deceased") dead++;
            if (o.stage === "Holdout" || o.stage === "Won't sell") holdouts++;
        }
        return { total, signed, dead, holdouts, paid };
    },

    noteSummaryInto() {
        const d = this.data, m = this.math(d), s = this.ownerStats(d);
        const lines = [];
        if (d.owners.length) lines.push(`OWNERS: ${d.owners.map((o) => `${o.name || "?"} ${o.share ? this.pct(this.n(o.share)) : "?%"} ${o.life === "Deceased" ? "DECEASED" : o.life === "Unknown" ? "alive?" : ""} — ${o.stage}${o.price ? " " + this.money(this.n(o.price)) : ""}`.replace(/\s+—/, " —")).join("; ")} (${this.pct(s.signed)} signed)`);
        const live = d.liens.filter((l) => this.LIVE_LIEN.includes(l.status));
        if (d.liens.length) lines.push(`LIENS: ${d.liens.map((l) => `${l.type}${l.holder ? " " + l.holder : ""}${l.ref ? " [" + l.ref + "]" : ""}${l.amount ? " " + this.money(this.n(l.amount)) : ""} ${l.status}`).join("; ")}${live.length ? ` (live payoff ~${this.money(this.liensPayoff(d))})` : ""}`);
        if (m.value) lines.push(`DEAL MATH: as-is ${this.money(m.value)}; spread ${this.money(m.net)}; max to owners ${this.money(m.maxToOwners)} at ${this.money(m.target)} profit; all-in ${Math.round(m.cents * 100)}¢ on the $`);
        const ta = document.getElementById("leadNotes");
        const prev = (SharedNotes.get(this.id) || {}).notes || "";
        const cur = ta.value.trim();
        ta.value = (cur && cur !== prev.trim() ? cur + "\n" : "") + lines.join("\n");
        ta.focus();
    },

    /* ---------- helpers ---------- */
    n(v) { const x = parseFloat(String(v == null ? "" : v).replace(/[$,%\s]/g, "")); return isNaN(x) ? null : x; },
    money(v) { v = Number(v) || 0; return (v < 0 ? "-$" : "$") + Math.round(Math.abs(v)).toLocaleString(); },
    pct(v) { v = Number(v) || 0; return (Math.round(v * 100) / 100) + "%"; },
    esc(s) { return s == null ? "" : String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); },
};

// Follow the card that's open: MyLeadsApp.setPin(id) runs on every card open (and setPin(null) on close).
(() => {
    const hook = () => {
        if (typeof MyLeadsApp === "undefined") return;
        const orig = MyLeadsApp.setPin.bind(MyLeadsApp);
        MyLeadsApp.setPin = (id, lead) => { orig(id, lead); if (!document.getElementById("wsOverlay") || !document.getElementById("wsOverlay").classList.contains("active")) Worksheet.setLead(id); };
    };
    hook();
    document.addEventListener("vapl:notes-loaded", () => { if (Worksheet.id) Worksheet.paintSummary(); });
})();
