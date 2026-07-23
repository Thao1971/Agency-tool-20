# AGENCY_TOOL_AUDIT_FINAL.md
**Auditoría final de la plataforma — Dependencias, consumidores y clasificación**
_Versión: `audit-final-v1` · 2026-06-26 · Estado: **VIGENTE (read-only; no elimina ni migra)**._

> Agency Tool es **plataforma compartida en producción**: **Valuo.pro** (prod) + **arroba.com** (nuevo) + **Platform Console** (admin interno).
> Esta auditoría inventaría y clasifica **todos** los componentes. **No se elimina código, no se migran consumidores, no se modifican contratos.** Solo Obsoletos (⚫) podrán proponerse para retirada futura.

## Leyenda de clasificación
- 🟢 **Canónico** — implementación definitiva y permanente.
- 🟡 **En convivencia** — puente legacy↔canónico o usado por varios consumidores.
- 🔴 **Legacy crítico** — consumido por Valuo.pro producción. **NO TOCAR** sin compatibilidad + validación.
- ⚫ **Obsoleto** — sin consumidores reales verificados (único candidato a retirada).

---

## 1. Dos capas de datos (núcleo de la auditoría)

| Aspecto | Legacy | Canónico |
|---|---|---|
| Colección | `companies_master` (106 refs) | `master_companies` (28 refs) |
| Productor | `intelligence_engine/linker`, `entity_resolution`, `valuo_enrichment`, `iberinform_processor`, `signal_engine` (antiguo), `publication`, `routes/master`, `taxonomy_embeddings` | `data_layer/master/master_builder` (rebuild desde `norm_*` + `entity_xref`) |
| Consumidor | **Valuo.pro**, Platform Console, skills | **arroba.com** (6 motores + Transaction OS) |
| Clase | 🔴 Legacy crítico | 🟢 Canónico |

> La migración consiste en que los lectores legacy pasen a leer del Master Layer canónico **detrás del mismo contrato externo**, sin que Valuo.pro lo perciba.

---

## 2. Matriz de dependencias — Endpoints (contratos públicos)

| Endpoint / Prefijo | Auth | Valuo.pro | Console | arroba | Sustituto canónico | Clase |
|---|---|:--:|:--:|:--:|---|:--:|
| `/api/v1/valuo/*` (request-update, status, health) | Valuo propia | ✅ | ✅ | ❌ | — (es el contrato de Valuo) | 🔴 |
| `/api/v1/intelligence/enrich` (`profile=valuo`) | JWT | ✅ | ✅ | ❌ | profile=arroba para arroba | 🔴 |
| `/api/v1/company/{id}/enriched`, `/by-valuo-id/{id}/enriched` | JWT | ✅ | ✅ | ❌ | Semantic/Master engines | 🔴 |
| `/api/v1/master/*` (CRUD, verify, publish-to-valuo) | JWT | ↩ indirecto (publish-to-valuo) | ✅ | ❌ | Master Layer canónico | 🟡 |
| `/api/v1/skills/*` | JWT | ❓ verificar | ✅ | ❌ | Financial/Recommendation engines | 🔴 |
| `/api/v1/data-layer/*` (rebuild-master/embeddings/signals/graph, jobs) | JWT admin | ❌ | ✅ | ❌ (lo alimenta) | — (es el productor canónico) | 🟢 |
| `/api/v1/financial-intelligence/*` | X-API-Key | ❌ | ❌ | ✅ | (es el sustituto) | 🟢 |
| `/api/v1/signal-intelligence/*` | X-API-Key | ❌ | ❌ | ✅ | sustituye `signal_engine` antiguo | 🟢 |
| `/api/v1/semantic-intelligence/*` | X-API-Key | ❌ | ❌ | ✅ | (nuevo) | 🟢 |
| `/api/v1/recommendation-intelligence/*` | X-API-Key | ❌ | ❌ | ✅ | sustituye skills_recommend | 🟢 |
| `/api/v1/strategy-intelligence/*` | X-API-Key | ❌ | ❌ | ✅ | (nuevo) | 🟢 |
| `/api/v1/transaction-intelligence/*` | X-API-Key | ❌ | ❌ | ✅ | (nuevo, Sprint 7) | 🟢 |
| Resto admin (taxonomy, sources, jobs, editorial, stats, providers…) | JWT | ❌ | ✅ | ❌ | — | 🟡/🟢 |

