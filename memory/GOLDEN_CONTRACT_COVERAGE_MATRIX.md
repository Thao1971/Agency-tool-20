# GOLDEN_CONTRACT_COVERAGE_MATRIX.md
**Matriz de cobertura — Golden Contract Tests (Sprint 8.1)**
_Versión: `golden-v1` · 2026-06-26 · Estado: **VIGENTE** · Suite: `/app/backend/tests/golden/`._

> Red de seguridad **black-box** que congela el comportamiento observable de los endpoints 🔴 Legacy crítico.
> Cualquier migración futura debe mantener esta suite **100% verde**. La implementación puede cambiar; el contrato **NO**.
> Resultado actual: **47/47 PASSED** (≈0.5s). Suite smoke global intacta: **203/203**.

## Qué valida cada Golden Test
HTTP code · headers (content-type JSON) · estructura JSON · tipos de datos · campos obligatorios · campos opcionales · valores calculados (invariantes) · manejo de errores (404/400/422/401) · respuestas vacías/parciales · compatibilidad hacia atrás (presencia de todos los campos documentados).

---

## 1. Valuo Integration — `/api/v1/valuo/*` · Consumidor: **Valuo.pro (prod)** 🔴
Archivo: `test_valuo_integration_contract.py` · **10 tests**

| Endpoint | Casos cubiertos | Tests | Estado |
|---|---|:--:|:--:|
| `POST /request-update-from-valuo` | normal (payload completo), edge (solo id requerido), error (422 sin id requerido) | 3 | ✅ |
| `GET /request-update-status/{id}` | normal (contrato completo), error 404 | 2 | ✅ |
| `GET /request-status/{id}` (polling Valuo) | normal (incl. `enrichment_meta` + `enriched_company_url`), error 404 | 2 | ✅ |
| `GET /valuo-requests` (JWT) | auth gate (401/403), contrato `{requests,total}` | 2 | ✅ |
| `GET /health` | verdict + by_status + 12 buckets timeline + duration_ms{p50,p95,samples} | 1 | ✅ |

## 2. Intelligence Enrichment — `/api/v1/intelligence/*` · Consumidores: **Valuo.pro (valuo) + arroba (arroba) + Console** 🔴
Archivo: `test_intelligence_enrich_contract.py` · **13 tests**

| Endpoint | Casos cubiertos | Tests | Estado |
|---|---|:--:|:--:|
| `POST /enrich` | perfil valuo, perfil arroba, perfil basic (default), 404 master inexistente, 400 perfil inválido, 422 sin master_id | 6 | ✅ |
| `GET /profiles` | catálogo + backward-compat (basic/valuo/arroba presentes) | 1 | ✅ |
| `GET /profile/{name}` | valuo (sources mínimos), arroba (superset), 404 desconocido | 3 | ✅ |
| `GET /company/{id}` (vista canónica) | contrato identity+sources, invariante sources_count, 404 | 3 | ✅ |

## 3. Enriched Company — `/api/v1/company/*/enriched` · Consumidores: **Valuo.pro + arroba** 🔴
Archivo: `test_enriched_company_contract.py` · **5 tests**

| Endpoint | Casos cubiertos | Tests | Estado |
|---|---|:--:|:--:|
| `GET /{id}/enriched` | contrato flat (35 campos) + envelope + invariante sources_count, 404 | 2 | ✅ |
| `GET /by-valuo-id/{vid}/enriched` | normal (linkado por valuo_id), 404 | 2 | ✅ |
| (transversal) | respuesta vacía/parcial: empresa recién creada mantiene forma completa | 1 | ✅ |

## 4. Master Layer + Publicación Valuo — `/api/v1/master/*` · Consumidores: **Console (JWT) + Valuo.pro (publish)** 🔴/🟡
Archivo: `test_master_publish_contract.py` · **11 tests**

| Endpoint | Casos cubiertos | Tests | Estado |
|---|---|:--:|:--:|
| `GET /master` | auth gate, contrato `{companies,total}` | 2 | ✅ |
| `GET /master/stats` | auth gate, 12 contadores int | 2 | ✅ |
| `GET /master/{id}` | contrato (+linked_agency_results, audit_history), 404 | 2 | ✅ |
| `POST /{id}/publish-to-valuo` | auth gate, 404, 400 (no publicable), 200 (publicable) | 4 | ✅ |
| `POST /{id}/unpublish-from-valuo` | auth gate, 200 (en flujo publish→unpublish) | 1 | ✅ |

## 5. Skills — `/api/v1/skills/*` · Consumidor: **arroba.com (público)** 🔴
Archivo: `test_skills_contract.py` · **8 tests**

| Endpoint | Casos cubiertos | Tests | Estado |
|---|---|:--:|:--:|
| `POST /search` | workspace.blocks (search_results), con filtros, body vacío (defaults) | 3 | ✅ |
| `POST /value` | contrato (valuation_range/comparables/…), 404, 422 | 3 | ✅ |
| `POST /recommend` | modo similar, modo thesis (por query), 404 | 3 | ✅ |

---

## Resumen
| Dominio | Endpoints protegidos | Tests | Estado |
|---|:--:|:--:|:--:|
| Valuo Integration | 5 | 10 | ✅ |
| Intelligence Enrichment | 4 | 13 | ✅ |
| Enriched Company | 2 | 5 | ✅ |
| Master + Publish Valuo | 5 | 11 | ✅ |
| Skills | 3 | 8 | ✅ |
| **TOTAL** | **19** | **47** | ✅ **100% verde** |

**Cobertura por tipo de caso**: normales ✅ · límite/edge ✅ · errores 404/400/422/401 ✅ · datos incompletos/sparse ✅ · vacíos ✅ · perfiles valuo/arroba ✅ · invariantes calculados (sources_count) ✅ · backward-compat (presencia de campos) ✅.
