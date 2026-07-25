# DOCUMENT_CONTENTS_SPEC.md
**Índice de contenidos por documento — Document Studio**
_Especificación acordada con Daniel, documento a documento. Cada bloque marca su ORIGEN:_
- **Auto** = lo rellena un motor (Financial/Signal/Sector/Strategy…) con dato real.
- **Manual** = lo escribe el asesor (dato comercial/de la operación que no está en las fuentes).
- **Mixto** = el sistema (Semantic/IA Claude) lo propone y el asesor lo edita.
- **Plantilla** = texto fijo (disclaimers, marca).

> Regla transversal: ningún bloque Auto inventa cifras. La IA (Claude) redacta/propone, nunca fabrica datos. Los bloques Mixto y Manual quedan siempre editables desde el editor de maquetación.

---

## 1 · TEASER (perfil ciego) — ✅ CERRADO (2026-07-24)
_Referencia: teaser real de BUD (`Teaser.pdf`). Formato: **1 página**, denso y visual. Anonimizado (sin nombre, CIF ni provincia exacta; métricas presentables sin permitir reidentificación)._

| # | Sección | Contenido | Origen |
|---|---|---|---|
| 1 | Descriptor anónimo (cabecera) | Titular tipo "Agencia independiente de marketing experiencial" | **Mixto** (Semantic/Claude propone desde perfil/actividad; asesor edita) |
| 2 | Descripción de la compañía | 2-3 bullets: qué hace, posicionamiento, trayectoria, modelo operativo | **Mixto** (Semantic/Claude propone; asesor edita) |
| 3 | Evolución de ingresos (M€) | Gráfico de barras multi-año + CAGR | **Auto** — Financial Intelligence Engine |
| 4 | Evolución de EBITDA (M€) | Gráfico de barras multi-año + CAGR | **Auto** — Financial Intelligence Engine |
| 5 | Servicios | Bullets de líneas de negocio | **Manual** (asesor) |
| 6 | Clientes | Descripción cualitativa de la cartera (sin nombres) | **Manual** |
| 7 | Sectores de clientes (%) | Desglose por sector de la cartera (Tecnología 64%…) | **Manual** (dato comercial, no está en Iberinform) |
| 8 | Transacción | % del capital en venta + momento de la operación | **Manual** (dato de la operación) |
| 9 | Oportunidad de inversión | Bullets de razones + párrafo con el motivo de la venta | **Mixto** (razones del assessment del motor + edición) |
| 10 | Disclaimer legal | Texto legal al pie | **Plantilla** |

**Implicaciones de implementación (pendientes, no bloquean el índice):**
- Añadir a `compose_teaser` los **2 bloques `chart`** de evolución (ingresos y EBITDA con CAGR) — el dato ya lo da el Financial Engine (`evolution.points` + `kpis.revenue_cagr`).
- Bloques 1, 2 y 9 (Mixto): proponer con Semantic profile + Claude; quedan editables. Sin `EMERGENT_LLM_KEY` salen vacíos/deterministas y el asesor los rellena.
- Bloques 5, 6, 7, 8 (Manual): crear bloques editables vacíos con placeholder para que el asesor los rellene (el editor ya soporta añadir/editar bloques).
- Anonimización: el teaser NO incluye nombre/CIF/provincia; métricas redondeadas.

---

## 2 · INFOMEMO (Information Memorandum) — ✅ CERRADO (2026-07-24)
_Documento extenso. Identificado (a diferencia del teaser). Mezcla de datos automáticos, base propuesta por el sistema (Mixto) y contenido comercial del asesor/cliente (Manual, vía `manual_blocks` o editor)._

| # | Sección | Contenido | Origen |
|---|---|---|---|
| 1 | Portada + confidencialidad | Título, proyecto, disclaimer | Plantilla |
| 2 | Resumen ejecutivo | Síntesis de la oportunidad y tesis | Mixto (Claude + edición) |
| 3 | Descripción de la compañía | Datos generales + historia/actividad | Mixto (identidad auto; relato Semantic/Claude) |
| 4 | Productos y servicios | Líneas de negocio, propuesta de valor | Manual (placeholder a completar) |
| 5 | Clientes y cartera | Descripción, recurrencia, sectores de cliente | Manual (placeholder) |
| 6 | Equipo y organización | Plantilla + órganos de administración reales + organigrama | **Mixto** (administradores/empleados auto; equipo directivo manual) |
| 7 | Mercado y sector | Tamaño, tendencias, dinámica | Auto — Sector/Economic Intelligence |
| 8 | Análisis financiero | KPIs + **gráficos de evolución (ingresos/EBITDA + CAGR)** + histórico | Auto — Financial Engine |
| 9 | Posicionamiento y comparables | Benchmark sectorial | Auto — Financial + benchmark |
| 10 | Proyecciones / plan de negocio | Escenarios (conservador/base/agresivo) como base | **Mixto** (escenarios del Strategy Engine + edición) |
| 11 | Estructura de la operación | Qué se vende, %, condiciones, motivo | Manual (placeholder) |
| 12 | Valoración | Rango orientativo (método real, honesto) | Auto — Financial `valuation()` |
| 13 | Riesgos y oportunidades | Assessment real + señales activas | Auto — Financial + Signal |
| 14 | Hallazgos clave + Conclusión | Síntesis y recomendaciones | Mixto (Claude) |

**Implementado en `compose_information_memorandum`:** añadidos los 2 gráficos de evolución (8), la base de Equipo (administradores reales de `norm_officers` + plantilla, editable), la base de Proyecciones (escenarios del Strategy Engine, editable), y secciones-placeholder editables para lo comercial (Productos/servicios, Clientes, Estructura de la operación). Los `[Completar: …]` son bloques manuales que el asesor/consumidor rellena (o llegan por `manual_blocks`).
