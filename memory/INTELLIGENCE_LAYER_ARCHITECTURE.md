# INTELLIGENCE_LAYER_ARCHITECTURE.md
**Arquitectura oficial de la Intelligence Layer — Agency Tool**
_Versión: `intelligence-layer-v1` · 2026-06-26 · Estado: ESTABLE (documento de arquitectura; no modifica motores ni contratos publicados)._

> Este documento define **cómo cooperan los motores** del Agency Tool durante los próximos años. Convierte un conjunto de motores independientes en una **plataforma coherente de inteligencia** que evoluciona sin perder consistencia. No introduce código ni cambia contratos congelados (`master-v1`, `financial-intelligence-v1`, `signal-intelligence-v1`).

---

## 1. Filosofía

### Qué es la Intelligence Layer
La capa que se sitúa **encima del Master Layer** y **debajo de los consumidores**. Agrupa todos los motores de inteligencia y define las **reglas de colaboración** entre ellos. No es un servicio único: es un **conjunto de motores con contratos estables** que cooperan de forma explícita.

```
Fuentes → Raw → Normalized → MASTER LAYER (única fuente de verdad)
                                   │
   ╔══════════════════ INTELLIGENCE LAYER ══════════════════╗
   ║  PRODUCTORES (enriquecen conocimiento del Master):       ║
   ║    Financial · Signal · Semantic                         ║
   ║  ─────────────────────────────────────────────────────  ║
   ║  CONSUMIDORES (reutilizan conocimiento, no lo recrean):  ║
   ║    Recommendation · Strategy · Transaction               ║
   ╚══════════════════════════════════════════════════════════╝
                                   │
        CONSUMIDORES: arroba.com · Arroba Copilot · APIs · futuros productos
```

### Qué problemas resuelve
- **Dependencias implícitas**: hoy un motor podría leer datos de otro de forma arbitraria. La capa lo prohíbe: todo intercambio pasa por contratos.
- **Reconstrucción de inteligencia**: evita que motores superiores recalculen lo que un productor ya generó (duplicación, incoherencia, coste).
- **Erosión de la frontera**: garantiza que ningún motor lea fuentes originales ni el Normalized Layer.
- **Evolución descontrolada**: da gobernanza para añadir/retirar motores y versionar contratos sin romper consumidores.

### Principios (resumen; detalle en §7)
Explainability First · Boundary First · Contract First · Master Layer como única verdad · ningún motor toca fuentes originales · todo motor reutilizable por cualquier consumidor.

---

## 2. Catálogo de motores

> Cada motor publica su contrato propio (documento `*_CONTRACT.md`). Aquí se describe su rol dentro de la capa. **Estado**: ✅ construido · 🔵 planificado.

### 2.1 Financial Intelligence Engine ✅ (`financial-intelligence-v1`) — PRODUCTOR
- **Propósito**: producir la verdad financiera de cada empresa.
- **Responsabilidades**: estados, KPIs, ratios, evolución, calidad financiera, comparables financieros, valoración, explicabilidad.
- **Entradas**: Master Layer (`master-v1`, resumen canónico) + Normalized (`norm_financials`, interno). *No consume otros motores.*
- **Salidas**: perfil financiero completo (determinista, sin IA).
- **Contratos publicados**: `FINANCIAL_INTELLIGENCE_ENGINE_CONTRACT.md` · API `/api/v1/financial-intelligence/*`.
- **Contratos consumidos**: `master-v1`.

### 2.2 Signal Intelligence Engine ✅ (`signal-intelligence-v1`) — PRODUCTOR
- **Propósito**: detectar oportunidades, riesgos y cambios relevantes (inteligencia proactiva).
- **Responsabilidades**: taxonomía canónica de señales (9 categorías), dimensiones (impact/confidence/urgency/persistence), señales compuestas, persistencia/histórico.
- **Entradas**: Master Layer + **Financial Engine** (señales financieras) + Knowledge Graph estructural (ownership).
- **Salidas**: señales explicables, versionadas, persistidas.
- **Contratos publicados**: `SIGNAL_INTELLIGENCE_ENGINE_CONTRACT.md` · API `/api/v1/signal-intelligence/*`.
- **Contratos consumidos**: `master-v1`, `financial-intelligence-v1`, `knowledge-graph-v1`.

### 2.3 Semantic Intelligence Engine 🔵 (`semantic-intelligence-v1`) — PRODUCTOR
- **Propósito**: representación semántica de cada empresa y similitud.
- **Responsabilidades**: Company Semantic Profile canónico, embeddings versionados (solo desde el Master consolidado), búsqueda/ similitud (Atlas Vector Search), Universal Search.
- **Entradas**: Master Layer (CRÍTICO: embeddings SOLO sobre Master) + opcionalmente Financial/Signal para enriquecer el profile.
- **Salidas**: profile semántico + embedding + servicio de similitud.
- **Contratos publicados (planificado)**: `SEMANTIC_INTELLIGENCE_ENGINE_CONTRACT.md` · API `/api/v1/semantic-intelligence/*`.
- **Contratos consumidos**: `master-v1` (+ opc. `financial-intelligence-v1`, `signal-intelligence-v1`).

