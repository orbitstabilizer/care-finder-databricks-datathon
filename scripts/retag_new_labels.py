"""Re-tag other_clinical / unlabelled-claim sentences with prompt pa_single_v2 (58 labels).

Usage (py13 python):
  python scripts/retag_new_labels.py prompt   # build pa_single_v2 from pa_single_v1, save to pa_prompt
  python scripts/retag_new_labels.py backup   # sentence_tags_backup_v1 (rows to re-tag, v1 state)
  python scripts/retag_new_labels.py test     # 500 sentences (fixed seed) -> retag_v2_test, gate 95% valid
  python scripts/retag_new_labels.py full     # the rest, chunked x4 concurrent, resumable; one retry pass
                                              # for invalid responses; then MERGE into sentence_tags
  python scripts/retag_new_labels.py merge    # only the MERGE step (idempotent)

pa_single_v2 = pa_single_v1 with ONLY the allowed-label list changed: 11 labels added
(reports/new_service_labels_proposal.md + pain_management, vascular_surgery, cardiology_medical), one "Note:" line per new label in
the style of the existing notes, and the rule that general/internal medicine and fever
treatment are outpatient_opd. Same model, temperature 0, max_tokens 300, one sentence per
ai_query call, failOnError => false, same validation (scripts/tag_sentences.py validate).

Scope: sentence_tags rows, not failed, with services containing other_clinical OR
unlabelled_claim = true (29,950), PLUS the cardiac set: rows tagged cardiac_surgery or
interventional_cardiology whose sentence matches CARDIAC_TEST_RE as whole words, and every row
tagged cardiac_surgery with strength 'weak'. Their v1 rows are kept in
workspace.vf.sentence_tags_backup_v1. Rows whose v2 response stays invalid after one retry keep
their v1 row. Credit guard as in tag_sentences.py: stop at once, write nothing for the chunk.

Tables (workspace.vf): retag_v2_members (chunk_id, sentence_id, part), retag_v2_raw (raw
responses), retag_v2_test (parsed test results), retag_v2_results (parsed results, all rows).
Local log: reports/retag_v2/.
"""
import concurrent.futures as cf
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tag_sentences as ts  # noqa: E402
from build_lookups import NEW_SERVICES_V2  # noqa: E402
from pilot_a_tagger import SERVICES as SERVICES_V1  # noqa: E402

VF = ts.VF
MODEL = ts.MODEL
V1, V2 = "pa_single_v1", "pa_single_v2"
SEED = "retag_v2_seed_1"
TEST_N = 500
CHUNK = 10_000
PARTS = 4
GATE = 0.95
ALLOWED_V2 = set(SERVICES_V1) | set(NEW_SERVICES_V2)
SCOPE = ("NOT coalesce(failed, false) AND (array_contains(services, 'other_clinical') "
         "OR coalesce(unlabelled_claim, false))")

CARDIAC_TEST_RE = r"(?i)\b(echo|echocardiography|ecg|ekg|holter|tmt|treadmill|stress test|doppler)\b"
CARDIAC_SCOPE = (f"NOT coalesce(failed, false) AND sentence_id IN (SELECT t.sentence_id FROM {VF}.sentence_tags t "
                 f"JOIN {VF}.distinct_sentences d USING (sentence_id) WHERE "
                 "(arrays_overlap(t.services, array('cardiac_surgery', 'interventional_cardiology')) "
                 "AND d.example_sentence RLIKE ?) "
                 "OR (array_contains(t.services, 'cardiac_surgery') AND t.strength = 'weak'))")

ts.LOGDIR = ts.ROOT / "reports" / "retag_v2"
ts.ALLOWED = ALLOWED_V2          # validate() reads this module global
ts.PROMPT_VERSION = V2           # to_row() stamps this
run, log = ts.run, ts.log

