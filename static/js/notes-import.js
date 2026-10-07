/* Private notes import. A notes file ({"notes": {"<parcel id>": "text"}}) is read in this
   browser only and never uploaded. Each note is added to the Notes box of every lead that
   holds that parcel, on every tab, including leads that appear on the board later. */
(function () {
    // Per county: the notes file is loaded while that county is selected, and stays with it.
    const MAP_KEY = "va_imported_notes_v1" + VAPL.ns;
    const BOARDS = [
        [VAPL.DATA + "title/leads.json", "va_title_leads_local_v1" + VAPL.ns],
        [VAPL.DATA + "obits/matches.json", "va_death_leads_local_v1" + VAPL.ns],
        [VAPL.DATA + "delinquency/leads.json", "va_delinq_leads_local_v1" + VAPL.ns],
        [VAPL.DATA + "combined/leads.json", "va_stack_leads_local_v1" + VAPL.ns],
    ];
    const read = (k) => { try { return JSON.parse(localStorage.getItem(k) || "{}"); } catch { return {}; } };

    async function apply() {
        const map = read(MAP_KEY);
        if (!Object.keys(map).length) return 0;
        let added = 0;
        for (const [url, key] of BOARDS) {
            let rows;
            try { rows = (await (await fetch(url, { cache: "no-store" })).json()).rows || []; } catch { continue; }
            const local = read(key);
            let changed = false;
            for (const r of rows) {
                for (const p of r.parcels || []) {
                    const note = map[String(p.pid)];
                    if (!note) continue;
                    const cur = local[r.id] || { status: "new", notes: "" };
                    if ((cur.notes || "").includes(note)) continue;
                    cur.notes = (cur.notes ? cur.notes + "\n\n" : "") + note;
                    cur.updated = new Date().toISOString();
                    local[r.id] = cur; changed = true; added++;
                }
            }
            if (changed) { try { localStorage.setItem(key, JSON.stringify(local)); } catch {} }
        }
        return added;
    }

    document.addEventListener("DOMContentLoaded", () => {
        const btn = document.getElementById("importNotesBtn"), file = document.getElementById("importNotesFile");
        if (btn && file) {
            btn.addEventListener("click", () => file.click());
            file.addEventListener("change", async () => {
                if (!file.files[0]) return;
                try {
                    const j = JSON.parse(await file.files[0].text());
                    const incoming = j.notes || j;
                    const map = Object.assign(read(MAP_KEY), incoming);
                    localStorage.setItem(MAP_KEY, JSON.stringify(map));
                    const n = await apply();
                    btn.textContent = `Notes loaded: ${Object.keys(incoming).length} parcels, ${n} added to leads`;
                    setTimeout(() => location.reload(), 1800);
                } catch (e) { btn.textContent = "That file could not be read"; }
            });
        }
        apply().then((n) => { if (n) location.reload(); });
    });
})();
