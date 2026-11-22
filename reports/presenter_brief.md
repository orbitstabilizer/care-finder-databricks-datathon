# Presenter brief — Care Finder

Read with `executive_summary.md` (the method) and `demo_script.md` (the video). This page is for answering judges.

## The one-sentence pitch
Type a need in plain words and a place; get the nearest facilities that offer it, ranked by how strong the evidence is, each with the facility's own sentences quoted and an honest confidence label.

## Numbers to remember
| | |
|---|---|
| Facilities | 10,077 (88 with shifted columns dropped → 9,989 usable) |
| Evidence sentences | 451,110 → 271,262 distinct, each read once by an LLM; 188,538 are real service claims |
| Services | 60 fixed labels (grew from 49 by studying the sentences that fitted none) |
| Facility types | 26 (eye hospital, dental clinic, maternity, multispecialty…) |
| Ownership check | 9,577 records read; 814 warned as possibly mixing other hospitals |
| Verdicts | 98,245 facility–service pairs: 12,128 Confirmed · 55,352 Likely · 8,005 Possible · 22,760 Unverified |
| Locations | 8,772 high/good confidence; 90 cannot be placed |
| Blind checks | 151 facilities, 3 services: Confirmed right 30 of 30 that could be checked |
| Model | Llama 3.3 70B through Databricks `ai_query`; all on Free Edition |

## Decisions: what we chose, what we rejected, why
1. **The sentence is the unit of evidence, not the record.** Records mix hospitals (an eye hospital carrying a Delhi dialysis unit). A sentence can be checked, quoted and dropped on its own.
2. **Read everything once with an LLM, then match exactly.** Rejected: searching the text (or vector search / RAG) at query time. Pre-tagging makes answers fast, identical every time, and auditable; every result points to stored sentences, never to generated text.
3. **A fixed list of 60 services.** Rejected: free-form labels. A fixed list can be validated (the model once invented a label) and matched exactly. The user's own words are mapped onto it at search time.
4. **Three separate questions per sentence:** is it a claim? which services (several allowed)? how strong (explicit / stated / weak)? Merging these into one label collided and lost evidence.
5. **Check that a record's text belongs to it.** An LLM reads each record against its own name and city and flags sentences about other organisations. Flagged sentences are removed; heavily mixed records get a warning.
6. **Know what kind of facility it is.** A service that is unexpected for the facility type (dialysis at an eye hospital) cannot be Confirmed.
7. **Departments back a claim but never prove it.** 2,153 facilities list nephrology; that does not say who runs dialysis.
8. **Tiers, then distance. Rejected: one blended score.** A tier rule can be read out loud, and a nearby weak claim can never outrank a confirmed one further away. Cost: no fine ordering inside a tier.
9. **Confirmed needs a quoted sentence that names the service with detail** (beds or machines, a dedicated unit, or for surgery a named procedure), plus department backing or a second statement.
10. **Never hide an option.** If a Likely facility is closer than the nearest Confirmed, both show and the app says call the closer one first (Rayagada).
11. **Coordinates, cross-checked.** Each point is checked against its postcode centre and city centre and gets a confidence level; uncertain ones say "about". Distances are straight-line, not road.
12. **District health data is context and a hint, never a ranking input.** A district rate says a service happens somewhere in the district, not at which hospital. When it shows the service is common but no Confirmed facility lies within 30 km, we list nearby related hospitals, each with its own quote, to call.
13. **Plain-words search asks rather than guesses.** A named service is selected; a symptom gets 2–3 options with reasons; emergency wording gets "call 108 / 112" first. It maps words to services and gives no medical advice.
14. **Citations = the verbatim sentence + the record's source websites.** The dataset has no URL per sentence, so we cannot claim which page a sentence came from; we say so.
15. **Measure, don't assume.** Every rule change was checked against counts and blind samples.

## Likely questions
- **How do you know it's right?** There is no ground truth, so we ran blind web checks: a sampled facility was looked up on its own website by an AI agent that did not see our tier. Every Confirmed facility we could verify offered the service (30 of 30). For cardiac surgery the share falls tier by tier: 100 / 80 / 17 / 0%. About 40% could not be checked (no website).
- **Why not just search the text?** That recommends an eye hospital for dialysis. Show Aravind.
- **Why not use the specialties column?** A department is not a service.
- **Could the LLM make things up?** It only labels; it never writes the evidence. Every label is validated against the list, every batch is checked for alignment, and every quote is copied verbatim from the dataset.
- **What if the website is out of date?** We prove a website made the claim, not that the service runs today, which is why the app says "call to check".
- **Why straight-line distance?** No road network in Free Edition data; travel time is the obvious next step.
- **Was anything tuned on the test?** Yes, honestly: after the dialysis check we relaxed two rules, so that check is not independent. The C-section and cardiac checks were scored against fixed rules and nothing was changed afterwards.
- **What does it cost?** The LLM reading is a one-off pass; each search is a plain SQL query, well under a second.
- **Why Thanjavur C-section shows 108 km?** No website within 40 km mentions C-sections; the district hint covers exactly this case.

## Weak spots: own them
- The ownership check over-flags "partly foreign" records (renamed cities, a hospital's own branches).
- LLM labels are not perfectly repeatable run to run.
- 148 facilities have no evidence text and cannot be recommended.
- Emergency and major trauma share one label.
- Blind checks cover 3 of 60 services and only facilities with a website.
