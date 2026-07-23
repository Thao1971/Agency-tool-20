# Auditoría P0 — Industrialización del Data Layer (escalado a 3,3M)
_Fecha: 2026-06-24 · Read-only · Métricas reales de preview (5.310 master records)_

> Veredicto: el Data Layer es **correcto funcionalmente e idempotente a nivel de documento**, pero **NO está industrializado para 3,3M**. Los bloqueos son de **ejecución** (N+1, sin batching, sin job en background, sin reanudación, sin incrementales) y de **dos capas O(n) / O(n²)** (embeddings en RAM y grafo). Hay que separar **ingestión cruda → derivación → capas analíticas** en pipelines reanudables y por lotes antes de cargar el fichero real.

---

## Métricas base medidas (collStats)

| Colección | Docs | avgObjSize | Data | Índices | nidx |
|-----------|------|-----------|------|---------|------|
| companies_master | 5.310 | **5,3 KB** | 28 MB | 0,8 MB | 6 |
| iberinform_companies | 5.000 | 620 B | 3,1 MB | 0,6 MB | 7 |
| iberinform_financials | 11.657 | 373 B | 4,3 MB | 1,2 MB | 5 |
| company_embeddings | 5.309 | **1,73 KB** | 9,2 MB | **0,1 MB (solo _id)** | 1 |
| company_relationships | 84.896 | 391 B | 33 MB | 12,2 MB | 4 |

Ratio observado de grafo: **~16 relaciones/empresa**.

---

## 1. Arquitectura de ingestión
**Estado**: hay 3 etapas mezcladas y no separadas formalmente:
1. **Ingestión cruda** (`iberinform_processor.py`): construye TODA la lista en memoria → `delete_many(source) + insert_many(lista_completa)`. Un único `insert_many` de 3,3M docs = pico de RAM y un round-trip gigante.
2. **Derivación** (`master_builder.rebuild_master_records`): enriquece `companies_master`.
3. **Capas analíticas**: embeddings → signals → graph.

**Limitación**: no hay contrato de "fuente → staging → master". La ingestión y la derivación están acopladas (el processor también toca `companies_master`).
**Recomendación**: pipeline explícito **raw → staging (`iberinform_companies`/`_financials`) → master (derivación) → analytics**, cada etapa con su job, su estado y su versión. Ingesta por **streaming + `bulk_write` en chunks de 1–5k con `ordered=False`** (nunca una lista de 3,3M en RAM).

## 2. Escalabilidad a 3,3 millones
**Proyección de tamaño** (extrapolando avgObjSize medido):
- `companies_master`: 5,3 KB × 3,3M ≈ **17,5 GB lógicos** (~12 GB en disco con compresión WiredTiger).
- `company_embeddings`: 1,73 KB × 3,3M ≈ **5,7 GB** en disco; y el vector en RAM (float32 128-dim) = 3,3M × 512 B ≈ **1,7 GB solo vectores** + overhead dict ≈ **5–8 GB RAM**.
- `company_relationships`: 16 × 3,3M ≈ **53M aristas** × 391 B ≈ **20 GB datos + ~8 GB índices ≈ 28 GB**.

**Bloqueos duros**:
- **Embeddings (Fase C)**: `_load_vectors()` carga TODO en RAM y `semantic_top()` hace **scan lineal sobre 3,3M por query** → inviable. Tope práctico actual ≈ 100–200k.
- **Knowledge Graph**: `rebuild_graph()` hace `M @ M.T` = **O(n²)** = 3,3M² ≈ 10¹³ ops → **imposible**. Requiere *blocking* (similitud solo intra-cluster) + ANN.

## 3. Procesamiento por lotes
**Estado**: **NO existe**. `rebuild_master_records` hace `update_one` documento a documento. Ingestión hace un `insert_many` monolítico.
**Recomendación**: `bulk_write([UpdateOne(...)], ordered=False)` en lotes de 1–5k; cursores con `batch_size`; en analytics, procesar por *chunks* y por cluster.

## 4. Idempotencia
**Estado**: **buena a nivel de documento**. `build_one` produce un `$set` determinista; `build_aliases` deduplica; embeddings/signals/graph borran-y-reconstruyen (idempotentes por diseño). `resolve_duplicates` es no-destructivo (marca `merge_status`).
**Riesgo a escala**: el `delete_many + insert_many` de ingestión NO es idempotente incremental (borra todo el `source`). Y `rebuild_graph` hace `delete_many({})` global → no reanudable a medias.
**Recomendación**: upserts por clave natural (`cif_normalized`) en lugar de delete+insert; versionar en vez de borrar.

## 5. Reanudación ante errores
**Estado**: **NO existe**. Todo corre **dentro del request HTTP** (`POST /rebuild-master` hace `await rebuild_master_records()`). A 3,3M:
- Excede el timeout del ingress (~60–100s) → el cliente corta, pero el proceso sigue huérfano.
- Si peta en el doc 2M, al reintentar **empieza de cero** (no hay checkpoint).
**Recomendación**: convertir cada rebuild en **job en background** con estado persistido (`rebuild_jobs`: `status`, `last_processed_id`, `processed`, `failed`, `started_at`, `pipeline_version`). Cursor ordenado por `_id`/`master_company_id` + `last_processed_id` como checkpoint → reanuda donde quedó. (Ya existe patrón de recovery en `_recover_stuck_valuo_requests`).

