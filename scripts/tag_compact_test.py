"""Step 2 side arm: compact prompt pa_compact_v1 vs full pa_single_v1 (and a full re-run)
on 500 sentences already tagged in chunk tp_single. Results only in workspace.vf.tag_compact_test
(never in sentence_tags)."""
import json, sys, time, textwrap
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tag_sentences as t
from pilot_a_tagger import SERVICES, PROMPT_SINGLE

COMPACT_VERSION = "pa_compact_v1"
COMPACT = textwrap.dedent(f"""\
    Label one snippet from an Indian hospital website: which clinical services is it
    evidence that this facility offers?

    Labels: {", ".join(SERVICES)}

    is_claim false (services [], strength "na") unless it asserts this facility offers a
    service: research, statistics, biographies, fees, dates, buildings, awards, education
    and training are false. If no label fits use other_clinical plus "suggested_name"
    (max 4 words). Teeth/orthodontics = dental. Emergency/casualty = trauma_emergency.
    strength: "explicit" = concrete capacity (beds, machines, units); "stated" = named
    plainly; "weak" = implied, bare department list or staffing.
    Use only listed labels. Reply ONLY JSON:
    {{"is_claim":true|false,"services":[...],"strength":"explicit"|"stated"|"weak"|"na","suggested_name":"..."}}

    Snippet:
    """)

def words(s): return len(s.split())

def arm(name, prompt):
    done = t.run("arm_done", f"SELECT count(*) FROM {t.VF}.tag_compact_test WHERE arm = ?", [name])[0][0]
    if done:  # already ran: take the statement time from the local log
        for line in open(t.LOGDIR / "statements.jsonl"):
            r = json.loads(line)
            if r["label"] == name:
                secs = r["seconds"]
        return secs
    t0 = time.time()
    t.run(name, f"""
        INSERT INTO {t.VF}.tag_compact_test
        SELECT s.sentence_id, '{name}', ai_query('{t.MODEL}', concat(?, q.example_sentence),
               modelParameters => named_struct('temperature', 0.0), failOnError => false),
               current_timestamp()
        FROM {t.VF}.tag_compact_sample s JOIN {t.VF}.st_queue q USING (sentence_id)""",
        [prompt], fetch=False)
    return time.time() - t0

def main():
    t.run("create_tct", f"CREATE TABLE IF NOT EXISTS {t.VF}.tag_compact_test (sentence_id STRING, "
          "arm STRING, resp STRUCT<result: STRING, errorMessage: STRING>, created_at TIMESTAMP)",
          fetch=False)
    t.run("upsert_compact_prompt", f"""MERGE INTO {t.VF}.pa_prompt p USING (SELECT ? v, ? m, 0.0 tmp, ? x) s
          ON p.prompt_version = s.v WHEN NOT MATCHED THEN INSERT
          (prompt_version, model, temperature, prompt, created_at)
          VALUES (s.v, s.m, s.tmp, s.x, current_timestamp())""",
          [COMPACT_VERSION, t.MODEL, COMPACT], fetch=False)
    t.run("create_sample", f"""CREATE OR REPLACE TABLE {t.VF}.tag_compact_sample AS
          SELECT m.sentence_id FROM {t.VF}.st_chunk_members m JOIN {t.VF}.st_queue q USING (sentence_id)
          WHERE m.chunk_id = 'tp_single' ORDER BY q.ord LIMIT 500""", fetch=False)
    secs = {"compact": arm("compact", COMPACT), "full_rerun": arm("full_rerun", PROMPT_SINGLE)}
    raw = t.run("read", f"SELECT arm, sentence_id, resp.result, resp.errorMessage FROM {t.VF}.tag_compact_test")
    base = t.run("read_base", f"""SELECT t.sentence_id, t.is_claim, t.services, t.failed
          FROM {t.VF}.sentence_tags t JOIN {t.VF}.tag_compact_sample s USING (sentence_id)""")
    full = {sid: (c, frozenset([] if sv is None else list(sv)), f) for sid, c, sv, f in base}
    res = {"words_full": words(PROMPT_SINGLE), "words_compact": words(COMPACT),
           "chars_full": len(PROMPT_SINGLE), "chars_compact": len(COMPACT)}
    for a in ("compact", "full_rerun"):
        rows = {sid: t.validate(r, e) for aa, sid, r, e in raw if aa == a}
        fails = Counter(f for _, f, _ in rows.values() if f)
        errs = sum(1 for aa, _, _, e in raw if aa == a and e)
        both = [s for s, (o, f, _) in rows.items() if not f and not full[s][2]]
        diff = sum(1 for s in both if rows[s][0]["is_claim"] != full[s][0]
                   or frozenset(rows[s][0]["services"]) != full[s][1])
        diff_claim = sum(1 for s in both if rows[s][0]["is_claim"] != full[s][0])
        res[a] = {"seconds": round(secs[a], 1), "rate": round(len(rows) / secs[a], 2),
                  "rows": len(rows), "failed": dict(fails), "error_messages": errs,
                  "compared": len(both), "differ_vs_full": diff,
                  "differ_pct": round(100 * diff / len(both), 1), "is_claim_differ": diff_claim}
    t.log("compact_test", res)

if __name__ == "__main__":
    main()
