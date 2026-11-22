import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import { useStore } from "../App.jsx";
import { COLOUR, fmtKm, visibleResults } from "../api.js";

// Muted basemap. CARTO Positron answers "API key required", so Esri's keyless gray canvas is used.
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/";
const ESRI_OPTS = { maxNativeZoom: 16, maxZoom: 18, attribution: "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors" };
const maskStyle = (dark) => (dark ? { fillColor: "#05080c", fillOpacity: 0.62 } : { fillColor: "#eef0f3", fillOpacity: 0.72 });
const borderStyle = (dark) => ({ color: dark ? "#4a5565" : "#b9c0ca" });
const markerStyle = (tier, hl) => ({ radius: hl ? 9 : 6, color: "#fff", weight: hl ? 2.5 : 1.5, fillColor: COLOUR[tier], fillOpacity: 1 });
const fitPad = () => (window.innerWidth <= 900 ? { paddingTopLeft: [30, 30], paddingBottomRight: [30, 40] } : { padding: [56, 56] });
const hasLoc = (r) => r && r.exact_location && Number.isFinite(r.lat) && Number.isFinite(r.lon);
const escHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function inRing(ring, lat, lon) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[j];
    if ((y1 > lat) !== (y2 > lat) && lon < ((x2 - x1) * (lat - y1)) / (y2 - y1) + x1) inside = !inside;
  }
  return inside;
}

