# PLAN DE CONTRATO — arroba.v2 (cierre de gaps de la Ficha de Empresa)
**Hoja de ruta priorizada para cubrir los ~41 campos MISSING sin romper `arroba.v1`.**
_Versión: `arroba-v2-plan-v1` · 2026-07-04 · Solo planificación (sin código, sin cambios de contrato hoy)._

> ✅ **ESTADO 2026-07-12 — Sprint V2.0 (V2-01 + V2-02) COMPLETADO, APROBADO Y CONGELADO.**
> DTO de respuesta tipados de los 6 motores + Company/Identity público. Contrato `arroba.v2.json`
> congelado (54 rutas, 91 schemas), matriz contrato↔runtime 53/53 MATCH, freeze v1 byte-idéntico.
> Docs: `ARROBA_V2_INTEGRATION_GUIDE.md`, `ARROBA_V2_SPRINT_V2.0_REPORT.md`.
> **Sprints V2.1–V2.4 siguen PENDIENTES (no iniciados).** V2.1 se retomará tras validar la Ficha de Empresa.

> Origen: auditorías `EMPRESA_COVERAGE_AUDIT_v1`, `EMPRESA_FIELD_MAPPING_AUDIT_v1`, `EMPRESA_ACC_ARCHITECTURE_AUDIT_v1`.
> Objetivo: que TODA la Ficha de Empresa (ACC v1.0) sea alimentable exclusivamente por contrato público.
> **Reglas invariables:** (1) `v1` permanece congelado y operativo · (2) todo cambio es **aditivo** o vive
> bajo `/api/v2/**` · (3) nada de lógica de negocio en el frontend (Intelligence First) · (4) todo endpoint
> nuevo con `X-API-Key`, versionado en respuesta y con DTO **tipado** en OpenAPI.

---

## 0. Dos ejes de trabajo
- **Eje A — Calidad de contrato (transversal):** **tipar los DTO de respuesta** de TODOS los motores en el
  OpenAPI (hoy `responses.200.schema = {}`). Desbloquea la trazabilidad contractual y la autogeneración de
  cliente. **Aditivo, no rompe `v1`** (solo añade schema a respuestas ya existentes).
- **Eje B — Cobertura de datos:** crear/ampliar endpoints para los ~41 campos MISSING, agrupados por dominio.

---

## 1. Backlog priorizado (P0 → P3)

### 🟥 P0 — Fundacional (habilita el resto)
| Item | Qué | Motor/Endpoint | Cierra |
|---|---|---|---|
| V2-01 | **Tipar DTOs de respuesta** (Financial, Signal, Semantic, Recommendation, Strategy, Transaction) en OpenAPI | (transversal) | Trazabilidad contractual · PARADA A del field-mapping |
| V2-02 | **Company/Identity público** (identidad extendida sin JWT) | `GET /api/v2/company/{id}` (nuevo, lectura Master proyectada) | 1001, 1002, 1003 (commercial_name, aliases, web/domain, country, capital_social, location, public_status) |

### 🟧 P1 — Núcleo de la Ficha (alto valor, datos ya existentes en el Master/KG)
| Item | Qué | Motor/Endpoint | Cierra |
|---|---|---|---|
| V2-03 | **Ownership público** (estructura de propiedad + grupo) | `POST /api/v2/ownership-intelligence/profile` | 5001–5005 (shareholders, parents, ultimate_parent, investees, group_id) |
| V2-04 | **Ownership Network** (grafo de propiedad) | `POST /api/v2/ownership-intelligence/network` (expone `master_relationships`) | 5006 |
| V2-05 | **Cash Flow** (estado de flujos) | AMPLIAR `financial/analyze` → `cashflow{operating,investing,financing}` o `POST /api/v2/financial-intelligence/cashflow` | 3005 |

### 🟨 P2 — Profundidad analítica y gobierno
| Item | Qué | Motor/Endpoint | Cierra |
|---|---|---|---|
| V2-06 | **Valoración avanzada** (EV bridge, escenarios, sensibilidad) | AMPLIAR `financial/valuation` → `bridge{}`, `scenarios[]`, `sensitivity[][]` | 4005, 4006, 4007 |
| V2-07 | **Governance público** (consejo, ejecutivos, apoderados, timeline) | `POST /api/v2/governance-intelligence/profile` (requiere ingesta previa de detalle societario) | 6001–6007 |
| V2-08 | **Comparativa consolidada** (matriz, gaps, positioning estructurado) | AMPLIAR `recommendation/*` → `positioning`, `gaps[]`, `difference_matrix` | 9002, 9003, 9005, 9006 |

### 🟩 P3 — Mercado, rankings y fuentes (mayor dependencia de dato/ingesta)
| Item | Qué | Motor/Endpoint | Cierra |
|---|---|---|---|
| V2-09 | **Market Intelligence público** (tamaño, estructura, tendencias, posicionamiento) | `POST /api/v2/market-intelligence/{overview,size,trends,positioning}` (expone `sector_intelligence`/`geo_*`) | 7001–7007 |
| V2-10 | **Rankings** (percentiles por dimensión) | `POST /api/v2/ranking-intelligence/company` | 8001, 8002 |
| V2-11 | **Sources & Registry** (BORME, cuentas anuales, trazabilidad de fuentes) | `POST /api/v2/sources/{registry-events,annual-accounts,provenance}` (expone `borme_events`, provenance) | 12001–12004 |
| V2-12 | **Documents público** (documentos de empresa fuera del Transaction OS) | `GET /api/v2/company/{id}/documents` | 12005 |

