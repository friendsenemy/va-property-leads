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
            taxSource: "Treasurer's Open Tax List" },
    },
};
(function () {
    let key = new URLSearchParams(location.search).get("county") || "";
    if (!VAPL.COUNTIES[key]) key = "king-george";
    VAPL.key = key;
    VAPL.county = VAPL.COUNTIES[key];
    VAPL.DATA = VAPL.county.data;
    VAPL.ns = VAPL.county.ns;
    document.addEventListener("DOMContentLoaded", () => {
        const sel = document.getElementById("countySelect");
        if (sel) {
            sel.innerHTML = Object.entries(VAPL.COUNTIES).map(([k, c]) => `<option value="${k}"${k === key ? " selected" : ""}>${c.name} County</option>`).join("");
            sel.addEventListener("change", () => { location.href = location.pathname + (sel.value === "king-george" ? "" : "?county=" + sel.value) + location.hash; });
        }
        document.querySelectorAll("[data-county-name]").forEach((el) => { el.textContent = VAPL.county.name; });
        document.title = `VA Property Leads — ${VAPL.county.name} County`;
        const note = document.getElementById("countyNote");
        if (note && VAPL.county.thin) {
            note.style.display = "block";
            note.innerHTML = `<b>${VAPL.county.name} County publishes less.</b> Its parcel record has owners, mailing addresses and deed book and page, but no assessed values, sale dates or prices, grantors, will references or assessor notes. So there is no title-age scoring and no condition signal here, and value columns are blank. Unpaid taxes come from the Treasurer's published Open Tax List. In the Town of Colonial Beach the county record names no owner; where the Treasurer bills a parcel, the name and address are taken from the tax list.`;
        }
    });
})();
