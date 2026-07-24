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
const patternChips = ps => (ps||[]).map(p=>`<span class="chip" style="background:#ef444422;color:#fca5a5">⚠ ${esc(p.label)}</span>`).join('');
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
  ingest:['Ingest / Upload','Score a customer on demand from documents'],
  audit:['Audit Trail','Append-only record of every decision']};
async function go(view){
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active', n.dataset.view===view));
  $('title').textContent = TITLES[view][0]; $('subtitle').textContent = TITLES[view][1];
  $('content').innerHTML = '<div class="text-muted">Loading…</div>';
  await refreshStats();
  await VIEWS[view]();
}
document.getElementById('nav').addEventListener('click', e => { const a=e.target.closest('.nav-item'); if(a) go(a.dataset.view); });

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
  $('content').innerHTML = tiles + `<div class="text-xs text-faint mb-2 uppercase tracking-wide">Prioritised risk queue — highest risk first</div><div class="grid gap-3">${rows}</div>`;
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
     <div class="flex items-start gap-2 mb-2"><span class="badge" style="background:#ef444422;color:#fca5a5">⚠ ${esc(p.label)}</span>
       <span class="text-sm text-muted">${esc(p.rationale)}</span></div>`).join('')
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
    <div class="grid grid-cols-2 gap-4">
      <div class="card p-5"><div class="font-semibold mb-2">Pick a sample profile</div>
        <div class="text-xs text-muted mb-3">${samples.length} sample profiles available for manual upload.</div>
        <select id="sampleSel" class="w-full bg-panel2 border border-line rounded-lg px-3 py-2 text-sm">${samples.map(s=>`<option>${s}</option>`).join('')}</select>
        <button class="act w-full mt-3 bg-brand text-white py-2.5 rounded-lg font-semibold" onclick="ingestSample()">▶ Score this customer</button></div>
      <div class="card p-5"><div class="font-semibold mb-2">Upload files</div>
        <div class="text-xs text-muted mb-3">kyc.json · account.json · transactions.csv · screening.json · *.txt</div>
        <input id="upFiles" type="file" multiple class="text-sm w-full">
        <button class="act w-full mt-3 bg-brand2 text-white py-2.5 rounded-lg font-semibold" onclick="ingestFiles()">▶ Score uploaded files</button></div>
    </div>
    <div id="ingestResult" class="mt-5"></div>`;
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
async function ingestSample(){
  $('ingestResult').innerHTML = '<div class="text-muted">Scoring via the LLM graph… (a live call, ~15–30s)</div>';
  ingestResult(await jpost('/api/ingest', {sample_id: $('sampleSel').value})); refreshStats();
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
