# ENTREGA INTEL — Ficha (contrato `arroba.v2`)

> Paquete PARA INTEL. Todo el trabajo es en el motor/back-office (`agency-tool` · `intel.arroba.com`).
> Regla de oro respetada: **solo dato real**; si no se puede calcular → `null`/omitir (Beta pinta
> "información en preparación"). Cambios **additivos**, sin regresión, textos en prosa de Corporate
> Finance (sin nombres internos ni de proveedores).
>
> **Estado global: FASE I-1 COMPLETA + huecos reales de I-2/I-3 cubiertos.** El resto del plan (I-2/I-3/I-4)
> ya era consumible con `X-API-Key` y se ha verificado 200.
>
> ⚠️ Todo está en **preview** y requiere **redeploy** para estar en producción (`intel.arroba.com`).

---

## 1. Resumen ejecutivo

| Fase | Ítems | Estado |
|------|-------|--------|
| **I-1** Núcleo de la Ficha | #1–#5 | ✅ **COMPLETO** (poblado y verificado) |
| **I-2** Secciones de alto valor | #6–#11 | ✅ #6,#7,#8 nuevos · #9,#10,#11 ya existían |
| **I-3** Inteligencia diferencial | #12–#15 | ✅ #15 nuevo · #12,#13,#14 ya existían |
| **I-4** Copilot | #16 | ✅ ya existía (`/copilot/ask`, service-key) |
| **Extras** | agregador `/ficha`, percentiles ampliados | ✅ nuevos |

Verificación transversal: smoke con `X-API-Key` sobre **3 empresas variadas** — Servier `B28184687`
(grande auditada), `B95222139` (PYME, cuentas abreviadas), `A0051199H` (sin cuentas). Sin regresión.

---

## 2. Detalle por ítem del plan

### FASE I-1 — Núcleo (endpoint `POST /api/v1/financial-intelligence/analyze`, salvo #1)

- **#1 Identidad enriquecida (Hero)** — ✅ HECHO
  `POST /api/v2/company-intelligence/identity` puebla con dato real:
  - `corporate_purpose` ← objeto social del dato maestro.
  - `description` ← enriquecimiento web (nuevo; antes venía vacío).
  - `activity` ← descripción CNAE.
  - `data_coverage.description` reflejado.

- **#2 Flujo de caja** — ✅ HECHO
  `analyze.statements.cash_flow = { years, rows:[{key,label,category,values:[{value,format}]}] }`.
  Filas: **OCF, capex, financiación, variación de caja, FCF, conversión de caja (OCF/EBITDA, %)**.
  Si la empresa no declara EFE (cuentas abreviadas/PYME) → `statements.cash_flow = null` +
  `statements.cash_flow_note` explicando el porqué.

- **#3 Ratios: percentil + tendencia** — ✅ HECHO
  Cada ratio lleva `trend` (▲/▼/▬ vs año anterior) + `prev_value` + `delta`, y `percentile`
  (percentil sectorial nacional) + `percentile_sample` donde hay muestra ≥20.
  Cobertura de percentil actual: solvency, debt_ratio, roe, roa, capital_intensity, ebit_margin,
  net_margin, ebitda_margin (ver §4 cobertura).

- **#4 Posición relativa (`ranking`)** — ✅ HECHO
  `analyze.ranking = { sector_revenue_percentile, market_position:{rank,total,scope},
  locality_position:{rank,total,scope}, explain:[frases CF] }`.

- **#5 Valoración: escenarios + benchmark** — ✅ HECHO
  `valuation.scenarios = [{label,multiple,enterprise_value,equity_value}]` (conservador/base/optimista);
  `valuation.benchmark = [{metric,company,category,format}]` (empresa vs mediana categoría) +
  `benchmark_scope`, `ebitda_margin_percentile`, `methodology` (texto CF).

### FASE I-2 — Secciones de alto valor

