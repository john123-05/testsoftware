"""Die Seite der Liftpictures Presentation (siehe presentation.py).

Rendert die Gestaltung aus presentation_design.py:
- Anordnung: grid (wie das Verkaufsprogramm), carousel (blaettert Seiten),
  spotlight (neuestes Foto gross), marquee (Laufband aus Fotos)
- Hoch-/Querformat per Drehung (orientation), Kopfzeile mit Logo und Text,
  Karten mit Ecken/Schatten/Rahmen, Beschriftung unter oder auf dem Foto,
  Wasserzeichen (Logo oder copy.png), QR-Code mit Beschriftung, "NEW"-Marke,
  Laufband mit mehreren Botschaften, Touch: Foto antippen -> gross mit QR.

Offline: keine Schriften/Skripte von aussen. Im CRM laeuft dieselbe Seite als
Vorschau (?preview=1) und bekommt ihren Stand per postMessage. Sie liegt dort
unter public/presentation/index.html (scripts/presentation_seite_ins_crm.py).
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Liftpictures Presentation</title>
<style>
*{box-sizing:border-box}
html,body{margin:0;height:100%;overflow:hidden;background:#000;-webkit-font-smoothing:antialiased;user-select:none}
body.kiosk{cursor:none}
#stage{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);overflow:hidden;background:#3977BD;color:var(--lc);font-family:var(--font)}
#head{position:absolute;left:0;right:0;top:0;height:var(--hh);display:flex;align-items:center;gap:28px;padding:0 var(--pad);background:var(--hbg);color:var(--hc)}
#head img{height:calc(var(--hh) * .62);max-width:30%;object-fit:contain}
#head .t{display:flex;flex-direction:column;gap:4px;min-width:0}
#head .t small{font-size:calc(var(--hh) * .15);letter-spacing:.14em;text-transform:uppercase;opacity:.8}
#head .t b{font-size:calc(var(--hh) * .34);line-height:1.05;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#main{position:absolute;left:0;right:0;top:var(--top);bottom:var(--bottom);padding:var(--pad)}
.grid{display:grid;gap:var(--gap);width:100%;height:100%;grid-template-columns:repeat(var(--cols),minmax(0,1fr));grid-template-rows:repeat(var(--rows),minmax(0,1fr))}
.spot .card:first-child{grid-column:span 2;grid-row:span 2}
.page{position:absolute;inset:var(--pad);transition:opacity .8s ease,transform .8s ease}
.page.out{opacity:0;transform:scale(.985)}
.dots{position:absolute;left:0;right:0;bottom:calc(var(--pad) * .3);display:flex;justify-content:center;gap:8px}
.dots i{width:9px;height:9px;border-radius:50%;background:var(--lc);opacity:.3}
.dots i.on{opacity:.95;background:var(--accent)}
.card{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:0;min-height:0;border-radius:var(--radius);background:var(--cbg);padding:var(--cpad);animation:pop .6s ease both}
.card.shadow{box-shadow:0 10px 30px rgba(0,0,0,.35)}
@keyframes pop{from{opacity:0;transform:translateY(8px) scale(.98)}to{opacity:1;transform:none}}
.pic{flex:1;min-height:0;width:100%;display:flex;align-items:center;justify-content:center;container-type:size}
.frame{position:relative;width:min(100cqw,calc(100cqh * var(--ar,1.5)));height:min(100cqh,calc(100cqw / var(--ar,1.5)));overflow:hidden;border-radius:var(--iradius);border:var(--bw) solid var(--bc);background:rgba(0,0,0,.12)}
.frame img.photo{position:absolute;left:0;top:0;display:block;width:100%;height:100%;object-fit:cover}
.frame img.wm{position:absolute;left:50%;top:50%;width:var(--wms);transform:translate(-50%,-50%);opacity:var(--wmo);pointer-events:none}
.qr{position:absolute;width:var(--qrs);max-width:320px;background:#fff;border-radius:6px;padding:3% 3% 2%;box-shadow:0 4px 18px rgba(0,0,0,.35);text-align:center}
.qr svg{display:block;width:100%;height:auto}
.qr b{display:block;margin-top:2px;font-size:clamp(9px,1.2cqw,16px);letter-spacing:.08em;color:var(--qcc);white-space:nowrap}
.qr.br{right:3%;bottom:4%}.qr.bl{left:3%;bottom:4%}.qr.tr{right:3%;top:4%}.qr.tl{left:3%;top:4%}
.label{font-size:var(--ls);line-height:1.2;white-space:pre;margin-top:6px;color:var(--lc);font-variant-numeric:tabular-nums}
.label.overlay{position:absolute;left:0;right:0;bottom:0;margin:0;padding:28px 18px 12px;background:linear-gradient(transparent,rgba(0,0,0,.62));color:#fff;text-align:left}
.label.overlay.right{text-align:right}
.badge{position:absolute;left:3%;top:4%;padding:5px 14px;border-radius:999px;background:var(--accent);color:#111;font-weight:700;font-size:clamp(11px,1.4cqw,22px);letter-spacing:.08em;animation:pulse 2s ease-in-out infinite}
.badge.right{left:auto;right:3%}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(255,255,255,0)}50%{box-shadow:0 0 0 8px rgba(255,255,255,.2)}}
.marq{display:flex;flex-direction:column;gap:var(--gap);height:100%}
.mrow{flex:1;min-height:0;overflow:hidden}
.mtrack{display:flex;gap:var(--gap);height:100%;width:max-content;animation:mq var(--mqd,60s) linear infinite}
.mtrack.rev{animation-direction:reverse}
.mtrack .card{height:100%;width:var(--mw);flex:none;animation:none}
.paused .mtrack{animation-play-state:paused}
@keyframes mq{to{transform:translateX(-50%)}}
#ticker{position:absolute;left:0;right:0;height:var(--th);background:var(--tbg);overflow:hidden}
#ticker.bottom{bottom:0}#ticker.top{top:var(--hht)}
#ticker span{position:absolute;top:50%;left:100%;transform:translateY(-50%);white-space:nowrap;color:var(--tc);font-size:var(--ts);font-weight:600;line-height:1;will-change:left}
#empty,#notice{position:absolute;left:0;right:0;top:var(--top);bottom:var(--bottom);display:flex;align-items:center;justify-content:center;text-align:center;padding:60px;font-size:34px;line-height:1.45;color:var(--lc)}
#zoom{position:absolute;inset:0;background:rgba(0,0,0,.84);display:flex;align-items:center;justify-content:center;gap:4%;padding:4%;z-index:20}
#zoom .zp{position:relative;flex:1.6;height:100%;display:flex;align-items:center;justify-content:center;container-type:size}
#zoom .zp .frame{border:0}
#zoom .zq{flex:1;display:flex;flex-direction:column;align-items:center;gap:22px;color:#fff;text-align:center}
#zoom .zq .box{width:min(100%,46vh);background:#fff;padding:18px;border-radius:18px}
#zoom .zq .box svg{display:block;width:100%;height:auto}
#zoom .zq p{margin:0;font-size:30px;line-height:1.3}
#zoom .zq small{font-size:20px;opacity:.7}
#zoom .zq .num{font-size:26px;letter-spacing:.06em;opacity:.85}
[hidden]{display:none!important}
</style>
</head>
<body>
<div id="stage">
  <div id="head" hidden><img id="headLogo" alt="" hidden><div class="t"><small id="headSub"></small><b id="headTitle"></b></div></div>
  <div id="main"></div>
  <div id="empty" hidden></div>
  <div id="notice" hidden></div>
  <div id="ticker"><span id="tickerText"></span></div>
  <div id="zoom" hidden></div>
</div>
<script>
(function(){
  "use strict";
  var PAGE_REV="__PAGE_REV__", PREVIEW=/[?&]preview=1/.test(location.search);
  var stage=document.getElementById("stage"), main=document.getElementById("main"), head=document.getElementById("head");
  var ticker=document.getElementById("ticker"), tickerText=document.getElementById("tickerText");
  var emptyEl=document.getElementById("empty"), notice=document.getElementById("notice"), zoom=document.getElementById("zoom");
  var st=null, photos=[], sig="", lastState=null, pageIdx=0, pageTimer=null, zoomTimer=null, lastTouch=0;
  if(!PREVIEW)document.body.className="kiosk";

  var FONTS={segoe:'"Segoe UI","Segoe UI Variable Text",Arial,sans-serif',bahnschrift:'Bahnschrift,"Segoe UI",Arial,sans-serif',
    arial:'Arial,Helvetica,sans-serif',georgia:'Georgia,"Times New Roman",serif',trebuchet:'"Trebuchet MS",Arial,sans-serif'};
  function px(v){return v+"px"}

  // Drehung fuer Hochkant-Bildschirme: die Buehne bekommt die getauschten Masse.
  function layoutStage(){
    var rot=(st&&!PREVIEW)?st.orientation:0,w=window.innerWidth,h=window.innerHeight,side=(rot===90||rot===270);
    stage.style.width=px(side?h:w);stage.style.height=px(side?w:h);
    stage.style.transform="translate(-50%,-50%) rotate("+rot+"deg)";
  }
  window.addEventListener("resize",function(){layoutStage();if(st&&st.layout==="marquee")render()});

  function applyStyle(){
    var s=st,r=document.documentElement.style,hh=s.header?s.header_height:0,th=s.ticker?s.ticker_height:0;
    stage.style.background=s.background2?"linear-gradient(135deg,"+s.background+","+s.background2+")":s.background;
    var set=function(k,v){r.setProperty(k,v)};
    set("--font",FONTS[s.font]||FONTS.segoe);set("--lc",s.label_color);set("--ls",px(s.label_size));
    set("--gap",px(s.gap));set("--pad",px(s.padding));set("--cols",s.columns);set("--rows",s.rows);
    set("--radius",px(s.radius));set("--iradius",px(s.card_background?Math.max(0,s.radius-6):s.radius));
    set("--cbg",s.card_background||"transparent");set("--cpad",s.card_background?"8px":"0px");
    set("--bw",px(s.border_width));set("--bc",s.border_color);
    set("--wms",s.watermark_size+"%");set("--wmo",s.watermark_opacity/100);
    set("--qrs",s.qr_size+"%");set("--qcc",s.qr_caption_color);set("--accent",s.accent);
    set("--hh",px(hh));set("--hht",px(hh));set("--hbg",s.header_background||"transparent");set("--hc",s.header_color);
    set("--th",px(th));set("--tbg",s.ticker_background);set("--tc",s.ticker_color);set("--ts",px(s.ticker_size));
    set("--top",px(hh+(s.ticker&&s.ticker_position==="top"?th:0)));
    set("--bottom",px(s.ticker&&s.ticker_position==="bottom"?th:0));
    head.hidden=!s.header;
    document.getElementById("headTitle").textContent=s.header_title||"";
    document.getElementById("headSub").textContent=s.header_subtitle||"";
    var hl=document.getElementById("headLogo");
    if(s.logo){if(hl.getAttribute("src")!==s.logo)hl.src=s.logo;hl.hidden=false}else hl.hidden=true;
    ticker.hidden=!s.ticker;ticker.className=s.ticker_position==="top"?"top":"bottom";
    var msg=(s.ticker_messages||[]).join("        •        ");
    if(tickerText.textContent!==msg){tickerText.textContent=msg;tx=null}
    layoutStage();
  }

  function timeText(p){
    if(!p.ts)return p.time||"";
    var d=new Date(p.ts*1000),h=d.getHours(),m=("0"+d.getMinutes()).slice(-2);
    return st.time_format==="12h"?((h%12)||12)+":"+m+" "+(h<12?"AM":"PM"):("0"+h).slice(-2)+":"+m;
  }
  function labelText(p){
    var parts=[];if(st.show_number)parts.push(p.number);if(st.show_time)parts.push(timeText(p));
    return parts.join(st.label_mode==="overlay"?"   ·   ":"    ");
  }
  function isNew(p){return st.new_badge&&p.ts&&(Date.now()/1000-p.ts)<st.new_minutes*60}
  function wmSrc(){return st.watermark==="logo"?st.logo:st.watermark==="viewer"?st.viewer_logo:null}

  function frame(p,big){
    var f=document.createElement("div");f.className="frame";
    var img=document.createElement("img");img.className="photo";img.alt="";img.decoding="async";
    img.onload=function(){
      var W=img.naturalWidth,H=img.naturalHeight,cx=st.crop_x||0,cy=st.crop_y||0,w=W-2*cx,h=H-2*cy;
      if(w>0&&h>0){f.style.setProperty("--ar",w/h);
        if(cx||cy){img.style.width=(W/w*100)+"%";img.style.height=(H/h*100)+"%";img.style.left=(-cx/w*100)+"%";img.style.top=(-cy/h*100)+"%"}}
    };
    img.src=p.src;f.appendChild(img);
    var wm=wmSrc();if(wm){var w=document.createElement("img");w.className="wm";w.alt="";w.src=wm;f.appendChild(w)}
    if(!big){
      if(isNew(p)){var b=document.createElement("div");b.className="badge"+(st.qr_position==="tl"?" right":"");b.textContent=st.new_text||"NEW";f.appendChild(b)}
      var q=document.createElement("div");q.className="qr "+st.qr_position;q.innerHTML=p.qr||"";
      if(st.qr_caption){var c=document.createElement("b");c.textContent=st.qr_caption;q.appendChild(c)}
      f.appendChild(q);
      if(st.label_mode==="overlay"){var lo=document.createElement("div");lo.className="label overlay"+(st.qr_position==="bl"?" right":"");lo.textContent=labelText(p);if(lo.textContent)f.appendChild(lo)}
    }
    return f;
  }

  function card(p){
    var c=document.createElement("div");c.className="card"+(st.shadow?" shadow":"");
    var pic=document.createElement("div");pic.className="pic";pic.appendChild(frame(p,false));c.appendChild(pic);
    if(st.label_mode==="below"){var l=document.createElement("div");l.className="label";l.textContent=labelText(p);if(l.textContent)c.appendChild(l)}
    if(st.touch)c.addEventListener("click",function(e){e.stopPropagation();openZoom(p)});
    return c;
  }

  function ordered(){var l=photos.slice();if(st.order==="oldest")l.reverse();return l}
  function perPage(){return st.layout==="spotlight"?Math.max(1,Math.max(3,st.columns)*Math.max(2,st.rows)-3):st.columns*st.rows}

  function render(){
    clearInterval(pageTimer);pageTimer=null;main.textContent="";main.onclick=null;main.classList.remove("paused");
    var list=ordered();
    emptyEl.hidden=list.length>0||!st.empty_text;emptyEl.textContent=st.empty_text||"";
    if(!list.length)return;
    if(st.layout==="marquee"){renderMarquee(list);return}
    var per=perPage();
    if(st.layout==="carousel"&&list.length>per){
      var pages=[];for(var i=0;i<list.length;i+=per)pages.push(list.slice(i,i+per));
      if(pageIdx>=pages.length)pageIdx=0;
      var holder=document.createElement("div");holder.className="page";holder.appendChild(gridOf(pages[pageIdx],false));main.appendChild(holder);
      var dots=document.createElement("div");dots.className="dots";
      pages.forEach(function(_,k){var d=document.createElement("i");if(k===pageIdx)d.className="on";dots.appendChild(d)});main.appendChild(dots);
      pageTimer=setInterval(function(){
        if(Date.now()-lastTouch<st.touch_seconds*1000||!zoom.hidden)return;
        holder.classList.add("out");
        setTimeout(function(){pageIdx=(pageIdx+1)%pages.length;render()},800);
      },st.page_seconds*1000);
      return;
    }
    main.appendChild(gridOf(list.slice(0,per),st.layout==="spotlight"));
  }
  function gridOf(list,spot){
    var g=document.createElement("div");g.className="grid"+(spot?" spot":"");
    if(spot){g.style.gridTemplateColumns="repeat("+Math.max(3,st.columns)+",minmax(0,1fr))";g.style.gridTemplateRows="repeat("+Math.max(2,st.rows)+",minmax(0,1fr))"}
    list.forEach(function(p){g.appendChild(card(p))});
    return g;
  }
  function renderMarquee(list){
    var rows=Math.max(1,Math.min(st.rows,3)),wrap=document.createElement("div");wrap.className="marq";
    var avail=main.clientHeight-2*st.padding-(rows-1)*st.gap;
    var ph=avail/rows-(st.label_mode==="below"?st.label_size*1.4:0)-(st.card_background?16:0);
    document.documentElement.style.setProperty("--mw",px(Math.max(120,ph)*1.5+(st.card_background?16:0)));
    for(var r=0;r<rows;r++){
      var items=list.filter(function(_,i){return i%rows===r});if(!items.length)continue;
      var row=document.createElement("div");row.className="mrow";
      var track=document.createElement("div");track.className="mtrack"+(r%2?" rev":"");
      for(var k=0;k<2;k++)items.forEach(function(p){track.appendChild(card(p))});
      row.appendChild(track);wrap.appendChild(row);
      (function(t){requestAnimationFrame(function(){t.style.setProperty("--mqd",Math.max(8,t.scrollWidth/2/st.marquee_speed)+"s")})})(track);
    }
    main.appendChild(wrap);
    // Antippen haelt das Laufband an, damit man in Ruhe scannen kann.
    main.onclick=function(){main.classList.add("paused");lastTouch=Date.now();
      setTimeout(function(){if(Date.now()-lastTouch>=st.touch_seconds*1000-50)main.classList.remove("paused")},st.touch_seconds*1000)};
  }

  // Touch: Foto gross, mit grossem QR-Code; schliesst sich von selbst.
  function openZoom(p){
    lastTouch=Date.now();zoom.textContent="";
    var zp=document.createElement("div");zp.className="zp";zp.appendChild(frame(p,true));
    var zq=document.createElement("div");zq.className="zq";
    var box=document.createElement("div");box.className="box";box.innerHTML=p.qr||"";zq.appendChild(box);
    var t=document.createElement("p");t.textContent=st.touch_text;zq.appendChild(t);
    var n=document.createElement("div");n.className="num";n.textContent=labelText(p);zq.appendChild(n);
    var s=document.createElement("small");s.textContent="Tap anywhere to close";zq.appendChild(s);
    zoom.appendChild(zp);zoom.appendChild(zq);zoom.hidden=false;
    clearTimeout(zoomTimer);zoomTimer=setTimeout(closeZoom,st.touch_seconds*1000);
  }
  function closeZoom(){zoom.hidden=true;zoom.textContent="";clearTimeout(zoomTimer)}
  zoom.addEventListener("click",closeZoom);

  function apply(s,force){
    if(!s)return;
    if(!PREVIEW&&s.page_rev&&s.page_rev!==PAGE_REV){location.reload();return}
    lastState=s;
    var next=JSON.stringify([s.style,s.licensed,s.reason,(s.photos||[]).map(function(p){return p.key})]);
    if(next===sig&&!force)return;sig=next;
    st=s.style;photos=s.photos||[];
    applyStyle();
    if(!s.licensed){
      main.textContent="";emptyEl.hidden=true;notice.hidden=false;
      var why={expired:"The licence for this presentation has expired.",
               offline:"This PC has had no connection to Liftpictures for more than 7 days. Please connect it to the internet.",
               not_paired:"This PC is not connected to Liftpictures yet."}[s.reason]||"This presentation is not activated for this PC.";
      notice.textContent=why+" Please contact Liftpictures support: support@liftpictures.com";
      return;
    }
    notice.hidden=true;
    if(!zoom.hidden&&!PREVIEW)return; // waehrend der Grossansicht nicht umbauen
    render();
  }
  window.__presentation=function(s){apply(s,false)};
  // CRM-Vorschau: Stand per postMessage.
  window.addEventListener("message",function(e){var d=e.data;if(d&&d.type==="lp-presentation"&&d.state)apply(d.state,true)});
  // "NEW"-Marken laufen ab, auch ohne neues Foto.
  setInterval(function(){if(st&&st.new_badge&&st.layout!=="carousel"&&zoom.hidden)apply(lastState,true)},60000);

  // Laufband-Text
  var tx=null,last=0;
  function run(t){
    if(st&&st.ticker){
      var dt=last?Math.min(0.1,(t-last)/1000):0,w=ticker.clientWidth,tw=tickerText.offsetWidth;
      if(tx===null||tx< -tw)tx=w;
      tx-=dt*st.ticker_speed;tickerText.style.left=tx+"px";
    }
    last=t;requestAnimationFrame(run);
  }
  requestAnimationFrame(run);

  if(!PREVIEW){
    var current=null;
    var load=function(){
      var sc=document.createElement("script");sc.src="photos.js?t="+Date.now();
      sc.onload=sc.onerror=function(){if(current&&current!==sc&&current.parentNode)current.parentNode.removeChild(current);current=sc};
      document.head.appendChild(sc);
    };
    load();setInterval(load,2000);
  }else if(window.parent!==window){window.parent.postMessage({type:"lp-presentation-ready"},"*")}
  layoutStage();
})();
</script>
</body>
</html>
"""
