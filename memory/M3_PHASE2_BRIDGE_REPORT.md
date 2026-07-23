# M3_PHASE2_BRIDGE_REPORT.md
**Informe final — M3 Fase 2 · Entity Bridge & Master Record Quality Tool**
_Versión: `bridge-report-v1` · 2026-06-26 · Estado: **COMPLETADO** · Recomendación: **NO activar `canonical` todavía**._

> Objetivo cumplido: NO migrar datos, sino **construir el bridge canónico y medir su calidad** con una
> herramienta permanente, idempotente, auditable y reversible. Requisitos obligatorios respetados:
> (1) legacy nunca modificado · (2) sin cambio de comportamiento en producción · (3) motor canónico NO activado ·
> (4) sin migrar tráfico · (5) sin eliminar datos.

---

## 1. Herramienta entregada
- **Job** `services/data_layer/master/entity_bridge.py`: `run_bridge(scope, limit, dry_run)`, `rollback_run(run_id)`, `list_runs`, `get_run`.
  - Escribe SOLO en colecciones dedicadas: `entity_xref` (filas `origin='er_bridge'`, `bridge_run_id`), `er_bridge_runs` (histórico), `er_bridge_results` (clasificación por entidad).
  - **Idempotente** (upsert por `external_id`), **repetible**, **monitorizable**, **auditable**, **rollback inmediato** (borra SOLO las filas del job de ese `run_id`; nunca toca legacy ni las xref de `master_builder`).
- **API admin (JWT)** `/api/v1/master/bridge/*`: `POST /run`, `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/rollback`.
- **Tests** `tests/golden/test_entity_bridge.py` (5): dry-run sin escritura, idempotencia, rollback selectivo, no-mutación de legacy, histórico. Golden suite total **111 verde**.

## 2. Métricas de la ejecución (universo completo)
| Métrica | Valor |
|---|---|
| Entidades procesadas (legacy `companies_master`) | **5350** |
| Universo canónico (`master_companies`) | **1000** |
| **Enlazadas (linked)** | **0** |
| **Cobertura alcanzada** | **0.00 %** |
| Conflictos | 0 |
| Ambigüedades | 0 |
| Duplicados potenciales (grupos / registros) | 0 / 0 |
| Huérfanas (sin resolver) | **5350** (100 %) |
| Pendientes de revisión manual | 0 |

## 3. Calidad de la resolución
- **Cobertura 0 %**: ninguna entidad legacy enlaza con el universo canónico por **CIF (overlap 0)**, ni por **dominio**, ni por **name_key**. Los dos datasets son **totalmente disjuntos**.
- Sin conflictos ni ambigüedades **porque no hay candidatos** (no es señal de buena calidad, sino de ausencia de solapamiento).
- Confirma cuantitativamente el bloqueante ya detectado en M2.

## 4. Riesgos encontrados
- **R1 (crítico para activar canónico)**: activar el flag `canonical` hoy **orfanaría el 100 %** de las entidades que consume Valuo.pro (0 % de cobertura) → regresión total. **NO ACTIVAR.**
- **R2**: `master_companies` es un subconjunto ingerido por el Data Layer (muestra Iberinform de ~1000), no el universo real de Valuo (~5350). La causa raíz es de **cobertura/ingesta**, no del motor de resolución.
- **R3**: normalizaciones de `name_key` posiblemente divergentes entre colecciones (no se pudo confirmar match por nombre); a vigilar cuando exista solapamiento real.

## 5. Casos conflictivos
- Ninguno observable hoy (sin candidatos). El detector de conflictos/ambigüedades/duplicados está implementado y probado, listo para cuando exista solapamiento.

## 6. Recomendación objetiva
**El flag `canonical` NO está preparado para iniciar la convivencia real.** Prerrequisito ineludible: **poblar `master_companies` con el universo real** (ejecutar el pipeline del Data Layer sobre las fuentes que hoy alimentan `companies_master`, o ingerir el universo Iberinform completo), y re-ejecutar este bridge hasta alcanzar una **cobertura objetivo acordada** (p. ej. ≥95 %) con conflictos/ambigüedades bajo umbral.

**Secuencia recomendada:**
1. **Ampliar la ingesta canónica** (Data Layer) para cubrir el universo real → M3-fase-2b (ingesta/cobertura).
2. Re-ejecutar `entity_bridge` y monitorizar la **serie histórica** (`er_bridge_runs`): Ejecución → Cobertura → Conflictos → Duplicados → Sin resolver.
3. Solo cuando la cobertura supere el umbral y los conflictos sean gestionables, **reevaluar** la activación de `canonical` (con nuevo informe y aprobación explícita).

## 7. Estado
Herramienta de calidad del Master Record **operativa y permanente**. Bridge medido: **cobertura 0 %**. **Motor canónico NO activado; producción intacta.** No se procede a M2 ni a activar `canonical` hasta ampliar cobertura y aprobar un nuevo informe.
