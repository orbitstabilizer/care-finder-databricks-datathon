# Proposal: using NFHS-5 district indicators in the facility recommender

Status: proposal only. Nothing was built, no table written, no LLM call made. All numbers below
were measured with read-only SQL on 2026-11-21/22 unless labelled "estimate". Coverage numbers use
`workspace.vf.facility_service` as built at 02:40 UTC (228,062 sentences tagged; tagging still
running), so tier counts will move.

## 1. The honest role of NFHS

NFHS-5 is a household survey. It says what a district's **population** looks like (how many adults
have high blood sugar, how many births happen in a facility). It says nothing about any facility.

So NFHS is **context about need**, shown next to results. It must NOT:

- raise or lower a facility's tier, or change the order of results for a patient search;
- be worded as if a service exists or is missing ("no dialysis in this district");
- be presented as a count of patients or as current (it is 2019-21 and reports percentages).

Tier and ranking stay driven by quoted facility sentences only. NFHS answers a different question:
*where does a gap in verified coverage matter most?*

## 2. Improvements, ranked by value versus effort

| # | Improvement | Who benefits | Value | Effort |
|---|---|---|---|---|
| 1 | **District context strip** under the results: district name, 2-3 indicators relevant to the chosen service, and distance to the nearest Confirmed facility | Health worker, NGO | Medium: turns a list into a situation ("high need, verified care is far") | ~1 h |
| 2 | **Planner view "Coverage gaps"**: table/map of districts with high indicator and no or distant Confirmed facility, per service | District planner | High: the brief's third user has no view today | 3-4 h |
| 3 | **Verification priority list**: Likely/Possible facilities in high-need, low-coverage districts, sorted so someone can phone them first | NGO, us | High: the cheapest way to improve real answers | 1-2 h after #2 |
| 4 | Barrier context (insurance cover, out-of-pocket delivery cost) on result cards | Health worker | Low-medium | 1 h |
| 5 | Demand-weighted scoring of facilities | none | Negative: mixes need into evidence; do not build | - |

### Which indicator maps to which service

| Service | Indicator(s) | Defensibility |
|---|---|---|
| caesarean_section, maternity | `births_delivered_by_csection_5y_pct`, `institutional_birth_5y_pct`, public/private C-section split | **Strong**: direct measure of use of the service. Very low C-section rate (<5%) signals unmet need; very high signals over-use, so show the number, not a "good/bad" label |
| nicu, neonatal | institutional births, home births without skilled attendant, 4+ ANC visits | Medium: risk factors for newborn complications, not NICU demand |
| dialysis, nephrology | blood sugar >140 mg/dl or on medication (men, women), high blood pressure | **Weak-medium**: the two main causes of kidney failure, years upstream. Label as "risk factors for kidney disease", never "dialysis need" |
| cardiac_surgery, cath lab | high blood pressure, blood sugar, tobacco use | Weak-medium: risk factors only |
| oncology, screening | cervical / breast / oral exam rates, tobacco, alcohol | Medium for screening gaps; weak for treatment demand |
| paediatrics | stunting, wasting, anaemia, vaccination, diarrhoea treatment | Medium, but these columns are the most suppressed (see section 4) |
| mri, burn_care, trauma, most surgical services | none | **No usable indicator.** Show no NFHS context rather than a stretched one |

Roughly 10-15 of the 48 service labels have a defensible indicator (estimate from the column list).

## 3. Linking facilities and locations to NFHS districts

**NFHS names versus PIN-directory names** (lowercase, `&` to `and`, strip non-letters, fix
`Maharastra` and `NCT of Delhi`):

- 616 of 706 NFHS rows match a PIN-directory (state, district) exactly: **87.3%**. Name only: 619.
- 8 district names occur in two states (Aurangabad, Bilaspur, Hamirpur...), so the key must be
  (state, district), never district alone.
- 90 NFHS rows do not match. They are mostly renames and transliteration (Bangalore/Bengaluru Urban,
  Gurgaon/Gurugram, Allahabad/Prayagraj, Haora/Howrah). 47 of the 90 have a same-state candidate
  within edit distance 2 (55 within 3); the rest need a hand-written alias.
- 138 of 754 PIN-directory districts have no NFHS match; besides the renames, about 50 (estimate)
  are districts created after the survey (NTR, Chengalpattu, Hanumakonda) and need a parent mapping.

**Facility to district** (9,989 non-shifted facilities):

| Route | Measured |
|---|---|
| Valid postcode | 9,909 |
| Postcode found in PIN directory (majority district of that PIN) | 9,700 |
| ...of which the PIN spans more than one district | 401 |
| District then matches NFHS by exact name | **8,242 (82.5%)**, covering 462 NFHS districts |
| District found but name not in NFHS | 1,458; the top 25 are all renames or new districts (Bengaluru Urban 294, Gurugram 141) |
| Nearest trusted PIN centre by coordinates (fallback) | district for 9,559; rescues 279 with no postcode district; median distance 1.06 km |
| Agreement of the two routes where both exist | 7,739 of 9,280 (83%); 100 disagree on state |

