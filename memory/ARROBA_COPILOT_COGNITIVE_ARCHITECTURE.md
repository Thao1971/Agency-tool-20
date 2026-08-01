# ARROBA — Arquitectura Cognitiva del Copilot y Comité de Inversión (CANON v1.0)

> **CANÓNICO.** A partir de aquí, toda pantalla, flujo y propuesta de UX respeta esta arquitectura.
> **Nunca** se simplifica ni se sustituye por un único agente de IA.
>
> Documentos hermanos:
> - `ARROBA_COPILOT_INTERACTION_SYSTEM.md` (CIM) → *cuándo* habla/calla/manda el Copilot (estados A–F, screen owner).
> - `INVESTMENT_DECISION_ENGINE_CONSTITUTION.md` + `..._DESIGN.md` → el **Comité** ya implementado (10 especialistas → consenso).
> Este documento define la **pila cognitiva** (quién razona y en qué orden). Los tres juntos son el canon del Copilot.

---

## Principio fundamental

El usuario **nunca** interactúa con múltiples agentes. Solo conoce **una entidad: ARROBA Copilot**,
con una única personalidad, un único tono, una única conversación y una única memoria.

Nunca aparecen varios copilots ni nombres como *Buyer Copilot*, *Seller Copilot*, *Investment Copilot*,
*Valuation Copilot*… **Todos son internos.** Muchos especialistas, **una sola voz**.

---

## Arquitectura (pila)

```
Usuario
  ↓
ARROBA Copilot   (voz única — la única IA visible)
  ↓
Orquestador      (invisible — enruta y combina)
  ↓
Especialistas    (dominios — no hablan con el usuario)
  ↓
Comités          (órganos colegiados — deliberan)
  ↓
Intelligence Engines (producen hechos, no decisiones)
  ↓
Data Layer
  ↓
Fuentes
```

---

## 1. ARROBA Copilot — la única IA visible
Explica · recomienda · conversa · pide autorización · resume. **Nunca calcula, nunca analiza
directamente, nunca decide por sí mismo.** Siempre representa el **consenso del sistema**.
(Su comportamiento —cuándo aparece/manda— lo rige el CIM: estados A–F.)

## 2. Orquestador — invisible
Decide qué especialistas consultar, qué comité convocar, cómo combinar respuestas y cómo resolver
discrepancias. **Nunca aparece en la interfaz.** Es el router entre la voz y los especialistas/comités.

## 3. Especialistas — por dominio, no hablan con el usuario
Cada uno interpreta **solo** su dominio: consulta sus Intelligence Engines, genera una opinión, aporta
**evidencias** y **condiciones**, puede formular **preguntas** y **emitir veto** si corresponde.
Actuales (10): **Director de Inversiones · CFO · Valoración · Estrategia · Mercado · Comercial ·
Operaciones · Riesgos · RRHH · Legal.** Se pueden añadir nuevos **sin cambiar la experiencia**.
> Implementados en `services/engines/investment_decision/committee/` (deterministas, con evidencia y vetos Legal/Risk).

## 4. Comité de Inversión — órgano colegiado (no es un agente)
**Delibera** con las opiniones de todos los especialistas. No consulta fuentes, no ejecuta motores, no
calcula: **escucha a los especialistas** y produce el **consenso**:
recomendación · puntuación · confianza · resumen ejecutivo · tesis · fortalezas · debilidades · riesgos
· oportunidades · preguntas abiertas · condiciones para avanzar.
> Implementado en `investment_decision/consensus.py` + `engine.py`. Podrá haber otros comités en el futuro
> (mismo patrón), siempre bajo una sola voz.

## 5. Intelligence Engines — producen hechos, nunca decisiones
Financial · Valuation · Strategy · Signals · Matching · Knowledge Graph · Sector · Recommendation…
Solo generan **datos verificables**. La decisión emerge del Comité, no del motor.

---

## Flujo de razonamiento

```
Usuario pregunta
  ↓ El Orquestador identifica qué especialistas necesita
  ↓ Cada especialista consulta sus motores
  ↓ Cada especialista genera una opinión (con evidencia)
  ↓ El Comité delibera → consenso
  ↓ ARROBA Copilot traduce la deliberación al usuario (una sola voz)
```

---

## Regla de UX

El usuario **nunca ve**: Intelligence Engines · Orquestador · JSON internos · llamadas entre
especialistas. Solo ve **ARROBA Copilot** y, cuando es relevante, **el resultado del Comité**.

---

## Visualización del Comité (componente premium)

El Comité es un **componente premium**, nunca una conversación entre agentes: se representa como un
**informe ejecutivo**.

```
────────────────────────
 COMITÉ DE INVERSIÓN
 Recomendación:  PROCEDER      72/100
 Confianza:      Alta
────────────────────────
 Han participado:
 ✓ Director de Inversiones   ✓ CFO           ✓ Estrategia
 ✓ Valoración                ✓ Mercado       ✓ Comercial
 ✓ Operaciones               ✓ Riesgos       ✓ RRHH        ✓ Legal
────────────────────────
 [ Ver deliberación ]
```

Al pulsar **"Ver deliberación"** NO aparece un chat: se muestra una **deliberación estructurada**, una
intervención por especialista. Cada intervención muestra: **conclusión · evidencias · nivel de
confianza · condiciones · preguntas abiertas.** Nunca opiniones inventadas; todo soportado por datos.

> El backend ya sirve esta vista sin trabajo extra: `POST /analyze` devuelve el `committee[]`
> (opinión + evidencia + confianza + condiciones por especialista) y
> `GET /decision/{id}/export-payload` da la estructura render-ready. El frontend solo maqueta; no
> inventa contenido.

---

## Principio de transparencia
El Comité **no pretende impresionar, pretende explicar.** La interfaz debe transmitir que la
recomendación es fruto de una **deliberación entre especialistas basada en datos trazables**. El
usuario debe sentir que **asiste a una reunión real de un comité de inversión**, no que lee un chatbot.

## Principio final
**ARROBA no vende una IA. ARROBA vende un Comité de Inversión Permanente** capaz de analizar miles de
oportunidades de forma continua con especialistas virtuales y **una única voz conversacional: ARROBA
Copilot.** Todas las pantallas futuras respetan esta arquitectura.

---

## Estado de implementación (2026-07-31)
- **Ya existe (código):** Especialistas (10) + Comité + Consenso + capacidades (compare/portfolio/
  recommend/copilot Q&A/export) = `investment_decision` engine; y la voz/estados = CIM (documento).
- **Falta nombrar/implementar como componente propio:** el **Orquestador** explícito (router
  multi‑especialista/multi‑comité que hoy vive implícito dentro del engine) y la **UI del Comité**
  ("Ver deliberación") en el frontend — fuera del alcance del backend, se maqueta desde el
  `committee[]`/`export-payload`.
