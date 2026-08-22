"""Bargeld und Karte am Automaten: Bestand, Zahlungsart, Wechselgeld-Kontrolle.

Warum es das gibt
-----------------
Am Automaten kann bar oder mit Karte gezahlt werden, aber nirgends stand
bisher, WIE ein einzelnes Foto bezahlt wurde, wie viel Wechselgeld heraus kam
und wie viel Wechselgeld ueberhaupt noch im Geraet liegt.

Der teure Fall: ein defekter Muenzwechsler gab dauerhaft zu viel Wechselgeld
heraus. Weil niemand Einwurf und Auszahlung gegeneinander rechnete, fiel das
ueber lange Zeit nicht auf. Genau diese Rechnung macht `pruefe_verkauf`.

Die vier Quellen
----------------
Keine davon wurde fuer uns gebaut; alle sind Nebenprodukte fremder Programme.

``CoinStats.txt``
    Eine Zeile je Momentaufnahme::

        14.08.2026 12:00 1x0,05€+43x0,10€+64x0,20€+51x0,50€+18x1,00€+0x2,00€=60,65€

    Der **Bestand in den Roehren**, also das verfuegbare Wechselgeld - nicht die
    Einnahmen. Beleg dafuer: die Summe faellt zwischen zwei Aufnahmen
    (131,70 € -> 101,20 €), Einnahmen koennten nur wachsen. Geschrieben wird
    etwa zweimal taeglich, es ist also eine Momentaufnahme und kein Live-Wert.

``NRI.CoinCharger_MMJJJJ.txt``
    Je Ereignis eine Zeile::

        ==> message: (1,2,500) - (Bill validator: Accepted - 500)   <- 5,00 € rein
        try payout:  setpaymentmanager(1,0,500,0) => 500            <- 5,00 € raus
        try payout:  setpaymentmanager(1,0,50,0) => 0               <- konnte NICHT

    Die Zahl hinter ``=>`` ist, was tatsaechlich heraus kam. ``=> 0`` heisst:
    angefordert, aber nichts ausgezahlt - der Gast bekam zu wenig zurueck.

``ZvtLog_<zeitpunkt>.txt``
    Eine INI-Datei je Kartenzahlung, mit angefordertem Betrag, Ergebniscode und
    Belegnummer. Der Zeitpunkt steht im Dateinamen.

``Statistic.txt``
    Je Verkauf eine Zeile::

        14.03.2026 12:00:06::C:\\liftpic\\fotos\\out\\00003.jpg::3||1||0,00

    Zeitpunkt, Foto, dann Felder des Verkaufsprogramms. Das letzte Feld ist der
    Betrag. Was die beiden davor genau bedeuten, ist nicht dokumentiert; sie
    werden roh mitgefuehrt und nicht gedeutet.

Die Grenze dieser Auswertung
----------------------------
**Es gibt keine gemeinsame Vorgangsnummer.** Verkauf, Muenzereignis und
Kartenzahlung stehen in drei Dateien, die nichts voneinander wissen. Zugeordnet
wird deshalb ueber die Uhrzeit. Solange ein Gast nach dem anderen am Automaten
steht - der Normalfall - ist das zuverlaessig. Ueberlappen zwei Vorgaenge,
kann die Zuordnung danebengehen. Jeder Befund traegt daher `sicher`, und
Unsicheres wird als solches gemeldet statt als Tatsache.
"""
from __future__ import annotations

import bisect
import glob
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


# ------------------------------------------------------------------ Datentypen

@dataclass(frozen=True)
class Muenzbestand:
    """Was zum Zeitpunkt der Aufnahme an Wechselgeld im Geraet lag.

    Wichtig: das ist **keine Messung an der Hardware**, sondern die Buchfuehrung
    des Verkaufsprogramms, zweimal taeglich weggeschrieben. Steht der
    Muenzpruefer still, schreibt es weiter denselben Wert - am 15.08.2026 seit
    drei Tagen dieselben 60,65 €, waehrend im Geraet nachweislich nichts lag.
    Deshalb wird mitgeliefert, seit wann sich nichts mehr geruehrt hat.
    """
    gemessen_am: datetime | None
    # Sorte in Cent -> Anzahl, z. B. {10: 43, 20: 64}
    sorten: dict[int, int]
    summe_cent: int
    # Seit wann exakt dieselbe Aufteilung geschrieben wird. Gleich
    # `gemessen_am`, wenn sich der Wert zuletzt geaendert hat.
    unveraendert_seit: datetime | None = None

    @property
    def unveraendert_stunden(self) -> float | None:
        if self.gemessen_am is None or self.unveraendert_seit is None:
            return None
        return max(0.0, (self.gemessen_am - self.unveraendert_seit).total_seconds() / 3600.0)

    def as_dict(self) -> dict:
        return {
            "gemessen_am": self.gemessen_am.isoformat() if self.gemessen_am else None,
            "unveraendert_seit": (
                self.unveraendert_seit.isoformat() if self.unveraendert_seit else None
            ),
            "unveraendert_stunden": self.unveraendert_stunden,
            "sorten": [
                {"cent": cent, "anzahl": anzahl, "wert_cent": cent * anzahl}
                for cent, anzahl in sorted(self.sorten.items())
            ],
            "summe_cent": self.summe_cent,
        }


@dataclass(frozen=True)
class Muenzereignis:
    """Ein Einwurf oder eine Auszahlung."""
    zeit: datetime
    art: str            # "ein" | "aus"
    cent: int           # tatsaechlich bewegter Betrag
    angefordert: int    # bei "aus": was angefordert war (sonst gleich `cent`)

    @property
    def fehlgeschlagen(self) -> bool:
        return self.art == "aus" and self.cent < self.angefordert


@dataclass(frozen=True)
class Kartenzahlung:
    zeit: datetime
    cent: int
    erfolgreich: bool
    ergebnis: str
    belegnr: str
    # Ergebnis-Code war nicht "0", aber Kartennummer, Belegnummer und Betrag
    # sehen nach einer echten, gebuchten Zahlung aus (F-051). Steht dabei, weil
    # der Automat sich hier nicht zu 100 % sicher sein kann - der Mensch am
    # Kontoauszug schon.
    unsicher: bool = False


@dataclass(frozen=True)
class Verkauf:
    zeit: datetime
    foto: str
    cent: int
    rohfelder: tuple[str, ...] = ()
    # Die Bildnummer aus dem Dateinamen (00003.jpg -> 3).
    #
    # Der einzige belastbare Schluessel zwischen diesem Verkauf und dem Foto in
    # der Datenbank. Ueber die Uhrzeit ginge es nicht: der Aufnahmezeitpunkt
    # des Fotos ist nicht der Kaufzeitpunkt - dazwischen liegt, wie lange der
    # Gast am Bildschirm stand.
    bildnummer: int | None = None


