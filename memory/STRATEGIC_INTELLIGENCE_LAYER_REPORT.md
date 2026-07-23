# STRATEGIC_INTELLIGENCE_LAYER_REPORT.md
**Informe de cierre — Capa de Inteligencia Estratégica (Q1–Q7 · E1/E2/E6/E7 · T3 · Control & Synergy)**
_Versión: `strategic-intelligence-layer-v1` · 2026-07-23 · Estado: **IMPLEMENTADO Y VERIFICADO (mongomock), PENDIENTE DE DESPLIEGUE**._

> Este documento cierra un hueco de documentación: todo el trabajo descrito aquí se implementó y se verificó (smoke tests reales contra `mongomock`, más verificación end-to-end en el entorno Emergent Preview donde se indica) a lo largo de varias sesiones, pero hasta ahora solo existía documentado en memoria de sesión de Claude, no en `memory/` del propio repositorio. Es el documento de referencia oficial para esta capa, complementario a `INTELLIGENCE_API_REFERENCE.md` (que cubre los 7 motores base) y a los `*_ENGINE_CONTRACT.md` (contratos congelados de cada motor).

---

## 0. Origen y alcance

Punto de partida: **Capability Map v1** (`agency-tool`, rama `12726`, commit `a044648`), una auditoría técnica que organizó el backend en 15 capacidades (C1–C15) por ciclo M&A (Descubrir→Analizar→Valorar→Emparejar→Decidir→Ejecutar) y propuso un roadmap de mejoras: **Quick Wins (Q1–Q7)**, **Evoluciones (E1–E7)** y **Transformacionales (T1–T5)**. Este informe documenta la implementación real de Q1–Q7, E1, E2, E6, E7, T3 y el Control & Synergy Score (mencionado por el roadmap sin fórmula, diseñado aquí), todos ellos construidos **sobre el esquema moderno** (`master_companies`/`master_id`/`master_relationships`), el mismo que consumen los 7 motores de `INTELLIGENCE_API_REFERENCE.md`.

**Principio transversal aplicado en todas las piezas de esta capa:** ninguna señal, score o recomendación se construye sobre un dato que no exista de verdad en las fuentes ya ingeridas. Cuando un dato aspiracional del roadmap no tenía respaldo real (edad de administradores, board interlocks, sinergia económica en €, complementariedad vertical `supplier_candidate`), se documenta explícitamente el hueco en vez de inventar el valor.

---

## 1. Q1 — Intent Signals desde BORME

- **Módulo**: `backend/services/engines/signal/borme_bridge.py`. Enlaza `borme_events` ↔ `master_companies` (nombre normalizado + CIF/provincia como boost).
- **4 tipos de señal nuevos** en `taxonomy.py`: `corporate.governance_change`, `corporate.capital_movement`, `risk.dissolution_signal`, `opportunity.succession_signal` (primera señal que puebla la categoría `opportunity`, antes vacía). `corporate.borme_event` deja de estar `pending`.
- **Corrección de dato importante**: la edad/fecha de nacimiento de administradores **no existe en ninguna fuente conectada** (verificado por grep exhaustivo: BORME, Iberinform, PLACSP, CNMV/BME, INE/SEPE/BdE, DataComex). El succession signal usa en su lugar **tenure real del administrador único/mayoritario** (años desde `appointment_date`, vía `norm_officers`/Iberinform), con umbral versionado 15 años en `thresholds.py` — un proxy real, no una simulación de "edad".
- **Endpoints admin**: `POST /borme-link-backfill`, `POST /baselines/compute`, `GET /baselines/status` (`routes/signal_intelligence.py`).
- **Pendiente de ejecutar en producción**: correr `/borme-link-backfill` tras el primer despliegue con datos reales de BORME (hoy `borme_events` está vacío en el entorno Preview → `events_linked: 0`, comportamiento esperado, no un bug).

## 2. Q2 — Grafo de control (corrección de diagnóstico + cierre del gap real)

El roadmap original afirmaba "grafo de control: solo 2 de 8 tipos de relación materializados (`similar_to`, `same_cluster`)". **Esa cifra describe únicamente el módulo legacy** (`services/knowledge_graph.py` + `services/taxonomy_embeddings.py`, esquema `companies_master`/`master_company_id`). El pipeline oficial de producción (`services/data_layer/bootstrap.py::run_bootstrap()`) ya materializaba, sobre el esquema moderno:
- **Grafo de propiedad real** (`services/data_layer/master/ownership_graph.py` → `master_relationships`): `shareholder_of`, `parent_of`, `ultimate_parent_of`, `investee_of` (desde `norm_ownership`) + `same_group` (unión-find sobre `ownership.group_id`).
- **Similitud semántica moderna** (`services/engines/semantic/engine.py::similar()`) — equivalente funcional a `similar_to`.

