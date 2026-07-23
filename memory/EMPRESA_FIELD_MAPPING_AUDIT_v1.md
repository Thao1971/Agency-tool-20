# AUDITORÍA DE SEGUNDO NIVEL — Field Mapping (Ficha de Empresa · ACC vs arroba.v1)
**Trazabilidad a nivel de campo: COMPONENTE → ENGINE → ENDPOINT → DTO → CAMPO → ORIGEN → ESTADO.**
_Versión: `empresa-field-mapping-v1` · 2026-07-04 · Sin código, sin cambios de OpenAPI/endpoints/DTO/ACC._

> Continuación de `EMPRESA_COVERAGE_AUDIT_v1.md`. Fuentes: ACC (`componentes empresa.md`) + `arroba.v1.json`
> + código real de los motores. Estados de campo: **READY** (existe directo) · **DERIVED** (calculado en
> backend) · **MISSING** (no existe) · **UNTRACEABLE** (origen indemostrable).

---

## 0. 🛑 DOS PARADAS CRÍTICAS (resolver antes de nada)

### PARADA A — Los DTO de respuesta NO están tipados en el contrato
Verificado en `arroba.v1.json`: **todos los endpoints de motores devuelven `responses.200.schema = {}`**
(dict libre). El OpenAPI solo tipa los **request models** (`AnalyzeRequest`, `SearchRequest`, …), no las
respuestas. **Consecuencia:** los campos de respuesta **existen en runtime** y su **origen es trazable por
implementación** (Iberinform / DERIVED / motores), pero **no son certificables ni autogenerables desde el
contrato**. Esto es un **gap de calidad de contrato** (no un error de frontend): impide "trazabilidad
completa a nivel de contrato". **Recomendación (fuera de esta fase):** tipar los DTO de respuesta en `v2`.

### PARADA B — Campos duplicados en distintos DTO → Source of Truth
| # | Campo(s) duplicado(s) | Aparece en | **Única Source of Truth** |
|---|---|---|---|
| F1 | `revenue, ebitda, ebitda_margin, net_income, employees_total` (KPIs) | `financial/analyze.kpis` y (extracto) Executive Snapshot/Metrics | **`financial/analyze.kpis`** |
| F2 | `valuation{enterprise_value, equity_value, range, multiple}` | `financial/analyze.valuation` **y** `financial/valuation` | **`financial/valuation`** |
| F3 | `comparables/peers[]` (`master_id, name, ebitda_margin, multiple`) | `financial/analyze.comparables` **y** `recommendation/comparables` | **`recommendation/comparables`** |
| F4 | `identity{legal_name, cnae_code, cnae_section, provincia}` | `financial/analyze.identity` **y** `semantic/profile.identity` | **`financial/analyze.identity`** (o Master público futuro) |
| F5 | `cif_normalized, master_id` | en TODOS los DTO de motor | **`master_companies`** (clave canónica; se propaga idéntica) |

> Los componentes de cabecera/executive deben **reutilizar** el DTO SoT, nunca una copia desde otro endpoint.

---

## 1. Leyenda de ORIGEN de campo

| Origen | Significado |
|---|---|
| **Iberinform** | Dato bruto ingerido de la fuente externa (cifras financieras, identidad básica) |
| **DERIVED · Financial** | Calculado por el Financial Engine (ratios, márgenes, valoración, calidad, tendencias) |
| **DERIVED · Signal** | Calculado por el Signal Engine (señales, severidad, score) |
| **DERIVED · Semantic** | Calculado por el Semantic Engine (perfil, embeddings, similitud) — IA/determinista |
| **DERIVED · Recommendation** | Calculado por el Recommendation Engine (fit, comparables, factores) |
| **DERIVED · Strategy** | Calculado por el Strategy Engine (dimensiones, escenarios, tesis) |
| **Master/KG (JWT)** | Vive en `master_companies`/`master_relationships` — **no público** (Master Layer) |
| **MISSING** | Sin origen ni endpoint público |

