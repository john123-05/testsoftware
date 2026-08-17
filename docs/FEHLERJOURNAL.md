# Fehlerjournal

Jeder Fehler bekommt **eine feste Nummer, die er behält**. Tritt derselbe Fehler
erneut auf, wird **keine neue Nummer vergeben**, sondern eine Zeile unter
„Wiederkehr" ergänzt.

Das ist der eigentliche Zweck dieser Datei. Ein zweites Auftreten heißt: die
Ursache war nicht verstanden — nicht „das kann nicht sein". Wer hier einen
Eintrag mit Wiederkehr findet, soll misstrauisch gegen die eingetragene Ursache
werden, nicht gegen den Beobachter.

Aufbau eines Eintrags:

```
## F-000 — Kurzer Satz, was falsch war
Status:     offen | behoben (Commit, Datum) | beobachtet
Gesehen:    wann und wobei
Beleg:      woran man es gemerkt hat, möglichst wörtlich
Ursache:    warum es passiert ist
Behebung:   was geändert wurde, welcher Test es festhält
Wiederkehr: — oder Datum + was diesmal anders war
```

Nachgetragen am 15.08.2026 aus der Arbeit der Vortage. Die Belege stammen aus
Protokolldateien, Datenbankabfragen und Commit-Beschreibungen.

---

# Offen

## F-040 — 4300 % Conversion nach einem Ausfalltag
Status:     Anzeige behoben (dashboard2, 17.08.2026) · Datenlücke bleibt offen
Gesehen:    17.08.2026, Betreiber beim Blick auf den 16.08.
Beleg:      Kacheln für So. 16.08.: „Gesamtfotos 4", „Gekauft 172",
            „Verfügbar 0", „Conversion 4300,0 %". Daneben der Kreis
            „von 4 Fahrten" bei 172 verkauften Fotos. Der Vortag 15.08. steht
            daneben völlig normal: 1145 Aufnahmen, 142 verkauft, 12,4 %.
            In `park_photo_ride_daily` für den 16.08.:
            `photos_taken_count = 4`, `photos_sold_count = 172`,
            `last_capture_at = 16.08. 10:48` — danach nichts mehr.
            Zum Vergleich 12.–15.08.: 1083, 1104, 1152, 1145 Aufnahmen.
Ursache:    Die beiden Zahlen kommen aus verschiedenen Quellen und überleben
            einen Ausfall unterschiedlich gut:

            * **Verkaufte Fotos** werden aus den hochgeladenen DATEIEN
              abgeleitet. Die liegen auf dem Automaten und warten. Nach dem
              Ausfall kamen alle 172 nach — vollständig.
            * **Aufgenommene Fotos** meldet nur der laufende Agent im
              Herzschlag. Ein toter Agent zählt nicht, und die Zahl lässt sich
              hinterher nicht mehr rekonstruieren. Für den 16.08. blieben die
              4 stehen, die er vor 10:48 noch mitbekommen hat.

            Die Anzeige teilte dann 172 durch 4. Zusätzlich rechnete
            `Verfügbar` als `max(0, 4 - 172)` und zeigte darum eine glatte 0 —
            als wäre bekannt, dass nichts übrig war.
Folge:      Keine Datenverfälschung, aber die Seite behauptete etwas
            Unmögliches und sah dadurch kaputt aus. Es ist dieselbe Klasse wie
            AP-3: eine Zahl erfinden, wo „unbekannt" die ehrliche Antwort wäre.
Behebung:   `src/pages/Photos.tsx` erkennt jetzt `verkauft > aufgenommen` als
            das, was es ist — eine Lücke, kein Rekord. In diesem Fall:
            Aufnahmen, Verfügbar und Conversion zeigen „—", der Conversion-Ring
            und der Verteilungsring entfallen, und ein Hinweis nennt die eine
            Zahl, die stimmt (die verkauften Fotos). Der Kreis je Attraktion
            ebenso.
Offen:      Die 1100-und-etwas Aufnahmen des 16.08. sind in unseren Daten
            weiterhin verloren. Rekonstruierbar wären sie nur aus dem
            Rohbildordner am Automaten. Grundsätzlicher: der Agent könnte die
            Tageszahlen aus der Statistikdatei nachliefern, statt sie nur live
            zu melden — dann heilt sich auch diese Zahl nach einem Ausfall.
Wiederkehr: —

## F-039 — Ein Ausfalltag wird als Umsatz des Folgetags verbucht
Status:     offen (Ursache belegt, Behebung als SQL vorbereitet, 17.08.2026)
Gesehen:    17.08.2026 ~09:30. Der Betreiber meldete: „Umsatz heute 860 € und
            letzte Datenquelle vor 1 Minute, kann doch nicht sein" — während
            das Dashboard denselben Automaten als seit 23 Stunden still führte.
