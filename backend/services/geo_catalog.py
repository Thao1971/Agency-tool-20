"""Spanish Geographic Catalog — CCAA and Provinces.

Official codes: INE codification.
17 CCAA + 2 Autonomous Cities = 19 entries.
50 Provinces + 2 Autonomous Cities = 52 entries.
"""

# ══════════════════════════════════════════
# CCAA (Comunidades Autónomas) — INE codes
# ══════════════════════════════════════════

CCAA = [
    {"code": "01", "label": "Andalucía", "provinces": ["04", "11", "14", "18", "21", "23", "29", "41"]},
    {"code": "02", "label": "Aragón", "provinces": ["22", "44", "50"]},
    {"code": "03", "label": "Asturias, Principado de", "provinces": ["33"]},
    {"code": "04", "label": "Balears, Illes", "provinces": ["07"]},
    {"code": "05", "label": "Canarias", "provinces": ["35", "38"]},
    {"code": "06", "label": "Cantabria", "provinces": ["39"]},
    {"code": "07", "label": "Castilla y León", "provinces": ["05", "09", "24", "34", "37", "40", "42", "47", "49"]},
    {"code": "08", "label": "Castilla-La Mancha", "provinces": ["02", "13", "16", "19", "45"]},
    {"code": "09", "label": "Cataluña", "provinces": ["08", "17", "25", "43"]},
    {"code": "10", "label": "Comunitat Valenciana", "provinces": ["03", "12", "46"]},
    {"code": "11", "label": "Extremadura", "provinces": ["06", "10"]},
    {"code": "12", "label": "Galicia", "provinces": ["15", "27", "32", "36"]},
    {"code": "13", "label": "Madrid, Comunidad de", "provinces": ["28"]},
    {"code": "14", "label": "Murcia, Región de", "provinces": ["30"]},
    {"code": "15", "label": "Navarra, Comunidad Foral de", "provinces": ["31"]},
    {"code": "16", "label": "País Vasco", "provinces": ["01", "20", "48"]},
    {"code": "17", "label": "Rioja, La", "provinces": ["26"]},
    {"code": "18", "label": "Ceuta", "provinces": ["51"]},
    {"code": "19", "label": "Melilla", "provinces": ["52"]},
]

# ══════════════════════════════════════════
# PROVINCES — INE codes (2-digit)
# ══════════════════════════════════════════

PROVINCES = {
    "01": {"label": "Araba/Álava", "ccaa": "16"},
    "02": {"label": "Albacete", "ccaa": "08"},
    "03": {"label": "Alicante/Alacant", "ccaa": "10"},
    "04": {"label": "Almería", "ccaa": "01"},
    "05": {"label": "Ávila", "ccaa": "07"},
    "06": {"label": "Badajoz", "ccaa": "11"},
    "07": {"label": "Balears, Illes", "ccaa": "04"},
    "08": {"label": "Barcelona", "ccaa": "09"},
    "09": {"label": "Burgos", "ccaa": "07"},
    "10": {"label": "Cáceres", "ccaa": "11"},
    "11": {"label": "Cádiz", "ccaa": "01"},
    "12": {"label": "Castellón/Castelló", "ccaa": "10"},
    "13": {"label": "Ciudad Real", "ccaa": "08"},
    "14": {"label": "Córdoba", "ccaa": "01"},
    "15": {"label": "Coruña, A", "ccaa": "12"},
    "16": {"label": "Cuenca", "ccaa": "08"},
    "17": {"label": "Girona", "ccaa": "09"},
    "18": {"label": "Granada", "ccaa": "01"},
    "19": {"label": "Guadalajara", "ccaa": "08"},
    "20": {"label": "Gipuzkoa", "ccaa": "16"},
    "21": {"label": "Huelva", "ccaa": "01"},
    "22": {"label": "Huesca", "ccaa": "02"},
    "23": {"label": "Jaén", "ccaa": "01"},
    "24": {"label": "León", "ccaa": "07"},
    "25": {"label": "Lleida", "ccaa": "09"},
    "26": {"label": "Rioja, La", "ccaa": "17"},
    "27": {"label": "Lugo", "ccaa": "12"},
    "28": {"label": "Madrid", "ccaa": "13"},
    "29": {"label": "Málaga", "ccaa": "01"},
    "30": {"label": "Murcia", "ccaa": "14"},
    "31": {"label": "Navarra", "ccaa": "15"},
    "32": {"label": "Ourense", "ccaa": "12"},
    "33": {"label": "Asturias", "ccaa": "03"},
    "34": {"label": "Palencia", "ccaa": "07"},
    "35": {"label": "Palmas, Las", "ccaa": "05"},
    "36": {"label": "Pontevedra", "ccaa": "12"},
    "37": {"label": "Salamanca", "ccaa": "07"},
    "38": {"label": "Santa Cruz de Tenerife", "ccaa": "05"},
    "39": {"label": "Cantabria", "ccaa": "06"},
    "40": {"label": "Segovia", "ccaa": "07"},
    "41": {"label": "Sevilla", "ccaa": "01"},
    "42": {"label": "Soria", "ccaa": "07"},
    "43": {"label": "Tarragona", "ccaa": "09"},
    "44": {"label": "Teruel", "ccaa": "02"},
    "45": {"label": "Toledo", "ccaa": "08"},
    "46": {"label": "Valencia/València", "ccaa": "10"},
    "47": {"label": "Valladolid", "ccaa": "07"},
    "48": {"label": "Bizkaia", "ccaa": "16"},
    "49": {"label": "Zamora", "ccaa": "07"},
    "50": {"label": "Zaragoza", "ccaa": "02"},
    "51": {"label": "Ceuta", "ccaa": "18"},
    "52": {"label": "Melilla", "ccaa": "19"},
}


