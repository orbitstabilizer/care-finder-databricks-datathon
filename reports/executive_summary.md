# Finding the right care — how our solution works

## The problem

A community health worker has a patient who needs dialysis. An NGO coordinator needs a hospital for a high-risk delivery. Both ask the same question: *where is the best place to get this service, from here?* Our tool takes a **service** and a **location** and returns the best facilities, each with the evidence for why it was chosen and an honest statement of how sure we are.

The data makes this hard. The Virtue Foundation dataset describes 10,077 Indian facilities, but it was assembled by scraping websites and merging them with a language model. So every field is a claim, not a fact:

- **Services hide in free text.** No column says "offers dialysis". The evidence is spread across about 451,000 short sentences such as *"20-bed dialysis unit with 10 machines"*, mixed in with doctor biographies, fees and founding dates.
- **Departments are not services.** 2,153 facilities list nephrology, which does not tell us which ones run dialysis.
- **Some records mix several hospitals.** The record for an eye hospital in Hyderabad carries a dialysis unit, a neurosurgery department and an Ayurvedic clinic, all copied from Delhi government hospitals. A plain text search would recommend an eye hospital for dialysis.
- **Place names are unreliable.** The state field holds 254 different values for India's 37 states and territories.

## Design principles

1. **Treat every field as a claim to check, not a fact.**
2. **Use the sentence as the unit of evidence.** Whole records can be contaminated; single sentences can be checked and quoted.
3. **Do the expensive reading once.** A language model reads the text in advance; queries then run on clean, structured results, so answers are fast, repeatable and auditable.
4. **Use coordinates, not names, for location.**
5. **Show proof and admit doubt.** Every recommendation quotes its sentences and carries a confidence tier and warnings.

## Step 1 — Clean the data

We removed exact duplicate records and detected 88 records whose columns had shifted during scraping (text sitting in the wrong fields). We split every record into its individual sentences, removed placeholders such as *"no procedures listed in the provided content"*, and marked sentences repeated within the same record so they are not counted twice. Identical sentences across facilities are stored once, so each is read only once.

## Step 2 — Place every facility on the map

Most facilities have coordinates, but some are wrong. We check each facility's listed point against two independent references:

- **A postcode centre**, built from the national post office directory after removing post offices that sit far from their region.
- **A city centre**, built from the other facilities in the same city.

From that cross-check each facility gets one point and a confidence level:

| Level | Meaning | Facilities |
|---|---|---|
| High | Coordinates agree with both postcode and city | 5,551 |
| Good | Coordinates agree with one of them | 3,221 |
| Approximate / suspect / unverified | Shown with a warning, or replaced by a city or postcode centre | 1,215 |
| Cannot be placed | No usable coordinates, postcode or city | 90 |

The user gives their location by clicking the map or typing a PIN code, and distances are straight-line kilometres.

## Step 3 — Identify what kind of facility each one is

An eye hospital that claims a dialysis unit deserves suspicion, so we need to know what each facility is. A language model reads the name, description and listed departments and assigns one of 26 types, such as eye hospital, dental clinic, maternity hospital or multispecialty hospital. The name and description lead; departments only break ties, because they are over-assigned in this data (general medicine appears on dental and hearing clinics). Each answer is checked against the allowed list.

## Step 4 — Tag each sentence with the service it proves

For every sentence, a language model answers three questions:

1. **Is it a claim that this facility offers a service?** Biographies, fees, awards and research findings are not.
2. **Which services?** Chosen from a fixed list of 60, such as dialysis, caesarean section, NICU, MRI, burn care, urology and AYUSH traditional medicine. A fixed list makes matching exact and inspectable; the user's own words are mapped onto it. We grew the list from 49 to 60 by studying the sentences that fitted no label and adding the services at least 300 facilities offer.
3. **How strong is the evidence?** *Explicit* (concrete capacity: beds, machines, units), *stated* (named plainly), or *weak* (only implied).

We tested this on real sentences until it held up. It had to allow several services per sentence, to say "not a claim" instead of forcing a label, and to reject any label outside the list. Sentences found only in dental clinics are labelled dental by rule, without the model. Of 271,262 distinct sentences, 269,731 were tagged and 188,538 turned out to be real service claims; the rest are biographies, fees, dates and similar.

## Step 5 — Check that a record's text belongs to that facility

To catch mixed records, a language model reads all of a facility's sentences against its own name and city and lists the sentences that describe a different organisation. Renamed cities, nearby localities and the hospital's own branches count as the same place; a similarly named hospital in another city counts as foreign. We ran it on all 9,575 facilities with enough text: 814 records carry a warning that parts of them may describe a different hospital. For the Hyderabad eye hospital, it flagged 79 of 149 sentences. Flagged sentences are removed from the evidence.