@dataclass(frozen=True)
class Zahlungsbefund:
    """Wie ein einzelner Verkauf bezahlt wurde - und ob es aufgeht."""
    verkauf: Verkauf
    zahlungsart: str          # "bar" | "karte" | "unbekannt"
    eingeworfen_cent: int
    ausgezahlt_cent: int
    erwartetes_wechselgeld_cent: int
    # > 0: es kam MEHR heraus als es sollte. < 0: weniger.
    abweichung_cent: int
    sicher: bool
    hinweis: str = ""
    # Der tatsaechlich ermittelte Betrag - NICHT dasselbe wie `verkauf.cent`.
    #
    # `verkauf.cent` kommt aus Statistic.txt und fehlt dort in praktisch allen
    # Zeilen (1323 von 1332 an dieser Anlage). Bisher zeigte die Uebersicht
    # trotzdem `verkauf.cent` an - das Ergebnis war eine Umsatzseite, auf der
    # so gut wie jeder Kauf 0,00 EUR zeigte, obwohl `pruefe_verkauf` den Preis
    # laengst kannte: bei Karte aus dem Beleg, bei Bar aus "was passt zu einem
    # eingestellten Preis". Der Wert wurde berechnet und dann verworfen (F-051).
    betrag_ermittelt_cent: int = 0

    def as_dict(self) -> dict:
        return {
            "zeit": self.verkauf.zeit.isoformat(),
            "foto": self.verkauf.foto,
            "bildnummer": self.verkauf.bildnummer,
            "betrag_cent": self.betrag_ermittelt_cent,
            "zahlungsart": self.zahlungsart,
            "eingeworfen_cent": self.eingeworfen_cent,
            "ausgezahlt_cent": self.ausgezahlt_cent,
            "erwartetes_wechselgeld_cent": self.erwartetes_wechselgeld_cent,
            "abweichung_cent": self.abweichung_cent,
            "sicher": self.sicher,
            "hinweis": self.hinweis,
        }


# --------------------------------------------------------------------- Lesen

def _lies(pfad: Path) -> list[str]:
    """Zeilen lesen, ohne an einem Zeichen zu scheitern.

    Diese Dateien stammen aus verschiedenen Jahrzehnten und Programmen; manche
    sind UTF-8, manche cp1252. Ein falsches Euro-Zeichen darf die ganze
    Auswertung nicht kosten.
    """
    try:
        roh = pfad.read_bytes()
    except OSError:
        return []
    for kodierung in ("utf-8", "cp1252", "latin-1"):
        try:
            return roh.decode(kodierung).splitlines()
        except UnicodeDecodeError:
            continue
    return roh.decode("utf-8", errors="replace").splitlines()


_ZEIT = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?")


def _zeit(text: str) -> datetime | None:
    treffer = _ZEIT.search(text)
    if not treffer:
        return None
    tag, monat, jahr, stunde, minute, sekunde = treffer.groups()
    try:
        return datetime(int(jahr), int(monat), int(tag),
                        int(stunde), int(minute), int(sekunde or 0))
    except ValueError:
        return None


def _cent(text: str) -> int | None:
    """'0,50' oder '0.50' in Cent. Gibt None, wenn es keine Zahl ist."""
    sauber = text.strip().replace("€", "").replace("\u20ac", "").strip()
    sauber = sauber.replace(".", "").replace(",", ".") if "," in sauber else sauber
    try:
        return int(round(float(sauber) * 100))
    except ValueError:
        return None


# Ein Geldbetrag hat zwei Nachkommastellen. Ohne diese Bedingung wird aus dem
# Druckprofil "3" am Zeilenende ein Preis von 3,00 EUR - in den echten Daten
# betraf das 1322 von 1330 Zeilen, weil aeltere Eintraege gar keinen Betrag
# enthalten. Lieber kein Preis als ein erfundener.
_BETRAG = re.compile(r"^\s*\d+[.,]\d{2}\s*(?:€|€)?\s*$")

_SORTE = re.compile(r"(\d+)\s*x\s*(\d+[.,]\d{2})")


def _sortenaufteilung(zeile: str) -> dict[int, int]:
    """Welche Sorten in welcher Anzahl in dieser Zeile stehen."""
    sorten: dict[int, int] = {}
    for anzahl, wert in _SORTE.findall(zeile):
        cent = _cent(wert)
        if cent:
            sorten[cent] = sorten.get(cent, 0) + int(anzahl)
    return sorten


def lies_muenzbestand(pfad: Path) -> Muenzbestand | None:
    """Die letzte Momentaufnahme aus CoinStats.txt - und wie alt sie wirklich ist.

    Das Verkaufsprogramm schreibt die Aufteilung nach Plan weg, nicht weil sich
    etwas geaendert haette. Ein stillstehender Muenzpruefer erzeugt deshalb
    beliebig viele frische Zeitstempel mit immer demselben Inhalt. Wir laufen
    ruekwaerts, solange die Aufteilung gleich bleibt, und melden den Zeitpunkt
    der ersten dieser gleichen Zeilen mit.
    """
    zeilen = [z for z in _lies(pfad) if z.strip()]
    if not zeilen:
        return None

    letzte = zeilen[-1]
    sorten = _sortenaufteilung(letzte)

    summe = None
    if "=" in letzte:
        summe = _cent(letzte.rsplit("=", 1)[1])
    if summe is None:
        summe = sum(cent * anzahl for cent, anzahl in sorten.items())

    gemessen = _zeit(letzte)
    unveraendert = gemessen
    for vorherige in reversed(zeilen[:-1]):
        if _sortenaufteilung(vorherige) != sorten:
            break
        zeitpunkt = _zeit(vorherige)
        if zeitpunkt is not None:
            unveraendert = zeitpunkt

    return Muenzbestand(
        gemessen_am=gemessen, sorten=sorten, summe_cent=summe,
        unveraendert_seit=unveraendert,
    )


