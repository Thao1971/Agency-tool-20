# CONTRATO DE INTEGRACIÓN v1.0 — Agency Tool → arroba.com
**Fuente única de verdad para la integración. Sin dependencia de implementación interna.**
_Versión: `arroba-integration-contract-v1` · 2026-07-04 · Estado: **VIGENTE**_

> **Principio rector.** Agency Tool es el **propietario de los datos y de la inteligencia**.
> arroba.com es **exclusivamente consumidor del contrato público**. Ningún desarrollador de
> arroba.com necesita conocer la implementación interna: todo lo que puede consumir está aquí.
>
> **Identidad canónica.** Toda empresa se referencia por `master_id` (colección `master_companies`).
> **Auth de servicio.** Todos los motores de inteligencia se consumen con cabecera
> `X-API-Key: <ARROBA_SERVICE_API_KEY>`. El Master/Foundation es administrativo (JWT, Platform Console).
> **Boundary/Contract First.** El consumidor depende solo del contrato; nunca de fuentes ni de estado interno.
> **DAG acíclico.** `Foundation → Financial → Signal → Semantic → Recommendation → Strategy → Transaction`.

---

## 1. Arquitectura general

Flujo completo de la plataforma:

```
Fuentes externas → Ingesta → Data Layer → Entity Resolution → Master Record
  → Knowledge Graph → Intelligence Engines → API pública → arroba.com
```

| Capa | Responsabilidad | Propietario | Entradas | Salidas |
|---|---|---|---|---|
| **Fuentes externas** | Datos brutos de terceros (Iberinform, BME, BORME, CNMV, INE, DataComex, Contratación Pública, web) | Proveedores externos | — | Ficheros/feeds crudos por proveedor |
| **Ingesta** (`services/data_layer/ingestion/*`, `data_providers`, `providers`) | Cargar, versionar y trazar los ficheros/feeds de cada proveedor sin transformarlos | Agency Tool (Data Layer) | Ficheros crudos + `X-Provider-Key` | Registros crudos + metadatos (`provider_files`, `provider_datasets`, `iberinform_companies`, `bme_companies`, `borme_events`, `cnmv_entities`, `ine_observations`, `datacomex_raw_data`, `public_procurement_contracts`) |
| **Data Layer / Normalización** (`normalize.py`, `accessors.py`) | Convertir lo crudo a un esquema normalizado común, sin resolver identidad todavía | Agency Tool (Data Layer) | Registros crudos por proveedor | `norm_company`, `norm_financials`, `norm_ownership`, `norm_officers` |
| **Entity Resolution** (`data_layer/master/identity_resolver.py` + `entity_bridge.py`) | Resolver la identidad única de cada empresa (CIF → dominio → nombre+provincia) y puentear legacy↔canónico | Agency Tool (Master/Foundation) | Capa normalizada + `entity_xref` | `master_id` determinista, `entity_xref` (mapa fuente→master y bridge legacy↔canónico) |
| **Master Record** (`data_layer/master/master_builder.py`, `master-v1`) | Consolidar el registro canónico único por empresa (merge no destructivo con procedencia) | Agency Tool (Foundation) | Capa normalizada + Entity Resolution | `master_companies` (única verdad de identidad) |
| **Knowledge Graph** (`services/knowledge_graph.py`, `master_relationships`) | Materializar relaciones objetivas de propiedad/gobierno (ownership real, grupos) | Agency Tool (Foundation) | `master_companies.ownership` | `master_relationships`, `ownership.group_id` (union-find) |
| **Intelligence Engines** (`services/engines/*`) | Producir inteligencia derivada: financiera, señales, semántica, recomendación, estrategia, transacción | Agency Tool (Intelligence Layer) | `master_companies` + grafo (solo lectura, por referencia) | KPIs, valoraciones, señales, perfiles, comparables, tesis, operaciones |
| **API pública** (`routes/*_intelligence`, `X-API-Key`) | Exponer los motores tras contrato versionado, autenticado y explicable | Agency Tool | Llamadas del consumidor | JSON versionado (`*_version`, `evidence`) |
| **arroba.com** | Construir la experiencia de producto (UI/UX) sobre el contrato | arroba.com | API pública | Frontend (Entity page, Copilot, Marketplace, Deal Rooms, …) |

**Frontera inviolable:** arroba.com **produce experiencia**; Agency Tool **produce inteligencia y posee el estado**. arroba.com nunca duplica el estado transaccional (vive en el Transaction OS) ni recrea conocimiento.

---

## 2. Inventario completo de entidades

