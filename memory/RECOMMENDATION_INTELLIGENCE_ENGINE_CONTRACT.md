# RECOMMENDATION_INTELLIGENCE_ENGINE_CONTRACT.md
**Contrato oficial (PROPUESTA) — Recommendation Intelligence Engine**
_Versión: `recommendation-intelligence-v1` · 2026-06-26 · Estado: **CONGELADO (FROZEN)** — DR1…DR10 aprobadas. Cualquier cambio posterior requiere versionado; no se permiten cambios incompatibles sin versión mayor._

> **Primer motor CONSUMIDOR** de la Intelligence Layer. **No genera conocimiento nuevo**: combina el conocimiento ya producido (Financial + Signal + Semantic + Master + KG) para responder **¿qué debería hacer con esta empresa?** de forma **explicable**. Nunca recrea inteligencia; la **reutiliza** vía los contratos de los productores.

---

## 0. Lugar en la Intelligence Layer
Consumidor según `INTELLIGENCE_LAYER_ARCHITECTURE.md` (DAG acíclico).
- **Consume**: Master (`master-v1`), Financial (`financial-intelligence-v1`), Signal (`signal-intelligence-v1`), Semantic (`semantic-intelligence-v1`), Knowledge Graph (`knowledge-graph-v1`).
- **No consume**: Strategy/Transaction (están por encima), ni fuentes originales/Normalized.
- **Desbloquea**: Strategy (tesis sobre recomendaciones) y Transaction (Copilot).

---

## 1. Filosofía
- **Pregunta única**: *¿Qué debería hacer con esta empresa?* No responde *qué es* (Semantic), *cómo funciona* (Financial) ni *qué ha ocurrido* (Signal).
- **Reutilización, no reconstrucción**: toda salida se apoya en los productores; el motor **orquesta y razona**, no recalcula KPIs, señales ni embeddings.
- **Explainability / Boundary / Contract First**: ninguna recomendación es un porcentaje opaco; siempre se explica con la evidencia de cada motor.
- **Master como única verdad**: todas las entidades se referencian por `master_id`.

---

## 2. Responsabilidades
Producir **rankings explicables** y **matching razonado** para:
1. **Comparables inteligentes** (no solo CNAE).
2. **Compradores** adecuados para un target.
3. **Vendedores / targets** de interés para un comprador.
4. **Inversores** con encaje.
5. **Advisors** con mejor encaje.
6. **Oportunidades prioritarias**.
7. **Matching empresarial** (por qué dos empresas encajan).

> **No** es responsabilidad: producir KPIs, señales, perfiles o embeddings (eso lo hacen los productores). Tampoco tesis estratégicas (Strategy) ni orquestación de operaciones (Transaction).

---

## 3. Entradas (estrictas)
Solo a través de los **contratos** de:
- **Master Layer** — identidad, clasificación, tamaño, ubicación, ownership, `group_id`.
- **Financial Engine** — KPIs, ratios, calidad, comparables financieros, valoración.
- **Signal Engine** — señales (con dimensiones), categoría `opportunity`, `signal_score`.
- **Semantic Engine** — Company Semantic Profile, embedding, `/similar` (similitud top-k con blocking).
- **Knowledge Graph** — relaciones de ownership reales (consolidadores, grupos, participadas).
- **Prohibido**: fuentes originales, `norm_*`, lectura directa de colecciones de otro motor.

---

## 4. Capacidades y salidas

### 4.1 Comparables inteligentes (`/comparables`)
Combina **similitud semántica** (Semantic `/similar`), **proximidad financiera** (Financial: tamaño, márgenes, sector) y **estructura** (KG/grupo). No solo CNAE. Devuelve ranking con desglose por dimensión.

### 4.2–4.6 Rankings explicables
**Compradores (`/buyers`)**, **Vendedores/targets (`/sellers`)**, **Inversores (`/investors`)**, **Advisors (`/advisors`)**, **Oportunidades (`/opportunities`)**. Cada ítem con score + breakdown + evidencia + explicación.

### 4.7 Matching empresarial (`/matching`)
Explica **por qué** dos empresas encajan: dimensiones de encaje (semántico, financiero, estructural, de señales), no solo un porcentaje.

---

