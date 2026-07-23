# TRANSACTION_INTELLIGENCE_ENGINE_CONTRACT.md
**Contrato oficial (PROPUESTA) — Transaction Intelligence Engine**
_Versión: `transaction-intelligence-v1` · 2026-06-26 · Estado: **CONGELADO (FROZEN)** — DTX1…DTX10 aprobadas. Cualquier cambio posterior requiere versionado; no se permiten cambios incompatibles sin versión mayor._

> **Último motor de la Intelligence Layer y orquestador de todo el sistema.** No genera inteligencia, recomendaciones ni estrategias: **orquesta la ejecución** de una Strategic Thesis a lo largo del ciclo completo de una operación, apoyándose en el **Transaction OS** (`TRANSACTION_OS_ARCHITECTURE.md`) y reutilizando todos los motores previos. Se comporta como un **Director de M&A**. No es un gestor de tareas ni un CRM.

---

## 0. Lugar en la arquitectura
Cima del DAG (`INTELLIGENCE_LAYER_ARCHITECTURE.md`): **ningún motor depende de él**. Gobierna entidades del **Transaction OS** y consume la inteligencia previa por contrato.

---

## 1. Filosofía
- **Pregunta única**: *¿Cómo ejecutamos correctamente una tesis estratégica?* (No *qué es / cómo funciona / qué señales / qué recomendar / qué estrategia* — ya resuelto aguas abajo.)
- **Orquesta, no crea**: convierte una `Strategic Thesis` (DT15) en una operación ejecutable, coordinando fases, artefactos, estados, eventos y participantes.
- **Explainability / Boundary / Contract First · Event Driven · Auditability · Reproducibility** (heredados del Transaction OS).
- **Reutiliza por referencia** toda la inteligencia; nunca recalcula ni accede a fuentes originales.

---

## 2. Entradas (estrictas)
Solo vía contratos de: **Transaction OS** (entidades/estado/eventos), **Strategic Thesis** (`strategy-intelligence-v1`/DT15), **Master Layer** (`master-v1`), **Financial**, **Signal**, **Semantic**, **Recommendation**, **Strategy**. **Prohibido**: fuentes originales, `norm_*`, lectura directa de colecciones de otros motores.

---

## 3. Responsabilidades (fases del ciclo)
Cubre la orquestación de: **Origination · Qualification · Screening · Outreach · NDA · Data Room · Valuation · IOI · LOI · Due Diligence · Negotiation · SPA · Signing · Closing · Post-Closing (preparado para futuro)**. Cada fase mapea a `Stage`(s) del Transaction OS, con sus `Milestone`/`Task`/`Approval`/`Deliverable` y la inteligencia que la soporta.

---

## 4. Transaction Copilot (orquestador, no chat)
Define cómo actúa el Copilot durante toda la operación. Capacidades mínimas, **todas explicables y registradas**:
- **suggest_next_action** — siguiente acción óptima según fase/estado/dependencias.
- **detect_blockers** — bloqueos (milestone incompleto, artefacto sin firmar, aprobación pendiente).
- **remind_tasks** — tareas pendientes/vencidas por participante.
- **prepare_documents** — preparar borradores de artefactos (NDA/IOI/LOI/SPA) a partir de plantillas + evidencia (la redacción IA, si aplica, queda acotada como en Strategy DT1).
- **request_information** — solicitar datos faltantes (DD requests, Data Room).
- **warn_risks** — advertir riesgos (financieros/legales/timing) reutilizando Signal/Financial.
- **justify** — justificar cada recomendación con su inteligencia de soporte.
- **record_decision** — registrar decisiones en la memoria transaccional (auditable).

> El Copilot **propone y orquesta**; la **autoridad de decisión** es de los roles humanos (los `Approval` son explícitos).

---

## 5. Modelo transaccional (entidades del motor, alineadas al Transaction OS)
Reutiliza las entidades del Transaction OS; el motor añade la capa de **orquestación e inteligencia**. Entidades principales:

| Entidad | Propósito | Relaciones |
|---|---|---|
| **Transaction** | entidad raíz que gobierna el ciclo | `from_thesis` (Strategic Thesis) · 1:1 `Deal` · agrega todo |
| **Deal** | negociación concreta entre partes | `under_mandate` · `parties[]` · `target master_id` |
| **Workflow** | plantilla+instancia del proceso | de `Transaction` · compuesto de `Stage` |
| **Stage** | fase del ciclo (§3) | ordenada · contiene `Milestone/Task` · estado por fase |
| **Milestone** | punto de control verificable | condiciona transiciones |
| **Task** | unidad de trabajo asignable | `assignee: Participant` · derivada del workflow |
| **Participant** | persona/rol en la operación | `role` (Buyer/Seller/Advisor/…) · permisos |
| **Approval** | decisión formal requerida | bloquea/permite transición · atribuida a rol |
| **Deliverable** | artefacto entregable de una fase | versionado/firmable · dependencias (Document/Data Room/NDA/IOI/LOI/SPA) |

