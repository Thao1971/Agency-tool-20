# MASTER_SOURCE_PARITY_REPORT.md
**Informe de paridad M2 — `enrich`: legacy `companies_master` vs canónico `master_companies`**
_Versión: `m2-parity-v1` · 2026-06-26 · Estado: **M2 DETENIDA EN VALIDACIÓN (bloqueante de cobertura)**._

> Conforme al patrón Construir → Validar → Migrar → Convivencia → Monitorizar → Retirar y a las
> reglas de M2 (*"si cualquiera de estas condiciones falla, detener inmediatamente y documentar"*).

---

## 1. Resumen ejecutivo
- Se construyó la **infraestructura de convivencia interna** (contrato público único): flag interno `MASTER_RECORD_SOURCE` (`legacy` por defecto | `canonical`), provider `services/intelligence_engine/master_provider.py`, cableado en `enrich_company`. **El consumidor no conoce qué backend se ejecuta.**
- En la fase de **Validación** se detectó un **bloqueante estructural**: los datasets `companies_master` (legacy, 5338) y `master_companies` (canónico, 1000) son **DISJUNTOS** — overlap de `cif_normalized` = **0**.
- Resolución canónica sobre el golden dataset (14 empresas): **0/14** → 100% fallback a legacy.
- **Conclusión**: la paridad de M2 es **estructuralmente imposible hoy**. NO se migra el tráfico ni se retira nada. Legacy permanece activo (default).

## 2. Evidencia
| Métrica | Valor |
|---|---|
| `companies_master` (legacy, Valuo.pro) | 5338 docs · esquema **plano** · id `master_company_id` |
| `master_companies` (canónico, motores arroba) | 1000 docs · esquema **anidado** (`identity{}`,`location{}`,`size{}`) · id `master_id` |
| Overlap `cif_normalized` | **0** (5306 vs 1000, intersección vacía) |
| Resolución canónica (golden dataset, 14 empresas) | **0/14** (100% fallback) |

**Causa raíz**: `master_companies` es el subconjunto ingerido por el Data Layer (muestra Iberinform para los Intelligence Engines de arroba); **no contiene** el universo de `companies_master` (scraper/Valuo). No hay enlace de identidad entre ambos.

## 3. Estado de las condiciones de retirada (gate M2)
| Condición obligatoria | Estado |
|---|---|
| 82/82 (ahora **96/96**) golden tests verde | ✅ |
| Snapshot-diffs sin diferencias funcionales (legacy activo) | ✅ |
| Comparación campo a campo / estructuras / señales / ratios (legacy vs canónico) | ❌ **imposible** (0 resolución canónica) |
| Sin regresiones Valuo.pro / arroba.com | ✅ (default legacy, byte-identical) |

➡️ **El gate NO se cumple. Legacy NO se retira. M2 detenida.**

## 4. Qué SÍ queda entregado y seguro
1. **Contrato público único** preservado (sin `?source=`); backend elegido por config interna.
2. **Convivencia transparente**: flip de `MASTER_RECORD_SOURCE` sin tocar la API; rollback inmediato. El canónico **nunca** provoca `master_not_found` (fallback transparente a legacy).
3. **Provider byte-identical** en modo legacy (test `test_legacy_path_is_byte_identical_to_direct_fetch`): cero regresión en `enrich` (ruta crítica de Valuo.pro).
4. **Golden dataset ampliado** a 14 empresas / 28 snapshots con casos límite reales: rich_financials, microempresa, pyme, holding/grupo, financials_incompletos, sin_web, baja_calidad, discovered. (Buckets sin datos reales en `companies_master` — gran_empresa, muy_grande, multi_cnae, sin_cuentas_recientes, inactiva, actividad_digital — quedan documentados como **no disponibles en el dataset actual**.)
5. **Adaptador canónico** (nested→flat) implementado y listo para cuando exista cobertura.

> **Higiene del dataset**: la selección excluye artefactos de test (registros creados/mutados por otras suites, p. ej. el flujo de petición de Valuo) exigiendo `legal_name` real y rechazando nombres `golden|test|unknown`. Esto garantiza que el oráculo congelado sea estable e independiente del orden de ejecución entre suites.

## 5. Prerrequisito para reanudar M2 (nuevo paso: **M2-pre · Backfill/Linkage del Master canónico**)
Antes de poder migrar `enrich`, el Master Layer canónico debe **cubrir el universo de `companies_master`**:
- **Opción A (recomendada)**: ejecutar el pipeline del Data Layer (`rebuild-master`) sobre **todas** las fuentes que hoy alimentan `companies_master`, poblando `master_companies` con el mismo universo + un `entity_xref` que enlace `master_company_id (legacy) ↔ master_id (canónico)`.
- **Opción B**: construir una tabla de enlace `cif_normalized/domain` legacy↔canónico y un proceso de backfill incremental.
- Una vez exista enlace y cobertura ≥ umbral acordado, reanudar M2: activar `canonical` en convivencia (allowlist/% de tráfico interno), ejecutar el harness de paridad campo a campo y solo entonces evaluar la retirada.

## 6. Recomendación
- **No reanudar M2 hasta M2-pre** (backfill/linkage). Es trabajo de Data Layer, no de `intelligence_engine`.
- Dado que **M3 (Entity Resolution)** es precisamente el núcleo del Master Record canónico de arroba, **M3 es prerrequisito natural de M2-pre**: resolver identidad canónica primero habilita la cobertura que M2 necesita.
- **Sugerencia de re-secuenciación**: priorizar **M3 (Entity Resolution)** ahora —como ya indicaste— y tratar M2 como dependiente de la cobertura que M3/M2-pre generen. La infraestructura de convivencia de M2 ya está lista y esperará desactivada (legacy) sin riesgo.
