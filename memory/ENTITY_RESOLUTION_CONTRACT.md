# ENTITY_RESOLUTION_CONTRACT.md
**Contrato del Entity Resolution Engine — `entity-resolution-v1`**
_Versión: **FROZEN** (DER1–DER9 aprobadas 2026-06-26) · Migración M3 · Fase 1 IMPLEMENTADA._

> Entity Resolution es el **núcleo del Master Record canónico** de arroba.com y el habilitador de la
> cobertura que M2 necesita. Riesgo ALTO: toca la ruta de identidad que consume **Valuo.pro en producción**.
> Regla absoluta: **no romper ningún consumidor**. Contrato CONGELADO; implementación aditiva y en convivencia.

## Decisiones congeladas (resueltas por el usuario)
- **DER1 SÍ** · ER canónico (`data_layer/master`) = único motor; legacy = shim en convivencia.
- **DER2 SÍ** · `entity_xref` = fuente de verdad del enlace, append-only, auditable.
- **DER3 SÍ** · enlace `master_company_id` (legacy) ↔ `master_id` (canónico) vía `entity_xref` (id_type=`master_company_id`) — **habilita M2**.
- **DER4 = a** · umbrales congelados: cif=1.0, domain=0.95, name+province=0.70, auto_merge=0.95, conflict=0.70.
- **DER5 = a** · `master_id` nuevo **determinista** por clave natural (cif>domain>name+prov); misma entidad → mismo id.
- **DER6 SÍ** · explicabilidad `{status, score, method, match_id, candidates, reasons}` + auditoría append-only (`entity_resolution_audit`).
- **DER7 SÍ** · contratos públicos (`resolve_entity`, `request-update-from-valuo`) NO cambian; ER canónico detrás vía flag interno `ENTITY_RESOLUTION_SOURCE` (default legacy); rollback inmediato.
- **DER8 = a** · M3 = motor + red de seguridad + paridad; **backfill masivo → M3-fase-2**.
- **DER9 SÍ** · estado `conflict` entre umbrales conflict y auto_merge (sin auto-merge).

## Fase 1 entregada (alcance confirmado)
1. Red de seguridad: snapshot-diff de `resolve_entity` (`tests/golden/test_resolve_snapshot_diff.py`) + golden existente de `request-update-from-valuo`.
2. Motor canónico unificado + adaptador: `services/data_layer/master/identity_resolver.py` (`resolve_identity`, `deterministic_master_id`, `link_legacy_master`).
3. Provider de convivencia `services/entity_resolution_provider.py` (flag interno, default legacy), cableado en `valuo_integration`/`master`/`procurement` con alias (call sites intactos).
4–7. Cero cambio en producción · sin retirar legacy · sin migrar tráfico · sin backfill masivo.

---

## 1. Auditoría — dos sistemas de Entity Resolution hoy

| | **Legacy ER** `services/entity_resolution.py` (396 líneas) | **Canónico ER** `services/data_layer/master/entity_resolution.py` (80 líneas) |
|---|---|---|
| Resuelve contra | `companies_master` (5338) | `master_companies` (1000) + `entity_xref` (2270) |
| Entrada | `resolve_entity(name, cif, domain, …)` | `resolve(entity, source)` |
| Salida | `{match_id, score, method, status, candidates}` | `(master_id, match_rule, confidence, created)` |
| Reglas | cif_exact **1.0**, domain_exact **0.97**, name fuzzy | exact_cif **1.0**, domain **0.9**, name+province **0.7**, new |
| Umbrales | `er_config`: auto_merge **0.95**, conflict **0.70** | (sin umbrales; primer match gana) |
| ID | `master_company_id` (aleatorio) | `master_id` (`new_master_id()` aleatorio) |
| Registro de enlace | ninguno (estado en el propio doc) | **`entity_xref`** (source, id_type, external_id → master_id), append-only |
| Consumidores | `routes/valuo_integration` (**Valuo.pro**), `routes/master`, `procurement_connector` | `data_layer/master/master_builder` (Data Layer arroba) |
| Cobertura `entity_xref` | — | solo `source=iberinform` (universo arroba). **No cubre companies_master** → brecha de M2 |

