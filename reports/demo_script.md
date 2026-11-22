# Demo script — every feature, five stories

Re-check the numbers after any rebuild. Last checked 2026-11-22.

| # | Story | Type / do | Features shown |
|---|---|---|---|
| 1 | **Rayagada, newborn** | Type *"my newborn baby needs intensive care"* → NICU. PIN **765019**. Click Christian Hospital Bissamcuttack. | Plain-language matching · PIN location · tiers then distance · Confirmed 143 km (MKCG) vs Likely 7.8 km · "call the Likely ones first" banner · map arrow + distance · quoted evidence + source column · "Why this result" checklist · Call / Directions / Website · district panel (72% skilled birth attendance, 36th lowest of 706) |
| 2 | **Thanjavur, C-section** | Service box: type *"caesar"* → C-section. PIN **613001**. | Synonym search · **district hint**: 51% of births by caesarean, nearest Confirmed 108 km, so it lists nearby maternity hospitals (Meenakshi, Vinodhagan) to call · tiers unchanged |
| 2b | **Thanjavur, dialysis** | Switch service to Dialysis, same PIN. | Confirmed nearby: Sudar Hospital, under 1 km · district panel shows high blood sugar (7th highest) |
| 3 | **Villupuram, dialysis** | PIN **605602**. Open Aravind Eye Hospital in Unverified. | Mixed-record check: nearest result (1.1 km) is an eye hospital whose record carries text copied from other hospitals; it lands in Unverified with a warning, below East Coast Hospital (Possible, 31 km) · uncertain-location warning (its city says Hyderabad, PIN says Delhi, coordinates say Villupuram) |
| 4 | **Gumla, dialysis** | Place box: type *"Gumla"* (or click the map). | Place-name search / map click · rural gap: Likely 81 km vs Confirmed 87 km, both shown and labelled |
| 5 | **Not sure what to ask** | Type *"I can't jump"*, then *"numb left arm and can't breathe"*. | Symptom → 2–3 options with reasons, least invasive first, user picks · emergency warning: call 108 / 112 |
| — | Close | Click "How this works". Toggle light/dark. | Method in plain words · theme |

Talking points
- WHY: every card quotes the facility's own sentences and lists its warnings.
- HOW: tier first (Confirmed / Likely / Possible / Unverified), then distance; a nearby weak claim never outranks a confirmed one, but it is never hidden either.
- Honesty: district data only *suggests* places to call; it never changes a tier.
