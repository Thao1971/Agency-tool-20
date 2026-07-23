# INTEGRATION PACK — Agency Tool → arroba.com
**Documento único y autosuficiente para integrar arroba.com contra el contrato `arroba.v1`.**
_Versión: `integration-pack-v1` · 2026-07-04 · Contrato: `arroba-integration-contract-v1` (congelado)_

> 🆕 **Actualización 2026-07-12 — Contrato `arroba.v2` disponible (aditivo, convive con v1).** Se han
> **tipado los DTO de respuesta** de los 6 motores en OpenAPI y se ha añadido la capacidad pública
> **Company/Identity** (`POST /api/v2/company-intelligence/identity`) para la cabecera de la Ficha de
> Empresa. **`arroba.v1` sigue congelado y sin cambios de runtime.** Manual dedicado:
> **`ARROBA_V2_INTEGRATION_GUIDE.md`**. OpenAPI v2: `/api/v1/openapi/arroba.v2.json` · Swagger v2: `/api/docs/arroba/v2`.

Índice
1. Visión general de la arquitectura
2. Guía de integración (Base URL · Auth · Rate limits · Errores · Versionado)
3. OpenAPI (arroba.v1.json · arroba.json · Swagger UI)
4. Documentación funcional de cada motor
5. Integration Playbook (por funcionalidad de arroba.com)
6. Ejemplos completos (cURL · TypeScript · Python)
7. Runbooks (Rotación de API Keys · Troubleshooting · Monitorización)
8. Roadmap (v1 vs v2)

---

## 1. Visión general de la arquitectura

### 1.1 Qué es Agency Tool
Agency Tool es la **fábrica de datos y capa de gobernanza (Intelligence Engine)** del ecosistema
Arroba/Valuo. Ingiere fuentes externas (Iberinform, BME, BORME, CNMV, INE, DataComex, Contratación
Pública, web), las normaliza, resuelve la **identidad canónica** de cada empresa (`master_id`), construye
el **Master Record** (`master_companies`), materializa un **Knowledge Graph** de propiedad, y expone
**inteligencia derivada** a través de 6 motores tras un contrato público, versionado y autenticado.

**Flujo:** Fuentes externas → Ingesta → Data Layer (normalización) → Entity Resolution → Master Record
→ Knowledge Graph → **Intelligence Engines** → **API pública** → arroba.com.

### 1.2 Qué son los 6 motores
| Motor | Pregunta que responde | Versión | Persistencia |
|---|---|---|---|
| **Financial** | ¿Cuánto vale / cómo rinde? | `financial-intelligence-v1` | stateless |
| **Signal** | ¿Qué está pasando (oportunidad/riesgo)? | `signal-intelligence-v1` | `signals` |
| **Semantic** | ¿A qué se parece / qué es? | `semantic-intelligence-v1` | `semantic_profiles` |
| **Recommendation** | ¿Qué recomendar (comparables, buyers, sellers)? | `recommendation-intelligence-v1` | `recommendation_memory` |
| **Strategy** | ¿Qué estrategia seguir? | `strategy-intelligence-v1` | `strategic_theses` |
| **Transaction** | ¿Cómo ejecutar la operación? | `transaction-intelligence-v1` / `transaction-os-v1` | `tx_*` |

DAG acíclico: `Foundation → Financial → Signal → Semantic → Recommendation → Strategy → Transaction`.

### 1.3 Responsabilidades
| Agency Tool (proveedor) | arroba.com (consumidor) |
|---|---|
| Poseer los datos y la identidad canónica (`master_id`) | Construir la experiencia/UI de producto |
| Producir inteligencia (KPIs, valoración, señales, tesis, operaciones) | Orquestar llamadas al contrato desde su **backend** |
| Mantener el contrato público estable y versionado | Generar cliente desde el OpenAPI y fijar versión |
| Ejecutar ingesta, normalización, Entity Resolution, rebuilds | Cachear e invalidar por `master_id` + versión de motor |
| Autenticar y aplicar rate limit (`X-API-Key`) | Guardar la API Key como secreto de servidor |
| Poseer TODO el estado transaccional (Transaction OS) | **No** duplicar estado transaccional; consumirlo en vivo |

