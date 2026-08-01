# ARROBA — Copilot: Memoria, Sesiones y Personalización (CANON v1.0)

> Cómo ARROBA Copilot **recuerda**, mantiene **continuidad** y se **adapta** a cada usuario y perfil.
> Capa fina **entre las sesiones y el Orquestador** (`ARROBA_COPILOT_ORCHESTRATOR.md`): NO toca los
> motores. Convive con el CIM (estados), la Arquitectura Cognitiva (voz única) y la constitución del
> Comité.
>
> **Principio inviolable:** la memoria personaliza *qué se muestra, el tono y las prioridades, y el
> nivel de autonomía*. **Nunca inventa hechos, nunca altera la evidencia ni los scores del comité**
> (más allá de los pesos por perfil de comprador, que ya son config legítima). Fact‑lock y
> determinismo se preservan.

Estado: CANON · `copilot-memory-v1` · documento (el código llega después, por fases §9).

**Decisiones tomadas (Daniel, 2026-07-31):** memoria **por usuario** (no compartida por equipo) ·
nivel de autonomía por defecto **1 · Informa** · sesión **hasta cerrar sesión de login** (sin TTL por
inactividad). Ver §10.

---

## 0. Principios

1. **Fact‑lock por encima de la memoria.** La memoria puede sesgar el orden y el tono; jamás crea un
   "PROCEDER" que el comité no soportó, ni una cifra que no exista.
2. **Determinismo del núcleo.** El comité y los scores siguen siendo reproducibles; la personalización
   actúa *alrededor* (surfacing, redacción, autonomía), no dentro del cálculo.
3. **Aislamiento por tenant.** Toda memoria está particionada por `tenant_id` (y `user_id`). Nunca se
   cruzan datos entre clientes.
4. **Privacidad y minimización.** No se guardan datos personales sensibles; se guardan **preferencias,
   feedback y punteros a decisiones**, no copias de dato financiero (eso vive en los motores).