**Diagnóstico**: dos motores divergentes, dos espacios de ID sin enlace, `entity_xref` parcial. M3 debe **converger** hacia un ER canónico con `entity_xref` como fuente de verdad del enlace, **sin cambiar** los contratos públicos que consume Valuo.pro.

---

## 2. Decisiones a congelar (DER) — propuestas con recomendación

- **DER1 · Frontera / motor único**: el **ER canónico** (`data_layer/master`) pasa a ser el **único servicio de resolución de identidad**. El legacy `entity_resolution.py` queda como **adaptador/shim en convivencia** detrás de su contrato actual (patrón M1/M2). _Recomendado: SÍ._
- **DER2 · Fuente de verdad del enlace**: **`entity_xref`** (append-only, auditable) es la verdad canónica: `(source, id_type, external_id) → master_id`. Toda resolución consulta/escribe aquí primero. _Recomendado: SÍ._
- **DER3 · Espacio de IDs y enlace legacy↔canónico**: mantener `master_id` canónico y **enlazar** `master_company_id` (legacy) ↔ `master_id` vía `entity_xref` (id_type=`master_company_id`). Esto **habilita M2**. No se renombra ni se rompe `master_company_id`. _Recomendado: SÍ._
- **DER4 · Reglas y umbrales unificados (congelados)**: `cif_exact=1.0`, `domain_exact=0.95`, `name+province=0.7`, `name_fuzzy` ponderado; `auto_merge_threshold=0.95`, `conflict_threshold=0.70`. (Unifica la discrepancia domain 0.97 vs 0.9 → **0.95**.) _¿Confirmas estos valores?_
- **DER5 · Determinismo de IDs nuevos**: un ID nuevo se deriva de forma **determinista** de la clave natural (p. ej. `mc_ + sha256(cif_normalized)` o `+domain` o `+name_key|provincia`), de modo que la misma entidad → mismo `master_id` (idempotente, reproducible), en lugar de aleatorio. _Recomendado: SÍ (determinista)._
- **DER6 · Explicabilidad + auditoría**: cada resolución devuelve `{master_id, match_rule, confidence, status∈{auto_merged|conflict|new}, candidates[], reasons[]}` y se **audita append-only** (quién/cuándo/regla/evidencia). _Recomendado: SÍ._
- **DER7 · Convivencia transparente (Valuo.pro)**: los contratos públicos `resolve_entity(...)` y `POST /api/v1/valuo/request-update-from-valuo` **NO cambian**. El ER canónico se activa **detrás** vía flag interno (como `MASTER_RECORD_SOURCE`); rollback inmediato; sin parámetro público. _Recomendado: SÍ._
- **DER8 · Backfill de cobertura (habilitador M2)**: ¿M3 incluye **poblar `entity_xref` para el universo de `companies_master`** (enlace legacy↔canónico) en este sprint, o se hace en **M3-fase-2** tras congelar el motor? _Recomendado: fase-2 (primero motor + red de seguridad, luego backfill masivo)._
- **DER9 · Conflictos**: por debajo de `auto_merge` y por encima de `conflict` → estado **`conflict`** (no auto-merge; cola de revisión), preservando el comportamiento legacy (`er_config`). _Recomendado: SÍ._

---

## 3. Método de migración (patrón oficial validado)
Construir (ER canónico + adaptador) → Validar (golden/paridad de `resolve_entity` y `request-update-from-valuo`) → Migrar (flag interno) → Convivencia → Monitorizar → Retirar. **Nada se retira** hasta paridad total + sin regresiones Valuo.pro/arroba.

## 4. Red de seguridad previa (antes de tocar código de ER)
- **Golden Contract Tests** de `POST /api/v1/valuo/request-update-from-valuo` (ya existen, 🔴) + **snapshot-diff** de `resolve_entity` sobre un golden dataset de identidades (cif/domain/name variados: match exacto, fuzzy, conflicto, nuevo).
- Estas pruebas serán el oráculo de paridad de M3.

---

## 5. Estado
**DRAFT — decisiones ABIERTAS.** No se implementa hasta que apruebes/ajustes DER1–DER9 (especialmente DER4 umbrales, DER5 determinismo y DER8 alcance del backfill).
