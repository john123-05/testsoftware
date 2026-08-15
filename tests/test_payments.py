"""Bargeld, Karte und die Wechselgeld-Kontrolle.

Der wichtigste Test hier ist `test_erkennt_zu_viel_wechselgeld`: genau dieser
Fall ist am Automaten schon einmal passiert - ein defekter Wechsler gab immer
mehr heraus, als er sollte, und niemand bemerkte es.
"""
from datetime import datetime
from pathlib import Path

from liftpic_sync.payments import (
    Muenzereignis, Verkauf, fasse_zusammen, lies_kartenzahlungen,
    lies_muenzbestand, lies_muenzereignisse, lies_verkaeufe,
    muenzpruefer_arbeitet, pruefe_alle, pruefe_verkauf,
)


def z(text: str) -> datetime:
    return datetime.strptime(text, "%d.%m.%Y %H:%M:%S")


# ------------------------------------------------------------------- Lesen

def test_muenzbestand_wird_gelesen(tmp_path: Path):
    datei = tmp_path / "CoinStats.txt"
    datei.write_text(
        "13.08.2026 23:00 1x0,05€+43x0,10€+64x0,20€+51x0,50€+18x1,00€+0x2,00€=60,65€\n"
        "14.08.2026 12:00 1x0,05€+40x0,10€+64x0,20€+51x0,50€+18x1,00€+0x2,00€=60,35€\n",
        encoding="utf-8",
    )

    bestand = lies_muenzbestand(datei)

    # Immer die neueste Aufnahme.
    assert bestand.gemessen_am == datetime(2026, 8, 14, 12, 0)
    assert bestand.sorten[10] == 40
    assert bestand.sorten[200] == 0
    assert bestand.summe_cent == 6035
    # Die Summe der Datei und die eigene Rechnung muessen uebereinstimmen.
    assert sum(c * a for c, a in bestand.sorten.items()) == bestand.summe_cent


def test_stillstehender_bestand_wird_als_solcher_erkannt(tmp_path: Path):
    """Ein frischer Zeitstempel heisst nicht, dass frisch gezaehlt wurde.

    Das Verkaufsprogramm schreibt seine Buchfuehrung zweimal taeglich weg, auch
    wenn sich nichts geruehrt hat. Am 15.08.2026 standen dieselben 60,65 € seit
    dem 13.08. um 23:00 - der letzte Eintrag sah trotzdem taggenau aktuell aus,
    waehrend im Geraet nachweislich keine Muenzen lagen.
    """
    datei = tmp_path / "CoinStats.txt"
    datei.write_text(
        "12.08.2026 23:00 1x0,05€+50x0,10€=5,05€\n"
        "13.08.2026 23:00 1x0,05€+43x0,10€+64x0,20€+51x0,50€+18x1,00€+0x2,00€=60,65€\n"
        "14.08.2026 12:00 1x0,05€+43x0,10€+64x0,20€+51x0,50€+18x1,00€+0x2,00€=60,65€\n"
        "14.08.2026 23:00 1x0,05€+43x0,10€+64x0,20€+51x0,50€+18x1,00€+0x2,00€=60,65€\n"
        "15.08.2026 12:00 1x0,05€+43x0,10€+64x0,20€+51x0,50€+18x1,00€+0x2,00€=60,65€\n",
        encoding="utf-8",
    )

    bestand = lies_muenzbestand(datei)

    assert bestand.gemessen_am == datetime(2026, 8, 15, 12, 0)
    # Bis zur letzten Aenderung zurueck, nicht bis zum Dateianfang.
    assert bestand.unveraendert_seit == datetime(2026, 8, 13, 23, 0)
    assert bestand.unveraendert_stunden == 37.0


def test_frisch_geaenderter_bestand_gilt_nicht_als_stillstand(tmp_path: Path):
    datei = tmp_path / "CoinStats.txt"
    datei.write_text(
        "14.08.2026 23:00 1x0,05€+43x0,10€=4,35€\n"
        "15.08.2026 12:00 1x0,05€+40x0,10€=4,05€\n",
        encoding="utf-8",
    )

    bestand = lies_muenzbestand(datei)

    assert bestand.unveraendert_seit == bestand.gemessen_am
    assert bestand.unveraendert_stunden == 0.0


