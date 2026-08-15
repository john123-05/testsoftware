from pathlib import Path

from liftpic_sync.config import Settings
from liftpic_sync.operational_monitor import read_operational_status
from liftpic_sync.service import LiftpicService


def make_settings(tmp_path: Path, globs: tuple[str, ...]) -> Settings:
    raw = tmp_path / "fotos"
    out = raw / "out"
    raw.mkdir()
    out.mkdir()
    return Settings(
        app_name="test",
        shadow_mode=True,
        park_slug="test-park",
        park_id="park-id",
        customer_code="1234",
        machine_id="machine",
        device_token="token",
        supabase_functions_url="http://example.test/functions/v1",
        supabase_url="http://example.test",
        supabase_anon_key="anon",
        raw_dir=raw,
        processed_dir=out,
        webout_dir=None,
        qrcode_dir=None,
        upload_source="qrcode",
        stage_in_shadow=False,
        statistic_file=None,
        print_count_file=None,
        app_dir=tmp_path,
        state_db=tmp_path / "state.db",
        log_dir=tmp_path / "logs",
        poll_seconds=0.1,
        file_stable_seconds=0,
        speed_match_seconds=12,
        speed_timeout_seconds=30,
        upload_retry_seconds=1,
        heartbeat_seconds=60,
        archive_raw=False,
        camera_code="cam1",
        operational_log_globs=globs,
        operational_log_tail_lines=20,
        operational_log_stale_minutes=240,
    )


def test_coin_error_is_reported_as_down(tmp_path: Path):
    log_dir = tmp_path / "imageloader"
    log_dir.mkdir()
    log_file = log_dir / "coin.log"
    log_file.write_text(
        "15.07.2026 10:00:00 CoinChangerStatus ready\n"
        "15.07.2026 10:01:00 CoinChangerError no response\n",
        encoding="utf-8",
    )

    status = read_operational_status(make_settings(tmp_path, (str(log_dir / "*.log"),)))

    assert status.coin_status == "down"
    geraet = status.devices[0]
    assert geraet.kind == "cash"
    # Der Klarname ist das, was der Betreiber liest - kein Dateiname. Die Datei
    # bleibt ueber source_file nachvollziehbar, der technische Name steht
    # getrennt daneben.
    assert geraet.name == "Münzprüfer"
    assert geraet.tech
    assert "coin.log" in geraet.source_file
    # Der Rohtext bleibt in `detail`, damit ein Techniker das Original sieht ...
    assert "CoinChangerError" in geraet.detail
    # ... und die Uebersetzung steht GETRENNT in `plain`. Zusammengeklebt hiesse:
    # eingeklappt beides lesen, aufgeklappt den Rohtext noch einmal.
    assert "antwortet nicht" in geraet.plain
    assert "CoinChangerError" not in geraet.plain


def test_later_ready_line_restores_operational_status(tmp_path: Path):
    log_dir = tmp_path / "imageloader"
    log_dir.mkdir()
    log_file = log_dir / "coin.log"
    log_file.write_text(
        "15.07.2026 10:00:00 CoinChangerError no response\n"
        "15.07.2026 10:02:00 CoinChangerStatus ready\n",
        encoding="utf-8",
    )

    status = read_operational_status(make_settings(tmp_path, (str(log_dir / "*.log"),)))

    assert status.coin_status == "operational"


def test_old_error_line_is_not_reported_as_live_fault(tmp_path: Path):
    import os
    import time

    log_dir = tmp_path / "3GerTis"
    log_dir.mkdir()
    log_file = log_dir / "Speedshot.log"
    # A defunct camera log whose last line is a year-old error.
    log_file.write_text("04.06.2025 11:29:36.355: Error 45\n", encoding="utf-8")
    old = time.time() - 400 * 24 * 3600  # ~400 days ago
    os.utime(log_file, (old, old))

    status = read_operational_status(make_settings(tmp_path, (str(log_dir / "*.log"),)))

    # No false "camera down" from a year-old line.
    assert status.camera_status is None
    assert status.devices == []


