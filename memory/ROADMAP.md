# Roadmap — Agency Tool como plataforma de Intelligence Engines
_Actualizado: 2026-06-25. Reorganización por MOTORES de inteligencia (no por funcionalidades). No modifica el trabajo ya construido; lo reencuadra._

## 🐛 BACKLOG — Bug de comportamiento: desempate en `resolve_label()` para términos genéricos (registrado 2026-09-11, Daniel, NO bloqueante)
**Síntoma:** `GET /api/v1/company-taxonomy/search?q=software` → `resolve_label()` (`services/taxonomy/search.py`). "software" aparece en las etiquetas de 6 industrias del sector S02 (Software empresarial/financiero/RRHH/comercial/marketing/"Desarrollo de software"). Las 6 empatan en ranking de coincidencia y el **desempate actual elige la etiqueta más CORTA por nº de caracteres** → sale "Software de RRHH". Resultado: buscar "software" a secas devuelve solo empresas de RRHH, no un resultado general de software.
**Causa:** el criterio de desempate (longitud de string) no tiene relación con la intención del usuario. No es problema de datos ni de nomenclatura, es de comportamiento.
**Ideas a evaluar (sin compromiso):** (a) si hay nodo padre común a los empates (aquí "Desarrollo de software" o el propio S02), priorizarlo sobre las hojas específicas; (b) si no hay forma clara, devolver resultados de las varias industrias empatadas en vez de una sola arbitraria; (c) desempate por señal real: volumen de empresas de la industria o especificidad semántica del término vs. etiqueta.
**Estado:** priorizado por Daniel para una ronda FUTURA. No toca nada de lo desplegado. Prioridad: media.


## Modelo en capas (estable)
```
FUENTES → Raw → Normalized → MASTER LAYER (canónico)        ← Foundation Engine ✅
                                   │
                                   ▼
   ┌─────────────── INTELLIGENCE ENGINES (consumen SOLO el Master Layer) ───────────────┐
   │ Financial · Signal · Semantic · Recommendation · Strategy · Transaction            │
   └────────────────────────────────────────────────────────────────────────────────────┘
                                   ▼
                 CONSUMIDORES: arroba.com · APIs · Copilots · futuros productos
```
**Principio**: cada motor es un servicio de inteligencia **reutilizable** con contrato estable; toda la complejidad vive en el Data Layer; los consumidores nunca tocan fuentes.

---

## 0. Foundation Engine ✅ (COMPLETADO)
Jobs reanudables · Data Layer (Raw→Normalized) · Master Layer (`master_companies`) · Entity Resolution · `entity_xref` · Merge no-destructivo · Knowledge Graph **estructural** (ownership real). Contrato: `MASTER_LAYER_CONTRACT.md`.
> Es el cimiento de todos los motores: todos leen el Master Layer y corren sus reconstrucciones como **handlers de job**.

**Integración del trabajo legacy**: `companies_master` + engines actuales (Search/Value/Recommend/Analyze sobre datos sintéticos) quedan **legacy en retirada**. Se migran motor a motor (paridad → migración → retirada) a medida que cada Intelligence Engine se construye sobre el Master real.

---

## 1. Financial Intelligence Engine ✅ (COMPLETADO — Sprint 2, 2026-06-25)
**Responsabilidad**: estados financieros · KPIs · ratios · evolución · calidad financiera · comparables financieros · valoración · explicabilidad.
- **Entregado**: motor desacoplado `financial-intelligence-v1` con API propia (`/api/v1/financial-intelligence/*`, auth `X-API-Key`), 13 ratios explicables, KPIs canónicos, evolución, `financial_quality_score` (rules-based), comparables estructurales (sin embeddings), valoración honesta (múltiplos referencia inferida) y trazabilidad/linaje completo (sin IA).
- **Tests**: 160/160 smoke verdes. **Contrato/referencia oficial**: `SPRINT_2_COMPLETION.md` + `FINANCIAL_INTELLIGENCE_ENGINE_CONTRACT.md`.
- **Migración legacy**: `skills_value` absorbido (paridad vía `/valuation`); pendiente redirigir consumidores públicos y retirar datos sintéticos.
- **Pendiente futuro**: conectar múltiplos reales de mercado/M&A (BME/transacciones).

## 2. Signal Intelligence Engine ✅ (COMPLETADO — Sprint 3, 2026-06-26)
**Responsabilidad**: oportunidades · anomalías · crecimiento · deterioro · cambios societarios · operaciones · señales de mercado.
- **Entregado**: motor desacoplado `signal-intelligence-v1` (`services/engines/signal/`) con API propia `/api/v1/signal-intelligence/*` (7 endpoints, auth `X-API-Key`, agnóstico de UI). Taxonomía canónica versionada (9 categorías, `tax-v1`), umbrales parametrizables por contexto (`thr-v1`, sin hardcodeo), 4 dimensiones independientes (impact/confidence/urgency/persistence), acciones canónicas (`act-v1`), señales compuestas (`comp-v1`), persistencia e histórico (`signals`), `signal_id` determinista/reproducible, explicabilidad total (sin IA).
- **Contrato CONGELADO** (D1–D8): `SIGNAL_INTELLIGENCE_ENGINE_CONTRACT.md`. **Tests**: 168/168 smoke verdes (8 nuevos).
- **Pendiente futuro**: tipos `corporate.borme_event`, `transaction.ma_event`, `transaction.control_change` declarados ⏳ (fuentes BORME/BME/M&A pendientes de ingesta); señales de cambio societario requieren snapshots versionados del Master. Sprint específico de calibración de `thr-v1` con datos reales.
- **Migración legacy**: `services/signal_engine.py` absorbido (pendiente migrar consumidores Analyze/Recommend/Search).