# Was am Muenzpruefer wirklich eine Stoerung ist - und was nur so aussieht.
#
# Nicht jede Zeile mit "Error" ist ein Defekt. Zwei Faelle sind voellig normal
# und duerfen niemals Alarm ausloesen:
#
#   * "Coin changer/validator reset" - das meldet das Geraet beim Hochfahren.
#     Es steht bei JEDEM Start des Verkaufsprogramms und beweist eher, dass der
#     Pruefer da ist und antwortet.
#   * "Payment unit disabled" - der Ruhezustand. Der Automat gibt den Pruefer
#     nur waehrend eines Kaufs frei und sperrt ihn danach sofort wieder; am
#     Geraet steht dann "gesperrt durch Automaten". So ist es gedacht.
#
# Eine erste Fassung stufte beides als Defekt ein und haette an einem voellig
# gesunden Automaten "Pruefer arbeitet nicht" angezeigt.
_MUENZ_FEHLER = re.compile(
    r"(coin jam|muenzstau|münzstau|sensor problem|"
    r"not found \(while running\)|coinchangererror)",
    re.IGNORECASE,
)
# Umgekehrt: was beweist, dass er arbeitet. "Ready" nach dem Freigeben, ein
# angenommenes Geldstueck, eine Auszahlung, oder eine Muenze in der Pruefung.
_MUENZ_BETRIEB = re.compile(
    r"(accepted\s*-\s*\d+|try payout:|status\s*-\s*ready|escrow\s*-)",
    re.IGNORECASE,
)


