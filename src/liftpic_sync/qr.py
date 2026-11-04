"""QR-Codes als SVG, ohne Internet und ohne Fremdpakete auf dem PC.

Rechnet mit dem unveraendert mitgelieferten segno-Kern (_vendor/segno_qr).
"""
from __future__ import annotations

from ._vendor.segno_qr import encoder


def qr_svg(text: str, *, border: int = 4, dark: str = "#000", light: str = "#fff") -> str:
    """Ein QR-Code als eigenstaendiges SVG (skaliert frei, scharfe Kanten).

    Fehlerkorrektur mindestens "L"; segno hebt sie selbst an, solange die
    Groesse gleich bleibt. Weniger Kaestchen heisst: jedes Kaestchen wird auf
    dem Bildschirm groesser und laesst sich aus mehr Abstand scannen.
    """
    code = encoder.encode(text, error="l", micro=False, boost_error=True)
    matrix = code.matrix
    size = len(matrix) + 2 * border
    teile = []
    for y, zeile in enumerate(matrix):
        x = 0
        breite = len(zeile)
        while x < breite:
            if zeile[x] & 1:
                start = x
                while x < breite and zeile[x] & 1:
                    x += 1
                teile.append(f"M{start + border} {y + border}h{x - start}v1h-{x - start}z")
            else:
                x += 1
    return (
        f'<svg viewBox="0 0 {size} {size}" shape-rendering="crispEdges">'
        f'<rect width="{size}" height="{size}" fill="{light}"/>'
        f'<path fill="{dark}" d="{"".join(teile)}"/></svg>'
    )
