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

- [ ] `config_to_env` um die neuen Schlüssel erweitern, aus `settings` gespeist,
      ohne Zurücksetzen auf Vorgabewerte
- [ ] (Super-Admin-Oberfläche wartet bewusst — wird gerade überarbeitet)

## AP-6 — Rückweg und Versionierung

- [ ] 6.1 Echte Version statt konstant `0.1.0`
- [ ] 6.4 `scripts/update_liftpic.ps1` — stoppt sauber, sichert `.env`/`state`
      inkl. `-wal`/`-shm`/Aufgabe, **koppelt nicht neu**, endet mit `preflight`
- [ ] 6.5 `scripts/rollback_lokal.ps1` — Ordnersicherung zurück, ohne Git

## AP-7 — Simulation (Tor zum Merge)

- [x] 1 Zweiter Agent von Hand → abgewiesen (15.08.2026 19:42, `pid=5868`,
      Exit 0; der erste `pid=12012` lief unberührt weiter)
- [x] 2 Sperrdatei auf SYSTEM-Rechte → weicht aus, meldet es (das ist die
      **echte** Lage auf diesem PC, nicht nachgestellt:
      `ProgramData … [Errno 13] Permission denied … fell back to LOCALAPPDATA`)
- [ ] 3 Aufgabe **und** Dienst → Installer räumt die andere Startart ab
- [ ] 4 Update bei laufendem Agenten → kein Enkelprozess übrig
- [ ] 5 Neustart-Auftrag bei zwei Instanzen → genau ein Neustart
- [ ] 6 Verkaufsprogramm klemmt → ehrliche Meldung, kein falscher Erfolg
- [ ] 7 Kamera während Neustart weg → kein Testfoto ins Leere
- [ ] 8 Protokolldatei umbenannt/verschoben → wird gefunden
- [ ] 9 Fremde `debug.log` daneben → wird nicht zum Verkaufsprogramm
- [ ] 10 Netz trennen → Ereignisse gepuffert, Wachhund greift
- [ ] 11 `.env` mit Umlaut, Installer → Umlaut überlebt
- [ ] 12 Rollback aus der Ordnersicherung → läuft wie vorher
- [ ] 13 Asset mit gesperrter Zieldatei → eine Sicherung, Neustart-Hinweis
- [ ] 14 Nach jedem Schritt: Foto → Upload → richtiger Park → Umsatz stimmt

Vor und nach jedem Schritt vergleichen — muss identisch bleiben:
`select * from park_photo_sales_daily where business_date >= current_date - 2`

## Freigabe

- [ ] Tag `v0.1.0-imst-stand` auf `d833ec0` (**vor** dem Merge!)
- [ ] Härtung nach `main` mergen
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