---

## 2. Field mapping por componente (detallado en READY/PARTIAL; MISSING agregado)

### Financiero — COMP-1005, 2001, 3001–3004, 3006, 3007
**Engine:** Financial · **Endpoint:** `POST /api/v1/financial-intelligence/analyze` · **DTO:** respuesta `analyze` (no tipada)

| Campo | Origen | Estado |
|---|---|---|
| `master_id`, `cif_normalized` | Master (canónico) | READY |
| `identity.legal_name` | Iberinform | READY |
| `cnae_code`, `cnae_section`, `provincia` | Iberinform | READY |
| `year`, `basis`, `audited`, `has_financials`, `data_source`, `source_version` | Iberinform | READY |
| `kpis.revenue`, `kpis.ebitda`, `kpis.net_income`, `kpis.employees_total` | Iberinform | READY |
| `kpis.ebitda_margin`, `ebit`, `ebit_margin`, `net_margin`, `gross_margin` | DERIVED · Financial | DERIVED |
| `kpis.revenue_per_employee`, `revenue_growth_yoy`, `revenue_cagr`, `ebitda_growth_yoy` | DERIVED · Financial | DERIVED |
| `kpis.evolution.{revenue,ebitda,net_income}[]` | DERIVED · Financial (sobre history) | DERIVED (PARTIAL si falta histórico) |
| `income_statement.{revenue, supplies, personnel_costs, depreciation, operating_income, financial_expenses, ebit, ebitda, net_income}` | Iberinform (+ ebit/ebitda DERIVED) | READY/DERIVED |
| `balance_sheet.{current_assets, non_current_assets, total_assets, cash, current_liabilities, non_current_liabilities, st_debt, lt_debt, financial_debt, equity, total_liabilities}` | Iberinform | READY |
| `ratios.{current_ratio, debt_ratio, debt_to_equity, interest_coverage, roe, roa, ebitda_margin, net_margin, capital_intensity}` | DERIVED · Financial | DERIVED |
| `financial_quality.{score, assessment, strengths[], weaknesses[], risks[]}` | DERIVED · Financial | DERIVED |
| `solvency`, `trend`, `anomaly`, `deterioration`, `size_band` | DERIVED · Financial | DERIVED |
| `explainability.{rules_applied[], formula, lineage, hypotheses[]}` | DERIVED · Financial | DERIVED |
| `income_statement.cashflow` (COMP-3005) | — (placeholder `null`) | **MISSING** |
| `engine_version`, `generated_at` | Sistema | READY |

**Validación:** 3001/3002/3003/3004/3006/2001/1005 → **SÍ**. 3007 (Period Selector) → **PARCIAL** (histórico). 3005 (Cash Flow) → **NO**.

### Valoración — COMP-4001–4004, 0008
**Engine:** Financial · **Endpoint:** `POST /api/v1/financial-intelligence/valuation` (SoT F2)

| Campo | Origen | Estado |
|---|---|---|
| `valuation.method`, `multiple`, `multiple_basis` | DERIVED · Financial | DERIVED |
| `valuation.enterprise_value`, `equity_value` | DERIVED · Financial | DERIVED |
| `valuation.range.{low, high}` | DERIVED · Financial | DERIVED |
| `valuation.subject_ebitda_margin_percentile` | DERIVED · Financial | DERIVED |
| `comparables.peers[].{master_id, name, cnae_section, same_province, ebitda_margin, multiple}` | DERIVED · Recommendation/Financial | DERIVED |
| `confidence`, `explanation`, `criteria` | DERIVED · Financial | DERIVED |
| EV Bridge: `deuda_neta, caja, ajustes, puente EV→Equity desglosado` (COMP-4005) | — | **MISSING** |
| Scenarios: `base/bull/bear con drivers` (COMP-4006) | — (Strategy `scenarios` no es de valoración) | **MISSING/PARTIAL** |
| Sensitivity: `matriz múltiplo × driver` (COMP-4007) | — | **MISSING** |