def test_start_und_ruhezustand_sind_kein_defekt(tmp_path: Path):
    """Die zwei "Error"-Zeilen, die voellig normal sind.

    Wortgleich aus NRI.CoinCharger_082026.txt. "reset" meldet das Geraet beim
    Hochfahren - es steht bei jedem Start und beweist eher, dass der Pruefer
    antwortet. "Payment unit disabled" ist der Ruhezustand: der Automat gibt
    den Pruefer nur waehrend eines Kaufs frei, am Geraet steht dann "gesperrt
    durch Automaten".

    Eine erste Fassung wertete beides als Defekt und haette an einem gesunden
    Automaten "Pruefer arbeitet nicht" angezeigt.
    """
    (tmp_path / "NRI.CoinCharger_082026.txt").write_text(
        "15.08.2026 12:14:52  openpaymentmanagerex(10000) => 0 (OK)\n"
        "15.08.2026 12:14:59  startpaymentmanager(xx,0,0,0) => 1 (Coin changer/validator)\n"
        "15.08.2026 12:14:59  ==> message: (4,1,1) - "
        "(Coin changer/validator: Error - Coin changer/validator reset)\n"
        "15.08.2026 12:15:02  ==> message: (4,1,11) - "
        "(Coin changer/validator: Error - Payment unit disabled)\n",
        encoding="utf-8",
    )

    # Keine Aussage - aber ausdruecklich kein Defekt.
    assert muenzpruefer_arbeitet(str(tmp_path / "NRI.CoinCharger_*.txt")) is not False


def test_muenzstau_ist_ein_defekt(tmp_path: Path):
    """Ein Muenzstau dagegen schon - da steckt etwas fest."""
    (tmp_path / "NRI.CoinCharger_082026.txt").write_text(
        "15.08.2026 17:03:43  ==> message: (3,1,0) - (Coin changer/validator: Escrow - 0)\n"
        "15.08.2026 17:03:44  ==> message: (4,1,13) - (Coin changer/validator: Error - Coin jam)\n",
        encoding="utf-8",
    )

    assert muenzpruefer_arbeitet(str(tmp_path / "NRI.CoinCharger_*.txt")) is False


def test_ready_nach_dem_stau_zaehlt_wieder(tmp_path: Path):
    """Die juengste Aussage gewinnt - genau wie bei der Kamera."""
    (tmp_path / "NRI.CoinCharger_082026.txt").write_text(
        "15.08.2026 17:03:44  ==> message: (4,1,13) - (Coin changer/validator: Error - Coin jam)\n"
        "15.08.2026 17:03:47  ==> message: (0,1,1) - (Coin changer/validator: Status - Ready)\n",
        encoding="utf-8",
    )

    assert muenzpruefer_arbeitet(str(tmp_path / "NRI.CoinCharger_*.txt")) is True


def test_angenommenes_geld_schlaegt_einen_alten_fehler(tmp_path: Path):
    """Die juengste Aussage gewinnt - sonst bliebe der Pruefer ewig defekt."""
    (tmp_path / "NRI.CoinCharger_082026.txt").write_text(
        "15.08.2026 09:00:00  ==> message: (4,1,1) - "
        "(Coin changer/validator: Error - Coin changer/validator reset)\n"
        "15.08.2026 10:00:00  ==> message: Accepted - 100\n",
        encoding="utf-8",
    )

    assert muenzpruefer_arbeitet(str(tmp_path / "NRI.CoinCharger_*.txt")) is True


def test_ohne_muenzprotokoll_wird_nichts_behauptet(tmp_path: Path):
    """Kein Protokoll heisst "unbekannt", nicht "defekt"."""
    assert muenzpruefer_arbeitet(str(tmp_path / "gibtesnicht_*.txt")) is None
    assert muenzpruefer_arbeitet("") is None


def test_muenzbestand_auch_in_alter_kodierung(tmp_path: Path):
    """Diese Dateien sind teils cp1252 - daran darf nichts scheitern."""
    datei = tmp_path / "CoinStats.txt"
    datei.write_bytes(
        "14.08.2026 12:00 2x0,50€+1x1,00€=2,00€\n".encode("cp1252")
    )
    bestand = lies_muenzbestand(datei)
    assert bestand.summe_cent == 200
    assert bestand.sorten[50] == 2