## 5. Modelo de respuesta (objeto Recomendación)
Toda recomendación expone el razonamiento, **no un número opaco**:

```jsonc
{
  "recommendation_id": "rec_<hash12>",         // determinista (ver §8)
  "target": { "master_id": "mc_…", "name": "…" },
  "candidate": { "entity_type": "company|buyer|seller|investor|advisor",
                 "master_id": "mc_…|null", "name": "…" },
  "recommendation_type": "comparable|buyer|seller|investor|advisor|opportunity|match",
  "recommendation_role": "strategic_buyer|financial_buyer|roll_up_candidate|acquisition_target|divestment_candidate|merger_candidate|partnership_candidate|null",  // DR4
  "score": 0.0-1.0,                            // DERIVADO de las 5 dimensiones; nunca opaco
  "fit_dimensions": {                          // DR2 — CINCO dimensiones independientes, SIEMPRE visibles
    "strategic_fit": { "value": 0.0-1.0, "evidence": [ "…" ], "sources": ["knowledge-graph-v1","signal-intelligence-v1"] },
    "financial_fit": { "value": 0.0-1.0, "evidence": [ "…" ], "sources": ["financial-intelligence-v1"] },
    "semantic_fit":  { "value": 0.0-1.0, "evidence": [ "…" ], "sources": ["semantic-intelligence-v1"] },
    "signal_fit":    { "value": 0.0-1.0, "evidence": [ "…" ], "sources": ["signal-intelligence-v1"] },
    "execution_fit": { "value": 0.0-1.0, "evidence": [ "…" ], "sources": ["master-v1","knowledge-graph-v1"] }
  },
  "score_method": "derived_from_fit_dimensions",   // pesos versionados; las 5 dims se conservan
  "composed_of": [ "rec_…" ],                  // DR7 — recomendaciones menores reutilizadas (no recalculadas)
  "graph_edges": [ { "from":"mc_…","to":"mc_…","relation":"buyer|advisor|comparable|opportunity","rec_id":"rec_…" } ],  // DR8 (previsto)
  "evidence": {                                // evidencia concreta reutilizada de cada motor
    "engines_used": ["semantic-intelligence-v1","financial-intelligence-v1","signal-intelligence-v1","master-v1"],
    "semantic_profile_used": { "dimensions": ["economic_activity","sectors","capabilities"], "similarity": 0.0-1.0 },
    "financial_metrics_used": { "revenue": …, "ebitda_margin": …, "valuation_method": "…" },
    "signals_relevant": [ { "signal_id":"…","signal_type":"…","dimensions":{…} } ],
    "structural": { "same_group": false, "is_consolidator": false, "ownership_path": null }
  },
  "confidence": {                              // DR5 — multifactor, no solo cobertura
    "value": 0.0-1.0,
    "factors": { "coverage": …, "data_quality": …, "cross_engine_consistency": …,
                 "recency": …, "profile_completeness": … }
  },
  "explanation": "texto final que justifica la recomendación citando la evidencia",
  "recommended_actions": ["analyze","compare","contact","request_due_diligence"],  // DR6 — enum canónico del Signal Engine (act-v*)
  "recommendation_version": "recommendation-intelligence-v1",
  "recommendation_method": "weighted-blend-v1",
  "engines_used": ["…"],
  "evidence_version": { "master":"master-v1","financial":"financial-intelligence-v1",
                        "signal":"signal-intelligence-v1","semantic":"semantic-intelligence-v1",
                        "knowledge_graph":"knowledge-graph-v1" }
}
```

> **Investors/Advisors (DR1)**: los endpoints existen pero responden `{ "status":"unavailable", "reason":"source_not_available", "recommendations": [] }`. **Nunca** datos simulados.

Respuesta de un endpoint de ranking:
```jsonc
{ "target": {…}, "recommendation_type": "buyer", "count": n,
  "recommendations": [ {…objeto Recomendación…} ],
  "method": "weighted-blend-v1", "blocking": {…},
  "recommendation_version": "recommendation-intelligence-v1", "generated_at": "ISO" }
```

---

## 6. API (contrato público del motor)
Auth: `X-API-Key`. Prefijo: `/api/v1/recommendation-intelligence`. Agnóstico de UI.