- **#6 Estructura de propiedad y control** — ✅ NUEVO
  `GET /api/v1/company/{id}/ownership` → accionistas (nombre, %, CIF si hay), concentración,
  accionista de control, tramo de control (mayoritario / significativo / disperso).

- **#7 Gobierno / personas** — ✅ NUEVO
  `GET /api/v1/company/{id}/governance` → órgano de administración (nombre, cargo, fecha, año),
  deduplicado por persona+cargo.

- **#8 Sinergias con comprador (control-synergy)** — ✅ NUEVO (service-key)
  `GET /api/v1/company/{id}/control-synergy/{buyer_id}` → control real + sinergias estructurales
  con racional en lenguaje natural. (Antes solo accesible con login de usuario.)

- **#9 Mercado / sector + Rankings** — ✅ YA EXISTÍA (service-key)
  `sector-intelligence`, `geo-intelligence`, `economic-intelligence` + el `ranking` de la empresa (#4).

- **#10 Documentos** — ✅ YA EXISTÍA
  Superficie de generación de informes (`ext/documents/*`) con `X-API-Key`.

- **#11 Seguimiento / alertas** — ✅ YA EXISTÍA
  `watchlist` + `alerts`.

### FASE I-3 — Inteligencia diferencial

- **#12 Recomendación del comité** — ✅ YA EXISTÍA (service-key)
  `investment-decision`: `/committee`, `/decision/{id}`, `/analyze`, `/recommendations`,
  `/decision/{id}/ask`, `/decision/{id}/export-payload`.

- **#13 Veredicto ejecutivo (narrativa)** — ✅ YA EXISTÍA (service-key)
  `strategy-intelligence/thesis` (+ growth/acquisition/divestment/…) y copilot.
  *Pendiente opcional*: empaquetar el formato exacto "1 frase posicionamiento + 1 frase atractivo M&A"
  como `GET /company/{id}/verdict` si Beta lo quiere calcado (ver §5).

- **#14 Sucesión / Roll-up / Fragmentación** — ✅ YA EXISTÍA (service-key)
  `signal-intelligence/succession-profile/{id}`, `investment-intelligence/rollup-thesis`,
  `investment-intelligence/fragmentation`.

- **#15 Eventos (registros BORME)** — ✅ NUEVO
  `GET /api/v1/company/{id}/events` → cronología de actos (fecha, tipo, subtipo, título, extracto,
  sección, provincia). Enlace por nombre normalizado.

### FASE I-4 — Copilot

- **#16 Asistente (`/ask`)** — ✅ YA EXISTÍA (service-key)
  `POST /api/v1/copilot/ask` con contexto de empresa (S2S).

---

## 3. Extra entregado (no pedido explícitamente, alto valor para Beta)

- **Agregador `GET /api/v1/company/{id}/ficha`** (service-key): **una sola llamada** devuelve
  `identity` + `finances` (analyze completo) + `ranking` + `ownership` + `governance` + `events`.
  Null-safe por bloque. Simplifica el consumo de Beta (1 request en vez de orquestar 6).
- **Backfill `financials.latest.ratios`** en 13.464 empresas → habilita percentiles sectoriales por ratio.
- **Arranque no bloqueante** del backend + endpoints de salud `/api/v1/health` (liveness) y
  `/api/v1/health/deep` · `/api/v1/readyz` (readiness con ping a Mongo) → sin ventanas de 520 en redeploys.

---

## 4. Cobertura real (transparencia — muchas fichas mostrarán "en preparación")

Por la naturaleza del dato de origen (Iberinform; mayoría de PYMES con **cuentas abreviadas**):

- **Ingresos/financieros**: ~9.593 / 24.992 empresas tienen estados financieros.
- **Cash flow (EFE)**: solo declarantes de **cuentas completas** (no PYME/abreviadas).
- **Percentil por ratio**: hoy cubre 8 ratios (rentabilidad + solvencia + intensidad de capital).
  **Liquidez/working-capital (current_ratio, DSO, DPO, días de existencias, deuda/FFPP,
  fondo de maniobra) = 0 cobertura** porque las cuentas abreviadas no traen esas líneas de balance.
  → Ya está **cableado**: aparecerán solos en cuanto se ingiera/denormalice el EAV de balance.
- **Objeto social**: 22.063 / 24.992. **Descripción web**: 29 / 24.992 (solo pilotos de enriquecimiento).
- **Eventos BORME**: solo si hay actos con nombre normalizado coincidente.
- **Propiedad/gobierno**: según lo declarado en Iberinform.

---

## 5. Pendiente / backlog (por prioridad)

**P0 — Operativo**
1. **Redeploy a producción** para publicar todo lo anterior en `intel.arroba.com`.

**P1 — Aumentar cobertura (dato, no código)**
2. **Ingesta EAV de balance** (current_assets, current_liabilities, trade_debtors, inventories,
   suppliers, financial_debt): activa cash flow + percentiles de liquidez/working-capital en más fichas.
   El código ya está listo; solo falta el dato.
3. **Enriquecimiento web a escala**: subir la cobertura de `description` (hoy 29 empresas).

**P2 — Refinamientos de contrato (si Beta los pide)**
4. **`GET /company/{id}/verdict`**: veredicto ejecutivo en el formato exacto del plan
   (1 frase posicionamiento + 1 frase atractivo M&A), sobre strategy-thesis/copilot.
5. **Árbol societario multi-nivel**: exponer `/graph/{id}/traverse` como árbol con beneficiario último
   (hoy `ownership` es de 1 nivel).
6. **`ratio.percentile_label`** y **`benchmark.delta_vs_category`** ya redactados en prosa CF
   (que Beta no calcule nada en el front).
7. **Cache de `/ficha`** por CIF (TTL corto) para bajar latencia si se llama en cada render.

**FUERA DE ALCANCE (decisión del plan)**
- **Innovación (Alta/Media/Baja)**: NO existe motor de innovación/patentes/I+D. Habría que construirlo.

---

## 6. Índice de endpoints `arroba.v2` para la Ficha (todos `X-API-Key`)

| Necesidad Ficha | Endpoint |
|---|---|
| Hero / identidad | `POST /api/v2/company-intelligence/identity` |
| Finanzas (P&L, balance, cash flow, ratios, valoración, ranking) | `POST /api/v1/financial-intelligence/analyze` |
| Propiedad y control | `GET /api/v1/company/{id}/ownership` |
| Gobierno / personas | `GET /api/v1/company/{id}/governance` |
| Sinergias con comprador | `GET /api/v1/company/{id}/control-synergy/{buyer_id}` |
| Eventos registrales (BORME) | `GET /api/v1/company/{id}/events` |
| **Ficha completa (1 llamada)** | `GET /api/v1/company/{id}/ficha` |
| Comité / decisión | `POST /api/v1/investment-decision/committee` · `/decision/{id}` |
| Tesis / veredicto | `POST /api/v1/strategy-intelligence/thesis` |
| Sucesión | `GET /api/v1/signal-intelligence/succession-profile/{id}` |
| Roll-up / fragmentación | `GET /api/v1/investment-intelligence/rollup-thesis` · `/fragmentation` |
| Compradores / comparables | `POST /api/v1/recommendation-intelligence/buyers` · `/comparables` |
| Sector / geo / economía | `sector-intelligence` · `geo-intelligence` · `economic-intelligence` |
| Documentos | `ext/documents/*` |
| Seguimiento / alertas | `watchlist` · `alerts` |
| Copilot | `POST /api/v1/copilot/ask` |

---

*Documento generado en preview. Verificado con `X-API-Key` sobre Servier `B28184687`, `B95222139`
(PYME) y `A0051199H` (sin cuentas). Requiere redeploy para producción.*
