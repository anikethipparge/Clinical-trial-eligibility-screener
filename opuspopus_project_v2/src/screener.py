"""Single-agent eligibility screener: LLM understands text, Python enforces hard rules + final decision."""
import json, re
from src import config
from src.llm import ask_json

FACTS_PROMPT = """You are a clinical data abstractor. Extract structured facts from this SYNTHETIC patient note.
Return ONLY JSON with exactly these keys:
{{"age": integer or null, "sex": "MALE" or "FEMALE" or null,
 "diagnoses": [strings], "labs": {{"name": "value with unit"}}, "medications": [strings],
 "history": [strings], "smoking": string or null, "pregnant": true/false/null}}
Patient note:
\"\"\"{note}\"\"\""""

JUDGE_PROMPT = """You are an expert clinical trial eligibility screener. All patient data is SYNTHETIC.
Evaluate the patient against EVERY criterion below. Use these exact rules:

INCLUSION criteria:
 - "MET" if the note shows the patient satisfies it.
 - "NOT_MET" if the note clearly contradicts it (e.g. lab value outside range, wrong diagnosis, wrong age).
 - "UNKNOWN" only if the required information is genuinely missing from the note.
EXCLUSION criteria:
 - "MET" if the patient HAS the excluding condition (this makes them ineligible).
 - "NOT_MET" if the patient does not have it OR it is not mentioned in the note.
SPECIAL CASES:
 - Administrative/procedural criteria (informed consent, willingness, ability to comply, agreeing to
   contraception, available for follow-up) -> treat inclusion as "MET" and exclusion as "NOT_MET".
 - Compare numbers carefully, respecting units and inclusive/exclusive bounds (>=, >, between).
 - Do not invent facts. Evidence must be a short exact phrase copied from the note, or "not mentioned".

Return ONLY JSON:
{{"results": [{{"id": "I1", "status": "MET|NOT_MET|UNKNOWN", "evidence": "...", "reason": "one short sentence"}}],
 "summary": "2-3 sentence plain-English rationale for a clinical coordinator, naming the decisive criteria"}}

Trial: {title}
Criteria (id: text):
{criteria}

Patient facts (pre-extracted): {facts}
Patient note:
\"\"\"{note}\"\"\""""


def extract_facts(note):
    facts = ask_json(FACTS_PROMPT.format(note=note))
    if not isinstance(facts, dict):
        facts = {}
    if not facts.get("age"):
        m = re.search(r"(\d{1,3})\s*[- ]?(?:year|yr|y/o|yo)", note, re.I)
        facts["age"] = int(m.group(1)) if m else None
    if not facts.get("sex"):
        if re.search(r"\b(female|woman|girl|she)\b", note, re.I): facts["sex"] = "FEMALE"
        elif re.search(r"\b(male|man|boy|he)\b", note, re.I): facts["sex"] = "MALE"
    if isinstance(facts.get("sex"), str):
        facts["sex"] = facts["sex"].upper()
    try:
        facts["age"] = int(facts["age"]) if facts.get("age") is not None else None
    except (TypeError, ValueError):
        facts["age"] = None
    return facts


def hard_checks(trial, facts):
    """Deterministic rule engine for structured fields (never wrong on numbers)."""
    out, age, sex = [], facts.get("age"), facts.get("sex")
    lo, hi = trial.get("min_age"), trial.get("max_age")
    if lo is not None or hi is not None:
        lo_, hi_ = lo or 0, hi or 120
        status = "UNKNOWN" if age is None else ("MET" if lo_ <= age <= hi_ else "NOT_MET")
        out.append({"id": "R-AGE", "type": "inclusion", "criterion": f"Age {lo_}-{hi_ if hi else '+'} years",
                    "status": status, "evidence": f"age = {age}", "reason": "Checked by rule engine",
                    "engine": "rule"})
    if trial.get("sex") in ("MALE", "FEMALE"):
        status = "UNKNOWN" if not sex else ("MET" if sex == trial["sex"] else "NOT_MET")
        out.append({"id": "R-SEX", "type": "inclusion", "criterion": f"Sex: {trial['sex'].title()} only",
                    "status": status, "evidence": f"sex = {sex}", "reason": "Checked by rule engine",
                    "engine": "rule"})
    return out


def _safety_overrides(results, facts):
    """Pregnancy exclusions are enforced from structured facts, regardless of LLM output."""
    for r in results:
        if r["type"] == "exclusion" and re.search(r"pregnan", r["criterion"], re.I) and facts.get("pregnant") is True:
            if r["status"] != "MET":
                r.update(status="MET", reason="Rule engine: patient is pregnant", engine="rule")
    return results


def judge(trial, facts, note):
    crit = [("I%d" % (i + 1), "inclusion", c) for i, c in enumerate(trial["inclusion"][:config.MAX_RULES])] + \
           [("E%d" % (i + 1), "exclusion", c) for i, c in enumerate(trial["exclusion"][:config.MAX_RULES])]
    text = "\n".join(f"{cid} [{typ.upper()}]: {c}" for cid, typ, c in crit)
    out = ask_json(JUDGE_PROMPT.format(title=trial["title"], criteria=text,
                                       facts=json.dumps(facts), note=note))
    by_id = {str(r.get("id", "")).upper(): r for r in out.get("results", []) if isinstance(r, dict)}
    results = []
    for cid, typ, c in crit:
        r = by_id.get(cid, {})
        status = str(r.get("status", "UNKNOWN")).upper().replace(" ", "_")
        if status not in ("MET", "NOT_MET", "UNKNOWN"):
            status = "UNKNOWN"
        results.append({"id": cid, "type": typ, "criterion": c, "status": status,
                        "evidence": r.get("evidence", ""), "reason": r.get("reason", ""), "engine": "llm"})
    return results, out.get("summary", "")


def decide(results):
    blockers = [r for r in results if (r["type"] == "inclusion" and r["status"] == "NOT_MET")
                or (r["type"] == "exclusion" and r["status"] == "MET")]
    if blockers:
        return "NOT ELIGIBLE", blockers
    unknown = [r for r in results if r["type"] == "inclusion" and r["status"] == "UNKNOWN"]
    if unknown:
        return "NEEDS REVIEW", unknown
    return "ELIGIBLE", []


def screen(note, trial, facts=None):
    facts = facts or extract_facts(note)
    llm_results, summary = judge(trial, facts, note)
    results = _safety_overrides(hard_checks(trial, facts) + llm_results, facts)
    decision, key = decide(results)
    inc = [r for r in results if r["type"] == "inclusion"]
    return {
        "nct_id": trial["nct_id"], "title": trial["title"], "decision": decision,
        "summary": summary, "key_criteria": [r["criterion"] for r in key][:3],
        "inclusion_met": sum(r["status"] == "MET" for r in inc), "inclusion_total": len(inc),
        "exclusions_hit": sum(r["type"] == "exclusion" and r["status"] == "MET" for r in results),
        "results": results, "facts": facts,
    }
