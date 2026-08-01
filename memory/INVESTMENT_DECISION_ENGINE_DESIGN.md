# Investment Decision Engine — Diseño Técnico (v1.0)

Complementa a `INVESTMENT_DECISION_ENGINE_CONSTITUTION.md` (el modelo de decisión). Aquí se
especifican los 10 entregables técnicos. **No incluye UI, PDF ni React** (fuera de alcance v1).

Motor: `investment-decision-engine-v1`. Tipo: **CONSUMER engine** (como Recommendation): reutiliza
productores, no recrea inteligencia; auth por service-key; contrato propio y UI-agnóstico.

---

## 1. Arquitectura técnica

```
Fuentes → Data Layer → Intelligence Engines ─┐
                                             ├─► Investment Decision Engine ─► API ─► (Copilot/UI/PDF/Marketplace)
                       Document Intelligence ─┘        (Comité → Consenso)
```

Mapa de reutilización (Boundary First — NO recalcula):

| Especialista | Motores/fuentes que consume (solo lectura) |
|---|---|
| CFO | `services/engines/financial` (+ `docstudio/financial_enrich`) |
| Valuation | Valuo (`services/skills_valuation`, `category_valuations`, `market_multiples`) |
| Strategy | `services/engines/strategy`, `recommendation` (strategic_fit), KG |
| Market | `services/economic_intelligence`, `engines/investment/fragmentation` (E7), benchmark |
| Commercial | Document Intelligence (composer bundles), KPIs, señales comerciales |
| Operations | Financial (rev/empleado), Semantic (capacidades), workforce |
| HR | `engines/signal/succession_intelligence`, officers, workforce |
| Legal | `norm_ownership`/cap table, `master/control_synergy`, BORME, CNMV/BME |
| Risk | `engines/signal` (severity=risk), finanzas, mercado, concentración |
| Investment Dir. | agrega todos + `BuyerProfile` |

El motor **no** importa de UI ni de `docstudio` salvo lectura de bundles de datos; se diseña para
poder extraerse a un paquete propio (desacoplado de ARROBA).

---

## 2. Modelos de datos (`models.py` / `schemas.py`)

