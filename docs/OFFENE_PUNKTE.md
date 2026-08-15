# Offene Punkte

Stand 14.08.2026. Alles hier ist bekannt, bewusst offen gelassen und beschrieben,
damit es niemand neu herausfinden muss.

---

## 1. Code-Vorschrift: nur Druckprofil 1 wird gelesen

**Wo:** `viewer_settings.py`, `Settings.with_viewer_recipe()`

Der Uploader liest `CustomerNumber` und `CodePositionsInFilename` aus
`samuel_neu\Settings.xml`, damit der hochgeladene Code exakt dem entspricht, den
Samuel in den QR druckt. Gelesen wird aber **nur Profil 1**.

Samuel hat drei Druckprofile mit eigenen Werten:

| Profil | Kundennummer | Stellen der Bildnummer |
| --- | --- | --- |
| 1 | `CustomerNumber` | `CodePositionsInFilename` |
| 2 | (keine eigene) | (keine eigene) |
| 3 | `CustomerNumber3` = 1706 | `CodePositionsInFilename3` = 1,2,3,4 |

Welches Profil gilt, haengt vom aktiven Drucker ab. Das laesst sich von aussen
nicht zuverlaessig erraten - deshalb bewusst der dokumentierte Standard.

**Zu tun:** Klaeren, welche Kunden ein anderes Profil als 1 fahren. Falls ja,
braucht es einen Weg, das Profil zu bestimmen - am ehesten ueber `PrinterName`
gegen den tatsaechlich eingestellten Windows-Drucker. Bis dahin gilt: Bei einem
Kunden mit Profil 3 waere der berechnete Code falsch.

---

## 2. Der Bucket `liftpic-assets` nimmt keine Uploads an

**Wo:** `operator-liftpic-assets` (Edge Function), Konstanten `BUCKET` /
`PATH_PREFIX`

Seit der Umstellung des Projekts auf die neuen API-Schluessel (`sb_secret_*`)
scheitert **jeder** Schreibzugriff aus der Function-Umgebung auf diesen Bucket
mit HTTP 400 / `"The related resource does not exist"`.

Ausgeschlossen wurde: Datentyp (Bytes/Blob/ArrayBuffer), `upsert`, Pfadtiefe,
public-Flag, Groessen- und MIME-Beschraenkung. Ein frisch ueber die API
angelegter Bucket verhaelt sich genauso, `daten` ebenfalls. Nur `test`
funktioniert - dort liegen auch die Gaestefotos.

Deshalb schreiben Automaten-Dateien vorerst nach `test/liftpic-assets/...`.
Damit sie nicht als Gaestefotos gezaehlt werden, ueberspringt
`handle_new_storage_object()` dieses Praefix (Migration
`20260814090000_asset_uploads_are_not_photos.sql`).

**Zu tun:** Bei Supabase melden. Dass Storage bei einem existierenden Bucket ein
stummes `404 InvalidRequest` liefert statt eines verwertbaren Fehlers, ist ein
Plattformproblem und kann uns anderswo genauso treffen. Ist es geloest, genuegt
das Zuruecksetzen der beiden Konstanten.

---

## 3. Imst laeuft auf einem aelteren Agent-Stand

Der Automat `pcneu` hat eine eigene Kopie des Agents. Alles, was am 14.08.2026
entstanden ist - Viewer-Neustart, Health-Ueberwachung, Offline-Puffer, Lesen der
Code-Vorschrift - laeuft **nur auf dem Testrechner**.

**Zu tun:** Vor einem Rollout nach Imst pruefen:

- Stimmt `CustomerNumber` in Imsts `Settings.xml` mit dem `CUSTOMER_CODE` des
  dortigen Uploaders ueberein? Aus den echten Claim-Codes ist bekannt, dass
  gedruckt `2734` verwendet wird. Weicht der Uploader ab, ist das die Ursache
  der "Foto nicht gefunden"-Faelle - und mit Punkt 1 dieser Liste behoben.