Beleg:      `park_photo_sales_daily` für `imster-bergbahnen`:
            17.08. = 172 verkaufte Fotos (× 5,00 € = 860,00 €), geschrieben
            09:10:08. Gleichzeitig 16.08. = 172, geschrieben 09:20:00.
            Dieselben 172 Fotos, zweimal gezählt, auf zwei Tagen.
            Gegenprobe an den Rohdaten: alle 172 Fotos wurden am 17.08.
            zwischen 08:51 und 09:10 **hochgeladen**, aber am 16.08. zwischen
            09:34 und 17:50 **aufgenommen**. Am 17.08. war zu dem Zeitpunkt
            noch kein einziges Foto entstanden.
Ursache:    Eine Kette aus vier Teilen, von denen jeder für sich harmlos aussieht:

            1. `handle_new_storage_object` legt die Fotozeile an und setzt
               `captured_at := NEW.created_at` — das ist die Entstehungszeit des
               **Speicherobjekts**, also der Zeitpunkt des Hochladens, nicht der
               der Aufnahme.
            2. `rollup_kiosk_photo_sale` feuert AFTER INSERT, also sofort. Es
               will das Geschäftsdatum aus `source_time_code` lesen und prüft
               dafür nur `^[0-9]{8}$`. `parse_source_time_code` liefert aus dem
               Pfad `processed/imster-bergbahnen/2026-08-16/2633176874402023.jpg`
               aber **`17687440`** — acht Ziffern aus dem 16-stelligen Codenamen,
               kein Datum. Der Test greift, `to_date('17687440','DDMMYYYY')`
               wirft „date/time field value out of range", der `exception`-Block
               setzt still auf `null`, und es bleibt der Rückfall auf
               `captured_at` — die Hochladezeit aus Punkt 1.
            3. Erst danach setzt `liftpic-ingest-commit` `captured_at` und
               `source_time_code` auf die richtigen Werte (16.08., `16082026`).
               Der Auslöser hat da längst gezählt und läuft nie wieder.
            4. `resync_recent_photo_sales` rechnet **richtig** — es hat die
               strenge Datumsprüfung und sieht die inzwischen korrigierten Werte.
               Es schreibt den 16.08. sauber. Aber es korrigiert den falschen
               17.08. nicht, weil es
               `photos_sold_count = greatest(alt, neu)` verwendet: eine einmal zu
               hoch eingetragene Zahl kann **nie wieder sinken**.

            Solange Aufnahme- und Hochladetag derselbe sind, fällt nichts davon
            auf — die falsche und die richtige Rechnung ergeben dieselbe Zahl.
            Erst der 23-Stunden-Ausfall hat die beiden Tage auseinandergezogen.
Folge:      Kein Geld verloren und kein Foto verloren — die Pufferung hat
            gehalten, alle 172 Aufnahmen kamen an. Falsch ist nur die
            **Zuordnung**: ein Betriebstag erscheint doppelt, der Ausfalltag
            sieht normal aus, der Folgetag beginnt mit einem Umsatz, den es nicht
            gab. Wer die Tageszahlen für Abrechnung oder Vergleich nutzt,
            rechnet mit einer erfundenen Zahl. Punkt 4 macht es dauerhaft.
Behebung:   Vorbereitet in `docs/sql/F-039-verkaufsdatum.sql`, drei Teile:
            strenge Datumsprüfung im Auslöser (dieselbe wie im Resync) und
            Bevorzugung des Datumssegments aus dem Speicherpfad · `greatest`
            im Resync durch Zuweisung ersetzen, damit sich Zahlen selbst
            korrigieren können · einmaliges Aufräumen der Geisterzeilen.
            **Nicht vom Agenten ausgeführt** — gehört in den SQL-Editor.
Wiederkehr: —

## F-038 — Der Wachhund beendet sich in eine Lücke hinein
Status:     behoben (`_darf_sich_beenden`, v0.2.1)
Gesehen:    16.08.2026 auf dem Testrechner
Beleg:      Nach einem Netzverlust um 03:44 war der Agent sieben Stunden später
            immer noch tot.
Ursache:    Der Wachhund beendet den Prozess in der Annahme, ein Autostart fange
            ihn wieder auf. Auf dem Testrechner gab es keinen. Die Annahme war
            nirgends geprüft.
Behebung:   `_darf_sich_beenden()` fragt den Aufgabenplaner, **bevor** es sich
            beendet. Ohne Autostart bleibt der Prozess am Leben.
Wiederkehr: —

## F-037 — Bargeldanteil aus zu wenigen Daten hochgerechnet
Status:     behoben (`ANTEIL_AB_ERKANNT`, v0.2.1)
Gesehen:    16.08.2026, Imst
Beleg:      Von 951 Verkäufen waren 49 als bar erkannt und 902 unbekannt.
            Daraus wurde ein Balken „100 % Karte" gebaut.
Ursache:    Der Anteil wurde aus den erkannten Fällen gebildet, ohne zu prüfen,
            ob die erkannten Fälle überhaupt aussagekräftig sind.
Behebung:   Unter 50 % Erkennungsrate liefert `bar_anteil` jetzt `None`, und die
            Anzeige lässt den Balken weg statt zu raten.
Wiederkehr: —