```python
# Entradas
BuyerProfile = {
  "type": "strategic|private_equity|family_office|search_fund|holding|corporate_venture",
  "mandate": {...},            # opcional: sector, tamaño, geografía, tesis
  "capacity_eur": float|None,  # capacidad de inversión (opcional)
}

AnalysisRequest = {
  "opportunity_id": str,
  "company_id"|"cif": str|None,       # para tirar de los engines reales
  "buyer_profile": BuyerProfile,
  "inputs": {                          # TODO opcional; funciona con parciales
     "information_memorandum": {...}|None, "investment_memo": {...}|None,
     "one_pager": {...}|None, "teaser": {...}|None,
     "financials": {...}|None, "valuation": {...}|None, "kpis": {...}|None,
     "comparables": {...}|None, "sector_intelligence": {...}|None,
     "signals": [...]|None, "knowledge_graph": {...}|None,
     "financial_history": [...]|None, "document_intelligence": {...}|None,
  }
}

# Evidencia (átomo de trazabilidad)
Evidence = {"source": str, "engine": str, "engine_version": str,
            "data_point": str, "value": Any, "confidence": float}

# Opinión de especialista (SIEMPRE estructurada)
SpecialistOpinion = {
  "specialist": str, "recommendation": "proceed|proceed_with_conditions|explore|pass|abstain",
  "score": float,            # 0..1
  "confidence": {"value": float, "factors": {...}},
  "weight_base": float, "weight_applied": float,
  "strengths": [{"text": str, "evidence": [Evidence]}],
  "weaknesses": [...], "risks": [...], "questions": [...],
  "conditions": [str], "veto": bool, "veto_kind": "none|blocking|existential",
  "evidence": [Evidence],
}

# Resultado del consenso
ConsensusResult = {
  "recommendation": "PROCEED|PROCEED_WITH_CONDITIONS|EXPLORE|PASS|REJECT",
  "investment_score": int,        # 0..100
  "confidence": float,            # 0..1
  "executive_summary": str,       # IA fact-lock
  "investment_thesis": str,
  "strengths": [...], "weaknesses": [...], "risks": [...], "opportunities": [...],
  "open_questions": [...], "conditions_to_proceed": [...],
  "valuation": {...}, "negotiation": [...],
  "committee": [SpecialistOpinion],
  "reasoning": {"weights_applied": {...}, "dispersion": float,
                "vetoes": [...], "engines_used": [...], "engines_missing": [...],
                "coverage": float},
  "meta": {"engine_version": "investment-decision-engine-v1",
           "buyer_profile": str, "generated_at": iso, "deterministic": true},
}

# ── Contratos de las capacidades contempladas en v1 (§11) ──
DecisionRecord   = {"decision_id": str, "opportunity_id": str, "buyer_profile": str,
                    "result": ConsensusResult, "evidence_versions": {...}, "created_at": iso}

ComparisonResult = {"buyer_profile": str, "ranking": [{"opportunity_id","investment_score",
                    "recommendation","confidence"}],
                    "matrix": {specialist: {opportunity_id: score}},   # comité × oportunidad
                    "dimension_matrix": {...}, "notes": [Evidence]}

PortfolioResult  = {"buyer_profile": str, "aggregate_score": int, "confidence": float,
                    "diversification": {"by_sector": {...}, "by_size": {...}, "by_risk": {...}},
                    "concentration_flags": [...], "cross_synergies": [Evidence],  # vía Knowledge Graph
                    "members": [{"opportunity_id","investment_score","recommendation"}]}

RecommendationList = {"buyer_profile": str, "items": [{"opportunity_id","fit_score",
                    "predicted_recommendation","confidence","rationale":[Evidence]}]}

CopilotAnswer    = {"decision_id": str, "question": str, "answer": str,          # IA fact-lock
                    "evidence": [Evidence], "confidence": float,
                    "unsupported": bool}    # true si la pregunta no puede responderse con la evidencia

ExportPayload    = {"decision_id": str, "format": "pdf|word",
                    "sections": [{"title","blocks":[...] }],   # estructura neutra render-ready
                    "committee": [...], "evidence_index": [Evidence]}   # lo consume un renderer externo
```

---

## 3. Esquema de puntuación (`scoring.py`)

Config versionada (recalibrable sin tocar lógica; patrón `recommendation/scoring.py`):

```python
SCORE_METHOD = "committee-weighted-v1"
COMMITTEE_WEIGHTS = { "cfo":0.15, "valuation":0.15, "strategy":0.15,
  "investment_director":0.11, "market":0.11, "commercial":0.09, "operations":0.08,
  "hr":0.05, "legal":0.055, "risk":0.055 }                     # Σ = 1.0
BUYER_PROFILE_WEIGHTS = { "private_equity": {"valuation":+0.05,"cfo":+0.03,"risk":+0.03,"strategy":-0.06,...}, ... }
RECOMMENDATION_BANDS = { "PROCEED":70, "PWC":55, "EXPLORE":45 }  # + reglas duras (veto/confianza)

def committee_score(opinions, weights):     # media ponderada de no-abstenidos → 0..1
def dispersion(opinions):                   # desviación de scores → 0..1
def apply_buyer_profile(weights, profile):  # deltas + renormaliza a 1.0
def confidence(factors): ...                # media multifactor (coverage/quality/consistency/recency/agreement)
def decide_band(score, confidence, dispersion, vetoes): -> banda   # implementa §6 de la Constitución
```

Cada especialista implementa `fit_dimension(value, evidence, sources)` internamente y devuelve un
`score` 0..1 derivado de sus propias sub-dimensiones con sub-pesos versionados.

---

## 4. Flujo del motor (`engine.py`)

