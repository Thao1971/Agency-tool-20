# Sprint 2 — Financial Intelligence Engine ✅ COMPLETADO
_Fecha de cierre: 2026-06-25 · Estado: oficialmente completado · Tests: 160/160 smoke verdes (153 previos + 7 nuevos)._

> **Este documento es la referencia oficial del Financial Intelligence Engine para todo el ecosistema (arroba.com, APIs, Copilots, futuros motores).**

---

## 1. Qué es el Financial Intelligence Engine

Servicio de inteligencia **desacoplado y reutilizable** que produce el perfil financiero completo de una empresa a partir **exclusivamente** del Master Layer (`master_companies`) + estados normalizados internos (`norm_financials`). Reglas deterministas, **sin IA**, **100% explicable**. La valoración es **una capacidad más** entre KPIs, ratios, evolución, calidad y comparables.

- **Versión del motor**: `financial-intelligence-v1`
- **Código**: `/app/backend/services/engines/financial/` (`engine.py`, `metrics.py`, `ratios_library.py`)
- **API**: `/app/backend/routes/financial_intelligence.py`
- **Contrato**: `/app/memory/FINANCIAL_INTELLIGENCE_ENGINE_CONTRACT.md`

---

## 2. Validación: ¿es realmente un motor? ✅

| Requisito | Verificación | Resultado |
|---|---|---|
| Ningún consumidor accede directamente a `master_companies` | El motor es el **boundary**: lee `master_companies` + `norm_financials` internamente; los consumidores solo invocan la API del motor | ✅ |
| Todo pasa por el Financial Intelligence Engine | KPIs, ratios, evolución, calidad, comparables y valoración se sirven **solo** a través de `/api/v1/financial-intelligence/*` | ✅ |
| Reutilizable desde arroba, APIs, Copilots o futuros motores sin depender de ningún consumidor concreto | El motor **no importa** ningún módulo de arroba/Copilot/UI. Autenticación por **service key** (`X-API-Key`), no por JWT de usuario | ✅ |
| Aislamiento de dependencias | `engine.py` solo importa `database`, `models`, `metrics`, `ratios_library` | ✅ |

**Conclusión**: el motor cumple el principio *Boundary First*. Cualquier consumidor (presente o futuro) obtiene inteligencia financiera **únicamente** vía API, sin tocar fuentes ni el Master directamente.

---

## 3. Validación: explicabilidad completa ✅ (no es una caja negra)

Cada capacidad expone trazabilidad total — datos usados, fuente, fecha, reglas y confianza:

| Capacidad | Trazabilidad expuesta |
|---|---|
| **Ratios** | `value` · `name` · `formula` · `explanation` · `category` · `source` · `available` (por cada ratio) |
| **KPIs** | Derivados de `statements` (mismas fuentes); consistencia interna verificada (`ebitda_margin == ebitda/revenue`) |
| **Valoración** | `method` · `multiple` · `multiple_basis` (`inferred_reference` — honesto, no observado en mercado) · `hypotheses[]` · `confidence` · `lineage` (fuente/basis/año) |
| **Comparables** | `criteria` (cnae_section + size_band + geography) · `method` (`structural`) · `embeddings_used=false` |
| **Calidad financiera** | `score` (0-100) · `rules[]` (cada regla con `points`/`max`/`passed`/`reason`) · `method=rules_based` · `ai_used=false`; `score == suma de reglas pasadas` |
| **Perfil global** | bloque `explainability`: `data_source` · `source_version` · `basis` · `year` · `rules_applied` · `ai_used=false`; `confidence` global |

**Conclusión**: para cada KPI, ratio, comparable o valoración se conocen datos utilizados, fuente, fecha, reglas aplicadas y nivel de confianza. **Sin caja negra.**

---

## 4. Capacidades del Financial Intelligence Engine

> Todas invocables por **cualquier consumidor** vía API, con independencia de arroba.com.

### API pública (auth `X-API-Key`)
| Endpoint | Capacidad |
|---|---|
| `POST /api/v1/financial-intelligence/analyze` | **Perfil financiero completo**: estados, KPIs, ratios, evolución, calidad, comparables, valoración, assessment y explicabilidad |
| `POST /api/v1/financial-intelligence/valuation` | **Valoración** aislada (superficie de paridad con el Value Engine legacy) |
| `GET  /api/v1/financial-intelligence/ratios/catalog` | **Catálogo de la librería de ratios** reutilizable: fórmula + explicación + categoría |

### Capacidades funcionales
1. **Estados financieros normalizados** — cuenta de resultados + balance del último ejercicio (cashflow N/A en individual).
2. **KPIs canónicos** — revenue, EBITDA, EBIT, net income, crecimientos YoY, CAGR, márgenes (EBITDA/neto), ROE, ROA, solvencia, liquidez, deuda/fondos propios, productividad por empleado, intensidad de capital.
3. **Librería de ratios reutilizable** — 13 ratios (rentabilidad, liquidez, solvencia, eficiencia), cada uno con fórmula + explicación + categoría + fuente.
4. **Evolución histórica** — tendencia (growth/stable/deterioration), crecimientos, detección de anomalías (>50%), serie de puntos por año.
5. **Financial Quality Score (0-100)** — reglas deterministas auditables (disponibilidad, histórico, auditoría, EBITDA/neto positivos, consistencia de balance, estabilidad de ingresos).
6. **Comparables financieros** — peers por sector (sección CNAE) + banda de tamaño (0.3x–3x revenue) + geografía; percentil de margen del sujeto; **sin embeddings**.
7. **Valoración honesta** — cascada EV/EBITDA → EV/revenue → book value → insufficient_data, con múltiplos marcados como **referencia inferida** (pendiente conectar múltiplos reales de mercado/M&A).
8. **Assessment explicable** — fortalezas / debilidades / riesgos derivados por reglas.
9. **Explicabilidad/linaje** — fuente, versión de fuente, basis, año y reglas aplicadas en cada respuesta.

---

## 5. Migración legacy
`skills_value` (Value Engine legacy) queda **absorbido** por este motor. La superficie `/valuation` ofrece paridad. Próximo paso de migración: redirigir consumidores públicos de `skills_value` a `/api/v1/financial-intelligence/valuation` sobre `master_companies` y retirar la dependencia de datos sintéticos.

## 6. Tests
- `tests/smoke/test_financial_intelligence.py` — 7 tests (perfil completo, KPIs/ratios coherentes, quality rules-based, valoración trazable, comparables sin embeddings, API requiere service key, analyze+valuation+catalog).
- Suite completa: **160/160 verdes**.