| Entidad | Finalidad | Identificador | Relaciones | Colección | Estado |
|---|---|---|---|---|---|
| **Master Company** | Registro canónico único de empresa (identidad, clasificación, ubicación, tamaño, contacto) | `master_id` (`mc_<hex12>`); clave natural `cif_normalized` | 1—N con financials/ownership/signals/semantic; referida por todos los motores | `master_companies` | 🟢 Canónico |
| **Financial Reports** | Estados financieros consolidados en el Master (`financials.latest` + `history`) | `master_id` + `year` | Subdocumento de Master Company | `master_companies.financials` | 🟢 |
| **Balance Sheets** | Balance (activo/pasivo/patrimonio) derivado por el Financial Engine | `master_id` + `year` | Deriva de Master Company | (stateless; se calcula bajo demanda) | 🟢 |
| **Profit & Loss** | Cuenta de resultados (ingresos, EBITDA, EBIT, resultado neto) | `master_id` + `year` | Deriva de Master Company | (stateless) | 🟢 |
| **Financial Ratios** | Ratios deterministas (liquidez, solvencia, rentabilidad, márgenes) | `master_id` | Deriva de financials del Master | (stateless; catálogo en `ratios/catalog`) | 🟢 |
| **Valuations** | Valoración por múltiplos/DCF con supuestos explicables | `master_id` | Usa Financial + comparables | (stateless bajo demanda) | 🟢 |
| **Valuation History** | Evolución histórica de valoración/KPIs | `master_id` + `year` | Deriva de `financials.history` | `master_companies.financials.history` | 🟡 Parcial (histórico dependiente de cobertura de fuente) |
| **Comparables** | Empresas comparables (peers) por sector/tamaño/geografía | `master_id` | Recommendation + Financial + Semantic | (derivado; memoria en `recommendation_memory`) | 🟢 |
| **M&A Transactions** | Operaciones de M&A normalizadas (histórico de mercado) | id normalizado | Referencia empresas por CIF/nombre | `transactions_normalized` | 🟡 Parcial |
| **Signals** | Señales de oportunidad/riesgo (corporativas, sectoriales, territoriales) con polaridad y severidad | `signal_id` + `master_id` | Producidas por Signal Engine desde Master | `signals`, `signal_thresholds` | 🟢 |
| **Ownership** | Accionistas, matrices, participadas, matriz última, grupo | `master_id` | Subdoc de Master; alimenta Knowledge Graph | `master_companies.ownership`, `norm_ownership` | 🟢 |
| **Governance** | Órganos de administración/consejeros (recuento y detalle) | `master_id` | Subdoc de Master | `master_companies.officers_count`, `norm_officers` | 🟡 Parcial (recuento sí; detalle según fuente) |
| **Documents** | Documentos asociados a una operación (Transaction OS) | `doc_key` + `transaction_id` | Pertenecen a una transacción | `tx_documents` | 🟢 (dentro de Transaction OS) |
| **Activity** | Eventos auditados de una operación (Universal Timeline) | `transaction_id` + evento | Pertenecen a una transacción | `tx_events` | 🟢 |
| **Opportunities** | Oportunidades detectadas (Signal) / convertidas desde tesis (Strategy) | id de oportunidad | Deriva de Signal/Strategy | (derivado; `strategic_theses` al convertir) | 🟢 |
| **Notes** | Notas de usuario sobre entidad/operación | — | — | (no expuesto en contrato público v1) | 🔴 Pendiente |
| **Sector KPIs** | Métricas agregadas de sector/territorio | `cnae_section`/`cnae_code`/`provincia` | Agregan Master + fuentes macro | `sector_intelligence`, `sector_geo_cross`, `geo_intelligence`, `economic_metrics` | 🟡 Parcial |
| **Knowledge Graph** | Relaciones objetivas de propiedad/gobierno entre empresas | `src_master_id`→`dst_master_id` | Aristas entre Master Companies | `master_relationships`, `company_relationships` | 🟢 (estructural fase 1) |
| **Entity Xref** | Mapa no destructivo fuente→master y bridge legacy↔canónico | `(source,id_type,external_id)` / `master_company_id`↔`master_id` | Une proveedores y legacy con canónico | `entity_xref` | 🟢 |
| **Master Record** | Sinónimo operativo de Master Company + procedencia + versionado | `master_id` | = Master Company | `master_companies` | 🟢 |
| **Intelligence Scores** | Scores derivados (signal_score, financial score, fit, confianza) | `master_id` (+ contexto) | Producidos por los motores | (derivados; algunos persistidos en `signals`) | 🟢 |
| **Copilot Context** | Contexto agregado para el Copilot transaccional (workspace + next-action) | `transaction_id` | Agrega Transaction OS + motores por referencia | (derivado en runtime; estado en `tx_*`) | 🟢 (v1: Origination→DD inicial) |
| **Strategic Thesis** | Tesis estratégica canónica con lifecycle y conversión | `thesis_id` | Origen de operaciones (Transaction) | `strategic_theses` | 🟢 |
| **Semantic Profile** | Perfil semántico + embeddings + similitud | `master_id` | Deriva de Master (objeto social) | `semantic_profiles`, `company_embeddings` | 🟢 |
| **Transaction** | Operación de M&A gestionada (estado, etapas, tareas, aprobaciones) | `transaction_id` | Origen `thesis_id`; contiene tasks/docs/events/approvals | `tx_transactions`, `tx_tasks`, `tx_events`, `tx_approvals`, `tx_documents` | 🟢 |
| **Recommendation Memory** | Memoria y feedback de recomendaciones | `recommendation_id` | Referencia Master + tipo | `recommendation_memory`, `recommendation_feedback` | 🟢 |
| **Evidence Items** | Evidencia trazable que respalda outputs | `evidence` id | Referida por outputs de motores | `evidence_items` | 🟢 |

---

## 3. Inventario de colecciones (relevantes para el contrato)

> Convención: `master_id` = id canónico; `master_company_id` = id legacy (`companies_master`). El **bridge** entre ambos vive en `entity_xref`.

