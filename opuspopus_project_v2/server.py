"""OpusPopus - Clinical Trial Eligibility Screener (FastAPI backend + web UI).
Run:  python server.py   then open http://127.0.0.1:8000
"""
import json, threading, webbrowser
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from src import config
from src.llm import provider_name, LLMError
from src.trials import load_trials, fetch_live, split_criteria
from src.retriever import Retriever
from src.screener import screen, extract_facts
from src.evaluation import run_evaluation, last_evaluation

app = FastAPI(title="OpusPopus Trial Screener")
STATE = {"trials": [], "by_id": {}, "retriever": None, "eval_progress": None}


def reload_trials():
    STATE["trials"] = load_trials()
    STATE["by_id"] = {t["nct_id"]: t for t in STATE["trials"]}
    STATE["retriever"] = Retriever(STATE["trials"])


def patients():
    return json.loads((config.DATA / "patients.json").read_text(encoding="utf-8"))


def note_for(pid):
    for p in patients():
        if p["id"] == pid:
            return p["note"]
    raise HTTPException(404, f"Patient {pid} not found")


def guard(fn):
    try:
        return fn()
    except LLMError as e:
        raise HTTPException(502, f"LLM error: {e}")


class MatchReq(BaseModel):
    note: str
    k: int = 3

class ScreenReq(BaseModel):
    note: str
    trial_id: Optional[str] = None
    criteria_text: Optional[str] = None

class BatchReq(BaseModel):
    trial_id: str
    patient_ids: List[str]

class RefreshReq(BaseModel):
    conditions: Optional[List[str]] = None
    per_condition: int = 15


@app.get("/api/status")
def status():
    t = STATE["trials"]
    return {"llm": provider_name(), "retriever": STATE["retriever"].mode, "trials": len(t),
            "live_trials": sum(x.get("source") == "ClinicalTrials.gov" for x in t),
            "rules": sum(len(x["inclusion"]) + len(x["exclusion"]) for x in t),
            "patients": len(patients())}


@app.get("/api/trials")
def trials(q: str = ""):
    items = STATE["trials"]
    if q:
        items = [t for t, _ in STATE["retriever"].search(q, 25)]
    return [{"nct_id": t["nct_id"], "title": t["title"], "conditions": t.get("conditions", []),
             "source": t.get("source", ""), "n_inc": len(t["inclusion"]), "n_exc": len(t["exclusion"]),
             "min_age": t.get("min_age"), "max_age": t.get("max_age"), "sex": t.get("sex")} for t in items]


@app.get("/api/trials/{nct_id}")
def trial(nct_id: str):
    if nct_id not in STATE["by_id"]:
        raise HTTPException(404, "Trial not found")
    return STATE["by_id"][nct_id]


@app.get("/api/patients")
def list_patients():
    return patients()


@app.post("/api/match")
def match(req: MatchReq):
    def run():
        facts = extract_facts(req.note)
        query = req.note + " " + " ".join(map(str, facts.get("diagnoses") or []))
        out = []
        for t, score in STATE["retriever"].search(query, max(1, min(req.k, 10))):
            r = screen(req.note, t, facts)
            r["similarity"] = round(score, 3); r["source"] = t.get("source"); r["url"] = t.get("url", "")
            out.append(r)
        order = {"ELIGIBLE": 0, "NEEDS REVIEW": 1, "NOT ELIGIBLE": 2}
        out.sort(key=lambda r: (order[r["decision"]], -r["similarity"]))
        return {"facts": facts, "matches": out}
    return guard(run)


@app.post("/api/screen")
def screen_one(req: ScreenReq):
    if req.criteria_text:
        inc, exc = split_criteria(req.criteria_text)
        t = {"nct_id": "CUSTOM", "title": "Custom pasted trial", "inclusion": inc, "exclusion": exc,
             "min_age": None, "max_age": None, "sex": "ALL"}
    elif req.trial_id in STATE["by_id"]:
        t = STATE["by_id"][req.trial_id]
    else:
        raise HTTPException(400, "Give a valid trial_id or criteria_text")
    return guard(lambda: screen(req.note, t))


@app.post("/api/batch")
def batch(req: BatchReq):
    t = STATE["by_id"].get(req.trial_id)
    if not t:
        raise HTTPException(404, "Trial not found")
    def run():
        rows = []
        for pid in req.patient_ids:
            r = screen(note_for(pid), t)
            r["patient_id"] = pid
            rows.append(r)
        return {"trial": t, "rows": rows}
    return guard(run)


@app.get("/api/evaluate")
def get_eval():
    return {"result": last_evaluation(), "progress": STATE["eval_progress"]}


@app.post("/api/evaluate")
def post_eval():
    def prog(i, n): STATE["eval_progress"] = f"{i}/{n}"
    def run():
        pmap = {p["id"]: p["note"] for p in patients()}
        return run_evaluation(STATE["by_id"], pmap, prog)
    try:
        return guard(run)
    finally:
        STATE["eval_progress"] = None


@app.post("/api/refresh-trials")
def refresh(req: RefreshReq):
    try:
        live = fetch_live(req.conditions, req.per_condition)
    except Exception as e:
        raise HTTPException(502, f"Could not reach ClinicalTrials.gov: {e}")
    reload_trials()
    return {"fetched": len(live), **status()}


app.mount("/static", StaticFiles(directory=config.ROOT / "static"), name="static")

@app.get("/")
def home():
    return FileResponse(config.ROOT / "static" / "index.html")


if __name__ == "__main__":
    print("Loading trials and building RAG index...")
    reload_trials()
    print(f"Ready: {len(STATE['trials'])} trials | retriever: {STATE['retriever'].mode} | LLM: {provider_name()}")
    print("Open http://127.0.0.1:8000  (Ctrl+C to stop)")
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    uvicorn.run(app, host="127.0.0.1", port=8000)