```
Strategic Thesis → Transaction → Deal
Transaction → Workflow → Stage → { Milestone, Task, Approval, Deliverable }
Stage/Task/Approval → Participant
```

---

## 6. Modelo de salida — objeto Acción/Orquestación
Toda acción propuesta por el motor expone su razonamiento (no caja negra):

```jsonc
{
  "action_id": "act_<hash12>",
  "transaction_id": "txn_<hash12>",
  "stage": "due_diligence|negotiation|…",
  "action_type": "next_action|blocker|reminder|prepare_document|request_info|risk_warning",
  "title": "…", "description": "…",
  "explainability": {                       // §7 — obligatorio
    "why_proposed": "…",
    "intelligence_support": ["financial-intelligence-v1","signal-intelligence-v1","strategy-intelligence-v1"],
    "risks_avoided": ["…"],
    "if_not_executed": "consecuencia explícita",
    "dependencies": ["milestone:…","document:NDA.signed","approval:…"]
  },
  "evidence_refs": { "thesis_id":"ths_…","recommendation_ids":["rec_…"],"signal_ids":["sig_…"] },
  "recommended_actions": ["request_due_diligence","contact","value"],   // enum canónico Signal act-v*
  "confidence": { "value":0.0-1.0, "factors": { … } },
  "transaction_version": "transaction-intelligence-v1", "workflow_version": "workflow-template-v1",
  "engines_used": ["…"],
  "evidence_version": { "master":"master-v1","financial":"…","signal":"…","semantic":"…",
                        "recommendation":"recommendation-intelligence-v1","strategy":"strategy-intelligence-v1",
                        "transaction_os":"transaction-os-v1" },
  "generated_at": "ISO"
}
```

---

## 7. Explicabilidad (obligatoria)
Toda acción indica: **por qué se propone**, **qué inteligencia la soporta** (referencias versionadas), **qué riesgos evita**, **qué ocurre si no se ejecuta** y **qué dependencias tiene**. Las decisiones quedan **registradas y auditadas** (Event Driven, Auditability).

---

## 8. API (contrato público del motor)
Auth: `X-API-Key`. Prefijo: `/api/v1/transaction-intelligence`. Agnóstico de UI.

| Método | Endpoint | Propósito |
|---|---|---|
| `POST` | `/transaction` | Crear/consultar una Transaction (origen: `from_thesis`). |
| `POST` | `/workflow` | Instanciar/consultar el Workflow (plantilla por tipo de operación). |
| `POST` | `/stage` | Avanzar/consultar una Stage (con guardas de transición). |
| `POST` | `/task` | Crear/asignar/cerrar Tasks. |
| `POST` | `/next-action` | Copilot: siguiente acción óptima explicada. |
| `POST` | `/risk` | Copilot: riesgos activos de la operación. |
| `POST` | `/documents` | Deliverables/artefactos: estado, versiones, dependencias. |
| `POST` | `/participants` | Participantes y permisos. |
| `POST` | `/timeline` | Línea temporal de eventos de la operación. |
| `POST` | `/decision` | Registrar/consultar Approvals y decisiones. |
| `POST` | `/memory` | Memoria transaccional reutilizable. |
| `GET`  | `/catalog` | Fases, estados, tipos de acción, versiones, dependencias. |

---

## 9. Versionado y reproducibilidad
- **Campos obligatorios**: `transaction_version`, `workflow_version`, `engines_used`, `evidence_version`.
- **`transaction_id` determinista**: `hash(thesis_id + deal_parties + workflow_version + evidence_version)`.
- **Reproducibilidad**: el estado se reconstruye reproduciendo el event log sobre las versiones fijadas (heredado del Transaction OS).
- **Compatibilidad**: aditivo = compatible; incompatible ⇒ versión mayor con convivencia; transacciones en curso no migran salvo migración explícita.

---

## 10. Memoria transaccional (reutilizable)
Registra de forma auditable: **decisiones · documentos · hitos · tareas · bloqueos · aprobaciones · resultados**. Realimenta (vía outcomes/eventos, no lectura directa): **Recommendation** (feedback DR9/DR10), **Strategy** (lifecycle/result/learning DT4/DT14) y **Signal/Financial** (múltiplos y M&A reales → futura fuente, vía ingesta en el Master).

---

## 11. Criterios de aceptación (Definition of Ready) — requieren resolver DTX1…DTX10
Aprobar: modelo transaccional (§5) y de acción (§6); los 12 endpoints (§8); explicabilidad (§7); versionado (§9); memoria (§10); y las decisiones abiertas DTX1…DTX10.

