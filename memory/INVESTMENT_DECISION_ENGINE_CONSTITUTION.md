# Investment Decision Engine — Constitución del Comité (v1.0)

> El modelo de decisión ES el activo. Este documento se escribe ANTES que el código.
> Define cómo razona el comité, cómo se pondera, cómo se resuelven las discrepancias y
> qué convierte una operación de «continuar» en «rechazar». El código de `investment_decision_engine/`
> es una implementación directa de este documento; si este documento es débil, ninguna
> implementación producirá recomendaciones consistentes.

Versión: `investment-decision-engine-v1` · Estado: DISEÑO (pendiente de aprobación de Daniel).

---

## 0. Principios rectores (no negociables)

1. **Boundary First — reutiliza, no recrees.** El motor NO recalcula finanzas, valoración,
   señales ni sector. Orquesta y razona sobre los Intelligence Engines existentes
   (Financial, Valuation/Valuo, Strategy, Signal, Semantic, Recommendation, Fragmentation/E7,
   Control&Synergy, Knowledge Graph, Economic/Sector) + Document Intelligence.
2. **Determinista siempre que sea posible.** Cada especialista puntúa con **reglas y pesos
   versionados** (config, no hardcode en la lógica), como el Recommendation Engine
   (`scoring.WEIGHTS`). Misma entrada ⇒ misma salida.
3. **La IA solo razona sobre evidencia (fact-lock).** El LLM NO decide el score ni inventa
   cifras: solo redacta la narrativa (executive summary, tesis, preguntas) a partir de la
   evidencia ya bloqueada, vía `model_provider.generate_summary(..., fact_lock=True)`.
4. **Todo trazable.** Cada afirmación lleva `{source, engine, data, confidence}`. Ninguna
   conclusión sin soporte. Si no hay dato ⇒ se declara `insufficient_data`, nunca se rellena.
5. **Funciona con información parcial.** La ausencia de una entrada baja la *cobertura* y la
   *confianza*, no rompe el motor. Un especialista sin datos emite `abstain`.
6. **Desacoplado y reutilizable.** El módulo no se acopla a ARROBA ni a su UI; recibe un
   `AnalysisRequest` y devuelve un objeto estructurado.

---

## 1. El comité (10 especialistas)

El usuario **nunca** ve a los especialistas; recibe una recomendación final explicable. Cada
especialista es un **scorer determinista** que consume ciertos motores y emite un objeto
`SpecialistOpinion` (nunca texto libre):

```
SpecialistOpinion = {
  specialist,                      # p.ej. "cfo"
  recommendation,                  # proceed | proceed_with_conditions | explore | pass | abstain
  score,                           # 0..1 (calidad de la oportunidad desde su óptica)
  confidence,                      # 0..1 (multifactor; cobertura/calidad/consistencia/recencia)
  weight_applied,                  # peso efectivo tras el perfil de comprador
  strengths[], weaknesses[], risks[], questions[],   # listas de {text, evidence[]}
  conditions[],                    # condiciones para proceder (si aplica)
  veto: bool,                      # solo Legal y Risk pueden vetar (ver §4)
  evidence[]                       # [{source, engine, data_point, value, confidence}]
}
```

Para cada especialista se define: **mandato**, **preguntas que responde**, **entradas
(motores)**, **criterios/umbrales** y **qué le hace decir proceed / conditions / pass**.

### 1.1 Investment Director (presidente)
- **Mandato:** visión global de la oportunidad y encaje con el mandato del comprador; sintetiza.
- **Entradas:** salida de todos los demás + `BuyerProfile` + Recommendation Engine (fit).
- **Criterios:** score global preliminar, dispersión del comité, número de vetos, cobertura.
- **Proceed** si score de consenso ≥ umbral del perfil y sin vetos; **conditions** si hay riesgos
  medios abordables; **pass** si tesis débil o dispersión alta sin catalizadores.

