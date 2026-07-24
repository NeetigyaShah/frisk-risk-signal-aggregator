// ---------- Frisk frontend: calls the backend API, renders the views ----------
const api = async (p, opts) => (await fetch(p, opts)).json();
const jpost = (p, body) => api(p, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
const $ = id => document.getElementById(id);
const esc = s => (s??'').toString().replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

const RISK = {LOW:'#22c55e', MED:'#f59e0b', HIGH:'#ef4444'};
const ACT = {AUTO_CLEAR:['🟢','Auto-clear','#22c55e'], REVIEW:['🟡','Review','#f59e0b'],
             ESCALATE:['🔴','Escalate','#ef4444'], PENDING_REVIEW:['🟠','Human review','#f97316']};
const riskColor = b => RISK[b] || '#94a3b8';
const gauge = (score, band) => {
  const c = riskColor(band);
  return `<div class="gauge shrink-0" style="background:conic-gradient(${c} ${score*3.6}deg,#1e293b 0)">
    <div style="position:absolute;inset:5px;border-radius:50%;background:#111826;display:grid;place-items:center;color:${c}">${score}</div></div>`;
};
const actionBadge = a => { const [i,l,c]=ACT[a]||['⚪',a,'#94a3b8']; return `<span class="badge" style="background:${c}22;color:${c}">${i} ${l}</span>`; };
const confBar = c => `<div class="bar"><i style="width:${Math.round(c*100)}%;background:${c<0.6?'#f97316':'#22c55e'}"></i></div>`;
// Plain-language meaning of each AML typology (shown as tooltips + in the case drawer).
const PATTERN_DEFS = {
  'Structuring':  'Many cash deposits just under the reporting floor, clustered in a short window and together exceeding it — splitting one big deposit to dodge reporting ("smurfing").',
  'Layering':     'Rapid onward transfers to several distinct counterparties in a short window — moving money through hops to hide its origin.',
  'Round-Trip':   'Money goes out, then a ~matching amount returns via a different counterparty within a window — circular flow to fake legitimacy.',
  'Dormant-Spike':'A long inactive gap, then a sudden burst of large transactions — an account waking up abnormally.',
};
const patternDef = label => PATTERN_DEFS[label] || 'Transaction-pattern anomaly flagged by the typology detectors.';
const patternChips = ps => (ps||[]).map(p=>`<span class="chip" title="${esc(patternDef(p.label))}" style="background:#ef444422;color:#fca5a5;cursor:help">⚠ ${esc(p.label)}</span>`).join('');
const tile = (label,val,color) => `<div class="card px-4 py-3"><div class="text-2xl font-extrabold" style="color:${color||'#e8edf7'}">${val}</div><div class="text-xs text-muted">${label}</div></div>`;

// ---------- router ----------
let STATS = {};
async function refreshStats(){
  STATS = await api('/api/stats');
  $('broker').innerHTML = `broker: <b class="${STATS.broker==='redis'?'text-low':'text-med'}">${STATS.broker}</b>`;
  $('rqcount').textContent = STATS.review_queue || '';
  $('topstats').innerHTML = actionBadge('ESCALATE').replace('Escalate',`${STATS.escalate} Escalate`)
    + actionBadge('PENDING_REVIEW').replace('Human review',`${STATS.review_queue} Human queue`);
}
const VIEWS = {dashboard:renderDashboard, review:renderReview, ingest:renderIngest, audit:renderAudit};
const TITLES = {dashboard:['Dashboard','Prioritised, risk-scored triage queue'],
  review:['Human Review Queue','Low-confidence cases the model routed to a person'],
  ingest:['Ingest / Upload','Score any subset — or every profile — in parallel, review when they land'],
  audit:['Audit Trail','Append-only record of every decision']};
async function go(view){
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active', n.dataset.view===view));
  $('title').textContent = TITLES[view][0]; $('subtitle').textContent = TITLES[view][1];
  $('content').innerHTML = '<div class="text-muted">Loading…</div>';
  await refreshStats();
  await VIEWS[view]();
}
document.getElementById('nav').addEventListener('click', e => { const a=e.target.closest('.nav-item'); if(a) go(a.dataset.view); });

// ---------- charts ----------
Chart.defaults.color = '#94a3b8'; Chart.defaults.font.family = 'Inter';
Chart.defaults.borderColor = '#1e293b'; Chart.defaults.plugins.legend.display = false;
const _CHARTS = {};
function chart(id, cfg){ _CHARTS[id]?.destroy(); _CHARTS[id] = new Chart($(id), cfg); }
const noAxes = {scales:{x:{grid:{display:false}},y:{display:false,grid:{display:false}}}};
function bar(id, labels, data, colors){
  chart(id, {type:'bar', data:{labels, datasets:[{data, backgroundColor:colors, borderRadius:5, maxBarThickness:46}]},
    options:{responsive:true, maintainAspectRatio:false, plugins:{tooltip:{enabled:true}},
      scales:{x:{grid:{display:false},ticks:{font:{size:11}}},y:{beginAtZero:true,ticks:{precision:0,font:{size:10}},grid:{color:'#1e293b'}}}}});
}
async function renderCharts(){
  const a = await api('/api/analytics');
  bar('chBands', ['Low','Medium','High'], [a.bands.LOW,a.bands.MED,a.bands.HIGH], ['#22c55e','#f59e0b','#ef4444']);
  const A = a.actions;
  chart('chActions', {type:'doughnut', cutout:'62%',
    data:{labels:['Auto-clear','Review','Escalate','Human queue'],
      datasets:[{data:[A.AUTO_CLEAR,A.REVIEW,A.ESCALATE,A.PENDING_REVIEW],
        backgroundColor:['#22c55e','#f59e0b','#ef4444','#f97316'], borderColor:'#111826', borderWidth:2}]},
    options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:true,position:'right',labels:{boxWidth:10,font:{size:11}}}}}});
  const pl = Object.keys(a.patterns), pv = Object.values(a.patterns);
  if(pl.length) bar('chPats', pl, pv, pl.map(()=>'#6366f1'));
  else $('chPats').closest('.card').innerHTML = '<div class="text-xs text-faint mb-2 uppercase tracking-wide">Detected patterns</div><div class="text-sm text-faint py-8 text-center">No typology anomalies in the population.</div>';
}