export default function MapView() {
  const s = useStore();
  const { point, data, shown, openUnverified, selectedId, hoveredId, isDark, byId, mapApi } = s;
  const el = useRef(null);
  const m = useRef({});            // leaflet objects
  const handlers = useRef({});     // latest callbacks for leaflet events
  handlers.current = { pickPoint: s.pickPoint, openDetails: s.openDetails, setHoveredId: s.setHoveredId };
  const visible = useMemo(() => visibleResults(data, shown, openUnverified), [data, shown, openUnverified]);
  const sel = useRef({ selectedId, byId, point });
  sel.current = { selectedId, byId, point };

  /* ---- create the map once ---- */
  useEffect(() => {
    const map = L.map(el.current, {
      center: [22.5, 82.5], zoom: 5, minZoom: 4, zoomControl: false,
      maxBounds: [[6, 68], [37.5, 98]], maxBoundsViscosity: 1.0,
    });
    L.control.zoom({ position: "topleft" }).addTo(map);
    const shade = document.documentElement.dataset.theme === "dark" ? "Dark" : "Light";
    const base = L.tileLayer(`${ESRI}World_${shade}_Gray_Base/MapServer/tile/{z}/{y}/{x}`, ESRI_OPTS).addTo(map);
    map.createPane("labels");
    map.getPane("labels").style.zIndex = 350;
    map.getPane("labels").style.pointerEvents = "none";
    const labels = L.tileLayer(`${ESRI}World_${shade}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, { ...ESRI_OPTS, attribution: "", pane: "labels" }).addTo(map);
    // Transparent label tiles: hide leftover zoom levels once the current one has loaded.
    labels.on("load", () => {
      const z = String(labels._tileZoom);
      labels.getContainer()?.querySelectorAll(".leaflet-tile-container").forEach((c) => {
        const lvl = Object.entries(labels._levels || {}).find(([, l]) => l.el === c);
        c.style.display = lvl && lvl[0] !== z ? "none" : "";
      });
    });
    const results = L.layerGroup().addTo(map);
    m.current = { map, base, labels, results, ring: null, mask: null, border: null, markers: {}, halo: null, point: null, fitPts: null };

    fetch("/india.geojson").then((r) => r.json()).then((g) => {
      const ring = g.geometry.coordinates[0];
      const world = [[-89, -179], [-89, 179], [89, 179], [89, -179]];
      const dark = document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && window.matchMedia?.("(prefers-color-scheme: dark)").matches);
      m.current.ring = ring;
      m.current.mask = L.polygon([world, ring.map(([lon, lat]) => [lat, lon])], { stroke: false, interactive: false, ...maskStyle(dark) }).addTo(map);
      m.current.border = L.polyline(ring.map(([lon, lat]) => [lat, lon]), { weight: 1, interactive: false, ...borderStyle(dark) }).addTo(map);
    }).catch(() => {});

    map.on("click", (e) => {
      const { lat, lng } = e.latlng;
      if (m.current.ring && !inRing(m.current.ring, lat, lng)) {
        L.popup({ className: "oops" }).setLatLng(e.latlng).setContent("Please choose a point in India").openOn(map);
        return;
      }
      handlers.current.pickPoint(lat, lng);
    });

    mapApi.current = {
      invalidate: () => map.invalidateSize({ pan: false }),
      refit: () => {
        const { selectedId: id, byId: b } = sel.current;
        const r = id && b[id];
        const pts = m.current.fitPts;
        const p = sel.current.point;
        if (r && p && hasLoc(r)) map.fitBounds([[p.lat, p.lon], [r.lat, r.lon]], { ...fitPad(), maxZoom: 13, animate: false });
        else if (r) map.panTo([r.lat, r.lon], { animate: false });
        else if (pts?.length > 1) map.fitBounds(pts, { ...fitPad(), maxZoom: 14, animate: false });
        else if (pts?.length === 1) map.setView(pts[0], map.getZoom(), { animate: false });
      },
    };
    return () => { map.remove(); mapApi.current = null; };
  }, [mapApi]);

  /* ---- theme: basemap + mask ---- */
  useEffect(() => {
    const { base, labels, mask, border } = m.current;
    const sh = isDark ? "Dark" : "Light";
    base?.setUrl(`${ESRI}World_${sh}_Gray_Base/MapServer/tile/{z}/{y}/{x}`);
    labels?.setUrl(`${ESRI}World_${sh}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`);
    mask?.setStyle(maskStyle(isDark)); border?.setStyle(borderStyle(isDark));
  }, [isDark]);

  /* ---- search point ---- */
  useEffect(() => {
    const o = m.current;
    o.point?.remove(); o.point = null;
    if (!point) { o.results.clearLayers(); o.markers = {}; o.halo = null; o.fitPts = null; return; }
    o.point = L.marker([point.lat, point.lon], { icon: L.divIcon({ className: "you", iconSize: [14, 14] }), keyboard: false, zIndexOffset: 1000 })
      .bindTooltip("Your point", { direction: "top", offset: [0, -8] }).addTo(o.map);
  }, [point]);

  /* ---- result markers; fit when a new result set arrives ---- */
  const lastData = useRef(null);
  useEffect(() => {
    const o = m.current;
    o.results.clearLayers(); o.markers = {}; o.halo = null;
    const pts = point ? [[point.lat, point.lon]] : [];
    for (const r of visible) {
      const mk = L.circleMarker([r.lat, r.lon], markerStyle(r.tier, false))
        .bindTooltip(`<span class="tt-n">${escHtml(r.name)}</span><span class="tt-m">${r.tier} · ${escHtml(r.location_text)}</span>`, { direction: "top", offset: [0, -6] })
        .on("click", () => handlers.current.openDetails(r.id))
        .on("mouseover", () => handlers.current.setHoveredId(r.id))
        .on("mouseout", () => handlers.current.setHoveredId((h) => (h === r.id ? null : h)))
        .addTo(o.results);
      o.markers[r.id] = mk;
      pts.push([r.lat, r.lon]);
    }
    o.fitPts = data ? pts : null;
    if (data && data !== lastData.current) {
      lastData.current = data;
      if (pts.length > 1) o.map.fitBounds(pts, { ...fitPad(), maxZoom: 14 });
      else if (pts.length === 1) o.map.setView(pts[0], 11);
    }
  }, [visible, data, point]);

  /* ---- highlight + halo ---- */
  useEffect(() => {
    const o = m.current;
    for (const [id, mk] of Object.entries(o.markers)) {
      const r = byId[id];
      if (!r) continue;
      const on = id === hoveredId || id === selectedId;
      mk.setStyle(markerStyle(r.tier, on));
      if (on) mk.bringToFront();
    }
    const id = hoveredId || selectedId;
    const r = id && byId[id];
    if (!r || !o.markers[id]) { o.halo?.remove(); o.halo = null; return; }
    if (!o.halo) o.halo = L.circleMarker([r.lat, r.lon], { radius: 18, stroke: false, fillOpacity: 0.22, interactive: false }).addTo(o.results);
    o.halo.setLatLng([r.lat, r.lon]).setStyle({ fillColor: COLOUR[r.tier] });
    o.halo.bringToBack();
  }, [hoveredId, selectedId, byId, visible]);

  /* ---- zoom to the selected facility; arrow from the search point to it ---- */
  useEffect(() => {
    const o = m.current;
    o.arrow?.remove(); o.arrow = null;
    const r = selectedId && byId[selectedId];
    if (!r) return;
    if (!point || !hasLoc(r)) {
      if (Number.isFinite(r.lat) && Number.isFinite(r.lon)) o.map.setView([r.lat, r.lon], Math.max(o.map.getZoom(), 13));
      return;
    }
    const a = [point.lat, point.lon], b = [r.lat, r.lon], col = COLOUR[r.tier] || "#0f6e6e";
    const casing = L.polyline([a, b], { color: isDark ? "#0b0f14" : "#ffffff", opacity: 0.75, weight: 6, interactive: false });
    const line = L.polyline([a, b], { color: col, weight: 3, dashArray: "8 7", lineCap: "round", interactive: false });
    const pa = o.map.project(a, 10), pb = o.map.project(b, 10);   // screen bearing is zoom-invariant in Web Mercator
    const deg = (Math.atan2(pb.y - pa.y, pb.x - pa.x) * 180) / Math.PI;
    const head = L.marker(b, { interactive: false, keyboard: false, zIndexOffset: 500, icon: L.divIcon({
      className: "arrow-head", iconSize: [0, 0],
      html: `<svg width="16" height="14" viewBox="0 0 16 14" style="transform:rotate(${deg}deg) translate(-27px,-7px)"><path d="M0 0 L16 7 L0 14 Z" fill="${col}" stroke="${isDark ? "#0b0f14" : "#fff"}" stroke-width="1.5" stroke-linejoin="round"/></svg>`,
    }) });
    const km = Number(r.distance_km);
    const label = Number.isFinite(km) ? L.marker(o.map.unproject(pa.add(pb).divideBy(2), 10), { interactive: false, keyboard: false, zIndexOffset: 400, icon: L.divIcon({
      className: "arrow-label", iconSize: [0, 0],
      html: `<span style="border-color:${col}">${r.location_uncertain ? "about " : ""}${fmtKm(km)}</span>`,
    }) }) : null;
    o.arrow = L.layerGroup([casing, line, head, ...(label ? [label] : [])]).addTo(o.map);
    line.bringToBack(); casing.bringToBack(); o.mask?.bringToBack();
    o.map.fitBounds([a, b], { ...fitPad(), maxZoom: 13 });
  }, [selectedId, byId, point, isDark]);

  return <div id="map" ref={el} aria-label="Map of India. Click to choose a search point." />;
}
