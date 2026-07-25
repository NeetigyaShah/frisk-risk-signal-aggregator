/* ============================================================
   Frisk frontend — vanilla JS, no build step.
   Views: dashboard · review · ingest · audit  (+ case drawer, ⌘K palette)
   ============================================================ */
const api   = async (p, o) => (await fetch(p, o)).json();
const jpost = (p, body) => api(p, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
const $     = id => document.getElementById(id);
const esc   = s => (s ?? '').toString().replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const el    = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content; };

const RISK = {LOW:'#22c55e', MED:'#f59e0b', HIGH:'#ef4444'};
const ACT  = {AUTO_CLEAR:['●','Auto-clear','#22c55e'], REVIEW:['●','Review','#f59e0b'],
              ESCALATE:['●','Escalate','#ef4444'], PENDING_REVIEW:['●','Human review','#f97316'], ERROR:['●','Error','#71717a']};
const LVL  = {low:'#22c55e', medium:'#f59e0b', high:'#ef4444'};

const bandUp    = b => ({low:'LOW', medium:'MED', high:'HIGH'}[String(b).toLowerCase()] || String(b).toUpperCase());
const riskColor = b => RISK[bandUp(b)] || '#a1a1aa';
const gauge = (score, band) => {
  const c = riskColor(band);
  return `<div class="gauge" style="background:conic-gradient(${c} ${score*3.6}deg,#232326 0)">
    <span style="color:${c}">${score}</span></div>`;
};
const actionBadge = a => { const [i,l,c] = ACT[a] || ['●', a, '#a1a1aa'];
  return `<span class="badge" style="background:${c}1f;color:${c}">${i} ${l}</span>`; };
const confBar = c => `<div class="bar"><i style="width:${Math.round(c*100)}%;background:${c<0.6?'#f97316':'#22c55e'}"></i></div>`;

const PATTERN_DEFS = {
  'Structuring':   'Many cash deposits just under the reporting floor, clustered in a short window and together exceeding it — splitting one big deposit to dodge reporting ("smurfing").',
  'Layering':      'Rapid onward transfers to several distinct counterparties in a short window — moving money through hops to hide its origin.',
  'Round-Trip':    'Money goes out, then a ~matching amount returns via a different counterparty within a window — circular flow to fake legitimacy.',
  'Dormant-Spike': 'A long inactive gap, then a sudden burst of large transactions — an account waking up abnormally.',
};
const patternDef = l => PATTERN_DEFS[l] || 'Transaction-pattern candidate surfaced by the advisory scan.';
const patternChips = ps => (ps||[]).slice(0,3).map(p =>
  `<span class="chip" title="${esc(patternDef(p.label))}" style="background:#ef44441f;color:#fca5a5;cursor:help">⚠ ${esc(p.label)}</span>`).join('');

const emptyState = (ico, title, body) =>
  `<div class="empty"><div class="e-ico">${ico}</div><h3>${title}</h3><p>${body}</p></div>`;

/* ───────────── shell chrome ───────────── */
function toggleRail(){
  document.body.classList.toggle('rail');
  localStorage.setItem('frisk_rail', document.body.classList.contains('rail') ? '1' : '');
  Object.values(_CHARTS).forEach(c => c && c.resize());
}
if (localStorage.getItem('frisk_rail')) document.body.classList.add('rail');

let STATS = {};
async function refreshStats(){
  STATS = await api('/api/stats');
  $('broker').textContent = 'broker: ' + (STATS.broker || '…');
  if (STATS.warming){
    $('rqcount').textContent = '';
    $('topstats').innerHTML = `<span class="chip">⚙ scoring ${STATS.done||0}/${STATS.total||20}…</span>`;
    return;
  }
  $('rqcount').textContent = STATS.review_queue || '';
  $('topstats').innerHTML =
    `<span class="badge" style="background:#ef44441f;color:#ef4444">● ${STATS.escalate} Escalate</span>
     <span class="badge" style="background:#f973161f;color:#f97316">● ${STATS.review_queue} Human queue</span>`;
}

// lazy lookup so view functions can be declared anywhere in the file
const VIEWS = {
  get dashboard(){ return renderDashboard; }, get review(){ return renderReview; },
  get compare(){ return renderCompare; },     get sar(){ return renderSar; },
  get ingest(){ return renderIngest; },       get audit(){ return renderAudit; },
};
const TITLES = {
  dashboard:['Dashboard','Prioritised, risk-scored triage queue'],
  review:['Review Queue','Low-confidence cases the agent routed to a person'],
  compare:['Case Comparison','Why did one clear and the other escalate?'],
  sar:['SAR Drafts','Auto-drafted Suspicious Activity Report narratives'],
  ingest:['Ingest / Upload','Score any subset — or every profile — in parallel'],
  audit:['Audit Trail','Append-only record of every decision'],
};
// Race guard: switching views fast (dashboard -> compare before dashboard's fetches land)
// used to let whichever render finished LAST win, overwriting the page you actually asked
// for. Every navigation bumps _navGen; each render checks it's still current before
// touching #content, and abandons silently otherwise.
let _navGen = 0;
const staleNav = gen => gen !== _navGen;

async function go(view){
  const gen = ++_navGen;
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === view));
  $('title').textContent = TITLES[view][0];
  $('subtitle').textContent = TITLES[view][1];
  await refreshStats();
  if (staleNav(gen)) return;
  if (STATS.warming) return showWarming(view, gen);
  await VIEWS[view](gen);
}
$('nav').addEventListener('click', e => { const a = e.target.closest('.nav-item'); if (a) go(a.dataset.view); });

function showWarming(view, gen = _navGen){
  if (staleNav(gen)) return;
  const pct = STATS.total ? Math.round((STATS.done / STATS.total) * 100) : 0;
  $('content').innerHTML = `<div class="card card-pad fade" style="max-width:520px;margin:8vh auto;text-align:center">
    <div style="font-size:34px;margin-bottom:10px">⚙️</div>
    <h3 style="font-size:17px;font-weight:800;margin-bottom:6px">Scoring customers live</h3>
    <p style="color:var(--muted);font-size:13px;margin-bottom:20px">Each customer runs the full agentic pipeline — memory → 3 parallel specialists → the tool-calling orchestrator. This happens once, on first start.</p>
    <div class="bar" style="height:9px"><i style="width:${pct}%;background:linear-gradient(90deg,#a1a1aa,#e4e4e7);transition:width .5s"></i></div>
    <p style="color:var(--muted);font-size:13px;margin-top:10px">${STATS.done||0} / ${STATS.total||20} scored</p></div>`;
  clearTimeout(window._warmT);
  window._warmT = setTimeout(() => go(view), 2500);
}

