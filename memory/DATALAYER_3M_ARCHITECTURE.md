# Arquitectura Industrial del Data Layer — Iberinform 3,3M (diseño, NO implementación)
_Fecha: 2026-06-24 · Fuente de verdad: muestra real `20260519_Data_ES_Muestra` · Pensado como CDO + arquitecto MongoDB + Data Layer de PitchBook/Capital IQ/Bloomberg_

> Principio: **toda la complejidad vive en el Data Layer; arroba.com consume entidades e inteligencia, nunca fuentes.** Y: nunca exponer una capa cuya calidad aparente supere la del dato real.

---

## 0. Lo que REALMENTE contiene la muestra (verificado fila a fila)

8 ficheros CSV (sep `;`, encoding mixto UTF-8/latin-1) + diccionario `.xlsx`. Dos naturalezas:

**A) Fichero ANCHO — maestro de empresa** (`ES_Company_Data_Valu8.csv`, 36 cols, 1.000 filas):
`ID_FIRMA` (id interno Iberinform), `CIF` (=NIF), `DENOMINACION`, `TITULO_COMERCIAL`, `SIGLA`, `CNAE`+`DESCRIPCION_CNAE`, `WEB`, **`OBJETO_SOCIAL` (2.000 chars — oro para embeddings)**, `VENTAS`, `CAPITAL_SOCIAL`, desglose de empleados (fijos/temporales/género), `SIT_MERCANTIL`, `AUDITADO`, dirección (`DOMICILIO`/`CP`/`MUNICIPIO`/`PROVINCIA`), `PAIS`, `MODELO_BALANCE`, `ULT_EJERCICIO_BALANCE`.

**B) Ficheros LARGOS — formato EAV** (clave común `ES_IberinformID`=ID_FIRMA + `ES_NIF` + `Year` + `ES_Account_ID` + `ES_Account_number` + `ES_Account_Name` + `Amount_Eur`):
| Fichero | Filas (muestra) | Semántica del EAV |
|---------|----------------|--------------------|
| `ES_Financial_Detail_Valu8` (Ordin) | 94.454 (373 empresas) | **Estados financieros completos**: `Account_number`=código contable (10000=Total Activo…), `Amount_Eur`=importe, por `Year`. **~253 filas/empresa**. Incluye ratios ya calculados (Ebitda/sales, Margin on sales…). |
| `ES_Financial_Detail_Conso` | 4.556 | Igual, **consolidado** (grupos). |
| `ES_Org_Social_Data_Valu8` (+_Empr_Activas) | 3.500 | **Órganos sociales / cargos**: `Account_number`=rol (Administrador Único, Apoderado, Consejero, Auditor…), `Account_Name`=persona, `Appointment_Date`. ~3,5 cargos/empresa. |
| `ES_Vinculaciones_Data` (Ordin/Conso) | 412 | **Grafo de propiedad**: `Account_ID` ∈ {`PARENT_CO`, `ULTIMATE_PARENT_CO`, `INVESTEE_CO`, `SHAREHOLDER`}; `Account_number`=CIF de la contraparte; `Account_Name`=razón social; `Amount_Eur`=**% participación**. |
| `ES_Matriz_Accionistas_Data` (_Empr_Activas) | 115 | **Accionariado** activo: SHAREHOLDER + ULTIMATE_PARENT_CO con %. |

**Hallazgos clave para el diseño**:
1. **CIF/NIF es la clave de join universal y fiable** (overlap empresa↔financiero = 373/373 exacto). `ID_FIRMA` y `ES_IberinformID` coinciden en org/vinculaciones, pero **no asumir** mismo espacio de id entre todos los ficheros → **unir SIEMPRE por CIF normalizado**.
2. **La propiedad (ownership) YA viene como dato real** (Vinculaciones + Matriz) → `shareholder_of/parent_of/subsidiary_of/ultimate_parent` se **materializan directamente, O(E)**, sin cómputo. Esto desbloquea P5 sin O(n²).
3. **Contrapartes extranjeras sin CIF** (p.ej. "SCANIA SALES AND SERVICES AB", "SERVIER INTERNATIONAL BV") → nodos de **entidad externa** (no empresa española completa).
4. **El financiero es el volumen dominante**: 9,78 MB/373 empresas. Extrapolado a 3,3M (con ~37% cobertura detalle observada) → **~30 GB de CSV solo financiero ordinario** y **cientos de millones de filas EAV**. Es el dimensionante.