```
analyze(request):
  1. resolve_evidence(request)         # tira de los engines reales por company_id/cif + inputs;
                                       #   marca engines_used / engines_missing / coverage
  2. run_committee(evidence, profile)  # cada especialista.evaluate(evidence, profile) → SpecialistOpinion
                                       #   (determinista; abstain si sin datos)
  3. weights = apply_buyer_profile(COMMITTEE_WEIGHTS, profile.type)
  4. score = committee_score(opinions, weights); disp = dispersion(opinions)
  5. vetoes = collect_vetoes(opinions)                 # solo legal/risk
  6. conf = confidence(coverage, data_quality, consistency, recency, 1-disp)
  7. band = decide_band(score, conf, disp, vetoes)     # reglas duras + bandas
  8. consensus = build_consensus(opinions, score, conf, band, vetoes)   # determinista
  9. consensus += ai_narrative(consensus, evidence)    # IA fact-lock: summary/thesis/questions/negotiation
 10. persist + return ConsensusResult
```

Idempotente: `decision_id = sha256(opportunity_id|profile|evidence_versions|score_method)`.

---

## 5. API REST (`api.py`)

Prefijo `/api/v1/investment-decision`, auth `require_service_key` (patrón Recommendation).

**Núcleo:**
- `POST /analyze` → body `AnalysisRequest` → `ConsensusResult`.
- `POST /committee` → solo el array `committee` (opiniones) sin narrativa IA (rápido/determinista).
- `GET  /decision/{decision_id}` → recupera un análisis persistido.
- `GET  /health` → versión del motor y de las evidencias.

**Capacidades contempladas en v1 (ver §11) — endpoints y contratos definidos desde el inicio:**
- `POST /compare` → `{opportunity_ids[], buyer_profile}` → `ComparisonResult` (matriz por especialista/dimensión + ranking). **Lógica de motor, en v1.**
- `POST /portfolio` → `{decision_ids[]|opportunity_ids[], buyer_profile}` → `PortfolioResult` (score agregado, diversificación por sector/tamaño/riesgo, solapes/sinergias vía KG). **Lógica de motor, en v1.**
- `POST /recommendations` → `{buyer_profile, universe?}` → `RecommendationList` (oportunidades rankeadas para ese mandato; reutiliza Recommendation Engine + decision score). **Lógica de motor, en v1.**
- `POST /decision/{id}/ask` → `{question}` → `CopilotAnswer` (Q&A **fact-lock** sobre la evidencia YA almacenada de esa decisión; la conversación/UI es externa, la respuesta fundamentada la da el motor). **En v1.**
- `GET  /decision/{id}/export-payload?format=pdf|word` → `ExportPayload` (estructura *render-ready*: secciones, tablas, evidencia). **El contrato se define en v1; el render a PDF/Word lo hace un renderer aparte, NO en este módulo** (respeta «No implementar PDF»).

Respuesta de error honesta: `{status:"insufficient_data", coverage, engines_missing}` en vez de inventar.

---

## 6. Estructura de código

```
services/engines/investment_decision/
  __init__.py
  engine.py            # orquestador analyze() (§4)
  models.py            # dataclasses/TypedDict de §2
  schemas.py           # Pydantic (request/response) para la API
  scoring.py           # pesos, bandas, consenso, confianza (§3)
  prompts.py           # plantillas IA fact-lock (narrativa)
  consensus.py         # build_consensus + resolución de discrepancias/vetos
  evidence.py          # resolve_evidence: adaptadores de lectura a los motores existentes
  store.py             # persistencia de DecisionRecord (idempotente por decision_id)
  capabilities/        # capacidades contempladas en v1 (§11), sobre el núcleo
    __init__.py
    compare.py         # ComparisonResult (matriz comité×oportunidad + ranking)
    portfolio.py       # PortfolioResult (agregado + diversificación + sinergias KG)
    recommend.py       # RecommendationList (oportunidades rankeadas por mandato)
    copilot.py         # CopilotAnswer (Q&A fact-lock sobre una decisión almacenada)
    export.py          # ExportPayload (estructura render-ready; NO renderiza PDF/Word)
  committee/
    __init__.py  base.py           # Specialist ABC: evaluate(evidence, profile)->SpecialistOpinion
    investment_director.py  cfo.py  strategy.py  market.py  valuation.py
    commercial.py  operations.py  legal.py  hr.py  risk.py
  tests/               # (ver §7)
  README.md
routes/investment_decision.py   # API FastAPI (thin; delega en engine)
```