## F-036 — `preflight` meldet die falsche Sitzung
Status:     offen
Gesehen:    16.08.2026 beim Imst-Rollout
Beleg:      `preflight` sagte „Benutzersitzung – Neustarts sind möglich und
            sichtbar." Der Agent meldet für denselben Automaten
            `session_zero: true`. Beides zugleich kann nicht stimmen.
Ursache:    `preflight` misst die Sitzung **des Prozesses, der es ausführt** —
            also die PowerShell des Monteurs. Der Agent läuft dort aber als
            Aufgabe unter SYSTEM, in Sitzung 0. Gemessen wurde die richtige
            Frage am falschen Prozess.
Folge:      Der Bericht behauptet, Neustart-Knöpfe würden funktionieren, wo sie
            es nicht tun. Beim Rollout hat es nichts angerichtet, weil der
            Herzschlag des Agenten die maßgebliche Antwort liefert und diese
            korrekt war — die Knöpfe blieben richtigerweise aus. Wer sich aber
            auf `preflight` verlässt, entscheidet auf falscher Grundlage.
Behebung:   offen. `preflight` müsste die Sitzung der Autostart-Aufgabe
            ermitteln (Konto und Trigger auslesen), nicht die eigene — oder
            ehrlich sagen, dass es nur über sich selbst Auskunft geben kann.
Wiederkehr: —

## F-035 — Die Ausweichsperre aus AP-1.1 erlaubte zwei Agenten
Status:     behoben (16.08.2026) — **selbst verursacht**
Gesehen:    16.08.2026 00:36, auf dem Testrechner
Beleg:      Zwei Agenten liefen gleichzeitig und schrieben abwechselnd:
            `00:36:02 pid=18072 … 00:36:05 pid=18876 … 00:36:08 pid=18072`
            `pid=18876` seit 23:42:42 erhöht gestartet, `pid=18072` seit
            00:34:01 normal.
Ursache:    Der Ausweichpfad, den ich in AP-1.1 eingebaut habe. Der **erhöhte**
            Agent darf `C:\ProgramData\…\singleton.lock` öffnen und hält sie;
            der **normale** darf es nicht, weicht auf `%LOCALAPPDATA%` aus und
            hält seine eigene. Zwei Sperren, zwei Welten, kein gegenseitiges
            Sehen.

            Die Ausweichlösung sollte verhindern, dass ein Rechteproblem eine
            Anlage stilllegt (das war die bewusste Entscheidung zu F-024). Sie
            hat stattdessen ein zweites Schlupfloch aufgemacht. Bei Imst wäre
            das der Normalfall: dort läuft der Agent als SYSTEM, ein Handstart
            daneben fällt genau hinein.
Behebung:   Zweite, unabhängige Absicherung, die nicht an Dateirechten hängt:
            eine Besitzmeldung in der **Zustandsdatenbank**. Sie ist der Ort, an
            dem sich zwei Agenten zwangsläufig treffen — es ist genau die
            Ressource, um die es geht. Wer einen frischen fremden Eintrag
            vorfindet, beendet sich und nennt die fremde Prozessnummer.
            Aufgefrischt bei jedem Durchlauf; nach 90 Sekunden ohne
            Auffrischung ist der Platz frei, ein Absturz blockiert also nichts.
            Die Dateisperre bleibt als erste Verteidigung. Fünf Tests.
Wiederkehr: —
            **Lehre:** Eine Absicherung, die im Fehlerfall „lieber
            weiterlaufen" sagt, braucht eine zweite Absicherung auf einer
            anderen Ebene. Sonst ist der Fehlerfall die Lücke.

## F-032 — Zeitstempel im Verlauf sind um zwei Stunden verschoben
Status:     behoben (16.08.2026)
Gesehen:    15.08.2026, mehrfach — zuletzt beim Nachprüfen der Szenarien
Beleg:      Ein Ereignis mit `occurred_at` = 16.08. 01:32:46 trägt im Text
            `2026-08-15 23:32:46`. Die Protokollzeile nennt Ortszeit, abgelegt
            wird sie als UTC.
Ursache:    Beim Ableiten eines Ereignisses aus einer Protokollzeile wird deren
            Ortszeit ohne Umrechnung als UTC gespeichert. Ereignisse, die der
            Agent selbst erzeugt (Testfoto, Neustart), sind korrekt.
Folge:      Harmlos für den Betrieb, aber jede Nachforschung im Verlauf wird
            unzuverlässig. Eine Abfrage „letzte 25 Minuten" lieferte mir 68
            angebliche frische Fehler, die in Wahrheit zwei Stunden alt waren —
            beinahe hätte ich daraus geschlossen, die Behebung von F-031 habe
            nicht gewirkt.
Behebung:   `_parse_line_time` baut den Zeitpunkt jetzt **ohne** `tzinfo` — das
            ist Ortszeit — und rechnet mit `astimezone` nach UTC um. Der
            Sommerzeit-Versatz kommt damit automatisch richtig heraus, statt
            fest angenommen zu werden. Zwei Tests, für beide Zeilenformate.