### Definition of Done (implementación, cuando arranque)
- Motor `transaction-intelligence-v1` desacoplado en `services/engines/transaction/`, API `/api/v1/transaction-intelligence/*` con `X-API-Key`.
- Orquesta el ciclo (§3) sobre entidades del Transaction OS; cada acción cumple §6/§7; event log auditable; memoria reutilizable.
- Reutiliza Strategy/Recommendation/productores por referencia (no recrea). Suite smoke verde + verificación end-to-end. Documento pasa a ESTABLE.

---

## Decisiones arquitectónicas cerradas (DTX1…DTX10) — congeladas en `transaction-intelligence-v1`
- **DTX1 — Frontera motor vs Transaction OS**: el **Transaction OS** es propietario de entidades transaccionales, estado, máquina de estados, event log, permisos, workflow runtime y auditoría. El **Transaction Intelligence Engine** es propietario de orquestación, next best action, detección de bloqueos, explicación, priorización, preparación de artefactos y soporte inteligente. **El motor NO duplica estado transaccional** (lo lee/gobierna vía el OS).
- **DTX2 — Workflow Templates versionadas**: cada operación se instancia desde una plantilla; versiones iniciales `buy_side_v1 · sell_side_v1 · capital_raise_v1 · partnership_v1`. Las plantillas evolucionan **sin romper** transacciones ya iniciadas (cada Transaction fija su `workflow_version`).
- **DTX3 — State Machine declarativa y versionada**: cada transición define `from · to · event · guards · authorized_actor · effects · audit`. **Sin transiciones implícitas.**
- **DTX4 — IA del Copilot (híbrido acotado)**: la IA puede redactar/resumir/ordenar/preparar borradores/explicar/convertir evidencia en lenguaje claro. La IA **no puede** cambiar estados, aprobar hitos, enviar comunicaciones, firmar, cerrar operaciones ni tomar decisiones de alto riesgo. **Toda acción crítica requiere aprobación humana.**
- **DTX5 — Approvals y autoridad (obligatorio)**: toda acción de alto riesgo (enviar NDA, abrir Data Room, compartir info sensible, enviar IOI/LOI, aceptar condiciones, avanzar a DD, firmar SPA, cerrar) requiere `Approval` explícito que registra `actor · role · timestamp · artifact_version · evidence_reviewed · decision`.
- **DTX6 — Data Room y firmas**: en v1 el Data Room existe como **entidad y contrato** con `versionado de documentos · hash · permisos · acceso auditado · relación con NDA · relación con DD`. Firma legal avanzada = **integración futura** (prevista, no implementada).
- **DTX7 — Confianza transaccional multifactor**: cada next action incluye `evidence_quality · document_completeness · approvals_state · risk · urgency · critical_dependency · thesis_consistency`.
- **DTX8 — Feedback por eventos reutilizables**: toda transacción genera eventos (`buyer_contacted · nda_signed · offer_received · loi_sent · dd_started · deal_lost · deal_closed`, …) que alimentan posteriormente Recommendation Memory, Strategy Memory, Signal, Financial y datasets de **múltiplos reales** (vía outcomes/ingesta en el Master; no lectura directa).
- **DTX9 — Multi-tenant desde v1**: toda entidad lleva `organization_id · visibility · role_based_access · attribute_based_access (cuando proceda) · audit_log`. **No se asume operación single-user.**
- **DTX10 — Alcance v1 acotado**: v1 cubre sólidamente **Origination · Qualification · Screening · Outreach · NDA · Data Room · Valuation · Due Diligence inicial**. Se **difieren a v2**: IOI avanzada, LOI avanzada, negociación, SPA, signing, closing, post-closing. **El contrato contempla el ciclo completo; la implementación v1 se concentra en Origination → DD inicial.**

## Principio fundamental
El Transaction Intelligence Engine **no es un gestor de tareas ni un CRM**. Es el **orquestador inteligente** que convierte una **Strategic Thesis** en **ejecución transaccional**, respetando **estado, permisos, approvals, trazabilidad y memoria**, apoyado en el Transaction OS y en toda la inteligencia del sistema.

## Principios obligatorios adicionales (DTX11–DTX13)
- **DTX11 — Universal Timeline**: toda transacción expone una **línea temporal única y unificada** de todos sus eventos (estado, tareas, approvals, documentos, accesos, inteligencia aplicada), reconstruible desde el event log (append-only). Es la vista canónica del histórico de la operación.
- **DTX12 — Transaction Workspace (modelo de dominio)**: existe un **Workspace** como agregado de dominio de una operación (transaction + workflow + stages + tasks + approvals + documents + participants + timeline + next actions), consumible por arroba.com/Copilot/futuros consumidores. La UI definitiva la construye arroba; el OS/motor entregan el **modelo**.
- **DTX13 — Event Driven First**: el estado **solo** cambia por eventos; cada mutación emite un evento auditado y atribuido. No hay estado oculto ni mutaciones fuera del event log. La reproducibilidad se garantiza reproduciendo eventos sobre las versiones fijadas.
