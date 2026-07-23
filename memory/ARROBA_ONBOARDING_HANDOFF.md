# HANDOFF DE INTEGRACIÓN — Agency Tool → arroba.com
**Todo lo necesario para empezar a consumir Agency Tool. Documento único y autosuficiente.**
_Versión: `arroba-onboarding-v1` · 2026-07-04 · Contrato: `arroba-integration-contract-v1`_

> 🆕 **2026-07-12 — Disponible `arroba.v2` (aditivo).** OpenAPI **tipado** de los 6 motores + endpoint
> **Company/Identity** (`POST /api/v2/company-intelligence/identity`) para la cabecera de la Ficha.
> Para la Ficha de Empresa genera el cliente desde `GET /api/v1/openapi/arroba.v2.json` (Swagger:
> `/api/docs/arroba/v2`). `arroba.v1` sigue congelado. Manual: **`ARROBA_V2_INTEGRATION_GUIDE.md`**.

> Agency Tool es el **proveedor de datos e inteligencia**. arroba.com es **consumidor del contrato
> público**. No necesitas conocer la implementación interna: todo lo que puedes consumir está descrito
> aquí y en el OpenAPI público. Contrato de referencia detallado: `ARROBA_INTEGRATION_CONTRACT_v1.md`.

---

## 1. Lo esencial (TL;DR)

| Dato | Valor |
|---|---|
| **Base URL (dev/staging preview)** | `https://data-factory-hub.preview.emergentagent.com` |
| **Base URL (producción)** | `https://agencias.wearebudadvisors.com` — mismo esquema de rutas `/api/...` (contrato v1 ya desplegado y verificado) |
| **Prefijo de todas las rutas** | `/api` |
| **Autenticación** | Cabecera HTTP `X-API-Key: <API_KEY>` en TODAS las llamadas a motores |
| **API Key (preview)** | Se entrega **por canal seguro** (no en este documento). Válida solo para preview. |
| **OpenAPI público (para generar cliente)** | `GET /api/v1/openapi/arroba.v1.json` |
| **Swagger UI interactivo** | `GET /api/docs/arroba` |
| **Identidad de empresa** | Siempre por `master_id` (o `cif_normalized`) |
| **Rate limit** | **600 req/min por API Key** (429 + `Retry-After` si se excede) |
| **Formato** | JSON UTF-8; fechas ISO-8601 UTC |
| **Versión del contrato** | `arroba-integration-contract-v1` (congelado, ver §9) |

**Motores disponibles (53 endpoints):** Financial · Signal · Semantic · Recommendation · Strategy · Transaction.

---

## 2. Autenticación

- **Mecanismo:** clave de servicio en cabecera `X-API-Key`. No se usa JWT de usuario para los motores.
- **Obtención de la clave:** te la entregará el equipo de Agency Tool **por canal seguro** (no viaja en
  documentación ni en repositorio). Hay una clave por entorno (preview y producción son distintas).
- **Almacenamiento:** guárdala como **secreto de servidor** (variable de entorno / secret manager).
  **Nunca** la incrustes en el frontend ni en repositorios: las llamadas a los motores deben hacerse
  desde el **backend de arroba.com**, no desde el navegador.
- **Errores de auth:** `401 Missing X-API-Key` (falta cabecera) · `401 Invalid API key` (clave incorrecta/inactiva).
- **Rotación:** la clave puede rotarse; se te avisará con antelación. Diseña tu cliente para leer la clave
  de configuración, no hardcodeada.

---

## 3. OpenAPI público y generación de cliente

**Contrato máquina-legible (solo los 6 motores, sin rutas internas):**
```
GET https://data-factory-hub.preview.emergentagent.com/api/v1/openapi/arroba.v1.json
```
- `arroba.v1.json` → **URL estable/versionada** recomendada para generar cliente y fijar en tu build.
- `arroba.json` → alias "latest" (mismo contenido en v1).
- Swagger UI navegable: `https://data-factory-hub.preview.emergentagent.com/api/docs/arroba`

### 3.1 Generar cliente TypeScript (frontend/BFF)
```bash
# Tipos TypeScript a partir del contrato
npx openapi-typescript \
  https://data-factory-hub.preview.emergentagent.com/api/v1/openapi/arroba.v1.json \
  -o src/agency-tool/types.ts

# Cliente completo (opcional) con openapi-generator
npx @openapitools/openapi-generator-cli generate \
  -i https://data-factory-hub.preview.emergentagent.com/api/v1/openapi/arroba.v1.json \
  -g typescript-axios \
  -o src/agency-tool/client
```

### 3.2 Generar cliente Python (backend)
```bash
pip install openapi-python-client
openapi-python-client generate \
  --url https://data-factory-hub.preview.emergentagent.com/api/v1/openapi/arroba.v1.json
```

> **Recomendación:** descarga el `arroba.v1.json` y **versiónalo en tu repositorio** como artefacto
> congelado; regenera el cliente solo cuando se publique un `arroba.v2` (ver §9).

---

## 4. Pasos de integración (checklist)

