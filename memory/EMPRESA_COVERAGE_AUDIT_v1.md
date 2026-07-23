# AUDITORÍA DE COBERTURA — Ficha de Empresa (ACC) vs Agency Tool (arroba.v1)
**Certificación de arquitectura y contratos. Sin código, sin cambios de OpenAPI/endpoints/DTO/ACC.**
_Versión: `empresa-coverage-audit-v1` · 2026-07-04 · Contrato evaluado: `arroba-integration-contract-v1`_

> Fuentes de verdad auditadas: **ACC** (`componentes empresa.md`, 67 componentes) + **HTML canónico** (`empresa.zip`).
> Contrato público evaluado: los **6 Intelligence Engines** vía `X-API-Key` (`arroba.v1.json`).
> Principio: **Zero Coupling** — todo componente debe alimentarse EXCLUSIVAMENTE por contrato público,
> sin lógica de negocio en el frontend y sin acceso a `/master/*` (JWT, no público).

---

## 0. Hallazgo estructural (leer primero)

El ACC referencia **4 "engines" que NO existen en el contrato público `arroba.v1`**:

| Engine citado en el ACC | ¿Existe como motor público? | Realidad en Agency Tool |
|---|---|---|
| **Market Intelligence Engine** (17+ menciones) | ❌ NO | Existe inteligencia interna (`sector_intelligence`, `geo_intelligence`, `sector_geo_cross`) pero **sin endpoint público** en `arroba.v1`. Signal `/sector` cubre solo señales de sector. |
| **Ownership Intelligence Engine** | ❌ NO | Los datos de propiedad viven en `master_companies.ownership` (**Master Layer, JWT, no público**) y en el Knowledge Graph interno. Ningún motor público expone la estructura de propiedad. |
| **Governance Intelligence Engine** | ❌ NO | El Master solo tiene `officers_count` (recuento). No hay detalle de consejeros/ejecutivos ni endpoint público. |
| **Company Intelligence Engine** | ❌ NO (= Master/Foundation) | Es el Master Layer (`/api/v1/master/*`, **JWT administrativo**), fuera de `arroba.v1`. |

**Consecuencia:** los capítulos de **Ownership (COMP-5xxx)**, **Governance (COMP-6xxx)**, **Market (COMP-7xxx)**,
**Rankings (COMP-8xxx)** y **Sources/Registry/Documents (COMP-12xxx)**, más **Cash Flow (COMP-3005)** y parte de
**Valuation avanzada (4005/4006/4007)**, **no pueden alimentarse hoy exclusivamente con contratos públicos**.

> ⚠️ **Nota Zero Coupling:** el contrato público **nunca** obliga al frontend a implementar lógica de negocio
> (principio *Intelligence First* respetado). El problema NO es lógica en frontend, sino **ausencia de endpoint
> público** para ciertos datos/inteligencia. La resolución correcta es **server-side** (CREAR/AMPLIAR ENDPOINT),
> jamás calcular en arroba. Calcular cualquiera de esos componentes en el frontend sería un **ERROR ARQUITECTÓNICO**.

---

## 1. 🛑 REGLA CRÍTICA — Duplicidades detectadas y Source of Truth

Se detienen y se resuelven ANTES de continuar (según regla crítica del encargo):