---

## 1. Arquitectura de capas (validada y corregida)

La cadena propuesta es **correcta**, con una precisión crítica: el Raw Layer NO debe materializar el EAV financiero fila-a-fila en Mongo (cientos de millones de docs minúsculos). Se pivota a **documento por entidad-año** en Normalized.

```
FUENTES (Iberinform CSVs, BORME, CNMV, PLACSP, BME, grants…)
      │  (object storage = landing inmutable de ficheros originales + manifest)
      ▼
RAW LAYER  ── auditoría/replay, 1:1 conceptual con la fuente
      ▼
NORMALIZED LAYER  ── tipado, canónico por fuente, pivotado EAV→entidad
      ▼
MASTER LAYER  ── entity resolution cross-source (companies_master + xref)
      ▼
ANALYTICS LAYER  ── embeddings, signals, relationships (rebuildable)
      ▼
INTELLIGENCE ENGINES  ── Search / Value / Recommend / Analyze / Signal / KG
      ▼
arroba.com  ── consume entidades e inteligencia (NUNCA fuentes)
```

### Colecciones por capa, claves y responsabilidades

**RAW (inmutable, append-only, auditable, versionado por entrega)**
- Landing físico de los CSV originales → **object storage** (no Mongo), + `raw_ingestion_manifest` {batch_id, file_name, source_version=`20260519`, source_hash (sha256 del fichero), rows, bytes, encoding, ingested_at, status}.
- `raw_company` (1 doc/fila del fichero ancho, tal cual + `batch_id` + `row_hash`). PK: (`source`, `ID_FIRMA`, `source_version`).
- EAV (financiero/org/vinculaciones): **NO** un doc por fila. Se aterriza ya pivotado en Normalized (ver abajo) leyendo el CSV ordenado. (Si se quiere replay puro, basta el fichero en object storage + manifest.)
- Responsabilidad: **conservar el original exacto** para replay/auditoría. Nunca se lee desde engines.

**NORMALIZED (canónico por fuente, tipado, pivotado)**
- `norm_company` — PK `cif_normalized`. Campos tipados: legal_name, commercial_name, cnae_code/section, address, province_code, employees, capital, objeto_social, web, sit_mercantil, audited, country, last_balance_year. + `source_version`, `source_hash`, `pipeline_version`.
- `norm_financials` — **PK compuesta `(cif_normalized, year, basis)`** con `basis ∈ {individual, consolidated}`. Doc = un estado financiero: `accounts: {<account_number>: amount}` (mapa) + `derived: {revenue, ebitda, ebitda_margin, net_income, equity, total_assets, employees}` (extraídos por catálogo de códigos) + `fiscal_close_date`. **Pivot EAV→doc/empresa-año** ⇒ de ~900M filas a ~10M docs.
- `norm_officers` — PK `(cif_normalized, person_key, role, appointment_date)`. person_key = name_key de la persona.
- `norm_ownership` — **arista PK `(src_cif, dst_cif, type, year)`**, type ∈ {shareholder_of, parent_of, subsidiary_of, ultimate_parent_of, investee_of}, `pct`, `counterparty_name`, `counterparty_has_cif`. Origen directo de Vinculaciones+Matriz.
- Responsabilidad: **una verdad por fuente**, sin entity resolution cross-source todavía.

**MASTER (entity resolution cross-source — la "single source of truth")**
- `companies_master` — PK surrogate `master_company_id` (estable, ya existe `mc_…`) + clave natural `cif_normalized` (única). Fusiona norm_company (Iberinform) + sources.web (scraping) + BME + … Mantiene `classification`, `financials` (proyección de norm_financials latest+history), `ownership` (resumen desde norm_ownership), `confidence_score`, `lineage` por campo, `pipeline_version`, `built_at`, `dirty`.
- `entity_xref` — **mapa de identidades** PK `(source, source_id)` → `master_company_id`. Guarda ID_FIRMA↔CIF↔isin(BME)↔valuo_id. **Imprescindible para joins incrementales a escala** (evita re-resolver).
- `persons_master` (futuro) — directivos resueltos como entidades persona.
- Responsabilidad: identidad única, merge no-destructivo, linaje.

