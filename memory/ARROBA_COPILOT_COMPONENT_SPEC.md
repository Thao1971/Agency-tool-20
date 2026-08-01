# ARROBA — Copilot & Comité · Especificación de Componente (Design Handoff v1.0)

> Handoff para Claude Design / frontend. El Copilot es **UN** componente con **6 variantes de estado**;
> el Comité es **UN** componente premium (tarjeta + deliberación). Ambos **obedecen** el CIM
> (`ARROBA_COPILOT_INTERACTION_SYSTEM.md`) y se alimentan del backend real (`investment_decision`:
> `committee[]`, `reasoning`, `export-payload`). No se inventa contenido: todo viene del payload.

Estado: CANON (capa visible) · `copilot-component-v1`.

---

## 0. Principios de diseño (no negociables)
- **Una sola voz.** Un único componente Copilot; nunca varios, nunca nombres de especialistas como
  interlocutores (solo dentro de la deliberación del Comité).
- **Presencia mínima.** Por defecto invisible (estado A). Aparece solo por evento (CIM §3).
- **Un solo dueño por pantalla** (CIM §6): en pantallas USER el Copilot es secundario; solo ocupa foco
  en estado E.
- **Nada sin soporte:** cada afirmación muestra su evidencia/fuente.

---

## 1. Componente Copilot — 6 variantes de estado

| Estado | Patrón visual | Ubicación | Acciones | Descartable | Disparo (CIM) |
|---|---|---|---|---|---|
| **A · Observador** | *sin render* (o punto idle 6px muy sutil) | — | ninguna | — | por defecto |
| **B · Informador** | franja/línea discreta, 1 frase, icono info | pie o inline, no modal | ninguna (solo "ver") | sí, auto‑oculta | nueva info / riesgo / acción terminada |
| **C · Recomendador** | tarjeta compacta: título + 1–2 líneas + 1–2 acciones | anclada al contexto, no bloquea | Aceptar · Descartar · Ver | sí | nueva recomendación / decisión |
| **D · Conversación** | panel lateral (drawer) con hilo | derecha, abierto por el usuario | escribir, ver fuentes | cerrar | **solo** solicitud del usuario |
| **E · Director** | foco/modal, toma el control | centro, bloquea el fondo | **Autorizar · Rechazar · Ajustar** | no (hay que decidir) | necesita autorización / decisión crítica |
| **F · Ejecutor** | barra de progreso/estado | superior o en la tarjeta | Cancelar | al terminar → A | acción autorizada en curso |

Reglas de variante:
- B/C **no** interrumpen lectura ni navegación (CIM §4).
- E es el **único** estado que puede bloquear el fondo, y **solo** en los 4 momentos del CIM §5.
- Tras F → siempre vuelve a **A** (el Copilot no se queda hablando).
- Microcopy: primera persona, tono asesor, breve. Nunca "como IA…"; es ARROBA Copilot.

Motion: entradas suaves (fade/slide 120–160 ms); E con leve escala; nada estridente.

---

## 2. Tokens visuales
- **Fondo:** blanco/gris muy claro en contenido; negro en portada/cierre/foco premium.
- **Acento único** (por marca). **Colores de banda** (semánticos, solo en el Comité/decisiones):
  PROCEDER `#1D9E75` · CON CONDICIONES `#EF9F27` · EXPLORAR `#378ADD` · PASAR `#888` · RECHAZAR `#E24B4A`.
- Tipografía: heading serif/expresiva + body sans legible (coherente con el resto de ARROBA).
- Separadores discretos; sin sombras exageradas; mucho aire.

---

## 3. Componente Comité de Inversión (premium)

### 3.1 Tarjeta resumen (colapsada)
Anatomía (todo del payload `/analyze`):
- Título **COMITÉ DE INVERSIÓN**.
- **Banda** (pill con color semántico) + **score /100** grande + **confianza** (Alta/Media/Baja desde `confidence`).
- **Han participado**: los 10 especialistas con ✓ (los que se abstienen → ✓ atenuado / "sin datos").
- Botón **[ Ver deliberación ]**.
- Si hay **veto** → banner rojo "Veto: …" y banda REJECT.
- Si `coverage < mínimo` → estado "Datos insuficientes" en vez de score.

### 3.2 Deliberación (expandida) — **no es un chat**
Vista estructurada, **una intervención por especialista** (de `committee[]`):
- Nombre del especialista + su **recomendación** (pill) + **peso aplicado**.
- **Conclusión** (1 frase).
- **Evidencias** (de `evidence[]`: dato · fuente · motor).
- **Nivel de confianza**.
- **Condiciones** y **preguntas abiertas** (si las hay).
Pie: **Trazabilidad** (pesos por perfil, cobertura, dispersión, vetos, motores usados) de `reasoning`.
Los que se abstienen se listan aparte ("Sin datos suficientes"), no se ocultan.

### 3.3 Estados del componente Comité
- **Cargando** (deliberando…), **OK**, **Datos insuficientes**, **Con veto** (destacado).

---

## 4. Ubicación por pantalla (según SCREEN OWNER del CIM)
- **Pantalla USER** (Empresa, Estrategia, Operación, Cartera): Copilot en A; si emerge, B/C **anclado**,
  nunca centro. El Comité aparece como **tarjeta** embebida cuando hay decisión.
- **Pantalla COPILOT** (Autorización de acercamiento): Copilot en **E**, centro, bloquea; botones de
  autorización explícitos.

---

## 5. Contrato de datos (qué alimenta cada elemento)
| Elemento UI | Campo backend |
|---|---|
| Banda + score + confianza | `recommendation`, `investment_score`, `confidence` |
| Resumen / tesis | `executive_summary`, `investment_thesis` |
| Participantes (✓/atenuado) | `committee[].specialist` + `recommendation` (abstain) |
| Intervención por especialista | `committee[]` (recommendation, score, evidence, conditions, questions) |
| Condiciones / preguntas globales | `conditions_to_proceed`, `open_questions` |
| Trazabilidad | `reasoning` (weights, coverage, dispersion, vetoes, engines_used) |
| Export a documento | `GET /decision/{id}/export-payload` |

---

## 6. Anti‑patrones de diseño (prohibido)
- Burbuja de chat persistente que "persigue" al usuario.
- Dos dueños en una pantalla; Copilot ocupando el centro fuera de E.
- Modales durante lectura/navegación.
- Mostrar la deliberación como conversación entre bots.
- Botón de "ejecutar" sin haber pasado por autorización (E).
- Texto/score sin su evidencia.

---

## 7. Entregable esperado de Claude Design
Un componente `Copilot` (6 variantes) + un componente `CommitteeReport` (tarjeta + deliberación), en el
catálogo, con sus estados y tokens, aplicados según el CIM en cada pantalla. Nada de improvisar cuándo
habla o manda: eso ya está fijado por el CIM.
