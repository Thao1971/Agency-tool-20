"""Clasificador de intención DETERMINISTA (sin IA). Mapea texto/pantalla del usuario a un nivel de
enrutado (L0–L4) y a los especialistas/capacidad objetivo.

Robustez: normaliza acentos y mayúsculas antes de casar palabras clave (tolerante a "valoracion" /
"Valoración"). Prioridad: comparativo-temporal > capacidad > decisión > dominio > hecho > overview.
El comparativo-temporal ("¿ha mejorado respecto al último análisis?", "compárala con la anterior") se
enruta a L3 porque el flujo del comité ya narra la evolución frente al análisis previo.
"""

import re
import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " " + re.sub(r"\s+", " ", s).strip() + " "


# L0 — hechos: palabra (normalizada) → clave de KPI
FACT_METRICS = {
    "ebitda": "ebitda", "facturacion": "revenue", "ingresos": "revenue", "ventas": "revenue",
    "revenue": "revenue", "margen": "ebitda_margin", "empleados": "employees",
    "plantilla": "employees", "deuda": "net_debt", "apalancamiento": "net_debt",
    "solvencia": "solvency", "autonomia": "solvency", "cagr": "revenue_cagr",
    "crecimiento": "revenue_cagr", "productividad": "revenue_per_employee",
}

# Comparativo-temporal (misma compañía frente a su pasado) → L3 (el comité narra la evolución).
EVOLUTION = ("ha mejorado", "ha empeorado", "ha cambiado", "respecto al anterior",
             "respecto a antes", "respecto al ultimo", "desde la ultima", "desde el ultimo",
             "la ultima vez", "ultimo analisis", "comparado con antes", "con la anterior",
             "que la anterior", "evolucion", "como va respecto", "sigue igual")

L4 = [
    # Peers/comparables (taxonomía ARROBA) — antes que 'compare' para que "comparables" no caiga en compare.
    (("comparable", "comparables", "similar", "similares", "parecid", "peers", "empresas como",
      "companias como", "compañias como"), "peers"),
    # Búsqueda por sector/vertical de la taxonomía ARROBA.
    (("empresas del sector", "companias del sector", "compañias del sector", "empresas del vertical",
      "empresas de la industria"), "taxo_search"),
    (("comparar", "compara", "versus", " vs ", "frente a", "mejor entre", "cual es mejor"), "compare"),
    (("cartera", "portfolio", "portafolio"), "portfolio"),
    (("recomiendame", "recomienda oportunidades", "busca objetivos", "encuentra objetivos",
      "oportunidades para", "que compro", "que empresas"), "recommend"),
]
DECISION = ("comprar", "compramos", "adquirir", "invertir", "invierto", "deberiamos", "deberia",
            "procede la", "luz verde", "recomiendas la operacion", "tomar la decision",
            "seguir adelante", "entramos", "cerramos la operacion", "merece la pena")
DOMAIN = {
    "valuation": ("valor", "valoracion", "cuanto vale", "cuanto cuesta", "multiplo", "precio", "cuanto pagar"),
    "risk": ("riesgo", "riesgos", "peligro", "amenaza", "red flag", "banderas rojas"),
    "legal": ("legal", "legales", "propiedad", "accionariado", "cap table", "litigio",
              "contingencia", "societario"),
    "strategy": ("estrategia", "encaje", "encaja", "sinergia", "sinergias", "tesis"),
    "market": ("mercado", "sector", "competencia", "competidores", "posicion", "hhi",
               "consolidacion", "cuota"),
    "commercial": ("clientes", "recurrencia", "cartera de clientes", "concentracion de clientes",
                   "ingresos recurrentes"),
    "operations": ("operativa", "escalabilidad", "productividad", "eficiencia", "operaciones"),
    "hr": ("equipo", "directivo", "sucesion", "relevo", "continuidad", "talento", "plantilla clave"),
    "cfo": ("finanzas", "financiero", "rentabilidad", "caja", "circulante", "beneficio", "margenes"),
}


# Palabras que NO son nombres de empresa aunque vayan capitalizadas o en mayúsculas.
_STOP_ENTITY = {"EBITDA", "CAGR", "IVA", "M&A", "PE", "CEO", "CFO", "DD", "KPI", "TAM", "SAM", "SOM"}


def extract_entities(text: str):
    """Heurística ligera: candidatos a nombre de empresa (tokens en mayúsculas o Capitalizados de ≥3
    letras), excluyendo acrónimos comunes. No resuelve a id (eso es del resolver); solo detecta menciones."""
    import re as _re
    raw = _re.findall(r"\b[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑ0-9&]{2,}\b", text or "")
    out, seen = [], set()
    for tok in raw:
        up = tok.upper()
        if up in _STOP_ENTITY or up in seen:
            continue
        seen.add(up)
        out.append(tok)
    return out


def classify(text: str, screen: str = None) -> dict:
    t = _norm(text)

    # Comparativo-temporal → L3 (antes que L4: "compárala con la anterior" es evolución, no comparar dos).
    if any(k in t for k in EVOLUTION):
        return {"level": "L3", "capability": None, "targets": [], "metric": None, "kind": "evolution"}

    # L4 — capacidades
    for kws, cap in L4:
        if any(_norm(k).strip() in t for k in kws):
            return {"level": "L4", "capability": cap, "targets": [], "metric": None, "kind": None}

    # L4 taxo_search "inteligente": consultas de listado ("empresas/compañías de <X>", "firmas en <X>")
    # donde <X> resuelve a un sector/vertical real de la taxonomía. Va DESPUÉS del loop L4 (peers/compare/
    # recommend explícitos ganan) y ANTES de DECISION, para no robar intents de recomendación/decisión.
    m = re.search(r"\b(?:empresas|companias|compa[nñ]ias|firmas|negocios|startups|scaleups)\s+"
                  r"(?:del sector|de la industria|de la|del|de|en el|en|sector)\s+(.+)", t)
    if m:
        try:
            from services.taxonomy import search as _SR
            if _SR.resolve_label(m.group(1)):
                return {"level": "L4", "capability": "taxo_search", "targets": [],
                        "metric": None, "kind": None}
        except Exception:
            pass

    # L3 — decisión de inversión (comité completo)
    if any(k in t for k in DECISION):
        return {"level": "L3", "capability": None, "targets": [], "metric": None, "kind": None}

    # L1/L2 — dominios
    hits = [name for name, kws in DOMAIN.items() if any(k in t for k in kws)]
    if hits:
        level = "L2" if len(hits) >= 2 else "L1"
        return {"level": level, "capability": None, "targets": hits[:3], "metric": None, "kind": None}

    # L0 — hecho puntual
    for word, metric in FACT_METRICS.items():
        if re.search(rf"\b{re.escape(word)}\b", t):
            return {"level": "L0", "capability": None, "targets": [], "metric": metric, "kind": None}

    # Por defecto: overview (hechos clave), sin convocar comité
    return {"level": "L0", "capability": None, "targets": [], "metric": "__overview__", "kind": None}
