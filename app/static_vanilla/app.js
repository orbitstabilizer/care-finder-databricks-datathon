/* Care finder front end: no build step, Leaflet from CDN. */
(() => {
  const TIERS = ["Confirmed", "Likely", "Possible", "Unverified"];
  const COLOUR = { Confirmed: "#1f9d55", Likely: "#d4900d", Possible: "#2b6cb0", Unverified: "#8a94a3" };
  const FIRST = 5, STEP = 5;
  const EXAMPLES = [
    { label: "dialysis", name: "Dialysis", q: "pin=835207", where: "835207" },
    { label: "caesarean_section", name: "C-section", q: "place=Hyderabad", where: "Hyderabad" },
    { label: "nicu", name: "NICU", q: "pin=560001", where: "560001" },
  ];
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const MQ = window.matchMedia?.("(prefers-color-scheme: dark)");
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
    set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (_) { /* storage blocked */ } },
  };
  let themePref = ["light", "dark"].includes(store.get("vf-theme")) ? store.get("vf-theme") : "auto";
  const isDark = () => themePref === "dark" || (themePref === "auto" && !!MQ?.matches);

  const ICON = {
    warn: `<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>`,
    phone: `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2Z"/></svg>`,
    nav: `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="m3 11 19-9-9 19-2-8-8-2Z"/></svg>`,
    web: `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm-10-10h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20Z"/></svg>`,
    back: `<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M19 12H5m7 7-7-7 7-7"/></svg>`,
    pin: `<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M12 22s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12Zm0-9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"/></svg>`,
  };

  const state = {
    services: [], service: null, point: null, origin: null, notes: [],
    data: null, shown: {}, openUnverified: false, emergency: false, loading: false,
    markers: {}, byId: {}, selected: null, hovered: null,
  };

  async function api(path, opts) {
    const r = await fetch(path, opts);
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || `Request failed (${r.status})`);
    return body;
  }

  /* ---------------------------------------------------------- toasts --- */
  function toast(text, kind = "err") {
    const t = document.createElement("div");
    t.className = `toast ${kind}`;
    t.innerHTML = `<span>${esc(text)}</span><button class="t-x" aria-label="Dismiss">&times;</button>`;
    const kill = () => { t.classList.add("out"); setTimeout(() => t.remove(), 170); };
    t.querySelector(".t-x").onclick = kill;
    $("toasts").appendChild(t);
    setTimeout(kill, 6000);
  }
  function msg(text) { if (text) toast(text); }
  function busy(btn, on) { if (!btn) return; btn.disabled = on; btn.classList.toggle("busy", on); }

  /* ------------------------------------------------------------ map --- */
  const map = L.map("map", {
    center: [22.5, 82.5], zoom: 5, minZoom: 4, zoomControl: false,
    maxBounds: [[6, 68], [37.5, 98]], maxBoundsViscosity: 1.0,
  });
  L.control.zoom({ position: "topleft" }).addTo(map);
  // Muted basemap. CARTO Positron now answers "API key required", so Esri's keyless gray canvas is used.
  const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/";
  const shade = isDark() ? "Dark" : "Light";
  const esriOpts = { maxNativeZoom: 16, maxZoom: 18, attribution: "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors" };
  const base = L.tileLayer(`${ESRI}World_${shade}_Gray_Base/MapServer/tile/{z}/{y}/{x}`, esriOpts).addTo(map);
  map.createPane("labels"); map.getPane("labels").style.zIndex = 350; map.getPane("labels").style.pointerEvents = "none";
  const labels = L.tileLayer(`${ESRI}World_${shade}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, { ...esriOpts, attribution: "", pane: "labels" }).addTo(map);
  // Transparent label tiles: drop leftover tiles of other zoom levels once the current level has loaded,
  // otherwise stretched labels from the previous zoom show through after an animated fitBounds.
  labels.on("load", () => {
    const z = String(labels._tileZoom);
    labels.getContainer()?.querySelectorAll(".leaflet-tile-container").forEach((c) => {
      const lvl = Object.entries(labels._levels || {}).find(([, l]) => l.el === c);
      if (lvl && lvl[0] !== z) c.style.display = "none"; else c.style.display = "";
    });
  });
  const resultLayer = L.layerGroup().addTo(map);
  let pointMarker = null, ring = null, halo = null, mask = null, border = null;
  const maskStyle = () => (isDark() ? { fillColor: "#05080c", fillOpacity: 0.62 } : { fillColor: "#eef0f3", fillOpacity: 0.72 });
  const borderStyle = () => ({ color: isDark() ? "#4a5565" : "#b9c0ca" });

  /* ---------------------------------------------------------- theme --- */
  const THEME_ICON = {
    auto: `<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor"/></svg>`,
    light: `<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></g></svg>`,
    dark: `<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>`,
  };
  function applyTheme() {
    const root = document.documentElement;
    if (themePref === "auto") delete root.dataset.theme; else root.dataset.theme = themePref;
    const sh = isDark() ? "Dark" : "Light";
    base.setUrl(`${ESRI}World_${sh}_Gray_Base/MapServer/tile/{z}/{y}/{x}`);
    labels.setUrl(`${ESRI}World_${sh}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`);
    mask?.setStyle(maskStyle()); border?.setStyle(borderStyle());
    const b = $("theme-btn");
    const next = { auto: "light", light: "dark", dark: "auto" }[themePref];
    b.innerHTML = THEME_ICON[themePref];
    b.setAttribute("aria-label", `Theme: ${themePref}. Switch to ${next}.`);
    b.title = `Theme: ${themePref} (click for ${next})`;
  }
  $("theme-btn").addEventListener("click", () => {
    themePref = { auto: "light", light: "dark", dark: "auto" }[themePref];
    store.set("vf-theme", themePref === "auto" ? null : themePref);
    applyTheme();
  });
  MQ?.addEventListener?.("change", () => { if (themePref === "auto") applyTheme(); });
  applyTheme();

  function inRing(lat, lon) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [x1, y1] = ring[i], [x2, y2] = ring[j];
      if ((y1 > lat) !== (y2 > lat) && lon < ((x2 - x1) * (lat - y1)) / (y2 - y1) + x1) inside = !inside;
    }
    return inside;
  }

  fetch("/india.geojson").then((r) => r.json()).then((g) => {
    ring = g.geometry.coordinates[0];
    const world = [[-89, -179], [-89, 179], [89, 179], [89, -179]];
    mask = L.polygon([world, ring.map(([lon, lat]) => [lat, lon])], { stroke: false, interactive: false, ...maskStyle() }).addTo(map);
    border = L.polyline(ring.map(([lon, lat]) => [lat, lon]), { weight: 1, interactive: false, ...borderStyle() }).addTo(map);
  }).catch(() => {});

  map.on("click", (e) => {
    const { lat, lng } = e.latlng;
    if (ring && !inRing(lat, lng)) {
      L.popup({ className: "oops" }).setLatLng(e.latlng).setContent("Please choose a point in India").openOn(map);
      return;
    }
    setPoint(lat, lng, "exact point you clicked", []);
  });

  function drawPoint() {
    if (pointMarker) pointMarker.remove();
    pointMarker = null;
    if (!state.point) return;
    pointMarker = L.marker([state.point.lat, state.point.lon], {
      icon: L.divIcon({ className: "you", iconSize: [14, 14] }), keyboard: false, zIndexOffset: 1000,
    }).bindTooltip("Your point", { direction: "top", offset: [0, -8] }).addTo(map);
  }

  function markerStyle(tier, hl) {
    return { radius: hl ? 9 : 6, color: "#fff", weight: hl ? 2.5 : 1.5, fillColor: COLOUR[tier], fillOpacity: 1 };
  }

  function fitPad() {
    return window.innerWidth <= 900 ? { paddingTopLeft: [30, 30], paddingBottomRight: [30, 40] } : { padding: [56, 56] };
  }

  function drawMarkers(fit) {
    resultLayer.clearLayers();
    halo = null;
    state.markers = {};
    const pts = state.point ? [[state.point.lat, state.point.lon]] : [];
    for (const t of state.data?.tiers || []) {
      if (t.tier === "Unverified" && !state.openUnverified) continue;
      for (const r of t.results.slice(0, state.shown[t.tier] || FIRST)) {
        const m = L.circleMarker([r.lat, r.lon], markerStyle(r.tier, false))
          .bindTooltip(`<span class="tt-n">${esc(r.name)}</span><span class="tt-m">${r.tier} · ${esc(r.location_text)}</span>`, { direction: "top", offset: [0, -6] })
          .on("click", () => openDetails(r.id))
          .on("mouseover", () => hlCard(r.id, true))
          .on("mouseout", () => hlCard(r.id, false))
          .addTo(resultLayer);
        state.markers[r.id] = m;
        pts.push([r.lat, r.lon]);
      }
    }
    state.fitPts = pts;
    if (fit && pts.length > 1) map.fitBounds(pts, { ...fitPad(), maxZoom: 14 });
    else if (fit && pts.length === 1) map.setView(pts[0], 11);
    syncHalo();
  }

  function syncHalo() {
    const id = state.hovered || state.selected;
    const r = id && state.byId[id];
    if (!r || !state.markers[id]) { if (halo) { halo.remove(); halo = null; } return; }
    if (!halo) halo = L.circleMarker([r.lat, r.lon], { radius: 18, stroke: false, fillOpacity: 0.22, interactive: false }).addTo(resultLayer);
    halo.setLatLng([r.lat, r.lon]).setStyle({ fillColor: COLOUR[r.tier] });
    halo.bringToBack();
  }

  function hlMarker(id, on) {
    const m = state.markers[id];
    const r = state.byId[id];
    if (on) state.hovered = id; else if (state.hovered === id) state.hovered = null;
    if (m && r) {
      m.setStyle(markerStyle(r.tier, on || state.selected === id));
      if (on || state.selected === id) m.bringToFront();
    }
    syncHalo();
  }
  function hlCard(id, on) {
    document.querySelectorAll(`.card[data-id="${CSS.escape(id)}"]`).forEach((c) => c.classList.toggle("hl", on));
    hlMarker(id, on);
  }

  /* ------------------------------------------------------- services --- */
  const svcInput = $("svc-input"), svcList = $("svc-list");
  let activeIdx = -1, visibleOpts = [];

  function svcByLabel(l) { return state.services.find((s) => s.label === l); }

  function renderList(filter) {
    const f = (filter || "").toLowerCase().trim();
    let html = "", group = null;
    visibleOpts = state.services.filter((s) => !f || s.entry.toLowerCase().includes(f));
    visibleOpts.forEach((s, i) => {
      if (s.group !== group) { group = s.group; html += `<li class="grp" role="presentation">${esc(group)}</li>`; }
      html += `<li class="opt${i === activeIdx ? " active" : ""}" role="option" data-i="${i}">${esc(s.name)}</li>`;
    });
    svcList.innerHTML = html || `<li class="grp">No matching service</li>`;
  }
  function openList() { activeIdx = -1; renderList(svcInput.value === currentName() ? "" : svcInput.value); svcList.hidden = false; svcInput.setAttribute("aria-expanded", "true"); }
  function closeList() { svcList.hidden = true; svcInput.setAttribute("aria-expanded", "false"); svcInput.value = currentName(); }
  function currentName() { return svcByLabel(state.service)?.name || ""; }

  svcInput.addEventListener("focus", () => { svcInput.select(); openList(); });
  svcInput.addEventListener("input", () => { activeIdx = -1; renderList(svcInput.value); svcList.hidden = false; });
  svcInput.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      activeIdx = Math.max(0, Math.min(visibleOpts.length - 1, activeIdx + (e.key === "ArrowDown" ? 1 : -1)));
      renderList(svcInput.value === currentName() ? "" : svcInput.value);
      svcList.querySelector(".opt.active")?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      const s = visibleOpts[activeIdx >= 0 ? activeIdx : 0];
      if (s) chooseService(s.label);
      svcInput.blur(); closeList();
    } else if (e.key === "Escape") { closeList(); svcInput.blur(); }
  });
  svcList.addEventListener("mousedown", (e) => {
    const li = e.target.closest(".opt");
    if (!li) return;
    e.preventDefault();
    chooseService(visibleOpts[+li.dataset.i].label);
    svcInput.blur(); closeList();
  });
  svcInput.addEventListener("blur", () => setTimeout(closeList, 120));

  function setService(label) {
    if (!svcByLabel(label)) return false;
    state.service = label;
    svcInput.value = currentName();
    const note = svcByLabel(label).coverage_note;
    $("svc-note").textContent = note || ""; $("svc-note").hidden = !note;
    $("match-out").querySelectorAll(".pill[data-l]").forEach((p) => {
      const on = p.dataset.l === label;
      p.classList.toggle("on", on);
      p.textContent = svcByLabel(p.dataset.l).name + (on ? " ✓" : "");
    });
    return true;
  }
  function chooseService(label) { if (setService(label)) search(); }

  /* ----------------------------------------------------------- match --- */
  $("need-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("need").value.trim();
    if (!text) return;
    const out = $("match-out"), btn = $("need-form").querySelector("button");
    out.hidden = false; out.innerHTML = `<div class="muted-line">Matching your words to a service…</div>`; busy(btn, true);
    try {
      const m = await api("/api/match", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
      state.emergency = !!m.emergency;
      const usable = (l) => !!svcByLabel(l.label);
      const matched = m.matched && svcByLabel(m.matched) ? m.matched : null;
      let html = "";
      if (m.emergency) html += `<div class="emergency">${ICON.warn} <span>If this is an emergency, call <a href="tel:108">108</a> for an ambulance, or <a href="tel:112">112</a>.</span></div>`;
      if (matched) {
        const alts = (m.alternatives || []).filter(usable);
        html += `<div class="pills"><span class="pill-label">Matched</span><button type="button" class="pill on" data-l="${esc(matched)}">${esc(svcByLabel(matched).name)} ✓</button>`
          + (alts.length ? `<span class="pill-label">or</span>` + alts.map((a) => `<button type="button" class="pill" data-l="${esc(a.label)}">${esc(a.name)}</button>`).join("") : "")
          + `</div>`;
      } else {
        // "Best guess" first; the rest keep the server's least-invasive order.
        const opts0 = (m.options || []).filter(usable);
        const opts = [...opts0.filter((o) => o.fit === "best"), ...opts0.filter((o) => o.fit !== "best")];
        if (opts.length) {
          html += `<div class="opt-q">Which of these fits?</div><div class="opts">${opts.map((o) =>
            `<button type="button" class="opt-card" data-l="${esc(o.label)}"><span class="opt-top"><b>${esc(svcByLabel(o.label).name)}</b>`
            + `<span class="opt-tag ${o.fit === "best" ? "best" : ""}">${o.fit === "best" ? "Best guess" : "Possible"}</span></span>`
            + (o.reason ? `<span class="opt-reason">${esc(o.reason)}</span>` : "") + `</button>`).join("")}</div>`;
        } else if (m.error) {
          html += `<div class="muted-line">Could not match right now (${esc(m.error)}). Pick a service from the list.</div>`;
        } else {
          html += `<div class="muted-line">Pick a service from the list.</div>`;
        }
      }
      html += `<p class="fine">This only matches words to a service; it is not medical advice.</p>`;
      out.innerHTML = html;
      out.querySelectorAll(".pill[data-l]").forEach((c) => c.addEventListener("click", () => { if (c.dataset.l !== state.service) chooseService(c.dataset.l); }));
      out.querySelectorAll(".opt-card").forEach((c) => c.addEventListener("click", () => {
        out.querySelectorAll(".opt-card").forEach((x) => x.classList.toggle("on", x === c));
        chooseService(c.dataset.l);
      }));
      if (matched) chooseService(matched);
      else renderResults();
    } catch (err) {
      out.hidden = true; toast(err.message);
    } finally { busy(btn, false); }
  });

  /* -------------------------------------------------------- location --- */
  async function resolve(q, btn) {
    busy(btn, true);
    try {
      const r = await api(`/api/resolve?${q}`);
      setPoint(r.lat, r.lon, r.origin, r.notes, q.startsWith("pin=") ? decodeURIComponent(q.slice(4)) : null);
    } catch (err) { toast(err.message); } finally { busy(btn, false); }
  }
  $("pin-form").addEventListener("submit", (e) => { e.preventDefault(); const v = $("pin").value.trim(); if (v) resolve(`pin=${encodeURIComponent(v)}`, e.target.querySelector("button")); });
  $("place-form").addEventListener("submit", (e) => { e.preventDefault(); const v = $("place").value.trim(); if (v) resolve(`place=${encodeURIComponent(v)}`, e.target.querySelector("button")); });

  function setPoint(lat, lon, origin, notes, pin) {
    state.point = { lat, lon, pin: pin || null }; state.origin = origin; state.notes = notes || [];
    const p = $("point-out");
    p.hidden = false;
    p.innerHTML = `<div class="point-top"><span class="point-dot" aria-hidden="true"></span>
        <span class="point-text"><b>${esc(origin)}</b> <span class="num">${lat.toFixed(4)}, ${lon.toFixed(4)}</span></span>
        <button class="text-btn" id="clear-pt" type="button">Clear</button></div>`
      + state.notes.map((n) => `<div class="note">${esc(n)}</div>`).join("");
    $("clear-pt").onclick = clearPoint;
    drawPoint();
    search();
  }
  function clearPoint() {
    state.point = null; state.data = null; $("point-out").hidden = true;
    state.fitPts = null;
    drawPoint(); resultLayer.clearLayers(); closeDetails(); renderResults();
    setSearched(false);
  }

  /* ---------------------------------------------------------- search --- */
  let searchSeq = 0;
  async function search() {
    closeDetails();
    if (!state.point || !state.service) { renderResults(); return; }
    const seq = ++searchSeq;
    state.loading = true; renderSkeleton();
    try {
      const d = await api(`/api/search?service=${encodeURIComponent(state.service)}&lat=${state.point.lat}&lon=${state.point.lon}`);
      if (seq !== searchSeq) return;
      state.data = d; state.shown = {}; state.openUnverified = false; state.byId = {};
      d.tiers.forEach((t) => t.results.forEach((r) => { state.byId[r.id] = r; }));
      state.loading = false;
      state.district = null;
      renderResults(); drawMarkers(true);
      setSearched(true);
      if (d.n) loadDistrict(seq, d);
    } catch (err) {
      if (seq !== searchSeq) return;
      state.loading = false; state.data = null;
      toast(err.message);
      $("results").innerHTML = emptyState("Search did not finish", "Something went wrong reaching the data. Try again in a moment.", false);
    }
  }

  function renderSkeleton() {
    const card = `<div class="sk-card"><div class="sk sk-line mid"></div><div class="sk sk-line short"></div><div class="sk sk-quote"></div></div>`;
    $("results").innerHTML = `<div class="sk sk-line short" style="height:16px;margin-top:14px"></div>
      <div class="sk-chips"><div class="sk"></div><div class="sk"></div><div class="sk"></div><div class="sk"></div></div>${card}${card}${card}`;
  }

  function where(s) {
    if (!s.exact_location) return `in ${s.city || "its area"}`;
    return s.distance_km >= 10 ? `${Math.round(s.distance_km)} km` : `${s.distance_km.toFixed(1)} km`;
  }

  /* ------------------------------------------------- district strip --- */
  function ordinal(n) {
    const v = n % 100;
    if (v >= 11 && v <= 13) return `${n}th`;
    return `${n}${{ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"}`;
  }
  function titleCase(s) { return String(s || "").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()); }
  function fmtKm(km) { return km >= 10 ? `${Math.round(km)} km` : `${Number(km).toFixed(1)} km`; }
  async function loadDistrict(seq, d) {
    const p = state.point;
    const qs = `service=${encodeURIComponent(d.service)}&lat=${p.lat}&lon=${p.lon}` + (p.pin ? `&pin=${encodeURIComponent(p.pin)}` : "");
    try {
      const c = await api(`/api/district_context?${qs}`);
      if (seq !== searchSeq || !c || !c.district) return;
      const svc = /^[A-Z][^a-z]/.test(d.service_name) ? d.service_name : d.service_name.charAt(0).toLowerCase() + d.service_name.slice(1);
      const name = titleCase(c.district) + (c.state ? `, ${titleCase(c.state)}` : "");
      let h = `<div class="ds-head"><span class="ds-kicker">District context</span><b>${esc(name)}</b>`
        + (c.district_method === "nearest_pin_centre" ? ` <span class="ds-note">approximate: nearest PIN centre</span>` : "")
        + (c.alias_note ? ` <span class="ds-note">matched via alias${c.nfhs_district ? ` (NFHS: ${esc(c.nfhs_district)})` : ""}</span>` : "") + `</div>`;
      const inds = (c.indicators || []).filter((i) => i && i.value != null);
      if (inds.length) {
        h += `<ul class="ds-ind">${inds.map((i) => {
          const r = i.rank_of_706 ? ` <span class="ds-rank">${ordinal(i.rank_of_706)} ${i.direction === "lower_is_worse" ? "lowest" : "highest"} of 706 districts</span>` : "";
          return `<li><span>${esc(i.label)}</span><span><b class="num">${esc(i.value)}${i.unit === "%" ? "%" : (i.unit ? " " + esc(i.unit) : "")}</b>${r}</span></li>`;
        }).join("")}</ul>`;
      } else if (c.no_indicator_reason) {
        h += `<p class="ds-note">${esc(c.no_indicator_reason)}</p>`;
      }
      const nC = c.n_confirmed_in_district || 0, nLP = (c.n_likely_in_district || 0) + (c.n_possible_in_district || 0);
      const nF = c.n_facilities_in_district || 0;
      const lines = [`${nF.toLocaleString("en-IN")} ${nF === 1 ? "facility" : "facilities"} in this district in our data`];
      lines.push(nC ? `${nC} Confirmed for ${esc(svc)} in this district in our data` : `No Confirmed ${esc(svc)} in this district in our data`);
      if (!nC && nLP) lines.push(`${nLP} ${nLP === 1 ? "facility" : "facilities"} here may offer this service, call to confirm`);
      const ex = c.nearest_confirmed_exact, any = c.nearest_confirmed_any;
      // nearest = nearest Confirmed with a high/good location (same rule as the tier chips)
      if (ex) lines.push(`Nearest Confirmed: ${esc(ex.name)}, <span class="num">${fmtKm(ex.km)}</span>`);
      else lines.push(`No Confirmed ${esc(svc)} with a reliable location found nearby in our data`);
      if (any && (!ex || (any.unique_id !== ex.unique_id && any.km < ex.km)))
        lines.push(`<span class="ds-sub">A closer one at about ${Math.round(any.km)} km has an uncertain location</span>`);
      h += `<ul class="ds-lines">${lines.map((l) => `<li>${l}</li>`).join("")}</ul>`;
      h += `<p class="ds-foot">NFHS-5 (2019–21) district survey. Context only; it does not change the ranking.</p>`;
      state.district = h;
      const el = $("district-strip");
      if (el) { el.innerHTML = h; el.hidden = false; }
    } catch (_) { /* context is optional: leave the strip hidden */ }
  }

  function emptyState(title, text, examples) {
    return `<div class="empty-state"><div class="ill">${ICON.pin}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>`
      + (examples ? `<div class="examples">${EXAMPLES.map((x, i) => `<button type="button" class="pill" data-ex="${i}">${esc(x.name)} <span class="sep">·</span> ${esc(x.where)}</button>`).join("")}</div>` : "")
      + `</div>`;
  }

  function cardHtml(r) {
    const q = r.evidence[0];
    const dist = !r.exact_location ? `<span class="dist unk">exact location unknown</span>`
      : r.location_uncertain ? `<span class="dist uncertain">about ${Math.round(r.distance_km)} km, location uncertain</span>`
      : `<span class="dist">${r.distance_km.toFixed(1)} km</span>`;
    const city = [r.city, r.state].filter(Boolean).join(", ");
    const w = r.warnings;
    return `<div class="card ${r.tier}${state.selected === r.id ? " sel" : ""}" data-id="${esc(r.id)}" tabindex="0" role="button" aria-label="${esc(r.name)}, ${r.tier}">
      <div class="card-top"><div><div class="card-name">${esc(r.name)}</div>
        <div class="card-city">${esc(r.exact_location ? city : `in ${r.city || "this area"}${r.state ? ", " + r.state : ""}`)}</div></div>${dist}</div>
      ${q ? `<div class="quote"><q>${esc(q.sentence)}</q> <span class="src">${esc(q.source_column)}</span></div>` : `<div class="noev">No quoted evidence.</div>`}
      ${w.length ? `<div class="warns"><span class="wchip" title="${esc(w.join("\n"))}">${ICON.warn}<span>${esc(w[0])}</span></span>${w.length > 1 ? `<span class="wchip" title="${esc(w.slice(1).join("\n"))}">+${w.length - 1} more</span>` : ""}</div>` : ""}
    </div>`;
  }

  function renderResults() {
    const box = $("results");
    if (state.loading) return;
    if (!state.point) {
      box.innerHTML = emptyState("Choose a location", "Enter a PIN code or place, or click the map. Or try one of these:", true);
      box.querySelectorAll("[data-ex]").forEach((b) => b.addEventListener("click", () => {
        const x = EXAMPLES[+b.dataset.ex];
        setService(x.label);
        if (x.q.startsWith("pin=")) { $("pin").value = x.where; $("place").value = ""; }
        else { $("place").value = x.where; $("pin").value = ""; }
        resolve(x.q, b);
      }));
      return;
    }
    const d = state.data;
    if (!d) return;
    let html = "";
    if (d.is_sample) html += `<div class="banner sample">SAMPLE DATA: not real recommendations. Real facilities and quoted sentences, placeholder tiers.</div>`;
    if (state.emergency) html += `<div class="emergency" style="margin:8px 0 4px">${ICON.warn} <span>If this is an emergency, call <a href="tel:108">108</a> for an ambulance, or <a href="tel:112">112</a>.</span></div>`;
    html += `<div class="res-head"><h2>${esc(d.service_name)}</h2>${d.n ? `<span class="count num">${d.n} ${d.n === 1 ? "facility" : "facilities"}</span>` : ""}</div>`;
    if (!d.n) {
      box.innerHTML = html + emptyState(`No facility has evidence for ${d.service_name}.`, "Try a related service or another location.", false);
      return;
    }
    const byTier = Object.fromEntries(d.summary.map((x) => [x.tier, x]));
    html += `<div class="summary">${TIERS.map((t) => {
      const x = byTier[t];
      if (!x) return `<div class="tchip none"><span class="tname"><span class="dot ${t}"></span>${t}</span><span class="tdist unk">none nearby</span></div>`;
      return `<button type="button" class="tchip" data-jump="${t}" title="Nearest ${t}: ${esc(x.name)}"><span class="tname"><span class="dot ${t}"></span>${t}</span>`
        + (x.trusted ? `<span class="tdist num">nearest ${esc(where(x))}</span>` : `<span class="tdist unk">no facility with a reliable location</span>`)
        + (x.closer_uncertain_km != null ? `<span class="tsub">A closer one at about ${x.closer_uncertain_km} km has an uncertain location</span>` : "") + `</button>`;
    }).join("")}</div>`;
    html += state.district ? `<div id="district-strip" class="district">${state.district}</div>`
      : `<div id="district-strip" class="district" hidden></div>`;  // district context strip (NFHS-5)
    html += `<p class="meta">Within each tier, facilities with an exact location come first, then by distance. Column-shifted records and facilities with no usable position are left out. Query ${d.query_s}s.</p>`;
    for (const t of d.tiers) {
      if (!t.count) continue;
      const open = t.tier !== "Unverified" || state.openUnverified;
      const n = state.shown[t.tier] || FIRST;
      html += `<section class="tier" id="tier-${t.tier}"><div class="tier-head"><span class="dot ${t.tier}"></span><h3>${t.tier}</h3><span class="tcount num">${t.count}${t.capped ? "+" : ""}</span>`
        + (t.tier === "Unverified" ? `<button class="btn ghost small" data-toggle>${open ? "Hide unverified" : "Show unverified"}</button>` : "") + `</div>`
        + `<p class="tier-meaning">${esc(t.meaning)}</p>`;
      if (open) {
        html += t.results.slice(0, n).map(cardHtml).join("");
        if (t.count > n) html += `<div class="more-row"><button class="btn ghost small" data-more="${t.tier}">Show ${Math.min(STEP, t.count - n)} more</button></div>`;
        else if (t.capped) html += `<p class="meta">Showing the nearest ${t.count}.</p>`;
      }
      html += `</section>`;
    }
    box.innerHTML = html;
    box.querySelectorAll(".card").forEach((c) => {
      const id = c.dataset.id;
      c.addEventListener("click", () => openDetails(id));
      c.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDetails(id); } });
      c.addEventListener("mouseenter", () => hlMarker(id, true));
      c.addEventListener("mouseleave", () => hlMarker(id, false));
    });
    box.querySelectorAll("[data-more]").forEach((b) => b.addEventListener("click", () => {
      state.shown[b.dataset.more] = (state.shown[b.dataset.more] || FIRST) + STEP; renderResults(); drawMarkers(false);
    }));
    box.querySelector("[data-toggle]")?.addEventListener("click", () => {
      state.openUnverified = !state.openUnverified; renderResults(); drawMarkers(false);
    });
    box.querySelectorAll("[data-jump]").forEach((b) => b.addEventListener("click", () => {
      const t = b.dataset.jump;
      if (t === "Unverified" && !state.openUnverified) { state.openUnverified = true; renderResults(); drawMarkers(false); }
      const sec = $(`tier-${t}`), sc = $("panel-scroll");
      if (sec) sc.scrollTo({ top: sec.offsetTop - 4 });
    }));
  }

  /* --------------------------------------------------------- details --- */
  const WHY_WARN = /([1-9]\d*% of its sentences were flagged|mostly|rarely|approximate|unknown|suspect|unverified|disagree|only weak|could not|not exact|no statement|centre)/i;
  function openDetails(id) {
    const r = state.byId[id];
    if (!r) return;
    if (r.tier === "Unverified" && !state.openUnverified) { state.openUnverified = true; renderResults(); drawMarkers(false); }
    const prev = state.selected; state.selected = id;
    if (prev) hlMarker(prev, false);
    hlMarker(id, true);
    document.querySelectorAll(".card.sel").forEach((c) => c.classList.remove("sel"));
    document.querySelectorAll(`.card[data-id="${CSS.escape(id)}"]`).forEach((c) => c.classList.add("sel"));
    map.setView([r.lat, r.lon], Math.max(map.getZoom(), 13));
    const d = r.details;
    const tel = d.phone ? d.phone.replace(/[^\d+]/g, "") : "";
    const dist = r.exact_location && r.location_uncertain ? `<span class="dist uncertain">about ${Math.round(r.distance_km)} km, location uncertain</span>`
      : r.exact_location ? `<span class="dist num">${r.distance_km.toFixed(2)} km away</span>` : `<span class="dist unk">in ${esc(r.city || "this area")}, exact location unknown</span>`;
    const rowsDl = [
      ["Address", d.address && esc(d.address)],
      ["Phone", d.phone && `<a href="tel:${esc(tel)}">${esc(d.phone)}</a>`],
      ["Website", d.website && `<a href="${esc(d.website)}" target="_blank" rel="noopener">${esc(d.domain)}</a>`],
      ["Type", esc(d.type)],
      ["Departments", d.departments && esc(d.departments)],
      ["Location", esc(d.location_confidence)],
    ].filter(([, v]) => v).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
    const actions = [
      d.phone && `<a class="action" href="tel:${esc(tel)}">${ICON.phone}Call<small>${esc(d.phone)}</small></a>`,
      `<a class="action primary" href="${esc(d.directions_url)}" target="_blank" rel="noopener">${ICON.nav}Directions${d.directions_approximate ? "<small>approximate: city or postcode centre</small>" : ""}</a>`,
      d.website && `<a class="action" href="${esc(d.website)}" target="_blank" rel="noopener">${ICON.web}Website<small>${esc(d.domain)}</small></a>`,
    ].filter(Boolean).join("");
    const dr = $("drawer");
    dr.innerHTML = `<div class="drawer-head">
        <button class="back" id="back" type="button">${ICON.back} Back to results</button>
        <h2>${esc(r.name)}</h2>
        <div class="drawer-meta"><span class="badge ${r.tier}"><span class="dot ${r.tier}"></span>${r.tier}</span>${dist}<span>${esc([r.city, r.state].filter(Boolean).join(", "))}</span></div>
      </div>
      <div class="drawer-body">
        <div class="actions">${actions}</div>
        ${r.warnings.length ? `<div class="sect"><h4>Warnings</h4><ul class="wlist">${r.warnings.map((w) => `<li>${ICON.warn}<span>${esc(w)}</span></li>`).join("")}</ul></div>` : ""}
        <div class="sect"><h4>Evidence <span class="sub-h">· quoted from the facility's own text</span></h4>
          ${r.evidence.length ? r.evidence.map((e) => `<blockquote class="ev">“${esc(e.sentence)}”<br><span class="src">source column: ${esc(e.source_column)}</span></blockquote>`).join("") : `<p class="noev">No quoted evidence.</p>`}</div>
        <div class="sect"><h4>Why this result</h4><ul class="check">${r.why.map((w) => {
          const bad = WHY_WARN.test(w);
          return `<li><span class="ic ${bad ? "wa" : "ok"}" aria-label="${bad ? "caution" : "ok"}">${bad ? "!" : "✓"}</span><span>${esc(w)}</span></li>`;
        }).join("")}</ul></div>
        <div class="sect"><h4>Details</h4><dl class="dl">${rowsDl}</dl></div>
      </div>`;
    dr.classList.add("open"); dr.setAttribute("aria-hidden", "false"); dr.scrollTop = 0;
    applyLayout();
    $("back").onclick = closeDetails;
    $("back").focus({ preventScroll: true });
  }
  function closeDetails() {
    const dr = $("drawer");
    const wasOpen = dr.classList.contains("open");
    dr.classList.remove("open"); dr.setAttribute("aria-hidden", "true");
    if (wasOpen) applyLayout();
    const prev = state.selected; state.selected = null;
    if (prev) hlMarker(prev, false);
    document.querySelectorAll(".card.sel").forEach((c) => c.classList.remove("sel"));
    if (wasOpen && prev) document.querySelector(`.card[data-id="${CSS.escape(prev)}"]`)?.focus({ preventScroll: true });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { if (!$("modal").hidden) $("modal").hidden = true; else closeDetails(); }
  });

  /* ----------------------------------------------------------- modal --- */
  const FUNNEL = [
    ["facilities", "Facilities in the dataset"],
    ["sentences_read", "Sentences read about them"],
    ["distinct_sentences", "Distinct sentences"],
    ["distinct_sentences_tagged", "Distinct sentences classified so far"],
    ["service_claim_sentences", "Distinct sentences that say a facility offers a service"],
    ["facilities_audited", "Records checked for text from other hospitals"],
    ["records_mixed", "Records that appear mixed with another hospital's text (flagged sentences never quoted)"],
  ];
  let statsLoaded = false;
  $("how-btn").addEventListener("click", async () => {
    $("modal").hidden = false; $("modal-close").focus();
    if (statsLoaded) return;
    try {
      const s = await api("/api/stats");
      const fmt = (v) => (v == null ? "?" : Number(v).toLocaleString("en-IN"));
      const known = new Set(FUNNEL.map(([k]) => k));
      const extra = Object.keys(s.funnel).filter((k) => !known.has(k)).map((k) => [k, k.replace(/_/g, " ")]);
      $("modal-body").innerHTML = `
        <p>Every result is traced to sentences in the facility's own record. Each sentence was classified for which service it describes and how strongly. Records that mix in another hospital's text were audited, and their flagged sentences are never quoted.</p>
        <ul class="funnel">${[...FUNNEL, ...extra].filter(([k]) => k in s.funnel).map(([k, l]) => `<li><span>${esc(l)}</span><b>${fmt(s.funnel[k])}</b></li>`).join("")}</ul>
        <dl class="rules">
          <dt><span class="badge Confirmed"><span class="dot Confirmed"></span>Confirmed</span></dt><dd>A detailed statement (numbers, units, beds) plus a matching department, a second statement, or a usual fit for the facility type.</dd>
          <dt><span class="badge Likely"><span class="dot Likely"></span>Likely</span></dt><dd>At least one detailed or plain statement.</dd>
          <dt><span class="badge Possible"><span class="dot Possible"></span>Possible</span></dt><dd>No statement, but the matching department plus a related service.</dd>
          <dt><span class="badge Unverified"><span class="dot Unverified"></span>Unverified</span></dt><dd>Only weak mentions, mostly another hospital's text, or a facility type that rarely offers the service.</dd>
        </dl>
        <p>Within each tier, facilities with an exact location come first, then by distance. Facilities placed only at a city or postcode centre show no distance.</p>
        ${s.validation.line ? `<div class="valid">${esc(s.validation.line)}</div>` : ""}
        ${s.build_ts ? `<p class="fine">Numbers as of ${esc(s.build_ts.slice(0, 16).replace("T", " "))} UTC.</p>` : ""}`;
      statsLoaded = true;
    } catch (err) { $("modal-body").textContent = err.message; }
  });
  $("modal-close").addEventListener("click", () => { $("modal").hidden = true; });
  $("modal").addEventListener("click", (e) => { if (e.target.id === "modal") $("modal").hidden = true; });

  /* ----------------------------------------------------------- split --- */
  const layout = document.querySelector(".layout"), divider = $("divider");
  const MIN_PANEL = 360, MIN_MAP = 280;
  const isMobile = () => window.innerWidth <= 900;
  let userW = +store.get("vf-panel-w") || null, mapCollapsed = false, layoutTimer = 0;
  const searched = () => layout.classList.contains("searched");
  const drawerOpen = () => $("drawer").classList.contains("open");
  const clampW = (w) => Math.max(MIN_PANEL, Math.min(window.innerWidth - MIN_MAP, w));
  function targetW() {
    const vw = window.innerWidth;
    // A width the user dragged wins in every state (empty, results, drawer); otherwise the
    // panel starts at its default and widens after a search and again with the drawer open.
    if (mapCollapsed && searched()) return clampW(vw - MIN_MAP);
    if (userW) return clampW(userW);
    if (!searched()) return clampW(vw >= 1400 ? 460 : 440);
    return clampW(Math.round(vw * (drawerOpen() ? 0.65 : 0.55)));
  }
  function refit() {
    const r = state.selected && state.byId[state.selected];
    if (r) map.panTo([r.lat, r.lon], { animate: false });
    else if (state.fitPts?.length > 1) map.fitBounds(state.fitPts, { ...fitPad(), maxZoom: 14, animate: false });
    else if (state.fitPts?.length === 1) map.setView(state.fitPts[0], map.getZoom(), { animate: false });
  }
  function afterResize(delay) {
    clearTimeout(layoutTimer);
    layoutTimer = setTimeout(() => { map.invalidateSize({ pan: false }); refit(); }, delay);
  }
  function applyLayout(animate = true) {
    if (isMobile()) layout.style.removeProperty("--pw");
    else layout.style.setProperty("--pw", `${targetW()}px`);
    const t = $("map-toggle");
    t.hidden = !searched();
    t.innerHTML = mapCollapsed ? "map &#10217;" : "&#10216; map";
    t.setAttribute("aria-label", mapCollapsed ? "Bring the map back" : "Make the map smaller");
    $("map-expand").textContent = layout.classList.contains("map-open") ? "Shrink map" : "Expand map";
    afterResize(animate ? 230 : 0);
  }
  function setSearched(on) {
    layout.classList.toggle("searched", on);
    if (!on) { layout.classList.remove("map-open"); mapCollapsed = false; }
    applyLayout();
  }

  let dragging = false, rafId = 0;
  divider.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".map-toggle") || isMobile()) return;
    dragging = true; divider.setPointerCapture(e.pointerId);
    layout.classList.add("dragging"); e.preventDefault();
  });
  divider.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const w = clampW(window.innerWidth - e.clientX);
    layout.style.setProperty("--pw", `${w}px`);
    cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(() => map.invalidateSize({ pan: false }));
  });
  const endDrag = (e) => {
    if (!dragging) return;
    dragging = false; layout.classList.remove("dragging");
    try { divider.releasePointerCapture(e.pointerId); } catch (_) { /* already released */ }
    userW = parseInt(getComputedStyle(layout).getPropertyValue("--pw"), 10) || null;
    store.set("vf-panel-w", userW ? String(userW) : null);
    mapCollapsed = false; applyLayout(false);
  };
  divider.addEventListener("pointerup", endDrag);
  divider.addEventListener("pointercancel", endDrag);
  divider.addEventListener("dblclick", (e) => {
    if (e.target.closest(".map-toggle")) return;
    userW = null; store.set("vf-panel-w", null); mapCollapsed = false; applyLayout();
  });
  divider.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const cur = parseInt(getComputedStyle($("panel")).width, 10);
    userW = clampW(cur + (e.key === "ArrowLeft" ? 32 : -32));
    store.set("vf-panel-w", String(userW));
    layout.style.setProperty("--pw", `${userW}px`); afterResize(230);
  });
  $("map-toggle").addEventListener("pointerdown", (e) => e.stopPropagation());
  $("map-toggle").addEventListener("click", () => { mapCollapsed = !mapCollapsed; applyLayout(); });
  $("map-expand").addEventListener("click", () => { layout.classList.toggle("map-open"); applyLayout(); });
  window.addEventListener("resize", () => applyLayout(false));

  /* ------------------------------------------------------------ init --- */
  applyLayout(false);
  renderResults();
  api("/api/services").then((d) => {
    state.services = d.services;
    setService(svcByLabel(d.default) ? d.default : d.services[0]?.label);
    renderResults();
  }).catch((err) => msg(`Could not load services: ${err.message}`));
})();
