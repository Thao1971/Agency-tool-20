# Intelligence Engine — PRD v34

## Vision
**Intelligence Engine** = un único motor común sirviendo a múltiples productos. Agency Tool no existe como producto: es el motor. **Platform Console** = panel administrativo separado para operar y observar el motor. Valuo y Arroba son productos independientes encima del motor.

## Architecture

```
                    Intelligence Engine (services/intelligence_engine/)
                    ┌────────────────────────────────────────────────┐
                    │ engine.py · profiles.py · linker.py            │
                    │ sources/{web, identity, bme, iberinform, ...}  │
                    │ cache-first → analysis_jobs queue → auto-link  │
                    └────────────────────────────────────────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            │                     │                     │
        valuo.pro            arroba.com         Platform Console
        profile=valuo        profile=arroba    (Health, Profiles,
                                                Sources, Admin)
```

## Platform Console — Sidebar (post-reorganización)

| Sección | Items |
|---------|-------|
| HOME | Dashboard |
| INTELLIGENCE ENGINE | Profiles, Web Source, Scrape Queue, Health, Macro/Sector/Economic/Geo/Cross Intel |
| M&A ENGINE | Transactions, M&A Radar, Valoraciones, Buyers, Sellers, Matching |
| KNOWLEDGE | Taxonomy Intel, Taxonomía CIS, Editorial, Manual, API Docs, Prompts |
| PLATFORM | Configuración, Integraciones, Jobs, Logs, Feature Flags, Calidad de Datos, Document Studio, Template Builder |
| DATA | Companies Master, Agency Results, Iberinform, INE, Economic Intelligence, BME, BORME, CNMV, Contratación Pública, DataComex, OEPM |
| ADMIN | Usuarios, Roles, Seguridad, Auditoría |

## Latest changes (Julio 2026)
- **Deploy v18 (snapshot completo) en Preview ✅ (2026-07-26)**
  - Aplicado `arroba_agency_tool_v18.zip` (consolida v17 + parches v17.1 PDF, v17.2 PPTX, v17.3 editor de marca, v17.4 pestañas editables). Reemplazo total de `backend/`+`frontend/` preservando `.env` y `/app/memory/test_credentials.md`. Deps: pip -r requirements.txt, yarn install, `playwright install --with-deps chromium` (Chromium v1208). Sin re-ingesta ni purga: 24.992 empresas reales intactas (ambos esquemas), 66.050 señales.
  - `export_to_pptx` ya es `async` en v18 (coincide con el `await` en routes.py) → el bug async/sync del traspaso quedó consolidado, sin parche manual.
  - Verificación backend (curl E2E): health OK, auth negativa 401, iberinform/stats 24.992 real / 0 sintético, motores M&A (fragmentation/rollup con X-API-Key 200, fragmentation/view JWT 200, ratios 200, watchlist 200), preview-live refleja el color de acento. IM de LABORATORIOS SERVIER (CIF B28184687): 27 secciones → PDF 27 págs 960×540 (16:9 apaisado, con gráficos), PPTX 27 slides 16:9 (1 imagen/slide), HTML de slides OK.
  - Verificación frontend (testing_agent iteration_15, 80%→100% tras fix): login + /doc-studio (5 pestañas), Marcas (editor + preview live + guardar persiste), Plantillas→Constructor navegación OK. **Bug HIGH corregido**: `TemplateBuilderPage.js VisualSection` leía solo campos planos legacy (`primary_color`/`accent_color`) → encabezados de sección salían azules para marcas basadas en `tokens.*` (CIS/Arroba/Valuo). Ahora lee `tokens.colors.accent` como VisualBlock. Verificado visualmente: marca CIS pinta encabezados/portada/KPIs en color de marca (oliva), no azul.
  - Nota: la app expone 5 marcas (brand_bud, brand_cis, brand_arroba, brand_valuo, brand_custom).

- **Sprint 9 — Capa de Inteligencia Estratégica (Q1–Q7·E1/E2/E6/E7·T3·Control&Synergy) + auditoría de fuentes + Copilot definition ✅ IMPLEMENTADO, VERIFICADO Y DESPLEGADO EN PREVIEW (2026-07-23, v16)**
  - **Documentación de cierre**: todo el trabajo de esta entrada se implementó a lo largo de varias sesiones previas pero solo existía en memoria de sesión — queda ahora documentado formalmente en `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md` (informe completo, 19 secciones) y `ARROBA_COPILOT_DEFINITION_v1.md` (definición del Copilot: cobertura actual vs. gap real de "predecir", propuesta de endpoint agregador Copilot Context).
  - **Quick Wins Q1–Q7** sobre el esquema moderno (`master_companies`/`master_id`): intent signals desde BORME (Q1, con corrección de diseño de "edad" → "tenure real", único dato respaldado por Iberinform), grafo de control de un salto + `competitor_of` real (Q2, corrigiendo el diagnóstico erróneo de "2/8 relaciones materializadas"), baselines contextuales por sector×tamaño (Q3), feed unificado de oportunidades con ciclo de vida (Q4), drill-down sector→empresa (Q5), múltiplos reales de M&A Radar acotados a agencias de publicidad CNAE 73 (Q6), watchlist + alertas in-app (Q7).
  - **Evoluciones**: Buyer Mandate Intelligence (E1), Succession Intelligence completa con perfil enriquecido (E2), Índice de fragmentación sectorial HHI (E7), Tesis de roll-up/plataforma (E6).
  - **Transformacional (MVP)**: grafo de control navegable multi-salto (T3, BFS acotado) + **Control & Synergy Score** (diseño propio en 2 scores independientes, control por % real de propiedad + synergy estructural, ya que el roadmap nombraba el score sin fórmula).
  - **Frontend**: 8 pantallas nuevas (Oportunidades, Señales, Watchlist, Fragmentación, Roll-up Thesis, Grafo de Control, Control & Synergy, DIRCE/Demografía Empresarial) + rediseño completo de `Layout.js` (14 páginas reales que no tenían entrada de menú, ahora navegables; sección "PRÓXIMAMENTE" separada visualmente de lo construido).
  - **Ingesta de datos real**: sustitución del dataset sintético por las 25.000 empresas reales de Iberinform en ambos esquemas (legacy + moderno) vía nuevo ingestor `.tab`, botón de subida en la app para entregas mensuales (`IberinformDeliveryPage.js`), y fix crítico del resolver de identidad (colisión `E11000` entre matriz/filial que comparten dominio — el CIF pasa a ser siempre el identificador definitivo cuando existe).
  - **Auditoría de fuentes de datos**: fix de enmascaramiento en cascada en `intelligence_scheduler.py` (4 pasos ahora aislados con try/except propio); scheduler nuevo para PLACSP (antes sin refresco periódico) + botón manual; reloj de frescura real en Banco de España (antes mostraba siempre "ahora"); `company_id` legacy de Iberinform ahora estable entre entregas (`$setOnInsert`, antes se regeneraba cada mes); reincorporación del fix de reciclado de Chromium de CNMV aplicado por Neo directamente en el entorno desplegado (evita que un futuro zip lo revierta); BME Growth/Scaleup diagnosticado como migración de sitio en curso, no bug de selector.
  - **Ciclo de vida de señales**: fix de fondo (clave de identidad de una señal deja de incluir `source_version`, antes generaba duplicados en cada entrega mensual) + migración de una sola vez (`POST /migrate-dedupe`); fix del filtro `category` vs. `severity` en Oportunidades (solo 1 de 4 tipos reales se mostraba); endpoints `/stats`/`/stats/view` de conteo real no acotado por paginación.
  - **Tests**: cobertura mongomock específica de cada pieza (rangos de 6/6 a 24/24 checks por módulo, ver `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md` para el detalle por sección) + verificación end-to-end contra el entorno Emergent Preview (datos sintéticos hasta la carga real; reales desde la Actualización v6 de ese entorno).
  - **Estado**: verificado localmente (mongomock + `py_compile` + esbuild) y **desplegado en Emergent Preview como `arroba_agency_tool_v16.zip`** — testing agent 19/20 backend (único "fallo" es un bug de aserción del test, no del código) + 100% frontend, 0 errores de consola. `migrate-dedupe` ejecutado una vez (9 grupos fusionados). Recuentos reales confirmados: `total_signals=66050`, `total_opportunities=160`, universo 24.992 empresas en los tres esquemas. Detalle completo en `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md` §18.
  - Docs: `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md`, `ARROBA_COPILOT_DEFINITION_v1.md`.


## Latest changes (Junio 2026)
- **Sprint 8.6 — M3 Fase 2b · Ingesta & Cobertura del Master Record ✅ (2026-07-04)**
  - **Proyección legacy→canónica** `legacy_projection.py` (`project_and_build`): puebla `master_companies` con el universo real de legacy vía pipeline legítimo (`norm_company` → `rebuild_master(cif_list)`), etiquetado y **reversible por batch** (`rollback_projection`). `companies_master` intacto (solo lectura).
  - **Resultado**: universo canónico 1.000→**6.259** (5.259 proyectados). Bridge re-ejecutado (`erb_202d8224d594`): **cobertura 0 % → 98,17 %** (5.255 enlazadas / 5.353; 21 conflictos, 4 ambiguas, 73 huérfanas, 25 revisión manual, 0 duplicados). Overlap CIF legacy 99,02 %. **Objetivo ≥95 % superado.**
  - **Requisitos**: motor canónico NO activado, sin migrar tráfico, sin borrar datos, sin matcher fuzzy, sin reanudar M2. Cero regresión.
  - **Recomendación**: bloqueante de cobertura RESUELTO. **NO activar `canonical`** hasta resolver 25 casos de revisión manual + huérfanas con nuevo informe. M2 desbloqueado. Ver `M3_PHASE2B_REPORT.md`.


- **Sprint 8.5 — M3 Fase 2 · Entity Bridge & Master Record Quality Tool ✅ (2026-06-26)**
  - **Herramienta permanente** `entity_bridge.py` + rutas admin `/api/v1/master/bridge/*`: bridge canónico `master_company_id`↔`master_id` en `entity_xref`, **idempotente/auditable/reversible** (rollback por run_id), histórico (`er_bridge_runs`) y clasificación por entidad (`er_bridge_results`). Detecta linked/conflictos/ambigüedades/duplicados/huérfanas.
  - **Requisitos cumplidos**: legacy intacto, cero cambio en producción, motor canónico NO activado, sin migrar tráfico, sin borrar datos.
  - **Medición objetiva**: 5350 legacy vs 1000 canónicos → **cobertura 0 %** (datasets disjuntos). Golden 106→**111 verde**.
  - **Recomendación**: **NO activar `canonical`** (orfanaría 100% de Valuo.pro). Prerrequisito: ampliar la ingesta canónica al universo real, re-ejecutar el bridge y aprobar nuevo informe. Ver `M3_PHASE2_BRIDGE_REPORT.md`.


