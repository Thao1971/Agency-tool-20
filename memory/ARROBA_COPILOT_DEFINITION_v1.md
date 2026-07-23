# ARROBA_COPILOT_DEFINITION_v1.md
**Definición de producto — Arroba Copilot**
_Versión: `arroba-copilot-definition-v1` · 2026-07-23 · Estado: **DEFINICIÓN APROBADA, IMPLEMENTACIÓN NO INICIADA**._

> Este documento responde a la pregunta "¿qué es el Copilot de arroba.com y qué le falta?" antes de construirlo, siguiendo el mismo principio que gobierna el resto de esta capa de inteligencia: definir con precisión sobre evidencia real antes de escribir código. Complementa (no sustituye) `ARROBA_INTEGRATION_PACK_v1.md` (§1.6 "Copilot First", §5.7, §5.9 — donde ya se decidió la arquitectura) y `TRANSACTION_INTELLIGENCE_ENGINE_CONTRACT.md` (donde ya existe una porción construida, el Transaction Copilot).

---

## 0. Dónde vive el Copilot (decisión ya congelada, no se reabre aquí)

`ARROBA_INTEGRATION_PACK_v1.md` ya estableció la frontera de responsabilidad de la plataforma:

| | Agency Tool (este repositorio) | arroba.com |
|---|---|---|
| Propiedad | Datos, inteligencia, algoritmos, Knowledge Graph, Transaction OS | Experiencia, navegación, entidades de producto, **Copilot** |
| Rol respecto al Copilot | Proveedor de intelligence vía contrato `X-API-Key` | Construye y opera el Copilot como orquestador |

**El Arroba Copilot se construye en arroba.com, no en Agency Tool.** Este repositorio no aloja lógica conversacional ni de orquestación de intención — solo expone los motores que el Copilot consumirá. Este documento define **qué tiene que consumir** y **qué le falta a la plataforma** para que ese Copilot cumpla la visión de Daniel; no es una spec de implementación del Copilot en sí (esa spec pertenece al repositorio de arroba.com).

**Principio ya definido en el Pack (§1.6, "Copilot First")**: el usuario nunca elige qué motor llamar. Habla con el Copilot, que interpreta la intención, decide qué motores invocar, agrega las respuestas y devuelve una única respuesta coherente.

---

## 1. Qué es Arroba Copilot

Un experto de mercado y M&A conversacional, con acceso a **toda** la inteligencia de Agency Tool (no solo a `transaction-intelligence`), capaz de:

1. **Analizar** una empresa a nivel financiero, sectorial, geográfico y societario.
2. **Valorar** (múltiplos, comparables, escenarios).
3. **Proponer** (targets, compradores, mandatos, tesis de roll-up).
4. **Predecir** (proyecciones, no solo diagnóstico del estado actual).
5. **Recordar y aprender** de la interacción (memoria conversacional + histórico de recomendaciones/decisiones).

Esta es la visión completa que Daniel articuló explícitamente ("que tenga memoria, que aprenda, que analice, que valore, que proponga, que pueda hacer incluso predicciones"). Las secciones siguientes contrastan cada capacidad contra lo que la plataforma ya soporta hoy.

---

## 2. Cobertura actual por capacidad

### 2.1 Analizar — ✅ cubierto por motores existentes

No requiere trabajo nuevo en Agency Tool. El Copilot puede orquestar hoy:
- **Financial Intelligence** (`financial-intelligence-v1`): KPIs, ratios, salud financiera, evolución.
- **Signal Intelligence** (`signal-intelligence-v1`): oportunidades, riesgos, señales de crecimiento/deterioro, por empresa/sector/territorio (§1-§13 de `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md`: Q1-Q5, T3).
- **Semantic Intelligence** (`semantic-intelligence-v1`): perfil semántico, similitud.
- **Geografía/concentración/paro/INE/tipos de interés/vehículos de inversión** (lo citado explícitamente por Daniel): cubierto por Sector Intelligence V2, `business_demography.py` (DIRCE), Macro/Economic Intelligence (INE/SEPE/Banco de España — ver `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md` §16), y el grafo de control (Q2/T3) para concentración de propiedad.

**Lo que falta no es un motor nuevo, sino el endpoint agregador que reduzca N llamadas a 1** — ver §5.

### 2.2 Valorar — ✅ cubierto, con gate anti-fabricación ya incorporado

`financial-intelligence-v1::valuation()` + Q6 (múltiplos reales, hoy acotados a agencias de publicidad — `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md` §6). El Copilot puede citar cuándo un múltiplo es real (`market_observed`) frente a inferido (`inferred_reference`) porque el motor ya distingue y expone esa procedencia.

### 2.3 Proponer — ✅ cubierto por motores existentes

