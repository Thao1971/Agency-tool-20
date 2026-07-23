# INFORME TÉCNICO — Sprint V2.0 (contrato `arroba.v2`)
**V2-01 · Tipado de DTOs públicos de respuesta · V2-02 · Company/Identity público**
_Versión: `arroba-v2-sprint-v2.0` · 2026-07-12 · Estado: COMPLETADO · `arroba.v1` 100 % compatible._

---

## 1. Resumen ejecutivo
- **V2-01 (P0):** los **53 endpoints** de los 6 motores de inteligencia tienen ahora un **DTO de
  respuesta explícito** en OpenAPI, adjuntado mediante `responses={200: {"model": ...}}`
  (nunca `response_model=`). **El runtime NO cambia**: los DTO documentan, no filtran.
- **V2-02 (P0):** nueva capacidad pública **`POST /api/v2/company-intelligence/identity`**
  (identidad canónica proyectada del Master Record, auth `X-API-Key`) con DTO tipado
  `CompanyIdentityResponse`. Alimenta COMP-1001/1002/1003.
- **`arroba.v1` congelado byte-idéntico**: el builder v1 normaliza (strippea) las respuestas
  tipadas y filtra `components` al set congelado → el snapshot y sus freeze tests siguen verdes.
- **Nuevo contrato `arroba.v2`**: superset TIPADO de v1 + Company/Identity, congelado en
  `contracts/arroba.v2.json` con su propio freeze test.
- **Matriz contrato ↔ runtime: 53/53 MATCH.** SDK tipado auto-generable: **SÍ**.

## 2. Diseño (reglas invariables respetadas)
| Regla del sprint | Cómo se cumple |
|---|---|
| `v1` permanece congelado y operativo | `_build_arroba_openapi()` strippea `responses.200.schema→{}` y filtra `components.schemas` al set del snapshot v1. Hash canónico idéntico. |
| No cambiar el comportamiento del runtime | Se usa `responses={200:{"model":...}}`; los handlers devuelven el mismo dict crudo. Cero `response_model`. |
| DTO tipado en OpenAPI | 91 schemas nombrados en `arroba.v2.json`; cada 200 referencia un `$ref`. |
| Nada de lógica en frontend | Todo en backend (motores + proyección Master). |
| Todo endpoint nuevo con `X-API-Key` + versionado | `company-intelligence` usa `require_service_key` y `capability_version`. |

**Convivencia de contratos**
- `GET /api/v1/openapi/arroba.v1.json` → contrato congelado (respuestas sin tipar, tal cual v1).
- `GET /api/v1/openapi/arroba.v2.json` → contrato TIPADO (6 motores + Company/Identity).
- Docs Swagger: `/api/docs/arroba` (v1) y `/api/docs/arroba/v2` (v2).

## 3. Verificaciones solicitadas
1. **OpenAPI refleja todos los DTOs** → ✅ `test_v2_all_200_responses_are_typed` (0 respuestas sin `$ref`).
2. **Runtime compatible con los DTOs** → ✅ matriz 53/53 MATCH (validación Pydantic sobre payloads reales).
3. **Divergencias contrato↔runtime** → detectadas 12 en el primer pase, todas de **fidelidad de tipo
   del borrador de DTO** (no del runtime). Ver §4.
4. **Matriz Endpoint → DTO → Campos → Runtime → Resultado** → §5.
5. **Política ante MISMATCH** → no se auto-corrigió runtime; la decisión fue **ajustar el CONTRATO
   al runtime** (runtime = fuente congelada, intocable). Documentado en §4.

## 4. MISMATCH detectados y decisión (contrato, nunca runtime)
Todos los desajustes eran del borrador de DTO tipando de más frente al runtime real:

| # | Endpoint(s) | Observación runtime | Decisión (contrato) |
|---|---|---|---|
| 1 | `financial.analyze` → `ratios` | valores son objetos ricos `{value,name,category,formula,explanation,source,available}`, no `float` | `ratios: Dict[str, Any]` |
| 2 | `strategy.*`, `transaction.next_action` → `confidence.factors` | es `dict` (`{evidence_quality,...}`), no lista | `ConfidenceScore.factors: Any` |
| 3 | `signal.analyze` → `signals[].source` | es `dict` (`{engine,fields,source_version}`), no string | `SignalItem.source: Any` |
| 4 | `recommendation.catalog` → `recommendation_roles` | contiene un `null` al final de la lista | `recommendation_roles: List[Optional[str]]` (⚠️ ver nota) |
| 5 | `recommendation.explain` | devuelve `RecommendationItem` + wrapper (`recommendation_version`, `evidence_version`, `engines_used`, `generated_at`, `recommendation_method`) | DTO dedicado `RecommendationExplainResponse` |

