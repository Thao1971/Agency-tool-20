# Architecture CHANGELOG

> Registro de cambios de arquitectura de la plataforma Agency Tool (compartida: Valuo.pro + arroba.com + Platform Console).

## 2026-07-23 — Documentación formal de la Capa de Inteligencia Estratégica + Definición del Copilot ✅ SOLO DOCUMENTACIÓN
- **Nuevo documento** `memory/STRATEGIC_INTELLIGENCE_LAYER_REPORT.md`: cierra un hueco de documentación — Q1–Q7 (quick wins), E1/E2/E6/E7 (evoluciones) y T3 + Control & Synergy Score (transformacional), construidos en sesiones previas sobre el esquema moderno (`master_companies`/`master_id`), no estaban documentados en `memory/` del propio repo (solo en memoria de sesión). Cubre también la ingesta real de las 25.000 empresas Iberinform (doble esquema, fix del resolver de identidad), la auditoría completa de fuentes de datos (CNMV/BME/PLACSP/DataComex/Banco de España/scheduler/DIRCE) y el fix de fondo del ciclo de vida de señales (identidad ya no depende de `source_version`).
- **Nuevo documento** `memory/ARROBA_COPILOT_DEFINITION_v1.md`: define qué es el Arroba Copilot (se construye en arroba.com, per `ARROBA_INTEGRATION_PACK_v1.md` §1.6), qué capacidades ya cubre la plataforma (analizar/valorar/proponer/ejecutar, vía los motores existentes), el gap real de "predecir" (requiere un motor nuevo `forecast-intelligence-v1`, no construido), el split de memoria/aprendizaje entre arroba.com y Agency Tool (`recommendation_memory`/`recommendation_feedback`/`strategic_theses.lifecycle` ya existen como semilla), y una propuesta de endpoint agregador "Copilot Context" (no implementada).
- **Actualización aditiva de contratos existentes** (sin romper compatibilidad — adiciones D10): `SIGNAL_INTELLIGENCE_ENGINE_CONTRACT.md` (§6.1 nueva: `/signals`, `/signals/view`, `/stats`, `/stats/view`, `/signal/{id}/view`, `/history/view`, `/migrate-dedupe`; corrección de la fórmula de `signal_id` — ya no incluye `source_version`) e `INTELLIGENCE_API_REFERENCE.md` (§2 Signal Intelligence actualizada con los mismos endpoints).
- **`PRD.md`**: nueva entrada "Sprint 9" en `## Latest changes (Julio 2026)` resumiendo todo lo anterior, con estado explícito: verificado (mongomock + `py_compile` + esbuild), **pendiente de empaquetar y desplegar** por instrucción de Daniel de acumular trabajo verificado y desplegar en un único paso cuando él lo indique.
- Sin cambios de código ni de comportamiento en este commit — solo documentación de trabajo ya implementado y verificado en sesiones anteriores.

## 2026-07-12 — Smoke Test Público Oficial de Integración (artefacto permanente) ✅
- Creado `memory/SMOKE_TEST_PUBLIC_PRODUCTION.md` (documento de gobierno) + `backend/tools/smoke_test_public.py` (script ejecutable, exit 0=PASS/1=FAIL, apto para gate de CI/despliegue).
- Verifica en <2 min el flujo canónico Arroba (resolve→identity→analyze) sobre CIF `A87803862`, solo con Base URL pública + X-API-Key: HTTP 200, identidad, financials L2, histórico real, data_source, explainability, master_id y compatibilidad `arroba.v2`.
- **Regla:** antes de cada despliegue de Arroba o del Intelligence Engine debe ejecutarse; FAIL = regresión de integración → no se despliega.
- **Ejecución 2026-07-12 contra producción: PASS (18/18).** F0.2 desbloqueado; contrato congelado durante F0.2.


