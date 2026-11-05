"""Liftpictures Kiosk (Verkaufsprogramm) ins CRM bzw. Dashboard uebernehmen.

Der Baukasten im CRM/Dashboard zeigt als Live-Vorschau genau die App, die am
Automaten laeuft, und rechnet mit denselben Vorgaben/Versionen/Farbwelten:
  public/kiosk/                 <- kiosk_app/dist (npm run build)
  <ts-ordner>/kioskConfig.ts    <- kiosk_app/src/config.ts   (Vorgaben, Versionen, Farbwelten)
  <ts-ordner>/kioskVouchers.ts  <- kiosk_app/src/vouchers.ts (Gutschein-Codes erzeugen)

Aufruf: python3 scripts/kiosk_ins_crm.py <Repo> [TS-Ordner im Repo]
  CRM:       ... ~/Projects/liftpictures-crm-claude
  Dashboard: ... ~/Projects/dashboard2 src/components/kiosk
"""
import shutil
import subprocess
import sys
from pathlib import Path

app = Path(__file__).resolve().parents[1] / "kiosk_app"
ziel = Path(sys.argv[1])
ts_ordner = ziel / (sys.argv[2] if len(sys.argv) > 2 else "src/crm/customer/kiosk")

subprocess.run(["npm", "run", "build"], cwd=app, check=True)
oeffentlich = ziel / "public" / "kiosk"
if oeffentlich.exists():
    shutil.rmtree(oeffentlich)
shutil.copytree(app / "dist", oeffentlich)

KOPF = ("// AUTOMATISCH ERZEUGT aus testsoftware/kiosk_app (scripts/kiosk_ins_crm.py) - nicht von Hand aendern.\n"
        "// Gleiche Vorgaben wie am Automaten.\n")
ts_ordner.mkdir(parents=True, exist_ok=True)
for quelle, name in (("config.ts", "kioskConfig.ts"), ("vouchers.ts", "kioskVouchers.ts")):
    (ts_ordner / name).write_text(KOPF + (app / "src" / quelle).read_text(encoding="utf-8"), encoding="utf-8")
print("ok:", oeffentlich, ts_ordner)
