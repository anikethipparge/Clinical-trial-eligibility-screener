"""Run accuracy test from terminal:  python evaluate.py"""
import json
from src.trials import load_trials
from src.evaluation import run_evaluation

trials = {t["nct_id"]: t for t in load_trials()}
patients = {p["id"]: p["note"] for p in json.load(open("data/patients.json", encoding="utf-8"))}
out = run_evaluation(trials, patients, progress=lambda i, n: print(f"  screened {i}/{n}", end="\r"))
print()
for r in out["rows"]:
    mark = "OK " if r["correct"] else "XX "
    print(f"{mark}{r['patient_id']} x {r['nct_id']:<15} expected={r['expected']:<13} got={r['predicted']}")
print(f"\nACCURACY: {out['accuracy']:.1%}  ({out['correct']}/{out['n']})")
print("Per trial:", out["per_trial"])
print("Saved -> outputs/eval_results.csv")
