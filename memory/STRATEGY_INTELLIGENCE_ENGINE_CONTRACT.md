# STRATEGY_INTELLIGENCE_ENGINE_CONTRACT.md
**Contrato oficial (PROPUESTA) — Strategy Intelligence Engine**
_Versión: `strategy-intelligence-v1` · 2026-06-26 · Estado: **CONGELADO (FROZEN)** — DT1…DT15 aprobadas. Cualquier cambio posterior requiere versionado; no se permiten cambios incompatibles sin versión mayor._

> Motor CONSUMIDOR de alto nivel. **No genera conocimiento ni recomendaciones**: construye **tesis estratégicas explicables** reutilizando toda la inteligencia previa (Financial + Signal + Semantic + Recommendation + Recommendation Memory + Master + KG). Equivale a un **analista senior de Corporate Development** trabajando sobre una infraestructura totalmente explicable. No es un generador de informes ni un LLM que opina.

---

## 0. Lugar en la Intelligence Layer
Consumidor superior según `INTELLIGENCE_LAYER_ARCHITECTURE.md` (DAG acíclico). Está **por encima** de Recommendation y **por debajo** de Transaction.
- **Consume**: Master (`master-v1`), Financial (`financial-intelligence-v1`), Signal (`signal-intelligence-v1`), Semantic (`semantic-intelligence-v1`), Recommendation (`recommendation-intelligence-v1`) **+ Recommendation Memory (DR9)**, Knowledge Graph (`knowledge-graph-v1`).
- **No consume**: Transaction (está por encima), ni fuentes originales/Normalized.
- **Desbloquea**: Transaction Intelligence Engine (ejecuta la tesis).

---

## 1. Filosofía
- **Pregunta única**: *¿Cuál es la mejor estrategia posible para esta empresa en este momento?* No responde *qué es / cómo funciona / qué señales tiene / qué comparables hay* (ya resuelto por otros motores).
- **Convierte inteligencia en tesis**: compone la inteligencia existente en una **estrategia coherente, justificada y comparable**.
- **Explainability / Boundary / Contract First**: ninguna tesis es caja negra; cada una cita la inteligencia y recomendaciones que la sustentan, con hipótesis explícitas y confianza.
- **Reutiliza, no recrea**: nunca recalcula KPIs, señales, perfiles ni recomendaciones.

---

## 2. Responsabilidades / Capacidades
Generar **tesis estratégicas explicables** y soporte a la decisión:
1. **Strategic Thesis** — tesis estratégica general de la empresa.
2. **Consolidation Thesis** — oportunidades de consolidación (roll-up, sector fragmentado).
3. **Acquisition Thesis** — justificación de una adquisición concreta.
4. **Divestment Thesis** — justificación de una desinversión.
5. **Partnership Thesis** — justificación de alianzas estratégicas.
6. **Capital Raising Thesis** — si la empresa debería buscar financiación.
7. **Growth Strategy** — escenarios de crecimiento.
8. **Risk Strategy** — riesgos estratégicos.
9. **Scenario Builder** — **varios** escenarios alternativos (no uno).
10. **Decision Support** — explicar por qué una estrategia es mejor que otra.

> **No** es responsabilidad: producir conocimiento base, recomendaciones individuales ni ejecutar operaciones (Transaction).

---

## 3. Entradas (estrictas)
Solo vía contratos de: **Master**, **Financial**, **Signal**, **Semantic**, **Recommendation** (+ **Recommendation Memory**), **Knowledge Graph**. **Prohibido**: fuentes originales, `norm_*`, lectura directa de colecciones de otros motores.

---

## 4. Modelo de salida — objeto Tesis (Strategy)

