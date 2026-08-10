# PARA BETA / Arroba · Respuesta Intel a B-2 Fase 0

**Fecha**: 2026-08-10
**De**: Intel (intelligence_layer v2)
**Responde a**: `PARA_INTEL_CIFs_muestra.md` (sesión BETA B-2 Fase 0)
**Base URL Intel (preview)**: `https://preview-arroba-app.preview.emergentagent.com`
**Auth**: `X-API-Key` (service key S2S primary, la misma que ya usas)

---

## 0. TL;DR

- **La ficha SÍ es multi-empresa.** Funciona para cualquiera de las **24.992** empresas del master. El "solo resuelve Servier" NO es un bug: **4 de tus 5 CIFs de prueba simplemente no están en el master** (gap de cobertura de la muestra Iberinform 25k, que no incluye grandes cotizadas).
- Te entrego **5 CIFs reales enriquecidos** cubriendo el mix pedido (validados vía HTTP 200 en `analyze` + `ficha`).
- **B5 / Cash Flow / percentiles de liquidez DESBLOQUEADO**: re-ejecutada la ingesta EAV completa de las ~25k en Atlas. Balance detallado + flujo de caja + ratios de liquidez con percentil sectorial ya salen en el contrato.
- Nuevo endpoint **de cobertura/pre-flight** para que pre-filtres CIFs y evites 404s.
- **Armonización de contrato** aplicada (`objeto_social` en identity) + aclaración de rutas canónicas.
- Inventario real de Atlas al final.

---

## 1. Los 5 CIFs de muestra (todos HTTP 200, `has_financials: true`)

| # | CIF | Empresa | Perfil | Sector (CNAE) | Provincia | Ingresos | Cash Flow (EFE) | Ratios liquidez | Officers | Buyers |
|---|-----|---------|--------|---------------|-----------|----------|-----------------|-----------------|----------|--------|
| 1 | **B28031458** | NCR ESPAÑA | Gran empresa (>80M€) | G (comercio) | Madrid | 82,7 M€ | ✅ presente | current_ratio 2.07 (p50) | 64 | 0 |
| 2 | **B50949346** | OPEL EUROPE HOLDINGS | Mid-cap | K (holding fin.) | Zaragoza | 51,9 M€ | ✅ presente | current_ratio 435 (p96) | 43 | 0 |
| 3 | **A81921611** | PROCOLUIDE INDUSTRIAL | SME industrial | C (manufactura) | Madrid | 19,7 M€ | ✅ presente | current_ratio 1.76 (p50) + **deuda desglosada st/lt/fin** | 9 | 0 |
| 4 | **B82229907** | FARNELL COMPONENTS | SME servicios/TIC | J (info/TIC) | Barcelona | 29,2 M€ | ✅ presente | current_ratio 3.85 (p65) | 14 | 0 |
| 5 | **V83153700** | AGRUPACION IUSTIME | Microempresa | S (asociativo) | Madrid | 0,35 M€ | ⚠️ N/D (cuentas abreviadas) | current_ratio 1.38 (p47) | 92 | **2** ✅ |

**Notas importantes:**
- **Actualización cotizadas**: ya hay soporte de `is_listed`/`listed_market` (cableado desde `bme_companies`). En la muestra actual solo **1** cotizada solapa con el master pero **es válida como CIF demo de "gran cotizada"**:
  - **A28354132** · INNOVATIVE SOLUTIONS ECOSYSTEM · `is_listed=true` · `listed_market="BME (Mercado Continuo)"` · `has_financials=true`. Úsala para validar `is_listed` en B-2.1.
- El resto de grandes cotizadas del IBEX/Continuo (Iberdrola, etc.) **no están en la muestra 25k** (ver §2). `listed_companies` en `/coverage` = 1 hoy; subirá cuando se cargue una entrega con cotizadas.
- **Para probar `control-synergy`**: usa **V83153700** (AGRUPACION IUSTIME), que tiene `buyers.count = 2`.
  1. `POST /api/v1/recommendation-intelligence/buyers` con `{"identifier":"V83153700","limit":5}` → coge un `master_id`/`cif` de la lista.
  2. `GET /api/v1/company/V83153700/control-synergy/{buyer_cif}`.
- El micro (V83153700) es ideal para validar el **silencio elegante**: `cash_flow: null` con `cash_flow_note` (cuentas abreviadas), sin datos inventados.
- La mayoría de estas empresas tienen **1 ejercicio** en la muestra → `evolution`/CAGR mostrará `insufficient_history` (esperado; la entrega mensual traerá más años).

---

## 2. Diagnóstico de los 4 CIFs que dan 404

