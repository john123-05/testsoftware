# Härtung vor dem Imst-Rollout — Fortschritt

**Diese Datei ist der Wiedereinstiegspunkt.** Wer hier weiterarbeitet (auch nach
einem Kontextverlust): erstes offenes Kästchen suchen, mit `git log --oneline`
gegenprüfen, dort weitermachen. Jedes Paket wird einzeln committet, die
AP-Nummer steht in der ersten Zeile der Commit-Beschreibung.

Ziel: Imst (produktiv, ~1145 Fotos und ~142 Verkäufe am Tag) kann aktualisiert
werden, ohne dass Doppelbetrieb, ein falscher Pfad, ein verschluckter Fehler
oder ein fehlgeschlagener Neustart die Anlage stört — mit einem Rückweg, der in
Minuten funktioniert.

---

## Bindende Reihenfolge

```
AP-0 ─→ AP-1 … AP-6 ─→ AP-7 Simulation ─→ Tag v0.1.0-imst-stand (Fallback!)
                                            ─→ Merge nach main ─→ Tag v0.2.0
                                                                   └─→ AP-8 Imst
```

Der Fallback-Tag muss **vor** dem Merge stehen. Nach dem Merge zieht jede
Neuinstallation den neuen Stand — deshalb ist die Simulation das Tor zum Merge,
nicht eine Empfehlung.

---

## AP-0 — Journale

- [x] `docs/HAERTUNG_FORTSCHRITT.md` (diese Datei)
- [x] `docs/FEHLERJOURNAL.md` mit den bereits gefundenen Fehlern

## AP-1 — Einmaligkeit erzwingen

- [x] 1.1 Sperre repariert — drei benannte Zustände (`gesperrt`/`belegt`/
      `ungesichert`), Ausweichpfad LOCALAPPDATA, bei endgültigem Fehlschlag
      weiterlaufen **aber** `log.error` + Verlaufseintrag. Gilt jetzt auch für
      `scan-once` und `assets`. Am Testrechner belegt: der systemweite Pfad ist
      wegen der SYSTEM-Rechte nicht nutzbar, der Ausweichpfad greift, und ein
      zweiter Agent wird abgewiesen (Exit 0, der erste läuft weiter).
- [x] 1.2 Prozessnummer im Protokollformat (`pid=%(process)d`)
- [x] 1.3 Upload-Anspruch atomar — `due_uploads` beansprucht die Zeilen in
      einer Transaktion (`uploading` + `claimed_by`/`claimed_at`), mit
      Verfallszeit von 600 s, damit ein Absturz nichts dauerhaft blockiert.
      Migration ergänzt die zwei Spalten und gibt hängende `uploading`-Zeilen
      einmalig frei. Auf der echten Datenbank (18 Zeilen) durchgelaufen.
- [x] 1.4 Neustart-/Testfoto-Auftrag genau einmal — neue Tabelle
      `handled_orders`, der Primärschlüssel ist die Absicherung. Der Anspruch
      steht unmittelbar **vor** der Ausführung, nicht beim Sehen des Auftrags:
      ein `tonight`-Auftrag durchläuft die Prüfungen stundenlang, würde er dabei
      beansprucht, ginge er nachts nie los. Einträge verfallen nach 30 Tagen.
- [x] 1.5 SQLite `busy_timeout` 30 s (Verbindung **und** PRAGMA) — vorher
      endete jeder Schreibkonflikt nach 5 s in „database is locked" und wurde
      von `run_forever` als „run_once failed" verschluckt
- [x] 1.6 Asset-Zwischendatei trägt die Prozessnummer; eine Leiche wird nach
      einem gescheiterten Ersetzen aufgeräumt
- [x] 1.7 `.env` wird daneben geschrieben und dann ersetzt — die alte Datei
      bleibt bis zur letzten Sekunde vollständig. Im Installer zusätzlich
      `ASCII` → `UTF8` beim Lesen **und** Schreiben: das Setzen eines einzigen
      Schlüssels machte vorher aus jedem Umlaut in *jeder* Zeile ein `?`.
- [x] 1.8 Startwege entwirrt — `install_windows_service.ps1` räumt jetzt immer
      die **andere** Startart ab (Dienst und Aufgabe liegen in getrennten
      Namensräumen und hießen beide `LiftpicSync`), beendet laufende Agenten und
      **wartet**, bis sie wirklich weg sind, statt sofort neu zu starten. Nimmt
      das venv-Python statt `python` aus dem PATH. `restart_service.ps1` prüft
      beide Startarten, warnt wenn es beide gibt, und startet erst nach
      bestätigtem Ende des alten Prozesses.