1. **Recibir la API Key** de preview por canal seguro y guardarla como secreto de servidor.
2. **Configurar tu backend** con `AGENCY_TOOL_BASE_URL` + `AGENCY_TOOL_API_KEY` (variables de entorno).
3. **Descargar el contrato** `arroba.v1.json` y **generar el cliente** (§3).
4. **Smoke test:** llamar `GET /api/v1/financial-intelligence/ratios/catalog` con la key → esperar `200`.
5. **Resolver identidad:** obtener un `master_id` (por búsqueda semántica `POST /semantic-intelligence/search`
   o por `cif_normalized`). Todas las demás llamadas usan ese `master_id`.
6. **Construir cada bloque de UI** mapeando endpoint → componente (ver §6 y la matriz de consumo del
   contrato detallado `ARROBA_INTEGRATION_CONTRACT_v1.md` §5/§11).
7. **Manejar estados especiales:** `unavailable`/`source_not_available` (dato sin fuente, no es error),
   `429` (respeta `Retry-After`), `404` (`master_not_found`, etc.).
8. **Cachear por `master_id` + versión del motor** (ver §7) e invalidar al cambiar la versión.
9. **No** duplicar estado transaccional: el estado de operaciones vive en el Transaction OS (consúmelo, no lo repliques).
10. **Confirmar readiness** y pasar a producción cuando se entregue la Base URL + API Key de producción.

---

## 5. Ejemplo de consumo

### 5.1 curl (smoke test end-to-end)
```bash
BASE="https://data-factory-hub.preview.emergentagent.com"
KEY="<TU_API_KEY>"

# a) Búsqueda semántica → obtener master_id
curl -s -X POST "$BASE/api/v1/semantic-intelligence/search" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"query":"transporte de mercancías","limit":5}'

# b) Análisis financiero por master_id
curl -s -X POST "$BASE/api/v1/financial-intelligence/analyze" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"identifier":"mc_457c000acfd3"}'

# c) Señales de la empresa
curl -s -X POST "$BASE/api/v1/signal-intelligence/analyze" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"identifier":"mc_457c000acfd3"}'

# d) Valoración
curl -s -X POST "$BASE/api/v1/financial-intelligence/valuation" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"identifier":"mc_457c000acfd3"}'
```

### 5.2 TypeScript (backend/BFF con fetch)
```ts
const BASE = process.env.AGENCY_TOOL_BASE_URL!;
const KEY = process.env.AGENCY_TOOL_API_KEY!; // secreto de servidor

async function analyze(masterId: string) {
  const res = await fetch(`${BASE}/api/v1/financial-intelligence/analyze`, {
    method: "POST",
    headers: { "X-API-Key": KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ identifier: masterId }),
  });
  if (res.status === 429) {
    const retry = Number(res.headers.get("Retry-After") ?? 1);
    throw new Error(`rate limited, retry after ${retry}s`);
  }
  if (!res.ok) throw new Error(`agency-tool ${res.status}`);
  return res.json(); // incluye engine_version, kpis, ratios, valuation, ...
}
```

### 5.3 Python (backend)
```python
import os, httpx

BASE = os.environ["AGENCY_TOOL_BASE_URL"]
KEY = os.environ["AGENCY_TOOL_API_KEY"]

def analyze(master_id: str) -> dict:
    r = httpx.post(f"{BASE}/api/v1/financial-intelligence/analyze",
                   headers={"X-API-Key": KEY}, json={"identifier": master_id}, timeout=30)
    r.raise_for_status()
    return r.json()
```

**Respuesta típica de `analyze` (recortada):**
```json
{
  "master_id": "mc_457c000acfd3",
  "cif_normalized": "B59022921",
  "identity": { "legal_name": "TRANSPORTS LA MUNTANYESA" },
  "has_financials": true,
  "kpis": { "revenue": 2722872.85, "ebitda": 0, "ebitda_margin": 0, "employees_total": 0 },
  "ratios": { "current_ratio": 0, "roe": 0 },
  "valuation": { "enterprise_value": 0, "range": { "low": 0, "high": 0 } },
  "engine_version": "financial-intelligence-v1",
  "generated_at": "2026-07-04T19:00:00Z"
}
```

---

## 6. Mapa rápido endpoint → bloque de UI (resumen)

| Bloque arroba.com | Endpoint |
|---|---|
| Hero / KPIs / P&L / Balance / Ratios | `POST /api/v1/financial-intelligence/analyze` |
| Valoración | `POST /api/v1/financial-intelligence/valuation` |
| Señales / Alertas | `POST /api/v1/signal-intelligence/analyze` (+ `/history`, `/opportunities`) |
| Universal Search / Similares | `POST /api/v1/semantic-intelligence/search` · `/similar` |
| Comparables / Buyers / Sellers / Matching | `POST /api/v1/recommendation-intelligence/*` |
| Tesis / Estrategia | `POST /api/v1/strategy-intelligence/thesis` (+ `/scenarios`, `/decision`) |
| Deal Room / Copilot / Timeline | `POST /api/v1/transaction-intelligence/{workspace,next-action,timeline,task,documents,stage}` |

