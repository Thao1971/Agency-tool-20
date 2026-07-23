# TRANSACTION_OS_COMPLETION.md
**Cierre oficial — Transaction OS & Transaction Intelligence Engine (Sprint 7)**
_Versión: `transaction-os-v1` + `transaction-intelligence-v1` · 2026-06-26 · Estado: **COMPLETADO / ESTABLE**._

> Documento de referencia oficial del núcleo operativo de Agency Tool. Cierra definitivamente
> la Intelligence Layer y establece la infraestructura permanente de ejecución de operaciones
> sobre la que crecerán **Marketplace, Deal Rooms, Copilot transaccional y arroba.com**.

---

## 1. Arquitectura definitiva

Dos componentes desacoplados con frontera estricta (DTX1):

- **Transaction OS** (`services/transaction_os/`) — **propietario único del estado**: entidades,
  máquina de estados, event log append-only, approvals, data room/documentos, tareas, timeline y
  memoria transaccional.
  - `workflows.py` — plantillas de workflow versionadas (DTX2) + máquina de estados declarativa (DTX3).
  - `store.py` — runtime: entidades, `emit()` (event-driven), guards, approvals, documentos, timeline, memoria.
- **Transaction Intelligence Engine** (`services/engines/transaction/engine.py`) — **orquestador**:
  next-best-action, detección de bloqueos, riesgos, preparación de borradores, workspace y
  explicabilidad. **No mantiene estado** (auditado: sin acceso directo a DB; delega 100 % en el OS).
- **API pública** (`routes/transaction_intelligence.py`) — prefijo `/api/v1/transaction-intelligence`,
  auth `X-API-Key`, agnóstica de UI. Registrada en `server.py`; índices creados en startup.

Lugar en el DAG: **cima de la Intelligence Layer**; ningún motor depende de él. Reutiliza
Master/Financial/Signal/Semantic/Recommendation/Strategy **por referencia** (solo lectura).

---

## 2. Decisiones tomadas (DTX1–DTX13, congeladas)
- **DTX1** Frontera OS↔Engine: el OS posee el estado; el motor solo orquesta.
- **DTX2** Workflow templates versionadas: `buy_side_v1 · sell_side_v1 · capital_raise_v1 · partnership_v1`.
- **DTX3** State machine declarativa y versionada (`state-machine-v1`); sin transiciones implícitas.
- **DTX4** IA del Copilot acotada: redacta/resume/explica; nunca cambia estado ni aprueba.
- **DTX5** Approvals explícitos para acciones de alto riesgo (`actor·role·timestamp·evidence·decision`).
- **DTX6** Data Room/documentos: versionado + hash + permisos + acceso auditado (firma legal avanzada → v2).
- **DTX7** Confianza multifactor (7 factores) en cada next action.
- **DTX8** Eventos de dominio reutilizables para realimentar Recommendation/Strategy/Signal/Financial.
- **DTX9** Multi-tenant desde v1 (`organization_id · visibility`).
- **DTX10** Alcance v1: Origination → Due Diligence inicial; IOI/LOI/SPA/closing diferidos a v2.
- **DTX11** Universal Timeline: cronología única reconstruida desde el event log.
- **DTX12** Transaction Workspace: agregado de dominio consumible (transaction+workflow+stages+tasks+
  approvals+documents+participants+timeline+next_action).
- **DTX13** Event Driven First: el estado solo cambia por eventos auditados.

---

## 3. Entidades finales (colecciones)
| Colección | Propósito |
|---|---|
| `tx_transactions` | entidad raíz: estado global, workflow/state-machine version, stages, parties, tenant |
| `tx_events` | event log append-only (fuente de verdad, timeline, reproducibilidad) |
| `tx_tasks` | tareas asignables derivadas del workflow |
| `tx_approvals` | aprobaciones formales de acciones de alto riesgo (DTX5) |
| `tx_documents` | deliverables versionados (NDA, data room, …) con hash y permisos |

`transaction_id` determinista = `txn_` + `sha256(thesis_id|target_master_id|workflow_version)[:12]`.

---

