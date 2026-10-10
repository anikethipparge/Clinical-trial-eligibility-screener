"""Download real recruiting trials from ClinicalTrials.gov:  python fetch_trials.py"""
from src.trials import fetch_live, DEFAULT_CONDITIONS

trials = fetch_live(DEFAULT_CONDITIONS, per_condition=15)
n = len(trials) or 1
inc = sum(len(t["inclusion"]) for t in trials)
exc = sum(len(t["exclusion"]) for t in trials)
print(f"Fetched {len(trials)} real trials for: {', '.join(DEFAULT_CONDITIONS)}")
print(f"Total criteria (rules): {inc + exc}  | inclusion {inc}, exclusion {exc}")
print(f"Average per trial: {inc/n:.1f} inclusion, {exc/n:.1f} exclusion")
print("Saved -> data/trials_live.json")
