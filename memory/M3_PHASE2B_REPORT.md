# M3_PHASE2B_REPORT.md
**Informe definitivo — M3 Fase 2b · Entity Resolution · Ingesta & Cobertura del Master Record**
_Versión: `m3-2b-report-v1` · 2026-07-04 · Estado: **COMPLETADO** · Recomendación: **NO activar `canonical` todavía** (revisión manual pendiente de 25 casos)._

> Objetivo de la fase: **resolver el bloqueante de solapamiento 0 %** poblando el Master canónico
> (`master_companies`) con el MISMO universo de entidades que vive en legacy (`companies_master`),
> usando el pipeline legítimo del Data Layer, y **re-medir la cobertura** del bridge. Objetivo de
> cobertura acordado: **≥ 95 %**.
>
> Requisitos obligatorios respetados: (1) legacy `companies_master` NUNCA modificado (solo lectura) ·
> (2) sin cambio de comportamiento en producción · (3) motor canónico NO activado ·
> (4) sin migrar tráfico · (5) sin eliminar datos · (6) proyección totalmente reversible por batch.

---

## 1. Qué se hizo (y qué NO se hizo)
- **Proyección legacy → canónica** vía `services/data_layer/master/legacy_projection.py`
  (`project_and_build`): proyecta las identidades legacy ausentes al schema de ingesta canónico
  `norm_company` (etiquetadas `source='companies_master_projection'`, `projection_batch`), y
  reconstruye el Master con el pipeline determinista `rebuild_master(scope='cif_list')`.
  - Se preservan los invariantes de `master_builder` (una xref por CIF; build idempotente),
    de modo que los motores de arroba y la smoke suite del master-layer siguen operativos.
  - **Reversible**: `rollback_projection(job_id)` elimina SOLO las filas norm/master/xref del batch.
- **Re-ejecución del bridge** `entity_bridge.run_bridge(scope='full')` sobre el universo completo.
- **NO** se activó el flag `canonical`, **NO** se migró tráfico, **NO** se construyó el matcher fuzzy,
  **NO** se reanudó M2, **NO** se tocó `companies_master`.

## 2. Evolución de la cobertura (baseline → final)

| Métrica | Inicial (M3-Fase-2, run `erb_45f3273dbfab`) | Final (M3-Fase-2b, run `erb_202d8224d594`) | Evolución |
|---|---|---|---|
| Universo canónico (`master_companies`) | 1.000 | **6.259** | +5.259 |
| Entidades legacy procesadas | 5.353 | 5.353 | = |
| **Enlazadas (linked)** | 0 | **5.255** | +5.255 |
| **Cobertura del bridge** | **0,00 %** | **98,17 %** | **+98,17 pts** ✅ |
| Conflictos | 0 | 21 | +21 |
| Ambiguas | 0 | 4 | +4 |
| Huérfanas | 5.353 (100 %) | **73** (1,36 %) | −5.280 |
| Pendientes de revisión manual | 0 | **25** (21 conflictos + 4 ambiguas) | +25 |
| Duplicados potenciales (grupos / registros) | 0 / 0 | 0 / 0 | = |

**Cobertura final del bridge: 98,17 % (5.255 / 5.353) — supera el objetivo acordado de ≥ 95 %.** ✅

## 3. Solapamiento de universos (informe cruzado read-only por `cif_normalized`)

| Métrica | Valor |
|---|---|
| Legacy total (`companies_master`) | 5.353 |
| Legacy con CIF | 5.311 |
| Canónico total (`master_companies`) | 6.259 |
| Canónico con CIF | 6.259 |
| **Solapamiento (CIF común)** | **5.259** |
| Solo legacy (sin par canónico) | 52 (legacy sin `cif_normalized`) |
| Solo canónico (universo Iberinform original) | 1.000 |
| **Cobertura de legacy** (legacy que ya existe en canónico) | **99,02 %** |
| Cobertura de canónico (canónico presente en legacy) | 84,02 % |
| Filas proyectadas a `norm_company` | 5.259 (2 batches: `proj_00c456036e88`, `proj_10007f5af93b`) |

