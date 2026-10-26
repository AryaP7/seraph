/* C12 connected shell. News/map previews remain explicitly fabricated.
 *
 * FIX11. The request lifecycle used to be a bare `pending` boolean set on send
 * and cleared only by the next render: a lost or slow response latched it
 * forever and every later click was silently dropped. Tool forms were rebuilt
 * on each render, so a half-typed holdings JSON vanished whenever a result
 * arrived. And a response was rendered without checking it still belonged to
 * the run, date and role on screen.
 *
 * Now: one in-flight record with a bounded timeout, an explicit status line,
 * retry that reuses the SAME idempotency id (Python deduplicates on it),
 * drafts preserved across renders, and a result shown only when its context
 * matches the current selection. Python enforces all of this again server
 * side; this is the visible half, not the security boundary.
 *
 * T03 (audit finding R05). Role buttons used to change the projection and
 * leave the map on screen: `active` started at 'map' and every response ended
 * with `show(active)`, so all three clicks looked like nothing happened. And
 * clicking the ALREADY-ACTIVE role waited for `data.role !== previous.role`,
 * which can never become true — it timed out after 15s and blocked every
 * later request, with the status control hidden inside Tools.
 *
 * Now: each role has a landing route, a role response navigates to it, a
 * same-role click is acknowledged immediately as a no-op, and the request
 * status bar is global rather than living in one tab.
 */