| # | Información equivalente | Endpoints que la ofrecen | **Única Source of Truth** |
|---|---|---|---|
| D1 | **KPIs financieros** (revenue, EBITDA, márgenes, empleados) | `financial/analyze.kpis` **y** Executive Snapshot (1005) **y** Executive Metrics (2001) | **`financial-intelligence/analyze.kpis`** — los componentes de cabecera/executive deben consumir este mismo DTO, no recalcular ni usar otra fuente. |
| D2 | **Valoración** | `financial/analyze.valuation` **y** `financial/valuation` | **`financial-intelligence/valuation`** (endpoint dedicado). `analyze.valuation` es un extracto de conveniencia; para el bloque de Valoración usar el dedicado. |
| D3 | **Comparables** | `financial/analyze.comparables` **y** `recommendation/comparables` | **`recommendation-intelligence/comparables`** (motor de recomendación es el propietario del fit/comparabilidad). |
| D4 | **Oportunidades** | `signal/opportunities` **y** `recommendation/opportunities` | **Por tipo:** oportunidades **dirigidas a una empresa/rol** → `recommendation/opportunities`; **señales de oportunidad de sector/territorio** → `signal/opportunities`. No mezclar en un mismo componente. |
| D5 | **Executive Overview (COMP-2006)** | Marcado como *Duplicidad funcional / Eliminado* en el propio ACC | **REDUNDANT** — no consumir. |
| D6 | **COMP-9003 con doble título** ("Comparable Companies" / "Competitive Positioning", mismo código) | Duplicidad **documental** dentro del ACC | Requiere desambiguación del ACC (no lo modifico); a efectos de datos se tratan como Comparables (Recommendation) + Positioning (derivado). |

---

## 2. Matriz de cobertura completa (COMPONENTE → ENGINE → ENDPOINT → DTO → ESTADO → ACCIÓN)

> Leyenda estado: **READY** / **PARTIAL** / **MISSING** / **REDUNDANT**. Endpoints prefijo `/api/v1`.
> "arroba-owned" = estado/UX propiedad de arroba (no es dato de Agency Tool).

### Header (COMP-1xxx)
| COMP | Engine | Endpoint | DTO | Estado | Campos faltantes | Acción |
|---|---|---|---|---|---|---|
| 1001 Company Identity | Company/Master | (público) `financial|semantic/analyze.identity` · (canónico) `/master/{id}` JWT | `identity{legal_name, cnae, provincia}` (público) | PARTIAL | `commercial_name, aliases, country, web/domain, capital_social, location completa` solo en Master(JWT) | CREAR ENDPOINT (identity pública) |
| 1002 Company Context | Company/Master | `semantic/profile` + `financial/analyze` | `semantic_profile`, `classification` | PARTIAL | contexto societario/registral no público | AMPLIAR ENDPOINT |
| 1003 Company Public Status | Company/Master | — | — | MISSING | estado de publicación/verificación vive en Master(JWT) | CREAR ENDPOINT |
| 1004 Company Quick Actions | — (arroba-owned) | n/a | n/a | REDUNDANT | UX/acciones de usuario | REUTILIZAR |
| 1005 Executive Snapshot | Financial (+Signal) | `financial/analyze` (+ `signal/analyze`) | `kpis`, `financial_quality`, `signals[]` | READY | — (SoT D1) | REUTILIZAR |
| 1010 User Relationship | — (arroba-owned) | n/a | n/a | REDUNDANT | estado de usuario propio de arroba | REUTILIZAR |

### Executive / Copilot (COMP-2xxx)
| COMP | Engine | Endpoint | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 2001 Executive Metrics | Financial | `financial/analyze` | `kpis` | READY | — (SoT D1) | REUTILIZAR |
| 2002 Arroba Copilot | Composición (Semantic+Reco+Strategy+…) | `semantic/*`, `recommendation/*`, `strategy/*`, `transaction/next-action` | agregación multi-motor | READY | — (orquestación en backend arroba) | REUTILIZAR |
| 2003 Next Step Panel | Recommendation / Transaction | `recommendation/opportunities` · `transaction/next-action` | `recommended_action, why, confidence` | READY | — | REUTILIZAR |
| 2006 Executive Overview | — | — | — | REDUNDANT | duplicidad eliminada (D5) | ELIMINAR ENDPOINT |

