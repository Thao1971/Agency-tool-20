# INTELLIGENCE_API_REFERENCE.md
**Referencia oficial de la Intelligence Layer — Agency Tool**
_Versión: `api-reference-v1` · 2026-06-26 · Estado: **VIGENTE**._

> Documento de referencia oficial para la integración de **arroba.com** y de cualquier consumidor futuro.
> Cubre los 7 motores: **Foundation · Financial · Signal · Semantic · Recommendation · Strategy · Transaction**.
> **Auth de servicio**: todos los motores de inteligencia exponen su API con cabecera `X-API-Key`
> (`ARROBA_SERVICE_API_KEY`). Foundation (data-layer/master) es administrativo (JWT, Platform Console).

## Convenciones
- **Boundary First / Contract First**: cada motor consume aguas abajo **solo por contrato**, nunca recrea conocimiento ni accede a fuentes ajenas.
- **DAG (acíclico)**: `Foundation → Financial → Signal → Semantic → Recommendation → Strategy → Transaction`. Ningún productor depende de un consumidor.
- **Explicabilidad + versionado**: las salidas incluyen `*_version` / `evidence_version` y trazabilidad a la evidencia.
- **Identidad canónica**: todas las empresas se referencian por `master_id` (colección `master_companies`).

---

## 0. Foundation Engine (Master Layer)
- **Propósito**: producir la **única verdad de identidad** de empresa (`master_companies`) consolidando fuentes normalizadas (`norm_company/_financials/_officers/_ownership` + `entity_xref`) y el grafo de relaciones (`master_relationships`).
- **Contrato / versión**: `master-v1`. Productor del resto de la Intelligence Layer.
- **Endpoints**:
  - `POST /api/v1/data-layer/rebuild-master` · `rebuild-embeddings` · `rebuild-signals` · `rebuild-graph`
  - `POST/GET /api/v1/data-layer/jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`
  - Admin Master: `GET /api/v1/master`, `/stats`, `/compare`, `/conflicts`, `/{mc_id}`, `POST /{mc_id}/transition|verify|publish-to-valuo|unpublish-from-valuo`, `/resolve`, `/ingest-from-scraper`, …
- **Auth**: JWT (Platform Console). Los motores leen `master_companies` **in-process**.
- **Dependencias**: ingesta + normalización (`data_layer/ingestion`, `normalize.py`, `accessors.py`).
- **Consumidores**: los 6 motores (arroba), Platform Console. (Valuo.pro usa la capa legacy `companies_master`, no esta.)
- **Cobertura de pruebas**: `test_master_layer.py` (7) + `test_data_layer.py` (3) + ingestión/normalize.
- **Estado de producción**: 🟢 Canónico, estable.

---

## 1. Financial Intelligence Engine
- **Propósito**: responder *"¿cuánto vale / cómo rinde?"* — valoración, KPIs y ratios financieros deterministas.
- **Contrato / versión**: `financial-intelligence-v1`. **Sin estado** (stateless; lee `master_companies`).
- **Endpoints** (`/api/v1/financial-intelligence`, `X-API-Key`):
  - `POST /analyze` — análisis financiero completo (KPIs, ratios, salud).
  - `POST /valuation` — valoración (métodos + supuestos explicables).
  - `GET /ratios/catalog` — catálogo de ratios y método.
- **Dependencias**: Foundation (`master_companies`).
- **Consumidores**: arroba; reutilizado por Recommendation, Strategy y Transaction (por referencia).
- **Cobertura**: `test_financial_intelligence.py` (7).
- **Estado**: 🟢 Canónico, estable. Integración arroba: lista.

---

