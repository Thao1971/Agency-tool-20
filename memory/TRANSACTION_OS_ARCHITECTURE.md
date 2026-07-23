# TRANSACTION_OS_ARCHITECTURE.md
**Arquitectura definitiva del Transaction OS — Agency Tool / arroba.com**
_Versión: `transaction-os-v1` · 2026-06-26 · Estado: ESTABLE (documento de arquitectura; NO introduce código, APIs ni endpoints)._

> Fuente de verdad para construir posteriormente el **Transaction Intelligence Engine**, el **Marketplace**, los **Deal Rooms**, los **Workflows**, el **Copilot transaccional** y el **Pipeline de operaciones**. Diseñado para gobernar **cientos de miles de operaciones simultáneas**. Optimizado para la arquitectura definitiva, no para el MVP.

---

## 1. Filosofía

### Qué es
El **Transaction OS** es el **sistema operativo que gobierna el ciclo completo de una operación corporativa**, desde una tesis estratégica hasta una operación ejecutada (y su integración posterior). Responde a una única pregunta:

> **¿Cómo convierte arroba una tesis estratégica en una operación ejecutada?**

Se sitúa **encima de la Intelligence Layer**: consume su inteligencia y orquesta personas, artefactos, estados y eventos a lo largo de una transacción.

### Qué problemas resuelve
- **Discontinuidad tesis→ejecución**: une el razonamiento estratégico (Strategic Thesis, DT15) con la ejecución real sin reconstruir el conocimiento.
- **Estado disperso e implícito**: centraliza el estado de cada operación como **entidad auditada y explícita** (no en hojas/correos/CRMs).
- **Falta de trazabilidad y auditabilidad**: cada decisión, documento y transición queda registrada como **evento inmutable**.
- **Escala**: diseñado para cientos de miles de operaciones concurrentes, multi-tenant, particionable.
- **Reutilización de inteligencia**: cada resultado transaccional **realimenta** Recommendation y Strategy.

### Qué NO es
- **No** es un CRM (la relación comercial es un subconjunto, no el centro).
- **No** es un gestor documental (los documentos son artefactos gobernados por estados/eventos, no el fin).
- **No** es un gestor de tareas (las tareas son derivadas de workflows/estados, no la abstracción principal).
- **No** es un motor de inteligencia (consume la Intelligence Layer; no recrea conocimiento).

### Principios arquitectónicos (resumen; detalle en §10)
Entity First · Transaction as Entity · Event Driven · No Hidden State · Explainability First · Contract First · Boundary First · Auditability · Reproducibility.

---

## 2. Modelo conceptual (entidades y relaciones)

Cada entidad tiene **id canónico**, **versión**, **estado explícito** y **event log**. Todas referencian empresas por `master_id` (Master Layer = única verdad de identidad).

| Entidad | Propósito | Relaciones clave |
|---|---|---|
| **Strategic Thesis** | Razonamiento estratégico (entidad canónica del Strategy Engine, DT15) | origina → `Opportunity` · `converts_to: opportunity/mandate/transaction` |
| **Opportunity** | Oportunidad accionable derivada de una tesis o señal | `from_thesis` · agrupa candidatos (`master_id`) · puede formalizarse en `Mandate` |
| **Mandate** | Encargo formal (sell-side/buy-side) que autoriza a operar | `for_opportunity` · `owner_org` · `advisor_org` · genera `Deal`(s) |
| **Deal** | Relación de negociación concreta entre partes sobre un objeto | `under_mandate` · `parties[]` · `target master_id` · contiene `Workflow` |
| **Transaction** | La operación como ENTIDAD raíz que gobierna todo el ciclo | 1:1 con `Deal` consolidado · agrega `Stage/Milestone/Task/Document/Participant` · estado global |
| **Workflow** | Plantilla + instancia del proceso (fases/hitos) | pertenece a `Transaction` · compuesto de `Stage` |
| **Stage** | Fase del ciclo (Contacto, NDA, DD, SPA…) | ordenada · contiene `Milestone`/`Task` · estado por fase |
| **Milestone** | Punto de control verificable de una fase | `in_stage` · condiciona transiciones |
| **Task** | Unidad de trabajo asignable | `in_stage` · `assignee: Participant` · derivada de workflow |
| **Participant** | Persona/rol dentro de una transacción | `role` (§5) · `belongs_to Organization` · permisos |
| **Organization** | Entidad jurídica/firma (comprador, vendedor, advisor, despacho…) | mapeable a `master_id` cuando es empresa del Master |
| **Document** | Artefacto versionado y firmable | `in_data_room` · `type` · versiones · firmas · dependencias |
| **Data Room** | Espacio gobernado de intercambio de información | `for_transaction` · permisos por `Participant`/`role` · audita accesos |
| **NDA** | Acuerdo de confidencialidad (artefacto + estado) | habilita acceso a `Data Room` |
| **IOI** | Indication of Interest (no vinculante) | precede a `LOI` · referencia valoración |
| **LOI** | Letter of Intent / term sheet | precede a `Due Diligence` · fija términos preliminares |
| **Due Diligence** | Proceso de revisión (financiera/legal/comercial/tech) | usa `Data Room` · produce findings · condiciona `SPA` |
| **SPA** | Sale & Purchase Agreement | resultado de DD + negociación · precede a `Signing` |
| **Closing** | Cierre y condiciones suspensivas | tras `Signing` · estado terminal de la fase de ejecución |
| **(futuro) PMI** | Post-Merger Integration | tras `Closing` · preparado, no detallado en v1 |