| Colección | Finalidad | Claves | Índices clave | Cardinalidad | Relaciones | Estado |
|---|---|---|---|---|---|---|
| `master_companies` | Registro canónico de empresa (Master Record) | `master_id`, `cif_normalized` (única) | `master_id` (u), `cif_normalized` (u), `name_key`, `contact.domain` | ~6.259 | Raíz del grafo; base de todos los motores | 🟢 Canónico |
| `companies_master` | Registro **legacy** (Valuo.pro) | `master_company_id`, `cif_normalized` | `cif_normalized`, `name_key`, `domain` | ~5.353 | Puente a `master_companies` vía `entity_xref` | 🔴 Legacy crítico (NO exponer a arroba) |
| `entity_xref` | Mapa fuente→master + bridge legacy↔canónico | `(source,id_type,external_id)`; `master_company_id`↔`master_id` | `external_id`, `id_type`, `origin`, `bridge_run_id` | ~10.500 | Une proveedores/legacy con canónico | 🟢 Canónico |
| `norm_company` / `norm_financials` / `norm_ownership` / `norm_officers` | Capa normalizada (entrada al Master) | `cif_normalized`, `source` | `cif_normalized`, `source` | ~5.300+ | Interno (NO expuesto) | 🟢 (interno) |
| `master_relationships` | Knowledge Graph estructural (ownership real) | `src_master_id`,`dst_master_id`,`relationship_type` | `src_master_id`, `dst_master_id` | media | Aristas entre Master Companies | 🟢 |
| `company_relationships` | Relaciones de empresa (legacy/aux) | `src`,`dst` | `src` | media | Auxiliar del grafo | 🟡 |
| `signals` | Señales persistidas (Signal Engine) | `signal_id`, `master_id`, `signal_type` | `master_id`, `signal_type` | media | 1—N con Master | 🟢 |
| `signal_thresholds` | Configuración de umbrales (`thr-v1`) | `key` | `key` | baja | Config de Signal | 🟢 |
| `semantic_profiles` | Perfiles semánticos | `master_id` | `master_id` | media | 1—1 con Master | 🟢 |
| `company_embeddings` | Vectores de embeddings | `master_id` | `master_id` | media | 1—1 con Master | 🟢 |
| `recommendation_memory` / `recommendation_feedback` | Memoria y feedback de recomendaciones | `recommendation_id`, `master_id` | `master_id`, `state` | media | Referencia Master | 🟢 |
| `strategic_theses` | Tesis estratégicas | `thesis_id`, `company_master_id`, `state` | `thesis_id`, `company_master_id` | media | Origen de transacciones | 🟢 |
| `tx_transactions` | Operaciones (estado raíz) | `transaction_id`, `organization_id` | `transaction_id`, `organization_id` | media | Contiene tasks/docs/events/approvals | 🟢 |
| `tx_tasks` | Tareas de operación | `task_id`, `transaction_id` | `transaction_id`, `stage` | media | N—1 con transacción | 🟢 |
| `tx_events` | Eventos auditados (timeline) | `transaction_id`, evento | `transaction_id` | alta | N—1 con transacción | 🟢 |
| `tx_approvals` | Aprobaciones de alto riesgo | `transaction_id` | `transaction_id` | baja | N—1 con transacción | 🟢 |
| `tx_documents` | Documentos de operación | `doc_key`, `transaction_id` | `transaction_id` | media | N—1 con transacción | 🟢 |
| `transactions_normalized` | Histórico de M&A de mercado | id normalizado | por empresa/sector | media | Referencia empresas | 🟡 |
| `evidence_items` | Evidencia trazable | `evidence` id | por output | media | Referida por outputs | 🟢 |
| `api_keys` | Claves de servicio (hash) | hash sha256 | hash | baja | Auth `X-API-Key` | 🟢 |
| `analysis_jobs` / `data_layer_jobs` | Cola de jobs reanudables (rebuilds/ingesta) | `job_id` | `job_id`, `status` | media | Administrativo (Console) | 🟢 |
| `sector_intelligence` / `sector_geo_cross` / `geo_intelligence` / `economic_metrics` / `macro_indicators` | Inteligencia agregada de sector/territorio/macro | claves de sector/geo | por dimensión | media | Contexto para señales/estrategia | 🟡 |
| `er_bridge_runs` / `er_bridge_results` / `er_audit_logs` | Auditoría de Entity Resolution/Bridge | `run_id` | `run_id`, `status` | media | Gobernanza (Console) | 🟢 |

> **Colecciones de proveedor** (`iberinform_companies/_financials`, `bme_companies/_signals`, `borme_events/_summaries`, `cnmv_entities/_signals`, `ine_*`, `datacomex_*`, `public_procurement_contracts`, `business_demography`, `provider_files/_datasets`): **internas de ingesta**. arroba.com **no** las consume directamente; su información llega consolidada vía `master_companies` y los motores.

---

## 4. Contrato API (endpoints que consume arroba.com)

**Base URL:** `${AGENCY_TOOL_BASE_URL}` (p. ej. entorno preview/producción). Todas las rutas se prefijan con `/api`.
**Contrato máquina-legible (OpenAPI):**
- `GET /api/v1/openapi/arroba.json` → **contrato público filtrado** para arroba.com (solo los 6 motores, `arroba-integration-contract-v1`). **Usar este para generar cliente/tipos.**
- `GET /api/docs/arroba` → Swagger UI del contrato de arroba.
- `GET /api/v1/openapi.json` / `GET /api/docs` → spec completo **interno** (todas las rutas; uso Console/interno).
**Auth (motores):** cabecera `X-API-Key: <ARROBA_SERVICE_API_KEY>`. Rate-limit: **600 req/min por key**.
**Versión:** cada respuesta incluye `engine_version` / `*_version`. Contratos congelados `*-intelligence-v1`.
**Formato:** JSON UTF-8. Fechas ISO-8601 UTC. Identidad por `master_id` o `cif_normalized`.

### 4.0 Foundation / Master (lectura de identidad) — Auth: JWT (Platform Console)
> arroba.com **no** administra el Master; obtiene la identidad canónica vía los motores. Estos endpoints son administrativos e informativos.

| Método | URL | Propósito |
|---|---|---|
| GET | `/api/v1/master` | Listado paginado de Master Companies |
| GET | `/api/v1/master/{mc_id}` | Detalle de una Master Company |
| GET | `/api/v1/master/stats` | Métricas del Master |
| POST | `/api/v1/master/resolve` | Resolver identidad (devuelve `master_id`, `match_rule`, `confidence`) |

### 4.1 Financial Intelligence — `X-API-Key`
| Método | URL | Body | Devuelve |
|---|---|---|---|
| POST | `/api/v1/financial-intelligence/analyze` | `{ "identifier": "<master_id|cif>" }` | KPIs, ratios, salud financiera, tendencia |
| POST | `/api/v1/financial-intelligence/valuation` | `{ "identifier": "<master_id|cif>" }` | Valoración (métodos + supuestos + rango) |
| GET | `/api/v1/financial-intelligence/ratios/catalog` | — | Catálogo de ratios y su fórmula |

### 4.2 Signal Intelligence — `X-API-Key`
| Método | URL | Body | Devuelve |
|---|---|---|---|
| POST | `/api/v1/signal-intelligence/analyze` | `{ "identifier", "windows?": ["30d","90d"] }` | Señales de la empresa (polaridad, severidad, acciones) |
| POST | `/api/v1/signal-intelligence/sector` | `{ "cnae_section?"|"cnae_code?", "limit":25 }` | Señales de sector |
| POST | `/api/v1/signal-intelligence/territory` | `{ "provincia?", "municipio?", "limit":25 }` | Señales territoriales |
| POST | `/api/v1/signal-intelligence/opportunities` | `{ "cnae_section?","provincia?","signal_types?","sort_by_dimension":"impact","limit":20 }` | Oportunidades priorizadas |
| POST | `/api/v1/signal-intelligence/history` | `{ "identifier","signal_type?" }` | Histórico de señales |
| GET | `/api/v1/signal-intelligence/signal/{signal_id}` | — | Detalle de una señal |
| GET | `/api/v1/signal-intelligence/catalog` | — | Catálogo de tipos de señal y acciones (`act-v1`) |