## 2. Signal Intelligence Engine
- **Propósito**: detectar *señales* de oportunidad/riesgo (corporativas, sectoriales, territoriales) con polaridad y severidad.
- **Contrato / versión**: `signal-intelligence-v1` (reglas DT1–DT8). Persiste en `signals` (+ `signal_thresholds` config `thr-v1`).
- **Endpoints** (`/api/v1/signal-intelligence`, `X-API-Key`; variantes `/view` con JWT para consumo directo desde el navegador de arroba.com):
  - `POST /analyze` · `POST /sector` · `POST /territory` · `POST /opportunities` (+`GET /opportunities/view`, `GET /opportunities/feed/view`)
  - `POST /history` (+`GET /history/view`) · `GET /signal/{signal_id}` (+`/view`) · `GET /catalog` (+`/view`)
  - **v1.1 (2026-07-23, aditivo — ver `SIGNAL_INTELLIGENCE_ENGINE_CONTRACT.md` §6.1)**: `POST /signals` + `GET /signals/view` (listado general, todas las categorías/severidades, sin restricción — distinto de `/opportunities`, acotado a `severity=="opportunity"`); `POST /stats` + `GET /stats/view` (conteos reales vía `count_documents`, no acotados por el límite de paginación); `POST /migrate-dedupe` (migración de una sola vez, corrige señales duplicadas por entrega — ver nota de identidad abajo).
  - Además, dentro del roadmap Q1–T3 (`STRATEGIC_INTELLIGENCE_LAYER_REPORT.md`): `POST /borme-link-backfill`, `POST /baselines/compute`, `GET /baselines/status`, `GET /succession-profile/{identifier}`.
- **Acciones canónicas**: enum `act-v1` (`analyze, monitor, value, compare, investigate, contact, buy, sell, raise_capital, add_to_watchlist, request_due_diligence, consult_advisor`).
- **Identidad de señal (fix 2026-07-23)**: `signal_id` = `hash(master_id + signal_type + engine_version + thresholds_version)` — ya NO incluye `source_version`, para que la misma situación continuada entre entregas de datos se identifique como el mismo documento (antes generaba duplicados mes a mes). Ver `SIGNAL_INTELLIGENCE_ENGINE_CONTRACT.md` §6.1/§10.
- **Dependencias**: Foundation; fuentes ya normalizadas en el Master.
- **Consumidores**: arroba; reutilizado por Recommendation, Strategy, Transaction.
- **Sustituye**: `services/signal_engine.py` (antiguo, aún en convivencia interna).
- **Nota M1 (Sprint 8.2)**: el módulo **legacy master-signals** (distinto de este motor canónico) se relocalizó byte-for-byte a `services/engines/signal/master_signals.py` (computa `signal_score`/`signals[]`/`signal_similarity` sobre `companies_master`, consumido por `rebuild-signals` y `skills/recommend`). `services/signal_engine.py` queda como **shim de convivencia**. NO confundir `master_signals.py` (legacy, companies_master) con `engine.py` (canónico, master_companies).
- **Cobertura**: `test_signal_intelligence.py` (8).
- **Estado**: 🟢 Canónico, estable.

---

## 3. Semantic Intelligence Engine
- **Propósito**: perfil semántico, embeddings y similitud (*"¿a qué se parece / qué es?"*).
- **Contrato / versión**: `semantic-intelligence-v1` (D-S1…D-S6). Persiste en `semantic_profiles`. Usa IA acotada (Emergent LLM Key) como extractor determinista (no inventa aserciones sin evidencia).
- **Endpoints** (`/api/v1/semantic-intelligence`, `X-API-Key`):
  - `POST /profile` · `POST /embedding` · `POST /similar` · `POST /search`
  - `GET /profile/schema` · `GET /catalog`
- **Dependencias**: Foundation.
- **Consumidores**: arroba; reutilizado por Recommendation y Strategy.
- **Cobertura**: `test_semantic_intelligence.py` (7).
- **Estado**: 🟢 Canónico, estable.

---

## 4. Recommendation Intelligence Engine
- **Propósito**: *"¿qué recomendar?"* — comparables, compradores, vendedores, matching, oportunidades, con rol y fit multidimensional.
- **Contrato / versión**: `recommendation-intelligence-v1` (DR1–DR10). Memoria `recommendation_memory` + `recommendation_feedback` (DR9/DR10). 1er motor **consumidor**.
- **Endpoints** (`/api/v1/recommendation-intelligence`, `X-API-Key`):
  - `POST /comparables · /buyers · /sellers · /opportunities · /investors · /advisors · /matching · /explain · /feedback · /memory` · `GET /catalog`
