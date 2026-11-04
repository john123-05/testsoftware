"""Gestaltung der Liftpictures Presentation: Vorlagen und erlaubte Werte.

Das CRM schickt eine Gestaltung als JSON (`presentation_design`). Hier wird
sie gegen eine feste Liste geprueft - jeder Wert hat Typ, Grenzen oder eine
Auswahl. Was nicht passt, faellt auf die Vorlage zurueck. So kann eine
falsche Eingabe im CRM den Bildschirm nie kaputt machen.

Reihenfolge: Grundwerte aus der Settings.xml des Verkaufsprogramms ("classic",
sieht aus wie das Original) -> gewaehlte Vorlage -> einzelne Werte aus dem CRM.

Groessen sind Pixel bei 1920x1080 (bzw. 1080x1920 hochkant).
Richtwerte aus der Signage-Praxis: Text ab ~24 px fuer 2-3 m Abstand, kurze
Botschaften im Laufband, Tippflaechen ab ~44 px, QR-Code-Kante etwa 1/10
des Scanabstands (bei 1080p: 30 % Kartenbreite ~ 5 cm -> ~50 cm Abstand;
im Touch-Vollbild deutlich groesser).
"""
from __future__ import annotations

import json
import re

FARBE = re.compile(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?")

# Schluessel -> (Art, Vorgabe, Grenzen/Auswahl)
FELDER: dict[str, tuple] = {
    "preset": ("wahl", "classic", ("classic", "signature", "midnight", "clean")),
    "orientation": ("wahl", 0, (0, 90, 180, 270)),
    "layout": ("wahl", "grid", ("grid", "carousel", "spotlight", "marquee")),
    "columns": ("zahl", 3, (1, 6)),
    "rows": ("zahl", 2, (1, 6)),
    "order": ("wahl", "newest", ("newest", "oldest")),
    "page_seconds": ("zahl", 10, (3, 120)),
    "max_photos": ("zahl", 24, (1, 60)),
    "marquee_speed": ("zahl", 60, (10, 400)),
    "background": ("farbe", "#3977BD", None),
    "background2": ("farbe_leer", "", None),
    "font": ("wahl", "segoe", ("segoe", "bahnschrift", "arial", "georgia", "trebuchet")),
    "gap": ("zahl", 20, (0, 80)),
    "padding": ("zahl", 20, (0, 160)),
    "radius": ("zahl", 0, (0, 48)),
    "border_width": ("zahl", 0, (0, 12)),
    "border_color": ("farbe", "#FFFFFF", None),
    "shadow": ("ja", False, None),
    "card_background": ("farbe_leer", "", None),
    "label_mode": ("wahl", "below", ("below", "overlay", "none")),
    "show_number": ("ja", True, None),
    "show_time": ("ja", True, None),
    "time_format": ("wahl", "24h", ("24h", "12h")),
    "label_size": ("zahl", 30, (10, 90)),
    "label_color": ("farbe", "#FFFFFF", None),
    "watermark": ("wahl", "viewer", ("viewer", "logo", "none")),
    "watermark_opacity": ("zahl", 75, (0, 100)),
    "watermark_size": ("zahl", 33, (10, 80)),
    "logo_url": ("url", "", None),
    "header": ("ja", False, None),
    "header_title": ("text", "", 90),
    "header_subtitle": ("text", "", 90),
    "header_height": ("zahl", 110, (50, 260)),
    "header_background": ("farbe_leer", "", None),
    "header_color": ("farbe", "#FFFFFF", None),
    "qr_size": ("zahl", 30, (15, 60)),
    "qr_position": ("wahl", "br", ("br", "bl", "tr", "tl")),
    "qr_caption": ("text", "", 40),
    "qr_caption_color": ("farbe", "#002858", None),
    "new_badge": ("ja", False, None),
    "new_minutes": ("zahl", 10, (1, 240)),
    "new_text": ("text", "NEW", 16),
    "accent": ("farbe", "#FFBE3D", None),
    "ticker": ("ja", True, None),
    "ticker_messages": ("liste", ["Scan your photo..!"], (8, 140)),
    "ticker_speed": ("zahl", 100, (10, 600)),
    "ticker_background": ("farbe", "#FFFFFF", None),
    "ticker_color": ("farbe", "#000000", None),
    "ticker_size": ("zahl", 40, (12, 120)),
    "ticker_height": ("zahl", 40, (20, 200)),
    "ticker_position": ("wahl", "bottom", ("bottom", "top")),
    "touch": ("ja", False, None),
    "touch_seconds": ("zahl", 30, (5, 180)),
    "touch_text": ("text", "Scan with your phone camera to buy this photo", 120),
    "empty_text": ("text", "", 120),
}

VORLAGEN: dict[str, dict] = {
    # Wie das Verkaufsprogramm - die Werte kommen aus seiner Settings.xml.
    "classic": {},
    # Markenauftritt: dunkler Grund, Akzentfarbe, Kopfzeile, Logo statt (c).
    "signature": {
        "background": "#002858", "background2": "#00407F", "font": "bahnschrift",
        "gap": 22, "padding": 28, "radius": 16, "shadow": True, "card_background": "#0B3A6E",
        "label_mode": "overlay", "label_size": 24, "label_color": "#FFFFFF", "time_format": "12h",
        "watermark": "logo", "watermark_opacity": 40, "watermark_size": 24,
        "header": True, "header_height": 110, "header_background": "", "header_color": "#FFFFFF",
        "qr_size": 32, "qr_caption": "SCAN TO BUY", "qr_caption_color": "#002858",
        "new_badge": True, "accent": "#FFBE3D",
        "ticker": True, "ticker_background": "#FFBE3D", "ticker_color": "#002858",
        "ticker_size": 28, "ticker_height": 52, "ticker_speed": 110,
        "touch": True,
    },
    "midnight": {
        "background": "#0B0F14", "background2": "#16202C", "font": "segoe",
        "gap": 20, "padding": 28, "radius": 14, "shadow": True, "card_background": "#141B24",
        "label_mode": "overlay", "label_size": 22, "label_color": "#E8EEF5",
        "watermark": "logo", "watermark_opacity": 32, "watermark_size": 24,
        "header": True, "header_color": "#E8EEF5", "qr_caption": "SCAN TO BUY", "qr_caption_color": "#0B0F14",
        "new_badge": True, "accent": "#4EA8FF",
        "ticker": True, "ticker_background": "#141B24", "ticker_color": "#E8EEF5",
        "ticker_size": 26, "ticker_height": 50, "touch": True,
    },
    "clean": {
        "background": "#F4F6F8", "background2": "", "font": "segoe",
        "gap": 24, "padding": 32, "radius": 12, "shadow": True, "card_background": "#FFFFFF",
        "label_mode": "below", "label_size": 22, "label_color": "#1F2933",
        "watermark": "logo", "watermark_opacity": 35, "watermark_size": 24,
        "header": True, "header_color": "#1F2933", "qr_caption": "SCAN TO BUY", "qr_caption_color": "#1F2933",
        "new_badge": True, "accent": "#C2410C", "border_width": 0,
        "ticker": True, "ticker_background": "#1F2933", "ticker_color": "#FFFFFF",
        "ticker_size": 26, "ticker_height": 50, "touch": True,
    },
}


def _wert(art: str, vorgabe, grenzen, roh):
    """Einen Wert pruefen; None heisst: nicht uebernehmen."""
    if art == "zahl":
        if isinstance(roh, bool) or not isinstance(roh, (int, float)):
            return None
        return int(max(grenzen[0], min(grenzen[1], roh)))
    if art == "wahl":
        return roh if roh in grenzen else None
    if art == "ja":
        return roh if isinstance(roh, bool) else None
    if art == "farbe":
        return roh.upper() if isinstance(roh, str) and FARBE.fullmatch(roh) else None
    if art == "farbe_leer":
        if roh == "":
            return ""
        return roh.upper() if isinstance(roh, str) and FARBE.fullmatch(roh) else None
    if art == "text":
        if not isinstance(roh, str):
            return None
        return re.sub(r"[\x00-\x1f]", " ", roh).strip()[:grenzen]
    if art == "url":
        if roh == "":
            return ""
        return roh if isinstance(roh, str) and roh.startswith("https://") and len(roh) <= 400 else None
    if art == "liste":
        anzahl, laenge = grenzen
        if not isinstance(roh, list):
            return None
        out = [re.sub(r"[\x00-\x1f]", " ", str(x)).strip()[:laenge] for x in roh if isinstance(x, str)]
        return [x for x in out if x][:anzahl]
    return None


def lies_design(roh: str | dict | None) -> dict:
    """JSON aus der Fernkonfiguration -> dict (leer bei Unsinn)."""
    if isinstance(roh, dict):
        return roh
    if not roh:
        return {}
    try:
        wert = json.loads(roh)
    except ValueError:
        return {}
    return wert if isinstance(wert, dict) else {}


def classic_aus_settings(s: dict) -> dict:
    """Grundwerte aus den Split-Werten des Verkaufsprogramms (stil())."""
    return {
        "background": s["background"].upper(),
        "columns": s["columns"], "rows": s["rows"],
        "gap": s["border"], "padding": s["border"],
        "label_mode": "below" if s["show_label"] else "none",
        "label_size": s["label_size"], "label_color": s["label_color"].upper(),
        "ticker": s["ticker"], "ticker_messages": [s["ticker_text"]],
        "ticker_color": s["ticker_color"].upper(), "ticker_background": s["ticker_background"].upper(),
        "ticker_size": s["ticker_size"], "ticker_height": s["ticker_height"],
        "ticker_speed": s["ticker_speed"] * 2,
    }


# Was ein Zeitplan vom Standard-Design erbt, wenn er es nicht selbst setzt.
ERBT = ("logo_url", "header_title", "header_subtitle", "ticker_messages", "qr_caption",
        "touch_text", "empty_text", "time_format", "orientation")
ZEIT = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def aktiver_plan(design: dict, jetzt=None) -> tuple[dict, str | None]:
    """Das Design, das gerade gilt: ein passender Zeitplan oder der Standard.

    `schedule` ist eine Liste aus {"name", "from": "HH:MM", "to": "HH:MM",
    "days": [0..6] (Mo=0, leer = jeden Tag), "design": {...}}. Ueber Mitternacht
    geht (from 22:00, to 06:00). Der erste passende Eintrag gewinnt.
    Rueckgabe: (Design, Name des Zeitplans oder None).
    """
    from datetime import datetime
    plaene = design.get("schedule")
    if not isinstance(plaene, list):
        return design, None
    jetzt = jetzt or datetime.now()
    uhr = jetzt.strftime("%H:%M")
    for plan in plaene[:6]:
        if not isinstance(plan, dict) or not isinstance(plan.get("design"), dict):
            continue
        von, bis = str(plan.get("from", "")), str(plan.get("to", ""))
        if not (ZEIT.fullmatch(von) and ZEIT.fullmatch(bis)):
            continue
        tage = plan.get("days")
        tag = jetzt.weekday()
        if von <= bis:
            drin = von <= uhr < bis
        else:  # ueber Mitternacht: der Morgen gehoert noch zum Vortag
            drin = uhr >= von or uhr < bis
            if uhr < bis:
                tag = (tag - 1) % 7
        if isinstance(tage, list) and tage and tag not in tage:
            drin = False
        if drin:
            eigenes = dict(plan["design"])
            for k in ERBT:
                if k not in eigenes and k in design:
                    eigenes[k] = design[k]
            return eigenes, str(plan.get("name") or "")[:40] or "schedule"
    return design, None


def gestaltung(viewer_stil: dict, design: dict | None, jetzt=None) -> dict:
    """Fertige Gestaltung fuer die Seite (mit Zeitplan)."""
    design, plan = aktiver_plan(design or {}, jetzt)
    ergebnis = {k: v[1] for k, v in FELDER.items()}
    ergebnis.update(classic_aus_settings(viewer_stil))
    vorlage = design.get("preset") if design.get("preset") in VORLAGEN else "classic"
    ergebnis.update(VORLAGEN[vorlage])
    for schluessel, roh in design.items():
        if schluessel not in FELDER:
            continue
        art, vorgabe, grenzen = FELDER[schluessel]
        wert = _wert(art, vorgabe, grenzen, roh)
        if wert is not None:
            ergebnis[schluessel] = wert
    ergebnis["preset"] = vorlage
    ergebnis["schedule_active"] = plan
    ergebnis["crop_x"] = viewer_stil.get("crop_x", 0)
    ergebnis["crop_y"] = viewer_stil.get("crop_y", 0)
    if not ergebnis["ticker_messages"]:
        ergebnis["ticker"] = False
    return ergebnis


def fotos_benoetigt(g: dict) -> int:
    """Wie viele Fotos die Seite braucht."""
    if g["layout"] in ("carousel", "marquee"):
        return g["max_photos"]
    if g["layout"] == "spotlight":
        return max(1, g["columns"] * g["rows"] - 3)
    return g["columns"] * g["rows"]