5. **Trazable y reversible.** Todo lo aprendido es explicable ("subo compañías farma porque descartaste
   3 de retail"), auditable, exportable y **borrable** (derecho al olvido).
6. **Transparencia con el usuario.** El usuario puede ver y editar lo que el Copilot "cree saber" de él
   (mandato, preferencias, nivel de autonomía).

---

## 1. Modelo de memoria — por niveles (no una sola bolsa)

### 1.1 Memoria de trabajo (sesión) — corto plazo
Contexto vivo de la conversación actual: entidad activa, último `decision_id`, últimos resultados,
estado CIM pendiente, hilo de turnos. TTL corto (ver §2). Permite resolver referencias implícitas
("¿y sus riesgos?" → la última empresa).

### 1.2 Memoria de usuario — largo plazo (por usuario, no por equipo)
Ámbito **por usuario** (`tenant_id + user_id`): dos analistas del mismo tenant no comparten memoria.
Lo que define a *este* usuario/comprador de forma estable:
- **Mandato** (sector/tamaño/geografía objetivo), **umbral de riesgo**, **tesis**.
- **Perfil de comprador** por defecto (PE/estratégico/family office/…) y **rol de usuario** (§3).
- **Nivel de autonomía** deseado (§3.3).
- **Preferencias de comunicación** (idioma, verbosidad, formato preferido).
Se usa para **sesgar el Orquestador** (qué prioriza) y **seleccionar los pesos** del comité por perfil.

### 1.3 Memoria de entidad — por compañía
Histórico por empresa: decisiones previas (`decision_id`), **cambios de banda entre análisis**
(p. ej. de EXPLORE→PROCEED al mejorar el margen), notas del asesor, hitos/alertas vistas. Base ya
existente: `investment_decisions` (`store.py`). Permite "esta empresa mejoró desde la última vez".

### 1.4 Memoria de feedback / aprendizaje
Qué recomendó el Copilot y **qué hizo el usuario** (aceptó/descartó/ignoró) y, si se conoce, el
**resultado**. Patrón ya presente en `services/engines/recommendation/memory.py`. Alimenta un **sesgo
de ranking versionado y acotado** (§8): nunca un peso arbitrario; siempre explicable y con tope.

### 1.5 Memoria episódica / resúmenes (futuro)
Resúmenes comprimidos de conversaciones pasadas (para no recargar el prompt). Opcional en v1; si se
usa, con fact‑lock (resume lo dicho, no inventa).

---

## 2. Modelo de sesión

```
CopilotSession = {
  session_id, tenant_id, user_id,
  buyer_profile,                # perfil en vigor en esta sesión (puede override el de usuario)
  working_context: {            # memoria de trabajo (§1.1)
     active_entity: {company_id|cif, name}?,
     last_decision_id?, last_level?, last_intent?,
     pending_cim_state?         # p. ej. "E" (autorización pendiente)
  },
  turns: [ {ts, user_text, intent, level, answer_ref, sources} ],   # hilo (acotado / resumible)
  created_at, updated_at, status   # status: active | closed
}
```

- **Ciclo de vida:** se crea al primer `/ask` sin `session_id`; se actualiza en cada turno; **vive
  mientras la sesión de login esté activa** y se marca `closed` al cerrar sesión (sin TTL por
  inactividad). Una sesión `closed` no se reanuda: un nuevo login abre una sesión nueva (la memoria
  de usuario, §1.2, sí persiste).
- **Continuidad:** el Orquestador lee `working_context` para resolver referencias y para retomar un
  estado CIM pendiente (una autorización a medias).
- **Multi‑dispositivo:** la sesión vive en servidor (Mongo), no en el cliente.
- **Enganche LLM:** el `session_id` se pasa al `model_provider` (ya lo soporta) para trazar la
  narrativa.

---

## 3. Personalización — tres ejes distintos (no confundir)

### 3.1 Perfil de comprador (ya existe)
PE/estratégico/family office/search fund/holding/corporate venture → **modula los pesos del comité**
(`BUYER_PROFILE_WEIGHTS`, validado) y el **surfacing** del Orquestador. La memoria solo aporta *cuál*
es el perfil por defecto del usuario.

### 3.2 Rol de usuario / persona
Analista · Partner/Director · Inversor · Asesor. Cambia:
- **Verbosidad** (analista: detalle y evidencia; partner: síntesis ejecutiva).
- **Capacidades ofrecidas** (quién puede lanzar acciones con efecto externo).
- **Densidad de la UI** y qué tarjetas se muestran por defecto.

### 3.3 Nivel de autonomía del Copilot (clave)
Escala explícita, ligada al CIM (cuándo aparece / toma el control). **Por defecto: nivel 1 · Informa**
(el usuario puede subirlo explícitamente):

| Nivel | Nombre | Comportamiento |
|---|---|---|
| 0 | **Silencioso** | Solo responde si se le pregunta (D). Nunca proactivo. |
| 1 | **Informa** | Avisa de hechos/riesgos (B). No propone acciones. |
| 2 | **Propone** | Recomienda decisiones (C). El usuario ejecuta. |
| 3 | **Ejecuta con permiso** | Puede llegar a Director (E) y, tras autorización, Ejecutor (F). |
| 4 | **Autónomo acotado** | Ejecuta por su cuenta **solo acciones sin efecto externo** (p. ej. re‑analizar cartera). |

**Tope de seguridad, por encima del nivel:** cualquier acción con **efecto externo** (contactar,
enviar, publicar, mover dinero) **siempre** pasa por autorización explícita (E), sea cual sea el nivel.
La autonomía nunca salta el gate de seguridad.

### 3.4 Aprendida (feedback)
Con el tiempo, el feedback (§1.4) ajusta el **ranking** y los **umbrales de alerta** — acotado,
versionado y explicable (§8).

---

## 4. Flujo con memoria y sesión

```
/ask {session_id?, user, question, ...}
   ↓ carga/crea sesión (§2) + memoria de usuario (§1.2)
   ↓ resuelve referencias con working_context (entidad activa, etc.)
   ↓ ORQUESTADOR: clasifica intención → nivel L0–L4, sesgado por perfil/mandato/autonomía
   ↓ ejecuta (motores/comité/capacidades) — fact-lock, determinista
   ↓ VOZ: redacta según rol/verbosidad (tono), respetando banda/score
   ↓ actualiza sesión (turno) + memoria (entidad, feedback pendiente)
Respuesta {answer, cim_state, session_id, sources, personalization_applied}
```

`personalization_applied` documenta qué se aplicó (perfil, rol, autonomía, sesgos) → transparencia.

---

## 5. Colecciones (Mongo) — propuesta

| Colección | Contenido | Clave |
|---|---|---|
| `copilot_sessions` | §2 CopilotSession | `session_id` (+ índices tenant/user, status) |
| `copilot_user_memory` | §1.2 preferencias/mandato/rol/autonomía | `(tenant_id, user_id)` |
| `copilot_entity_memory` | §1.3 histórico por compañía | `(tenant_id, user_id, company_id)` |
| `copilot_feedback` | §1.4 eventos accept/dismiss/outcome | `event_id` (+ índices) |

Memoria **por usuario**: todas las colecciones llevan `user_id` en la clave (además de `tenant_id`).
`tenant_id` obligatorio en cada consulta.

---

## 6. Privacidad, seguridad y gobernanza
- **Aislamiento por tenant** en cada consulta (nunca sin `tenant_id`).
- **No PII sensible** (nada de datos personales protegidos; solo preferencias de negocio + punteros).
- **Auditoría**: cada escritura de memoria de aprendizaje queda registrada (qué, por qué).
- **Retención** configurable; **export** y **borrado** por usuario (derecho al olvido).
- **Editable por el usuario**: puede ver/editar mandato, preferencias y nivel de autonomía.

---

## 7. Invariantes (no se rompen)
- Memoria **no** fabrica hechos ni cambia scores/evidencia del comité.
- Autonomía **no** salta el gate de autorización de acciones con efecto externo.
- Personalización **explicable**: siempre se puede decir por qué se priorizó/omitió algo.
- Determinismo del núcleo intacto; solo varían orden, tono y proactividad.
- Aislamiento estricto por tenant.

---

## 8. Bucle de aprendizaje (feedback → mejora), acotado y explicable
- Señales: `accept` (usó la recomendación), `dismiss` (la descartó), `ignore`, `outcome` (resultado real).
- Efecto: ajusta un **sesgo de preferencia versionado** (p. ej. `pref_bias[sector]`, `pref_bias[tamaño]`)
  con **tope ±10 %** y **decaimiento a 90 días**; se aplica **solo al surfacing/ranking**, nunca al
  score del comité. Las **preferencias aprendidas** del comportamiento comparten la misma caducidad de
  90 días (§10.1). Lo que el usuario configura explícitamente no caduca.
- Explicabilidad: cada sesgo lleva su origen ("−10% retail: 3 descartes en 30 días"). Reversible.
- Nunca caja negra; nada de reentrenar modelos con datos del cliente sin consentimiento.

---

## 9. Plan de implementación por fases
- **Fase 1 — Sesión + memoria de usuario:** `services/copilot/session.py` + `memory.py`
  (`copilot_sessions`, `copilot_user_memory`); el Orquestador lee sesión y preferencias; `/ask` acepta
  `session_id` y `user`. Continuidad de referencias. Tests.
- **Fase 2 — Personalización:** rol de usuario + nivel de autonomía (mapeado al CIM) + tono/verbosidad
  en la voz. `personalization_applied` en la respuesta.
- **Fase 3 — Memoria de entidad:** histórico por compañía + diferencias entre análisis ("mejoró desde…").
- **Fase 4 — Feedback/aprendizaje:** captura de accept/dismiss + sesgo de ranking acotado y explicable.
- **Fase 5 — Gobernanza:** export/borrado, panel "lo que sé de ti", auditoría, retención.
- **Futuro:** memoria episódica/resúmenes con fact‑lock.

---

## 10. Decisiones (Daniel, 2026-07-31)
1. **Ámbito de la memoria de usuario:** ✅ **por usuario** (`tenant_id + user_id`). No compartida por
   equipo. (Multi‑usuario/equipo queda como toggle futuro, fuera de v1.)
2. **Nivel de autonomía por defecto:** ✅ **1 · Informa**. El usuario puede subirlo explícitamente.
3. **Sesión:** ✅ **hasta cerrar sesión de login** (sin TTL por inactividad); `status: active|closed`.
4. **Multi‑usuario en un mismo mandato:** ✅ descartado en v1 (coherente con "por usuario").

### 10.1 Política de retención (✅ Daniel)

| Información | ¿Caduca? | Uso |
|---|---|---|
| **Configurado por el usuario** (mandato, umbral de riesgo, perfil, nivel de autonomía, idioma) | ❌ Nunca (hasta que él lo cambie) | Ajustes explícitos |
| **Histórico de la empresa** (operaciones, directivos, adquisiciones, resultados, decisiones/bandas) | ❌ Nunca | Memoria permanente |
| **Preferencias aprendidas** de un comprador/usuario (del comportamiento) | ✅ Sí (90 días) | Personalización |
| **Sesgo aprendido** del algoritmo | ✅ Sí (90 días, máximo **±10 %**) | Ajuste fino del ranking/surfacing |

> **Distinción clave:** lo que el usuario *configura* persiste hasta que lo cambie; lo que el sistema
> *aprende* de su comportamiento (preferencias y sesgo) **decae a 90 días** y el sesgo está topado a
> ±10 %. Nada de esto toca el score del comité (solo el orden/tono/prioridad).