### Finanzas (COMP-3xxx)
| COMP | Engine | Endpoint | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 3001 Financial Workspace | Financial | `financial/analyze` | DTO completo analyze | READY | — | REUTILIZAR |
| 3002 Financial Intelligence | Financial | `financial/analyze` | `kpis, financial_quality, explainability` | READY | — (SoT D1) | REUTILIZAR |
| 3003 Income Statement | Financial | `financial/analyze` | `income_statement` | READY | — | REUTILIZAR |
| 3004 Balance Sheet | Financial | `financial/analyze` | `balance_sheet` | READY | — | REUTILIZAR |
| **3005 Cash Flow** | Financial | `financial/analyze` | — | **MISSING** | **estado de flujos de caja (operativo/inversión/financiación); no está en el DTO** | CREAR ENDPOINT / AMPLIAR ENDPOINT |
| 3006 Financial Ratios | Financial | `financial/analyze` (+ `ratios/catalog`) | `ratios` | READY | — | REUTILIZAR |
| 3007 Period Selector | Financial | `financial/analyze` | `kpis.evolution` / `financials.history` | PARTIAL | histórico multi-periodo depende de cobertura de fuente | AMPLIAR ENDPOINT |

### Valoración (COMP-4xxx + 0008)
| COMP | Engine | Endpoint | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 4001 Valuation Section | Financial | `financial/valuation` | `valuation` | READY | — (SoT D2) | REUTILIZAR |
| 0008 Connected Intelligence | Composición | multi-motor | agregación | READY | — | REUTILIZAR |
| 4002 Valuation Intelligence | Financial (+Strategy) | `financial/valuation` (+ `strategy/thesis`) | `valuation`, narrativa | PARTIAL | narrativa/tesis viene de Strategy; encaje a validar | REUTILIZAR |
| 4003 Valuation Summary | Financial | `financial/valuation` | `valuation.{ev, equity, range}` | READY | — | REUTILIZAR |
| 4004 Valuation Methods | Financial | `financial/valuation` | `valuation.{method, multiple, multiple_basis}` | READY | — | REUTILIZAR |
| **4005 Enterprise Value Bridge** | Financial | `financial/valuation` | parcial | **PARTIAL** | **descomposición puente EV→Equity (deuda, caja, ajustes) no desglosada en el DTO** | AMPLIAR ENDPOINT |
| **4006 Valuation Scenarios** | Financial / Strategy | `financial/valuation` · `strategy/scenarios` | no específico de valoración | **PARTIAL** | **escenarios de valoración (base/bull/bear con drivers) no en el DTO de valuation** | AMPLIAR ENDPOINT |
| **4007 Sensitivity Analysis** | Financial | `financial/valuation` | — | **MISSING** | **matriz de sensibilidad (múltiplo × driver) no existe en el contrato** | CREAR ENDPOINT |

### Propiedad (COMP-5xxx) — ❌ sin engine público
| COMP | Engine (ACC) | Endpoint público | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 5001 Ownership Section | Ownership IE (no público) | — | — | MISSING | estructura de propiedad no expuesta públicamente | CREAR ENDPOINT |
| 5002 Ownership Intelligence | Ownership IE | — | — | MISSING | idem | CREAR ENDPOINT |
| 5003 Ownership Overview | Ownership IE | — | — | MISSING | `ownership{shareholders,parents,ultimate_parent}` solo en Master(JWT) | CREAR ENDPOINT |
| 5004 Shareholders | Ownership IE | — | — | MISSING | lista de accionistas y % (Master JWT) | CREAR ENDPOINT |
| 5005 Corporate Group | Ownership IE / KG | — | — | MISSING | `ownership.group_id` / grafo (interno) | CREAR ENDPOINT |
| 5006 Ownership Network | Knowledge Graph | — | — | MISSING | `master_relationships` no público | CREAR ENDPOINT |