| Método | Endpoint | Propósito |
|---|---|---|
| `POST` | `/comparables` | Comparables inteligentes (semántico+financiero+estructural). |
| `POST` | `/buyers` | Ranking de compradores para un target. |
| `POST` | `/sellers` | Ranking de vendedores/targets para un comprador. |
| `POST` | `/investors` | Ranking de inversores con encaje. |
| `POST` | `/advisors` | Ranking de advisors con encaje. |
| `POST` | `/matching` | Encaje razonado entre dos empresas (`{a, b}`). |
| `POST` | `/opportunities` | Oportunidades prioritarias (reutiliza Signal `opportunity` + fit). |
| `POST` | `/explain` | Explicación detallada de una recomendación (`{recommendation_id}` o `{target, candidate, type}`). |
| `GET`  | `/catalog` | Tipos de recomendación, método/pesos, versiones de evidencia y motores consumidos. |

---

## 7. Explicabilidad (obligatoria)
Toda recomendación indica: **motores utilizados** (`engines_used`), **evidencias** (`evidence`), **señales relevantes** (`signals_relevant`), **perfil semántico utilizado** (`semantic_profile_used`), **métricas financieras utilizadas** (`financial_metrics_used`), **confianza multifactor** (`confidence.factors`, DR5) y **explicación final** (`explanation`). Nunca un porcentaje solo: el `score` se **deriva de las 5 `fit_dimensions`** (DR2), que permanecen siempre visibles.

## 7bis. Recomendaciones compuestas (DR7)
Una recomendación puede **componerse** de recomendaciones menores ya calculadas (p. ej. *Strong Acquisition Candidate* = comparable excelente + alta calidad financiera + señales de crecimiento + alta similitud semántica). Se referencian en `composed_of: [rec_id…]`; el motor **reutiliza** esas piezas, **nunca las recalcula**. La compuesta hereda/agrega sus `fit_dimensions` y cita su evidencia.

## 7ter. Recommendation Graph (DR8 — previsto, no implementado en v1)
Las recomendaciones **no son independientes**: forman un **grafo** (`empresa → buyer → advisor → opportunity → comparable → transaction thesis`). Cada recomendación declara `graph_edges` para que **Strategy** y **Transaction** reutilicen estas relaciones. v1 emite `graph_edges` por recomendación; la **materialización del grafo completo** queda prevista para una versión posterior (sin romper el contrato).

---

## 8. Versionado y reproducibilidad
- **Campos obligatorios** en cada recomendación: `recommendation_version`, `recommendation_method`, `engines_used`, `evidence_version`.
- **`evidence_version`**: snapshot de las versiones de los motores consumidos → reproducibilidad "as-of".
- **`recommendation_id` determinista**: `hash(target + candidate + recommendation_type + recommendation_method + evidence_version)`.
- **`recommendation_method` versionado** (`weighted-blend-v1`): los pesos del `score_breakdown` viven en **config versionada** (no hardcode), recalibrables sin romper el contrato.
- **Compatibilidad**: añadir tipos/dimensiones de fit = aditivo; cambios incompatibles ⇒ versión mayor con convivencia.

---

## 9. Dependencias estrictas
Consume **solo** Master + Financial + Signal + Semantic + KG (vía sus contratos). Migración legacy: `skills_recommend` → este motor (paridad → migración de consumidores → retirada de `companies_master`).

---

## 10. Criterios de aceptación

### Definition of Ready (contrato congelable) — estado tras DR1…DR8
1. ✅ Modelo de recomendación (§5) con `fit_dimensions` (5) y `score` derivado, nunca opaco.
2. ✅ 9 endpoints (§6) y tipos + `recommendation_role` (DR4) aprobados.
3. ✅ Universo resuelto (DR1): comparables/buyers/sellers/matching/opportunities disponibles; investors/advisors `unavailable`+`source_not_available`.
4. ✅ Score por 5 dimensiones (DR2) + confianza multifactor (DR5) + acciones canónicas reutilizadas (DR6).
5. ✅ Dependencias limitadas a los 5 motores; sin acceso a fuentes ni colecciones ajenas.
6. ✅ Persistencia selectiva (DR3), recomendaciones compuestas (DR7) y Recommendation Graph previsto (DR8).