// ---------- Dashboard ----------
async function renderDashboard(){
  const q = await api('/api/queue');
  const tiles = `<div class="grid grid-cols-5 gap-3 mb-6">
    ${tile('Total customers', STATS.total)}
    ${tile('🔴 Escalate', STATS.escalate, '#ef4444')}
    ${tile('🟡 Review', STATS.review, '#f59e0b')}
    ${tile('🟢 Auto-cleared', STATS.auto_clear, '#22c55e')}
    ${tile('🟠 Human queue', STATS.pending_review, '#f97316')}
  </div>`;
  const charts = `<div class="grid grid-cols-3 gap-3 mb-6">
    <div class="card p-4"><div class="text-xs text-faint mb-2 uppercase tracking-wide">Risk bands</div><div style="height:150px"><canvas id="chBands"></canvas></div></div>
    <div class="card p-4"><div class="text-xs text-faint mb-2 uppercase tracking-wide">Disposition</div><div style="height:150px"><canvas id="chActions"></canvas></div></div>
    <div class="card p-4"><div class="text-xs text-faint mb-2 uppercase tracking-wide">Detected patterns <span title="AML transaction typologies detected on every customer by the deterministic engine, and independently hunted by the LLM transactions-analyst." style="cursor:help">ⓘ</span></div><div style="height:150px"><canvas id="chPats"></canvas></div></div>
  </div>
  <div class="card p-3 mb-6 text-xs text-muted grid grid-cols-2 gap-x-6 gap-y-1">
    ${Object.entries(PATTERN_DEFS).map(([k,v])=>`<div><b class="text-ink">${k}:</b> ${esc(v)}</div>`).join('')}
  </div>`;
  const rows = q.map((d,i)=>`
    <div class="card p-4 flex items-center gap-4 cursor-pointer fade" onclick="openCase('${d.id}')">
      <div class="text-faint text-sm w-7 text-center font-semibold">#${i+1}</div>
      ${gauge(d.score,d.band)}
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="font-semibold">${esc(d.name)}</span>
          <span class="chip">${esc(d.occupation)}</span><span class="chip">${esc(d.country)}</span>
          ${d.flags.length?`<span class="badge" style="background:#ef444422;color:#fca5a5">🚨 ${esc(d.flags.join(', '))}</span>`:''}
        </div>
        <div class="text-sm text-muted truncate mt-1">${esc(d.summary)}</div>
        <div class="flex items-center gap-1.5 mt-2 flex-wrap">${actionBadge(d.action)}${patternChips(d.patterns)}</div>
      </div>
      <div class="w-32 shrink-0 text-right">
        <div class="text-[11px] text-faint mb-1">confidence ${d.confidence.toFixed(2)}</div>${confBar(d.confidence)}
      </div>
    </div>`).join('');
  $('content').innerHTML = tiles + charts + `<div class="text-xs text-faint mb-2 uppercase tracking-wide">Prioritised risk queue — highest risk first</div><div class="grid gap-3">${rows}</div>`;
  renderCharts();
}

