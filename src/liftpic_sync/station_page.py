"""Die HTML-Seite der Liftpictures Station (siehe station.py).

Bewusst als Python-Text statt als Datei im Paket: so kommt sie mit jedem Build
mit, ohne dass Paketdaten eingerichtet sein muessen. Kein CDN, keine Webfonts:
die Seite muss offline laufen.
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Liftpictures Station</title>
<style>
:root{
  --bg:#080b10; --bg2:#0c1118; --panel:#111821; --panel2:#151e29; --line:#1e2935; --line2:#273444;
  --text:#e8eef5; --muted:#8a97a8; --faint:#5d6b7c;
  --ok:#2fd27a; --ok-bg:rgba(47,210,122,.10); --warn:#f5b13d; --warn-bg:rgba(245,177,61,.11);
  --down:#ff5a5f; --down-bg:rgba(255,90,95,.11); --idle:#6b7a8c; --idle-bg:rgba(107,122,140,.12);
  --accent:#4ea8ff;
  --r:18px;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{
  background:radial-gradient(1200px 600px at 85% -10%,rgba(78,168,255,.07),transparent 60%),var(--bg);
  color:var(--text);
  font-family:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
  font-size:16px; line-height:1.45; -webkit-font-smoothing:antialiased;
  overflow:hidden; cursor:default; user-select:none;
}
.app{height:100vh;display:grid;grid-template-rows:auto auto 1fr auto;gap:22px;padding:28px 36px 20px}
.num{font-variant-numeric:tabular-nums}

/* header */
header{display:flex;align-items:center;justify-content:space-between;gap:24px}
.brand{display:flex;align-items:center;gap:14px}
.mark{width:42px;height:42px;border-radius:12px;background:linear-gradient(145deg,#1d2a3a,#111821);border:1px solid var(--line2);display:grid;place-items:center}
.brand b{font-size:20px;letter-spacing:.2px;font-weight:650}
.brand span{display:block;font-size:12px;letter-spacing:2.4px;text-transform:uppercase;color:var(--muted);margin-top:1px}
.site{text-align:center}
.site .park{font-size:19px;font-weight:600}
.site .machine{font-size:13px;color:var(--muted)}
.clock{text-align:right}
.clock .t{font-size:34px;font-weight:600;letter-spacing:.5px;line-height:1}
.clock .d{font-size:13px;color:var(--muted);margin-top:6px}

/* hero */
.hero{display:flex;align-items:center;gap:26px;padding:26px 30px;border-radius:var(--r);border:1px solid var(--line);background:linear-gradient(180deg,var(--panel2),var(--panel));position:relative;overflow:hidden}
.hero::before{content:"";position:absolute;inset:0 auto 0 0;width:6px;background:var(--c)}
.hero .ring{width:74px;height:74px;border-radius:50%;flex:none;display:grid;place-items:center;background:var(--cbg);box-shadow:0 0 0 1px var(--c) inset}
.hero .ring svg{width:38px;height:38px;stroke:var(--c)}
.hero h1{font-size:34px;font-weight:650;letter-spacing:-.3px;line-height:1.1}
.hero p{color:var(--muted);font-size:17px;margin-top:6px;max-width:980px}
.hero .meta{margin-left:auto;text-align:right;color:var(--muted);font-size:14px;white-space:nowrap}
.hero .meta strong{display:block;color:var(--text);font-size:15px;font-weight:600}
.s-ok{--c:var(--ok);--cbg:var(--ok-bg)} .s-warn{--c:var(--warn);--cbg:var(--warn-bg)}
.s-down{--c:var(--down);--cbg:var(--down-bg)} .s-idle,.s-unknown{--c:var(--idle);--cbg:var(--idle-bg)}
.pulse .ring{animation:pulse 2.2s ease-in-out infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 1px var(--c) inset,0 0 0 0 var(--cbg)}50%{box-shadow:0 0 0 1px var(--c) inset,0 0 0 12px transparent}}

/* body grid */
main{display:grid;grid-template-columns:minmax(0,1.85fr) minmax(0,1fr);gap:22px;min-height:0}
.col{display:flex;flex-direction:column;gap:22px;min-height:0}
h2{font-size:12px;letter-spacing:2.2px;text-transform:uppercase;color:var(--faint);font-weight:600;margin-bottom:12px}
.tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.tile{border:1px solid var(--line);background:var(--panel);border-radius:var(--r);padding:18px 20px;display:flex;flex-direction:column;gap:10px;min-height:118px}
.tile.bad{border-color:color-mix(in srgb,var(--c) 45%,var(--line));background:linear-gradient(180deg,var(--cbg),var(--panel) 70%)}
.tile .top{display:flex;align-items:center;gap:12px}
.dot{width:12px;height:12px;border-radius:50%;background:var(--c);box-shadow:0 0 0 4px var(--cbg);flex:none}
.tile .name{font-size:18px;font-weight:620}
.tile .tech{font-size:12px;color:var(--faint);margin-left:auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:45%}
.tile .state{font-size:15px;color:var(--text)}
.tile .state small{color:var(--muted);font-size:14px}
.tile .purpose{font-size:13px;color:var(--muted)}
.todo{border-top:1px solid var(--line);padding-top:10px;margin-top:2px}
.todo b{display:block;font-size:12px;letter-spacing:1.6px;text-transform:uppercase;color:var(--c);margin-bottom:6px}
.todo ol{padding-left:20px;font-size:14.5px;color:var(--text)}
.todo li{margin:2px 0}
.chips{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.chip{border:1px solid var(--line);background:var(--panel);border-radius:14px;padding:14px 16px;display:flex;flex-direction:column;gap:4px}
.chip .k{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:8px}
.chip .k .dot{width:8px;height:8px;box-shadow:0 0 0 3px var(--cbg)}
.chip .v{font-size:16px;font-weight:600}

/* side */
.card{border:1px solid var(--line);background:var(--panel);border-radius:var(--r);padding:20px 22px}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:18px 20px}
.stat .k{font-size:13px;color:var(--muted)}
.stat .v{font-size:30px;font-weight:650;letter-spacing:-.4px;line-height:1.15;margin-top:2px}
.stat .v small{font-size:14px;color:var(--muted);font-weight:500;letter-spacing:0}
.list{display:flex;flex-direction:column}
.list .row{display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--line);font-size:14.5px}
.list .row:first-child{border-top:0;padding-top:0}
.list .row time{color:var(--muted);margin-left:auto;white-space:nowrap}
.help ol{padding-left:20px;font-size:14.5px}
.help li{margin:4px 0}
.help .note{color:var(--muted);font-size:13.5px;margin-top:10px}
.empty{color:var(--muted);font-size:14.5px}
footer{display:flex;justify-content:space-between;color:var(--faint);font-size:12.5px;letter-spacing:.2px}
footer span+span::before{content:"·";margin:0 10px;color:var(--line2)}

@media (max-width:1100px){
  body{overflow:auto} .app{height:auto;padding:16px} main{grid-template-columns:1fr}
  .tiles{grid-template-columns:1fr} .chips{grid-template-columns:repeat(2,1fr)}
  header{flex-wrap:wrap} .site{text-align:left} .hero{flex-wrap:wrap} .hero .meta{margin-left:0;text-align:left}
}
</style>
</head>
<body>
<div class="app">
  <header>
    <div class="brand">
      <div class="mark" aria-hidden="true">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#4ea8ff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 19l6-9 4 5 3-4 5 8z"/><path d="M2 5l20-2"/><path d="M14 4v4"/></svg>
      </div>
      <div><b>Liftpictures</b><span>Station</span></div>
    </div>
    <div class="site"><div class="park" id="park">&nbsp;</div><div class="machine" id="machine">&nbsp;</div></div>
    <div class="clock"><div class="t num" id="time">--:--</div><div class="d" id="date">&nbsp;</div></div>
  </header>

  <section class="hero s-idle" id="hero">
    <div class="ring" id="heroIcon"></div>
    <div><h1 id="heroTitle">Starting up</h1><p id="heroText">Waiting for the first status report from Liftpictures Sync.</p></div>
    <div class="meta" id="heroMeta"></div>
  </section>

  <main>
    <div class="col">
      <div><h2>Components</h2><div class="tiles" id="tiles"></div></div>
      <div><h2>Computer</h2><div class="chips" id="chips"></div></div>
    </div>
    <div class="col">
      <div class="card"><h2>Today</h2><div class="stats" id="stats"></div></div>
      <div class="card"><h2>Recent</h2><div class="list" id="recent"></div></div>
      <div class="card help"><h2>If something is wrong</h2>
        <ol>
          <li>Follow the steps shown on the red or amber tile.</li>
          <li>Still not working? Restart the PC: Start, Power, Restart. Everything starts again by itself.</li>
          <li>Then contact Liftpictures support and tell us the machine name shown at the bottom.</li>
        </ol>
        <div class="note">Photos are never lost while offline. They stay on this PC and upload as soon as the connection is back.</div>
      </div>
    </div>
  </main>

  <footer><div><span id="fMachine">Machine</span><span id="fVersion">Agent</span><span>Works without internet</span></div><div id="fUpdated">&nbsp;</div></footer>
</div>

<script>
(function(){
  "use strict";
  var data = null, loadedAt = 0;

  var ICONS = {
    ok:'<svg viewBox="0 0 24 24" fill="none" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    warn:'<svg viewBox="0 0 24 24" fill="none" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8v5"/><path d="M12 16.8v.2"/><path d="M10.3 3.9L2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
    down:'<svg viewBox="0 0 24 24" fill="none" stroke-width="2.4" stroke-linecap="round"><path d="M7 7l10 10M17 7L7 17"/></svg>',
    idle:'<svg viewBox="0 0 24 24" fill="none" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>'
  };

  // Englische Namen und Hilfen, nach Anfang des Probe-Schluessels.
  var CATALOG = [
    {k:"proc:PhotoViewerFacebook", n:"Sales screen", p:"Shows the photos to guests, takes payment and prints.",
     todo:["Check that the guest screen is switched on.","Restart the PC."]},
    {k:"proc:AidaTest", n:"Light barrier", p:"Detects riders and triggers the camera.",
     todo:["Make sure nothing blocks the light barrier sensors.","Check the light barrier cable on the PC.","Restart the PC."]},
    {k:"proc:3gerTis_v70", n:"Camera software", p:"Receives every photo from the camera.", camera:true,
     todo:["Check that the camera is switched on and shows no error on its display.","Check the USB cable at the camera and at the PC.","Restart the PC."]},
    {k:"tcp:", n:"Card terminal", p:"Accepts card payments.",
     todo:["Check that the card terminal is switched on.","Check its network cable.","Switch the terminal off and on again."]},
    {k:"printer", n:"Photo printer", p:"Prints purchased photos.",
     todo:["Check paper and ribbon.","Close the printer cover.","Switch the printer off and on again."]},
    {k:"serial", n:"USB / COM ports", p:"Connections for the light barrier and coin unit.",
     todo:["A device is not connected. Check the USB cables on the PC.","Restart the PC."]},
    {k:"disk", n:"Disk space", sys:true, todo:["The disk is almost full. Contact Liftpictures support."]},
    {k:"memory", n:"Memory", sys:true, todo:["Restart the PC."]},
    {k:"uptime", n:"PC running", sys:true, todo:[]},
    {k:"clock", n:"Clock", sys:true, todo:["The PC clock is not synchronized. Check the internet connection."]}
  ];

  function info(key){
    for (var i=0;i<CATALOG.length;i++) if (key.indexOf(CATALOG[i].k)===0) return CATALOG[i];
    return {k:key, n:key, p:"", todo:[]};
  }

  function el(tag, cls, text){
    var e=document.createElement(tag); if(cls) e.className=cls; if(text!=null) e.textContent=text; return e;
  }
  function pad(n){return (n<10?"0":"")+n}
  function hm(ts){var d=new Date(ts*1000);return pad(d.getHours())+":"+pad(d.getMinutes())}
  function dur(min){
    if(min==null||isNaN(min)) return "";
    min=Math.max(0,Math.round(min));
    if(min<1) return "less than a minute";
    if(min<60) return min+" min";
    var h=Math.floor(min/60), m=min%60;
    if(h<48) return h+" h"+(m?" "+m+" min":"");
    return Math.floor(h/24)+" days";
  }
  function ago(ts){
    if(!ts) return "";
    var s=(Date.now()/1000)-ts;
    if(s<60) return Math.max(0,Math.round(s))+" s ago";
    return dur(s/60)+" ago";
  }
  function title(slug){
    return String(slug||"").split(/[-_]/).filter(Boolean).map(function(w){return w.charAt(0).toUpperCase()+w.slice(1)}).join(" ");
  }

  // Probe -> Stufe fuer die Anzeige. Ein Programm, das nicht laeuft, ist hier
  // ein Fehler: auf dieser Seite sieht man nur Programme, die laufen sollen.
  function level(p){
    if(p.kind==="process") return p.status==="ok"?"ok":p.status==="off"?"down":p.status==="unknown"?"unknown":p.status;
    if(p.status==="off") return "idle";
    return p.status;
  }

  function stateText(p, lv){
    var key=p.key||"";
    if(p.kind==="process"){
      if(lv==="ok") return ["Running", p.since_minutes!=null?"for "+dur(p.since_minutes):""];
      if(lv==="unknown") return ["Could not be checked",""];
      return ["Not running",""];
    }
    if(key.indexOf("tcp:")===0) return lv==="ok"?["Ready", p.value!=null?"responds in "+p.value+" ms":""]:["No response",""];
    if(key.indexOf("printer")===0) return lv==="ok"?["Ready", (p.value||0)+" jobs waiting"]:lv==="idle"?["No photo printer set up",""]:["Reports a problem",""];
    if(key==="serial"){var ports=Array.isArray(p.value)?p.value.join(", "):""; return lv==="ok"?["Connected",ports]:["A port is missing",ports?"present: "+ports:""];}
    if(key==="disk") return [(p.value!=null?p.value+" GB free":"OK"),""];
    if(key==="memory") return [(p.value!=null?p.value+" GB free":"OK"),""];
    if(key==="uptime") return [dur(p.since_minutes!=null?p.since_minutes:p.value),""];
    if(key==="clock") return lv==="ok"?["Synchronized",""]:lv==="unknown"?["Unknown",""]:["Not synchronized",""];
    return [lv==="ok"?"OK":lv==="unknown"?"Unknown":"Needs attention",""];
  }

  function stale(){
    if(!data) return false;
    var limit=Math.max(300,3*(data.heartbeat_seconds||60));
    return (Date.now()/1000-data.updated_at)>limit;
  }

  function render(){
    var hero=document.getElementById("hero");
    var tiles=document.getElementById("tiles"), chips=document.getElementById("chips");
    tiles.textContent=""; chips.textContent="";

    if(!data){ setHero("idle","Starting up","Waiting for the first status report from Liftpictures Sync. This can take up to two minutes after the PC starts.",""); return; }

    document.getElementById("park").textContent=title(data.park_slug)||"Liftpictures";
    document.getElementById("machine").textContent="Machine "+(data.machine_id||"");
    document.getElementById("fMachine").textContent="Machine "+(data.machine_id||"-");
    document.getElementById("fVersion").textContent="Liftpictures Sync "+(data.version||"");
    document.getElementById("fUpdated").textContent="Last report "+hm(data.updated_at)+" ("+ago(data.updated_at)+")";

    var down=[], warn=[], ka=data.keepalive||{};
    (data.probes||[]).forEach(function(p){
      var meta=info(p.key||""), lv=level(p);
      if(meta.sys){
        var c=el("div","chip s-"+lv), k=el("div","k"); k.appendChild(el("span","dot")); k.appendChild(document.createTextNode(meta.n));
        c.appendChild(k); c.appendChild(el("div","v num",stateText(p,lv)[0]));
        chips.appendChild(c);
        if(lv==="down") down.push(meta.n); else if(lv==="warn") warn.push(meta.n);
        return;
      }
      if(lv==="idle") return;
      if(p.key==="serial" && lv==="ok") return;
      var bad=(lv==="down"||lv==="warn");
      if(lv==="down") down.push(meta.n); else if(lv==="warn") warn.push(meta.n);
      var t=el("div","tile s-"+lv+(bad?" bad":"")), top=el("div","top");
      top.appendChild(el("span","dot")); top.appendChild(el("div","name",meta.n));
      if(p.tech) top.appendChild(el("div","tech",p.tech));
      t.appendChild(top);
      var st=stateText(p,lv), s=el("div","state num",st[0]);
      if(st[1]){ s.appendChild(document.createTextNode(" ")); s.appendChild(el("small",null,st[1])); }
      t.appendChild(s);
      if(!bad && meta.p) t.appendChild(el("div","purpose",meta.p));
      if(bad){
        var box=el("div","todo"), steps=meta.todo.slice();
        if(meta.camera && ka.enabled){
          box.appendChild(el("b",null,ka.last_error?"Automatic restart failed":"Restarting automatically"));
          steps=["Wait two minutes. The camera software is started again by itself."].concat(steps);
        } else box.appendChild(el("b",null,"What to do"));
        var ol=el("ol"); steps.forEach(function(x){ol.appendChild(el("li",null,x))}); box.appendChild(ol);
        t.appendChild(box);
      }
      tiles.appendChild(t);
    });
    // Internet und Upload als eigene Kachel: das ist es, was der Betreiber
    // wissen will - kommen die Fotos bei den Gaesten an?
    var q=data.queue_count||0, up=el("div","tile "+(data.online?"s-ok":"s-warn bad")), ut=el("div","top");
    ut.appendChild(el("span","dot")); ut.appendChild(el("div","name","Internet & photo upload")); ut.appendChild(el("div","tech","Liftpictures Cloud"));
    up.appendChild(ut);
    var us=el("div","state num",data.online?"Online":"Offline"+(data.offline_since?" since "+hm(data.offline_since):""));
    us.appendChild(document.createTextNode(" ")); us.appendChild(el("small",null,q?q+(q===1?" photo":" photos")+" waiting":"nothing waiting"));
    up.appendChild(us);
    if(data.online) up.appendChild(el("div","purpose","Sends photos to the Liftpictures cloud so guests can buy them."));
    else {
      warn.push("Internet");
      var ub=el("div","todo"); ub.appendChild(el("b",null,"What to do"));
      var uo=el("ol"); ["Photos are kept on this PC and upload by themselves when the internet is back.","Check the network cable and the router.","Restart the router if it does not come back within 15 minutes."].forEach(function(x){uo.appendChild(el("li",null,x))});
      ub.appendChild(uo); up.appendChild(ub);
    }
    tiles.appendChild(up);

    // Heute
    var stats=document.getElementById("stats"); stats.textContent="";
    function stat(k,v,small){var d=el("div","stat"); d.appendChild(el("div","k",k)); var vv=el("div","v num",v); if(small){vv.appendChild(document.createTextNode(" ")); vv.appendChild(el("small",null,small));} d.appendChild(vv); stats.appendChild(d);}
    stat("Photos today", String(data.photos_today||0));
    stat("Last photo", data.last_photo_at?hm(data.last_photo_at):"None", data.last_photo_at?ago(data.last_photo_at):"");
    stat("Waiting to upload", String(data.queue_count||0), (data.queue_count||0)===1?"photo":"photos");
    stat("Sold today", String(data.photos_sold_today||0));

    // Zuletzt
    var recent=document.getElementById("recent"); recent.textContent="";
    if(ka.last_start && (Date.now()/1000-ka.last_start)<86400){
      var r=el("div","row"); r.appendChild(el("span",null,"Camera software was restarted automatically")); r.appendChild(el("time","num",hm(ka.last_start))); recent.appendChild(r);
    }
    if(!data.online && data.offline_since){
      var r2=el("div","row"); r2.appendChild(el("span",null,"Connection lost")); r2.appendChild(el("time","num",hm(data.offline_since))); recent.appendChild(r2);
    }
    if(ka.enabled){
      var r3=el("div","row"); r3.appendChild(el("span",null,"Camera watchdog active"+(ka.program?" ("+ka.program+")":""))); r3.appendChild(el("time",null,"on")); recent.appendChild(r3);
    }
    if(!recent.childNodes.length) recent.appendChild(el("div","empty","Nothing to report."));

    var when="Checked "+hm(data.updated_at);
    if(stale()) setHero("down","Monitoring stopped","Liftpictures Sync has not reported since "+hm(data.updated_at)+". Restart the PC. If this message stays, contact Liftpictures support.", "Last report <strong>"+ago(data.updated_at)+"</strong>", true);
    else if(down.length) setHero("down","Action required", down.join(", ")+(down.length>1?" need":" needs")+" attention. Follow the steps on the red tile.", when, true);
    else if(warn.length) setHero("warn","Attention needed", warn.join(", ")+". Everything else is running.", when);
    else setHero("ok","All systems running","Camera, uploads and connection are working normally.", when);
  }

  function setHero(lv,t,p,meta,pulse){
    var hero=document.getElementById("hero");
    hero.className="hero s-"+(lv==="unknown"?"idle":lv)+(pulse?" pulse":"");
    document.getElementById("heroIcon").innerHTML=ICONS[lv]||ICONS.idle;
    document.getElementById("heroTitle").textContent=t;
    document.getElementById("heroText").textContent=p;
    var m=document.getElementById("heroMeta");
    if(meta && meta.indexOf("<strong>")>=0){ m.textContent=""; var parts=meta.split("<strong>"); m.appendChild(document.createTextNode(parts[0])); m.appendChild(el("strong","num",parts[1].replace("</strong>",""))); }
    else m.textContent=meta||"";
  }

  function tick(){
    var d=new Date();
    document.getElementById("time").textContent=pad(d.getHours())+":"+pad(d.getMinutes());
    document.getElementById("date").textContent=d.toLocaleDateString("en-US",{weekday:"long",month:"long",day:"numeric"});
  }

  window.__station=function(s){ data=s; loadedAt=Date.now(); try{render()}catch(e){} };

  var current=null;
  function load(){
    var s=document.createElement("script");
    s.src="status.js?t="+Date.now();
    s.onload=s.onerror=function(){ if(current&&current!==s&&current.parentNode) current.parentNode.removeChild(current); current=s; };
    document.head.appendChild(s);
  }

  tick(); render(); load();
  setInterval(tick,1000);
  setInterval(load,5000);
  setInterval(function(){try{render()}catch(e){}},15000);
})();
</script>
</body>
</html>
"""