### Gobierno (COMP-6xxx) — ❌ sin engine público
| COMP | Engine (ACC) | Endpoint público | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 6001 Governance Section | Governance IE (no público) | — | — | MISSING | detalle de gobierno no público | CREAR ENDPOINT |
| 6002 Governance Intelligence | Governance IE | — | — | MISSING | idem | CREAR ENDPOINT |
| 6003 Governance Overview | Governance IE | — | `officers_count` (solo recuento, Master JWT) | MISSING | detalle inexistente | CREAR ENDPOINT |
| 6004 Board Members | Governance IE | — | — | MISSING | consejeros (no ingerido/expuesto) | CREAR ENDPOINT |
| 6005 Executives | Governance IE | — | — | MISSING | ejecutivos | CREAR ENDPOINT |
| 6006 Legal Representatives | Governance IE | — | — | MISSING | apoderados | CREAR ENDPOINT |
| 6007 Governance Timeline | Governance IE | — | — | MISSING | histórico de cargos | CREAR ENDPOINT |

### Mercado (COMP-7xxx) — ❌ engine no público
| COMP | Engine (ACC) | Endpoint público | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 7001 Market Section | Market IE (no público) | (parcial) `signal/sector` | — | MISSING | sin engine de mercado público | CREAR ENDPOINT |
| 7002 Market Intelligence | Market IE | — | — | MISSING | idem | CREAR ENDPOINT |
| 7003 Market Overview | Market IE | — | — | MISSING | indicadores de mercado (interno `sector_intelligence`) | CREAR ENDPOINT |
| 7004 Market Size & Structure | Market IE | — | — | MISSING | tamaño/estructura de mercado | CREAR ENDPOINT |
| 7005 Market Trends | Market IE | (parcial) `signal/sector` | `signals[]` sector | PARTIAL | tendencias estructuradas | AMPLIAR ENDPOINT |
| 7006 Market Positioning | Market IE | — | — | MISSING | posicionamiento calculado | CREAR ENDPOINT |
| 7007 Market Risks & Opportunities | Market IE / Signal | `signal/sector` · `signal/opportunities` | `signals[]` | PARTIAL | riesgos/oportunidades de mercado estructurados | AMPLIAR ENDPOINT |

### Rankings (COMP-8xxx)
| COMP | Engine | Endpoint público | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 8001 Rankings Section | — | — | — | MISSING | no hay endpoint de rankings de empresas | CREAR ENDPOINT |
| 8002 Ranking Cards | — | — | — | MISSING | métricas de ranking/percentil por dimensión | CREAR ENDPOINT |

### Comparativa (COMP-9xxx)
| COMP | Engine | Endpoint | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 9001 Comparison Universe | Recommendation | `recommendation/comparables` | `recommendations[]` | READY | — (SoT D3) | REUTILIZAR |
| 9002 Executive Comparison | Recommendation (+Financial) | `recommendation/comparables` + `financial/analyze` | fit + kpis | PARTIAL | tabla comparativa consolidada (composición) | REUTILIZAR |
| 9003 Comparable Companies | Recommendation | `recommendation/comparables` | `recommendations[]` | READY | — | REUTILIZAR |
| 9003 Competitive Positioning | Recommendation/Semantic | `recommendation/matching` · `semantic/similar` | `fit_score, dimensions` | PARTIAL | posicionamiento competitivo consolidado | AMPLIAR ENDPOINT |
| 9004 Opportunity Map | Recommendation | `recommendation/opportunities` | `items[]` | PARTIAL | mapa (composición cliente sobre datos servidos) | REUTILIZAR |
| 9005 Competitive Gaps | Recommendation/Financial | `recommendation/explain` + `financial/analyze` | `factors[]` | PARTIAL | gaps estructurados por dimensión | AMPLIAR ENDPOINT |
| 9006 Competitive Difference Matrix | Recommendation | `recommendation/matching` | `dimensions` | PARTIAL | matriz N×N no servida directamente | AMPLIAR ENDPOINT |
| 9007 Financial Comparison | Financial | `financial/analyze` (por peer) | `kpis`, `ratios` | READY | — (composición de peers, sin lógica de negocio) | REUTILIZAR |