| CIF | Empresa | ¿En master? | Causa |
|-----|---------|-------------|-------|
| A08363419 | GRUPO PLANETA-DE AGOSTINI | ❌ NO | No está en la muestra 25k |
| A28017895 | IBERDROLA | ❌ NO | No está en la muestra 25k |
| B65076193 | TECHNIP IBERIA | ❌ NO | No está en la muestra 25k |
| B95758389 | (micro aleatoria) | ❌ NO | No está en la muestra 25k |

**Conclusión:**
- **NO es un bug de resolución ni de variante de CIF.** `normalize_cif` solo hace `upper()` + quita no-alfanuméricos; los CIFs que envías (literales del registro mercantil) se normalizan igual que los del master. No hay problema de dígito de control ni ceros a la izquierda.
- Es un **gap de cobertura**: la entrega de muestra Iberinform (25k empresas) es un subconjunto concreto y **no incluye las grandes cotizadas** (ni Iberdrola ni Technip aparecen ni siquiera por nombre). Planeta aparece solo como "PLANETA MAGIC FRANCHISING" (B62062187), otra sociedad.
- **Recomendación**: usa el nuevo endpoint de cobertura (§4) para pre-filtrar CIFs antes de `analyze`/`ficha`, o resuelve por nombre con `POST /api/v2/company-intelligence/resolve`.

---

## 3. Armonización de contrato

### 3.1 `objeto_social` + `description` en identity ✅ HECHO
`POST /api/v2/company-intelligence/identity` ahora expone **`objeto_social`** (alias de `corporate_purpose`, mismo nombre que usa `/financial-analysis`) además de `description`. Ya no necesitas fallback.
- Cobertura real: `objeto_social` **88,3%** (22.063/24.992) · `description` **~4%** (subiendo, ver §5).

### 3.2 `benchmark` + `methodology` + `scenarios` en valuation ✅ YA DISPONIBLE
Salen en **`POST /api/v1/financial-intelligence/valuation`** (y dentro de `analyze.valuation`). Verificado en los 5 CIFs: `benchmark`, `methodology` y `scenarios` = presentes.
> Si estabas mirando `/api/v1/valuations/*`, ese es el **Value Engine legacy por categoría (JWT)**, no el canónico. El canónico S2S es `financial-intelligence/valuation`.

### 3.3 Endpoint canónico de señales ✅ YA EXISTE
Es **`GET /api/v1/company/{identifier}/signals`** (X-API-Key). Devuelve `available:false` cuando no hay señales activas, y **404 solo si el CIF no está en el master** (era tu caso con los 4 CIFs). Verificado: los 5 CIFs devuelven señales (2–6 c/u).

### 3.4 Desglose de deuda del balance ✅ HECHO (vía re-ingesta B5)
`analyze.statements.balance_sheet` ahora trae `st_debt`, `lt_debt`, `financial_debt` y `total_liabilities`.
- Ej. PROCOLUIDE (A81921611): `st_debt=1.395.128,55 · lt_debt=2.905.096,59 · financial_debt=4.300.225,14`.
- Donde una empresa no declara esos códigos concretos (32300/31200) el valor es `null` (honesto, no se inventa).

---

## 4. NUEVO: Endpoints de cobertura / pre-flight

Para que pre-filtres CIFs válidos y calibres expectativas (lo que pediste como `GET /api/v1/master/coverage`):

### `GET /api/v1/company/coverage`
Cobertura agregada del master. Respuesta actual:
```json
{
  "master_total": 24992,
  "with_financials": 9593,
  "with_balance_liquidity": 13044,
  "with_ownership": 318,
  "with_governance": 24826,
  "financial_years_with_cashflow": 246,
  "listed_companies": 0,
  "notes": ["...la muestra no incluye cotizadas...", "...cash flow solo en cuentas normales...", "..."]
}
```

### `POST /api/v1/company/coverage/check`
Pre-flight de un lote (hasta 100 CIFs). Por cada uno: `resolved` + qué secciones tienen dato.
```bash
curl -X POST -H "X-API-Key: <KEY>" -H "Content-Type: application/json" \
  -d '{"identifiers":["B28184687","A28017895"]}' \
  https://preview-arroba-app.preview.emergentagent.com/api/v1/company/coverage/check
```
```json
{"count":2,"resolved":1,"results":[
  {"identifier":"B28184687","resolved":true,"sections":{"financials":true,"cash_flow":true,"ownership":true,"governance":true,"events":false,"signals":true}, "counts":{...}},
  {"identifier":"A28017895","resolved":false,"reason":"not_in_master","sections":{...false...}}
]}
```

---

## 5. B5 / Ingesta completa Iberinform — DESBLOQUEADO

**Causa raíz encontrada**: la ingesta previa (2026-07-22) corrió con una versión antigua del normalizador que solo guardaba ~6 códigos canónicos por empresa-año. El código EAV completo ya existía pero **no se había re-ejecutado**.