```jsonc
{
  "thesis_id": "ths_<hash12>",                 // determinista (ver §7)
  "subject": { "master_id": "mc_…", "name": "…" },
  "thesis_type": "strategic|consolidation|acquisition|divestment|partnership|capital_raising|growth|risk",
  "statement": "tesis en lenguaje claro (qué se propone y por qué)",
  "rationale": [ "argumento 1 (citando evidencia)", "argumento 2", … ],
  "narrative_method": "rules|ai",             // [DT1] IA solo redacta/resume/explica; nunca crea afirmaciones sin evidencia
  "hypotheses": [ { "assumption":"…", "basis":["rec_…","signal_…"], "confidence":0.0-1.0 } ],   // explícitas
  "time_horizon": { "chosen":"short|mid|long", "justification":"…",       // [DT9] siempre presente
                    "by_horizon": { "short":"…","mid":"…","long":"…" } },
  "strategic_dimensions": {                    // [DT2] dimensiones oficiales; el score NO las sustituye
    "strategic_attractiveness": { "value":0.0-1.0, "evidence":[…] },
    "execution_feasibility":    { "value":0.0-1.0, "evidence":[…] },
    "value_creation_potential": { "value":0.0-1.0, "evidence":[…] },
    "risk_exposure":            { "value":0.0-1.0, "evidence":[…] },
    "timing":                   { "value":0.0-1.0, "evidence":[…] }
  },
  "score": 0.0-1.0,                            // DERIVADO de las dimensiones (no opaco)
  "constraints": [ "requires_financing|requires_regulatory_approval|requires_tech_integration|requires_prior_growth|requires_partners|…" ],  // [DT12]
  "alternatives": [ { "thesis_type":"…","statement":"…","score":0.0-1.0,
                      "why_not_preferred":"…" } ],   // [DT11] siempre ≥1 alternativa
  "preferred_rationale": "por qué la tesis recomendada es preferible a las alternativas",  // [DT11]
  "explainability_tree": {                     // [DT13] tesis→hipótesis→recomendaciones→señales→evidencias→datos
    "thesis": "ths_…",
    "hypotheses": [ "…" ],
    "recommendations": [ "rec_…" ],
    "signals": [ "signal_…" ],
    "evidence": [ "financial:…","semantic:…","structural:…" ],
    "source_data": [ "master_id:…","source_version:…" ]
  },
  "evidence": {
    "intelligence_used": ["financial-intelligence-v1","signal-intelligence-v1","semantic-intelligence-v1"],
    "recommendations_used": [ "rec_…" ],       // [DT7] referencias versionadas, NUNCA copia de datos
    "recommendation_memory_used": [ "rec_… (state)" ],
    "signals_used": [ {"signal_id":"…","signal_type":"…"} ],
    "financial_evidence": { "ref":"financial-intelligence-v1","valuation_ref":… },
    "semantic_evidence": { "ref":"semantic-intelligence-v1","positioning_ref":… },
    "structural_evidence": { "ref":"knowledge-graph-v1","group":…,"consolidator":… }
  },
  "recommended_actions": ["analyze","value","contact","raise_capital","request_due_diligence"], // enum canónico Signal act-v*
  "confidence": { "value":0.0-1.0, "factors": {                     // [DT5] multifactor
      "evidence_quality":…, "cross_engine_consistency":…, "coverage":…, "recency":…, "hypotheses_count":… } },
  "lifecycle": { "state":"proposed|validated|rejected|executing|completed|abandoned",   // [DT4][DT14]
                 "result":null, "result_date":null, "learning":null },
  "graph_edges": [ { "from":"ths_…","to":"ths_…|mc_…|rec_…","relation":"depends_on|targets|derived_from|leads_to" } ],   // [DT8] Strategy Graph
  "status": "available|insufficient_evidence",  // [DT10]
  "insufficient": { "missing_evidence":[…], "needed_hypotheses":[…], "additional_info_required":[…] }, // [DT10] cuando aplique
  "strategy_version": "strategy-intelligence-v1",
  "strategy_method": "evidence-composition-v1",
  "engines_used": ["…"],
  "recommendation_version": "recommendation-intelligence-v1",
  "evidence_version": { "master":"master-v1","financial":"…","signal":"…","semantic":"…",
                        "recommendation":"recommendation-intelligence-v1","knowledge_graph":"knowledge-graph-v1" },
  "generated_at": "ISO"
}
```

Scenario Builder (`/scenarios`) devuelve **escenarios parametrizables** (por defecto `conservative · base · aggressive`, ampliable):
```jsonc
{ "subject":{…}, "scenario_types_requested":["conservative","base","aggressive"],
  "scenarios": [ { "scenario":"conservative|base|aggressive|<custom>",
    "narrative":"…", "narrative_method":"rules|ai", "assumptions":[…], "implied_strategy":"acquisition|…",
    "time_horizon":{…}, "strategic_dimensions":{…}, "score":0.0-1.0, "constraints":[…], "confidence":{…} } ],
  "decision_support": { "preferred":"…","ranking":[…],
                        "comparison": { "advantages":[…],"disadvantages":[…],"risks":[…],
                                        "hypotheses":[…],"success_conditions":[…] } },   // [DT6]
  "strategy_version":"strategy-intelligence-v1","generated_at":"ISO" }
```