**Gap real confirmado** (grep exhaustivo: `master_relationships` nunca se leía, solo se escribía):
1. No existía función de consulta para leer el grafo de propiedad (solo-escritura).
2. `competitor_of` no estaba calculado en ningún sitio.
3. `supplier_candidate`/`acquisition_candidate`: sin datos reales en ninguna fuente conectada — permanecen sin construir.

**Implementación real:**
- `ownership_graph.py` — añadidas `relationships_for(master_id)` y `group_members(master_id)` (cierran el "solo-escritura").
- `services/data_layer/master/competitor_graph.py` (nuevo) — `rebuild_competitor_edges()`: `competitor_of` real (mismo `cnae_code` + misma banda de tamaño de `baselines.py`, excluyendo pares ya en el mismo `ownership.group_id`), confianza heurística 0.5. Idempotente.
- Endpoints: `GET /relationships/{master_id}`, `GET /relationships/{master_id}/group`, `POST /rebuild-competitor-graph` (`routes/data_layer.py`). El endpoint legacy `/rebuild-graph` queda marcado `deprecated` en su docstring.
- **Pendiente de ejecutar en producción**: `POST /rebuild-competitor-graph` tras cada `/bootstrap`.
- **Verificado en Emergent Preview**: 468 aristas `competitor_of` generadas sobre datos reales.

## 3. Q3 — Baselines contextuales

- `backend/services/engines/signal/baselines.py`: percentiles (p25/p50/p75) de `ebitda_margin`, `revenue_per_employee`, `revenue_growth_yoy` por (sector CNAE × banda de tamaño por facturación), reutilizando el motor financiero existente. Umbral mínimo de muestra: 12 empresas/bucket; si no se alcanza, cae al `default_threshold` de `thr-v1` (nunca inventa un valor).
- `thresholds.py::resolve()` ya aceptaba `context`, pero nunca se le pasaba nada real — `engine.py::_evaluate()` ahora construye contexto real por empresa.
- **Verificado en Emergent Preview**: `POST /baselines/compute` → 18 sectores, 355 empresas, 20 buckets.
- **Pendiente en producción**: recalibración periódica razonable, mensual.

## 4. Q4 — Feed unificado de oportunidades

- `bootstrap.py::build_signals_canonical()` ya poblaba `db.signals` con ciclo de vida (`first_detected_at`, `trend`, `occurrences`) para todo el universo activo — Q4 consistió en **exponerlo**, no en recalcularlo.
- `POST /opportunities` — nuevos filtros `new_since_days` y `trend`; los campos de ciclo de vida ahora se devuelven en cada fila.
- `GET /opportunities/feed?days=N` (nuevo) — vista cronológica (más nuevo primero), complementaria al ranking por impacto.
- **Fuera de alcance (follow-up documentado)**: unificar cross-motor (Recommendation `buyers()`/`sellers()`/Strategy thesis) en un único stream — el Recommendation Engine es hoy por-target, no por-cartera.

## 5. Q5 — Drill-down sector→empresa

- Motor real ya existente: `services/sector_intelligence_v2.py` (`dynamism_score = 0.25·size + 0.40·growth + 0.35·activity`), jerarquía CNAE sección→división→grupo, `routes/sector_intelligence.py`. El drill-down se cortaba justo antes de la empresa.
- **Hallazgo de datos importante**: el `active_companies` de cada sector es una **estimación nacional DIRCE/INE redistribuida por CNAE** (`_gather_demography()`), no un conteo real de Iberinform — el propio código intenta cruzar con el conteo real y lo descarta explícitamente. Cualquier lista real de empresas por CNAE debe presentarse con su propio conteo (`total_in_arroba_universe`) y un caveat que la distinga de la cifra estimada del sector.
- `_company_query_for_sector()` + `_companies_page()` (`routes/sector_intelligence.py`): mapea el nivel del sector a `classification.cnae_section`/`cnae_division`/`cnae_code` real, consulta paginada por facturación, enriquecida con conteo de señales activas (reutiliza Q1/Q4).
- `GET /detail/{cnae_code}` — embebe preview de 10 empresas reales al nivel más fino (grupo CNAE).
- `GET /detail/{cnae_code}/companies` (nuevo) — versión paginada completa (`limit`/`offset`), cualquier nivel.
- **Fuera de alcance**: no se toca la estimación DIRCE de `sector_intelligence_v2.py`; no se construye `dynamism_score` a nivel empresa individual.