(✅ usa · ❌ no usa · ❓ verificar · ↩ indirecto)

---

## 3. Matriz de dependencias — Servicios / módulos

| Módulo | Valuo.pro | Console | arroba | Sustituto canónico | Clase |
|---|:--:|:--:|:--:|---|:--:|
| `services/data_layer/*` (Foundation/Master Layer) | ❌ | ✅ | ✅ (vía motores) | — (es canónico) | 🟢 |
| `services/engines/financial` | ❌ | ❌ | ✅ | — | 🟢 |
| `services/engines/signal` | ❌ | ❌ | ✅ | reemplaza `signal_engine.py` | 🟢 |
| `services/engines/semantic` | ❌ | ❌ | ✅ | — | 🟢 |
| `services/engines/recommendation` | ❌ | ❌ | ✅ | — | 🟢 |
| `services/engines/strategy` | ❌ | ❌ | ✅ | — | 🟢 |
| `services/transaction_os` + `services/engines/transaction` | ❌ | ❌ | ✅ | — | 🟢 |
| `services/service_auth.py` | ❌ | ❌ | ✅ | — | 🟢 |
| `services/intelligence_engine/*` (engine, linker, sources, profiles) | ✅ (profile=valuo) | ✅ | ✅ (profile=arroba) | parcialmente los motores | 🟡 |
| `services/entity_resolution.py` (companies_master) | ✅ | ✅ | ❌ | `data_layer/master/entity_resolution.py` | 🟡 |
| `services/valuo_enrichment.py` | ✅ | ✅ | ❌ | Semantic/Master engines | 🔴 |
| `services/iberinform_processor.py` (escribe companies_master) | ✅ | ✅ | ❌ | `data_layer/ingestion/iberinform_ingest` | 🟡 |
| `services/signal_engine.py` (antiguo) | ❌ | ✅ (`data_layer.py`, `skills_recommend`) | ❌ | `engines/signal` | 🟡 |
| `services/skills_*` (analyze/recommend/search/valuation) | ❓ verificar | ✅ | ❌ | Financial/Recommendation | 🔴 |
| `services/knowledge_graph.py` | ❌ | ✅ | ↩ (KG reutilizado) | `master_relationships`/graph | 🟡 |
| `services/intelligence_engine/sources/{oepm,patentes,catastro,boe}.py` | ❌ | ❌ | ⏳ (perfil arroba, stub) | pendientes de implementar | 🟡 (stub, **no** ⚫) |
| Conectores fuente (`bme_*`, `cnmv_*`, `placsp`, `datacomex_*`, `ine_*`, `banco_espana`, `procurement_*`) | ↩ (alimentan companies_master) | ✅ | ↩ (alimentan master_companies) | — | 🟡/🟢 |

---

## 4. Matriz de dependencias — Colecciones (principales)

