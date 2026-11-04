"""Die HTML-Seite der Liftpictures Station (siehe station.py).

Bewusst als Python-Text statt als Datei im Paket: so kommt sie mit jedem Build
mit, ohne dass Paketdaten eingerichtet sein muessen. Kein CDN, keine Webfonts:
die Seite muss offline laufen.

Gestaltung wie die Systemzustand-Seite im Dashboard (ruhig, HubSpot-artig),
inklusive Lichtlauf durch den Ablauf-Streifen (AutomatHealth.tsx): Station fuer
Station leuchtet kurz auf, an der ersten roten bleibt er stehen und sie
pulsiert rot. Texte auf Englisch (Kunde Kalahari, USA).
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Liftpictures Station</title>
<style>
:root{
  --ink:#1f2933; --ink-2:#33475b; --ink-3:#5c6f82;
  --line:#dfe3eb; --line-strong:#cbd6e2; --canvas:#f5f7fa; --card:#ffffff; --nav:#2b2b2b;
  --brand:#c2410c;
  --ok:#10b981; --ok-ink:#047857; --ok-bg:#ecfdf5; --ok-ring:#a7f3d0;
  --warn:#f59e0b; --warn-ink:#b45309; --warn-bg:#fffbeb; --warn-ring:#fde68a;
  --bad:#e11d48; --bad-ink:#be123c; --bad-bg:#fff1f2; --bad-ring:#fecdd3;
  --idle:#94a3b8; --idle-ink:#5c6f82; --idle-bg:#f1f5f9; --idle-ring:#e2e8f0;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--canvas)}
body{color:var(--ink);font:14px/1.5 "Segoe UI","Segoe UI Variable Text",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
button{font:inherit;color:inherit;cursor:pointer}
.num{font-variant-numeric:tabular-nums}
[hidden]{display:none!important}

/* Kopfleiste */
.nav{height:60px;background:var(--nav);color:#fff;display:flex;align-items:center;gap:16px;padding:0 24px;position:sticky;top:0;z-index:5}
.lp-chip{height:44px;padding:4px 12px;background:#fff;border-radius:6px;display:flex;align-items:center}
.lp-chip img{height:36px;width:auto;display:block}
.nav-title{font-size:15px;font-weight:600;letter-spacing:.2px}
.nav-sep{width:1px;height:28px;background:rgba(255,255,255,.18)}
.park-logo{height:30px;width:auto;max-width:220px;object-fit:contain;display:block}
.nav-right{margin-left:auto;display:flex;align-items:center;gap:18px;text-align:right}
.nav-clock{font-size:15px;font-weight:600}
.nav-date{font-size:12px;color:rgba(255,255,255,.65);margin-top:-2px}
.btn-nav{display:inline-flex;align-items:center;gap:8px;height:34px;padding:0 14px;border-radius:4px;border:1px solid rgba(255,255,255,.28);background:transparent;color:#fff;font-size:13px;font-weight:600}
.btn-nav:hover{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.45)}
.btn-nav svg{width:15px;height:15px}

/* Seite */
.page{max-width:1640px;margin:0 auto;padding:16px 32px 20px}
.crumb{font-size:12px;color:var(--ink-3)}
.head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin:2px 0 14px}
h1{font-size:26px;font-weight:600;color:var(--ink);letter-spacing:-.2px}
.sub{color:var(--ink-3);margin-top:2px}
.head-right{display:flex;align-items:center;gap:14px}
.updated{font-size:12.5px;color:var(--ink-3)}
.pill{display:inline-flex;align-items:center;gap:7px;height:28px;padding:0 12px;border-radius:999px;font-size:13px;font-weight:600;background:var(--bg);color:var(--fg);box-shadow:inset 0 0 0 1px var(--ring)}
.pill i{width:7px;height:7px;border-radius:50%;background:var(--dot)}
.t-ok{--bg:var(--ok-bg);--fg:var(--ok-ink);--ring:var(--ok-ring);--dot:var(--ok)}
.t-warn{--bg:var(--warn-bg);--fg:var(--warn-ink);--ring:var(--warn-ring);--dot:var(--warn)}
.t-bad{--bg:var(--bad-bg);--fg:var(--bad-ink);--ring:var(--bad-ring);--dot:var(--bad)}
.t-idle{--bg:var(--idle-bg);--fg:var(--idle-ink);--ring:var(--idle-ring);--dot:var(--idle)}

.card{background:var(--card);border:1px solid var(--line);border-radius:8px}
.card-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:13px 20px;border-bottom:1px solid var(--line)}
.card-head h2{font-size:16px;font-weight:600;color:var(--ink)}
.card-head p,.card-head span{font-size:13px;color:var(--ink-3)}

/* Hinweis bei Stoerungen */
.alert{display:flex;gap:14px;padding:14px 20px;border-radius:8px;border:1px solid var(--ring);border-left:4px solid var(--dot);background:var(--bg);margin-bottom:16px}
.alert>svg{width:22px;height:22px;flex:none;color:var(--fg);margin-top:1px}
.alert h3{font-size:15px;font-weight:600;color:var(--ink)}
.alert .lead{color:var(--ink-2);margin-top:2px}
.alert .items{display:flex;flex-wrap:wrap;gap:12px 40px;margin-top:10px}
.alert .item b{display:block;font-size:13px;color:var(--ink);margin-bottom:2px}
.alert ol{padding-left:18px;color:var(--ink-2);font-size:13.5px}
.alert li{margin:1px 0}

/* Ablauf-Streifen mit Lichtlauf */
.flow-wrap{background:#f8fafc;padding:18px 24px 14px;border-radius:0 0 8px 8px;overflow-x:auto}
.flow{list-style:none;display:flex;align-items:flex-start;min-width:max-content}
.flow .line{position:relative;margin-top:24px;height:1px;min-width:28px;flex:1;background:var(--line-strong);overflow:hidden}
.flow .line span{position:absolute;left:0;top:-.5px;height:2px;width:100%;transform:translateX(-100%);background:linear-gradient(90deg,transparent,rgba(16,185,129,.9),transparent)}
.flow .line.warn span{background:linear-gradient(90deg,transparent,rgba(245,158,11,.9),transparent)}
.flow .line.run span{animation:lp-flow .6s ease-out forwards}
.st{width:132px;flex:none;display:flex;flex-direction:column;align-items:center;text-align:center;gap:6px}
.st .c{position:relative;width:48px;height:48px;border-radius:50%;border:1px solid var(--line-strong);background:#fff;color:var(--ink-2);display:grid;place-items:center;transition:border-color .5s,box-shadow .5s}
.st .c svg{width:20px;height:20px}
.st .c i{position:absolute;right:-1px;top:-1px;width:13px;height:13px;border-radius:50%;background:var(--dot);box-shadow:0 0 0 2px #fff}
.st .c.glow{transition-delay:.2s;border-color:#34d399;box-shadow:0 0 0 4px rgba(16,185,129,.14),0 0 14px rgba(16,185,129,.55)}
.st .c.glow.warn{border-color:#fbbf24;box-shadow:0 0 0 4px rgba(245,158,11,.14),0 0 14px rgba(245,158,11,.55)}
.st .c.red{border-color:#fb7185;animation:lp-red-glow 1.6s ease-in-out infinite}
.st .n{font-size:13px;font-weight:600;color:var(--ink);line-height:1.25}
.st .s{font-size:12px;color:var(--fg);line-height:1.2}
@keyframes lp-flow{from{transform:translateX(-100%)}to{transform:translateX(100%)}}
@keyframes lp-red-glow{0%,100%{box-shadow:0 0 0 0 rgba(225,29,72,0)}50%{box-shadow:0 0 0 4px rgba(225,29,72,.14),0 0 14px rgba(225,29,72,.5)}}
@media (prefers-reduced-motion:reduce){.flow .line.run span,.st .c.red{animation:none}}

/* Raster */
.grid{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:16px;margin-top:16px;align-items:start}
.side{display:flex;flex-direction:column;gap:16px}

/* Tabelle */
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:11.5px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;color:var(--ink-3);background:#f8fafc;padding:8px 20px;border-bottom:1px solid var(--line)}
td{padding:7px 20px;border-bottom:1px solid var(--line);vertical-align:middle}
tr:last-child td{border-bottom:0}
.comp{display:flex;align-items:center;gap:12px}
.comp .ic{width:30px;height:30px;border-radius:50%;border:1px solid var(--line);display:grid;place-items:center;color:var(--ink-2);flex:none}
.comp .ic svg{width:16px;height:16px}
.comp b{display:block;font-weight:600;color:var(--ink)}
.comp small{display:block;color:var(--ink-3);font-size:12.5px}
.badge{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 10px;border-radius:999px;font-size:12.5px;font-weight:600;background:var(--bg);color:var(--fg);box-shadow:inset 0 0 0 1px var(--ring);white-space:nowrap}
.badge i{width:6px;height:6px;border-radius:50%;background:var(--dot)}
td.det{color:var(--ink-2)}

/* Heute */
.stats{display:grid;grid-template-columns:1fr 1fr}
.stat{padding:11px 20px;border-top:1px solid var(--line)}
.stat:nth-child(-n+2){border-top:0}
.stat:nth-child(odd){border-right:1px solid var(--line)}
.stat .k{font-size:12.5px;color:var(--ink-3)}
.stat .v{font-size:24px;font-weight:300;color:var(--ink);line-height:1.2;margin-top:2px}
.stat .v small{font-size:13px;color:var(--ink-3);font-weight:400}

/* Fragen & Antworten */
.faq details{border-top:1px solid var(--line)}
.faq details:first-child{border-top:0}
.faq summary{list-style:none;display:flex;align-items:center;gap:10px;padding:10px 20px;font-weight:600;color:var(--ink);cursor:pointer}
.faq summary::-webkit-details-marker{display:none}
.faq summary:hover{background:#f8fafc}
.faq summary svg{width:16px;height:16px;color:var(--ink-3);flex:none;transition:transform .2s}
.faq details[open] summary svg{transform:rotate(90deg)}
.faq .a{padding:0 20px 14px 46px;color:var(--ink-2)}
.faq .a ol{padding-left:18px;margin-top:4px}
.faq .a li{margin:2px 0}
.faq .a p+p,.faq .a p+ol,.faq .a ol+p{margin-top:6px}
code{font-family:Consolas,"SF Mono",Menlo,monospace;font-size:12.5px;background:#f1f5f9;border:1px solid var(--line);border-radius:4px;padding:0 5px;color:var(--ink)}
kbd{font-family:inherit;font-size:12px;border:1px solid var(--line-strong);border-bottom-width:2px;border-radius:4px;padding:0 5px;background:#fff}

footer{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 20px;margin-top:16px;color:var(--ink-3);font-size:12.5px}
footer span+span::before{content:"\00b7";margin:0 8px;color:var(--line-strong)}

.toast{position:fixed;right:24px;top:76px;z-index:9;max-width:380px;background:#fff;border:1px solid var(--line);border-left:4px solid var(--brand);border-radius:8px;box-shadow:0 8px 24px rgba(16,24,40,.12);padding:14px 16px}
.toast b{display:block;margin-bottom:2px}
.toast p{color:var(--ink-2);font-size:13.5px}

@media (max-width:1100px){
  .grid{grid-template-columns:1fr} .page{padding:16px} .head{flex-direction:column;align-items:flex-start}
  .nav{padding:0 12px;gap:10px} .nav-date,.nav-title{display:none} td{padding:10px 12px} th{padding:8px 12px}
}
</style>
</head>
<body>
<header class="nav">
  <div class="lp-chip"><img src="liftpic-logo.png" alt="Liftpictures"></div>
  <div class="nav-title">Station</div>
  <div class="nav-sep" id="parkSep" hidden></div>
  <img class="park-logo" id="parkLogo" alt="" hidden>
  <div class="nav-right">
    <div><div class="nav-clock num" id="clock">--:--</div><div class="nav-date" id="date"></div></div>
    <button class="btn-nav" id="hideBtn" type="button" title="Close this screen (Esc)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>Hide screen
    </button>
  </div>
</header>

<main class="page">
  <div class="crumb">Liftpictures &rsaquo; Station</div>
  <div class="head">
    <div><h1>System status</h1><div class="sub" id="sub">Waiting for the first report from Liftpictures Sync. This takes up to two minutes after the PC starts.</div></div>
    <div class="head-right"><span class="updated num" id="updated"></span><span class="pill t-idle" id="pill"><i></i><span>Starting</span></span></div>
  </div>

  <section class="alert t-bad" id="alert" hidden></section>

  <section class="card">
    <div class="card-head"><h2>Photo path</h2><p>Every photo passes these steps, from the camera to the guest.</p></div>
    <div class="flow-wrap"><ol class="flow" id="flow"></ol></div>
  </section>

  <div class="grid">
    <section class="card">
      <div class="card-head"><h2>Components</h2><span id="compCount"></span></div>
      <table><thead><tr><th>Component</th><th>Status</th><th>Details</th></tr></thead><tbody id="rows"></tbody></table>
    </section>
    <div class="side">
      <section class="card">
        <div class="card-head"><h2>Today</h2></div>
        <div class="stats" id="stats"></div>
      </section>
      <section class="card">
        <div class="card-head"><h2>Questions &amp; answers</h2></div>
        <div class="faq" id="faq"></div>
      </section>
    </div>
  </div>

  <footer>
    <div><span id="fMachine">Machine</span><span id="fVersion">Liftpictures Sync</span><span>Works without internet</span></div>
    <div><span>Support: support@liftpictures.com</span><span>+49 5222 8504-90</span></div>
  </footer>
</main>

<div class="toast" id="toast" hidden><b>Close this screen</b><p>Press <kbd>Alt</kbd> + <kbd>F4</kbd>. To open it again, double-click <b style="display:inline">Liftpictures Station</b> on the desktop.</p></div>

<script>
(function(){
  "use strict";
  var data=null, flowSig="", flowList=[], parkLogoShown=false, faqSig="";
  // Fassung dieser Seite. Schreibt der Agent nach einem Update eine neuere,
  // laedt sich das offene Fenster selbst neu (sonst zeigte es bis zum
  // naechsten Neustart die alte Seite mit neuen Daten).
  var PAGE_REV="__PAGE_REV__";

  var I={
    camera:'<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z"/><circle cx="12" cy="13" r="3"/>',
    image:'<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
    sync:'<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    wifi:'<path d="M12 20h.01"/><path d="M2 8.82a15 15 0 0 1 20 0"/><path d="M5 12.86a10 10 0 0 1 14 0"/><path d="M8.5 16.43a5 5 0 0 1 7 0"/>',
    cloud:'<path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2"/><path d="M12 12v9"/><path d="m16 16-4-4-4 4"/>',
    monitor:'<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
    sensor:'<circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49M7.76 16.24a6 6 0 0 1 0-8.49M19.07 4.93a10 10 0 0 1 0 14.14M4.93 19.07a10 10 0 0 1 0-14.14"/>',
    printer:'<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
    card:'<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
    plug:'<path d="M12 22v-5"/><path d="M9 8V2M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8z"/>',
    disk:'<path d="M22 12H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><path d="M6 16h.01M10 16h.01"/>',
    chip:'<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2M15 20v2M2 15h2M2 9h2M20 15h2M20 9h2M9 2v2M9 20v2"/>',
    clock:'<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    power:'<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>',
    warn:'<path d="M10.3 3.9 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    bad:'<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>',
    chev:'<path d="m9 18 6-6-6-6"/>'
  };
  function svg(name){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+(I[name]||I.chip)+'</svg>'}

  // Was bei einer Stoerung zu tun ist, je Station. Kurz und in der
  // Reihenfolge, in der man es am Automaten pruefen wuerde.
  var STEPS={
    sensor:["Make sure nothing blocks the light barrier.","Check the light barrier cable at the PC.","Restart the PC."],
    camera:["Check that the camera is switched on and shows no error.","Check the USB cable at the camera and at the PC.","Start the camera software again: click Start, type EOS Utility and open it.","Still red? Restart the PC."],
    sync:["Restart the PC. Liftpictures Sync starts by itself.","Still red after 5 minutes? Contact Liftpictures support."],
    internet:["Click the network icon at the bottom right, next to the clock.","Your network should say Connected. If not, choose it and click Connect.","Using a cable? Check it at the back of the PC and check that the router lights are on."],
    upload:["Check the internet (see Internet).","Photos stay on this PC and upload by themselves later."],
    sales:["Check that the sales screen is switched on.","Restart the PC."],
    terminal:["Check that the card terminal is switched on.","Check its network cable.","Switch the terminal off and on again."],
    printer:["Check paper and ribbon.","Close the printer cover.","Switch the printer off and on again."],
    screen:["Check that the second monitor is switched on and its cable is plugged in.","Restart the PC. The guest screen opens by itself."],
    serial:["A device is not connected. Check the USB cables at the PC.","Restart the PC."],
    disk:["The disk is almost full. Contact Liftpictures support."],
    memory:["Restart the PC."],
    clock:["The PC clock is not synchronized. Check the internet connection."]
  };

  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
  function pad(n){return (n<10?"0":"")+n}
  function hm(ts){var d=new Date(ts*1000);return pad(d.getHours())+":"+pad(d.getMinutes())}
  function dur(min){
    if(min==null||isNaN(min))return "";
    min=Math.max(0,Math.round(min));
    if(min<1)return "less than a minute";
    if(min<60)return min+" min";
    var h=Math.floor(min/60),m=min%60;
    if(h<48)return h+" h"+(m?" "+m+" min":"");
    return Math.floor(h/24)+" days";
  }
  function ago(ts){if(!ts)return "";var s=Date.now()/1000-ts;return s<60?"just now":dur(s/60)+" ago"}
  function isToday(ts){return new Date(ts*1000).toDateString()===new Date().toDateString()}
  function title(slug){return String(slug||"").split(/[-_]/).filter(Boolean).map(function(w){return w.charAt(0).toUpperCase()+w.slice(1)}).join(" ")}
  function esc(t){return String(t).replace(/[&<>"]/g,function(x){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[x]})}
  function probe(prefix){var ps=(data&&data.probes)||[];for(var i=0;i<ps.length;i++)if((ps[i].key||"").indexOf(prefix)===0)return ps[i];return null}
  function stale(){return !!data&&(Date.now()/1000-data.updated_at)>Math.max(300,3*(data.heartbeat_seconds||60))}

  // Programm-Messung -> Station. "off" heisst hier: sollte laufen, tut es nicht.
  function prog(p,id,name,icon,sub,purpose,okText,offText){
    if(!p)return null;
    var tone=p.status==="ok"?"ok":p.status==="unknown"?"idle":p.status==="warn"?"warn":"bad";
    var status=tone==="ok"?okText:tone==="idle"?"Unknown":offText;
    var det=tone==="ok"&&p.since_minutes!=null?"Running for "+dur(p.since_minutes):tone==="idle"?"Could not be checked":status;
    return {id:id,name:name,icon:icon,tone:tone,status:status,sub:sub||p.tech||"",purpose:purpose,det:det};
  }

  // Die Stationen in der Reihenfolge, die ein Foto durchlaeuft.
  function stations(){
    var list=[],d=data,dead=stale(),q=d.queue_count||0,lp=d.last_photo_at,lpToday=lp&&isToday(lp);
    function add(s){if(s)list.push(s)}
    add(prog(probe("proc:AidaTest"),"sensor","Light barrier","sensor","","Detects riders and triggers the camera.","Running","Not running"));
    add(prog(probe("proc:3gerTis_v70"),"camera","Camera","camera",d.camera_program,"Receives every photo from the camera.","Running","Not running"));
    add({id:"photos",name:"Photos",icon:"image",tone:lpToday?"ok":"idle",status:lpToday?"Last "+hm(lp):"None today",sub:"",
         purpose:"New photos are saved on this PC.",
         det:lp?"Last photo "+(lpToday?"":new Date(lp*1000).toLocaleDateString("en-US",{month:"short",day:"numeric"})+", ")+hm(lp)+" ("+ago(lp)+")":"No photos yet"});
    add({id:"sync",name:"Liftpictures Sync",icon:"sync",tone:dead?"bad":"ok",status:dead?"Not responding":"Running",sub:"Version "+(d.version||""),
         purpose:"Uploads photos and watches this PC.",det:dead?"No report since "+hm(d.updated_at):"Last report "+ago(d.updated_at)});
    add({id:"internet",name:"Internet",icon:"wifi",tone:d.online?"ok":"warn",status:d.online?"Online":"Offline",sub:"",
         purpose:"Connects this PC to the Liftpictures cloud.",det:d.online?"Connected":"Offline"+(d.offline_since?" since "+hm(d.offline_since):"")});
    add({id:"upload",name:"Upload",icon:"cloud",tone:!d.online||q>=25?"warn":"ok",status:!d.online?"Paused":q?q+" waiting":"Up to date",sub:"",
         purpose:"Guests can buy their photos online.",det:q?q+(q===1?" photo":" photos")+" waiting to upload":"All photos uploaded"});
    add(prog(probe("proc:PhotoViewerFacebook"),"sales","Sales screen","monitor","","Shows photos to guests, takes payment and prints.","Running","Not running"));
    var t=probe("tcp:");
    if(t)add({id:"terminal",name:"Card terminal",icon:"card",tone:t.status==="ok"?"ok":t.status==="unknown"?"idle":"bad",status:t.status==="ok"?"Ready":"No response",sub:"",
              purpose:"Accepts card payments.",det:t.status==="ok"&&t.value!=null?"Responds in "+t.value+" ms":"No response"});
    (d.probes||[]).forEach(function(p){
      if((p.key||"").indexOf("printer:")!==0)return;
      add({id:"printer",name:"Printer",icon:"printer",tone:p.status==="ok"?"ok":"warn",status:p.status==="ok"?"Ready":"Problem",sub:p.tech||"",
           purpose:"Prints purchased photos.",det:p.status==="ok"?(p.value||0)+" jobs waiting":"Reports a problem"});
    });
    add(prog(probe("screen:"),"screen","Guest screen","monitor","Second monitor","Shows guests their photos with a QR code.","Showing photos","Not open"));
    if(dead)list.forEach(function(s){if(s.id!=="sync"){s.tone="idle";s.status="No data";s.det="Waiting for Liftpictures Sync"}});
    return list;
  }

  function systemRows(){
    var out=[],s=probe("serial");
    if(s&&s.status!=="ok"&&s.status!=="unknown")out.push({id:"serial",name:"USB / COM ports",icon:"plug",tone:"bad",status:"Missing",purpose:"Connections for devices.",det:"A device is not connected"});
    [["disk","Disk space","disk","Free space for new photos."],["memory","Memory","chip","Working memory of this PC."],
     ["clock","Clock","clock","Part of every photo code."],["uptime","PC running","power","Time since the last restart."]].forEach(function(r){
      var p=probe(r[0]);if(!p)return;
      var tone=p.status==="ok"?"ok":p.status==="warn"?"warn":p.status==="down"?"bad":"idle";
      if(stale())tone="idle";
      var det=r[0]==="disk"||r[0]==="memory"?(p.value!=null?p.value+" GB free":""):r[0]==="clock"?(p.status==="ok"?"Synchronized":"Not synchronized"):dur(p.since_minutes!=null?p.since_minutes:p.value);
      out.push({id:r[0],name:r[1],icon:r[2],tone:tone,status:tone==="ok"?"OK":tone==="idle"?"No data":"Check",sub:"",purpose:r[3],det:det});
    });
    return out;
  }

  function badge(tone,text){var b=el("span","badge t-"+tone);b.appendChild(el("i"));b.appendChild(document.createTextNode(text));return b}

  function renderFlow(list){
    flowList=list;
    var sig=list.map(function(s){return s.id+":"+s.tone+":"+s.status}).join("|");
    if(sig===flowSig)return;
    flowSig=sig;
    var ol=document.getElementById("flow");ol.textContent="";
    list.forEach(function(s,i){
      if(i>0){var ln=el("li","line"+(s.tone==="warn"?" warn":""));ln.setAttribute("aria-hidden","true");ln.appendChild(el("span"));ol.appendChild(ln)}
      var li=el("li","st t-"+s.tone),c=el("div","c");
      c.innerHTML=svg(s.icon);c.appendChild(el("i"));
      li.appendChild(c);li.appendChild(el("div","n",s.name));li.appendChild(el("div","s",s.status));
      ol.appendChild(li);
    });
    step=-1;
  }

  // Lichtlauf wie im Dashboard: alle 650 ms eine Station weiter, 4 Takte
  // Pause, Halt vor der ersten roten Station - die pulsiert dann rot.
  var step=-1;
  function tick(){
    var sts=document.querySelectorAll("#flow .st"),lines=document.querySelectorAll("#flow .line");
    if(!sts.length)return;
    var firstRed=-1;for(var i=0;i<flowList.length;i++)if(flowList[i].tone==="bad"){firstRed=i;break}
    var last=firstRed===-1?flowList.length-1:firstRed-1,PAUSE=4;
    step=step>=last+PAUSE?0:step+1;
    var cur=step<=last?step:-1;
    for(var j=0;j<sts.length;j++){
      var c=sts[j].querySelector(".c"),tone=flowList[j]?flowList[j].tone:"idle";
      c.classList.toggle("red",j===firstRed);
      c.classList.toggle("glow",j===cur&&j!==firstRed);
      c.classList.toggle("warn",tone==="warn");
    }
    for(var k=0;k<lines.length;k++){
      var ln=lines[k];ln.classList.remove("run");
      if(k+1===cur){void ln.offsetWidth;ln.classList.add("run")}
    }
  }

  function render(){
    if(!data)return;
    var list=stations(),all=list.concat(systemRows()),dead=stale();
    document.getElementById("sub").textContent=title(data.park_slug)+" \u00b7 Machine "+(data.machine_id||"");
    document.getElementById("updated").textContent="Updated "+hm(data.updated_at);
    document.getElementById("fMachine").textContent="Machine "+(data.machine_id||"-");
    document.getElementById("fVersion").textContent="Liftpictures Sync "+(data.version||"");

    if(data.park_logo&&!parkLogoShown){
      var img=document.getElementById("parkLogo");parkLogoShown=true;
      img.onload=function(){img.hidden=false;document.getElementById("parkSep").hidden=false};
      img.onerror=function(){img.hidden=true;document.getElementById("parkSep").hidden=true};
      img.src="park-logo?v="+Date.now();
    }

    var bad=all.filter(function(s){return s.tone==="bad"}),warn=all.filter(function(s){return s.tone==="warn"});
    var pt=bad.length?"bad":warn.length?"warn":"ok",pill=document.getElementById("pill");
    pill.className="pill t-"+pt;
    pill.lastChild.textContent=dead?"Monitoring stopped":bad.length?"Action required":warn.length?"Attention needed":"All systems running";

    var al=document.getElementById("alert"),probs=bad.concat(warn);al.textContent="";
    if(probs.length){
      al.hidden=false;al.className="alert t-"+pt;
      var ic=el("div");ic.innerHTML=svg(pt==="bad"?"bad":"warn");al.appendChild(ic.firstChild);
      var body=el("div");
      body.appendChild(el("h3",null,dead?"Liftpictures Sync is not responding":probs.length===1?probs[0].name+": "+probs[0].status:probs.length+" items need attention"));
      body.appendChild(el("div","lead",dead?"There has been no new report since "+hm(data.updated_at)+". The values below may be out of date.":"Please follow these steps. Everything else is running normally."));
      var items=el("div","items");
      var offline=probs.some(function(s){return s.id==="internet"});
      probs.forEach(function(s){
        var steps=STEPS[s.id];if(!steps||(s.id==="upload"&&offline))return;
        var it=el("div","item"),ol=el("ol");it.appendChild(el("b",null,s.name));
        steps.forEach(function(x){ol.appendChild(el("li",null,x))});it.appendChild(ol);items.appendChild(it);
      });
      body.appendChild(items);al.appendChild(body);
    } else al.hidden=true;

    renderFlow(list);

    var tb=document.getElementById("rows");tb.textContent="";
    all.forEach(function(s){
      var tr=el("tr"),td=el("td"),comp=el("div","comp"),ic=el("span","ic"),txt=el("div");
      ic.innerHTML=svg(s.icon);
      txt.appendChild(el("b",null,s.name));
      txt.appendChild(el("small",null,s.sub?s.sub+" \u00b7 "+s.purpose:s.purpose));
      comp.appendChild(ic);comp.appendChild(txt);td.appendChild(comp);tr.appendChild(td);
      var td2=el("td");td2.appendChild(badge(s.tone,s.status));tr.appendChild(td2);
      tr.appendChild(el("td","det num",s.tone==="bad"&&!dead?"See the steps at the top":s.det||""));tb.appendChild(tr);
    });
    document.getElementById("compCount").textContent=all.filter(function(s){return s.tone==="ok"}).length+" of "+all.length+" OK";

    var st=document.getElementById("stats"),lp=data.last_photo_at,lpToday=lp&&isToday(lp);st.textContent="";
    function stat(k,v,small){var d=el("div","stat"),vv=el("div","v num",v);d.appendChild(el("div","k",k));if(small){vv.appendChild(document.createTextNode(" "));vv.appendChild(el("small",null,small))}d.appendChild(vv);st.appendChild(d)}
    stat("Photos today",String(data.photos_today||0));
    stat("Last photo",lpToday?hm(lp):"\u2013",lpToday?ago(lp):"");
    stat("Sold today",String(data.photos_sold_today||0));
    stat("Waiting to upload",String(data.queue_count||0));

    renderFaq();
  }

  // Fragen & Antworten. Neu aufgebaut nur, wenn sich die eingesetzten Werte
  // aendern - sonst klappten offene Antworten bei jedem Neuladen zu.
  function renderFaq(){
    var raw=data.raw_dir||"C:\\liftpic\\fotos",m=data.machine_id||"";
    var sig=raw+"|"+m;if(sig===faqSig)return;faqSig=sig;
    function c(t){return "<code>"+esc(t)+"</code>"}
    var Q=[
      ["What does this screen show?","<p>Whether the photo system is working. Green means everything is fine. The screen updates itself every few seconds and also works without internet.</p>"],
      ["How do I close this screen and open it again?","<p>Click <b>Hide screen</b> at the top right, or press <kbd>Esc</kbd>.</p><p>To open it again, double-click <b>Liftpictures Station</b> on the desktop. It also opens by itself when the PC starts.</p>"],
      ["The camera is red. What do I do?","<ol><li>Check that the camera is switched on and its display shows no error.</li><li>Check the USB cable at the camera and at the PC.</li><li>Start the camera software again: click <b>Start</b>, type <b>EOS Utility</b> and open it.</li><li>Still red? Restart the PC.</li></ol><p>The camera software must stay open while the attraction runs. Please do not close its window.</p>"],
      ["No new photos are coming in.","<p>Look at <b>Last photo</b> under Today. If it does not change while guests ride, check the camera (see the question above).</p><p>New photos are saved in "+c(raw)+".</p>"],
      ["The guest screen is black or shows an error.","<ol><li>Check that the second monitor is switched on and its cable is plugged in.</li><li>Restart the PC. The guest screen opens by itself.</li></ol><p>The guest screen needs internet to show new photos.</p>"],
      ["How do I check the internet or Wi-Fi?","<ol><li>Click the network icon at the bottom right of the screen, next to the clock.</li><li>Your network should say <b>Connected</b>. If not, choose it and click <b>Connect</b>.</li><li>Using a network cable? Check it at the back of the PC and check that the router lights are on.</li></ol><p>While offline, photos stay on this PC and upload by themselves later. Nothing is lost.</p>"],
      ["How do I restart the PC correctly?","<p>Click <b>Start</b>, then <b>Power</b>, then <b>Restart</b>. Please do not just unplug the power.</p><p>After about two minutes everything runs again by itself: camera software, guest screen and this screen.</p>"],
      ["Where are the photos stored on this PC?","<p>In "+c(raw)+". Please do not move, rename or delete files there. The online shop needs them.</p>"],
      ["Who do I contact?","<p>Liftpictures support: <b>support@liftpictures.com</b> or <b>+49 5222 8504-90</b>.</p><p>Please tell us the machine name: "+c(m)+".</p>"]
    ];
    var box=document.getElementById("faq"),open={};
    Array.prototype.forEach.call(box.querySelectorAll("details"),function(d,i){if(d.open)open[i]=true});
    box.innerHTML=Q.map(function(q,i){return "<details"+(open[i]?" open":"")+"><summary>"+svg("chev")+"<span>"+esc(q[0])+"</span></summary><div class=\"a\">"+q[1]+"</div></details>"}).join("");
  }

  function clock(){
    var d=new Date();
    document.getElementById("clock").textContent=pad(d.getHours())+":"+pad(d.getMinutes());
    document.getElementById("date").textContent=d.toLocaleDateString("en-US",{weekday:"short",month:"short",day:"numeric"});
  }

  // Schliessen: ein per Verknuepfung geoeffnetes App-Fenster darf sich selbst
  // schliessen. Klappt es nicht, sagt die Seite, wie es geht.
  function hide(){
    try{window.close()}catch(e){}
    setTimeout(function(){var t=document.getElementById("toast");t.hidden=false;setTimeout(function(){t.hidden=true},8000)},300);
  }
  document.getElementById("hideBtn").addEventListener("click",hide);
  document.addEventListener("keydown",function(e){if(e.key==="Escape")hide()});

  window.__station=function(s){
    if(s&&s.page_rev&&s.page_rev!==PAGE_REV){location.reload();return}
    data=s;try{render()}catch(e){if(window.console)console.error(e)}
  };
  var current=null;
  function load(){
    var s=document.createElement("script");
    s.src="status.js?t="+Date.now();
    s.onload=s.onerror=function(){if(current&&current!==s&&current.parentNode)current.parentNode.removeChild(current);current=s};
    document.head.appendChild(s);
  }

  clock();load();
  setInterval(clock,1000);
  setInterval(load,5000);
  setInterval(function(){try{render()}catch(e){}},20000);
  if(!(window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches))setInterval(tick,650);
})();
</script>
</body>
</html>
"""