### 1.2 CFO (finanzas y calidad del beneficio)
- **Preguntas:** ¿es rentable y sostenible el beneficio? ¿apalancamiento? ¿generación de caja?
- **Entradas:** Financial Intelligence (`services/engines/financial`): márgenes, CAGR, Rule of 40,
  deuda neta/EBITDA, autonomía financiera (PN/activo), ciclo de caja, ratios.
- **Umbrales base:** margen EBITDA vs mediana sector; deuda neta/EBITDA `<3x` cómodo, `3–4x`
  condición, `>4x` red flag; solvencia `>40%` sano; calidad del beneficio (EBITDA reportado vs
  ajustado si hay bridge).
- **Proceed** con márgenes ≥ mediana y apalancamiento cómodo; **conditions** si el precio exige
  ajuste por deuda o si el beneficio requiere normalización (add-backs sin cuantificar).

### 1.3 Strategy Director (encaje estratégico)
- **Preguntas:** ¿encaja con la tesis del comprador? ¿crea plataforma? ¿sinergias estratégicas?
- **Entradas:** Strategy Engine, Recommendation Engine (strategic_fit), Semantic (propuesta de
  valor), Knowledge Graph (adyacencias), roll-up thesis (E6) si aplica.
- **Umbrales:** strategic_fit del Recommendation Engine; complementariedad de capacidades.
- **Proceed** con fit alto y racional claro; **pass** si la operación no mueve la aguja estratégica.

### 1.4 Market Intelligence Director (mercado y posición)
- **Preguntas:** ¿mercado atractivo y defendible? ¿posición competitiva? ¿consolidación?
- **Entradas:** Economic/Sector Intelligence, Fragmentation/E7 (HHI, actores, objetivos),
  benchmark sectorial, percentiles.
- **Umbrales:** crecimiento/tamaño sector; HHI (fragmentado = oportunidad buy&build);
  percentil de la compañía por ingresos y margen.
- **Proceed** en mercado con demanda estructural y hueco de consolidación; **conditions** si el
  mercado es maduro/plano pero la posición es sólida.

### 1.5 Valuation Director (precio y retorno)
- **Preguntas:** ¿el precio es razonable? ¿hay recorrido de retorno para el perfil?
- **Entradas:** Valuation/Valuo (Quality Score, múltiplo 4x+q/100·(8x−4x), escenarios EV/Equity),
  comparables (M&A Radar / market_multiples), reference multiples por sector.
- **Umbrales:** EV/EBITDA propuesto vs rango de referencia/observado; equity value vs capacidad
  del comprador; sensibilidad (bajo/medio/alto).
- **Proceed** si el precio está dentro/por debajo del rango justo; **conditions** con propuesta de
  ajuste de múltiplo o earn-out; **pass** si el precio implícito supera el rango alto sin justificación.

### 1.6 Commercial Director (clientes e ingresos)
- **Preguntas:** ¿ingresos recurrentes? ¿concentración de clientes? ¿pipeline?
- **Entradas:** Document Intelligence (infomemo/one-pager: clientes, recurrencia), KPIs, señales
  comerciales; si no hay dato ⇒ `abstain` con pregunta abierta.
- **Umbrales:** recurrencia; concentración top-5/top-10; churn (cuando exista).
- **Riesgo típico:** concentración comercial alta ⇒ weakness + question, no veto.

### 1.7 Operations Director (operativa y escalabilidad)
- **Preguntas:** ¿modelo escalable? ¿productividad? ¿dependencia de personas/procesos?
- **Entradas:** ingresos/empleado (Financial), estructura operativa (orgchart, plantilla),
  Semantic (capacidades), circulante.
- **Umbrales:** productividad vs sector; capacidad de escalar sin coste lineal.

### 1.8 HR Director (equipo y continuidad)
- **Preguntas:** ¿continuidad del equipo directivo? ¿relevo/sucesión? ¿retención de clave?
- **Entradas:** Signal Engine (succession_intelligence), officers/administradores, workforce.
- **Umbrales:** señal de sucesión (puede ser catalizador de venta y a la vez riesgo de continuidad).

