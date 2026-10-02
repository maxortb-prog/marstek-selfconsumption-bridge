#!/usr/bin/env python3
"""Prueft, ob jedes ``self.x`` auch definiert ist.

Hintergrund: Ruff und ``compileall`` finden fehlende Attribute nicht - ein
versehentlich geloeschter Methodenblock faellt erst zur Laufzeit auf, und dann
womoeglich erst nach Stunden im Betrieb. Dieses Skript geht den Syntaxbaum
durch und meldet jeden Zugriff auf ``self.<name>``, zu dem es weder eine
Methode noch eine Zuweisung noch ein Klassenattribut gibt.

    python3 tools/check_self_attributes.py

Rueckgabewert 1, wenn etwas fehlt.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

PAKET = Path(__file__).resolve().parent.parent / "marstek_bridge"
WURZEL = PAKET / "app"

# Von der Basisklasse erst zur Laufzeit gesetzt, stehen also nicht in dir().
BEKANNT = {"path", "wfile"}


def geerbt(modul: str, klasse: str) -> set[str]:
    """Namen, die die Klasse von ihren Basisklassen mitbringt."""
    sys.path.insert(0, str(PAKET))
    try:
        objekt = getattr(importlib.import_module(f"app.{modul}"), klasse, None)
        return set(dir(objekt)) if objekt is not None else set()
    except Exception:  # Modul nicht importierbar - dann eben ohne
        return set()
    finally:
        sys.path.remove(str(PAKET))


def pruefe_klasse(klasse: ast.ClassDef) -> set[str]:
    definiert: set[str] = set()
    for knoten in ast.walk(klasse):
        if isinstance(knoten, ast.FunctionDef | ast.AsyncFunctionDef):
            definiert.add(knoten.name)
        elif isinstance(knoten, ast.Assign):
            for ziel in knoten.targets:
                if isinstance(ziel, ast.Attribute) and _ist_self(ziel.value):
                    definiert.add(ziel.attr)
                elif isinstance(ziel, ast.Name):
                    definiert.add(ziel.id)
        elif isinstance(knoten, ast.AnnAssign):
            ziel = knoten.target
            if isinstance(ziel, ast.Attribute) and _ist_self(ziel.value):
                definiert.add(ziel.attr)
            elif isinstance(ziel, ast.Name):
                definiert.add(ziel.id)

    benutzt: set[str] = set()
    for knoten in ast.walk(klasse):
        if isinstance(knoten, ast.Attribute) and _ist_self(knoten.value):
            benutzt.add(knoten.attr)
    return benutzt - definiert - BEKANNT


def _ist_self(knoten: ast.AST) -> bool:
    return isinstance(knoten, ast.Name) and knoten.id == "self"


def main() -> int:
    fehler = 0
    for datei in sorted(WURZEL.glob("*.py")):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        for knoten in baum.body:
            if not isinstance(knoten, ast.ClassDef):
                continue
            fehlend = sorted(
                pruefe_klasse(knoten) - geerbt(datei.stem, knoten.name)
            )
            if fehlend:
                fehler += len(fehlend)
                print(f"{datei.name}: Klasse {knoten.name}")
                for name in fehlend:
                    print(f"    fehlt: self.{name}")
    if fehler:
        print(f"\n{fehler} fehlende Attribute oder Methoden gefunden.")
        return 1
    print("Alle self-Zugriffe sind definiert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
