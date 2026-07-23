# ARROBA_INTEGRATION_READINESS_CERT.md
**Certificación de preparación — Agency Tool como proveedor de datos para arroba.com**
_Versión: `readiness-cert-v1` · 2026-07-04 · Verificación EN VIVO contra el entorno preview._

> Objetivo: certificar que Agency Tool está listo para que arroba.com inicie la integración
> **sin cambios posteriores del contrato público**. No se desarrolló funcionalidad nueva ni se
> modificó el contrato. Todas las comprobaciones se ejecutaron contra la URL real con la API Key real.

---

## Veredicto global: ✅ **APTO PARA INICIAR INTEGRACIÓN** (con 3 puntos de atención operativa, no de contrato)

Los 6 motores están desplegados, autenticados, versionados y devuelven **datos reales**. El contrato
de schemas está **congelado** (`*-intelligence-v1`) y respaldado por tests (Golden 111 + Smoke 203).
Los 3 puntos de atención son **operativos/entorno** (no rompen el contrato ni exigen cambiarlo):
exposición pública del OpenAPI, cobertura actual del universo canónico y nombre del campo de versión.

---

## 1. Confirmaciones solicitadas

| # | Punto | Resultado | Detalle |
|---|---|---|---|
| 1 | **Base URL dev/staging** | ✅ | Preview: `https://data-factory-hub.preview.emergentagent.com`. **Producción: `https://agencias.wearebudadvisors.com`** (contrato v1 desplegado y verificado, 200). Ambos con idéntica estructura `/api/...`. |
| 2 | **API Key de servicio** | ✅ | `X-API-Key` activa y funcional. Se siembra desde `ARROBA_SERVICE_API_KEY` (env) y se almacena **hasheada (sha256)** en `db.api_keys`. Sin key → `401`; key inválida → `401` (verificado). ⚠️ Regenerar y entregar por canal seguro antes de producción. |
| 3 | **Endpoints desplegados** | ✅ | Los 6 motores responden `200` con datos reales vía `/api` público (Financial, Signal, Semantic, Recommendation, Strategy, Transaction verificados en vivo). |
| 4 | **OpenAPI = implementación** | 🟡 Parcial | El spec **interno** es 3.1.0 y coincide EXACTAMENTE con la implementación (496 rutas; conteos por motor: financial 3, signal 7, semantic 6, recommendation 11, strategy 13, transaction 13, master 22). **PERO** `/openapi.json` y `/docs` **no son accesibles públicamente**: al no ir bajo `/api`, el ingress los enruta al frontend y devuelven el HTML de la SPA. arroba.com no puede autodescargar el spec hoy. → Ver "Atención A". |
| 5 | **Datos reales, no placeholders** | ✅ (con matiz) | Valores reales confirmados (ej. `mc_4a5347d2c39b` "TRANSPORTS LA MUNTANYESA": `revenue=2.722.872,85 €`, ratios, señales, perfil semántico, comparables). `investors`/`advisors` devuelven honestamente `status:"unavailable", reason:"source_not_available"` (por diseño, no placeholder). ⚠️ El universo canónico actual es de **1.000 empresas** (muestra Iberinform); la proyección M3-2b (→6.259) **no persistió** en este entorno. → Ver "Atención B". |
| 6 | **Versionado (`engine_version`) operativo** | ✅ (con matiz) | Presente y operativo en toda respuesta. Nombre del campo **por motor**: Financial/Signal/Semantic/Transaction usan `engine_version`; Recommendation usa `recommendation_version`; Strategy usa `strategy_version` (+ mapa `evidence_version` con versión de cada dependencia). Cumple el contrato (§4.7 admite `engine_version`/`*_version`). → Ver "Atención C". |
| 7 | **Rate limit definitivo y cómo aplica** | ✅ | **600 req/min POR API Key** (`ANALYZE_RATE_LIMIT_PER_MIN=600`). Algoritmo: token-bucket **por `key_hash`** (no por organización ni por IP). Excedente → `429` con cabecera `Retry-After`. Nota de escalado: el bucket es **in-process** (un worker); si se escala a múltiples pods habría que moverlo a Redis para límite global. |
| 8 | **Schemas estables/congelados** | ✅ | Contratos congelados `*-intelligence-v1` + `master-v1`, documentados en `*_ENGINE_CONTRACT.md` y `ARROBA_INTEGRATION_CONTRACT_v1.md`. Red de seguridad: **Golden 111/111** + **Smoke 203/203** verdes. Política de estabilidad en §10 del contrato (aditivo permitido; ruptura exige `*-v2` con convivencia). |

---

## 2. Informe de endpoints (Endpoint · Estado · Observaciones)

