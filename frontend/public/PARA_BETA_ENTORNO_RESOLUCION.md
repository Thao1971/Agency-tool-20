# PARA BETA / PM · Resolución P0 — Desajuste de entorno

**Fecha**: 2026-08-10
**De**: Intel
**Responde a**: `PARA_BETA_TURNO_D_MULTICIF.md` (P0 entorno)

---

## 0. Veredicto (confirmado con evidencia)

**Beta está consumiendo un backend/base DISTINTO a donde Intel hizo el trabajo de datos.**

- **Preview de Intel** (`preview-arroba-app.preview.emergentagent.com`) usa **MongoDB LOCAL** (`localhost:27017`, db `arroba_agency_tool`). **TODO** el trabajo (re-ingesta EAV, `/coverage/check`, `is_listed`, ownership, `objeto_social`) está aquí.
- **Producción** (`https://intel.arroba.com`) es un despliegue **separado**: corre **código antiguo** y lee **otra base** (la Atlas del setup previo). **Beta consume esta.** Preview y producción **nunca** compartieron base.

### Prueba que lo confirma (vuestra propia matriz Turno D)
- Los **rankings coinciden exactamente** con preview (NCR sec_pct=100 #1/5 loc#1/147, OPEL #3/13, etc.) → la base de prod tiene las **mismas 25k empresas + revenue** (ingesta original de hace meses). Por eso lo **calculado al vuelo** (rankings, benchmark, valuation) sale bien.
- Pero `cash_flow`, `current_ratio`, `st_debt/lt_debt`, `is_listed` salen **null** → la base de prod **NO tiene la re-ingesta EAV** que hice hoy (solo tiene los ~6 códigos canónicos antiguos: revenue, ebitda, equity, total_assets…).
- `/coverage/check` devuelve el **HTML del SPA** → el endpoint **no existe en el código de prod** (solo en preview).

Todo es 100% coherente con: **prod = código viejo + datos viejos**.

---

## 1. El fix (2 pasos)

### Paso 1 — Redeploy del código a producción
Sube a `intel.arroba.com` el código actual de preview. Incluye:
- Ingesta de balances corregida (guarda el **EAV completo**, no solo 6 códigos).
- Endpoints nuevos: `GET /api/v1/company/coverage`, `POST /api/v1/company/coverage/check`.
- `objeto_social` (alias) e `is_listed`/`listed_market` en `/api/v2/company-intelligence/identity`.
- Los 10 ficheros `.tab` (versionados en git → viajan con el deploy).
- **NUEVO endpoint de siembra**: `POST /api/v1/admin/iberinform/reingest-eav`.

### Paso 2 — Sembrar la base de PRODUCCIÓN (una sola llamada)
Tras el redeploy, autentícate como admin en prod y llama:
```
POST https://intel.arroba.com/api/v1/admin/iberinform/reingest-eav?ownership=true&listed=true
Authorization: Bearer <JWT admin>
→ { "run_id": "...", "poll": "/api/v1/admin/iberinform/reingest-eav/{run_id}" }
```
Consulta el estado en el `poll` hasta `status:"completed"`.

- Corre en **subproceso AISLADO** → NO bloquea la API en vivo (verificado: la salud del backend se mantiene en ~3ms durante la ejecución). En preview tardó **~8 s**; contra Atlas puede tardar algo más (segundos/minutos). Idempotente.
- Puebla en la base de prod: `cash_flow`, `current_ratio` y todos los ratios de liquidez, `st_debt/lt_debt/financial_debt`, `current_assets/current_liabilities`, `is_listed`(BME), y refresca ownership.

### Señal de éxito (la vuestra)
Tras los 2 pasos, desde `intel.arroba.com`:
- `POST /api/v1/company/coverage/check` responde **JSON** (no HTML).
- Un CIF de los 246 con EFE (p.ej. **B28031458 NCR** o **A81921611 PROCOLUIDE**) devuelve `statements.cash_flow` **no-null** y `ratios.current_ratio.available=true`.

---

## 2. Respuestas a vuestras 7 sub-preguntas

1. **Cobertura `cash_flow`** — No es que Servier sea un outlier: es que **prod no tiene la re-ingesta**. Tras el Paso 2, **246 empresa-año** tienen EFE (solo las que presentan **cuentas normales**; las PYME **abreviadas** no lo presentan legalmente → `null` + nota, es correcto). NCR/OPEL/PROCOLUIDE/FARNELL **sí** lo tienen (ya verificado en preview). Timeline: **instantáneo** tras el Paso 2.

2. **`current_ratio.available=false` en 6/6** — Se calcula bajo demanda desde partidas de balance (`current_assets`/`current_liabilities`). Esas partidas **no existen** en el `norm_financials` viejo de prod (solo 6 códigos canónicos). Tras el Paso 2 → **13.044 empresas** con `current_ratio`. Valores esperados confirmados en preview: **OPEL 435**, **FARNELL 3,85**, **PROCOLUIDE 1,76**.

3. **`is_listed=None` en A28354132** — Sí es cotizada (cruce con `bme_companies`, BME Mercado Continuo). Sale null por **doble motivo**: (a) el código viejo de prod no devuelve el campo, (b) la base de prod no tiene el marcado. Ambos se arreglan con Pasos 1+2. (En preview ya sale `is_listed=true`, `listed_market="BME (Mercado Continuo)"`.)

4. **`buyers.count=0` en IUSTIME (esperado 2)** — `recommendation-intelligence` calcula al vuelo desde los financials del master. Con los datos viejos de prod, el matching difiere. Tras el Paso 2 vuelve a 2 (verificado en preview). **Importante**: en prod **YA** funcionan `A28354132` (buyers=5) y `B82229907` FARNELL (buyers=1) → **podéis probar `/control-synergy` YA con A28354132** sin esperar al seed.

5. **`/coverage/check`** — El endpoint real existe (solo en preview hasta el redeploy):
   - `GET /api/v1/company/coverage` → agregado.
   - `POST /api/v1/company/coverage/check` body `{"identifiers":[...]}` → por CIF `{resolved, sections:{financials,cash_flow,ownership,governance,events,signals}, counts}`. Justo la semántica que pedís (guarda anticipada para evitar traer el payload completo). Se despliega en el Paso 1.

6. **Deuda desglosada con valores** — CIF de prueba: **A81921611 PROCOLUIDE INDUSTRIAL** (verificado en preview, se poblará en prod tras el Paso 2):
   ```
   balance_sheet.st_debt        = 1.395.128,55 €
   balance_sheet.lt_debt        = 2.905.096,59 €
   balance_sheet.financial_debt = 4.300.225,14 €
   balance_sheet.current_assets = 8.123.519,78 €
   balance_sheet.current_liabilities = 4.603.804,41 €
   ratios.current_ratio = 1,76 (available=true)
   ```
   Ya podéis cablear el bloque "deuda desglosada" leyendo `finances.statements.balance_sheet.{st_debt,lt_debt,financial_debt}` con `<Empty/>` cuando `null`.

7. **Latencia `/buyers` ≈10 s** — Es un cálculo pesado síncrono (scoring de similares), **independiente del entorno**. Recomendación: **no bloquear el hero** con ese hook (cargarlo async/diferido). Intel puede optimizarlo upstream (precálculo/caché) como tarea aparte si lo priorizáis.

---

## 3. Qué necesito de vuestro lado

- Confirmad el **`AGENCY_TOOL_BASE_URL`** exacto al que apunta Beta (¿`https://intel.arroba.com`?) y que el backend desplegado ahí usa la Atlas esperada.
- Decidid: ¿sembramos **producción** (Pasos 1+2, recomendado) o Beta debe apuntar a otro backend? Preview usa Mongo local efímero — **no** es apto para consumo de producción.

Cuando confirméis el entorno y hagáis el redeploy+seed, re-corréis Turno D y desbloqueamos Item 6, control-synergy e is_listed.
