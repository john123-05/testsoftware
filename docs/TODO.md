# Was noch offen ist

Stand 16.08.2026, nach dem Imst-Rollout auf `v0.2.1`.

Wer hier weiterarbeitet: **`docs/NOTFALL.md`** zuerst lesen, wenn etwas
brennt. **`docs/FEHLERJOURNAL.md`** enthält jeden bisher gefundenen Fehler
mit fester Nummer — kommt einer wieder, dort eine Zeile unter „Wiederkehr"
ergänzen statt eine neue Nummer zu vergeben. **`docs/HAERTUNG_FORTSCHRITT.md`**
zeigt, was gebaut wurde und was belegt ist.

---

## Dringend — betrifft laufende Anlagen

### 1. Imst: Münzprüfer setzt sich wiederholt zurück
Drei Meldungen `CoinChangerError: Coin changer/validator reset` in drei
Stunden (16.08. 01:13, 02:04, 02:05), nachts, ohne Gäste. Das ist ein
Befund an der Anlage, kein Softwarefehler — aber er war vor dem Rollout
unsichtbar. Prüfen, ob der Prüfer tagsüber Geld annimmt.

### 2. Imst: ein Gast bekam 4,00 € zu wenig
`10.08.2026 16:58` — eingeworfen 10,00 €, erwartet 5,00 € zurück,
ausgezahlt 1,00 €. Vom Automaten als auffällig gemeldet. Einzelfall in
sieben Tagen, aber der Fall, für den die Wechselgeldkontrolle gebaut wurde.

### 3. F-036: `preflight` meldet die falsche Sitzung
Sagt „Benutzersitzung", während der Agent in Sitzung 0 läuft — es misst die
Sitzung des ausführenden Prozesses, nicht die des Agenten. Wer sich darauf
verlässt, entscheidet falsch. Müsste Konto und Auslöser der Autostart-Aufgabe
lesen.

### 4. F-034: ungeklärter zweiter Aufgaben-Treffer
Beim Prüfen auf dem Testrechner wurden zwei Aufgaben gefunden statt einer.
Danach war keine mehr da, das Aufgabenplaner-Protokoll ist nicht aktiviert.
Nicht belegbar, deshalb offen. Bei jeder Anlage prüfen: es darf genau eine
Startart geben.

---

## Nächste sinnvolle Schritte

### Kartenzahlungen bei Imst sichtbar machen
Aktuell **null** Kartendaten dort — der Pfad zum Terminal-Protokoll ist nicht
gesetzt. Von 951 Verkäufen sind 49 als bar erkannt und **902 unbekannt**.
Erst prüfen, ob es dort ein Terminal gibt:
```
Get-ChildItem C:\liftpic\terminal -ErrorAction SilentlyContinue
```
Wenn ja, aus der Ferne freischalten (siehe unten).

### Lichtschranke und Kamera bei Imst finden
Beide müssen laufen — sonst gäbe es keine Fotos. Sie schreiben nur an einen
Ort, den wir nicht kennen. Suchen:
```
Get-ChildItem C:\liftpic -Directory | Select-Object Name, LastWriteTime
```
Sobald ihr Protokoll gefunden ist, erscheinen sie **von allein** als Kachel.
Nur die Knöpfe bräuchten zusätzlich den Pfad zur `.exe`.

### Merkmale aus der Ferne freischalten
Ohne Besuch, ohne PowerShell. Beispiel:
```sql
update liftpic_machine_configs
set settings = coalesce(settings, '{}'::jsonb) || jsonb_build_object(
      'card_log_glob', 'C:\liftpic\terminal\ZvtLog_*.txt'
    )
where machine_id = 'pcneu';
```
Der Agent hat es binnen zwei Minuten. Fehlt die Datei dort, passiert nichts —
das Merkmal erscheint dann einfach nicht.

Schaltbar sind: `viewer_restart_enabled`, `viewer_exe`, `camera_exe`,
`lightbarrier_exe`, `test_photo_exe`, `viewer_settings_xml`,
`coin_stats_file`, `coin_log_glob`, `card_log_glob`,
`operational_log_globs`, `asset_sync_enabled`, `probe_enabled`,
`terminal_host`.

**Wichtig:** ein fehlender Eintrag lässt den Wert am Automaten stehen — er
schaltet ihn *nicht* ab. Abschalten geht mit leerem String oder `false`.

### Super-Admin-Oberfläche für die Merkmalsschalter
Die Mechanik steht, die Bedienoberfläche fehlt. Bewusst nicht gebaut, weil
der Super-Admin gerade visuell überarbeitet wird. Es geht um Schalter pro
Kunde, die in das `settings`-Feld schreiben.

---

## Kleinere offene Punkte

- **Verschwundene Geräte** sind nicht von nie dagewesenen zu unterscheiden.
  Fällt auf, wenn ein Protokoll älter als 48 Stunden wird (die Lichtschranke
  am Testrechner). Ein „zuletzt gesehen"-Rest wäre ehrlicher.
- **F-033**: Ein erhöht laufender Agent ist für eine normale Sitzung
  unsichtbar. Alle Skripte verlangen deshalb Administratorrechte. Eine
  Rückfallprüfung über `Get-Process` wäre robuster.
- **Serversperre für echte Fotos** (nicht nur Testfotos): sinnvoll, könnte
  aber Uploads blockieren. Erst mit Imst-Daten prüfen.
- **QR-Code aus dem Dashboard steuern**: `OFFENE_PUNKTE.md` Punkt 6,
  erfordert schreibenden Zugriff auf die `Settings.xml`.
- **Verkaufsart** (Druck/E-Mail) und **Geschwindigkeit** aus `kosel\test.txt`:
  Daten liegen bereit, reine Auswertung, kein Risiko.
- **Push-Alarm bei Ausfall**: seit Tagen offen.
- **`css-alpine-pc2`**: meldet Nummer 4488, registriert ist im Park nur 2026.
  Dieselbe Falle wie am 15.08. Die Anlage läuft nicht, deshalb ist noch
  nichts passiert — vor der Inbetriebnahme klären.

---

## Größere Themen

### Park-Trennung
Alle fünf Parks liegen in **einer** Organisation mit sieben Mitgliedern, und
der Zugriff hängt allein an der Mitgliedschaft. Das Park-Passwort ist nur
eine Hürde im Frontend — die Functions sehen es nie. Ein Mitgliedskonto
könnte mit einer fremden Park-Kennung die Daten eines anderen Kunden
abrufen. In der Oberfläche passiert das nicht versehentlich, auf der
Schnittstelle ist es nicht verhindert. Eigene Entscheidung, eigener Umfang.

### bolt.new und das Dashboard-Repo
bolt.new hält eine eigene, ältere Kopie von `john123-05/dashboard2`. Ein
Publish-Klick hat am 15.08. **23 Dateien und 4136 Zeilen zurückgedreht** —
unter der Beschreibung „Updated config.toml". Vor jedem Publish dort den
GitHub-Stand holen, sonst wiederholt es sich. Siehe F-013.