- `VIEWER_EXE` und `VIEWER_RESTART_ENABLED` setzen, sonst bleibt der
  Neustart-Knopf dort wirkungslos (er meldet das sauber, tut aber nichts).
- `OPERATIONAL_LOG_GLOBS` auf die dort tatsaechlich lebenden Logs anpassen.

---

## 4. Was "Speed" im Claim-Code wirklich ist

Die Migration `20260716130000_add_safe_speed_ignoring_fallback.sql` beschreibt
die vier verworfenen Stellen als "a 4-digit slot meant for a live speed reading".
**Das stimmt nicht.** Nachgerechnet an echten Imst-Codes:

    Code 2373186874102025  ->  Kunde 2734, Datum 13.08.2026, Bildnummer 1875

Der Code besteht aus Kundennummer, Datum und Bildnummer - eine Geschwindigkeit
kommt darin ueberhaupt nicht vor. Die vier Stellen, die der Fallback verwirft
(1-basiert 3, 6, 11, 16), sind `Z[0]` bis `Z[3]`: die **komplette Bildnummer**.

Das erklaert, warum der Fallback praktisch nie greift - ohne Bildnummer bleiben
nur Kunde und Datum, und an einem Tag mit 1.104 Aufnahmen ist das nie eindeutig.

Wichtiger: Eine Bildnummer ist deterministisch, kein Messwert. Eine Abweichung
hat eine benennbare Ursache und ist damit behebbar.

**Zu tun:** Kommentar in der Migration richtigstellen, damit niemand weiter nach
einem Sensorproblem sucht. Und die gescheiterten Claims gegen die hochgeladenen
Fotos halten: Weicht die Bildnummer konstant ab, ist es ein Off-by-One in einer
der beiden Berechnungen; weicht sie unregelmaessig ab, ist es ein Zeitproblem -
am ehesten der naechtliche Zaehler-Reset.

---

## 5. 3GerTis verbindet sich nach Kameraverlust nicht neu

**Wo:** `C:\liftpic\3GerTis\3gertis.ini`, Eintrag `restart_if_lost=0`

Am 10.08.2026 um 20:27 steht `Device lost` in `3gerlog.txt`. Seitdem kam keine
Aufnahme mehr. Das Programm laeuft weiter und sieht im Task-Manager gesund aus,
hat aber keine Kamera mehr - und versucht wegen `restart_if_lost=0` auch keinen
neuen Verbindungsaufbau.

Hintergrund in `3GERTIS.md`.

**Zu tun:** Entscheiden, ob `restart_if_lost=1` gesetzt werden soll. Dafuer
spricht, dass eine kurze Netzwerkstoerung sonst einen ganzen Betriebstag kostet.
Dagegen spricht, dass der Wert bewusst auf 0 stehen koennte, etwa weil ein
Reconnect-Versuch bei laufender Aufnahme frueher Probleme gemacht hat. Das weiss
nur, wer die Anlage aufgebaut hat. **Hier wurde nichts umgestellt** - die
Ueberwachung meldet den Zustand inzwischen aber sauber.

---

## 6. QR-Code aus dem Dashboard steuern - GEPLANT, NICHT GEBAUT

**Wunsch:** Der Betreiber soll im Dashboard sagen koennen "QR-Code an" oder
"QR-Code aus" und den Link setzen, der sich beim Scannen oeffnet.

**Alles noetige ist bereits vorhanden** - in `samuel_neu\Settings.xml`:

```xml
<EnableQrCode>true</EnableQrCode>
<QrCodeBeginningString>www2.liftpictures.de/jpeg4web/frame/preview.php?code=</QrCodeBeginningString>
<QrCodeEndingString></QrCodeEndingString>
<QrCodeSize>12</QrCodeSize>          <!-- mm -->
<ShowQrCodeOnPreview>true</ShowQrCodeOnPreview>
```

Der gescannte Link ist `QrCodeBeginningString` + Abholcode + `QrCodeEndingString`.

### Warum es noch nicht gebaut ist