/* ───────────── charts ───────────── */
Chart.defaults.color = '#a1a1aa';
Chart.defaults.font.family = 'Inter';
Chart.defaults.borderColor = '#232326';
Chart.defaults.plugins.legend.display = false;
const _CHARTS = {};
const chart = (id, cfg) => { _CHARTS[id]?.destroy(); if ($(id)) _CHARTS[id] = new Chart($(id), cfg); };
const barChart = (id, labels, data, colors) => chart(id, {
  type:'bar',
  data:{labels, datasets:[{data, backgroundColor:colors, borderRadius:6, maxBarThickness:44}]},
  options:{responsive:true, maintainAspectRatio:false, plugins:{tooltip:{enabled:true}},
    scales:{x:{grid:{display:false}, ticks:{font:{size:11}}},
            y:{beginAtZero:true, ticks:{precision:0, font:{size:10}}, grid:{color:'#232326'}}}},
});

/* ───────────── scroll reveal + count-up ───────────── */
function revealAll(){
  const io = new IntersectionObserver((ents, obs) => ents.forEach(e => {
    if (e.isIntersecting){ setTimeout(() => e.target.classList.add('in'), +(e.target.dataset.delay||0)); obs.unobserve(e.target); }
  }), {threshold:.1});
  document.querySelectorAll('.reveal:not(.in)').forEach(n => io.observe(n));
}
function countUp(node, to, ms = 700){
  const t0 = performance.now();
  const tick = now => { const p = Math.min(1, (now - t0)/ms);
    node.textContent = Math.round(to * (1 - Math.pow(1-p, 3)));
    if (p < 1) requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
}

/* ───────────── Dashboard ───────────── */
async function renderDashboard(gen = _navGen){
  const [q, a] = await Promise.all([api('/api/queue'), api('/api/analytics')]);
  if (staleNav(gen)) return;   // user navigated away while these fetches were in flight
  const autoPct = STATS.total ? Math.round(STATS.auto_clear / STATS.total * 100) : 0;
  const high = q.filter(d => bandUp(d.band) === 'HIGH').length;

  const KPI = [
    {label:'Total customers', v:STATS.total,          c:'var(--ink)'},
    {label:'Escalate',        v:STATS.escalate,       c:'#ef4444'},
    {label:'Review',          v:STATS.review,         c:'#f59e0b'},
    {label:'Auto-cleared',    v:STATS.auto_clear,     c:'#22c55e'},
    {label:'Human queue',     v:STATS.pending_review, c:'#f97316'},
  ];

  $('content').innerHTML = `
    <div class="grid grid-hero">
      <div class="card-accent card-pad reveal">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:4px">
          <div><p class="section-label" style="margin:0 0 4px">Population risk profile</p>
            <h3 style="font-size:17px;font-weight:800;letter-spacing:-.02em">Score distribution across ${STATS.total} customers</h3></div>
          <span class="chip">${high} high-risk</span></div>
        <div class="chart-box" style="height:190px;margin-top:12px"><canvas id="chDist"></canvas></div>
      </div>
      <div class="card-accent card-pad reveal" data-delay="90">
        <p class="section-label" style="margin:0 0 4px">Analyst load saved</p>
        <h3 style="font-size:17px;font-weight:800;letter-spacing:-.02em;margin-bottom:18px">Auto-cleared without review</h3>
        <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:8px">
          <span style="font-size:40px;font-weight:900;letter-spacing:-.04em;line-height:1;color:#22c55e"><span id="apct">0</span>%</span>
          <span style="font-size:12px;color:var(--faint)">${STATS.auto_clear} of ${STATS.total} cases</span></div>
        <div class="bar" style="height:8px"><i id="apbar" style="width:0%;background:linear-gradient(90deg,#22c55e,#15803d);transition:width .9s cubic-bezier(.22,1,.36,1)"></i></div>
        <p style="font-size:12px;color:var(--faint);margin-top:12px;line-height:1.55">
          ${STATS.escalate} escalated to a senior reviewer · ${STATS.pending_review} sent to the human queue.</p>
      </div>
    </div>

    <div class="grid grid-kpi" style="margin-top:14px">
      ${KPI.map((k,i) => `<div class="kpi reveal" data-delay="${80+i*60}">
        <div class="k-label">${k.label}</div>
        <div class="k-row"><div class="k-value" style="color:${k.c}"><span class="cu" data-to="${k.v}">0</span></div>
          ${i ? `<span class="k-delta" style="background:${k.c}1a;color:${k.c}">${STATS.total?Math.round(k.v/STATS.total*100):0}%</span>` : ''}
        </div></div>`).join('')}
    </div>

    <div class="grid grid-charts" style="margin-top:14px">
      <div class="card card-pad reveal"><p class="section-label" style="margin:0 0 10px">Risk bands</p>
        <div class="chart-box" style="height:160px"><canvas id="chBands"></canvas></div></div>
      <div class="card card-pad reveal" data-delay="70"><p class="section-label" style="margin:0 0 10px">Disposition</p>
        <div class="chart-box" style="height:160px"><canvas id="chActions"></canvas></div></div>
      <div class="card card-pad reveal" data-delay="140"><p class="section-label" style="margin:0 0 10px">Detected patterns</p>
        <div class="chart-box" style="height:160px"><canvas id="chPats"></canvas></div></div>
    </div>

    <div class="card card-pad reveal" style="margin-top:14px">
      <div class="grid grid-2" style="gap:12px 26px">
        ${Object.entries(PATTERN_DEFS).map(([k,v]) =>
          `<p style="font-size:12.5px;color:var(--muted);line-height:1.6"><b style="color:var(--ink)">${k}:</b> ${esc(v)}</p>`).join('')}
      </div></div>

    <p class="section-label">Prioritised risk queue — highest risk first</p>
    <div class="grid" style="gap:10px">
      ${q.map((d,i) => `
        <div class="card qrow fade" onclick="openCase('${d.id}')">
          <div class="rank">#${i+1}</div>
          ${gauge(d.score, d.band)}
          <div class="qmain">
            <div class="qhead">
              <span class="qname">${esc(d.name)}</span>
              <span class="chip">${esc(d.occupation)}</span><span class="chip">${esc(d.country)}</span>
              ${actionBadge(d.action)}${patternChips(d.patterns)}
            </div>
            <p class="qsum">${esc(d.summary)}</p>
            ${(d.key_signals?.length) ? `<div class="qsig">
              ${d.key_signals.slice(0,2).map(s => `<span class="chip chip-soft">${esc(s)}</span>`).join('')}
              ${d.key_signals.length > 2 ? `<span class="chip" style="color:var(--faint)">+${d.key_signals.length-2} more</span>` : ''}
            </div>` : ''}
          </div>
          <div class="qconf">
            <div class="c-label">Confidence</div>
            <div class="c-val" style="color:${d.confidence<0.6?'#f97316':'#22c55e'}">${d.confidence.toFixed(2)}</div>
            ${confBar(d.confidence)}
          </div>
        </div>`).join('')}
    </div>`;

  // hero distribution chart
  const sorted = q.slice().sort((x,y) => x.score - y.score);
  const ctx = $('chDist').getContext('2d');
  const grad = ctx.createLinearGradient(0,0,0,190);
  grad.addColorStop(0,'rgba(228,228,231,.22)'); grad.addColorStop(1,'rgba(228,228,231,0)');
  chart('chDist', {type:'line',
    data:{labels:sorted.map(d => d.id.replace(/^[A-Z]+_/,'#')),
      datasets:[{data:sorted.map(d => d.score), fill:true, backgroundColor:grad, borderColor:'#a1a1aa',
        borderWidth:2, tension:.4, pointRadius:4, pointHoverRadius:6,
        pointBackgroundColor:sorted.map(d => riskColor(d.band)), pointBorderColor:'#141416', pointBorderWidth:2}]},
    options:{responsive:true, maintainAspectRatio:false, animation:{duration:900},
      plugins:{tooltip:{callbacks:{title:i => sorted[i[0].dataIndex].name,
        label:i => `score ${i.raw} · ${sorted[i.dataIndex].action}`}}},
      scales:{x:{grid:{display:false}, ticks:{font:{size:9}, color:'#52525b'}},
              y:{min:0, max:100, grid:{color:'#232326'}, ticks:{stepSize:25, font:{size:10}}}}}});

  barChart('chBands', ['Low','Medium','High'], [a.bands.LOW, a.bands.MED, a.bands.HIGH], ['#22c55e','#f59e0b','#ef4444']);
  chart('chActions', {type:'doughnut', data:{labels:['Auto-clear','Review','Escalate','Human queue'],
      datasets:[{data:[a.actions.AUTO_CLEAR, a.actions.REVIEW, a.actions.ESCALATE, a.actions.PENDING_REVIEW],
        backgroundColor:['#22c55e','#f59e0b','#ef4444','#f97316'], borderColor:'#141416', borderWidth:2}]},
    options:{cutout:'62%', responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:true, position:'right', labels:{boxWidth:9, font:{size:11}, padding:9}}}}});
  const pl = Object.keys(a.patterns);
  if (pl.length) barChart('chPats', pl, Object.values(a.patterns), pl.map(() => '#71717a'));
  else $('chPats').closest('.card').innerHTML = `<p class="section-label" style="margin:0 0 10px">Detected patterns</p>
    <p style="color:var(--faint);font-size:13px;text-align:center;padding:44px 0">No typology candidates in this population.</p>`;

  revealAll();
  document.querySelectorAll('.cu').forEach(n => countUp(n, +n.dataset.to));
  setTimeout(() => { if ($('apbar')) $('apbar').style.width = autoPct + '%'; if ($('apct')) countUp($('apct'), autoPct, 900); }, 260);
}

