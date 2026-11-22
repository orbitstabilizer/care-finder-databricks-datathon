# Demo video — 2:30

Pre-load the app (warm the warehouse: run each search once before recording). Last checked 2026-11-22.

| Time | Screen | Do | Say (gist) |
|---|---|---|---|
| 0:00–0:15 | App, empty | — | A health worker needs the nearest place for a service. 10,000 facility records, scraped and messy: every field is a claim, not a fact. |
| 0:15–1:00 | **Rayagada NICU** | Type *"my newborn baby needs intensive care"* → NICU. PIN **765019**. Click Christian Hospital Bissamcuttack. | Plain words become a service. Results by tier, then distance. Nearest Confirmed is 143 km; a Likely hospital is 7.8 km, so the app says call it first. Arrow + distance. Its own sentence: *"Neonatal incubators introduced…"*. Why-this-result checklist, call, directions. District panel: 72% skilled birth attendance, 36th lowest in India. |
| 1:00–1:30 | **Thanjavur C-section** | Service box *"caesar"*. PIN **613001**. | No nearby website mentions C-sections, yet 51% of births here are caesarean. The app uses district data as a hint: these maternity hospitals nearby, call to check. It never changes a tier. |
| 1:30–1:55 | **Villupuram dialysis** | Service Dialysis, PIN **605602**. Open Aravind Eye Hospital. | A keyword search sends this patient to an eye hospital 1.1 km away: its record carries text copied from other hospitals. We check every record's text belongs to it, so it lands in Unverified with a warning. |
| 1:55–2:10 | **Emergency** | Type *"numb left arm and can't breathe"*. | It recognises an emergency and says call 108 / 112 first. |
| 2:10–2:30 | How this works | Open the panel. | HOW: an LLM tags 450k sentences once; tiers from evidence, ownership check and facility type; blind web checks: every Confirmed we could verify was right (30 of 30). Runs entirely on Databricks Free Edition. |

Cut if over time: the emergency beat first, then the district panel line in Rayagada.
Backup stories (not in the video): Thanjavur dialysis (Sudar, Confirmed <1 km), Gumla dialysis (Likely 81 km vs Confirmed 87 km), "I can't jump" (symptom → options).