# ══════════════════════════════════════════
# BORME registry_province → Province code mapping
# ══════════════════════════════════════════
# BORME uses uppercase province names from the mercantile registry

BORME_PROVINCE_MAP = {
    "ALBACETE": "02", "ALICANTE/ALACANT": "03", "ALICANTE": "03",
    "ALMERÍA": "04", "ALMERIA": "04",
    "ARABA/ÁLAVA": "01", "ÁLAVA": "01", "ALAVA": "01",
    "ASTURIAS": "33", "ÁVILA": "05", "AVILA": "05",
    "BADAJOZ": "06", "ILLES BALEARS": "07", "BALEARS": "07", "BALEARES": "07",
    "BARCELONA": "08", "BIZKAIA": "48", "VIZCAYA": "48",
    "BURGOS": "09", "CÁCERES": "10", "CACERES": "10",
    "CÁDIZ": "11", "CADIZ": "11", "CANTABRIA": "39",
    "CASTELLÓN/CASTELLÓ": "12", "CASTELLÓN": "12", "CASTELLON": "12",
    "CIUDAD REAL": "13", "CÓRDOBA": "14", "CORDOBA": "14",
    "A CORUÑA": "15", "CORUÑA": "15", "LA CORUÑA": "15",
    "CUENCA": "16", "GIPUZKOA": "20", "GUIPÚZCOA": "20", "GUIPUZCOA": "20",
    "GIRONA": "17", "GRANADA": "18", "GUADALAJARA": "19",
    "HUELVA": "21", "HUESCA": "22", "JAÉN": "23", "JAEN": "23",
    "LEÓN": "24", "LEON": "24", "LLEIDA": "25", "LÉRIDA": "25",
    "LUGO": "27", "MADRID": "28", "MÁLAGA": "29", "MALAGA": "29",
    "MURCIA": "30", "NAVARRA": "31",
    "OURENSE": "32", "ORENSE": "32",
    "PALENCIA": "34", "LAS PALMAS": "35", "PALMAS": "35",
    "PONTEVEDRA": "36", "LA RIOJA": "26", "RIOJA": "26",
    "SALAMANCA": "37",
    "SANTA CRUZ DE TENERIFE": "38", "TENERIFE": "38", "S.C. TENERIFE": "38",
    "SEGOVIA": "40", "SEVILLA": "41", "SORIA": "42",
    "TARRAGONA": "43", "TERUEL": "44", "TOLEDO": "45",
    "VALENCIA/VALÈNCIA": "46", "VALENCIA": "46", "VALÈNCIA": "46",
    "VALLADOLID": "47", "ZAMORA": "49", "ZARAGOZA": "50",
    "CEUTA": "51", "MELILLA": "52",
}


def resolve_borme_province(registry_province: str) -> str | None:
    """Map BORME registry_province name to INE province code."""
    if not registry_province:
        return None
    return BORME_PROVINCE_MAP.get(registry_province.upper().strip())


def get_ccaa_for_province(province_code: str) -> str | None:
    """Get CCAA code for a province code."""
    prov = PROVINCES.get(province_code)
    return prov["ccaa"] if prov else None


def get_ccaa_label(ccaa_code: str) -> str | None:
    """Get CCAA label by code."""
    for c in CCAA:
        if c["code"] == ccaa_code:
            return c["label"]
    return None


def get_province_label(province_code: str) -> str | None:
    """Get province label by code."""
    prov = PROVINCES.get(province_code)
    return prov["label"] if prov else None


def build_geo_catalog():
    """Build full geographic catalog for API response."""
    result = []
    for ccaa in CCAA:
        provinces = []
        for prov_code in ccaa["provinces"]:
            prov_info = PROVINCES.get(prov_code, {})
            provinces.append({
                "code": prov_code,
                "label": prov_info.get("label", ""),
                "level": "province",
            })
        provinces.sort(key=lambda p: p["label"])
        result.append({
            "code": ccaa["code"],
            "label": ccaa["label"],
            "level": "ccaa",
            "provinces": provinces,
        })
    return result
