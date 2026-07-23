# PLATFORM_GOVERNANCE_AND_CONSUMER_AUDIT.md
**Gobernanza de plataforma compartida + Auditoría de consumidores por módulo**
_Versión: `governance-v1` · 2026-06-26 · Estado: **VIGENTE (política de obligado cumplimiento)**._

> **Agency Tool ya NO es un proyecto: es una plataforma compartida en producción.**
> Consumidores actuales:
> - **Valuo.pro** — PRODUCCIÓN. Dependencia crítica viva.
> - **arroba.com** — nuevo consumidor (Intelligence Engines + Transaction OS).
> - **Platform Console** — panel administrativo interno (frontend de este repo).
>
> Cualquier cambio debe superar la **Pregunta de Compatibilidad** (§1) antes de aprobarse.

---

## 1. Política de cambio (obligatoria)

### Pregunta de Compatibilidad
> **¿Este cambio mantiene la compatibilidad con TODOS los consumidores actuales (Valuo.pro, arroba.com, Platform Console)?**
Si la respuesta no es un **sí** demostrable, el cambio **no se aprueba** como está.

### Reglas
1. **Prohibido** eliminar, renombrar o cambiar el contrato (request/response, status codes, semántica) de cualquier módulo que sirva a un consumidor en producción.
2. **Backward compatibility por defecto**: los cambios deben ser **aditivos** (nuevos campos opcionales, nuevos endpoints, nuevas versiones) — nunca incompatibles.
3. **Convivencia obligatoria**: implementación antigua y nueva coexisten **hasta que todos los consumidores hayan migrado y validado**. La migración se cierra solo con evidencia (tests verdes + confirmación del consumidor).
4. **Versionado, no ruptura**: un cambio incompatible exige nueva versión (`/v2`, `*-v2`) conviviendo con la anterior; las operaciones/datos en curso no migran salvo migración explícita, idempotente y auditada.
5. **Solo los módulos clasificados como `Obsoleto`** (§3) pueden **proponerse** para eliminación — y la eliminación requiere confirmación explícita del owner + verificación de cero consumidores.
6. Toda migración legacy→canónico se hace **detrás del mismo contrato externo**: el consumidor no debe notar el cambio de implementación.

### Esquema de clasificación
| Clase | Significado | ¿Se puede tocar/eliminar? |
|---|---|---|
| **Canónico** | Implementación definitiva y permanente. | Evolución aditiva sí; ruptura no. |
| **En convivencia** | Puente activo entre legacy y canónico, o usado por varios consumidores. | Mantener ambos caminos; no romper ninguno. |
| **Legacy crítico** | Consumido por **Valuo.pro producción**. | **NO TOCAR** sin compatibilidad + validación del consumidor. |
| **Obsoleto** | Sin consumidores reales verificados. | Único candidato a eliminación (previa confirmación). |

---

## 2. Mapa de consumidores (superficie real)

### 2.1 Dos capas de datos en convivencia (núcleo de la migración)
| Capa | Colección | Escritores | Lectores / Consumidor |
|---|---|---|---|
| **Legacy** | `companies_master` | `intelligence_engine/linker`, `entity_resolution`, `valuo_enrichment`, `iberinform_processor`, `signal_engine` (antiguo), `publication`, `routes/master`, `taxonomy_embeddings` | **Valuo.pro** (vía `/api/v1/valuo/*`, `/api/v1/intelligence/enrich?profile=valuo`, `/api/v1/companies/*/enriched`), Platform Console, skills | **LEGACY CRÍTICO** |
| **Canónico** | `master_companies` (Master/Foundation Layer) | `data_layer/master/master_builder` (rebuild desde fuentes normalizadas) | **arroba.com** (vía los 6 Intelligence Engines + Transaction OS) | **CANÓNICO** |

> Ambas colecciones conviven hoy. La migración consiste en que los consumidores legacy pasen progresivamente a leer del Master Layer canónico **detrás de su contrato actual**, sin que Valuo.pro lo perciba.

### 2.2 Contratos externos por consumidor
- **Valuo.pro →** `POST /api/v1/valuo/request-update-from-valuo`, `GET /api/v1/valuo/request-update-status/{id}`, `GET /api/v1/valuo/health`, `GET /api/v1/companies/by-valuo-id/{valuo_id}/enriched`, `POST /api/v1/intelligence/enrich` (`profile=valuo`). **Auth propia de Valuo.**
- **arroba.com →** `/api/v1/financial-intelligence/*`, `/api/v1/signal-intelligence/*`, `/api/v1/semantic-intelligence/*`, `/api/v1/recommendation-intelligence/*`, `/api/v1/strategy-intelligence/*`, `/api/v1/transaction-intelligence/*`. **Auth `X-API-Key` (`ARROBA_SERVICE_API_KEY`).**
- **Platform Console →** resto de rutas administrativas (master, sources, jobs, taxonomy, editorial, stats, etc.) con **JWT** de usuario.

### 2.3 Modelo de perfiles (desacople por producto, ya existente)
`services/intelligence_engine/profiles.py` define `basic | valuo | arroba`. Añadir un producto = añadir un perfil; **no** se modifica el engine. Este patrón es **Canónico** y debe preservarse como mecanismo de aislamiento entre consumidores.

---

## 3. Auditoría de módulos (clasificación)

