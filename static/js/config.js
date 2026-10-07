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
            note: "<b>Fauquier County publishes no tax balances.</b> Its tax inquiry needs a login and there is no public delinquent list, so the Delinquent tab shows only the parcels on a 2025 list you supplied, with the amount due then. Treat every one as possibly paid until the Treasurer confirms it. The parcel record is rich: it gives the type of the last instrument (will, list of heirs, heirship affidavit), sale date and price, and values. Obituaries are not automated here yet; deaths come from federal records through 2007 and anything entered by hand." },
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