Wiederkehr: —

## F-033 — Ein erhöht laufender Agent ist für eine normale Sitzung unsichtbar
Status:     offen (Einschränkung, kein Defekt)
Gesehen:    15.08.2026 nach `ap7_pruefung.ps1`
Beleg:      Vier `python.exe` liefen; von zweien war die Befehlszeile lesbar,
            von den beiden erhöht gestarteten **nicht**. Die übliche Abfrage
            `Where-Object { $_.CommandLine -like "*liftpic_sync*" }` lieferte
            deshalb **null Treffer**, obwohl der Agent lief und im Sekundentakt
            protokollierte. Ich hielt ihn kurzzeitig für abgestürzt.
Ursache:    `Win32_Process.CommandLine` bleibt leer, wenn der fragende Prozess
            nicht mindestens dieselben Rechte hat wie der befragte.
Folge:      Alle Skripte, die Agenten über die Befehlszeile suchen
            (`install_windows_service.ps1`, `restart_service.ps1`,
            `update_liftpic.ps1`, `ap7_pruefung.ps1`), **müssen erhöht laufen** —
            sie tun es, alle vier verlangen Administratorrechte. Für Imst
            wichtig: dort läuft der Agent als SYSTEM, eine nicht erhöhte
            Prüfung würde ihn übersehen und „kein Agent" melden.
Behebung:   Als Einschränkung dokumentiert. Zusätzlich sollte eine Prüfung auf
            `Get-Process -Name python` zurückfallen, wenn die Befehlszeile
            nicht lesbar ist.
Wiederkehr: —

## F-034 — Ungeklärt: zweiter Aufgaben-Treffer bei Szenario 3
Status:     offen, aktuell ohne Auswirkung
Gesehen:    15.08.2026, `ap7_pruefung.ps1`
Beleg:      `[bestanden] 3 - fremd benannte Aufgabe wird gefunden
            (2 Treffer insgesamt)` — erwartet war **ein** Treffer, die Attrappe.
Nachprüfung: Unmittelbar danach: **null** Aufgaben, die den Agenten starten,
            und kein Dienst. Das Aufgabenplaner-Protokoll ist nicht aktiviert,
            also gibt es keinen Nachweis, was der zweite Treffer war.
Deutung:    Entweder wurde die Attrappe während der Registrierung doppelt
            aufgezählt, oder es gab eine Alt-Aufgabe, die seither verschwunden
            ist. **Nicht belegbar, deshalb nicht als geklärt abgehakt.**
Folge:      Zurzeit keine — es existiert nachweislich kein zweiter Startweg.
            Vor dem Imst-Rollout dort dasselbe prüfen: es darf genau eine
            Startart geben.
Wiederkehr: —

## F-031 — Ein Deploy sperrte alle Automaten aus `liftpic-config` aus
Status:     offen — **braucht einen Handgriff im Supabase-Dashboard**
Gesehen:    15.08.2026 abends, unmittelbar nach dem Ausrollen von AP-5
Beleg:      `curl` gegen die Function mit einem Gerätetoken:
            `HTTP 401 {"code":"UNAUTHORIZED_INVALID_JWT_FORMAT"}`
            Das Tor weist ab, **bevor** die Function läuft.
Ursache:    Der Deploy über die Programmierschnittstelle (MCP) setzt
            `verify_jwt` **immer auf `true`** und ignoriert die Vorgabe aus
            `supabase/config.toml`. Dreimal versucht — mit funktionseigener
            `config.toml` und mit der Datei an der Repo-Stelle —, beides
            wirkungslos. Die Automaten melden sich mit einem Gerätetoken, das
            kein JWT ist.
Umfang:     Nur `liftpic-config`. Geprüft: `liftpic-ingest-begin`,
            `liftpic-ingest-commit`, `liftpic-status` und `liftpic-assets`
            stehen unverändert auf `verify_jwt = false`. Foto-Upload,
            Herzschlag und Asset-Abgleich liefen durchgehend weiter — Imst
            meldete währenddessen normal (1145 Fotos, Warteschlange 0).
            Ausgefallen sind Fernkonfiguration und Kopplung.
Behebung:   Im Dashboard: Edge Functions → `liftpic-config` → Settings →
            „Verify JWT" aus. Oder mit der Befehlszeile:
            `supabase functions deploy liftpic-config --no-verify-jwt`
Wiederkehr: —

**Regel, die daraus folgt:** Die vier Automaten-Functions
(`liftpic-config`, `liftpic-status`, `liftpic-ingest-begin`,
`liftpic-ingest-commit`, `liftpic-assets`) dürfen **nicht** über die
Programmierschnittstelle ausgerollt werden — sie verwenden alle
Gerätetokens statt JWTs, und jeder Deploy auf diesem Weg sperrt sie zu.
Nur über die Supabase-Befehlszeile mit `--no-verify-jwt`.

Ein Rückrollen auf die vorherige Fassung hilft **nicht**: jeder Deploy über
denselben Weg setzt den Schalter erneut.

