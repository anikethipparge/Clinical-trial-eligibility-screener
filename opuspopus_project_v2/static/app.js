const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const cls = d => d.split(" ")[0];
const ICON = {"ELIGIBLE":"✅","NOT ELIGIBLE":"❌","NEEDS REVIEW":"⚠️"};
let PATIENTS = [], TRIALS = [];

async function api(path, body) {
  const r = await fetch(path, body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}
function toast(msg){ const t=$("#toast"); t.textContent=msg; t.style.display="block"; setTimeout(()=>t.style.display="none",7000); }
function loading(el, msg){ el.innerHTML = `<div class="card"><span class="spin"></span>${msg}</div>`; }
async function busy(btn, fn){ btn.disabled = true; try { await fn(); } catch(e){ toast("⚠️ " + e.message); } finally { btn.disabled = false; } }

document.querySelectorAll(".tab").forEach(b => b.onclick = () => {
  document.querySelectorAll(".tab,.panel").forEach(x => x.classList.remove("active"));
  b.classList.add("active"); $("#" + b.dataset.tab).classList.add("active");
});

function factsHtml(f){
  const items = [];
  if (f.age != null) items.push(`Age ${f.age}`); if (f.sex) items.push(f.sex);
  (f.diagnoses||[]).forEach(d => items.push("Dx: " + d));
  Object.entries(f.labs||{}).forEach(([k,v]) => items.push(`${k}: ${v}`));
  (f.medications||[]).forEach(m => items.push("Rx: " + m));
  if (f.smoking) items.push("Smoking: " + f.smoking); if (f.pregnant === true) items.push("Pregnant");
  return `<div class="facts">${items.map(i=>`<span class="fact">${esc(i)}</span>`).join("")}</div>`;
}
function checklist(results){
  const row = r => {
    const st = r.type === "exclusion"
      ? `<span class="ex-${r.status}">${r.status==="MET"?"✗ PRESENT":r.status==="NOT_MET"?"✓ ABSENT":"? UNKNOWN"}</span>`
      : `<span class="s-${r.status}">${r.status==="MET"?"✓ MET":r.status==="NOT_MET"?"✗ NOT MET":"? UNKNOWN"}</span>`;
    return `<tr><td>${r.type==="inclusion"?"Inclusion":"Exclusion"} <span class="tag ${r.engine}">${r.engine==="rule"?"RULE":"AI"}</span></td>
      <td>${esc(r.criterion)}</td><td>${st}</td><td><i>${esc(r.evidence)}</i><div class="muted">${esc(r.reason)}</div></td></tr>`;
  };
  return `<table><tr><th style="width:120px">Type</th><th>Criterion</th><th style="width:110px">Status</th><th>Evidence / reason</th></tr>${results.map(row).join("")}</table>`;
}
function resultCard(r, extra=""){
  const link = r.url ? ` · <a href="${r.url}" target="_blank">view on ClinicalTrials.gov ↗</a>` : "";
  return `<div class="card result ${cls(r.decision)}">
    <div class="rhead"><div><h3>${esc(r.title)}</h3>
      <div class="meta">${esc(r.nct_id)}${r.source?" · "+esc(r.source):""}${r.similarity!=null?" · relevance "+r.similarity:""}${link}${extra}</div></div>
      <span class="badge b-${cls(r.decision)}">${ICON[r.decision]} ${r.decision}</span></div>
    <div class="summary">🤖 ${esc(r.summary)}</div>
    <div class="meta">Inclusion met: <b>${r.inclusion_met}/${r.inclusion_total}</b> · Exclusions triggered: <b>${r.exclusions_hit}</b>
      ${r.key_criteria.length?` · Deciding: ${r.key_criteria.map(esc).join("; ")}`:""}</div>
    <details style="margin-top:10px"><summary>Criterion-by-criterion checklist (${r.results.length})</summary>${checklist(r.results)}</details>
  </div>`;
}

async function init(){
  const s = await api("/api/status");
  $("#status").innerHTML = `LLM: <b>${esc(s.llm)}</b> · RAG: <b>${esc(s.retriever)}</b><br>${s.trials} trials (${s.live_trials} live) · ${s.rules} rules · ${s.patients} patients`;
  PATIENTS = await api("/api/patients"); TRIALS = await api("/api/trials");
  $("#m-patient").innerHTML = PATIENTS.map(p => `<option value="${p.id}">${p.id} — ${esc(p.note.slice(0,70))}…</option>`).join("");
  $("#m-note").value = PATIENTS[0]?.note || "";
  $("#b-trial").innerHTML = TRIALS.map(t => `<option value="${t.nct_id}">${t.nct_id} — ${esc(t.title.slice(0,90))}</option>`).join("");
  $("#b-patients").innerHTML = PATIENTS.map(p => `<span class="chip" data-id="${p.id}" title="${esc(p.note)}">${p.id}</span>`).join("");
  document.querySelectorAll("#b-patients .chip").forEach(c => c.onclick = () => c.classList.toggle("on"));
  showCriteria(); renderTrials(TRIALS); loadEval();
}
$("#m-patient").onchange = e => $("#m-note").value = PATIENTS.find(p => p.id === e.target.value).note;

$("#m-go").onclick = e => busy(e.target, async () => {
  const out = $("#m-out"); loading(out, "Extracting facts → retrieving trials → screening each criterion…");
  try {
    const d = await api("/api/match", {note: $("#m-note").value, k: +$("#m-k").value});
    out.innerHTML = `<div class="card"><h3>Extracted patient facts</h3><div style="margin-top:8px">${factsHtml(d.facts)}</div></div>` +
                    d.matches.map(r => resultCard(r)).join("");
  } catch(err){ out.innerHTML = ""; throw err; }
});

async function showCriteria(){
  if (!$("#b-trial").value) return;
  const t = await api("/api/trials/" + encodeURIComponent($("#b-trial").value));
  $("#b-criteria").innerHTML = `<b>Age:</b> ${t.min_age ?? 0}–${t.max_age ?? "any"} · <b>Sex:</b> ${t.sex} · <b>Inclusion:</b> ${t.inclusion.slice(0,6).map(esc).join(" | ")} …`;
}
$("#b-trial").onchange = showCriteria;
$("#b-all").onclick = () => document.querySelectorAll("#b-patients .chip").forEach(c => c.classList.add("on"));
$("#b-none").onclick = () => document.querySelectorAll("#b-patients .chip").forEach(c => c.classList.remove("on"));
$("#b-go").onclick = e => busy(e.target, async () => {
  const ids = [...document.querySelectorAll("#b-patients .chip.on")].map(c => c.dataset.id);
  if (!ids.length) return toast("Select at least one patient");
  const out = $("#b-out"); loading(out, `Screening ${ids.length} patient(s)…`);
  let d;
  try { d = await api("/api/batch", {trial_id: $("#b-trial").value, patient_ids: ids}); }
  catch(err){ out.innerHTML = ""; throw err; }
  const counts = {}; d.rows.forEach(r => counts[r.decision] = (counts[r.decision]||0) + 1);
  out.innerHTML = `<div class="card"><h3>${esc(d.trial.title)}</h3>
    <div class="row" style="margin-top:10px">${Object.entries(counts).map(([k,v])=>`<span class="badge b-${cls(k)}">${ICON[k]} ${k}: ${v}</span>`).join("")}</div>
    <table><tr><th>Patient</th><th>Decision</th><th>Inclusion met</th><th>Deciding criteria</th></tr>
    ${d.rows.map((r,i)=>`<tr class="clickable" data-i="${i}"><td>${r.patient_id}</td><td><span class="badge b-${cls(r.decision)}">${ICON[r.decision]} ${r.decision}</span></td>
      <td>${r.inclusion_met}/${r.inclusion_total}</td><td>${esc(r.key_criteria.join("; ")||"—")}</td></tr>`).join("")}</table>
    <p class="muted">Click a row for the full explanation.</p></div><div id="b-detail"></div>`;
  out.querySelectorAll("tr.clickable").forEach(tr => tr.onclick = () => {
    const r = d.rows[+tr.dataset.i]; $("#b-detail").innerHTML = resultCard(r, " · patient " + r.patient_id);
    $("#b-detail").scrollIntoView({behavior:"smooth"});
  });
});
$("#c-go").onclick = e => busy(e.target, async () => {
  const out = $("#c-out"); loading(out, "Screening…");
  try { out.innerHTML = resultCard(await api("/api/screen", {note: $("#c-note").value, criteria_text: $("#c-criteria").value})); }
  catch(err){ out.innerHTML = ""; throw err; }
});

function renderEval(r){
  if (!r) return $("#e-out").innerHTML = `<div class="card muted">No evaluation run yet.</div>`;
  const L = ["ELIGIBLE","NOT ELIGIBLE","NEEDS REVIEW"], pct = (r.accuracy*100).toFixed(1);
  const color = r.accuracy >= .85 ? "var(--ok)" : "var(--no)";
  $("#e-out").innerHTML = `<div class="grid">
    <div class="card kpi"><p class="big" style="color:${color}">${pct}%</p><div class="lbl">Decision accuracy (${r.correct}/${r.n}) · target 85%</div></div>
    <div class="card"><h3>Confusion matrix</h3><table><tr><th>Expected ↓ / Predicted →</th>${L.map(l=>`<th>${ICON[l]}</th>`).join("")}</tr>
      ${L.map(e=>`<tr><td>${ICON[e]} ${e}</td>${L.map(p=>`<td style="${e===p?"font-weight:700;color:var(--ok)":""}">${r.confusion[e][p]}</td>`).join("")}</tr>`).join("")}</table></div>
    <div class="card"><h3>Per-trial accuracy</h3><table>${Object.entries(r.per_trial).map(([k,v])=>`<tr><td>${k}</td><td><b>${(v*100).toFixed(0)}%</b></td></tr>`).join("")}</table></div></div>
    <div class="card"><h3>All screenings</h3><table><tr><th></th><th>Patient</th><th>Trial</th><th>Expected</th><th>Predicted</th><th>Why (label)</th></tr>
    ${r.rows.map(x=>`<tr><td>${x.correct?"✅":"❌"}</td><td>${x.patient_id}</td><td>${x.nct_id}</td><td>${x.expected}</td><td>${x.predicted}</td><td class="muted">${esc(x.why_expected)}</td></tr>`).join("")}</table></div>`;
}
async function loadEval(){ const d = await api("/api/evaluate"); renderEval(d.result); }
$("#e-go").onclick = e => busy(e.target, async () => {
  loading($("#e-out"), "Running evaluation (first run calls the LLM for every pair; later runs are cached)…");
  const poll = setInterval(async () => { try { const d = await api("/api/evaluate"); $("#e-prog").textContent = d.progress ? "Progress: " + d.progress : ""; } catch(_){} }, 1500);
  try { renderEval(await api("/api/evaluate", {})); } catch(err){ loadEval(); throw err; }
  finally { clearInterval(poll); $("#e-prog").textContent = ""; }
});

function renderTrials(list){
  $("#x-out").innerHTML = `<div class="card"><table><tr><th>ID</th><th>Title</th><th>Source</th><th>Age</th><th>Sex</th><th>Rules</th></tr>
  ${list.map(t=>`<tr class="clickable" data-id="${t.nct_id}"><td>${t.nct_id}</td><td>${esc(t.title)}<div class="muted">${esc((t.conditions||[]).join(", "))}</div></td>
    <td class="muted">${esc(t.source)}</td><td>${t.min_age ?? 0}–${t.max_age ?? "any"}</td><td>${t.sex}</td><td>${t.n_inc} inc / ${t.n_exc} exc</td></tr>`).join("")}</table></div><div id="x-detail"></div>`;
  document.querySelectorAll("#x-out tr.clickable").forEach(tr => tr.onclick = async () => {
    const t = await api("/api/trials/" + encodeURIComponent(tr.dataset.id));
    $("#x-detail").innerHTML = `<div class="card"><h3>${esc(t.title)}</h3><p class="muted">${esc(t.summary||"")}</p>
      <b>Inclusion</b><ol>${t.inclusion.map(c=>`<li>${esc(c)}</li>`).join("")}</ol><b>Exclusion</b><ol>${t.exclusion.map(c=>`<li>${esc(c)}</li>`).join("")}</ol></div>`;
    $("#x-detail").scrollIntoView({behavior:"smooth"});
  });
}
$("#x-go").onclick = e => busy(e.target, async () => renderTrials(await api("/api/trials?q=" + encodeURIComponent($("#x-q").value))));
$("#x-refresh").onclick = e => busy(e.target, async () => {
  $("#x-msg").innerHTML = `<span class="spin"></span>Downloading recruiting trials and rebuilding the RAG index…`;
  try {
    const d = await api("/api/refresh-trials", {});
    $("#x-msg").textContent = `Fetched ${d.fetched} live trials · library now has ${d.trials} trials and ${d.rules} rules.`;
    await init();
  } catch(err){ $("#x-msg").textContent = ""; throw err; }
});

init().catch(e => toast("Backend not reachable: " + e.message));