// ---------- Case drawer ----------
async function openCase(cid){
  const d = await api('/api/case/'+cid);
  const src = (d.llm_detail?.source_findings)||[];
  const lv = {low:'🟢',medium:'🟡',high:'🔴'};
  const analysts = src.length ? `<div class="grid grid-cols-3 gap-2">${src.map(s=>`
     <div class="card p-3"><div class="font-semibold text-sm">${lv[s.risk_level]||'⚪'} ${esc(s.domain[0].toUpperCase()+s.domain.slice(1))}</div>
       <div class="text-xs text-muted mt-1">${esc(s.note)}</div></div>`).join('')}</div>` : '';
  const verd = d.llm_detail?.verdict;
  const patterns = d.patterns.length ? d.patterns.map(p=>`
     <div class="mb-3"><div class="flex items-start gap-2"><span class="badge" style="background:#ef444422;color:#fca5a5">⚠ ${esc(p.label)}</span>
       <span class="text-sm text-muted">${esc(p.rationale)}</span></div>
       <div class="text-xs text-faint mt-1 pl-1 italic">${esc(patternDef(p.label))}</div></div>`).join('')
     : `<div class="text-sm text-faint">No transaction-pattern anomalies detected by the rules engine.</div>`;
  const tx = (d.dossier.transactions||[]);
  const txRows = tx.slice().sort((a,b)=>a.date<b.date?1:-1).slice(0,40).map(t=>`
     <tr class="${t.anomalous?'bg-high/10':''}">
       <td class="py-1 pr-3 text-faint">${t.date}</td>
       <td class="pr-3">${t.direction==='in'?'▲':'▼'} £${t.amount.toLocaleString()}</td>
       <td class="pr-3 text-muted">${esc(t.type)}</td>
       <td class="pr-3 text-muted truncate max-w-[160px]">${esc(t.counterparty)} <span class="text-faint">${esc(t.cp_country)}</span></td>
       <td>${t.anomalous?'<span class="chip" style="background:#ef444422;color:#fca5a5">anomaly</span>':''}</td></tr>`).join('');
  const docs = (d.dossier.documents||[]).map(x=>`
     <details class="card p-3 mb-2"><summary class="cursor-pointer text-sm font-medium">📄 ${esc(x.name)}</summary>
       <pre class="text-xs text-muted whitespace-pre-wrap mt-2">${esc(x.text)}</pre></details>`).join('');

  $('drawer-body').innerHTML = `<div class="slide">
    <div class="p-5 border-b border-line flex items-start gap-4 sticky top-0 bg-panel z-10">
      ${gauge(d.score,d.band)}
      <div class="flex-1"><div class="text-lg font-bold">${esc(d.name)}</div>
        <div class="text-sm text-muted">${d.id} · ${esc(d.occupation)} · ${esc(d.country)}</div>
        <div class="mt-2 flex gap-2 items-center flex-wrap">${actionBadge(d.action)}
          <span class="chip">confidence ${d.confidence.toFixed(2)}</span>
          <span class="chip">${esc(d.engine_path)}</span></div></div>
      <button onclick="closeDrawer()" class="text-faint hover:text-ink text-xl">✕</button>
    </div>
    <div class="p-5 space-y-5">
      ${d.flags.length?`<div class="card p-3" style="border-color:#ef4444"><b class="text-high">🚨 Kill-switch:</b> ${esc(d.flags.join(', '))} — mandatory escalation.</div>`:''}
      <div><div class="text-xs uppercase tracking-wide text-faint mb-1">AI risk summary</div>
        <div class="card p-4 text-sm leading-relaxed">${esc(d.summary)}</div></div>
      <div><div class="text-xs uppercase tracking-wide text-faint mb-2">Detected patterns &amp; anomalies</div>
        <div class="card p-4">${patterns}</div></div>
      ${analysts?`<div><div class="text-xs uppercase tracking-wide text-faint mb-2">Multi-step AI reasoning — parallel analysts → synthesis → verification</div>
        ${analysts}${verd?`<div class="text-xs text-muted mt-2">QA verifier: ${verd.consistent?'✅ consistent':'✏️ adjusted'} — ${esc(verd.note||'')}</div>`:''}</div>`:''}
      <div><div class="text-xs uppercase tracking-wide text-faint mb-2">Transactions ${tx.length?`(${tx.length}, anomalies highlighted)`:'(none on file)'}</div>
        <div class="card p-3 overflow-x-auto"><table class="w-full text-sm">${txRows}</table></div></div>
      <div><div class="text-xs uppercase tracking-wide text-faint mb-2">Dossier</div>
        <div class="card p-3 mb-2"><div class="text-xs text-faint mb-1">KYC / Screening</div>
          <pre class="text-xs text-muted whitespace-pre-wrap">${esc(JSON.stringify({kyc:d.dossier.kyc, screening:d.dossier.screening}, null, 1))}</pre></div>
        ${docs}</div>
    </div></div>`;
  $('drawer').classList.remove('hidden');
}
const closeDrawer = () => $('drawer').classList.add('hidden');