**ANALYTICS (derivado, 100% reconstruible, versionado por capa)**
- `company_embeddings` (vector BinData float32 + cluster_id + embed_version).
- `company_signals` o `signals[]` embebido (signal_version).
- `company_relationships` (KG: ownership real O(E) + similarity con blocking).
- Responsabilidad: capas caras y volátiles, separadas del master para poder regenerarlas selectivamente.

---

## 2. Ingestión de 3,3M (visión de arquitecto MongoDB)

- **Streaming siempre**: leer CSV por filas con cursor (`csv.reader`), nunca `list()` completo en RAM. El fichero financiero llega ordenado por (IberinformID, Year, Account) ⇒ **sort-merge pivot**: acumular filas de una misma (empresa, año) y emitir 1 doc al cambiar de clave. RAM acotada a una empresa-año.
- **bulk_write con `ordered=False`**, lotes de **1.000–5.000 ops** (equilibrio entre overhead de red y límite BSON de 48 MB/lote; con docs de financiero ~2–4 KB, 2.000 es buen punto). `UpdateOne(upsert=True)` por clave natural ⇒ idempotente y re-ejecutable.
- **Preloads acotados**: solo catálogos pequeños en RAM (CNAE secciones/divisiones, mapa de account_number→métrica canónica, mapa provincia→código). **Jamás** precargar empresas/financieros.
- **Throughput esperado**: bulk_write upsert ~10–30k docs/s en replica set local sano ⇒ master (3,3M) en **minutos**; financieros (~10M docs entidad-año) en **decenas de minutos**. La ingesta cruda del CSV (~30 GB) es I/O-bound: planificar ventana.
- **Consumo de RAM objetivo**: O(batch) + O(catálogos) = decenas de MB. Independiente del tamaño total.
- **Tamaños proyectados a 3,3M** (extrapolando avgObjSize medido + densidad de muestra):
  | Colección | Docs | Tamaño aprox |
  |-----------|------|--------------|
  | companies_master | 3,3M | ~17 GB |
  | norm_financials (entidad-año) | ~10M | ~6–10 GB |
  | norm_ownership (aristas) | ~1,5M | ~0,6 GB |
  | norm_officers | ~11M | ~3 GB |
  | company_embeddings (BinData) | 3,3M | ~1,7 GB |
  | company_relationships | ~33–53M | ~15–28 GB |
  | **Total** | | **~50–65 GB** |
- **Sharding** (diseñar ahora, activar a decenas de millones): NO usar `ID_FIRMA` (monótono → hotspot de escritura). 
  - `companies_master`: **hashed(`cif_normalized`)** (distribución uniforme de escritura).
  - `norm_financials`: **compuesta `{cif_normalized:1, year:1}`** (co-localiza los años de una empresa → consultas de historia eficientes).
  - `company_relationships`: shard por `source_master_company_id`.
  - A 3,3M / ~60 GB un **replica set único basta** (no shardear todavía); el diseño de shard key evita rehacer arquitectura al crecer 10×.

---

## 3. Jobs reanudables (`data_layer_jobs`)

Ningún rebuild largo dentro de un request HTTP. Endpoint encola y devuelve `job_id`; un **worker en background** (proceso/scheduler) ejecuta por lotes y persiste checkpoint.

```
data_layer_jobs {
  job_id, job_type (ingest|normalize|master|embeddings|signals|graph),
  status: queued|running|completed|failed|cancelled,
  started_at, finished_at, heartbeat_at,
  last_processed_id,          // checkpoint (cursor por _id / cif_normalized)
  processed_count, failed_count, total_estimated,
  pipeline_version, source_hash, source_version,
  params (scope: full|incremental|cif_list), error, retries
}
```
- **Checkpoint**: cursor ordenado por `_id`; tras cada lote, `last_processed_id = max(_id del lote)`. Reanudar = `find({_id: {$gt: last_processed_id}})`.
- **Idempotencia de reanudación**: como las escrituras son upsert por clave natural, reprocesar un lote ya hecho es inocuo.
- **Recovery en startup**: detectar jobs `running` huérfanos (heartbeat viejo) y re-encolar (patrón ya existente en `_recover_stuck_valuo_requests`).
- **Cancelación**: el worker comprueba `status==cancelled` entre lotes.
- Estados de terminación claros + `error` con traza acotada.