(Se ubica en `services/engines/` junto al resto; el brief lo llama `investment_decision_engine/` —
mismo contenido, alineado a la convención real del repo.)

---

## 7. Tests (`tests/`)

- **Determinismo:** misma request ⇒ mismo `investment_score`, banda y `decision_id` (N corridas).
- **Entrada parcial:** sin finanzas / sin valoración / solo teaser ⇒ no rompe; baja cobertura/confianza;
  banda ≤ EXPLORE cuando cobertura < mínimo.
- **Veto existencial** (Risk) ⇒ `REJECT` aunque el score sea alto.
- **Veto levantable** (Legal) ⇒ techo `PROCEED_WITH_CONDITIONS` + condiciones presentes.
- **Modulación por perfil:** misma empresa como PE vs estratégico ⇒ pesos y banda cambian de forma
  coherente (PE penaliza precio alto; estratégico lo tolera con sinergias).
- **Explainability:** toda strength/risk/opinion lleva `evidence` no vacía; ninguna conclusión sin soporte.
- **Abstención:** especialista sin datos ⇒ `abstain`, no arrastra el score.
- **Golden snapshot** por empresa de la muestra (Servier) para detectar regresiones.

---

## 8. Documentación técnica

- `README.md` del módulo: propósito, contrato, cómo añadir un especialista, cómo recalibrar pesos.
- Este documento + la Constitución = contrato del motor (junto al resto de `*_ENGINE_CONTRACT.md`).
- `INTELLIGENCE_API_REFERENCE.md`: añadir la sección `/investment-decision`.

---

## 9. ADR (decisiones de arquitectura)

- **ADR-1 · Consumer engine (reutiliza, no recrea).** Alternativa: recalcular. Elegido reutilizar
  (coherencia, single source of truth, menos deuda). Consecuencia: depende de las versiones de los
  productores (se registran en `evidence.engine_version`).
- **ADR-2 · Determinista + IA solo narrativa (fact-lock).** Alternativa: LLM decide el score.
  Rechazada (no trazable, no reproducible, riesgo de invención). Consecuencia: scores testeables;
  IA aislada tras la evidencia.
- **ADR-3 · Comité de especialistas deterministas con pesos versionados.** Alternativa: un único
  scorer monolítico. Elegido comité (explicable, extensible, recalibrable por perfil).
- **ADR-4 · Vetos Legal/Risk sobre el promedio ponderado.** Alternativa: solo media ponderada.
  Rechazada (una media alta no debe tapar un riesgo existencial).
- **ADR-5 · Config de pesos/bandas versionada y separada de la lógica** (patrón Recommendation).
  Permite recalibrar sin tocar código de decisión.
- **ADR-6 · Módulo desacoplado de ARROBA/UI**, contrato por objetos ⇒ reutilizable y exportable.
- **ADR-7 · Idempotencia por `decision_id`** (hash de entradas+versiones) ⇒ cacheable y auditable.
- **ADR-8 · Capacidades de nivel superior nativas del motor, con la frontera UI/PDF intacta.**
  Comparación, cartera y recomendaciones automáticas son **lógica de motor** (operan sobre
  `ConsensusResult`/`DecisionRecord`) ⇒ se diseñan e implementan en v1. El **Copilot** se soporta con
  un endpoint de Q&A *fact-lock* sobre la decisión almacenada (la conversación/render vive fuera).
  El **export PDF/Word** se contempla como un **contrato `ExportPayload` render-ready** que produce el
  motor; el renderer real (PDF/Word) es un componente aparte y NO forma parte de este módulo (respeta
  «No implementar PDF»). Consecuencia: nada de UI/PDF aquí, pero todo queda **habilitado sin refactor**.

---

## 10. Plan de implementación por fases

