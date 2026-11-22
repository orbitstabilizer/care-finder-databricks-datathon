import { useCallback, useEffect, useRef, useState } from "react";
import { useStore } from "../App.jsx";
import { store } from "../api.js";

const MIN_PANEL = 360, MIN_MAP = 280;
const isMobile = () => window.innerWidth <= 900;
const clampW = (w) => Math.max(MIN_PANEL, Math.min(window.innerWidth - MIN_MAP, w));

/** Map | divider | panel. The divider drags in every state; a dragged width wins over the automatic
 *  widening (55% after a search, 65% with the drawer open) and survives search, drawer and clear. */
export default function SplitLayout({ map, panel }) {
  const { searched, selectedId, mapApi } = useStore();
  const drawerOpen = selectedId != null;
  const [userW, setUserW] = useState(() => +store.get("vf-panel-w") || null);
  const [mapCollapsed, setMapCollapsed] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);       // mobile: map expanded back to 40vh
  const [dragW, setDragW] = useState(null);
  const [vw, setVw] = useState(window.innerWidth);
  const dragging = useRef(false);
  const timer = useRef(0), raf = useRef(0);

  useEffect(() => { if (!searched) { setMapCollapsed(false); setMapOpen(false); } }, [searched]);
  useEffect(() => {
    const f = () => setVw(window.innerWidth);
    window.addEventListener("resize", f);
    return () => window.removeEventListener("resize", f);
  }, []);

  let w;
  if (mapCollapsed && searched) w = clampW(vw - MIN_MAP);
  else if (userW) w = clampW(userW);
  else if (!searched) w = clampW(vw >= 1400 ? 460 : 440);
  else w = clampW(Math.round(vw * (drawerOpen ? 0.65 : 0.55)));
  if (dragW != null) w = dragW;

  const afterResize = useCallback((delay) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => { mapApi.current?.invalidate(); mapApi.current?.refit(); }, delay);
  }, [mapApi]);
  // Every width change animates for 200 ms; then resize the map and re-fit it to the results.
  useEffect(() => { if (dragW == null) afterResize(230); }, [w, mapOpen, dragW, afterResize]);

  const onDown = (e) => {
    if (e.target.closest(".map-toggle") || isMobile()) return;
    dragging.current = true; e.currentTarget.setPointerCapture(e.pointerId); e.preventDefault();
    setDragW(w);
  };
  const onMove = (e) => {
    if (!dragging.current) return;
    setDragW(clampW(window.innerWidth - e.clientX));
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() => mapApi.current?.invalidate());
  };
  const onUp = (e) => {
    if (!dragging.current) return;
    dragging.current = false;
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch (_) { /* released */ }
    const nw = dragW;
    setUserW(nw); store.set("vf-panel-w", nw ? String(nw) : null);
    setMapCollapsed(false); setDragW(null); afterResize(0);
  };
  const onDbl = (e) => {
    if (e.target.closest(".map-toggle")) return;
    setUserW(null); store.set("vf-panel-w", null); setMapCollapsed(false);
  };
  const onKey = (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const nw = clampW(w + (e.key === "ArrowLeft" ? 32 : -32));
    setUserW(nw); store.set("vf-panel-w", String(nw)); setMapCollapsed(false);
  };

  const cls = ["layout", searched && "searched", mapOpen && "map-open", dragW != null && "dragging"].filter(Boolean).join(" ");
  return (
    <div className={cls} style={isMobile() ? undefined : { "--pw": `${w}px` }}>
      {map}
      {searched && (
        <button className="map-expand" type="button" onClick={() => setMapOpen((o) => !o)}>{mapOpen ? "Shrink map" : "Expand map"}</button>
      )}
      <div className="divider" id="divider" role="separator" aria-orientation="vertical" tabIndex={0}
        aria-label="Resize map and panel. Double-click to reset."
        onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
        onDoubleClick={onDbl} onKeyDown={onKey}>
        <span className="grip" aria-hidden="true" />
        {searched && (
          <button className="map-toggle" type="button" onPointerDown={(e) => e.stopPropagation()}
            onClick={() => setMapCollapsed((c) => !c)} aria-label={mapCollapsed ? "Bring the map back" : "Make the map smaller"}>
            {mapCollapsed ? "map ⟩" : "⟨ map"}
          </button>
        )}
      </div>
      {panel}
    </div>
  );
}
