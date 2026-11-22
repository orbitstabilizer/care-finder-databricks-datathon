# Brief for the conversation agent

You are going to brainstorm a plan with me (the user) for a weekend datathon. We have not
agreed a method yet — that is what this conversation is for. Keep answers short and
conversational.

## How we work together

You have no access to the code or the data. A second Claude, running in Claude Code on my
laptop, does. It can query the data and can hand larger jobs to other agents.

When you need a fact from the data, or want something tested, **write a prompt for that
Claude** and I will paste it over and paste the answer back. Write the prompt so it
stands on its own: say what you want to know and what form the answer should take. Ask
for a measurement, not an opinion. Small questions are cheap, so ask instead of guessing.

## The task

CMU Datathon, Fall 2026, with the Virtue Foundation and Databricks.

Build something that takes **a service** (dialysis, emergency C-section, NICU, cardiac
surgery, MRI, burn care) and **a location** (city, district, PIN code or coordinates) and
returns the **best facility options, with an evidence-based explanation** of each.

The one rule is to show the reasoning. For every recommendation we must be able to answer:

1. **Why this facility?** What evidence says it exists, offers the service, and is the
   best choice for this location?
2. **How did we decide?** What logic or scoring turned 10,000 records into this answer,
   and what did we trade off?

It must run on Databricks Free Edition, use the provided dataset, work for a non-technical
user (a health worker, an NGO coordinator, a district planner), quote the underlying
facility text for any important claim, and show uncertainty instead of presenting weak
evidence as fact. The format is our choice: an app, a dashboard, a Genie space, a
notebook, an agent, or a mix.

## The dataset

Three tables, about 20 MB in total. Small.

**`facilities`** — about 10,000 healthcare facilities in India, 51 columns. This is the
main table. It was built by scraping websites and extracting facts with an LLM, so every
field is a claim, not a verified fact. Per facility:

- Name, address, city, state, postcode, latitude and longitude. 99% have coordinates.
  State and city names are messy (254 different "states"; India has 37).
- `specialties` — a clean list of departments from a fixed vocabulary, such as
  `nephrology`, `cardiology`, `gynecologyAndObstetrics`, `dentistry`.
- `procedure`, `capability`, `equipment` — each a list of free-text sentences, such as
  *"20-bed Dialysis Unit with 10 machines"* or *"Has a 3 Tesla MRI scanner"*. This is
  where the actual services are. About 450,000 sentences in total, averaging 43
  characters. Many are not service claims at all: doctor biographies, fees, founding
  dates, research results.
- `description` — a short free-text paragraph.
- Number of doctors, bed capacity, year established — mostly missing (25–48% filled).
- `source_urls` — the web pages the record came from, about 17 per facility. A sentence
  cannot be traced to the specific page it came from.

**`india_post_pincode_directory`** — 165,000 post offices with PIN code, district, state
and coordinates. Lets us turn a PIN code into a point on the map.

**`nfhs_5_district_health_indicators`** — 706 districts with 109 public-health
indicators (maternal health, vaccination, anaemia and so on). Optional context.

## What we already know about the data

- **A department is not a service.** 2,153 facilities list `nephrology`; that does not
  tell us which ones do dialysis. Services only appear in the free-text sentences.
- **Some records mix sentences from different hospitals.** The record for *Aravind Eye
  Hospital*, Hyderabad contains *"Dialysis treatment is provided via a 20-bed Dialysis
  Unit"* — text that belongs to another hospital. A plain text search for "dialysis"
  therefore recommends an eye hospital. We do not know how common this is overall. For
  dialysis: 1,036 facilities mention it, and 205 of those do not list nephrology.
- Many sentences name the hospital they are about (*"…offered at Fortis Hospital,
  Anandapur"*), which might let us catch sentences sitting in the wrong record.
- 148 facilities have no sentences at all in those three columns.
- 4,190 facilities are dental. We have not decided whether to keep them.

## What we can use

- **Databricks Free Edition.** One small SQL warehouse, and that cannot be made bigger.
- **LLM calls from SQL** (`ai_query`, `ai_classify`) with hosted open models, including
  Llama 3.3 70B and embedding models. Measured speed: about 17 sentences per second when
  25 sentences go in one call. Labelling every relevant sentence would take roughly an
  hour.
- **Databricks Apps** (we can host a small web app), **Vector Search**, **Genie**
  (natural-language questions over tables), dashboards, notebooks and jobs.
- The Claude in Claude Code reaches Databricks through two MCP servers: one runs SQL,
  one asks Genie questions.

## Where the thinking stands

Nothing is built. Two things were tried, and both can be changed:

- A prompt that labels each sentence with the services it is evidence for (from a fixed
  list of about 48), marks sentences that are not service claims, and grades the
  evidence as explicit, stated or weak. It gave clean results on 40 random sentences.
- An idea for ranking: sort facilities into Confirmed, Likely and Unverified first, then
  by distance within each group, instead of blending everything into one score.

I leaned towards a web app, with an LLM labelling pass done once and stored in a table.
Treat those as starting points, not decisions.
