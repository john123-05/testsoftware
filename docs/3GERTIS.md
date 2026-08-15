# 3GerTis — das Kameraprogramm

## Kurz gesagt

3GerTis ist **das Programm, das die Kamera bedient und das Foto auslöst**. Es ist
keine übergeordnete „Steuerung" der Anlage — dieser Name im Dashboard war
irreführend und wurde auf „Kamera" korrigiert.

Der Name setzt sich zusammen aus **TIS = The Imaging Source**, dem Hersteller der
verbauten Kamera, und „3Ger" als Kürzel des Integrators. Die zugehörigen
Bibliotheken im Ordner (`TIS_DShowLib10.dll`, `TIS_UDSHL*.dll`) stammen vom
Kamerahersteller.

Laufende Datei: `C:\liftpic\3GerTis\3gerTis_v70.exe` (104 KB, Stand 2017).

## Was es konkret tut

Das Programm hält dauerhaft die Verbindung zur Netzwerkkamera offen und wartet
auf den Auslösebefehl. Es läuft deshalb rund um die Uhr, auch wenn stundenlang
kein Foto entsteht.

Die Kette bei einer Fahrt:

1. Die Lichtschranke spricht an.
2. `AidaTest` erkennt das und ruft das Hilfsprogramm auf, das in
   `C:\liftpic\kosel\AidaTest.ini` hinterlegt ist:
   `Executable=C:\Liftpic\3gertis\tools\3gerimage.exe`
3. `3gerimage.exe` weist das laufende 3GerTis an, ein Bild aufzunehmen.
4. 3GerTis nimmt auf und legt die Datei ab.

Im Protokoll `3gerlog.txt` sieht ein erfolgreicher Durchlauf so aus:

```
10.08.2026 08:29:57	Snap Image
10.08.2026 08:29:57	Generate file - c:\liftpic\fotos\00001.jpg
10.08.2026 08:29:58	Image has been saved-c:\liftpic\fotos\00001.jpg
```

Danach übernimmt die restliche Kette: Datum und Nummer werden eingebrannt, das
Bild wandert nach `fotos\out\`, der Uploader lädt es hoch.

## Die Einstellungen (`3gertis.ini`)

| Eintrag | Wert | Bedeutung |
|---|---|---|
| `dest_folder` | `c:\liftpic\fotos\` | Wohin die Bilder geschrieben werden |
| `digits` / `start_index` | `5` / `1` | Dateiname `00001.jpg`, fortlaufend |
| `reset_counter` | `07:50` | Zähler springt jeden Morgen um 07:50 auf 1 zurück |
| `restart_if_lost` | `0` | **Verbindet sich nach Kameraverlust nicht selbst neu** |
| `init_lib` | `ISB3200016679` | Seriennummer der Lizenz/Kamera |
| `xml_file` | `trigger.xml` | Datei mit den Bildeinstellungen |

Der Zählerstand aus `digits`/`start_index` ist die **Bildnummer**, die später im
16-stelligen Abholcode auftaucht.

## Die Kamera (`trigger.xml`)

* Modell **DFK 33GX545**, GigE-Netzwerkkamera
* Auflösung **4096 × 3000**, Format YUY2, 4,75 Bilder/Sekunde
* Belichtung und Verstärkung **automatisch** (Verstärkung bis max. 48)
* **Blitzauslösung aktiv** (`Strobe` → `Enable = 1`) — die Kamera steuert das
  Blitzlicht selbst mit

Diese Datei wurde zuletzt am 08.08.2026 geändert. Wer an Helligkeit oder
Schärfe dreht, ändert sie — entweder im Programmfenster oder über die
Hilfsprogramme in `tools\`.

## Die Hilfsprogramme in `tools\`

Kleine Einzweck-Programme, die von außen auf das laufende 3GerTis wirken:

| Datei | Zweck |
|---|---|
| `3GerImage.exe` | Bild aufnehmen (das ruft die Lichtschranke auf) |
| `3GerExpPlus.exe` / `3GerExpMinus.exe` | Belichtung heller / dunkler |
| `3GerGainPlus.exe` / `3GerGainMinus.exe` | Verstärkung hoch / runter |
| `3GerChangeMode.exe` | Betriebsart umschalten |
| `DeleteTIS.exe` | Aufräumen |

## Wichtig für den Betrieb: `restart_if_lost=0`

Am 10.08.2026 um 20:27 steht im Protokoll:

```
10.08.2026 20:27:05	Device lost
```

Die Kamera war ab diesem Zeitpunkt nicht mehr erreichbar. Weil
`restart_if_lost=0` gesetzt ist, versucht 3GerTis **von sich aus keinen neuen
Verbindungsaufbau**. Das Programm läuft weiter und wirkt im Task-Manager
gesund, nimmt aber nichts mehr auf, bis es jemand neu startet.

Genau deshalb wertet der Uploader beides aus: dass das Programm läuft *und* wann
zuletzt eine Meldung kam. Ein „läuft seit 23 Std." allein sagt in diesem Fall
nichts über die Betriebsbereitschaft aus.

Ob `restart_if_lost=1` sinnvoll wäre, ist eine Entscheidung für die Anlage —
siehe `OFFENE_PUNKTE.md`. Hier wurde nichts umgestellt.

## Zwei Programmgenerationen für dieselbe Aufgabe

Dieselbe Aufgabe erledigt auf neueren Anlagen `camera26.exe` (TIScapture).
Beide zusammen laufen nie. Im Dashboard sind sie deshalb **ein** Gerät namens
„Kamera"; in der Detailansicht steht in Klammern, welches Programm gerade
arbeitet. Getrennte Einträge hätten auf jeder Anlage „Kamera ausgefallen"
gemeldet, nur weil dort die jeweils andere Variante installiert ist.