def test_health_payload_includes_operational_devices(tmp_path: Path):
    log_dir = tmp_path / "logs-source"
    log_dir.mkdir()
    log_file = log_dir / "zvt.log"
    log_file.write_text("15.07.2026 10:02:00 Terminal bereit\n", encoding="utf-8")
    service = LiftpicService(make_settings(tmp_path, (str(log_dir / "*.log"),)))

    health = service.health()

    assert health["terminal_status"] == "operational"
    assert health["operational_devices"]


def test_statistic_email_failure_is_not_a_viewer_outage(tmp_path: Path):
    """Eine kaputte Nebenfunktion darf das Verkaufsprogramm nicht rot faerben.

    Der Automat verschickt nachts einen Umsatzbericht per E-Mail. Scheitert das,
    steht der Fehler im errors.log des Verkaufsprogramms - obwohl der Verkauf
    laeuft. Frueher meldete die Seite deshalb "Verkaufsprogramm ausgefallen".
    """
    log_dir = tmp_path / "samuel_neu"
    log_dir.mkdir()
    (log_dir / "errors.log").write_text(
        "[14.08.2026 11:50:05] --> Error sending statistic email: "
        "System.Security.Authentication.AuthenticationException: "
        "Fehler bei SSPI-Aufruf\n",
        encoding="utf-8",
    )

    devices = read_operational_status(
        make_settings(tmp_path, (str(log_dir / "*.log"),))
    ).devices

    nach_namen = {d.name: d for d in devices}
    # Die Meldung bekommt einen eigenen Eintrag ...
    assert "Statistik-E-Mail" in nach_namen
    # ... und das Verkaufsprogramm bleibt trotzdem sichtbar. Frueher verdraengte
    # die fremde Zuordnung den Urheber, wodurch das Programm ganz aus der Liste
    # fiel, sobald es einmal ueber etwas anderes schrieb.
    assert "Verkaufsprogramm" in nach_namen
    assert nach_namen["Verkaufsprogramm"].status != "down"
    # In seiner Kachel darf nicht die fremde Meldung stehen.
    assert "AuthenticationException" not in nach_namen["Verkaufsprogramm"].detail

    eintrag = nach_namen["Statistik-E-Mail"]
    # Warnung, nicht Ausfall: verkauft wird weiter.
    assert eintrag.status == "degraded"
    assert eintrag.severity == "warning"
    # Klartext getrennt vom Rohtext - sonst steht die Meldung doppelt auf der
    # Seite, einmal eingeklappt und einmal aufgeklappt.
    assert "Verschl" in eintrag.plain
    assert "AuthenticationException" in eintrag.detail
    assert "AuthenticationException" not in eintrag.plain
    assert eintrag.purpose


def test_customer_number_notice_does_not_colour_the_uploader(tmp_path: Path):
    """Eine Startmeldung darf den Uploader nicht dauerhaft gelb faerben.

    Der Uploader meldet beim Start, wenn seine Kundennummer von der des
    Verkaufsprogramms abweicht - richtig und gewollt. Weil es aber die letzte
    aussagekraeftige Zeile in seinem Protokoll bleibt, stand er danach fuer
    immer auf "eingeschraenkt", obwohl er einwandfrei arbeitete.
    """
    log_dir = tmp_path / "liftpic-sync" / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "liftpic-sync.log").write_text(
        "2026-08-14 15:08:26,427 INFO liftpic_sync.service: rides seen=0 new=0 "
        "queued=0 uploaded=0\n"
        "2026-08-14 15:08:30,284 WARNING liftpic_sync.config: customer number "
        "differs: viewer says 1234, agent had 7623 - taking the viewer's value\n"
        "2026-08-14 15:08:32,409 INFO liftpic_sync.service: rides seen=0 new=0 "
        "queued=0 uploaded=0\n",
        encoding="utf-8",
    )

    devices = read_operational_status(
        make_settings(tmp_path, (str(log_dir / "*.log"),))
    ).devices
    nach_namen = {d.name: d for d in devices}

    # Die Meldung wird zu einem eigenen Punkt ...
    assert "Abholcode" in nach_namen
    abholcode = nach_namen["Abholcode"]
    assert abholcode.status == "degraded"
    assert "Kundennummern" in abholcode.plain
    assert abholcode.tech == "Settings.xml"

    # ... und der Uploader bleibt sichtbar UND unauffaellig.
    assert "Uploader" in nach_namen
    assert nach_namen["Uploader"].status == "operational"
    assert "customer number" not in nach_namen["Uploader"].detail