| Endpoint | Estado | Observaciones |
|---|---|---|
| `POST /api/v1/financial-intelligence/analyze` | ✅ Operativo | Datos reales; `engine_version=financial-intelligence-v1`; KPIs/ratios/balance/valuation/explainability. |
| `POST /api/v1/financial-intelligence/valuation` | ✅ Operativo | Valoración con rango y método; versionado ok. |
| `GET  /api/v1/financial-intelligence/ratios/catalog` | ✅ Operativo | Catálogo de ratios + fórmulas. |
| `POST /api/v1/signal-intelligence/analyze` | ✅ Operativo | `engine_version` + `taxonomy/thresholds/actions/composites_version`; señales reales. |
| `POST /api/v1/signal-intelligence/sector` | ✅ Operativo | Agregado sectorial. |
| `POST /api/v1/signal-intelligence/territory` | ✅ Operativo | Agregado territorial. |
| `POST /api/v1/signal-intelligence/opportunities` | ✅ Operativo | Oportunidades priorizadas. |
| `POST /api/v1/signal-intelligence/history` | ✅ Operativo | Histórico de señales. |
| `GET  /api/v1/signal-intelligence/signal/{id}` | ✅ Operativo | Detalle de señal. |
| `GET  /api/v1/signal-intelligence/catalog` | ✅ Operativo | Tipos + acciones `act-v1`. |
| `POST /api/v1/semantic-intelligence/profile` | ✅ Operativo | Perfil + `profile_version` + `embedding` + `coverage`. |
| `POST /api/v1/semantic-intelligence/embedding` | ✅ Operativo | Vector de embedding. |
| `POST /api/v1/semantic-intelligence/similar` | ✅ Operativo | Similares por embeddings. |
| `POST /api/v1/semantic-intelligence/search` | ✅ Operativo | Universal Search; `backend`+`embedding_model`. |
| `GET  /api/v1/semantic-intelligence/profile/schema` | ✅ Operativo | Schema del perfil. |
| `GET  /api/v1/semantic-intelligence/catalog` | ✅ Operativo | Catálogo semántico. |
| `POST /api/v1/recommendation-intelligence/comparables` | ✅ Operativo | Campo de versión = `recommendation_version` (no `engine_version`). |
| `POST /api/v1/recommendation-intelligence/buyers` | ✅ Operativo | — |
| `POST /api/v1/recommendation-intelligence/sellers` | ✅ Operativo | — |
| `POST /api/v1/recommendation-intelligence/opportunities` | ✅ Operativo | — |
| `POST /api/v1/recommendation-intelligence/investors` | 🟡 Parcial | Responde `unavailable / source_not_available` (por diseño, sin fuente). |
| `POST /api/v1/recommendation-intelligence/advisors` | 🟡 Parcial | Igual que investors: `unavailable` honesto. |
| `POST /api/v1/recommendation-intelligence/matching` | ✅ Operativo | Fit A↔B multidimensional. |
| `POST /api/v1/recommendation-intelligence/explain` | ✅ Operativo | Factores + narrativa. |
| `POST /api/v1/recommendation-intelligence/feedback` | ✅ Operativo | Persiste feedback. |
| `POST /api/v1/recommendation-intelligence/memory` | ✅ Operativo | Memoria de recomendaciones. |
| `GET  /api/v1/recommendation-intelligence/catalog` | ✅ Operativo | Catálogo. |
| `POST /api/v1/strategy-intelligence/thesis` | ✅ Operativo | Campo de versión = `strategy_version` + `evidence_version` (mapa por dependencia). |
| `POST /api/v1/strategy-intelligence/{scenarios,growth,acquisition,divestment,partnership,capital,risk}` | ✅ Operativo | Análisis por dimensión. |
| `POST /api/v1/strategy-intelligence/decision` | ✅ Operativo | Decisión justificada. |
| `POST /api/v1/strategy-intelligence/lifecycle` | ✅ Operativo | Transición de estado de tesis. |
| `POST /api/v1/strategy-intelligence/convert` | ✅ Operativo | Tesis → oportunidad/mandato/transacción. |
| `POST /api/v1/strategy-intelligence/memory` | ✅ Operativo | Memoria de tesis. |
| `GET  /api/v1/strategy-intelligence/catalog` | ✅ Operativo | Catálogo. |
| `POST /api/v1/transaction-intelligence/transaction` | ✅ Operativo | Crear/consultar operación. |
| `POST /api/v1/transaction-intelligence/{workflow,stage,task,next-action,risk,documents,participants,timeline,decision,memory,workspace}` | ✅ Operativo | Transaction OS v1 (Origination→DD). `engine_version=transaction-intelligence-v1` + `os_version`/`state_machine_version`. |
| `GET  /api/v1/transaction-intelligence/catalog` | ✅ Operativo | Workflows/etapas/estados/acciones. |
| `GET  /api/v1/master/{mc_id}` (JWT) | ✅ Operativo | Requiere JWT (admin/Console). Sin token → `401` (verificado). arroba obtiene identidad vía motores. |
| `GET  /openapi.json` · `/docs` (público) | 🟠 Pendiente (exposición) | Spec correcto internamente pero **no accesible públicamente** (lo intercepta el frontend). Ver Atención A. |
| `POST /*/{investors,advisors}` transacción v2 (IOI/LOI/SPA/closing) | 🔴 Pendiente | Diferido a Transaction v2 (DTX10). |

