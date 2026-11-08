#!/usr/bin/env python3
"""Wyciąga teksty tr("...") z aplikacji i raportuje brakujące w katalogu locale/<lang>.json.
Użycie: python3 scripts/extract-strings.py [pl]   (kod wyjścia 1 = brakujące tłumaczenia)"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "apps"
lang = sys.argv[1] if len(sys.argv) > 1 else "pl"
strings = set()
for py in ROOT.rglob("*.py"):
    for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args \
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            strings.add(node.args[0].value)
# nazwy stron/kategorii przekazywane pośrednio
import re
for py in ROOT.rglob("*.py"):
    for m in re.finditer(r'TITLE, SUBTITLE, ICON = "([^"]+)", "([^"]+)"', py.read_text(encoding="utf-8")):
        strings.update(m.groups())
cat = json.loads((ROOT.parent / "apps/nova_store/catalog.json").read_text())
strings.update(c["name"] for c in cat["categories"])
strings.update(["very weak", "weak", "fair", "good", "strong", "Nova", "Violet", "Blue", "Cyan", "Green", "Orange",
                "Pink", "Red", "System", "Base", "Kernel", "Desktop", "Qt", "Computer", "Processor", "Graphics",
                "Memory", "Disk", "Firmware", "Hostname", "PID", "Name", "User", "CPU %", "Threads", "State"])
path = ROOT / "novakit/locale" / f"{lang}.json"
have = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
missing = sorted(s for s in strings if s not in have)
print(json.dumps(missing, ensure_ascii=False, indent=0))
print(f"# {len(strings)} tekstów, brakuje {len(missing)}", file=sys.stderr)
sys.exit(1 if missing else 0)