## 6. Q6 — Múltiplos reales de M&A Radar (acotado a agencias)

- Verificado antes de construir: el M&A Radar (`transactions_normalized`/`category_valuations.py`) sí tiene múltiplos reales (`ve_ebitda`/`ve_sales`), pero clasifica transacciones en la taxonomía CIS de **agencias de marketing/comunicación**, sugerida por LLM y siempre `requires_human_review=True` — sin mapeo determinista CNAE↔categoría CIS. `master_companies` cubre secciones CNAE mucho más amplias que marketing; aplicar el múltiplo de agencias fuera de ese sector habría repetido el problema que Q6 quiere resolver.
- **Decisión de alcance**: acotar Q6 a agencias (División CNAE 73, "Publicidad y estudios de mercado") ahora; ampliar cuando existan múltiplos reales de otros sectores.
- `services/category_valuations.py` — `MIN_SAMPLE_SIZE=5` (antes una "mediana" con 1-2 transacciones no se distinguía de una muestra real); nuevos campos `ev_ebitda_multiples_count`, `sample_sufficient`, `confidence_label`; `get_marketing_agency_aggregate()` agrupa las 9 categorías CIS de marketing, excluye `deleted`/`confidence_level=low`, devuelve `None` si la muestra no alcanza el mínimo.
- `services/engines/financial/market_multiples.py` (nuevo) — `MARKETING_AGENCY_CNAE_CODES = {"7311","7312","7320"}`; `real_multiple_for_company()` solo devuelve múltiplo real si el CNAE está en ese conjunto **y** la muestra es suficiente.
- `engine.py::valuation()` (Financial Intelligence Engine) — para EBITDA positivo, intenta primero el múltiplo real (`multiple_basis="market_observed"`), y si no aplica cae al múltiplo inferido de siempre (`multiple_basis="inferred_reference"`), sin cambio de comportamiento para el resto de sectores.
- **Verificado en Emergent Preview**: la pantalla de Valoraciones muestra correctamente "datos insuficientes" cuando no hay transacciones suficientes — el gate anti-fabricación funciona.
- **Fuera de alcance (follow-up)**: desglose por subcategoría CIS; extensión a otros CNAE (requiere mapeo adicional o bridge de identidad transacción→`master_id`).

## 7. Q7 — Watchlist + alertas in-app

- No existía ningún concepto de watchlist; `"add_to_watchlist"` era solo una etiqueta de acción sugerida (`actions.py`), sin persistencia. No existe infraestructura de envío saliente (SMTP/SES/SendGrid) — solo un lector IMAP de entrada para ingesta editorial.
- **Decisión de alcance**: alertas in-app únicamente; email/push queda como trabajo de infraestructura futuro (requeriría elegir proveedor; no hay ningún uso real de `boto3`/SES en el código aunque esté en `requirements.txt`).
- `services/watchlist.py` (nuevo) — CRUD de `watchlist` (`user_id`+`master_id`, índice único) y `watchlist_alerts` (`user_id`+`signal_id`, índice único, deduplica). `sync_alerts_for_user()` cruza empresas seguidas contra `db.signals` activas.
- `services/watchlist_scheduler.py` (nuevo) — barrido cada 15 minutos, registrado en `server.py` startup/shutdown.
- `routes/watchlist.py` (JWT) — `POST/GET/DELETE /api/v1/watchlist`, `GET /alerts` (con `unread_only`), `GET /alerts/unread-count`, `POST /alerts/{id}/mark-read`, `POST /sync`.
- **Fuera de alcance**: canal email/push; roles de usuario diferenciados (`db.users.role` siempre vale `"admin"` hoy, no hay roles reales implementados).

## 8. E1 — Buyer Mandate Intelligence

- No existía ninguna entidad de "mandato de comprador" — `recommendation/engine.py::buyers()` solo infería el rol de comprador de forma reactiva contra UN target.
- `models.py` — `BuyerMandateCreate`/`BuyerMandateUpdate` (sector CNAE, provincias, rango de facturación, preferencia de propiedad, exclusiones, `buyer_master_id` opcional).
- `services/engines/recommendation/mandates.py` (nuevo) — CRUD + `mandate_fit()` (5 dimensiones explicables: sector/tamaño/geografía/propiedad/oportunidad, reutiliza `scoring.py`) + `find_targets_for_mandate()` + `find_mandates_for_target()` (dirección inversa: una señal de sucesión de Q1 puede buscar automáticamente qué mandatos activos la querrían).
- Exclusión real de auto-recomendación: si el mandato tiene `buyer_master_id`, se excluyen empresas ya conectadas por una arista real del grafo (Q2) o que comparten `ownership.group_id`.
- `routes/buyer_mandates.py` (JWT, lo crea una persona) — `POST/GET/PATCH /api/v1/buyer-mandates`, `GET /{id}/targets`, `GET /for-target/{master_id}`.