### 4.3 Semantic Intelligence — `X-API-Key`
| Método | URL | Body | Devuelve |
|---|---|---|---|
| POST | `/api/v1/semantic-intelligence/profile` | `{ "identifier","enrich":false,"with_relationships":false }` | Perfil semántico |
| POST | `/api/v1/semantic-intelligence/embedding` | `{ "identifier" }` | Vector de embedding |
| POST | `/api/v1/semantic-intelligence/similar` | `{ "identifier","limit":10,"same_section":true }` | Empresas similares |
| POST | `/api/v1/semantic-intelligence/search` | `{ "query","limit":10,"cnae_section?" }` | Búsqueda semántica (Universal Search) |
| GET | `/api/v1/semantic-intelligence/profile/schema` | — | Schema del perfil semántico |
| GET | `/api/v1/semantic-intelligence/catalog` | — | Catálogo semántico |

### 4.4 Recommendation Intelligence — `X-API-Key`
| Método | URL | Body | Devuelve |
|---|---|---|---|
| POST | `/api/v1/recommendation-intelligence/comparables` | `{ "identifier","limit":10 }` | Comparables (peers) |
| POST | `/api/v1/recommendation-intelligence/buyers` | `{ "identifier","limit":10 }` | Compradores potenciales |
| POST | `/api/v1/recommendation-intelligence/sellers` | `{ "identifier","limit":10 }` | Vendedores potenciales |
| POST | `/api/v1/recommendation-intelligence/opportunities` | `{ "identifier","limit":10 }` | Oportunidades recomendadas |
| POST | `/api/v1/recommendation-intelligence/investors` | `{ "identifier","limit":10 }` | Inversores (→ `unavailable` si sin fuente) |
| POST | `/api/v1/recommendation-intelligence/advisors` | `{ "identifier","limit":10 }` | Asesores (→ `unavailable` si sin fuente) |
| POST | `/api/v1/recommendation-intelligence/matching` | `{ "a":"<id>","b":"<id>" }` | Fit multidimensional entre dos empresas |
| POST | `/api/v1/recommendation-intelligence/explain` | `{ "target","candidate","recommendation_type":"comparable" }` | Explicación de una recomendación |
| POST | `/api/v1/recommendation-intelligence/feedback` | `{ "recommendation_id","event","outcome?","notes?" }` | Registrar feedback |
| POST | `/api/v1/recommendation-intelligence/memory` | `{ "target?","recommendation_id?","state?" }` | Consultar memoria |
| GET | `/api/v1/recommendation-intelligence/catalog` | — | Catálogo de tipos de recomendación |

### 4.5 Strategy Intelligence — `X-API-Key`
| Método | URL | Body | Devuelve |
|---|---|---|---|
| POST | `/api/v1/strategy-intelligence/thesis` | `{ "identifier","thesis_type?","opportunity_id?","owner":"system" }` | Tesis estratégica (5 dimensiones + score) |
| POST | `/api/v1/strategy-intelligence/scenarios` | `{ "identifier","scenario_types?" }` | Escenarios |
| POST | `/api/v1/strategy-intelligence/growth`·`/acquisition`·`/divestment`·`/partnership`·`/capital`·`/risk` | `{ "identifier" }` | Análisis estratégico por dimensión |
| POST | `/api/v1/strategy-intelligence/decision` | `{ "identifier","type_a","type_b" }` | Decisión justificada entre alternativas |
| POST | `/api/v1/strategy-intelligence/lifecycle` | `{ "thesis_id","state","result?","learning?" }` | Transición de ciclo de vida de la tesis |
| POST | `/api/v1/strategy-intelligence/convert` | `{ "thesis_id","target":"opportunity|mandate|transaction" }` | Convertir tesis en operación |
| POST | `/api/v1/strategy-intelligence/memory` | `{ "company_master_id?","thesis_id?","state?","thesis_type?" }` | Memoria de tesis |
| GET | `/api/v1/strategy-intelligence/catalog` | — | Catálogo de tipos de tesis/escenario |

### 4.6 Transaction Intelligence (+ Transaction OS) — `X-API-Key`
| Método | URL | Body | Devuelve |
|---|---|---|---|
| POST | `/api/v1/transaction-intelligence/transaction` | crear: `{ "thesis_id","workflow_name?","organization_id":"org_default","parties?","actor":"platform" }` · consultar: `{ "transaction_id" }` | Operación (estado, etapa, metadatos) |
| POST | `/api/v1/transaction-intelligence/workflow` | `{ "transaction_id?"|"workflow_name?" }` | Workflow/etapas (instancia o plantilla) |
| POST | `/api/v1/transaction-intelligence/stage` | `{ "transaction_id","stage?"|"event?","actor","actor_role" }` | Avanzar etapa / aplicar evento (con guards) |
| POST | `/api/v1/transaction-intelligence/task` | crear: `{ "transaction_id","title","stage?","assignee?" }` · cerrar: `{ "task_id","action":"complete" }` | Tarea |
| POST | `/api/v1/transaction-intelligence/next-action` | `{ "transaction_id" }` | Next-best-action explicada (Copilot) |
| POST | `/api/v1/transaction-intelligence/risk` | `{ "transaction_id" }` | Riesgos y bloqueos |
| POST | `/api/v1/transaction-intelligence/documents` | `{ "transaction_id","doc_key?" }` | Documentos de la operación |
| POST | `/api/v1/transaction-intelligence/participants` | `{ "transaction_id" }` | Participantes |
| POST | `/api/v1/transaction-intelligence/timeline` | `{ "transaction_id" }` | Universal Timeline (eventos auditados) |
| POST | `/api/v1/transaction-intelligence/decision` | `{ "transaction_id" }` | Decisión de operación |
| POST | `/api/v1/transaction-intelligence/memory` | `{ "transaction_id?" }` | Memoria de operación |
| POST | `/api/v1/transaction-intelligence/workspace` | `{ "transaction_id" }` | Workspace agregado (Copilot/Deal Room) |
| GET | `/api/v1/transaction-intelligence/catalog` | — | Catálogo de workflows/etapas/acciones |

