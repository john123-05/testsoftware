"""Reading the code recipe out of the sales viewer's own configuration.

Why
---
The 16-digit claim code is built from three parts: customer number, date and
picture number. Two programs compute it independently - the viewer ("Samuel"),
which prints it into the QR on the paper, and this agent, which uses it as the
online filename. If the two disagree by a single digit, the printed QR points at
a photo that does not exist, and the guest sees "Foto nicht gefunden".

Until now both sides kept their own copy of the recipe: the viewer in
`Settings.xml`, the agent in its `.env`. Nothing kept them in step. On the test
PC they had already drifted apart - viewer `CustomerNumber=1234` against agent
`CUSTOMER_CODE=7623` - which would make every single claim fail.

So the viewer's configuration is the source of truth, and this module reads it.
The agent cannot disagree with a value it takes from the other side.

Deliberately read-only: `Settings.xml` belongs to the viewer, and a config file
that two programs write is exactly the kind of thing that breaks at 3am.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ViewerCodeRecipe:
    customer_number: str | None
    code_positions: str | None
    qr_prefix: str | None
    source: str

    def is_empty(self) -> bool:
        return not self.customer_number and not self.code_positions


def read_viewer_recipe(settings_path: Path | str | None) -> ViewerCodeRecipe | None:
    """Read customer number and picture-code positions from Settings.xml.

    Returns None when the file is missing or unreadable - the caller then keeps
    its configured values. A viewer config we cannot read must never stop the
    agent from uploading.

    Only the FIRST print profile is read. The viewer also has profiles 2 and 3
    with their own values (`CustomerNumber3`, `CodePositionsInFilename3`); which
    one applies depends on the printer in use, and guessing that from here would
    be worse than using the documented default.
    """
    if not settings_path:
        return None
    path = Path(settings_path)
    if not path.is_file():
        return None

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("could not read viewer settings %s: %s", path, exc)
        return None

    customer = _first_tag(text, "CustomerNumber")
    positions = _first_tag(text, "CodePositionsInFilename")
    prefix = _first_tag(text, "QrCodeBeginningString")

    if customer is None and positions is None:
        return None

    return ViewerCodeRecipe(
        customer_number=_digits(customer),
        code_positions=_clean_positions(positions),
        qr_prefix=prefix,
        source=str(path),
    )


# Welcher Preis gilt, haengt davon ab, welche Verkaufsart eingeschaltet ist.
# Steht der Schalter auf false, bietet der Automat das Produkt gar nicht an -
# sein Preis darf dann auch nicht als gueltig gelten.
_PREISE: tuple[tuple[str, str | None], ...] = (
    ("PriceFacebook", None),
    ("PriceEmail", None),
    ("PricePrint", None),
    ("PricePrintWithoutQrCode", "EnableQrCodePrintButtons"),
    ("PricePrintWithQrCode", "EnableQrCodePrintButtons"),
    ("PriceQrCodeShare", "EnableQrCodeShare"),
)


def read_viewer_prices(settings_path: Path | str | None) -> list[int]:
    """Die Preise in Cent, die dieser Automat ueberhaupt verlangen kann.

    Warum als LISTE und nicht als ein Preis: welches Produkt ein Gast gewaehlt
    hat, steht nirgends. `Statistic.txt` fuehrt auf diesem Automaten in 1323 von
    1332 Zeilen gar keinen Betrag. Einen Preis anzunehmen hiesse raten.

    Mit der Liste laesst sich trotzdem pruefen: was der Automat einbehalten hat
    (eingeworfen minus ausgezahlt), muss EINER dieser Preise sein. Trifft es
    keinen, stimmt etwas nicht - und das ist der Befund, auf den es ankommt.
    """
    if not settings_path:
        return []
    path = Path(settings_path)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    preise: set[int] = set()
    for tag, schalter in _PREISE:
        if schalter and (_first_tag(text, schalter) or "").strip().lower() != "true":
            continue
        roh = _first_tag(text, tag)
        if roh is None:
            continue
        try:
            cent = int(round(float(roh.strip().replace(",", ".")) * 100))
        except ValueError:
            continue
        if cent > 0:
            preise.add(cent)
    return sorted(preise)


def _first_tag(text: str, tag: str) -> str | None:
    """Value of the first <tag>…</tag>, ignoring the numbered variants.

    Parsed by regex rather than an XML parser on purpose: these files are hand
    edited over many years and are not always well-formed. A stray character
    somewhere else in the file must not cost us the two values we need. The
    negative lookahead keeps `CustomerNumber3` from matching `CustomerNumber`.
    """
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _digits(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return digits or None


def _clean_positions(value: str | None) -> str | None:
    if not value:
        return None
    parts = [p.strip() for p in re.split(r"[,\s]+", value) if p.strip().isdigit()]
    return ",".join(parts) or None