// ---------- Review Queue ----------
async function renderReview(){
  const pend = await api('/api/review');
  window._PEND = pend;
  if(!pend.length){ $('content').innerHTML = `<div class="card p-8 text-center text-muted">Queue empty — the model was confident on every case.</div>`; return; }
  const why = c => (c.source_findings||[]).map(s=>`${s.domain.slice(0,4)}=${s.risk_level}`).join(', ') || 'low confidence';
  const cards = pend.map((c,i)=>`
    <div class="card p-4 fade">
      <div class="flex items-center gap-3">
        <div class="gauge" style="background:conic-gradient(#f97316 ${(c.llm_score||0)*3.6}deg,#1e293b 0)"><div style="position:absolute;inset:5px;border-radius:50%;background:#111826;display:grid;place-items:center;color:#f97316">${c.llm_score??'?'}</div></div>
        <div class="flex-1"><div class="font-semibold">${esc(c.name)} <span class="text-faint text-sm">${c.customer_id}</span></div>
          <div class="text-sm text-muted">LLM unsure — confidence ${(c.confidence||0).toFixed(2)} · analysts: ${esc(why(c))}</div>
          <div class="text-sm text-muted mt-1">${esc(c.reason||'')}</div></div>
        <button class="act bg-brand text-white px-3 py-2 rounded-lg text-sm font-medium" onclick="openReview(${i})">Review →</button>
      </div>
      <div class="grid grid-cols-3 gap-2 mt-3">${(c.source_findings||[]).map(s=>{const lv={low:'🟢',medium:'🟡',high:'🔴'};
        return `<div class="card p-2 text-xs"><b>${lv[s.risk_level]||'⚪'} ${esc(s.domain)}</b><div class="text-muted mt-0.5">${esc(s.note)}</div></div>`}).join('')}</div>
    </div>`).join('');
  $('content').innerHTML = `<div class="text-sm text-muted mb-3">${pend.length} case(s) awaiting a human decision. Set the correct score — it teaches the model.</div><div class="grid gap-3">${cards}</div>`;
}
function openReview(i){
  const c = window._PEND[i];
  $('drawer-body').innerHTML = `<div class="slide p-6 space-y-4">
    <div class="flex items-center justify-between"><div class="text-lg font-bold">${esc(c.name)} <span class="text-faint text-sm">${c.customer_id}</span></div>
      <button onclick="closeDrawer()" class="text-faint hover:text-ink text-xl">✕</button></div>
    <div class="card p-3 text-sm">LLM proposed <b>${c.llm_score}</b> at confidence <b class="text-review">${(c.confidence||0).toFixed(2)}</b>. ${esc(c.reason||'')}</div>
    <div class="grid grid-cols-3 gap-2">${(c.source_findings||[]).map(s=>{const lv={low:'🟢',medium:'🟡',high:'🔴'};
      return `<div class="card p-2 text-xs"><b>${lv[s.risk_level]||'⚪'} ${esc(s.domain)}</b><div class="text-muted mt-0.5">${esc(s.note)}</div></div>`}).join('')}</div>
    <div class="pt-2 border-t border-line"><div class="text-xs uppercase tracking-wide text-faint mb-2">Your decision — teaches the model</div>
      <label class="text-sm text-muted">Correct score: <b id="rvS">${c.llm_score||50}</b></label>
      <input id="rvScore" type="range" min="0" max="100" value="${c.llm_score||50}" class="w-full" oninput="$('rvS').textContent=this.value">
      <div class="grid grid-cols-2 gap-3 mt-2">
        <select id="rvBand" class="bg-panel2 border border-line rounded-lg px-3 py-2 text-sm"><option>LOW</option><option selected>MED</option><option>HIGH</option></select>
        <select id="rvAction" class="bg-panel2 border border-line rounded-lg px-3 py-2 text-sm"><option>AUTO_CLEAR</option><option selected>REVIEW</option><option>ESCALATE</option></select>
      </div>
      <textarea id="rvNote" placeholder="Correction note — why (the lesson the model learns)" class="w-full bg-panel2 border border-line rounded-lg px-3 py-2 text-sm mt-2" rows="2"></textarea>
      <button class="act w-full mt-3 bg-brand text-white py-2.5 rounded-lg font-semibold" onclick="submitReview('${c.customer_id}')">✓ Submit &amp; teach the model</button>
    </div></div>`;
  $('drawer').classList.remove('hidden');
}
async function submitReview(cid){
  await jpost(`/api/review/${cid}/resolve`, {score:+$('rvScore').value, band:$('rvBand').value, action:$('rvAction').value, note:$('rvNote').value});
  closeDrawer(); go('review');
}