**Jerarquía de agregación**: `Strategic Thesis → Opportunity → Mandate → Deal → Transaction → {Workflow → Stage → {Milestone, Task}}`, con `Participant/Organization`, `Document/Data Room` y artefactos legales (`NDA/IOI/LOI/SPA`) colgando de `Transaction`.

---

## 3. Ciclo completo de una operación
```
Empresa (master_id)
  ↓  [Intelligence Layer]
Strategic Thesis            (Strategy Engine — DT15, entidad canónica)
  ↓  convert
Opportunity                 (accionable; candidatos)
  ↓  formalize
Mandate                     (encargo buy-side / sell-side)
  ↓  matching               (reutiliza Recommendation Engine)
Contacto / Outreach
  ↓
NDA                         (habilita Data Room)
  ↓
Intercambio de información  (Data Room gobernado y auditado)
  ↓
Valoración                  (reutiliza Financial Engine)
  ↓
IOI  → LOI                  (no vinculante → términos preliminares)
  ↓
Due Diligence               (financiera/legal/comercial/tech)
  ↓
SPA                         (negociación de contrato)
  ↓
Signing
  ↓
Closing                     (terminal de ejecución)
  ↓
Post-Merger Integration     (preparado para el futuro)
```
Cada flecha es una **transición de estado** disparada por un **evento** y registrada en el **event log** de la `Transaction`.

---

## 4. Máquina de estados

Diseño de **estados explícitos** (No Hidden State). Tres niveles: **global** (Transaction), **por fase** (Stage) y **artefacto** (Document/legal).

### 4.1 Estado global de la Transaction
`draft → sourcing → engaged → diligence → negotiation → signing → closed_won` con ramas terminales `closed_lost`, `abandoned`, `on_hold` (reversible).

### 4.2 Estados por fase (Stage)
Cada Stage: `pending → active → blocked → completed` (o `skipped`). Una Stage no se completa hasta cumplir sus `Milestone`s.

### 4.3 Estados de artefactos clave
- **NDA**: `drafted → sent → negotiated → signed → expired`.
- **IOI/LOI**: `drafted → submitted → countered → accepted/rejected/withdrawn`.
- **Due Diligence**: `not_started → in_progress → findings_open → cleared/blocked`.
- **SPA**: `drafting → under_negotiation → agreed → executed`.
- **Closing**: `conditions_pending → conditions_met → completed`.

### 4.4 Clasificación de estados
- **Terminales**: `closed_won`, `closed_lost`, `abandoned` (y `executed`/`completed` a nivel artefacto).
- **Reversibles**: `on_hold` (↔ estado previo), `blocked` (↔ active), `countered` (↔ submitted).
- **No reversibles**: cualquier paso tras `signing` solo avanza o aborta con `abandoned` registrado.

