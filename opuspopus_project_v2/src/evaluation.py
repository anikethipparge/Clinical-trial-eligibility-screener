import csv, json
from collections import defaultdict
from src import config
from src.screener import screen, extract_facts

RESULT_FILE = config.OUTPUTS / "eval_results.json"
LABELS = ["ELIGIBLE", "NOT ELIGIBLE", "NEEDS REVIEW"]


def run_evaluation(trials_by_id, patients_by_id, progress=None):
    with open(config.DATA / "ground_truth.csv", newline="", encoding="utf-8") as f:
        gt = list(csv.DictReader(f))
    facts_cache, rows = {}, []
    for i, r in enumerate(gt):
        pid, nct = r["patient_id"], r["nct_id"]
        note = patients_by_id[pid]
        if pid not in facts_cache:
            facts_cache[pid] = extract_facts(note)
        res = screen(note, trials_by_id[nct], facts_cache[pid])
        rows.append({"patient_id": pid, "nct_id": nct, "expected": r["expected"],
                     "predicted": res["decision"], "correct": r["expected"] == res["decision"],
                     "why_expected": r.get("why", ""), "model_summary": res["summary"]})
        if progress:
            progress(i + 1, len(gt))
    n = len(rows) or 1
    confusion = {e: {p: sum(1 for x in rows if x["expected"] == e and x["predicted"] == p) for p in LABELS} for e in LABELS}
    groups = defaultdict(list)
    for x in rows:
        groups[x["nct_id"]].append(x["correct"])
    per_trial = {k: round(sum(v) / len(v), 3) for k, v in groups.items()}
    correct = sum(x["correct"] for x in rows)
    out = {"accuracy": round(correct / n, 4), "n": len(rows), "correct": correct,
           "confusion": confusion, "per_trial": per_trial, "rows": rows}
    RESULT_FILE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    with open(config.OUTPUTS / "eval_results.csv", "w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    return out


def last_evaluation():
    return json.loads(RESULT_FILE.read_text(encoding="utf-8")) if RESULT_FILE.exists() else None