LABEL_NOTES = """\
Note: urology consultations, kidney and urinary stone treatment (lithotripsy, PCNL, URS,
RIRS), prostate treatment (TURP, HoLEP), cystoscopy, uroflowmetry, circumcision and
andrology are "urology", NOT dialysis or nephrology_renal.
Note: diabetes clinics and diabetes management, insulin pumps, diabetic foot care, thyroid
and hormone (endocrine) treatment are "diabetes_endocrinology". A bare blood sugar test in a
lab list is "laboratory_pathology".
Note: health check-up packages, vaccination and immunisation, cancer screening programmes
and visa or employment medical examinations are "health_checkup_vaccination". A single lab
test is "laboratory_pathology"; antenatal check-ups are "obstetrics_maternity".
Note: echocardiography / 2D echo, treadmill or stress test (TMT), Holter monitoring, EECP and
cardiac Doppler tests are "cardiac_diagnostics". ECG mentioned alone is NOT
cardiac_diagnostics. Angioplasty, angiography and cath lab are "interventional_cardiology".
Note: general heart care - cardiology departments, cardiologist consultations and heart
clinics where no surgery, catheter procedure or heart test is named - is "cardiology_medical".
Open-heart, bypass and valve surgery are "cardiac_surgery"; angiography, angioplasty, stents
and pacemakers are "interventional_cardiology"; echo, ECG, TMT and Holter tests are
"cardiac_diagnostics".
Note: non-surgical brain and nerve care - neurology consultations, epilepsy, headache and
migraine, vertigo, Parkinson's, dementia, neuropathy, and EEG / EMG / nerve conduction
offered as a test service - is "neurology". A bare "EEG machine" line is NOT neurology.
Brain and spine operations are "neurosurgery"; stroke units are "stroke_care".
Note: Ayurveda (including Panchakarma, Shirodhara, Kshar Sutra), homeopathy, naturopathy,
Unani, Siddha and yoga therapy are "ayush_traditional_medicine". An Ayurvedic or homeopathic
treatment for a condition gets ONLY "ayush_traditional_medicine".
Note: non-pregnancy gynaecology - hysteroscopy, colposcopy, Pap smear, PCOS/PCOD, fibroids,
endometriosis, hysterectomy, menopause, contraception, tubectomy, MTP - is "gynecology".
Pregnancy, antenatal care and delivery keep the obstetric labels; IVF is "infertility_ivf".
Note: piles / haemorrhoids, anal fistula, fissure, pilonidal sinus and laser proctology are
"proctology". An AV fistula for dialysis access is "vascular_surgery", NOT proctology.
Note: varicose vein treatment (laser, sclerotherapy, surgery), peripheral arterial surgery
and AV fistula creation for dialysis access are "vascular_surgery". Angioplasty and stents of
the heart are "interventional_cardiology".
Note: pain clinics, nerve blocks and interventional pain procedures for back, joint or
chronic pain are "pain_management".
Note: general medicine, internal medicine, fever and infection treatment are
"outpatient_opd".
"""


def build_prompt_v2(v1: str) -> str:
    old = "nephrology_renal, gastroenterology, other_clinical\n"
    assert v1.count(old) == 1
    new = ("nephrology_renal, gastroenterology, " + ", ".join(NEW_SERVICES_V2)
           + ", other_clinical\n\n" + LABEL_NOTES)
    return v1.replace(old, new)


def load_prompt(version=V2) -> str:
    rows = run("read_prompt", f"SELECT prompt, model FROM {VF}.pa_prompt WHERE prompt_version = ?",
               [version])
    assert rows and rows[0][1] == MODEL, f"{version} missing or wrong model"
    return rows[0][0]


def cmd_prompt():
    v1 = load_prompt(V1)
    v2 = build_prompt_v2(v1)
    have = run("v2_exists", f"SELECT prompt FROM {VF}.pa_prompt WHERE prompt_version = ?", [V2])
    if have and have[0][0] == v2:
        print("pa_single_v2 already stored, identical")
        return
    if have:  # label list extended before any v2 row was written
        used = run("v2_used", f"SELECT count(*) FROM {VF}.sentence_tags WHERE prompt_version = ?", [V2])[0][0]
        assert not used, "pa_single_v2 already used in sentence_tags; make a new version"
        run("v2_delete", f"DELETE FROM {VF}.pa_prompt WHERE prompt_version = ?", [V2], fetch=False)
    run("v2_insert", f"INSERT INTO {VF}.pa_prompt (prompt_version, model, temperature, prompt, created_at) "
        "VALUES (?, ?, 0.0, ?, current_timestamp())", [V2, MODEL, v2], fetch=False)
    print(f"stored pa_single_v2 ({len(v2)} chars)")