**Validación:** 4001/4002/4003/4004/0008 → **SÍ/PARCIAL**. 4005 → **NO**. 4006 → **PARCIAL**. 4007 → **NO**.

### Señales — COMP-10001, 10002
**Engine:** Signal · **Endpoints:** `POST /signal-intelligence/analyze`, `/history`

| Campo | Origen | Estado |
|---|---|---|
| `signals[].signal_id`, `signal_type`, `polarity`, `severity`, `score` | DERIVED · Signal | DERIVED |
| `signals[].window`, `dimension`, `rule`, `rules_applied[]`, `actions[]`, `evidence`, `observed_at` | DERIVED · Signal | DERIVED |
| `signal_score`, `counts_by_category`/`summary` | DERIVED · Signal | DERIVED |
| histórico (`/history`) `first_detected_at, last_seen_at, occurrences, lifecycle` | DERIVED · Signal (persistido) | DERIVED |

**Validación:** 10001/10002 → **SÍ**.

### Comparativa — COMP-9001, 9003(Comparable), 9007 (READY) · 9002, 9003(Positioning), 9004, 9005, 9006 (PARTIAL)
**Engine:** Recommendation (+Financial/Semantic) · **Endpoints:** `/recommendation/comparables|matching|explain`, `/financial/analyze`

| Campo | Origen | Estado |
|---|---|---|
| `recommendations[].master_id, name, fit_score` | DERIVED · Recommendation | DERIVED |
| `recommendations[].dimensions.{sector, size, geography, financial, semantic}` | DERIVED · Recommendation | DERIVED |
| `recommendations[].role, rationale, recommendation_id` | DERIVED · Recommendation | DERIVED |
| `explain.factors[].{name, weight, contribution}`, `narrative` | DERIVED · Recommendation | DERIVED |
| `matching.fit_score, dimensions` (posicionamiento) | DERIVED · Recommendation | DERIVED |
| KPIs de peers (Financial Comparison 9007) | Iberinform + DERIVED · Financial | READY/DERIVED |
| Matriz N×N consolidada / opportunity map / gaps estructurados | — (composición) | PARTIAL |

**Validación:** 9001/9003(Comp)/9007 → **SÍ**. 9002/9003(Pos)/9004/9005/9006 → **PARCIAL** (datos servidos; consolidación es composición SIN lógica de negocio).

### Oportunidades / Acciones / Copilot — COMP-2002, 2003, 11001, 13001, 13002, 13003
**Engines:** Recommendation, Signal, Strategy, Transaction(next-action), Semantic

| Campo | Origen | Estado |
|---|---|---|
| `opportunities.items[].{master_id, fit_score, role, rationale}` | DERIVED · Recommendation | DERIVED |
| `signal/opportunities.items[]` (sector/territorio) | DERIVED · Signal | DERIVED |
| `next-action.{recommended_action, why, confidence, blockers[], alternatives[]}` | DERIVED · Recommendation/Transaction | DERIVED |
| `explain.factors[], narrative` (13002) | DERIVED · Recommendation | DERIVED |
| priorización `items[].fit_score` (13003) | DERIVED · Recommendation | DERIVED |
| Copilot (2002): agregación multi-motor | DERIVED (composición backend arroba) | READY |

**Validación:** 2002/2003/11001/13001/13002/13003 → **SÍ**.

### Header identidad/contexto — COMP-1001, 1002, 1003
| Campo | Origen | Estado |
|---|---|---|
| `legal_name, cnae, provincia` (público vía analyze) | Iberinform | READY |
| `commercial_name, aliases[], country, contact.web, contact.domain, capital_social, location completa` | Master/KG (JWT) | **MISSING (público)** |
| `public_status / verificación` (1003) | Master (JWT) | **MISSING (público)** |

**Validación:** 1001/1002 → **PARCIAL**. 1003 → **NO**.

