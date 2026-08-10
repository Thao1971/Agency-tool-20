# INFORME DE SESIÓN — Intel (arroba.v2) · 2026-08-10
> Handoff para el siguiente agente (Claude). Contiene TODO el contexto de esta sesión.
> Idioma del usuario: **Español** (responder siempre en español).

---

## 0. RESUMEN EJECUTIVO (léelo primero)

Esta sesión tuvo 3 bloques encadenados:
1. **B5 (EAV balance + cash flow)** — RESUELTO. Se encontró la causa raíz y se re-ingirió el EAV completo en la base de **preview**.
2. **Petición de Beta (equipo Arroba)** — 5 CIFs demo + diagnóstico de 404 + inventario de Atlas + armonización de contrato. ENTREGADO.
3. **P0 CRÍTICO — Desajuste de ENTORNO** — Beta consume **producción** (`intel.arroba.com`), que es una base/código DISTINTO al **preview** donde trabajo. **Todo el trabajo de datos está solo en preview.** Se construyó un endpoint de siembra para producción. **PENDIENTE de que el usuario haga redeploy + siembre prod.**

**Lo más importante que debe saber el siguiente agente:**
- **Hay DOS entornos con BASES DE DATOS DISTINTAS que nunca se comparten:**
  - **PREVIEW** (donde trabaja el agente): `MONGO_URL = mongodb://localhost:27017`, `DB_NAME = arroba_agency_tool` (**Mongo LOCAL**). Aquí está todo el trabajo de datos.
  - **PRODUCCIÓN** (`https://intel.arroba.com`, lo que consume Beta): despliegue separado, **otra base (Atlas)**, y hasta que se redepliegue corre **código antiguo**. El agente NO tiene acceso a producción.
- Cualquier cambio de DATOS (ingesta, rebuild, marcados) hecho en preview **NO** se ve en producción. Solo el redeploy lleva el CÓDIGO; los DATOS de prod hay que sembrarlos aparte (endpoint `reingest-eav`, ver §4).

---

## 1. ARQUITECTURA / STACK

- **Backend**: FastAPI + Motor (MongoDB async). Arranca con `uvicorn server:app --reload` bajo supervisor (`/etc/supervisor/conf.d/supervisord.conf`), dir `/app/backend`, puerto 8001.
- **Frontend**: React (SPA "Agency Tools Hub" de BUD Advisors), puerto 3000. `REACT_APP_BACKEND_URL` en `/app/frontend/.env`.
- **Preview URL**: `https://preview-arroba-app.preview.emergentagent.com`.
- **Contrato**: `arroba.v2` — JSON que consume el frontend (Beta) desde Intel.
- **Modelos de dominio clave** (colecciones Mongo):
  - `master_companies` (24.992): empresa canónica. Campos: `identity`, `classification`, `financials.latest{revenue,ebitda,...,ratios}`, `ranking`, `ownership`, `officers_count`, `contact.web`, `objeto_social`, `web_description`, `is_listed`/`listed_market` (nuevo), `name_key`, `cif_normalized`, `master_id`.
  - `norm_financials` (13.501): financieros normalizados EAV. Campo clave `accounts` = dict `{codigo_EAV: valor}` (p.ej. `"10000"`=total activo, `"12000"`=activo corriente, `"32000"`=pasivo corriente, `"61500"`=OCF cash flow). `basis="individual"`.
  - `norm_ownership` (1.994), `norm_officers` (84.351), `signals` (66.050), `bme_companies` (123, cotizadas), `borme_events` (9.214), `company_classifications` (228.729).

### Pipeline de datos (importante)
`.tab crudos (Iberinform)` → **ingestión EAV** (`services/data_layer/ingestion/iberinform_tab_ingest.py`) → `norm_financials.accounts` (EAV completo) → **rebuild master** (`services/data_layer/master/master_builder.py::rebuild_master`) → `master_companies.financials.latest` (+ratios vía `_year_metrics`+`ratios_library.compute_all`).

El endpoint `/analyze` (`services/engines/financial/engine.py::analyze`) construye el contrato **al vuelo** desde `norm_financials` vía `metrics.build_series(norm)` (lee `accounts` completo). Por eso balance/cash-flow/ratios/valuación salen en tiempo real **si** `norm_financials.accounts` tiene el EAV completo. Los **percentiles sectoriales** leen `master_companies.financials.latest.ratios` de los peers → necesitan el rebuild del master.

---

## 2. B5 — Re-ingesta EAV (RESUELTO en preview)

