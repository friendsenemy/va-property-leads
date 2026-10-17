/* Aerial / street imagery panel on every lead card — the same panel as the Maryland tool.
   All free sources, built in the browser:
   - Esri World Imagery tiles (usually the newest; free basemap, attribution required)
   - USGS National Map NAIP Plus (~1 m)
   Where the point comes from:
   - data/<county>/centroids.json: one point inside each lot, from the county's parcel
     outlines (engine/centroids.py, weekly)
   - otherwise the Esri World Geocoder, free for look-ups that are not stored, by address
   Links out to Google Street View / Satellite / Maps / Earth, Mapillary, Zillow, Redfin and
   the county's property card. No API keys, no billing. */
const Aerial = {
    NAIP: "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer/exportImage",
    ESRI: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile",
    GEOCODE: "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",

    SOURCES: [
        { id: "esri", label: "Satellite", sub: "newest" },
        { id: "naip", label: "NAIP 1-m", sub: "USGS" },
        { id: "wide", label: "Wide", sub: "" },
    ],

    _pts: {},          // county data dir -> Promise<{pid: [lat, lon]}>
    _geo: {},          // address -> Promise<[lat, lon] | null>

    /* ── where the parcel is ───────────────────────────────────────────── */
    countyDir(name) {
        const n = String(name || "").trim().toLowerCase();
        if (!n) return VAPL.DATA;
        const hit = Object.values(VAPL.COUNTIES).find((c) => c.name.toLowerCase() === n);
        return hit ? hit.data : null;                 // a county the tool does not cover: geocode instead
    },
    countyName(r) { return r.county || VAPL.county.name; },
    points(dir) {
        if (!dir) return Promise.resolve({});
        if (!this._pts[dir]) {
            this._pts[dir] = fetch(`${dir}centroids.json`, { cache: "force-cache" })
                .then((x) => (x.ok ? x.json() : {})).catch(() => ({}));
        }
        return this._pts[dir];
    },
    addrText(p, county) {
        return `${p.address || ""}, ${county} County, VA`.replace(/\s+/g, " ").replace(/^, /, "").trim();
    },
    geocode(addr) {
        if (!this._geo[addr]) {
            const u = `${this.GEOCODE}?f=json&maxLocations=1&outFields=Score&SingleLine=${encodeURIComponent(addr)}`;
            this._geo[addr] = fetch(u).then((x) => x.json()).then((j) => {
                const c = (j.candidates || [])[0];
                return c && c.score >= 85 ? [c.location.y, c.location.x] : null;
            }).catch(() => null);
        }
        return this._geo[addr];
    },
    async locate(p, county) {
        const pts = await this.points(this.countyDir(county));
        const hit = p.pid != null ? pts[String(p.pid)] : null;
        if (hit) return { lat: hit[0], lon: hit[1], how: "lot" };
        if (p.address) {
            const g = await this.geocode(this.addrText(p, county));
            if (g) return { lat: g[0], lon: g[1], how: "address" };
        }
        return null;
    },

    /* ── links ─────────────────────────────────────────────────────────── */
    streetViewUrl(lat, lon) { return `https://www.google.com/maps?q=&layer=c&cbll=${lat},${lon}&cbp=11,0,0,0,0`; },
    mapsUrl(lat, lon) { return `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`; },
    satelliteUrl(lat, lon) { return `https://www.google.com/maps/@${lat},${lon},19z/data=!3m1!1e3`; },
    mapillaryUrl(lat, lon) { return `https://www.mapillary.com/app/?lat=${lat}&lng=${lon}&z=17.5`; },
    // /search/<address> makes Earth drop its pin and open the place card; a bare lot searches by its point
    earthUrl(lat, lon, p, county) {
        const q = p.address ? encodeURIComponent(this.addrText(p, county)).replace(/%20/g, "+") : `${lat},${lon}`;
        return `https://earth.google.com/web/search/${q}`;
    },
    zillowUrl(p, county) {
        const slug = this.addrText(p, county).replace(/[^A-Za-z0-9 ]/g, "").trim().replace(/\s+/g, "-");
        return `https://www.zillow.com/homes/${encodeURIComponent(slug)}_rb/`;
    },
    redfinUrl(p, county) { return `https://www.redfin.com/search#query=${encodeURIComponent(this.addrText(p, county))}`; },

    /* ── tiles ─────────────────────────────────────────────────────────── */
    bbox(lat, lon, meters) {
        const dLat = meters / 111320, dLon = meters / (111320 * Math.cos(lat * Math.PI / 180));
        return `${lon - dLon},${lat - dLat},${lon + dLon},${lat + dLat}`;
    },
    naipUrl(lat, lon, meters = 60, size = 640) {
        return `${this.NAIP}?bbox=${this.bbox(lat, lon, meters)}&bboxSR=4326&imageSR=3857&size=${size},${size}&format=jpg&f=image`;
    },
    tileXY(lat, lon, z) {
        const n = 2 ** z, latR = lat * Math.PI / 180;
        return { x: (lon + 180) / 360 * n, y: (1 - Math.log(Math.tan(latR) + 1 / Math.cos(latR)) / Math.PI) / 2 * n };
    },
    /** Tile mosaic centred on the point, exactly covering a px×px square, with a pin on the lot. */
    tileGridHtml(lat, lon, z, px) {
        const { x, y } = this.tileXY(lat, lon, z);
        const T = 256, half = px / 2 / T;
        let tiles = "";
        for (let ty = Math.floor(y - half); ty <= Math.floor(y + half); ty++) {
            for (let tx = Math.floor(x - half); tx <= Math.floor(x + half); tx++) {
                const left = (tx - x) * T + px / 2, top = (ty - y) * T + px / 2;
                tiles += `<img src="${this.ESRI}/${z}/${ty}/${tx}" style="position:absolute;left:${left.toFixed(1)}px;top:${top.toFixed(1)}px;width:${T}px;height:${T}px" alt="" loading="lazy">`;
            }
        }
        return `<div class="tile-grid" style="position:relative;width:${px}px;height:${px}px;overflow:hidden">${tiles}
                <div class="aerial-pin" title="Parcel point"></div>
                <div class="tile-attrib">Esri, Maxar, Earthstar Geographics</div></div>`;
    },

    /* ── panel ─────────────────────────────────────────────────────────── */
    /** Placeholder for a lead's imagery; Aerial.bind() fills it in once the point is known. */
    section(r) {
        const parcels = (r.parcels && r.parcels.length ? r.parcels : [r]).filter((p) => p && (p.pid != null || p.address));
        if (!parcels.length) return "";
        // the parcel worth looking at first: a street address, then the highest value
        const order = parcels.slice().sort((a, b) => (!!b.address - !!a.address) || ((b.total_value || b.assessed_value || 0) - (a.total_value || a.assessed_value || 0)));
        const county = this.countyName(r);
        const uid = `aer-${Math.random().toString(36).slice(2)}`;
        this._pending = this._pending || {};
        this._pending[uid] = { parcels: order.slice(0, 12), county };
        const pick = order.length > 1 ? `<select class="aerial-pick" title="Which parcel to show">${order.slice(0, 12).map((p, i) =>
            `<option value="${i}">${TitleApp.esc(p.address || "Tax map " + (p.parcel || p.pin || p.pid))}</option>`).join("")}</select>` : "";
        return `<div class="detail-section"><h3>Property imagery${pick ? " " + pick : ""}</h3>
            <div class="aerial" id="${uid}"><div class="aerial-missing">Finding the parcel on the map…</div></div></div>`;
    },

    async fill(box, p, county) {
        const esc = TitleApp.esc;
        const loc = await this.locate(p, county);
        if (!loc) {
            box.innerHTML = `<div class="aerial-missing">No map point for this parcel yet (the weekly parcel-outline pull adds new lots).</div>
                <div class="aerial-links">${p.address ? `<a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(this.addrText(p, county))}" target="_blank" rel="noopener">Google Maps ↗</a>
                <a href="${this.zillowUrl(p, county)}" target="_blank" rel="noopener">Zillow ↗</a>
                <a href="${this.redfinUrl(p, county)}" target="_blank" rel="noopener">Redfin ↗</a>` : ""}
                ${p.card_url ? `<a href="${esc(p.card_url)}" target="_blank" rel="noopener">County card ↗</a>` : ""}</div>`;
            return;
        }
        const { lat, lon } = loc;
        box.dataset.lat = lat; box.dataset.lon = lon; box.dataset.addr = p.address || "";
        const ac = parseFloat(p.acres) || 0;           // zoom out for big lots so the whole parcel is in frame
        box.dataset.z = ac > 20 ? 16 : ac > 5 ? 17 : ac > 1 ? 18 : 19;
        box.innerHTML = `
            <div class="aerial-tabs">
                ${this.SOURCES.map((s, i) => `<button class="aerial-tab${i === 0 ? " active" : ""}" data-src="${s.id}">${s.label}${s.sub ? ` <span class="aerial-date">${s.sub}</span>` : ""}</button>`).join("")}
            </div>
            <a class="aerial-img-wrap" href="${this.satelliteUrl(lat, lon)}" target="_blank" rel="noopener" title="Open in Google Maps satellite">
                <div class="aerial-stage"></div>
                <div class="aerial-fail">Imagery unavailable from all free sources right now — use the links below.</div>
            </a>
            <div class="aerial-links">
                <a href="${this.streetViewUrl(lat, lon)}" target="_blank" rel="noopener">Street View ↗</a>
                <a href="${this.satelliteUrl(lat, lon)}" target="_blank" rel="noopener">Google Satellite ↗</a>
                <a href="${this.mapsUrl(lat, lon)}" target="_blank" rel="noopener">Google Maps ↗</a>
                <a href="${this.earthUrl(lat, lon, p, county)}" target="_blank" rel="noopener">Google Earth ↗</a>
                <a href="${this.mapillaryUrl(lat, lon)}" target="_blank" rel="noopener">Mapillary ↗</a>
                ${p.address ? `<a href="${this.zillowUrl(p, county)}" target="_blank" rel="noopener">Zillow ↗</a>
                <a href="${this.redfinUrl(p, county)}" target="_blank" rel="noopener">Redfin ↗</a>` : ""}
                ${p.card_url ? `<a href="${esc(p.card_url)}" target="_blank" rel="noopener">County card ↗</a>` : ""}
                <span class="aerial-coords">${lat.toFixed(5)}, ${lon.toFixed(5)}</span>
            </div>
            <div class="aerial-note">${loc.how === "lot" ? "Pin marks a point inside the lot, from the county's parcel outlines." : "Pin placed by street address (no parcel outline on file), so it may sit on the road or a neighbour."}
                Imagery dates vary by source. Condition may have changed since capture.</div>`;
        box.querySelectorAll(".aerial-tab").forEach((tab) => tab.addEventListener("click", (e) => { e.preventDefault(); this.show(box, tab.dataset.src, false); }));
        this.show(box, "esri", true);
    },

    /** Render one source into the stage; on failure fall through to the next. */
    show(box, srcId, autoFallback) {
        const lat = parseFloat(box.dataset.lat), lon = parseFloat(box.dataset.lon);
        const stage = box.querySelector(".aerial-stage"), wrap = box.querySelector(".aerial-img-wrap");
        const px = Math.min(640, Math.max(280, Math.floor(wrap.clientWidth || 640)));
        wrap.classList.remove("failed");
        box.querySelectorAll(".aerial-tab").forEach((t) => t.classList.toggle("active", t.dataset.src === srcId));
        const order = this.SOURCES.map((s) => s.id);
        const next = () => {
            if (!autoFallback) { wrap.classList.add("failed"); return; }
            const nxt = order.slice(order.indexOf(srcId) + 1).find((s) => s !== "wide");
            if (nxt) this.show(box, nxt, true); else wrap.classList.add("failed");
        };
        if (srcId === "esri" || srcId === "wide") {
            const z = parseInt(box.dataset.z, 10) || 19;
            stage.innerHTML = this.tileGridHtml(lat, lon, srcId === "wide" ? Math.max(14, z - 2) : z, px);
            const imgs = stage.querySelectorAll("img");
            let failed = 0;
            imgs.forEach((im) => { im.onerror = () => { failed++; if (failed === imgs.length) next(); }; });
            return;
        }
        const meters = { 16: 400, 17: 200, 18: 100 }[parseInt(box.dataset.z, 10)] || 60;
        stage.innerHTML = `<img class="aerial-img" src="${this.naipUrl(lat, lon, meters, px)}" alt="Aerial of ${TitleApp.esc(box.dataset.addr)}" loading="lazy">`;
        const img = stage.querySelector("img");
        img.onerror = next;
        img.onload = () => { if (img.naturalWidth < 50) next(); };   // ArcGIS sometimes returns a tiny blank image
    },

    /** Fill every pending imagery block inside a container (call after setting innerHTML). */
    bind(container) {
        container.querySelectorAll(".aerial:not([data-bound])").forEach((box) => {
            const job = (this._pending || {})[box.id];
            if (!job) return;
            box.dataset.bound = "1";
            const sel = box.parentElement.querySelector(".aerial-pick");
            if (sel) sel.addEventListener("change", () => { box.innerHTML = '<div class="aerial-missing">Finding the parcel on the map…</div>'; this.fill(box, job.parcels[+sel.value], job.county); });
            this.fill(box, job.parcels[0], job.county);
        });
    },

    /** "Property" block: the subject parcel's address and facts, the way the Maryland card shows them. */
    propertySection(r) {
        const esc = TitleApp.esc;
        const ps = (r.parcels && r.parcels.length ? r.parcels : [r]);
        const p = ps.slice().sort((a, b) => (!!b.address - !!a.address) || ((b.total_value || b.assessed_value || 0) - (a.total_value || a.assessed_value || 0)))[0] || {};
        const county = this.countyName(r);
        const m = (v) => (v != null && v !== "" && !isNaN(parseFloat(v)) && parseFloat(v) !== 0) ? "$" + Math.round(parseFloat(v)).toLocaleString() : "";
        const row = (label, val) => val ? `<div class="detail-row"><span class="label">${label}</span><span class="value">${val}</span></div>` : "";
        const total = p.total_value || p.assessed_value;
        const transfer = p.sale_year && !p.sale_year_estimated ? `${p.sale_year}${p.years_since_transfer != null ? ` (${p.years_since_transfer} yrs ago)` : ""}${p.sale_price ? " · " + m(p.sale_price) : " · $0 / not a sale"}`
            : p.sale_year_estimated ? "undated (old deed book)" : "";
        const type = VAPL.county.thin ? "" : p.impr_value === 0 || (p.impr_value == null && !p.year_built && (r.flags || []).includes("VACANT_LAND")) ? "Land, no building on the assessment"
            : p.year_built ? `Building · built ${p.year_built}` : (p.impr_value ? "Building" : "");
        const addr = p.address ? `<b>${esc(p.address)}</b>, ${esc(county)} County, VA` : `<span class="sub">No street address (land)</span> · ${esc(county)} County, VA`;
        return `<div class="detail-section"><h3>Property${ps.length > 1 ? ` <span class="sub">(1 of ${ps.length} parcels, all listed below)</span>` : ""}</h3>
            ${row("Address", addr)}
            ${row("County", esc(county) + " County")}
            ${row("Tax map / PIN", `<span class="mono">${esc(p.parcel || p.pin || "")}</span>${p.card_url ? ` · <a href="${esc(p.card_url)}" target="_blank" rel="noopener" style="color:var(--cyan-dim)">county card ↗</a>` : ""}`)}
            ${row("Type", esc(type))}
            ${row("Assessed", total ? `${m(total)}${p.land_value || p.impr_value ? ` <span class="sub">(${m(p.land_value) || "$0"} land / ${m(p.impr_value) || "$0"} impr)</span>` : ""}` : (VAPL.county.thin ? '<span class="sub">not published by this county</span>' : ""))}
            ${row("Acres", p.acres ? Number(p.acres).toLocaleString() + " ac" : "")}
            ${row("Condition", p.cond ? esc(p.cond) : "")}
            ${row("Last transfer", esc(transfer))}
            ${row("Deed", p.deed_ref ? `<span class="mono">${esc(p.deed_ref)}</span>` : "")}
            ${row("Will / heirs ref", p.will_ref ? `<span class="mono" style="color:var(--purple)">${esc(p.will_ref)}</span>` : "")}
            ${row("Legal", esc(p.legal || ""))}
            ${row("Waterfront", p.water ? "💧 " + esc(VAPL.waterText(p.water)) : "")}
            ${row("Assessor remarks", esc(p.remarks || p.note || ""))}
        </div>`;
    },

    /** Insert the Property and imagery blocks after the first section of a card's HTML. */
    insert(html, r) {
        const block = this.propertySection(r) + this.section(r);
        if (!block) return html;
        const first = html.indexOf('<div class="detail-section"');
        const second = first < 0 ? -1 : html.indexOf('<div class="detail-section"', first + 1);
        return second < 0 ? html + block : html.slice(0, second) + block + html.slice(second);
    },
};