### Señales (COMP-10xxx)
| COMP | Engine | Endpoint | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 10001 Signals Section | Signal | `signal/analyze` | `signals[], score, counts_by_category` | READY | — | REUTILIZAR |
| 10002 Signals Timeline | Signal | `signal/history` | histórico de señales | READY | — | REUTILIZAR |

### Oportunidades (COMP-11xxx)
| COMP | Engine | Endpoint | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 11001 Opportunities Section | Recommendation (+Signal) | `recommendation/opportunities` (+ `signal/opportunities`) | `items[]` | READY | — (SoT D4) | REUTILIZAR |

### Fuentes / Registro / Documentos (COMP-12xxx) — ❌ internas, no públicas
| COMP | Engine | Endpoint público | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 12001 Sources Section | — | — | — | MISSING | trazabilidad de fuentes no expuesta | CREAR ENDPOINT |
| 12002 Corporate Registry Events | — (BORME interno) | — | — | MISSING | `borme_events` no en `arroba.v1` | CREAR ENDPOINT |
| 12003 Annual Accounts Registry | — | — | — | MISSING | cuentas anuales registrales no públicas | CREAR ENDPOINT |
| 12004 Registry Information | — | — | — | MISSING | datos registrales | CREAR ENDPOINT |
| 12005 Documents Section | — | — | — | MISSING | documentos (fuera del Transaction OS) no públicos | CREAR ENDPOINT |

### Recomendación / Acciones (COMP-13xxx)
| COMP | Engine | Endpoint | DTO | Estado | Faltantes | Acción |
|---|---|---|---|---|---|---|
| 13001 Next Best Actions | Recommendation / Transaction | `recommendation/opportunities` · `transaction/next-action` | `recommended_action, confidence` | READY | — | REUTILIZAR |
| 13002 Recommendation Explainability | Recommendation | `recommendation/explain` | `factors[], narrative` | READY | — | REUTILIZAR |
| 13003 Recommendation Prioritization | Recommendation | `recommendation/opportunities` | `items[].fit_score` | READY | — | REUTILIZAR |

---

## 3. Heat Map (estado general — 66 componentes activos; 2006 eliminado)

| Estado | Nº | Componentes |
|---|---:|---|
| **READY** | 22 | 1005, 2001, 2002, 2003, 0008, 3001, 3002, 3003, 3004, 3006, 4001, 4003, 4004, 9001, 9003(Comparable), 9007, 10001, 10002, 11001, 13001, 13002, 13003 |
| **PARTIAL** | 14 | 1001, 1002, 3007, 4002, 4005, 4006, 7005, 7007, 9002, 9003(Positioning), 9004, 9005, 9006 |
| **MISSING** | 27 | 1003, 3005, 4007, 5001, 5002, 5003, 5004, 5005, 5006, 6001, 6002, 6003, 6004, 6005, 6006, 6007, 7001, 7002, 7003, 7004, 7006, 8001, 8002, 12001, 12002, 12003, 12004, 12005 |
| **REDUNDANT** | 3 | 1004 (arroba-owned), 1010 (arroba-owned), 2006 (eliminado) |

> Nota: 1004 y 1010 son propiedad de arroba (UX/estado de usuario), sin dato de Agency Tool; se clasifican
> REDUNDANT respecto al contrato de datos (no requieren endpoint).

---

## 4. Auditoría arquitectónica (respuestas obligatorias)

**1. ¿Componentes no implementables solo con contratos públicos?**
**SÍ.** Bloques completos: **Ownership (5xxx), Governance (6xxx), Market (7xxx), Rankings (8xxx),
Sources/Registry/Documents (12xxx)** + **Cash Flow (3005)**, **Sensitivity (4007)** y parcialmente
**identity completa (1001/1002/1003)** y **valoración avanzada (4005/4006)**. Todos requieren
**CREAR/AMPLIAR ENDPOINT** en Agency Tool (server-side).