## 9. E2 — Succession Intelligence completa

Investigación previa confirmó qué datos reales existen más allá de la tenure de Q1: el evento BORME `"Constitución"` (antigüedad de empresa); ningún campo de parentesco/apellido en ninguna fuente, pero `norm_officers.person_name` permite una heurística de apellidos compartidos (marcada siempre como proxy, nunca como parentesco confirmado); conteo de administradores distintos (concentración de gobierno); tenure por persona no-administradora con alta posterior (posible sucesor ya nombrado). Sigue sin existir edad/fecha de nacimiento en ninguna fuente.

- **Diseño no invasivo**: la puerta de disparo de Q1 (`administrator_tenure_years >= 15`) no cambia de umbral. E2 añade un **perfil de solo lectura** que refina impact/confidence/urgency/explanation de esa misma señal y se expone completo para análisis.
- `services/engines/signal/succession_intelligence.py` (nuevo, fuente única de verdad para tenure — antes duplicada en `borme_bridge.py`): `administrator_tenure()`, `_admin_count()`, `_family_overlap()` (heurística de apellidos, excluye entidades no-persona), `_successor_candidate()`, `_company_age_years()`, `_financial_stagnation()` (lee, no recalcula, señales ya persistidas), `build_profile()` → `succession_risk_score` (0-100, reglas explícitas versionadas `succession-v1`).
- **Bug real corregido durante el smoke test**: la tenure de Q1 podía ser dominada por un administrador **persona jurídica** (patrón real y válido en derecho societario español, p. ej. sociedades tipo "ESTYOFI" actuando como administrador). Corregido filtrando con el mismo heurístico `_looks_like_person()`.
- `GET /succession-profile/{identifier}` (`routes/signal_intelligence.py`, service-key).
- **Deliberadamente fuera de alcance**: el heurístico de apellidos nunca se presenta como confirmación de parentesco (`data_caveat` explícito en cada perfil).

## 10. T3 — Grafo de control navegable (MVP)

Q2 solo exponía consultas de un salto. T3 (y P4/E6, que lo necesitan) requieren el mapa multi-salto.

- `services/data_layer/master/graph_traversal.py` (nuevo) — `traverse(master_id, max_hops, max_nodes, relationship_types)`: BFS real sobre `master_relationships` (ownership + `competitor_of`), bidireccional, acotado por saltos y nodos, marca `truncated` si aplica (necesario porque un BFS sin límite sobre `competitor_of` puede explotar a cientos de nodos). `sector_consolidation_map(cnae_field, cnae_value, limit_companies)`: relaciones reales internas a un universo sectorial (Q5).
- `GET /graph/{master_id}/traverse` (filtro opcional `relationship_types`), `GET /graph/sector-map`.
- **Fuera de alcance (MVP)**: no hay pre-cómputo/caché del grafo sectorial completo (se calcula al vuelo); "Control & Synergy Score" (§13) se construye como iniciativa separada que consume este módulo.
- **Verificado en Emergent Preview**: `GET /graph/{master_id}/traverse?max_hops=2` → ~85 nodos/aristas, aristas `shareholder_of`/`parent_of` con `src_master_id: null` para accionistas externos aún no mapeados (comportamiento estructuralmente correcto).

## 11. E7 — Índice de fragmentación sectorial

Dependiente de Q2 (el roadmap lo marca explícitamente).

- `services/engines/investment/fragmentation.py` (nuevo) — **HHI** (Herfindahl-Hirschman, escala estándar DOJ/FTC 0–10000) agrupando facturación real por `ownership.group_id` (dos empresas del mismo grupo cuentan como un solo actor de mercado — sin esto la fragmentación sería una ilusión estadística). **Targets add-on viables** (`standalone_targets_count`): empresas sin `ownership.group_id`. **Dispersión de múltiplos**: solo cuando Q6 tiene múltiplo real para ese CNAE (hoy solo agencias, división 73); en cualquier otro caso, `None` con caveat explícito.
- `GET /api/v1/investment-intelligence/fragmentation?cnae_field=&cnae_value=` (`routes/investment_intelligence.py`, service-key).
- **Verificado en Emergent Preview**: `fragmentation?cnae_value=4711` → HHI 7829.5 (`highly_concentrated`), 5 empresas, `multiple_dispersion: null` (caveat correcto, Q6 no cubre ese CNAE).

## 12. E6 — Tesis de roll-up/plataforma

