# GUÍA DE INTEGRACIÓN — `arroba.v2` (contrato público tipado)
**Manual de consumo del contrato v2: DTOs de respuesta tipados + capacidad Company/Identity.**
_Versión: `arroba-integration-contract-v2` · 2026-07-12 · Estado: **APROBADO Y CONGELADO** · convive con `arroba.v1`._

> Complementa (no sustituye) a `ARROBA_INTEGRATION_PACK_v1.md` y `ARROBA_ONBOARDING_HANDOFF.md`.
> Todo lo de v1 (Base URL, `X-API-Key`, rate limits, errores, identidad por `master_id`/`cif_normalized`,
> playbooks por experiencia) **sigue vigente sin cambios**. v2 solo **añade tipado y una capacidad nueva**.

---

## 1. Qué es `arroba.v2` y por qué existe
`arroba.v2` es un **superset TIPADO de `arroba.v1`**:
1. **V2-01 — DTOs de respuesta tipados.** Los 53 endpoints de los 6 motores ahora describen su respuesta
   `200` con un **schema nombrado** en OpenAPI (antes `schema: {}`). Esto permite **generar un SDK
   totalmente tipado** sin escribir tipos a mano.
2. **V2-02 — Company/Identity público.** Nuevo endpoint `POST /api/v2/company-intelligence/identity`
   que proyecta la **identidad canónica** del Master Record para la cabecera de la Ficha de Empresa
   (componentes COMP-1001/1002/1003).

**Garantía clave:** v2 **NO cambia el comportamiento en runtime** de ningún motor. Los DTO **documentan**
la respuesta; **no filtran ni recortan** campos (son abiertos / `additionalProperties`). Cualquier campo
que hoy devuelve un motor se sigue devolviendo idéntico. `arroba.v1` permanece **byte-idéntico y congelado**.

---

## 2. URLs del contrato (v1 y v2 conviven)
| Recurso | Preview | Producción |
|---|---|---|
| **OpenAPI v1 (congelado)** | `…preview…/api/v1/openapi/arroba.v1.json` | `https://agencias.wearebudadvisors.com/api/v1/openapi/arroba.v1.json` |
| **OpenAPI v2 (tipado)** | `…preview…/api/v1/openapi/arroba.v2.json` | `https://agencias.wearebudadvisors.com/api/v1/openapi/arroba.v2.json` |
| **Swagger UI v1** | `…preview…/api/docs/arroba` | `…/api/docs/arroba` |
| **Swagger UI v2** | `…preview…/api/docs/arroba/v2` | `…/api/docs/arroba/v2` |

- Preview Base URL: `https://data-factory-hub.preview.emergentagent.com`.
- `arroba.v2.json`: **55 rutas** (53 motores + `/api/v2/company-intelligence/identity` + `/api/v2/company-intelligence/resolve`), **94 schemas** nombrados.
- Snapshot documental congelado en el repo: `backend/contracts/arroba.v2.json` (protegido por freeze test en CI).

**Recomendación:** para la **Ficha de Empresa** genera el cliente desde **`arroba.v2.json`** (respuestas
tipadas + Company/Identity). Si ya tienes integración v1, puedes migrar por componente sin big-bang: mismos
paths, mismos runtime; solo mejora el tipado.

---

## 2-bis. Identificador oficial y resolución pública (F0.2)
**Identificador oficial de entrada: `CIF`.** Todos los contratos públicos son **agnósticos al
identificador**: aceptan indistintamente `cif_normalized` (CIF) **o** `master_id` en el campo
`identifier`. Arroba puede integrar **usando el CIF de extremo a extremo** — no necesita `master_id`.
El `master_id` (clave canónica interna, estable) se devuelve en toda respuesta por si se quiere cachear.

**Resolución pública `CIF|Nombre → master_id`** (sin JWT, sin `/master/*`, sin Mongo):
- **Ruta:** `POST /api/v2/company-intelligence/resolve` · **Auth:** `X-API-Key`.
- **Request:** `{ "cif": "A87803862" }`  o  `{ "name": "Totalenergies", "limit": 10 }` (uno de los dos).
- **Response (`CompanyResolveResponse`):** `{ query, count, matches: [{ master_id, cif, legal_name,
  province, cnae_section, match_type, score }], capability_version }`.
  - `match_type`: `cif_exact` (score 1.0) · `name_exact` (1.0) · `name_partial` (0.6).
