# Was noch offen ist

Stand 16.08.2026, nach dem Imst-Rollout auf `v0.2.1`.

Wer hier weiterarbeitet: **`docs/NOTFALL.md`** zuerst lesen, wenn etwas
brennt. **`docs/FEHLERJOURNAL.md`** enthält jeden bisher gefundenen Fehler
mit fester Nummer — kommt einer wieder, dort eine Zeile unter „Wiederkehr"
ergänzen statt eine neue Nummer zu vergeben. **`docs/HAERTUNG_FORTSCHRITT.md`**
zeigt, was gebaut wurde und was belegt ist.

---

## GANZ OBEN — der vereinbarte Fahrplan (22.08.2026)

Reihenfolge, die der Betreiber festgelegt hat. Nicht umsortieren, ohne dass
er es sagt.

**1. Erst alles auf dem Testrechner sauber laufen lassen.**
Stand heute: F-045 bis F-051 sind gebaut, getestet und auf dem Testrechner
verifiziert (Agent laeuft mit dem neuen Code, Dashboard zeigt korrekte
Betraege). Bevor irgendetwas live geht: hier zuerst pruefen, ob es rund
laeuft - Kamera-Neustart, Testfoto, Beenden/Pause, Zahlungsanzeige.

**2. Danach arbeitet der Betreiber vom Mac aus am selben Dashboard-Repo
weiter** (Design, Frontend) - `github.com/john123-05/dashboard2`, derselbe
Ablauf wie hier: aendern, committen, pushen. **Wichtig zu wissen, bevor er
dort etwas macht:**
  - GitHub ist die eine Wahrheit, aber es gibt DREI getrennte Wege, wie Code
    bei den Kunden ankommt: (a) GitHub → bolt.new → Netlify fuers Dashboard,
    (b) GitHub-Kopien der Supabase-Functions, die aber nur gelten, wenn sie
    auch ausgerollt wurden, (c) das Uploader-Repo (`testsoftware`) fuer den
    Agenten, der nur per `update_liftpic.ps1` auf einen Automaten kommt.
    Diese drei laufen NIE von selbst synchron - siehe F-013 (Wiederkehr
    17.08.) und die Repo-Sync-Luecke vom 19.08. Vor jedem bolt.new-Publish
    dort erst den GitHub-Stand holen, sonst wiederholt sich F-013.
  - `/version.txt` auf dem Dashboard sagt in einer Sekunde, ob ein Deploy
    wirklich angekommen ist.
  - Falls von zwei Stellen gleichzeitig gearbeitet wird (Mac + hier): vor
    jedem Push `git fetch` + `git log --oneline -5 origin/main` gegenpruefen,
    damit nicht wieder eine Function-Aenderung die andere ueberschreibt (wie
    beim Personalisierungs-Umbau am 19.08.).

**3. Erst danach: live schalten auf weiteren PCs (Imst zuerst).** Was dafuer
konkret zu tun ist:
  a. Alle offenen SQL-Nacharbeiten ausfuehren, die noch niemand im SQL-Editor
     laufen liess: `docs/sql/F-039-verkaufsdatum.sql` (Uploader-Repo) und
     `docs/sql/kiosk_photos_for_day_exclude_test.sql` (Dashboard-Repo).
  b. Auf Imst: `preflight` (rein lesend) → Ordnersicherung →
     `update_liftpic.ps1` mit dem aktuellen `main`-Stand → 30 Minuten
     beobachten (Abholcode bleibt 2734, Uploads laufen, keine neuen Fehler
     im Verlauf). Genaues Schema in AP-8 weiter unten in dieser Datei.
  c. Card-Terminal an Imst klaeren (Punkt weiter unten: existiert dort
     ueberhaupt eins? `card_log_glob` ist fuer `pcneu` nicht gesetzt).
  d. Kameraeinstellungen-Seite bewusst NICHT live schalten, solange sie nicht
     an echten Werten (nicht nur Testrechner-Werten) erprobt ist.
  e. Nach dem Update: dieselbe Zahlungspruefung wie hier auf dem Testrechner
     wiederholen - stimmen Betraege, Zahlungsart, „unzugeordnete Ereignisse"?

---

## Dringend — betrifft laufende Anlagen

### 0. Kein Herzschlag-Verlauf — Ausfallzeiten sind nicht rekonstruierbar
`machine_status` hat pro Automat **genau eine Zeile**; jeder Herzschlag
überschreibt den vorherigen. Wir wissen also immer nur, wann der *letzte* war,
nie den Verlauf.

Am 18.08.2026 fragte der Betreiber, ob die Ausfälle in Imst immer zur selben
Uhrzeit passieren. Beantworten liess sich das nur durch Rückrechnen aus
Foto-Uploads und Störmeldungen — und Foto-Uploads sind dafür untauglich, weil
sie nur beim Verkauf entstehen: eine halbe Stunde ohne Käufer sieht aus wie ein
Ausfall.

Was fehlt, ist eine schmale Verlaufstabelle, in die jeder Herzschlag eine Zeile
schreibt (Zeitpunkt, Warteschlange, Version). Bei 30-Sekunden-Takt sind das
rund 2 900 Zeilen je Automat und Tag — mit einer Aufbewahrung von 30 Tagen
unkritisch. Danach beantwortet **eine** Abfrage, wann eine Anlage still wurde,
wie lange, und ob es ein Muster gibt.

Bis dahin: `scripts/ausfall_spurensuche.ps1` am Automaten ausführen, solange
die Spur noch frisch ist.