## F-024 — Der Doppelstart-Schutz ist seit dem 08.08.2026 wirkungslos
Status:     behoben (15.08.2026, AP-1.1) — **die Ursache besteht fort**
            Die Rechte an `C:\ProgramData\liftpic-sync\singleton.lock` sind
            unverändert falsch; der Agent weicht jetzt lediglich aus. Wer die
            Datei repariert (`icacls`), stellt den systemweiten Schutz wieder
            her — der Ausweichpfad schützt nur gegen zwei Agenten **desselben
            Benutzers**, nicht gegen Aufgabe (SYSTEM) neben Handstart.
Gesehen:    15.08.2026, bei der Erkundung vor dem Imst-Rollout
Beleg:      `C:\ProgramData\liftpic-sync\singleton.lock` gehört `NT AUTHORITY\SYSTEM`,
            `BUILTIN\Users` hat nur `ReadAndExecute`. `LastWriteTime` ist der
            08.08.2026 13:58:50 — der einzige Start, bei dem die Datei je
            angefasst wurde, bei über 20 dokumentierten Starts seither.
            `grep "another liftpic-sync instance"` über alle Protokolle: 0 Treffer.
            Die Sperre hat noch nie jemanden abgewiesen.
Ursache:    `cli.py:71-72` fängt den `PermissionError` mit
            `except OSError: return True  # proceed unlocked` ab und
            protokolliert **nichts**. Die Datei wurde einmal von SYSTEM
            angelegt, danach lief der Agent als Benutzer.
Behebung:   Drei benannte Zustände statt geratener `None`/`True`-Werte:
            `gesperrt`, `belegt`, `ungesichert`. Bei einem Rechteproblem wird
            auf `%LOCALAPPDATA%` ausgewichen; scheitert auch das, läuft der
            Agent weiter — aber mit `log.error` und einem Verlaufseintrag
            „Doppelstart-Schutz nicht aktiv". Die Sperre gilt jetzt auch für
            `scan-once` und `assets`, die beide vollwertige Zweitagenten sind.
            Sieben Tests in `tests/test_einmaligkeit.py`.
Beleg nach
der Behebung: 15.08.2026 19:42 am Testrechner — Ausweichpfad greift auf der
            echten kaputten Rechtelage, der zweite Agent wird abgewiesen
            (`pid=5868`, Exit 0), der erste (`pid=12012`) läuft unberührt.
Wiederkehr: —
            **Wichtig:** Die Sperre darf jetzt ausfallen, ohne den Betrieb zu
            stoppen. Die eigentliche Last tragen deshalb F-025 (atomarer
            Anspruch auf Uploads und Aufträge) — die wirken auch ohne Sperre.

## F-025 — Kein atomarer Anspruch auf Arbeit
Status:     offen (AP-1.3, AP-1.4)
Gesehen:    15.08.2026, Erkundung
Beleg:      `state.py:338-349` `due_uploads` ist ein reines `SELECT`; der Status
            wechselt erst nach dem fertigen Upload. Zwei Instanzen selektieren
            garantiert dieselben Zeilen und laden jedes Foto zweimal hoch.
            `service.py:161` hält die Auftrags-Quittung nur im Hauptspeicher —
            beide Instanzen führen denselben Neustart aus.
Ursache:    Entwurf ging von genau einem Agenten aus und verließ sich dafür auf
            die Sperre aus F-024.
Behebung:   offen — Beanspruchen in einer Transaktion mit Verfallszeit.
Wiederkehr: —

## F-026 — Doppelbetrieb ist im Nachhinein nicht nachweisbar
Status:     behoben (15.08.2026, AP-1.2)
Gesehen:    15.08.2026
Beleg:      `logging_setup.py:17` — Format ohne `%(process)d`. In 11 MB
            Protokoll ist kein Verdachtsfall entscheidbar. Deshalb wurde die
            Störung am Imster Automaten monatelang als „401-Problem" gelesen.
Ursache:    Prozessnummer nie ins Format aufgenommen.
Behebung:   `pid=%(process)d` im Format. Test prüft, dass die eigene
            Prozessnummer in der Datei landet.
Wiederkehr: —
            Dies war die Voraussetzung für alles Übrige in AP-1: ohne die
            Prozessnummer wäre keine der Änderungen überprüfbar gewesen.

## F-027 — Der Asset-Abgleich legt endlos identische Sicherungen an
Status:     offen (AP-4)
Gesehen:    14.08.2026, aufgefallen 15.08.2026
Beleg:      `backups/assets`: 121 Ordner, 7,5 MB, davon **119 byte-gleiche**
            Kopien derselben `hintergrund.png` (MD5 `1429f632…`), im
            31-Sekunden-Takt. Protokoll: 118 Zyklen mit `failed: 1` und
            `asset 'viewer_background' is in use by the viewer`.
Ursache:    `asset_sync.py:140-141` — Sicherung läuft **vor** dem Schreiben, das
            Schreiben scheitert an der vom Verkaufsprogramm gehaltenen Datei,
            der Zustand wird nie „aktuell", beim nächsten Abruf beginnt alles
            von vorn. `restart_needed` wird gesetzt (`:91`) und **nirgends
            gelesen**.
