"""Liftpic Sync package."""

# Die Version, die im Herzschlag landet und im Dashboard steht.
#
# Sie stand monatelang konstant auf "0.1.0" - damit war am Server nicht
# ablesbar, welcher Stand auf einem Automaten laeuft. Bei Imst hiess das: man
# konnte den alten Stand nicht vom neuen unterscheiden, und die Zahl war
# wertlos fuer genau die Frage, fuer die sie da ist.
#
# Beim Anheben eines Standes wird sie hier UND als Git-Tag gesetzt
# (`v<version>`), damit `build-windows.yml` das passende Artefakt baut und
# `update_liftpic.ps1 -Tag v<version>` genau diesen Stand installiert.
__version__ = "0.2.1"