### arroba-owned — COMP-1004, 1010
| Campo | Origen | Estado |
|---|---|---|
| quick actions / user relationship | arroba (estado propio) | READY (no requiere dato de Agency Tool) |

### ❌ Bloques sin origen público — todos los campos MISSING
| Componentes | Campos requeridos (ejemplos) | Origen | Estado |
|---|---|---|---|
| Ownership 5001–5006 | `shareholders[].{name,cif,pct}, parents[], ultimate_parent, group_id, network edges` | Master/KG (JWT) | **MISSING (público)** |
| Governance 6001–6007 | `board_members[], executives[], legal_representatives[], timeline[]` (Master solo `officers_count`) | MISSING | **MISSING** |
| Market 7001–7004, 7006 | `market_size, structure, share, positioning, hhi` | MISSING (Market IE no público) | **MISSING** |
| Market 7005, 7007 | tendencias/riesgos | DERIVED · Signal (parcial `/sector`) | PARTIAL |
| Rankings 8001, 8002 | `rank, percentile por dimensión` | MISSING | **MISSING** |
| Sources/Registry/Docs 12001–12005 | `borme_events[], annual_accounts[], registry_info, documents[], source_trace` | MISSING (interno/Console) | **MISSING** |
| 2006 Executive Overview | — | duplicado eliminado | REDUNDANT |

**Validación de estos bloques:** **NO** (salvo 7005/7007 → PARCIAL).

---

## 3. Matriz final (COMP → ENGINE → ENDPOINT → DTO → CAMPO(s) → ORIGEN → ESTADO)

| COMP | Engine | Endpoint | DTO | Campos (resumen) | Origen dominante | Estado |
|---|---|---|---|---|---|---|
| 1001 | Financial/Master | `/financial/analyze` (+/master JWT) | analyze.identity | legal_name; +commercial_name… | Iberinform / Master(JWT) | PARCIAL |
| 1002 | Semantic/Financial | `/semantic/profile`,`/financial/analyze` | profile,classification | contexto | Iberinform/DERIVED | PARCIAL |
| 1003 | Master | — | — | public_status | Master(JWT) | NO |
| 1004 | arroba | — | — | quick actions | arroba | READY |
| 1005 | Financial(+Signal) | `/financial/analyze`(+`/signal/analyze`) | kpis,quality,signals | KPIs+quality | Iberinform/DERIVED | SÍ |
| 1010 | arroba | — | — | user rel. | arroba | READY |
| 2001 | Financial | `/financial/analyze` | kpis | revenue,ebitda,… | Iberinform/DERIVED | SÍ |
| 2002 | Multi | `/semantic,/recommendation,/strategy,/transaction` | agregación | multi | DERIVED | SÍ |
| 2003 | Reco/Transaction | `/recommendation/opportunities`,`/transaction/next-action` | next-action | action,why,conf | DERIVED | SÍ |
| 2006 | — | — | — | — | — | REDUNDANT |
| 3001 | Financial | `/financial/analyze` | analyze | todo analyze | Iberinform/DERIVED | SÍ |
| 3002 | Financial | `/financial/analyze` | kpis,quality,explain | KPIs+quality | Iberinform/DERIVED | SÍ |
| 3003 | Financial | `/financial/analyze` | income_statement | P&L líneas | Iberinform/DERIVED | SÍ |
| 3004 | Financial | `/financial/analyze` | balance_sheet | balance líneas | Iberinform | SÍ |
| 3005 | Financial | `/financial/analyze` | (cashflow=null) | flujos de caja | MISSING | NO |
| 3006 | Financial | `/financial/analyze`(+`ratios/catalog`) | ratios | ratios | DERIVED | SÍ |
| 3007 | Financial | `/financial/analyze` | kpis.evolution | histórico | DERIVED | PARCIAL |
| 4001–4004,0008 | Financial(+Strategy) | `/financial/valuation` | valuation | EV,equity,range,method | DERIVED | SÍ/PARCIAL |
| 4005 | Financial | `/financial/valuation` | valuation(parcial) | EV bridge | MISSING | NO |
| 4006 | Financial/Strategy | `/financial/valuation`,`/strategy/scenarios` | — | escenarios valoración | MISSING/PARTIAL | PARCIAL |
| 4007 | Financial | `/financial/valuation` | — | sensibilidad | MISSING | NO |
| 5001–5006 | Ownership IE (NO público) | — | — | ownership/network | Master/KG(JWT) | NO |
| 6001–6007 | Governance IE (NO público) | — | — | consejeros/ejecutivos | MISSING | NO |
| 7001–7004,7006 | Market IE (NO público) | — | — | tamaño/estructura/posición | MISSING | NO |
| 7005,7007 | Signal | `/signal/sector`,`/signal/opportunities` | signals[] | tendencias/riesgos | DERIVED·Signal | PARCIAL |
| 8001,8002 | — | — | — | rankings/percentil | MISSING | NO |
| 9001,9003(Comp),9007 | Recommendation/Financial | `/recommendation/comparables`,`/financial/analyze` | recommendations,kpis | fit+kpis | DERIVED | SÍ |
| 9002,9003(Pos),9004,9005,9006 | Recommendation/Semantic | `/recommendation/matching\|explain`,`/semantic/similar` | dimensions,factors | posición/gaps/matriz | DERIVED | PARCIAL |
| 10001,10002 | Signal | `/signal/analyze`,`/signal/history` | signals[] | señales | DERIVED·Signal | SÍ |
| 11001 | Reco(+Signal) | `/recommendation/opportunities`(+`/signal/opportunities`) | items[] | oportunidades | DERIVED | SÍ |
| 12001–12005 | — | — | — | fuentes/registro/docs | MISSING | NO |
| 13001,13002,13003 | Recommendation/Transaction | `/recommendation/explain\|opportunities`,`/transaction/next-action` | factors,items,narrative | acciones/explicabilidad | DERIVED | SÍ |

