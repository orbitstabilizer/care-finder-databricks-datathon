# Care finder — evaluation and improvement proposals

Evaluation only; nothing was built or changed. Numbers are from read-only SQL on `workspace.vf` (build stamp 2026-11-22 03:26 UTC), the app source and `databricks apps logs vf-locator`. Where a figure is my reading of a small sample it says "my judgement". 12 LLM calls were used, all on the matcher.

## Scorecard

### 1. Recommendation correctness — good for dialysis, weaker and unmeasured elsewhere

**Works.** The blind dialysis check found no wrong Confirmed or Likely result: 15 of 15 checked Confirmed, 9 of 9 Likely, 11 of 11 Possible offer dialysis; Unverified 4 of 9. The tiers separate good from bad where it matters.

**What that check does not show.**
- 36 of 80 (45%) were "cannot tell" (Confirmed 5 of 20, Likely 11 of 20). The checked set leans towards facilities with websites.
- 15 of 15 is a small sample: it is consistent with a true rate anywhere above roughly 80% (estimate, rule of three).
- It covers dialysis only, a service that is named plainly in text. It says nothing about the other 59 services.

**Spot check of other services (my judgement, 10 random Confirmed + 10 random Likely each, reading the up-to-3 quotes the app shows).**

| service | Confirmed: supported / doubtful / wrong | Likely: supported / doubtful or wrong |
|---|---|---|
| NICU | 8 / 2 / 0 | 7 / 3 |
| Trauma and emergency | 10 offer emergency care, but only 3 show real capacity | 7 / 3 (children's, maternity and cardiac-only emergency) |
| Cardiac surgery | 6 / 3 / 1 | 3 / 7 |

**Failure patterns, counted over all rows with keyword checks on the shown quotes** (a keyword check undercounts synonyms, so treat as upper bounds):
- **Department or generic line counted as the service.** Cardiac surgery: 235 of 565 Confirmed (42%) and 686 of 997 Likely (69%) show no quote with a surgery word (surgery, CABG, bypass, valve, cardiothoracic, TAVI). 105 Confirmed (19%) and 272 Likely (27%) show only generic operating-theatre lines, e.g. Confirmed on "Modular operating theatres" alone. "Offers Cardiology" produces Likely cardiac surgery.
- **Any digit counts as "detailed".** Trauma and emergency: 209 of 327 Confirmed (64%) are "detailed" only through "24/7"-type numbers or marketing counts ("Has 42+ emergency services"). 155 Confirmed (47%) show no trauma, accident or casualty word. A children's hospital with 24/7 emergency is not a trauma centre.
- **Near-miss services.** NICU: 293 of 570 Likely (51%) and 53 of 426 Confirmed (12%) never say NICU or neonatal intensive care ("Offers newborn care", phototherapy, SNCU). Dialysis: 18 of 335 Confirmed (5%) show only neonatal or peritoneal dialysis lines, which will not help an adult kidney patient.
- **Thin Confirmed.** 2,424 of 17,980 Confirmed pairs (13%) rest on one sentence plus a department.
- **Mixed records.** 7,843 Confirmed pairs (44%) come from records audited "partly foreign"; flagged sentences are removed, but only 289 Confirmed pairs carry a warning.

### 2. Coverage and gaps — broad in total, thin for the brief's own examples

- 9,785 of 9,989 usable facilities have a tier for at least one service (204, 2.0%, have none); 9,206 have a Confirmed or Likely; 5,070 have a Confirmed. 88 shifted records are excluded. 90 facilities cannot be placed; none of them carries a verdict, so nothing rankable is lost.
- **Thin headline services (Confirmed nationwide):** burn care 20, caesarean section 32, high-risk obstetrics 32, stroke care 30, mental health 15, medical cardiology 11. Caesarean section has 361 Likely and 384 Possible, so the practical list is not the Confirmed one.
- **Districts.** Facilities fall in 532 of 706 survey districts; 174 districts (25%) have no facility at all, and 97 have exactly one. Of the 532, districts with no Confirmed facility: burn care 512, caesarean 505, dialysis 391, MRI 368, cardiac surgery 348, NICU 347, trauma 382, ICU 260. With no Confirmed or Likely: burn 443, caesarean 378, dialysis 273, NICU 269.
- **Distance from 300 random PIN codes to the nearest Confirmed (median / 90th percentile, km):** dialysis 54 / 129, NICU 43 / 104, MRI 46 / 111, cardiac surgery 41 / 107, caesarean 142 / 272, burn care 161 / 370. Nearest Confirmed is over 100 km for 72% of PINs (burn) and 64% (caesarean).

### 3. Ranking and explanation — honest and inspectable, but rigid at the edges

**Works.** Results are grouped by tier, each with a meaning line, a nearest-per-tier summary, quotes, warnings, a "why" list (statement counts, department, facility-type fit, mixed-record check, location quality) and a "How this works" panel with the tier rules, the funnel and the validation line. Uncertain locations say "about N km, location uncertain"; centroid-placed facilities show no distance.

**Weaknesses.**
- **Strict tier-first over-rewards a fragile label.** Given the patterns in section 1, a Confirmed "24/7" emergency line 150 km away outranks a Likely "Trauma Care Center" nearby. For caesarean section, 52% of random PINs have a Likely at under half the distance of the nearest Confirmed (and that Confirmed is over 50 km away); burn care 47%, dialysis 18%.
- **No distance limit.** Burn care has 20 Confirmed, so its Confirmed section is the same national list for every user.
- **Centroid-placed facilities sink.** They sort after every exactly-located facility in the tier, then the 20-per-tier cap cuts them. 3,845 of 71,039 Confirmed or Likely pairs (5.4%) are affected; a Confirmed hospital in the user's own city can be invisible.
- **"Suspect" coordinates rank as if exact** (4,278 Confirmed or Likely pairs), with only a text caveat.
- **Why this one and not the next?** The card explains the tier, not the position. Nothing says "ranked first because it is the nearest Confirmed; 2 closer Likely options below".
- **No source link.** Quotes show the source column (procedure, capability), not a URL. Only 3 quotes are stored, and the first is sometimes off-topic (a cardiac hospital's first cardiac-surgery quote is its ambulance).
- No bed count, doctor count or opening-hours signal is used, even as a tie-break.

### 4. Free-text matcher — 11 of 12 sensible

Tested with the exact app prompt and post-processing: "dialysis", "emergency c-section", "MRI scan of the brain", "my father needs a kidney machine", "sugar ki problem hai" (diabetes), "pet me dard hai aur ulti ho rahi hai" (clinic, then gastroenterology), premature baby not breathing (NICU), chest pain with numb arm (cardiology), highway accident (trauma), severe burns (burn care), knee pain (clinic, physiotherapy, orthopaedics), gibberish. The emergency flag fired on all 5 urgent phrases and on none of the others.

Weaknesses: gibberish returns "Outpatient clinic" as best match instead of "not understood"; four of five emergencies also offer an outpatient clinic ("General checkup" for severe burns); chest pain maps to medical cardiology, the thinnest service (11 Confirmed); for the knee phrase the "best" option is listed second. Results are cached per text; a failure returns an empty list.

### 5. Speed and robustness — fast when warm, untested when cold

- Startup probe: search SQL 0.17–0.27 s, matcher call 0.9–1.3 s, connection 0.7–0.85 s. Live searches return in about 1 s by log timestamps, with a 127 KB payload.
- Log window (03:26–03:45 UTC, 450 lines): 6 searches, 12 matcher calls, all HTTP 200; no tracebacks or timeouts. The only error lines are 6 "Security scan failed" build messages, one per deploy, harmless so far.
- **Risks.** One 2X-Small warehouse serves everything and stops after 10 idle minutes; cold-start time was not measured. Any rebuild or ad-hoc query during the demo competes with the app. Searches are cached 10 minutes per exact point. The log does not record search latency or what the matcher returned, so problems would be hard to diagnose afterwards.

### 6. Fit to the judging rule — strong on "how", exposed on three points

Meets: Databricks Free Edition, provided dataset, non-technical flow (plain words; map click, PIN or place name), verbatim quotes, tiers and warnings, and a reproducible, non-LLM ranking step.

Where a judge can poke:
1. "Show me why this is Confirmed for cardiac surgery" and the quote is "Modular operating theatres".
2. "How accurate is it?" — one service, 44 usable checks.
3. "Where did this sentence come from?" — no link.
4. "Emergency C-section near here?" — 32 Confirmed in India; the first result may be 140 km away while Likely options sit nearby.
5. "A city or district as input" — the place box only resolves exact city names that have enough facilities in the data (exact match on a lower-cased name); districts, villages and spelling variants return "No point known".

## Proposals, ranked by impact against effort

| # | Problem | Evidence | Proposed change | Effort | Risk |
|---|---|---|---|---|---|
| 1 | Confirmed/Likely granted on sentences that do not name the service | Cardiac surgery 42% of Confirmed, NICU 51% of Likely, without the service's own words | In the verdict build, require at least one quote matching the service's term list (`SERVICE_TERMS` already exists) for Confirmed; otherwise cap at Likely, and send department-only or generic-theatre evidence to Possible. Put the matching quote first | 2–3 h, SQL only, no LLM | Confirmed counts drop; term lists miss synonyms, so review the 8 headline services by hand |
| 2 | "Detailed" triggered by any digit | 64% of trauma Confirmed rest on "24/7" or "42+ services" | Strip time and marketing numbers before the digit test; require a unit word (beds, machines, units, stations, theatres) | 1 h | Small; rerun the three demo stories |
| 3 | Position in the list is not explained; no source link | UI shows tier reasons and source column only | Add one line per card ("Nearest Confirmed. 2 Likely options are closer, see below") and the record's source domains beside the quote | 2 h, app only | Links are per record, not per sentence; say so |
| 4 | Far Confirmed hides near Likely for thin services | Caesarean: 52% of PINs have a Likely at under half the distance | Keep tier-first, but add a "closest credible option" line at the top when a Likely is much closer, and a note when the nearest Confirmed is over 100 km: "few facilities state this in detail; call the Likely ones first" | 2 h | Must stay clearly labelled as less certain |
| 5 | Accuracy evidence is one service | 44 usable checks, dialysis only | Repeat the blind check for caesarean section and cardiac surgery (40 each), and show "x of y checked, z could not be checked" in the app | 3–4 h | May expose a lower hit rate; better found by us than by a judge |
| 6 | Caesarean section, burn care, stroke are thin | 32, 20, 30 Confirmed | Do not loosen the rule silently. Show a per-service coverage note, and order Likely by statement count before distance for these services | 1–2 h | Changes order within Likely |
| 7 | Centroid-placed facilities fall off the list | 3,845 Confirmed or Likely pairs | Add an "in this city, exact address unknown" block when the centroid is within about 25 km of the user | 1–2 h | Centroid can be off in large cities |
| 8 | Matcher edge cases | Gibberish maps to a clinic; emergencies offer "General checkup" | Return "not understood" when confidence is low and nothing was recognised; drop the outpatient option when the emergency flag is set; map chest-pain emergencies to emergency care first; sort best first | 1 h | Prompt change needs the 12 phrases rerun |
| 9 | Emergency care and trauma centre are one label | 47% of Confirmed show no trauma word | Split into "24-hour emergency" and "trauma centre" using the existing sentences and a term rule | 2–3 h, no LLM | New label needs a place in the picker and the matcher |
| 10 | Cold start and blind logs | Warehouse stops after 10 min; latency not logged | Warm the warehouse and the three demo searches before presenting; log search time and matcher outcome; freeze rebuilds during the demo | 1 h | None |

Proposals 1, 2 and 9 change tier counts, so the numbers in the executive summary and the three demo stories would need refreshing afterwards.