Behebung:   offen.
Wiederkehr: —

## F-028 — Der Installer würde den alten Stand installieren
Status:     offen (AP-6)
Gesehen:    15.08.2026
Beleg:      `install_liftpic_sync_bootstrap.ps1:4` zieht fest
            `refs/heads/main`; dort steht `d833ec0` vom 08.08. Die Härtung liegt
            auf `haertung-rollout-20260815` (23 Dateien, +5691/−122).
Ursache:    Kein Tag, kein Release, `agent_version` konstant `0.1.0` — am Server
            ist nicht ablesbar, welcher Stand auf einem Automaten läuft.
Behebung:   offen — Fallback-Tag **vor** dem Merge, dann Merge nach `main`.
Wiederkehr: —

## F-029 — Dienst und Aufgabe tragen denselben Namen
Status:     offen (AP-1.8)
Gesehen:    15.08.2026
Beleg:      `install_windows_service.ps1:14-33` legt je nach Vorhandensein von
            `nssm.exe` einen **Dienst** oder eine **Aufgabe** `LiftpicSync` an.
            Beide liegen in getrennten Namensräumen und können gleichzeitig
            existieren; das Aufräumen sucht nur per `Get-Service`.
Ursache:    Zwei Startwege, ein Name, keine gegenseitige Prüfung.
Behebung:   offen. Das ist der Weg, auf dem echter Doppelbetrieb entsteht.
Wiederkehr: —

## F-030 — Die Vorgabe-Protokollmuster machen einen Automaten halb blind
Status:     offen (AP-2)
Gesehen:    15.08.2026
Beleg:      Imst (`pcneu`) meldet `operational_devices` als **leere Liste**,
            `camera_status`/`coin_status`/`printer_status`/`terminal_status`
            allesamt `null`, und hat **null** Ereignisse im Verlauf — bei 1145
            Fotos am Tag.
Ursache:    `config.py:176-187` deckt weder `samuel_neu` (Verkaufsprogramm,
            Münzprüfer) noch `liftpic-sync\logs` (der Uploader selbst) noch
            `terminal` ab. Nur eine handgepflegte `.env` repariert das.
Behebung:   offen.
Wiederkehr: —

---

# Behoben

## F-009 — Ein Testfoto landete im Park eines fremden Kunden
Status:     behoben (15.08.2026, `liftpic-ingest-begin` v4 + Registrierung)
Gesehen:    15.08.2026 vormittags
Beleg:      Foto vom Testrechner erschien unter `imster-bergbahnen`, samt
            Zählung im Tagesumsatz.
Ursache:    Die Bremse verglich die Nummer im Dateinamen gegen
            `settings.customer_code` (1234) statt gegen die **Registrierung in
            der Datenbank**. Registriert war nur 7623, also griff die
            Rückfallregel über den Bucket — und der zeigt auf Imst.
Behebung:   1234 für den Testrechner registriert, serverseitige Sperre in
            `liftpic-ingest-begin` v4, Prüfpunkt „Abholcode" im Dashboard.
            `customer_code_registered: null` heißt ausdrücklich „nicht prüfbar",
            nicht „in Ordnung".
Wiederkehr: —

## F-010 — Der zweite Schreiber auf den Tagesumsatz war übersehen
Status:     behoben (15.08.2026, Migration `20260815060000`)
Gesehen:    15.08.2026, vom Nutzer bemerkt: „bei Imst steht jetzt auch 5 Euro"
Beleg:      Nach der Korrektur an `resync_recent_photo_sales` stand der
            Testfoto-Verkauf weiterhin in `park_photo_sales_daily`.
Ursache:    Es gibt **zwei** Schreiber. `rollup_kiosk_photo_sale()` zählt sofort
            beim Einfügen und ignorierte `is_test`.
Behebung:   Beide Funktionen überspringen Testfotos, die zwei falschen Zeilen
            entfernt.
Wiederkehr: —

## F-013 — Eine Veröffentlichung drehte 23 Dateien zurück
Status:     behoben (15.08.2026, `8a0ed9c`)
Gesehen:    15.08.2026, Frontend zeigte die neuen Knöpfe nicht
Beleg:      Commit `7edf8db` „Updated config.toml" — tatsächlich 23 Dateien,
            **+258/−4136**. Entfernt: `AutomatHealth` (−1276),
            `AutomatBranding` (−715), `ZahlungsUebersicht` (−395), zwei
            Functions, sechs Migrationen ab dem 08.08.
Ursache:    bolt.new hält eine eigene, ältere Kopie des Repos. Der
            Publish-Klick lieferte diese aus **und** schrieb sie nach `main`.
Behebung:   Inhalt aus `b1d461c` wiederhergestellt, ohne Historie zu
            überschreiben.
Wiederkehr: —
            **Achtung:** Der Auslöser besteht fort. Vor jedem Publish in
            bolt.new muss dort der GitHub-Stand geholt werden.