def test_muenzereignisse_einwurf_und_auszahlung(tmp_path: Path):
    datei = tmp_path / "NRI.CoinCharger_082026.txt"
    datei.write_text(
        "01.09.2025 10:41:46  ==> message: (1,2,500) - (Bill validator: Accepted - 500)\n"
        "01.09.2025 10:41:50  ==> message: (1,1,200) - (Coin changer/validator: Accepted - 200)\n"
        "01.09.2025 10:42:01  try payout:  setpaymentmanager(1,0,100,0) => 100\n"
        "01.09.2025 10:42:03  try payout:  setpaymentmanager(1,0,50,0) => 0\n"
        "01.09.2025 10:42:05  disable all:  setpaymentmanager(0,1,0,0) => 0 (OK)\n",
        encoding="utf-8",
    )

    ereignisse = lies_muenzereignisse(str(datei))

    assert [(e.art, e.cent) for e in ereignisse] == [
        ("ein", 500), ("ein", 200), ("aus", 100), ("aus", 0),
    ]
    # "disable all: ... => 0" ist KEINE Auszahlung, sondern eine Abschaltung.
    assert len(ereignisse) == 4
    # Angefordert 50, heraus kam 0: fehlgeschlagen.
    assert ereignisse[3].fehlgeschlagen is True
    assert ereignisse[2].fehlgeschlagen is False


def test_kartenzahlung_wird_gelesen(tmp_path: Path):
    (tmp_path / "ZvtLog_2026-07-19_19-15-59-749.txt").write_text(
        "[ToZvt]\nBetrag=500\nFunktion=0\n"
        "[FromZvt]\nErgebnis=0\nErgebnisText=Zahlung erfolgt\nBetrag=500\n"
        "BelegNr=0042\nKartentyp=5\n",
        encoding="utf-8",
    )
    (tmp_path / "ZvtLog_2026-07-19_19-12-19-719.txt").write_text(
        "[ToZvt]\nBetrag=500\n"
        "[FromZvt]\nErgebnis=108\nErgebnisText=Abbruch durch Timeout\nBetrag=0\n"
        "BelegNr=0\n",
        encoding="utf-8",
    )

    zahlungen = lies_kartenzahlungen(str(tmp_path / "ZvtLog_*.txt"))

    assert len(zahlungen) == 2
    # Nach Zeit sortiert, der Abbruch war frueher.
    assert zahlungen[0].erfolgreich is False
    assert zahlungen[1].erfolgreich is True
    assert zahlungen[1].cent == 500
    assert zahlungen[1].belegnr == "0042"
    assert zahlungen[1].zeit == datetime(2026, 7, 19, 19, 15, 59)


def test_verkaeufe_werden_gelesen(tmp_path: Path):
    datei = tmp_path / "Statistic.txt"
    datei.write_text(
        "14.03.2026 12:00:06::C:\\liftpic\\fotos\\out\\00003.jpg::3||1||5,00\n"
        "16.03.2026 07:31:54::<decrease count>::3||0||0,00\n"
        "14.03.2026 13:38:58::C:\\liftpic\\fotos\\out\\00019.jpg::3||2||0,00\n",
        encoding="utf-8",
    )

    verkaeufe = lies_verkaeufe(datei)

    # Die Korrekturzeile ist kein Verkauf.
    assert len(verkaeufe) == 2
    assert verkaeufe[0].cent == 500
    assert verkaeufe[0].foto.endswith("00003.jpg")
    assert verkaeufe[1].cent == 0