> Matriz completa (dato → colección → entidad → endpoint → campo → bloque) en
> `ARROBA_INTEGRATION_CONTRACT_v1.md` §5 y §11. Schemas completos en §6 del mismo documento.

---

## 7. Versionado y caché

- Cada respuesta incluye un campo de versión. **El nombre varía por motor** (conforme al contrato §4.7):
  - `engine_version` → Financial, Signal, Semantic, Transaction.
  - `recommendation_version` → Recommendation.
  - `strategy_version` (+ mapa `evidence_version`) → Strategy.
  - **Lee el campo `*_version` del motor correspondiente; no asumas `engine_version` en todos.**
- **Caché recomendada:** clave `master_id` + versión del motor; TTL 5–15 min para datos financieros/semánticos.
  Invalida al detectar cambio de versión.
- **Estado transaccional:** no cachear (event-driven; la verdad vive en el Transaction OS). Consúltalo en tiempo real.

---

## 8. Requisitos y limitaciones (léelo antes de empezar)

1. **Llamadas desde servidor.** La API Key es un secreto de servidor; no expongas los motores desde el navegador.
2. **Rate limit 600/min POR API Key** (no por organización ni IP). Implementa reintentos con backoff y respeta `Retry-After`.
3. **Datos "unavailable" ≠ error.** `recommendation/investors` y `/advisors` devuelven
   `{"status":"unavailable","reason":"source_not_available"}` (no hay fuente todavía). Trátalo como estado válido.
4. **Transaction v1 (alcance).** Cubre Origination → Due Diligence inicial. IOI/LOI/SPA/signing/closing
   están **diferidos a v2** (no disponibles aún).
5. **Cobertura de datos (preview).** El entorno de preview usa un **dataset Iberinform SINTÉTICO** (~6.261
   empresas canónicas). Los valores son de prueba, no reales de mercado. Úsalo para integrar contra el
   **contrato/estructura**, no para conclusiones de negocio. Producción se poblará con datos reales.
6. **`master_id` puede regenerarse** si se reconstruye el dataset de preview (es determinista por CIF, pero
   un reseed de la muestra puede cambiar el universo). Resuelve identidad por `cif_normalized`/búsqueda,
   no fijes `master_id` a largo plazo en preview.
7. **Endpoints administrativos NO disponibles.** El contrato de arroba solo incluye los 6 motores. Las rutas
   de Master/Valuo/Console no forman parte de tu contrato.
8. **CORS.** Configurado permisivo en preview; en producción se restringirá a los orígenes de arroba
   (si haces alguna llamada desde navegador, coordina el origen). Recomendado: llamadas server-to-server.
9. **Escalado del rate limit.** Hoy el limitador es in-process (un worker). Si se escala a múltiples pods,
   Agency Tool lo migrará a un límite global; el contrato observable (600/min por key) se mantiene.

---

## 9. Estabilidad del contrato (garantías)

- **Congelado (`arroba-integration-contract-v1`):** prefijos/versiones de los 6 motores, identidad por
  `master_id`, auth `X-API-Key`, códigos de error, presencia de campo de versión, y los campos publicados
  de cada respuesta (no se eliminan ni renombran).
- **Cambios compatibles (sin aviso de ruptura):** nuevos endpoints, nuevos campos opcionales, nuevos tipos
  en enums abiertos (ignora los desconocidos), mejoras de precisión que conserven rango/semántica.
- **Cambios que rompen (exigen `arroba-v2` con convivencia):** eliminar/renombrar campo o endpoint, cambiar
  tipo/unidad/semántica, cambiar códigos de error o identificador o esquema de auth. Cuando ocurra, `v1`
  seguirá disponible hasta que arroba.com valide y migre.
- **URL estable de contrato:** genera tu cliente contra `arroba.v1.json`. Cuando exista `arroba.v2.json`,
  se te comunicará con antelación y ambos convivirán.

---

## 10. Contacto y siguientes pasos

- **Para empezar necesitas de Agency Tool:** (a) API Key de preview por canal seguro. Eso es todo; el resto
  (Base URL, OpenAPI, ejemplos) está en este documento.
- **Cuando confirmes readiness en preview**, Agency Tool entregará **Base URL + API Key de producción**
  (mismo contrato, datos reales).
- **Referencias:** contrato detallado `ARROBA_INTEGRATION_CONTRACT_v1.md`; certificación de preparación
  `ARROBA_INTEGRATION_READINESS_CERT.md`.

---

### Resumen para copiar/pegar al equipo de arroba.com
```
Base URL (producción): https://agencias.wearebudadvisors.com
Base URL (preview):    https://data-factory-hub.preview.emergentagent.com
Auth:               header  X-API-Key: <te la pasamos por canal seguro>
OpenAPI (cliente):  GET /api/v1/openapi/arroba.v1.json
Swagger UI:         GET /api/docs/arroba
Identidad:          master_id (o cif_normalized)
Rate limit:         600 req/min por API Key (429 + Retry-After)
Motores:            financial | signal | semantic | recommendation | strategy | transaction  (/api/v1/<motor>-intelligence/*)
Notas:              llamadas server-to-server; datos de preview SINTÉTICOS; 'unavailable' es estado válido; contrato v1 congelado.
```