### 2.4 Recommendation Intelligence Engine 🔵 (`recommendation-intelligence-v1`) — CONSUMIDOR
- **Propósito**: comparables inteligentes y matching (buyer↔seller, advisor↔client, investor↔target).
- **Responsabilidades**: scoring de afinidad explicable; **reutiliza** similitud (Semantic), fundamentos (Financial) y prioridad (Signal). No recrea inteligencia.
- **Entradas**: Semantic + Financial + Signal + KG ownership.
- **Salidas**: recomendaciones/matches con explicación y trazabilidad a los motores origen.
- **Contratos publicados (planificado)**: `RECOMMENDATION_INTELLIGENCE_ENGINE_CONTRACT.md`.
- **Contratos consumidos**: `semantic-*`, `financial-*`, `signal-*`, `knowledge-graph-*`.

### 2.5 Strategy Intelligence Engine 🔵 (`strategy-intelligence-v1`) — CONSUMIDOR
- **Propósito**: hipótesis estratégicas, tesis de inversión, consolidación, escenarios.
- **Responsabilidades**: roll-ups/consolidadores, tesis, escenarios; **compone** la inteligencia de los productores + Recommendation.
- **Entradas**: Financial + Signal + Semantic + Recommendation + KG.
- **Salidas**: tesis/escenarios estratégicos explicables.
- **Contratos publicados (planificado)**: `STRATEGY_INTELLIGENCE_ENGINE_CONTRACT.md`.
- **Contratos consumidos**: `financial-*`, `signal-*`, `semantic-*`, `recommendation-*`, `knowledge-graph-*`.

### 2.6 Transaction Intelligence Engine 🔵 (`transaction-intelligence-v1`) — CONSUMIDOR (cima del stack)
- **Propósito**: soporte inteligente al ciclo completo de una transacción (origination → screening → valoración → outreach → negociación → cierre).
- **Responsabilidades**: orquestar **todos** los motores anteriores como Copilot transaccional. No produce conocimiento base.
- **Entradas**: todos los motores anteriores.
- **Salidas**: orquestación transaccional explicable.
- **Contratos publicados (planificado)**: `TRANSACTION_INTELLIGENCE_ENGINE_CONTRACT.md`.
- **Contratos consumidos**: todos los anteriores.

---

## 3. Relaciones entre motores

### Matriz de dependencias permitidas (consume ↓ a →)
| Motor \ puede consumir | Master | Financial | Signal | Semantic | Recommendation | Strategy | Transaction |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **Financial** (P) | ✅ | — | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Signal** (P) | ✅ | ✅ | — | ❌ | ❌ | ❌ | ❌ |
| **Semantic** (P) | ✅ | ⚪ opc | ⚪ opc | — | ❌ | ❌ | ❌ |
| **Recommendation** (C) | ✅ | ✅ | ✅ | ✅ | — | ❌ | ❌ |
| **Strategy** (C) | ✅ | ✅ | ✅ | ✅ | ✅ | — | ❌ |
| **Transaction** (C) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |

`✅` permitido · `⚪` opcional · `❌` prohibido · `—` el propio motor. (P)=productor, (C)=consumidor.

### Reglas de dependencia
- **Permitido**: consumir el Master y motores situados **a la izquierda/abajo** en el ciclo (§5).
- **Prohibido (acíclico estricto)**: ningún productor consume a un consumidor; ningún motor consume a otro situado por encima en el ciclo → el grafo de dependencias es **un DAG sin ciclos**.
- **Prohibido**: que cualquier motor lea fuentes originales o el Normalized/Raw Layer (solo el Foundation Engine los toca).
- **Prohibido**: dependencias implícitas (lectura directa de colecciones de otro motor). Todo intercambio pasa por el contrato/API del motor productor.

---

## 4. Contratos internos (cómo se intercambia inteligencia)

La inteligencia **no** se intercambia mediante llamadas ad hoc ni lectura de colecciones ajenas, sino mediante **contratos estables y versionados**:

- **Unidad de intercambio = contrato del motor productor** (`<engine>-vN`), idéntico para consumidores internos y externos (Boundary/Contract First).
- **Mecanismo**: un motor consumidor invoca la **API del motor productor** (auth `X-API-Key`) o su **interfaz de servicio interna equivalente** que respeta el mismo contrato. Nunca lee la colección interna del productor.
- **Identidad común**: todos los motores referencian la entidad por `master_id` (clave canónica del Master), garantizando *joins* coherentes sin acoplar implementaciones.
- **Trazabilidad de procedencia**: toda salida que reutiliza inteligencia de otro motor debe **citar su origen y versión** (p. ej. la señal compuesta cita `component_types` + `composites_version`; una recomendación citará `semantic-intelligence-v1` + `financial-intelligence-v1`). Esto preserva *Explainability First* a través de la cadena.
- **Versionado del intercambio**: cada contrato declara su versión; un consumidor fija la(s) versión(es) que consume. Cambios aditivos = compatibles; cambios incompatibles ⇒ versión mayor con convivencia (§6).
- **Sin estado oculto compartido**: la única "memoria" común es el Master Layer + las salidas persistidas de cada motor bajo su propio contrato (p. ej. `signals`). Ningún motor escribe en el espacio de otro.