- **Recommendation Intelligence**: comparables, buyers, sellers, matching, oportunidades.
- **Strategy Intelligence**: Strategic Thesis (tesis compuesta, escenarios, decisión justificada).
- **Buyer Mandate Intelligence** (E1): mandatos de comprador con matching bidireccional.
- **Roll-up Thesis** (E6): candidatos a plataforma + ranking de targets add-on.

### 2.4 Predecir — 🔴 gap real, requiere ingeniería nueva

Todos los motores actuales son **deterministas y basados en reglas** (umbrales resueltos por contexto, tendencias de trend flags: `worsening`/`improving`/`stable`), no forecasting probabilístico. No existe hoy ningún componente que proyecte una magnitud futura (ingresos, EBITDA, probabilidad de impago, probabilidad de operación) con un intervalo de confianza estadístico.

**Qué requeriría construirlo de verdad** (no estimado en detalle aquí, es una iniciativa nueva):
- Un motor de series temporales sobre el histórico financiero ya ingerido (`norm_financials`, multi-ejercicio) — el dato de entrada ya existe, el motor de predicción no.
- Framing explícito de **"escenario", no "garantía"** — la misma cautela legal que ya aplica al resto de la plataforma (Claude/Agency Tool no puede dar asesoramiento financiero personalizado sin más matización) se traslada directamente al Copilot: cualquier predicción debe presentarse con su incertidumbre y como apoyo a la decisión humana, nunca como una afirmación de hecho futuro.
- Reutilizar la misma disciplina de explicabilidad del resto del repo (`rule`/`evidence`/`confidence` en cada señal) — una predicción sin su metodología visible rompería el estándar ya establecido.

**Recomendación**: tratar "Predecir" como su propio motor futuro (`services/engines/forecast/`, contrato propio `forecast-intelligence-v1`), no como una extensión de Signal o Financial — mismo patrón de "nueva iniciativa con su propio contrato" que ya se ha aplicado en E1/E6/E7 de esta capa.

### 2.5 Memoria y aprendizaje — parcialmente cubierto, split de responsabilidad

| Tipo de memoria | Dónde vive | Estado |
|---|---|---|
| Memoria conversacional (qué se habló, contexto de la sesión del usuario) | **arroba.com** | No es responsabilidad de Agency Tool; es UX/producto de arroba. |
| Personalización por usuario (preferencias, watchlist, mandatos) | Ya en Agency Tool | `watchlist.py` (Q7), `buyer_mandates.py` (E1) — ya persistidos y consultables. |
| Memoria de recomendaciones ya dadas + feedback sobre si acertaron | Agency Tool | `recommendation_memory` + `recommendation_feedback` (Recommendation Intelligence, DR9/DR10) — **ya existe y es real**, seed data reutilizable por el Copilot. |
| Ciclo de vida de una tesis estratégica (aprobada, descartada, convertida en operación) | Agency Tool | `strategic_theses.lifecycle` (Strategy Intelligence) — **ya existe**. |
| "Aprender" en sentido de mejorar el modelo con el uso | Ninguno de los dos, hoy | No existe ningún mecanismo de reentrenamiento/ajuste automático de umbrales a partir de feedback — sería una iniciativa nueva, separada de "predecir". |

**Conclusión**: la memoria/aprendizaje NO es un vacío total — Agency Tool ya aporta primitivas reales (`recommendation_memory`, `recommendation_feedback`, `strategic_theses`) que el Copilot puede consumir como semilla, en vez de construir su propio almacén desde cero para ese propósito. Lo que sí es responsabilidad exclusiva de arroba.com es la memoria conversacional (qué dijo el usuario, en qué sesión) — eso no pertenece al contrato de Agency Tool.

---

## 3. Relación con el Transaction Copilot ya construido

El **Transaction Copilot** (`transaction-intelligence-v1`, DTX1-DTX13, `TRANSACTION_INTELLIGENCE_ENGINE_CONTRACT.md`) es una porción ya construida y en producción de esta visión más amplia, deliberadamente acotada al ciclo de una transacción activa: next-best-action, detección de bloqueos, riesgos, preparación de borradores, Universal Timeline, Workspace agregado. Principios que el Arroba Copilot general debe heredar de él, ya validados:

- **DTX4**: la IA puede redactar/resumir/explicar, pero **nunca** cambia estados, aprueba, firma o cierra — aprobación humana obligatoria para acciones de alto riesgo. Este mismo límite aplica a cualquier acción que el Copilot general proponga (contactar, añadir a watchlist son de bajo riesgo; iniciar una operación, no).
- **DTX7**: confianza multifactor (7 factores) en cada recomendación — el Copilot general debe exponer su confianza, no solo su conclusión.
- Explicabilidad obligatoria: ninguna sugerencia del Copilot es una caja negra — se apoya en `rule`/`evidence`/`explanation` de los motores subyacentes, ya presentes en el 100% de los datos que consumiría.

