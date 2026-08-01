# ARROBA — Orquestador del Copilot (CANON v1.0)

> El **Orquestador** es la pieza invisible entre la voz (ARROBA Copilot) y los especialistas/comités.
> Decide **a quién consultar**, **qué comité convocar** (o ninguno), **cómo combinar** las respuestas y
> **cómo resolver discrepancias** — y siempre devuelve **una sola voz**. Complementa a
> `ARROBA_COPILOT_COGNITIVE_ARCHITECTURE.md` (la pila) y al `ARROBA_COPILOT_INTERACTION_SYSTEM.md`
> (los estados A–F). Nunca es visible para el usuario.

Estado: CANON · `copilot-orchestrator-v1` · sin código todavía (spec; encaje futuro en `services/copilot/orchestrator.py`).

---

## 1. Responsabilidad (qué hace y qué no)

**Hace:** clasificar la intención → enrutar a los especialistas/motores mínimos necesarios → (si procede)
convocar un comité → fusionar en una respuesta única → entregarla a la voz con el estado CIM correcto.

**No hace:** hablar con el usuario (eso es la voz), calcular (eso son los motores), decidir por su cuenta
(la decisión emerge del comité), ni aparecer en la interfaz.

Regla de oro del Orquestador: **usar el mínimo aparato necesario.** No todo convoca al comité entero.

---

## 2. Niveles de enrutado (del más ligero al más pesado)

| Nivel | Cuándo | A quién activa | Estado CIM |
|---|---|---|---|
| **L0 · Hecho** | Pregunta factual ("¿qué EBITDA tiene?") | 1 motor (lectura directa) | D (responde) / B |
| **L1 · Especialista** | Pregunta de un dominio ("¿está bien valorada?") | 1 especialista + sus motores | D / C |
| **L2 · Panel** | Cruza 2–3 dominios ("¿riesgos financieros y legales?") | subconjunto de especialistas | C |
| **L3 · Comité** | Decisión de inversión ("¿compramos?") | **Comité completo** (Investment Decision) | C→E |
| **L4 · Capacidad** | Comparar / cartera / recomendar universo | capability (compare/portfolio/recommend) | C |

El Orquestador **escala** de nivel solo si la intención lo exige. Un L3 (comité) reutiliza el
`investment_decision.analyze`; un L0/L1 **no** debe convocar al comité (coste y ruido innecesarios).

---

## 3. Mapa intención/pantalla → activación (starter)

| Intención / pantalla | Nivel | Especialistas/Comité | Motores |
|---|---|---|---|
| Ficha de empresa (leer) | L0/L1 | — / Valoración o CFO puntual | Financial, Valuation, Signal |
| "¿Cuánto vale?" | L1 | Valoración | Valuo, comparables, market_multiples |
| "¿Qué riesgos tiene?" | L2 | Riesgos (+Legal si aplica) | Signal, Financial, ownership |
| "¿Encaja con mi estrategia?" | L1/L2 | Estrategia (+Mercado) | Strategy, Recommendation, KG |
| "¿Debería comprarla?" | **L3** | **Comité completo** | Investment Decision (todos) |
| Comparar A vs B | L4 | capability.compare | Investment Decision ×N |
| Mi cartera / watchlist | L4 | capability.portfolio | Investment Decision + Signal |
| "Recomiéndame objetivos" | L4 | capability.recommend | Recommendation + Investment Decision |
| Autorizar acercamiento | L3→E | Comité (contexto) + Matching | Matching, Investment Decision |

---

## 4. Contrato (interno, invisible)

```
OrchestrationRequest = { user_intent | screen + event, entity_ref?, buyer_profile?, context }
        ↓ classify(intent) → level (L0..L4) + specialists[] / committee? / capability?
        ↓ fan-out: cada especialista/motor devuelve su objeto estructurado (con evidencia)
        ↓ merge(): combina; si hay comité → consenso del Investment Decision Engine
        ↓ resolve_discrepancies(): §5
OrchestrationResult = { answer_payload (para la voz), cim_state (A–F), sources[], committee? }
```

La voz (Copilot) recibe `OrchestrationResult` y lo redacta en una sola personalidad (fact-lock).
El usuario nunca ve el `OrchestrationResult` crudo.

---

## 5. Resolución de discrepancias (una sola voz, sin contradicciones)

1. **Dentro de un comité:** ya resuelto por el Consensus Engine (media ponderada + dispersión + vetos
   Legal/Risk). El Orquestador no re‑delibera; usa el consenso.
2. **Entre especialistas sueltos (L2):** si dos dominios chocan, el Orquestador **no elige un ganador
   arbitrario**: presenta ambos como matices de una sola respuesta ("sólido en X, pero atención a Y")
   y baja la confianza. Si el choque afecta a una decisión, **escala a L3** (comité).
3. **Veto presente:** cualquier veto (Legal/Risk) domina el mensaje final (no se puede "tapar" con una
   media alta).
4. **Datos insuficientes:** se declara explícitamente (cobertura baja) en vez de inventar.

---

## 6. Garantías (invariantes)

- **Voz única:** el resultado siempre se entrega como ARROBA Copilot; jamás se exponen nombres de
  especialistas como interlocutores.
- **Mínimo aparato:** no convocar comité para preguntas de nivel L0/L1.
- **Estado correcto:** el Orquestador propone el `cim_state`; la aparición/control la valida el CIM
  (p. ej. una acción con efecto externo → E antes de F).
- **Trazabilidad:** todo `answer_payload` arrastra `sources[]`; nada sin soporte.
- **Determinismo del núcleo:** el enrutado y los scores son deterministas; solo la redacción varía (IA).

---

## 7. Encaje con lo ya construido / pendiente

- **Ya existe:** los especialistas, el comité y el consenso (`investment_decision` engine) y las
  capacidades (compare/portfolio/recommend) → cubren L3 y L4. El Copilot Q&A (`/decision/{id}/ask`)
  es un L1/L2 sobre una decisión almacenada.
- **Pendiente (este spec):** el **clasificador de intención** y el **router L0–L4** como componente
  propio (`services/copilot/orchestrator.py`), más los adaptadores L0/L1/L2 (responder hechos o
  consultar 1–3 especialistas sin convocar al comité entero). Es una capa fina sobre los motores; no
  recrea inteligencia.