- **Sprint 8.4 — M3 (Entity Resolution) Fase 1 ✅ (2026-06-26)**
  - **Contrato CONGELADO** `entity-resolution-v1` (DER1–DER9). Alcance Fase 1: motor canónico + red de seguridad + paridad; **sin migrar tráfico, sin retirar legacy, sin backfill masivo** (→ M3-fase-2).
  - **Motor canónico unificado**: `data_layer/master/identity_resolver.py` (`resolve_identity` shape legacy-compatible, `deterministic_master_id` DER5, `link_legacy_master` DER3 bridge `entity_xref`, umbrales DER4, auditoría DER6).
  - **Provider de convivencia** `entity_resolution_provider.py` (flag `ENTITY_RESOLUTION_SOURCE`, default legacy), cableado en `valuo_integration`/`master`/`procurement` (contrato público único DER7, rollback inmediato).
  - **Validación**: snapshot-diff de `resolve_entity` + guards. Golden 96→**106 verde**. Smoke **203/203** (cero regresión Valuo.pro). Default legacy = byte-identical.
  - `entity_xref` bridge legacy↔canónico establecido (mecanismo) → habilitará la cobertura de M2 tras M3-fase-2.


- **Sprint 8.3 — M2 inicio → ⛔ DETENIDA EN VALIDACIÓN (2026-06-26)**
  - Entregada **infra de convivencia interna** con **contrato público único**: flag `MASTER_RECORD_SOURCE` (default legacy), `master_provider.py` (legacy byte-identical / canónico con fallback transparente), cableado en `enrich_company`. Rollback inmediato; sin parámetro público; el canónico nunca causa `master_not_found`.
  - **Golden dataset ampliado** (casos límite): 14 empresas / 28 snapshots. Golden suite 82→**96 verde**. Smoke **203/203** (cero regresión en `enrich`, ruta crítica Valuo.pro).
  - **BLOQUEANTE**: `companies_master` (5338) y `master_companies` (1000) **disjuntos** (overlap cif_normalized=0; resolución canónica 0/14). Paridad imposible hoy → legacy NO retirado, tráfico NO migrado (`MASTER_SOURCE_PARITY_REPORT.md`).
  - **Re-secuenciación**: M2 depende de cobertura del Master canónico ⇒ priorizar **M3 (Entity Resolution)** + **M2-pre (backfill/linkage)** antes de reanudar M2.


- **Sprint 8.2b — Preparación M2 (snapshot-diff + golden dataset) 🟡 LISTO (2026-06-26)**
  - Red de paridad para M2: golden dataset **congelado** de 9 empresas (rich_financials/with_web/discovered) × {valuo, arroba} = **18 snapshots** (`tests/golden/data/enrich_golden_snapshots.json`).
  - `test_enrich_snapshot_diff.py` recomputa `enrich_company` y exige **paridad byte-level** (order-insensitive) de `fields`/`sources_with_data`/`found_map`/`engine_version`. Generador: `python -m tests.golden.gen_enrich_golden`.
  - Suite golden **62 → 82 tests** (verdes, idempotentes). **Sin cambios de código de producción.** Detectará cualquier deriva de cálculo cuando M2 cambie el origen de datos interno.


- **Sprint 8.2 — Consolidación red de seguridad + M1 (migración piloto) ✅ COMPLETADO (2026-06-26)**
  - **FASE A**: Golden Contract Tests ampliados 47→**62** (data-layer admin + contrato `rebuild-signals` + snapshot determinista de `compute_signals`/`signal_similarity` + invariantes + test de paridad).
  - **FASE B — M1**: `services/signal_engine.py` (legacy master-signals sobre `companies_master`) **relocalizado byte-for-byte** a `services/engines/signal/master_signals.py` (md5 idéntico); el path antiguo queda como **shim de convivencia**; 2 importadores (`routes/data_layer`, `skills_recommend`) migrados a la ruta canónica.
  - **Decisión clave**: la sustitución semántica por el motor canónico `engines/signal.engine` se DESCARTÓ (no equivalente; habría roto contrato). M1 = relocalizar + shim.
  - **Validación (testing_agent iteration_24, 0 issues)**: Golden **62/62** (incl. paridad: shim↔canónico mismo objeto, `signal_score=71`), Smoke **203/203**, `rebuild-signals` total=5329/with_signals=5329, `skills/recommend` intacto. Cero regresiones, cero cambios de contrato, impacto Valuo.pro/arroba nulo.
  - Docs: `M1_PILOT_MIGRATION_REPORT.md`, `CHANGELOG.md`, `LEGACY_MIGRATION_PLAN.md` (M1 ✅), `INTELLIGENCE_API_REFERENCE.md`. Patrón Construir→Validar→Migrar→Convivencia→Monitorizar→Retirar **VALIDADO**. M2–M5 NO iniciadas (pendiente aprobación).


- **Sprint 8.1 — Golden Contract Tests ✅ COMPLETADO (2026-06-26, solo red de seguridad)**
  - Suite black-box `/app/backend/tests/golden/` que **congela el contrato observable** (HTTP code, headers, estructura JSON, tipos, campos obligatorios/opcionales, invariantes calculados, errores 404/400/422/401, vacíos/parciales, backward-compat) de **19 endpoints 🔴 Legacy crítico** en **47 tests** (5 dominios: Valuo Integration, Intelligence Enrich, Enriched Company, Master+Publish-to-Valuo, Skills).
  - **47/47 PASS** (idempotente) + smoke global **203/203** intacta. Validado de forma independiente por testing_agent (iteration_23, 0 issues). **No se tocó ningún endpoint** (regla de congelación de contrato respetada).
  - Entregables: `GOLDEN_CONTRACT_COVERAGE_MATRIX.md`, `GOLDEN_CONTRACT_FINAL_REPORT.md` (incl. gaps conocidos, riesgos R1–R4 y siguiente paso recomendado **M1: signal_engine antiguo → engines/signal**, riesgo BAJO / impacto Valuo.pro nulo).
  - Migración NO iniciada: empezará solo tras aprobación, con todos los contratos críticos protegidos.


- **Sprint 8 — Agency Tool Final Audit & Migration Plan ✅ COMPLETADO (2026-06-26, solo documentación)**
  - Nueva prioridad: **consolidar la plataforma antes de Marketplace**. Agency Tool = plataforma compartida en producción (Valuo.pro + arroba.com + Platform Console). Regla absoluta: **no romper ningún consumidor**.
  - Entregables (read-only, sin tocar código/contratos): `AGENCY_TOOL_AUDIT_FINAL.md` (matriz de dependencias y clasificación 🟢/🟡/🔴/⚫ de endpoints, servicios y colecciones), `LEGACY_MIGRATION_PLAN.md` (ciclo Construir→Validar→Migrar→Convivencia→Monitorizar→Retirar + golden tests), `INTELLIGENCE_API_REFERENCE.md` (los 7 motores: propósito, contrato, endpoints, dependencias, consumidores, versión, tests, estado). + `PLATFORM_GOVERNANCE_AND_CONSUMER_AUDIT.md`.
  - Hallazgo clave: 2 capas de datos en convivencia — `companies_master` (legacy, Valuo.pro) vs `master_companies` (canónico, arroba). **0 componentes elegibles para retirada hoy.**
  - Marketplace/Deal Rooms/Copilot UI/Pipeline Board quedan EN PAUSA hasta aprobar esta auditoría.


- **Sprint 7 — Transaction OS & Transaction Intelligence Engine ✅ COMPLETADO (2026-06-26)**
  - **Transaction OS** (`services/transaction_os/`): propietario único del estado — entidades (`tx_transactions/tx_events/tx_tasks/tx_approvals/tx_documents`), máquina de estados declarativa versionada (`state-machine-v1`), event log append-only, approvals, data room/documentos, tareas, Universal Timeline y memoria. `workflows.py` (templates DTX2 + transiciones DTX3) + `store.py` (runtime event-driven).
  - **Transaction Intelligence Engine** (`services/engines/transaction/engine.py`): orquestador `transaction-intelligence-v1`; next-best-action, riesgos, prepare_document, workspace y explicabilidad multifactor. NO mantiene estado (auditado: sin acceso directo a DB; delega 100% en el OS).
  - **API** `routes/transaction_intelligence.py` con los 12 endpoints del contrato (§8) + `/workspace` (DTX12), `X-API-Key`, registrada en `server.py`, índices en startup.
  - DTX1–DTX13 verificados con tests reales (no solo documental): frontera OS↔Engine, máquina de estados sin transiciones implícitas, approvals de alto riesgo, confianza de 7 factores, Universal Timeline, Workspace agregado, Event Driven First.
  - Auditoría arquitectónica completa PASS. Contrato CONGELADO. Doc de cierre: `TRANSACTION_OS_COMPLETION.md`. Tests: **203/203 smoke verdes** (12 nuevos) + validación E2E del testing_agent (24/24). Sin regresiones.
  - Cierra definitivamente el núcleo operativo; base permanente para Marketplace, Deal Rooms, Copilot transaccional y arroba.com.


- **Sprint 6 — Strategy Intelligence Engine ✅ COMPLETADO (2026-06-26)**
  - Motor consumidor superior `strategy-intelligence-v1` en `services/engines/strategy/` con API `/api/v1/strategy-intelligence/*` (thesis, scenarios, growth, acquisition, divestment, partnership, capital, risk, decision, lifecycle, convert, memory, catalog; `X-API-Key`).
  - DT1–DT15: composición determinista (IA solo redacta), 5 dimensiones estratégicas + score derivado, escenarios parametrizables, confianza multifactor, decision support justificado, reutilización por referencia, Strategy Graph, horizonte temporal, evidencia insuficiente honesta, alternativas, constraints, explainability tree, lifecycle, y Strategic Thesis como ENTIDAD CANÓNICA persistida (`strategic_theses`) con convert→opportunity/mandate/transaction.
  - Reutiliza todos los motores previos; no recrea. Contrato CONGELADO: `STRATEGY_INTELLIGENCE_ENGINE_CONTRACT.md`. Tests: 191/191 smoke verdes (8 nuevos).
  - Próximo: Transaction Intelligence Engine (ejecuta la tesis), última pieza del flujo M&A.