**Frontera:** arroba **produce experiencia**; Agency Tool **produce inteligencia y posee el estado**.

### 1.4 Arquitectura de integración
```
                              FUENTES EXTERNAS
      Iberinform · BORME · CNMV · INE · DataComex · Web · APIs · ...
                                     │
                                     ▼
                              INGESTA / ETL
                                     │
                                     ▼
                                DATA LAYER
               Normalización · Calidad · Enriquecimiento
                                     │
                                     ▼
                            ENTITY RESOLUTION
                     Resolución de identidad canónica
                                     │
                                     ▼
                              MASTER RECORD
                  master_companies (Single Source of Truth)
                                     │
                                     ▼
                            KNOWLEDGE GRAPH
              Relaciones · Propiedad · Señales · Contexto
                                     │
                                     ▼
                         INTELLIGENCE ENGINES
   Financial │ Signal │ Semantic │ Recommendation │ Strategy │ Transaction
                                     │
                                     ▼
                 API PÚBLICA (arroba-integration-contract-v1)
                                     │
                                     ▼
                          BACKEND DE arroba.com
                                     │
                                     ▼
                             ARROBA COPILOT
                     (Orquestador inteligente único)
                                     │
     ┌───────────────────┬──────────────────┬───────────────────┐
     ▼                   ▼                  ▼                   ▼
 Entity Pages       Valoraciones       Marketplace       Transaction OS
```

### 1.5 Filosofía de integración
Principio fundamental: **Agency Tool produce inteligencia. arroba.com produce experiencia.**

| Agency Tool (responsable de) | arroba.com (responsable de) |
|---|---|
| ingesta · normalización · calidad del dato | experiencia de usuario · navegación |
| resolución de identidad · Master Record | Copilot · entidades · oportunidades |
| Knowledge Graph · motores de inteligencia | marketplace · visualización |
| Transaction OS · versionado del contrato | workflow del usuario · composición de respuestas |

### 1.6 Principios de integración
- **Single Source of Truth** — Agency Tool es la única fuente de verdad para datos maestros, inteligencia y estado transaccional.
- **Copilot First** — el usuario nunca selecciona motores; habla con Arroba Copilot, que decide automáticamente qué motores consultar.
- **Intelligence First** — arroba.com nunca recalcula valoraciones, scores, matching, señales ni estrategias; esa inteligencia pertenece a Agency Tool.
- **Stateless Frontend** — el frontend nunca mantiene estado económico; solo representa información.
- **Contract First** — toda integración se realiza exclusivamente mediante `arroba.v1`, nunca mediante implementaciones internas.
- **Progressive Enhancement** — cada motor evoluciona de forma independiente mientras respete el contrato público.

### 1.7 Anti-patrones (expresamente prohibidos)
- ❌ Acceder directamente a MongoDB.
- ❌ Consumir endpoints internos.
- ❌ Recalcular valoraciones.
- ❌ Reimplementar matching.
- ❌ Reimplementar scoring.
- ❌ Duplicar el estado de una transacción.
- ❌ Copiar datos maestros en arroba.
- ❌ Acoplar la UI a estructuras internas de Agency Tool.

---

## 2. Guía de integración

### 2.1 Base URL
| Entorno | Base URL |
|---|---|
| **Producción** | `https://agencias.wearebudadvisors.com` |
| **Preview (dev/staging)** | `https://data-factory-hub.preview.emergentagent.com` |

Todas las rutas se prefijan con `/api`. Identidad de empresa por `master_id` (o `cif_normalized`).

### 2.2 Autenticación
- Cabecera `X-API-Key: <API_KEY>` en **todas** las llamadas a motores.
- La clave la entrega Agency Tool **por canal seguro** (una por entorno; preview ≠ producción).
- Guardar como **secreto de servidor**; llamadas **server-to-server** (nunca desde el navegador).
- Errores: `401 Missing X-API-Key` · `401 Invalid API key`.

