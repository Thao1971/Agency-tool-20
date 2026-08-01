# ARROBA Copilot — Contrato de Acciones (Next Best Action) · CANON v1.0

> Acuerdo entre el **backend del Copilot** (agency-tool) y el **front de ARROBA**. El backend emite
> *intenciones* de acción en `answer`/`actions[]`; ARROBA las renderiza como chips/botones y resuelve el
> deep-link o el efecto. Fuente de verdad en código: `services/copilot/actions.py` (`CONTRACT`), servida
> por `GET /api/v1/copilot/actions/contract`. Estado: CANON · `copilot-actions-v1`.

## Principio
El Copilot **propone, la UI dispone**. Ninguna acción se auto-ejecuta salvo autonomía alta (estado CIM E)
y, para las de efecto externo, **siempre** con autorización explícita del usuario.

## Forma de una acción
```
{ id, label, kind, target?, params{}, requires_confirmation }
```

## Tipos (`kind`) y comportamiento esperado en la UI
| kind | params | La UI debe… | Efecto externo |
|---|---|---|---|
| `navigate` | target, company_id? | Navegar al deep-link `target` | No |
| `analyze` | company_id | Lanzar análisis del comité (L3) sobre la compañía | No |
| `open_deliberation` | decision_id | Abrir el panel de deliberación de esa decisión | No |
| `generate_document` | doc_type, company_id | Abrir el generador (teaser/one-pager/memo) precargado | No |
| `add_to_watchlist` | company_id? / query? | Añadir la compañía a la watchlist del usuario | No |
| `explain_order` | — | Mostrar "¿por qué este orden?" (sesgo de ranking) | No |
| `search` | query | Abrir búsqueda con la query | No |

## Rutas (deep-links)
- `company_profile`: `/company/{company_id}`
- `compare`: `/compare`
- `document_new`: `/documents/new`

## Reglas para el front
1. Renderiza como máximo las acciones que llegan (el backend ya prioriza, ≤3).
2. Para `external_effect=true` (hoy ninguna; reservado para contactar/enviar/publicar): pide confirmación
   y respeta el gate de autorización.
3. La `ui.card` (mini-card de entidad) se renderiza junto a la respuesta; `answer.disclosure` alimenta
   "ver deliberación"; `personalization_applied.ranking_bias` alimenta "¿por qué este orden?".
4. Si el backend cambia el contrato, sube la `version`; el front debe leer `GET /actions/contract` para
   mantenerse en sync.
