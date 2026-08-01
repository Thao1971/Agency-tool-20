# ARROBA — Copilot Interaction System (CIS / CIM v1.0)

> **No diseñes pantallas. Diseña el sistema de interacción entre el usuario y ARROBA Copilot.**
> Las pantallas son *consecuencia*. Este documento es la **gramática universal** del comportamiento
> del Copilot: cuándo habla, cuándo calla, cuándo recomienda y cuándo toma el control. Claude Design
> (y cualquier constructor de UI) **no improvisa** ese comportamiento: aplica estas reglas en todas
> las pantallas.
>
> Nota de nomenclatura: "CIS" ya es la sigla de CIS/Valuo.pro. Para evitar colisión, la clave interna
> de este documento es **CIM (Copilot Interaction Model)**; el nombre de producto puede seguir siendo
> "Copilot Interaction System". Un usuario perdona una pantalla mejorable; no perdona un Copilot impredecible.

Estado: CANON (rige por encima del catálogo de componentes y de Claude Design). Versión: `cim-v1`.

---

## 1. Jerarquía (no se invierte nunca)

```
Usuario  →  Pantalla  →  Copilot  →  Motores IA
```

- El **usuario** manda.
- La **pantalla** es el medio; presenta datos y acciones.
- El **Copilot** es un asesor que vive *dentro* de la pantalla, **nunca es la pantalla**.
- Los **motores** (Financial, Valuation/Valuo, Strategy, Signal, Semantic, Recommendation,
  Fragmentation/E7, Investment Decision, Matching/Buyer Mandate, KG) son la fuente; el Copilot los
  orquesta y traduce, no los sustituye.

Regla dura: **el Copilot no ocupa la pantalla**. Salvo en el Estado E (Director), es un elemento
secundario y contextual.

---

## 2. Estados del Copilot (no está activo siempre)

El Copilot **tiene estados**; por defecto está en A (silencio). Cada estado define presencia visual,
qué puede hacer y qué NO.

| # | Estado | Presencia | Puede | NO puede | Se nutre de |
|---|--------|-----------|-------|----------|-------------|
| **A** | **Observador** | Ninguna (invisible) | Trabajar en segundo plano, precomputar | Hablar, interrumpir, mostrar mensajes | Todos (lectura) |
| **B** | **Informador** | Aviso discreto, no modal | Señalar 1 hecho relevante | Recomendar, pedir acción, abrir chat | Signal, Financial |
| **C** | **Recomendador** | Tarjeta con acciones sugeridas | Proponer una decisión + acciones | Ejecutar, tomar el control | Recommendation, Strategy, Investment Decision |
| **D** | **Conversación** | Panel de chat (abierto por el usuario) | Responder con fact-lock, explicar | Iniciar conversación motu proprio | Copilot Q&A (fact-lock) sobre motores |
| **E** | **Director** | Toma el control (modal/foco) | Pedir autorización explícita | Ejecutar sin el "sí" del usuario | Investment Decision, Matching |
| **F** | **Ejecutor** | Barra de progreso / estado | Ejecutar lo ya autorizado | Volver a preguntar, cambiar el alcance | Acciones + motores |

Transición canónica: `A → (evento) → B/C → (usuario) → D → (decisión con efecto) → E → (autorización) → F → A`.
Tras F, el Copilot **vuelve a A** (silencio). Nunca se queda "hablando".

Invariante de seguridad: **ninguna acción del Estado F sin un Estado E previo con autorización
explícita del usuario** (contactar empresa, enviar, publicar, mover datos → siempre pasan por E).

---

## 3. La regla de oro — cuándo APARECE

El Copilot **nunca habla porque sí**. Solo emerge (de A a B/C/E/F) ante uno de estos eventos:

```
Nueva información  ·  Nueva decisión  ·  Nuevo riesgo  ·  Nueva recomendación
·  Solicitud del usuario  ·  Acción terminada  ·  Acción bloqueada
```

| Evento | Estado que activa |
|---|---|
| Nueva información relevante | B (Informador) |
| Nuevo riesgo | B (o C si hay acción defensiva) |
| Nueva recomendación / decisión | C (Recomendador) |
| Solicitud del usuario | D (Conversación) |
| Acción que requiere permiso | E (Director) |
| Acción terminada | B breve ("hecho") → A |
| Acción bloqueada | B/E (según requiera decisión) |