No existía motor de roll-up a nivel sectorial (solo tres señales dispersas per-company usando el mismo proxy `ownership.investees >= 2`, sin ranking de targets).

- `services/engines/investment/rollup_thesis.py` (nuevo) — `compute_rollup_thesis(cnae_field, cnae_value, limit_companies)`:
  1. **Viabilidad**: reutiliza `fragmentation.compute_fragmentation()` (no recalcula HHI) — viable si HHI < `HHI_MODERATE` y `standalone_targets_count >= 3`. Sin datos → `None`, nunca inferido.
  2. **Candidato a plataforma**: mayor actor de mercado real por facturación agrupada; `platform_type="existing"` solo si su cuota supera 20%, si no `"external_needed"`.
  3. **Ranking de targets add-on**: solo empresas standalone reales (T3), 3 dimensiones explicables — `size_fit`, `succession_ease` (reutiliza E2), `synergy_proximity` (0.8 solo si existe arista real `competitor_of`, Q2; nunca un € estimado).
- `GET /rollup-thesis` (mismo router de E7).
- **Verificado en Emergent Preview**: `rollup-thesis?cnae_value=4711` → `rollup_viable:false`, plataforma real detectada (market_share 0.876, sector muy concentrado en los datos de esa muestra).
- **Fuera de alcance**: ninguna estimación de sinergia económica en €; ningún football-field de valoración del roll-up combinado.

## 13. Control & Synergy Score

El roadmap nombra este score (dueño Ownership & Control/Buyer Intelligence, parte de T3, dependiente de Q2) sin especificar fórmula. Investigado antes de construir: `supplier_candidate` sigue sin datos reales; el campo `pct` real de `master_relationships` (Iberinform) existía pero nunca se usaba más allá del `same_group` binario; no existe ningún dato de board seats/consejeros compartidos entre empresas.

**Decisión de diseño**: dos scores independientes y explicables (no un único número opaco):

- `services/data_layer/master/control_synergy.py` (nuevo) — `compute_control_synergy(master_id_a, master_id_b)`:
  1. **Control**: arista directa de propiedad real (`pct`) clasificada por umbrales estándar (`full_control` ≥50%, `significant_influence` 25-50%, `minority_stake` <25%). Sin arista directa pero mismo `group_id`: `same_group_sin_camino_pct` (honesto, nunca inventado). Camino indirecto multi-salto (T3) con `pct` real en cada tramo: `implied_effective_pct` = producto de las participaciones; si falta un `pct` en cualquier tramo, queda `None` (`control_level="indirect_path_pct_incompleto"`).
  2. **Synergy**: `competitor_of` real (Q2, +0.5), mismo `cnae_code` (+0.3) o misma `cnae_division` (+0.15), misma provincia (+0.2), capado a 1.0. `data_caveat` explícito: solo solapamiento estructural/horizontal, nunca € de sinergia; excluye `supplier_candidate` por falta de datos.
- `GET /control-synergy/{master_id_a}/{master_id_b}` (`routes/data_layer.py`, JWT).
- **Verificado en Emergent Preview**: `relationship:unrelated`, `synergy_score:0.3` (mismo CNAE 4711, sin relación societaria).
- **Versionado**: `control-synergy-v1`. Cualquier recalibración de pesos/umbrales requiere `v2`, no cambiar en silencio bajo el mismo nombre.

---

## 14. Frontend construido para toda la capa

**Backend, patrón `/view` (JWT) para exponer motores con auth de servicio al navegador** (mismo patrón que `routes/valuations.py` ya usaba para Q6): `GET /fragmentation/view`, `/rollup-thesis/view` (`investment_intelligence.py`); `GET /search-companies?q=` (`data_layer.py`, esquema moderno — deliberadamente distinto de `GET /api/v1/master`, que busca en el esquema legacy y devolvería IDs incompatibles).

**Pantallas React entregadas** (`frontend/src/pages/`): `SectorIntelligencePage.js` (extendida con drill-down de empresas, Q5), `WatchlistPage.js` (Q7), `FragmentationPage.js` (E7), `RollupThesisPage.js` (E6), `ControlGraphPage.js` (T3), `ControlSynergyPage.js` (Control & Synergy), `OpportunitiesPage.js` (Q4), `SignalsPage.js` (listado general de señales, todas las categorías — ver §17). Rutas registradas en `App.js`, entradas de sidebar en `Layout.js` bajo M&A E INVERSIÓN.