---

## 3. Puntos de atención (operativos — NO son cambios de contrato)

**Atención A · Exposición del OpenAPI (✅ RESUELTO 2026-07-04).** Reubicados los endpoints integrados de
FastAPI bajo `/api` y añadido un **contrato filtrado solo para arroba.com**:
- `GET /api/v1/openapi.json` → spec **OpenAPI 3.1.0** completo interno (496 rutas). Uso interno/Console.
- `GET /api/docs` / `GET /api/redoc` → Swagger UI / ReDoc del spec completo.
- `GET /api/v1/openapi/arroba.json` → **contrato público filtrado** (`arroba-integration-contract-v1`):
  **solo los 6 motores** (Financial 3, Signal 7, Semantic 6, Recommendation 11, Strategy 13, Transaction 13
  = **53 rutas**), sin rutas administrativas ni de Valuo. Incluye `components`/schemas.
- `GET /api/docs/arroba` → **Swagger UI** del contrato filtrado.
Cambio de **configuración/derivado únicamente**; no altera ningún endpoint ni schema de los motores.
Desacopla el contrato externo del interno. Verificado en vivo (`200`, 0 fugas de rutas internas), sin
regresión (backend sano, universo 6.261 intacto).

**Atención B · Cobertura del universo canónico (✅ RESUELTO 2026-07-04).** Se re-ejecutó la proyección
M3-2b: `master_companies` = **6.261** empresas; bridge re-medido `erb_c0c480261423` = **98,13 %**
(5.257 enlazadas / 5.357; 23 conflictos, 4 ambiguas, 73 huérfanas, 27 revisión manual); overlap CIF
legacy **99,02 %**. Entidades proyectadas verificadas en vivo (ej. `mc_d178502397b0` "Transporte AGUTO SA"
resuelve por Financial/Semantic). Operación **solo de datos**; contrato y schemas intactos (Golden 111 +
Smoke 203 = **314/314** verde, sin cambios de código).
> **⚠️ Causa raíz de la no-persistencia (importante para el entorno preview):** la app y la **suite de
> tests comparten `test_database`**. `tests/smoke/test_jobs.py` ejecuta `norm_company.delete_many({})` y
> varios smoke tests llaman `rebuild_master(scope="full")`, lo que **reconstruye `master_companies` a la
> muestra base (~1.000)** y regenera `master_id`. Por eso la proyección "desaparecía". **En producción los
> tests NO corren contra la BD productiva**, por lo que el universo proyectado persiste. En preview: **no
> ejecutar la smoke suite** contra la BD viva o **re-aplicar la proyección** tras cualquier corrida de tests.

**Atención C · Nombre del campo de versión (ℹ️).** No es uniforme: `engine_version` (Financial,
Signal, Semantic, Transaction), `recommendation_version` (Recommendation), `strategy_version`
(Strategy), además de `evidence_version`. Es **conforme** al contrato (§4.7 admite `*_version`).
Recomendación para arroba.com: leer el campo `*_version` correspondiente a cada motor (documentado
en el contrato §6), no asumir `engine_version` en todos.

---

## 4. Evidencia de verificación (en vivo)
- Auth: `POST /financial-intelligence/analyze` sin `X-API-Key` → `401` ✓; con key válida → `200` ✓.
- Datos reales: `mc_4a5347d2c39b` → `has_financials=true`, `kpis.revenue=2722872.85`.
- Versionado: `financial/signal/semantic/transaction-intelligence-v1`, `recommendation_version`, `strategy_version`, `evidence_version` (mapa).
- Rate limit: `ANALYZE_RATE_LIMIT_PER_MIN=600` por `key_hash` (token-bucket in-process; `429`+`Retry-After`).
- OpenAPI interno: `openapi 3.1.0`, 496 rutas, conteos por motor coincidentes con el contrato.
- Estabilidad: Golden 111/111 + Smoke 203/203 (verdes).

---

## 5. Conclusión
Agency Tool está **certificado como APTO** para que arroba.com inicie la integración contra el
contrato público congelado. Los schemas no requieren cambios. Los 3 puntos de atención son de
naturaleza operativa/entorno (exposición del OpenAPI, cobertura de datos y nombre del campo de
versión) y pueden abordarse sin alterar el contrato público.