## F-014 — Eine leere Geräteliste ergab „Alles in Ordnung"
Status:     behoben (15.08.2026, `bf0645e`)
Gesehen:    15.08.2026, bei der Prüfung der Imst-Verträglichkeit
Beleg:      Imst meldet `operational_devices` als leere Liste; die
            Zusammenfassung fiel auf Grün durch.
Ursache:    Kein Zweig für „kein einziger Eintrag".
Behebung:   Eigener neutraler Zustand „Keine Gerätedaten".
Wiederkehr: —

## F-015 — „Device lost" galt nicht als Störung
Status:     behoben (15.08.2026, `b8bddc5`)
Gesehen:    15.08.2026, Kamera seit 10:11 weg, Kachel grün
Beleg:      `15.08.2026 10:11:42\tDevice lost` — nackte Zeile, kein
            Protokoll-Rang, kein Reizwort.
Ursache:    `PROBLEM_RE` kannte `communication lost`, aber nicht `device lost`.
            `PLAIN_EXPLANATION` kannte den Fall längst und formulierte ihn
            verständlich — nur die Einstufung fehlte.
Behebung:   Aufgenommen, Test mit der wortgleichen Zeile.
Wiederkehr: —

## F-016 — Der laufende Prozess entschärfte den Geräteverlust
Status:     behoben (15.08.2026, `e034c57`)
Gesehen:    15.08.2026, unmittelbar nach F-015
Beleg:      Kachel „degraded" mit dem Text
            `Programm laeuft, meldet aber: … Device lost`.
Ursache:    `_reconcile` stuft „down" auf „degraded" herab, wenn der Prozess
            läuft — richtig für einen Vorschaufehler des Verkaufsprogramms,
            falsch für die Kamera: 3GerTis läuft weiter und nimmt trotzdem nie
            wieder ein Bild auf.
Behebung:   `PROZESS_HILFT_NICHT` nimmt solche Zeilen von der Herabstufung aus.
            Test hält beide Seiten fest.
Wiederkehr: —

## F-017 — Die Kamera konnte sich nicht wieder entwarnen
Status:     behoben (15.08.2026, `8c02b93`)
Gesehen:    15.08.2026, vom Nutzer bemerkt: „wieso steht da immernoch
            Kamera nicht erreichbar?"
Beleg:      Kamera um 11:38:55 wieder verbunden, Kachel weiter rot mit dem Fund
            von 10:11:42.
Ursache:    Kehrseite von F-015: „Device lost" wurde zur Störung, aber die
            Zeile, mit der sich die Kamera zurückmeldet, zählte in `OK_RE` nicht
            als Entwarnung. Die Kamera wäre **für immer** rot geblieben.
Behebung:   `(from cam)` und `image has been saved` aufgenommen. `(from ini)`
            bleibt bewusst draußen — das erscheint auch ohne Kamera. Zwei Tests.
Wiederkehr: —
            **Lehre:** Wer eine Störung neu erkennt, muss im selben Zug die
            Entwarnung mitbauen.

## F-018 — Testfoto lief 76 Sekunden nach dem Kamera-Neustart ins Leere
Status:     behoben (15.08.2026, `fe474ca`)
Gesehen:    15.08.2026 11:33
Beleg:      Neustart 11:32:27, Kamera verbunden erst 11:38:55 — 6,5 Minuten.
            Der erste Durchgang (Neustart 11:26:31, Foto 11:27:32) hatte
            funktioniert.
Ursache:    Der Neustart meldet Erfolg, sobald der Prozess läuft — nicht, sobald
            die Kamera da ist.
Behebung:   `kamera_ist_verbunden()` liest das Kameraprotokoll von hinten; der
            Auslöser unterscheidet „gerade neu gestartet, bitte warten" von
            „länger weg, erst neu starten". Vier Tests.
Wiederkehr: —

## F-019 — Der Münzbestand wurde als Messung ausgegeben
Status:     behoben (15.08.2026, `cf52630`)
Gesehen:    15.08.2026, vom Nutzer bemerkt: „im Gerät sind gar keine drin"
Beleg:      60,65 € mit Stand „15.08. 12:00", tatsächlich seit dem 13.08. 23:00
            unverändert — 37 Stunden.
Ursache:    `CoinStats.txt` ist die Buchführung des Verkaufsprogramms, zweimal
            täglich weggeschrieben, auch wenn sich nichts rührt.
Behebung:   `unveraendert_seit` und `muenzpruefer_arbeitet()`; ein nicht
            gesicherter Betrag wird im Dashboard durchgestrichen.
Wiederkehr: —