def cmd_backup():
    exists = run("bk_exists", "SELECT count(*) FROM workspace.information_schema.tables "
                 "WHERE table_schema = 'vf' AND table_name = 'sentence_tags_backup_v1'")[0][0]
    if not exists:
        run("bk_create", f"""CREATE TABLE {VF}.sentence_tags_backup_v1
            COMMENT 'v1 (pa_single_v1) rows of workspace.vf.sentence_tags that were re-tagged with pa_single_v2 by scripts/retag_new_labels.py: not failed AND (services contains other_clinical OR unlabelled_claim). Snapshot before the MERGE.'
            AS SELECT * FROM {VF}.sentence_tags WHERE {SCOPE}""", fetch=False)
    # cardiac set (added later): append rows not yet in the backup, still in v1 state
    run("bk_cardiac", f"""INSERT INTO {VF}.sentence_tags_backup_v1
        SELECT * FROM {VF}.sentence_tags WHERE prompt_version = '{V1}' AND {CARDIAC_SCOPE}
          AND sentence_id NOT IN (SELECT sentence_id FROM {VF}.sentence_tags_backup_v1)""",
        [CARDIAC_TEST_RE], fetch=False)
    n_c = run("bk_cardiac_n", f"SELECT count(*) FROM {VF}.sentence_tags_backup_v1 WHERE {CARDIAC_SCOPE}",
              [CARDIAC_TEST_RE])[0][0]
    print("cardiac set rows in backup:", n_c)
    n = run("bk_count", f"SELECT count(*), count(DISTINCT sentence_id) FROM {VF}.sentence_tags_backup_v1")[0]
    print("backup rows:", tuple(n))
    return n[0]


def ensure_tables():
    run("mk_members", f"""CREATE TABLE IF NOT EXISTS {VF}.retag_v2_members (
        chunk_id STRING, sentence_id STRING, part INT, created_at TIMESTAMP)""", fetch=False)
    run("mk_raw", f"""CREATE TABLE IF NOT EXISTS {VF}.retag_v2_raw (
        sentence_id STRING, chunk_id STRING, attempt INT, part INT,
        resp STRUCT<result: STRING, errorMessage: STRING>, created_at TIMESTAMP)""", fetch=False)
    for t in ("retag_v2_test", "retag_v2_results"):
        run(f"mk_{t}", f"""CREATE TABLE IF NOT EXISTS {VF}.{t} (
            sentence_id STRING, is_claim BOOLEAN, services ARRAY<STRING>, strength STRING,
            suggested_name STRING, prompt_version STRING, chunk_id STRING, failed BOOLEAN,
            fail_reason STRING, unlabelled_claim BOOLEAN, tagged_at TIMESTAMP)""", fetch=False)


def add_members(chunk_id: str, n: int, order_sql: str):
    have = run("mem_have", f"SELECT count(*) FROM {VF}.retag_v2_members WHERE chunk_id = ?",
               [chunk_id])[0][0]
    if have:
        return have
    run(f"{chunk_id}_members", f"""
        INSERT INTO {VF}.retag_v2_members
        SELECT ?, sentence_id, CAST(pmod(rn - 1, {PARTS}) AS INT), current_timestamp()
        FROM (SELECT b.sentence_id, row_number() OVER (ORDER BY {order_sql}) rn
              FROM {VF}.sentence_tags_backup_v1 b
              WHERE NOT EXISTS (SELECT 1 FROM {VF}.retag_v2_members m WHERE m.sentence_id = b.sentence_id)
              ORDER BY {order_sql} LIMIT {n})""", [chunk_id], fetch=False)
    return run("mem_count", f"SELECT count(*) FROM {VF}.retag_v2_members WHERE chunk_id = ?",
               [chunk_id])[0][0]


def query_part(prompt, chunk_id, attempt, part, extra=""):
    part_sql = "" if part is None else f"AND m.part = {int(part)}"
    run(f"{chunk_id}_a{attempt}_p{part}", f"""
        INSERT INTO {VF}.retag_v2_raw
        SELECT m.sentence_id, m.chunk_id, {attempt}, m.part,
               ai_query('{MODEL}', concat(?, q.example_sentence),
                        modelParameters => named_struct('max_tokens', 300, 'temperature', 0.0),
                        failOnError => false),
               current_timestamp()
        FROM {VF}.retag_v2_members m JOIN {VF}.st_queue q USING (sentence_id)
        WHERE m.chunk_id = ? {part_sql} {extra}""", [prompt, chunk_id], fetch=False)


def query_chunk(prompt, chunk_id):
    """Attempt 1 for every part that lacks complete, error-free raw rows (resumable)."""
    stat = run("raw_parts", f"""
        SELECT m.part, count(*), count(r.sentence_id), count(r.resp.errorMessage)
        FROM {VF}.retag_v2_members m
        LEFT JOIN {VF}.retag_v2_raw r
          ON r.sentence_id = m.sentence_id AND r.chunk_id = m.chunk_id AND r.attempt = 1
        WHERE m.chunk_id = ? GROUP BY m.part""", [chunk_id])
    todo = []
    for p, n_mem, n_raw, n_err in stat:
        if n_raw == n_mem and n_err == 0:
            continue
        if n_raw:
            run("raw_reset", f"DELETE FROM {VF}.retag_v2_raw WHERE chunk_id = ? AND attempt = 1 "
                f"AND part = {int(p)}", [chunk_id], fetch=False)
        todo.append(p)
    t0 = time.time()
    if todo:
        with cf.ThreadPoolExecutor(PARTS) as ex:
            list(ex.map(lambda p: query_part(prompt, chunk_id, 1, p), todo))
    return time.time() - t0, len(todo)