## 4. Eventos soportados
Ciclo de vida y mutaciones (todos auditados, atribuidos a actor):
`transaction_created · thesis_instantiated · stage_completed · task_created · task_completed ·
approval_requested · approval_decided · document_added · document_state_changed · document_accessed`
+ transiciones de estado (`buyer_contacted · advance_to_due_diligence · deal_closed · deal_lost · abandon · hold`).

Eventos de dominio reutilizables (DTX8): `buyer_contacted · nda_signed · offer_received · loi_sent ·
dd_started · deal_lost · deal_closed`.

---

## 5. Máquina de estados (state-machine-v1)
Estado global: `draft → sourcing → engaged → diligence → closed_won`; ramas terminales
`closed_lost · abandoned`; reversible `on_hold`.

Transiciones declarativas (from·to·event·guards·authorized·effects):
- `draft → sourcing` (`thesis_instantiated`, guard `has_thesis`) — automática al crear.
- `sourcing → engaged` (`buyer_contacted`, guard `screening_complete`).
- `engaged → diligence` (`advance_to_due_diligence`, guards `nda_signed`+`data_room_open`+`approval:advance_to_due_diligence`).
- `diligence → closed_won` (`deal_closed`, guard `approval:close_deal`).
- `* → closed_lost / abandoned / on_hold`.
Stages v1: `origination · qualification · screening · outreach · nda · data_room · valuation · due_diligence_initial`.

---

## 6. Workflow templates
`buy_side_v1 · sell_side_v1 · capital_raise_v1 · partnership_v1`, todas con los 8 stages v1.
Cada Transaction fija su `workflow_version` y `state_machine_version` (las plantillas evolucionan sin
romper transacciones en curso).

---

## 7. APIs (contrato §8)
`POST /transaction · /workflow · /stage · /task · /next-action · /risk · /documents · /participants ·
/timeline · /decision · /memory · /workspace (DTX12)` y `GET /catalog`. Auth `X-API-Key`.
Cada next action cumple §6/§7 (explicabilidad obligatoria + confianza multifactor + versionado/evidence).

---

## 8. Pruebas realizadas
- Suite smoke dedicada: `tests/smoke/test_transaction_intelligence.py` — **12/12 verde**.
  Cubre: engine sin estado (DTX1), creación event-driven + timeline (DTX13/DTX11), `transaction_id`
  determinista, explicabilidad + 7 factores de confianza (§7/DTX7), no transición implícita (DTX3),
  ciclo completo con guards y approvals hasta `closed_won` (DTX5), tareas+memoria, workspace (DTX12),
  riesgos (reuso Signal por referencia), 401 sin key, 404, catálogo.
- Suite smoke global: **203/203 verde** (191 previos + 12 nuevos). Sin regresiones.
- Validación end-to-end vía `testing_agent` sobre la API completa.

---

## 9. Limitaciones conocidas (v1)
- Firma legal avanzada del Data Room: entidad/contrato presentes; integración de firma → v2.
- Realimentación a Recommendation/Strategy/Signal/Financial: los eventos existen y son reutilizables;
  la **ingesta** de outcomes (múltiplos reales, feedback) se materializará en sprints posteriores
  (vía Master/Memory, nunca lectura directa cruzada).
- Contenido de documentos: el OS guarda metadatos/hash/versión; el binario irá a object storage (preparado).

---

## 10. Backlog diferido a v2
- IOI/LOI avanzadas, negociación, SPA, signing, closing, post-closing (PMI).
- Auctions multi-bidder y nuevas plantillas de workflow.
- Firma electrónica legal e integración de Data Room con almacenamiento masivo de binarios.
- Bucle de realimentación completo a la Intelligence Layer (outcomes → Master/Memory).
- Consumidores: **Marketplace (P1) · Deal Rooms (P2) · Copilot transaccional UI (P3) · Pipeline de operaciones (P4)** — todos sobre este OS.

---

## Resultado
El **Transaction OS** queda establecido como la **infraestructura permanente de ejecución de
operaciones** de Agency Tool: canónica, desacoplada, event-driven, auditable, reproducible y
multi-tenant. **Sprint 7 = COMPLETADO.**
