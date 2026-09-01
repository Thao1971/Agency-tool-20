# Fase 6 (Intel) · Desglose completo de balance/PyG + cuentas consolidadas de grupo

Ver instrucciones completas en el chat de origen. Orden: aplicar DESPUÉS de Fase 5.

## Paso 1 — Copiar `pgc_account_labels.py` a `backend/services/engines/financial/pgc_account_labels.py`.

## Paso 2 — `metrics.py`: añadir `build_series_strict()` (sin fallback) tras `build_series()`.

## Paso 3 — `engine.py`: import `pgc_account_labels as PGC`; tras el bloque de Fase 5
(`iberinform_ratios = IR.curate(...)`) añadir `statements["detail"]` + bloque
`statements_consolidated`; y añadir `"statements_consolidated": statements_consolidated,`
al return. (El detalle textual está en el mensaje del chat; los bloques reales de
buscar/sustituir se aplican directamente sobre engine.py.)
