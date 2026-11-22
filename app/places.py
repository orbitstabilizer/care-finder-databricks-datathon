"""Place-name search: cities, districts (incl. NFHS aliases) and post-office names, with spelling tolerance.

Exact matches win in this order: city (has a facility centre) > district > district alias > post office.
Otherwise a fuzzy match (difflib ratio) over city, district and alias names; post offices are exact only
because there are ~150k of them. Returns the chosen place plus up to 3 alternatives when it is ambiguous."""
import difflib
import re

_KIND_RANK = {"city": 0, "district": 1, "alias": 2, "office": 3}
_STRIP = re.compile(r"\b(district|dist|city|town|nagar palika)\b", re.I)


_OFFICE_SUFFIX = re.compile(r"\s+(b\.?\s?o|s\.?\s?o|h\.?\s?o|g\.?\s?p\.?\s?o)\.?$")


def norm(s: str) -> str:
    s = _OFFICE_SUFFIX.sub("", str(s or "").lower().strip())
    s = _STRIP.sub(" ", s)
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


class PlaceIndex:
    def __init__(self, rows: list[dict]):
        self.exact: dict[str, list[dict]] = {}
        fuzzy: dict[str, list[dict]] = {}
        for r in rows:
            if r.get("lat") is None or r.get("lon") is None or not r.get("name"):
                continue
            k = norm(r["name"])
            if not k:
                continue
            self.exact.setdefault(k, []).append(r)
            if r["kind"] != "office":
                fuzzy.setdefault(k, []).append(r)
        for v in self.exact.values():
            v.sort(key=lambda r: (_KIND_RANK[r["kind"]], r.get("office_rank") or 0, -(r.get("n") or 0)))
        self.fuzzy = fuzzy
        self.fuzzy_keys = list(fuzzy)

    @staticmethod
    def label(r: dict) -> str:
        name = _OFFICE_SUFFIX.sub("", str(r["name"]).lower().strip()).title()
        if r["kind"] == "city":
            return name
        if r["kind"] == "office":
            return f"{name} ({str(r.get('district') or '').title()}, {str(r.get('state') or '').title()})"
        dist = str(r.get("district") or r["name"]).title()
        return f"{dist} district, {str(r.get('state') or '').title()}"

    def _alt(self, r: dict) -> dict:
        return {"name": self.label(r), "kind": r["kind"], "lat": r["lat"], "lon": r["lon"]}

    def resolve(self, text: str) -> dict | None:
        k = norm(text)
        if not k:
            return None
        hits = self.exact.get(k)
        if hits:
            best = hits[0]
            alts, seen = [], {(best["kind"], best.get("district"), best.get("state"))}
            for h in hits[1:]:
                key = (h["kind"], h.get("district"), h.get("state"))
                if key in seen or len(alts) >= 3:
                    continue
                seen.add(key)
                alts.append(h)
            return {"place": best, "exact": True, "score": 1.0, "alternatives": [self._alt(a) for a in alts]}
        scored = sorted(((difflib.SequenceMatcher(None, k, key).ratio(), key)
                         for key in difflib.get_close_matches(k, self.fuzzy_keys, n=8, cutoff=0.72)),
                        reverse=True)
        if not scored:
            return None
        cands = []
        for score, key in scored:
            for r in self.fuzzy[key][:2]:
                cands.append((score, r))
        cands.sort(key=lambda x: (-x[0], _KIND_RANK[x[1]["kind"]], -(x[1].get("n") or 0)))
        best_score, best = cands[0]
        # ambiguous when another distinct place scores within 0.06 of the best
        seen, alts = {(best["kind"], norm(best["name"]), best.get("state"))}, []
        for score, r in cands[1:]:
            key = (r["kind"], norm(r["name"]), r.get("state"))
            if key in seen:
                continue
            seen.add(key)
            if score >= best_score - 0.06 and len(alts) < 3:
                alts.append(self._alt(r))
        return {"place": best, "exact": False, "score": round(best_score, 2), "alternatives": alts}