## 2026-07-12 — Desbloqueo integración Arroba F0.2 · Resolución pública + caso canónico ✅
- **Identificador oficial = CIF** (contratos agnósticos: aceptan CIF o master_id en `identifier`). Documentado en `ARROBA_V2_INTEGRATION_GUIDE.md`.
- **Endpoint público de resolución** `POST /api/v2/company-intelligence/resolve` (solo X-API-Key): CIF→master_id (cif_exact) y Nombre→master_id (name_exact/name_partial). Sin JWT, sin /master/*, sin Mongo. Modelos `CompanyResolve*` (nombres únicos para no colisionar con `master.py::ResolveRequest` — evita romper el freeze v1).
- **Caso canónico F0.2 verificado:** CIF `A87803862` (TOTALENERGIES) → identity completa + financial-analyze con L2 real (revenue 933M, EBITDA 36,5M, net_income 25M), histórico real 3 años (2024/2023/2022, sin interpolar) y `explainability.data_source` trazable a Iberinform.
- **Contrato v2 re-congelado:** 55 paths (añade `/resolve`), 94 schemas. `arroba.v1` sigue byte-idéntico (53 paths). Freeze test v2 actualizado (55). 10 golden tests verdes.
- **Verificado:** testing_agent backend 100% (resolve CIF/nombre/401/422, caso canónico agnóstico CIF↔master_id, regresión contratos). Report: `/app/test_reports/iteration_33.json`.


## 2026-07-12 — Desbloqueo Data Layer · Bootstrap reproducible + dataset canónico ✅
- **Diagnóstico:** NO hay bug de mapeo raw→master (norm_financials→master.financials: 0 pérdidas). El 404 "para todas" es por **BD de producción vacía** (despliegue independiente). Cobertura financiera 374/1000 = cobertura real de la fuente.
- **Track A — Bootstrap reproducible:** `services/data_layer/bootstrap.py` reconstruye TODO el Data Layer desde la fuente oficial (`tests/fixtures/iberinform_sample`, real) sin pasos manuales: ingestión→master(+ER+financieros)→ownership→signals canónicas→índice semántico canónico→verificación→set canónico. 3 vías: self-healing al arranque (`AUTO_BOOTSTRAP_DATA_LAYER=1` si Master vacío), endpoint `POST /api/v1/data-layer/bootstrap` (JWT), y CLI `python -m services.data_layer.bootstrap`. Probado desde BD vacía: 1000 empresas, 2443 señales, 998 perfiles, ~15s.
- **Track B — Dataset canónico:** `select_canonical_set(50)` (data-driven, ≥2 ejercicios reales) → `db.canonical_validation_set` + `GET /api/v1/data-layer/canonical-set`. Empresas reales (TOTALENERGIES, SCANIA HISPANIA…). Cadena pública completa validada (identidad+financieros+histórico real+señales+semántica+estrategia).
- **Histórico:** solo ejercicios reales ingeridos; sin interpolar/estimar. Serie expuesta vía `evolution`.
- **Endpoints nuevos:** `POST /api/v1/data-layer/bootstrap`, `GET /bootstrap/{run_id}`, `GET /bootstrap`, `GET /canonical-set` (todos JWT). Startup self-healing hook `_auto_bootstrap_data_layer_if_empty()`.
- **Verificado:** testing_agent 20/20 (incl. regresión contratos congelados v1+v2). Informe: `DATA_LAYER_UNBLOCK_REPORT_v1.md`.


## 2026-07-12 — Sprint V2.0 · Contrato `arroba.v2` (V2-01 tipado DTOs + V2-02 Company/Identity) ✅ ADITIVA
- **V2-01 (tipado):** los 53 endpoints de los 6 motores tienen DTO de respuesta explícito en OpenAPI vía `responses={200:{"model":...}}` (NUNCA `response_model`). Runtime intacto (los DTO documentan, no filtran; `extra="allow"`). Nuevos DTOs en `routes/engine_schemas.py`.
- **V2-02 (Company/Identity):** `POST /api/v2/company-intelligence/identity` (auth `X-API-Key`, `capability_version=company-intelligence-v2`) → `CompanyIdentityResponse` proyectada del Master Record (añade `capital_social`, `domain`, `employees_total`). Alimenta COMP-1001/1002/1003. Router registrado en `server.py`.
- **`arroba.v1` congelado byte-idéntico:** `_build_arroba_openapi()` strippea las respuestas tipadas y filtra `components` al set del snapshot v1 → hash canónico idéntico, freeze tests verdes.
- **Nuevo contrato v2:** `_build_arroba_v2_openapi()` + `GET /api/v1/openapi/arroba.v2.json` (54 paths, 91 schemas) + `/api/docs/arroba/v2`. Snapshot congelado `contracts/arroba.v2.json` + freeze test `tests/golden/test_arroba_v2_contract_freeze.py`.
- **Verificado:** matriz contrato↔runtime **53/53 MATCH** (`tools/validate_matrix.py`), **10/10 golden tests**, testing_agent backend **22/22 (100%)**. SDK tipado auto-generable confirmado (OpenAPI 3.1 válido; `datamodel-code-generator` → 91 clases). Informe: `memory/ARROBA_V2_SPRINT_V2.0_REPORT.md`.


## 2026-07-12 — Utilidad AI Chat (OpenAI gpt-5.5) ✅ ADITIVA
- **Backend** `routes/ai_chat.py` (prefijo `/api/ai-chat`, fuera de `arroba.v1`): `POST /message` (gpt-5.5 vía `emergentintegrations` LlmChat con **OPENAI_API_KEY** propia del usuario), `GET /history/{session_id}`, `GET /sessions`, `DELETE /session/{session_id}`. Historial persistido en `ai_chat_messages`; memoria por `session_id`.
- **Frontend** `pages/AIChatPage.jsx` + ruta `/ai-chat` + ítem de menú HOME→AI Chat. UI request/response (no streaming: la lib instalada v0.1.0 solo soporta `send_message`).
- **Verificado:** backend por curl (respuesta real, memoria, historial) + testing_agent frontend **100% PASS**. No toca el contrato público ni otros motores. `OPENAI_API_KEY` guardada como secreto en `backend/.env`.

## 2026-07-04 — Cierre de Agency Tool como proveedor + Runbook de rotación de API Keys ✅
- **Producción confirmada:** `https://agencias.wearebudadvisors.com` (dominio custom; contrato v1 desplegado y verificado: `/api/v1/openapi/arroba.v1.json`, `/api/docs/arroba`, `/api/v1/health` → 200). Documentos de handoff/certificación actualizados con la URL de producción.
- **Runbook operativo** `memory/API_KEY_ROTATION_RUNBOOK.md`: rotación de `ARROBA_SERVICE_API_KEY` sin downtime (solape clave nueva/antigua en `db.api_keys`, migración del consumidor, revocación) + variante simple, verificación post-rotación y buenas prácticas. No bloquea la integración.
- **Hito:** Agency Tool queda **cerrado como proveedor de servicios** (contrato `arroba.v1` congelado). Nuevo desarrollo se realiza en arroba.com como consumidor. Se volverá a Agency Tool solo para incidencias, ampliaciones o publicar contrato `v2`.

## 2026-07-04 — CI gate del contrato de arroba.com (freeze en cada push) ✅
- **GitHub Actions** `.github/workflows/arroba-contract-freeze.yml`: en cada `push`/`pull_request` a main/master construye el contrato de arroba **en proceso** (sin servidor ni MongoDB; conexión Motor lazy) y lo compara por hash canónico con `backend/contracts/arroba.v1.json`.
- **Test offline añadido** `test_arroba_contract_matches_code_offline` en `tests/golden/test_arroba_contract_freeze.py` (4 tests en total; el subset de CI = 3, excluye el que requiere servidor vivo). Cualquier deriva de la superficie pública de los 6 motores **falla el CI** → obliga a `v2` deliberado; v1 no se puede romper en silencio.
- ⚠️ Para **bloquear el merge** hay que activar Branch Protection en GitHub exigiendo el check "Arroba Public Contract Freeze". Universo canónico 6.261 intacto.

## 2026-07-04 — Snapshot congelado + freeze test del contrato de arroba.com ✅
- **Endpoint versionado oficial** `GET /api/v1/openapi/arroba.v1.json` (fuente que consume arroba.com) + `GET /api/docs/arroba` (Swagger UI).
- **Snapshot físico congelado** `backend/contracts/arroba.v1.json` (referencia documental / comparación de versiones), **idéntico** al endpoint. `sha256(canonical)=0a266fff…f187f41`. README con política de versionado en `backend/contracts/README.md`.
- **Freeze test** `tests/golden/test_arroba_contract_freeze.py` (3 tests, read-only, no toca colecciones canónicas): verifica que endpoint↔snapshot son idénticos (hash canónico) y que solo exponen los 6 motores. Cualquier deriva de la superficie pública falla el test → obliga a un `v2` deliberado sin romper v1.
- **Handoff completo** para arroba.com: `memory/ARROBA_ONBOARDING_HANDOFF.md` (URL base, auth, OpenAPI, generación de cliente, pasos, ejemplos, límites). Universo canónico 6.261 intacto; ningún endpoint/schema de motor modificado.

## 2026-07-04 — Contrato OpenAPI filtrado para arroba.com (desacople externo/interno) ✅
- **Añadido `GET /api/v1/openapi/arroba.json`**: contrato público filtrado (`arroba-integration-contract-v1`) con **solo los 6 motores** (Financial 3, Signal 7, Semantic 6, Recommendation 11, Strategy 13, Transaction 13 = **53 rutas**), incluye `components`/schemas; sin rutas administrativas ni de Valuo. `GET /api/docs/arroba` = Swagger UI del contrato filtrado.
- **Full spec interno intacto** en `/api/v1/openapi.json` + `/api/docs` + `/api/redoc` (496 rutas). Cambio derivado/config; ningún endpoint ni schema de motor modificado. Verificado en vivo (`200`, 0 fugas), backend sano, universo 6.261 intacto. Ver `ARROBA_INTEGRATION_READINESS_CERT.md` (Atención A).

## 2026-07-04 — Punto A · OpenAPI expuesto bajo `/api/...` (mejora operativa) ✅
- **Solo configuración, sin cambios de contrato.** Reubicados los endpoints integrados de FastAPI: `openapi_url=/api/v1/openapi.json`, `docs_url=/api/docs`, `redoc_url=/api/redoc`. Antes iban fuera de `/api` y el ingress los enrutaba al frontend (devolvían HTML de la SPA).
- **Resultado:** `GET /api/v1/openapi.json` (OpenAPI 3.1.0, 496 rutas, coincidente con la implementación), `GET /api/docs` (Swagger UI) y `GET /api/redoc` accesibles públicamente → arroba.com ya puede autodescargar el contrato. Verificado en vivo (`200`); backend sano; universo canónico 6.261 intacto; ningún endpoint ni schema de motor modificado. `ARROBA_INTEGRATION_READINESS_CERT.md` (Atención A → RESUELTO).

## 2026-07-04 — Recuperación del universo canónico (proyección M3-2b re-ejecutada) ✅
- **Solo datos, cero cambios de código/contrato.** Re-ejecutada `legacy_projection.project_and_build` (4 batches, 5.261 proyectados) → `master_companies` **1.000 → 6.261**. Bridge re-medido `erb_c0c480261423`: **cobertura 98,13 %** (5.257 enlazadas / 5.357; 23 conflictos, 4 ambiguas, 73 huérfanas, 27 revisión manual); overlap CIF legacy **99,02 %**.
- **Validación de contrato:** Golden 111 + Smoke 203 = **314/314 verde**; endpoint público `financial-intelligence/analyze` y entidad proyectada `mc_d178502397b0` verificados en vivo con `engine_version` intacto. Ningún endpoint ni schema modificado.
- **Causa raíz documentada:** app y suite de tests comparten `test_database`; `test_jobs.py` borra `norm_company` + smoke tests hacen `rebuild_master(full)` → resetean el universo a ~1.000 en preview. En producción no ocurre (tests no corren contra BD productiva). Ver `ARROBA_INTEGRATION_READINESS_CERT.md` (Atención B, RESUELTO).

## 2026-07-04 — Contrato de Integración v1.0 + Certificación de readiness · arroba.com 📄
- **Documento oficial** `memory/ARROBA_INTEGRATION_CONTRACT_v1.md` (`arroba-integration-contract-v1`): fuente única de verdad para que arroba.com consuma la inteligencia SIN conocer la implementación interna. Sin código.
- Cubre las 11 secciones solicitadas: arquitectura por capas (responsabilidad/owner/entradas/salidas), inventario de 26 entidades, inventario de colecciones (claves/índices/cardinalidad/estado), contrato API completo (endpoints de los 6 motores + Master, auth `X-API-Key`, códigos de error, paginación, límites 600/min, versión), matriz de consumo por bloque de arroba, schema completo por endpoint, estado de implementación (🟢🟡🟠🔴), estrategia de sincronización, roadmap (actual/siguiente/futuro), contrato de estabilidad (congelado/aditivo/ruptura) y matriz final obligatoria.
- Basado 100% en auditoría del código real (rutas, modelos de request, colecciones, contratos congelados `*_ENGINE_CONTRACT.md`). No se modificó ningún endpoint ni comportamiento.

## 2026-07-04 — Sprint 8.6 · M3 Fase 2b · Ingesta & Cobertura del Master Record ✅
- **Proyección legacy→canónica** `services/data_layer/master/legacy_projection.py` (`project_and_build`): proyecta identidades legacy ausentes a `norm_company` (etiquetadas `source='companies_master_projection'`, `projection_batch`) y reconstruye vía `rebuild_master(scope='cif_list')`. Preserva invariantes de `master_builder`; **reversible por batch** (`rollback_projection`).
- **Requisitos respetados**: `companies_master` intacto (solo lectura), sin cambio en producción, motor canónico NO activado, sin migrar tráfico, sin borrar datos, sin matcher fuzzy, sin reanudar M2.
- **Resultado**: universo canónico 1.000→**6.259** (5.259 proyectados, 2 batches). Bridge re-ejecutado (`erb_202d8224d594`): **cobertura 0 % → 98,17 %** (5.255 enlazadas / 5.353; 21 conflictos, 4 ambiguas, 73 huérfanas, 25 revisión manual, 0 duplicados). Overlap por CIF: legacy 99,02 %. **Objetivo ≥95 % superado.**
- **Recomendación**: bloqueante de cobertura RESUELTO. **NO activar `canonical`** hasta resolver los 25 casos de revisión manual + huérfanas y aprobar nuevo informe. M2 queda desbloqueado para retomarse. Ver `M3_PHASE2B_REPORT.md`.

## 2026-06-26 — Sprint 8.5 · M3 Fase 2 · Entity Bridge & Master Record Quality Tool ✅
- **Herramienta permanente** `services/data_layer/master/entity_bridge.py` (+ rutas admin `/api/v1/master/bridge/*`): construye el bridge canónico `master_company_id`↔`master_id` en `entity_xref` (origin='er_bridge') y mide calidad. **Idempotente, auditable, reversible** (rollback por run_id), histórico en `er_bridge_runs`, clasificación por entidad en `er_bridge_results`.
- **Requisitos respetados**: legacy nunca modificado, sin cambio en producción, motor canónico NO activado, sin migrar tráfico, sin eliminar datos.
- **Medición**: 5350 legacy vs 1000 canónicos → **cobertura 0 %** (100% huérfanos; datasets disjuntos por cif/domain/name). Golden suite 106→**111 verde**. Detector de conflictos/ambigüedades/duplicados implementado y probado.
- **Recomendación**: **NO activar `canonical`** (orfanaría el 100% de Valuo.pro). Prerrequisito: ampliar la ingesta canónica al universo real y re-ejecutar el bridge hasta cobertura objetivo. `M3_PHASE2_BRIDGE_REPORT.md`.

## 2026-06-26 — Sprint 8.4 · M3 (Entity Resolution) Fase 1 ✅ (motor canónico + red de seguridad, sin migrar)
- **Contrato CONGELADO** `entity-resolution-v1` (DER1–DER9 aprobadas). `ENTITY_RESOLUTION_CONTRACT.md`.
- **Motor canónico unificado**: `services/data_layer/master/identity_resolver.py` — `resolve_identity` (shape legacy-compatible), `deterministic_master_id` (DER5), `link_legacy_master` (DER3 bridge legacy↔canónico en `entity_xref`), umbrales congelados DER4, auditoría append-only DER6.
- **Provider de convivencia** `services/entity_resolution_provider.py` (flag interno `ENTITY_RESOLUTION_SOURCE`, default `legacy`), cableado en `valuo_integration`/`master`/`procurement` vía alias (call sites intactos). Contrato público único (DER7); rollback inmediato.
- **Red de seguridad**: snapshot-diff de `resolve_entity` (cif_exact/domain_exact/discovered) + guards del provider. Golden suite 96 → **106 tests verde**. Smoke **203/203** (cero regresión en ruta Valuo.pro).
- **NO** se retira legacy, **NO** se migra tráfico, **NO** backfill masivo (→ M3-fase-2, DER8). Default legacy = byte-identical.

## 2026-06-26 — Sprint 8.3 · M2 inicio → DETENIDA EN VALIDACIÓN (bloqueante de cobertura) ⛔
- **Infraestructura de convivencia interna (contrato público único)**: flag `MASTER_RECORD_SOURCE` (default `legacy`), `services/intelligence_engine/master_provider.py` (legacy byte-identical / canónico con fallback transparente), cableado en `enrich_company`. Sin `?source=` público; rollback inmediato; el canónico nunca causa `master_not_found`.
- **Golden dataset ampliado**: 9→**14 empresas** / 18→**28 snapshots** con casos límite (micro/pyme/holding/incompletos/sin_web/baja_calidad/discovered). Golden suite 82 → **96 tests verde**. Smoke **203/203** (cero regresión en ruta crítica de Valuo.pro).
- **BLOQUEANTE**: `companies_master` (5338) y `master_companies` (1000) son **DISJUNTOS** (overlap `cif_normalized`=0; resolución canónica 0/14). Paridad estructuralmente imposible → legacy NO retirado, tráfico NO migrado. Ver `MASTER_SOURCE_PARITY_REPORT.md`.
- **Re-secuenciación recomendada**: M2 depende de cobertura del Master canónico ⇒ priorizar **M3 (Entity Resolution)** + **M2-pre (backfill/linkage)** antes de reanudar M2. Infra de M2 lista y desactivada, sin riesgo.

## 2026-06-26 — Sprint 8.2b · Preparación M2 (snapshot-diff + golden dataset) 🟡
- **Red de paridad para M2**: golden dataset congelado de 9 empresas × {valuo, arroba} = **18 snapshots** (`tests/golden/data/enrich_golden_snapshots.json`); generador `tests/golden/gen_enrich_golden.py`; util `enrich_snapshot_util.py` (normalización order-insensitive); test `test_enrich_snapshot_diff.py` (paridad byte-level de `fields`/`sources_with_data`/`found_map`/`engine_version`).
- **Suite golden: 62 → 82 tests** (todas verdes, idempotentes). **Sin cambios de código de producción** (solo harness de prueba).
- Propósito: detectar cualquier deriva de cálculo cuando M2 cambie el origen de datos interno (`companies_master` → `master_companies`) sin tocar el contrato externo.

## 2026-06-26 — Sprint 8.2 · M1 migración piloto (relocalización Signal legacy) ✅
- **Componente migrado**: `services/signal_engine.py` (legacy master-signals: `signal_score`, `signals[]`, `signal_similarity` sobre `companies_master`) → **relocalizado byte-for-byte** a `services/engines/signal/master_signals.py` (md5 idéntico).
- **Implementación retirada**: ninguna (fase CONVIVENCIA). `services/signal_engine.py` permanece como **shim** que re-exporta `compute_signals/rebuild_signals/signal_similarity`. Retirada diferida.
- **Consumidores migrados a la ruta canónica**: `routes/data_layer.py` (`rebuild_signals`), `services/skills_recommend.py` (`signal_similarity`).
- **Impacto**: 🟢 nulo en Valuo.pro y arroba.com; `rebuild-signals` (Console) y `skills/recommend` (arroba) con contrato idéntico.
- **Riesgo real observado**: BAJO/nulo. Sin cambios de contrato, sin regresiones.
- **Validación**: Golden 62/62 (incl. paridad shim↔canónico), Smoke 203/203, snapshot determinista (`signal_score=71`) congelado.
- **Lección aprendida**: sin equivalente funcional, "migrar" = **relocalizar + shim** (consolidar ubicación), no sustituir lógica. La sustitución semántica (consumir entidades canónicas del `engines/signal.engine`) queda como trabajo futuro con su propio contrato.

## 2026-06-26 — Sprint 8.1 · Golden Contract Tests (red de seguridad)
- Suite black-box `/app/backend/tests/golden/` congelando 19 endpoints 🔴 Legacy crítico (47 tests). Sin cambios de código de producción.

## 2026-06-26 — Sprint 8 · Auditoría final + plan de migración
- `AGENCY_TOOL_AUDIT_FINAL.md`, `LEGACY_MIGRATION_PLAN.md`, `INTELLIGENCE_API_REFERENCE.md`, `PLATFORM_GOVERNANCE_AND_CONSUMER_AUDIT.md`. 0 componentes retirables.

## 2026-06-26 — Sprint 7 · Transaction OS + Transaction Intelligence Engine
- `transaction-os-v1` / `transaction-intelligence-v1` (DTX1–DTX13). Cima del DAG. Smoke 203/203.
