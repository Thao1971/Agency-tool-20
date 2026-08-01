"""Puente CNAE → ARROBA. El CNAE da un ANCLA (no la última palabra); las reglas de alias/semántica
refinan. Sección CNAE → sector ARROBA (siempre); + hints división→industria para casos de alta señal.
Ver memory/ARROBA_TAXONOMY_ENGINE_DESIGN.md (P1)."""

# Sección CNAE (A–U) → sector ARROBA (ancla coarse; las reglas afinan y pueden mover a otro sector).
SECTION_TO_SECTOR = {
    "A": "S11", "B": "S06", "C": "S06", "D": "S07", "E": "S07", "F": "S06", "G": "S04", "H": "S10",
    "I": "S04", "J": "S02", "K": "S08", "L": "S09", "M": "S01", "N": "S01", "O": "S01", "P": "S01",
    "Q": "S05", "R": "S03", "S": "S01", "T": "S01", "U": "S01",
}

# División CNAE (2 díg.) → (sector, etiqueta de industria ARROBA) para los casos claros.
DIVISION_TO_INDUSTRY = {
    "62": ("S02", "Desarrollo de software"),
    "63": ("S03", "Medios digitales"),
    "58": ("S02", "Software empresarial"),
    "59": ("S03", "Televisión y vídeo"),
    "60": ("S03", "Audio"),
    "73": ("S03", "Agencias creativas"),
    "70": ("S01", "Consultoría empresarial"),
    "69": ("S01", "Servicios legales"),
    "71": ("S01", "Ingeniería y servicios técnicos"),
    "78": ("S01", "Recursos humanos"),
    "82": ("S01", "BPO"),
    "64": ("S08", "Banca"),
    "65": ("S08", "Seguros"),
    "66": ("S08", "Servicios de inversión"),
    "86": ("S05", "Hospitales"),
    "72": ("S05", "CRO y servicios farmacéuticos"),
    "49": ("S10", "Transporte terrestre"),
    "52": ("S10", "Logística"),
    "68": ("S09", "Servicios inmobiliarios"),
    "41": ("S06", "Construcción"),
    "47": ("S04", "Retail especializado"),
    "56": ("S04", "Restauración organizada"),
    "35": ("S07", "Electricidad"),
    "10": ("S11", "Alimentación"),
}


def _digits(code) -> str:
    return "".join(ch for ch in str(code or "") if ch.isdigit())


def anchor_from_cnae(code):
    """Devuelve (sector_id, industry_label|None) para un código/ sección CNAE. Nunca lanza."""
    if not code:
        return (None, None)
    c = str(code).strip()
    if len(c) == 1 and c.isalpha():
        return (SECTION_TO_SECTOR.get(c.upper()), None)
    d = _digits(c)
    if len(d) >= 2 and d[:2] in DIVISION_TO_INDUSTRY:
        return DIVISION_TO_INDUSTRY[d[:2]]
    # sección vía catálogo CNAE
    try:
        from services.cnae_catalog import resolve_cnae_to_section
        sec = resolve_cnae_to_section(c)
        if sec:
            return (SECTION_TO_SECTOR.get(sec), None)
    except Exception:
        pass
    return (None, None)