### 1.9 Legal Director (legal, gobernanza, cumplimiento) — con veto
- **Preguntas:** ¿estructura de propiedad limpia? ¿contingencias? ¿cumplimiento?
- **Entradas:** ownership/cap table (norm_ownership), Control&Synergy, BORME (litigios/cargas),
  Document Intelligence (contratos/NDA), CNMV/BME si aplica.
- **Veto (§4):** contingencia legal grave o estructura de propiedad no verificable/ilícita.

### 1.10 Risk Director (riesgo agregado) — con veto
- **Preguntas:** ¿riesgo agregado aceptable? ¿concentraciones? ¿solvencia?
- **Entradas:** todas las señales de riesgo (Signal Engine severity=risk), finanzas, mercado,
  concentración comercial, apalancamiento.
- **Veto (§4):** riesgo existencial (insolvencia, fraude, dependencia crítica no mitigable).

---

## 2. Modelo de ponderación (config versionada)

Pesos **base** del comité (suman 1.0; recalibrables sin tocar la lógica, patrón `scoring.WEIGHTS`):

| Especialista | Peso base |
|---|---|
| CFO | 0.15 |
| Valuation | 0.15 |
| Strategy | 0.15 |
| Investment Director | 0.11 |
| Market | 0.11 |
| Commercial | 0.09 |
| Operations | 0.08 |
| HR | 0.05 |
| Legal | 0.055 |
| Risk | 0.055 |

> (Decisión Daniel 2026-07-31: Strategy sube a 0.15, al nivel de CFO y Valuation — las tres voces
> de mayor peso; se rebaja Investment Director 0.12→0.11 y Commercial 0.10→0.09 para mantener Σ=1.0.)

> Legal y Risk tienen peso moderado en el promedio PERO poder de **veto** (§4): su influencia
> real no es solo el peso, es la capacidad de bloquear.

### 2.1 Moduladores por perfil de comprador
Cada perfil reescala pesos y mueve umbrales (deltas sobre la base; se renormaliza a 1.0):

| Perfil | Sube el peso de | Baja el peso de | Efecto en umbral |
|---|---|---|---|
| **Estratégico** | Strategy, Commercial, Operations (sinergias) | Valuation | Tolera múltiplo mayor si hay sinergias |
| **Private Equity** | Valuation, CFO, Risk | Strategy | Exige retorno/IRR y apalancamiento sano |
| **Family Office** | CFO, Risk, HR (continuidad) | Strategy | Prioriza estabilidad y bajo riesgo |
| **Search Fund** | Operations, HR, CFO | Market | Foco en operabilidad por un individuo |
| **Holding** | Strategy, CFO | Commercial | Encaje de cartera a largo plazo |
| **Corporate Venture** | Strategy, Market | CFO, Valuation | Tolera menor rentabilidad por opción estratégica |

Los deltas concretos se definen en `scoring.py` como `BUYER_PROFILE_WEIGHTS[profile]` (config).

---

## 3. Modelo de confianza (multifactor)

Reutiliza el patrón `recommendation.scoring.confidence`. La confianza de cada especialista y del
consenso se compone de:

- **coverage** — % de entradas esperadas que están presentes.
- **data_quality** — calidad del dato subyacente (Data Quality / real vs inferido).
- **cross_engine_consistency** — coherencia entre motores (p.ej. valoración vs finanzas).
- **recency** — antigüedad del dato (ejercicio fiscal, señales).
- **committee_agreement** — 1 − dispersión de las opiniones (solo a nivel consenso).

`confidence = media(factores)`. La confianza NUNCA se infla: baja con datos parciales.

---

## 4. Resolución de discrepancias y vetos

1. **Promedio ponderado** de los `score` de especialistas que NO se abstienen (pesos del perfil).
2. **Dispersión** (desviación de las opiniones): alta dispersión ⇒ baja `committee_agreement` ⇒
   baja confianza y empuja la recomendación hacia `explore` (más due diligence) en vez de `proceed`.
