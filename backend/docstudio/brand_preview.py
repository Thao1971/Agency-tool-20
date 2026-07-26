"""Documento-muestra para el editor de marca en tiempo real.

Genera un doc de tipo 'slides' (mismo renderizador que el infomemo) que ejercita los
elementos cuyo estilo depende de la marca: portada negra, separador de sección, tarjetas
KPI, subtítulo con acento, tabla, insight y varios gráficos (barras, línea, donut). Así el
usuario ve EN VIVO cómo quedan sus colores/tipografías/logo sobre un documento real, sin
tener que guardar ni componer un infomemo completo (es instantáneo, no toca la BBDD)."""

from typing import Dict
from docstudio import (new_document, new_section, cover_block, text_block, kpi_block,
                       table_block, chart_block, insight_block)


def brand_sample_doc(brand: Dict = None) -> Dict:
    name = (brand or {}).get("name") or "Su Marca"
    doc = new_document(title="Vista previa de marca", brand_id=(brand or {}).get("brand_id", "brand_bud"))
    doc["metadata"] = {"type": "information_memorandum"}  # -> layout de slides

    # 1. Portada (negra / color de portada de la marca)
    s1 = new_section("Portada", 1, [
        cover_block(title="Cuaderno de Venta", subtitle=f"Vista previa · {name}"),
    ])
    s1["blocks"][0]["data"]["date"] = "Ejemplo"
    s1["blocks"][0]["data"]["advisor"] = name

    # 2. Separador de sección (usa el acento de la marca)
    sep = new_section("Resumen y Compañía", 0, [])
    sep["slide_kind"] = "separator"; sep["section_number"] = "01"

    # 3. Contenido: KPIs + subtítulo + tabla + insight
    s2 = new_section("Resumen Ejecutivo", 2, [
        kpi_block("Facturación 2024", "164.200.180", "€", commentary="crecimiento sostenido"),
        kpi_block("Margen EBITDA", "11,3 %", "", commentary="rentabilidad operativa sólida"),
        kpi_block("Empleados", "346", "personas", commentary="equipo a cierre de ejercicio"),
        text_block("Fortalezas del negocio", "subhead"),
        table_block("", ["Métrica", "Q1", "Mediana", "Q3"],
                    [["Ingresos (€)", "5,0 M", "12,0 M", "25,0 M"],
                     ["Margen EBITDA", "6 %", "12 %", "22 %"]]),
        insight_block("Posición competitiva",
                      "La compañía se sitúa por encima de la mediana del sector en rentabilidad y "
                      "productividad, con un modelo escalable.", importance="medium"),
    ])

    # 4. Gráficos (barras, línea, donut) — para ver el acento y la paleta en los charts
    s3 = new_section("Análisis Financiero", 3, [
        chart_block("Evolución de ingresos", "bar",
                    {"bars": [{"label": "2022", "value": 137_400_000},
                              {"label": "2023", "value": 147_000_000},
                              {"label": "2024", "value": 164_200_000}], "fmt": "millions"}),
        chart_block("Evolución de EBITDA", "line",
                    {"points": [{"label": "2022", "value": 14_800_000},
                                {"label": "2023", "value": 16_500_000},
                                {"label": "2024", "value": 18_500_000}],
                     "value_key": "value", "fmt": "millions"}),
        chart_block("Composición de la plantilla", "donut",
                    {"segments": [{"label": "Hombres", "value": 190, "color": "#2E6BB0"},
                                  {"label": "Mujeres", "value": 156, "color": "#C9569A"}]}),
    ])
    doc["sections"] = [s1, sep, s2, s3]
    return doc
