# LEGACY_MIGRATION_PLAN.md
**Plan de migración legacy → canónico (compatible con Valuo.pro)**
_Versión: `migration-plan-v1` · 2026-06-26 · Estado: **PLAN APROBADO PARA PREPARACIÓN (no ejecuta migración)**._

> Regla absoluta: **No romper ningún consumidor existente.** Toda migración sigue el ciclo
> **Construir → Validar → Migrar consumidor → Convivencia → Monitorizar → Retirar**.
> **Nunca** sustitución directa. Nada se elimina en este sprint.

---

## 1. Metodología (6 fases) — aplicable a cada componente legacy

| Fase | Qué se hace | Criterio de salida |
|---|---|---|
| **1. Construir** | Existe (o se crea) el sustituto canónico **sin tocar el legacy**. | Sustituto desplegado y con tests propios verdes. |
| **2. Validar** | Tests de contrato (golden) que comparan salida legacy vs canónica para los mismos inputs. | Paridad funcional demostrada (o diferencias documentadas y aceptadas). |
| **3. Migrar consumidor** | Redirigir la **implementación interna** detrás del **mismo contrato externo** (feature flag por consumidor). | El consumidor recibe respuesta equivalente; golden tests verdes. |
| **4. Convivencia** | Legacy y canónico activos simultáneamente; flag permite rollback inmediato. | Periodo de convivencia definido (p. ej. ≥2 semanas) sin incidencias. |
| **5. Monitorizar** | Métricas/logs de uso del camino legacy; alertas ante divergencias. | Uso del camino legacy → 0 por parte del consumidor migrado. |
| **6. Retirar** | Solo tras confirmación del owner + 0 consumidores: deprecación → borrado. | Confirmación explícita registrada. **No automático.** |

**Invariantes**: cambios aditivos; sin cambios de contrato; rollback siempre disponible; suite smoke verde en cada fase.

---

## 2. Pre-requisito transversal: Golden Contract Tests (antes de migrar nada)
Capturar request/response actuales como regresión para los contratos 🔴 Legacy crítico:
- `POST /api/v1/valuo/request-update-from-valuo` + `GET /api/v1/valuo/request-update-status/{id}` + `GET /api/v1/valuo/health`
- `POST /api/v1/intelligence/enrich` con `profile=valuo`
- `GET /api/v1/company/{master_company_id}/enriched` y `GET /api/v1/company/by-valuo-id/{valuo_company_id}/enriched`
- `POST /api/v1/master/{mc_id}/publish-to-valuo` (contrato de salida hacia Valuo)
- `/api/v1/skills/*` (tras verificar consumidor)

Estos tests son la **red de seguridad**: ninguna migración se aprueba si rompe un golden test.

---

## 3. Backlog de migración priorizado (cuándo, no ahora)

### M1 — `signal_engine.py` (antiguo) → `engines/signal` · riesgo BAJO · ✅ COMPLETADO (2026-06-26, Sprint 8.2)
- Consumidores: solo internos (`routes/data_layer`, `services/skills_recommend`). **Sin contrato externo de Valuo.**
- **Hallazgo clave**: el módulo legacy (master-signals sobre `companies_master`: `signal_score`/`signals[]`/`signal_similarity`) **NO es funcionalmente equivalente** al motor canónico `engines/signal` (entidades canónicas sobre `master_companies`). Una **sustitución semántica** habría roto el contrato → se DESCARTÓ.
- **Qué se hizo (preservando contrato)**: **relocalización byte-for-byte** del módulo a `services/engines/signal/master_signals.py` (md5 idéntico). El antiguo `services/signal_engine.py` queda como **shim de convivencia** que re-exporta `compute_signals/rebuild_signals/signal_similarity`. Los 2 importadores migrados a la ruta canónica.
- **Validación**: Golden **62/62** (incl. test de paridad: shim ↔ canónico son el mismo objeto; mismo `signal_score=71`), Smoke **203/203**, snapshot determinista de `compute_signals`/`signal_similarity` congelado, contrato `rebuild-signals` protegido. **Cero regresiones, cero cambios de contrato.**
- **Estado**: CONVIVENCIA (shim activo, 0 importadores internos restantes del path antiguo salvo el snapshot test, intencional). **Retirada DIFERIDA** hasta confirmar 0 importadores externos.
- **Riesgo real observado**: 🟢 nulo. **Impacto Valuo.pro**: ninguno. **Impacto arroba**: ninguno (skills/recommend idéntico).
- **Lección aprendida**: cuando "migrar" no tiene equivalente funcional, el movimiento seguro es **relocalizar + shim** (consolidar ubicación canónica) en lugar de sustituir lógica; la sustitución semántica se trata como trabajo aparte con su propio contrato.

