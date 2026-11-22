import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, store } from "./api.js";
import SplitLayout from "./components/SplitLayout.jsx";
import MapView from "./components/MapView.jsx";
import Panel from "./components/Panel.jsx";
import HowItWorksModal from "./components/HowItWorksModal.jsx";
import Toasts from "./components/Toasts.jsx";

const Store = createContext(null);
export const useStore = () => useContext(Store);

const MQ = typeof window !== "undefined" ? window.matchMedia?.("(prefers-color-scheme: dark)") : null;

/** The single store: all app state lives here and is shared through context. */
export default function App() {
  const [services, setServices] = useState([]);
  const [service, setService] = useState(null);
  const [point, setPoint] = useState(null);           // {lat, lon, origin, notes, pin}
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState(false);
  const [searched, setSearched] = useState(false);
  const [shown, setShown] = useState({});
  const [openUnverified, setOpenUnverified] = useState(false);
  const [emergency, setEmergency] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [hoveredId, setHoveredId] = useState(null);
  const [district, setDistrict] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [pinText, setPinText] = useState("");
  const [placeText, setPlaceText] = useState("");
  const [themePref, setThemePref] = useState(() => (["light", "dark"].includes(store.get("vf-theme")) ? store.get("vf-theme") : "auto"));
  const [systemDark, setSystemDark] = useState(() => !!MQ?.matches);
  const mapApi = useRef(null);                          // {invalidate(), refit()} set by MapView
  const seq = useRef(0);

  /* ---- theme ---- */
  const isDark = themePref === "dark" || (themePref === "auto" && systemDark);
  useEffect(() => {
    const root = document.documentElement;
    if (themePref === "auto") delete root.dataset.theme; else root.dataset.theme = themePref;
    store.set("vf-theme", themePref === "auto" ? null : themePref);
  }, [themePref]);
  useEffect(() => {
    const f = () => setSystemDark(!!MQ?.matches);
    MQ?.addEventListener?.("change", f);
    return () => MQ?.removeEventListener?.("change", f);
  }, []);

  /* ---- toasts ---- */
  const toast = useCallback((text, kind = "err") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);

  /* ---- services ---- */
  const svcByLabel = useCallback((l) => services.find((s) => s.label === l), [services]);
  useEffect(() => {
    api("/api/services").then((d) => {
      setServices(d.services);
      setService(d.services.some((s) => s.label === d.default) ? d.default : d.services[0]?.label);
    }).catch((err) => toast(`Could not load services: ${err.message}`));
  }, [toast]);

  const byId = useMemo(() => {
    const m = {};
    data?.tiers.forEach((t) => [...t.results, ...(t.city_block || [])].forEach((r) => { m[r.id] = r; }));
    return m;
  }, [data]);

  /* ---- district context (optional; hidden on any failure) ---- */
  const loadDistrict = useCallback(async (mySeq, d, p) => {
    const qs = `service=${encodeURIComponent(d.service)}&lat=${p.lat}&lon=${p.lon}` + (p.pin ? `&pin=${encodeURIComponent(p.pin)}` : "");
    try {
      const c = await api(`/api/district_context?${qs}`);
      if (mySeq === seq.current && c && c.district) setDistrict(c);
    } catch (_) { /* context is optional */ }
  }, []);

  /* ---- search: runs whenever service or point changes ---- */
  const [searchNonce, setSearchNonce] = useState(0);
  useEffect(() => {
    setSelectedId(null);
    if (!point || !service) { setData(null); setLoading(false); return; }
    const mySeq = ++seq.current;
    setLoading(true); setSearchError(false); setDistrict(null);
    api(`/api/search?service=${encodeURIComponent(service)}&lat=${point.lat}&lon=${point.lon}`)
      .then((d) => {
        if (mySeq !== seq.current) return;
        setData(d); setShown({}); setOpenUnverified(false); setLoading(false); setSearched(true);
        if (d.n) loadDistrict(mySeq, d, point);
      })
      .catch((err) => {
        if (mySeq !== seq.current) return;
        setLoading(false); setData(null); setSearchError(true); toast(err.message);
      });
  }, [service, point, searchNonce, loadDistrict, toast]);

  const chooseService = useCallback((label) => {
    if (!services.some((s) => s.label === label)) return;
    if (label === service) setSearchNonce((n) => n + 1); else setService(label);
  }, [services, service]);

  const resolve = useCallback(async (q) => {
    try {
      const r = await api(`/api/resolve?${q}`);
      const pin = q.startsWith("pin=") ? decodeURIComponent(q.slice(4)) : null;
      setPoint({ lat: r.lat, lon: r.lon, origin: r.origin, notes: r.notes || [], pin,
        matched: r.matched || null, alternatives: r.alternatives || [] });
    } catch (err) { toast(err.message); }
  }, [toast]);

  const pickPoint = useCallback((lat, lon) => setPoint({ lat, lon, origin: "exact point you clicked", notes: [], pin: null }), []);
  // one of the "did you mean" alternatives from a place search
  const pickPlace = useCallback((alt) => setPoint({ lat: alt.lat, lon: alt.lon, origin: alt.name, pin: null,
    notes: ["Approximate: the centre of this place."], matched: null, alternatives: [] }), []);
  const clearPoint = useCallback(() => {
    seq.current++;
    setPoint(null); setData(null); setDistrict(null); setSelectedId(null); setSearched(false);
  }, []);

  const openDetails = useCallback((id) => {
    const r = byId[id];
    if (!r) return;
    if (r.tier === "Unverified") setOpenUnverified(true);
    setSelectedId(id);
  }, [byId]);
  const closeDetails = useCallback(() => setSelectedId(null), []);

  useEffect(() => {
    const f = (e) => {
      if (e.key !== "Escape") return;
      if (modalOpen) setModalOpen(false); else setSelectedId(null);
    };
    document.addEventListener("keydown", f);
    return () => document.removeEventListener("keydown", f);
  }, [modalOpen]);

  const value = {
    services, service, setService, svcByLabel, chooseService,
    point, resolve, pickPoint, pickPlace, clearPoint, pinText, setPinText, placeText, setPlaceText,
    data, loading, searchError, searched, shown, setShown, openUnverified, setOpenUnverified,
    emergency, setEmergency, byId, selectedId, openDetails, closeDetails, hoveredId, setHoveredId,
    district, toast, toasts, setToasts, modalOpen, setModalOpen,
    themePref, setThemePref, isDark, mapApi,
  };

  return (
    <Store.Provider value={value}>
      <SplitLayout map={<MapView />} panel={<Panel />} />
      <Toasts />
      {modalOpen && <HowItWorksModal />}
    </Store.Provider>
  );
}