- [x] 1.9 Token-Selbstheilung begrenzt auf 10 Versuche (~20 min), danach ein
      Fehlereintrag „Anmeldung am Server schlägt dauerhaft fehl" mit dem Hinweis
      auf die häufigste Ursache. Vorher lief das endlos alle 120 s weiter — bei
      zwei Instanzen entwerten sie sich das Token gegenseitig, und genau so sah
      die 401-Störung aus.

## AP-2 — Protokolle zuverlässig finden

- [x] 2.1 Vorgabe-Muster ergänzt: `samuel_neu\*.log`, `samuel_neu\Log\*.txt`,
      `CoinStats.txt`, `terminal\*`, `liftpic-sync\logs\*.log`
- [x] 2.2 Selbsterkennung — die Suchorte werden **aus den Mustern abgeleitet**
      (Ordner vor dem ersten Platzhalter plus dessen Elternordner), nicht fest
      verdrahtet. Damit wandert die Suche mit, wenn eine Anlage anders ablegt.
      Deckel von 60 auf 200, und: Treffer aus Mustern gehen **immer** mit,
      Fundstücke füllen nur auf. Ohne diese Trennung verdrängten 200
      Fundstücke ältere, aber wichtige Protokolle. `recursive=True`, damit `**`
      in einem Muster auch wirklich wirkt.
- [x] 2.3 Generische Fragmente (`debug.log`, `errors.log`, `watchdog.log`)
      greifen nicht mehr in Ordnern, die nachweislich einem anderen Gerät
      gehören
- [x] 2.4 Unbekanntes, fehlerfreies Protokoll erscheint als eigene Quelle
      unter „system", statt verworfen zu werden
- [x] 2.5 `merge_key` wird im Dashboard als Schlüssel benutzt, wenn der Automat
      einen mitschickt (ältere Stände: weiter über den Klarnamen). Dazu ein
      zweiter Index über den Klarnamen, weil die Neustart-Ziele nur ihren Namen
      mitschicken und ihren Eintrag sonst nicht mehr fänden.

**Beobachtung dabei (gehört zu AP-3):** die Lichtschranke ist aus der Anzeige
verschwunden, weil ihre Protokolldatei 54 h alt ist und die Grenze bei 48 h
liegt. Das ist so gewollt — aber ein verschwundenes Gerät ist derzeit nicht von
einem nie dagewesenen zu unterscheiden.

## AP-3 — Keine erfundenen Zahlen

