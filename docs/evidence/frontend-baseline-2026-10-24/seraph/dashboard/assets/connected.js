/* C12 presentation only: no generated market values or model calculations. */
const run = JSON.parse(document.getElementById('seraph-run').textContent);
const p=run.point, c=p.composite, names=['hawkes','rmt','hamilton'];
const el=id=>document.getElementById(id);
const esc=x=>String(x??'Unavailable').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=x=>typeof x==='number'&&Number.isFinite(x)?x.toFixed(4):'Unavailable';
const row=(k,v)=>'<div class="row"><div class="label">'+esc(k)+'</div>'+esc(v)+'</div>';
const json=x=>'<pre>'+esc(JSON.stringify(x,null,2))+'</pre>';
el('decision').textContent=p.evaluation_timestamp;
el('ticker').textContent='HISTORICAL REPLAY · '+p.date+' · '+run.manifest.mode+' · EXPERIMENTAL';
el('status').textContent='RUN '+p.run_id+' · Decision cutoff '+p.data_cutoff;
el('score').innerHTML=c?'<div class="value">'+num(c.csrs)+'</div>'+row('Warning',c.alert_level.toUpperCase())+row('Conditional interval',num(c.ci_lower)+' to '+num(c.ci_upper)):'No composite: original inputs unavailable.';
el('signals').textContent=p.explanation?.sentence||'No explanation available.';
el('coverage').innerHTML=row('Input coverage',p.coverage.degraded?'DEGRADED':'AVAILABLE')+row('Sector / regional stress','Unavailable — no geographic risk measurement')+row('Warning status',p.warning_status);
el('pillars').innerHTML=names.map((name,i)=>{const d=p.original_pillars[name]||{};return row(name.toUpperCase(),num(d.value))+row('Fusion status',c?.mask[i]?'Included':'Excluded / unavailable')+row('Source timestamp',d.information_timestamp);}).join('');
el('pillar-details').innerHTML=names.map((name,i)=>'<h3>'+esc(name.toUpperCase())+'</h3>'+row('Contribution',c?num(c.shapley[i]):'Unavailable')+json(p.original_pillars[name])).join('');
const forecasts=p.astra_predictions||[];
el('forecast-summary').innerHTML=forecasts.filter(x=>x.model==='combined').map(x=>row(x.target,num(x.probability))+row('Model alarm',x.alarm===null?'Unassessable':x.alarm?'Raised':'Not raised')).join('')||'No forecasts available.';
el('forecasts').innerHTML=forecasts.length?'<table><thead><tr>'+['Model','Target','Probability','Threshold','Alarm','Fit status'].map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+forecasts.map(x=>'<tr>'+[x.model,x.target,num(x.probability),num(x.threshold),x.alarm==null?'Unassessable':x.alarm?'Raised':'Not raised',x.fit_status].map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>':'No forecasts available.';
el('exposure').innerHTML=p.portfolio?json(p.portfolio):'No user holdings supplied. Exposure unavailable.';
el('method').innerHTML='<p>Three original pillars retained. Hamilton remains diagnostic-only. CSRS thresholds are provisional; predictive skill remains unvalidated. Globe geometry is a reference map, not measured regional risk. Animated clouds are decorative, not meteorological data.</p>'+json(p.limitations)+json(run.manifest);
const hist=run.history;
// Missing observations break the line; future dates are excluded server-side.
let paths=[],segment=[];
hist.forEach((h,i)=>{if(!h.composite){if(segment.length)paths.push(segment);segment=[];return;}segment.push([10+i/Math.max(1,hist.length-1)*260,70-h.composite.csrs*60]);});if(segment.length)paths.push(segment);
el('history').innerHTML='<svg viewBox="0 0 280 80" width="100%" aria-label="Historical CSRS through selected date">'+paths.map(s=>'<polyline points="'+s.map(x=>x.join(',')).join(' ')+'" fill="none" stroke="#c9a63a" stroke-width="2"/>').join('')+'</svg>'+row('Through',p.date);
document.querySelectorAll('nav a').forEach(a=>a.onclick=(event)=>{event.preventDefault();const map=a.dataset.view==='map';document.querySelectorAll('nav a').forEach(n=>n.classList.toggle('on',n===a));document.querySelectorAll('.map-pane').forEach(n=>n.style.display=map?'':'none');document.querySelectorAll('.connected-view').forEach(n=>n.style.display=n.id==='view-'+a.dataset.view?'block':'none');window.dispatchEvent(new Event('resize'));});
try {
 const stage=el('stage'),scene=new THREE.Scene();scene.background=new THREE.Color(0x020203);
 const camera=new THREE.PerspectiveCamera(38,1,1,6000),renderer=new THREE.WebGLRenderer({antialias:true});
 renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));stage.appendChild(renderer.domElement);
 scene.add(new THREE.AmbientLight(0x555555,1));const sun=new THREE.DirectionalLight(0xf2ece2,.82);sun.position.set(120,240,200);scene.add(sun);
 const globe=SERAPH_GLOBE.build(THREE,DATA,{R:100,stress:{},triggers:[],arcs:[],assets:[],stars:true,clouds:true,cloudSeed:7,colors:{ocean:0x0b0c0e,land:0x2b2b2c,coast:0x585a5d,stateLine:0x6b6459}});scene.add(globe.root);
 let lon=80,lat=20,r=235,paused=false,drag=false,lastX=0,lastY=0;
 const cv=renderer.domElement;cv.style.touchAction='none';cv.style.cursor='grab';
 cv.onpointerdown=e=>{drag=true;lastX=e.clientX;lastY=e.clientY;cv.setPointerCapture(e.pointerId);};
 cv.onpointermove=e=>{if(drag){lon-=(e.clientX-lastX)*.25;lat=Math.max(-80,Math.min(80,lat+(e.clientY-lastY)*.25));lastX=e.clientX;lastY=e.clientY;}};
 cv.onpointerup=cv.onpointercancel=()=>drag=false;
 cv.addEventListener('wheel',e=>{e.preventDefault();r=Math.max(145,Math.min(600,r+e.deltaY*.15));},{passive:false});
 el('india').onclick=()=>{lon=80;lat=20;r=235;el('india').classList.add('on');el('global').classList.remove('on');};el('global').onclick=()=>{lon=48;lat=24;r=335;el('global').classList.add('on');el('india').classList.remove('on');};
 el('pause').onclick=()=>{paused=!paused;el('pause').textContent=paused?'RESUME':'PAUSE';};
 el('clouds').onclick=()=>{if(globe.clouds)globe.clouds.visible=!globe.clouds.visible;};
 function frame(){requestAnimationFrame(frame);if(!stage.clientWidth||!stage.clientHeight)return;renderer.setSize(stage.clientWidth,stage.clientHeight,false);camera.aspect=stage.clientWidth/stage.clientHeight;camera.updateProjectionMatrix();const xyz=SERAPH_GLOBE.toXYZ(lon,lat,r);camera.position.set(...xyz);camera.lookAt(0,0,0);if(!paused&&globe.clouds)globe.clouds.rotation.y+=.00015;SERAPH_GLOBE.applyLimbFade(globe,camera.position);renderer.render(scene,camera);}
 frame();window.SERAPH_CONNECTED={runId:p.run_id,date:p.date,geographicSignals:0,ready:true};
} catch(error){el('fail').style.display='block';el('fail').textContent='3D rendering unavailable: '+error.message+'. Saved risk data remain available.';}