### 4.7 Convenciones transversales (todos los endpoints)
- **Autenticación:** `X-API-Key` obligatoria en motores. `401` si falta/invalida; `429` si supera rate-limit (600/min).
- **Parámetros de identidad:** `identifier` acepta `master_id` **o** `cif_normalized`.
- **Paginación:** endpoints de listado aceptan `limit` (y `skip`/`page` donde aplique en Master). Por defecto `limit` documentado por endpoint.
- **Códigos de error estándar:** `200` OK · `400` request inválida · `401` no autenticado · `403` sin permiso · `404` entidad no encontrada (`master_not_found`, `transaction_not_found`, …) · `409` conflicto de estado (guards de la state-machine) · `422` validación de payload · `429` rate-limit · `500` error interno. Datos no disponibles → respuesta honesta `{"status":"unavailable","reason":"source_not_available"}` (no inventa).
- **Versionado en respuesta:** cada payload incluye `engine_version`/`*_version` y, cuando aplica, `evidence`/`evidence_version` para reproducibilidad.

---

## 5. Matriz de consumo de arroba.com

> Cada bloque de UI de arroba.com se alimenta EXCLUSIVAMENTE del/los endpoint(s) indicados.

| Bloque arroba.com | Endpoint(s) que lo alimenta(n) | Estado |
|---|---|---|
| **Entity Header / Hero** | `GET /master/{mc_id}` (identidad, CNAE, ubicación) + `financial-intelligence/analyze` | 🟢 |
| **KPIs** | `POST /financial-intelligence/analyze` (`kpis`) | 🟢 |
| **Revenue History** | `POST /financial-intelligence/analyze` (`kpis.evolution` / `financials.history`) | 🟡 |
| **EBITDA History** | `POST /financial-intelligence/analyze` (`kpis.evolution.ebitda`) | 🟡 |
| **P&L (Cuenta de resultados)** | `POST /financial-intelligence/analyze` (`income_statement`/`statements`) | 🟢 |
| **Balance** | `POST /financial-intelligence/analyze` (`balance_sheet`) | 🟢 |
| **Ratios** | `POST /financial-intelligence/analyze` (`ratios`) + `GET /financial-intelligence/ratios/catalog` | 🟢 |
| **Valuation** | `POST /financial-intelligence/valuation` | 🟢 |
| **Comparables** | `POST /recommendation-intelligence/comparables` (+ `explain`) | 🟢 |
| **Signals** | `POST /signal-intelligence/analyze` (+ `history`, `signal/{id}`) | 🟢 |
| **Ownership** | `GET /master/{mc_id}` (`ownership`) + `master_relationships` (grafo) | 🟢 |
| **Governance** | `GET /master/{mc_id}` (`officers_count`) | 🟡 |
| **Documents** | `POST /transaction-intelligence/documents` | 🟢 (en operación) |
| **Activity / Timeline** | `POST /transaction-intelligence/timeline` | 🟢 |
| **Copilot** | `POST /transaction-intelligence/next-action` + `/workspace` + `/risk` | 🟢 (v1: Origination→DD) |
| **Universal Search** | `POST /semantic-intelligence/search` | 🟢 |
| **Similar / "A qué se parece"** | `POST /semantic-intelligence/similar` | 🟢 |
| **Buyers / Sellers** | `POST /recommendation-intelligence/buyers` · `/sellers` | 🟢 |
| **Matching** | `POST /recommendation-intelligence/matching` | 🟢 |
| **Strategy / Thesis** | `POST /strategy-intelligence/thesis` (+ `scenarios`, `decision`) | 🟢 |
| **Marketplace** | `POST /recommendation-intelligence/opportunities` + `signal-intelligence/opportunities` + Transaction OS | 🟠 En desarrollo |
| **Transaction OS (Deal Rooms)** | `POST /transaction-intelligence/transaction` · `/workflow` · `/stage` · `/task` · `/participants` · `/documents` · `/workspace` | 🟢 (v1) |
| **Watchlist** | `POST /recommendation-intelligence/memory` + `signal-intelligence/analyze` | 🟡 Parcial |
| **Alertas** | `POST /signal-intelligence/analyze` + `/opportunities` (polling/subscripción) | 🟡 Parcial |
| **Sector / Territory Intel** | `POST /signal-intelligence/sector` · `/territory` | 🟡 |

---

## 6. Schema completo por endpoint (campos disponibles)

> Campos observados en los motores canónicos. Todos los objetos incluyen `engine_version` y, cuando aplica, `generated_at`, `data_source`/`source`, `explainability`/`explanation`, `confidence`.

### 6.1 `master_companies` (Master Record) — devuelto por `GET /master/{mc_id}`
```
master_id, cif_normalized, status(active|merged|deprecated),
identity{ legal_name, commercial_name, aliases[], cif, country },
classification{ cnae_code, cnae_description, cnae_division, cnae_section },
location{ provincia, municipio, codigo_postal, pais },
contact{ web, domain },
name_key,
size{ employees_total, capital_social },
financials{
  latest{ year, basis(individual|consolidated), revenue, ebitda, ebitda_margin,
          equity, total_assets, net_income, operating_income } | null,
  history[ { year, basis, revenue, ebitda, net_income } ]
},
ownership{
  shareholders[ { cif, name, pct } ], parents[ { cif, name, pct } ],
  ultimate_parent{ cif, name, pct } | null, investees[ { cif, name, pct } ],
  group_id
},
officers_count, objeto_social,
provenance{ <field>: [ { source, value, observed_at, confidence } ] },
sources[ { source, external_id, source_version, source_file_id, ingested_at } ],
pipeline_version, source_hash, dirty, created_at, updated_at, built_at
```

### 6.2 `POST /financial-intelligence/analyze`
```
master_id, cif_normalized, identity{...}, cnae_code, cnae_section, provincia,
has_financials, financials_source, data_source, source_version, audited, basis, year, years,
kpis{ revenue, ebitda, ebitda_margin, ebit, ebit_margin, net_income, net_margin, gross_margin,
      employees_total, revenue_per_employee, revenue_growth_yoy, revenue_cagr,
      ebitda_growth_yoy, evolution{ revenue[], ebitda[], net_income[] } },
income_statement{ revenue, supplies, personnel_costs, depreciation, operating_income,
                  financial_expenses, ebit, ebitda, net_income },
balance_sheet{ current_assets, non_current_assets, total_assets, cash,
               current_liabilities, non_current_liabilities, total_liabilities,
               st_debt, lt_debt, financial_debt, equity },
ratios{ current_ratio, debt_ratio, debt_to_equity, interest_coverage,
        roe, roa, ebitda_margin, net_margin, capital_intensity, ... (ver ratios/catalog) },
financial_quality{ score, assessment, strengths[], weaknesses[], risks[] },
solvency, trend, anomaly, deterioration, size_band,
explainability{ rules_applied[], formula, lineage, hypotheses[] },
engine_version, generated_at
```