- [x] `photos_sold_today ?? 0` → Angabe entfällt, wenn nicht gemeldet
- [x] `monitored_sources ?? 0` → „Anzahl überwachter Quellen unbekannt"
- [x] `restart_poll_seconds ?? 20` → Satz entfällt („beim nächsten Abruf").
      Die 20 waren doppelt falsch: bei abgeschalteten Neustarts sind es 300.
- [x] `bar_anteil/karte_anteil ?? 0` → ohne Anteile kein Balken. Vorher zeigte
      er 0 % bar und 100 % Karte, obwohl der Automat bewusst `null` liefert.
- [ ] Offen: ein Gerät, das aus dem Herzschlag verschwindet, verschwindet
      spurlos aus der Seite — nicht unterscheidbar von „gab es nie". Aufgefallen
      an der Lichtschranke (Protokoll 54 h alt, Grenze 48 h). Eigener Punkt,
      blockiert den Rollout nicht.

## AP-4 — Asset-Sicherungs-Kreislauf

- [x] 4.1 Vor der Sicherung wird geprüft, ob das Ziel überhaupt beschreibbar
      ist (`_ziel_ist_gesperrt`). Ist es belegt, entsteht **keine** Sicherung
      mehr — das war der Kreislauf. Dazu Entdopplung: gleicher alter Inhalt wie
      die jüngste vorhandene Sicherung → keine neue.
- [x] 4.2 `restart_needed` wird ausgewertet und **einmal** als Verlaufseintrag
      gemeldet („Ein neues Bild wartet auf einen Neustart des
      Verkaufsprogramms"), nicht alle 20 Sekunden erneut. Steht außerdem im
      Herzschlag.
- [x] 4.3 Aufbewahrung: 10 Stände je Datei, leere Ordner werden mitgenommen.
      Einmalige Bereinigung auf dem Testrechner: 122 → 4 Dateien, 6,9 MB frei,
      **jeder der vier unterschiedlichen Inhalte erhalten** (nur byte-gleiche
      Dubletten entfernt).
- [x] 4.4 Zwei Tests: gesperrtes Ziel erzeugt keine Sicherung und meldet den
      Wartezustand; derselbe alte Inhalt wird nicht zweimal gesichert.

## AP-5 — Merkmale aus der Ferne schalten

- [x] `config_to_env` um 13 Schlüssel erweitert, aus dem `settings`-Feld der
      Maschine gespeist. **Andere Regel als die Haupttabelle:** ein fehlender
      Eintrag lässt den Wert am Automaten stehen, statt ihn auf einen
      Vorgabewert zurückzusetzen — sonst würde eine Anlage mit eigenen Pfaden
      beim nächsten Abruf plattgemacht. Sieben Tests.
- [x] `liftpic-config` liefert `settings` mit
- [ ] **BLOCKIERT — siehe F-031:** Der Deploy hat `verify_jwt` auf `true`
      gesetzt und sperrt damit alle Automaten aus dieser Function aus. Muss im
      Supabase-Dashboard abgeschaltet werden (Edge Functions → `liftpic-config`
      → Settings → „Verify JWT"). Erst danach wirken die Fernschalter.
- [ ] (Super-Admin-Oberfläche wartet bewusst — wird gerade überarbeitet)

> **Regel für alle Automaten-Functions:** `liftpic-config`, `liftpic-status`,
> `liftpic-ingest-begin`, `liftpic-ingest-commit` und `liftpic-assets` dürfen
> **nicht** über die Programmierschnittstelle ausgerollt werden. Sie verwenden
> Gerätetokens statt JWTs, und jeder Deploy auf diesem Weg sperrt sie zu. Nur
> über die Supabase-Befehlszeile mit `--no-verify-jwt`.

## AP-6 — Rückweg und Versionierung

- [x] 6.1 Version auf `0.2.0` in `__init__.py` **und** `pyproject.toml`, ein
      Test hält beide gleich. Sie stand monatelang konstant auf `0.1.0` — am
      Server war damit nicht ablesbar, welcher Stand auf einem Automaten läuft.
- [x] 6.4 `scripts/update_liftpic.ps1` — hält an und **wartet**, sichert
      `.env`, `state\` inkl. `-wal`/`-shm`, die exportierte Aufgabe und den
      Programmstand, installiert aus einem Tag, **koppelt nicht neu** wenn ein
      Gerätetoken da ist (das Koppeln würde 16 Schlüssel überschreiben), und
      endet mit `preflight`. Bricht ab, wenn der alte Agent nicht weggeht —
      statt zwei Codestände zu mischen.
- [x] 6.5 `scripts/rollback_lokal.ps1` — spielt die Ordnersicherung zurück,
      ohne Git. Das mitgelieferte `rollback.ps1` macht `git checkout` und ist
      auf einem Automaten unbrauchbar, weil dort kein Repo liegt.

## AP-7 — Simulation (Tor zum Merge)

- [x] 1 Zweiter Agent von Hand → abgewiesen (15.08.2026 19:42, `pid=5868`,
      Exit 0; der erste `pid=12012` lief unberührt weiter)
- [x] 2 Sperrdatei auf SYSTEM-Rechte → weicht aus, meldet es (das ist die
      **echte** Lage auf diesem PC, nicht nachgestellt:
      `ProgramData … [Errno 13] Permission denied … fell back to LOCALAPPDATA`)
- [x] 3 Aufgabe **und** Dienst → die fremd benannte Aufgabe wird gefunden.
      *Offener Punkt:* es waren **2** Treffer statt einem — siehe F-034.
      Nachgeprüft: es existiert derzeit weder eine Aufgabe noch ein Dienst,
      der den Agenten startet.
- [x] 4 Update bei laufendem Agenten → alle Prozesse beendet, kein Enkel übrig.
      Zusätzlich am Prozesswechsel belegt (`pid=1228` → `pid=18804` → `18876`) —
      genau wofür AP-1.2 gebaut wurde.
- [x] 5 Neustart-Auftrag bei zwei Instanzen → genau ein Neustart. Live gegen
      die **echte** Zustandsdatenbank geprüft: Agent A bekommt ihn, Agent B
      nicht. Probe danach wieder entfernt.
- [x] 6 Verkaufsprogramm neu gestartet → ehrlich gemeldet:
      `23:32:46 Verkaufsprogramm neu gestartet on dashboard order '9753d745…'`
- [x] 7 Kamera weg → kein Testfoto ins Leere. Fünf Fälle geprüft: gerade
      verloren (0 min) · seit 90 min verloren · verloren und
      zurückgemeldet → `True` · **nur `(from ini)` zählt nicht als
      Entwarnung** · keine Aussage → `None`, nicht „nicht verbunden".
- [x] 8 Protokolldatei an einem Ort, den kein Muster trifft → wird gefunden
      (`test_protokoll_wird_auch_ohne_passendes_muster_gefunden`)
- [x] 9 Fremde `debug.log` unter `CAMware\` → wird **nicht** zum
      Verkaufsprogramm, verschwindet aber auch nicht
- [x] 10 Netz trennen → nichts ging verloren:
      `23:30:50 delivered 11 buffered health notes after reconnect`
- [x] 11 `.env` mit Umlaut, Installer setzt einen Schlüssel → Umlaut überlebt.
      Gegenprobe mit der alten ASCII-Kodierung: `Süd` → `S?d` und
      `\Überwachung` → `\?berwachung`. Der zweite Fall ist der gefährliche —
      aus einem gültigen Pfad wird einer, den es nicht gibt.
- [x] 12 Rücksicherung → Token, Umlaut und die `-wal` sind zurück
- [x] 13 Asset mit gesperrter Zieldatei → keine Sicherung, Wartezustand
      gemeldet (`test_gesperrtes_ziel_erzeugt_keine_sicherung`)
- [x] 14 Die ganze Kette, 15.08. 23:37:03 — Testfoto ausgelöst, hochgeladen,
      Park **testrechner** (nicht Imst), `is_test = true`, Nummer **7623**
      (die konfigurierte, nicht die 1234 aus der `Settings.xml`), Pfad
      `processed/testrechner/testfoto/…`. Und der entscheidende Teil:
      **kein Umsatzeintrag** — in `park_photo_sales_daily` stehen nur Imsts
      echte Zeilen (142 heute, 115 gestern), unverändert.

**Szenario 3, 4 und 12 brauchen eine erhöhte Konsole.** Dafür liegt bereit:

```powershell
# Als Administrator ausführen:
powershell -ExecutionPolicy Bypass -File C:\liftpic\liftpic-sync\scripts\ap7_pruefung.ps1
```

Es stellt jeden Fall nach, prüft die Erwartung und räumt hinter sich auf.
Szenario 12 läuft auf einer Kopie in `%TEMP%`, die Installation wird nicht
angefasst; Szenario 4 hält den Agenten kurz an und startet ihn wieder.

Vor und nach jedem Schritt vergleichen — muss identisch bleiben:
`select * from park_photo_sales_daily where business_date >= current_date - 2`

## Freigabe

- [x] Tag `v0.1.0-imst-stand` auf `d833ec0` gesetzt und gepusht — **der
      Rückweg existiert.** Nachgeprüft, nicht nur gesetzt: das Archiv lädt
      (105 KB, 92 Einträge), enthält `cli.py`, `service.py` und den Installer,
      und **keine** der Härtungsdateien (`preflight.py`, `update_liftpic.ps1`,
      `FEHLERJOURNAL.md`, `rollback_lokal.ps1`). Es zeigt also wirklich auf den
      Stand, der heute in Imst läuft.

      Zurück damit: `.\scripts\update_liftpic.ps1 -Tag v0.1.0-imst-stand`
      Weil der Installer nur darüberkopiert und nichts löscht, überlebt
      `update_liftpic.ps1` die Rücksicherung — man kommt auch wieder vorwärts.
- [ ] Härtung nach `main` mergen — **erst wenn Szenario 3, 4 und 12 durch sind**
- [ ] Tag `v0.2.0-haertung` auf den neuen `main`

## AP-8 — Imst (nach Betriebsschluss)

- [ ] `preflight` aus einer Wegwerf-Kopie, rein lesend
- [ ] Ordnersicherung anlegen
- [ ] `update_liftpic.ps1`, ohne Neukopplung
- [ ] 30 Minuten beobachten: Abholcode 2734 · Uploads · Gerätekacheln ·
      keine Neustart-Knöpfe (Sitzung 0) · Umsatz unverändert
- [ ] Merkmale einzeln aus der Ferne freischalten

---

## Bewusst nicht in diesem Vorhaben

- **Park-Trennung**: alle fünf Parks liegen in einer Organisation, sieben
  Mitglieder, der Zugriff hängt allein an der Mitgliedschaft. Echter Befund,
  eigene Entscheidung, eigener Umfang.
- **`css-alpine-pc2`**: Nummer 4488 ist im Park nicht registriert (dort: 2026).
  Die Anlage läuft nicht und wird nicht angefasst.
- **QR-Code aus dem Dashboard steuern**: `OFFENE_PUNKTE.md` Punkt 6.