---

## 5. API (contrato público del motor)
Auth: `X-API-Key`. Prefijo: `/api/v1/strategy-intelligence`. Agnóstico de UI.

| Método | Endpoint | Propósito |
|---|---|---|
| `POST` | `/thesis` | Strategic Thesis general (`{identifier}`). |
| `POST` | `/scenarios` | Scenario Builder — varios escenarios + decision support. |
| `POST` | `/growth` | Growth Strategy. |
| `POST` | `/acquisition` | Acquisition Thesis (`{acquirer, target}` o `{identifier}`). |
| `POST` | `/divestment` | Divestment Thesis. |
| `POST` | `/partnership` | Partnership Thesis. |
| `POST` | `/capital` | Capital Raising Thesis. |
| `POST` | `/risk` | Risk Strategy. |
| `POST` | `/decision` | Decision Support — comparar estrategias y explicar la mejor. |
| `GET`  | `/catalog` | Tipos de tesis, dimensiones, método/pesos, versiones de evidencia. |

---

## 6. Explicabilidad (obligatoria)
Toda estrategia indica: **inteligencia utilizada**, **recomendaciones utilizadas** (+ memoria), **señales utilizadas**, **evidencia financiera/semántica/estructural**, **hipótesis realizadas** (explícitas con confianza) y **nivel de confianza** multifactor. El `score` se **deriva** de las `strategic_dimensions`, nunca un número opaco.

---

## 7. Versionado y reproducibilidad
- **Campos obligatorios**: `strategy_version`, `engines_used`, `recommendation_version`, `evidence_version`, `confidence`.
- **`thesis_id` determinista**: `hash(subject + thesis_type + strategy_method + evidence_version)`.
- **`strategy_method` versionado** (`evidence-composition-v1`); pesos de `strategic_dimensions` en **config versionada** (recalibrables sin romper contrato).
- **Compatibilidad**: añadir tipos/dimensiones/escenarios = aditivo; incompatibles ⇒ versión mayor con convivencia.

---

## 8. Dependencias estrictas
Consume solo los 6 motores/capas del §3. Migración legacy: no hay equivalente directo (motor nuevo); compone los existentes.

---

## 9. Criterios de aceptación (Definition of Ready) — requieren resolver DT1…DT10
Aprobar: modelo de tesis (§4) con dimensiones y score derivado; los 10 endpoints (§5); explicabilidad obligatoria (§6); versionado (§7); dependencias estrictas (§8); y las decisiones abiertas DT1…DT10.

### Definition of Done (implementación, cuando arranque)
- Motor `strategy-intelligence-v1` desacoplado en `services/engines/strategy/`, API `/api/v1/strategy-intelligence/*` con `X-API-Key`.
- Cada tesis cumple §4/§6/§7; reutiliza Recommendation+productores (no recrea); hipótesis explícitas; ≥2 escenarios en `/scenarios`.
- Suite smoke verde + verificación end-to-end contra URL externa; documento pasa a ESTABLE.

---

