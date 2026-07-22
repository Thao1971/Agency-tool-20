# Checklist de despliegue — Q1 (BORME) + Q2 (grafo de control) + Q3 (baselines)

Generado durante la implementación de estos quick wins del roadmap real (`docs/strategic-intelligence-architecture/08_STRATEGIC_ROADMAP.md`). Ninguno de estos pasos se puede ejecutar sin acceso a la base de datos MongoDB real — quedan pendientes de correr tras el despliegue. Ninguno es bloqueante: sin ellos el sistema cae a comportamiento por defecto (sin señales BORME, umbrales fijos `thr-v1`, sin `competitor_of`), sin errores.

## Orden recomendado (una sola vez tras el deploy)

1. **`/bootstrap`** (si no se ha corrido ya) — pipeline oficial existente (ingestion → master_builder → ownership_graph → signals → semantic index → verify → canonical_set). Prerrequisito de todo lo demás.
2. **`POST /api/v1/signal-intelligence/borme-link-backfill`** (Q1) — enlaza `borme_events` con `master_companies`. Repetir con `limit_companies` hasta `companies_remaining: 0`. No es estrictamente obligatorio: el enlace también ocurre de forma perezosa la primera vez que se analiza cada empresa (`borme_bridge.py::evaluate()`), pero correrlo una vez es más rápido.
3. **`POST /api/v1/signal-intelligence/baselines/compute`** (Q3) — calcula percentiles sector×tamaño. Re-ejecutar periódicamente (mensual razonable). Verificar cobertura con `GET /api/v1/signal-intelligence/baselines/status`.
4. **`POST /api/v1/data-layer/rebuild-competitor-graph`** (Q2) — calcula `competitor_of`. Ejecutar después del `/bootstrap` normal (necesita `master_companies` + `ownership.group_id` ya poblados). Re-ejecutar periódicamente conforme se ingieran empresas nuevas — deliberadamente NO está encadenado al `/bootstrap` oficial todavía.

## Ya materializado y consultable sin pasos extra

- `GET /api/v1/data-layer/relationships/{master_id}` y `GET /api/v1/data-layer/relationships/{master_id}/group` (Q2): leen el grafo de propiedad real (`shareholder_of`/`parent_of`/`ultimate_parent_of`/`investee_of`/`same_group`) que ya construye `ownership_graph.py` en el `/bootstrap` normal. Solo faltaba la API de lectura.

## Qué NO se ha tocado (a propósito)

- `/api/v1/data-layer/rebuild-graph` (legacy, esquema `companies_master`) sigue existiendo tal cual, solo marcado como deprecated en su docstring.
- `supplier_candidate`/`acquisition_candidate` siguen sin calcular — sin datos reales en ninguna fuente conectada hoy.

## Archivos tocados/creados en esta ronda

- `services/engines/signal/taxonomy.py`, `thresholds.py`, `engine.py` (Q1+Q3)
- `services/engines/signal/borme_bridge.py` (nuevo, Q1)
- `services/engines/signal/baselines.py` (nuevo, Q3)
- `routes/signal_intelligence.py` (endpoints Q1+Q3)
- `services/data_layer/master/ownership_graph.py` (lectura añadida, Q2)
- `services/data_layer/master/competitor_graph.py` (nuevo, Q2)
- `routes/data_layer.py` (endpoints Q2)
- `server.py` (bootstrap de índices Q1+Q3)
