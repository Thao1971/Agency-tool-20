"""Reusable financial ratio library. Each ratio is fully explainable:
formula + explanation + category + inputs + source/traceability. No AI.
"""

from typing import Callable, Dict, List, Optional


def _safe_div(a, b):
    if a is None or b in (None, 0):
        return None
    return round(a / b, 4)


# key: (name, category, formula, explanation, compute(metrics, employees))
_DEFS = {
    "ebitda_margin": ("Margen EBITDA", "profitability", "EBITDA / Ingresos",
                      "Rentabilidad operativa antes de amortizaciones.",
                      lambda m, e: _safe_div(m.get("ebitda"), m.get("revenue"))),
    "ebit_margin": ("Margen EBIT", "profitability", "EBIT / Ingresos",
                    "Rentabilidad operativa tras amortizaciones.",
                    lambda m, e: _safe_div(m.get("ebit"), m.get("revenue"))),
    "net_margin": ("Margen neto", "profitability", "Beneficio neto / Ingresos",
                   "Porcentaje de ingresos que se convierte en beneficio.",
                   lambda m, e: _safe_div(m.get("net_income"), m.get("revenue"))),
    "gross_margin": ("Margen bruto", "profitability", "(Ingresos - Aprovisionamientos) / Ingresos",
                     "Margen tras coste directo de aprovisionamientos.",
                     lambda m, e: _safe_div((m.get("revenue") - m.get("supplies"))
                                            if (m.get("revenue") is not None and m.get("supplies") is not None) else None,
                                            m.get("revenue"))),
    "roa": ("ROA", "profitability", "Beneficio neto / Activo total",
            "Rentabilidad económica sobre activos.",
            lambda m, e: _safe_div(m.get("net_income"), m.get("total_assets"))),
    "roe": ("ROE", "profitability", "Beneficio neto / Patrimonio neto",
            "Rentabilidad financiera para el accionista.",
            lambda m, e: _safe_div(m.get("net_income"), m.get("equity"))),
    "current_ratio": ("Ratio de liquidez", "liquidity", "Activo corriente / Pasivo corriente",
                      "Capacidad de cubrir obligaciones a corto plazo.",
                      lambda m, e: _safe_div(m.get("current_assets"), m.get("current_liabilities"))),
    "solvency": ("Solvencia (autonomía)", "solvency", "Patrimonio neto / Activo total",
                 "Proporción de activos financiada con fondos propios.",
                 lambda m, e: _safe_div(m.get("equity"), m.get("total_assets"))),
    "debt_ratio": ("Ratio de endeudamiento", "solvency", "Pasivo total / Activo total",
                   "Grado de apalancamiento sobre el activo.",
                   lambda m, e: _safe_div(m.get("total_liabilities"), m.get("total_assets"))),
    "debt_to_equity": ("Deuda financiera / Fondos propios", "solvency",
                       "Deuda financiera / Patrimonio neto",
                       "Apalancamiento financiero respecto a fondos propios.",
                       lambda m, e: _safe_div(m.get("financial_debt"), m.get("equity"))),
    "interest_coverage": ("Cobertura de intereses", "solvency", "EBIT / Gastos financieros",
                          "Veces que el resultado operativo cubre los intereses.",
                          lambda m, e: _safe_div(m.get("ebit"), m.get("financial_expenses"))),
    "revenue_per_employee": ("Productividad (ingresos/empleado)", "efficiency",
                             "Ingresos / Nº empleados",
                             "Ingresos generados por empleado.",
                             lambda m, e: _safe_div(m.get("revenue"), e)),
    "capital_intensity": ("Intensidad de capital", "efficiency", "Activo total / Ingresos",
                          "Activos necesarios por unidad de ingreso.",
                          lambda m, e: _safe_div(m.get("total_assets"), m.get("revenue"))),
    # Working-capital / cash-cycle ratios (need full-EAV line items; N/D on abbreviated data).
    "dso": ("Periodo medio de cobro (días)", "working_capital", "Clientes / Ingresos × 365",
            "Días que tarda en cobrar a clientes.",
            lambda m, e: _safe_div(m.get("trade_debtors"), m.get("revenue")) and
                         round(_safe_div(m.get("trade_debtors"), m.get("revenue")) * 365, 1)),
    "dpo": ("Periodo medio de pago (días)", "working_capital", "Proveedores / Aprovisionamientos × 365",
            "Días que tarda en pagar a proveedores.",
            lambda m, e: _safe_div(m.get("suppliers"), m.get("supplies")) and
                         round(_safe_div(m.get("suppliers"), m.get("supplies")) * 365, 1)),
    "inventory_days": ("Días de existencias", "working_capital", "Existencias / Aprovisionamientos × 365",
                       "Días de stock sobre el consumo.",
                       lambda m, e: _safe_div(m.get("inventories"), m.get("supplies")) and
                                    round(_safe_div(m.get("inventories"), m.get("supplies")) * 365, 1)),
    "cash_conversion_cycle": ("Ciclo de conversión de caja (días)", "working_capital",
                              "PMC + Días existencias − PMP",
                              "Días netos que el circulante inmoviliza caja.",
                              lambda m, e: _ccc(m)),
    "working_capital": ("Fondo de maniobra", "working_capital",
                        "Activo corriente − Pasivo corriente",
                        "Capital circulante neto disponible.",
                        lambda m, e: (round(m.get("current_assets") - m.get("current_liabilities"), 2)
                                      if (m.get("current_assets") is not None
                                          and m.get("current_liabilities") is not None) else None)),
}


def _ccc(m: Dict):
    """Cash conversion cycle = DSO + inventory days − DPO (days). None if inputs missing."""
    dso = _safe_div(m.get("trade_debtors"), m.get("revenue"))
    inv = _safe_div(m.get("inventories"), m.get("supplies"))
    dpo = _safe_div(m.get("suppliers"), m.get("supplies"))
    if dso is None or dpo is None:
        return None
    return round((dso + (inv or 0) - dpo) * 365, 1)

SOURCE = "Iberinform statements (Normalized Layer)"


def definitions() -> List[Dict]:
    return [{"key": k, "name": v[0], "category": v[1], "formula": v[2], "explanation": v[3]}
            for k, v in _DEFS.items()]


def compute_all(metrics: Dict, employees: Optional[int]) -> Dict[str, Dict]:
    """Compute every ratio for one year, returning value + full explainability."""
    out = {}
    for key, (name, category, formula, explanation, fn) in _DEFS.items():
        try:
            value = fn(metrics, employees)
        except Exception:
            value = None
        out[key] = {"value": value, "name": name, "category": category,
                    "formula": formula, "explanation": explanation,
                    "source": SOURCE, "available": value is not None}
    return out