### 2.3 Rate limits
- **600 req/min por API Key** (token-bucket). Excedente → `429` con cabecera `Retry-After` (segundos).
- Implementa reintentos con backoff exponencial respetando `Retry-After`.
- El límite es por **key** (no por organización ni IP).

### 2.4 Gestión de errores
| Código | Significado | Acción del cliente |
|---|---|---|
| `200` | OK | Procesar payload (incluye campo de versión) |
| `400` | Request inválida | Revisar body |
| `401` | No autenticado (falta/mala key) | Revisar `X-API-Key` |
| `403` | Sin permiso | Contactar Agency Tool |
| `404` | Entidad no encontrada (`master_not_found`, `transaction_not_found`) | Reconfirmar `master_id` |
| `409` | Conflicto de estado (guards de la state-machine) | Releer estado de la operación |
| `422` | Validación de payload | Corregir campos |
| `429` | Rate limit | Backoff + `Retry-After` |
| `500` | Error interno | Reintentar; si persiste, abrir incidencia |
| — | `{"status":"unavailable","reason":"source_not_available"}` | **Estado válido**, no error (dato sin fuente) |

### 2.5 Versionado del contrato
- Cada respuesta incluye un campo de versión. **El nombre varía por motor:**
  `engine_version` (Financial, Signal, Semantic, Transaction), `recommendation_version` (Recommendation),
  `strategy_version` + `evidence_version` (Strategy). **Lee el campo del motor correspondiente.**
- Contrato **congelado** `arroba-integration-contract-v1`. Cambios aditivos permitidos; rupturas exigen
  **`arroba-v2`** conviviendo con v1 (ver §8 y Roadmap).

### 2.6 Resolución de identidad (CIF → MasterRecord) — patrón OFICIAL de integración
> Validado contra el código y **congelado como parte de `arroba.v1`** (protegido por freeze test + CI).

**Reglas oficiales:**
1. **Los 5 motores de análisis de empresa** (Financial, Signal, Semantic, Recommendation, Strategy)
   aceptan **indistintamente `master_id` o `cif_normalized`** en el campo `identifier` (y en los campos
   equivalentes de Recommendation: `target`, `a`, `b`, `candidate`). Resolución interna:
   `{"$or": [{"master_id": identifier}, {"cif_normalized": identifier}]}`.
2. El **`master_id`** devuelto por cualquier motor es la **clave canónica estable** y es **reutilizable de
   forma segura** en el resto de motores. Es el identificador recomendado tras la primera resolución.
3. El **Master Layer (`/api/v1/master/*`) NO es público**: es administrativo (JWT, Platform Console) y
   **queda fuera** de `arroba.v1`. arroba.com **no** debe consumir `/master`. La identidad se obtiene
   **a través de los motores** (o de `semantic/search` si no se tiene el CIF).
4. El motor **Transaction** no se direcciona por empresa, sino por `transaction_id` / `thesis_id`
   (por diseño). La empresa entra en el flujo transaccional vía la tesis: Strategy (`thesis`) → `thesis_id`
   → Transaction.

**Flujo recomendado:**
```
1) Normaliza el CIF (mayúsculas, sin separadores): "B-59022921" → "B59022921"
2) Llama a un motor con identifier = cif_normalized:
   POST /api/v1/financial-intelligence/analyze  { "identifier": "B59022921" }
3) La respuesta incluye el master_id canónico:
   { "master_id": "mc_...", "cif_normalized": "B59022921", ... }
4) Reutiliza ese master_id (cacheado) en el resto de motores de la ficha.
Alternativa sin CIF:
   POST /api/v1/semantic-intelligence/search  { "query": "...", "limit": 5 }  → candidatos con master_id
```
- CIF inexistente en el Master canónico → `404 master_not_found` (o resultado vacío en search) = "empresa no cubierta aún".
- Cachea por `master_id` + versión de motor. En **preview** no fijes `master_id` a largo plazo (puede
  regenerarse en un reseed del dataset sintético; el CIF es la clave natural estable).