> **Nota de calidad de dato (#4):** el runtime incluye un `null` en `recommendation_roles`. No se
> modificó el runtime (regla del sprint). Queda como observación menor para un sprint futuro si se
> desea limpiar el catálogo en origen.

Tras aplicar los ajustes de contrato: **matriz 53/53 MATCH, 0 MISMATCH.**

## 5. Matriz de validación contrato ↔ runtime (53/53)
> Cada fila validada parseando el payload REAL del endpoint contra su DTO con Pydantic
> (detecta campos no documentados, requeridos ausentes y errores de tipo). Fuente:
> `backend/tools/validation_matrix.json` (reproducible con `tools/validate_matrix.py`).

| Endpoint | DTO de respuesta | Campos doc. | Resultado |
|---|---|---|---|
| `company.identity` | `CompanyIdentityResponse` | ✓ | ✅ MATCH |
| `financial.analyze` | `FinancialAnalyzeResponse` | ✓ | ✅ MATCH |
| `financial.ratios_catalog` | `RatiosCatalogResponse` | ✓ | ✅ MATCH |
| `financial.valuation` | `FinancialValuationResponse` | ✓ | ✅ MATCH |
| `recommendation.advisors` | `RecommendationUnavailableResponse` | ✓ | ✅ MATCH |
| `recommendation.buyers` | `RecommendationSetResponse` | ✓ | ✅ MATCH |
| `recommendation.catalog` | `RecommendationCatalogResponse` | ✓ | ✅ MATCH |
| `recommendation.comparables` | `RecommendationSetResponse` | ✓ | ✅ MATCH |
| `recommendation.explain` | `RecommendationExplainResponse` | ✓ | ✅ MATCH |
| `recommendation.investors` | `RecommendationUnavailableResponse` | ✓ | ✅ MATCH |
| `recommendation.matching` | `RecommendationMatchingResponse` | ✓ | ✅ MATCH |
| `recommendation.memory` | `RecommendationMemoryResponse` | ✓ | ✅ MATCH |
| `recommendation.opportunities` | `RecommendationSetResponse` | ✓ | ✅ MATCH |
| `recommendation.sellers` | `RecommendationSetResponse` | ✓ | ✅ MATCH |
| `semantic.catalog` | `SemanticCatalogResponse` | ✓ | ✅ MATCH |
| `semantic.embedding` | `SemanticEmbeddingResponse` | ✓ | ✅ MATCH |
| `semantic.profile` | `SemanticProfileResponse` | ✓ | ✅ MATCH |
| `semantic.profile_schema` | `SemanticProfileSchemaResponse` | ✓ | ✅ MATCH |
| `semantic.search` | `SemanticSearchResponse` | ✓ | ✅ MATCH |
| `semantic.similar` | `SemanticSimilarResponse` | ✓ | ✅ MATCH |
| `signal.analyze` | `SignalAnalyzeResponse` | ✓ | ✅ MATCH |
| `signal.catalog` | `SignalCatalogResponse` | ✓ | ✅ MATCH |
| `signal.history` | `SignalHistoryResponse` | ✓ | ✅ MATCH |
| `signal.opportunities` | `SignalOpportunitiesResponse` | ✓ | ✅ MATCH |
| `signal.sector` | `SignalAggregateResponse` | ✓ | ✅ MATCH |
| `signal.territory` | `SignalAggregateResponse` | ✓ | ✅ MATCH |
| `strategy.acquisition` | `StrategyThesisResponse` | ✓ | ✅ MATCH |
| `strategy.capital` | `StrategyThesisResponse` | ✓ | ✅ MATCH |
| `strategy.catalog` | `StrategyCatalogResponse` | ✓ | ✅ MATCH |
| `strategy.decision` | `StrategyDecisionResponse` | ✓ | ✅ MATCH |
| `strategy.divestment` | `StrategyThesisResponse` | ✓ | ✅ MATCH |
| `strategy.growth` | `StrategyThesisResponse` | ✓ | ✅ MATCH |
| `strategy.lifecycle` | `StrategyThesisResponse` | ✓ | ✅ MATCH |
| `strategy.memory` | `StrategyMemoryResponse` | ✓ | ✅ MATCH |
| `strategy.partnership` | `StrategyThesisResponse` | ✓ | ✅ MATCH |
| `strategy.risk` | `StrategyThesisResponse` | ✓ | ✅ MATCH |
| `strategy.scenarios` | `StrategyScenariosResponse` | ✓ | ✅ MATCH |
| `strategy.thesis` | `StrategyThesisResponse` | ✓ | ✅ MATCH |
| `transaction.catalog` | `TransactionCatalogResponse` | ✓ | ✅ MATCH |
| `transaction.decision` | `TransactionDecisionResponse` | ✓ | ✅ MATCH |
| `transaction.documents` | `DocumentsResponse` | ✓ | ✅ MATCH |
| `transaction.memory` | `TransactionMemoryResponse` | ✓ | ✅ MATCH |
| `transaction.next_action` | `NextActionResponse` | ✓ | ✅ MATCH |
| `transaction.participants` | `ParticipantsResponse` | ✓ | ✅ MATCH |
| `transaction.risk` | `TransactionRiskResponse` | ✓ | ✅ MATCH |
| `transaction.stage` | `StageResponse` | ✓ | ✅ MATCH |
| `transaction.task` | `TaskResponse` | ✓ | ✅ MATCH |
| `transaction.timeline` | `TimelineResponse` | ✓ | ✅ MATCH |
| `transaction.transaction` | `TransactionEndpointResponse` | ✓ | ✅ MATCH |
| `transaction.transaction_create` | `TransactionEndpointResponse` | ✓ | ✅ MATCH |
| `transaction.workflow` | `WorkflowResponse` | ✓ | ✅ MATCH |
| `transaction.workflow_template` | `WorkflowResponse` | ✓ | ✅ MATCH |
| `transaction.workspace` | `WorkspaceResponse` | ✓ | ✅ MATCH |

## 6. ¿SDK tipado auto-generable sin conocimiento manual? — **SÍ**
- `arroba.v2.json` valida como **OpenAPI 3.1** (`openapi-spec-validator`: VALID).
- `datamodel-code-generator` genera **91 clases Pydantic tipadas** directamente del spec, incluidos
  todos los DTOs de respuesta (`CompanyIdentityResponse`, `FinancialAnalyzeResponse`, …) sin
  intervención manual. Igualmente compatible con `openapi-generator` (TS/Python/Go/Java, etc.).
- Los campos dinámicos legítimos (mapas variables como `counts_by_type`, `weights`, `factors`) se
  documentan como `object` (additionalProperties) — fiel al runtime, no inventado.

## 7. Tests (todos verdes)
- `tests/golden/test_arroba_contract_freeze.py` — 4 tests (v1 byte-idéntico) ✅
- `tests/golden/test_arroba_v2_contract_freeze.py` — 6 tests (v2 congelado, 54 paths, 200 tipados,
  solo motores+company, Company/Identity presente) ✅
- **10 passed.**

## 8. Entregables
- **OpenAPI actualizado:** `/api/v1/openapi/arroba.v2.json` (91 schemas, 54 paths).
- **Snapshot congelado:** `backend/contracts/arroba.v2.json`.
- **DTOs:** `backend/routes/engine_schemas.py` + `backend/routes/company_intelligence.py`.
- **Matriz:** `backend/tools/validation_matrix.json` (+ este informe §5).
- **Herramientas reproducibles:** `tools/capture_runtime.py`, `tools/analyze_types.py`, `tools/validate_matrix.py`.
- **Tests:** freeze v1 + freeze v2.
- **Confirmación:** `arroba.v1` sigue **100 % compatible** (hash canónico idéntico, freeze verde).

## 9. Fuera de alcance (según autorización)
No se tocó Ownership, Cash Flow, Valoración avanzada, Governance, Market, Rankings, Registry ni
Documents (Sprints V2.1–V2.4).