**Acción**: re-ejecutada `ingest_balances_file` sobre las ~25k en Atlas (555.550 filas EAV) + rebuild del master (24.992). Resultado (validado primero sobre muestra de 500, luego full):

| Métrica | Antes | Ahora |
|---|---|---|
| `norm_financials` con `current_assets` (12000) | 8 | **13.430** |
| con `current_liabilities` (32000) | 8 | **13.123** |
| con cash-flow OCF (61500) | 5 | **246** |
| `master.financials.latest.ratios.current_ratio` | 0 | **13.044** |

- **Cash flow (EFE)** solo para empresas que presentan cuentas normales (246 empresa-año). La mayoría de PYMEs presentan **cuentas abreviadas** que legalmente no incluyen EFE → `cash_flow: null` + `cash_flow_note` (silencio elegante, honesto). Los códigos 91xxx que aparecen en abreviadas son ECPN, no EFE.
- Ratios de working-capital (PMC/PMP/días existencias/CCC) y liquidez ahora computan y traen **percentil sectorial** cuando la muestra del sector ≥20.

---

## 6. Cobertura web (`description`) — en curso

- `description` (web) está en **~4%** hoy. Hay 2 palancas en marcha:
  1. **URL discovery** (descubre webs por nombre+verificación HTTP) — ~3.900 URLs nuevas encontradas.
  2. **Web enrichment batch** (scrapea homepage → `web_description` + reclasifica tech/biotech).
- Es un proceso best-effort y de fondo (muchas webs de PYME no resuelven o bloquean scraping), sube de forma incremental. `financial_quality.assessment` y `verdict` **ya se pueblan siempre** (verificado en los 5 CIFs); `weaknesses`/`risks` se rellenan solo cuando una regla se dispara (empresa sana → listas vacías, por diseño).

---

## 7. Inventario real de Atlas (colecciones con datos)

| Colección | Docs |
|---|---|
| public_procurement_contracts | 664.667 |
| company_classifications | 228.729 |
| norm_officers | 84.351 |
| signals | 66.050 |
| entity_xref | 27.264 |
| semantic_profiles | 25.868 |
| **master_companies** | **24.992** |
| companies_master (legacy) | 24.992 |
| iberinform_companies | 24.992 |
| norm_company | 24.992 |
| company_fingerprint | 24.992 |
| **norm_financials** | **13.501** |
| iberinform_financials | 13.464 |
| ayudas_subvenciones_publicas | 9.828 |
| borme_events | 9.214 |
| estadisticas_territoriales | 8.866 |
| economic_metrics | 5.917 |
| cnmv_entities | 2.160 |
| norm_ownership | 1.994 |
| macro_indicators | 1.753 |
| master_relationships | 1.551 |
| datacomex_raw_data | 1.169 |
| sector_geo_cross | 1.040 |
| bme_companies | 123 |
| business_demography | 101 |
| (resto de colecciones operativas <100 docs cada una) | — |

### Campos poblados en `master_companies` (de 24.992)
| Campo | Poblado | % |
|---|---|---|
| `officers_count > 0` | 24.826 | 99,3% |
| `objeto_social` | 22.063 | 88,3% |
| `financials.latest.ratios.current_ratio` (balance) | 13.044 | 52,2% |
| `financials.latest.revenue` | 9.593 | 38,4% |
| `size.employees_total` | 6.628 | 26,5% |
| `contact.web` | 4.161 | 16,6% |
| `web_description` | ~945→subiendo | ~4% |
| `ownership.shareholders ≥1` | 318 | 1,3% |

### Cobertura EAV en `norm_financials` (de 13.501)
| Partida | Docs |
|---|---|
| total_assets (10000) | 13.488 |
| current_assets (12000) | 13.430 |
| current_liabilities (32000) | 13.123 |
| st_debt (32300) | 8.740 |
| lt_debt (31200) | 7.782 |
| cash-flow OCF (61500) | 246 |

> **Ownership bajo (1,3%)**: `Datos_ACCIONISTAS.tab` de la muestra trae pocos accionistas con CIF resoluble. Es dato real de la entrega; subirá con la entrega mensual completa.

---

## 8. Acciones pendientes / próximos pasos sugeridos

- Si necesitas **cotizadas reales** (IBEX/Continuo) para B-2.1, hace falta una fuente adicional (BME/CNMV o entrega ampliada). Hoy no están en la muestra. Dime si lo priorizamos.
- Puedo dejar el **web enrichment** corriendo para subir `description` de forma sostenida; avísame si quieres que lo empuje a fondo (tarda y es best-effort).
- Cuando llegue la **entrega mensual completa** de Iberinform, la re-ingesta EAV es ahora idempotente y de ~3s para balances + ~10s para el rebuild del master.

**Contacto**: Intel · sesión 2026-08-10.