| Colección | Productor | Consumidor | Sustituto canónico | Clase |
|---|---|---|---|:--:|
| `companies_master` | linker/entity_resolution/valuo_enrichment/… | Valuo.pro, Console, skills | `master_companies` | 🔴 |
| `master_companies` | `data_layer/master_builder` | 6 motores (arroba) | — | 🟢 |
| `norm_company/_financials/_officers/_ownership`, `entity_xref` | ingestion/normalize | master_builder | — | 🟢 |
| `master_relationships` | ownership_graph | Recommendation/Strategy | — | 🟢 |
| `signals` | `engines/signal` | Recommendation/Strategy/Transaction | reemplaza señales legacy | 🟢 |
| `semantic_profiles` | `engines/semantic` | Recommendation/Strategy | — | 🟢 |
| `recommendation_memory`, `recommendation_feedback` | `engines/recommendation` | arroba | — | 🟢 |
| `strategic_theses` | `engines/strategy` | Transaction | — | 🟢 |
| `tx_transactions/tx_events/tx_tasks/tx_approvals/tx_documents` | Transaction OS | arroba | — | 🟢 |
| `valuo_update_requests` | `routes/valuo_integration` | Valuo.pro flow | — | 🔴 |
| `agency_results` | scraper/intelligence_engine | Console, enriched_company | — | 🟡 |
| `analysis_jobs`, `data_layer_jobs`, `bulk_jobs` | colas | Console/worker | — | 🟢 |
| Fuentes (`bme_companies`, `cnmv_entities`, `public_procurement_contracts`, `ine_observations`, `borme_events`, `datacomex_*`, `iberinform_*`, `macro_indicators`, `economic_*`, `sector_intelligence`, `geo_intelligence`, `business_demography`, …) | conectores | Console + ambos data layers | — | 🟡 |
| `taxonomy_*` | taxonomy services | Console + clasificación | — | 🟡 |
| `api_keys` | service_auth/auth | arroba (X-API-Key) + Console | — | 🟢 |
| `transactions_normalized`, `transaction_imports` | M&A Radar (módulo distinto) | Console | — | 🟡 |

---

## 5. Resumen de clasificación

| Clase | Componentes (resumen) | ¿Retirable? |
|---|---|---|
| 🟢 Canónico | Master/Foundation Layer, 6 Intelligence Engines, Transaction OS, service_auth, colecciones `master_companies`/`norm_*`/engines | No (evolución aditiva) |
| 🟡 En convivencia | `intelligence_engine/*`, `entity_resolution`, `iberinform_processor`, `signal_engine` antiguo, `knowledge_graph`, conectores fuente, `routes/master`, taxonomy, stubs de fuentes | No (mantener ambos caminos) |
| 🔴 Legacy crítico | `/api/v1/valuo/*`, `/intelligence/enrich?profile=valuo`, `/company/*/enriched`, `valuo_enrichment`, `companies_master`, `valuo_update_requests`, `skills_*` (verificar) | No (Valuo.pro vivo) |
| ⚫ Obsoleto | **NINGUNO confirmado a fecha de hoy** | — |

> **Conclusión: 0 componentes elegibles para retirada.** Todo es Canónico, En convivencia o Legacy crítico.

---

## 6. Puntos a verificar antes de cualquier migración (open items)
1. **`skills_*`**: confirmar si Valuo.pro o algún flujo externo los consume, o solo Console. Determina si son 🔴 o 🟡.
2. **`signal_engine.py` antiguo**: 2 consumidores internos (`routes/data_layer`, `skills_recommend`). Migrables a `engines/signal` sin contrato externo afectado.
3. **`iberinform_processor` vs `data_layer/ingestion/iberinform_ingest`**: dos rutas de ingesta hacia `companies_master` y `master_companies` respectivamente; documentar diferencias antes de unificar.
4. **`publish-to-valuo`**: contrato de salida hacia Valuo; capturar golden tests antes de tocar `routes/master`.

---

## 7. Cobertura de pruebas (estado actual)
Suite smoke global: **203/203 verde**. Por motor: Financial 7 · Signal 8 · Semantic 7 · Recommendation 8 · Strategy 8 · Transaction 12 · Master Layer 7 · Data Layer 3 · (resto: fuentes, skills, taxonomy, ingestión, profiles, e2e Valuo). **Sin regresiones.**

> Recomendación: añadir **tests de contrato (golden)** para los endpoints 🔴 Legacy crítico de Valuo.pro **antes** de iniciar cualquier migración interna (ver `LEGACY_MIGRATION_PLAN.md`).