### 6.3 `POST /financial-intelligence/valuation`
```
master_id, valuation{ method, multiple, multiple_basis, enterprise_value, equity_value,
                      range{ low, high }, subject_ebitda_margin_percentile },
comparables{ peers[ { master_id, name, cnae_section, same_province, ebitda_margin, multiple } ],
             criteria, count },
assumptions/criteria, confidence, explanation, engine_version, generated_at
```

### 6.4 `POST /signal-intelligence/analyze`
```
identifier→master_id, signals[ { signal_id, signal_type, polarity(positive|negative|neutral),
  severity, score, window, dimension(impact|urgency|...), rule, rules_applied[],
  actions[]  // enum act-v1: analyze,monitor,value,compare,investigate,contact,buy,sell,
             //             raise_capital,add_to_watchlist,request_due_diligence,consult_advisor
  evidence, observed_at } ],
signal_score, summary{ positive, negative, neutral }, engine_version, generated_at
```
`/sector`·`/territory`·`/opportunities`: `{ items[], count, criteria, engine_version }`.
`/catalog`: tipos de señal, dimensiones y `act-v1`.

### 6.5 `POST /semantic-intelligence/profile` · `/similar` · `/search`
```
profile: { master_id, semantic_profile{ activities[], products[], markets[], keywords[],
           value_proposition, business_model }, embedding_version, ai_used,
           relationships?[], evidence, engine_version }
similar: { items[ { master_id, name, cnae_section, similarity_score } ], count, engine_version }
search:  { results[ { master_id, name, similarity_score, snippet } ], count, query, engine_version }
```

### 6.6 `POST /recommendation-intelligence/*`
```
comparables|buyers|sellers|opportunities|investors|advisors:
  { target→master_id, recommendation_type, items[ { master_id, name, fit_score,
    dimensions{ sector, size, geography, financial, semantic }, role, rationale,
    recommendation_id } ] | { status:"unavailable", reason:"source_not_available" },
    count, engine_version }
matching: { a, b, fit_score, dimensions{...}, explanation, engine_version }
explain:  { recommendation_id, factors[ { name, weight, contribution } ], narrative }
feedback: { recommendation_id, event, stored:true }
memory:   { items[], count }
```

### 6.7 `POST /strategy-intelligence/*`
```
thesis: { thesis_id, company_master_id, thesis_type, state(lifecycle),
  dimensions{ 5 dimensiones + score }, confidence{ 7-factor }, alternatives[], constraints[],
  evidence_tree, narrative(IA), scenarios?[], engine_version, created_at }
decision: { type_a, type_b, chosen, justification, scores{...} }
lifecycle: { thesis_id, state, result?, learning?, transitioned:true }
convert: { thesis_id, target, created_ref_id }  // opportunity|mandate|transaction
```

### 6.8 `POST /transaction-intelligence/*`
```
transaction: { transaction_id, organization_id, thesis_id?, workflow_name, current_stage,
  state, parties[], created_at, updated_at, engine_version }
workflow: { transaction_id?, workflow_name, stages[ { key, name, order, guards[] } ] }
stage:  { transaction_id, from_stage, to_stage, event?, applied:true, guards_passed[] }
task:   { task_id, transaction_id, title, stage, assignee, status, created_at }
next-action: { transaction_id, recommended_action, why, confidence{ 7-factor }, blockers[],
  alternatives[], evidence }
risk: { transaction_id, risks[ { type, severity, description } ], blockers[] }
documents: { transaction_id, items[ { doc_key, name, status, url? } ], count }
participants: { transaction_id, participants[ { name, role } ] }
timeline: { transaction_id, events[ { event, actor, actor_role, at, payload } ], count }
workspace: { transaction_id, summary, tasks[], documents[], risks[], next_action, timeline[] }
```

> **Schema exhaustivo por motor congelado:** ver `FINANCIAL_INTELLIGENCE_ENGINE_CONTRACT.md`,
> `SIGNAL_INTELLIGENCE_ENGINE_CONTRACT.md`, `SEMANTIC_INTELLIGENCE_ENGINE_CONTRACT.md`,
> `RECOMMENDATION_INTELLIGENCE_ENGINE_CONTRACT.md`, `STRATEGY_INTELLIGENCE_ENGINE_CONTRACT.md`,
> `TRANSACTION_INTELLIGENCE_ENGINE_CONTRACT.md`, `MASTER_LAYER_CONTRACT.md`. Estos contratos son
> **normativos** y prevalecen en caso de duda de campo.

---

## 7. Estado de implementación

| Capacidad | Estado |
|---|---|
| Master Record (`master_companies`, `master-v1`) | 🟢 Implementada |
| Entity Resolution + Bridge (cobertura 98,17%) | 🟢 Implementada |
| Knowledge Graph estructural (ownership real) | 🟢 Implementada (fase 1) |
| Financial Intelligence (analyze, valuation, ratios) | 🟢 Implementada |
| Signal Intelligence (analyze, sector, territory, opportunities, history) | 🟢 Implementada |
| Semantic Intelligence (profile, embedding, similar, search) | 🟢 Implementada |
| Recommendation Intelligence (comparables, buyers, sellers, matching, explain) | 🟢 Implementada |
| Recommendation: investors / advisors | 🟡 Parcial (responde `unavailable` sin fuente) |
| Strategy Intelligence (thesis, scenarios, decision, lifecycle, convert) | 🟢 Implementada |
| Transaction Intelligence + Transaction OS (Origination → DD inicial) | 🟢 Implementada (v1) |
| Transaction v2 (IOI/LOI/SPA/signing/closing/post-closing) | 🔴 Pendiente (diferido a v2, DTX10) |
| Valuation History / Governance detalle / Sector KPIs | 🟡 Parcial (dependen de cobertura de fuente) |
| M&A Transactions (`transactions_normalized`) | 🟡 Parcial |
| Marketplace | 🟠 En desarrollo (arquitectura Transaction OS lista) |
| Deal Rooms UI | 🟠 En desarrollo |
| Copilot transaccional UI | 🟠 En desarrollo (API `next-action`/`workspace` lista) |
| Watchlist / Alertas (suscripción push) | 🔴 Pendiente (hoy vía polling) |
| Notes | 🔴 Pendiente |
| Activación del flag `canonical` en producción | 🔴 Pendiente (bloqueado hasta resolver 25 casos revisión manual) |