## 3. Semantic Intelligence Engine ✅ (COMPLETADO — Sprint 4, 2026-06-26)
**Responsabilidad**: Company Semantic Profile (producto) · embeddings derivados · similitud · búsqueda semántica básica.
- **Entregado**: motor desacoplado `semantic-intelligence-v1` (`services/engines/semantic/`) con API propia `/api/v1/semantic-intelligence/*` (6 endpoints: profile, embedding, similar, search, profile/schema, catalog; auth `X-API-Key`, agnóstico de UI). Company Semantic Profile canónico con 14 dimensiones (cada una con `status` available/partial/unavailable + evidence + method + confidence), `coverage` score, IA híbrida y trazable opcional (D-S1), `EmbeddingProvider` local determinista sustituible (D-S2), `VectorSearchBackend` local top-k con blocking por sector (D-S3/D-S5), `profile_checksum` reproducible.
- **Contrato CONGELADO** (D-S1…D-S6): `SEMANTIC_INTELLIGENCE_ENGINE_CONTRACT.md`. **Tests**: 175/175 smoke verdes (7 nuevos). Consume solo Master (+ opc. Financial/Signal); embeddings solo sobre Master.
- **Diferido a futuro**: Atlas Vector Search (backend), Universal Search completo, relaciones semánticas materializadas, IA por defecto en bulk.
- **Migración legacy**: `taxonomy_embeddings` + parte semántica de `skills_search` → este motor (pendiente migrar consumidores).

## 4. Recommendation Intelligence Engine ✅ (COMPLETADO — Sprint 5, 2026-06-26)
**Responsabilidad**: transformar conocimiento en decisiones explicables (comparables, buyers, sellers, opportunities, matching).
- **Entregado**: 1er motor CONSUMIDOR desacoplado `recommendation-intelligence-v1` (`services/engines/recommendation/`), API `/api/v1/recommendation-intelligence/*` (comparables, buyers, sellers, investors, advisors, matching, opportunities, explain, feedback, memory, catalog; auth `X-API-Key`). Reutiliza Financial+Signal+Semantic+Master+KG (no recrea inteligencia).
- **DR1–DR10**: 5 dimensiones de fit independientes (strategic/financial/semantic/signal/execution) con score derivado; `recommendation_role` (strategic_buyer, acquisition_target, roll_up_candidate…); confianza multifactor; acciones canónicas reutilizadas del Signal Engine; recomendaciones compuestas + graph_edges (previsto); **Recommendation Memory** (DR9) + **Feedback Loop** (DR10). Investors/advisors → `unavailable`/`source_not_available` (sin inventar).
- **Contrato CONGELADO**: `RECOMMENDATION_INTELLIGENCE_ENGINE_CONTRACT.md`. **Tests**: 183/183 smoke verdes (8 nuevos).
- **Migración legacy**: `skills_recommend` → este motor (pendiente migrar consumidores).

## 5. Strategy Intelligence Engine ✅ (COMPLETADO — Sprint 6, 2026-06-26)
**Responsabilidad**: razonar estratégicamente componiendo toda la inteligencia previa en tesis explicables y reutilizables.
- **Entregado**: motor consumidor superior `strategy-intelligence-v1` (`services/engines/strategy/`), API `/api/v1/strategy-intelligence/*` (thesis, scenarios, growth, acquisition, divestment, partnership, capital, risk, decision, lifecycle, convert, memory, catalog). DT1–DT15: composición determinista, 5 dimensiones + score derivado, escenarios parametrizables, confianza multifactor, decision support justificado, reutilización por referencia, Strategy Graph, horizonte temporal, evidencia insuficiente honesta, alternativas, constraints, explainability tree, lifecycle, y **Strategic Thesis como entidad canónica persistida** (`strategic_theses`, convert→opportunity/mandate/transaction).
- **Contrato CONGELADO**: `STRATEGY_INTELLIGENCE_ENGINE_CONTRACT.md`. Tests: 191/191 smoke verdes. Reutiliza todos los motores previos; no recrea.