## 6. Versionado
**Estado**: parcial. Hay `updated_at` y `lineage.source` por doc, y versiones de capa (`analyze-v1`, `lsa-v1`, `kg-v1`). **Falta** un `build_version`/`schema_version` en cada master record y un `source_hash` del input.
**Recomendación**: añadir `pipeline_version` + `source_version` + `built_at` por doc → permite **rebuild selectivo** ("reprocesa solo docs con version < N") y trazabilidad.

## 7. Incrementales
**Estado**: **NO existen**. Cada rebuild es full-scan de toda la colección, aunque solo cambie 1 fuente.
**Recomendación**: ingestión incremental por **delta de CIF** (nuevos/cambiados) marcando `dirty=true`; los jobs de derivación/analytics procesan solo `dirty` o `pipeline_version<N`. Para embeddings: `partial_fit`/transform incremental sobre el modelo ya entrenado (no reentrenar SVD con 3,3M cada vez).

## 8. Índices Mongo
**Presentes y correctos**: `iberinform_companies.cif` ✓, `iberinform_financials.cif`+`year` ✓ (las lookups por CIF del rebuild SÍ usan índice).
**Faltantes / a crear antes de 3,3M**:
- `companies_master.name_key` — usado en el `$group` de dedupe → **full scan a 3,3M sin él**.
- `companies_master.cif_normalized` ✓ existe.
- `companies_master.classification.cluster_id` — filtro de Search + benchmark de signals.
- `companies_master.signal_score` — boost de Search.
- `company_embeddings.master_company_id` — **hoy solo tiene `_id`** → lookups por id hacen colección scan.
- Compuesto `iberinform_financials (cif, year:-1)` para el `find().sort(year)` por empresa.
- TTL ya correcto en `analyze_cache.expires_at`.

## 9. Tamaño esperado (resumen a 3,3M)
| Colección | Proyección | Nota |
|-----------|-----------|------|
| companies_master | ~17,5 GB (datos) | doc 5,3 KB incl. signals[]+history+sources |
| company_embeddings | ~5,7 GB disco / 5–8 GB RAM | vectores como JSON list = ineficiente |
| company_relationships | ~28 GB (datos+idx) | 53M aristas a 16/empresa |
| **Total motor** | **~50–55 GB** | + analytics intermedias |

**Implicaciones**: viable en Mongo de disco, pero **embeddings/grafo no caben en el modelo actual en memoria/cómputo**. Reconsiderar: vectores en binario comprimido o **Atlas Vector Search / ANN (FAISS/hnswlib)**; aristas de grafo **acotadas** (top-K por empresa, no todas) y solo intra-cluster.

## 10. Tiempo estimado de reconstrucción
Extrapolación desde lo medido (rebuild_master ~7s / 5.300 docs = **1,3 ms/doc** con N+1 de 3 round-trips, local):
- **master rebuild secuencial**: 3,3M × 1,3 ms ≈ **72 min teórico** (optimista local); realista con índices/datos mayores y red **2–5 h**. Con `bulk_write` + preload de fuentes → estimable en **15–40 min**.
- **embeddings**: TF-IDF+TruncatedSVD+KMeans sobre 3,3M docs = **horas** y picos de RAM altos; el scan por query lo hace inusable en runtime.
- **graph O(n²)**: **inviable** sin blocking/ANN.
- **signals**: O(n) con benchmarks por cluster → minutos (aceptable si se batchea).

---

## Plan de industrialización priorizado (sin tocar contratos públicos)

**P0.1 — Quitar el N+1 y batchear el master rebuild** (mayor ROI inmediato)
- Pre-cargar `iberinform_companies` y `iberinform_financials` en diccionarios por `cif` (o `$lookup` por lotes) en vez de 2 finds por doc.
- `bulk_write([UpdateOne], ordered=False)` en chunks de 2–5k.

**P0.2 — Rebuilds como jobs en background reanudables**
- Colección `rebuild_jobs` con checkpoint (`last_processed_id`, `pipeline_version`, contadores). Endpoints devuelven `job_id` + estado; worker procesa por lotes; reanuda tras fallo/restart.

**P0.3 — Versionado + incrementales**
- `pipeline_version` + `source_version` + `dirty` por doc. Rebuild selectivo (`version<N` o `dirty=true`). Ingestión por delta de CIF (upsert, no delete-all).

**P0.4 — Índices antes de cargar**
- Crear: `name_key`, `classification.cluster_id`, `signal_score` en master; `master_company_id` en embeddings; compuesto `(cif, year)` en financials. Crearlos **antes** de la carga masiva.

**P0.5 — Rediseño de capas no escalables (embeddings + grafo)**
- Embeddings: entrenar SVD en muestra, transformar incremental; vectores binarios; ANN (hnswlib/FAISS) o Atlas Vector Search para el `semantic_top`. 
- Grafo: similitud **solo intra-cluster** (blocking) + top-K acotado → de O(n²) a O(n·k). Aristas acotadas (~k=10) → ~33M en vez de explotar.

**P0.6 — Ingestión cruda por streaming**
- Parseo del fichero 3,3M por filas/chunks → `bulk_write` incremental. Nunca materializar la lista completa en RAM.

> Nota de coherencia con el principio rector: industrializar el **transporte y la escala** del Data Layer NO mejora la calidad del dato; simplemente permite cargar el dato real (Iberinform 3,3M) que es la palanca maestra identificada en la auditoría de motores.