---

## 8. Estrategia de sincronización

| Entidad | Origen | Frecuencia | Incremental / Full | Invalidación | Caché | SLA | Versionado |
|---|---|---|---|---|---|---|---|
| Master Company | `rebuild_master` desde capa normalizada | Al ingerir fuente nueva / bajo demanda | Incremental (`source_hash`) + full opcional | `dirty=true` marca recálculo | Cache-first en engine; TTL corto | Lectura < 300 ms típica | `pipeline_version` (`master-v1`) + `source_version` |
| Financials / Ratios / Valuation | Stateless desde Master | Bajo demanda (por request) | — (se recalcula) | Al cambiar Master (`updated_at`) | Recomendado cliente 5–15 min | Cálculo < 1 s | `financial-intelligence-v1` |
| Signals | `rebuild-signals` / Signal Engine | Batch (rebuild) + on-demand | Incremental por `master_id dirty` | Nueva señal o cambio de Master | Persistido en `signals` | Batch diario / on-demand | `signal-intelligence-v1`, `thr-v1` |
| Semantic Profile / Embeddings | `rebuild-embeddings` | Batch + on-demand (`enrich`) | Incremental | Cambio de objeto social | Persistido | Batch bajo demanda | `semantic-intelligence-v1` |
| Recommendations | Derivado (Financial+Signal+Semantic) | On-demand | — | Al cambiar inputs | Memoria `recommendation_memory` | < 1 s | `recommendation-intelligence-v1` |
| Strategic Thesis | Persistida | On-demand + lifecycle | Incremental (estado) | Transición de lifecycle | Persistido | < 1 s | `strategy-intelligence-v1` |
| Transaction / OS | Event-driven (Transaction OS) | Tiempo real (por evento) | Incremental (append events) | Cada mutación emite evento | Persistido `tx_*` | Tiempo real | `transaction-os-v1` / `transaction-intelligence-v1` |
| Knowledge Graph | `rebuild-graph` | Batch | Incremental | Cambio de ownership | Persistido `master_relationships` | Batch | `master-v1` |

**Reglas de caché para arroba.com:** cachear por `master_id` + `engine_version`; invalidar al detectar cambio de `engine_version` o `updated_at` del Master. El estado transaccional **no se cachea** en cliente (event-driven, fuente de verdad en el OS).

---

## 9. Roadmap

**Sprint actual (disponible ya):**
- Master Record canónico + Entity Resolution (98,17% cobertura).
- Financial, Signal, Semantic, Recommendation, Strategy, Transaction (v1) — todos 🟢.
- Universal Search, Similar, Comparables, Matching, Thesis, Transaction OS (Origination→DD).

**Sprint siguiente:**
- Marketplace (sobre `recommendation/opportunities` + `signal/opportunities` + Transaction OS).
- Deal Rooms UI y Copilot transaccional UI (API `next-action`/`workspace`/`risk` ya disponible).
- Resolución de los 25 casos de revisión manual del Entity Resolution → prerrequisito para activar `canonical`.

**Sprint futuro:**
- Transaction v2 (IOI/LOI/SPA/signing/closing/post-closing).
- Watchlist/Alertas con suscripción push (hoy polling).
- Notes; Governance detallado; Sector KPIs ampliados; M&A Transactions enriquecidas.
- Knowledge Graph v2 (relaciones semánticas de alta confianza).

---

## 10. Contrato de estabilidad

**🔒 Congelado (no cambia dentro de la versión mayor):**
- Prefijos y versiones de motores: `/api/v1/{financial|signal|semantic|recommendation|strategy|transaction}-intelligence` con `*-intelligence-v1`.
- Identidad por `master_id` / `cif_normalized`.
- Auth `X-API-Key`; códigos de error estándar (§4.7); presencia de `engine_version` en toda respuesta.
- Campos publicados del Master Record (§6.1) y de cada motor (§6.2–6.8): **no se eliminan ni se renombran**.
- Semántica de la state-machine de Transaction OS (guards, eventos auditados).

**✅ Cambios compatibles (aditivos, permitidos sin aviso de ruptura):**
- Añadir **nuevos endpoints** o **nuevos campos opcionales** en las respuestas.
- Añadir **nuevos tipos** en enums abiertos (señales, acciones) — el cliente debe ignorar los desconocidos.
- Añadir **nuevas fuentes/procedencia** sin cambiar la forma del campo.
- Mejorar precisión de scores manteniendo rango y significado.

**⛔ Cambios que ROMPEN el contrato (exigen nueva versión mayor `*-v2` con convivencia):**
- Eliminar/renombrar un campo o endpoint publicado.
- Cambiar el tipo de un campo (p. ej. `float`→`string`) o su unidad/semántica.
- Cambiar códigos de error o el significado de un estado.
- Cambiar el identificador canónico o el esquema de autenticación.
- Cambiar umbrales que alteren la clasificación observable sin nueva versión.

> Todo cambio incompatible convive con la versión anterior hasta que arroba.com valide y migre (política de gobernanza §1 de `PLATFORM_GOVERNANCE_AND_CONSUMER_AUDIT.md`).

---

## 11. Matriz final (dato funcional → colección → entidad → endpoint → campo → bloque arroba → estado → observaciones)