- **Errores:** `401` sin API key · `422` si no se envía `cif` ni `name`.
```bash
curl -s -X POST "$BASE/api/v2/company-intelligence/resolve" -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" -d '{"cif":"A87803862"}'
# → { "count":1, "matches":[{"master_id":"mc_...","cif":"A87803862",
#      "legal_name":"TOTALENERGIES ELECTRICIDAD Y GAS ESPAÑA","match_type":"cif_exact","score":1.0}] }
```

## 3. V2-02 · Company/Identity — referencia del endpoint
Identidad canónica pública de una empresa (proyección de solo lectura del Master Record). Alimenta la
cabecera de la Ficha (razón social, nombre comercial, CIF, forma jurídica, domicilio, CNAE, web, capital…).

- **Método/Ruta:** `POST /api/v2/company-intelligence/identity`
- **Auth:** cabecera `X-API-Key` (igual que los motores).
- **Request:** `{ "identifier": "<master_id | cif_normalized>" }`  · ej. `{ "identifier": "B59022921" }`
- **Errores:** `401` sin/mal API key · `404` `company not found in Master Layer` · `422` body inválido.

### 3.1 Respuesta (`CompanyIdentityResponse`)
> **Nunca inventa datos**: los campos no verificables se devuelven como `null`. `data_coverage` indica
> qué campos están presentes (`true`) o ausentes (`false`).

| Campo | Tipo | Notas |
|---|---|---|
| `master_id` | string | Clave canónica estable. |
| `cif` | string? | CIF normalizado. |
| `legal_name` | string? | Razón social. |
| `commercial_name` | string? | Nombre comercial. |
| `aliases` | string[] | Denominaciones alternativas. |
| `legal_form` | string? | Forma jurídica (`null` si no verificable). |
| `mercantile_status` | string? | Estado mercantil (`null` si no verificable). |
| `activity_status` | string? | Situación de actividad (`null` si no verificable). |
| `incorporation_date` | string? | Fecha de constitución (`null` si no verificable). |
| `address` / `postal_code` / `locality` / `province` / `autonomous_community` / `country` | string? | Domicilio. |
| `website` | string? | Web. |
| `domain` | string? | Dominio. |
| `capital_social` | number? | Capital social (`null` si no verificable). |
| `employees_total` | integer? | Nº empleados (`null` si no verificable). |
| `cnae_primary` | object? | `{ code, description, section, division }`. |
| `cnae_secondary` | object[] | CNAE secundarios (mismo shape). |
| `activity` | string? | Descripción de actividad. |
| `corporate_purpose` | string? | Objeto social. |
| `description` | string? | Solo si existe con soporte; nunca texto inventado. |
| `sectors` | string[] | Secciones/sectores. |
| `is_listed` | bool? | Cotizada (`null` si no verificable). |
| `listed_market` | string? | Mercado de cotización. |
| `record_status` | string? | Estado del registro (`active`…). |
| `updated_at` | string? | ISO-8601. |
| `sources` | object[] | `{ source, external_id, source_version, ingested_at }`. |
| `provenance_fields` | string[] | Campos con procedencia trazada. |
| `data_coverage` | object | Mapa `campo→bool` (presencia). |
| `capability_version` | string | `company-intelligence-v2`. |

### 3.2 Ejemplo
```bash
curl -s -X POST "$BASE/api/v2/company-intelligence/identity" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"identifier":"B59022921"}'
# → { "master_id":"mc_...", "legal_name":"TRANSPORTS LA MUNTANYESA",
#     "capital_social":60101.2, "cnae_primary":{...}, "data_coverage":{...},
#     "capability_version":"company-intelligence-v2" }
```

> **Nota de límites (V2-02):** algunos campos de la Ficha (forma jurídica, estado mercantil, fecha de
> constitución, comunidad autónoma, cotización) hoy salen `null` porque su fuente no está ingerida en el
> dataset de preview. Se irán poblando con datos reales; el contrato ya los reserva y `data_coverage` lo refleja.

---

## 4. V2-01 · DTOs de respuesta tipados (motores v1)
- Cada endpoint `200` de los 6 motores referencia ahora un schema nombrado (`FinancialAnalyzeResponse`,
  `SignalAnalyzeResponse`, `SemanticProfileResponse`, `RecommendationSetResponse`, `StrategyThesisResponse`,
  `WorkspaceResponse`, …). Ver `backend/routes/engine_schemas.py`.
- **Runtime idéntico a v1.** Los DTO son **abiertos** (`extra="allow"` → `additionalProperties`): si un motor
  añade campos en el futuro, el cliente tipado no rompe.
- **Mapas dinámicos** legítimos (p. ej. `counts_by_type`, `weights`, `confidence.factors`) se documentan como
  `object` (additionalProperties) — fiel al runtime, sin inventar estructura.
