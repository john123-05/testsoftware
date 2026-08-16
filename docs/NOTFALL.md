# Notfall — wie man einen Automaten zurückholt

Für den Fall, dass etwas nicht läuft und jemand schnell handeln muss. Wer
diese Datei liest, hat vermutlich wenig Zeit — deshalb zuerst das Wichtigste.

---

## Der Rückweg in einem Befehl

PowerShell **als Administrator** auf dem betroffenen Automaten:

```
$zip="$env:TEMP\lp.zip"; $ziel="$env:TEMP\lp"; Remove-Item $ziel -Recurse -Force -ErrorAction SilentlyContinue; Invoke-WebRequest -UseBasicParsing -OutFile $zip "https://github.com/john123-05/testsoftware/archive/refs/tags/v0.1.0-imst-stand.zip"; Expand-Archive $zip $ziel -Force; $src=(Get-ChildItem $ziel -Directory)[0].FullName; powershell -ExecutionPolicy Bypass -File "$src\scripts\update_liftpic.ps1" -Tag v0.1.0-imst-stand
```

Das setzt den Automaten auf den Stand vom 08.08.2026 zurück — den, der vor
der Härtung monatelang produktiv lief. Es koppelt **nicht** neu, sichert
vorher, und die Kopplung bleibt erhalten (sie hängt am Datensatz auf dem
Server und am Gerätetoken in der `.env`, nicht am Programmstand).

**Warum das sicher ist:** der Tag wurde am 15.08.2026 geprüft, nicht nur
gesetzt — Archiv heruntergeladen, hineingesehen: 105 KB, 92 Einträge, der
alte Kern vollständig, keine einzige Datei der Härtung.

### Oder aus einer örtlichen Sicherung

Jeder Lauf von `update_liftpic.ps1` legt vorher eine an und nennt am Ende
ihren Pfad. Sie enthält `.env`, die Zustandsdatenbank samt `-wal`, die
exportierte Autostart-Aufgabe und den Programmstand.

```
powershell -ExecutionPolicy Bypass -File "$src\scripts\rollback_lokal.ps1" -Sicherung "C:\liftpic\sicherung-liftpic-sync-JJJJMMTT-HHMMSS"
```

Vorhandene Sicherungen findet man mit:
```
Get-ChildItem C:\liftpic -Directory -Filter "sicherung-liftpic-sync-*" | Sort-Object Name -Descending
```

---

## Zuerst nachsehen, dann handeln

Bevor irgendetwas zurückgesetzt wird — dieser Befehl sagt in zehn Sekunden,
was los ist. Er ändert **nichts** und darf im laufenden Betrieb laufen:

```
$zip="$env:TEMP\lp2.zip"; $ziel="$env:TEMP\lp2"; Remove-Item $ziel -Recurse -Force -ErrorAction SilentlyContinue; Invoke-WebRequest -UseBasicParsing -OutFile $zip "https://github.com/john123-05/testsoftware/archive/refs/heads/main.zip"; Expand-Archive $zip $ziel -Force; $s=(Get-ChildItem $ziel -Directory)[0].FullName; powershell -ExecutionPolicy Bypass -File "$s\scripts\anlagenpruefung.ps1"
```

Er beantwortet: Kommt der Uploader nach einem Stromausfall wieder? Läuft
genau einer? Was läuft sonst? Lebt er? Gibt es eine Sicherung?

---

## Häufige Lagen und was zu tun ist

| Lage | Was tun |
|---|---|
| **Es läuft kein Agent** | `anlagenpruefung.ps1` zeigt, ob es einen Autostart gibt. Fehlt er: `install_windows_service.ps1` als Administrator. |
| **Es laufen mehrere Agenten** | Sollte seit v0.2.1 nicht mehr vorkommen (Datei- und Datenbanksperre). Falls doch: `install_windows_service.ps1` räumt die zweite Startart ab. |
| **Uploads stocken** (`queue_count` wächst) | Zuerst Internet prüfen. Dann im Protokoll `logs\liftpic-sync.log` nach `ERROR` sehen. Bei `401`: der Gerätetoken passt nicht — siehe unten. |
| **Dauernd 401** | Meist zwei Agenten, die sich das Token gegenseitig entwerten. Seit v0.2.1 gibt der Agent nach zehn Versuchen auf und meldet es. Ursache beheben, nicht neu koppeln. |
| **Nach einem Update ist alles anders** | Zurück mit dem Befehl ganz oben. Erst danach in Ruhe die Ursache suchen. |
| **Automat steht, Verkaufsprogramm läuft nicht** | Es steht in **keinem** Autostart. Von Hand starten. Ein fehlgeschlagener Neustart heilt sich nicht von selbst. |

---

## Was man auf keinen Fall tun sollte

- **Nicht neu koppeln, um ein Problem zu lösen.** Das Koppeln überschreibt
  16 Schlüssel in der `.env` mit Serverwerten und harten Vorgabepfaden. Eine
  Anlage mit eigenen Ordnern verliert dabei ihre Konfiguration.
  `update_liftpic.ps1` koppelt bewusst nicht, solange ein Token da ist.

- **Nicht den Bootstrap-Installer für ein Update benutzen.** Er ist ein
  Einrichtungswerkzeug: er verlangt immer einen Pairing-Code, koppelt
  bedingungslos neu und hält den laufenden Agenten nicht an. Für bestehende
  Anlagen ist `update_liftpic.ps1` da.

- **Die fünf Automaten-Functions nicht über die Programmierschnittstelle
  ausrollen** (`liftpic-config`, `liftpic-status`, `liftpic-ingest-begin`,
  `liftpic-ingest-commit`, `liftpic-assets`). Jeder Deploy auf diesem Weg
  setzt `verify_jwt` auf `true` und sperrt damit **alle** Automaten aus — sie
  melden sich mit einem Gerätetoken, das kein JWT ist. Nur über die
  Supabase-Befehlszeile mit `--no-verify-jwt`. Siehe F-031 im Fehlerjournal.

- **Dateien nicht über `Set-Content` bearbeiten.** Windows PowerShell 5.1
  schreibt dabei eine Bytefolge-Markierung und zerstört Umlaute. Hat schon
  zweimal Schaden angerichtet (F-003, und eine unbrauchbare `pyproject.toml`).

---

## Woran man von außen sieht, ob eine Anlage lebt

Ohne Fernzugriff, allein über die Datenbank (Supabase, geteiltes Projekt
`kvpcwlcfgmsmarjtwpsx`):

```sql
select machine_id,
       round(extract(epoch from (now() - last_seen_at))) as herzschlag_vor_sek,
       last_status->>'agent_version' as version,
       last_status->>'queue_count'   as warteschlange,
       last_status->>'photos_taken_today' as fotos_heute
from liftpic_machine_configs
where is_active;
```

Herzschlag unter 120 Sekunden und leere Warteschlange heißt: es läuft.

Die letzten Ereignisse einer Anlage:

```sql
select occurred_at at time zone 'Europe/Vienna' as zeit, severity, summary
from liftpic_machine_health_events
where machine_id = 'pcneu'
order by id desc limit 20;
```

---

## Stände und Tags

| Tag | Was |
|---|---|
| `v0.1.0-imst-stand` | Der Stand vor der Härtung, 08.08.2026. **Der Rückweg.** |
| `v0.2.0-haertung` | Erste gehärtete Fassung |
| `v0.2.1` | Zeitstempel und Besitzmeldung behoben — **aktuell im Einsatz** |

Repo: `https://github.com/john123-05/testsoftware`
Der Installer zieht `main`; die Skripte nehmen `-Tag`.