---

## 4. Incrementales

- **`source_hash` por fichero y `row_hash` por entidad** → detectar qué cambió entre entregas (la próxima será `20260xxx`). Solo se reprocesa el delta.
- **`dirty` flag + `pipeline_version` por doc** en cada capa. Un cambio en norm_company marca `companies_master.dirty=true`; el job master procesa solo `dirty=true` o `pipeline_version<N`.
- **Propagación de invalidación selectiva** (clave para no recalcular 3,3M):
  - Cambia financiero de una empresa → recalcular **sus** signals + **su** embedding (objeto_social cambia raramente) → marcar **sus** aristas de similitud para refresco.
  - Cambia ownership de una empresa → re-derivar solo **su componente de grupo** (union-find local), no todo el grafo.
  - Cambia objeto_social/cnae → recalcular embedding de esa empresa (transform, no refit) + sus vecinos top-k.
- **Rebuild selectivo por scope** en `data_layer_jobs.params`: `full | incremental(dirty) | cif_list[...]`.

---

## 5. Entity Resolution a escala (decenas de millones)

- **Determinista primero (cubre ~99%)**: `cif_normalized` = upper, sin separadores. Clave única en master ⇒ merge directo. `entity_xref` mapea ID_FIRMA/isin/valuo_id→master.
- **`name_key`**: deaccent + lower + quitar formas jurídicas (SL/SA/…) + colapsar espacios (ya implementado).
- **`aliases`**: unión de DENOMINACION + TITULO_COMERCIAL + SIGLA + nombres de scraping + razones sociales de vinculaciones.
- **Probabilístico segundo, SOLO con blocking** (jamás O(n²)): bloque = (`name_key`[:8] o token-set, `province_code`); comparar candidatos solo dentro del bloque. Para 3,3M esto es lineal en nº de bloques.
- **Entidades sin CIF** (accionistas extranjeros): nodo `external_entity` con `name_key`+`country`; NO se promueve a company_master salvo que aparezca con CIF.
- **`merge_status`/`merged_into`** no-destructivo; canónico = mayor `confidence_score`.
- **`confidence_score`** por completitud real (identidad+CNAE+financieros+web) — bimodal hoy, se equilibra con el dato real.
- **`lineage` por campo** (qué fuente puso cada valor) → auditoría tipo Bloomberg.

---

## 6. Knowledge Graph — qué es O(n²) y qué no

| Relación | Origen | Coste | Estrategia |
|----------|--------|-------|------------|
| `shareholder_of`, `parent_of`, `subsidiary_of`, `ultimate_parent_of`, `investee_of` | **Dato real** (Vinculaciones+Matriz) | **O(E)** ~1,5M | Materialización directa desde `norm_ownership`. Sin cómputo. |
| `same_group` | Derivado de ultimate_parent | **~O(V+E)** | **Union-Find / componentes conexas** sobre aristas de propiedad. Incremental por componente. |
| `similar_to`, `same_cluster` | Embeddings | **O(n²)** ❌ | **Blocking**: candidatos solo intra-cluster + **ANN top-k** (k≈10). De O(n²) a O(n·k). |

- **Ownership ya resuelve P5/P6 sin O(n²)**: el grafo de control accionarial es directo. La explosión cuadrática vive solo en la similitud semántica → se acota con cluster-first + ANN.
- **Grafo incremental**: cambio de propiedad de X ⇒ recomputar solo el componente de X (no el grafo global). `delete_many({})` global queda **prohibido**; reemplazar por upsert por arista + borrado selectivo de aristas de las entidades tocadas.
- **Aristas acotadas**: similar_to top-k por empresa ⇒ ~33M en vez de explotar.

---

## 7. Embeddings industriales (diseño, sin implementar)