---

## 5. Ciclo de generación de inteligencia

Flujo completo, **estrictamente acíclico** (cada paso reutiliza lo anterior, nunca al revés):

```
            MASTER LAYER (única fuente de verdad)
                     │
   ┌─────────────────┼───────────────────────────────┐
   ▼                 ▼                                 │
FINANCIAL ───────► SIGNAL ───────► SEMANTIC            │  (PRODUCTORES: enriquecen conocimiento)
   │                 │                 │               │
   └────────┬────────┴────────┬────────┘               │
            ▼                  ▼                        │
        RECOMMENDATION ──► STRATEGY ──► TRANSACTION     │  (CONSUMIDORES: reutilizan conocimiento)
                                          │             │
                                          ▼             │
                       CONSUMIDORES (arroba, Copilot, APIs, futuros productos)
```

- **Master → Financial**: el dato real consolidado habilita KPIs/ratios/valoración.
- **Financial → Signal**: las señales financieras (crecimiento/deterioro/anomalías) se derivan del Financial Engine; Signal también lee Master + KG.
- **Signal/Master → Semantic**: el profile semántico se enriquece (opcionalmente) con señales y fundamentos; embeddings SOLO sobre Master consolidado.
- **Productores → Recommendation**: comparables/matching reutilizan similitud + fundamentos + prioridad.
- **Recommendation → Strategy**: tesis/escenarios componen recomendaciones e inteligencia base.
- **Strategy → Transaction**: el Copilot transaccional orquesta todo el stack.

**Regla de oro**: un motor solo puede consumir lo que está **antes** que él en este ciclo.

---

## 6. Gobernanza

- **Versionado**: cada motor versiona su contrato (`<engine>-vN`) y, donde aplique, sub-versiones independientes (p. ej. Signal: `taxonomy/thresholds/actions/composites/score`). La capa versiona su propio documento (`intelligence-layer-vN`).
- **Compatibilidad**: cambios **aditivos** (nuevos campos, nuevos tipos dentro de una taxonomía cerrada, nuevas acciones) = compatibles, no rompen consumidores. Cambios **incompatibles** ⇒ versión mayor del contrato.
- **Convivencia**: una versión mayor nueva convive con la anterior durante un periodo de migración; los consumidores migran de forma controlada y declarada.
- **Evolución**: incorporar una nueva fuente no crea un motor nuevo si encaja en uno existente (p. ej. BORME/M&A → nuevos tipos del Signal Engine), preservando contratos.
- **Incorporación de un nuevo motor**: (1) declarar propósito y clasificación (productor/consumidor); (2) publicar su `*_CONTRACT.md`; (3) ubicarlo en el ciclo (§5) respetando el DAG; (4) actualizar la matriz (§3) y este documento; (5) implementar solo tras congelar su contrato (Contract First).
- **Retirada de un motor**: (1) marcar `deprecated` en este documento; (2) migrar consumidores a su sustituto; (3) periodo de convivencia; (4) retirada cuando ningún consumidor dependa de él (mismo criterio que `companies_master` legacy).
- **Migración legacy**: cada motor productor **absorbe** su equivalente legacy (Value/`signal_engine`/`taxonomy_embeddings`) por la ruta paridad → migración de consumidores → retirada de la dependencia de `companies_master`.

---

## 7. Principios de diseño (invariantes de la capa)

1. **Explainability First** — toda salida (y toda reutilización entre motores) es trazable a dato + regla/umbral + fuente + versión + confianza. Ningún resultado es caja negra.
2. **Boundary First** — cada motor es una frontera: los consumidores obtienen inteligencia solo vía su contrato/API, nunca por lectura directa.
3. **Contract First** — primero se congela el contrato (producto), después se implementa. Los intercambios entre motores son contratos, no llamadas ad hoc.
4. **Master Layer como única fuente de verdad** — todos los motores referencian `master_id`; el conocimiento se ancla al Master canónico.
5. **Ningún motor accede a las fuentes originales** — Raw/Normalized solo los toca el Foundation Engine; los motores nunca leen proveedores directamente.
6. **Reutilizable por cualquier consumidor** — agnóstico de UI; arroba, Copilot, APIs y futuros productos consumen los mismos contratos sin privilegios.
7. **Grafo acíclico (DAG)** — productores no dependen de consumidores; cada motor solo consume lo anterior en el ciclo. Sin dependencias implícitas ni circulares.

---

## Restricciones de este trabajo
Documento exclusivamente arquitectónico: **no** modifica motores existentes, **no** introduce código y **no** cambia contratos ya publicados (`master-v1`, `financial-intelligence-v1`, `signal-intelligence-v1`). Sirve de marco para construir el Semantic Engine y los consumidores sin perder coherencia.