def read_raw(chunk_id, attempt):
    rows = run(f"{chunk_id}_read{attempt}", f"""SELECT sentence_id, resp.result, resp.errorMessage
        FROM {VF}.retag_v2_raw WHERE chunk_id = ? AND attempt = {attempt}""", [chunk_id])
    return {sid: (res, err) for sid, res, err in rows}


def write_rows(table, rows):
    for i in range(0, len(rows), ts.WRITE_BATCH):
        payload = json.dumps(rows[i: i + ts.WRITE_BATCH], ensure_ascii=False)
        run(f"write_{table}", f"""
            INSERT INTO {VF}.{table}
            SELECT sentence_id, is_claim, services, strength, suggested_name, prompt_version,
                   chunk_id, failed, fail_reason, unlabelled_claim, current_timestamp()
            FROM (SELECT inline(from_json(?, 'array<struct<sentence_id:string,
                  is_claim:boolean,services:array<string>,strength:string,
                  suggested_name:string,prompt_version:string,chunk_id:string,
                  failed:boolean,fail_reason:string,unlabelled_claim:boolean>>')))""",
            [payload], fetch=False)


def cmd_test():
    ensure_tables()
    prompt = load_prompt()
    n = add_members("v2_test", TEST_N, f"xxhash64(concat('{SEED}', b.sentence_id))")
    secs, _ = query_chunk(prompt, "v2_test")
    raw = read_raw("v2_test", 1)
    ts.credit_check("v2_test", [e for _, e in raw.values()])
    res = {sid: ts.validate(r, e) for sid, (r, e) in raw.items()}
    rows = [ts.to_row(sid, "v2_test", o, f) for sid, (o, f, _) in res.items()]
    done = run("test_have", f"SELECT count(*) FROM {VF}.retag_v2_test")[0][0]
    if not done:
        write_rows("retag_v2_test", rows)
    valid = sum(not r["failed"] for r in rows)
    share = valid / len(rows)
    svc = Counter(s for r in rows if not r["failed"] for s in r["services"])
    stats = {"members": n, "responses": len(rows), "valid": valid, "valid_share": round(share, 4),
             "gate": GATE, "passed": share >= GATE, "seconds": round(secs, 1),
             "fail_reasons": dict(Counter(r["fail_reason"] for r in rows if r["failed"])),
             "is_claim_false": sum(1 for r in rows if not r["failed"] and r["is_claim"] is False),
             "unlabelled_claim": sum(r["unlabelled_claim"] for r in rows),
             "labels": dict(svc.most_common())}
    log("test", stats)
    return stats