**Autenticación por superficie (resumen):**
| Superficie | Auth | ¿Pública para arroba? |
|---|---|---|
| 6 Intelligence Engines (`/api/v1/*-intelligence/*`) | `X-API-Key` | ✅ Sí (contrato `arroba.v1`) |
| Master Layer (`/api/v1/master/*`) | JWT administrativo | ❌ No (Platform Console) |

---

## 3. OpenAPI

| Recurso | Producción | Preview |
|---|---|---|
| **Contrato congelado (para generar cliente)** | `https://agencias.wearebudadvisors.com/api/v1/openapi/arroba.v1.json` | `…preview…/api/v1/openapi/arroba.v1.json` |
| **Contrato "latest"** | `…/api/v1/openapi/arroba.json` | idem |
| **Swagger UI (arroba)** | `https://agencias.wearebudadvisors.com/api/docs/arroba` | `…preview…/api/docs/arroba` |

- `arroba.v1.json` (53 rutas, solo los 6 motores) es la **fuente que consume arroba.com**.
- Snapshot documental congelado en el repo de Agency Tool: `backend/contracts/arroba.v1.json` (idéntico
  al endpoint; protegido por un freeze test en CI). Cualquier cambio de superficie pública = **v2**.

### Generar cliente
```bash
# TypeScript (tipos)
npx openapi-typescript https://agencias.wearebudadvisors.com/api/v1/openapi/arroba.v1.json -o src/agency/types.ts
# TypeScript (cliente axios)
npx @openapitools/openapi-generator-cli generate -i https://agencias.wearebudadvisors.com/api/v1/openapi/arroba.v1.json -g typescript-axios -o src/agency/client
# Python
pip install openapi-python-client && openapi-python-client generate --url https://agencias.wearebudadvisors.com/api/v1/openapi/arroba.v1.json
```

---

## 4. Documentación funcional de cada motor

> Base de motor: `/api/v1/<motor>-intelligence`. Auth `X-API-Key`. `identifier` acepta `master_id` o `cif_normalized`.

### 4.1 Financial Intelligence
- **Qué hace:** KPIs, cuenta de resultados, balance, ratios deterministas, calidad financiera y valoración.
- **Cuándo usarlo:** ficha de empresa (KPIs, P&L, Balance, Ratios) y bloque de valoración.
- **Endpoints / Inputs:**
  - `POST /analyze` → `{ "identifier" }`
  - `POST /valuation` → `{ "identifier" }`
  - `GET /ratios/catalog`
- **Outputs:** `kpis`, `income_statement`, `balance_sheet`, `ratios`, `financial_quality`, `valuation`,
  `explainability`, `engine_version`, `generated_at`.
- **Casos de uso:** Hero/KPIs, P&L, Balance, Ratios, Valuation.

### 4.2 Signal Intelligence
- **Qué hace:** detecta señales de oportunidad/riesgo (corporativas, sectoriales, territoriales) con
  polaridad, severidad y acciones canónicas (`act-v1`).
- **Cuándo usarlo:** bloque de señales de la ficha, alertas, radar sectorial/territorial, oportunidades.
- **Endpoints / Inputs:**
  - `POST /analyze` → `{ "identifier", "windows?" }`
  - `POST /sector` · `POST /territory` · `POST /opportunities` · `POST /history`
  - `GET /signal/{signal_id}` · `GET /catalog`
- **Outputs:** `signals[]` (`signal_type`, `polarity`, `severity`, `score`, `actions[]`), `score`,
  `counts_by_category`, `engine_version`.
- **Casos de uso:** Signals, Alertas, Sector/Territory Intel, Marketplace (oportunidades).

### 4.3 Semantic Intelligence
- **Qué hace:** perfil semántico, embeddings y similitud/búsqueda.
- **Cuándo usarlo:** Universal Search, "empresas similares", enriquecimiento del Copilot.
- **Endpoints / Inputs:**
  - `POST /profile` → `{ "identifier","enrich?","with_relationships?" }`
  - `POST /embedding` · `POST /similar` → `{ "identifier","limit","same_section" }`
  - `POST /search` → `{ "query","limit","cnae_section?" }`
  - `GET /profile/schema` · `GET /catalog`