### M2 — Lectura de `companies_master` → `master_companies` en `intelligence_engine` · riesgo MEDIO · ⛔ DETENIDA EN VALIDACIÓN (2026-06-26)
- Consumidores: Valuo (profile=valuo) + arroba (profile=arroba) + Console.
- **Infraestructura de convivencia ENTREGADA y SEGURA**: flag interno `MASTER_RECORD_SOURCE` (default `legacy`), provider `master_provider.py` (legacy byte-identical / canónico con fallback transparente), cableado en `enrich_company`. **Contrato público único** (sin `?source=`); rollback inmediato; el canónico nunca provoca `master_not_found`.
- **Golden dataset ampliado** a 14 empresas / 28 snapshots con casos límite (micro/pyme/holding/incompletos/sin_web/baja_calidad/discovered). Golden suite 82 → **96 verde**.
- **BLOQUEANTE detectado en Validación**: `companies_master` (5338) y `master_companies` (1000) son **DISJUNTOS** — overlap `cif_normalized` = **0**; resolución canónica 0/14. La paridad es estructuralmente imposible hoy → **gate NO cumplido, legacy NO retirado, tráfico NO migrado**. Ver `MASTER_SOURCE_PARITY_REPORT.md`.
- **Prerrequisito para reanudar (M2-pre · Backfill/Linkage)**: poblar el Master canónico con el universo de `companies_master` + `entity_xref` legacy↔canónico. Como **M3 (Entity Resolution)** es el núcleo del Master Record canónico, **M3 habilita M2**. Recomendación: priorizar M3 ahora; M2 espera (infra lista, desactivada, sin riesgo).

### M3 — `valuo_enrichment` / `entity_resolution` (companies_master) → `data_layer/master` · riesgo ALTO
- Consumidor: Valuo.pro directo. **Máxima cautela.**
- Plan: paridad estricta vía golden tests del flujo `request-update-from-valuo` end-to-end; doble escritura temporal (companies_master + master_companies) si procede; validación explícita de Valuo antes de conmutar.

### M4 — `skills_*` → Financial/Recommendation engines · riesgo MEDIO (pendiente verificar consumidor)
- Acción previa: confirmar si Valuo/externos consumen `/api/v1/skills/*`. Si solo Console → riesgo baja a BAJO.

### M5 — Unificación de ingesta (`iberinform_processor` ↔ `data_layer/ingestion`) · riesgo MEDIO
- Plan: documentar diferencias de esquema; converger hacia la ingesta canónica que alimenta `master_companies`; mantener la legacy hasta migrar lectores.

> **Orden sugerido**: M1 → M4(verificación) → M2 → M5 → M3. Cada uno completa sus 6 fases antes de empezar el siguiente.

---

## 4. Estrategia de convivencia técnica
- **Feature flags por consumidor** (Valuo / arroba / Console) para seleccionar implementación legacy o canónica.
- **Misma firma de contrato**: la respuesta externa no cambia; cambia solo el origen de datos interno.
- **Doble lectura/escritura temporal** donde haga falta paridad de estado (M3).
- **Rollback inmediato** vía flag ante cualquier divergencia detectada en monitorización.
- **No migrar datos en curso** salvo migración explícita, idempotente y auditada.

---

## 5. Criterios de cierre de migración (por componente)
- [ ] Golden tests del consumidor verdes en paridad legacy/canónico.
- [ ] Convivencia estable durante el periodo definido, sin incidencias.
- [ ] Monitorización: uso del camino legacy = 0 por el consumidor migrado.
- [ ] Confirmación explícita del owner del consumidor (p. ej. Valuo.pro).
- [ ] Suite smoke global verde.
- Solo entonces: deprecación → (futuro) retirada del módulo legacy.

---

## 6. Qué NO se hace en este sprint
- ❌ Eliminar código.
- ❌ Migrar consumidores.
- ❌ Modificar contratos públicos.
- ✅ Auditar, documentar, y dejar listos los golden tests como red de seguridad para el futuro.