(()=>{
let data=null, active='map';
/* T03: every role has a landing route, so a role click goes somewhere. */
const ROLE_HOME={retail:'console',institutional:'pillars',regulator:'tools'};
const ROLE_LABEL={retail:'RETAIL HOME',institutional:'INSTITUTIONAL HOME',
                  regulator:'REGULATOR HOME'};
/* The in-flight request: {id, op, args, sentAt, timer, context} or null. */
let inflight=null, lastStatus={state:'idle'}, drafts={};
const REQUEST_TIMEOUT_MS=15000;
const q=id=>document.getElementById(id), esc=x=>String(x??'Unavailable').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=x=>typeof x==='number'&&Number.isFinite(x)?x.toFixed(4):'Unavailable';
const tag='<span class="fabricated">FABRICATED PREVIEW</span>';
/* A portfolio weight is a share of a portfolio, not a measurement: eight
   decimal places on it suggest a precision the number does not have, and
   the retail panel was printing whatever float arrived. Two decimals, and
   a floor so a tiny holding reads as "<0.01%" rather than "0.00%". */
const pct=x=>{const n=Number(x);
 if(!Number.isFinite(n))return 'Unavailable';
 if(n>0&&n<0.01)return '<0.01%';
 return n.toFixed(2).replace(/\.?0+$/,'')+'%';};
/* The accounting scenario behind a duty change, or the reason there is
   none. A refusal with its reasons tells a reader more than a blank. */
function scenarioHTML(s){
 if(!s)return '';
 if(s.status!=='conditional_scenario')
  return '<p class="m">No accounting scenario: '
   +esc((s.reasons||['not applicable at this decision time']).join('; '))+'</p>';
 const change=Number(s.landed_component_change);
 return '<p class="m">Landed cost of '+esc(s.product)+' from '+esc(s.origin)
  +' into '+esc(s.destination)+': '
  +(Number.isFinite(change)?(change>=0?'+':'')+(change*100).toFixed(2)+'%':'Unavailable')
  +' (duty '+esc(s.old_rate)+' → '+esc(s.new_rate)+', from '+esc(s.effective_from)+'). '
  +esc(s.monetary_basis)+'. '+esc(s.assumption)+'. Not a return forecast.</p>';
}


const kv=(k,v)=>'<div class="ckv"><span>'+esc(k)+'</span><b>'+esc(v)+'</b></div>';
const json=x=>'<pre>'+esc(JSON.stringify(x,null,2))+'</pre>';
const card=(title,body)=>'<div class="ccard"><h4>'+esc(title)+'</h4><div class="cbody">'+body+'</div></div>';
const send=(type,extra={})=>parent.postMessage({isStreamlitMessage:true,type,...extra},'*');

/* --- request status -------------------------------------------------- */
const DRAFT_FIELDS=['holdings','shock-pillar','magnitude','horizon','xi-path','action-op','action-value'];
function captureDrafts(){for(const id of DRAFT_FIELDS){const n=q(id);if(n)drafts[id]=n.value;}}
function restoreDrafts(){for(const id of DRAFT_FIELDS){const n=q(id);if(n&&drafts[id]!==undefined)n.value=drafts[id];}}
function setStatus(state,detail){lastStatus={state,detail,at:Date.now()};renderStatus();}
/* T03: one status bar visible from every route, including the map. The old
   control lived inside Tools, so a stalled request on the map was invisible. */
function statusBar(){let n=q('req-status-global');
 if(!n){n=document.createElement('div');n.id='req-status-global';
  n.style.cssText='position:fixed;right:12px;bottom:12px;z-index:9999;'
   +'font:11px var(--mono,monospace);padding:7px 11px;border-radius:4px;'
   +'background:#15161a;border:1px solid #2b2d35;color:#c9c6bf;max-width:46ch';
  document.body.appendChild(n);}
 return n;}
function renderStatus(){renderStatusInto(statusBar());const n=q('req-status');
 if(n)renderStatusInto(n);}
function renderStatusInto(n){if(!n)return;
 const label={idle:'READY',pending:'SENDING…',succeeded:'DONE',failed:'FAILED',timed_out:'NO RESPONSE',discarded:'DISCARDED'}[lastStatus.state]||'READY';
 const colour={idle:'#77736b',pending:'#c9a63a',succeeded:'#4f9e6a',failed:'#d8776a',timed_out:'#d8776a',discarded:'#8b80ad'}[lastStatus.state]||'#77736b';
 n.innerHTML='<span style="color:'+colour+'">●</span> <b>'+esc(label)+'</b>'+(lastStatus.detail?' — '+esc(lastStatus.detail):'')
  +((lastStatus.state==='timed_out'||lastStatus.state==='failed')&&inflight?' <button id="req-retry">Retry</button>':'')
  +(lastStatus.state==='timed_out'?' <button id="req-cancel">Cancel</button>':'');
 n.setAttribute('role','status');n.setAttribute('aria-live','polite');
 n.style.display=(lastStatus.state==='idle'&&n.id==='req-status-global')?'none':'';
 const retryBtn=n.querySelector('[id$="req-retry"],#req-retry');
 const cancelBtn=n.querySelector('[id$="req-cancel"],#req-cancel');
 if(retryBtn)retryBtn.onclick=()=>retry();
 if(cancelBtn)cancelBtn.onclick=()=>{clearInflight();setStatus('idle','request cancelled; nothing was discarded server side');};}
function clearInflight(){if(inflight&&inflight.timer)clearTimeout(inflight.timer);inflight=null;}
function transmit(){captureDrafts();
 send('streamlit:setComponentValue',{value:{...inflight.args,op:inflight.op,id:inflight.id,
   run_id:inflight.context.run_id,date:inflight.context.date},dataType:'json'});
 inflight.timer=setTimeout(()=>{if(inflight)setStatus('timed_out',
   'no response in '+(REQUEST_TIMEOUT_MS/1000)+'s. Retry sends the same request id, so a '
   +'request that did arrive cannot be applied twice.');},REQUEST_TIMEOUT_MS);
 setStatus('pending',inflight.op);}
function request(op,args={}){if(!data)return;
 if(inflight){setStatus('pending','a '+inflight.op+' request is already in flight; wait or retry it');return;}
 inflight={id:crypto.randomUUID(),op,args,sentAt:Date.now(),timer:null,
   context:{run_id:data.run_id,date:data.date,role:data.role}};
 transmit();}
/* Retry reuses the same idempotency id: Python deduplicates on it, so a lost
   response can be recovered without risking a second journal event. */
function retry(){if(!inflight)return;if(inflight.timer)clearTimeout(inflight.timer);transmit();}
// Label original preserved previews at panel level, including drill-downs.
document.querySelectorAll('main .card h3').forEach(n=>n.insertAdjacentHTML('beforeend',tag));
q('ticker').insertAdjacentHTML('afterbegin',tag);q('online').textContent='1,019 desks · FABRICATED';
q('beaconKey').insertAdjacentHTML('afterbegin',tag);
/* The detail panel holds EITHER sourced news evidence or the original
   illustrative preview, and `showNewsDetail` says which by setting
   data-evidenced. Stamping FABRICATED on everything, as this did before,
   put that tag above real Federal Register headlines with working source
   links — which teaches the viewer to ignore the tag, and the tag is the
   only thing protecting the preview layer from being read as data. */
const EVIDENCED_NOTE='<div class="evidenced">EVIDENCED NEWS \u00b7 sourced '
 +'documents with links and timestamps. Impact hypotheses are qualitative '
 +'mechanisms, not measured losses, and are not SERAPH pillar output.</div>';
const detailTag=()=>{for(const id of ['dbody','siteinfo']){const n=q(id);
 if(!n||!n.childNodes.length)return;
 if(n.querySelector('.fabricated')||n.querySelector('.evidenced'))return;
 n.insertAdjacentHTML('afterbegin',n.getAttribute('data-evidenced')
  ?EVIDENCED_NOTE
  :tag+' News/asset estimation preview; not SERAPH pillar output.');}};
new MutationObserver(detailTag).observe(q('dbody'),{childList:true});new MutationObserver(detailTag).observe(q('siteinfo'),{childList:true});
/* F01. `history` is an OBJECT -- {rows, series, units, coverage,
   representativeness, note} -- since the FR41 benchmark overlay landed in
   `console_backend._history_with_benchmark`. This function still called
   `history.forEach`, so every render threw

     TypeError: history.forEach is not a function

   and because `renderConsole()` is called before the role toggles, the
   liveness banner, `applyNewsLayer()` and `show()`, the whole handler
   aborted. The console rendered nothing and news never updated.

   Normalised in ONE place rather than shape-checked per chart. A legacy
   list becomes {rows: list} with the benchmark declared unavailable, so an
   old payload renders a CSRS line instead of crashing. */
function historyOf(h){
 if(!h)return {rows:[],series:{available:false},units:{},coverage:{}};
 if(Array.isArray(h))return {rows:h,series:{available:false,
   label:'benchmark',source:'legacy payload carried no benchmark series'},
   units:{},coverage:{csrs_dates:h.length,matched:0,benchmark_missing:h.length}};
 return {rows:h.rows||[],series:h.series||{available:false},
   units:h.units||{},coverage:h.coverage||{},
   representativeness:h.representativeness,note:h.note};
}

/* One polyline per unbroken run, so a null stays a GAP. Forward-filling a
   missing index observation would draw a flat segment where there is no
   measurement, which is the specific thing FR41's overlay must not do. */
function polylines(values,scale,colour){
 let paths=[],s=[];
 values.forEach((v,i)=>{
  if(v==null){if(s.length>1)paths.push(s);s=[];return;}
  s.push((i/Math.max(1,values.length-1)*600)+','+scale(v));});
 if(s.length>1)paths.push(s);
 return paths.map(pts=>'<polyline points="'+pts.join(' ')
  +'" fill="none" stroke="'+colour+'" stroke-width="2"/>').join('');
}

function spark(h){
 const hist=historyOf(h),rows=hist.rows;
 if(!rows.length)return '<p class="muted">No scored dates in this run.</p>';
 /* CSRS is 0..1 by construction; the benchmark is a simple return centred on
    zero. Two different units, so two labelled scales -- a shared axis would
    make the benchmark look flat and invite reading one off the other. */
 const csrs=rows.map(r=>r.csrs==null?null:r.csrs);
 const ret=rows.map(r=>(r.benchmark_available&&r.benchmark_return!=null)
   ?r.benchmark_return:null);
 const seen=ret.filter(v=>v!=null).map(Math.abs);
 const span=seen.length?Math.max(0.01,Math.max.apply(null,seen)):0.01;
 const csrsChart='<svg viewBox="0 0 600 80" width="100%" role="img"'
  +' aria-label="CSRS history">'
  +polylines(csrs,v=>70-v*65,'#c9a63a')+'</svg>';
 let out='<div class="chart-row"><span class="axis">CSRS 0..1</span>'
  +csrsChart+'</div>';
 if(hist.series.available&&seen.length){
  out+='<div class="chart-row"><span class="axis">'
   +esc(hist.series.label||'benchmark')+' return &plusmn;'
   +(span*100).toFixed(1)+'%</span>'
   +'<svg viewBox="0 0 600 80" width="100%" role="img" aria-label="benchmark'
   +' return history"><line x1="0" y1="40" x2="600" y2="40"'
   +' stroke="#444" stroke-width="1"/>'
   +polylines(ret,v=>40-(v/span)*34,'#6a9ad8')+'</svg></div>';
  const cov=hist.coverage||{};
  out+=kv('Benchmark',esc(hist.series.source||'')+' · '
   +(cov.matched||0)+' of '+(cov.csrs_dates||0)+' dates matched'
   +(cov.benchmark_missing?(' · '+cov.benchmark_missing+' missing from '
     +esc(cov.first_missing||'')+', shown as gaps'):''));
  if(hist.units&&hist.units.benchmark)out+=kv('Units',esc(hist.units.benchmark));
  if(hist.representativeness)out+=kv('Representativeness',
    esc(typeof hist.representativeness==='string'?hist.representativeness
        :JSON.stringify(hist.representativeness)));
 }else{
  out+=kv('Benchmark',esc(hist.note||hist.series.source
    ||'the official index series is not available for these dates'));
 }
 return out;
}
function renderConsole(){const v=data.view;
 q('c_csrs').textContent=num(v.csrs);q('c_ci').textContent=num(v.ciLower)+' – '+num(v.ciUpper);
 q('c_level').textContent=(v.alertLevel||'unavailable').toUpperCase();q('c_level').style.color=({red:'#d8776a',amber:'#c9a63a',green:'#4f9e6a'})[v.alertLevel]||'#888';
 q('c_mode').textContent=v.reconciliationMode||'HISTORICAL';q('c_plain').textContent=v.explanation;
 q('c_fill').style.left=((v.ciLower||0)*100)+'%';q('c_fill').style.width=(((v.ciUpper||0)-(v.ciLower||0))*100)+'%';q('c_tick').style.left=((v.csrs||0)*100)+'%';
 q('c_sigcount').textContent='SAVED RUN';q('c_signals').innerHTML=kv('Decision',data.timestamp)+kv('Coverage',v.maskDegraded?'DEGRADED':'COMPLETE')+kv('Warning',data.warning_status);
 q('c_trends').innerHTML='<div style="width:100%">'+spark(data.history)+kv('Through',data.date)+'</div>';
 q('c_mask').innerHTML=data.mask?['hawkes','rmt','hamilton'].map((n,i)=>kv(n,data.mask[i]?'IN FUSION':'EXCLUDED')).join(''):'Detailed mask withheld for this role; degraded coverage shown above.';
 q('c_shapley').innerHTML=v.shapley?Object.entries(v.shapley).map(([k,x])=>kv(k,num(x))).join(''):'Not supplied to this role.';
 const xi=v.regimeProbabilities;
 q('c_stack').innerHTML=xi?xi.map((x,i)=>'<div style="width:'+x*100+'%;background:'+['#4f9e6a','#c9a63a','#b7362a'][i]+'"></div>').join(''):'';
 q('c_slabels').textContent=xi?xi.map(num).join(' / '):'Measured regime probabilities unavailable for fusion. Hamilton diagnostics remain separate.';
 q('c_fields').textContent=Object.keys(v).length+' FIELDS';q('c_access').textContent=data.role.toUpperCase()+' · server-projected payload. Local role switching is not authentication.';
 document.querySelectorAll('[data-field]').forEach(n=>{const field={shapley:'shapley',mask:'pillarScores',xi_src:'regimeProbabilities',mode:'reconciliationMode',ci:'ciLower'}[n.dataset.field];n.classList.toggle('locked',field&&!(field in v));});
}
function renderPillars(){['hawkes','rmt','hamilton'].forEach(name=>{const item=data.pillars?.[name];const preview=PREVIEW_PILLARS[name];q('p_'+name).innerHTML=card(name.toUpperCase(),item?kv('Source',item.origin)+kv('Model',item.model)+kv('Value',num(item.value))+kv('Timestamp',item.information_timestamp)+kv('Score eligible',item.score_eligible)+json(item.detail||{}):'Model internals are not supplied to this role.')+(item&&item.value==null?card('Unfilled design preview',tag+kv(preview.label,num(preview.val))+preview.rows.map(([k,v])=>kv(k,v)).join('')+'<p>Preview values are not used for scoring.</p>'):'');});}
/* F01. These were three fabricated numbers -- `FII net (example) -1200`,
   `DII net (example) 900`, `Residual share (example) 0.72` -- sitting where a
   measurement belongs. `console_backend.market_flow` has read real published
   prints from E14 since FR45/FR51 landed, and the payload has carried
   `data.flow` all along; the panel just never looked at it.

   `market_flow` already filters `date <= as_of`, so a historical decision
   cannot show a later print. Unavailability renders as the reason, not a
   placeholder: an empty panel that says why is honest, and an example number
   in a measurement's place is not, however it is labelled. */
function flowHTML(){
 const f=data.flow;
 if(!f)return '<p>No flow payload in this run.</p>';
 if(!f.available)return '<p>'+esc(f.reason||'flow unavailable')+'</p>'
  +(f.date?kv('Last stored print',esc(f.date)):'');
 let html=kv('FII net',num2(f.fiiNet))+kv('DII net',num2(f.diiNet))
  +kv('Residual share',num2(f.residualFlowShare));
 if(f.totalTurnoverCrore!=null)html+=kv('Cash turnover',num2(f.totalTurnoverCrore));
 html+=kv('As of',esc(f.date||'unknown'))+kv('Units',esc(f.units||''));
 if(f.basis)html+=kv('Basis',esc(f.basis));
 html+='<p>'+esc(f.scope||'')+'</p>';
 (f.warnings||[]).forEach(w=>{html+='<p class="warn">'+esc(w)+'</p>';});
 return html;
}

function num2(x){return x==null?'unavailable':(Math.round(x*100)/100).toString();}

function renderMethod(){q('m_flow').innerHTML=kv('Run',data.run_id)+kv('Decision',data.timestamp)+kv('Cutoff',data.cutoff)+kv('Mode',data.mode);q('m_std').textContent='Existing causal standardisation, reconciliation and CSRS pipeline. News estimates are a separate subsystem, not a source of these pillar scores.';q('m_status').innerHTML=kv('Engineering','Historical persisted integration')+kv('Predictive validation','Not established')+kv('News ingestion / estimator',newsConnectionLine())+kv('Authentication','Local role demo only');q('m_limits').innerHTML=json(data.limitations||['Experimental warnings; predictive skill unvalidated.'])+(data.manifest?json(data.manifest):'');}
function table(rows){if(!rows?.length)return 'No saved outputs.';const keys=Object.keys(rows[0]);return '<table><thead><tr>'+keys.map(k=>'<th>'+esc(k)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+keys.map(k=>'<td>'+esc(typeof r[k]==='object'?JSON.stringify(r[k]):r[k])+'</td>').join('')+'</tr>').join('')+'</tbody></table>';}
function resultView(result){if(!result)return 'No operation submitted for this run/date/role.';if(Array.isArray(result.value)&&(result.kind==='shock'||result.kind==='policy'))return '<p>'+esc(result.basis)+'</p>'+table(result.value.map((r,i)=>({step:i+1,csrs:num(r.csrs),warning:r.alert_level,conditional_lower:num(r.ci_lower),conditional_upper:num(r.ci_upper)})))+'<details><summary>Scenario metadata</summary>'+json(result)+'</details>';return json(result);}
function tools(){const professional=data.role!=='retail',reg=data.role==='regulator';let html=card('Portfolio holdings','<p>Enter current holdings as JSON: symbol, value, sector, optional quantity. Real exposure calculation uses no fabricated news flags.</p><textarea id="holdings" placeholder="Paste your holdings JSON list"></textarea><button id="portfolio-go">Calculate coverage</button>');
 if(professional)html+=card('Pillar shock simulator · C11 / C9','<p>Hypothetical ECDF-rank shock; excluded pillars remain excluded.</p><select id="shock-pillar"><option>hawkes</option><option>rmt</option><option>hamilton</option></select><input id="magnitude" type="number" min="-1" max="1" step="0.05" value="0.1" aria-label="Shock magnitude"><input id="horizon" type="number" min="1" max="60" value="5" aria-label="Horizon"><button id="shock-go">Run shock</button>')+card('Defensive playbook',json(data.view.playbook)+'<p>Open MY WORKSPACE to run a saved defensive comparison with supplied historical prices and costs. Guidance here remains distinct from that evaluated result.</p>')+card('Institutional / residual flow',tag+flowHTML());
 if(reg)html+=card('Counterfactual policy simulator','<p>Open MY WORKSPACE to select a fitted macro or policy artifact and enter named covariate paths. This control runs an explicit hypothetical regime path; equal or excluded weights may give an unchanged score.</p><textarea id="xi-path">[[0.8,0.15,0.05],[0.2,0.5,0.3]]</textarea><button id="policy-go">Run regime-path scenario</button>')+card('Regulator action journal','<p>Annotations for this historical alert; no real trading or circuit breaker execution.</p><select id="action-op"><option>create</option><option>update</option><option>delete</option></select><select id="action-value"><option>none</option><option>soft_warning</option><option>circuit_breaker</option></select><button id="action-go">Record action</button>'+json(data.action_log))+card('Institution exposures',data.view.institutionDecomposition?json(data.view.institutionDecomposition):'<p>No eligible institution submission is attached at this cutoff. Use INSTITUTION EXPOSURES to preview and accept submissions.</p>')+card('Directed sector contagion',data.view.contagionNetwork?json(data.view.contagionNetwork):'<p>No supported measured network artifact is attached at this cutoff.</p>');
 html+=card('Last operation','<div id="req-status"></div>'+discardedView()+resultView(data.result));return html;}
function discardedView(){const d=data.discarded_result;if(!d)return '';
 return '<p class="fabricated">RESULT DISCARDED</p><p>'+esc(d.reason)+'</p>'
  +(d.produced_for?kv('Produced for',JSON.stringify(d.produced_for)):'');}
function bindTools(){
 /* Inputs are restored before binding, and every keystroke is kept, so a
    render triggered by an arriving result cannot destroy a draft. */
 restoreDrafts();
 for(const id of DRAFT_FIELDS){const n=q(id);if(n){n.oninput=captureDrafts;n.onchange=captureDrafts;}}
 const bind=(id,op,args)=>{if(q(id))q(id).onclick=()=>{captureDrafts();try{request(op,args());}catch(e){setStatus('failed','input rejected: '+e.message);q('extra-content').insertAdjacentHTML('afterbegin',card('Input error',esc(e.message)));}}};
 bind('portfolio-go','portfolio',()=>({holdings:JSON.parse(q('holdings').value)}));bind('shock-go','shock',()=>({pillar:q('shock-pillar').value,magnitude:Number(q('magnitude').value),horizon:Number(q('horizon').value)}));bind('policy-go','policy',()=>({xi_path:JSON.parse(q('xi-path').value)}));bind('action-go','action',()=>({operation:q('action-op').value,action:q('action-value').value}));
 renderStatus();}
/* T13 (audit findings R07/R08). The console used to carry one flat claim —
   "MAP / NEWS / SECTOR / TICKER / WEATHER: FABRICATED PREVIEWS" — for every
   surface at once, so a surface that HAD been connected was still described
   as fabricated and a viewer could not tell the two apart. Status is now per
   surface, and it comes from the payload rather than from this string. */
/* How old is the data behind every surface, in words a reader can act on.
   `as_of` is the DECISION time and reads as "this is current", so when the
   sources are past the freshness policies they themselves declared, that has
   to be said plainly rather than left to be inferred from a ratio. */
function ageWords(mins){
 if(mins==null)return 'unknown age';
 if(mins<120)return Math.round(mins)+' min old';
 if(mins<2880)return (mins/60).toFixed(1)+' h old';
 return (mins/1440).toFixed(1)+' days old';
}

/* Two INDEPENDENT failures, and the second used to be invisible: the SOURCES
   can be late, or the WORKER can be dead. A dead worker whose sources were
   fetched recently looks perfectly healthy for up to three polling intervals,
   so that is reported first and in its own words. */
function stalenessNote(){
 const f=(data&&data.news&&data.news.freshness)||null;
 if(!f)return '';
 const parts=[];
 const w=f.worker||{};
 if(w.state==='never_started')
  parts.push('NO WORKER \u2014 nothing is fetching. These stories came from a '
   +'one-off run; the screen will keep re-rendering and never get newer.');
 else if(w.state==='stopped'||w.state==='failed')
  parts.push('WORKER '+String(w.state).toUpperCase()+' \u2014 last heartbeat '
   +ageWords(w.age_minutes)+'. Nothing is fetching'
   +(w.detail?' ('+w.detail+')':'')+'.');
 if(f.stale)
  parts.push('STALE \u2014 newest item '+ageWords(f.age_minutes)+'; '
   +f.late_sources+' of '+f.total_sources
   +' sources past the freshness policy they declared.');
 if(!parts.length)return '';
 parts.push('Nothing on screen reflects what has happened since.');
 return parts.join(' ');
}

/* The method panel used to state "Not connected — fabricated previews
   retained" as a constant, so it went on saying so after the channel was
   connected and nobody reading the method page learned otherwise. It is
   derived from the same payload the banner reads. */
function newsConnectionLine(){
 const news=data&&data.news;
 if(!news||news.status==='absent')
  return 'Not connected — fabricated previews retained'
   +((news&&news.reason)?' ('+esc(news.reason)+')':'');
 const connected=news.connected_surfaces||[],preview=news.preview_surfaces||[];
 const cov=news.source_coverage||{};
 const rights=cov.rights||{};
 const parts=[];
 parts.push(connected.length
  ? 'Connected: '+esc(connected.join(', '))
  : 'Connected, but no surface has data at this decision time');
 if(preview.length)parts.push('still fabricated preview: '+esc(preview.join(', ')));
 if(cov.total!=null)parts.push(esc(cov.covered)+'/'+esc(cov.total)+' feed(s) within their declared freshness policy');
 if(rights.total!=null)parts.push(esc(rights.reviewed)+'/'+esc(rights.total)+' source rights reviewed per use');
 const manifest=news.manifest||{};
 if(manifest.provenance)parts.push(esc(manifest.provenance)+' with '+esc(manifest.extractor||'current rules'));
 return parts.join(' · ');
}

function newsStatusLine(){
 const news=data&&data.news;
 if(!news||news.status==='absent')
  return 'MAP / NEWS / SECTOR: FABRICATED PREVIEWS \u2014 '
   +esc((news&&news.reason)||'news channel not connected');
 const connected=news.connected_surfaces||[],preview=news.preview_surfaces||[];
 const parts=[];
 // First, not last: a reader who stops reading after one clause must still
 // have been told the data is old.
 const stale=stalenessNote();
 if(stale)parts.push(stale);
 parts.push('NEWS '+(news.mode||'historical_decision')+' '+(news.as_of||'unknown'));
 const coverage=news.source_coverage||{};
 parts.push((coverage.covered||0)+'/'+(coverage.total||0)+' feeds fresh');
 if(connected.length)parts.push('CONNECTED: '+connected.join(', ').toUpperCase());
 if(preview.length)parts.push('FABRICATED PREVIEW: '+preview.join(', ').toUpperCase());
 const globe=news.globe||{};
 if(globe.nodes)parts.push(globe.nodes.length+' evidenced map node(s)');
 if((globe.review_queue||{}).count)
  parts.push((globe.review_queue.count)+' unplaced \u2192 review queue');
 return parts.join(' | ');}

/* Hand the news branch to the globe. The browser does not decide where a node
   goes or what it claims: positions and click detail are computed server side
   and only drawn here. */
function applyNewsLayer(){
 const ctx=data&&data.news&&data.news.context;
 if(ctx&&(ctx.run_id!==data.run_id||ctx.date!==data.date||ctx.role!==data.role||
   (ctx.news_mode==='historical_decision'&&ctx.news_as_of!==data.timestamp))) {
   setStatus('failed','news context mismatch');return null;}

 if(!window.SERAPH_GLOBE_API||!window.SERAPH_NEWS)return null;
 try{return window.SERAPH_GLOBE_API.applyNews(data&&data.news);}
 catch(err){setStatus('failed','news layer: '+err.message);return null;}}

let originalNewsPanels=null;

/* ---- institutional: the product/country shape of the exposure --------
   One route at a time never showed WHICH products, from WHICH origins,
   reach which sectors. A pair with no documented edge is absent here,
   not present with a zero: "no documented route" and "no exposure" are
   different claims and only the first is ours. */
function matrixHTML(matrix){
 if(!matrix||!(matrix.cells||[]).length)return '';
 const rows=matrix.cells.map(c=>({product:c.product,origin:c.origin_name||c.origin,
   target:c.target,mechanism:c.mechanism,role:c.target_role||'-',
   size:c.sized?(c.magnitude+' '+c.unit):'UNSIZED',
   events:(c.active_events||[]).length,confidence:c.confidence}));
 return card('PRODUCT \u00d7 COUNTRY EXPOSURE',
  '<p>'+esc(matrix.documented_pairs)+' documented pair(s); '
  +esc(matrix.unsized)+' unsized. '+esc(matrix.note)+'</p>'+table(rows));
}

/* ---- institutional: two instruments side by side ---------------------
   Offered only where two documents CITE the same instrument identifier,
   the same evidence standard the supersession linkage uses. */
function compareHTML(pairs){
 if(!(pairs||[]).length)return '';
 const options=pairs.map((p,i)=>'<option value="'+i+'">'+esc(p.instrument_id)
   +' \u2014 '+esc((p.earlier_headline||'').slice(0,60))+' \u2192 '
   +esc((p.later_headline||'').slice(0,60))+'</option>').join('');
 window.SERAPH_COMPARE_PAIRS=pairs;
 return card('COMPARE INSTRUMENTS',
  '<p>Pairs that cite the same instrument identifier. A similar headline is '
  +'not evidence that two documents are the same measure.</p>'
  +'<select id="news-compare-pair">'+options+'</select>'
  +'<button id="news-compare-go">Compare</button>');
}

/* ---- institutional: conditional scenario, with the caller's inputs ---
   Empty by default on purpose. A blank field is an unsupplied
   assumption; a pre-filled one would be an invented input. */
function scenarioFormHTML(view){
 const routes=(view.items||[]).filter(i=>i.event_id);
 const seen=new Set(),options=['<option value="historical:us-steel-10947">HISTORICAL EXAMPLE · India-origin covered steel · June 2025 · 25% to 50%</option>'];
 for(const r of routes){ if(seen.has(r.event_id))continue; seen.add(r.event_id);
  options.push('<option value="'+esc(r.event_id)+'">'+esc(r.target)+' \u00b7 '
   +esc(r.mechanism)+'</option>'); }
 return card('CONDITIONAL SCENARIO',
  '<p>Landed-cost arithmetic from the instrument\u2019s own stated rates. The two '
  +'inputs below are YOUR assumptions, recorded as such \u2014 they are not '
  +'observed company data. Leave them blank for the rate change alone; with '
  +'no old-duty-inclusive covered component cost there is no monetary range. The historical example is a curated June 2025 calculation, not a live policy claim.</p>'
  +'<select id="news-scenario-event">'+options.join('')+'</select>'
  +'<input id="news-scenario-base" type="number" min="0" step="any" '
  +'placeholder="Old-duty-inclusive component cost (optional)" aria-label="Eligible cost base">'
  +'<input id="news-scenario-low" type="number" min="0" max="1" step="0.05" '
  +'placeholder="Pass-through low 0-1" aria-label="Pass-through low">'
  +'<input id="news-scenario-high" type="number" min="0" max="1" step="0.05" '
  +'placeholder="Pass-through high 0-1" aria-label="Pass-through high">'
  +'<button id="news-scenario-go">Run scenario</button>');
}

/* F05a. What the screen is currently showing, so the export can name it.
   The export button used to send `{}`, so the server had nothing to
   reconstruct and the artefact carried neither the displayed scenario nor
   the comparison. These are IDENTIFIERS and INPUTS only: the server re-runs
   the scenario itself, because a browser-supplied result dictionary is not
   authority for what was computed. */
let shownAnalysis={analysis_id:null};
let exportURL=null;

function exportHTML(){
 const has=shownAnalysis.analysis_id;
 return card('EXPORT ANALYSIS',
  '<p>The displayed analysis with its evidence links, input assumptions, '
  +'processing manifest and limitations \u2014 so a reader who disagrees can '
  +'find the documents and the versions that produced it.</p>'
  +(has?'<p class="muted">Downloads the displayed result at its recorded decision time.</p>':'<p class="muted">Exports the current role matrix and evidence.</p>')
  +'<button id="news-export-go">Export displayed analysis</button>'
  +'<span id="news-export-dl"></span>');
}

/* A real file, not JSON on screen. The export is the artefact a reader takes
   away and checks, so it has to leave the browser. UTF-8 JSON is the format
   the plan fixed; the name carries the role and the decision time so two
   exports from different contexts cannot be confused. */
function offerExportDownload(result){
 const slot=q('news-export-dl');
 if(!slot||!result||result.kind!=='news_export')return;
 const stamp=String(result.decision_ts||result.exported_at||'')
   .replace(/[^0-9A-Za-z]/g,'').slice(0,14);
 const name='seraph-news-analysis-v1-'+String(result.analysis_id||'').slice(0,12)+'-'+stamp+'.json';
 try{
  const blob=new Blob([JSON.stringify(result,null,2)],
    {type:'application/json;charset=utf-8'});
  if(exportURL)URL.revokeObjectURL(exportURL);
  const url=exportURL=URL.createObjectURL(blob);
  slot.innerHTML='<a id="news-export-link" download="'+esc(name)+'" href="'
   +url+'">Download '+esc(name)+'</a>';
 }catch(err){
  slot.innerHTML='<span class="warn">This browser refused the download: '
   +esc(String(err&&err.message||err))+'. The analysis is shown below.</span>';
 }
}

/* ---- regulator: accept or reject a proposed instrument link ----------
   The queue was already on screen; a queue you cannot act on is not a
   review workflow. A reason is required, because a decision nobody can
   read the grounds for cannot be audited later. */
function reviewHTML(view){
 const block=(view.items||[]).find(i=>i.kind==='supersession_review');
 if(!block)return '';
 const rows=(block.unresolved||[]).concat(block.proposed||[]);
 if(!rows.length)return card('INSTRUMENT LINK REVIEW',
   '<p>Nothing is awaiting review at this decision time.</p>');
 const items=rows.map((r,i)=>{
  const later=r.event_id||r.later,earlier=r.earlier||'';
  return '<article class="news-review" data-later="'+esc(later)+'" data-earlier="'
   +esc(earlier)+'"><b>'+esc((r.headline||r.later_headline||later).slice(0,110))+'</b>'
   +'<p>'+esc(r.warning||r.reason||'')+'</p>'
   +(earlier?kv('Proposed predecessor',earlier):'<p>No predecessor is '
     +'identified. Enter one below only if you have established it from the '
     +'documents; this system will not guess it from a similar title.</p>')
   +'<input class="news-review-earlier" value="'+esc(earlier)+'" '
   +'placeholder="Earlier event id" aria-label="Earlier event id">'
   +'<input class="news-review-reason" placeholder="Reason (required)" '
   +'aria-label="Reason for this decision">'
   +'<button class="news-review-go" data-decision="confirmed">Accept link</button>'
   +'<button class="news-review-go" data-decision="rejected">Reject link</button>'
   +'</article>';}).join('');
 return card('INSTRUMENT LINK REVIEW',
  '<p>While a link is missing, the earlier order is still reported as in '
  +'force. A decision here changes later projections and changes no stored '
  +'document. You are acting as a LOCAL DEMO ROLE, not an authenticated '
  +'user, and the record says so.</p>'+items);
}

function roleNewsHTML(view){
 if(!view)return '<p>Role news view unavailable.</p>';
 const openEvents=ids=>ids.length?'<button class="role-news-evidence" data-events="'+esc(ids.join(' '))+'">Open source events</button>':'';
 const links=rows=>(rows||[]).filter(r=>/^https?:\/\//i.test(r.url||'')).map(r=>'<a target="_blank" rel="noopener noreferrer" href="'+esc(r.url)+'">'+esc(r.source_id||'Source document')+'</a>').join(' · ');
 let body=(view.notes||[]).map(n=>'<p>'+esc(n)+'</p>').join('');
 if(view.role==='retail'){
  body+=(view.items||[]).map(i=>'<article><b>'+esc(i.holding)+'</b>'
   +kv('Sector',i.sector||'Unknown')+kv('Current evidence',i.documented?'Matched':'No matched event')
   +(i.portfolio_weight_pct==null?'':kv('Portfolio weight (not loss)',pct(i.portfolio_weight_pct)))
   +(i.touching||[]).slice(0,3).map(t=>'<p>'+esc(t.direction+' · '+t.mechanism+' · '+t.target)+'</p>').join('')
   +((i.touching||[]).length>3?'<p>'+esc(i.touching.length-3)+' additional routes; open source events for the full evidence.</p>':'')
   +openEvents([...new Set((i.touching||[]).map(t=>t.event_id))])+'</article>').join('');
  body+=(view.uncovered||[]).map(i=>'<p><b>'+esc(i.holding)+' — UNMAPPED</b> '+esc(i.reason)+'</p>').join('');
  if(!(view.items||[]).length&&!(view.uncovered||[]).length)body+='<p>Add your holdings in Tools to see portfolio-specific news routes.</p>';
 }else if(view.role==='institutional'){
  body+=(view.items||[]).map(i=>'<details><summary>'+esc(i.target+' · '+i.direction+' · '+i.mechanism)+'</summary>'
   +kv('Evidence confidence',i.confidence)+kv('Exposure size',i.size==null?'UNSIZED':i.size+' '+i.unit)
   +(i.opposing?'<p>Opposing mechanisms</p>'+json(i.opposing):'')
   +scenarioHTML(i.scenario)
   +(i.unknowns||[]).concat(i.limitations||[]).map(s=>'<p>'+esc(s)+'</p>').join('')
   +'<p>'+esc((i.path||[]).join(' → '))+'</p>'+links(i.evidence_links)
   +openEvents(i.event_id?[i.event_id]:[])+'</details>').join('');
  if(!(view.items||[]).length)body+='<p>No documented impact routes at this decision time.</p>';
  body+=matrixHTML(view.matrix)+compareHTML(view.comparable)+scenarioFormHTML(view)+exportHTML();
 }else{
  body+=reviewHTML(view);
  body+=(view.items||[]).map(i=>'<details open><summary>'+esc(i.kind)+'</summary>'+json(i)+'</details>').join('');
 }
 return '<section class="role-news-view" aria-label="Role-specific news intelligence">'+card(view.role.toUpperCase()+' NEWS INTELLIGENCE',body)+'</section>';
}
function renderNewsPanels(){
 if(!originalNewsPanels)originalNewsPanels={signals:q('signals').innerHTML,stress:q('stress').innerHTML};
 const news=data.news||{},surfaces=news.surfaces||{},items=(surfaces.signals||{}).items||[];
 const page=news.pagination||{};
 q('sigcount').textContent=items.length+' / '+(page.total||0)+' EVENTS';
 const cov=news.source_coverage||{};
 const scope=((surfaces.signals||{}).scope)||{};
 q('signals').innerHTML='<p style="color:#79bacc">'+esc(news.mode)+' · '+esc(news.as_of)+'</p>'
  +roleNewsHTML(news.role_view)
  // Relevance is a different question from classification. Without this
  // line, "50% unclassified" read as an extraction failure when it was
  // mostly a whole jurisdiction's daily register arriving on one feed.
  +(scope.in_scope==null?'':'<p class="m">'+esc(scope.in_scope)
    +' in scope · '+esc(scope.out_of_scope)+' received but not about this '
    +'system (carried and linked, never deleted) · '
    +esc(scope.unclassified_in_scope)+' in scope and unidentified</p>')
  +items.map(it=>'<details class="sig" data-event-id="'+esc(it.event_id)+'"><summary>'
    +(it.off_page?'<span class="offpage">REFERENCED</span> ':'')+esc(it.headline)+'</summary>'
    +(it.off_page?'<p class="m">Not on this page of LATEST SIGNALS. It is kept '
      +'here because an inference on screen references it.</p>':'')
    +newsEvidence(it)
    // Both sides of one instrument. A measure that constrains an exporter
    // also protects the producer competing with it; showing one and not the
    // other makes the same document read as good or bad news depending on
    // which target happened to be mapped.
    +(it.opposing
      ? '<p class="m">Constrains: '+esc((it.opposing.constrained_roles||[]).join(', ')||'-')
        +' | Benefits: '+esc((it.opposing.benefiting_roles||[]).join(', ')||'-')
        +(it.opposing.reversed_by_status?' (reversed: the measure has ended)':'')
        +'<br>'+esc(it.opposing.net_effect)+'</p>'
      : '')
    // An exclusion that cannot state its reason cannot be argued with.
    +(it.relevance&&!it.relevance.in_scope
      ? '<p class="m">Not in scope: '+esc((it.relevance.reasons||[])[0]||'')+'</p>'
      : '')
    +(it.relevance&&it.relevance.in_scope
      ? '<p class="m">In scope: '+esc((it.relevance.reasons||[]).join('; '))+'</p>'
      : '')
    +'<div class="m">First seen '+esc(it.first_seen_at)
    // A document on public inspection is fully knowable now; only its
    // publication date is still ahead. Saying so keeps a future date from
    // reading as a stale one.
    +(it.publication_scheduled
      ? ' · scheduled for publication '+esc(it.published_at)+', not yet published'
      : '')
    +'</div></details>').join('')
  +'<p>'+esc((cov.uncovered||[]).join('; ')||'Registered sources currently covered')+'</p>'
  +'<p>'+esc((cov.coverage_gaps||[]).join('; '))+'</p>'
  +'<details><summary>FABRICATED illustrative signals</summary>'+originalNewsPanels.signals+'</details>';
 const rows=(((surfaces.sector_stress||{}).news||{}).rows)||[];
 const covered=page.aggregates_cover||page.total||0;
 q('stress').innerHTML='<p>NEWS \u00b7 inferred mechanisms</p>'
  +'<p class="m">over all '+esc(covered)+' eligible events, not just the page shown</p>'
  // The sector panel is where a reader forms a view. An inference drawn
  // from stale inputs must carry that on the same surface.
  +(stalenessNote()?'<p class="m" style="color:#ffb3ae">'+esc(stalenessNote())+'</p>':'')
  +rows.map(sectorRow).join('')
  +(rows.length?'':'<p>No documented sector exposure is reachable from the '
    +'events eligible at this decision time. That is missing exposure '
    +'mapping, not an absence of risk.</p>')
  +'<details><summary>FABRICATED sector preview</summary>'+originalNewsPanels.stress+'</details>';
 q('stress').querySelectorAll('.srow[data-event-ids]').forEach(row=>{
  row.onclick=()=>revealEvents((row.dataset.eventIds||'').split(' ').filter(Boolean));});
 q('signals').querySelectorAll('.role-news-evidence').forEach(button=>{
  button.onclick=()=>revealEvents((button.dataset.events||'').split(' ').filter(Boolean));});
 bindRoleActions(q('signals'));
}

/* The role ACTIONS. Each sends one request through the ordinary lifecycle,
   so a failure shows in the same status line as every other operation and
   the result lands in `data.result` where the panel can read it. */
function bindRoleActions(root){
 if(!root)return;
 const go=root.querySelector('#news-compare-go');
 if(go)go.onclick=()=>{
  const pairs=window.SERAPH_COMPARE_PAIRS||[];
  const chosen=pairs[Number((root.querySelector('#news-compare-pair')||{}).value||0)];
  if(!chosen){setStatus('failed','no instrument pair selected');return;}
  shownAnalysis.compare=[chosen.earlier,chosen.later];
  shownAnalysis.event_ids=[chosen.earlier,chosen.later];
  request('news_export',{compare:shownAnalysis.compare,
   event_ids:shownAnalysis.event_ids});};

 const run=root.querySelector('#news-scenario-go');
 if(run)run.onclick=()=>{
  const value=id=>{const n=root.querySelector(id);return n&&n.value!==''?n.value:null;};
  const inputs={event_id:(root.querySelector('#news-scenario-event')||{}).value,
   cost_base:value('#news-scenario-base'),
   pass_through_low:value('#news-scenario-low'),
   pass_through_high:value('#news-scenario-high')};
  shownAnalysis.scenario_inputs=inputs;
  shownAnalysis.event_ids=[inputs.event_id];
  request('news_scenario',inputs);};

 const out=root.querySelector('#news-export-go');
 if(out)out.onclick=()=>request('news_export',{analysis_id:shownAnalysis.analysis_id});

 root.querySelectorAll('.news-review-go').forEach(button=>{
  button.onclick=()=>{
   const card=button.closest('.news-review');
   if(!card)return;
   const earlier=(card.querySelector('.news-review-earlier')||{}).value||'';
   const reason=(card.querySelector('.news-review-reason')||{}).value||'';
   if(!earlier.trim()){setStatus('failed','name the earlier instrument this '
    +'document supersedes; it is not guessed from a similar title');return;}
   if(!reason.trim()){setStatus('failed','a review needs a reason');return;}
   request('news_review',{later:card.dataset.later,earlier:earlier.trim(),
    decision:button.dataset.decision,reason:reason.trim()});};});
}

/* Plain words for what the row actually claims. "ambiguous" alone reads as a
   failure; it is a finding — opposing mechanisms, or a target role the
   evidence does not establish. */
const DIRECTION_TEXT={favourable:'favourable for this sector',
 adverse:'adverse for this sector',ambiguous:'direction unknown \u2014 opposing or unestablished mechanisms',
 mixed:'mixed across targets',neutral:'no directional effect established',
 unknown:'direction unknown'};
function sectorRow(r){
 const dirs=(r.direction||[]).map(d=>DIRECTION_TEXT[d]||d);
 const sized=r.exposure_magnitude==null
  ?'size unknown'+((r.unsized_relationships||0)?' \u00b7 '+esc(r.unsized_relationships)+' unsized relationship(s)':'')
  :esc(r.exposure_magnitude)+' '+esc(r.exposure_unit);
 return '<div class="srow" data-event-ids="'+esc((r.event_ids||[]).join(' '))+'"'
  +' title="Show the events behind this inference">'
  +'<b>'+esc(r.sector)+'</b>'
  +'<p>'+esc((r.mechanisms||[]).join(', ')||'mechanism unrecorded')+'</p>'
  +'<small>'+esc(dirs.join('; '))+'</small>'
  +'<small>severity '+esc(r.severity)+' \u00b7 evidence '+esc(r.evidence_confidence)
  +' \u00b7 '+sized+'</small>'
  +'<small>'+esc(r.events)+' event(s) \u2014 click for the documents</small></div>';
}

/* Clickable evidence: open the rail entries this inference came from. An
   event that is not on the displayed page says so rather than silently
   opening nothing. */
function revealEvents(ids){
 if(!ids.length)return;
 show('map');
 let found=0;
 ids.forEach(id=>{const n=q('signals').querySelector('details.sig[data-event-id="'+id+'"]');
  if(n){n.open=true;if(!found)n.scrollIntoView({block:'center'});found++;}});
 setStatus(found?'succeeded':'discarded',found
  ?found+' of '+ids.length+' source event(s) opened in LATEST SIGNALS'
  :'the event behind this inference is not on the displayed page \u2014 page '
   +'through LATEST SIGNALS to reach its documents');
}
function newsEvidence(it){
 const links=(it.evidence_links||[]).filter(r=>/^https?:\/\//i.test(r.url||''));
 const f=it.interpretation||{};
 /* What the record actually holds for this item, rather than a sentence
    asserting that bodies are never retained. `text_scope` is written at
    acquisition and says whether this is a title, a feed summary or a
    retrieved document. */
 const scope=r=>r.text_scope?' · '+esc(String(r.text_scope).replace(/_/g,' ')):'';
 const rights=r=>r.display_permitted===false?' · quotation withheld by licence':'';
 return '<p>'+esc([f.assertion_status,f.action,f.policy_status].filter(Boolean).join(' · '))+'</p>'
  +links.map(r=>'<p>'+esc(r.source_note||'')+'</p><a target="_blank" rel="noopener noreferrer" href="'+esc(r.url)+'">'+esc(r.source_id)+' · evidence</a>'+scope(r)+rights(r)).join(' · ')
  +'<p>'+esc((it.impacts||[]).map(i=>i.target_id+': '+i.direction+' via '+i.mechanism).join('; ')||'No supported target impact')+'</p>';
}
/* The display timer RE-PROJECTS stored data. It must never acquire: this
   fired `news_refresh` every 30s, which forced all eleven sources, in the
   web process, once per open browser tab. Acquisition is asked for
   explicitly by `news_acquire` and served by the worker. */
if(typeof window.setInterval==='function') window.setInterval(()=>{
 if(!inflight&&data&&data.news&&data.news.mode==='current_news')
  request('news_project',{});
},30000);

/* Asking for acquisition. Returns immediately -- the request is queued and
   the worker serves it -- so the page acknowledges rather than blocking. */
function requestAcquisition(){
 if(inflight)return;
 request('news_acquire',{});
}
window.SERAPH_REQUEST_ACQUISITION=requestAcquisition;

function show(view){active=view;if(!data)return;
 const home=ROLE_HOME[data.role]||'console';
 document.querySelector('main').style.display=view==='map'?'':'none';document.querySelectorAll('.vw').forEach(n=>n.classList.remove('show'));
 document.querySelectorAll('nav a').forEach(n=>n.classList.toggle('on',n.dataset.view===view));
 /* Name the route so the user can see which role workspace is open. */
 let crumb=q('route-crumb');
 if(!crumb){crumb=document.createElement('div');crumb.id='route-crumb';
  crumb.style.cssText='padding:5px 14px;font:11px var(--mono,monospace);'
   +'background:#191a1f;color:#8d8a84;border-bottom:1px solid #26272e';
  const banner=q('preview-banner');
  if(banner&&banner.parentNode)banner.parentNode.insertBefore(crumb,banner);
  else if(document.body&&document.body.appendChild)document.body.appendChild(crumb);}
 crumb.textContent=(view===home?(ROLE_LABEL[data.role]||'HOME')+' · ':'')
  +view.toUpperCase()+(view===home?'  (landing route for this role)':'');
 if(view==='console'){q('viewConsole').classList.add('show');renderConsole();}else if(view==='pillars'){q('viewPillars').classList.add('show');renderPillars();}else if(view==='method'){q('viewMethod').classList.add('show');renderMethod();}else if(view!=='map'){
 q('viewExtra').classList.add('show');q('extra-title').textContent=view.toUpperCase();let html='';
 if(view==='feed'){const items=((data.news||{}).surfaces||{}).signals;
  html=card('SERAPH alert · persisted',esc(data.view.explanation))
   +((items&&items.status==='observed'&&items.items&&items.items.length)
     ?card('News feed · received sources',items.items.map(it=>
       kv(esc(it.event_type||'event'),esc(it.headline))
       +'<div class="ckv"><span>first seen</span><b>'+esc(it.first_seen_at)
       +'</b></div>'+newsEvidence(it)).join(''))
     :card('News feed · separate subsystem',tag+q('signals').innerHTML));}
 if(view==='exposure')html=card('Current supplied portfolio',data.portfolio?json(data.portfolio):'No holdings supplied. Use TOOLS to calculate coverage.')+card('Original design preview',tag+q('exposure').innerHTML);
 if(view==='forecasts')html=data.role==='retail'?'Detailed model forecasts are available in the institutional and regulator views. See CONSOLE for the simplified warning.':table(data.predictions);
 if(view==='backtest')html='<p>Retrospective saved-run comparison; not a new fit or evidence of general predictive edge.</p>'+(data.report?table(data.report.retrospective_comparison):'Comparison details not available to this role.')+spark(data.history);
 if(view==='tools')html=tools();q('extra-content').innerHTML=html;if(view==='tools')bindTools();}
 let rolePanel=q('role-news-home');
 if(!rolePanel){rolePanel=document.createElement('div');rolePanel.id='role-news-home';document.body.appendChild(rolePanel);}
 rolePanel.style.display=view===home?'':'none';
 if(view===home){const host=q(home==='console'?'viewConsole':home==='pillars'?'viewPillars':'viewExtra');if(host)host.appendChild(rolePanel);}
 rolePanel.innerHTML=view===home?roleNewsHTML((data.news||{}).role_view):'';
 bindRoleActions(rolePanel);
 rolePanel.querySelectorAll('.role-news-evidence').forEach(button=>{
  button.onclick=()=>revealEvents((button.dataset.events||'').split(' ').filter(Boolean));});
 window.dispatchEvent(new Event('resize'));send('streamlit:setFrameHeight',{height:1050});}
 document.querySelectorAll('nav a').forEach(a=>a.onclick=e=>{e.preventDefault();show(a.dataset.view);});
 document.querySelector('.cta').textContent='VIEW BACKTEST';document.querySelector('.cta').onclick=()=>show('backtest');
 /* T03: a same-role click never waits for role inequality. It acknowledges
    at once and navigates to that role's landing route. */
 document.querySelectorAll('#roles button').forEach(b=>b.onclick=()=>{
  const wanted=b.dataset.role;
  if(data&&data.role===wanted){
   setStatus('succeeded','already '+wanted+'; opened '+(ROLE_LABEL[wanted]||wanted));
   show(ROLE_HOME[wanted]||'console');return;}
  request('role',{role:wanted});});
 window.addEventListener('message',e=>{if(e.source!==parent||e.data.type!=='streamlit:render')return;
 const previous=data;data=e.data.args.payload;
 const analysisScope=p=>JSON.stringify(p&&[p.run_id,p.date,p.role,p.portfolio_context,(p.news||{}).mode]);
 if(analysisScope(previous)!==analysisScope(data)){
  shownAnalysis={analysis_id:null};
  if(exportURL){URL.revokeObjectURL(exportURL);exportURL=null;}
 }
 if(data.result&&!data.result.error&&data.result.analysis_id)
  shownAnalysis.analysis_id=data.result.analysis_id;
 /* Resolve the in-flight request against what actually came back. A response
    for a context the user has since left is reported, not rendered — Python
    has already withheld it in `discarded_result`. */
 const ctx=data.context||{run_id:data.run_id,date:data.date,role:data.role};
 const answered=inflight&&data.result&&data.result.context
   &&data.result.context.request_id===inflight.id;
 const contextMoved=inflight&&(inflight.context.run_id!==ctx.run_id
   ||inflight.context.date!==ctx.date||inflight.context.role!==ctx.role);
 if(inflight&&(inflight.op==='news_project'||inflight.op==='news_refresh'||inflight.op==='news_acquire')&&data.news&&data.news.as_of!==(previous&&previous.news&&previous.news.as_of)){clearInflight();setStatus('idle');}
 /* The ERROR check comes first. A refused operation comes back with an
    `error` and no `kind`, and it carries the same `context.request_id` as
    a successful one -- so testing `answered` first reported a refusal as
    "DONE" with an empty detail, which is the most misleading status a
    request bar can show. */
 else if(inflight&&data.result&&data.result.error&&data.result.context
   &&data.result.context.request_id===inflight.id){
  clearInflight();setStatus('failed',data.result.error);}
 else if(answered){clearInflight();setStatus('succeeded',data.result.kind);}
 /* A change of role, date or run must not hand back the previous context's
    export, so the link is rebuilt only from the result that just arrived. */
 else if(inflight&&data.result&&data.result.error){clearInflight();setStatus('failed',data.result.error);}
 else if(inflight&&inflight.op==='role'&&data.role!==(previous&&previous.role)){
  clearInflight();setStatus('succeeded','role · '+(ROLE_LABEL[data.role]||data.role));
  active=ROLE_HOME[data.role]||'console';}
 else if(contextMoved){clearInflight();setStatus('discarded','the run, date or role changed while the request was in flight; its result is not shown here');}
 else if(inflight){setStatus('pending',inflight.op);}
 else if(data.discarded_result){setStatus('discarded',data.discarded_result.reason);}
 /* F01. These used to run bare, so ONE throwing chart aborted the whole
    handler -- the role toggles, the liveness banner, `applyNewsLayer()` and
    `show()` all sit below this line, and a history-shape error took every one
    of them with it. Each renderer now reports its own failure visibly and the
    rest of the update proceeds. This is a boundary around the known failure,
    not a redesign. */
 [['console',renderConsole,'c_trends'],['pillars',renderPillars,'viewPillars'],
  ['method',renderMethod,'m_limits']].forEach(([name,fn,slot])=>{
  try{fn();}catch(err){
   try{q(slot).innerHTML='<p class="warn">The '+name+' view failed to render: '
    +esc(String(err&&err.message||err))
    +'. Other panels and the news layer are unaffected.</p>';}catch(e){}
   try{console.error('seraph: '+name+' render failed',err);}catch(e){}}});
 q('extra-content').innerHTML='';
 document.querySelectorAll('#roles button').forEach(b=>b.classList.toggle('on',b.dataset.role===data.role));
 /* The liveness banner. CSRS is specified as a CURRENT market risk score, and
    every score this system can produce today comes from an archive. That has
    to be on screen, not in a caption. */
 const live=data.liveness;
 if(live){const n=q('preview-banner');
  n.style.background=live.publishable_as_current?'#12301c':'#3a1518';
  n.style.color=live.publishable_as_current?'#9ad8ae':'#ffb3ae';
  n.innerHTML='<b>'+esc(live.headline)+'</b> — '+esc(live.note)
   +' | observed '+esc(live.observed_at)+' · now '+esc(live.now)
   +' · market '+esc(live.market_state)+' · feed: '+esc(live.feed)
   +'<br>RUN '+esc(data.run_id.slice(0,16))+' · '+esc(data.date)+' · '
   +esc(data.role.toUpperCase())
   +' | '+newsStatusLine()+' | NEWS '+((data.news||{}).mode||'historical')+' '+((data.news||{}).as_of||'unknown')+' | MARKET '+data.timestamp;}
 else q('preview-banner').textContent='RUN '+data.run_id.slice(0,16)+' · '+data.date+' · '+data.role.toUpperCase()+' | '+newsStatusLine()+' | NEWS '+((data.news||{}).mode||'historical')+' '+((data.news||{}).as_of||'unknown')+' | MARKET '+data.timestamp;
 // Published for the detail card in index.html, which has its own single
 // writer and must not reach into `data` itself.
 try{window.SERAPH_NEWS_FRESHNESS=(data.news&&data.news.freshness)||null;}catch(e){}
 applyNewsLayer();
 if(data.news&&data.news.status!=='absent')renderNewsPanels();
 show(active);
 try{offerExportDownload(data.result);}catch(e){}});
 send('streamlit:componentReady',{apiVersion:1});send('streamlit:setFrameHeight',{height:1050});
 /* Test seam. Inert in the browser: the harness must pre-declare the hook,
    so nothing is exposed unless a test asked for it. Used by
    tests/js/bridge_harness.mjs to drive the real request lifecycle rather
    than grep the source for the word "retry". */
 if(typeof globalThis!=='undefined'&&globalThis.__SERAPH_BRIDGE_TEST__===null){
  globalThis.__SERAPH_BRIDGE_TEST__={request,retry,show,captureDrafts,restoreDrafts,
   status:()=>lastStatus,inflight:()=>inflight,drafts:()=>drafts,
   active:()=>active,roleHome:ROLE_HOME,
   clickRole:r=>{const b=document.querySelector('#roles button[data-role="'+r+'"]');
    if(b&&b.onclick)b.onclick();},
   cancelInflight:()=>{clearInflight();setStatus('idle');},
   newsStatusLine,applyNewsLayer,roleNewsHTML};}
})();