- **Outputs:** `semantic_profile`, `embedding`, `results[]`/`items[]` (`similarity_score`), `engine_version`.
- **Casos de uso:** Universal Search, Similares, contexto Copilot.

### 4.4 Recommendation Intelligence
- **Qué hace:** comparables, compradores, vendedores, matching y oportunidades con fit multidimensional.
- **Cuándo usarlo:** comparables de la ficha, buyers/sellers, matching A↔B, marketplace.
- **Endpoints / Inputs:**
  - `POST /comparables · /buyers · /sellers · /opportunities · /investors · /advisors` → `{ "identifier","limit" }`
  - `POST /matching` → `{ "a","b" }` · `POST /explain` → `{ "target","candidate","recommendation_type" }`
  - `POST /feedback` · `POST /memory` · `GET /catalog`
- **Outputs:** `recommendations[]`/`items[]` (`fit_score`, `dimensions`, `role`, `rationale`,
  `recommendation_id`), `recommendation_version`. `investors`/`advisors` → `unavailable` (sin fuente).
- **Casos de uso:** Comparables, Buyers/Sellers, Matching, Watchlist (memory), Marketplace.

### 4.5 Strategy Intelligence
- **Qué hace:** Strategic Thesis (5 dimensiones + score + confianza), escenarios y decisión justificada;
  conversión a oportunidad/mandato/transacción.
- **Cuándo usarlo:** bloque de estrategia/tesis, comparación de alternativas, origen de operaciones.
- **Endpoints / Inputs:**
  - `POST /thesis` → `{ "identifier","thesis_type?","opportunity_id?","owner" }`
  - `POST /scenarios · /growth · /acquisition · /divestment · /partnership · /capital · /risk` → `{ "identifier" }`
  - `POST /decision` → `{ "identifier","type_a","type_b" }`
  - `POST /lifecycle` → `{ "thesis_id","state","result?","learning?" }`
  - `POST /convert` → `{ "thesis_id","target" }` · `POST /memory` · `GET /catalog`
- **Outputs:** `strategic_dimensions`, `score`, `hypotheses`, `constraints`, `recommendation_ids`,
  `strategy_version`, `evidence_version`.
- **Casos de uso:** Strategy/Thesis, decisión, conversión a operación.

### 4.6 Transaction Intelligence (+ Transaction OS)
- **Qué hace:** orquesta el ciclo de una operación (Director de M&A). El **OS posee el estado**
  (`tx_transactions/tx_events/tx_tasks/tx_approvals/tx_documents`); el Engine orquesta (Copilot).
- **Cuándo usarlo:** Deal Room, Copilot transaccional, timeline, tareas, documentos, workspace.
- **Endpoints / Inputs:**
  - `POST /transaction` (crear: `{ "thesis_id","workflow_name?","organization_id","parties?","actor" }` · consultar: `{ "transaction_id" }`)
  - `POST /workflow · /stage · /task · /next-action · /risk · /documents · /participants · /timeline · /decision · /memory · /workspace`
  - `GET /catalog`
- **Outputs:** `current_stage`, `state`, `tasks`, `documents`, `events` (timeline), `next-action`
  (`recommended_action`, `why`, `confidence`, `blockers`), `workspace` agregado, `engine_version`,
  `os_version`, `state_machine_version`.
- **Casos de uso:** Deal Room, Copilot, Timeline/Activity, aprobaciones de alto riesgo.
- **Alcance v1:** Origination → Due Diligence inicial (IOI/LOI/SPA/closing → v2).

---

## 5. Integration Playbook (por funcionalidad de arroba.com)

> La integración **no se realiza por endpoints, sino por experiencias de usuario**.
> Orquesta desde el **backend de arroba**. Resuelve primero la identidad (`master_id`) y reutilízala.

### 5.1 Página Empresa (Entity Page)
```
1) Identidad + Hero  → GET  /api/v1/master/{master_id}            (o resolver por búsqueda semántica)
2) KPIs/P&L/Balance/Ratios/Valuation → POST /api/v1/financial-intelligence/analyze  (+ /valuation)
3) Señales           → POST /api/v1/signal-intelligence/analyze
4) Comparables       → POST /api/v1/recommendation-intelligence/comparables
5) Similares/Perfil  → POST /api/v1/semantic-intelligence/profile | /similar
```
Cachea por `master_id` + versión de cada motor.