- **Fase 0 — Constitución (HECHO):** modelo de decisión aprobado (este + Constitución).
- **Fase 1 — Esqueleto:** módulo, `models.py`, `schemas.py`, `Specialist` ABC, `evidence.resolve` con
  adaptadores de lectura (stubs) + `/health`. Tests de contrato.
- **Fase 2 — Especialistas deterministas:** CFO, Valuation, Market, Strategy, Risk primero (mayor
  peso/impacto), reutilizando los motores reales; luego Commercial, Operations, HR, Legal, Investment Dir.
- **Fase 3 — Consenso + vetos + bandas:** `consensus.py`, `scoring.decide_band`, dispersión.
- **Fase 4 — Confianza + explainability:** multifactor + `reasoning` completo + cobertura.
- **Fase 5 — API REST:** `/analyze`, `/committee`, `/decision/{id}`, persistencia + idempotencia.
- **Fase 6 — Capa IA narrativa (fact-lock):** summary/thesis/questions/negotiation.
- **Fase 7 — Perfiles de comprador:** `BUYER_PROFILE_WEIGHTS` + tests de modulación.
- **Fase 8 — Capacidades v1 (§11):** `capabilities/` → compare · portfolio · recommend · copilot (Q&A)
  · export-payload, con sus endpoints y tests.
- **Fase 9 — Hardening:** golden snapshots, smoke con datos reales (muestra), auditoría de trazabilidad.
- **Fuera de v1 (otros componentes, no este módulo):** el **renderer** que convierte `ExportPayload`
  en PDF/Word, la **UI conversacional** del Copilot y cualquier **componente React**.

---

## 11. Capacidades contempladas en v1 (diseñadas desde el inicio)

Todas se apoyan en el núcleo (`ConsensusResult` + `DecisionRecord` persistido) sin tocarlo:

1. **Comparación de oportunidades** (`capabilities/compare.py`, `POST /compare`).
   Ejecuta/recupera el análisis de N oportunidades con el mismo `buyer_profile` y produce un
   `ComparisonResult`: ranking por `investment_score`, matriz comité×oportunidad y por dimensión, y
   notas con evidencia. 100 % determinista.

2. **Análisis de cartera** (`capabilities/portfolio.py`, `POST /portfolio`).
   Agrega varias decisiones: score de cartera, **diversificación** por sector/tamaño/riesgo,
   flags de concentración y **sinergias/solapes** entre participadas vía Knowledge Graph.

3. **Recomendaciones automáticas** (`capabilities/recommend.py`, `POST /recommendations`).
   Dado un `buyer_profile` (y un universo opcional), rankea oportunidades combinando el
   Recommendation Engine (fit) con una predicción de `investment_score`. Proactivo, explicable.

4. **Conversación con Copilot** (`capabilities/copilot.py`, `POST /decision/{id}/ask`).
   Q&A **fact-lock** sobre la evidencia YA almacenada de una decisión: responde solo con lo soportado
   por `evidence`; si la pregunta excede la evidencia ⇒ `unsupported:true` (no inventa). La UI de chat
   y el hilo conversacional viven fuera del motor; el motor da la **respuesta fundamentada**.

5. **Export PDF/Word** (`capabilities/export.py`, `GET /decision/{id}/export-payload`).
   Devuelve un `ExportPayload` **render-ready** (secciones/tablas/índice de evidencia) que un renderer
   externo (p. ej. el pipeline de `docstudio`/pptx-pdf o un renderer Word) convierte a documento. El
   motor **no** genera el binario ⇒ se respeta la restricción, pero el export queda **contemplado y
   habilitado** por contrato desde v1.

> Frontera clara: **comparación, cartera y recomendaciones = lógica de motor (implementadas en v1)**;
> **Copilot Q&A = endpoint de motor en v1** (UI fuera); **export = contrato en v1, render fuera**.

---

### Verificación de alcance (restricciones del brief)
NO UI · NO PDF · NO React · NO modificar otros Intelligence Engines · módulo desacoplado y reutilizable.
Se respeta: el motor solo **lee** de los productores, y de las 5 capacidades solo quedan fuera el
render binario (PDF/Word) y la UI conversacional; todo lo demás es contrato/lógica del propio motor.