Der Agent liest `Settings.xml` heute **absichtlich nur** (siehe Kopfkommentar in
`viewer_settings.py`). Sie gehoert dem Verkaufsprogramm, und eine
Konfigurationsdatei, die zwei Programme schreiben, ist genau die Sorte Problem,
die nachts um drei zuschlaegt. Aus dem Dashboard schreiben zu duerfen ist eine
echte Aenderung dieser Zusage - deshalb bewusst vertagt statt nebenbei erledigt.

### Wie es gebaut werden muss

1. **Nur gezielt einzelne Tags ersetzen**, per Regex wie beim Lesen. Die Datei
   ist ueber Jahre von Hand gepflegt und **nicht wohlgeformt** - sie mit einem
   XML-Parser neu zu schreiben wuerde Kommentare, Einrueckung und womoeglich
   kaputte Stellen umbauen, die das Verkaufsprogramm heute toleriert.
2. **Feste Allowlist im Agent**, nicht vom Server bestimmt - dieselbe Regel wie
   bei den Neustart-Zielen: der Server nennt einen Schluessel, der Automat
   entscheidet, was das ist. Erlaubt sind ausschliesslich:
   `EnableQrCode`, `QrCodeBeginningString`, `QrCodeEndingString`, `QrCodeSize`.
3. **Werte pruefen, bevor geschrieben wird.** `EnableQrCode` nur `true`/`false`,
   `QrCodeSize` eine Zahl in einem sinnvollen Bereich, der Link auf `https://`
   oder `www.` und ohne Zeichen, die die XML-Struktur zerreissen (`<`, `>`, `&`).
4. **Sicherung vor jedem Schreiben**, mit Zeitstempel im Namen, wie bei
   `Settings.xml.vor-preistest-20260814`.
5. **Atomar schreiben** (Temp-Datei + `os.replace`) und danach **zurueeklesen**:
   steht der neue Wert wirklich drin und sind die uebrigen Tags unveraendert?
   Wenn nicht - Sicherung zurueckspielen und Fehler melden.
6. **Nicht schreiben, waehrend das Verkaufsprogramm laeuft**, oder direkt danach
   einen Neustart ausloesen: die Werte werden beim Start gelesen. Der
   Neustart-Knopf existiert bereits.
7. Im Dashboard unter Personalisierung: Schalter, Linkfeld, Groesse, dazu
   "Speichern und Verkaufsprogramm neu starten" in einem Schritt - sonst
   aendert jemand etwas und wundert sich, dass nichts passiert.

### Zu beachten

* Es gibt **drei Druckprofile** (`EnableQrCode3`, `QrCodeBeginningString3` ...).
  Geaendert werden darf zunaechst nur Profil 1 - dieselbe Einschraenkung wie bei
  der Code-Vorschrift, siehe Punkt 1 dieser Liste.
* `EnableQrCodePrintButtons` und `EnableQrCodeShare` stehen auf `false`; deren
  Preise gelten deshalb nicht. Nicht damit verwechseln.

---

## 7. Kleinere Punkte

- **`test_scan_keeps_same_capture_id_on_different_days` ist zeitabhaengig.**
  `is_stable()` vergleicht die Aenderungszeit nach 50 ms; NTFS aktualisiert sie
  verzoegert, dadurch faellt der Test sporadisch durch. Nicht die Logik, die
  Pruefung ist zu streng.
- **`camera_capture.log` wird nicht ausgewertet**, weil TIScapture auf dem
  Testrechner nicht laeuft - die Kamera wird hier von 3GerTis bedient (siehe
  `3GERTIS.md`). Auf einer Anlage mit TIScapture greift die Datei automatisch;
  beide zaehlen im Dashboard als ein Geraet "Kamera".
- **Zwei `unknown`-Zeilen in `park_photo_sales_daily`** (02.07.2026, 1 Foto)
  stammen aus der Zeit vor diesen Arbeiten. Herkunft ungeklaert, bewusst nicht
  angefasst.