## Decisiones arquitectónicas cerradas (DT1…DT14) — congeladas en `strategy-intelligence-v1`
- **DT1 — IA acotada**: la IA **nunca** construye una tesis desde cero. La tesis se construye por **composición determinista de evidencia**; la IA solo **redacta/resume/reorganiza/mejora la narrativa/explica**. Toda frase IA debe trazarse a las evidencias (`narrative_method:"ai"`); nunca afirmaciones sin soporte.
- **DT2 — Dimensiones oficiales**: `strategic_attractiveness · execution_feasibility · value_creation_potential · risk_exposure · timing`. El `score` global es **derivado** y **no las sustituye**.
- **DT3 — Escenarios parametrizables**: por defecto `conservative · base · aggressive`; el contrato permite añadir tipos sin romperse.
- **DT4 — Strategy Memory**: toda tesis evoluciona; estados `proposed · validated · rejected · executing · completed · abandoned`; registra `result · result_date · learning`.
- **DT5 — Confianza multifactor**: `evidence_quality · cross_engine_consistency · coverage · recency · hypotheses_count`.
- **DT6 — Decision Support justificado**: no solo ordena; explica *por qué A es mejor que B* con `advantages · disadvantages · risks · hypotheses · success_conditions`.
- **DT7 — Reutilización por referencia**: las tesis reutilizan **referencias versionadas** a Financial/Signal/Semantic/Recommendation; **nunca copian datos**.
- **DT8 — Strategy Graph**: las tesis se relacionan entre sí (`graph_edges`: depends_on/targets/derived_from/leads_to); reutilizable por Transaction.
- **DT9 — Horizonte temporal**: toda tesis indica corto/medio/largo plazo (`time_horizon.by_horizon`) y **justifica** el horizonte elegido.
- **DT10 — Evidencia insuficiente (nunca inventar)**: si falta evidencia → `status:"insufficient_evidence"` con `missing_evidence · needed_hypotheses · additional_info_required`.
- **DT11 — Alternative Thesis**: nunca una sola estrategia; siempre `alternatives` (≥1) + `preferred_rationale` (por qué la recomendada es preferible).
- **DT12 — Strategy Constraints**: toda tesis declara `constraints` (financiación, aprobación regulatoria, integración tecnológica, crecimiento previo, socios…). Forman parte de la tesis.
- **DT13 — Explainability Tree**: toda tesis se descompone en `explainability_tree` (tesis→hipótesis→recomendaciones→señales→evidencias→datos originales).
- **DT14 — Strategy Lifecycle**: contempla todo el ciclo (generación→validación→ejecución→seguimiento→cierre→aprendizaje); consumible por Transaction.
- **DT15 — Strategic Thesis como ENTIDAD CANÓNICA**: la salida principal **no es un texto** sino una **entidad del sistema** persistida e independiente (no respuesta efímera de API). La narrativa es solo una **representación** de la entidad.
  - **Campos mínimos**: `thesis_id · thesis_type · status · company_master_id · opportunity_id(opc) · recommendation_ids · signal_ids · semantic_profile_version · financial_snapshot_version · strategy_version · created_at · updated_at · owner · lifecycle · confidence · evidence_tree · graph_edges`.
  - **Relaciones**: una Strategic Thesis puede **originarse** desde una empresa / oportunidad / recomendación, y **convertirse** posteriormente en `Opportunity · Mandate · Transaction` **sin reconstruir el razonamiento**.
  - **Persistencia**: vive como entidad independiente (colección `strategic_theses`). **El verdadero producto del motor es un conjunto de tesis estratégicas reutilizables por todo el ecosistema**, no estrategias efímeras.

### Entidad `Strategic Thesis` (colección `strategic_theses`, DT15)
```jsonc
{
  "thesis_id": "ths_<hash12>", "thesis_type": "strategic|consolidation|acquisition|divestment|partnership|capital_raising|growth|risk",
  "status": "available|insufficient_evidence",
  "company_master_id": "mc_…", "opportunity_id": null,
  "recommendation_ids": ["rec_…"], "signal_ids": ["sig_…"],
  "semantic_profile_version": "semantic-profile-v1", "financial_snapshot_version": "<master source_version>",
  "strategy_version": "strategy-intelligence-v1",
  "owner": "system|<user>", "created_at": "ISO", "updated_at": "ISO",
  "lifecycle": { "state":"proposed|validated|rejected|executing|completed|abandoned",
                 "result":null,"result_date":null,"learning":null,
                 "timeline":[{"state":"…","at":"ISO"}] },
  "confidence": { "value":0.0-1.0, "factors":{…} },
  "evidence_tree": { … },          // [DT13] explainability_tree materializado
  "graph_edges": [ {…} ],          // [DT8]
  "converts_to": null,             // Opportunity|Mandate|Transaction (DT15) — reutilizable sin recomputar
  "representation": { "statement":"…","rationale":[…],"narrative_method":"rules|ai" }   // narrativa = representación de la entidad
}
```

## Principio fundamental
El Strategy Intelligence Engine **razona estratégicamente** reutilizando toda la inteligencia disponible y deja un razonamiento **explicable, trazable y reutilizable**. Se comporta como un **Director de Corporate Development** apoyado por toda la infraestructura de inteligencia. No es un generador de estrategias ni un LLM que opina.