**2. ¿Algún componente obligaría al frontend a implementar lógica de negocio? (ERROR ARQUITECTÓNICO)**
**NO por diseño del contrato** — el contrato público jamás expone datos crudos que fuercen cálculo en
frontend (Intelligence First se respeta). **PERO existe un RIESGO** si arroba, ante los gaps, intentara
derivar en cliente: Cash Flow, EV Bridge, Sensibilidad, Market positioning, Ownership network, matrices
competitivas. **Regla:** esos componentes deben servirse **calculados por un engine**; calcularlos en el
frontend sería un ERROR ARQUITECTÓNICO. Hoy no hay ninguno que *obligue* a ello (no hay datos crudos
públicos que lo tienten), por lo que **no se marca FAIL** por este criterio.

**3. ¿Algún Intelligence Engine sin representación en el ACC?**
**SÍ.** El **Transaction Engine** apenas aparece en la Ficha de Empresa (solo indirectamente vía
Next Step/Copilot); pertenece a otra superficie (Deal Room). El **Semantic Engine** está infrarrepresentado
como componente explícito (se usa transversalmente en Copilot/Comparativa/Search). No es un problema, pero
conviene reflejar que la Ficha de Empresa se apoya sobre todo en Financial/Signal/Recommendation.

**4. ¿Algún endpoint público sin consumidor (en la Ficha)?**
En el ámbito de la Ficha de Empresa: **`transaction-intelligence/*`** (salvo `next-action`) no tiene
consumidor aquí (su consumidor es el Deal Room). Globalmente sí tienen consumidor. No eliminar.

**5. ¿DTOs demasiado grandes que deberían dividirse?**
**SÍ.** `financial-intelligence/analyze` devuelve un DTO monolítico (kpis + income_statement +
balance_sheet + ratios + financial_quality + comparables + valuation + explainability). Para una Ficha con
pestañas y Period Selector, conviene poder consumir por partes (o selección de campos). **Recomendación
(no en esta fase):** valorar segmentación en `v2` sin romper `v1`.

**6. ¿Varios endpoints con la misma información? → Source of Truth**
**SÍ** (ver §1): D1 KPIs → **`financial/analyze.kpis`**; D2 Valoración → **`financial/valuation`**;
D3 Comparables → **`recommendation/comparables`**; D4 Oportunidades → por tipo (Recommendation vs Signal).

---

## 5. Validación final

### 🟡 PASS WITH GAPS

- **NO es FAIL:** ningún componente del ACC obliga al frontend de arroba a implementar lógica de negocio;
  el contrato público respeta *Intelligence First* y *Zero Coupling*.
- **NO es PASS:** existe un conjunto sustancial de componentes **MISSING/PARTIAL** (Ownership, Governance,
  Market, Rankings, Sources/Registry/Documents, Cash Flow, Sensitivity, identity completa) que **hoy no
  pueden construirse exclusivamente con contratos públicos**.
- **Cobertura actual:** **22 READY**, **14 PARTIAL**, **27 MISSING**, **3 REDUNDANT** (66 activos).

**Conclusión:** la Ficha de Empresa **NO es 100% alimentable** por `arroba.v1` en su estado actual. Las áreas
financiera nuclear, señales, comparables, oportunidades y recomendación están **listas**. Las áreas de
**propiedad, gobierno, mercado, rankings y fuentes registrales requieren nuevos motores/endpoints públicos**
en Agency Tool (server-side), que deberían planificarse como **capacidades del contrato `arroba.v2`** — sin
romper `v1` y sin que arroba implemente lógica de negocio.

> Restricciones respetadas: no se escribió código, no se modificó OpenAPI/endpoints/DTO/ACC, no se propusieron
> cambios visuales ni se analizó el frontend. Esta auditoría es exclusivamente de arquitectura y contratos.