### 0a. F-040: Aufnahmezahl nach einem Ausfall nachliefern
Die verkauften Fotos heilen sich nach einem Ausfall von selbst — sie werden aus
den hochgeladenen Dateien abgeleitet. Die Zahl der **Aufnahmen** nicht: die
meldet nur der laufende Agent, ein toter Agent zählt nicht, und hinterher ist
sie weg. Für den 16.08. stehen bei Imst darum 4 Aufnahmen zu 172 Verkäufen.
Die Anzeige sagt das inzwischen ehrlich, die Zahl fehlt aber weiterhin.

Sinnvoll wäre, dass der Agent die Tageszahlen aus der Statistikdatei
**nachliefert** statt sie nur live zu melden. Dann heilt sich auch diese Zahl.
Details und Belege: F-040 im Journal.

### 0b. F-039: SQL ausführen — ein Ausfalltag wird doppelt verbucht
**Fertig vorbereitet in `docs/sql/F-039-verkaufsdatum.sql`, muss nur noch in den
Supabase-SQL-Editor.** Nach dem 23-Stunden-Ausfall am 16./17.08. wurden Imsts
172 Fotos auf beiden Tagen gezählt — der 17.08. begann mit 860 € Umsatz, obwohl
noch kein Foto entstanden war. Kein Geld und kein Foto verloren, nur falsch
zugeordnet. Solange Aufnahme- und Hochladetag gleich sind, fällt es nicht auf;
jeder weitere Ausfall erzeugt es erneut. Ursache und Belege: F-039 im Journal.

### 1. Imst: Münzprüfer setzt sich wiederholt zurück
Drei Meldungen `CoinChangerError: Coin changer/validator reset` in drei
Stunden (16.08. 01:13, 02:04, 02:05), nachts, ohne Gäste. Das ist ein
Befund an der Anlage, kein Softwarefehler — aber er war vor dem Rollout
unsichtbar. Prüfen, ob der Prüfer tagsüber Geld annimmt.

### 2. Imst: ein Gast bekam 4,00 € zu wenig
`10.08.2026 16:58` — eingeworfen 10,00 €, erwartet 5,00 € zurück,
ausgezahlt 1,00 €. Vom Automaten als auffällig gemeldet. Einzelfall in
sieben Tagen, aber der Fall, für den die Wechselgeldkontrolle gebaut wurde.

**Achtung, es sieht nach mehr aus, als es ist:** dieselbe Meldung steht
inzwischen viermal im Verlauf (16.08. 01:40, 01:45, 08:27, 17.08. 08:52). Alle
vier tragen im Detail denselben Verkauf `2026-08-10T16:58`. Es ist **ein**
Vorfall, viermal gemeldet — der Wechselgeld-Prüfer setzt `occurred_at` auf den
Zeitpunkt der Erkennung statt auf den des Verkaufs und erkennt beim erneuten
Einlesen nicht, dass er den Fall schon gemeldet hat. Jeder Neustart meldet ihn
neu. Zu beheben: stabiler Schlüssel je Verkauf, und `occurred_at` = Verkaufszeit.
Nebenbei ein brauchbares Nebenprodukt — die vier Zeitpunkte zeigen, wann der
Agent neu eingelesen hat.

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

### Kameraeinstellungen aus dem Dashboard (Vorschlag, noch nicht gebaut)
Die Kamera ist eine **DFK 33GX545** von The Imaging Source, GigE, 4096×3000 bei
4,75 Bildern/s. Ihre Einstellungen stehen vollständig in
`C:\liftpicGerTis	rigger.xml`, die 3GerTis beim Start liest
(`xml_file=trigger.xml` in `3gertis.ini`).

Einstellbar sind unter anderem — Ist-Werte vom Testrechner:

| Eigenschaft | aktuell |
|---|---|
| Belichtung | **automatisch**, Sollwert 88, zuletzt 1,48 ms |
| Verstärkung | **automatisch**, höchstens 48 |
| Sättigung | 120,3 (angehoben) |
| Gamma | 0,81 |
| Helligkeit / Kontrast / Schärfe / Farbton | je 0 |
| Weißabgleich, Farbmatrix, Rauschminderung, Tone Mapping, Spitzlichter | vorhanden |

**Technisch ist alles da:** Werte aus der Ferne schicken kann `config_to_env`
schon, Dateien am Automaten schreiben samt Sicherung kann der Asset-Abgleich
schon, die Kamerasoftware neu starten kann `camera_exe` schon, und seit F-043
gibt es den Testfoto-Knopf. Damit schließt sich der Kreis: **ändern → Kamera
neu starten → Testfoto → Ergebnis im Dashboard ansehen.**

Was vorher geklärt sein muss, weil es Umsatz kostet, wenn es schiefgeht:
- `trigger.xml` ist GUID-basiert. Es dürfen **einzelne Werte** geändert werden,
  die Datei darf nie neu geschrieben werden.
- Vor jeder Änderung eine Sicherung, und ein „zurück zum vorherigen Stand" mit
  einem Klick. Ohne das nicht ausliefern.
- Grenzen erzwingen. Eine falsch gesetzte Belichtung macht einen ganzen
  Betriebstag unbrauchbar, und das merkt niemand sofort.
- Belichtung und Verstärkung stehen auf **automatisch**. Auf Hand umzustellen
  ist eine eigene Entscheidung, keine Nebenwirkung eines Schiebereglers.

**Achtung:** `C:\liftpic\TIScapture\config.ini` nennt dieselbe Seriennummer
`42320366`. Es gibt also zwei Programme für **eine** Kamera, und nur eines kann
sie gleichzeitig haben. Vor dem Bau klären, welches am jeweiligen Automaten
wirklich läuft.

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