def muenzpruefer_arbeitet(muster: str) -> bool | None:
    """Arbeitet der Muenzpruefer, laut seinem eigenen Protokoll?

    `None` heisst "nicht feststellbar" - kein Protokoll, keine Aussage darin.
    Das ist ausdruecklich nicht dasselbe wie "arbeitet nicht".

    Gelesen wird von hinten: die juengste Aussage gewinnt. Ein Fehler von heute
    frueh zaehlt nicht mehr, wenn danach wieder Geld angenommen wurde.
    """
    if not muster:
        return None
    dateien = sorted(
        (p for p in map(Path, glob.glob(muster)) if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    if not dateien:
        return None

    for pfad in reversed(dateien[-3:]):
        for zeile in reversed(_lies(pfad)):
            if _MUENZ_BETRIEB.search(zeile):
                return True
            if _MUENZ_FEHLER.search(zeile):
                return False
    return None


_ANGENOMMEN = re.compile(r"Accepted\s*-\s*(\d+)", re.IGNORECASE)
_AUSZAHLUNG = re.compile(
    r"try payout:\s*setpaymentmanager\(\s*\d+\s*,\s*\d+\s*,\s*(\d+)\s*,\s*\d+\s*\)\s*=>\s*(-?\d+)",
    re.IGNORECASE,
)


def lies_muenzereignisse(muster: str, seit: datetime | None = None) -> list[Muenzereignis]:
    """Einwuerfe und Auszahlungen aus den NRI-Protokollen."""
    ereignisse: list[Muenzereignis] = []
    for treffer in sorted(glob.glob(muster)):
        pfad = Path(treffer)
        if not pfad.is_file():
            continue
        for zeile in _lies(pfad):
            zeit = _zeit(zeile)
            if zeit is None or (seit and zeit < seit):
                continue

            aus = _AUSZAHLUNG.search(zeile)
            if aus:
                ereignisse.append(Muenzereignis(
                    zeit=zeit, art="aus",
                    cent=max(0, int(aus.group(2))),
                    angefordert=int(aus.group(1)),
                ))
                continue

            ein = _ANGENOMMEN.search(zeile)
            if ein:
                betrag = int(ein.group(1))
                ereignisse.append(Muenzereignis(
                    zeit=zeit, art="ein", cent=betrag, angefordert=betrag,
                ))
    ereignisse.sort(key=lambda e: e.zeit)
    return ereignisse


_DATEINAME_ZEIT = re.compile(
    r"ZvtLog_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})", re.IGNORECASE
)

# Vorgaenge des Terminals, die kein Verkauf sind.
#
# Bewusst eng: "tagesabschluss erfolgt" statt nur "tagesabschluss", weil sonst
# der Wortteil "Kassenschnitt" in "F0h (240) Offener Kassenschnitt vorhanden"
# mitgetroffen haette - das ist die Warnung EINER ZAHLUNG, kein Tagesabschluss
# (F-051, im ersten Anlauf selbst uebersehen). "Offen" und "erfolgt" schliessen
# sich aus, aber nur, wenn man beide Woerter auch wirklich verlangt.
_VERWALTUNG = re.compile(
    r"tagesabschluss\s*(erfolgt|:)|kassenschnitt\s*erfolgt"
    r"|diagnose|abmeldung|anmeldung|initialisierung",
    re.IGNORECASE,
)

# Formulierungen, die eine ECHTE Ablehnung bedeuten - im Unterschied zu einem
# Hinweis, der neben einer trotzdem gebuchten Zahlung steht (F-051).
_ABGELEHNT = re.compile(
    r"abgelehnt|storniert|abgebrochen|nicht erm(ä|ae)chtigt|ung(ü|ue)ltige? karte"
    r"|kein netz|keine verbindung|timeout|karte entfernt",
    re.IGNORECASE,
)


def _wirkt_gebucht(werte: dict[str, str], cent: int, verwaltung: bool) -> bool:
    """Sieht diese Zahlung nach einer echten Buchung aus, auch wenn der
    Ergebnis-Code nicht "0" ist?

    Der Anlass (F-051): ein Testkauf ueber 0,02 EUR kam mit `Ergebnis=999`
    ("Offener Kassenschnitt vorhanden") zurueck - unsere bisherige Pruefung
    (`Ergebnis == "0"`) haette das als nicht erfolgreich verworfen. Der
    anschliessende Tagesabschluss desselben Terminals bestaetigte aber
    "3 Zahlungen, 0,05 EUR" fuer genau diesen Beleg-Bereich: das Geld WAR
    abgebucht, der Code beschreibt nur einen offenen Vorgang beim Kassieren,
    keine Ablehnung.
    
    Deshalb zaehlt eine Zahlung auch ohne `Ergebnis == "0"` als gebucht, wenn
    sie die Kennzeichen eines echten Belegs traegt - Kartennummer, Belegnummer,
    ein Betrag - UND der Text keine der bekannten Ablehnungs-Formulierungen
    enthaelt.
    """
    if verwaltung or cent <= 0:
        return False
    text = werte.get("fromzvt.ergebnistext", "")
    if _ABGELEHNT.search(text):
        return False
    pan = werte.get("fromzvt.pan", "").strip()
    try:
        beleg_ok = int(werte.get("fromzvt.belegnr", "0").strip() or "0") > 0
    except ValueError:
        beleg_ok = False
    return bool(pan) and beleg_ok


def lies_kartenzahlungen(muster: str, seit: datetime | None = None) -> list[Kartenzahlung]:
    """Eine Kartenzahlung je ZvtLog-Datei."""
    zahlungen: list[Kartenzahlung] = []
    for treffer in glob.glob(muster):
        pfad = Path(treffer)
        name = _DATEINAME_ZEIT.search(pfad.name)
        if not name:
            continue
        jahr, monat, tag, stunde, minute, sekunde = (int(x) for x in name.groups())
        try:
            zeit = datetime(jahr, monat, tag, stunde, minute, sekunde)
        except ValueError:
            continue
        if seit and zeit < seit:
            continue

        werte: dict[str, str] = {}
        abschnitt = ""
        for zeile in _lies(pfad):
            zeile = zeile.strip()
            if zeile.startswith("[") and zeile.endswith("]"):
                abschnitt = zeile.strip("[]").lower()
                continue
            if "=" in zeile:
                schluessel, _, wert = zeile.partition("=")
                werte[f"{abschnitt}.{schluessel.strip().lower()}"] = wert.strip()

        ergebnis = werte.get("fromzvt.ergebnis", "")
        text = werte.get("fromzvt.ergebnistext", "")
        # Zweites, verlaesslicheres Merkmal: das Terminal traegt den
        # Vorgangstyp selbst ein. "2" war in jeder beobachteten Datei ein
        # Tagesabschluss - zusaetzlich zur Wortsuche, nicht statt ihr, falls
        # ein anderes Terminal-Modell den Text anders formuliert.
        ist_tagesabschluss_funktion = werte.get("tozvt.funktion", "").strip() == "2"
        # Der Automat fordert den Betrag an; das Terminal meldet ihn zurueck.
        # Bei Abbruch steht dort 0 - dann zaehlt der angeforderte Betrag als
        # das, was versucht wurde.
        # Bei Abbruch steht in [FromZvt] haeufig "0", selbst wenn die Anfrage
        # in [ToZvt] einen echten Betrag nannte UND der Text einen belegten
        # Umsatz beschreibt (F-051: "EUR 0,02" im Klartext, FromZvt.Betrag=0).
        # Deshalb gilt die Antwort nur, wenn sie wirklich > 0 ist; sonst
        # zaehlt, was angefordert wurde.
        def _cent_aus(schluessel: str) -> int:
            roh = werte.get(schluessel, "").strip()
            try:
                return int(roh) if roh else 0
            except ValueError:
                return 0
        cent = _cent_aus("fromzvt.betrag")
        if cent <= 0:
            cent = _cent_aus("tozvt.betrag")

        # Ein Tagesabschluss oder Kassenschnitt meldet ebenfalls "Ergebnis=0",
        # ist aber KEIN Verkauf - er fasst nur den Tag zusammen. Ohne diese
        # Unterscheidung waeren in den echten Daten mehrere Abschluesse als
        # Kartenzahlungen gezaehlt worden, samt ihrer Tagessumme.
        verwaltung = ist_tagesabschluss_funktion or bool(_VERWALTUNG.search(text))
        ergebnis_ok = ergebnis.strip() == "0" and cent > 0 and not verwaltung
        gebucht = ergebnis_ok or _wirkt_gebucht(werte, cent, verwaltung)

        zahlungen.append(Kartenzahlung(
            zeit=zeit,
            cent=cent,
            erfolgreich=gebucht,
            ergebnis=text or ergebnis,
            belegnr=werte.get("fromzvt.belegnr", ""),
            unsicher=gebucht and not ergebnis_ok,
        ))
    zahlungen.sort(key=lambda z: z.zeit)
    return zahlungen


_BILDNUMMER = re.compile(r"(\d+)\s*\.\w+$")


def _bildnummer(foto: str) -> int | None:
    """Die Bildnummer aus dem Dateinamen, z. B. 00003.jpg -> 3.

    Nur bei den fortlaufenden Namen des Automaten sinnvoll. Ein anderer Name
    (etwa ein Zeitstempel) ergibt None statt einer erfundenen Nummer.
    """
    name = foto.replace("/", "\\").split("\\")[-1]
    treffer = _BILDNUMMER.search(name)
    if not treffer:
        return None
    ziffern = treffer.group(1)
    # Ein Zeitstempel als Dateiname ist keine Bildnummer.
    if len(ziffern) > 8:
        return None
    return int(ziffern)


def lies_verkaeufe(pfad: Path, seit: datetime | None = None) -> list[Verkauf]:
    """Verkaeufe aus Statistic.txt des Verkaufsprogramms."""
    verkaeufe: list[Verkauf] = []
    for zeile in _lies(pfad):
        if "::" not in zeile:
            continue
        teile = zeile.split("::")
        zeit = _zeit(teile[0])
        if zeit is None or (seit and zeit < seit):
            continue
        foto = teile[1].strip() if len(teile) > 1 else ""
        # Korrekturzeilen des Verkaufsprogramms sind keine Verkaeufe.
        if foto.startswith("<") and foto.endswith(">"):
            continue

        felder = tuple(teile[2].split("||")) if len(teile) > 2 else ()
        # Nur was wie ein Geldbetrag aussieht, ist einer. Aeltere Zeilen enden
        # mit dem Druckprofil ("::3") - das ist kein Preis.
        cent = None
        if felder and _BETRAG.match(felder[-1]):
            cent = _cent(felder[-1])
        verkaeufe.append(Verkauf(
            zeit=zeit, foto=foto, cent=cent or 0, rohfelder=felder,
            bildnummer=_bildnummer(foto),
        ))
    verkaeufe.sort(key=lambda v: v.zeit)
    return verkaeufe


# ----------------------------------------------------------------- Abgleich

# Wie weit vor dem Verkauf Geld eingeworfen worden sein darf, und wie lange
# danach das Wechselgeld herausfallen darf. Grosszuegig genug fuer einen Gast,
# der Muenze fuer Muenze einwirft, eng genug, um zwei Vorgaenge zu trennen.
FENSTER_VOR = timedelta(minutes=4)
FENSTER_NACH = timedelta(minutes=2)


def _im_fenster(
    eintraege: list, von: datetime, bis: datetime, zeiten: list | None = None,
) -> list:
    """Der Ausschnitt einer zeitsortierten Liste zwischen zwei Zeitpunkten.

    `zeiten` ist die bereits ausgelesene Liste der Zeitstempel. Sie einmal zu
    bauen und durchzureichen statt bei jedem Verkauf neu ist der eigentliche
    Gewinn - sonst kostet allein das Zusammenstellen wieder so viel wie die
    vollstaendige Suche.
    """
    if zeiten is None:
        zeiten = [e.zeit for e in eintraege]
    links = bisect.bisect_left(zeiten, von)
    rechts = bisect.bisect_right(zeiten, bis)
    return eintraege[links:rechts]


def _naechstes_ereignis_sek(zeit: datetime, sortierte_zeiten: list[datetime]) -> int | None:
    """Wie viele Sekunden bis zum naechsten Ereignis, egal in welche Richtung.

    Rein diagnostisch (F-050) - nicht Teil der eigentlichen Zuordnung.
    `pruefe_verkauf` schneidet sein Fenster bewusst an den Nachbarverkaeufen
    ab, damit nichts falsch zugeordnet wird. Diese Funktion schneidet NICHTS
    ab: sie beantwortet nur "war ueberhaupt irgendwo in der Naehe etwas?" -
    das ist der Unterschied zwischen "hier fehlt wirklich eine Zahlung" und
    "hier war eine, nur zu weit weg oder einem Nachbarverkauf zugeschlagen".
    """
    if not sortierte_zeiten:
        return None
    i = bisect.bisect_left(sortierte_zeiten, zeit)
    kandidaten = []
    if i < len(sortierte_zeiten):
        kandidaten.append(sortierte_zeiten[i])
    if i > 0:
        kandidaten.append(sortierte_zeiten[i - 1])
    if not kandidaten:
        return None
    naechstes = min(kandidaten, key=lambda z: abs((z - zeit).total_seconds()))
    return int(abs((naechstes - zeit).total_seconds()))


def _unbekannt_erklaeren(
    zeit: datetime,
    ein_zeiten: list[datetime],
    karten_zeiten: list[datetime],
    voriger_verkauf: datetime | None,
) -> str:
    """Warum sich ein Verkauf keiner Zahlung zuordnen liess - in Worten.

    Vorher stand hier immer nur "unbekannt", ohne Grund. Bei Imst betraf das
    92 % aller Verkaeufe (F-050) - eine Zahl, die niemand einordnen konnte,
    ohne die Rohdateien von Hand zu lesen. Diese Funktion liest sie stattdessen
    aus und nennt den wahrscheinlichsten Grund - eine Erklaerung, keine neue
    Zuordnung: an der Zahlungsart oder den gezaehlten Summen aendert das nichts.
    """
    muenz_abstand = _naechstes_ereignis_sek(zeit, ein_zeiten)
    karten_abstand = _naechstes_ereignis_sek(zeit, karten_zeiten)

    # Zwei Verkaeufe innerhalb weniger Sekunden sind fast immer ein einziger
    # Kauf mit mehreren Fotos (Kombi-Angebot): eine Muenze, zwei Zeilen in der
    # Statistik. Die zweite Zeile hat dann zu Recht kein eigenes Geldereignis.
    if voriger_verkauf is not None:
        abstand_vorheriger = (zeit - voriger_verkauf).total_seconds()
        if 0 <= abstand_vorheriger <= MEHRFACHKAUF_SEKUNDEN:
            return (
                f"{int(abstand_vorheriger)} Sek. nach dem vorherigen Kauf - "
                "vermutlich zusammen mit diesem bezahlt (mehrere Fotos, eine Zahlung)"
            )

    naeher = None
    if muenz_abstand is not None and (karten_abstand is None or muenz_abstand <= karten_abstand):
        naeher = ("Münzeinwurf", muenz_abstand)
    elif karten_abstand is not None:
        naeher = ("Kartenzahlung", karten_abstand)

    if naeher is None:
        return "Weder Münz- noch Kartenprotokoll verzeichnen hier etwas"

    art, abstand = naeher
    if abstand <= 60:
        return f"{art} {abstand} Sek. entfernt, aber einem Nachbarverkauf zugeordnet"
    if abstand < 3600:
        return f"Nächst gelegene {art} liegt {abstand // 60} Min. entfernt - zu weit für eine sichere Zuordnung"
    return f"Nächst gelegene {art} liegt {abstand // 3600} Std. entfernt"


# Zwei Verkaeufe binnen dieser Spanne gelten als derselbe Vorgang (mehrere
# Fotos, eine Zahlung) - nicht als zwei separate, von denen einer unbezahlt
# blieb. 90 Sekunden sind grosszuegig genug fuer "Foto ansehen, zweites dazu
# waehlen", aber zu knapp fuer zwei verschiedene Gaeste nacheinander.
MEHRFACHKAUF_SEKUNDEN = 90


def pruefe_verkauf(
    verkauf: Verkauf,
    muenzereignisse: list[Muenzereignis],
    kartenzahlungen: list[Kartenzahlung],
    naechster_verkauf: datetime | None = None,
    voriger_verkauf: datetime | None = None,
    moegliche_preise: list[int] | None = None,
    zeiten_muenzen: list[datetime] | None = None,
    zeiten_karten: list[datetime] | None = None,
    ein_zeiten_alle: list[datetime] | None = None,
    karten_zeiten_alle: list[datetime] | None = None,
) -> Zahlungsbefund:
    """Zahlungsart bestimmen und das Wechselgeld nachrechnen.

    Die Fenster werden an den Nachbarverkaeufen abgeschnitten: liegt ein
    anderer Verkauf dazwischen, gehoert das Geld wahrscheinlich zu jenem. Das
    ist der wichtigste Schutz gegen falsche Zuordnung.
    """
    von = verkauf.zeit - FENSTER_VOR
    bis = verkauf.zeit + FENSTER_NACH
    if voriger_verkauf:
        von = max(von, voriger_verkauf)
    if naechster_verkauf:
        bis = min(bis, naechster_verkauf)

    # Nur die Ereignisse im Zeitfenster ansehen statt jedes Mal alle. Die
    # Listen sind nach Zeit sortiert, deshalb genuegt eine Bereichssuche - sonst
    # waeren es bei 1330 Verkaeufen und 3689 Ereignissen Millionen Vergleiche
    # bei jedem Herzschlag.
    nahe = _im_fenster(muenzereignisse, von, bis, zeiten_muenzen)
    ausgabe_ab = verkauf.zeit - timedelta(seconds=30)

    eingeworfen = sum(
        e.cent for e in nahe
        if e.art == "ein" and von <= e.zeit <= verkauf.zeit
    )
    auszahlungen = [
        e for e in nahe if e.art == "aus" and ausgabe_ab <= e.zeit <= bis
    ]
    ausgezahlt = sum(e.cent for e in auszahlungen)
    fehl_auszahlung = any(e.fehlgeschlagen for e in auszahlungen)
    karte = next(
        (k for k in _im_fenster(kartenzahlungen, von, bis, zeiten_karten)
         if k.erfolgreich),
        None,
    )

    if karte is not None and eingeworfen == 0:
        hinweis = f"Beleg {karte.belegnr}" if karte.belegnr else ""
        if karte.unsicher:
            # Der Ergebnis-Code war nicht "0", die Zahlung sieht aber gebucht
            # aus - Kartennummer, Belegnummer und Betrag stimmen (F-051). Das
            # gehoert gesagt, damit jemand mit Kontoauszug gegenpruefen kann.
            zusatz = "Ergebniscode weicht ab, Zahlung wirkt aber gebucht"
            hinweis = f"{hinweis} - {zusatz}" if hinweis else zusatz
        return Zahlungsbefund(
            verkauf=verkauf, zahlungsart="karte",
            eingeworfen_cent=0, ausgezahlt_cent=0,
            erwartetes_wechselgeld_cent=0, abweichung_cent=0,
            sicher=not karte.unsicher,
            hinweis=hinweis,
            betrag_ermittelt_cent=karte.cent,
        )

    if eingeworfen == 0:
        # Weder Muenzen noch Karte im Fenster gefunden. Warum, steht jetzt im
        # Hinweis (F-050) - vorher stand hier nur "unbekannt", ohne Grund.
        #
        # Ohne vorbereitete Listen (Direktaufruf, etwa in Tests) werden sie
        # hier aus den ohnehin vorhandenen Rohlisten abgeleitet - teurer als
        # der vorbereitete Weg aus pruefe_alle, aber fuer einen einzelnen
        # Verkauf unerheblich.
        ein_zeiten = (
            ein_zeiten_alle if ein_zeiten_alle is not None
            else sorted(e.zeit for e in muenzereignisse if e.art == "ein")
        )
        karten_zeiten = (
            karten_zeiten_alle if karten_zeiten_alle is not None
            else sorted(k.zeit for k in kartenzahlungen if k.erfolgreich)
        )
        hinweis = _unbekannt_erklaeren(
            verkauf.zeit, ein_zeiten, karten_zeiten, voriger_verkauf,
        )
        if verkauf.cent != 0:
            hinweis = "Keine Zahlung zu diesem Verkauf gefunden - " + hinweis
        return Zahlungsbefund(
            verkauf=verkauf, zahlungsart="unbekannt",
            eingeworfen_cent=0, ausgezahlt_cent=ausgezahlt,
            erwartetes_wechselgeld_cent=0, abweichung_cent=0,
            sicher=verkauf.cent == 0,
            hinweis=hinweis,
        )

    # Der Preis steht selten in der Statistikdatei. Dann wird andersherum
    # gerechnet: was der Automat einbehalten hat, MUSS einer seiner
    # eingestellten Preise sein. Ist es keiner, stimmt etwas nicht - ohne dass
    # man wissen muss, welches Produkt der Gast gewaehlt hat.
    preis = verkauf.cent
    einbehalten = eingeworfen - ausgezahlt
    ueber_preisliste = False
    if preis == 0 and moegliche_preise:
        if einbehalten in moegliche_preise:
            preis = einbehalten          # passt zu einem Angebot: in Ordnung
        else:
            # Der einbehaltene Betrag ist mehrdeutig: 3,00 € koennen "Preis
            # 5,00 €, zwei Euro zu viel zurueck" heissen oder "Preis 1,00 €,
            # zwei Euro zu wenig". Bei gleichem Abstand faellt die Wahl auf den
            # hoeheren Preis, also auf die Lesart "es kam zu viel heraus" -
            # das ist der Fehler, der Geld kostet und der hier gesucht wird.
            # Lieber einmal zu viel hinsehen als den teuren Fall uebersehen.
            preis = min(
                moegliche_preise,
                key=lambda p: (abs(p - einbehalten), -p),
            )
        ueber_preisliste = True

    erwartet = max(0, eingeworfen - preis)
    abweichung = ausgezahlt - erwartet
    hinweis = ""
    if fehl_auszahlung:
        hinweis = "Auszahlung schlug fehl - vermutlich leere Röhre"
    elif abweichung > 0:
        hinweis = "Es kam mehr Wechselgeld heraus als vorgesehen"
    elif abweichung < 0:
        hinweis = "Es kam weniger Wechselgeld heraus als vorgesehen"
    if ueber_preisliste and abweichung != 0:
        hinweis += (
            f" (einbehalten {einbehalten / 100:.2f} € passt zu keinem "
            f"eingestellten Preis)"
        )

    # Ohne bekannten Preis laesst sich nichts nachrechnen - dann ist der Befund
    # eine Beobachtung, keine Pruefung.
    sicher = (verkauf.cent > 0 or ueber_preisliste) and karte is None

    return Zahlungsbefund(
        verkauf=verkauf, zahlungsart="bar",
        betrag_ermittelt_cent=preis,
        eingeworfen_cent=eingeworfen, ausgezahlt_cent=ausgezahlt,
        erwartetes_wechselgeld_cent=erwartet, abweichung_cent=abweichung,
        sicher=sicher, hinweis=hinweis,
    )


@dataclass(frozen=True)
class UnzugeordnetesEreignis:
    """Geld, das keinem einzigen Verkauf zugeordnet werden kann - nicht weil
    die Zahlungsart unklar ist, sondern weil in der Naehe gar kein Verkauf
    aus `Statistic.txt` steht, dem es gehoeren koennte.

    Der Anlass (F-051): am 19.08.2026 wurden 2,00 EUR und 0,20 EUR eingeworfen,
    aber wegen einer im selben Moment entnommenen Wechselgeldroehre nicht
    ausgezahlt. Weil danach kein Verkauf folgte, tauchte der Vorgang in keiner
    Auswertung auf - das Geld war da, aber fuer uns unsichtbar. `pruefe_alle`
    geht die Verkaeufe durch und fragt "wie wurde bezahlt"; das hier geht die
    EREIGNISSE durch und fragt die Gegenfrage: "gehoert das ueberhaupt zu
    etwas?"
    """
    zeit: datetime
    art: str          # "muenze_ein" | "muenze_aus_fehlgeschlagen" | "karte"
    cent: int
    hinweis: str

    def as_dict(self) -> dict:
        return {
            "zeit": self.zeit.isoformat(), "art": self.art,
            "cent": self.cent, "hinweis": self.hinweis,
        }


def finde_unzugeordnete_ereignisse(
    verkaeufe: list[Verkauf],
    muenzereignisse: list[Muenzereignis],
    kartenzahlungen: list[Kartenzahlung],
) -> list[UnzugeordnetesEreignis]:
    """Geldbewegungen, die zu keinem Verkauf in der Naehe gehoeren."""
    fenster: list[tuple[datetime, datetime]] = []
    for i, v in enumerate(verkaeufe):
        von = v.zeit - FENSTER_VOR
        bis = v.zeit + FENSTER_NACH
        if i > 0:
            von = max(von, verkaeufe[i - 1].zeit)
        if i + 1 < len(verkaeufe):
            bis = min(bis, verkaeufe[i + 1].zeit)
        fenster.append((von, bis))
    fenster.sort()

    def _gehoert_zu_verkauf(zeit: datetime) -> bool:
        # Eine einfache Schleife statt bisect: die Fenster ueberlappen sich
        # nicht, aber sie sind auch nicht luecken- oder ueberschneidungsfrei
        # sortierbar genug, um sich auf eine einzelne bisect-Grenze zu
        # verlassen. Bei der ueblichen Anzahl Ereignisse pro Herzschlag faellt
        # das nicht auf.
        return any(von <= zeit <= bis for von, bis in fenster)

    ereignisse: list[UnzugeordnetesEreignis] = []
    for e in muenzereignisse:
        if _gehoert_zu_verkauf(e.zeit):
            continue
        if e.art == "ein":
            ereignisse.append(UnzugeordnetesEreignis(
                zeit=e.zeit, art="muenze_ein", cent=e.cent,
                hinweis="Münze angenommen, aber kein Verkauf in der Nähe",
            ))
        elif e.fehlgeschlagen:
            ereignisse.append(UnzugeordnetesEreignis(
                zeit=e.zeit, art="muenze_aus_fehlgeschlagen", cent=e.angefordert,
                hinweis="Auszahlung angefordert, aber fehlgeschlagen - und keinem Verkauf zuzuordnen",
            ))
    for k in kartenzahlungen:
        if not k.erfolgreich or _gehoert_zu_verkauf(k.zeit):
            continue
        beleg = f" (Beleg {k.belegnr})" if k.belegnr else ""
        ereignisse.append(UnzugeordnetesEreignis(
            zeit=k.zeit, art="karte", cent=k.cent,
            hinweis=f"Kartenzahlung gebucht, aber kein Verkauf in der Nähe{beleg}",
        ))
    ereignisse.sort(key=lambda e: e.zeit, reverse=True)
    return ereignisse


def pruefe_alle(
    verkaeufe: list[Verkauf],
    muenzereignisse: list[Muenzereignis],
    kartenzahlungen: list[Kartenzahlung],
    moegliche_preise: list[int] | None = None,
) -> list[Zahlungsbefund]:
    # Einmal fuer alle Verkaeufe, nicht einmal je Verkauf.
    zeiten_muenzen = [e.zeit for e in muenzereignisse]
    zeiten_karten = [k.zeit for k in kartenzahlungen]
    # Fuer die Diagnose bei "unbekannt": nur erfolgreiche Einwuerfe/Zahlungen,
    # sortiert, ohne das Fenster der eigentlichen Pruefung.
    ein_zeiten_alle = sorted(e.zeit for e in muenzereignisse if e.art == "ein")
    karten_zeiten_alle = sorted(k.zeit for k in kartenzahlungen if k.erfolgreich)

    befunde: list[Zahlungsbefund] = []
    for i, verkauf in enumerate(verkaeufe):
        befunde.append(pruefe_verkauf(
            verkauf, muenzereignisse, kartenzahlungen,
            voriger_verkauf=verkaeufe[i - 1].zeit if i > 0 else None,
            naechster_verkauf=verkaeufe[i + 1].zeit if i + 1 < len(verkaeufe) else None,
            moegliche_preise=moegliche_preise,
            zeiten_muenzen=zeiten_muenzen,
            zeiten_karten=zeiten_karten,
            ein_zeiten_alle=ein_zeiten_alle,
            karten_zeiten_alle=karten_zeiten_alle,
        ))
    return befunde


# ------------------------------------------------------------ Zusammenfassung

@dataclass
class Zahlungsuebersicht:
    bar_anzahl: int = 0
    bar_cent: int = 0
    karte_anzahl: int = 0
    karte_cent: int = 0
    unbekannt_anzahl: int = 0
    auffaellig: list[Zahlungsbefund] = field(default_factory=list)
    # Die letzten Kaeufe einzeln, damit man je Foto sehen kann, wie bezahlt
    # wurde und wie viel Wechselgeld heraus kam. Bewusst begrenzt: die Liste
    # reist im Heartbeat mit und soll ihn nicht aufblaehen.
    letzte: list[Zahlungsbefund] = field(default_factory=list)
    # Geld, das zu keinem Verkauf gehoert (F-051) - siehe
    # finde_unzugeordnete_ereignisse. Ebenfalls begrenzt.
    unzugeordnet: list[UnzugeordnetesEreignis] = field(default_factory=list)

    @property
    def gesamt_anzahl(self) -> int:
        return self.bar_anzahl + self.karte_anzahl + self.unbekannt_anzahl

    # Ab welchem Anteil erkannter Zahlungen eine Aufteilung ueberhaupt etwas
    # aussagt. Darunter waere sie eine Hochrechnung aus einer Handvoll Faelle.
    ANTEIL_AB_ERKANNT = 0.5

    def as_dict(self) -> dict:
        erkannt = self.bar_anzahl + self.karte_anzahl
        gesamt = erkannt + self.unbekannt_anzahl

        # Die Aufteilung nur nennen, wenn der groessere Teil auch erkannt wurde
        # (F-037).
        #
        # Sie wurde vorher ueber die ERKANNTEN Zahlungen gerechnet. Bei Imst
        # sind das 49 von 951 - die restlichen 902 lassen sich keiner Zahlungsart
        # zuordnen, weil es dort kein Kartenprotokoll gibt und die Muenzereignisse
        # nicht bis zu jedem Verkauf zurueckreichen. Herausgekommen waere
        # "100 % bar", obwohl bei 95 Prozent der Verkaeufe niemand weiss, wie
        # gezahlt wurde. Lieber keine Aufteilung als eine erfundene.
        aussagekraeftig = gesamt > 0 and (erkannt / gesamt) >= self.ANTEIL_AB_ERKANNT

        return {
            "bar_anzahl": self.bar_anzahl,
            "bar_cent": self.bar_cent,
            "karte_anzahl": self.karte_anzahl,
            "karte_cent": self.karte_cent,
            "unbekannt_anzahl": self.unbekannt_anzahl,
            "erkannt_anteil": round(erkannt / gesamt, 3) if gesamt else None,
            "bar_anteil": round(self.bar_anzahl / erkannt, 3) if aussagekraeftig else None,
            "karte_anteil": round(self.karte_anzahl / erkannt, 3) if aussagekraeftig else None,
            "auffaellig": [b.as_dict() for b in self.auffaellig],
            "letzte": [b.as_dict() for b in self.letzte],
            "unzugeordnet": [e.as_dict() for e in self.unzugeordnet],
        }


def bestandswarnungen(bestand: Muenzbestand, ab_anzahl: int) -> list[dict]:
    """Welche Muenzsorten leer oder knapp sind.

    Eine leere Roehre heisst nicht "kein Umsatz", sondern: der naechste Gast
    bekommt zu wenig Wechselgeld heraus. Das ist der Moment, in dem jemand
    nachfuellen muss - und den sieht heute niemand.
    """
    warnungen: list[dict] = []
    for cent, anzahl in sorted(bestand.sorten.items()):
        if anzahl == 0:
            warnungen.append({
                "cent": cent, "anzahl": 0, "stufe": "leer",
                "text": f"{cent / 100:.2f} € ist leer",
            })
        elif anzahl < ab_anzahl:
            warnungen.append({
                "cent": cent, "anzahl": anzahl, "stufe": "knapp",
                "text": f"{cent / 100:.2f} € wird knapp ({anzahl} Stück)",
            })
    return warnungen


def read_payments(settings) -> dict:
    """Alles zum Thema Geld in einem Rutsch, fertig für den Heartbeat.

    Jede Quelle ist einzeln optional. Fehlt eine, entfaellt ihr Teil - es wird
    nichts geschaetzt und nichts ersetzt.
    """
    from datetime import timedelta as _td

    seit = datetime.now() - _td(days=max(1, settings.payment_days))
    ergebnis: dict = {}

    if settings.coin_stats_file:
        bestand = lies_muenzbestand(settings.coin_stats_file)
        if bestand:
            eintrag = bestand.as_dict()

            # Ob man dem Wert glauben darf. Das Verkaufsprogramm schreibt seine
            # Buchfuehrung nach Plan weg, auch wenn der Muenzpruefer stillsteht -
            # dann sieht ein toter Wert taggenau frisch aus. Am 15.08.2026 waren
            # es 60,65 €, seit 37 Stunden unveraendert, bei einem Pruefer, der
            # bei jedem Start einen Fehler meldete; im Geraet lag nichts.
            arbeitet = muenzpruefer_arbeitet(settings.coin_log_glob)
            eintrag["pruefer_arbeitet"] = arbeitet
            grund = None
            if arbeitet is False:
                grund = (
                    "Der Münzprüfer meldet einen Fehler und arbeitet nicht. "
                    "Der Betrag stammt aus der Buchführung des Verkaufsprogramms, "
                    "nicht aus dem Gerät - er kann längst überholt sein."
                )
            elif (bestand.unveraendert_stunden or 0) >= 24:
                grund = (
                    f"Seit {int(bestand.unveraendert_stunden or 0)} Stunden "
                    "unverändert. Entweder wurde nichts eingeworfen, oder der "
                    "Münzprüfer meldet nichts mehr."
                )
            eintrag["verlaesslich"] = grund is None
            eintrag["hinweis"] = grund

            ergebnis["coin_inventory"] = eintrag
            ergebnis["coin_warnings"] = bestandswarnungen(
                bestand, settings.coin_low_count,
            )

    muenzen = (
        lies_muenzereignisse(settings.coin_log_glob, seit)
        if settings.coin_log_glob else []
    )
    karten = (
        lies_kartenzahlungen(settings.card_log_glob, seit)
        if settings.card_log_glob else []
    )
    verkaeufe = (
        lies_verkaeufe(settings.statistic_file, seit)
        if settings.statistic_file else []
    )

    if muenzen:
        fehl = [e for e in muenzen if e.fehlgeschlagen]
        ergebnis["coin_payout_failures"] = [
            {
                "zeit": e.zeit.isoformat(),
                "angefordert_cent": e.angefordert,
                "ausgezahlt_cent": e.cent,
            }
            for e in fehl[-20:]
        ]

    if verkaeufe:
        from .viewer_settings import read_viewer_prices
        preise = read_viewer_prices(settings.viewer_settings_xml)
        uebersicht = fasse_zusammen(
            pruefe_alle(verkaeufe, muenzen, karten, moegliche_preise=preise)
        )
        # Geld ohne Verkauf in der Naehe (F-051) - unabhaengig von den
        # einzelnen Verkaufs-Befunden, deshalb ein eigener Durchlauf.
        uebersicht.unzugeordnet = finde_unzugeordnete_ereignisse(
            verkaeufe, muenzen, karten,
        )[:20]
        ergebnis["payments"] = uebersicht.as_dict()
        ergebnis["payments_days"] = settings.payment_days
        ergebnis["prices_cent"] = preise

    return ergebnis


def fasse_zusammen(befunde: list[Zahlungsbefund]) -> Zahlungsuebersicht:
    uebersicht = Zahlungsuebersicht()
    for befund in befunde:
        if befund.zahlungsart == "bar":
            uebersicht.bar_anzahl += 1
            uebersicht.bar_cent += befund.betrag_ermittelt_cent
        elif befund.zahlungsart == "karte":
            uebersicht.karte_anzahl += 1
            uebersicht.karte_cent += befund.betrag_ermittelt_cent
        else:
            uebersicht.unbekannt_anzahl += 1
        # Nur nachgerechnete Faelle koennen auffaellig sein. Eine Abweichung bei
        # unbekanntem Preis waere geraten, und ein falscher Alarm kostet mehr
        # Vertrauen als ein spaet entdeckter echter.
        if befund.sicher and befund.abweichung_cent != 0:
            uebersicht.auffaellig.append(befund)

    # Neueste zuerst, aber Kaeufe MIT erkannter Zahlungsart zuerst. Sonst fuellt
    # sich die Liste mit Eintraegen, zu denen es gar keine Zahlungsdaten gibt -
    # etwa aus einer Zeit, in der nur die Verkaufsliste mitlief. Der Betreiber
    # sucht hier "wie wurde bezahlt", nicht "welche Zeile steht ganz oben".
    uebersicht.letzte = sorted(
        befunde,
        key=lambda b: (b.zahlungsart != "unbekannt", b.verkauf.zeit),
        reverse=True,
    )[:50]
    return uebersicht
