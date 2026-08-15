from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .files import sha256_file
from .state import StateStore
from .supabase_client import SupabaseIngestClient


log = logging.getLogger(__name__)


def _is_locked_target(exc: Exception) -> bool:
    """Whether this failure is 'the target file is currently in use'.

    Windows reports this in three flavours on the atomic rename: WinError 32
    (sharing violation), 33 (lock violation) and - the one the kiosk viewer
    actually produces on a file it keeps open - 5 (access denied).
    """
    winerror = getattr(exc, "winerror", None)
    if winerror in (5, 32, 33):
        return True
    text = str(exc).lower()
    return (
        "used by another process" in text
        or "wird von einem anderen prozess" in text
        or "zugriff verweigert" in text
        or "access is denied" in text
    )


class AssetInUse(RuntimeError):
    """Die Zieldatei ist vom Verkaufsprogramm belegt.

    Kein Fehler im eigentlichen Sinn, sondern ein Wartezustand: erst nach einem
    Neustart des Verkaufsprogramms laesst sich die Datei ersetzen.
    """


@dataclass(frozen=True)
class AssetSyncResult:
    fetched: int = 0
    applied: int = 0
    skipped: int = 0
    failed: int = 0
    # Restart order handed down by the dashboard, passed through untouched for
    # the service to act on. None when nothing is pending.
    restart_request: dict[str, Any] | None = None
    # True when a slot whose file could not be replaced is still waiting - the
    # viewer holds the target open, so the swap needs a restart first.
    restart_needed: bool = False


