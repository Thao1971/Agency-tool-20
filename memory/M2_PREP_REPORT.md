# M2_PREP_REPORT.md
**Informe — Preparación de M2 (snapshot-diff + golden dataset)**
_Versión: `m2-prep-v1` · 2026-06-26 · Estado: **LISTO PARA M2 (migración NO iniciada)**._

> M2 = migrar la lectura interna de `intelligence_engine` de `companies_master` → `master_companies`
> **sin cambiar el contrato externo** de `enrich` (consumido por Valuo.pro `profile=valuo` y arroba `profile=arroba`).
> Antes de tocar nada, se construye la **red de paridad** que detectará cualquier deriva de cálculo.

## 1. Qué se ha construido
- **Golden dataset congelado**: `tests/golden/data/enrich_golden_snapshots.json` — 9 empresas (buckets `rich_financials`, `with_web`, `discovered`) × {valuo, arroba} = **18 snapshots**. Selección **determinista** (ordenada por `master_company_id`).
- **Generador**: `tests/golden/gen_enrich_golden.py` (`python -m tests.golden.gen_enrich_golden`). Regenerar SOLO ante un cambio aprobado.
- **Normalización order-insensitive**: `tests/golden/enrich_snapshot_util.py` — descarta volátiles (`duration_ms`, `started_at`, `completed_at`) y canoniza listas/dicts (paridad a nivel de SET, no de orden).
- **Test de paridad**: `tests/golden/test_enrich_snapshot_diff.py` — recomputa `enrich_company` y exige paridad byte-level de `fields` / `sources_with_data` / `found_map` / `engine_version`. Incluye test de determinismo (doble ejecución) y de diversidad del dataset.

## 2. Validación
- Suite golden: **62 → 82 tests**, **82/82 PASS** (idempotente). Snapshot-diff: **20/20**.
- Verificado de forma independiente (testing_agent, iteration_25, 0 issues): dataset 18 entradas / 3 buckets, normalización correcta, determinismo confirmado.
- **Sin cambios de código de producción** (solo `tests/` + `data/`). `enrich_company` es read-only.

## 3. Cómo se usará en M2
1. **Antes** de M2: snapshot actual congelado (hecho).
2. **Durante** M2 (lectura desde `master_companies` detrás del mismo contrato): el harness se ejecuta y debe seguir **82/82** verde. Cualquier diferencia en `fields` se reporta campo a campo.
3. Si aparece deriva legítima/esperada por mejor dato canónico → se documenta y se regenera el snapshot **intencionadamente** con aprobación.

## 4. Pendiente antes de ejecutar M2 (recomendado)
- Golden de endpoints admin secundarios de `master` / `intelligence_engine` (cobertura de superficie operativa).
- Ampliar el dataset si se quiere más cobertura sectorial/territorial (añadir buckets en el generador).
- Definir el **feature flag por perfil** para convivencia (companies_master ↔ master_companies) durante M2.

## 5. Estado
Red de paridad de M2 **operativa**. **M2/M3/M4/M5 NO iniciadas** — pendiente de tu visto bueno para arrancar M2 sobre esta red.
