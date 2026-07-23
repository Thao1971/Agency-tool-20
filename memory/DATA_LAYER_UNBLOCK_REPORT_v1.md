# INFORME TÉCNICO — Desbloqueo del Data Layer (bootstrap reproducible + dataset canónico)
_Versión: `datalayer-unblock-v1` · 2026-07-12 · Estado: COMPLETADO y verificado (20/20 tests)._

## 1. Diagnóstico definitivo (corrige la hipótesis inicial)
- **NO hay bug de mapeo raw→normalización→master.** En el linaje canónico, `norm_financials` cubre
  **374 empresas** y las **374 tienen `financials.latest` en `master_companies`** (0 pérdidas verificadas).
  Los financieros del raw se proyectan íntegros al Master vía `_fin_summary` (master_builder).
- **La comparación previa era engañosa:** contrastaba `iberinform_companies` (linaje **legacy/sintético**
  que alimenta `companies_master`) contra el canónico `master_companies`. Los motores públicos consumen
  **exclusivamente `master_companies`** (canónico), no el legacy.
- **Causa raíz del "company not found para todas" en producción:** el despliegue tiene **MongoDB propia
  y vacía**; el dataset se había construido interactivamente en preview y no se sembraba ni migraba. El
  arranque no creaba `master_companies`.
- **Cobertura financiera (374/1000):** es la **cobertura real de la fuente** (el fichero
  `ES_Financial_Detail_Valu8.csv` trae detalle para 373 NIF + 9 consolidados), no una pérdida de datos.

## 2. Fuente oficial (real, versionada)
`backend/tests/fixtures/iberinform_sample/` (Iberinform Valu8): **1.000 empresas reales**, **374 con
detalle financiero real**, histórico **2018–2025**, + ownership y órganos sociales. Empresas reales
(ej. TRANSPORTS LA MUNTANYESA, TOTALENERGIES, SCANIA HISPANIA). **Cero datos simulados.**

## 3. Track A — Bootstrap reproducible (entregado)
`backend/services/data_layer/bootstrap.py` reconstruye TODO el Data Layer desde la fuente oficial, sin
pasos manuales, idempotente. Cadena ejecutada en orden, cada paso con timing/estado persistido en
`db.bootstrap_runs`:
1. **ingestión** → `norm_company / norm_financials / norm_ownership / norm_officers`
2. **master builder** (incluye **Entity Resolution** + **proyección financiera** real) → `master_companies` + `entity_xref`
3. **ownership graph** (group_id, union-find)
4. **signal builder canónico** → `db.signals` por `master_id`
5. **semantic index canónico** → `semantic_profiles` + embeddings (motor `services/engines/semantic`)
6. **verificación** (counts, cobertura, smoke de contratos públicos) + **selección del set canónico**

> Nota: los builders legacy (`master_signals.rebuild_signals`, `taxonomy_embeddings.build_index`)
> escriben sobre `companies_master` (legacy) y **no** sirven a los motores canónicos. El bootstrap usa
> builders canónicos que iteran `master_companies`.

### Cómo reconstruir un entorno vacío (un único proceso, 3 vías)
- **Automática (self-healing):** al arrancar, si `master_companies` está vacío, se lanza el bootstrap en
  segundo plano. Controlado por `AUTO_BOOTSTRAP_DATA_LAYER` (por defecto `1`; poner `0` para desactivar).
- **Endpoint admin (JWT):** `POST /api/v1/data-layer/bootstrap` `{"rebuild_intelligence": true, "canonical_n": 50}`
  → devuelve `run_id`; seguimiento en `GET /api/v1/data-layer/bootstrap/{run_id}`.
- **CLI:** `python -m services.data_layer.bootstrap` (usa `DATA_LAYER_SOURCE_DIR` o el fixture oficial).

### Prueba de reconstrucción desde CERO (BD vacía aislada)
`DB_NAME=test_database_bootstrap python -m services.data_layer.bootstrap` → en **~15 s**:
`norm_company 1000 · master_companies 1000 · entity_xref 2270 · signals 2443 · semantic_profiles 998`;
cobertura `legal_name 1000 · financials 374 · revenue 355 · histórico≥2años 345`; smoke de motores
(signals 6, similar 5, comparables 5, thesis ✅) OK. **Entorno vacío → totalmente reconstruido.**

## 4. Track B — Dataset canónico de validación (entregado)
`select_canonical_set(50)` selecciona, de forma **data-driven**, las 50 empresas reales con histórico
financiero real más rico (≥2 ejercicios reales), ordenadas por (nº años, ingresos). Persistido en
`db.canonical_validation_set` y expuesto en `GET /api/v1/data-layer/canonical-set`.
Cadena completa validada en vivo (X-API-Key) para una empresa canónica (TOTALENERGIES, A87803862):
- **identidad:** legal_name, `capital_social=689.136`, CNAE 3515.
- **financieros:** `has_financials=true`, revenue `933.267.000 €`.
- **histórico REAL (sin interpolar):** `evolution.years=3` → 2024: 933.267.000 · 2023: 1.288.562.000 · 2022: 2.229.436.000.
- **inteligencia:** signals ✅, semantic profile ✅, thesis ✅.

## 5. Histórico — política aplicada
Solo se muestran **ejercicios realmente ingeridos** (de `norm_financials`). **No se interpola, no se
estima, no se generan ejercicios ilustrativos.** El motor financiero expone la serie real vía
`evolution.years/points`; `statements` es el último ejercicio detallado.

## 6. Verificación
- **Reconstrucción desde vacío:** probada en proceso aislado (ver §3).
- **testing_agent (backend): 20/20 (100%)** — endpoint bootstrap + poll, canonical-set, cadena pública
  para empresa canónica (identidad/financieros/histórico/señales/semántica/estrategia), y **regresión de
  contratos congelados v1+v2 (10 golden tests)**. Report: `/app/test_reports/iteration_32.json`.

## 7. Criterio de finalización — cumplido
✅ Un entorno completamente vacío se reconstruye íntegramente mediante el bootstrap reproducible.
✅ El dataset canónico permite validar todos los contratos públicos consumidos por Arroba.
No se han desarrollado nuevas capacidades fuera de este alcance.

## 8. Acción en PRODUCCIÓN (`https://intel-agency.emergent.host`)
Tras el próximo **redeploy** con este código, al arrancar con la BD vacía el **self-healing bootstrap**
poblará automáticamente el Master Layer (o ejecutar el endpoint admin manualmente). Requiere que el
directorio de fuentes esté presente en el contenedor (el fixture oficial se versiona en el repo).