### 5.2 Valoración
```
POST /api/v1/financial-intelligence/valuation   (enterprise_value, equity_value, range, múltiplos)
POST /api/v1/strategy-intelligence/thesis        (contexto estratégico / escenarios para la narrativa)
```

### 5.3 Oportunidades / Marketplace
```
POST /api/v1/recommendation-intelligence/opportunities   (fit por rol)
POST /api/v1/signal-intelligence/opportunities           (señales de oportunidad sector/territorio)
```

### 5.4 Copilot
```
Contexto:      POST /api/v1/semantic-intelligence/profile | /search
Sugerencias:   POST /api/v1/recommendation-intelligence/comparables | /buyers | /sellers
Estrategia:    POST /api/v1/strategy-intelligence/thesis | /decision
(En operación) POST /api/v1/transaction-intelligence/next-action | /workspace | /risk
```

### 5.5 Transaction Workspace (Deal Room)
```
Crear:      POST /api/v1/transaction-intelligence/transaction   { thesis_id, ... }
Workspace:  POST /api/v1/transaction-intelligence/workspace     { transaction_id }
Avanzar:    POST /api/v1/transaction-intelligence/stage         { transaction_id, event|stage, actor }
Tareas:     POST /api/v1/transaction-intelligence/task
Docs:       POST /api/v1/transaction-intelligence/documents
Timeline:   POST /api/v1/transaction-intelligence/timeline
```

### 5.6 Universal Search / Watchlist / Alertas
```
Search:    POST /api/v1/semantic-intelligence/search      { query, limit }
Watchlist: POST /api/v1/recommendation-intelligence/memory { target|state }
Alertas:   POST /api/v1/signal-intelligence/analyze | /opportunities   (polling; push en v2)
```

### 5.7 Copilot como única puerta de entrada inteligente
El **Arroba Copilot** es la única puerta de entrada inteligente a la plataforma. El usuario expresa una
intención en lenguaje natural; el Copilot **interpreta la intención → identifica qué motores necesita →
ejecuta las llamadas → agrega la información → devuelve una respuesta única**. El usuario **nunca**
necesita conocer la existencia de los motores.

**Motores por intención (uno o varios):**
| Intención | Motores |
|---|---|
| Analizar empresa | Financial + Signal + Semantic |
| Valorar empresa | Financial + Strategy |
| Buscar compradores | Recommendation |
| Buscar vendedores | Recommendation |
| Buscar oportunidades | Recommendation + Signal |
| Analizar estrategia | Strategy |
| Gestionar operación | Transaction |
| Comparar empresas | Financial + Recommendation |
| Explicar una empresa | Semantic + Strategy |

**Motores por experiencia:**
- **Página Empresa:** Financial · Signal · Semantic · Recommendation
- **Valoración:** Financial · Strategy
- **Marketplace:** Recommendation · Signal
- **Strategic Thesis:** Strategy
- **Transaction Workspace:** Transaction

### 5.8 Secuencia de la Entity Page
```
Usuario
   │
   ▼
Frontend arroba
   │
   ▼
Backend arroba
   │
   ├────────► Financial
   ├────────► Signal
   ├────────► Semantic
   └────────► Recommendation
                 │
                 ▼
            Agency Tool
                 │
                 ▼
         Respuesta agregada
                 │
                 ▼
           Backend arroba
                 │
                 ▼
        Entity Page renderizada
```

### 5.9 Orquestación del Copilot
```
Usuario
   │
   ▼
        Arroba Copilot
   │
 Comprende la intención
   │
 Decide qué motores necesita
   │
 Ejecuta llamadas en paralelo
   │
 Agrega resultados
   │
 Genera una respuesta única
   │
   ▼
Usuario
```

### 5.10 Principio arquitectónico fundamental
> **La complejidad vive en Agency Tool. La simplicidad vive en arroba.com.**