- **Dependencias**: Financial + Signal + Semantic + Foundation + grafo (por referencia; no recrea).
- **Datos no disponibles**: `investors`/`advisors` → `unavailable / source_not_available` (honesto, no inventa).
- **Consumidores**: arroba; reutilizado por Strategy y Transaction.
- **Cobertura**: `test_recommendation_intelligence.py` (8).
- **Estado**: 🟢 Canónico, estable.

---

## 5. Strategy Intelligence Engine
- **Propósito**: *"¿qué estrategia seguir?"* — Strategic Thesis (entidad canónica), escenarios y decisión justificada.
- **Contrato / versión**: `strategy-intelligence-v1` (DT1–DT15). Entidad persistida `strategic_theses` con `lifecycle` y `convert → opportunity/mandate/transaction`.
- **Endpoints** (`/api/v1/strategy-intelligence`, `X-API-Key`):
  - `POST /thesis · /scenarios · /growth · /acquisition · /divestment · /partnership · /capital · /risk · /decision · /lifecycle · /convert · /memory` · `GET /catalog`
- **Composición**: determinista (5 dimensiones + score derivado, confianza multifactor, alternativas, constraints, evidence tree). IA solo redacta narrativa (DT1).
- **Dependencias**: todos los motores anteriores (por referencia).
- **Consumidores**: arroba; **origen** de las operaciones del Transaction Engine (DT15 → Transaction).
- **Cobertura**: `test_strategy_intelligence.py` (8).
- **Estado**: 🟢 Canónico, estable.

---

## 6. Transaction Intelligence Engine (+ Transaction OS)
- **Propósito**: *"¿cómo ejecutamos la tesis?"* — orquesta el ciclo de una operación (Director de M&A). Cima del DAG.
- **Contrato / versión**: `transaction-intelligence-v1` (DTX1–DTX13) sobre `transaction-os-v1` / `state-machine-v1`.
- **Frontera (DTX1)**: el **Transaction OS** posee TODO el estado (`tx_transactions/tx_events/tx_tasks/tx_approvals/tx_documents`); el **Engine** solo orquesta (no mantiene estado). Event Driven First (DTX13): toda mutación emite evento auditado.
- **Endpoints** (`/api/v1/transaction-intelligence`, `X-API-Key`):
  - `POST /transaction · /workflow · /stage · /task · /next-action · /risk · /documents · /participants · /timeline · /decision · /memory · /workspace` · `GET /catalog`
- **Capacidades del Copilot**: next-best-action explicada (explicabilidad obligatoria + confianza de 7 factores DTX7), detección de bloqueos, riesgos, preparación de borradores (DTX4: IA nunca cambia estado ni aprueba), Universal Timeline (DTX11), Workspace agregado (DTX12), approvals de alto riesgo (DTX5).
- **Dependencias**: Strategy (origen `thesis_id`), Financial y Signal (por referencia), Transaction OS.
- **Consumidores**: arroba (futuros Marketplace, Deal Rooms, Copilot UI, Pipeline Board se construirán sobre este OS).
- **Cobertura**: `test_transaction_intelligence.py` (12) + validación E2E `testing_agent` (24/24).
- **Alcance v1 (DTX10)**: Origination → Due Diligence inicial. Diferido a v2: IOI/LOI/SPA/signing/closing/post-closing.
- **Estado**: 🟢 Canónico, estable (Sprint 7 cerrado).

---

## 7. Resumen ejecutivo