### 4.5 Transiciones
- Toda transición es **explícita, validada por guardas** (precondiciones: milestones cumplidos, artefactos firmados, permisos del rol) y **emite un evento** (`transition_id`, `from`, `to`, `actor`, `at`, `evidence`).
- Las transiciones permitidas se definen en una **State Machine versionada** (`state-machine-vN`); cambios incompatibles ⇒ versión mayor con convivencia.

---

## 5. Roles y permisos (conceptual)

| Rol | Participa como | Permisos conceptuales |
|---|---|---|
| **Buyer** | parte compradora | ve oportunidades/targets, firma NDA/IOI/LOI/SPA, accede a Data Room concedido |
| **Seller** | parte vendedora / target | publica info en Data Room, aprueba accesos, firma artefactos |
| **Advisor** | M&A advisor / banca de inversión | gestiona Mandate, matching, conduce el proceso, no firma por las partes |
| **Investor** | capital (PE/VC/family office) | similar a Buyer con foco en tesis/retorno |
| **Lawyer** | asesoría legal | redacta/negocia NDA/LOI/SPA, gestiona DD legal |
| **Auditor** | due diligence financiera | acceso de solo lectura a Data Room financiero, emite findings |
| **Administrator** | admin de Organization/tenant | gobierna usuarios, permisos y configuración del tenant |
| **Platform** | arroba (sistema) | orquesta, audita, aplica políticas, ejecuta Copilot; nunca es parte de la operación |

- **Modelo de permisos**: RBAC por `role` **+** ABAC por contexto (`transaction_id`, `data_room`, fase, `organization`). Acceso **mínimo necesario**; todo acceso **auditado**. Los permisos son **conceptuales** aquí (la implementación los materializará en el motor/servicios).

---

## 6. Artefactos
- **Tipos**: NDA, teaser/IM, IOI, LOI/term sheet, financials, DD requests/findings, SPA, disclosure schedules, closing checklist.
- **Evolución**: cada artefacto tiene **ciclo de vida** (§4.3) y **versionado inmutable** (cada versión es un objeto nuevo; nunca se sobrescribe). 
- **Firmas**: registro de firmas por `Participant` (quién, cuándo, sobre qué versión, hash del contenido). Una firma vincula a una **versión concreta** (reproducibilidad).
- **Dependencias**: grafo de dependencias entre artefactos (p. ej. `Data Room` requiere `NDA.signed`; `SPA` requiere `DD.cleared` + `LOI.accepted`). Las dependencias actúan como **guardas** de las transiciones.
- **Almacenamiento**: contenido en **object storage** (no en la BD); la BD guarda metadatos, versiones, hashes, permisos y eventos. Preparado para volumen masivo.

---

## 7. Memoria transaccional
- **Qué se conserva**: el **event log inmutable** por `Transaction` (origen, transiciones, accesos, firmas, decisiones), el histórico de artefactos, los participantes y los resultados (`closed_won/lost`, motivo, valoración final, múltiplos reales observados).
- **Qué decisiones se registran**: aceptaciones/rechazos de IOI/LOI, findings de DD, condiciones de SPA, decisiones de los roles con su justificación.
- **Auditoría**: cada evento es **append-only**, sellado temporalmente y atribuido a un actor → cumple Auditability y Reproducibility ("rehacer" el estado a cualquier momento reproduciendo eventos).
- **Realimentación a la Intelligence Layer** (cierra el bucle del flujo M&A):
  - → **Recommendation**: resultados (aceptado/rechazado/cerrado, encaje real) alimentan `recommendation_feedback`/Memory (DR9/DR10) para recalibrar.
  - → **Strategy**: outcomes de tesis (`lifecycle`/`result`/`learning`, DT4/DT14) cierran el ciclo de la Strategic Thesis y mejoran futuras tesis.
  - → **Signal/Financial**: **múltiplos reales** y eventos de control observados en transacciones cerradas pasan a ser fuente futura para `transaction.ma_event` (Signal ⏳) y valoración real (Financial), vía ingesta en el Master por el Foundation Engine (nunca lectura directa cruzada).

---

## 8. Relaciones con la Intelligence Layer

> El Transaction OS **consume por contrato** (Boundary First) y **devuelve outcomes** que realimentan los productores.