def cmd_full():
    ensure_tables()
    prompt = load_prompt()
    test = run("test_done", f"SELECT count(*) FROM {VF}.retag_v2_test")[0][0]
    assert test, "run the test first"
    total = run("bk_n", f"SELECT count(*) FROM {VF}.sentence_tags_backup_v1")[0][0]
    k = 1
    while True:
        cid = f"v2_c{k:02d}"
        left = run("unassigned", f"""SELECT count(*) FROM {VF}.sentence_tags_backup_v1 b
            WHERE NOT EXISTS (SELECT 1 FROM {VF}.retag_v2_members m WHERE m.sentence_id = b.sentence_id)""")[0][0]
        have = run("mem_have", f"SELECT count(*) FROM {VF}.retag_v2_members WHERE chunk_id = ?", [cid])[0][0]
        if not have and not left:
            break
        n = add_members(cid, CHUNK, "b.sentence_id")
        secs, nparts = query_chunk(prompt, cid)
        raw = read_raw(cid, 1)
        ts.credit_check(cid, [e for _, e in raw.values()])
        log("chunks", {"chunk_id": cid, "members": n, "raw": len(raw), "parts_queried": nparts,
                       "seconds": round(secs, 1),
                       "per_s": round(len(raw) / secs, 1) if secs > 1 else None,
                       "invalid_first": sum(1 for r, e in raw.values() if ts.validate(r, e)[1])})
        k += 1
    # one retry pass for every invalid attempt-1 response (test chunk included), one statement
    chunks = [c for (c,) in run("chunks", f"SELECT DISTINCT chunk_id FROM {VF}.retag_v2_members ORDER BY 1")]
    first = {}
    for c in chunks:
        for sid, (r, e) in read_raw(c, 1).items():
            first[sid] = (c, ts.validate(r, e))
    bad = [sid for sid, (_, v) in first.items() if v[1]]
    have2 = run("raw2", f"SELECT count(*), count(resp.errorMessage) FROM {VF}.retag_v2_raw WHERE attempt = 2")[0]
    if bad and (not have2[0] or have2[1]):
        run("raw2_reset", f"DELETE FROM {VF}.retag_v2_raw WHERE attempt = 2", fetch=False)
        run("retry_members", f"DELETE FROM {VF}.retag_v2_members WHERE chunk_id = 'v2_retry'", fetch=False)
        vals = ",".join(f"('{s}')" for s in bad)
        run("retry_members_ins", f"""INSERT INTO {VF}.retag_v2_members
            SELECT 'v2_retry', s, 0, current_timestamp() FROM VALUES {vals} AS v(s)""", fetch=False)
        t0 = time.time()
        query_part(prompt, "v2_retry", 2, None)
        log("chunks", {"chunk_id": "v2_retry", "rows": len(bad), "seconds": round(time.time() - t0, 1)})
    raw2 = read_raw("v2_retry", 2) if bad else {}
    ts.credit_check("v2_retry", [e for _, e in raw2.values()])
    rows = []
    for sid, (c, (o, f, _)) in first.items():
        if f and sid in raw2:
            o, f, _ = ts.validate(*raw2[sid])
            c = "v2_retry" if not f else c
        rows.append(ts.to_row(sid, c, o, f))
    run("results_reset", f"TRUNCATE TABLE {VF}.retag_v2_results", fetch=False)
    write_rows("retag_v2_results", rows)
    log("full", {"backup_rows": total, "results": len(rows), "invalid_first": len(bad),
                 "failed_after_retry": sum(r["failed"] for r in rows),
                 "fail_reasons": dict(Counter(r["fail_reason"] for r in rows if r["failed"]))})
    cmd_merge()


def cmd_merge():
    run("merge", f"""
        MERGE INTO {VF}.sentence_tags t
        USING (SELECT * FROM {VF}.retag_v2_results WHERE NOT failed) s
        ON t.sentence_id = s.sentence_id
        WHEN MATCHED AND t.prompt_version = '{V1}' THEN UPDATE SET
          is_claim = s.is_claim, services = s.services, strength = s.strength,
          suggested_name = s.suggested_name, prompt_version = '{V2}', chunk_id = s.chunk_id,
          failed = false, fail_reason = NULL, tagged_at = current_timestamp(),
          unlabelled_claim = s.unlabelled_claim""", fetch=False)
    r = run("merge_check", f"""SELECT prompt_version, count(*) FROM {VF}.sentence_tags
        WHERE sentence_id IN (SELECT sentence_id FROM {VF}.sentence_tags_backup_v1) GROUP BY 1""")
    log("merge", {"by_prompt_version": {p: n for p, n in r}})
    run("comment_pv", f"ALTER TABLE {VF}.sentence_tags ALTER COLUMN prompt_version COMMENT ?",
        ["pa_single_v1 (LLM, 49 labels), pa_single_v2 (LLM, 58 labels: re-tag of v1 rows that were "
         "other_clinical or unlabelled_claim, scripts/retag_new_labels.py; v1 rows in "
         "sentence_tags_backup_v1), or rule_dental_only (rule)."], fetch=False)
    run("comment_svc", f"ALTER TABLE {VF}.sentence_tags ALTER COLUMN services COMMENT ?",
        ["Model labels: 49-label list for pa_single_v1 rows, 58-label list for pa_single_v2 rows "
         "(exact prompts in workspace.vf.pa_prompt); [] when is_claim false. Rule rows: [dental]. "
         "NULL when failed."], fetch=False)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"prompt": cmd_prompt, "backup": cmd_backup, "test": cmd_test, "full": cmd_full,
          "merge": cmd_merge}.get(cmd)
    if not fn:
        sys.exit(__doc__)
    try:
        fn()
    except ts.CreditsExhausted as e:
        msg = f"CREDITS EXHAUSTED, TOP UP NEEDED {ts.now()}\nerror: {e}\nResume: python scripts/retag_new_labels.py {cmd}\n"
        print(msg, flush=True)
        ts.LOGDIR.mkdir(parents=True, exist_ok=True)
        (ts.LOGDIR / "CREDITS_EXHAUSTED.txt").write_text(msg)
        sys.exit(2)


if __name__ == "__main__":
    main()