**Rediseño de navegación** (auditoría completa de 45 páginas, agente de exploración exhaustivo): 43/45 páginas eran 100% funcionales (fetch real, sin mocks); el problema no era funcionalidad falsa sino **descubribilidad** — 14 páginas reales sin ninguna entrada de menú (`/hub`, `/analysis`, `/bulk`, `/results`, `/documents`, `/brands`, `/borme`, `/data-providers`, `/master-entities`, `/datacomex`, `/cnmv`, `/bme`, `/procurement`, `/review`). `Layout.js` reagrupado por tarea de usuario (INICIO, EMPRESAS, INTELIGENCIA DE MERCADO, M&A E INVERSIÓN, DOCUMENTOS Y CONTENIDO, TAXONOMÍA Y CALIDAD, MOTOR DE SCRAPING, DATA, PLATAFORMA); todas las rutas `PlaceholderPage` consolidadas en una sección final "PRÓXIMAMENTE" (visualmente atenuada). `DashboardPage.js`: el contador "Empresas" (antes literal `5265`) se conectó a `/api/v1/admin/iberinform/stats`.

---

## 15. Ingesta real de las 25.000 empresas Iberinform

Sustitución del dataset sintético (~1.000-5.000 empresas de fixtures/tests) por la entrega real de Iberinform (~25.000 empresas, formato de 10 ficheros `.tab` separados por tabulador, Latin-1).

- **Doble esquema confirmado**: LEGACY (`companies_master`/`master_company_id`, usado por Sector/Geo Intelligence, Valuo, DocStudio) y MODERNO (`master_companies`/`master_id`, usado por todos los motores de esta capa: Q1–T3, E1/E2/E6/E7, Control&Synergy, Semantic/Recommendation/Strategy). Cargar solo uno habría dejado la mitad de la plataforma con datos sintéticos.
- **Ingesta moderna**: `services/data_layer/ingestion/iberinform_tab_ingest.py` (nuevo) → `norm_company`/`norm_financials`/`norm_ownership`/`norm_officers`. `POST /api/v1/data-layer/bootstrap-tab`.
- **Ingesta legacy**: `services/iberinform_processor.py::process_real_iberinform_tab_directory()` (extendida). `POST /api/v1/admin/iberinform/process-tab-directory`.
- **Purgas de datos sintéticos**: `purge_synthetic_dataset()` (legacy, por `source`) y `purge_fixture_sample()` (moderno, por `source_version` — distingue el ingestor Valu8 CSV del fixture del ingestor `.tab` real, sin lista de IDs hardcodeada; también purga `db.signals` huérfanas de los `master_id` afectados).
- **Botón de subida en la app**: `routes/iberinform_admin.py::POST /upload-delivery` (multipart, extrae zip, lanza en background legacy→intelligence→moderno) + `pages/IberinformDeliveryPage.js` (polling de progreso, historial, botón de purga). Da autonomía real al equipo para las entregas mensuales ad hoc de Iberinform (sin API/SFTP).
- **Fix crítico del resolver de entidades** (`entity_resolution_provider`/`identity_resolver.py`): cuando una entidad nueva traía CIF sin coincidencia existente, el resolver igual intentaba "adivinar" por dominio/nombre+provincia antes de crear `master_id` nuevo — provocando colisiones `E11000 duplicate key` entre empresas reales distintas que comparten dominio de grupo (caso real: OBLANCA HOLDING vs. CANTÁBRICA DE PIENSOS, matriz-filial). Fix: con CIF sin coincidencia → siempre `master_id` nuevo; el fallback de dominio/nombre solo se alcanza sin CIF utilizable. Regla de negocio confirmada: **el CIF es el identificador definitivo de una compañía**.
- **Resultado final verificado en Emergent Preview**: `master_companies` = 25.989 (24.992 reales + 997 del fixture, purgados después) → 24.992 tras purga; `companies_master` (legacy) idéntico tras su propia purga.

## 16. Auditoría de fuentes de datos

Patrón recurrente encontrado en múltiples conectores: cuando el scraping/sync falla, la función retorna **antes** de escribir el log de sincronización (fallo invisible, `last_sync` congelado sin explicación); varios frontends muestran éxito incondicional sin comprobar `status==='error'`.

