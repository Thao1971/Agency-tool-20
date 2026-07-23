# GOLDEN_CONTRACT_FINAL_REPORT.md
**Informe final — Sprint 8.1 Golden Contract Tests**
_Versión: `golden-report-v1` · 2026-06-26 · Estado: **COMPLETADO**._

> Sprint exclusivamente de **red de seguridad**. **No se migró código, no se modificaron contratos, no se eliminó nada.**
> Se construyó la batería oficial de Golden Contract Tests que toda migración futura deberá superar al 100%.

---

## 1. Resultado
- **Suite Golden**: `/app/backend/tests/golden/` — **47/47 PASSED** (≈0.5s, idempotente en re-ejecución).
- **Regresión**: suite smoke global **203/203** intacta (no se tocó ningún endpoint).
- **Naturaleza**: tests **black-box** (solo contrato HTTP público); inmunes a cambios internos de implementación.

## 2. Endpoints protegidos (19) — todos 🔴 Legacy crítico
- **Valuo.pro (prod)**: `request-update-from-valuo`, `request-update-status/{id}`, `request-status/{id}`, `valuo-requests`, `health`, `company/{id}/enriched`, `company/by-valuo-id/{vid}/enriched`, `intelligence/enrich?profile=valuo`, `master/{id}/publish-to-valuo`, `master/{id}/unpublish-from-valuo`.
- **arroba.com**: `intelligence/enrich?profile=arroba`, `skills/search`, `skills/value`, `skills/recommend`.
- **Console (JWT)**: `master`, `master/stats`, `master/{id}`, `intelligence/profiles`, `intelligence/profile/{name}`, `intelligence/company/{id}`.

## 3. Cobertura conseguida
- Verbos y rutas: 19 endpoints, 47 casos.
- Tipos de caso: normales · límite · errores (404/400/422/401/403) · datos incompletos/sparse · vacíos · perfiles valuo+arroba · invariantes calculados · backward-compat (presencia de todos los campos documentados).
- Invariantes verificados: `sources_count == nº sources presentes`; `timeline_last_hour` = 12 buckets; tipos int en todos los contadores de `stats`/`health`; envelope flat de 35 campos en enriched company.

## 4. Posibles zonas SIN cobertura (gaps conocidos, para futuras iteraciones)
1. **Endpoints admin secundarios de `master`** (conflicts, transition, bulk-verify, bulk-publish, resolve, ingest-from-scraper, audit-log, pipeline, er-config): usados por Console; aún sin golden test. Riesgo bajo (no los consume Valuo.pro directamente), pero conviene cubrirlos antes de migrar `routes/master`.
2. **`intelligence_engine` endpoints operativos** (scrape-queue, sources/ingest, sources/sample, sources/query, sidebar, coverage, scheduler/audit, migrate-agency-results): Console/automáticos. Sin golden test todavía.
3. **Valores numéricos exactos de valoración/enriquecimiento**: por diseño se validan **estructura e invariantes**, no cifras concretas (varían con los datos). Para detectar derivas de cálculo se recomienda, en la fase de migración, **snapshot diffs** por empresa fija (golden data set) además del contrato.
4. **Contrato de salida real hacia Valuo en `publish-to-valuo`**: hoy el endpoint solo marca `published_to_valuo=True` y audita; **no** hace push a un sistema Valuo externo. Si en el futuro se añade integración saliente, requerirá su propio golden/contract test.
5. **Autenticación propia de Valuo**: los endpoints `valuo/*` públicos no validan auth de Valuo (lo hace Valuo por su lado). No es un gap del contrato actual, pero debe documentarse al endurecer seguridad.

## 5. Riesgos detectados durante la auditoría de contrato
- **R1 — Dos contratos `company` solapados**: `/api/v1/company/{id}/enriched` (enriched_company.py, flat+sources) y `/api/v1/intelligence/company/{id}` (intelligence_engine.py, identity+sources). Ambos product-facing y con formas distintas. **Riesgo**: confundirlos durante la migración. **Mitigación**: ambos quedan protegidos por golden tests separados; documentado en API Reference.
- **R2 — `_build_company_view` duplicado** en `intelligence_engine.py` y `enriched_company.py` (lógica similar, contratos distintos). Cualquier refactor de uno no debe alterar el otro. Golden tests lo detectarían.
- **R3 — `publish-to-valuo` depende de `merge_status`** (verified/auto_merged) → 400 si no. Migraciones que toquen `merge_status` deben preservar esta guarda (cubierto por test 400).
- **R4 — Efectos de fondo (BackgroundTasks)** en `request-update-from-valuo`: la respuesta es síncrona pero dispara enriquecimiento async. El contrato síncrono está congelado; el resultado async se valida vía `request-status`.

## 6. Siguiente paso propuesto del plan de migración

> **Recomendación: ejecutar M1 — migrar `services/signal_engine.py` (antiguo) → `services/engines/signal`.**

| Dimensión | Evaluación |
|---|---|
| **Riesgo estimado** | 🟢 **BAJO**. Solo 2 consumidores **internos** (`routes/data_layer`, `services/skills_recommend`). **Ningún contrato público externo** depende directamente del módulo. |
| **Impacto Valuo.pro** | 🟢 **Nulo/indirecto**. Valuo no consume `signal_engine` directamente. Único punto de contacto: `skills/recommend` (arroba, no Valuo) si su salida cambiara → **protegido por golden tests de skills**. |
| **Impacto Agency Tool/Console** | 🟡 **Bajo**. `routes/data_layer` (rebuild-signals) es admin/Console → cubierto por smoke `test_data_layer`. Añadir golden test de `rebuild-signals` antes de migrar. |
| **Impacto arroba.com** | 🟢 **Bajo**. `skills/recommend` y `signal-intelligence` ya tienen tests; la migración no cambia el contrato. |
| **Método** | Construir (ya existe `engines/signal`) → Validar (paridad vía golden + smoke) → Migrar los 2 importadores internos detrás de su comportamiento actual → Convivencia con flag → Monitorizar → Retirar el módulo antiguo solo al final. |
| **Pre-requisito** | Añadir 1 golden test a `rebuild-signals` (gap #2) para cerrar la red de seguridad de M1. |

**Alternativa más conservadora**: antes de M1, completar los gaps #1 y #2 (golden tests de los endpoints admin de `master` e `intelligence_engine`) para tener la red de seguridad **completa** y poder abordar después M2 (lectura `companies_master` → `master_companies`) con máxima confianza.

---

## 7. Cierre
La plataforma queda **protegida por una red de seguridad de contrato** sobre todos los endpoints 🔴 Legacy crítico de cara a Valuo.pro y arroba.com. **No se inicia ninguna migración** hasta tu aprobación. Una vez aprobada, M1 es el primer paso recomendado por su riesgo bajo y su impacto nulo sobre Valuo.pro.