- **Sprint 5 — Recommendation Intelligence Engine ✅ COMPLETADO (2026-06-26)**
  - 1er motor CONSUMIDOR `recommendation-intelligence-v1` en `services/engines/recommendation/` con API `/api/v1/recommendation-intelligence/*` (comparables, buyers, sellers, investors, advisors, matching, opportunities, explain, feedback, memory, catalog; `X-API-Key`).
  - Reutiliza Financial+Signal+Semantic+Master+KG (no recrea). DR1–DR10: 5 fit dims independientes + score derivado, recommendation_role, confianza multifactor, acciones canónicas del Signal Engine, composites/graph_edges (DR7/DR8 previstos), Recommendation Memory (DR9) + Feedback Loop (DR10). Investors/advisors unavailable/source_not_available.
  - Contrato CONGELADO: `RECOMMENDATION_INTELLIGENCE_ENGINE_CONTRACT.md`. Tests: 183/183 smoke verdes (8 nuevos).
  - Pendiente estratégico (diferido por decisión del usuario): enriquecimiento IA masivo del Semantic Profile (tras medir qué dimensiones mejoran las recomendaciones).

- **Sprint 4 — Semantic Intelligence Engine ✅ COMPLETADO (2026-06-26)**
  - Motor desacoplado `semantic-intelligence-v1` en `services/engines/semantic/` con API `/api/v1/semantic-intelligence/*` (profile, embedding, similar, search, profile/schema, catalog; `X-API-Key`).
  - Producto = **Company Semantic Profile** (14 dimensiones con status/evidence/method/confidence, coverage score). Embeddings = artefacto derivado versionado (`EmbeddingProvider` local sustituible) + `VectorSearchBackend` local top-k con blocking (Atlas diferido). IA híbrida opcional y trazable (D-S1). Contrato CONGELADO con D-S1…D-S6.
  - Consume solo Master (+ opc. Financial/Signal); embeddings solo sobre Master. Tests: 175/175 smoke verdes (7 nuevos). Doc: `SEMANTIC_INTELLIGENCE_ENGINE_CONTRACT.md`. Arquitectura de la capa: `INTELLIGENCE_LAYER_ARCHITECTURE.md`.
  - Próximo: Recommendation Engine (1er consumidor); Universal Search y Atlas diferidos.

- **Sprint 3 — Signal Intelligence Engine ✅ COMPLETADO (2026-06-26)**
  - Motor desacoplado `signal-intelligence-v1` en `services/engines/signal/` con API propia `/api/v1/signal-intelligence/*` (analyze, sector, territory, opportunities, catalog, signal/{id}, history; auth `X-API-Key`, agnóstico de UI).
  - Contrato CONGELADO con D1–D8: taxonomía canónica versionada (9 categorías), umbrales parametrizables (sin hardcodeo), 4 dimensiones independientes (impact/confidence/urgency/persistence), acciones canónicas, señales compuestas (reutilizan señales como evidencia), persistencia+histórico, `signal_id` determinista, explicabilidad total. Sin IA.
  - Consume solo Master + Financial Engine + KG. Tipos BORME/M&A declarados ⏳ (fuentes pendientes). Tests: 168/168 smoke verdes (8 nuevos). Doc oficial: `SIGNAL_INTELLIGENCE_ENGINE_CONTRACT.md`.
  - Próximo: Semantic Engine; sprint de calibración de `thr-v1` con datos reales.

- **Sprint 2 — Financial Intelligence Engine ✅ COMPLETADO (2026-06-25)**
  - Motor desacoplado `financial-intelligence-v1` en `services/engines/financial/` con API propia `/api/v1/financial-intelligence/*` (auth `X-API-Key`). Boundary First: consumidores nunca tocan `master_companies`.
  - Capacidades: estados, KPIs canónicos, 13 ratios explicables, evolución, `financial_quality_score` (rules-based), comparables estructurales (sin embeddings), valoración honesta (múltiplos referencia inferida), assessment y linaje completo. **Sin IA.**
  - Tests: 160/140 smoke verdes (7 nuevos). Referencia oficial: `SPRINT_2_COMPLETION.md`. Absorbe `skills_value` legacy.
  - **Nuevo modo de trabajo a partir de Sprint 3 (Signal)**: cada motor es un producto con su propio contrato y APIs expuestas, no un "sprint que terminar".
- **Fase 1 fuentes públicas — 3 nuevas sources en el Intelligence Engine (NUEVO)**
  - `sources/grants.py` → colección `government_grants` (datos.gob.es / CDTI / ENISA / Fondos UE). Match por CIF o razón social.
  - `sources/employment.py` → colección `employment_statistics` (Seg. Social + SEPE). Agregado CNAE × Provincia × CCAA.
  - `sources/territorial.py` → colección `territorial_statistics` (INE). Agregado Municipio / Provincia / CCAA.
  - **Profile `valuo`**: 5 → 7 sources (añadidos `grants`, `territorial`)
  - **Profile `arroba`**: 10 → 13 sources (añadidos `grants`, `employment`, `territorial`)
  - Índices Mongo creados. Colecciones existen pero vacías — pendiente scripts de ingestión desde datos.gob.es, Seg.Social y INE.
  - Engine sigue completando arroba en 134ms con 13 sources. **Smoke 27/27 verde** sin regresiones.
