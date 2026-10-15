/* Dashboard settings. Edit here, commit, done.

   SHARED_NOTES_URL: the Google Apps Script web app that the Maryland dashboard already
   uses (md-property-leads, docs/shared-notes-setup.md). Every status change and note is
   appended to that one Google Sheet and shown to everyone using either dashboard.
   Virginia rows are written with tab names that start "va-" and ids that start "va:",
   so the two tools never collide. Leave it empty and notes stay in each browser. */
window.VAPL = {
    SHARED_NOTES_URL: "https://script.google.com/macros/s/AKfycbzpEwPb5I4hEjA5YhtzfpcJSVRlhDJvQv5kAeV24KDJ9X9K5mA7QHkq1HJ-tYa_d2igUw/exec",

    /* Counties. The page shows one at a time, picked in the header (…/?county=westmoreland).
       `data` is where that county's boards live; `ns` keeps its notes and statuses apart.
       `thin` marks a county whose parcel record has no values, sale dates or assessor notes. */
    COUNTIES: {
        "king-george": { name: "King George", data: "data/", ns: "", thin: false,
            taxSource: "Treasurer's Real Estate Public Inquiry" },
        "westmoreland": { name: "Westmoreland", data: "data/westmoreland/", ns: "wm:", thin: true,
            taxSource: "Treasurer's Open Tax List",
            note: "<b>Westmoreland County publishes less.</b> Its parcel record has owners, mailing addresses and deed book and page, but no assessed values, sale dates or prices, grantors, will references or assessor notes. So there is no title-age scoring and no condition signal here, and value columns are blank. Unpaid taxes come from the Treasurer's published Open Tax List. In the Town of Colonial Beach the county record names no owner; where the Treasurer bills a parcel, the name and address are taken from the tax list." },
        "fauquier": { name: "Fauquier", data: "data/fauquier/", ns: "fq:", thin: false,
            taxSource: "a 2025 delinquent list", listShort: "on a 2025 list",
            listOnly: "On a 2025 delinquent list you supplied. The list gives an amount only: no tax years, no payment count, and it has not been re-checked.",
            note: "<b>Fauquier's tax balances are loaded by hand.</b> The Treasurer posts a Real Estate Delinquent Aging Account List (PIN, owner, amount) on its Delinquent Listings page, but the county website blocks automated readers, so the Delinquent tab shows the newest list that was downloaded and loaded by hand, with the amount due on its date. Treat every one as possibly paid until the Treasurer confirms it. The parcel record is rich: it gives the type of the last instrument (will, list of heirs, heirship affidavit), sale date and price, and values. Obituaries are not automated here yet; deaths come from federal records through 2007 and anything entered by hand." },
    },
};
(function () {
    let key = new URLSearchParams(location.search).get("county") || "";
    if (!VAPL.COUNTIES[key]) key = "king-george";
    VAPL.key = key;
    VAPL.county = VAPL.COUNTIES[key];
    VAPL.DATA = VAPL.county.data;
    VAPL.ns = VAPL.county.ns;

    /* Waterfront. Every parcel carries `water` when its lot line reaches mapped water
       (engine/waterfront.py) or the assessor's note says waterfront. */
    VAPL.waterOnly = false;

    /* Distress signals (engine/distress.py). Each parcel carries `signals`: public agency
       records matched to it. Chips show OPEN kinds; the panel lists every record. */
    VAPL.SIG = { FIRE: "🔥 FIRE", VACANT_NOTICE: "🏚 VACANT / DERELICT", DERELICT_STRUCTURE: "🏚 DERELICT", RECEIVERSHIP: "🏛 RECEIVERSHIP", SPOT_BLIGHT: "🏛 SPOT BLIGHT",
                 CODE_VIOLATIONS: "⚠ CODE CASE", NUISANCE_CASE: "⚠ NUISANCE", DEMO_PERMIT: "🧱 DEMO PERMIT", REPEAT_CODE_CASES: "⚠ REPEAT CODE CASES", ZONING_CASE: "⚠ ZONING" };
    VAPL.sigFilter = "";
    VAPL.sigsOf = (r) => (r.parcels || []).flatMap((p) => (p.signals || []).map((s) => Object.assign({ _pin: p.parcel || p.pin, _addr: p.address }, s)));
    VAPL.openKinds = (r) => [...new Set(VAPL.sigsOf(r).filter((s) => s.open).map((s) => s.kind))];
    VAPL.sigChips = (r) => {
        const kinds = VAPL.openKinds(r);
        if (!kinds.length) return "";
        const cooling = VAPL.sigsOf(r).some((s) => s.open && s.cooling);
        const e = (s) => String(s).replace(/</g, "&lt;");
        return `<div>${kinds.map((k) => `<span class="chip chip-sig${k === "FIRE" ? " chip-fire" : ""}" title="${e(VAPL.SIG[k] || k)}: an open public-agency record on one of this owner's parcels">${e(VAPL.SIG[k] || k)}</span>`).join(" ")}${kinds.length >= 2 ? '<span class="chip chip-sig" title="Two or more different kinds of record">⚡ STACKED</span>' : ""}${cooling ? '<span class="chip" style="opacity:.8" title="Fire under 30 days old: do not call this week">cooling</span>' : ""}</div>`;
    };
    VAPL.sigPass = (r) => {
        const f = VAPL.sigFilter; if (!f) return true;
        const k = VAPL.openKinds(r);
        if (f === "any") return k.length > 0;
        if (f === "fire") return k.includes("FIRE");
        if (f === "stacked") return k.length >= 2;
        if (f === "repeat") return k.includes("REPEAT_CODE_CASES");
        return true;
    };
    VAPL.sigPanel = (r) => {
        const sigs = VAPL.sigsOf(r);
        if (!sigs.length) return "";
        const e = (s) => (s == null ? "" : String(s)).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
        const open = sigs.filter((s) => s.open), closed = sigs.filter((s) => !s.open);
        const row = (s) => `<tr>
            <td class="mono">${e(s.date || "—")}</td>
            <td>${e(VAPL.SIG[s.kind] || s.kind)}${s.cooling ? ' <span class="chip">cooling</span>' : ""}<div class="sub">${e(s.type || "")}</div></td>
            <td>${e(s.status || "—")}<div class="sub">${s.confirmed ? "inspector-confirmed" : (s.complaint ? "complaint, not yet inspected" : "")}</div></td>
            <td class="mono">${s.url ? `<a href="${e(s.url)}" target="_blank" rel="noopener">${e(s.case_number || "record")}</a>` : e(s.case_number || "")}<div class="sub">${e(s.source || "")}</div></td>
            <td><div class="sub">${e(s._addr || s.address || "")} · map ${e(s._pin || "")} · ${s.match === "parcel" ? "exact (parcel id)" : s.match === "address" ? "exact (address)" : e(s.match || "")}</div>${s.description ? `<div class="sub">${e(s.description)}</div>` : ""}</td></tr>`;
        return `<div class="detail-section"><h3>Distress Signals <span class="sub">${open.length} open · ${closed.length} closed</span></h3>
            <div class="verify"><b>A record is not a condition.</b> An open case means the agency has an active file; a closed or old one says nothing about the property today. Fires under 30 days are marked cooling: do not call that week. Click the case number to read the agency's own record.</div>
            <div class="ptable-wrap"><table class="ptable"><thead><tr><th>Date</th><th>Kind</th><th>Status</th><th>Case / source</th><th>Match</th></tr></thead>
            <tbody>${open.map(row).join("")}${closed.length ? `<tr><td colspan="5" class="sub" style="padding-top:8px">Closed records (history and repeat count only; no points)</td></tr>` + closed.map(row).join("") : ""}</tbody></table></div></div>`;
    };
    VAPL.sigCsv = (r) => { const s = VAPL.sigsOf(r).filter((x) => x.open); return [s.map((x) => x.kind).join("|"), s.map((x) => x.date || "").join("|"), s.map((x) => `${x.source || ""} ${x.case_number || ""}`.trim()).join("|")]; };
    VAPL.waterOf = (r) => (r.parcels || []).map((p) => p.water).find(Boolean) || r.water || null;
    VAPL.waterText = (w) => !w ? "" : (w.source === "assessor" ? "the assessor's note says waterfront; not confirmed on the map"
        : `lot line reaches ${w.water}${w.frontage_ft ? `, about ${Number(w.frontage_ft).toLocaleString()} ft of shoreline` : ""} (measured from the map)`);
    VAPL.drip = (r) => {
        const w = VAPL.waterOf(r);
        if (!w) return "";
        const n = (r.parcels || []).filter((p) => p.water).length;
        const label = w.source === "assessor" ? "waterfront (assessor)" : `${w.water}${w.frontage_ft ? " · ~" + Number(w.frontage_ft).toLocaleString() + " ft" : ""}`;
        return `<div><span class="chip chip-water" title="${VAPL.waterText(w).replace(/"/g, "&quot;")}">💧 ${label.replace(/</g, "&lt;")}${n > 1 ? ` · ${n} parcels` : ""}</span></div>`;
    };
    document.addEventListener("DOMContentLoaded", () => {
        const sel = document.getElementById("countySelect");
        if (sel) {
            sel.innerHTML = Object.entries(VAPL.COUNTIES).map(([k, c]) => `<option value="${k}"${k === key ? " selected" : ""}>${c.name} County</option>`).join("");
            sel.addEventListener("change", () => { location.href = location.pathname + (sel.value === "king-george" ? "" : "?county=" + sel.value) + location.hash; });
        }
        const sf = document.getElementById("sigFilter");
        if (sf) sf.addEventListener("change", () => { VAPL.sigFilter = sf.value; document.dispatchEvent(new CustomEvent("vapl:water")); });
        const wo = document.getElementById("waterOnly");
        if (wo) wo.addEventListener("change", () => { VAPL.waterOnly = wo.checked; document.dispatchEvent(new CustomEvent("vapl:water")); });
        document.querySelectorAll("[data-county-name]").forEach((el) => { el.textContent = VAPL.county.name; });
        document.title = `VA Property Leads — ${VAPL.county.name} County`;
        const note = document.getElementById("countyNote");
        if (note && VAPL.county.note) {
            note.style.display = "block";
            note.innerHTML = VAPL.county.note;
        }
    });
})();
