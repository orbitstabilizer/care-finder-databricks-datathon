export async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `Request failed (${r.status})`);
  return body;
}

export const store = {
  get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
  set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (_) { /* storage blocked */ } },
};

export const TIERS = ["Confirmed", "Likely", "Possible", "Unverified"];
export const COLOUR = { Confirmed: "#1f9d55", Likely: "#d4900d", Possible: "#2b6cb0", Unverified: "#8a94a3" };
export const FIRST = 5, STEP = 5;
export const EXAMPLES = [
  { label: "dialysis", name: "Dialysis", q: "pin=835207", where: "835207", kind: "pin" },
  { label: "caesarean_section", name: "C-section", q: "place=Hyderabad", where: "Hyderabad", kind: "place" },
  { label: "nicu", name: "NICU", q: "pin=560001", where: "560001", kind: "pin" },
];

export function where(s) {
  if (!s.exact_location) return `in ${s.city || "its area"}`;
  return s.distance_km >= 10 ? `${Math.round(s.distance_km)} km` : `${s.distance_km.toFixed(1)} km`;
}
export function ordinal(n) {
  const v = n % 100;
  if (v >= 11 && v <= 13) return `${n}th`;
  return `${n}${{ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"}`;
}
export const titleCase = (s) => String(s || "").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
export const fmtKm = (km) => (km >= 10 ? `${Math.round(km)} km` : `${Number(km).toFixed(1)} km`);

/** Visible results per tier, as the map and list show them. */
export function visibleResults(data, shown, openUnverified) {
  const out = [];
  for (const t of data?.tiers || []) {
    if (t.tier === "Unverified" && !openUnverified) continue;
    out.push(...t.results.slice(0, shown[t.tier] || FIRST), ...(t.city_block || []));
  }
  return out;
}