---

## 2. Mapa item → componentes → campos MISSING cerrados

| Item | Componentes ACC | Campos MISSING que cierra |
|---|---|---|
| V2-01 | (todos) | trazabilidad contractual de los ~92 campos servidos |
| V2-02 | 1001, 1002, 1003 | commercial_name, aliases, country, contact.web/domain, capital_social, location, public_status |
| V2-03 | 5001–5005 | shareholders[], parents[], ultimate_parent, investees[], group_id |
| V2-04 | 5006 | ownership network edges (`master_relationships`) |
| V2-05 | 3005 | cashflow{operating, investing, financing} |
| V2-06 | 4005, 4006, 4007 | EV bridge, valuation scenarios, sensitivity matrix |
| V2-07 | 6001–6007 | board_members[], executives[], legal_representatives[], governance_timeline[] |
| V2-08 | 9002, 9003, 9005, 9006 | positioning, competitive_gaps[], difference_matrix |
| V2-09 | 7001–7007 | market_size, structure, trends, positioning, risks |
| V2-10 | 8001, 8002 | rank, percentile por dimensión |
| V2-11 | 12001–12004 | borme_events[], annual_accounts[], registry_info, source_provenance |
| V2-12 | 12005 | documents[] |

> Tras V2-01…V2-12: **0 campos MISSING** en la Ficha → objetivo **PASS** (100% alimentable por contrato público).

---

## 3. Dependencias de datos (qué existe vs qué requiere ingesta)
| Item | ¿Dato ya en Agency Tool? | Trabajo previo de ingesta |
|---|---|---|
| V2-02, V2-03, V2-04 | ✅ Sí (`master_companies.ownership`, `master_relationships`) | Ninguno (solo exponer/proyectar) |
| V2-05 | ⚠️ Parcial | Requiere modelo de cash flow (deriva de balances o fuente) |
| V2-06 | ✅ Base en Financial | Solo cálculo/desglose adicional |
| V2-08, V2-10 | ✅ Base en Recommendation | Solo agregación/derivación |
| V2-09 | ⚠️ Parcial (`sector_intelligence`) | Consolidar y exponer |
| V2-07, V2-11, V2-12 | ❌ No / incompleto | **Requiere ingesta real** (detalle societario, BORME, cuentas anuales, documentos) |

> **Nota crítica:** V2-07/09/10/11/12 dependen de **datos reales de Iberinform/BORME/registro** (hoy el
> preview usa dataset sintético). Su fecha real depende de la disponibilidad de esas fuentes.

---

## 4. Estrategia de versionado y convivencia
- **`v1` intacto**: los 6 motores actuales y sus DTO no se tocan (freeze test + CI lo protegen).
- **Aditivo dentro de v1** cuando sea posible (V2-05 ampliando `financial/analyze.cashflow`, V2-06 ampliando
  `financial/valuation`): campos **opcionales nuevos** → compatibles, no rompen v1.
- **Nuevos motores/endpoints bajo `/api/v2/**`** (Ownership, Governance, Market, Ranking, Sources, Company):
  contrato **`arroba.v2`** con su propio `GET /api/v2/openapi/arroba.v2.json` + snapshot congelado + freeze test.
- **Convivencia**: `v1` y `v2` operan en paralelo; arroba migra por componente sin big-bang.

---

## 5. Secuencia recomendada (sprints)
1. **Sprint V2.0** — V2-01 (tipar DTOs) + V2-02 (Company/Identity público). *Desbloquea trazabilidad y cabecera.*
2. **Sprint V2.1** — V2-03 + V2-04 (Ownership) + V2-05 (Cash Flow). *Datos ya existentes; alto valor.*
3. **Sprint V2.2** — V2-06 (valoración avanzada) + V2-08 (comparativa consolidada).
4. **Sprint V2.3** — V2-09 (Market) + V2-10 (Rankings). *Sujeto a consolidación de sector intel.*
5. **Sprint V2.4** — V2-07 (Governance) + V2-11 + V2-12 (Sources/Registry/Documents). *Sujeto a ingesta real.*

**Criterio de cierre de v2:** los 3 audits re-ejecutados dan **PASS** (cobertura 100%, field-mapping sin
MISSING, ACC sin cambios) y `arroba.v2.json` congelado con freeze test verde.

---

## 6. Fuera de alcance (no incluir en v2 salvo decisión de producto)
- Push/suscripción de alertas (hoy polling) — mejora, no gap de la Ficha.
- Transaction v2 (IOI/LOI/SPA/closing) — pertenece al Deal Room, no a la Ficha de Empresa.
- Enriquecimiento de M&A Transactions — no requerido por el ACC de Empresa.