### Causa raíz
La ingesta original (2026-07-22) corrió con una versión ANTIGUA del normalizador que solo guardaba ~6 códigos canónicos por empresa-año (había un filtro `_ACCOUNT_CODES`, hoy código muerto en `iberinform_tab_ingest.py`). El código actual de `ingest_balances_file` ya guarda el **EAV completo** (~168 códigos: balance + EFE) pero **nunca se re-ejecutó**. Los `.tab` crudos SÍ traen todos los códigos.

### Acción y resultado (en la base LOCAL de preview)
Re-ejecutada `ingest_balances_file` sobre las ~25k (555.550 filas) + `rebuild_master(force=True)`. Validado primero en muestra de 500, luego full:
| Métrica | Antes | Después |
|---|---|---|
| `norm_financials.accounts.12000` (activo corriente) | 8 | **13.430** |
| `.accounts.32000` (pasivo corriente) | 8 | **13.123** |
| `.accounts.61500` (OCF cash-flow) | 5 | **246** |
| `master.financials.latest.ratios.current_ratio` | 0 | **13.044** |

### Limitaciones de DATOS (no de código)
- **Cash flow (EFE)**: solo **246** empresa-año (las que presentan cuentas **normales**). Las PYME presentan **cuentas abreviadas** que legalmente no incluyen EFE → `cash_flow: null` + `cash_flow_note` (silencio elegante, correcto). Los códigos `91xxx` que aparecen en abreviadas son ECPN, no EFE.
- **Multi-ejercicio (B, "evolution/CAGR")**: `Datos_BALANCES.tab` tiene **exactamente 1 año por empresa** (13.493 empresas = 13.493 pares empresa-año, es un snapshot, no histórico). **NO se puede activar evolution/CAGR** sin una entrega con varios ejercicios. El usuario confirmó que **no tiene ese histórico por ahora**.
- **Ownership (C)**: `Datos_ACCIONISTAS.tab` = solo **628 filas / 318 empresas** (+1046 participadas). Ya está todo ingerido; el 1,3% ES el límite del fichero. Se expandirá solo con una entrega más rica.

---

## 3. CAMBIOS DE CÓDIGO EN ESTA SESIÓN (todos en preview, PENDIENTES de redeploy a prod)

### 3.1 `routes/company_ficha.py` — endpoints de cobertura (NUEVOS)
- `GET /api/v1/company/coverage` (X-API-Key) → agregado: `master_total`, `with_financials`, `with_balance_liquidity`, `with_ownership`, `with_governance`, `financial_years_with_cashflow`, `listed_companies` (dinámico), `notes`.
- `POST /api/v1/company/coverage/check` body `{"identifiers":[...]}` (hasta 100) → por CIF `{resolved, reason?, sections:{financials,cash_flow,ownership,governance,events,signals}, counts}`. Sirve a Beta como pre-flight para evitar 404.

### 3.2 `routes/company_intelligence.py` — armonización identity
- Añadido `objeto_social` (alias de `corporate_purpose`) a la respuesta de `POST /api/v2/company-intelligence/identity` y a `data_coverage`.
- Añadidos `is_listed` y `listed_market` a la respuesta de identity (leídos de `master_companies`).

### 3.3 `routes/iberinform_admin.py` — endpoint de SIEMBRA (NUEVO, clave para prod)
- `POST /api/v1/admin/iberinform/reingest-eav?ownership=true&listed=true` (JWT admin) → lanza **subproceso AISLADO** `scripts/prod_seed_eav.py` (NO bloquea el event loop). Devuelve `{run_id, poll}`.
- `GET /api/v1/admin/iberinform/reingest-eav/{run_id}` → estado del run (`eav_reingest_runs`).
- El subproceso hace: re-ingesta EAV completa de balances + ownership (accionistas/participadas) + marca `is_listed` cruzando `bme_companies` por `name_key` + `rebuild_master(force=True)` de las empresas con balance. Idempotente.
- ⚠️ La 1ª versión usaba `asyncio.create_task` in-process y **tumbó el backend** (el rebuild de 13k bloquea el loop). Corregido a subproceso aislado. **NO volver a meter trabajo pesado en el event loop del backend.**

---

## 4. P0 — DESAJUSTE DE ENTORNO (LO MÁS IMPORTANTE, PENDIENTE)