- **Agency Tool** concentra: datos · inteligencia · algoritmos · Knowledge Graph · Transaction OS.
- **arroba.com** concentra: experiencia · navegación · Copilot · entidades · oportunidades · interacción con el usuario.

Este principio garantiza el desacoplamiento entre ambos productos y permite que evolucionen de forma
independiente respetando el contrato público `arroba.v1`.

---

## 6. Ejemplos completos

> Sustituye `<API_KEY>` y `<master_id>`. En producción usa `https://agencias.wearebudadvisors.com`.

### 6.1 cURL (flujo end-to-end)
```bash
BASE="https://agencias.wearebudadvisors.com"
KEY="<API_KEY>"

# 1) Resolver identidad por búsqueda
curl -s -X POST "$BASE/api/v1/semantic-intelligence/search" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"query":"transporte de mercancías","limit":5}'

# 2) Análisis financiero
curl -s -X POST "$BASE/api/v1/financial-intelligence/analyze" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"identifier":"<master_id>"}'

# 3) Señales
curl -s -X POST "$BASE/api/v1/signal-intelligence/analyze" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"identifier":"<master_id>"}'

# 4) Comparables
curl -s -X POST "$BASE/api/v1/recommendation-intelligence/comparables" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"identifier":"<master_id>","limit":10}'
```

### 6.2 TypeScript (backend/BFF, con manejo de 429)
```ts
const BASE = process.env.AGENCY_TOOL_BASE_URL!;   // https://agencias.wearebudadvisors.com
const KEY  = process.env.AGENCY_TOOL_API_KEY!;    // secreto de servidor

async function callEngine(path: string, body: unknown, attempt = 0): Promise<any> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "X-API-Key": KEY, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 429 && attempt < 3) {
    const retry = Number(res.headers.get("Retry-After") ?? 1);
    await new Promise(r => setTimeout(r, retry * 1000));
    return callEngine(path, body, attempt + 1);
  }
  if (!res.ok) throw new Error(`agency-tool ${res.status} on ${path}`);
  return res.json();
}

// Página Empresa
async function entityPage(masterId: string) {
  const [financial, signals, comparables, profile] = await Promise.all([
    callEngine("/api/v1/financial-intelligence/analyze", { identifier: masterId }),
    callEngine("/api/v1/signal-intelligence/analyze", { identifier: masterId }),
    callEngine("/api/v1/recommendation-intelligence/comparables", { identifier: masterId, limit: 10 }),
    callEngine("/api/v1/semantic-intelligence/profile", { identifier: masterId }),
  ]);
  return { financial, signals, comparables, profile };
}
```

### 6.3 Python (backend, con reintentos)
```python
import os, time, httpx

BASE = os.environ["AGENCY_TOOL_BASE_URL"]
KEY  = os.environ["AGENCY_TOOL_API_KEY"]

def call_engine(path: str, body: dict, attempts: int = 3) -> dict:
    with httpx.Client(timeout=30) as c:
        for i in range(attempts):
            r = c.post(f"{BASE}{path}", headers={"X-API-Key": KEY}, json=body)
            if r.status_code == 429 and i < attempts - 1:
                time.sleep(int(r.headers.get("Retry-After", "1")))
                continue
            r.raise_for_status()
            return r.json()
    raise RuntimeError("rate limited")

def valuation(master_id: str) -> dict:
    return call_engine("/api/v1/financial-intelligence/valuation", {"identifier": master_id})
```

---

## 7. Runbooks

### 7.1 Rotación de API Keys (resumen; detalle en `API_KEY_ROTATION_RUNBOOK.md`)
Rotación **sin downtime** (solape): 1) generar clave nueva · 2) admitir su hash en `db.api_keys` sin
revocar la antigua · 3) entregar la nueva por canal seguro · 4) actualizar `ARROBA_SERVICE_API_KEY` en el
entorno (preview: `.env`+restart; prod: variable de entorno del deployment + redeploy) · 5) confirmar que
arroba usa la nueva · 6) revocar la antigua (`active:false`). Verificar: clave nueva → 200, antigua → 401.