El Arroba Copilot general **no sustituye** al Transaction Copilot — lo engloba como una de sus capacidades (la fase "Ejecutar" del ciclo M&A), junto con Analizar/Valorar/Proponer (motores base) y, en el futuro, Predecir.

---

## 4. Capacidades objetivo (checklist de arranque para arroba.com)

| Capacidad | Motor(es) que la sostienen | Estado |
|---|---|---|
| Analizar empresa/sector/geografía | Financial + Signal + Semantic + Sector Intelligence + Macro/DIRCE | ✅ Disponible hoy |
| Valorar | Financial (`valuation`) + Q6 (múltiplos reales acotados a agencias) | ✅ Disponible hoy |
| Proponer targets/compradores/mandatos | Recommendation + Strategy + E1 (Buyer Mandate) + E6 (Roll-up) | ✅ Disponible hoy |
| Ejecutar (orquestar una operación) | Transaction Intelligence + Transaction OS | ✅ Disponible hoy (Transaction Copilot) |
| Predecir | — | 🔴 No existe; requiere nuevo motor `forecast-intelligence-v1` |
| Memoria conversacional | — | 🔴 Responsabilidad de arroba.com, no de este repo |
| Memoria de recomendaciones/feedback | Recommendation Memory (DR9/DR10) + Strategic Thesis lifecycle | 🟡 Existe como semilla, integración con el Copilot pendiente de diseño en arroba.com |
| Aprendizaje automático del sistema con el uso | — | 🔴 No existe en ningún lado; iniciativa nueva, separada de "predecir" |

---

## 5. Propuesta: endpoint agregador "Copilot Context" (no construido — propuesta de diseño)

**Problema que resuelve**: hoy, para que el Copilot responda "analiza esta empresa" tendría que hacer 3-5 llamadas separadas (Financial + Signal + Semantic +, según el caso, Sector/Geo/Ownership) y componer el resultado él mismo en arroba.com, repitiendo lógica de agregación en cada implementación de Copilot que se construya.

**Propuesta**: `POST /api/v1/copilot-context/company` (o bajo el prefijo que decida el contrato v3), auth `X-API-Key`, entrada `{identifier}` (CIF o `master_id`, igual que el resto del contrato v2). Consolidaría en una sola respuesta:
- Identidad (`company-intelligence-v2`).
- Resumen financiero (Financial Intelligence, ya resumido, no el objeto completo de `/analyze`).
- Señales activas relevantes (Signal Intelligence, top-N por impacto).
- Perfil semántico resumido (Semantic Intelligence).
- Posición sectorial/geográfica (Sector Intelligence + concentración de propiedad, Q2/T3).
- Recomendaciones activas si existen (Recommendation/Strategy, por referencia — no recalcula).

**Naturaleza del endpoint**: es una **composición de lecturas ya existentes**, no un motor nuevo con lógica propia — no recalcula nada que los motores base no calculen ya, solo reduce la cantidad de round-trips. Encajaría como una extensión aditiva del contrato `arroba.v2` (mismo patrón que `POST /api/v2/company-intelligence/identity`), nunca como sustituto de los endpoints individuales (que siguen siendo el contrato de bajo nivel para consumidores que no sean el Copilot).

**Estado**: propuesta de diseño, no implementada. Requiere decisión de Daniel/arroba.com sobre qué campos priorizar según el primer caso de uso real del Copilot (probablemente "resumen ejecutivo de una empresa" es el más frecuente, y por tanto el primer candidato a construir).

---

## 6. Próximos pasos recomendados

1. **No construir nada en Agency Tool todavía** para el Copilot en sí — la parte que falta aquí (Predecir, Copilot Context) son iniciativas que deben priorizarse explícitamente, no derivarse automáticamente de esta definición.
2. Si arroba.com empieza a construir el Copilot ahora mismo con lo que ya existe, puede cubrir Analizar/Valorar/Proponer/Ejecutar sin esperar a nada de este repositorio — solo integrando el contrato `arroba.v2` ya congelado.
3. Cuando se decida abordar "Predecir", abrir un contrato propio (`forecast-intelligence-v1`) siguiendo el mismo proceso de definición-antes-de-construir que el resto de esta capa (ver `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md` §0).
4. Si el volumen de llamadas del Copilot a los motores base resulta ineficiente en la práctica, retomar la propuesta de "Copilot Context" (§5) como extensión aditiva del contrato v2/v3.

**Documentos relacionados**: `ARROBA_INTEGRATION_PACK_v1.md` (arquitectura ya congelada del Copilot First), `ARROBA_INTEGRATION_CONTRACT_v1.md`, `TRANSACTION_INTELLIGENCE_ENGINE_CONTRACT.md` (Transaction Copilot ya construido), `RECOMMENDATION_INTELLIGENCE_ENGINE_CONTRACT.md` (DR9/DR10, memoria/feedback), `STRATEGY_INTELLIGENCE_ENGINE_CONTRACT.md` (`strategic_theses.lifecycle`), `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md`.
