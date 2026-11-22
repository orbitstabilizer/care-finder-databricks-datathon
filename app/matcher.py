"""Map a user's free-text need onto service labels with ONE LLM call.

Only the typed text and the label list are sent (no location, nothing else). It maps
words to services; it gives no medical advice. Every returned label is validated
against the allowed list."""
import concurrent.futures as cf
import itertools
import json
import os
import re

from config import SERVICE_GROUPS, HIDDEN_SERVICES

ENDPOINT = os.getenv("SERVING_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct")
TIMEOUT_S = 10
ALLOWED = {s: n for g in SERVICE_GROUPS.values() for s, n in g if s not in HIDDEN_SERVICES}
_calls = itertools.count(1)
_pool = cf.ThreadPoolExecutor(max_workers=2)

PROMPT = """You map a person's words to hospital service labels. Do not give medical advice.
Labels (label: meaning):
{labels}

Text: "{text}"

Step 1. Classify the text:
- "service": it names a service or procedure (e.g. dialysis, MRI, C-section, knee replacement).
- "symptom": it describes a problem or symptom (e.g. "I can't jump", "chest pain", "my child has fever").
- "unclear": it is not a health need, or cannot be understood (gibberish, random words). Then return no
  options and confidence "low"; do not guess.
Step 2. Choose up to 3 labels from the list, each with a plain reason of at most 10 words
(e.g. "Joint or leg problem -> orthopaedic clinic").
For "symptom": order options least invasive first: outpatient_opd (clinic), physiotherapy_rehab,
diagnostics (imaging, lab) before any surgery label. A surgery label may only come after a non-surgical
one, unless the text explicitly asks for surgery. Confidence may not be "high" for a symptom.
Exactly one option has "fit": "best": the label that most specifically matches the text. Prefer a specific
medical specialty when the text points to one (e.g. arm numbness with breathlessness -> cardiology_medical,
sugar problem -> diabetes_endocrinology) over the generic outpatient_opd. List the best option first, then the
others; the others are "possible".
"emergency" is true only if the text suggests an urgent, possibly life-threatening situation. When it is
true, do not offer outpatient_opd or health_checkup_vaccination; include trauma_emergency (emergency
department) or icu_critical_care among the options, plus the matching specialty.

Return ONLY JSON, no other text:
{{"kind": "service" | "symptom" | "unclear", "options": [{{"service": "label", "reason": "...", "fit": "best" | "possible"}}], "confidence": "high" | "medium" | "low", "emergency": true | false}}"""

EMERGENCY_LABELS = {"trauma_emergency", "icu_critical_care", "ambulance"}
NOT_FOR_EMERGENCY = {"outpatient_opd", "health_checkup_vaccination"}
SURGICAL = {"general_surgery", "cardiac_surgery", "interventional_cardiology", "neurosurgery",
            "orthopedic_surgery", "joint_replacement", "spine_surgery", "eye_surgery", "transplant",
            "cosmetic_aesthetic", "cancer_surgery", "caesarean_section", "vascular_surgery"}
ASKS_SURGERY = re.compile(r"surg|operat|replace|transplant|c-?section|caesar|cesar|bypass|angioplast", re.I)


def _call(text: str) -> str:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
    labels = "\n".join(f"{s}: {n}" for s, n in ALLOWED.items())
    r = WorkspaceClient().serving_endpoints.query(
        name=ENDPOINT, temperature=0, max_tokens=350,
        messages=[ChatMessage(role=ChatMessageRole.USER,
                              content=PROMPT.format(labels=labels, text=text[:500]))])
    return r.choices[0].message.content


def _clean(d: dict, text: str) -> dict:
    kind = d.get("kind") if d.get("kind") in ("service", "symptom", "unclear") else "symptom"
    conf = d.get("confidence") if d.get("confidence") in ("high", "medium", "low") else "low"
    emergency = d.get("emergency") is True
    if kind == "unclear":
        # not understood: no guess at all (the page asks the person to describe the care they need)
        return {"kind": "unclear", "options": [], "services": [], "confidence": "low",
                "emergency": emergency, "error": None}
    opts, seen = [], set()
    for o in d.get("options") or []:
        if not isinstance(o, dict):
            continue
        s = o.get("service")
        if isinstance(s, str) and s in ALLOWED and s not in seen:
            seen.add(s)
            reason = " ".join(str(o.get("reason") or "").split()[:12])
            opts.append({"service": s, "reason": reason,
                         "fit": "best" if o.get("fit") == "best" else "possible"})
    if kind == "symptom":
        if conf == "high":
            conf = "medium"
        if not ASKS_SURGERY.search(text):
            # least invasive first: no surgery label before a non-surgical one
            non = [o for o in opts if o["service"] not in SURGICAL]
            sur = [o for o in opts if o["service"] in SURGICAL]
            if sur and not non:
                non = [{"service": "outpatient_opd", "reason": "Start with a clinic visit", "fit": "possible"}]
            opts = non + sur
            # a surgery label cannot be the best guess for a symptom unless surgery was asked for
            if any(o["fit"] == "best" and o["service"] in SURGICAL for o in opts) and non:
                for o in opts:
                    o["fit"] = "possible"
                non[0]["fit"] = "best"
    if emergency:
        # an emergency never gets a clinic or check-up option, and always gets emergency care
        had_best = any(o["fit"] == "best" and o["service"] in NOT_FOR_EMERGENCY for o in opts)
        opts = [o for o in opts if o["service"] not in NOT_FOR_EMERGENCY]
        if had_best:
            for o in opts:
                o["fit"] = "possible"
        if not any(o["service"] in EMERGENCY_LABELS for o in opts):
            opts.insert(1 if opts else 0, {"service": "trauma_emergency",
                                           "reason": "Urgent symptoms -> emergency department",
                                           "fit": "possible" if opts else "best"})
    elif not opts and kind == "symptom":
        opts = [{"service": "outpatient_opd", "reason": "Start with a clinic visit", "fit": "best"}]
    opts = opts[:3]
    if opts and not any(o["fit"] == "best" for o in opts):
        opts[0]["fit"] = "best"
    for o in opts[1:]:
        if o["fit"] == "best" and opts[0]["fit"] == "best":
            o["fit"] = "possible"
    return {"kind": kind, "options": opts, "services": [o["service"] for o in opts],
            "confidence": conf, "emergency": emergency, "error": None}


def match(text: str) -> dict:
    """{"kind", "options": [{service, reason, fit}], "services": [labels], "confidence", "emergency", "error"}"""
    n = next(_calls)
    print(f"MATCHER call n={n}", flush=True)
    empty = {"kind": "symptom", "options": [], "services": [], "confidence": "low", "emergency": False}
    try:
        raw = _pool.submit(_call, text).result(timeout=TIMEOUT_S)
        m = re.search(r"\{.*\}", raw or "", re.S)
        d = json.loads(m.group(0)) if m else {}
        return _clean(d, text)
    except cf.TimeoutError:
        print(f"MATCHER call n={n} timeout", flush=True)
        return {**empty, "error": "timeout"}
    except Exception as e:
        print(f"MATCHER call n={n} error {type(e).__name__}: {e}", flush=True)
        return {**empty, "error": type(e).__name__}