## F-020 — Normale Startmeldungen galten als Münzprüfer-Defekt
Status:     behoben (15.08.2026, `f9e21ac`)
Gesehen:    15.08.2026 17:03, nachdem der Nutzer Münzen eingeworfen hatte
Beleg:      `Coin changer/validator reset` steht bei **jedem** Start;
            `Payment unit disabled` ist der Ruhezustand („gesperrt durch
            Automaten" am Display). Beides wurde als Defekt gewertet.
Ursache:    `_MUENZ_FEHLER` war zu weit gefasst.
Behebung:   Nur noch Münzstau, Sensorproblem und „Not found (while running)"
            gelten als Störung. Vier Tests.
Wiederkehr: —
            **Beinahe-Schaden:** hätte an einem völlig gesunden Automaten
            „Prüfer arbeitet nicht" angezeigt — bei Imst genauso.

## F-021 — „Invalid operator auth token" statt „nicht angemeldet"
Status:     behoben (15.08.2026, `eff9979`)
Gesehen:    15.08.2026, auf localhost
Beleg:      `sharedEdgeFunctions.ts:46`
            `Bearer ${session?.access_token ?? EXTERNAL_SUPABASE_ANON_KEY}`
Ursache:    Ohne Sitzung ging der anonyme Schlüssel des **geteilten** Projekts
            an eine Function, die gegen das **Operator**-Projekt prüft.
Behebung:   Ohne Sitzung wird nicht mehr losgeschickt.
Wiederkehr: —

## F-004 / F-005 — Neustart beendete das Verkaufsprogramm und startete es nie
Status:     behoben (14.08.2026)
Beleg:      `TypeError: argument of type 'NoneType' is not iterable` —
            `tasklist` lieferte ohne Konsole `stdout=None`.
Ursache:    Anhalten und Starten hingen in einem gemeinsamen `try`.
Behebung:   `_ausgabe()` liest Bytes und verträgt `None`; Anhalten und Starten
            sind getrennt abgesichert.
Wiederkehr: —
            **Das ist der teuerste Fehlertyp:** keines dieser Programme steht im
            Autostart, es startet also niemand nach.

## F-006 / F-007 — Zwei Fehler in der Zahlungsauswertung
Status:     behoben (14.08.2026)
Beleg:      `Tagesabschluss` wurde als Kartenzahlung gezählt; das Druckprofil
            `::3` als 3,00 € gelesen — in **1322 von 1330** Zeilen.
Behebung:   Beide mit Tests an echten Daten.
Wiederkehr: —

## F-023 — „Preis 0,00 heißt Gratis-Betrieb" war eine Fehldeutung
Status:     behoben (Erkenntnis, 15.08.2026)
Gesehen:    15.08.2026 abends
Beleg:      Imsts letzte Statistikzeile lautet
            `15.08.2026 17:52:53::…\44674.jpg::3||2||0,00` — bei 5 € pro Foto
            und 142 Verkäufen am Tag.
Ursache:    Der Preis wird in dieser Programmversion generell als `0,00`
            geschrieben; der Umsatz entsteht aus `parks.price_per_photo_cents`.
Behebung:   Keine Codeänderung nötig — die Auswertung nimmt den Preis ohnehin
            aus der Preisliste, wenn keiner vermerkt ist. Hier festgehalten,
            damit die Fehldeutung nicht wiederkehrt.
Wiederkehr: —

## F-022 — Falsches USB-Gerät für den Münzprüfer gehalten
Status:     behoben (Erkenntnis, 15.08.2026)
Beleg:      `VID_24AE` ist ein **Rapoo-Funkempfänger** für Tastatur und Maus.
            Der Münzprüfer ist `NRI-USB-HID-DEV-01`, `VID_155D:PID_0002`.
Ursache:    Von der Häufung mehrerer HID-Teilgeräte auf den Hersteller
            geschlossen, statt den Produktnamen zu lesen.
Behebung:   Hersteller- und Busnamen auslesen statt Kennungen zu raten.
Wiederkehr: —

## F-003 — PowerShell zerstörte Umlaute in einer Quelldatei
Status:     behoben (14.08.2026)
Beleg:      `Get-Content`/`Set-Content` schrieben doppeltes UTF-8 mit BOM.
Behebung:   Datei repariert. **Regel seither: Dateiänderungen nur mit den
            Bearbeitungswerkzeugen, nie über die Konsole.**
Wiederkehr: —
            Verwandt: derselbe Mechanismus steckt noch im Installer
            (`Set-EnvValue`, ASCII) → AP-1.7.

## F-001 / F-002 / F-008 / F-011 / F-012 — kleinere Fehler
Status:     behoben (13.–15.08.2026)
- F-001 Statistik-E-Mail wurde als Ausfall des Verkaufsprogramms gemeldet →
  Zuordnung nach Inhalt plus Nebenfunktionen eingeführt.
- F-002 Klartext und Rohtext standen im selben Feld → doppelt angezeigt.
  Getrennt in `plain` und `detail`.
- F-008 `NameError: name 'Path' is not defined` in `service.py` — ein
  Import-Test hätte es nicht gefunden, nur ein Test, der die Funktion **aufruft**.
- F-011 Falsches Dashboard-Repo angenommen; per Dateivergleich widerlegt
  (0 von 20 gemeinsamen Dateien identisch).
- F-012 Beinahe `priceHistory` aus einer Function entfernt, weil die
  ausgelieferte Fassung neuer war als die Repo-Kopie.
Wiederkehr: —