PINs are mostly clean keys: 18,108 of 19,586 map to one district, 1,391 to two, 87 to three or four.

**Options compared**

- **A. Postcode to PIN-directory district + alias table (recommended first).** No external data.
  82.5% of facilities today; an alias table of about 140 rows (90 NFHS-side, about 50 new-district
  parents) should bring this to roughly 95-97% (estimate: 8,242 + 1,458 = 9,700 of 9,989 is the ceiling).
- **B. Nearest post office by coordinates.** Use only as a fallback and for map clicks. It agrees
  with route A only 83% of the time, because the nearest PIN centre near a border is often across it.
  Show the district as "approximate".
- **C. District polygons (geoBoundaries / DataMeet), point-in-polygon.** The most correct, and the
  only clean answer for a map click. Not measured: needs an external file uploaded, and the boundary
  vintage must match NFHS-5's 2019 district list. About 2-3 h; do it only if the planner view ships.

User locations: PIN input uses route A; place name uses the district lookup; map click uses B (or C).

## 4. Data quality handling

Measured on the local parquet copy:

- 49 of the 107 indicator columns are STRING. They hold 4,125 suppressed `*` cells and 5,068
  parenthesised low-confidence cells out of 34,594. 688 of 706 districts have at least one `*`.
- Suppression is concentrated: child feeding and diarrhoea-treatment columns are 70-91% suppressed.
  `pregnant women anaemic` is `*` in 134 districts and low-confidence in 421: unusable as a headline.
- The 58 DOUBLE columns (blood sugar, blood pressure, institutional births, overall C-section rate,
  insurance, tobacco) have no missing values. **Use these first.**
- Odd rows exist: "Chandel" appears under both Manipur and Mizoram; Maharashtra has "Raigarh".

Rules: `*` becomes NULL and is shown as "not reported", never zero. Parenthesised values are parsed
to a number with `low_confidence = true` and shown with "(small sample)". Each value carries its
source: "NFHS-5, 2019-21". Use quartile wording ("among the highest quarter of districts") rather
than ranks, because one district's sample is small (median 908 households) and nearby ranks are
not distinguishable. District assignment shows its method: "from PIN code" or "approximate, nearest
post office".

## 5. Minimal first step (about one hour)

1. `workspace.vf.nfhs_district` - one row per NFHS row: `nfhs_key` (state|district normalised),
   `district`, `state`, 8 clean DOUBLE indicators, and each one's quartile.
2. `workspace.vf.pin_district` - `pin`, `district`, `state`, `pin_share` (share of the PIN's post
   offices in that district), `nfhs_key`, `match_method` (exact / alias / none). Start with exact
   matches plus aliases for the 25 districts that hold the most facilities.
3. One UI element: a grey "District context" strip between the search box and the result cards.
   It never touches the cards, tiers or order.

Example, **Thanjavur, Tamil Nadu**, service = dialysis (all measured):

> **Thanjavur district - context, not evidence.** 29.0% of men and 23.3% of women aged 15+ have high
> blood sugar or take medication for it (7th highest of 706 districts; NFHS-5, 2019-21). 34.6% of
> men have high blood pressure. These are risk factors for kidney disease, not a count of dialysis
> patients. In our data: 23 facilities in the district, 0 with Confirmed dialysis, 4 Likely
> (nearest 11 km from the district centre). Nearest Confirmed: 139 km.

This is the useful reading: a high-need district where the answer rests on Likely evidence, so
those 4 facilities are the first ones worth a phone call.

Scale of the planner view, over 572 districts that have both an exact NFHS match and a centre point:
457 have no Confirmed dialysis facility, 342 are more than 50 km from one, 152 more than 100 km
(median 63 km). Of 144 districts in the top quarter for male blood sugar, 100 have none and 71 are
more than 50 km away. 418 districts have no Confirmed NICU; 118 have no facility in the dataset.

## 6. Risks and what not to do

- **Absence in this dataset is not absence of care.** The dataset holds about 10,000 facilities and
  118 matched districts have none at all. Thanjavur has a government medical college; "0 Confirmed"
  means "none we could verify". Wording must always be "in our data" and "verified", and the planner
  view must show the facility count per district beside every gap.
- **Do not feed NFHS into tier or ranking**, and do not build a composite "need score" with
  invented weights: it cannot be defended to the judges. Show the raw indicator and its quartile.
- **Ecological fallacy**: a district average says nothing about the patient in front of the health
  worker. Keep context visually separate from recommendations.
- **Stretched proxies**: blood sugar is not dialysis demand. Services without a defensible
  indicator get no context strip.
- **Vintage and boundaries**: 2019-21 data on 2019 boundaries; newer districts inherit a parent's
  value and must say so.
- **Distances are straight-line from a district centre** (mean of trusted PIN points), not travel
  time and not the user's location. In the patient view use the user's point instead.
- **Name matching fails silently on the biggest cities** (Bengaluru, Gurugram, Prayagraj are in
  the unmatched set). Ship the alias table with the first step, and show "no district data" rather
  than a wrong district.
