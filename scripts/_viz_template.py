"""HTML/CSS/JS template constants for generate_html_viz.py."""

CSS = r"""
:root{--bg:#f0f2f5;--surface:#fff;--text:#1a1a2e;--muted:#6b7280;--border:#e5e7eb;
--sh:0 1px 3px rgba(0,0,0,.08);--sh-lg:0 4px 14px rgba(0,0,0,.10);--r:10px;--rs:6px;
--da:#f59e0b;--dabg:#fffbeb;--fa:#3b82f6;--fabg:#eff6ff;
--mc-d:rgba(40,80,160,.30);--mc-c:rgba(0,130,100,.30);--mc-s:rgba(180,100,20,.30);--mc-m:rgba(120,50,140,.30);
--ms-d:rgb(40,80,160);--ms-c:rgb(0,130,100);--ms-s:rgb(180,100,20);--ms-m:rgb(120,50,140)}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',-apple-system,sans-serif;font-size:14px;line-height:1.6;color:var(--text);background:var(--bg)}
.app-header{padding:28px 32px 22px;text-align:center;color:#000}
.app-header h1{font-size:22px;font-weight:700;letter-spacing:-.5px}
.main-content{max-width:1200px;margin:0 auto;padding:0 24px 40px}
.top-controls{display:flex;gap:10px;margin:20px 0 16px;flex-wrap:wrap}
.btn{padding:8px 16px;border:1px solid var(--border);background:var(--surface);cursor:pointer;border-radius:var(--rs);font-size:13px;font-weight:500;transition:.2s;font-family:inherit;color:var(--text)}
.btn:hover{background:#f3f4f6;box-shadow:var(--sh)}
.btn.active{background:#dbeafe;border-color:#93c5fd;color:#1d4ed8}
.panel{background:var(--surface);border-radius:var(--r);border:1px solid var(--border);box-shadow:var(--sh);margin-bottom:14px;overflow:hidden;transition:box-shadow .3s}
.panel:hover{box-shadow:var(--sh-lg)}
.panel-header{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;cursor:pointer;user-select:none;font-weight:600;font-size:14px;transition:background .15s}
.panel-header:hover{background:rgba(0,0,0,.02)}
.panel-chevron{transition:transform .25s ease;font-size:12px;color:var(--muted)}
.panel.open .panel-chevron{transform:rotate(180deg)}
.panel-body{max-height:0;overflow:hidden;transition:max-height .35s ease,padding .35s ease;padding:0 20px}
.panel.open .panel-body{max-height:2000px;padding:0 20px 18px}
.display-panel{border-left:4px solid var(--da)}
.display-panel .panel-header .panel-title{color:#b45309}
.filter-panel{border-left:4px solid var(--fa)}
.filter-panel .panel-header .panel-title{color:#1d4ed8}
.ctrl-group{margin-bottom:14px}
.ctrl-group:last-child{margin-bottom:0}
.ctrl-group-title{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:8px;display:flex;align-items:center;gap:6px}
.ctrl-group-title::after{content:'';flex:1;height:1px;background:var(--border)}
.ctrl-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.ctrl-row label{font-size:13px;cursor:pointer;display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;transition:.15s;user-select:none;border:1px solid transparent}
.ctrl-row label:hover{background:#f3f4f6;border-color:var(--border)}
.ctrl-row label.mode-label{font-weight:600}
.ctrl-row input[type=checkbox]{accent-color:var(--fa);width:15px;height:15px;cursor:pointer}
.display-panel .ctrl-row input[type=checkbox]{accent-color:var(--da)}
.search-row{display:flex;justify-content:space-between;align-items:center;margin-top:10px;padding-top:12px;border-top:1px solid var(--border)}
#search-box{font-size:13px;padding:8px 14px;width:380px;max-width:100%;border:1px solid var(--border);border-radius:var(--rs);font-family:inherit;transition:border .2s,box-shadow .2s;background:#fafafa}
#search-box:focus{outline:none;border-color:var(--fa);box-shadow:0 0 0 3px rgba(59,130,246,.15);background:#fff}
.counter{font-size:13px;color:var(--muted);font-weight:500}
.counter span{font-weight:700;color:var(--text)}
.qual-filter-group{margin-top:6px}
.qual-filter-group summary{font-size:13px;font-weight:500;cursor:pointer;padding:5px 10px;border-radius:var(--rs);transition:.15s;list-style:none;display:flex;align-items:center;gap:6px;color:var(--text)}
.qual-filter-group summary:hover{background:#f3f4f6}
.qual-filter-group summary::before{content:'▸';font-size:11px;transition:transform .2s}
.qual-filter-group[open] summary::before{transform:rotate(90deg)}
.qual-filter-group .qual-opts{padding:6px 0 4px 20px;display:flex;flex-wrap:wrap;gap:4px 10px}
.qual-filter-group .qual-opts label{font-size:12px;padding:3px 8px}
.legend{display:flex;gap:14px;margin:16px 0 8px;font-size:13px;align-items:center;flex-wrap:wrap}
.legend-item{display:inline-flex;align-items:center;gap:6px;font-weight:500}
.legend-swatch{display:inline-block;width:16px;height:16px;border-radius:4px}
.corpus-section{margin-top:8px}
.doc-container{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);margin-bottom:10px;padding:14px 18px;box-shadow:var(--sh);transition:box-shadow .2s,border-color .2s}
.doc-container:hover{box-shadow:var(--sh-lg);border-color:#d1d5db}
.doc-header{margin-bottom:8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.doc-corpus-badge{display:none;background:#e5e7eb;color:#374151;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.3px}
body.show-corpus .doc-corpus-badge{display:inline-block}
.doc-meta{background:#eef2ff;border:1px solid #c7d2fe;padding:3px 10px;border-radius:20px;color:#3730a3;font-size:11px;font-weight:600}
.badge{display:none;padding:2px 9px;border-radius:20px;font-size:10px;font-weight:600;letter-spacing:.3px;text-transform:uppercase}
.badge-ironie{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}
.badge-insulte{background:#fff7ed;color:#ea580c;border:1px solid #fed7aa}
.badge-mepris{background:#faf5ff;color:#9333ea;border:1px solid #e9d5ff}
.badge-argot{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0}
.badge-abreviation{background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe}
.badge-qual{display:none;padding:2px 9px;border-radius:20px;font-size:10px;font-weight:600}
.badge-role{background:#dbeafe;color:#1e40af;border:1px solid #93c5fd}
.badge-hate{background:#fef2f2;color:#991b1b;border:1px solid #fca5a5}
.badge-sentiment{background:#fefce8;color:#a16207;border:1px solid #fde68a}
.badge-target{background:#f5f3ff;color:#6d28d9;border:1px solid #c4b5fd}
.badge-verbalabuse{background:#fff7ed;color:#c2410c;border:1px solid #fdba74}
.badge-intention{background:#ecfdf5;color:#047857;border:1px solid #6ee7b7}
.badge-context{background:#f1f5f9;color:#334155;border:1px solid #94a3b8}
body.show-badge-ironie .badge-ironie,body.show-badge-insulte .badge-insulte,
body.show-badge-mepris .badge-mepris,body.show-badge-argot .badge-argot,
body.show-badge-abreviation .badge-abreviation{display:inline-block}
body.show-badge-role .badge-role,body.show-badge-hate .badge-hate,
body.show-badge-sentiment .badge-sentiment,body.show-badge-target .badge-target,
body.show-badge-verbalabuse .badge-verbalabuse,body.show-badge-intention .badge-intention,
body.show-badge-context .badge-context{display:inline-block}
.doc-text{white-space:pre-wrap;color:#111;line-height:1.7;font-size:14px}
.hl{border-radius:3px;padding:2px 0}
.elong{color:#c0392b;text-decoration:underline wavy;text-decoration-color:#c0392b;text-underline-offset:3px}
body:not(.show-elongations) .elong{color:inherit;text-decoration:none}
.doc-container.no-emo{opacity:.7;border-left:3px solid #e5e7eb}
@media(max-width:768px){.main-content{padding:0 12px 24px}.app-header{padding:20px 16px}#search-box{width:100%}
.ctrl-row{gap:6px}.ctrl-row label{padding:3px 6px;font-size:12px}}
"""