class AssetSyncWorker:
    """Download dashboard-managed local UI/print assets onto this PC."""

    def __init__(
        self,
        settings: Settings,
        store: StateStore,
        client: SupabaseIngestClient | None = None,
    ):
        self.settings = settings
        self.store = store
        self.client = client or SupabaseIngestClient(settings)
        self.allowed_roots = tuple(settings.asset_allowed_roots)

    def sync_once(self, restart_ack: str | None = None) -> AssetSyncResult:
        response = self.client.assets(restart_ack=restart_ack)
        assets = response.get("assets") or []
        if not isinstance(assets, list):
            raise RuntimeError("liftpic-assets did not return an assets list")

        applied = skipped = failed = 0
        restart_needed = False
        for asset in assets:
            if not isinstance(asset, dict):
                failed += 1
                continue
            try:
                outcome = self._sync_asset(asset)
                if outcome == "applied":
                    applied += 1
                else:
                    skipped += 1
            except Exception as exc:
                failed += 1
                # A locked target means the viewer holds the file open (the
                # classic case: hintergrund.png). That is not a broken asset,
                # it just needs the viewer restarted before it can be swapped.
                if isinstance(exc, AssetInUse) or _is_locked_target(exc):
                    restart_needed = True
                    log.info(
                        "asset '%s' is in use by the viewer - needs a restart before it can be replaced",
                        asset.get("slot") or asset.get("target_path"),
                    )
                else:
                    log.warning("asset sync failed: %s", exc)
                self._record_failure(asset, str(exc))

        restart_request = response.get("restart_request")
        return AssetSyncResult(
            fetched=len(assets),
            applied=applied,
            skipped=skipped,
            failed=failed,
            restart_request=restart_request if isinstance(restart_request, dict) else None,
            restart_needed=restart_needed,
        )

    def _sync_asset(self, asset: dict[str, Any]) -> str:
        deployment_id = self._deployment_id(asset)
        slot = self._optional_str(asset.get("slot"))
        target_path_raw = self._required_str(asset.get("target_path"), "target_path")
        target = self._allowed_target(target_path_raw)
        sha256 = self._optional_str(asset.get("sha256"))
        source_updated_at = self._optional_str(asset.get("updated_at"))
        bucket = self._optional_str(asset.get("bucket"))
        storage_path = self._optional_str(asset.get("storage_path"))

        if self.store.asset_is_current(
            deployment_id=deployment_id,
            target_path=str(target),
            sha256=sha256,
            source_updated_at=source_updated_at,
        ):
            return "skipped"

        if sha256 and target.exists() and sha256_file(target).lower() == sha256.lower():
            self._record_applied(asset, target, backup_path=None)
            return "skipped"

        signed_url = self._required_str(asset.get("signed_url"), "signed_url")
        data = self.client.download_signed_url(signed_url)
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if sha256 and actual_sha256.lower() != sha256.lower():
            raise RuntimeError(
                f"downloaded asset hash mismatch for {target}: expected {sha256}, got {actual_sha256}"
            )

        # Erst schreiben koennen, dann sichern (F-027).
        #
        # Frueher stand die Sicherung vor dem Schreiben. Haelt das
        # Verkaufsprogramm die Zieldatei offen - bei `hintergrund.png` ist das
        # der Normalfall -, scheitert das Ersetzen, der Zustand wird nie
        # "aktuell", und beim naechsten Abruf beginnt alles von vorn. Ergebnis
        # am 14.08.2026: 121 Ordner mit 119 byte-gleichen Kopien derselben
        # Datei, 7,5 MB, im 31-Sekunden-Takt.
        #
        # Ist das Ziel gesperrt, wird deshalb gar nicht erst gesichert.
        if target.exists() and self._ziel_ist_gesperrt(target):
            raise AssetInUse(
                f"asset '{slot or target.name}' is in use by the viewer - "
                "needs a restart before it can be replaced"
            )

        backup_path = self._backup_existing(target, deployment_id, data)
        self._atomic_write(target, data)
        self.store.record_asset_deployment(
            deployment_id=deployment_id,
            slot=slot,
            target_path=str(target),
            source_bucket=bucket,
            source_path=storage_path,
            sha256=sha256 or actual_sha256,
            source_updated_at=source_updated_at,
            backup_path=str(backup_path) if backup_path else None,
            status="applied",
            error=None,
        )
        return "applied"

    def _record_applied(self, asset: dict[str, Any], target: Path, backup_path: Path | None) -> None:
        self.store.record_asset_deployment(
            deployment_id=self._deployment_id(asset),
            slot=self._optional_str(asset.get("slot")),
            target_path=str(target),
            source_bucket=self._optional_str(asset.get("bucket")),
            source_path=self._optional_str(asset.get("storage_path")),
            sha256=self._optional_str(asset.get("sha256")),
            source_updated_at=self._optional_str(asset.get("updated_at")),
            backup_path=str(backup_path) if backup_path else None,
            status="applied",
            error=None,
        )

    def _record_failure(self, asset: dict[str, Any], error: str) -> None:
        target_path = str(asset.get("target_path") or "<missing>")
        self.store.record_asset_deployment(
            deployment_id=self._deployment_id(asset),
            slot=self._optional_str(asset.get("slot")),
            target_path=target_path,
            source_bucket=self._optional_str(asset.get("bucket")),
            source_path=self._optional_str(asset.get("storage_path")),
            sha256=self._optional_str(asset.get("sha256")),
            source_updated_at=self._optional_str(asset.get("updated_at")),
            backup_path=None,
            status="failed",
            error=error,
        )

    def _allowed_target(self, raw_path: str) -> Path:
        if not self.allowed_roots:
            raise RuntimeError("ASSET_SYNC_ALLOWED_ROOTS is empty")
        target = Path(raw_path).expanduser().resolve(strict=False)
        target_norm = self._norm(target)
        for root in self.allowed_roots:
            root_norm = self._norm(Path(root).expanduser().resolve(strict=False))
            try:
                if os.path.commonpath([target_norm, root_norm]) == root_norm:
                    return target
            except ValueError:
                continue
        raise RuntimeError(f"asset target is outside allowed roots: {raw_path}")

    def _ziel_ist_gesperrt(self, target: Path) -> bool:
        """Haelt gerade jemand die Zieldatei offen?

        Geprueft wird, indem die Datei zum Schreiben geoeffnet wird - ohne etwas
        zu schreiben. Unter Windows scheitert das, solange ein anderes Programm
        sie mit ausschliesslichem Zugriff haelt.
        """
        try:
            with open(target, "r+b"):
                return False
        except OSError as exc:
            if _is_locked_target(exc):
                return True
            # Ein anderer Fehler (Datei weg, Rechte) ist nicht unsere Frage -
            # den soll das eigentliche Schreiben melden.
            return False

    def _gleiche_sicherung_vorhanden(self, relative: Path, data: bytes) -> bool:
        """Gibt es schon eine Sicherung mit genau diesem Inhalt?

        Ohne diese Pruefung entstand bei jedem Abruf eine weitere byte-gleiche
        Kopie. Verglichen wird gegen die juengste vorhandene Sicherung derselben
        Datei - aeltere Staende sollen erhalten bleiben, nur die Wiederholung
        desselben Inhalts nicht.
        """
        backup_root = self.settings.asset_backup_dir
        if backup_root is None or not backup_root.is_dir():
            return False
        try:
            kandidaten = sorted(
                (p for p in backup_root.glob(f"*/*/{relative.as_posix()}") if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return False
        if not kandidaten:
            return False
        try:
            return kandidaten[0].read_bytes() == data
        except OSError:
            return False

    def _backup_existing(
        self, target: Path, deployment_id: str, neuer_inhalt: bytes | None = None,
    ) -> Path | None:
        if not target.exists():
            return None
        backup_root = self.settings.asset_backup_dir
        if backup_root is None:
            return None
        relative = self._relative_to_allowed_root(target)

        try:
            alter_inhalt = target.read_bytes()
        except OSError:
            return None

        # Nichts sichern, was sich gar nicht aendert.
        if neuer_inhalt is not None and alter_inhalt == neuer_inhalt:
            return None
        if self._gleiche_sicherung_vorhanden(relative, alter_inhalt):
            return None

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_root / timestamp / deployment_id[:8] / relative
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(alter_inhalt)
        self._alte_sicherungen_aufraeumen(relative)
        return backup_path

    # Wie viele Staende je Datei aufbewahrt werden. Genug, um einen
    # missratenen Austausch zurueckzunehmen; wenig genug, dass der Ordner nicht
    # unbegrenzt waechst (er stand bei 121 Ordnern und 7,5 MB).
    SICHERUNGEN_JE_DATEI = 10

    def _alte_sicherungen_aufraeumen(self, relative: Path) -> None:
        backup_root = self.settings.asset_backup_dir
        if backup_root is None:
            return
        try:
            vorhanden = sorted(
                (p for p in backup_root.glob(f"*/*/{relative.as_posix()}") if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for alt in vorhanden[self.SICHERUNGEN_JE_DATEI:]:
            try:
                alt.unlink()
                # Leere Ordner mitnehmen, sonst bleiben hunderte Huellen liegen.
                for ordner in (alt.parent, alt.parent.parent):
                    try:
                        ordner.rmdir()
                    except OSError:
                        break
            except OSError:
                log.warning("could not remove old asset backup %s", alt)

    def _relative_to_allowed_root(self, target: Path) -> Path:
        target_resolved = target.resolve(strict=False)
        for root in self.allowed_roots:
            root_resolved = Path(root).expanduser().resolve(strict=False)
            try:
                return target_resolved.relative_to(root_resolved)
            except ValueError:
                continue
        safe_parts = [part.replace(":", "").replace("\\", "_").replace("/", "_") for part in target.parts if part]
        return Path(*safe_parts)

    @staticmethod
    def _atomic_write(target: Path, data: bytes) -> None:
        """Schreiben, ohne dass ein halbes Bild im Verkaufsprogramm landet.

        Der Name der Zwischendatei traegt die Prozessnummer (F-025). Vorher war
        er fest aus dem Ziel abgeleitet und damit fuer zwei Agenten identisch:
        beide schrieben in dieselbe Datei, die erste `replace()` verschob sie,
        die zweite scheiterte - und im unguenstigen Fall lag eine halb
        geschriebene `hintergrund.png` in `C:\\liftpic\\samuel_neu`.

        `replace()` selbst ist auf einem Datentraeger atomar; nur der
        Schreibschritt davor war es nicht.
        """
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f"{target.name}.{os.getpid()}.liftpic-sync.tmp")
        try:
            temp.write_bytes(data)
            temp.replace(target)
        finally:
            # Scheitert das Ersetzen (Zieldatei vom Verkaufsprogramm gehalten),
            # bleibt sonst eine Leiche neben dem Original liegen.
            if temp.exists():
                try:
                    temp.unlink()
                except OSError:
                    log.warning("could not remove temp file %s", temp)

    @staticmethod
    def _deployment_id(asset: dict[str, Any]) -> str:
        raw = str(asset.get("id") or "").strip()
        if raw:
            return raw
        target = str(asset.get("target_path") or "")
        sha256 = str(asset.get("sha256") or "")
        updated_at = str(asset.get("updated_at") or "")
        digest = hashlib.sha256(f"{target}|{sha256}|{updated_at}".encode("utf-8")).hexdigest()
        return digest

    @staticmethod
    def _required_str(value: object, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"asset is missing {name}")
        return value.strip()

    @staticmethod
    def _optional_str(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    @staticmethod
    def _norm(path: Path) -> str:
        return os.path.normcase(os.path.abspath(str(path)))
