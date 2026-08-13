"""Etiqueta CNAE en español (catálogo oficial `borme/cnae2025.json`).

El master sirve el literal en inglés (`cnae_description`); esto devuelve la etiqueta ES
que necesita la ficha (p. ej. "2120" -> "Fabricación de especialidades farmacéuticas").
"""
import json
import os
import re
from typing import Optional

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "borme", "cnae2025.json")
try:
    with open(_PATH, encoding="utf-8") as _f:
        _CNAE = json.load(_f)
except Exception:
    _CNAE = {}


def cnae_label_es(code) -> Optional[str]:
    """Etiqueta CNAE ES por código. Prueba clase (21.20) -> grupo (21.2) -> división (21)."""
    if not code:
        return None
    c = re.sub(r"\D", "", str(code))
    if not c:
        return None
    candidates = []
    if len(c) >= 4:
        candidates.append(f"{c[:2]}.{c[2:4]}")
    if len(c) >= 3:
        candidates.append(f"{c[:2]}.{c[2:3]}")
    candidates.append(c[:2])
    for key in candidates:
        if key in _CNAE:
            return _CNAE[key]
    return None