- **CNMV/BME**: `fatal_error` capturado y logueado siempre (antes el `return` temprano lo saltaba); `bme_enrichment.py` deja de forzar `status:"completed"`; nuevo `services/cnmv_bme_scheduler.py` (antes dependían 100% de un botón manual, sin scheduler).
- **Causa raíz real de los crashes de CNMV** (diagnosticada y corregida por Neo directamente en el entorno desplegado, reincorporada al código local para no revertirla en el siguiente empaquetado): un único Chromium reutilizado para 14 tipologías × 100 páginas se degradaba tras ~50 navegaciones — fix: Chromium se recicla cada 30 navegaciones.
- **BME Growth/Scaleup**: investigado con fetch directo — BME Growth ya no publica tabla en absoluto (migración de sitio permanente a una página sin datos); BME Scaleup todavía sirve la tabla legacy en la URL base pero cualquier parámetro de paginación ya redirige a la página nueva — migración de BME en curso, no un bug de selector arreglable con certeza. Lo corregido: `_scrape_listing()` ya no puede reportar "completado, 0 importados" en silencio — detecta explícitamente la redirección y la primera página vacía como fallo.
- **PLACSP**: un fallo total se marcaba `"partial"` en vez de `"error"` (corregido); no tenía scheduler periódico, solo un auto-populate único al arrancar — nuevo `services/placsp_scheduler.py` (re-sincroniza si el último run tiene más de 7 días) + botón manual "Sincronizar PLACSP" en `ProcurementPage.js`.
- **DataComex**: bug de lectura anidada del frontend ("undefined registros importados") corregido.
- **Watchlist**: `sync_alerts_all()` aislado por usuario con try/except (antes un fallo abortaba el barrido completo).
- **`intelligence_scheduler.py` — enmascaramiento en cascada**: los 4 pasos nocturnos (Sector/Geo/Cross/Economic Intelligence) compartían un único try/except — si uno fallaba, los posteriores ni se ejecutaban ni se registraban como fallidos (su log quedaba congelado en el último éxito, mostrándose como "sano" en `GET /public/intelligence/sync-status`). Confirmado que los 4 pasos son independientes (ninguno lee el resultado de otro). Fix: cada paso con su propio try/except, registro de resultado real en cada corrida.
- **Banco de España**: el indicador de "última actualización" en `MacroIntelligencePage.js` mostraba `generated_at` (momento de construir la respuesta HTTP, siempre "ahora") en vez de la fecha real del dato — daba una falsa sensación de frescura. Fix: se calcula y muestra el `last_updated_at` real más reciente entre los indicadores devueltos.
- **`company_id` inestable (esquema legacy)**: `process_real_iberinform_tab_directory()` regeneraba `company_id` en cada entrega mensual y lo sobrescribía sin protección (a diferencia de `companies_master.master_company_id`, ya protegido con `$setOnInsert`). Fix: resolución del id ya existente vía query batched por `cif_normalized` antes de escribir, reutilizado; `fiscal_years` referencia siempre el id estable; `company_id` pasa a `$setOnInsert` en el upsert.
- **DIRCE (demografía empresarial)**: `routes/business_demography.py` ya exponía `/overview`, `/active-companies`, `/new-companies`, `/closed-companies`, `/history` (todos públicos, sin auth) pero **sin ninguna pantalla en el frontend** — fuente completamente invisible en la UI. Construida `pages/BusinessDemographyPage.js` (KPIs, barras mensuales constituidas-vs-disueltas, botón "Sincronizar DIRCE").
- **Paneles de gobernanza de datos desalineados con la carga real**: "Calidad de Datos" calculaba "empresas reales" por resta (`companies_master.total - iberinform.total_companies`), fórmula que asumía que Iberinform sería siempre sintético — con datos reales la resta converge a ~0 y caía en un fallback hardcodeado. Fix: `GET /admin/iberinform/stats` devuelve `real_companies`/`synthetic_companies` explícitos (contados por el campo `source`, nunca inferidos). "Proveedores de datos" contaba `provider_files` (mecanismo antiguo de subida fichero-a-fichero, nunca escrito por los pipelines reales `bootstrap-tab`/`upload-delivery`) — repuntado a `iberinform_companies`/`cif_normalized` (mismo patrón que BORME/INE).

## 17. Ciclo de vida de señales, filtro Oportunidades y pestaña Señales (v13–v15, esta sesión)