### 7.2 Troubleshooting
| Síntoma | Causa probable | Solución |
|---|---|---|
| `401 Missing X-API-Key` | Falta la cabecera | Añadir `X-API-Key` |
| `401 Invalid API key` | Clave incorrecta/inactiva o de otro entorno | Usar la clave del entorno correcto; revisar rotación |
| `429 Too Many Requests` | Superado 600/min por key | Backoff + `Retry-After`; agrupar llamadas |
| `404 master_not_found` | `master_id` inexistente (o reseed de preview) | Resolver identidad por `cif_normalized`/búsqueda |
| `409` en `stage` | Guard de la state-machine no cumplido | Releer estado/etapa antes de transicionar |
| `unavailable` en investors/advisors | Sin fuente de datos | Tratar como estado válido (no error) |
| Datos "vacíos"/de prueba | Preview usa dataset **sintético** | Validar contra estructura; datos reales en producción |
| OpenAPI devuelve HTML | Usar la ruta bajo `/api` | `GET /api/v1/openapi/arroba.v1.json` (no `/openapi.json`) |

### 7.3 Monitorización
- **Salud del proveedor:** `GET /api/v1/health` (esperar `200`).
- **Contrato disponible:** `GET /api/v1/openapi/arroba.v1.json` (`200`, `info.version = arroba-integration-contract-v1`).
- **Métricas a vigilar en arroba:** tasa de `429` (ajustar concurrencia), latencia p95 por motor, tasa de
  `5xx`, ratio de respuestas `unavailable`.
- **Versionado:** registrar el `*_version` recibido; alertar si cambia inesperadamente (posible bump).
- **Freeze del contrato (lado Agency Tool):** CI `Arroba Public Contract Freeze` bloquea cambios que
  rompan `arroba.v1` sin publicar `v2`.

---

## 8. Roadmap

### Cubierto por v1 (disponible hoy)
- Master Record canónico + Entity Resolution (cobertura ~98%).
- Financial, Signal, Semantic, Recommendation, Strategy (completos).
- Transaction OS **Origination → Due Diligence inicial** (workspace, next-action, tasks, docs, timeline, stage).
- Universal Search, Similares, Comparables, Buyers/Sellers, Matching, Thesis, Scenarios, Decision.
- OpenAPI público filtrado + Swagger UI + snapshot congelado + freeze test en CI.

### Diferido a v2 (no disponible aún)
> 🆕 **Ya disponible en `arroba.v2` (Sprint V2.0, 2026-07-12):** DTO de respuesta **tipados** de los 6
> motores + **Company/Identity** público (cabecera de la Ficha). Ver `ARROBA_V2_INTEGRATION_GUIDE.md`.
> Lo siguiente **sigue diferido** a sprints V2.1–V2.4:
- Transaction v2: IOI / LOI / SPA / signing / closing / post-closing.
- Recommendation: `investors` / `advisors` con fuente real (hoy `unavailable`).
- Alertas/Watchlist con **push/suscripción** (hoy polling).
- Notes; Governance detallado; Sector KPIs ampliados; M&A Transactions enriquecidas.
- Knowledge Graph v2 (relaciones semánticas de alta confianza).
- Datos reales de Iberinform (hoy dataset sintético en preview) y, tras ello, resolución de los ~27 casos
  de revisión manual del Entity Resolution y eventual activación del motor canónico.

> Cualquier cambio incompatible se publicará como **`arroba-v2`** (nuevo endpoint `/api/v1/openapi/arroba.v2.json`)
> conviviendo con v1 hasta que arroba.com valide y migre. v1 no se romperá en silencio.

---

### Anexo · Referencias
- Contrato detallado: `ARROBA_INTEGRATION_CONTRACT_v1.md` · Handoff: `ARROBA_ONBOARDING_HANDOFF.md`
- Certificación: `ARROBA_INTEGRATION_READINESS_CERT.md` · Rotación: `API_KEY_ROTATION_RUNBOOK.md`
- Snapshot congelado: `backend/contracts/arroba.v1.json` · Freeze test: `tests/golden/test_arroba_contract_freeze.py`