> El overlap por CIF (99,02 % de legacy) es superior a la cobertura del bridge (98,17 %) porque el
> bridge exige además superar los umbrales congelados de resolución (DER4) por CIF/dominio/nombre;
> los 25 casos de conflicto/ambigüedad quedan por debajo del auto-merge y requieren revisión manual.

## 4. Calidad de la resolución
- **98,17 % auto-enlazado** con score ≥ `auto_merge`, mayoritariamente por **CIF exacto**.
- **21 conflictos**: candidato único con score entre umbral de conflicto y auto-merge (match débil).
- **4 ambiguas**: más de un candidato canónico plausible para la misma entidad legacy.
- **0 duplicados potenciales**: ningún grupo de varios registros legacy apuntando al mismo canónico.
- **73 huérfanas** (1,36 %): sin candidato. Incluye ~52 legacy sin `cif_normalized` (no proyectables
  por el pipeline CIF) más casos residuales sin match por dominio/nombre.

## 5. Riesgos abiertos
- **R1 — Revisión manual pendiente (medio)**: 25 casos (21 conflictos + 4 ambiguas) requieren
  resolución humana o un matcher adicional antes de considerar 100 % de confianza. NO bloquea el
  cierre de la fase (objetivo ≥95 % cumplido), pero **debe resolverse antes de activar `canonical`**.
- **R2 — Huérfanas residuales (bajo)**: 73 entidades (1,36 %), en gran parte legacy sin CIF
  normalizado; no proyectables por el pipeline actual basado en CIF. Requerirían normalización previa
  o resolución por nombre/dominio.
- **R3 — Divergencia de universos (informativo)**: 1.000 registros canónicos (muestra Iberinform
  original) no tienen par legacy; es esperado y no afecta a la cobertura de Valuo.pro.
- **R4 — Contrato de producción (crítico si se activa)**: el flag `canonical` sigue en `legacy` por
  defecto. Activarlo hoy dejaría sin resolver el 1,36 % huérfano + 25 casos → NO activar sin
  revisión previa y nuevo informe aprobado.

## 6. Recomendación objetiva
- **El bloqueante de cobertura de M3-Fase-2 queda RESUELTO**: de 0 % a **98,17 %**, superando el
  umbral acordado (≥95 %). Legacy y canónico comparten ahora el mismo universo de entidades.
- **El Master Record canónico está estructuralmente listo** para futuras fases de convivencia, pero
  **NO está preparado para activar `canonical` en producción todavía**: prerrequisito ineludible es
  **procesar los 25 casos de revisión manual** (conflictos/ambigüedades) y decidir el tratamiento de
  las 73 huérfanas.
- **Secuencia recomendada para la SIGUIENTE fase (requiere aprobación explícita del usuario):**
  1. Resolver los 25 casos de revisión manual (workflow de revisión o matcher fuzzy acotado).
  2. Normalizar/proyectar el residuo huérfano sin CIF donde sea posible.
  3. Solo entonces reevaluar la activación de `canonical` (convivencia real) con nuevo informe.
  4. En paralelo, con la cobertura resuelta, **M2 (Enrich Engine) queda desbloqueado** para retomarse.

## 7. Reversibilidad y auditoría
- Proyección reversible por batch: `rollback_projection('proj_00c456036e88' | 'proj_10007f5af93b')`.
- Bridge reversible por run: `rollback_run('erb_202d8224d594')` (borra solo xref `origin='er_bridge'`
  y resultados de ese run; legacy y xref de `master_builder` intactos).
- Histórico completo en `er_bridge_runs`; clasificación por entidad en `er_bridge_results`.

## 8. Estado final
**M3-Fase-2b COMPLETADO.** Cobertura del bridge **98,17 %** (objetivo ≥95 % superado). Motor canónico
**NO activado**; **producción intacta**; legacy **no modificado**. No se abre ninguna fase nueva, no se
construye el matcher fuzzy, no se reanuda M2 y no se activa `canonical` hasta nueva aprobación.