### Definition of Done (implementación, cuando arranque)
- Motor `recommendation-intelligence-v1` desacoplado en `services/engines/recommendation/`, API `/api/v1/recommendation-intelligence/*` con `X-API-Key`.
- Cada recomendación cumple §5/§7/§8; `score` siempre con breakdown; reutiliza productores (no recrea inteligencia).
- Suite smoke verde + verificación end-to-end contra URL externa; este documento pasa a ESTABLE.

---

## Decisiones arquitectónicas cerradas (DR1…DR8) — congeladas en `recommendation-intelligence-v1`
- **DR1 — Universo disponible (sin inventar datasets)**: v1 disponibles → **comparables, buyers, sellers, matching, opportunities**. **Investors y advisors** permanecen en el contrato pero responden `status:"unavailable"` + `reason:"source_not_available"`; **nunca** datos simulados.
- **DR2 — 5 dimensiones de fit independientes**: cada recomendación expone `fit_dimensions` = **Strategic Fit · Financial Fit · Semantic Fit · Signal Fit · Execution Fit**. El `score` final se **deriva** de ellas (pesos versionados) pero las 5 permanecen **siempre visibles**.
- **DR3 — Persistencia selectiva**: solo se persisten recomendaciones **aceptadas**, **descartadas** o **convertidas en oportunidad**. Las **exploratorias** se calculan **on-demand** (caché opcional). Colección `recommendation_decisions` (estado + decisión + timestamp).
- **DR4 — `recommendation_role`**: además del `recommendation_type`, cada recomendación lleva un **rol** reutilizable: `strategic_buyer · financial_buyer · roll_up_candidate · acquisition_target · divestment_candidate · merger_candidate · partnership_candidate`.
- **DR5 — Confianza multifactor**: `confidence.factors` = **coverage · data_quality · cross_engine_consistency · recency · profile_completeness**. No depende solo de cobertura.
- **DR6 — Acciones canónicas**: se **reutiliza exactamente** el catálogo de acciones del Signal Engine (`act-v*`). No se crea uno nuevo.
- **DR7 — Recomendaciones compuestas**: una recomendación puede componerse de recomendaciones menores ya calculadas (`composed_of`), **reutilizando** inteligencia, nunca recalculándola.
- **DR8 — Recommendation Graph (previsto)**: las recomendaciones forman un grafo (`graph_edges`) reutilizable por **Strategy** y **Transaction**. v1 emite las aristas por recomendación; la materialización completa del grafo queda prevista para una versión posterior.
- **DR9 — Recommendation Memory**: las recomendaciones no son efímeras. El motor registra el ciclo de vida de cada una: `proposed · accepted · rejected · ignored · converted_to_opportunity · converted_to_deal · outcome`. No es solo persistencia: construye **memoria** para mejorar futuras recomendaciones; este histórico será consumido por **Strategy Intelligence Engine**. Colección `recommendation_memory` (keyed por `recommendation_id`, con timeline de estados).
- **DR10 — Recommendation Feedback Loop**: el motor queda preparado para **recalibrarse mediante feedback explícito** (no ML obligatorio). Eventos: `accepted · rejected · ended_in_acquisition · ended_in_failure · never_executed`. El feedback **no modifica directamente las reglas**: queda registrado como **evidencia** (`recommendation_feedback`) para futuras versiones/recalibración del motor (enlaza con la calibración versionada de pesos `recommendation_method`).

## API adicional (DR9/DR10)
| Método | Endpoint | Propósito |
|---|---|---|
| `POST` | `/feedback` | Registrar feedback/decisión sobre una recomendación (`{recommendation_id, event, outcome?, notes?}`) — alimenta Memory (DR9) y Feedback Loop (DR10). |
| `POST` | `/memory` | Consultar la memoria/histórico de recomendaciones (`{target?, recommendation_id?, state?}`) — consumible por Strategy. |

## Principio fundamental
El Recommendation Intelligence Engine no responde solo *"¿qué empresa se parece a esta?"*. Responde **¿cuál es la mejor decisión posible utilizando toda la inteligencia disponible del sistema?** — combinando, sin recrear, Financial + Signal + Semantic + Master + KG, con explicabilidad total.
