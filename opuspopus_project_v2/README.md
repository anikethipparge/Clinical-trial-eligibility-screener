# OpusPopus TrialMatch – Clinical Trial Eligibility Screener

A single-agent GenAI system for the TCS Technology Day Life Sciences problem. It takes in synthetic patient notes and clinical trial criteria (live from ClinicalTrials.gov), then gives an **Eligible / Not Eligible / Needs Review** decision for each trial, with a criterion-by-criterion checklist, quoted evidence and a plain-English rationale.

## Architecture
```
Patient note ──► [1] LLM fact extraction (age, sex, diagnoses, labs, meds, pregnancy)
      │
      └──► [2] RAG retriever over the trial library ──► top-k relevant trials
                                                          │
ClinicalTrials.gov API v2 ──► criteria text split into rules ┤
                                                          ▼
          [3] Rule engine (Python): age, sex, pregnancy – deterministic
          [4] LLM reasoner: each criterion → MET / NOT_MET / UNKNOWN + evidence
          [5] Decision logic (Python):
                failed inclusion OR triggered exclusion → NOT ELIGIBLE
                missing data for an inclusion          → NEEDS REVIEW
                otherwise                              → ELIGIBLE
          [6] LLM explanation for the clinical coordinator
```
**Why this design:** LLMs understand messy medical language but are unreliable at final decisions. The LLM judges each criterion. Python handles the structured rules and the final decision, so results are auditable and repeatable (temperature 0 + cache).

**Why RAG and not fine-tuning:** eligibility rules are different for every trial and change often. Retrieval adds new trials instantly without retraining, and every decision traces back to the exact criterion text.

**RAG engine:** uses gte embeddings when `sentence-transformers` is installed; otherwise a built-in TF-IDF retriever written in pure Python (works on locked-down machines).

## Data
| File | Content |
|---|---|
| `data/benchmark_trials.json` | 5 labelled benchmark trials in ClinicalTrials.gov format |
| `data/trials_live.json` | Real recruiting trials from ClinicalTrials.gov (`python fetch_trials.py`) |
| `data/patients.json` | 20 synthetic patient notes (no real patient data) |
| `data/ground_truth.csv` | 30 labelled patient×trial pairs for accuracy |

## Run
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      (paste your Gemini key)
python fetch_trials.py
python server.py            → http://127.0.0.1:8000
python evaluate.py
```
Offline backup: in `.env` set `LLM_PROVIDER=ollama` and `OLLAMA_MODEL=<name from ollama list>`.

## Responsible AI
Synthetic data only. Decision support only, not a medical decision. Every decision shows its evidence. Missing data goes to human review instead of being guessed.