def test_tagesabschluss_ist_keine_kartenzahlung(tmp_path: Path):
    """An den echten Daten aufgefallen.

    Ein Kassenschnitt meldet ebenfalls "Ergebnis=0" und traegt die Tagessumme
    als Betrag. Als Zahlung gezaehlt, erfindet er Umsatz, den es nicht gab.
    """
    (tmp_path / "ZvtLog_2024-01-12_14-11-37-000.txt").write_text(
        "[ToZvt]\nBetrag=0\n"
        "[FromZvt]\nErgebnis=0\nErgebnisText=Tagesabschluss erfolgt\nBetrag=35\n",
        encoding="utf-8",
    )
    (tmp_path / "ZvtLog_2024-01-12_14-40-11-000.txt").write_text(
        "[ToZvt]\nBetrag=30\n"
        "[FromZvt]\nErgebnis=0\nErgebnisText=Zahlung erfolgt\nBetrag=30\nBelegNr=7\n",
        encoding="utf-8",
    )

    zahlungen = lies_kartenzahlungen(str(tmp_path / "ZvtLog_*.txt"))
    erfolgreiche = [z for z in zahlungen if z.erfolgreich]

    assert len(erfolgreiche) == 1
    assert erfolgreiche[0].belegnr == "7"


def test_nullbetrag_ist_keine_zahlung(tmp_path: Path):
    (tmp_path / "ZvtLog_2026-07-19_19-12-19-000.txt").write_text(
        "[ToZvt]\nBetrag=0\n[FromZvt]\nErgebnis=0\nErgebnisText=0\nBetrag=0\n",
        encoding="utf-8",
    )
    zahlungen = lies_kartenzahlungen(str(tmp_path / "ZvtLog_*.txt"))
    assert zahlungen[0].erfolgreich is False


def test_bildnummer_wird_aus_dem_dateinamen_gelesen(tmp_path: Path):
    """Der Schluessel, ueber den ein Verkauf zum Foto in der Datenbank findet.

    Ueber die Uhrzeit ginge es nicht: der Aufnahmezeitpunkt des Fotos ist nicht
    der Kaufzeitpunkt - dazwischen liegt, wie lange der Gast am Bildschirm
    stand.
    """
    datei = tmp_path / "Statistic.txt"
    datei.write_text(
        "14.03.2026 12:00:06::C:\\liftpic\\fotos\\out\\00003.jpg::3||1||5,00\n"
        "14.03.2026 12:10:06::C:\\liftpic\\fotos\\out\\00150.jpg::3||1||5,00\n"
        "05.05.2026 08:47:27::C:\\liftpic\\fotos\\1632145419516010.jpg::3||2||0,00\n",
        encoding="utf-8",
    )

    verkaeufe = lies_verkaeufe(datei)

    assert verkaeufe[0].bildnummer == 3
    assert verkaeufe[1].bildnummer == 150
    # Ein Zeitstempel als Dateiname ist keine Bildnummer - lieber nichts als
    # eine erfundene Zahl, mit der spaeter falsch zugeordnet wird.
    assert verkaeufe[2].bildnummer is None


def test_druckprofil_wird_nicht_als_preis_gelesen(tmp_path: Path):
    """An den echten Daten aufgefallen.

    Aeltere Zeilen enden mit dem Druckprofil statt mit einem Betrag. Aus "::3"
    wurde ein Preis von 3,00 EUR - und damit 1322 erfundene Umsaetze.
    """
    datei = tmp_path / "Statistic.txt"
    datei.write_text(
        "28.02.2026 15:33:59::C:\\liftpic\\fotos\\out\\00152.jpg::3\n"
        "11.03.2026 11:36:04::C:\\liftpic\\fotos\\out\\00053.jpg::1||1||0,00\n"
        "14.03.2026 12:00:06::C:\\liftpic\\fotos\\out\\00003.jpg::3||1||5,00\n",
        encoding="utf-8",
    )

    verkaeufe = lies_verkaeufe(datei)

    assert [v.cent for v in verkaeufe] == [0, 0, 500]


# -------------------------------------------------------------- Nachrechnen