### Evidencia (de la batería Turno D de Beta sobre 6 CIFs)
Beta probó exactamente los 5 CIFs que dimos + A28354132 y obtuvo `cash_flow=null`, `current_ratio=null`, `is_listed=null`, `st_debt/lt_debt=null`, `buyers=0` en IUSTIME — TODO lo contrario a lo verificado en preview. PERO los **rankings coinciden exactamente** con preview, y `/coverage/check` devuelve el **HTML del SPA** (no JSON).

### Conclusión (confirmada)
- **Preview** = Mongo LOCAL (`localhost:27017`, `arroba_agency_tool`). Todo el trabajo de datos está aquí.
- **Producción** (`intel.arroba.com`, lo que consume Beta) = otra base (Atlas) + código antiguo. La base de prod tiene las mismas 25k empresas + revenue (ingesta original), por eso los rankings al vuelo coinciden, pero NO tiene la re-ingesta EAV ni el is_listed, y el código no tiene `/coverage/check` ni el campo `is_listed`.

### Fix (2 pasos, PENDIENTE del usuario — no tengo acceso a prod)
1. **Redeploy** del código de preview a producción.
2. **Sembrar prod**: `POST https://intel.arroba.com/api/v1/admin/iberinform/reingest-eav?ownership=true&listed=true` (JWT admin) y hacer poll hasta `completed`. Puebla en la base de prod: cash_flow, current_ratio + ratios de liquidez, st/lt/financial_debt, current_assets/liabilities, is_listed, ownership.

### Señal de éxito
Desde `intel.arroba.com`: `/coverage/check` responde JSON, y un CIF de los 246 (NCR B28031458 o PROCOLUIDE A81921611) devuelve `statements.cash_flow` no-null y `ratios.current_ratio.available=true`.

### Respuestas a las 7 sub-preguntas de Beta (todas se resuelven tras el fix)
1. cash_flow no es outlier de Servier: prod solo carece de la re-ingesta. 246 empresas tienen EFE tras el seed.
2. current_ratio.available=false: se calcula bajo demanda desde partidas de balance que no existían en prod. OPEL 435, FARNELL 3,85, PROCOLUIDE 1,76 (verificados en preview).
3. is_listed=None en A28354132: SÍ es cotizada (BME). Null por código viejo + base sin marcar. Se arregla con los 2 pasos.
4. buyers IUSTIME 0 vs 2: motor calcula al vuelo desde financials del master; con datos viejos difiere. **A28354132 (buyers=5) y FARNELL (buyers=1) YA funcionan en prod** → control-synergy probable YA con A28354132.
5. /coverage/check: endpoints reales = `GET /company/coverage` + `POST /company/coverage/check` (solo en preview hasta redeploy).
6. Deuda desglosada (CIF prueba PROCOLUIDE A81921611, verificado en preview): st_debt=1.395.128,55 · lt_debt=2.905.096,59 · financial_debt=4.300.225,14 · current_assets=8.123.519,78 · current_liabilities=4.603.804,41 · current_ratio=1,76.
7. /buyers ~10s: cálculo pesado síncrono, independiente del entorno → no bloquear el hero (cargar async) / optimizar upstream (caché/precálculo).

---

## 5. ENRIQUECIMIENTO WEB + ESTABILIDAD (parado por decisión del usuario)

- **Estabilidad**: la API caía porque `uvicorn --reload` vigila `/app/backend` (incluido `scripts/`); ejecutar scripts ahí disparaba un reload que se colgaba en el scraper síncrono de CNMV del arranque. Solución: **runners AISLADOS en `/app/tools_runtime/`** (fuera del árbol vigilado) + `PYTHONDONTWRITEBYTECODE=1` + throttling. Regla: **trabajo pesado siempre en subproceso aislado, nunca en el event loop del backend**.
- **Enriquecimiento web (`description`)**: `web_description` ≈ 2.942/24.992. Las URLs adivinadas por url_discovery dan scraping ok≈0,2% (casi todas muertas); las descripciones reales vienen de las URLs de Iberinform. **PARADO** por el usuario (rendimiento marginal, sin LLM).
- **is_listed (d)**: cableado desde `bme_companies`; solo **1** cotizada solapa con el master: **A28354132 INNOVATIVE SOLUTIONS ECOSYSTEM** (tiene financials → CIF demo de cotizada válido).

---

## 6. CREDENCIALES Y CIFs DEMO