---

## 4. Auditoría de arquitectura (respuestas obligatorias)

**1. ¿Componentes cuyo DTO no contiene todos los campos necesarios?**
**SÍ.** `financial/analyze` no incluye Cash Flow (3005; `cashflow=null`). `financial/valuation` no incluye
EV bridge (4005), escenarios (4006) ni sensibilidad (4007). Los bloques Ownership/Governance/Market/
Rankings/Sources **no tienen DTO** (sin endpoint público).

**2. ¿Algún campo mostrado en la Ficha cuyo origen NO pueda demostrarse? → UNTRACEABLE**
**A nivel de dato: NO** — todo campo servido tiene origen demostrable (Iberinform o DERIVED por un motor).
**A nivel de CONTRATO: SÍ, condicional** — como los DTO de respuesta **no están tipados** en OpenAPI
(PARADA A), ningún campo de respuesta es certificable *desde el contrato*. Se clasifican **READY/DERIVED por
implementación**, pero marcados **UNTRACEABLE-by-contract** hasta tipar las respuestas en `v2`.

**3. ¿Algún campo obligaría al frontend a calcular información? → ARCHITECTURE ERROR**
**NO.** Todos los campos calculados (márgenes, ratios, valoración, scores, fit, tendencias) son **DERIVED
en el backend** por los motores. El contrato **no** expone datos crudos que fuercen cálculo en arroba
(*Intelligence First* respetado). **0 ARCHITECTURE ERRORS.**

**4. ¿Algún DTO con información nunca usada por ningún componente?**
En la Ficha: `financial/analyze` incluye `comparables/peers` que se solapa con `recommendation/comparables`
(usar SoT F3 → el bloque `analyze.comparables` queda sin consumidor si se sigue el SoT). Además
`transaction-intelligence/*` (salvo `next-action`) no tiene consumidor en la Ficha (pertenece al Deal Room).