def test_erkennt_zu_viel_wechselgeld():
    """Der Fall, der schon einmal Geld gekostet hat.

    Gast wirft 10,00 € ein, Foto kostet 5,00 €. Zurueck muessten 5,00 € kommen.
    Der defekte Wechsler zahlt 7,00 € aus - 2,00 € zu viel, bei jedem Verkauf.
    """
    verkauf = Verkauf(zeit=z("14.08.2026 12:00:00"), foto="00003.jpg", cent=500)
    muenzen = [
        Muenzereignis(z("14.08.2026 11:59:40"), "ein", 1000, 1000),
        Muenzereignis(z("14.08.2026 12:00:10"), "aus", 500, 500),
        Muenzereignis(z("14.08.2026 12:00:12"), "aus", 200, 200),
    ]

    befund = pruefe_verkauf(verkauf, muenzen, [])

    assert befund.zahlungsart == "bar"
    assert befund.eingeworfen_cent == 1000
    assert befund.erwartetes_wechselgeld_cent == 500
    assert befund.ausgezahlt_cent == 700
    assert befund.abweichung_cent == 200      # 2,00 € zu viel
    assert befund.sicher is True
    assert "mehr Wechselgeld" in befund.hinweis

    # Und es taucht in der Zusammenfassung als auffaellig auf.
    uebersicht = fasse_zusammen([befund])
    assert len(uebersicht.auffaellig) == 1


def test_korrektes_wechselgeld_ist_unauffaellig():
    verkauf = Verkauf(zeit=z("14.08.2026 12:00:00"), foto="a.jpg", cent=500)
    muenzen = [
        Muenzereignis(z("14.08.2026 11:59:40"), "ein", 1000, 1000),
        Muenzereignis(z("14.08.2026 12:00:10"), "aus", 500, 500),
    ]

    befund = pruefe_verkauf(verkauf, muenzen, [])

    assert befund.abweichung_cent == 0
    assert befund.hinweis == ""
    assert fasse_zusammen([befund]).auffaellig == []


def test_erkennt_zu_wenig_wechselgeld_bei_leerer_roehre():
    """Angefordert, aber nichts ausgezahlt: der Gast wurde benachteiligt."""
    verkauf = Verkauf(zeit=z("14.08.2026 12:00:00"), foto="a.jpg", cent=500)
    muenzen = [
        Muenzereignis(z("14.08.2026 11:59:40"), "ein", 1000, 1000),
        Muenzereignis(z("14.08.2026 12:00:10"), "aus", 0, 500),
    ]

    befund = pruefe_verkauf(verkauf, muenzen, [])

    assert befund.abweichung_cent == -500
    assert "leere" in befund.hinweis.lower()


def test_kartenzahlung_wird_als_solche_erkannt():
    from liftpic_sync.payments import Kartenzahlung

    verkauf = Verkauf(zeit=z("14.08.2026 12:00:00"), foto="a.jpg", cent=500)
    karte = [Kartenzahlung(z("14.08.2026 11:59:50"), 500, True, "OK", "0042")]

    befund = pruefe_verkauf(verkauf, [], karte)

    assert befund.zahlungsart == "karte"
    assert befund.eingeworfen_cent == 0
    assert befund.abweichung_cent == 0
    assert "0042" in befund.hinweis


def test_abgebrochene_kartenzahlung_zaehlt_nicht():
    from liftpic_sync.payments import Kartenzahlung

    verkauf = Verkauf(zeit=z("14.08.2026 12:00:00"), foto="a.jpg", cent=500)
    karte = [Kartenzahlung(z("14.08.2026 11:59:50"), 0, False, "Abbruch", "0")]

    befund = pruefe_verkauf(verkauf, [], karte)

    assert befund.zahlungsart != "karte"


def test_nachbarverkauf_schneidet_das_fenster_ab():
    """Der wichtigste Schutz gegen falsche Zuordnung.

    Ohne diese Grenze wuerde das Geld des naechsten Gastes dem vorigen Verkauf
    zugerechnet - und daraus entstuende ein Fehlalarm ueber zu viel Wechselgeld.
    """
    erster = Verkauf(zeit=z("14.08.2026 12:00:00"), foto="a.jpg", cent=500)
    zweiter = Verkauf(zeit=z("14.08.2026 12:01:00"), foto="b.jpg", cent=500)
    muenzen = [
        Muenzereignis(z("14.08.2026 11:59:40"), "ein", 500, 500),   # zum ersten
        Muenzereignis(z("14.08.2026 12:00:50"), "ein", 500, 500),   # zum zweiten
    ]

    befunde = pruefe_alle([erster, zweiter], muenzen, [])

    assert befunde[0].eingeworfen_cent == 500
    assert befunde[1].eingeworfen_cent == 500
    assert all(b.abweichung_cent == 0 for b in befunde)