| Motor | Versión | Prefijo API | Auth | Persistencia | Tests | Estado |
|---|---|---|---|---|:--:|:--:|
| Foundation | `master-v1` | `/api/v1/data-layer`, `/api/v1/master` | JWT | `master_companies`, `norm_*`, `master_relationships` | 10 | 🟢 |
| Financial | `financial-intelligence-v1` | `/api/v1/financial-intelligence` | X-API-Key | — (stateless) | 7 | 🟢 |
| Signal | `signal-intelligence-v1` | `/api/v1/signal-intelligence` | X-API-Key | `signals`, `signal_thresholds` | 8 | 🟢 |
| Semantic | `semantic-intelligence-v1` | `/api/v1/semantic-intelligence` | X-API-Key | `semantic_profiles` | 7 | 🟢 |
| Recommendation | `recommendation-intelligence-v1` | `/api/v1/recommendation-intelligence` | X-API-Key | `recommendation_memory/_feedback` | 8 | 🟢 |
| Strategy | `strategy-intelligence-v1` | `/api/v1/strategy-intelligence` | X-API-Key | `strategic_theses` | 8 | 🟢 |
| Transaction | `transaction-intelligence-v1` / `transaction-os-v1` | `/api/v1/transaction-intelligence` | X-API-Key | `tx_transactions/tx_events/tx_tasks/tx_approvals/tx_documents` | 12 | 🟢 |

**Suite smoke global: 203/203 verde.** Documentos relacionados: `INTELLIGENCE_LAYER_ARCHITECTURE.md`, `TRANSACTION_OS_ARCHITECTURE.md`, `*_ENGINE_CONTRACT.md` (contratos congelados), `AGENCY_TOOL_AUDIT_FINAL.md`, `LEGACY_MIGRATION_PLAN.md`, `PLATFORM_GOVERNANCE_AND_CONSUMER_AUDIT.md`. Capa adicional construida sobre estos 7 motores (Q1–Q7, E1/E2/E6/E7, T3, Control&Synergy) documentada en `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md`; definición del Copilot de arroba.com (qué cubre, qué falta para "predecir") en `ARROBA_COPILOT_DEFINITION_v1.md`.

---

## 8. Contrato `arroba.v2` (2026-07-12) — DTOs tipados + Company/Identity
> Superset **aditivo** de v1. **No cambia el runtime** de ningún motor. `arroba.v1` sigue **congelado**.
> Manual de integración dedicado: `ARROBA_V2_INTEGRATION_GUIDE.md`.

- **V2-01 · DTOs tipados:** los 53 endpoints de los 6 motores exponen ahora un **schema de respuesta
  nombrado** en OpenAPI (antes `schema: {}`), habilitando **SDK tipado**. Implementación:
  `responses={200:{"model":...}}` (nunca `response_model`; los DTO documentan, no filtran; `extra="allow"`).
  Modelos en `backend/routes/engine_schemas.py`.
- **V2-02 · Company/Identity:** `POST /api/v2/company-intelligence/identity` (auth `X-API-Key`,
  `capability_version=company-intelligence-v2`) → `CompanyIdentityResponse` (identidad canónica proyectada
  del Master: razón social, nombre comercial, CIF, forma jurídica, domicilio, CNAE, web, `capital_social`,
  `employees_total`, `sources`, `data_coverage`). Alimenta COMP-1001/1002/1003. Nunca inventa: ausente → `null`.
- **Contrato/OpenAPI:** `GET /api/v1/openapi/arroba.v2.json` (54 rutas, 91 schemas) · Swagger `/api/docs/arroba/v2`.
  Snapshot congelado `backend/contracts/arroba.v2.json` + freeze test `tests/golden/test_arroba_v2_contract_freeze.py`.
- **Verificación:** matriz contrato↔runtime **53/53 MATCH**; freeze v1 byte-idéntico; 10/10 golden tests;
  backend testing agent 22/22. Informe: `ARROBA_V2_SPRINT_V2.0_REPORT.md`.
- **Estado:** Sprint V2.0 **APROBADO Y CONGELADO**. V2.1 (Ownership/Network/Cash Flow) pendiente (no iniciado).

---

## 9. Notas de integración para arroba.com
1. Autenticar todas las llamadas con `X-API-Key: <ARROBA_SERVICE_API_KEY>`.
2. Referenciar empresas siempre por `master_id` (obtenido del Foundation/Master Layer).
3. Flujo M&A típico: `strategy/thesis` → `transaction-intelligence/transaction (from_thesis)` → `next-action`/`workspace` para orquestar.
4. Respetar la frontera: arroba **produce experiencia**; los motores **producen inteligencia**. No duplicar estado transaccional (vive en el Transaction OS).
5. Cada respuesta incluye versión y evidencia: fijarlas para reproducibilidad.