Nada más dispara al Copilot.

---

## 4. Cuándo NO aparece (la pantalla manda)

El Copilot permanece en A —invisible— mientras el usuario:

- navega por una empresa,
- lee informes / cuadernos,
- consulta ratios,
- compara empresas,
- descarga documentos.

En estos contextos **conduce la pantalla**, no el Copilot. Como mucho, una micro‑recomendación (C) no
intrusiva; jamás un modal.

---

## 5. Cuándo TOMA EL CONTROL (solo 4 momentos)

El Copilot pasa a **Director (E)** —ocupa el foco— únicamente en:

1. **Descubre una oportunidad** (merece decisión del usuario).
2. **Recomienda una decisión** de peso (incorporar a estrategia, avanzar operación).
3. **Necesita autorización** (antes de una acción con efecto externo).
4. **Termina una acción** (cierre/confirmación de un flujo que él conducía).

**Nunca en más momentos.** Fuera de estos cuatro, el control es del usuario.

---

## 6. SCREEN OWNER — un solo dueño por pantalla

Cada pantalla declara **quién la conduce**, y es excluyente:

```
SCREEN OWNER: USER      ó      SCREEN OWNER: COPILOT
```

**Nunca ambos a la vez.** Ejemplos:

| Pantalla | Owner | Rol del Copilot |
|---|---|---|
| Empresa (ficha) | USER | Observador; micro‑recomendación puntual |
| Estrategia | USER | Recomendador (propone; el usuario decide) |
| Autorización de acercamiento | **COPILOT** | Director (necesita aprobación) |
| Operación / Deal | USER | Recomendador/Asesor |

Cuando el Copilot termina de conducir (E/F), **devuelve el control** al usuario y vuelve a A.

---

## 7. Contrato obligatorio por pantalla (los 10 puntos)

Toda especificación de pantalla —antes de dibujarla— DEBE rellenar:

1. **Objetivo** de la pantalla.
2. **Quién conduce** (USER | COPILOT).
3. **Estado(s) del Copilot** permitido(s) aquí (A–F).
4. **Qué puede hacer el usuario**.
5. **Qué puede hacer el Copilot**.
6. **Qué acciones requieren autorización** (pasan por Estado E).
7. **Qué ocurre al abandonar** la pantalla (¿se cancela? ¿persiste? ¿el Copilot vuelve a A?).
8. **Qué ocurre si el usuario no hace nada** (estado por defecto, sin nag).
9. **Siguiente pantalla natural** (el flujo esperado).
10. **Qué motores participan** (Recommendation, Strategy, Signal, Matching, Investment Decision, …).

Sin estos 10 puntos, la pantalla **no se diseña**.

---

## 8. Anti‑patrones (prohibido)

- Copilot hablando sin un evento del §3 ("porque sí").
- Dos dueños en una pantalla (§6).
- Interrumpir la lectura/navegación con modales (§4).
- Ejecutar (F) sin autorización previa (E) en acciones con efecto externo.
- Chat que se auto‑inicia o "persigue" al usuario.
- El Copilot ocupando la pantalla fuera de los 4 momentos del §5.
- Recomendaciones sin evidencia trazable (heredado de los motores: nada sin `{source, engine, data}`).

---

## 9. Catálogo inicial aplicado (starter — mismo contrato §7)

### 9.1 Empresa (ficha)
1. Objetivo: entender una compañía. 2. Owner: **USER**. 3. Estados: A, (C micro). 4. Usuario: navegar,
leer ratios, ver evolución, descargar. 5. Copilot: en A; si hay señal fuerte, una tarjeta C discreta.
6. Autorización: ninguna. 7. Al salir: Copilot→A. 8. Sin acción: solo datos. 9. Siguiente: Estrategia
o Comparar. 10. Motores: Financial, Valuation, Signal, Semantic.

### 9.2 Descubrimiento / Oportunidades
1. Objetivo: surfacing de oportunidades. 2. Owner: USER (pero el Copilot puede pasar a **C/E** al
descubrir). 3. Estados: A→B/C, E (momento 1 del §5). 4. Usuario: filtrar, abrir, descartar.
5. Copilot: proponer oportunidades con racional. 6. Autorización: añadir a estrategia (C→confirm).
7. Al salir: persiste el feed. 8. Sin acción: feed estático. 9. Siguiente: Empresa o Estrategia.
10. Motores: Recommendation, Signal, Fragmentation/E7, Matching.