## 6. Transaction Intelligence Engine ✅ (COMPLETADO — Sprint 7, 2026-06-26; nota de actualización 2026-07-23)
**Responsabilidad**: soporte inteligente al ciclo COMPLETO de una transacción (origination → screening → valoración → outreach → negociación → cierre).
- **Entregado**: `transaction-intelligence-v1` + `transaction-os-v1` (DTX1-DTX13) — orquesta todos los motores anteriores como **Transaction Copilot**. Detalle: `TRANSACTION_INTELLIGENCE_ENGINE_CONTRACT.md`, `TRANSACTION_OS_COMPLETION.md`.
- **Nota (2026-07-23)**: esta sección quedó desactualizada tras el Sprint 7 (seguía marcada 🔴 SIGUIENTE pese a estar completada desde 2026-06-26, ver `PRD.md`). Corregido aquí. El Transaction Copilot es una porción ya construida de la visión más amplia de "Arroba Copilot" (experto de mercado/M&A con acceso a TODA la inteligencia, no solo a transacciones) — ver `ARROBA_COPILOT_DEFINITION_v1.md` para el alcance completo, qué ya está cubierto y el gap real de "predecir".

## 7. Capa de Inteligencia Estratégica (Q1–Q7 · E1/E2/E6/E7 · T3 · Control&Synergy) ✅ (IMPLEMENTADA Y DESPLEGADA EN PREVIEW — 2026-07-23, v16)
**Responsabilidad**: capacidades por-encima de los 6 motores base derivadas del roadmap de Quick Wins/Evoluciones/Transformacionales del Capability Map v1 (intent signals BORME, grafo de control navegable, baselines contextuales, feed de oportunidades, drill-down sectorial, múltiplos reales acotados, watchlist, mandatos de comprador, succession intelligence, fragmentación sectorial, tesis de roll-up, Control & Synergy Score) — más una auditoría completa de fuentes de datos y el fix de fondo del ciclo de vida de señales.
- **Estado**: verificado (mongomock + `py_compile` + esbuild) y desplegado en Emergent Preview (testing agent 19/20 backend + 100% frontend). Universo real 24.992 empresas; 160 oportunidades y 66.050 señales confirmadas vía `/stats/view`.
- **Contrato/referencia oficial**: `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md` (informe de cierre completo, 19 secciones, §18 con el detalle de despliegue).

---

## Cadena de dependencias y orden recomendado
```
Foundation ✅ → Financial → Signal → Semantic → Recommendation → Strategy → Transaction
```
- **Financial primero**: el dato real (financieros Iberinform) ya está en el Master → máximo valor inmediato y base para los demás.
- **Signal** puede solaparse parcialmente con Financial (señales financieras dependen de KPIs).
- **Semantic** después del Master consolidado + (idealmente) Financial/Signal para un profile rico (D1/D4: nunca embeddings sobre entidades sin consolidar).
- **Recommendation/Strategy/Transaction** se apilan encima.

## Cómo encaja la migración legacy (transversal a cada motor)
Cada Intelligence Engine, al construirse sobre `master_companies`, **absorbe** su equivalente legacy y dispara la migración controlada: (1) paridad funcional → (2) migración del contrato público al nuevo motor → (3) retirada de la dependencia sobre `companies_master`. El agregador público `enrich_company` (Analyze) pasa a ser una **composición** que consume Financial+Signal+Semantic+KG, manteniendo su contrato estable.
- `skills_value` → Financial · `signal_engine` → Signal · `taxonomy_embeddings`+`skills_search` → Semantic · `skills_recommend` → Recommendation · `enrich_company` → composición de motores.

## Restricciones
No se modifica el trabajo ya construido. No se rompen contratos públicos de arroba. Cada motor consume EXCLUSIVAMENTE el Master Layer. `companies_master` se retira cuando ningún consumidor dependa de ella (D6).

---

## Contrato público arroba (v1 → v2)
- **`arroba.v1`** ✅ congelado (6 motores, 53 rutas, auth `X-API-Key`). Freeze test en CI.
- **Sprint V2.0** ✅ **COMPLETADO Y CONGELADO (2026-07-12):**
  - **V2-01** — DTO de respuesta **tipados** de los 6 motores en OpenAPI (SDK tipado auto-generable).
  - **V2-02** — **Company/Identity** público (`POST /api/v2/company-intelligence/identity`) para la Ficha.
  - Contrato `arroba.v2.json` (54 rutas, 91 schemas) + freeze test. Runtime intacto; v1 byte-idéntico.
  - Docs: `ARROBA_V2_INTEGRATION_GUIDE.md`, `ARROBA_V2_SPRINT_V2.0_REPORT.md`.
- **Sprint V2.1** ⏳ **PENDIENTE (no iniciado)** — Ownership + Ownership Network + Cash Flow. Se retomará
  cuando la Ficha de Empresa esté implementada y validada por arroba.com. Detalle: `ARROBA_V2_CONTRACT_PLAN.md`.
- **Sprints V2.2–V2.4** ⏳ backlog — Valoración avanzada, Comparativa consolidada, Market, Rankings,
  Governance, Sources/Registry, Documents (varios requieren ingesta de datos reales).
- **Mantenimiento actual:** Agency Tool estable; solo corrección de bugs que surjan durante la integración con arroba.com.
