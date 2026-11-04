"""Presentation-Seite und Gestaltungsregeln ins CRM uebernehmen.

Das CRM zeigt die Presentation als Live-Vorschau im Baukasten. Damit dort
genau dasselbe zu sehen ist wie am PC, kommen Seite und Regeln aus diesem Repo:
  public/presentation/index.html              <- presentation_page.PAGE
  src/crm/customer/presentationDesignData.ts  <- presentation_design.FELDER/VORLAGEN

Aufruf: python3 scripts/presentation_seite_ins_crm.py <Pfad zum CRM-Repo>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from liftpic_sync.presentation_design import FELDER, VORLAGEN  # noqa: E402
from liftpic_sync.presentation_page import PAGE  # noqa: E402

crm = Path(sys.argv[1])
seite = crm / "public" / "presentation" / "index.html"
seite.parent.mkdir(parents=True, exist_ok=True)
seite.write_text(PAGE.replace("__PAGE_REV__", "preview"), encoding="utf-8")

felder = {k: {"kind": v[0], "default": v[1], "limits": v[2]} for k, v in FELDER.items()}
ts = (
    "// AUTOMATISCH ERZEUGT aus testsoftware (scripts/presentation_seite_ins_crm.py) - nicht von Hand aendern.\n"
    "// Gleiche Regeln wie im Agenten (presentation_design.py).\n"
    f"export const PRESENTATION_FIELDS = {json.dumps(felder, indent=2)} as const;\n\n"
    f"export const PRESENTATION_PRESETS: Record<string, Record<string, unknown>> = {json.dumps(VORLAGEN, indent=2)};\n"
)
(crm / "src" / "crm" / "customer" / "presentationDesignData.ts").write_text(ts, encoding="utf-8")
print("ok:", seite)