| Dato funcional | Colección origen | Entidad | Endpoint | Campo | Bloque arroba.com | Estado | Observaciones |
|---|---|---|---|---|---|---|---|
| Nombre legal | `master_companies` | Master Company | `GET /master/{mc_id}` | `identity.legal_name` | Entity Header/Hero | 🟢 | Clave `cif_normalized` |
| CIF | `master_companies` | Master Company | `GET /master/{mc_id}` | `identity.cif` / `cif_normalized` | Hero | 🟢 | — |
| Sector (CNAE) | `master_companies` | Master Company | `GET /master/{mc_id}` | `classification.cnae_code/_section` | Hero / Sector | 🟢 | — |
| Ubicación | `master_companies` | Master Company | `GET /master/{mc_id}` | `location.{provincia,municipio}` | Hero | 🟢 | — |
| Web/Dominio | `master_companies` | Master Company | `GET /master/{mc_id}` | `contact.{web,domain}` | Hero | 🟢 | — |
| Empleados | `master_companies` | Master Company | `financial-intelligence/analyze` | `kpis.employees_total` | KPIs | 🟢 | — |
| Ingresos | `master_companies` | Financial Reports | `financial-intelligence/analyze` | `kpis.revenue` | KPIs / Revenue History | 🟢 | Histórico en `evolution.revenue` |
| EBITDA | `master_companies` | Financial Reports | `financial-intelligence/analyze` | `kpis.ebitda`,`ebitda_margin` | KPIs / EBITDA History | 🟢 | — |
| Crecimiento (YoY/CAGR) | `master_companies` | Financial Reports | `financial-intelligence/analyze` | `kpis.revenue_growth_yoy`,`revenue_cagr` | KPIs | 🟡 | Depende de histórico |
| Cuenta de resultados | `master_companies` | Profit & Loss | `financial-intelligence/analyze` | `income_statement.*` | P&L | 🟢 | — |
| Balance | `master_companies` | Balance Sheets | `financial-intelligence/analyze` | `balance_sheet.*` | Balance | 🟢 | — |
| Ratios | `master_companies` | Financial Ratios | `financial-intelligence/analyze` + `ratios/catalog` | `ratios.*` | Ratios | 🟢 | Fórmulas en catálogo |
| Valoración | `master_companies` | Valuations | `financial-intelligence/valuation` | `valuation.{enterprise_value,equity_value,range}` | Valuation | 🟢 | Explicable |
| Historial de valoración | `master_companies.financials.history` | Valuation History | `financial-intelligence/analyze` | `kpis.evolution` | Valuation | 🟡 | Según cobertura de fuente |
| Comparables | derivado + `recommendation_memory` | Comparables | `recommendation-intelligence/comparables` | `items[].fit_score,dimensions` | Comparables | 🟢 | `explain` para detalle |
| Señales | `signals` | Signals | `signal-intelligence/analyze` | `signals[].{type,polarity,severity,actions}` | Signals / Alertas | 🟢 | `history` para evolución |
| Oportunidades | `signals` + derivado | Opportunities | `signal-intelligence/opportunities` · `recommendation-intelligence/opportunities` | `items[]` | Marketplace / Alertas | 🟠 | Marketplace en desarrollo |
| Propiedad | `master_companies.ownership` + `master_relationships` | Ownership | `GET /master/{mc_id}` | `ownership.{shareholders,parents,ultimate_parent,group_id}` | Ownership | 🟢 | Grafo en `master_relationships` |
| Gobierno | `master_companies` | Governance | `GET /master/{mc_id}` | `officers_count` | Governance | 🟡 | Detalle según fuente |
| Perfil semántico | `semantic_profiles` | Semantic Profile | `semantic-intelligence/profile` | `semantic_profile.*` | Hero / Search | 🟢 | — |
| Similares | `company_embeddings` | Semantic Profile | `semantic-intelligence/similar` | `items[].similarity_score` | "A qué se parece" | 🟢 | — |
| Búsqueda universal | `company_embeddings` | Semantic Profile | `semantic-intelligence/search` | `results[]` | Universal Search | 🟢 | — |
| Compradores/Vendedores | derivado | Comparables/Recos | `recommendation-intelligence/buyers`·`sellers` | `items[].fit_score` | Buyers/Sellers/Matching | 🟢 | — |
| Matching A↔B | derivado | Recos | `recommendation-intelligence/matching` | `fit_score,dimensions` | Matching | 🟢 | — |
| Tesis estratégica | `strategic_theses` | Strategic Thesis | `strategy-intelligence/thesis` | `dimensions,confidence,scenarios` | Strategy | 🟢 | `convert`→operación |
| Operación (deal) | `tx_transactions` | Transaction | `transaction-intelligence/transaction` | `current_stage,state,parties` | Transaction OS / Deal Room | 🟢 | Origen `thesis_id` |
| Tareas de deal | `tx_tasks` | Transaction | `transaction-intelligence/task` | `task_id,status,stage` | Deal Room | 🟢 | — |
| Documentos de deal | `tx_documents` | Documents | `transaction-intelligence/documents` | `items[].doc_key,status` | Documents | 🟢 | — |
| Timeline / Actividad | `tx_events` | Activity | `transaction-intelligence/timeline` | `events[].{event,actor,at}` | Activity / Timeline | 🟢 | Event-driven |
| Next-best-action | derivado (OS + motores) | Copilot Context | `transaction-intelligence/next-action` | `recommended_action,why,confidence,blockers` | Copilot | 🟢 | Explicabilidad obligatoria |
| Workspace del deal | agrega `tx_*` | Copilot Context | `transaction-intelligence/workspace` | `summary,tasks,documents,risks,next_action` | Copilot / Deal Room | 🟢 | — |
| Riesgos del deal | derivado | Copilot Context | `transaction-intelligence/risk` | `risks[],blockers[]` | Copilot | 🟢 | — |
| Aprobaciones | `tx_approvals` | Transaction | `transaction-intelligence/stage` (guards) | `approvals` | Deal Room | 🟢 | Alto riesgo (DTX5) |
| Watchlist | `recommendation_memory` | Recos Memory | `recommendation-intelligence/memory` | `items[],state` | Watchlist | 🟡 | Push diferido |
| KPIs de sector | `sector_intelligence`,`sector_geo_cross` | Sector KPIs | `signal-intelligence/sector`·`territory` | `items[]` | Sector Intel | 🟡 | Cobertura parcial |
| Evidencia/trazabilidad | `evidence_items` | Evidence Items | (embebida en cada motor) | `evidence`,`*_version` | (todos) | 🟢 | Reproducibilidad |

---

## Objetivo cumplido
Con este documento, cualquier desarrollador de arroba.com puede construir el frontend completo
**sin conocer la implementación interna** de Agency Tool: dispone de la arquitectura, entidades,
colecciones, endpoints, schemas, matriz de consumo, estados, estrategia de sincronización, roadmap
y garantías de estabilidad. **Agency Tool posee los datos; arroba.com consume el contrato público.**
Ambos productos evolucionan de forma desacoplada mientras se respete el §10 (Contrato de estabilidad).