- **Login admin (JWT)**: `daniel@wearebudadvisors.com` / `Thao1971@`. ⚠️ La respuesta de `/api/v1/auth/login` usa la clave **`token`** (NO `access_token`).
- **Service key (X-API-Key, S2S)**: `as_ace1afcc17a0901743f629b3cca64aa4314f433669`.
- **5 CIFs demo** (todos en master, has_financials, tras re-ingesta EAV en preview):
  - `B28031458` NCR ESPAÑA (grande >80M€, G, Madrid)
  - `B50949346` OPEL EUROPE HOLDINGS (mid-cap, K, Zaragoza; current_ratio 435)
  - `A81921611` PROCOLUIDE INDUSTRIAL (SME industrial C, Madrid; deuda desglosada)
  - `B82229907` FARNELL COMPONENTS (SME servicios J, Barcelona; current_ratio 3,85; buyers=1)
  - `V83153700` AGRUPACION IUSTIME (micro, S, Madrid; buyers=2; única con description)
  - `A28354132` INNOVATIVE SOLUTIONS ECOSYSTEM (is_listed=true, BME; buyers=5) — para probar cotizada + control-synergy.
  - `B28184687` LABORATORIOS SERVIER (válido; multi-año por ser fixture antiguo).
- **NO en master (404 esperado, gap de cobertura)**: A28017895 Iberdrola, A08363419 Planeta, B65076193 Technip, B95758389.

---

## 7. FICHEROS CLAVE

- Datos crudos: `/app/data/muestra_25000/*.tab` (10 ficheros, versionados en git → viajan al deploy). `Datos_BALANCES.tab` (17MB, 555k filas, 1 año/empresa).
- Ingesta: `backend/services/data_layer/ingestion/iberinform_tab_ingest.py` (`ingest_balances_file`, `ingest_accionistas_file`, `ingest_participadas_file`), `account_map.py` (`parse_amount`, `derive_metrics`), `bulk.py` (`BulkUpserter`, usa `$set`).
- Master: `backend/services/data_layer/master/master_builder.py` (`rebuild_master`, `_fin_summary`).
- Motor financiero: `backend/services/engines/financial/engine.py` (`analyze`, `valuation`), `metrics.py` (`build_series`, `cashflow_statement`, `_year_metrics`), `ratios_library.py` (`compute_all`).
- Rutas: `routes/company_ficha.py` (ficha + coverage), `routes/company_intelligence.py` (identity), `routes/financial_intelligence.py` (analyze/valuation), `routes/recommendation_intelligence.py` (buyers), `routes/iberinform_admin.py` (upload-delivery + **reingest-eav**).
- **Endpoint de siembra**: `backend/scripts/prod_seed_eav.py` (subproceso aislado).
- Runners aislados (preview, no git-obligatorio): `/app/tools_runtime/{web_enrich_throttled,mark_listed_from_bme,reingest_ownership}.py`.
- Handoffs a Beta (servidos en `{preview}/`): `PARA_BETA_B2_FASE0_RESPUESTA.md`, `PARA_BETA_ENTORNO_RESOLUCION.md`.
- Memoria: `/app/memory/{PRD.md, CHANGELOG.md, test_credentials.md}` (CHANGELOG con detalle día a día).

---

## 8. ESTADO Y PRÓXIMAS ACCIONES

**Hecho y verificado (en preview):** B5 re-ingesta EAV, endpoints coverage, objeto_social, is_listed, ownership idempotente, endpoint de siembra prod (probado end-to-end 7.8s, backend estable).

**PENDIENTE (requiere al usuario / prod):**
1. **Redeploy** del código a producción + **llamar `POST /reingest-eav`** en prod para sembrar los datos. (P0, bloquea a Beta.)
2. Confirmar el `AGENCY_TOOL_BASE_URL` de Beta y que prod usa la Atlas esperada.
3. Re-correr Turno D de Beta tras el seed; desbloquear Item 6 (deuda), control-synergy, is_listed en UI.

**Bloqueado por datos (necesita nueva entrega Iberinform):** multi-ejercicio/evolution/CAGR (histórico), ownership a escala (>318 empresas).

**Backlog:** optimizar latencia de `/buyers` (~10s → caché/precálculo); enriquecimiento `description` (marginal sin mejor fuente / LLM).

**Reglas críticas aprendidas:**
- Preview (local) ≠ Producción (Atlas): los datos NO se comparten; sembrar prod aparte.
- Trabajo pesado (ingesta/rebuild) → SIEMPRE en subproceso aislado, nunca `create_task` in-process (tumba el backend por el reload/loop).
- `/api/v1/auth/login` devuelve `token` (no `access_token`).
- Cash flow y multi-ejercicio están limitados por los DATOS de la muestra, no por el código.