- **Fidelidad certificada:** matriz contrato↔runtime **53/53 MATCH** (ver §5 de
  `ARROBA_V2_SPRINT_V2.0_REPORT.md`). Reproducible con `backend/tools/validate_matrix.py`.

---

## 5. Generar SDK tipado desde `arroba.v2.json`
`arroba.v2.json` es **OpenAPI 3.1 válido** y genera un SDK tipado **sin conocimiento manual**:
```bash
V2=https://agencias.wearebudadvisors.com/api/v1/openapi/arroba.v2.json
# TypeScript (tipos)
npx openapi-typescript "$V2" -o src/agency/types.v2.ts
# TypeScript (cliente axios tipado)
npx @openapitools/openapi-generator-cli generate -i "$V2" -g typescript-axios -o src/agency/client-v2
# Python (modelos Pydantic)  — verificado: genera 91 clases tipadas
pip install datamodel-code-generator && datamodel-codegen --url "$V2" --input-file-type openapi --output agency_models.py
# Python (cliente)
pip install openapi-python-client && openapi-python-client generate --url "$V2"
```

---

## 6. Compatibilidad y versionado
- **`arroba.v1` congelado:** byte-idéntico; sus freeze tests siguen verdes. No se rompe en silencio.
- **`arroba.v2` congelado:** snapshot `backend/contracts/arroba.v2.json` + freeze test
  `tests/golden/test_arroba_v2_contract_freeze.py`. Cualquier cambio de superficie exigirá un bump deliberado.
- **Convivencia:** v1 y v2 operan en paralelo. arroba.com puede seguir en v1 y migrar a v2 por componente.
- **Migración recomendada:** empezar por la **cabecera de la Ficha** (Company/Identity, solo en v2) y por
  regenerar tipos desde `arroba.v2.json` para el resto de bloques (mismos endpoints, ahora tipados).

---

## 6-bis. Caso de integración canónico F0.2 (verificado, solo contratos públicos)
Un único caso completamente funcional con **Base URL pública + `X-API-Key`**, sin privilegios:

- **Empresa:** `TOTALENERGIES ELECTRICIDAD Y GAS ESPAÑA` · **CIF `A87803862`** (identificador oficial).
- `POST /api/v2/company-intelligence/identity` `{"identifier":"A87803862"}` → identidad completa
  (legal_name, `capital_social`, CNAE `3515`/sección `D`, provincia MADRID, `data_coverage`).
- `POST /api/v1/financial-intelligence/analyze` `{"identifier":"A87803862"}` →
  - `has_financials=true`;
  - **partidas L2 reales** (`kpis`): revenue `933.267.000`, EBITDA `36.544.000`, net_income `25.017.000`;
  - `income_statement` con revenue/supplies/personnel_costs/operating_income/depreciation/ebitda/ebit/financial_expenses/net_income;
  - **histórico REAL (3 ejercicios, sin interpolar)** vía `evolution`: 2024 / 2023 / 2022;
  - **`data_source` trazable:** `explainability = { data_source: "master_companies + norm_financials (Iberinform)", source_version: "iberinform", basis: "individual", year: 2024, ai_used: false }`.
- Flujo opcional por nombre: `resolve {"name":"Totalenergies"}` → `master_id` → identity/analyze.

> El caso es **reproducible**: `A87803862` proviene de la fuente oficial versionada, de modo que tras el
> bootstrap (o redeploy con self-healing) existe en cualquier entorno, incluida producción.

## 7. Estado del roadmap (contexto)
- **Sprint V2.0 (este): APROBADO Y CONGELADO.** V2-01 + V2-02 entregados y verificados.
- **Sprint V2.1 (Ownership + Network + Cash Flow): PENDIENTE, no iniciado.** Se retomará cuando la Ficha de
  Empresa esté implementada y validada por arroba.com. Ver `ARROBA_V2_CONTRACT_PLAN.md` §5.

### Referencias
- Informe técnico del sprint: `ARROBA_V2_SPRINT_V2.0_REPORT.md` (incluye matriz 53/53 MATCH).
- Plan de contrato v2: `ARROBA_V2_CONTRACT_PLAN.md` · Pack v1: `ARROBA_INTEGRATION_PACK_v1.md`.
- Snapshots: `backend/contracts/arroba.v1.json` (congelado) · `backend/contracts/arroba.v2.json` (nuevo).
- Freeze tests: `tests/golden/test_arroba_contract_freeze.py` (v1) · `tests/golden/test_arroba_v2_contract_freeze.py` (v2).