- **Enriched Company API — Contrato canónico explícito Valuo ↔ Intelligence Engine (FINAL)**
  - `GET /api/v1/company/{master_company_id}/enriched` — público, devuelve TODO en una sola respuesta:
    - **Top-level flat fields** (lo que Valuo bindea directamente en la ficha): `description`, `category`, `subcategory`, `tags`, `logo_url` (resuelto), `email`, `phone`, `address`, `main_clients`, `awards`, `has_awards`, `is_public_company`, `isin`, `market_cap`, `revenue_latest`, `employees_latest`, …
    - **`sources` nested** (lineage para consumidores avanzados como arroba): `web`, `bme`, `borme`, `cnmv`, `iberinform`, `procurement`, `datacomex`, `economic_intel`, `oepm`
    - **`sources_present`** — mapa booleano por fuente
    - **`updated_fields`** — lista de campos top-level con datos
  - `GET /api/v1/company/by-valuo-id/{valuo_company_id}/enriched` — lookup desde el ID externo de Valuo
  - `/valuo/request-status/{id}` ahora devuelve `enriched_company_url` apuntando al nuevo endpoint
  - Logos resueltos automáticamente: `logo_storage_path` → `{BACKEND_URL}/api/v1/screenshots/{path}` (servible directamente como `<img src>`)
  - Smoke tests: 5 nuevos (incluyendo verificación de que el logo URL devuelve un binario con content-type image/*)
  - **Suite total: 27/27 verde en 2.2s** (local) / 4s (preview)
  - Flujo final Valuo: `POST request-update-from-valuo → poll request-status → status==completed → GET enriched_company_url → pintar ficha`
- **Canonical Enriched Company Contract (intelligence/company/{id}) — primera iteración**
  - `GET /api/v1/intelligence/company/{master_company_id}` — público, devuelve identity + sources blocks + sources_present map + logo_url (resuelto) + linked_valuo_ids + last_enriched_at
  - `GET /api/v1/intelligence/company/by-valuo-id/{valuo_company_id}` — lookup directo desde el ID de Valuo
  - `GET /api/v1/valuo/request-status/{id}` ahora incluye campo `enriched_company_url` apuntando al endpoint canónico → Valuo solo necesita dereferenciar después de `status==completed`
  - logos resueltos automáticamente: `logo_storage_path` → `{BACKEND_URL}/api/v1/screenshots/{path}` (Valuo puede usar el URL directamente en `<img src>`)
  - Smoke tests añadidos: 4 nuevos (get_company_by_id, 404, by-valuo-id, url dereferenciable). **Suite total: 26/26 verde en 2s**
  - Fix raíz del problema reportado: `updated_fields: []` no es bug — significa "no se enriqueció nada nuevo en esta llamada concreta", pero los datos ya enriquecidos previamente (description, tags, logo) viven en `master.sources.*` y se leen via el nuevo endpoint canónico
- **Engine Versioning — `/api/v1/engine/version` y `/api/v1/engine/capabilities`**
  - `GET /engine/version` devuelve identity card completo: `engine_name`, `engine_version`, `build_timestamp`, `git_commit` (resuelto vía git, env GIT_COMMIT/COMMIT_SHA o fallback), `environment` (APP_ENV/ENVIRONMENT/NODE_ENV), `profiles`, `sources`, `health` verdict en vivo
  - `GET /engine/capabilities` declarativo: `profiles`, `sources`, `modules` = [lineage, cache, queue, enrichment, matching]
  - Módulo `services/intelligence_engine/engine_info.py` con caché lru por proceso
  - Smoke tests añadidos: 22/22 verde (incluye test_engine_version + test_engine_capabilities)
  - Útil para: auditoría desde Valuo/arroba ("¿qué versión me sirve?"), smoke post-deploy ("¿estoy probando el commit que acabo de desplegar?"), soporte sin SSH
- **Smoke Tests E2E — Red de seguridad para deploys**
  - Paquete `/app/backend/tests/smoke/` con **20 tests en 8 archivos** + `conftest.py` compartido + `run_smoke.sh` ejecutable
  - Cubre: engine health, profiles (existencia + jerarquía basic ⊂ valuo ⊂ arroba), enrichment (200/404/400), Valuo E2E (pending→completed <10s), web source (cache hit/miss/queue), lineage (master.sources.* presente), sidebar (7 secciones + branding)
  - Tiempo: **~1s contra localhost, ~4s contra preview**. 20/20 verde.
  - Parametrizable vía `SMOKE_BASE_URL=…` — apto para pre-deploy, post-deploy y rollback automático
  - Documentación en `tests/smoke/README.md`
- **Platform Console — Reorganización completa**
  - Sidebar rediseñado en 7 secciones que reflejan la arquitectura real
  - Branding actualizado: "Intelligence Engine / Platform Console" (antes "Agency Tools / BUD Advisors")
  - Nuevas páginas: `/engine/health` (observabilidad consolidada: requests + scrape queue + profiles + timeline 1h), `/engine/profiles` (3 perfiles + test sandbox), `/engine/scrape-queue` (cola con auto-refresh 10s), `/engine/web-source` (wrapper sobre agency_results)
  - Placeholders informativos para secciones futuras (M&A Buyers/Sellers/Matching, Knowledge Prompts, Platform Integrations/Jobs/Logs/Feature Flags, OEPM, Admin Usuarios/Roles/Seguridad/Auditoría) — cada uno explica por qué está pending y de qué depende
  - Auto-refresh cada 30s en Health, cada 10s en Scrape Queue
- **Intelligence Engine — Fase 2 (Convergencia total)**
  - Cache-first web source, auto-queue on miss
  - 309 agency_results migrados al master
  - Worker post-link automático
- **Intelligence Engine — Fase 1**
  - 10 sources modulares + 3 perfiles
  - `POST /api/v1/intelligence/enrich`
- **Dashboard: Valuo Health Check panel**
  - Endpoint `GET /api/v1/valuo/health` con counts, timeline última hora, oldest_stuck, p50/p95
- **Valuo Enrichment Pipeline — Verificación E2E completa**
  - Bug fix: `legal_name` ahora se incluye en el merge desde el payload de Valuo (faltaba en `valuo_integration.py`)
  - Bug fix: `merge_into_master` ahora sobrescribe valores placeholder ("Unknown", "N/A", "None", "")
  - Bug fix: `duration_ms` ahora se calcula correctamente (era negativo: `started_at` vs `finished_at`)
  - Bug fix: `last_enriched_at` se actualiza siempre (antes solo si había `enriched_data` no vacío)
  - Recovery automático: nueva función `_recover_stuck_valuo_requests` en startup que detecta peticiones en `pending`/`processing` huérfanas (de reinicios anteriores) y las re-procesa en background
  - Test de carga: 5 peticiones concurrentes completadas en ~27ms cada una, 0 atascadas
  - Resultado producción: 14/14 completed, 0 pending, 0 failed

## Current State (Junio 2026)

### Data Sources (8 activas)
| Fuente | Registros | Estado | Auto-sync |
|--------|-----------|--------|-----------|
| PLACSP | 183,978 contratos (948M EUR) | Active | Background startup |
| BORME | 39,721 eventos | Active | Diario 03:00 |
| **BME Markets** | **254 cotizadas (1.4T EUR)** | **Active** | **Diario enrichment** |
| CNMV | 2,090 entidades inversoras | Active | Background startup |
| DataComex | 1,169 registros comercio | Active | Mensual Playwright |
| Iberinform | 5,000 empresas (DIRCE) | Synthetic | Startup seed |
| INE | 525 registros | Active | Startup |
| BdE | 1,742 indicadores | Active | Startup |

### Intelligence Layers
| Layer | Metrics | Signals | Sources |
|-------|---------|---------|---------|
| Economic Intelligence | 4,290 | 86 | 7 (incl. BME) |
| Sector Intelligence | 285 | — | BORME+INE+Procurement |
| Geo Intelligence | 71 | — | BORME+DIRCE |
| Cross Intelligence | 1,040 | — | BORME×CNAE×Province |
| CNMV Investor Intel | 2,090 entities | 13 signals | CNMV |
| BME Market Intel | 254 companies | 7 signals | BME |
| Taxonomy Intelligence | 143 mappings | — | TARIC+CPV |

### BME Markets (MATURE — closed)
- 254 companies (121 Principal + 98 Growth + 35 Scaleup)
- 1.4T EUR total market cap
- Quality Score 96/100
- Comparables by sector/CNAE with quartiles
- Sector leaders (full IBEX 35)
- Sector multiples for Valuation Engine
- 11 corporate events + 7 signals
- Daily enrichment scheduler
- Integrated with Economic Intelligence

### Document Intelligence Studio (DIS)
- 8 document types active
- Template Builder with visual designer
- Financial Engine (deterministic)
- Fact-Lock Mode
- Export PDF + PPTX
- Quality Score A/B/C/D
- Telemetry

## Completed Modules (All)
- All data connectors (BORME, INE, BdE, PLACSP, DataComex, CNMV, BME, Iberinform)
- All intelligence layers (Sector, Geo, Cross, Economic, CNMV Investor, BME Market)
- Taxonomy Intelligence (TARIC+CPV→CNAE, auto-approve)
- Document Intelligence Studio (8 doc types, Template Builder, Financial Engine)
- Dashboard reorganized (Estado de las Fuentes, 8 sources)
- Auto-reconstruction on startup (background strategic sources)
- Daily schedulers (BORME, Intelligence, BME enrichment)
- Monthly scheduler (DataComex Playwright)
- Manual v11, API Docs, full documentation

## Roadmap
### Next priorities (TBD by user)
- Iberinform real file (3.3M companies → unlocks cross-matching)
- MongoDB Atlas (scale for production)
- Universal Search (arroba.com)
- OEPM (congelado — post-Iberinform)
- CNMC (diferido — datos no estructurados)
- Copilot IA

### Maintenance (automatic)
- BME daily enrichment (50 companies/night)
- BORME daily ingestion
- Intelligence daily rebuild (04:00-04:15)
- DataComex monthly sync (day 15)

---

## CHANGELOG

### 2026-06-25 — Sprint 1: Master Intelligence Layer (núcleo canónico del Data Layer)
- **`master_companies` = colección canónica OFICIAL** (decisión D6). `companies_master` queda **legacy en retirada**; conviven solo por compatibilidad (engines actuales intactos, contratos arroba inmutables). Migración controlada posterior (paridad → engine por engine → retirada). Contrato oficial: `/app/memory/MASTER_LAYER_CONTRACT.md`.
- **Master Layer** (`services/data_layer/master/master_builder.py`): construye `master_companies` desde el Normalized Layer (provider-independent, `master_id` permanente). Batched (lotes de 500, sin N+1: pre-fetch financials/ownership/officers por lote), idempotente vía `source_hash`. Proyecta identity/classification/location/contact/size/financials(latest+history)/ownership/officers_count/objeto_social.
- **Entity Resolution reutilizable y explicable** (`entity_resolution.py`): cadena de reglas por prioridad (exact_cif 1.0 → domain 0.9 → name+province 0.7 → nuevo id). Arquitectura preparada para reglas probabilísticas/IA. Cada resolución registra `match_rule`+`confidence`.
- **`entity_xref`**: mapa no-destructivo `(source, id_type, external_id) → master_id` (cif/iberinform_id/domain). Las fuentes originales NUNCA se modifican.
- **Merge no-destructivo con provenance** (`merge.py`): cada campo conflictuable conserva todos los candidatos `{source,value,observed_at,confidence}`; canónico = max(confidence, prioridad_fuente, recencia). Re-ejecutar una fuente solo reemplaza su candidato.
- **P0.3 integrado**: `pipeline_version` (master-v1), `source_hash`, `dirty`; jobs incrementales (scope `full|incremental|cif_list`), recomputación solo de afectados (rerun full → 0 built / todos skipped; incremental procesa solo dirty).
- **P0.4 integrado**: índices creados al introducir cada colección (master_companies: cif_normalized unique, name_key, contact.domain, cnae_section, provincia, status, dirty, group_id; entity_xref: (source,id_type,external_id) unique + master_id; master_relationships: (src,dst,type,year) unique).
- **Knowledge Graph fase 1 (solo estructural)** (`ownership_graph.py`): `master_relationships` derivadas del **ownership real** (shareholder_of/parent_of/ultimate_parent_of/investee_of), mapeando CIF↔master_id. `same_group` vía **union-find → `group_id`** (sin aristas pairwise O(n²)). Sin similitud/embeddings (diferido).
- **Job handlers** (`rebuild_master`, `rebuild_ownership_graph`) sobre la infra reanudable; **validado e2e**: API encola → worker separado procesa (1000 masters). Ingestión muestra: 1000 masters, 2270 xref, 429 aristas ownership (10 resueltas + 419 externas), 1 grupo.
- **Tests**: `tests/smoke/test_master_layer.py` (7: shape canónico, xref+fuentes intactas, idempotencia+id permanente, incremental, provenance no-destructiva, KG solo estructural, rebuild vía job runner). Suite total: **153/153 verde** en 75s.
- ⚠️ Entregables Sprint 1 COMPLETOS: Master Layer · Entity Resolution · entity_xref · merge no-destructivo · jobs de rebuild · versionado incremental (P0.3) · índices (P0.4) · KG estructural ownership · MASTER_LAYER_CONTRACT.md.


### 2026-06-25 — P0.2 Infraestructura de jobs reanudables (worker separado, cola en Mongo)
- **Decisión de arquitectura aprobada (worker separado, sin infra distribuida)**: API ↔ procesamiento separados. La API solo recibe/consulta/encola; toda tarea pesada corre en un **worker independiente gestionado por Supervisor**. Cola = colección `data_layer_jobs`. Diseñado para multi-worker sin cambiar el contrato. Decisiones D1–D5 (Master único origen de embeddings, Company Semantic Profile, versionado de embeddings, orden de desarrollo, Embedding Engine como infra compartida) registradas en `/app/memory/DATALAYER_3M_ARCHITECTURE.md`.
- **JobRunner 100% genérico** (`services/jobs/`): `queue.py` (cola Mongo: enqueue, **claim atómico** vía `find_one_and_update` → multi-worker safe, heartbeat, complete/fail con **requeue hasta max_attempts**, cancel, **recover_stale**), `registry.py` (registro `job_type → handler`), `context.py` (`JobContext`: params, checkpoint, `heartbeat`, `should_cancel`), `runner.py` (`process_one` unit-testable + `run_forever` con recovery periódica), `worker.py` (entrypoint Supervisor). El runner **no conoce nada de ingestión**.
- **Primer handler = `ingest_iberinform`** (`services/jobs/handlers/ingest_handler.py`): envuelve la ingestión P0.7 con **checkpoint por fichero** → reanuda exactamente donde paró (salta ficheros completados). Refactor: `iberinform_ingest` expone `list_ingestable` + `ingest_file` (single source of truth).
- **Worker Supervisor**: `/etc/supervisor/conf.d/data_layer_worker.conf` (`python -m services.jobs.worker`, autorestart). Estados: queued/running/completed/failed/cancelled. Heartbeat + stale-recovery (re-encola jobs huérfanos) + cancelación entre lotes. Config vía env: `JOB_HEARTBEAT_STALE_SECONDS=120`, `JOB_MAX_ATTEMPTS=3`.
- **Endpoints admin (auth JWT, NO contrato arroba)** en `routes/data_layer.py`: `POST /jobs` (encola → job_id), `GET /jobs` (recientes), `GET /jobs/{id}` (estado+progreso+checkpoint), `POST /jobs/{id}/cancel`. **Ningún rebuild largo dentro del request HTTP** — el endpoint solo encola.
- **Validación e2e real (separate-process)**: API encola `ingest_iberinform` → el worker separado (pid distinto) lo procesa (8/8 ficheros) y completa en ~2s; `norm_company` poblado.
- **Tests**: `tests/smoke/test_jobs.py` (10: enqueue, claim atómico, complete+checkpoint, cancelación, stale-recovery, requeue→fail, ingest vía runner, resume saltando ficheros, auth del endpoint, crear/consultar/cancelar vía API). Worker pausado en el módulo para determinismo. Loop de tests compartido (`smoke_loop.py`) para evitar conflicto de event-loops del cliente motor. Suite total: **146/146 verde** en 65s.
- ⚠️ Próximo (orden aprobado): **Master Layer + Entity Resolution + entity_xref** (como nuevos handlers de job sobre esta misma infraestructura) → luego Value sobre financiero real, KG sobre ownership real, Embedding Engine sobre Master, Atlas Vector Search, Universal Search.


### 2026-06-25 — P0.7 + P0.1 Ingestión industrial Iberinform → Normalized Layer (validado con muestra real)
- **Fuente de verdad**: muestra real `20260519_Data_ES_Muestra` (8 CSVs). Diseño completo en `/app/memory/DATALAYER_3M_ARCHITECTURE.md`. Decisiones aprobadas: landing CSV en object storage (NO raw fila-a-fila en Mongo), pivot directo a Normalized, ANN futuro = Atlas Vector Search, orden P0.7+P0.1 primero.
- **Módulo nuevo `services/data_layer/ingestion/`** (sin tocar contratos públicos, sin endpoints HTTP aún):
  - `csv_stream.py`: lectura streaming O(1) RAM, autodetección encoding UTF-8/latin-1, sep `;`, checksum sha256.
  - `account_map.py`: catálogo contable Valu8 verificado (40100=NET SALES→revenue, 10000→total_assets, 20000→equity, 49100→operating_income, 40800→depreciation, 49500→net_income; EBITDA=operating+|depreciation|, fallback REN007×revenue).
  - `bulk.py`: `BulkUpserter` con `bulk_write(ordered=False)` en lotes de 2.000 `UpdateOne(upsert=True)` por clave natural → idempotente, RAM O(batch).
  - `iberinform_ingest.py`: orquestador. **Pivot sort-merge EAV→doc por (cif_normalized, year, basis)** agrupando por empresa contigua.
- **Normalized Layer (colecciones nuevas)**: `norm_company` (PK cif_normalized), `norm_financials` (PK cif+year+basis, con `accounts{}` completo + métricas derivadas), `norm_ownership` (aristas PK src+counterparty+type+year, con %), `norm_officers` (PK cif+person+role+fecha). + `raw_ingestion_manifest` (source_file_id, checksum, bytes, rows, ingestion_job_id, lineage raw→normalized). Índices únicos creados antes de la carga.
- **Validación end-to-end (muestra, 1,18s)**: 1.000 empresas; **94.454 filas financieras → 1.006 docs empresa-año (pivot OK)**; 374/1.000 con financieros (join por CIF exacto); grafo de propiedad real materializado (shareholder/parent/ultimate_parent/investee con %); idempotencia verificada (re-ingesta = 0 duplicados); métricas coherentes (Servier: revenue €137M, EBITDA €15,8M margen 11,5%).
- **CIF/NIF como clave de join universal**; contrapartes extranjeras sin CIF → `counterparty_key=name_key`. `objeto_social` (2.000 chars) disponible para embeddings futuros.
- **Tests**: `tests/smoke/test_ingestion_normalized.py` (5: e2e+pivot, métricas+join, idempotencia, tipos de ownership, manifest+checksum+lineage). Suite total: **136/136 verde** en 78s. Fixture en `tests/fixtures/iberinform_sample` (tests hacen skip si ausente).
- ⚠️ Próximo: **P0.2 jobs reanudables** envolverá esta ingestión en workers en background con checkpoint (`data_layer_jobs`), sin ejecutar rebuilds largos dentro de requests HTTP. La derivación Normalized→Master (entity resolution cross-source) y la conexión a engines llegan después de P0.2.


### 2026-06-24 — P2 Robustecimiento de Analyze (caché + auth de servicio + rate limit + métricas)
- **Principio rector adoptado**: _"nunca introducir una capa de inteligencia cuya calidad aparente supere la calidad real de los datos que la soportan"_.
- **P1 (BME→Value) APARCADO** por decisión de usuario tras auditoría: BME tiene market cap pero **0 EBITDA/revenue**, NIF de BME sin solape con financieros, `transactions_normalized`/`category_valuations` vacías → no hay fuente de múltiplos reales hoy. No se fabrica. Ver `/app/memory/ENGINE_MATURITY_AUDIT.md`.
- **Seguridad de `enrich_company`** (antes público): ahora exige **service API key** `X-API-Key` (`services/service_auth.py`, reutiliza colección `api_keys`, hash sha256). Key de arroba en `ARROBA_SERVICE_API_KEY` (.env), sembrada idempotente al startup. **401** sin/mal key.
- **Rate limiting** por key: token-bucket en proceso (`services/rate_limit.py`), `ANALYZE_RATE_LIMIT_PER_MIN=600` (10/s). Rate-limit aplicado DESPUÉS de auth (keys inválidas no consumen cuota). **429** con `Retry-After` al exceder. (Per-proceso; migrar a Redis si se escala a múltiples workers).
- **Caché de Analyze** (`services/analyze_cache.py`): clave = sha256(`master_company_id | include_narrative | data_version`), `data_version` derivado de timestamps mutables del master + `ANALYZE_VERSION`. Persistida en `analyze_cache` con índice TTL Mongo (`ANALYZE_CACHE_TTL_SECONDS=86400`). Elimina llamadas repetidas a Claude (hit ≈ 4ms vs 4–16s). Sobrevive a reinicios.
- **Métricas** en `analyze_metrics` (1 doc/llamada, sin nuevas APIs públicas): `latency_ms`, `cache_hit`, `tokens` (heurística ~4 chars/token), `estimated_cost_usd` (`ANALYZE_CLAUDE_COST_PER_1K_TOKENS`), `claude_error`, `retries`. Narrativa con **1 reintento** ante fallo de Claude.
- **Contrato de `enrich_company` INMUTABLE** (solo se añadió la cabecera de auth; el body de salida no cambia).
- **Bug corregido**: comparación de TTL naive-vs-aware (Mongo devuelve datetime naive) → 500 en cache hit; resuelto normalizando a UTC.
- **Tests**: `tests/smoke/test_analyze_hardening.py` (5: 401 sin key, 401 key inválida, 200 con key, caché idéntica + métrica hit, token-bucket unitario 429). Tests existentes que llaman a enrich actualizados con `X-API-Key`. Suite total: **131/131 verde** en 65s.
- ⚠️ Tras redeploy: regenerar `ARROBA_SERVICE_API_KEY` en producción y entregarla a arroba por canal seguro.


### 2026-06-24 — P3 Knowledge Graph (cierre · capa relacional)
- **Colección `company_relationships`** independiente del master (`services/knowledge_graph.py`). Materializa SOLO `similar_to` (vecinos semánticos globales, umbral 0.35, top-8) y `same_cluster` (co-miembros del cluster P2.2 rankeados por similitud, confidence por proximidad de signal_score). Tipos de ownership (`shareholder_of`, `subsidiary_of`, `same_group`, `competitor_of`, etc.) reservados en el modelo pero NO poblados — entrarán con fuentes reales + Ownership Engine.
- **Reutiliza infra existente** (sin motores nuevos): embeddings/clusters (P2.2) + signal_score (P3). `rebuild_graph()` idempotente y no-destructivo (índice único source+target+type), inserción en batches.
- **Endpoint** `POST /api/v1/data-layer/rebuild-graph` (auth) → `{status, companies, relationships, by_type, version}`. Ejecutado en preview: 5.306 empresas, 84.846 relaciones (42.398 similar_to + 42.448 same_cluster), ~2,9s.
- **Cableado en skills (contratos públicos respetados)**:
  - **Analyze** (`skills_analyze.py`): nuevo bloque ADITIVO `relationships` alimentado por `relationships_for()` (top-10). `ownership` se mantiene como estructura preparada vacía.
  - **Recommend** (`skills_recommend.py`): boost interno de afinidad vía `neighbor_scores()` (`+0.10·g` sobre similar_to/same_cluster). Request/Response INMUTABLES. Fallback automático (dict vacío → no-op) cuando el grafo no está construido.
  - **Search** (`skills_search.py`): soporte interno de `filters.cluster_id` (filtra `classification.cluster_id` en query de candidatos + `_passes_filters`). Contrato de salida intacto, NO expuesto en UI todavía.
- **Tests**: `tests/smoke/test_knowledge_graph.py` (6: auth, rebuild idempotente + by_type ⊆ {similar_to,same_cluster}, shape de relación + sin autorrelaciones, bloque relationships en Analyze + ownership reservado, contrato Recommend inmutable con grafo, filtro cluster_id interno en Search). Actualizado `test_enrich_company_skill.py` (TOP_KEYS += relationships). Suite total: **126/126 verde** en 63s.
- ⚠️ **Orden de reconstrucción tras redeploy**: `rebuild-master` → `rebuild-embeddings` → `rebuild-signals` → **`rebuild-graph`** (el grafo es siempre la última capa).
- **Próximo**: P4 Memory & Learning, P5 Matching Engine, P6 Strategy Engine — arquitectura ya preparada, no requiere rehacerla.


### 2026-06-17 — Refactor dinámico de `/sync-status` (ZERO HARDCODES)
- **Backend**: `routes/intelligence_status.py` reescrito. El array legacy hardcodeado de 8 fuentes (`_get_source_breakdown`) fue eliminado. La lista de fuentes ahora proviene **exclusivamente** de `engine_info.get_all_sources()` (16 fuentes del perfil arroba). Por fuente se computan dinámicamente: `records`, `signals_count`, `last_run`, `last_status`, `duration_ms`, `inserted_count`, `updated_count`, `error_count`, `frequency`, `phase`, `supports_manual_ingestion`. Retrocompat: `modules`, `schedule`, `data-updated`, `datacomex_health`, `last_update`, `status`, `signals`.
- **META por módulo**: cada `services/intelligence_engine/sources/*.py` declara su propio `META` (display_name, collection, frequency, signal_source, audit_action, phase, supports_manual_ingestion, ingest_runner). NO hay registry central. Helpers nuevos: `engine_info.get_source_meta()` / `get_all_source_meta()`.
- **Ingesta manual dinámica**: `POST /api/v1/intelligence/sources/ingest/{source}` resuelve el runner desde `META['ingest_runner']`, acepta nombre de fuente del engine + alias legacy (ayudas/empleo/territoriales) + `all`, y audita cada corrida en `er_audit_logs` (`_run_and_audit` con `performed_by`). last_run refleja disparos manuales y del scheduler.
- **Frontend**: `DashboardPage.js` (tabla con columnas Origen, Señales, Última ejecución, Duración, Insertados, Errores) y `HealthPage.js` (tarjeta "Fuentes Públicas": 16 cards dinámicas + botón "Ejecutar ahora" solo cuando `supports_manual_ingestion`). UI 100% derivada del backend, sin arrays manuales.
- **Test**: `tests/smoke/test_sync_status_dynamic.py` (6 tests) — asegura ≥16 fuentes, igualdad exacta con `get_all_sources()`, ausencia de keys legacy, self-describing rows y flag manual desde META. Falla si se reintroducen hardcodes. Suite total: **33/33 verde**.
- **Sistema autoextensible**: añadir una fuente = crear módulo + META + entrada en perfil. No requiere tocar sync-status, Dashboard, Health, tests ni arrays.


### 2026-06-17 — Sidebar DATA dinámico (ZERO HARDCODES)
- **META extendido**: cada `sources/*.py` añade `show_in_sidebar`, `sidebar_group`, `sidebar_route`, `sidebar_dot`. `engine_info.get_source_meta()` los expone con defaults.
- **Backend**: nuevo `GET /api/v1/intelligence/sources/sidebar` — itera `get_all_sources()` (orden engine = orden sidebar), filtra `show_in_sidebar=True`, agrupa por `sidebar_group`. 15 fuentes (OEPM legacy stub oculto). Sin arrays.
- **Frontend**: `Layout.js` elimina el array estático de DATA; la sección se construye en runtime desde el endpoint. Nueva página genérica `DataSourcePage` (`/data/source/:source`) que renderiza cualquier fuente (stats + historial de ingestas + botón "Ejecutar ahora" si `supports_manual_ingestion`) — destino por defecto para fuentes sin página dedicada.
- **Test**: `tests/smoke/test_sidebar_dynamic.py` (3 tests) — catálogo == engine, items self-describing, Layout.js sin hardcodes. Suite total: **36/36 verde**.
- Iberinform NO tocado (solo metadata declarativa de sidebar; lógica de datos intacta).
- Autoextensible end-to-end: nueva fuente = módulo + META + perfil → aparece automáticamente en Dashboard, Health y Sidebar.


### 2026-06-17 — Data Explorer genérico (sample dinámico, ZERO HARDCODES)
- **META**: añadido `supports_sample` a cada fuente (default `bool(collection)`; oepm=False). Expuesto en `get_source_meta` y en filas de `sync-status`.
- **Backend**: nuevo `GET /api/v1/intelligence/sources/{source}/sample?page=&page_size=` — colección resuelta desde META (sin switch/arrays), paginado real (excluye `_id`), gated por `supports_sample`. Respuesta: `total_records`, `current_page`, `page_size`, `total_pages`, `items`. 400 si no soporta sample, 404 si fuente desconocida.
- **Frontend**: `DataSourcePage` evolucionada a explorador genérico único — resumen (estado/registros/señales/última ejec./duración/errores/frecuencia) + historial filtrado por colección (`er_audit_logs`) + botón "Ejecutar ahora" (si `supports_manual_ingestion`) + tabla paginada de datos reales con columnas derivadas dinámicamente del documento. Una sola página sirve a las 15 fuentes.
- **Test**: `tests/smoke/test_source_sample.py` (5 tests). Suite total: **41/41 verde**. Verificado en UI: tabla de 25 filas reales (territorial) + paginación operativa.
- Autoextensible: nueva fuente con colección → explorable automáticamente, sin tocar endpoint/página/tests.


### 2026-06-17 — Data query / inspección dinámica (ZERO HARDCODES)
- **META**: añadido `queryable` (default `bool(collection)`; oepm=False). Expuesto en `get_source_meta` y filas de `sync-status`.
- **Backend**: nuevo `GET /api/v1/intelligence/sources/{source}/query` — colección desde META, gated por `queryable`. Params: `page`, `page_size`, `sort_by`, `sort_order`, `field`, `value`. Filtro dinámico: valores numéricos por igualdad, strings por substring case-insensitive (regex). `fields` se derivan automáticamente de documentos reales (sin hardcode). 400 si no queryable, 404 si fuente desconocida.
- **Frontend**: `DataSourcePage` ahora consume el endpoint `query`. Añadido buscador (dropdown de Campo autogenerado desde `fields` + input Valor + botón Buscar + limpiar), banner de filtro activo, tabla con columnas dinámicas y paginación. Historial filtrado por colección.
- **Test**: `tests/smoke/test_source_query.py` (7 tests). Suite total: **48/48 verde**. Verificado en UI: province=Barcelona → 2.158 filtrados; year=2023 + sort average_income desc OK.
- Autoextensible: nueva fuente con colección → visible/explorable/filtrable/consultable sin tocar componentes.


### 2026-06-17 — DATA 100% genérico + acciones operativas declarativas (1a + 2c)
- **Routing unificado**: eliminado `sidebar_route` del META; el endpoint sidebar fuerza SIEMPRE `/data/source/{source}`. Las 15 fuentes del bloque DATA (incluida Economic Intelligence) se sirven desde la única `DataSourcePage`. Vistas analíticas de INTELLIGENCE ENGINE conservadas (Economic Intel, Macro, Sector, Geo, Sector×Geo).
- **Acciones operativas migradas (2c)**: nuevo campo declarativo `META['actions']` (id, label, endpoint, kind=button|upload, params). Expuesto en `get_source_meta` y `sync-status`. `DataSourcePage` renderiza una tarjeta "Acciones operativas" genérica (botones POST con query params + upload multipart). Migradas: identity (ingest-scraper/bulk-verify/bulk-publish), bme (sync/enrich), economic_intel (rebuild), borme (reprocess-failures), procurement (sync-placsp), cnmv (sync/match), datacomex (sync/rebuild-metrics/rebuild-signals/upload-csv).
- **Test**: `tests/smoke/test_source_actions.py` (4 tests). Suite total: **52/52 verde**. Verificado en UI: DataComex muestra 4 acciones (3 botones + upload); Economic Intelligence abre el explorador genérico.
- **Pendiente (retirada progresiva de legacy)**: páginas con ops aún no migradas siguen vivas — borme fetch date-range, master per-registro, iberinform upload (X-Provider-Key), bme params de mercado. Retirar `*Page.js` legacy cuando su funcionalidad esté 100% cubierta por la genérica.
- **Nota datos**: `datacomex` (META.collection=`datacomex_records`) está vacío; los datos reales viven en `datacomex_raw_data`. Revisar mapeo del módulo datacomex en una iteración futura.


### 2026-06-17 — DataComex fix + Platform Console FEATURE COMPLETE
- **DataComex corregido**: `META['collection']` cambiado de `datacomex_records` (vacío) a `datacomex_raw_data` (1169 reales). Data Explorer, query y sync-status muestran datos correctos (records=1169). Verificado UI + curl. BME: añadido `params markets=growth,scaleup` a su acción sync (capacidad preservada).
- **PLATFORM CONSOLE = FEATURE COMPLETE**. Arquitectura final lograda: Dashboard dinámico, Sidebar dinámico, Health dinámico, Data Explorer genérico, query dinámica, acciones operativas declarativas, META por módulo, cero hardcodes, cero arrays manuales, autoextensible. Nueva fuente = módulo + META + perfil. Suite smoke: **52/52 verde**.
- **NO se añadirá** (decisión de producto, bajo ROI): export CSV, AND/OR, multi-filtros, auditorías avanzadas, badges por acción, features tipo Mongo Compass.
- **Retirada legacy DIFERIDA** (gated por "toda la funcionalidad cubierta", aún no alcanzada). Páginas legacy NO eliminadas para no perder capacidades; ya están desenlazadas del sidebar (orphan por ruta). Pendiente de migrar antes de borrar: BORME por rango de fechas (date pickers), upload Iberinform (X-Provider-Key header), acciones por registro de Master, dashboards analíticos específicos. Estas migraciones implican complejidad de UI que el usuario pidió evitar → evaluar coste/beneficio antes de proceder.
- **Nota pre-existente**: `datacomex.py::enrich()` aún lee `datacomex_records` (vacío) para enriquecimiento de empresas; separado del Data Explorer. Revisar en iteración futura si se requiere enriquecimiento datacomex.


### 2026-06-17 — Capa de presentación humana del Data Explorer (declarativa, ZERO HARDCODES)
- **META**: añadidos campos opcionales `display_fields` (whitelist ordenada), `hidden_fields` (blacklist) y `field_labels` (etiquetas humanas ES). Expuestos en `get_source_meta` y `sync-status`.
- **Frontend** (`DataSourcePage`): resolución de columnas = display_fields (orden) > hidden_fields/ocultación-por-defecto heurística (oculta `_id`, `*_id`, `*_url`, `*_at`, uuid, claves de auditoría/auxiliares). Etiquetas: `field_labels` o humanización automática snake_case→Title. `fmtCell` mejorado: decodifica entidades HTML (`&#211;`→Ó), une arrays, vacíos→"—", booleanos Sí/No. La capa de DATOS sigue 100% dinámica; el dropdown de búsqueda mantiene TODOS los campos (full-power).
- **display_fields curados** para 10 fuentes con datos: cnmv, territorial, employment, procurement, bme, economic_intel, identity, borme, web, datacomex. Fuentes sin display_fields → auto + ocultación por defecto.
- **Test**: `tests/smoke/test_source_presentation.py` (4 tests). Suite total: **56/56 verde**. Verificado UI: CNMV muestra Nombre/Tipo de entidad/NIF/Gestora/CNAE/Estado/Fecha de registro (sin UUIDs ni URLs).


### 2026-06-17 — Normalización HTML-encoded en ingesta + backfill (calidad de datos, P-Alta)
- **Util nuevo** `services/text_normalize.py`: `normalize_strings(obj)` decodifica entidades HTML (`&#211;`→Ó, `&amp;`→&, `&aacute;`→á) recursivamente en dicts/listas/strings. No-op para texto limpio (idempotente, barato).
- **Ingesta normalizada en origen** (no en presentación): aplicado antes de persistir en `cnmv_connector._store_entities`, `placsp_connector.sync_placsp` y `procurement_connector` (insert). La BD guarda siempre texto canónico.
- **Backfill** `scripts/backfill_html_unescape.py`: barrido idempotente de 11 colecciones de fuentes, actualiza solo docs que cambian. Ejecutado: **405 documentos limpiados** (128 `cnmv_entities` + 277 `public_procurement_contracts`); resto ya limpio. Verificado: 0 entidades restantes.
- **Frontend**: se mantiene `decodeEntities` en `fmtCell` como FALLBACK temporal (eliminar cuando se confirme que toda futura reingesta queda limpia).
- **Beneficio**: búsquedas/filtros/matching/exportaciones/embeddings/Universal Search/RAG operan sobre texto limpio. Habilita con calidad las fases P1 (Universal Search) y P2 (Company Advisor+RAG).
- **Test**: `tests/smoke/test_text_normalize.py` (4 tests: decode, recursividad, no-op, BD sin entidades). Suite total: **60/60 verde**.
- **Sin impacto arquitectónico**: Platform Console sigue Feature Complete.

### 2026-06-18 — Semantic Mapping Engine v2 (Taxonomy Governance Engine) — Fase A
- **Cambio de paradigma**: eliminada la aprobación humana. `taxonomy_mappings` migra de `auto_approved/pending_review/low_confidence/rejected` → `active`/`inactive`. Nuevos campos: `confidence_score` (calidad intrínseca), `weight` (cuota proporcional, los pesos de un código suman 1.0), `origin` (seed/manual/llm). Migración idempotente en startup (`ensure_taxonomy_v2`): seed-si-vacío + migrate legacy + recompute weights. 143 mappings migrados, 0 campos legacy restantes.
- **Multi-mapping ponderado**: un código mapea a varios CNAEs con peso normalizado (ej. TARIC 27 → CNAE 19 @ 70% + CNAE 06 @ 30%). `_normalize_weights` reparte `confidence_score` para sumar 1.0.
- **`resolve()` nunca devuelve None**: códigos sin mapping → `{"orphan": true, "mappings": []}`. Endpoint público `/resolve/{tax}/{code}` para Arroba/Valuo devuelve mappings con cnae/confidence_score/weight/origin.
- **Signals Weighted Engine**: `economic_intelligence._aggregate_datacomex` reparte el valor económico por `weight` (antes por `confidence`, que perdía ~10% en mappings 0.9). Verificado lossless: 0 códigos con pérdida por fila. Subido `to_list(500)→5000` (585 trade_metrics ya no se truncan).
- **4 endpoints de calidad** (`routes/taxonomy_intelligence.py`, contract v2.0): `/health` (verdict healthy/degraded/critical + métricas), `/coverage` (universo/mapeados/integridad por taxonomía), `/orphans` (huérfanos, data-driven con flag de pérdida real de señal), `/inconsistencies` (weight_breaches + weak_mappings + conflicts/fragmentación). Conservados `/all`, `/resolve`, `/seed`, nuevo `/recompute-weights`.
- **UI Quality Console** (`TaxonomyIntelligencePage.js`): refactor completo a 5 tabs (Salud, Cobertura, Huérfanos, Mappings débiles, Conflictos) + badge de verdict + botones Re-normalizar pesos / Re-seed. Eliminada toda la UI de aprobar/rechazar.
- **Estado verificado**: verdict `healthy`, TARIC 99% cobertura (solo "00" confidencial sin mapear, sin datos), CPV 100%, integridad de pesos 100%, 0 pérdida de datos, 6 mappings débiles (confidence<0.5, solo observacional), 0 conflictos.
- **Tests**: `tests/smoke/test_taxonomy_v2.py` (7 tests). Suite total: **70/70 verde** en 4.5s.

### 2026-06-18 — Semantic Mapping Engine v2 — Fase B (LLM Assisted Mapping)
- **Bucle de gobernanza automática cerrado** sin convertir el LLM en fuente de verdad: `Orphan/Weak → GPT-5.2 → taxonomy_suggestions → MetaScore → taxonomy_mappings`.
- **Integración GPT-5.2** (`services/taxonomy_llm.py`) vía Emergent LLM Key (emergentintegrations, `send_message` JSON estructurado). Recibe taxonomía+código+etiqueta+catálogo CNAE, devuelve hasta 3 CNAEs con confidence_score.
- **Nueva colección `taxonomy_suggestions`**: source_*, suggested_cnae/label, confidence_score, origin=llm, llm_model, target_type (orphan/weak), los 5 sub-scores, metascore, status (candidate/accepted/rejected). Índices en server.py.
- **MetaScore** (pesos exactos): 40% semantic_similarity + 25% frequency_score + 15% historical_score + 10% sector_consistency_score + 10% gpt_confidence. `semantic_similarity` es un proxy léxico SIN embeddings (token + stem Jaccard + sequence ratio), listo para crecer a embeddings en Fase C.
- **Activación automática**: metascore≥0.90 → crea mapping `active` origin=llm + renormaliza pesos; 0.70–0.90 → candidate; <0.70 → rejected (descartado, auditable).
- **5 endpoints nuevos**: `POST /suggest` (scope orphans/weak/all), `GET /suggestions`, `/suggestions/weak`, `/suggestions/orphans`, `/suggestions/stats`. `/health` ahora incluye `llm_candidates`, `auto_accepted`, `pending_candidates`, `average_metascore`.
- **Quality Console**: 2 tabs nuevas (Sugerencias IA = candidatos 0.70–0.90; Auto-learn = mappings auto-activados) + botón "Generar sugerencias IA" + señales LLM en la tab Salud.
- **Tests**: `tests/smoke/test_taxonomy_llm.py` (10 tests: MetaScore math, bandas de umbral, similitud léxica, wiring de endpoints, invariante de no-pérdida de señal, auto-activación→mapping llm). Auto-activación verificada también con valores forzados. Suite total: **80/80 verde** en 5.8s.
- **Nota de calidad**: con proxy léxico, los MetaScore de TARIC↔CNAE quedan bajos (vocabulario producto vs actividad) → auto-accept conservador por diseño (seguro). Embeddings (Fase C) desbloquearían candidatos/auto-accepts reales.

### 2026-06-24 — REQ-002 Platform Stats (endpoint público para arroba.com)
- **`GET /api/v1/platform_stats`** — público (sin auth), sin PII, cacheable. Header **`X-Source: real`** (sustituye el mock `X-Source: mock`). `Cache-Control: public, max-age=3600` en origen + caché en memoria (TTL 1h).
- **Métricas reales** (`services/platform_stats.py`): `companies_analyzed`=companies_master · `active_opportunities`=licitaciones PLACSP + ayudas/grants · `market_movements`=borme_events + corporate_events · `signals_detected`=señales (economic/cnmv/bme/datacomex) + economic_metrics · `confidence`=cobertura real de fuentes con datos · `lineage.source="normalized"` · `valid_until`=now+TTL (formato Z).
- **Contrato idéntico al mock** → arroba sustituye `PlatformStatsMock` por `PlatformStatsReal` solo a nivel de adapter (Home/MetricsBlock/componentes/TS intactos). Campos: companies_analyzed, active_opportunities, market_movements, signals_detected, **confidence=0.8 (fijo, aprobado)**, lineage.source, **generated_at** (nuevo), valid_until. ⚠️ URL pública real: `{BACKEND_URL}/api/v1/platform_stats` (el ingress solo enruta `/api/*`; el adapter de arroba debe incluir `/api`). El `no-store` que añade el edge del preview no aplica en producción. ETag NO incluido (decisión de producto).
- **Tests**: `tests/smoke/test_platform_stats.py` (5: público sin auth, X-Source real, tipos del contrato, valores reales, cacheable en origen). Suite total: **85/85 verde**.

### 2026-06-24 — REQ-003 Search Engine skill (P0)
- **`POST /api/v1/skills/search`** — público (sin auth, como platform_stats), búsqueda léxica de compañías sobre `companies_master`. Boundary First: Agency Tool produce inteligencia, arroba renderiza.
- **Contrato estable** (swap transparente del mock de arroba, sin tocar Skills/Workspaces/componentes): entrada `{query, filters{cnae,category,tags,has_domain}, context{} (passthrough), pagination{page,page_size}}` → salida `{workspace:{blocks:[{type:"search_results", props:{query, results:[{master_company_id,name,sector,cif,score}]}}]}}`. Un único block `search_results`; NO se inventan summary/pagination/company_card (eso pertenece al renderer de arroba).
- **Motor** (`services/skills_search.py`): candidatos vía regex sobre legal_name/normalized_name/commercial_names/aliases/domain/category/tags/description, re-ranking en Python (exact>prefix>substring>token-overlap, boosts por dominio/desc/tags, blend con confidence_score), filtros category/tags/cnae + has_domain, paginación page/page_size. Embeddings/semantic → Fase C.
- **SLA**: objetivo p95<400ms. Medido **p95≈5ms** en origen (5.296 docs). Nota escala: para 3,3M se migrará a Atlas Search/text index en Fase C.
- **Tests**: `tests/smoke/test_skills_search.py` (8: contrato, shape de item, ranking desc, paginación, query vacía browse, body mínimo, SLA). Suite total: **93/93 verde**.
- ⚠️ URL pública real: `{BACKEND_URL}/api/v1/skills/search` (ingress enruta solo `/api/*`).

### 2026-06-24 — REQ-004 Valuation Engine skill (P1)
- **`POST /api/v1/skills/value`** — público. Entrada `{master_company_id, context{}}` → salida flat `{master_company_id, company_name, valuation_range, comparables, explanation, confidence, lineage}`. 404 si el id no existe. Agency Tool calcula, arroba renderiza.
- **Motor** (`services/skills_valuation.py`): financieros reales desde `iberinform_financials` (latest year por CIF: ebitda/revenue/equity); múltiplos de **referencia sectorial por sección CNAE** (EV/EBITDA, EV/Ventas) — lineage.source=`inferred`; método en cascada ev_ebitda → ev_revenue → book_value → insufficient_data; comparables reales del mismo sector (con financieros); explicación narrativa ES; confidence por disponibilidad de datos + confidence_score.
- **Limitación de datos conocida**: las empresas con financieros (Iberinform sintético) no traen categoría y las de agencia no traen CIF en Iberinform → `comparables` suele salir vacío hasta el entity resolution del Data Layer (P2). El motor lo maneja con gracia.
- **Tests**: `tests/smoke/test_skills_value.py` (5: 404, shape del contrato, rango ordenado low≤base≤high cuando computable, lineage inferred). Suite total: **97/97 verde**.

### 2026-06-24 — REQ-005 Recommendation Engine skill (P1)
- **`POST /api/v1/skills/recommend`** — público. Salida flat `{recommendations:[{master_company_id,name,sector,score,reason,type}], confidence, lineage{source:"normalized"}}`. 404 si seed no existe.
- **Dos modos** (`services/skills_recommend.py`): si llega `master_company_id` → **similar** (peers del mismo sector/categoría, con proximidad de tamaño empleados/ingresos vía iberinform_financials + señales disponibles; fallback por tamaño si no hay categoría); si llega `query`/`filters` → **tesis** (ranking léxico reutilizando el motor de Search). `type="similar"` (campo preparado para target/opportunity/consolidator/acquirer sin romper contrato).
- **Similitud estructural** sin embeddings (Fase C evolucionará internamente con embeddings/reranker/graph proximity manteniendo el contrato inmutable). `reason` narrativo ES ("Mismo sector (X), tamaño similar, con señales disponibles").
- **Tests**: `tests/smoke/test_skills_recommend.py` (5: contrato tesis + ranking desc, contrato similar + reason, 404, lineage normalized). Suite total: **102/102 verde**.

### 2026-06-24 — P2.1 Data Layer + Entity Resolution (canonical master record)
- **Diagnóstico**: la "fragmentación" era de **esquema canónico**, no de entity resolution (0 duplicados por CIF). Los datos ya existían dispersos (iberinform_companies con CNAE/sector, iberinform_financials por CIF) pero las skills leían campos inexistentes.
- **Master Record Builder idempotente** (`services/data_layer/`): `normalize.py` (CIF/name_key/aliases/sección CNAE), `accessors.py` (lectura unificada con backward-compat), `master_builder.py` (build_one + rebuild + entity resolution).
- **Esquema unificado in-place en `companies_master`**: `classification{cnae_code,division,section,label,sector,category}`, `financials{latest,history[],years[]}` (join iberinform_financials por CIF), `sources{iberinform,financials}` con lineage, `aliases[]`, `cif_normalized`, `name_key`, `confidence_score` recalculado, `lineage{identity,classification,financials}`. Backward-compat: `sector`/`category_name`/`cnae` top-level. **NO** sobrescribe el bloque `sources.web` (description/tags scrapeados).
- **Entity resolution** por `cif_normalized` y `name_key+provincia` (no-destructivo, marca `merge_status='merged'`+`merged_into`); no-op hoy (0 dups), listo para 3,3M.
- **Endpoint**: `POST /api/v1/data-layer/rebuild-master` (autenticado, idempotente). Ejecutado: **5.301 enriquecidos, 5.000 con clasificación + financieros, 0 merges, ~7s**.
- **Skills migradas a accessors** (contratos INMUTABLES, solo cambia de qué campo leen): Search/Value/Recommend leen `classification.sector`/`financials.latest`. **Desbloqueo verificado**: Value ahora resuelve sección + múltiplos sectoriales correctos + 5 comparables reales con EBITDA; Recommend con proximidad de tamaño real ("~30 empl."); Search con sector poblado.
- **Incidente corregido**: la 1ª pasada del rebuild pisó `sources.web` (description/tags) de 365 empresas de agencia → restaurado desde `agency_results` (backref) vía `build_web_block`, y `_build_sources` corregido para no clobberar web.
- **Tests**: `tests/smoke/test_data_layer.py` (3: auth, idempotencia+enriquecimiento, unlock de comparables). Suite total: **105/105 verde**.
- ⚠️ Tras deploy a producción, ejecutar `POST /api/v1/data-layer/rebuild-master` una vez para enriquecer el master de producción (no se auto-ejecuta en startup).

### 2026-06-24 — P2.3 REQ-001 Analyze Skill (`POST /api/v1/enrich_company`)
- **Nuevo endpoint público** `POST /api/v1/enrich_company` (no existía; es el contrato de la Analyze Skill). Entrada `{master_company_id, context}` → contrato flat enriquecido. Aprovecha el master unificado de P2.1 (evolución 100% interna, sin tocar Search/Value/Recommend ni crear motores nuevos).
- **Bloques** (`services/skills_analyze.py`): `financial_summary` (financials.latest), `growth` (revenue/ebitda desde financials.history), `ratios` (ebitda_margin, revenue/ebitda per_employee, debt_ratio), `peers` (REUTILIZA `_comparables` de Value + `_size_proximity` de Recommend → {master_company_id, legal_name, sector, score}), `ownership` (estructura preparada, vacía), `signals` ([] para futuro Signal Engine), `narrative` (Claude `claude-sonnet-4-6` vía Emergent LLM Key → summary/key_points/risks/opportunities en ES), `confidence` desdoblado {identity,classification,financials,overall}, `lineage` desdoblado {identity,classification,financials,narrative}.
- **Control de coste**: `context.include_narrative=false` salta la llamada a Claude (narrativa vacía + lineage.narrative="none").
- **Verificado**: empresa Iberinform devuelve growth (5,4%/13,3%), ratios completos, 5 peers reales del mismo sector con score, narrativa Claude rica. 404 si no existe.
- **Tests**: `tests/smoke/test_enrich_company_skill.py` (5: 404, contrato, financieros+growth+ratios+peers, narrativa opcional, narrativa Claude en vivo). Suite total: **110/110 verde**.
- ⚠️ Público y consume Claude por llamada (usa `include_narrative=false` para vistas sin narrativa). URL real `{BACKEND_URL}/api/v1/enrich_company`.

### 2026-06-24 — P2.2 Taxonomía Fase C (embeddings / semantic similarity / clustering)
- **Embeddings locales LSA** (`services/taxonomy_embeddings.py`) — la Emergent LLM Key NO soporta embeddings y los principios piden "sin vector DB": TF-IDF (word 1-2gram) → TruncatedSVD 128-dim → Normalizer. Offline, gratis, determinista, escalable, **sustituible por embeddings neuronales sin tocar contratos**.
- **Índice persistente** (`/app/backend/models/company_lsa.joblib` + colección `company_embeddings`): vectores unitarios por empresa, 24 clusters KMeans con auto-tags (términos top por centroide) escritos en `classification.cluster_id/cluster_tags` (base para KG/taxonomía). Construido: 5.304 empresas, 128-dim, ~5,5s.
- **Ranking híbrido transparente** (contratos INMUTABLES): Search une candidatos léxicos + `semantic_top` global y puntúa `0.6·léxico + 0.4·semántico`; Recommend (similar) mezcla `0.7·estructural + 0.3·afinidad semántica`. Fallback automático a léxico/estructural si el índice no existe.
- **Endpoint**: `POST /api/v1/data-layer/rebuild-embeddings` (auth). Warm-up del modelo+vectores en startup para evitar cold-load.
- **Verificado**: "publicidad y marketing" surface agencias de marketing/medios semánticamente relevantes; SLA Search **p95≈16ms** (cold-load 1ª llamada eliminado por warm-up). sklearn/scipy/joblib añadidos a requirements.
- **Tests**: `tests/smoke/test_taxonomy_fase_c.py` (5: auth, build index, relevancia semántica, contrato intacto, recommend con blend). Suite total: **115/115 verde**.
- ⚠️ Tras redeploy ejecutar `rebuild-master` y luego `rebuild-embeddings` en producción.

### 2026-06-24 — P3 Signal Engine
- **Motor de señales** (`services/signal_engine.py`) — evolución interna, contratos públicos INMUTABLES. Deriva señales del master unificado en 5 categorías: **Growth** (revenue/ebitda/employees desde financials.history), **Profitability** (ebitda_margin, revenue/ebitda per_employee), **Size** (posición sectorial por percentil de ingresos dentro del cluster), **Activity** (nº fuentes + riqueza de datos), **Similarity** (cluster_id + cluster_tags de P2.2).
- **Modelo Signal**: signal_id, signal_type (`categoria.metrica`), title, description, severity (positive/negative/neutral/info), score, confidence, created_at, lineage.
- **`signal_score` 0-100** (25% growth + 25% profitability + 20% size + 15% activity + 15% data richness) persistido en `companies_master` junto a `signals[]`.
- **Consumidores**: Analyze rellena `signals[]` (lee persistido, sin recomputar); Recommend mezcla `0.6·estructural + 0.25·semántico + 0.15·signal_similarity` (cluster match + proximidad de signal_score); Search soporta `context.use_signals=true` (boost interno por signal_score, default off). Todo transparente.
- **Endpoint**: `POST /api/v1/data-layer/rebuild-signals` (auth). Ejecutado: 5.305 empresas, todas con señales, ~2,6s.
- **Verificado**: Analyze devuelve 9 señales ricas (growth +5.4%/+13.3%/+15.4%, margen, posición sectorial, fuentes, segmento semántico). Clusters de P2.2 reutilizados como señal + base de filtros internos (cluster_id/cluster_tags) listos para Segmentos/KG/Matching.
- **Tests**: `tests/smoke/test_signal_engine.py` (5). Suite total: **120/120 verde** (1 test de logo externo es flaky por timeout de red, pasa al reejecutar — ajeno a estos cambios).
- ⚠️ Tras redeploy ejecutar en orden: `rebuild-master` → `rebuild-embeddings` → `rebuild-signals`.

## ESTADO PRE-DEPLOY (2026-06-17)
- Suite smoke completa: **60/60 verde** (`cd /app/backend && python -m pytest tests/smoke/`).
- Backend sano (sin errores de import). Frontend hot-reload OK.
- Endpoints clave dinámicos verificados: `/sync-status` (16 fuentes), `/sources/sidebar` (15), `/sources/{src}/sample`, `/sources/{src}/query`, `/sources/{src}/ingest`, acciones operativas declarativas.
- Datos: BD sin entidades HTML tras backfill. DataComex apunta a `datacomex_raw_data` (1169 reales).
- Credenciales de prueba en `/app/memory/test_credentials.md`.


### 2026-06-18 — Auditoría de APIs de fuentes + "Última actualización" universal
- **BUG BDNS (Ayudas) corregido**: endpoint caducado `/api/concesiones` (404) → `/api/concesiones/busqueda` (SNPSAP real). Nuevo mapeo de campos (beneficiary_name, amount_eur, program, organism, admin_region, granted_date) + display_fields/field_labels. Verificado: 1000 concesiones reales 2026 (Navarra, etc.). Historial muestra los ERROR previos ahora OK.
- **BUG PLACSP corregido**: botón sync apuntaba a `/procurement/sync-placsp` (404) → prefijo real `/public-procurement/sync-placsp`.
- **"Última actualización" UNIFORME en todas las fuentes** (`_source_status`): resolución por prioridad audit (er_audit_logs) → sync-log declarativo en META (`sync_log`: cnmv/datacomex/bme/procurement/borme) → timestamp del documento más reciente (`timestamp_field`: economic_intel=last_updated, identity=updated_at; fallback común). Status normalizado a ok/error. Verificado: 12/12 fuentes activas con fecha/hora real; stubs vacíos en None correctamente.
- **Auditoría de conectividad**: INE (employment/territorial) 200 OK; BDNS (grants) OK tras fix; cnmv/datacomex/bme/procurement/borme con sync-logs y datos reales presentes; botones de sync operativos en todas las fuentes activas.
- **Tests**: `tests/smoke/test_sources_freshness.py` (3 tests: frescura universal, grants con datos, endpoint PLACSP válido). Suite total: **63/63 verde**.
- **Nota (producción)**: las BDs de preview y producción son distintas. Si en producción siguen vacías/desactualizadas tras redeploy, revisar que los schedulers del Intelligence Engine estén activos en el entorno deployado y re-ejecutar las ingestas manuales ("Ejecutar ahora"/acciones de sync) por fuente.