**5. ¿Campos duplicados en distintos DTO? → Source of Truth**
**SÍ** (ver PARADA B): F1 KPIs → `financial/analyze.kpis`; F2 valuation → `financial/valuation`;
F3 comparables → `recommendation/comparables`; F4 identity → `financial/analyze.identity`;
F5 `master_id/cif_normalized` → `master_companies`.

**6. ¿Componentes que dependen de >1 endpoint pudiendo resolverse con uno solo?**
- **1005 Executive Snapshot** usa `financial/analyze` + `signal/analyze` (justificado: dominios distintos).
- **9002 Executive Comparison** usa `recommendation/comparables` + `financial/analyze` (podría beneficiarse de
  un DTO comparativo consolidado en `v2`, sin obligar hoy a lógica en frontend).
- **13001 Next Best Actions** usa `recommendation/opportunities` + `transaction/next-action` (dominios distintos).
No hay dependencia múltiple *injustificada* que rompa Zero Coupling.

---

## 5. Heat Map — por CAMPO (no solo componentes)

> Recuento de campos distintos mapeados en la Ficha (aprox., agrupando familias de campos).

| Categoría | Nº de campos | Detalle |
|---|---:|---|
| **READY** (existe directo) | **34** | identity básica, cifras Iberinform (revenue, ebitda, net_income, employees, balance completo, P&L líneas, year/basis/audited), `master_id/cif`, versiones |
| **DERIVED** (backend) | **58** | márgenes, ratios (9), growth/cagr, evolution, financial_quality, solvency/trend/anomaly/size_band, valuation (7), explainability, signals (10+), semantic profile, fit/dimensions/factors, next-action, scenarios/strategy |
| **MISSING** | **41** | cashflow, EV bridge, sensitivity, ownership (shareholders/parents/group/network), governance (board/execs/legal/timeline), market (size/structure/positioning/rankings), sources/registry/docs, identity extendida (commercial_name/aliases/web/domain/country/capital_social/public_status) |
| **UNTRACEABLE** (a nivel dato) | **0** | todo campo servido tiene origen demostrable |
| **UNTRACEABLE-by-contract** | **92** | = READY(34)+DERIVED(58): existen pero **no tipados** en OpenAPI (PARADA A) |
| **ARCHITECTURE ERRORS** | **0** | ningún campo obliga a cálculo en frontend |

---

## 6. Validación final

### 🟡 PASS WITH GAPS

- **NO es FAIL:** **0 campos** obligan al frontend de arroba a implementar lógica de negocio; todo lo
  calculado es **DERIVED en backend** (*Intelligence First* y *Zero Coupling* respetados).
- **NO es PASS:** existen **~41 campos MISSING** (Cash Flow, valoración avanzada, propiedad, gobierno,
  mercado, rankings, fuentes registrales, identidad extendida) sin origen/endpoint público.
- **Gap transversal de trazabilidad (PARADA A):** los **DTO de respuesta no están tipados** en el contrato;
  los ~92 campos servidos son READY/DERIVED por implementación pero **no certificables desde el OpenAPI**.

**Conclusión:** la trazabilidad **origen → campo → componente** es **demostrable a nivel de implementación**
para el núcleo financiero, señales, comparables, oportunidades y recomendación, **sin ningún cálculo en el
frontend**. Para certificar trazabilidad **completa y contractual** de la Ficha se requiere: (a) **tipar los
DTO de respuesta** en `arroba.v2`, y (b) **CREAR/AMPLIAR endpoints** para los ~41 campos MISSING
(Ownership, Governance, Market, Rankings, Sources, Cash Flow, valoración avanzada, identidad extendida),
siempre **server-side**. Duplicidades resueltas con SoT (PARADA B).

> Restricciones respetadas: sin código, sin modificar OpenAPI/endpoints/DTO/ACC/engines, sin análisis de
> frontend ni cambios visuales.