def test_failed_internet_check_is_not_a_viewer_outage(tmp_path: Path):
    """Ein DNS-Aussetzer ist ein Leitungsproblem, kein Programmfehler.

    Das Verkaufsprogramm prueft die Verbindung, indem es www.google.com
    aufloest. Schlaegt das fehl, stand bisher "Verkaufsprogramm ausgefallen" -
    und der eigentliche Befund, dass die Leitung weg war, fehlte ganz.
    """
    from liftpic_sync.service import _reconcile

    log_dir = tmp_path / "samuel_neu"
    log_dir.mkdir()
    (log_dir / "errors.log").write_text(
        "[14.08.2026 03:35:40] --> InternetConnection error: "
        "System.Net.WebException: Der Remotename konnte nicht aufgelöst "
        "werden: 'www.google.com'\n",
        encoding="utf-8",
    )

    devices = read_operational_status(
        make_settings(tmp_path, (str(log_dir / "*.log"),))
    ).devices
    nach_namen = {d.name: d for d in devices}

    assert "Internetverbindung" in nach_namen
    assert nach_namen["Internetverbindung"].kind == "network"
    assert "keine Internetverbindung" in nach_namen["Internetverbindung"].plain
    # Das Programm selbst bleibt sichtbar und wird nicht rot gefaerbt.
    assert nach_namen["Verkaufsprogramm"].status != "down"

    # Und weil wir gerade mit dem Server sprechen, ist die Leitung jetzt da:
    # der alte Eintrag gehoert in die Vergangenheitsform, nicht auf Rot.
    abgeglichen = {d["name"]: d for d in _reconcile(devices, [], online=True)}
    assert abgeglichen["Internetverbindung"]["status"] == "operational"
    assert "Aktuell verbunden" in abgeglichen["Internetverbindung"]["plain"]

    # Ohne Verbindung bleibt der Befund dagegen stehen.
    offline = {d["name"]: d for d in _reconcile(devices, [], online=False)}
    assert offline["Internetverbindung"]["status"] == "down"


def test_sales_program_logs_collapse_into_one_entry(tmp_path: Path):
    """Drei Protokolle, ein Programm, eine Kachel."""
    log_dir = tmp_path / "samuel_neu"
    log_dir.mkdir()
    for datei in ("errors.log", "debug.log", "watchdog.log"):
        (log_dir / datei).write_text(
            "15.07.2026 10:00:00 Programmstart\n", encoding="utf-8"
        )

    devices = read_operational_status(
        make_settings(tmp_path, (str(log_dir / "*.log"),))
    ).devices

    assert [d.name for d in devices] == ["Verkaufsprogramm"]


def test_unknown_logs_of_same_kind_stay_separate(tmp_path: Path):
    """Der Klarname darf zwei fremde Protokolle nicht verschmelzen."""
    log_dir = tmp_path / "fremd"
    log_dir.mkdir()
    (log_dir / "eins.log").write_text(
        "15.07.2026 10:00:00 exception in modul a\n", encoding="utf-8"
    )
    (log_dir / "zwei.log").write_text(
        "15.07.2026 10:00:00 exception in modul b\n", encoding="utf-8"
    )

    devices = read_operational_status(
        make_settings(tmp_path, (str(log_dir / "*.log"),))
    ).devices

    assert len(devices) == 2
    assert {d.tech for d in devices} == {"eins.log", "zwei.log"}