- **Almacenamiento**: vector como **BSON BinData float32 empaquetado** (128×4 = 512 B) en vez de lista JSON (~1,7 KB) ⇒ 3,3M × 512 B ≈ **1,7 GB** y deserialización rápida.
- **Texto fuente**: `OBJETO_SOCIAL` (2.000 chars) + DENOMINACION + CNAE desc + tags web ⇒ corpus rico real (hoy el 96% no tenía descripción; con Iberinform real, casi todos la tienen).
- **Modelo**: entrenar TF-IDF+SVD (o modelo neuronal sustituible) sobre **muestra representativa (~200k)**; luego **transform incremental** del resto. **No refit** sobre 3,3M en cada corrida.
- **ANN**: el `semantic_top` lineal sobre 3,3M es inviable. Opciones: **Atlas Vector Search (HNSW)** gestionado, o índice **HNSW local (hnswlib/FAISS)** persistido y cargado por el worker. top-k neighbors O(log n).
- **Blocking por cluster**: generación de candidatos de similitud restringida a su cluster KMeans ⇒ alimenta el KG de forma escalable.
- Contrato de Search/Recommend **inmutable**: el ANN se inyecta internamente (mismo patrón que el LSA actual con fallback).

---

## 8. Señales — integración sin romper contratos

Cada fuente se normaliza a **hechos por empresa unidos por `cif_normalized`** y alimenta el Signal Engine (señales internas; `signals[]`/`signal_score` ya existen):
- **Ownership** (nuevo, de Iberinform): "pertenece a grupo", "filial de X", "participada extranjera", "matriz última = Y", concentración accionarial.
- **BORME**: constituciones, nombramientos, cambios de capital → eventos por CIF.
- **CNMV**: participaciones significativas, hechos relevantes.
- **PLACSP** (184k contratos): tracción comercial pública por adjudicatario (join por CIF/nombre).
- **Grants/empleo**: ayudas concedidas, dinámica de empleo sectorial/territorial.
- **M&A** (cuando haya datos reales): múltiplos y operaciones.
Todo se proyecta a `signals[]` (contrato inmutable). Los engines no cambian su firma; solo se enriquecen internamente.

---

## 9. Roadmap P0 priorizado (con criterios de aceptación)

**P0.1 — Eliminar N+1 + bulk_write + chunks + preloads** _(mayor ROI; desbloquea todo)_
- master rebuild: preload de norm_* por cif en lote; `bulk_write(ordered=False)` 2k/lote. Criterio: rebuild de la muestra sin queries por-doc; throughput ≥10k docs/s; RAM O(batch).

**P0.2 — Jobs reanudables + workers en background**
- `data_layer_jobs` + checkpoint + recovery en startup. Criterio: matar el proceso a mitad y que reanude desde `last_processed_id` sin duplicar ni reprocesar todo. Ningún rebuild en request HTTP.

**P0.3 — Versionado + dirty flags + incrementales**
- `pipeline_version`/`source_version`/`source_hash`/`dirty` por capa + propagación de invalidación. Criterio: segunda entrega reprocesa solo el delta; rebuild selectivo por `cif_list`.

**P0.4 — Índices** (crear ANTES de la carga masiva)
- master: `cif_normalized`(unique), `name_key`, `classification.cluster_id`, `signal_score`, `(name_key, province_code)` para blocking. 
- norm_financials: `(cif_normalized, year, basis)`(unique). norm_ownership: `(src_cif, dst_cif, type, year)`(unique) + `dst_cif`. 
- entity_xref: `(source, source_id)`(unique) + `master_company_id`. 
- company_embeddings: `master_company_id`(unique) (hoy solo `_id`). 
- company_relationships: `(source, target, type)`(unique, ya existe).

**P0.5 — Embeddings industriales**
- BinData float32 + train-on-sample/transform-incremental + ANN (Atlas Vector Search o HNSW local) + blocking por cluster. Criterio: `semantic_top` sin scan lineal global; RAM acotada.

**P0.6 — Knowledge Graph industrial**
- Ownership directo O(E) desde norm_ownership; `same_group` por union-find; similarity con blocking+top-k; grafo incremental (sin `delete_many({})` global). Criterio: rebuild sin O(n²); cambio de una empresa recomputa solo su componente.