JAVASCRIPT = r"""
const MODE_COLORS={
'Désignée':'rgba(40,80,160,.30)','Comportementale':'rgba(0,130,100,.30)',
'Suggérée':'rgba(180,100,20,.30)','Montrée':'rgba(120,50,140,.30)'};
const MODE_COLORS_SOLID={
'Désignée':'rgb(40,80,160)','Comportementale':'rgb(0,130,100)',
'Suggérée':'rgb(180,100,20)','Montrée':'rgb(120,50,140)'};

document.querySelectorAll('.panel-header').forEach(h=>{
  h.addEventListener('click',()=>h.parentElement.classList.toggle('open'));
});
// Corpus names toggle via Affichage checkbox
const dcn=document.getElementById('display-corpus-names');
if(dcn)dcn.addEventListener('change',function(){
  document.body.classList.toggle('show-corpus',this.checked);
});

function applyDisplay(){
  const activeModes=new Set();
  document.querySelectorAll('.display-mode').forEach(cb=>{if(cb.checked)activeModes.add(cb.value);});
  document.querySelectorAll('.hl').forEach(span=>{
    const modes=(span.dataset.modes||'').split(',').filter(Boolean);
    const vis=modes.filter(m=>activeModes.has(m));
    if(vis.length===0){span.style.background='';span.style.borderBottom='';}
    else{span.style.background=MODE_COLORS[vis[0]];
      span.style.borderBottom=vis.length>1?'2px solid '+MODE_COLORS_SOLID[vis[1]]:'';}
  });
  document.querySelectorAll('.display-binary').forEach(cb=>{
    document.body.classList.toggle('show-badge-'+cb.dataset.feature,cb.checked);});
  document.querySelectorAll('.display-qual').forEach(cb=>{
    document.body.classList.toggle('show-badge-'+cb.dataset.feature,cb.checked);});
  const ec=document.getElementById('display-elongations');
  if(ec)document.body.classList.toggle('show-elongations',ec.checked);
}

function applyFilters(){
  const ac=[...document.querySelectorAll('.filter-corpus:checked')].map(c=>c.value);
  const showEmo=document.getElementById('filter-with-emo').checked;
  const showNoEmo=document.getElementById('filter-without-emo').checked;
  const showElong=document.getElementById('filter-with-elong').checked;
  // Mode d'expression filter
  const filterModes=[...document.querySelectorAll('.filter-mode:checked')].map(c=>c.value);
  const ab=[...document.querySelectorAll('.filter-binary:checked')].map(c=>c.dataset.feature);
  const qf={};
  document.querySelectorAll('.filter-qual').forEach(cb=>{
    if(cb.checked){const f=cb.dataset.feature;if(!qf[f])qf[f]=[];qf[f].push(cb.value);}});
  const search=(document.getElementById('search-box').value||'').toLowerCase();
  let shown=0;
  document.querySelectorAll('.doc-container').forEach(doc=>{
    let v=true;
    if(ac.length>0&&!ac.includes(doc.dataset.corpus))v=false;
    if(v){const he=doc.dataset.hasEmo==='1';
      if(!showEmo&&he)v=false;if(!showNoEmo&&!he)v=false;}
    if(v&&showElong&&doc.dataset.hasElongation!=='1')v=false;
    // Mode d'expression: if any filter-mode checked, require at least one matching mode
    if(v&&filterModes.length>0){
      const docModes=(doc.dataset.modes||'').split(',').filter(Boolean);
      if(!filterModes.some(m=>docModes.includes(m)))v=false;
    }
    if(v){for(const f of ab){
      if(f==='elongation'){if(doc.dataset.hasElongation!=='1'){v=false;break;}}
      else{if(doc.dataset[f]!=='1'){v=false;break;}}
    }}
    if(v){for(const[feat,vals]of Object.entries(qf)){
      const dv=doc.dataset[feat]||'';
      const dvs=dv.split('/').map(s=>s.trim());
      if(!vals.some(x=>dvs.includes(x))){v=false;break;}}}
    if(v&&search&&!doc.textContent.toLowerCase().includes(search))v=false;
    doc.style.display=v?'':'none';if(v)shown++;
  });
  document.querySelectorAll('.corpus-section').forEach(s=>{
    s.style.display=s.querySelectorAll('.doc-container:not([style*="display: none"])').length>0?'':'none';});
  document.getElementById('shown-count').textContent=shown;
}

document.querySelectorAll('.display-mode,.display-binary,.display-qual,#display-elongations')
  .forEach(cb=>cb.addEventListener('change',applyDisplay));
document.querySelectorAll('.filter-corpus,.filter-binary,.filter-qual,.filter-mode,#filter-with-emo,#filter-without-emo,#filter-with-elong')
  .forEach(cb=>cb.addEventListener('change',applyFilters));
const sb=document.getElementById('search-box');if(sb)sb.addEventListener('input',applyFilters);
applyDisplay();applyFilters();
"""