### 🟢 Canónico (implementación definitiva)
| Módulo | Consumidor | Notas |
|---|---|---|
| `services/data_layer/` (Foundation/Master Layer, `master_companies`) | arroba (motores) | Única fuente de verdad de identidad canónica. |
| `services/engines/financial` + `routes/financial_intelligence` | arroba | `financial-intelligence-v1`. |
| `services/engines/signal` + `routes/signal_intelligence` | arroba | `signal-intelligence-v1` (sustituye a `services/signal_engine.py` antiguo). |
| `services/engines/semantic` + `routes/semantic_intelligence` | arroba | `semantic-intelligence-v1`. |
| `services/engines/recommendation` + `routes/recommendation_intelligence` | arroba | `recommendation-intelligence-v1`. |
| `services/engines/strategy` + `routes/strategy_intelligence` | arroba | `strategy-intelligence-v1` (entidad `strategic_theses`). |
| `services/transaction_os` + `services/engines/transaction` + `routes/transaction_intelligence` | arroba | `transaction-os-v1` / `transaction-intelligence-v1` (Sprint 7). |
| `services/service_auth.py` | arroba | Auth de servicio `X-API-Key`. |
| `services/intelligence_engine/profiles.py` | todos | Mecanismo de aislamiento por producto. |

### 🟡 En convivencia (puente legacy↔canónico / multi-consumidor)
| Módulo | Consumidores | Acción |
|---|---|---|
| `services/intelligence_engine/` (engine, linker, sources) | Valuo (profile=valuo) + arroba (profile=arroba) | Camino de enriquecimiento compartido sobre `companies_master`. Mantener; migrar lectura a Master Layer **sin cambiar contrato**. |
| `routes/master.py` (`/api/v1/master`, escribe `companies_master`) | Platform Console + tests | Convive con `master_companies`. No unificar sin compat. |
| `services/entity_resolution.py` | Valuo + intelligence_engine | Resolución de identidad sobre `companies_master`. Convive con `data_layer/master/entity_resolution.py`. |
| `services/data_layer/ingestion/*` + `normalize.py` + `accessors.py` | Master Layer | Alimentan `master_companies`; conviven con ingestas legacy. |
| `routes/data_layer.py` (importa `signal_engine` antiguo) | Platform Console | Atado al signal_engine legacy; migrar a `engines/signal` con cuidado. |

### 🔴 Legacy crítico (Valuo.pro PRODUCCIÓN — NO TOCAR sin compat)
| Módulo | Por qué es crítico |
|---|---|
| `routes/valuo_integration.py` (`/api/v1/valuo/*`) | Punto de entrada directo de Valuo.pro. Contrato congelado de facto. |
| `routes/enriched_company.py` (`/by-valuo-id/{id}/enriched`) | Valuo lee el perfil enriquecido por su propio id. |
| `services/valuo_enrichment.py` | Lógica de enriquecimiento que sirve a Valuo. |
| `routes/intelligence_engine.py` (`/api/v1/intelligence/enrich`, `profile=valuo`) | Enriquecimiento on-demand de Valuo. |
| Colección `companies_master` y sus escritores | Estado vivo del que depende Valuo.pro. |
| `services/skills_*` + `routes/skills.py` + `routes/enrich_company.py` | Capacidades consumidas por el flujo actual; verificar consumidor antes de migrar. |

### ⚪ Obsoleto (candidato a eliminación — requiere confirmación)
| Módulo | Estado | Recomendación |
|---|---|---|
| (ninguno confirmado) | — | **A fecha de hoy NO se identifica ningún módulo seguro para eliminar.** |
| `sources/{oepm,patentes,catastro,boe}.py` | **Stubs** (no obsoletos): referenciados por el perfil `arroba`. | **NO eliminar.** Son incompletos/pendientes de implementar, no obsoletos. Reclasificar a Canónico al implementarse. |
| `services/signal_engine.py` (antiguo) | Aún importado por `skills_recommend` y `routes/data_layer`. | **NO eliminar.** Mantener hasta migrar esos 2 consumidores a `engines/signal`, luego reevaluar. |

> **Conclusión de la auditoría inicial: 0 módulos elegibles para eliminación.** Todo lo existente es Canónico, En convivencia o Legacy crítico. Cualquier propuesta futura de borrado pasará por reverificación de consumidores.

---

## 4. Plan de migración legacy→canónico (compatibilidad primero)
1. **Inventario de contratos externos** (hecho aquí): congelar el comportamiento observable de cada endpoint Legacy crítico.
2. **Tests de contrato (golden) por consumidor** antes de migrar: capturar request/response actuales de `/api/v1/valuo/*`, `/intelligence/enrich?profile=valuo`, `/companies/by-valuo-id/*` como regresión.
3. **Migración interna detrás del contrato**: redirigir lectura de `companies_master` → Master Layer canónico **sin** cambiar la respuesta externa. Validar contra los golden tests.
4. **Convivencia + feature flag**: permitir alternar implementación antigua/nueva por consumidor durante la transición.
5. **Validación del consumidor** (Valuo.pro) y solo entonces marcar el camino legacy como migrado.
6. **Deprecación** (no borrado) tras migración total y periodo de gracia; borrado solo previa confirmación explícita.

---

## 5. Checklist por cada cambio (pegar en cada PR/sprint)
- [ ] ¿Afecta a un módulo `Legacy crítico` o `En convivencia`? → exige plan de compatibilidad.
- [ ] ¿El cambio es aditivo (no rompe contratos existentes)?
- [ ] ¿Existen tests de regresión para los consumidores afectados (Valuo.pro, arroba, Console)?
- [ ] ¿Convive la implementación antigua hasta validar la nueva?
- [ ] ¿Se ha respondido la **Pregunta de Compatibilidad** con evidencia?
- [ ] ¿La suite smoke completa sigue verde y sin regresiones?

---

## Resultado
Esta política y auditoría establecen que **Agency Tool es infraestructura compartida en producción**. Hasta nueva orden: **no se elimina nada**, toda evolución es **aditiva y con convivencia**, y cada cambio debe demostrar compatibilidad con Valuo.pro, arroba.com y Platform Console.