// ---------- Ingest ----------
async function renderIngest(){
  const samples = await api('/api/samples');
  $('content').innerHTML = `
    <div class="grid grid-cols-3 gap-4">
      <div class="card p-5 col-span-2">
        <div class="flex items-center justify-between mb-3">
          <div><div class="font-semibold">Sample profiles</div>
            <div class="text-xs text-muted">${samples.length} available — tick any subset, or select all and score them in parallel.</div></div>
          <label class="text-sm text-muted flex items-center gap-2 cursor-pointer"><input type="checkbox" id="selAll" onchange="toggleAll(this.checked)"> Select all</label>
        </div>
        <div class="max-h-[300px] overflow-y-auto grid grid-cols-2 gap-1 mb-4 pr-1">
          ${samples.map(s=>`<label class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-panel2 text-sm cursor-pointer">
            <input type="checkbox" class="smp" value="${s}" onchange="updateSel()"> <span class="truncate">${esc(s)}</span></label>`).join('')}
        </div>
        <button class="act w-full bg-brand text-white py-2.5 rounded-lg font-semibold" onclick="scoreSelected()">
          ▶ Score selected (<span id="selCount">0</span>) in parallel</button>
        <div class="text-[11px] text-faint mt-2 text-center">Each customer runs the full 5-step LLM graph · bounded concurrency to respect rate limits · results stream in below</div>
      </div>
      <div class="card p-5"><div class="font-semibold mb-2">Upload files</div>
        <div class="text-xs text-muted mb-3">kyc.json · account.json · transactions.csv · screening.json · *.txt</div>
        <input id="upFiles" type="file" multiple class="text-sm w-full">
        <button class="act w-full mt-3 bg-brand2 text-white py-2.5 rounded-lg font-semibold" onclick="ingestFiles()">▶ Score uploaded files</button></div>
    </div>
    <div id="batchArea" class="mt-6"></div>
    <div id="ingestResult" class="mt-5"></div>`;
}
const _selected = () => [...document.querySelectorAll('.smp:checked')].map(c=>c.value);
function updateSel(){ $('selCount').textContent = _selected().length; }
function toggleAll(on){ document.querySelectorAll('.smp').forEach(c=>c.checked=on); updateSel(); }

const batchShell = (total, workers) => `<div class="card p-5">
  <div class="flex items-center justify-between mb-2">
    <div class="font-semibold">Batch scoring — up to ${workers} customers at once</div>
    <div id="bpText" class="text-sm text-muted">0 / ${total} scored</div></div>
  <div class="bar mb-1" style="height:8px"><i id="bpBar" style="width:0%;background:#3b82f6;transition:width .3s"></i></div>
  <div id="bpDone" class="text-xs text-faint mb-4">Scoring… fire-and-review — you can leave this running.</div>
  <div id="bResults" class="grid grid-cols-2 gap-2"></div></div>`;