## Step 6 — Turn evidence into a verdict

For each facility and service we combine:

- **Evidence**: how many explicit, stated and weak sentences remain after foreign ones are removed.
- **Department backing**: whether the facility lists a department that supports the service, such as nephrology for dialysis.
- **Type fit**: whether the service is expected, plausible or unexpected for that kind of facility.

These give a tier: **Confirmed** (detailed evidence, backed by a department or a second statement), **Likely** (the facility says it plainly), **Possible** (no direct claim, but the right department and a closely related service), or **Unverified** (weak evidence, text that may belong to another hospital, or a facility that rarely offers the service). Each verdict carries quoted sentences as proof. Across 60 services and 9,989 facilities this gives 17,980 Confirmed, 53,059 Likely, 4,446 Possible and 22,760 Unverified facility–service pairs.

## Step 7 — Rank and show the results

Results are sorted **by tier first, then by distance**. Sending a patient hours away to a place that does not offer the service costs more than a longer trip to one that does, so a confirmed hospital further away ranks above a closer unverified one. Each result shows the name, distance, tier, the quoted sentences and any warnings, including an uncertain location.

## Asking in plain words

A health worker does not think in service labels, so the search box takes plain language such as *"my father needs a kidney machine"*. One language-model call maps the words onto our services. If the text names a service, it is selected straight away. If it describes a symptom, such as *"I can't jump"*, the app does not guess: it offers two or three options with a short reason each, the least invasive first (an outpatient clinic before surgery), and waits for the user to pick. If the words sound like an emergency, such as a numb left arm with trouble breathing, the app first shows a warning to call 108, India's free ambulance number, or the national emergency number 112. It only matches words to services; it never gives medical advice.

## How well it works: a blind spot check

We checked 80 dialysis results, 20 from each tier, against each facility's own website or one web search, without knowing our tier. 15 of 15 checked Confirmed facilities offer dialysis, as do 9 of 9 Likely and 11 of 11 Possible. Among Unverified facilities only 4 of 9 did; the 5 that did not were eye hospitals and diagnostic centres, exactly the cases our checks are built to catch. 36 of 80 could not be checked, mostly small facilities with no website. Two of the Unverified that did offer dialysis were heart hospitals, so we relaxed that rule.

## Demo stories

**Thanjavur, dialysis (PIN 613001).** Thanjavur ranks 7th highest of 706 districts for high blood sugar in men, a leading cause of kidney failure. In our data the nearest Confirmed dialysis centre is about 143 km away, but 4 hospitals inside the district are Likely. Those four are worth a phone call before anyone travels 143 km. We say "in our data" on purpose: Thanjavur has a government medical college, so a gap here means missing evidence, not missing care.

**Gumla, dialysis (PIN 835207).** Gumla is a rural district with only 1 facility in our data. The nearest Confirmed dialysis is about 87 km away in Ranchi, and a Likely one is a little closer at 81 km. The tool shows both: the confirmed answer first, and the closer but less certain option right below it, clearly labelled. It never hides an option, and it never presents a guess as a fact.

**Aravind Eye Hospital, Hyderabad.** A plain keyword search recommends this eye hospital for dialysis, because its record holds text copied from Delhi government hospitals. Our ownership check flags 79 of its 149 sentences as belonging to other organisations, so it lands in Unverified with a warning. The blind web check confirmed it: Aravind does not offer dialysis. This is why we check that a record's text belongs to the facility before we trust it.

## What is built

- **The app** (a Databricks App): describe a need or pick one of 60 services, click the map or type a PIN code, and get facilities by tier then distance, each with quoted evidence, warnings, contact details and directions. A district panel adds public-health context from the national family health survey without changing the ranking.
- **The data behind it:** cleaned facility and sentence tables, a checked location for every facility that can be placed, a type for each facility, a service tag for every sentence, an ownership check for every record with enough text, and the verdict table the app reads. It can be rebuilt end to end from scripts.

## Trade-offs and limits

- **No ground truth.** We can review samples by hand, but we cannot measure accuracy across the whole dataset.
- **The ownership check over-flags.** In a review of 300 records, its "mostly foreign" calls were usually right, but its "partly foreign" calls often flagged renamed cities or a hospital's own branches.
- **Language models are not perfectly repeatable.** The same record can get slightly different flags on two runs.
- **Web text can be out of date.** A sentence proves that a website made a claim, not that the service runs today. Evidence is tied to a record's sources, not to a single page.
- **A fixed service list misses rare services.** We keep a suggested name for anything outside the list so gaps are visible.
