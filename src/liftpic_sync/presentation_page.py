"""Die Seite der Liftpictures Presentation (siehe presentation.py).

Nachbau von `SlideshowWindow` aus dem Verkaufsprogramm: Raster aus Spalten x
Reihen (neuestes Foto oben links), Abstand SplitBorder, unter jedem Foto
Bildnummer + vier Leerzeichen + Uhrzeit, Wasserzeichen in der Mitte, Laufband
unten. Neu ist nur der QR-Code mit dem echten Kauf-Link auf jedem Foto.
Alles offline: keine Schriften, keine Skripte von aussen.
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Liftpictures Presentation</title>
<style>
html,body{margin:0;height:100%;overflow:hidden;background:var(--bg,#3977BD);cursor:none;font-family:"Segoe UI","Segoe UI Variable Text",Arial,sans-serif;-webkit-font-smoothing:antialiased}
#grid{position:absolute;left:0;right:0;top:0;bottom:var(--th,40px);box-sizing:border-box;padding:var(--b,20px);display:grid;gap:var(--b,20px);
  grid-template-columns:repeat(var(--cols,3),minmax(0,1fr));grid-template-rows:repeat(var(--rows,2),minmax(0,1fr))}
.cell{display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:0;min-height:0}
.pic{flex:1;min-height:0;width:100%;display:flex;align-items:center;justify-content:center;container-type:size}
.frame{position:relative;width:min(100cqw,calc(100cqh * var(--ar,1.5)));height:min(100cqh,calc(100cqw / var(--ar,1.5)));overflow:hidden;background:rgba(0,0,0,.08)}
.frame img.photo{position:absolute;left:0;top:0;display:block;width:100%;height:100%;object-fit:cover}
.frame img.logo{position:absolute;left:50%;top:50%;width:33%;transform:translate(-50%,-50%);opacity:.75;pointer-events:none}
.qr{position:absolute;right:2.5%;bottom:3.5%;width:30%;max-width:240px;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.35)}
.qr svg{display:block;width:100%;height:auto}
.label{color:var(--lc,#fff);font-size:var(--ls,30px);line-height:1.25;white-space:pre;margin-top:6px;font-variant-numeric:tabular-nums}
#ticker{position:absolute;left:0;right:0;bottom:0;height:var(--th,40px);background:var(--tbg,#fff);overflow:hidden}
#ticker span{position:absolute;top:50%;left:100%;transform:translateY(-50%);white-space:nowrap;color:var(--tc,#000);font-size:var(--ts,40px);line-height:1;will-change:left}
#notice{position:absolute;inset:0 0 var(--th,40px) 0;display:flex;align-items:center;justify-content:center;text-align:center;color:#fff;font-size:28px;line-height:1.5;padding:40px}
[hidden]{display:none!important}
</style>
</head>
<body>
<div id="grid"></div>
<div id="notice" hidden></div>
<div id="ticker"><span id="tickerText"></span></div>
<script>
(function(){
  "use strict";
  var PAGE_REV="__PAGE_REV__", sig="", style=null, cells={};
  var grid=document.getElementById("grid"), notice=document.getElementById("notice");
  var ticker=document.getElementById("ticker"), tickerText=document.getElementById("tickerText");
  var root=document.documentElement.style;

  function setStyle(s){
    style=s;
    root.setProperty("--bg",s.background);
    root.setProperty("--cols",s.columns);
    root.setProperty("--rows",s.rows);
    root.setProperty("--b",s.border+"px");
    root.setProperty("--lc",s.label_color);
    root.setProperty("--ls",s.label_size+"px");
    root.setProperty("--th",(s.ticker?s.ticker_height:0)+"px");
    root.setProperty("--tbg",s.ticker_background);
    root.setProperty("--tc",s.ticker_color);
    root.setProperty("--ts",s.ticker_size+"px");
    ticker.hidden=!s.ticker;
    if(tickerText.textContent!==s.ticker_text)tickerText.textContent=s.ticker_text;
  }

  // Eine Kachel je Foto; vorhandene Kacheln werden wiederverwendet, damit
  // bei jedem neuen Foto nicht alle Bilder neu laden.
  function cell(p){
    var c=cells[p.key];
    if(c)return c;
    c=document.createElement("div");c.className="cell";
    var pic=document.createElement("div");pic.className="pic";
    var frame=document.createElement("div");frame.className="frame";
    var img=document.createElement("img");img.className="photo";img.alt="";img.decoding="async";
    img.onload=function(){
      // Zuschnitt wie Utils.CropImage: cx Pixel links/rechts, cy oben/unten weg.
      var W=img.naturalWidth,H=img.naturalHeight,cx=style.crop_x||0,cy=style.crop_y||0,w=W-2*cx,h=H-2*cy;
      if(w>0&&h>0){frame.style.setProperty("--ar",w/h);
        if(cx||cy){img.style.width=(W/w*100)+"%";img.style.height=(H/h*100)+"%";
          img.style.left=(-cx/w*100)+"%";img.style.top=(-cy/h*100)+"%";}}
    };
    img.src=p.src;
    frame.appendChild(img);
    if(style.preview_logo){var lg=document.createElement("img");lg.className="logo";lg.alt="";lg.src=style.preview_logo;frame.appendChild(lg)}
    var qr=document.createElement("div");qr.className="qr";qr.innerHTML=p.qr;frame.appendChild(qr);
    pic.appendChild(frame);c.appendChild(pic);
    var label=document.createElement("div");label.className="label";label.textContent=p.number+"    "+p.time;
    label.hidden=!style.show_label;c.appendChild(label);
    cells[p.key]=c;
    return c;
  }

  window.__presentation=function(s){
    if(s&&s.page_rev&&s.page_rev!==PAGE_REV){location.reload();return}
    var next=JSON.stringify([s.style,s.licensed,(s.photos||[]).map(function(p){return p.key})]);
    if(next===sig)return;
    var styleChanged=!style||JSON.stringify(style)!==JSON.stringify(s.style);
    sig=next;
    if(styleChanged){cells={};grid.textContent=""}
    setStyle(s.style);
    if(!s.licensed){
      grid.textContent="";cells={};
      notice.hidden=false;
      notice.textContent="This presentation is not activated for this PC. Please contact Liftpictures support.";
      return;
    }
    notice.hidden=true;
    var keep={},list=s.photos||[];
    list.forEach(function(p,i){var c=cell(p);keep[p.key]=1;if(grid.children[i]!==c)grid.insertBefore(c,grid.children[i]||null)});
    Object.keys(cells).forEach(function(k){if(!keep[k]){if(cells[k].parentNode)cells[k].parentNode.removeChild(cells[k]);delete cells[k]}});
  };

  // Laufband: von rechts herein, nach links hinaus, dann von vorn.
  var x=null,last=0;
  function run(t){
    if(style&&style.ticker){
      var dt=last?Math.min(0.1,(t-last)/1000):0,w=ticker.clientWidth,tw=tickerText.offsetWidth;
      if(x===null||x< -tw)x=w;
      x-=dt*style.ticker_speed*2;
      tickerText.style.left=x+"px";
    }
    last=t;requestAnimationFrame(run);
  }
  requestAnimationFrame(run);

  var current=null;
  function load(){
    var s=document.createElement("script");
    s.src="photos.js?t="+Date.now();
    s.onload=s.onerror=function(){if(current&&current!==s&&current.parentNode)current.parentNode.removeChild(current);current=s};
    document.head.appendChild(s);
  }
  load();setInterval(load,2000);
})();
</script>
</body>
</html>
"""
