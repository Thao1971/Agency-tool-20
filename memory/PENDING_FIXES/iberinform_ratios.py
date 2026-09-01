"""Curación de los 28 ratios de Iberinform decididos con Daniel (2026-07-24, ver
memory/IBERINFORM_RATIOS_PRIORITY.md).

Contexto: Iberinform entrega 31 ratios precalculados por empresa-año en
`Datos_RATIOS.tab`. La ingesta (`services/data_layer/ingestion/iberinform_tab_ingest.py
::ingest_ratios_file`) ya los guarda ÍNTEGROS desde el 24/07 en el propio documento
`norm_financials` (campo `ratios`: código Iberinform → valor, más `ratios_source:
"iberinform"` para poder distinguirlos de cualquier otro uso del nombre "ratios") —
pero hasta ahora nada los leía de vuelta (ver `memory/AUDITORIA_DATOS_IBERINFORM_NO_
EXPUESTOS.md`, punto 2). Este módulo selecciona los 28 acordados (fuera quedan, por
decisión de Daniel, los 3 de Tier 4 — riesgo de crédito comercial, no relevantes en
sell-side: OC1, SF019, SF024) y les da un nombre canónico + etiqueta en español + tier
de prioridad, para exponerlos en la Ficha SIN tocar los ratios que ya calcula arroba
(campo `ratios` del mismo bloque financiero — nombre de campo distinto a propósito:
`iberinform_ratios`, para que nunca se confundan ni se pisen).

⚠️ SF021/SF022/SF023 (periodos medios de cobro/pago/aprovisionamiento) y SF006/SF007
(ratios de endeudamiento A/B) llevan nombre "propuesto, verificar" en el documento de
origen — antes de dar esto por cerrado, cotejar código y signo contra
`Diccionario_Datos_Financial_Info.pdf` (entregado junto a la muestra real de Daniel,
no incluido en este repo). Se marcan como `verified: False` en la salida de `curate()`
para que la Ficha, si quiere, pueda señalarlos como "pendiente de verificar" en vez de
ocultarlos — decisión de presentación, no de este módulo.
"""

from typing import Dict, Optional, Tuple

# código Iberinform -> (nombre_canónico, etiqueta ES, tier 1-3)
IBERINFORM_RATIOS: Dict[str, Tuple[str, str, int]] = {
    # ── Tier 1 — máxima prioridad (nuevo e imprescindible; hoy imposible o score propietario) ──
    "R01": ("rating_iberinform", "Rating Iberinform", 1),
    "S01": ("solvency_score", "Score de solvencia", 1),
    "SF025": ("interest_coverage", "Cobertura de intereses", 1),
    "SF021": ("avg_collection_period", "Periodo medio de cobro", 1),
    "SF022": ("avg_payment_period", "Periodo medio de pago", 1),
    "SF023": ("avg_supply_period", "Periodo medio de aprovisionamiento", 1),
    "PRO001": ("working_capital", "Capital circulante", 1),
    "SF003": ("immediate_liquidity", "Liquidez inmediata", 1),
    "SF004": ("treasury_ratio", "Coeficiente de tesorería", 1),
    "SF008": ("debt_quality", "Calidad de la deuda", 1),
    "SF009": ("lt_debt_ratio", "Endeudamiento a largo plazo", 1),
    "SF010": ("st_debt_ratio", "Endeudamiento a corto plazo", 1),
    # ── Tier 2 — alta (eficiencia/productividad) ──
    "EFI008": ("personnel_expense_per_employee", "Gasto de personal por empleado", 2),
    "EFI006": ("sales_per_employee", "Ventas por empleado", 2),
    "PRO002": ("productivity", "Productividad", 2),
    "PRO005": ("leverage", "Apalancamiento", 2),
    "EFI001": ("asset_turnover", "Rotación de activo", 2),
    "EFI003": ("working_capital_turnover", "Rotación del circulante", 2),
    # ── Tier 3 — media (arroba ya calcula el equivalente propio; se ingiere el oficial
    #    de Iberinform como validación cruzada, nunca sustituye al propio) ──
    "REN007": ("ebitda_margin_iberinform", "Margen EBITDA (Iberinform)", 3),
    "REN005": ("net_margin_iberinform", "Margen neto (Iberinform)", 3),
    "REN006": ("margin_on_sales", "Margen sobre ventas", 3),
    "REN001": ("roa_iberinform", "Rentabilidad económica · ROA (Iberinform)", 3),
    "REN003": ("roe_iberinform", "Rentabilidad financiera · ROE (Iberinform)", 3),
    "REN010": ("sales_variation", "Variación de ventas", 3),
    "SF001": ("solvency_ratio", "Ratio de solvencia", 3),
    "SF006": ("debt_ratio_a", "Ratio de endeudamiento A", 3),
    "SF007": ("debt_ratio_b", "Ratio de endeudamiento B", 3),
    "SF011": ("guarantee_ratio", "Coeficiente de garantía", 3),
}

# Nombres "propuesto, verificar" en IBERINFORM_RATIOS_PRIORITY.md — no confirmados
# contra el diccionario oficial de Iberinform.
UNVERIFIED_CODES = {"SF021", "SF022", "SF023", "SF006", "SF007"}


def curate(raw_ratios: Optional[Dict[str, float]]) -> Optional[Dict[str, Dict]]:
    """`raw_ratios`: dict código Iberinform -> valor, tal cual llega de
    `norm_financials.<doc>.ratios` (sin curar, los 31). Devuelve un dict
    `nombre_canónico -> {value, label_es, code, tier, verified}` con solo los 28
    códigos acordados que además tengan valor no nulo en este company-año — R15:
    nunca inventa ni interpola un ratio que Iberinform no entregó para este ejercicio.
    `None` si no hay nada que mostrar (empresa sin Datos_RATIOS.tab, o sin ninguno de
    los 28 con valor)."""
    if not raw_ratios:
        return None
    out: Dict[str, Dict] = {}
    for code, (name, label_es, tier) in IBERINFORM_RATIOS.items():
        val = raw_ratios.get(code)
        if val is not None:
            out[name] = {
                "value": val,
                "label_es": label_es,
                "code": code,
                "tier": tier,
                "verified": code not in UNVERIFIED_CODES,
            }
    return out or None