3. **Vetos (solo Legal y Risk):**
   - `veto=True` de Legal o Risk ⇒ la recomendación global no puede ser mejor que `pass`
     (o `reject` si el veto es existencial), independientemente del score. El veto siempre
     viene con `evidence` y `conditions` (qué habría que resolver para levantarlo).
4. **Condiciones sobrescriben el verdict:** si el bloqueo es abordable (p.ej. ajuste de precio,
   verificación legal), la recomendación es `proceed_with_conditions` con la lista de condiciones,
   no `proceed`.

---

## 5. Consensus Engine — de opiniones a recomendación

Produce el objeto final (todos los campos que pide el brief):

- **investment_score** (0–100): `100 × Σ(peso_perfil · score_especialista)` sobre no-abstenidos.
- **confidence** (0–1): media de factores (§3), penalizada por dispersión y vetos.
- **recommendation** (bandas, ver §6).
- **executive_summary** — narrativa IA (fact-lock) sobre la evidencia.
- **investment_thesis** — por qué sí, apoyada en strengths con evidencia.
- **value_creation_opportunities** — de Strategy/Operations/Market (palancas 100d/3a/5a).
- **critical_risks** — unión de risks de peso alto + vetos.
- **open_questions** — preguntas de los especialistas que faltan por resolver.
- **conditions_to_proceed** — condiciones agregadas (precio, DD, legal…).
- **valuation_opinion** — del Valuation Director (rango + lectura).
- **negotiation_recommendations** — de Valuation + Investment Director (múltiplo, earn-out,
   reinversión, exclusividad).
- **final_verdict** — la banda + una frase.
- **committee** — el array de `SpecialistOpinion` (razonamiento individual trazable).
- **reasoning** — cómo se combinó todo (pesos aplicados, dispersión, vetos).

---

## 6. Bandas de recomendación (qué convierte «continuar» en «rechazar»)

| Banda | Score consenso | Condición adicional |
|---|---|---|
| **PROCEED** | ≥ 70 | Sin vetos · confianza ≥ 0.6 · dispersión baja |
| **PROCEED_WITH_CONDITIONS** | 55–85 | Riesgos medios abordables o veto **levantable** con condiciones |
| **EXPLORE** (más DD) | 45–70 | Confianza baja o dispersión alta o cobertura insuficiente |
| **PASS** | < 45 | Tesis débil, o veto no crítico no resuelto |
| **REJECT** | cualquiera | **Veto existencial** de Legal o Risk (insolvencia, fraude, ilegalidad) |

Reglas duras (independientes del score):
- Un **veto existencial** ⇒ `REJECT` siempre.
- Un **veto no existencial** ⇒ techo en `PROCEED_WITH_CONDITIONS`.
- **Confianza < 0.4** ⇒ nunca `PROCEED`; como mucho `EXPLORE` (no hay base suficiente).
- **Cobertura < umbral mínimo** (p.ej. sin finanzas ni valoración) ⇒ `EXPLORE` con
  `insufficient_data` explícito.

---

## 7. Explainability (contrato)

Cada conclusión (strength/weakness/risk/opinion/condición) referencia su evidencia:
`{source, engine (versión), data_point, value, confidence}`. El objeto final incluye
`reasoning` con: pesos efectivos por perfil, score por especialista, dispersión, vetos
aplicados y qué motores/fuentes se usaron y cuáles faltaron. **No existe conclusión sin soporte.**

---

## 8. Determinismo vs IA (frontera)

- **Determinista:** recolección de evidencia, scores por especialista, pesos, consenso,
  confianza, banda de recomendación, condiciones y vetos. → reproducible, testeable.
- **IA (narrativa, fact-lock):** redacción de `executive_summary`, `investment_thesis`,
  formulación de `open_questions` y `negotiation_recommendations` en prosa — SIEMPRE a partir de
  la evidencia y los scores ya calculados; nunca altera números ni la banda.

Esto garantiza que dos ejecuciones con los mismos datos den la **misma recomendación y score**,
variando como mucho la redacción.