### 9.3 Estrategia
1. Objetivo: construir la tesis del comprador. 2. Owner: **USER**. 3. Estados: A, **C** (propone).
4. Usuario: definir mandato, aceptar/rechazar propuestas. 5. Copilot: recomendar encajes (no decide).
6. Autorización: ninguna (aún no hay efecto externo). 7. Al salir: guarda mandato. 8. Sin acción:
mantiene estado. 9. Siguiente: Oportunidades o Autorización de acercamiento. 10. Motores: Strategy,
Recommendation, Investment Decision, Buyer Mandate.

### 9.4 Decisión de inversión (Comité)
1. Objetivo: veredicto explicable sobre una oportunidad. 2. Owner: USER; Copilot **C** (momento 2).
3. Estados: C. 4. Usuario: pedir análisis, leer comité, pedir Q&A (D). 5. Copilot: recomendación
PROCEED/…/REJECT con evidencia. 6. Autorización: "avanzar operación" (C→E). 7. Al salir: decisión
persiste (`decision_id`). 8. Sin acción: muestra el veredicto. 9. Siguiente: Autorización de
acercamiento. 10. Motores: **Investment Decision Engine** (+ los que consume).

### 9.5 Autorización de acercamiento
1. Objetivo: obtener el "sí" antes de contactar. 2. Owner: **COPILOT** (Director, momento 3).
3. Estados: **E**. 4. Usuario: autorizar / rechazar / ajustar. 5. Copilot: explicar qué hará y pedir
permiso; **no ejecuta** sin "sí". 6. Autorización: **obligatoria** (contactar = efecto externo).
7. Al salir sin autorizar: no se hace nada. 8. Sin acción: espera; no ejecuta. 9. Siguiente: Ejecución
(F) → Operación. 10. Motores: Matching, Investment Decision.

### 9.6 Ejecución del acercamiento
1. Objetivo: ejecutar lo autorizado. 2. Owner: COPILOT (F, momento 4 al terminar). 3. Estados: **F**→B("hecho")→A.
4. Usuario: seguir progreso, cancelar. 5. Copilot: ejecutar, informar del resultado. 6. Autorización:
ya concedida en 9.5 (no se re‑pregunta). 7. Al salir: acción continúa/queda registrada. 8. Sin acción:
progresa sola. 9. Siguiente: Operación. 10. Motores: acción + registro.

### 9.7 Operación / Deal
1. Objetivo: gestionar la transacción. 2. Owner: **USER**. 3. Estados: A, C (asesor). 4. Usuario:
conducir el proceso, documentos, fases. 5. Copilot: recomendar (valoración, estructura), sin tomar el
control. 6. Autorización: cada acción externa vuelve a pasar por E. 7. Al salir: persiste. 8. Sin
acción: estado del deal. 9. Siguiente: cierre. 10. Motores: Valuation, Investment Decision, Documentos.

### 9.8 Cartera / Watchlist
1. Objetivo: vigilar el conjunto. 2. Owner: USER. 3. Estados: A→B (nuevo riesgo/hito). 4. Usuario:
revisar, comparar, priorizar. 5. Copilot: avisar de cambios (B); recomendar rebalanceo (C). 6.
Autorización: ninguna para ver. 7/8/9/10: persiste · feed estático · Empresa/Decisión · Portfolio
(Investment Decision), Signal.

---

## 10. Encaje en la arquitectura (la gramática que faltaba)

```
Fuentes → Data Layer → Intelligence Engines → API → [ CIM: gramática de interacción ] → Copilot → Pantalla → Usuario
```

Hasta ahora había arquitectura, entidades, motores y pantallas — pero **faltaba la gramática de la
interacción**. Este documento la fija. Consecuencia práctica:

- **Claude Design** deja de decidir cuándo el Copilot habla/calla/manda: aplica §2–§6 y rellena el
  contrato §7 en cada pantalla.
- El catálogo de componentes gana un componente transversal: el **Copilot**, con sus 6 estados como
  variantes visuales (A invisible, B aviso, C tarjeta, D panel, E modal/foco, F progreso).
- Toda pantalla nueva se valida contra §7 y §8 antes de construirse.

Este documento es, a efectos de producto, **tan importante como el catálogo de componentes**.
