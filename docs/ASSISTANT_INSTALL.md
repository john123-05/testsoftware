# Installation über den Liftpictures Assistenten

Die bestehenden Installationen und Legacy-Skripte bleiben kompatibel. Neue Installationen verwenden die geprüften Befehle aus CRM → KI-Assistent → Kunden und PCs einrichten.

- `export_pc_diagnostic.ps1`: liest nur ausgewählte Bildcode-, Pfad-, Preis- und Programmfelder. Schreibt einen bereinigten JSON-/Textbericht nach Downloads. Keine vollständigen Settings.xml-/Env-/Log-Exporte.
- `install_assistant.ps1`: prüft festes Release-Paket, erkennt bestehende Installation, löst einen kurzlebigen Code ein und startet den Agenten im Testbetrieb. Kein pip/venv nötig; das Laufzeitpaket verwendet nur die Python-Standardbibliothek. Gerätegeheimnisse bleiben ausschließlich lokal mit eingeschränkten Dateirechten.
- `assistant_watchdog.ps1`: exakt ein Agent, Wartungssperre und `paused`-Datei beachten. Installation braucht Agent und Wächter; keine Viewer-/Kamera-Steuerung.
- `update_assistant.ps1`: für bereits gekoppelte PCs; hält den Agenten an, sichert .env, Code und SQLite-Zustand und erhält das Gerätetoken. Kein neues Pairing. Zusätzliche Kameras werden aus der freigegebenen Serverkonfiguration geladen und bleiben bis zur Abnahme im Testbetrieb.
- `test_assistant.ps1`: fragt vor Ort Kamera und Pfad eines gerade aufgenommenen Testbilds ab, verlangt eine ausdrückliche lokale Bestätigung und lädt genau dieses Bild als `is_test` hoch. Kein Umsatz. Gedruckten Code und richtige Claim-Seite anschließend prüfen.

Mehrere Kameras teilen einen Agenten und eine Queue, behalten aber ihre eigenen Bildcodes, Quellen, Profile und Upload-Freigaben. `count_only` und nicht freigegebene Streams dürfen auch durch einen bereits live laufenden Hauptstream keine Bilder hochladen.

Neue Geräte sind serverseitig vom bisherigen Header-Identitätsfallback und vom wiederverwendbaren Legacy-Pairing ausgeschlossen. Einmalcode-Wiederholung ist nur für dieselbe lokale Sitzung und innerhalb des begrenzten Wiederholungsfensters möglich. Keine dauerhaften Tokens in Chat, Diagnoseberichten oder Git.

## Release

Version 0.4.0. Das `liftpic-install.zip` enthält ausschließlich `src/` und `scripts/` aus dem geprüften Commit. CRM/MCP konfigurieren Commit, Script-Hashes und Paket-Hash; keine beliebige Downloadadresse durch die KI. Bestehende Kunden werden durch die Veröffentlichung nicht automatisch aktualisiert.

## Tests und Grenzen

Python-Tests für Scanner, Remote-Konfiguration, Viewer-XML, Fahrtenzählung und neue Einrichtungslogik; der Exporter wurde zusätzlich unter PowerShell mit Dateifixtures ausgeführt. Alle neuen PowerShell-Dateien wurden mit dem echten Parser geprüft.

Die vollständige bestehende Python-Suite hat auf macOS vier bereits auf dem unveränderten Hauptbranch reproduzierbare Fehler in älteren Viewer-/Sitzungstests. Die neuen Einrichtungs-/Scanner-Tests bestehen.

Ein realer Windows-PC mit Aufgabenplanung, Kamera, Drucker und Terminal steht dieser Entwicklungssitzung nicht zur Verfügung. Autostart nach Reboot, echter Agentenabsturz/Wächter und Rückweg müssen vor dem ersten Kundenrollout auf einem Test-PC geprüft werden. Ein erfolgreicher Build oder gesendeter Herzschlag ersetzt diese Abnahme nicht.