/* ───────────── Case drawer ───────────── */
async function openCase(cid){
  $('drawer').classList.remove('hidden');
  $('drawer-body').innerHTML = `<div class="empty"><div class="e-ico">⏳</div><p>Loading case…</p></div>`;
  const [d, hist] = await Promise.all([api('/api/case/'+cid), api(`/api/case/${cid}/history`).catch(() => [])]);
  const cap = s => (s||'').replace(/^\w/, c => c.toUpperCase());
  const ops = d.opinions || [], trace = d.trace || [], im = d.injected_memory || {};
  const tx  = d.dossier?.transactions || [], docs = d.dossier?.documents || [];

  $('drawer-body').innerHTML = `
    <div class="dhead">
      ${gauge(d.score, d.band)}
      <div style="flex:1;min-width:0">
        <h3 style="font-size:18px;font-weight:800;letter-spacing:-.02em">${esc(d.name)}</h3>
        <p style="color:var(--muted);font-size:13px;margin-top:2px">${d.id} · ${esc(d.occupation)} · ${esc(d.country)}</p>
        <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:9px">
          ${actionBadge(d.action)}<span class="chip">confidence ${d.confidence.toFixed(2)}</span><span class="chip">${esc(d.engine_path)}</span></div>
      </div>
      <button class="icon-btn" onclick="closeDrawer()" style="font-size:17px">✕</button>
    </div>

    <div class="dbody">
      <div class="dsec"><h4>AI risk summary</h4>
        <div class="card card-pad" style="font-size:13.5px;line-height:1.65">${esc(d.summary)}</div>
        ${(d.key_signals?.length) ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px">
          ${d.key_signals.map(s => `<span class="chip chip-soft">${esc(s)}</span>`).join('')}</div>` : ''}
      </div>

      <div class="dsec"><h4>Parallel specialists — KYC · transactions · documents</h4>
        <div class="grid grid-3">${ops.length ? ops.map(o => `
          <div class="card card-pad">
            <div style="display:flex;align-items:center;gap:7px;font-weight:700;font-size:13.5px">
              <span style="width:8px;height:8px;border-radius:50%;background:${LVL[o.risk_level]||'#71717a'}"></span>
              ${esc(cap(o.domain))}<span style="color:var(--faint);font-weight:500">${o.tentative_score ?? ''}</span></div>
            <p style="color:var(--muted);font-size:12.5px;margin-top:7px;line-height:1.55">${esc(o.note||'')}</p>
            ${(o.signals?.length) ? `<div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:8px">
              ${o.signals.slice(0,3).map(s => `<span class="chip chip-soft" style="font-size:10.5px">${esc(s)}</span>`).join('')}</div>` : ''}
          </div>`).join('') : `<p style="color:var(--faint);font-size:13px">No specialist opinions.</p>`}</div>
      </div>

      <div class="dsec"><h4>Agent investigation — serial tool-call trace</h4>
        <div class="card card-pad">
          ${trace.length ? `<div class="trace-list">${trace.map((t,i) => `
            <div class="trace-item"><span class="t-n">${i+1}.</span>
              <span class="chip">${esc(t.tool)}</span>
              <span class="t-args">${esc(JSON.stringify(t.args||{}))}</span></div>`).join('')}</div>` :
            `<p style="color:var(--faint);font-size:13px">No trace recorded.</p>`}
          ${(d.evidence_refs?.length) ? `<p style="font-size:12px;color:var(--faint);margin-top:11px">
            Cited evidence: ${d.evidence_refs.map(esc).join(', ')}</p>` : ''}
        </div></div>

      <div class="grid grid-2">
        <div class="dsec"><h4>Memory injected</h4>
          <div class="card card-pad">
            <div style="display:flex;gap:7px;flex-wrap:wrap">
              <span class="chip">history: ${im.history_n ?? 0}</span>
              <span class="chip">similar cases: ${im.similar_n ?? 0}</span>
              <span class="chip">lessons: ${im.lessons_n ?? 0}</span></div>
            ${im.history_summary ? `<p style="font-size:12px;color:var(--faint);margin-top:9px">${esc(im.history_summary)}</p>` : ''}
          </div></div>
        <div class="dsec"><h4>Per-customer history</h4>
          <div class="card card-pad">${(hist?.length > 1) ? hist.map(h => `
            <div style="display:flex;gap:9px;font-size:12.5px;color:var(--muted);padding:3px 0">
              <span style="color:var(--faint)">${(h.ts||'').slice(0,10)}</span>
              <b style="color:${riskColor(h.band)}">${bandUp(h.band)} (${h.score})</b>
              <span style="color:var(--faint)">${esc(h.disposition||'')}</span>
              ${h.human_verified ? '<span style="color:#22c55e">✓ reviewer</span>' : ''}</div>`).join('')
            : `<p style="font-size:12.5px;color:var(--faint)">First assessment on file — history builds as this customer is re-scored.</p>`}
          </div></div>
      </div>

      <div class="dsec"><h4>Detected patterns (advisory)</h4>
        <div class="card card-pad">${d.patterns?.length ? d.patterns.map(p => `
          <div style="margin-bottom:12px">
            <div style="display:flex;gap:9px;align-items:flex-start;flex-wrap:wrap">
              <span class="badge" style="background:#ef44441f;color:#fca5a5">⚠ ${esc(p.label)}${p.strength!=null?` · ${p.strength}`:''}</span>
              <span style="font-size:12.5px;color:var(--muted);flex:1;min-width:200px">${esc(p.rationale)}</span></div>
            <p style="font-size:11.5px;color:var(--faint);font-style:italic;margin-top:5px">${esc(patternDef(p.label))}</p>
          </div>`).join('') : `<p style="font-size:13px;color:var(--faint)">No transaction-pattern candidates surfaced.</p>`}
        </div></div>

      <div class="dsec"><h4>Transactions ${tx.length ? `(${tx.length}, anomalies highlighted)` : '(none on file)'}</h4>
        <div class="card card-pad" style="overflow-x:auto">
          <table class="tx">${tx.slice().sort((a,b) => a.date < b.date ? 1 : -1).slice(0,40).map(t => `
            <tr class="${t.anomalous?'anom':''}">
              <td style="color:var(--faint)">${t.date}</td>
              <td>${t.direction==='in'?'▲':'▼'} £${t.amount.toLocaleString()}</td>
              <td style="color:var(--muted)">${esc(t.type)}</td>
              <td style="color:var(--muted)">${esc(t.counterparty)} <span style="color:var(--faint)">${esc(t.cp_country)}</span></td>
              <td>${t.anomalous?'<span class="chip" style="background:#ef44441f;color:#fca5a5">anomaly</span>':''}</td></tr>`).join('')}
          </table></div></div>

      <div class="dsec"><h4>Dossier &amp; documents</h4>
        <details class="doc card card-pad"><summary>📋 KYC / screening (structured)</summary>
          <pre>${esc(JSON.stringify({kyc:d.dossier?.kyc, screening:d.dossier?.screening}, null, 1))}</pre></details>
        ${docs.map(x => `<details class="doc card card-pad"><summary>📄 ${esc(x.name)}</summary>
          <pre>${esc(x.text)}</pre></details>`).join('')}
      </div>
    </div>`;
}
const closeDrawer = () => $('drawer').classList.add('hidden');

/* ───────────── Review Queue ───────────── */
async function renderReview(gen = _navGen){
  const pend = await api('/api/review');
  if (staleNav(gen)) return;
  window._PEND = pend;
  if (!pend.length){
    $('content').innerHTML = emptyState('✅','Queue is empty',
      'The agent was confident on every case — nothing needs a human decision right now. Low-confidence cases appear here automatically.');
    return;
  }
  $('content').innerHTML = `
    <p style="color:var(--muted);font-size:13.5px;margin-bottom:14px">
      <b style="color:var(--ink)">${pend.length}</b> case(s) awaiting a human decision. Setting the correct score teaches the model.</p>
    <div class="grid" style="gap:12px">
      ${pend.map((c,i) => `
        <div class="card card-pad fade">
          <div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
            ${gauge(c.llm_score ?? 0, 'MED')}
            <div style="flex:1;min-width:0">
              <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <b style="font-size:15px">${esc(c.name)}</b><span class="chip">${c.customer_id}</span>
                <span class="badge" style="background:#f973161f;color:#f97316">confidence ${(c.confidence||0).toFixed(2)}</span></div>
              <p style="color:var(--muted);font-size:13px;margin-top:7px;
                 display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden">${esc(c.reason||'')}</p>
            </div>
            <button class="btn btn-primary" onclick="openReview(${i})" style="flex:0 0 auto;margin-left:auto">Review →</button>
          </div>
          <div class="grid grid-3" style="margin-top:14px">
            ${(c.opinions||[]).map(o => `<div class="card card-pad" style="background:var(--panel2)">
              <div style="display:flex;align-items:center;gap:6px;font-size:12.5px;font-weight:700">
                <span style="width:7px;height:7px;border-radius:50%;background:${LVL[o.risk_level]||'#71717a'}"></span>${esc(o.domain)}</div>
              <p style="color:var(--muted);font-size:12px;margin-top:5px;line-height:1.5">${esc(o.note||'')}</p></div>`).join('')}
          </div>
        </div>`).join('')}
    </div>`;
}
function openReview(i){
  const c = window._PEND[i];
  $('drawer').classList.remove('hidden');
  $('drawer-body').innerHTML = `
    <div class="dhead">
      ${gauge(c.llm_score ?? 0, 'MED')}
      <div style="flex:1;min-width:0"><h3 style="font-size:18px;font-weight:800">${esc(c.name)}</h3>
        <p style="color:var(--muted);font-size:13px">${c.customer_id}</p></div>
      <button class="icon-btn" onclick="closeDrawer()" style="font-size:17px">✕</button>
    </div>
    <div class="dbody">
      <div class="card card-pad" style="font-size:13.5px;line-height:1.6">
        The agent proposed <b>${c.llm_score}</b> at confidence
        <b style="color:#f97316">${(c.confidence||0).toFixed(2)}</b> — below the threshold, so it asked for a human.
        <p style="color:var(--muted);font-size:13px;margin-top:9px">${esc(c.reason||'')}</p></div>

      <div class="dsec"><h4>Specialist opinions</h4>
        <div class="grid grid-3">${(c.opinions||[]).map(o => `
          <div class="card card-pad"><div style="display:flex;align-items:center;gap:6px;font-size:12.5px;font-weight:700">
            <span style="width:7px;height:7px;border-radius:50%;background:${LVL[o.risk_level]||'#71717a'}"></span>${esc(o.domain)}</div>
            <p style="color:var(--muted);font-size:12px;margin-top:5px">${esc(o.note||'')}</p></div>`).join('')}</div></div>

      <div class="dsec"><h4>Your decision — this teaches the model</h4>
        <div class="card card-pad">
          <label style="font-size:13px;color:var(--muted)">Correct score: <b id="rvS" style="color:var(--ink)">${c.llm_score||50}</b></label>
          <input id="rvScore" type="range" min="0" max="100" value="${c.llm_score||50}" style="width:100%;margin:10px 0"
            oninput="document.getElementById('rvS').textContent=this.value">
          <div class="grid" style="grid-template-columns:1fr 1fr;gap:10px;margin-top:6px">
            <select id="rvBand" class="field"><option>LOW</option><option selected>MED</option><option>HIGH</option></select>
            <select id="rvAction" class="field"><option>AUTO_CLEAR</option><option selected>REVIEW</option><option>ESCALATE</option></select>
          </div>
          <textarea id="rvNote" rows="3" class="field" style="margin-top:10px;resize:vertical"
            placeholder="Correction note — why? (this becomes a lesson the model learns)"></textarea>
          <button class="btn btn-primary btn-block" style="margin-top:12px"
            onclick="submitReview('${c.customer_id}')">✓ Submit &amp; teach the model</button>
        </div></div>
    </div>`;
}
async function submitReview(cid){
  await jpost(`/api/review/${cid}/resolve`, {score:+$('rvScore').value, band:$('rvBand').value,
    action:$('rvAction').value, note:$('rvNote').value});
  closeDrawer(); go('review');
}

/* ───────────── Ingest ───────────── */
async function renderIngest(gen = _navGen){
  const samples = await api('/api/samples');
  if (staleNav(gen)) return;
  $('content').innerHTML = `
    <div class="grid grid-2" style="align-items:start">
      <div class="card card-pad">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:12px">
          <div><b style="font-size:15px">Sample profiles</b>
            <p style="color:var(--muted);font-size:12.5px;margin-top:3px">${samples.length} available — tick any subset, or select all.</p></div>
          <label style="display:flex;align-items:center;gap:7px;font-size:13px;color:var(--muted);cursor:pointer;white-space:nowrap">
            <input type="checkbox" id="selAll" onchange="toggleAll(this.checked)"> Select all</label>
        </div>
        <div style="max-height:290px;overflow-y:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:2px;margin-bottom:14px">
          ${samples.map(s => `<label style="display:flex;align-items:center;gap:7px;padding:6px 8px;border-radius:7px;font-size:12.5px;cursor:pointer"
            onmouseover="this.style.background='var(--panel2)'" onmouseout="this.style.background=''">
            <input type="checkbox" class="smp" value="${s}" onchange="updateSel()"><span>${esc(s)}</span></label>`).join('')}
        </div>
        <button class="btn btn-primary btn-block" onclick="scoreSelected()">▶ Score selected (<span id="selCount">0</span>) in parallel</button>
        <p style="font-size:11.5px;color:var(--faint);text-align:center;margin-top:9px">
          Each customer runs parallel specialists + an agentic orchestrator · bounded concurrency · keeps running if you switch pages.</p>
      </div>

      <div class="card card-pad">
        <b style="font-size:15px">📤 Upload files</b>
        <p style="color:var(--muted);font-size:12.5px;margin:6px 0 10px">Drop one customer's documents:</p>
        <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:14px">
          ${['kyc.json','account.json','transactions.csv','screening.json','*.txt'].map(f => `<span class="chip">${f}</span>`).join('')}</div>
        <input id="upFiles" type="file" multiple style="font-size:12.5px;width:100%">
        <button class="btn btn-alt btn-block" style="margin-top:12px" onclick="ingestFiles()">▶ Score uploaded files</button>
        <p style="font-size:11.5px;color:var(--faint);text-align:center;margin-top:9px">Missing files are fine — the agent works with what's there.</p>
      </div>
    </div>
    <div id="batchArea" style="margin-top:16px"></div>
    <div id="ingestResult" style="margin-top:16px"></div>`;
  restoreBatch();
}
const _selected = () => [...document.querySelectorAll('.smp:checked')].map(c => c.value);
const updateSel = () => { if ($('selCount')) $('selCount').textContent = _selected().length; };
const toggleAll = on => { document.querySelectorAll('.smp').forEach(c => c.checked = on); updateSel(); };

const JOB = { get id(){ return sessionStorage.getItem('frisk_job') || ''; },
              set id(v){ v ? sessionStorage.setItem('frisk_job', v) : sessionStorage.removeItem('frisk_job'); } };
function restoreBatch(){ if (JOB.id){ $('batchArea').innerHTML = batchShell(window._bTotal||0, window._bWorkers||6); pollBatch(JOB.id); } }

const batchShell = (total, workers) => `<div class="card card-pad">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:10px">
    <div><b style="font-size:14.5px">⚙ Batch scoring</b>
      <span style="color:var(--faint);font-size:12.5px"> — up to ${workers} at once</span>
      <p style="font-size:11.5px;color:var(--faint);margin-top:2px">Keeps running if you switch pages.</p></div>
    <span id="bpText" style="font-size:13px;color:var(--muted);white-space:nowrap">0 / ${total} scored</span></div>
  <div class="bar" style="height:9px"><i id="bpBar" style="width:0%;background:linear-gradient(90deg,#a1a1aa,#e4e4e7);transition:width .4s"></i></div>
  <p id="bpDone" style="font-size:12px;color:var(--faint);margin:9px 0 14px">Scoring…</p>
  <div id="bResults" class="grid grid-2" style="gap:9px"></div></div>`;

const batchCard = r => r.error
  ? `<div class="card card-pad" style="font-size:13px;border-color:#ef444455"><b>${esc(r.name)}</b> <span style="color:#ef4444">✕ ${esc(r.error).slice(0,60)}</span></div>`
  : `<div class="card qrow fade" style="padding:12px" onclick="openCase('${r.id}')">
      ${gauge(r.score, r.band)}
      <div class="qmain"><div class="qhead"><b style="font-size:13.5px">${esc(r.name)}</b>
        <span class="chip">${r.id}</span></div>
        <div class="qsig" style="margin-top:6px">${actionBadge(r.action)}<span class="chip">conf ${(r.confidence||0).toFixed(2)}</span>${patternChips(r.patterns)}</div>
      </div></div>`;

async function scoreSelected(){
  const ids = _selected();
  if (!ids.length){ $('batchArea').innerHTML = `<p style="font-size:13px;color:#f59e0b">Select at least one profile.</p>`; return; }
  const j = await jpost('/api/ingest/batch', {ids});
  JOB.id = j.job_id; window._bTotal = j.total; window._bWorkers = j.workers;
  $('batchArea').innerHTML = batchShell(j.total, j.workers);
  pollBatch(j.job_id);
}
async function pollBatch(job_id){
  const j = await api('/api/ingest/batch/'+job_id);
  if (j.error){ JOB.id = ''; return; }
  window._bTotal = j.total; window._bWorkers = j.workers;
  const pct = j.total ? Math.round(j.done / j.total * 100) : 0;
  if ($('bpBar')){
    $('bpBar').style.width = pct + '%';
    $('bpText').textContent = `${j.done} / ${j.total} scored`;
    $('bResults').innerHTML = (j.results||[]).map(batchCard).join('');
  }
  if (j.status !== 'complete'){ clearTimeout(window._bT); window._bT = setTimeout(() => pollBatch(job_id), 1500); return; }
  refreshStats();
  const rev = (j.results||[]).filter(r => r.action === 'PENDING_REVIEW').length;
  if ($('bpDone')) $('bpDone').innerHTML = `✓ Complete · ${j.total} scored${rev?` · <b style="color:#f97316">${rev} routed to Human Review</b>`:''} · click a card to open the case.`;
}
async function ingestFiles(){
  const fs = $('upFiles').files; if (!fs.length) return;
  const fd = new FormData(); for (const f of fs) fd.append('files', f);
  $('ingestResult').innerHTML = `<p style="color:var(--muted);font-size:13px">Scoring uploaded files…</p>`;
  const d = await api('/api/ingest/files', {method:'POST', body:fd});
  $('ingestResult').innerHTML = `<div class="card qrow fade" onclick="openCase('${d.id}')">
    ${gauge(d.score, d.band)}
    <div class="qmain"><div class="qhead"><b style="font-size:15px">${esc(d.name)}</b><span class="chip">${d.id}</span>
      ${actionBadge(d.action)}<span class="chip">conf ${d.confidence.toFixed(2)}</span></div>
      <p class="qsum">${esc(d.summary)}</p></div></div>`;
  refreshStats();
}

/* ───────────── Audit ───────────── */
async function renderAudit(gen = _navGen){
  const rows = await api('/api/audit');
  if (staleNav(gen)) return;
  if (!rows.length){ $('content').innerHTML = emptyState('📜','No audit records yet','Every decision — cleared or escalated — is appended here with its tool-call trace.'); return; }
  $('content').innerHTML = `<div class="card" style="overflow-x:auto">
    <table class="tx" style="min-width:720px">
      <thead><tr style="color:var(--faint);text-align:left">
        ${['Time','Customer','Actor','Action','Score','Conf','Path'].map(h => `<th style="padding:12px;font-size:11px;text-transform:uppercase;letter-spacing:.1em">${h}</th>`).join('')}
      </tr></thead>
      <tbody>${rows.map(r => `<tr>
        <td style="padding:11px 12px;color:var(--faint)">${(r.ts||'').slice(0,19).replace('T',' ')}</td>
        <td style="padding:11px 12px">${esc(r.customer_id)}</td>
        <td style="padding:11px 12px;color:var(--muted)">${esc(r.actor)}</td>
        <td style="padding:11px 12px">${actionBadge(r.action)}</td>
        <td style="padding:11px 12px">${r.score >= 0 ? r.score : '—'}</td>
        <td style="padding:11px 12px">${r.confidence >= 0 ? Number(r.confidence).toFixed(2) : '—'}</td>
        <td style="padding:11px 12px;color:var(--faint)">${esc(r.engine_path)}</td></tr>`).join('')}
      </tbody></table></div>`;
}

/* ───────────── Case Comparison ───────────── */
let _CMP = [];
let _cmpGen = 0;   // runCompare() is user-triggered (dropdown), guarded separately from nav
async function renderCompare(gen = _navGen){
  _CMP = await api('/api/queue');
  if (staleNav(gen)) return;
  _cmpGen = gen;
  if (_CMP.length < 2){ $('content').innerHTML = emptyState('⚖️','Need at least two scored cases','Score a few customers first, then come back to compare them side by side.'); return; }
  const opts = sel => _CMP.map(d => `<option value="${d.id}" ${d.id===sel?'selected':''}>${esc(d.name)} — ${d.id} (${d.score})</option>`).join('');
  const hi = _CMP[0].id, lo = _CMP[_CMP.length-1].id;
  $('content').innerHTML = `
    <div class="card card-pad" style="margin-bottom:16px">
      <div class="grid" style="grid-template-columns:1fr auto 1fr;gap:14px;align-items:end">
        <div><p class="section-label" style="margin:0 0 6px">Case A</p>
          <select id="cmpA" class="field" onchange="runCompare()">${opts(hi)}</select></div>
        <div style="font-size:20px;color:var(--faint);padding-bottom:8px">vs</div>
        <div><p class="section-label" style="margin:0 0 6px">Case B</p>
          <select id="cmpB" class="field" onchange="runCompare()">${opts(lo)}</select></div>
      </div>
    </div>
    <div id="cmpOut"></div>`;
  runCompare();
}
const cmpCol = (d, other) => {
  const diff = (v, o) => v === o ? '' : 'style="color:var(--ink);font-weight:700"';
  return `<div class="card card-pad">
    <div style="display:flex;gap:14px;align-items:flex-start;margin-bottom:14px">
      ${gauge(d.score, d.band)}
      <div style="min-width:0"><b style="font-size:15px">${esc(d.name)}</b>
        <p style="color:var(--muted);font-size:12.5px;margin-top:2px">${d.id} · ${esc(d.occupation)} · ${esc(d.country)}</p>
        <div style="margin-top:8px">${actionBadge(d.action)}</div></div>
    </div>
    <table class="tx" style="width:100%">
      <tr><td style="color:var(--faint)">Confidence</td><td ${diff(d.confidence,other.confidence)}>${d.confidence.toFixed(2)}</td></tr>
      <tr><td style="color:var(--faint)">Band</td><td ${diff(d.band,other.band)}>${bandUp(d.band)}</td></tr>
      <tr><td style="color:var(--faint)">PEP</td><td ${diff(d.pep,other.pep)}>${d.pep?'Yes':'No'}</td></tr>
      <tr><td style="color:var(--faint)">KYC complete</td><td ${diff(d.kyc_complete,other.kyc_complete)}>${d.kyc_complete?'Yes':'No'}</td></tr>
      <tr><td style="color:var(--faint)">Transactions</td><td ${diff(d.txn_count,other.txn_count)}>${d.txn_count}</td></tr>
      <tr><td style="color:var(--faint)">Cash in</td><td ${diff(d.cash_in,other.cash_in)}>£${d.cash_in.toLocaleString()}</td></tr>
      <tr><td style="color:var(--faint)">Total credits</td><td ${diff(d.credits,other.credits)}>£${d.credits.toLocaleString()}</td></tr>
      <tr><td style="color:var(--faint)">Counterparty countries</td><td>${d.cp_countries.join(', ')||'—'}</td></tr>
      <tr><td style="color:var(--faint)">Tool calls</td><td ${diff(d.tools_used,other.tools_used)}>${d.tools_used}</td></tr>
      <tr><td style="color:var(--faint)">Documents</td><td>${d.documents.length}</td></tr>
    </table>
    <p class="section-label" style="margin:16px 0 7px">Specialists</p>
    <div style="display:flex;flex-direction:column;gap:6px">
      ${(d.opinions||[]).map(o => `<div style="display:flex;align-items:center;gap:7px;font-size:12.5px">
        <span style="width:7px;height:7px;border-radius:50%;background:${LVL[o.risk_level]||'#71717a'};flex:0 0 auto"></span>
        <b>${esc(o.domain)}</b><span style="color:var(--faint)">${o.tentative_score ?? ''}</span>
        <span style="color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(o.note||'')}</span></div>`).join('')}
    </div>
    <p class="section-label" style="margin:16px 0 7px">AI rationale</p>
    <p style="font-size:12.5px;color:var(--muted);line-height:1.6">${esc(d.summary)}</p>
    <button class="btn btn-ghost btn-block" style="margin-top:14px" onclick="openCase('${d.id}')">Open full case →</button>
  </div>`;
};
async function runCompare(){
  const myGen = _cmpGen, navAtStart = _navGen;
  const a = $('cmpA').value, b = $('cmpB').value;
  if (a === b){ $('cmpOut').innerHTML = `<p style="color:#f59e0b;font-size:13px">Pick two different customers.</p>`; return; }
  $('cmpOut').innerHTML = `<p style="color:var(--muted);font-size:13px">Comparing…</p>`;
  const r = await api(`/api/compare?a=${a}&b=${b}`);
  if (staleNav(navAtStart) || myGen !== _cmpGen) return;   // left the page (or picked new options) mid-fetch
  if (r.error){ $('cmpOut').innerHTML = `<p style="color:#ef4444;font-size:13px">${esc(r.error)}</p>`; return; }
  const gap = Math.abs(r.score_delta);
  $('cmpOut').innerHTML = `
    <div class="card-accent card-pad" style="margin-bottom:14px;text-align:center">
      <p class="section-label" style="margin:0 0 6px">Score gap</p>
      <div style="font-size:38px;font-weight:900;letter-spacing:-.04em;line-height:1">${gap}<span style="font-size:18px;color:var(--faint)"> pts</span></div>
      <p style="color:var(--muted);font-size:13px;margin-top:8px">
        <b style="color:${riskColor(r.a.band)}">${esc(r.a.name)}</b> ${r.a.score} · ${r.a.action}
        &nbsp;vs&nbsp; <b style="color:${riskColor(r.b.band)}">${esc(r.b.name)}</b> ${r.b.score} · ${r.b.action}</p>
    </div>
    <div class="grid grid-2" style="margin-bottom:14px">
      <div class="card card-pad"><p class="section-label" style="margin:0 0 9px">Signals only in ${esc(r.a.name)}</p>
        <div style="display:flex;gap:6px;flex-wrap:wrap">${r.only_a.length ? r.only_a.map(s => `<span class="chip chip-soft">${esc(s)}</span>`).join('') : '<span style="color:var(--faint);font-size:12.5px">none</span>'}</div></div>
      <div class="card card-pad"><p class="section-label" style="margin:0 0 9px">Signals only in ${esc(r.b.name)}</p>
        <div style="display:flex;gap:6px;flex-wrap:wrap">${r.only_b.length ? r.only_b.map(s => `<span class="chip chip-soft">${esc(s)}</span>`).join('') : '<span style="color:var(--faint);font-size:12.5px">none</span>'}</div></div>
    </div>
    ${r.shared_signals.length ? `<div class="card card-pad" style="margin-bottom:14px">
      <p class="section-label" style="margin:0 0 9px">Shared signals</p>
      <div style="display:flex;gap:6px;flex-wrap:wrap">${r.shared_signals.map(s => `<span class="chip">${esc(s)}</span>`).join('')}</div></div>` : ''}
    <div class="grid grid-2">${cmpCol(r.a, r.b)}${cmpCol(r.b, r.a)}</div>`;
}

/* ───────────── SAR drafts ───────────── */
async function renderSar(gen = _navGen){
  const q = await api('/api/queue');
  if (staleNav(gen)) return;
  const flagged = q.filter(d => ['ESCALATE','REVIEW','PENDING_REVIEW'].includes(d.action));
  if (!flagged.length){ $('content').innerHTML = emptyState('📋','Nothing to report','No case currently warrants a Suspicious Activity Report — every customer auto-cleared.'); return; }
  $('content').innerHTML = `
    <p style="color:var(--muted);font-size:13.5px;margin-bottom:14px">
      <b style="color:var(--ink)">${flagged.length}</b> case(s) may warrant a filing. Generate a draft narrative from the agent's evidence — then review, edit and sign off.</p>
    <div class="grid" style="gap:10px">
      ${flagged.map(d => `<div class="card qrow">
        ${gauge(d.score, d.band)}
        <div class="qmain"><div class="qhead"><b style="font-size:15px">${esc(d.name)}</b>
          <span class="chip">${d.id}</span><span class="chip">${esc(d.occupation)}</span>${actionBadge(d.action)}</div>
          <p class="qsum">${esc(d.summary)}</p></div>
        <button class="btn btn-primary" style="flex:0 0 auto;align-self:center" onclick="openSar('${d.id}')">📋 Draft SAR</button>
      </div>`).join('')}
    </div>`;
}
async function openSar(cid){
  $('drawer').classList.remove('hidden');
  $('drawer-body').innerHTML = `<div class="empty"><div class="e-ico">📝</div><h3>Drafting SAR narrative…</h3>
    <p>Composing the report from the agent's evidence, cited transactions and specialist opinions.</p></div>`;
  const s = await api(`/api/case/${cid}/sar`);
  if (s.error){ $('drawer-body').innerHTML = `<div class="empty"><div class="e-ico">⚠️</div><h3>Could not draft</h3><p>${esc(s.error)}</p></div>`; return; }
  const PCOL = {HIGH:'#ef4444', MEDIUM:'#f59e0b', LOW:'#22c55e'};
  const today = new Date().toISOString().slice(0,10);
  const sec = (n, title, body) => `<section class="sar-sec"><h3><span class="sar-num">${n}</span>${title}</h3><p>${esc(body||'—')}</p></section>`;
  $('drawer-body').innerHTML = `
    <div class="dhead" style="justify-content:space-between">
      <div><h3 style="font-size:16px;font-weight:800">Suspicious Activity Report</h3>
        <p style="color:var(--muted);font-size:12.5px;margin-top:2px">Draft · ${s.customer_id}</p></div>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="btn btn-ghost" onclick="window.print()">🖨 Print / PDF</button>
        <button class="icon-btn" onclick="closeDrawer()" style="font-size:17px">✕</button></div>
    </div>
    <div class="dbody">
      <div class="sar-doc" id="sarDoc">
        <div class="sar-watermark">DRAFT</div>
        <header class="sar-head">
          <div class="sar-org"><b>FRISK</b><span>Financial Intelligence Unit</span></div>
          <h1>Suspicious Activity Report</h1>
          <p class="sar-sub">Confidential — prepared for internal review and MLRO sign-off</p>
        </header>
        <table class="sar-meta">
          <tr><td>Report reference</td><td>SAR-${s.customer_id}-${today.replace(/-/g,'')}</td>
              <td>Date prepared</td><td>${today}</td></tr>
          <tr><td>Subject</td><td>${esc(s.subject_name)}</td>
              <td>Customer ID</td><td>${s.customer_id}</td></tr>
          <tr><td>Risk score</td><td>${s.score}/100 (${bandUp(s.band)})</td>
              <td>Filing priority</td><td><b style="color:${PCOL[s.priority]||'#a1a1aa'}">${esc(s.priority)}</b></td></tr>
          <tr><td>Prepared by</td><td>Frisk agentic analyst</td>
              <td>Status</td><td><b style="color:#f59e0b">DRAFT — unsigned</b></td></tr>
        </table>
        ${sec(1,'Subject of the report', s.subject_summary)}
        ${sec(2,'Description of suspicious activity', s.suspicious_activity)}
        ${sec(3,'Supporting evidence', s.supporting_evidence)}
        ${sec(4,'Analysis and rationale', s.analysis)}
        ${sec(5,'Recommended action', s.recommended_action)}
        ${(s.evidence_refs?.length || s.key_signals?.length) ? `<section class="sar-sec"><h3><span class="sar-num">A</span>Appendix — cited evidence</h3>
          ${s.evidence_refs?.length ? `<p><b>Transaction / document references:</b> ${s.evidence_refs.map(esc).join(', ')}</p>` : ''}
          ${s.key_signals?.length ? `<p style="margin-top:7px"><b>Risk indicators:</b> ${s.key_signals.map(esc).join(' · ')}</p>` : ''}
        </section>` : ''}
        <footer class="sar-foot">
          <div class="sar-sign"><span>MLRO signature</span><i></i></div>
          <div class="sar-sign"><span>Date</span><i></i></div>
        </footer>
        <p class="sar-note">Machine-generated draft from the case evidence. It must be reviewed, corrected
          and signed by a qualified compliance officer before any regulatory filing.</p>
      </div>
      <button class="btn btn-ghost btn-block" onclick="closeDrawer();openCase('${s.customer_id}')">Open the underlying case →</button>
    </div>`;
}

