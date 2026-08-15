"""Ein Testfoto so hochladen, dass es sichtbar, aber kein Umsatz ist.

Warum getrennt vom normalen Upload
----------------------------------
Ein Testfoto durchlaeuft nicht die uebliche Kette. Die Lichtschranke hat es
nicht ausgeloest, also brennt `AidaTest` kein Datum ein und legt es auch nicht
in `qrcode\\` ab - der Uploader wuerde es nie sehen. Es wird deshalb direkt aus
`fotos\\` genommen und selbst hochgeladen.

Die Falle, die hier vermieden wird
----------------------------------
Der Serverauslöser `handle_new_storage_object()` bestimmt den Park **aus dem
Dateinamen**: er liest die Kundennummer aus dem 16-stelligen Code. Findet er
keine, faellt er auf die Zuordnung Bucket -> Park zurueck. Bucket ``test`` zeigt
auf **Imst**.

Genau so sind am 14.08.2026 vier Fotos dieses Testrechners in Imsts Umsatz
gelandet. Ein Testfoto mit dem Rohnamen ``00001.jpg`` haette denselben Weg
genommen. Deshalb bekommt es hier zwingend einen regulaeren Codenamen, und
`pruefe_name_ist_zuordenbar` verweigert den Upload, wenn das nicht klappt -
lieber kein Testfoto als ein Foto im falschen Park.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from .config import Settings
from .filename_codec import build_legacy_filename


log = logging.getLogger(__name__)

# Ein Name, aus dem der Server den Park ableiten kann: genau 16 Ziffern.
CODENAME_RE = re.compile(r"^\d{16}\.jpg$", re.IGNORECASE)


class NichtZuordenbar(RuntimeError):
    """Der Dateiname laesst keine sichere Parkzuordnung zu."""


def pruefe_name_ist_zuordenbar(dateiname: str, customer_code: str) -> None:
    """Sicherstellen, dass dieses Foto beim richtigen Park landet.

    Die letzte Bremse vor dem Upload. Ohne sie kann ein Name, den der Server
    nicht deuten kann, ueber die Bucket-Zuordnung in einem fremden Park landen.
    """
    if not CODENAME_RE.match(dateiname):
        raise NichtZuordenbar(
            f"'{dateiname}' ist kein 16-stelliger Codename - der Server koennte "
            f"den Park nicht bestimmen und wuerde das Foto einem fremden Park "
            f"zuordnen."
        )
    kunde = _kundennummer_aus_code(dateiname[:16])
    erwartet = re.sub(r"\D", "", customer_code or "")[:4].zfill(4)
    if kunde != erwartet:
        raise NichtZuordenbar(
            f"Im Codenamen steckt Kundennummer {kunde}, erwartet war {erwartet}."
        )


def _kundennummer_aus_code(code: str) -> str:
    """Die Kundennummer aus dem 16-stelligen Code zurueckrechnen.

    Umkehrung von `mix_customer_time_capture`: dort liegt die Kundennummer auf
    den Positionen 1, 9, 4, 10 (1-basiert) - dieselbe Rechnung, die auch der
    Server in `parse_source_customer_code` anstellt.
    """
    return code[0] + code[8] + code[3] + code[9]


def baue_metadaten(settings: Settings, bild: Path) -> tuple[str, dict]:
    """Codenamen und Metadaten fuer ein Testfoto bilden."""
    aufgenommen = datetime.fromtimestamp(bild.stat().st_mtime)
    # Die Bildnummer aus dem Rohnamen (00001.jpg -> 00001); sonst die Uhrzeit,
    # damit zwei Testfotos desselben Tages nicht denselben Code bekommen.
    ziffern = re.sub(r"\D", "", bild.stem) or aufgenommen.strftime("%H%M%S")

    name = build_legacy_filename(
        customer_code=settings.customer_code,
        capture_id=ziffern,
        captured_at=aufgenommen,
        file_code_positions=settings.file_code_positions,
    )
    pruefe_name_ist_zuordenbar(name.filename, settings.customer_code)

    metadaten = {
        "park_slug": settings.park_slug,
        "camera_code": settings.camera_code,
        "capture_id": ziffern,
        "legacy_filename": name.filename,
        "legacy_code": name.legacy_code,
        "time_code": name.time_code,
        "file_code": name.file_code,
        "captured_at": aufgenommen.isoformat(),
        "raw_path": str(bild),
        "speed_status": "missing",
        "checksum_sha256": _pruefsumme(bild),
        # Das Kennzeichen. Der Server legt das Foto dadurch unter .../testfoto/
        # ab, und der Datenbankauslöser markiert es als is_test - damit zaehlt
        # es nirgends als Verkauf.
        "is_test": True,
        "event_key": f"testfoto|{aufgenommen.isoformat()}|{uuid.uuid4().hex[:8]}",
    }
    return name.filename, metadaten


def _pruefsumme(pfad: Path) -> str:
    h = hashlib.sha256()
    with pfad.open("rb") as datei:
        for block in iter(lambda: datei.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def lade_testfoto_hoch(settings: Settings, client, bild: Path) -> str:
    """Das Testfoto hochladen. Gibt den Ablagepfad zurueck.

    Wirft `NichtZuordenbar`, wenn der Name keine sichere Parkzuordnung erlaubt -
    dann wird bewusst nichts hochgeladen.
    """
    dateiname, metadaten = baue_metadaten(settings, bild)
    log.info("test photo: uploading %s as %s", bild.name, dateiname)

    begin = client.begin(metadaten, bild.stat().st_size)
    upload = begin.get("upload") or {}
    ablagepfad = upload.get("storage_path")
    if not ablagepfad:
        raise RuntimeError("liftpic-ingest-begin lieferte keinen storage_path")
    if "/testfoto/" not in ablagepfad:
        # Der Server hat das Kennzeichen nicht beruecksichtigt - dann waere das
        # Foto ein ganz normaler Verkauf. Lieber abbrechen.
        raise RuntimeError(
            f"Server legt das Testfoto nicht als Testfoto ab: {ablagepfad}"
        )

    client.upload_signed(
        bucket=upload.get("bucket"),
        storage_path=ablagepfad,
        token=upload.get("token"),
        signed_url=upload.get("signed_url"),
        path=bild,
    )
    client.commit(metadaten["capture_id"], ablagepfad,
                  event_key=metadaten["event_key"])
    return ablagepfad