- **Fix de fondo del ciclo de vida** (`services/engines/signal/persistence.py` + `engine.py`): la clave de identidad de una señal era `(master_id, signal_type, source_version)` — como `source_version` cambia en cada entrega mensual, cada entrega creaba un documento nuevo para la misma situación continuada, y el mecanismo de "ya no se detecta → desaparecida" solo comparaba dentro de la misma entrega. Efecto: duplicados en el feed de Oportunidades y avisos de Watchlist repetidos cada mes sin cambio real. Fix: clave pasa a `(master_id, signal_type)` (`source_version` es un campo, no parte de la identidad); `_signal_id()` ya no incluye `source_version` en el hash; migración de una sola vez `migrate_dedupe_and_reindex()` (`POST /migrate-dedupe`) fusiona duplicados existentes reconstruyendo `first_detected_at` real.
- **Fix category vs. severity**: `category=="opportunity"` en `taxonomy.py` es cierto **solo** para `opportunity.succession_signal`; la etiqueta real de "es una oportunidad de M&A" es `severity=="opportunity"` (4 tipos: `growth.revenue_surge`, `growth.sustained`, `ownership.consolidator`, `opportunity.succession_signal`). Corregido en `_list_opportunities()`, `_opportunities_feed()`, `_aggregate()` (`routes/signal_intelligence.py`) y en el desplegable de `OpportunitiesPage.js`.
- **Pestaña "Señales"** (todas las categorías, sin restricción de severidad, distinta de "Oportunidades"): `_list_signals()` + `POST /signals` (X-API-Key) + `GET /signals/view` (JWT) — filtrable por categoría/severidad/estado/provincia/master_id/tipo; `GET /signal/{id}/view` + `GET /history/view` (JWT) para detalle e histórico. Frontend `pages/SignalsPage.js` — tabla + filtros + modal de detalle con historial cronológico; exporta el helper `signalLink(signalId, masterId)` para enlazar desde cualquier pantalla (conectado en Oportunidades y Watchlist).
- **Conteos reales**: los endpoints de listado (`/opportunities/view`, `/signals/view`) devuelven `count` acotado por el límite de paginación, nunca un total real. Añadido `GET /signal-intelligence/stats/view` (JWT) + `POST /stats` (X-API-Key): conteos reales vía `count_documents` (sin cap de paginación), desglosados por severidad/categoría/tipo de oportunidad. Mostrado en cabecera de Oportunidades ("X oportunidades activas en total") y Señales ("X señales en total").
- **Fix "Todos los estados"**: el filtro de estado en `SignalsPage.js` enviaba `status=undefined` al elegir "todos", y el backend tiene un default `"active"` cuando el parámetro no llega — así que "todos" seguía filtrando solo activas. Fix: el frontend envía `status=''` explícito, que el backend interpreta como "sin filtro".

---

## 18. Estado de despliegue

- **Entorno**: Emergent Preview ("preview-arroba-app"), deliberadamente separado de la app de producción existente ("data-factory-hub"). Nunca se ha tocado producción desde este trabajo.
- **Datos**: universo real de 24.992 empresas Iberinform cargado y verificado en ambos esquemas (§15); BORME real sin ingerir (`borme_events` vacío → Q1 sin eventos enlazados aún); resto de fuentes (CNMV/BME/PLACSP/DataComex/Banco de España/DIRCE) con conectores activos pero pendientes de una carga completa a escala de producción.
- **Código**: verificado localmente (mongomock + `py_compile` + esbuild) hasta la v15 (esta sesión) inclusive. **Empaquetado y despliegue pendientes de instrucción explícita de Daniel** — el flujo de trabajo acordado es acumular fixes verificados y desplegar en un único paso cuando él lo indique.
- **Pendiente de ejecutar tras el próximo despliegue** (ninguno requiere código nuevo, son pasos operativos): `POST /migrate-dedupe` (una vez, limpia duplicados de señales del entorno real), `POST /borme-link-backfill` (si se ingiere BORME real), `POST /rebuild-competitor-graph` (tras cada `/bootstrap`), recalibración periódica de `POST /baselines/compute`.

## 19. Deuda técnica y huecos conocidos (no fabricados, documentados)

- `supplier_candidate`/`acquisition_candidate` (grafo de control) y complementariedad vertical del Control & Synergy Score: sin dato real en ninguna fuente conectada.
- Board seats/consejeros compartidos entre empresas: no existe ese dato en `norm_officers`.
- Ninguna estimación de sinergia económica en € en E6/Control&Synergy: solo solapamiento estructural real.
- Canal de alertas por email/push (Q7): no hay infraestructura de envío saliente hoy.
- Roles de usuario reales (advisor/buyer/PE): el campo existe pero siempre vale `"admin"`.
- Extensión de Q6 (múltiplos reales) más allá de agencias: requiere mapeo CNAE↔CIS adicional o bridge de identidad transacción→`master_id`.
- Caché/pre-cómputo del grafo sectorial completo (T3): se calcula al vuelo; revisar si el volumen de `master_companies` lo exige en el futuro.

**Documentos relacionados**: `INTELLIGENCE_API_REFERENCE.md`, `SIGNAL_INTELLIGENCE_ENGINE_CONTRACT.md`, `ARROBA_INTEGRATION_CONTRACT_v1.md`, `ARROBA_INTEGRATION_PACK_v1.md`, `ARROBA_COPILOT_DEFINITION_v1.md`.
