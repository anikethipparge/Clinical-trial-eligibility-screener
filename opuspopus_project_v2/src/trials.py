"""Load trials (benchmark + live ClinicalTrials.gov) and fetch new ones from the public API v2."""
import json, re
import requests
from src import config

API = "https://clinicaltrials.gov/api/v2/studies"
BENCH_FILE = config.DATA / "benchmark_trials.json"
LIVE_FILE = config.DATA / "trials_live.json"
DEFAULT_CONDITIONS = ["type 2 diabetes", "hypertension", "asthma", "breast cancer",
                      "chronic kidney disease", "heart failure", "COPD", "depression"]


def load_trials():
    trials = []
    for f in (BENCH_FILE, LIVE_FILE):
        if f.exists():
            trials += json.loads(f.read_text(encoding="utf-8"))
    seen, out = set(), []
    for t in trials:
        if t["nct_id"] not in seen:
            seen.add(t["nct_id"]); out.append(t)
    return out


def _age(a):
    if not a:
        return None
    nums = re.findall(r"\d+", a)
    if not nums:
        return None
    n = int(nums[0])
    return n if "year" in a.lower() else 0


def _bullets(text):
    out = []
    for line in text.splitlines():
        line = re.sub(r"^\s*([*\-•]|\d+[.)]|[a-z][.)])\s*", "", line).strip()
        if len(line) > 3 and not re.match(r"^(key )?(inclusion|exclusion) criteria", line, re.I):
            out.append(line)
    return out


def split_criteria(text):
    parts = re.split(r"(?:key\s+)?exclusion\s+criteria\s*:?", text, flags=re.I, maxsplit=1)
    inc = _bullets(parts[0])
    exc = _bullets(parts[1]) if len(parts) > 1 else []
    return inc, exc


def fetch_live(conditions=None, per_condition=15):
    conditions = conditions or DEFAULT_CONDITIONS
    trials = []
    for cond in conditions:
        r = requests.get(API, timeout=30, params={
            "query.cond": cond, "filter.overallStatus": "RECRUITING", "pageSize": per_condition})
        r.raise_for_status()
        for s in r.json().get("studies", []):
            p = s.get("protocolSection", {})
            e = p.get("eligibilityModule", {})
            text = e.get("eligibilityCriteria", "")
            if not text:
                continue
            inc, exc = split_criteria(text)
            if not inc:
                continue
            ident = p.get("identificationModule", {})
            trials.append({
                "nct_id": ident.get("nctId"),
                "title": ident.get("briefTitle", ""),
                "conditions": p.get("conditionsModule", {}).get("conditions", [cond]),
                "summary": p.get("descriptionModule", {}).get("briefSummary", "")[:600],
                "min_age": _age(e.get("minimumAge")),
                "max_age": _age(e.get("maximumAge")),
                "sex": e.get("sex", "ALL"),
                "inclusion": inc, "exclusion": exc,
                "source": "ClinicalTrials.gov",
                "url": f"https://clinicaltrials.gov/study/{ident.get('nctId')}",
            })
    LIVE_FILE.write_text(json.dumps(trials, indent=2), encoding="utf-8")
    return trials