**P0.7 — Streaming ingestion**
- Parseo CSV por filas + sort-merge pivot EAV→entidad-año + bulk upsert + manifest/source_hash. Criterio: ingerir el fichero financiero completo con RAM O(batch); idempotente y reanudable.

---

## Decisiones aprobadas (2026-06-25)

**D1 — El Master Record es la ÚNICA fuente de embeddings.** Nunca generar embeddings desde Raw ni Normalized. Cadena definitiva: `Fuentes → Raw → Normalized → Master → Embedding Engine → Vector Index → (Universal Search / Matching / Recommendations / Comparables / Arroba Copilot)`. Toda la inteligencia semántica consume la identidad consolidada.

**D2 — Company Semantic Profile (perfil semántico canónico).** El embedding NO se construye solo del objeto social, sino de un perfil canónico por empresa que incorpora (mínimo): objeto social · CNAE principal · CNAEs secundarios · actividades normalizadas · productos/servicios · tecnologías · marcas · sectores · localización · grupo empresarial · ownership · resumen IA · señales relevantes · histórico de operaciones · cualquier otra info estructurada del Master. ⇒ **un único embedding representativo por empresa**, reutilizado por todos los motores.

**D3 — Versionado de embeddings.** Cada embedding almacena metadatos (mínimo): `embedding_version` · `model` · `generated_at` · `sources_used` · `profile_checksum` (sha256 del Company Semantic Profile) · `status`. Permite regeneración incremental cuando cambie el modelo, el perfil, las fuentes o el pipeline, sin recalcular toda la plataforma (recalcular solo los docs cuyo `profile_checksum` cambió).

**D4 — Orden de desarrollo aprobado** (NO avanzar aún a Atlas Vector Search):
`P0.2 Jobs reanudables → Master Layer → Entity Resolution → entity_xref → Value Engine sobre financiero real → Knowledge Graph sobre ownership real → Embedding Engine sobre Master → Atlas Vector Search → Universal Search semántico`. Objetivo: **nunca generar embeddings sobre entidades no consolidadas**.

**D5 — El Embedding Engine es infraestructura compartida**, no un motor independiente. Lo consumen: Universal Search · Similar Companies · Recommendations · Matching · Comparable Engine · Opportunity Engine · Arroba Copilot · Advisor Copilot · Transaction Copilot. Un único embedding canónico por empresa, reutilizable. Contratos públicos inmutables; separación Data Layer / Intelligence Engines / arroba.com mantenida.

**D6 — `master_companies` es la colección canónica OFICIAL (Sprint 1).** No es temporal ni "v2": es la colección canónica definitiva del sistema. `companies_master` queda **legacy en proceso de retirada**. Durante el Sprint conviven SOLO por compatibilidad (no romper contratos con arroba): los engines siguen sobre `companies_master` hasta una migración controlada (1. validación de paridad → 2. migración engine por engine → 3. retirada de dependencias → 4. eliminación de `companies_master`). **Fecha/criterio de deprecación de `companies_master`: cuando todos los engines consuman exclusivamente `master_companies`.** Objetivo final: una única fuente de verdad para Company Intelligence. Contrato oficial: `/app/memory/MASTER_LAYER_CONTRACT.md`.

## Restricciones respetadas
- **No implementado** (solo diseño). **Sin nuevas funcionalidades**. **Contratos públicos (Search/Value/Recommend/Analyze/enrich_company) INMUTABLES** — toda la evolución es interna. **Sin asumir UX**. arroba consume entidades+inteligencia, nunca fuentes.

## Decisiones que requieren tu validación antes de construir
1. **Raw EAV**: ¿landing del CSV en object storage + pivot directo a Normalized (recomendado), o también `raw_financial` fila-a-fila en Mongo (auditoría máxima, +cientos de millones de docs)?
2. **ANN de embeddings**: ¿**Atlas Vector Search** (gestionado, requiere Atlas) o **HNSW local** (FAISS/hnswlib, sin dependencia de Atlas)? — afecta a infra.
3. **Orden de ataque**: ¿empiezo por **P0.7+P0.1** (ingestión real + carga eficiente de la muestra para validar el modelo end-to-end) o por **P0.2** (jobs reanudables) como cimiento previo?