function batchCard(r){
  if(r.error) return `<div class="card p-3 text-sm border-high/50"><b>${esc(r.name)}</b> <span class="text-high">✕ ${esc(r.error).slice(0,60)}</span></div>`;
  return `<div class="card p-3 flex items-center gap-3 fade cursor-pointer" onclick="openCase('${r.id}')">
    ${gauge(r.score,r.band)}
    <div class="flex-1 min-w-0"><div class="font-semibold text-sm truncate">${esc(r.name)} <span class="text-faint">${r.id}</span></div>
      <div class="mt-1 flex gap-1.5 items-center flex-wrap">${actionBadge(r.action)}<span class="chip">conf ${(r.confidence||0).toFixed(2)}</span>${patternChips(r.patterns)}</div></div></div>`;
}
async function scoreSelected(){
  const ids = _selected();
  if(!ids.length){ $('batchArea').innerHTML = `<div class="text-sm text-med">Select at least one profile.</div>`; return; }
  const j = await jpost('/api/ingest/batch', {ids});
  $('batchArea').innerHTML = batchShell(j.total, j.workers);
  pollBatch(j.job_id);
}
async function pollBatch(job_id){
  const j = await api('/api/ingest/batch/'+job_id);
  const pct = j.total ? Math.round(j.done/j.total*100) : 0;
  if($('bpBar')){ $('bpBar').style.width = pct+'%'; $('bpText').textContent = `${j.done} / ${j.total} scored`;
    $('bResults').innerHTML = (j.results||[]).map(batchCard).join(''); }
  if(j.status !== 'complete'){ setTimeout(()=>pollBatch(job_id), 1500); return; }
  refreshStats();
  const rev = (j.results||[]).filter(r=>r.action==='PENDING_REVIEW').length;
  if($('bpDone')) $('bpDone').innerHTML = `✓ Complete · ${j.total} scored${rev?` · <b class="text-review">${rev} routed to Human Review →</b>`:''} · click any card to open the case.`;
}
function ingestResult(d){
  const src=(d.llm_detail?.source_findings)||[]; const lv={low:'🟢',medium:'🟡',high:'🔴'};
  $('ingestResult').innerHTML = `<div class="card p-5 fade">
    <div class="flex items-center gap-4">${gauge(d.score,d.band)}
      <div class="flex-1"><div class="font-bold">${esc(d.name)} <span class="text-faint text-sm">${d.id}</span></div>
        <div class="mt-1 flex gap-2 items-center">${actionBadge(d.action)}<span class="chip">confidence ${d.confidence.toFixed(2)}</span>${patternChips(d.patterns)}</div></div>
      <button class="act bg-panel2 border border-line px-3 py-2 rounded-lg text-sm" onclick="openCase('${d.id}')">Open case →</button></div>
    <div class="card p-3 mt-3 text-sm">${esc(d.summary)}</div>
    ${src.length?`<div class="grid grid-cols-3 gap-2 mt-3">${src.map(s=>`<div class="card p-2 text-xs"><b>${lv[s.risk_level]||'⚪'} ${esc(s.domain)}</b><div class="text-muted mt-0.5">${esc(s.note)}</div></div>`).join('')}</div>`:''}
    ${d.action==='PENDING_REVIEW'?`<div class="mt-3 text-review text-sm">🟠 Low confidence — added to the Human Review Queue.</div>`:''}</div>`;
}
async function ingestFiles(){
  const fs = $('upFiles').files; if(!fs.length) return;
  const fd = new FormData(); for(const f of fs) fd.append('files', f);
  $('ingestResult').innerHTML = '<div class="text-muted">Scoring uploaded files…</div>';
  ingestResult(await api('/api/ingest/files', {method:'POST', body:fd})); refreshStats();
}

// ---------- Audit ----------
async function renderAudit(){
  const rows = await api('/api/audit');
  $('content').innerHTML = `<div class="card overflow-x-auto"><table class="w-full text-sm">
    <thead><tr class="text-faint text-left border-b border-line">${['time','customer','actor','action','score','conf','path'].map(h=>`<th class="p-3">${h}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r=>`<tr class="border-b border-line/50"><td class="p-3 text-faint">${(r.ts||'').slice(0,19).replace('T',' ')}</td>
      <td class="p-3">${esc(r.customer_id)}</td><td class="p-3 text-muted">${esc(r.actor)}</td>
      <td class="p-3">${esc(r.action)}</td><td class="p-3">${r.score}</td><td class="p-3">${(r.confidence||0).toFixed?.(2)??r.confidence}</td>
      <td class="p-3 text-faint">${esc(r.engine_path)}</td></tr>`).join('')}</tbody></table></div>`;
}

go('dashboard');