def test_gratis_betrieb_erzeugt_keinen_alarm():
    """Ohne Preis und ohne Zahlung ist nichts nachzurechnen.

    Der Testrechner laeuft im Gratis-Betrieb. Ein Alarm waere hier reine
    Erfindung - lieber ehrlich "unbekannt" als eine geratene Zahl.
    """
    verkauf = Verkauf(zeit=z("14.08.2026 12:00:00"), foto="a.jpg", cent=0)

    befund = pruefe_verkauf(verkauf, [], [])

    assert befund.zahlungsart == "unbekannt"
    assert befund.sicher is True
    assert befund.hinweis == ""
    assert fasse_zusammen([befund]).auffaellig == []


def test_pruefung_ohne_bekannten_preis_ueber_die_preisliste():
    """Der Normalfall an dieser Anlage: der Preis steht nirgends.

    In 1323 von 1332 Zeilen fuehrt Statistic.txt gar keinen Betrag. Statt einen
    Preis anzunehmen, wird andersherum gerechnet: was der Automat einbehalten
    hat, muss EINER der eingestellten Preise sein.
    """
    preise = [50, 100, 500]      # 0,50 / 1,00 / 5,00 EUR

    # 10 EUR rein, 5 EUR zurueck -> einbehalten 5,00 EUR, ein gueltiger Preis.
    sauber = pruefe_verkauf(
        Verkauf(z("14.08.2026 12:00:00"), "a.jpg", 0),
        [
            Muenzereignis(z("14.08.2026 11:59:40"), "ein", 1000, 1000),
            Muenzereignis(z("14.08.2026 12:00:10"), "aus", 500, 500),
        ],
        [], moegliche_preise=preise,
    )
    assert sauber.abweichung_cent == 0
    assert fasse_zusammen([sauber]).auffaellig == []

    # Derselbe Vorgang, aber der Wechsler gibt 7 EUR heraus: einbehalten 3,00 -
    # das ist kein eingestellter Preis, also stimmt etwas nicht.
    defekt = pruefe_verkauf(
        Verkauf(z("14.08.2026 12:00:00"), "a.jpg", 0),
        [
            Muenzereignis(z("14.08.2026 11:59:40"), "ein", 1000, 1000),
            Muenzereignis(z("14.08.2026 12:00:10"), "aus", 700, 700),
        ],
        [], moegliche_preise=preise,
    )
    assert defekt.abweichung_cent == 200
    assert defekt.sicher is True
    assert "keinem eingestellten Preis" in defekt.hinweis
    assert len(fasse_zusammen([defekt]).auffaellig) == 1


def test_ohne_preisliste_und_ohne_preis_kein_alarm():
    """Nichts zu vergleichen heisst: nichts behaupten."""
    befund = pruefe_verkauf(
        Verkauf(z("14.08.2026 12:00:00"), "a.jpg", 0),
        [
            Muenzereignis(z("14.08.2026 11:59:40"), "ein", 1000, 1000),
            Muenzereignis(z("14.08.2026 12:00:10"), "aus", 700, 700),
        ],
        [], moegliche_preise=None,
    )
    assert befund.sicher is False
    assert fasse_zusammen([befund]).auffaellig == []


def test_uebersicht_rechnet_anteile():
    from liftpic_sync.payments import Kartenzahlung

    verkaeufe = [
        Verkauf(z("14.08.2026 12:00:00"), "a.jpg", 500),
        Verkauf(z("14.08.2026 12:10:00"), "b.jpg", 500),
        Verkauf(z("14.08.2026 12:20:00"), "c.jpg", 500),
    ]
    muenzen = [
        Muenzereignis(z("14.08.2026 11:59:40"), "ein", 500, 500),
        Muenzereignis(z("14.08.2026 12:09:40"), "ein", 500, 500),
    ]
    karte = [Kartenzahlung(z("14.08.2026 12:19:50"), 500, True, "OK", "7")]

    uebersicht = fasse_zusammen(pruefe_alle(verkaeufe, muenzen, karte))

    assert uebersicht.bar_anzahl == 2
    assert uebersicht.karte_anzahl == 1
    assert uebersicht.bar_cent == 1000
    daten = uebersicht.as_dict()
    assert daten["bar_anteil"] == 0.667
    assert daten["karte_anteil"] == 0.333