| Motor | Qué consume el Transaction OS | Qué devuelve / realimenta |
|---|---|---|
| **Financial** (`financial-intelligence-v1`) | valoración, KPIs, ratios para IOI/LOI/SPA y DD financiera | múltiplos reales y resultado de valoración → futura fuente Financial |
| **Signal** (`signal-intelligence-v1`) | señales de oportunidad/riesgo para sourcing y timing | `ma_event`/`control_change` reales (cerrados) → futura fuente Signal ⏳ |
| **Semantic** (`semantic-intelligence-v1`) | perfiles/similitud para matching y screening | confirmación de encaje real → evidencia |
| **Recommendation** (`recommendation-intelligence-v1`) | comparables/buyers/sellers/matching para construir el universo de la operación | feedback de aceptación/cierre (DR9/DR10) |
| **Strategy** (`strategy-intelligence-v1`) | **Strategic Thesis (DT15)** como origen de la operación (`convert`→opportunity/mandate/transaction) | `lifecycle/result/learning` de la tesis (DT4/DT14) |

**Dependencia estricta y acíclica**: el Transaction OS está en la **cima** del DAG (`INTELLIGENCE_LAYER_ARCHITECTURE.md`); ningún motor depende de él. La realimentación **no** es lectura directa: se materializa como **outcomes/eventos** que se ingieren en el Master o en las colecciones de Memory/Feedback de los motores.

---

## 9. Gobernanza
- **Versionado**: el OS (`transaction-os-vN`), la **State Machine** (`state-machine-vN`), las **plantillas de Workflow** (`workflow-template-vN`) y cada **tipo de artefacto** se versionan de forma independiente. Cada `Transaction` fija las versiones con las que opera (reproducibilidad).
- **Compatibilidad**: cambios aditivos (nuevos estados opcionales, nuevos tipos de artefacto, nuevos roles) = compatibles; cambios incompatibles ⇒ versión mayor con convivencia. Las transacciones en curso **no migran de versión** salvo migración explícita.
- **Evolución**: nuevas fases/flujos (p. ej. PMI, auctions multi-bidder) se añaden como nuevas plantillas/estados sin romper transacciones existentes.
- **Migraciones**: idempotentes, versionadas y auditadas; nunca alteran el event log histórico (append-only). Multi-tenant: aislamiento por `organization`/tenant.

---

## 10. Principios de diseño (invariantes)
1. **Entity First** — todo es una entidad con id, versión, estado y event log; no objetos efímeros.
2. **Transaction as Entity** — la operación es la entidad raíz que gobierna todo el ciclo (no una suma de tareas/documentos).
3. **Event Driven** — el estado cambia solo por eventos; el event log es la fuente de verdad reproducible.
4. **No Hidden State** — ningún estado vive implícito en correos/hojas/lógica oculta; todo estado es explícito y consultable.
5. **Explainability First** — toda decisión/transición es trazable a su evidencia (incl. la inteligencia que la originó).
6. **Contract First** — entidades, estados y relaciones se definen y congelan antes de implementar; los intercambios con la Intelligence Layer son contratos.
7. **Boundary First** — el OS consume la Intelligence Layer solo por contrato; no recrea conocimiento ni accede a fuentes/colecciones ajenas.
8. **Auditability** — event log append-only, atribuido, sellado temporalmente; cualquier acción es auditable.
9. **Reproducibility** — el estado de cualquier transacción se puede reconstruir reproduciendo sus eventos sobre la versión fijada.
10. **Escala por diseño** — multi-tenant, particionable por `transaction_id`/tenant, contenido en object storage, pensado para cientos de miles de operaciones concurrentes.

---

## Resultado esperado
Esta es la **arquitectura definitiva del sistema operativo transaccional**. Sobre ella se construirán, en fases posteriores y *Contract First*: **Transaction Intelligence Engine**, **Marketplace**, **Deal Rooms**, **Workflows**, **Copilot transaccional** y **Pipeline de operaciones**. Ningún componente transaccional se diseñará fuera de este marco.

> **Restricción de este trabajo**: documento exclusivamente arquitectónico. No introduce código, APIs ni endpoints. No optimiza para el MVP, sino para la arquitectura definitiva.