/* ───────────── ⌘K palette ───────────── */
let _PAL = [];
async function openPalette(){
  $('palette').classList.remove('hidden'); $('pq').value = ''; $('pq').focus();
  try { _PAL = await api('/api/queue'); } catch { _PAL = []; }
  paletteFilter();
}
const closePalette = () => $('palette').classList.add('hidden');
function paletteFilter(){
  const q = ($('pq').value || '').toLowerCase();
  const hits = _PAL.filter(d => !q || [d.id,d.name,d.occupation,d.country].join(' ').toLowerCase().includes(q)).slice(0,8);
  $('presults').innerHTML = hits.length ? hits.map(d => `
    <div class="prow" onclick="closePalette();openCase('${d.id}')">
      <span class="badge" style="background:${riskColor(d.band)}1f;color:${riskColor(d.band)}">${d.score}</span>
      <span class="p-name">${esc(d.name)}</span>
      <span class="p-meta">${d.id} · ${esc(d.occupation)}</span>
      <span class="p-act">${actionBadge(d.action)}</span></div>`).join('')
    : `<p style="color:var(--faint);font-size:13px;text-align:center;padding:22px">No matching customers.</p>`;
}
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k'){ e.preventDefault(); openPalette(); }
  if (e.key === 'Escape'){ closePalette(); closeDrawer(); }
});

go('dashboard');
