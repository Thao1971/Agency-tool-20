# Architecture CHANGELOG

> Registro de cambios de arquitectura de la plataforma Agency Tool (compartida: Valuo.pro + arroba.com + Platform Console).

## 2026-08-14 — Buscador semántico → Atlas Vector Search ($vectorSearch/HNSW) con fallback in-memory ✅
- **Problema**: en prod la búsqueda tardaba >2 min porque el código desplegado cargaba todo el universo de embeddings y calculaba coseno en Python por request (+OOM del worker).
- **Tier/soporte**: cluster prod = MongoDB **8.0.29**, `getSearchIndexes()` responde (Atlas Search/Vector Search **disponible**); `hostInfo` restringido → tier compartido, pero soporta Vector Search igualmente.
- **Índice creado en PROD Atlas**: `semantic_vec` (tipo `vectorSearch`, `path=embedding.vector`, `numDimensions=512`, `similarity=cosine`, `filter=cnae_section`). Estado READY/queryable. Creado con el usuario de app (`createSearchIndex` permitido).
- **Backend nuevo (auto-detección)**: `vector_search.py` reescrito — usa **Atlas `$vectorSearch`** (coseno dentro de Atlas, `numCandidates` ~20×limit, filtro `cnae_section`, exclusión de self por over-fetch) cuando está disponible; **cae a la matriz numpy en memoria** (memory-safe) donde no lo está (Mongo local de preview). `warm()` prueba Atlas al arrancar y, si responde, **NO carga el índice en memoria** (evita el OOM en prod). `current_backend()` reporta `atlas-vectorsearch-v1` / `inmemory-cosine-v2`.
- **Mismo contrato** `/search` y `/similar` (shape idéntico). Nota: el score de Atlas para coseno es `(1+cos)/2 ∈ [0,1]`, el in-memory es coseno crudo — el ranking es idéntico.
- **Latencia medida contra prod** (pool caliente): `$vectorSearch` **p50 ~118ms** (p95 ~121ms); embedding OpenAI ~356ms → **~474ms por búsqueda end-to-end** (vs >2 min). Validado por el propio código: search, similar (self excluido), filtro de sección J → todo correcto.
- **Preview** (Mongo local, sin $vectorSearch): usa fallback in-memory (warm log: `inmemory-cosine-v2, 25868 vectors`), "agencias de viajes" → agencias reales. ✅
- **Archivos**: `services/engines/semantic/vector_search.py` (reescrito: dispatcher Atlas+in-memory, `warm`, `current_backend`), `engine.py` (`VS.current_backend()`), `routes/semantic_intelligence.py` (catalog backend), `server.py` (warm probe).
- **ACCIÓN REQUERIDA → REDEPLOY de prod** para activar el path Atlas. El índice `semantic_vec` YA existe en el Atlas de prod, así que tras el redeploy el backend lo autodetecta y lo usa (sin OOM, sin carga en memoria). No hay que recrear índice ni re-embeddear.


## 2026-08-14 — Re-embed semántico de PROD + fix de memoria del índice (evita OOM) ✅⚠️
- **Re-embed PROD ejecutado** (autorizado): `scripts/reembed_semantic_openai.py --force` contra el Atlas de producción (`MONGO_URL`/`DB_NAME` de prod inline, `OPENAI_API_KEY` del `.env`; NO se tocó el `.env` de preview). Resultado: **25.868/25.868 fichas en `text-embedding-3-small`, 0 legacy** (antes solo 3 pilotos openai → por eso prod devolvía siempre IUSTIME/COPISA/SERVIER). 282s.
- **Búsqueda verificada (preview, mismos datos que prod)**: "agencias de viajes" → VIAJES MARKETING, JULIATOURS, GIRATUR, VILLAR Y LORO (agencias reales, sección N/M). Relevancia correcta.
- **⚠️ INCIDENCIA PROD (breve, auto-recuperada)**: al lanzar la búsqueda de verificación contra prod, el worker devolvió **520 en todos los endpoints** ~15s y se reinició solo. Causa: el código DESPLEGADO en prod construía el índice en memoria materializando TODO el universo como lista Python (pico ~350-400MB) → **OOM del worker** al cargar 25.868 vectores.
- **FIX de memoria (en preview, pendiente de redeploy)**: `vector_search._ensure_index` ahora **preasigna UNA matriz `float32` [N,D] (53MB) y la llena fila a fila desde un cursor en streaming** (`persistence.iter_embeddings`/`count_embeddings`) → **RSS pico del proceso 221MB** (medido contra Atlas prod). Además **warm-up en background al arrancar** (`server.py` → `vector_search.reload()`) para no pagar carga en frío en la primera `/search`.
- **Archivos**: `services/engines/semantic/vector_search.py` (cargador seguro + warm), `persistence.py` (`iter_embeddings`, `count_embeddings`), `server.py` (warm-up en `_run_startup_init`).
- **ACCIÓN REQUERIDA**: **REDEPLOY de prod** para aplicar el fix de memoria. Hasta entonces, NO ejecutar búsquedas semánticas en prod (cada una provoca un blip de ~15s auto-recuperado). Tras el redeploy, prod servirá las agencias reales sin caerse. Los DATOS de prod ya están correctos (no requieren re-embed de nuevo).


## 2026-08-14 — `summary` enriquecido en cada SearchHit de search + resolve (tabla sin N+1) ✅
- **Motivo (arroba.com página de resultados)**: pintar la tabla con una sola llamada. `search` y `resolve` ahora devuelven, por hit, un objeto `summary` con: `revenue`, `ebitda`, `ebitda_margin`, `growth_pct` (YoY), `signal_score` (0-100), `signal_badge` (enum), `valuation` {low,mid,high,currency,basis}, `employees`, `arroba_score` (0-100 explicable), `city`, `activity_label`, `updated_at` (+ `arroba_score_detail` con componentes, `market_position_pct`).
- **Sin N+1**: nuevo `services/company_card.py::build_summaries(master_ids)` usa **2 queries en lote** (`master_companies $in` + `signals $in activas`) + **1 carga de revenues por sección CNAE distinta** (cacheada 600s) → todo lo demás en memoria. Reutiliza `SE._score` (score-v1 desde `signals.dimensions`), `FE.financial_quality` (puro) y los múltiplos de `skills_valuation`.
- **signal_badge** (precedencia M&A): `riesgo` (financial.net_loss/negative_equity/quality_low | risk.*) > `buscando_financiacion` (capital.*) > `comprando` (ownership.consolidator) > `alto_crecimiento` (growth.* | market.outperforms_peers | financial.margin_strong) > `estable`. `null` si la empresa no tiene señales.
- **valuation**: rango por múltiplos de sección — `EV = EBITDA × EV/EBITDA` (si EBITDA>0), si no `EV = revenue × EV/Revenue`; `{low, mid, high, currency:"EUR", basis}`.
- **arroba_score** (0-100, determinista, explicable): media ponderada re-normalizada sobre componentes disponibles — financial_quality 40% · growth 20% · market_position (percentil sectorial) 20% · signals 20%. Guarda `components` + `confidence` (suma de pesos disponibles) + `partial`. Si faltan cuentas, calcula con lo que haya y baja confianza; si no hay nada fiable → `null` (la tabla pinta "—").
- **Archivos**: `services/company_card.py` (nuevo); `routes/semantic_intelligence.py` (search enriquece), `routes/company_intelligence.py` (resolve enriquece + `CompanyResolveMatch.summary`), `routes/engine_schemas.py` (`SearchHit.summary`).
- **Validado (preview, curl local + URL externa)**: SERVIER resolve → revenue 164M, ebitda 18.5M, margin 11.3%, growth +11.7%, signal 62/**comprando**, valuation ev_ebitda 111–166M, arroba **81** (conf 1.0); empresas sin cuentas → nulls honestos + arroba parcial (conf 0.2-0.8); `basis` conmuta ev_ebitda/ev_revenue. Los 12 campos presentes.
- **PROD**: lee de `master_companies` + `signals` (ya poblados en prod) → **funciona nada más redeployar el código, sin migración de datos** (a diferencia del re-embed semántico).


## 2026-08-14 — Semantic search: buscador global NL con embeddings reales + `cif` en resultados ✅
- **Motivo (Beta/arroba.com)**: `semantic-intelligence/search` daba resultados poco fiables (backend `hashing-tf-v1` → "laboratorio farmacéutico" traía empresas de educación) y no devolvía `cif`, imposibilitando abrir la ficha (que navega por CIF).
- **Causa doble detectada**: (1) embedding sin semántica (bolsa de palabras por hashing); (2) **bug de pool**: en búsqueda global (sin `cnae_section`) `top_k` solo puntuaba un slice ARBITRARIO de 500 fichas (`find().limit(500)` sin orden), no las 25.868.
- **Solución (Opción A1)**: proveedor de embeddings **OpenAI `text-embedding-3-small` (512-d, L2-normalizado)** vía `OPENAI_API_KEY` (clave del usuario en `backend/.env`; la clave Emergent NO soporta embeddings). Fallback automático a local `hashing-tf-v1` si no hay key.
  - `services/engines/semantic/embeddings.py`: nuevo `OpenAIEmbeddingProvider` (+`embed_many`) y selección de proveedor por env.
  - `services/engines/semantic/vector_search.py`: reescrito a **`inmemory-cosine-v2`** — carga TODOS los vectores del modelo activo en una matriz numpy cacheada (TTL 300s) y escanea el universo completo; filtra por `embedding.model` activo → degradación segura a vacío si el modelo cambia y aún no se re-embeddeó.
  - `persistence.all_embeddings(model)`: streamer de todo el universo por modelo.
  - `engine.search`/`build_profile`: embedding de query/doc vía `asyncio.to_thread` (no bloquea el loop).
  - `SearchHit`: **añadido `cif`** (schema + runtime; las rutas usan `responses=` doc-only → nada se recorta).
  - `scripts/reembed_semantic_openai.py`: job batch idempotente (BATCH=128, reintentos con backoff, `--force`).
- **Re-embed en PREVIEW**: 25.868 fichas re-embeddadas en 117s (~220/s). Coste medido ~2,06M tokens ≈ $0,04.
- **Validación (preview, curl)**: relevancia correcta en NL — "laboratorio farmacéutico"→farma (Servier, Antibióticos Alcalá), "construcción de carreteras"→sección F (COPISA), "asesoría fiscal"→M, "clínica dental"→Q, "transporte y logística"→H; `/similar` de Servier→otras farma (0.85); `cif` presente en todos; `/catalog` refleja `openai / text-embedding-3-small / inmemory-cosine-v2`.
- **⚠️ ACCIÓN REQUERIDA EN PROD tras redeploy**: los 25.868 `semantic_profiles` de prod siguen con vectores `hashing-tf-v1`; hasta correr `python scripts/reembed_semantic_openai.py` contra el Atlas de prod (con `OPENAI_API_KEY` en secretos), **la búsqueda en prod devolverá vacío** (degradación segura por filtro de modelo). El re-embed de prod es una operación de datos independiente del deploy de código.


## 2026-08-10 (incidente prod) — 520 por OOM del pod + master_id divergente
- **520 en prod durante el seed**: el paso `balances` de `prod_seed_eav` carga 555k filas en memoria → satura el pod pequeño de prod → Cloudflare 520 (~45s) → el pod reinicia → mata el subproceso a mitad (run3 quedó congelado en step=balances). Los balances YA estaban sembrados de runs previos (cashflow=246), así que re-ejecutarlos era innecesario y peligroso.
- **FIX**: (1) endpoint `/reingest-eav` acepta `balances: bool = Query(True)` → `balances=false` salta el paso pesado. (2) `_backfill_ratios` reescrito a STREAMING (un doc + buffer de 500 ops, sin cargar todos los accounts en memoria) → seguro en pods pequeños. Verificado en preview con `balances=false`: **1.3s**, seen=13.481, ratios_backfilled=13.452, master_current_ratio=13.044.
- **master_id divergente (incidente reportado por PM)**: intel.arroba.com devuelve `mc_36c100bcee4a` para Servier de forma CONSISTENTE (8/8 llamadas) = una sola instancia/Atlas. PREVIEW también da `mc_36c100bcee4a` → master_id es DETERMINISTA. Beta ve `mc_908b00949ee2` → **Beta NO consume intel.arroba.com**; lee de un Intel/Atlas DISTINTO y más ANTIGUO (resolver anterior). Canónico = intel.arroba.com (master_total=24.992, service key sha256[:8]=2ba91e0d válida). Acción de consolidación (ops/Beta): apuntar `AGENCY_TOOL_BASE_URL` de Beta a https://intel.arroba.com. NO borrar nada aún.
- PENDIENTE: 1 redeploy más (fix balances=false) → luego `POST /reingest-eav?ownership=false&listed=true&balances=false` en prod (ligero, sin OOM) → percentiles poblados.


## 2026-08-10 (fix seed) — Backfill ligero de ratios (rebuild_master era inviable en Atlas)
- Diagnóstico: `rebuild_master` (full o con cif_list de 13k) NO escribe ni un lote en la Atlas de prod (0 flushes en >8 min) — reescribe el doc entero de 25k empresas con 13 índices. Los VALORES por-empresa ya salían (analyze lee norm directo: NCR cash_flow ok, current_ratio 2.07), pero los PERCENTILES quedaban null (`with_balance_liquidity`=0).
- **FIX en `scripts/prod_seed_eav.py`**: sustituido `rebuild_master` por `_backfill_ratios` — un solo cursor sobre `norm_financials` (con balance) + `bulk_write` de `$set financials.latest.ratios` (campo NO indexado) en lotes de 1000. Verificado en preview: **3.9s**, `ratios_backfilled=13.447`, `master_current_ratio=13.044`, NCR percentil=50.
- **Invalidación de caché**: `analyze_cache` usa `data_version = updated_at|signals_updated_at|last_enriched_at`. El backfill ahora bumpea `updated_at` en cada empresa → cache_key cambia → analyze recomputa fresco (resuelve el riesgo de servir respuestas cacheadas viejas tras el seed).
- El endpoint `/reingest-eav` y su subproceso aislado siguen igual. PENDIENTE: **1 redeploy más** para llevar este fix a prod; luego re-ejecutar el seed (los subprocesos lentos antiguos mueren al reiniciar el backend en el deploy).
- VERIFICADO en prod (antes del fix): master_total=24.992, NCR B28031458 resolved=true (financials+cash_flow+governance+signals), cashflow_years=246, is_listed=1 → prod apunta al Atlas correcto con las 25k; NO hace falta ingesta completa.


## 2026-08-10 (deploy) — Siembra de PRODUCCIÓN ejecutada
- Deploy a `intel.arroba.com` confirmado (código nuevo: `/coverage/check` da JSON). Lanzado `POST /api/v1/admin/iberinform/reingest-eav` en prod.
- **Core sembrado y VERIFICADO en prod**: balances EAV (cashflow_years 5→246), is_listed (0→1), y por-empresa: NCR B28031458 cash_flow presente + current_ratio 2.07; PROCOLUIDE A81921611 st_debt=1.395.128,55/lt=2.905.096,59/fin=4.300.225,14 + current_ratio 1,76; A28354132 is_listed=true (BME). **Señal de éxito del usuario CUMPLIDA.**
- ⚠️ **`rebuild_master` (percentiles sectoriales) se arrastró en Atlas**: pasé `cif_list` de 13.451 CIFs → `$in` gigante patológicamente lento en Atlas (0 lotes escritos en ~9 min; en local fue 8s). `with_balance_liquidity` quedó en 0. La API en vivo de prod se mantuvo sana (subproceso aislado OK).
- **FIX** en `scripts/prod_seed_eav.py`: rebuild ahora `scope="full"` (escaneo secuencial, sin `$in` gigante) + `create_index` en cif_normalized/src_cif/name_key. Verificado en preview: seed completo en **10.5s**, rebuild 24.992, current_ratio 13.044. **PENDIENTE: redeploy + re-ejecutar el seed en prod** (el redeploy reinicia el backend y mata el subproceso lento antiguo).


## 2026-08-10 (P0) — Desajuste de ENTORNO: preview(local) ≠ producción(Atlas)
- **Diagnóstico**: preview usa MongoDB LOCAL (`localhost:27017`, `arroba_agency_tool`); producción (`intel.arroba.com`) es despliegue separado con código antiguo + otra base (Atlas). Beta consume producción → no ve nada del trabajo de datos hecho en preview. Prueba: rankings coinciden (misma base de empresas/revenue) pero cash_flow/current_ratio/st_debt/is_listed = null (falta re-ingesta EAV) y `/coverage/check` devuelve HTML del SPA (código no desplegado).
- **NUEVO endpoint de siembra idempotente**: `POST /api/v1/admin/iberinform/reingest-eav` (+ `GET .../reingest-eav/{run_id}`) en `routes/iberinform_admin.py`. Corre en **SUBPROCESO AISLADO** (`scripts/prod_seed_eav.py`) → NO bloquea el event loop (verificado: health ~3ms durante ejecución; ~8s en preview). Re-ingiere balances EAV completo + ownership + marca is_listed(BME) + rebuild master de las empresas con balance. Úsalo UNA vez tras el redeploy para sembrar la base de producción.
  - IMPORTANTE: la 1ª versión usaba `asyncio.create_task` in-process y tumbó el backend (rebuild de 13k bloquea el loop). Corregido a subproceso aislado.
- Ruta de datos: `SAMPLE_DIR = /app/data/muestra_25000` (los 10 `.tab` están versionados en git → viajan al deploy).
- Handoff de resolución para Beta/PM: `/app/frontend/public/PARA_BETA_ENTORNO_RESOLUCION.md`.
- Login admin: la respuesta de `/api/v1/auth/login` usa la clave **`token`** (no `access_token`).


## 2026-08-10 (cont.) — Estabilidad enriquecimiento + is_listed + ownership idempotente
- **Estabilidad (a)**: causa raíz de la caída de la API = `uvicorn --reload` vigila `/app/backend` (incluido `scripts/`); ejecutar scripts ahí disparaba un reload que se colgaba en el scraper síncrono de CNMV del arranque. Solución: runners AISLADOS en `/app/tools_runtime/` (fuera del árbol vigilado) con `PYTHONDONTWRITEBYTECODE=1` + throttling (concurrencia 4, lotes con pausas). Verificado: API en 200 (3ms) mientras corre el enriquecimiento.
- **Enriquecimiento web PARADO por decisión del usuario**: rendimiento marginal (ok≈0,2% sobre URLs adivinadas por url_discovery; las descripciones reales ~2.942 vienen de las URLs de Iberinform). Sin LLM.
- **(b) multi-ejercicio EAV: BLOQUEADO POR DATOS** — `Datos_BALANCES.tab` tiene 1 año/empresa (snapshot, no histórico). El usuario no tiene el histórico por ahora. `evolution`/CAGR quedan pendientes de datos.
- **(c) ownership: DATA-LIMITED** — `Datos_ACCIONISTAS.tab` = 628 filas/318 empresas (ya todo ingerido, idempotente re-verificado). Se expandirá al subir una entrega completa por `POST /api/v1/admin/iberinform/upload-delivery` (zip con todos los .tab).
- **(d) is_listed: cableado** desde `bme_companies` (`tools_runtime/mark_listed_from_bme.py`), expuesto en `/api/v2/company-intelligence/identity` (`is_listed`/`listed_market`) y contado en `/api/v1/company/coverage.listed_companies`. Solape actual: 1 (A28354132 INNOVATIVE SOLUTIONS ECOSYSTEM, con financials → CIF demo de cotizada para Beta).
- Runners nuevos (aislados): `tools_runtime/web_enrich_throttled.py`, `tools_runtime/mark_listed_from_bme.py`, `tools_runtime/reingest_ownership.py`.


## 2026-08-10 — B5 EAV completo re-ingerido + armonización contrato B-2 (Beta Fase 0) ✅
- **Causa raíz B5 encontrada y resuelta**: la ingesta 2026-07-22 corrió con una versión antigua de `ingest_balances_file` (filtro `_ACCOUNT_CODES`, código muerto ahora) que solo guardaba ~6 códigos canónicos por empresa-año. El código EAV completo ya existía pero **nunca se re-ejecutó**. Re-ejecutada sobre las ~25k en Atlas (555.550 filas, ~3s balances + ~10s rebuild master). Validado primero sobre muestra de 500.
  - `norm_financials` con `current_assets`(12000): 8 → **13.430**; `current_liabilities`(32000): 8 → **13.123**; cash-flow OCF(61500): 5 → **246**.
  - `master.financials.latest.ratios.current_ratio`: 0 → **13.044**. Ratios de liquidez/working-capital + percentil sectorial y desglose de deuda (st/lt/financial_debt) ahora activos en el contrato. Cash flow (EFE) solo en cuentas normales (246); PYMEs abreviadas → `cash_flow:null`+nota (honesto).
- **Armonización de contrato para Beta**:
  - `routes/company_intelligence.py`: añadido `objeto_social` (alias de `corporate_purpose`) a la respuesta de `POST /api/v2/company-intelligence/identity` + a `data_coverage`.
  - Confirmado (sin cambios): `benchmark`/`methodology`/`scenarios` ya salen en `POST /api/v1/financial-intelligence/valuation`; señales canónicas = `GET /api/v1/company/{id}/signals`.
- **NUEVO endpoint de cobertura** (`routes/company_ficha.py`, X-API-Key): `GET /api/v1/company/coverage` (agregado) + `POST /api/v1/company/coverage/check` (pre-flight por lote hasta 100 CIFs). Permite a Beta pre-filtrar CIFs y evitar 404s.
- **Diagnóstico 404 de Beta**: los 4 CIFs (Iberdrola A28017895, Planeta A08363419, Technip B65076193, micro B95758389) **NO están en el master** (gap de cobertura de la muestra 25k; no incluye cotizadas). NO es bug de lookup ni de variante de CIF. La ficha es multi-empresa (funciona para las 24.992). `is_listed` no poblado en ningún registro (sin fuente de cotizadas en la entrega).
- **5 CIFs demo entregados** a Beta (ver test_credentials.md). Handoff publicado en `/app/frontend/public/PARA_BETA_B2_FASE0_RESPUESTA.md` (accesible en `{preview}/PARA_BETA_B2_FASE0_RESPUESTA.md`).
- **Web enrichment** (`description` ~4%): batch corrido (+335 descripciones, +19 tech tags); url_discovery encontró ~3.900 URLs. **PAUSADO**: los jobs en background saturaban el pool de Atlas y tumbaban la API en vivo (health timeout). Retomar de forma controlada bajo demanda.
- Scripts nuevos: `scripts/reingest_balances_sample.py`, `scripts/reingest_balances_full.py`, `scripts/beta_diagnostic.py`.


## 2026-07-23 — v16 desplegada y verificada en Emergent Preview ✅
- `arroba_agency_tool_v16.zip` (v13 fix ciclo de vida de señales + v14 fix category/severity y pestaña Señales + v15 auditoría de fuentes/DIRCE/stats + documentación de esta capa) subida y desplegada por Neo sobre "preview-arroba-app".
- **Testing agent**: backend 19/20 (el único punto es un bug de aserción del propio test — busca `real_companies` en la raíz cuando la respuesta lo anida bajo `iberinform`; el dato servido es correcto: `real=24992, synthetic=0`), frontend 100%, 0 errores de consola en las 5 pantallas nuevas/tocadas (Oportunidades, Señales, DIRCE, y regresión de Watchlist/Fragmentación/Roll-up/Control-Synergy).
- **Pasos post-deploy ejecutados** (por orden, ninguno requirió código nuevo): `POST /api/v1/signal-intelligence/migrate-dedupe` (9 grupos de duplicados fusionados, 9 documentos borrados — limpia el residuo del bug de identidad de señales de v13); `GET /api/v1/signal-intelligence/stats/view` confirmado (`total_signals=66050`, `total_opportunities=160`: 159 `ownership.consolidator` + 1 `opportunity.succession_signal`); scheduler de PLACSP confirmado arrancando en logs junto a BORME/DataComex/Watchlist/CNMV-BME.
- **Regresión verificada**: fragmentation, ratios/catalog, rollup-thesis, watchlist, control-synergy, iberinform/stats, data-providers/health, auth negativa (X-API-Key y JWT) → todo correcto. `companies_master`/`master_companies`/`iberinform_companies` = 24.992 en los tres.
- **Nota operativa de Neo** (no bloqueante): mover los ficheros de test de integración fuera de `/app/backend/` (o usar `--reload-exclude tests/`) — uvicorn `--reload` vigila ese árbol y recarga al crearlos ahí.
- **Pendiente** (sin código nuevo): sincronizar DIRCE/INE para poblar la pantalla de Demografía Empresarial (renderiza correctamente, en estado vacío hasta ese sync).
- Detalle completo: `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md` §18.

## 2026-07-23 — Documentación formal de la Capa de Inteligencia Estratégica + Definición del Copilot ✅ SOLO DOCUMENTACIÓN
- **Nuevo documento** `memory/STRATEGIC_INTELLIGENCE_LAYER_REPORT.md`: cierra un hueco de documentación — Q1–Q7 (quick wins), E1/E2/E6/E7 (evoluciones) y T3 + Control & Synergy Score (transformacional), construidos en sesiones previas sobre el esquema moderno (`master_companies`/`master_id`), no estaban documentados en `memory/` del propio repo (solo en memoria de sesión). Cubre también la ingesta real de las 25.000 empresas Iberinform (doble esquema, fix del resolver de identidad), la auditoría completa de fuentes de datos (CNMV/BME/PLACSP/DataComex/Banco de España/scheduler/DIRCE) y el fix de fondo del ciclo de vida de señales (identidad ya no depende de `source_version`).
- **Nuevo documento** `memory/ARROBA_COPILOT_DEFINITION_v1.md`: define qué es el Arroba Copilot (se construye en arroba.com, per `ARROBA_INTEGRATION_PACK_v1.md` §1.6), qué capacidades ya cubre la plataforma (analizar/valorar/proponer/ejecutar, vía los motores existentes), el gap real de "predecir" (requiere un motor nuevo `forecast-intelligence-v1`, no construido), el split de memoria/aprendizaje entre arroba.com y Agency Tool (`recommendation_memory`/`recommendation_feedback`/`strategic_theses.lifecycle` ya existen como semilla), y una propuesta de endpoint agregador "Copilot Context" (no implementada).
- **Actualización aditiva de contratos existentes** (sin romper compatibilidad — adiciones D10): `SIGNAL_INTELLIGENCE_ENGINE_CONTRACT.md` (§6.1 nueva: `/signals`, `/signals/view`, `/stats`, `/stats/view`, `/signal/{id}/view`, `/history/view`, `/migrate-dedupe`; corrección de la fórmula de `signal_id` — ya no incluye `source_version`) e `INTELLIGENCE_API_REFERENCE.md` (§2 Signal Intelligence actualizada con los mismos endpoints).
- **`PRD.md`**: nueva entrada "Sprint 9" en `## Latest changes (Julio 2026)` resumiendo todo lo anterior, con estado explícito: verificado (mongomock + `py_compile` + esbuild), **pendiente de empaquetar y desplegar** por instrucción de Daniel de acumular trabajo verificado y desplegar en un único paso cuando él lo indique.
- Sin cambios de código ni de comportamiento en este commit — solo documentación de trabajo ya implementado y verificado en sesiones anteriores.

## 2026-07-12 — Smoke Test Público Oficial de Integración (artefacto permanente) ✅
- Creado `memory/SMOKE_TEST_PUBLIC_PRODUCTION.md` (documento de gobierno) + `backend/tools/smoke_test_public.py` (script ejecutable, exit 0=PASS/1=FAIL, apto para gate de CI/despliegue).
- Verifica en <2 min el flujo canónico Arroba (resolve→identity→analyze) sobre CIF `A87803862`, solo con Base URL pública + X-API-Key: HTTP 200, identidad, financials L2, histórico real, data_source, explainability, master_id y compatibilidad `arroba.v2`.
- **Regla:** antes de cada despliegue de Arroba o del Intelligence Engine debe ejecutarse; FAIL = regresión de integración → no se despliega.
- **Ejecución 2026-07-12 contra producción: PASS (18/18).** F0.2 desbloqueado; contrato congelado durante F0.2.


## 2026-07-12 — Desbloqueo integración Arroba F0.2 · Resolución pública + caso canónico ✅
- **Identificador oficial = CIF** (contratos agnósticos: aceptan CIF o master_id en `identifier`). Documentado en `ARROBA_V2_INTEGRATION_GUIDE.md`.
- **Endpoint público de resolución** `POST /api/v2/company-intelligence/resolve` (solo X-API-Key): CIF→master_id (cif_exact) y Nombre→master_id (name_exact/name_partial). Sin JWT, sin /master/*, sin Mongo. Modelos `CompanyResolve*` (nombres únicos para no colisionar con `master.py::ResolveRequest` — evita romper el freeze v1).
- **Caso canónico F0.2 verificado:** CIF `A87803862` (TOTALENERGIES) → identity completa + financial-analyze con L2 real (revenue 933M, EBITDA 36,5M, net_income 25M), histórico real 3 años (2024/2023/2022, sin interpolar) y `explainability.data_source` trazable a Iberinform.
- **Contrato v2 re-congelado:** 55 paths (añade `/resolve`), 94 schemas. `arroba.v1` sigue byte-idéntico (53 paths). Freeze test v2 actualizado (55). 10 golden tests verdes.
- **Verificado:** testing_agent backend 100% (resolve CIF/nombre/401/422, caso canónico agnóstico CIF↔master_id, regresión contratos). Report: `/app/test_reports/iteration_33.json`.


## 2026-07-12 — Desbloqueo Data Layer · Bootstrap reproducible + dataset canónico ✅
- **Diagnóstico:** NO hay bug de mapeo raw→master (norm_financials→master.financials: 0 pérdidas). El 404 "para todas" es por **BD de producción vacía** (despliegue independiente). Cobertura financiera 374/1000 = cobertura real de la fuente.
- **Track A — Bootstrap reproducible:** `services/data_layer/bootstrap.py` reconstruye TODO el Data Layer desde la fuente oficial (`tests/fixtures/iberinform_sample`, real) sin pasos manuales: ingestión→master(+ER+financieros)→ownership→signals canónicas→índice semántico canónico→verificación→set canónico. 3 vías: self-healing al arranque (`AUTO_BOOTSTRAP_DATA_LAYER=1` si Master vacío), endpoint `POST /api/v1/data-layer/bootstrap` (JWT), y CLI `python -m services.data_layer.bootstrap`. Probado desde BD vacía: 1000 empresas, 2443 señales, 998 perfiles, ~15s.
- **Track B — Dataset canónico:** `select_canonical_set(50)` (data-driven, ≥2 ejercicios reales) → `db.canonical_validation_set` + `GET /api/v1/data-layer/canonical-set`. Empresas reales (TOTALENERGIES, SCANIA HISPANIA…). Cadena pública completa validada (identidad+financieros+histórico real+señales+semántica+estrategia).
- **Histórico:** solo ejercicios reales ingeridos; sin interpolar/estimar. Serie expuesta vía `evolution`.
- **Endpoints nuevos:** `POST /api/v1/data-layer/bootstrap`, `GET /bootstrap/{run_id}`, `GET /bootstrap`, `GET /canonical-set` (todos JWT). Startup self-healing hook `_auto_bootstrap_data_layer_if_empty()`.
- **Verificado:** testing_agent 20/20 (incl. regresión contratos congelados v1+v2). Informe: `DATA_LAYER_UNBLOCK_REPORT_v1.md`.


## 2026-07-12 — Sprint V2.0 · Contrato `arroba.v2` (V2-01 tipado DTOs + V2-02 Company/Identity) ✅ ADITIVA
- **V2-01 (tipado):** los 53 endpoints de los 6 motores tienen DTO de respuesta explícito en OpenAPI vía `responses={200:{"model":...}}` (NUNCA `response_model`). Runtime intacto (los DTO documentan, no filtran; `extra="allow"`). Nuevos DTOs en `routes/engine_schemas.py`.
- **V2-02 (Company/Identity):** `POST /api/v2/company-intelligence/identity` (auth `X-API-Key`, `capability_version=company-intelligence-v2`) → `CompanyIdentityResponse` proyectada del Master Record (añade `capital_social`, `domain`, `employees_total`). Alimenta COMP-1001/1002/1003. Router registrado en `server.py`.
- **`arroba.v1` congelado byte-idéntico:** `_build_arroba_openapi()` strippea las respuestas tipadas y filtra `components` al set del snapshot v1 → hash canónico idéntico, freeze tests verdes.
- **Nuevo contrato v2:** `_build_arroba_v2_openapi()` + `GET /api/v1/openapi/arroba.v2.json` (54 paths, 91 schemas) + `/api/docs/arroba/v2`. Snapshot congelado `contracts/arroba.v2.json` + freeze test `tests/golden/test_arroba_v2_contract_freeze.py`.
- **Verificado:** matriz contrato↔runtime **53/53 MATCH** (`tools/validate_matrix.py`), **10/10 golden tests**, testing_agent backend **22/22 (100%)**. SDK tipado auto-generable confirmado (OpenAPI 3.1 válido; `datamodel-code-generator` → 91 clases). Informe: `memory/ARROBA_V2_SPRINT_V2.0_REPORT.md`.


## 2026-07-12 — Utilidad AI Chat (OpenAI gpt-5.5) ✅ ADITIVA
- **Backend** `routes/ai_chat.py` (prefijo `/api/ai-chat`, fuera de `arroba.v1`): `POST /message` (gpt-5.5 vía `emergentintegrations` LlmChat con **OPENAI_API_KEY** propia del usuario), `GET /history/{session_id}`, `GET /sessions`, `DELETE /session/{session_id}`. Historial persistido en `ai_chat_messages`; memoria por `session_id`.
- **Frontend** `pages/AIChatPage.jsx` + ruta `/ai-chat` + ítem de menú HOME→AI Chat. UI request/response (no streaming: la lib instalada v0.1.0 solo soporta `send_message`).
- **Verificado:** backend por curl (respuesta real, memoria, historial) + testing_agent frontend **100% PASS**. No toca el contrato público ni otros motores. `OPENAI_API_KEY` guardada como secreto en `backend/.env`.

## 2026-07-04 — Cierre de Agency Tool como proveedor + Runbook de rotación de API Keys ✅
- **Producción confirmada:** `https://agencias.wearebudadvisors.com` (dominio custom; contrato v1 desplegado y verificado: `/api/v1/openapi/arroba.v1.json`, `/api/docs/arroba`, `/api/v1/health` → 200). Documentos de handoff/certificación actualizados con la URL de producción.
- **Runbook operativo** `memory/API_KEY_ROTATION_RUNBOOK.md`: rotación de `ARROBA_SERVICE_API_KEY` sin downtime (solape clave nueva/antigua en `db.api_keys`, migración del consumidor, revocación) + variante simple, verificación post-rotación y buenas prácticas. No bloquea la integración.
- **Hito:** Agency Tool queda **cerrado como proveedor de servicios** (contrato `arroba.v1` congelado). Nuevo desarrollo se realiza en arroba.com como consumidor. Se volverá a Agency Tool solo para incidencias, ampliaciones o publicar contrato `v2`.

## 2026-07-04 — CI gate del contrato de arroba.com (freeze en cada push) ✅
- **GitHub Actions** `.github/workflows/arroba-contract-freeze.yml`: en cada `push`/`pull_request` a main/master construye el contrato de arroba **en proceso** (sin servidor ni MongoDB; conexión Motor lazy) y lo compara por hash canónico con `backend/contracts/arroba.v1.json`.
- **Test offline añadido** `test_arroba_contract_matches_code_offline` en `tests/golden/test_arroba_contract_freeze.py` (4 tests en total; el subset de CI = 3, excluye el que requiere servidor vivo). Cualquier deriva de la superficie pública de los 6 motores **falla el CI** → obliga a `v2` deliberado; v1 no se puede romper en silencio.
- ⚠️ Para **bloquear el merge** hay que activar Branch Protection en GitHub exigiendo el check "Arroba Public Contract Freeze". Universo canónico 6.261 intacto.

## 2026-07-04 — Snapshot congelado + freeze test del contrato de arroba.com ✅
- **Endpoint versionado oficial** `GET /api/v1/openapi/arroba.v1.json` (fuente que consume arroba.com) + `GET /api/docs/arroba` (Swagger UI).
- **Snapshot físico congelado** `backend/contracts/arroba.v1.json` (referencia documental / comparación de versiones), **idéntico** al endpoint. `sha256(canonical)=0a266fff…f187f41`. README con política de versionado en `backend/contracts/README.md`.
- **Freeze test** `tests/golden/test_arroba_contract_freeze.py` (3 tests, read-only, no toca colecciones canónicas): verifica que endpoint↔snapshot son idénticos (hash canónico) y que solo exponen los 6 motores. Cualquier deriva de la superficie pública falla el test → obliga a un `v2` deliberado sin romper v1.
- **Handoff completo** para arroba.com: `memory/ARROBA_ONBOARDING_HANDOFF.md` (URL base, auth, OpenAPI, generación de cliente, pasos, ejemplos, límites). Universo canónico 6.261 intacto; ningún endpoint/schema de motor modificado.

## 2026-07-04 — Contrato OpenAPI filtrado para arroba.com (desacople externo/interno) ✅
- **Añadido `GET /api/v1/openapi/arroba.json`**: contrato público filtrado (`arroba-integration-contract-v1`) con **solo los 6 motores** (Financial 3, Signal 7, Semantic 6, Recommendation 11, Strategy 13, Transaction 13 = **53 rutas**), incluye `components`/schemas; sin rutas administrativas ni de Valuo. `GET /api/docs/arroba` = Swagger UI del contrato filtrado.
- **Full spec interno intacto** en `/api/v1/openapi.json` + `/api/docs` + `/api/redoc` (496 rutas). Cambio derivado/config; ningún endpoint ni schema de motor modificado. Verificado en vivo (`200`, 0 fugas), backend sano, universo 6.261 intacto. Ver `ARROBA_INTEGRATION_READINESS_CERT.md` (Atención A).

## 2026-07-04 — Punto A · OpenAPI expuesto bajo `/api/...` (mejora operativa) ✅
- **Solo configuración, sin cambios de contrato.** Reubicados los endpoints integrados de FastAPI: `openapi_url=/api/v1/openapi.json`, `docs_url=/api/docs`, `redoc_url=/api/redoc`. Antes iban fuera de `/api` y el ingress los enrutaba al frontend (devolvían HTML de la SPA).
- **Resultado:** `GET /api/v1/openapi.json` (OpenAPI 3.1.0, 496 rutas, coincidente con la implementación), `GET /api/docs` (Swagger UI) y `GET /api/redoc` accesibles públicamente → arroba.com ya puede autodescargar el contrato. Verificado en vivo (`200`); backend sano; universo canónico 6.261 intacto; ningún endpoint ni schema de motor modificado. `ARROBA_INTEGRATION_READINESS_CERT.md` (Atención A → RESUELTO).

## 2026-07-04 — Recuperación del universo canónico (proyección M3-2b re-ejecutada) ✅
- **Solo datos, cero cambios de código/contrato.** Re-ejecutada `legacy_projection.project_and_build` (4 batches, 5.261 proyectados) → `master_companies` **1.000 → 6.261**. Bridge re-medido `erb_c0c480261423`: **cobertura 98,13 %** (5.257 enlazadas / 5.357; 23 conflictos, 4 ambiguas, 73 huérfanas, 27 revisión manual); overlap CIF legacy **99,02 %**.
- **Validación de contrato:** Golden 111 + Smoke 203 = **314/314 verde**; endpoint público `financial-intelligence/analyze` y entidad proyectada `mc_d178502397b0` verificados en vivo con `engine_version` intacto. Ningún endpoint ni schema modificado.
- **Causa raíz documentada:** app y suite de tests comparten `test_database`; `test_jobs.py` borra `norm_company` + smoke tests hacen `rebuild_master(full)` → resetean el universo a ~1.000 en preview. En producción no ocurre (tests no corren contra BD productiva). Ver `ARROBA_INTEGRATION_READINESS_CERT.md` (Atención B, RESUELTO).

## 2026-07-04 — Contrato de Integración v1.0 + Certificación de readiness · arroba.com 📄
- **Documento oficial** `memory/ARROBA_INTEGRATION_CONTRACT_v1.md` (`arroba-integration-contract-v1`): fuente única de verdad para que arroba.com consuma la inteligencia SIN conocer la implementación interna. Sin código.
- Cubre las 11 secciones solicitadas: arquitectura por capas (responsabilidad/owner/entradas/salidas), inventario de 26 entidades, inventario de colecciones (claves/índices/cardinalidad/estado), contrato API completo (endpoints de los 6 motores + Master, auth `X-API-Key`, códigos de error, paginación, límites 600/min, versión), matriz de consumo por bloque de arroba, schema completo por endpoint, estado de implementación (🟢🟡🟠🔴), estrategia de sincronización, roadmap (actual/siguiente/futuro), contrato de estabilidad (congelado/aditivo/ruptura) y matriz final obligatoria.
- Basado 100% en auditoría del código real (rutas, modelos de request, colecciones, contratos congelados `*_ENGINE_CONTRACT.md`). No se modificó ningún endpoint ni comportamiento.

## 2026-07-04 — Sprint 8.6 · M3 Fase 2b · Ingesta & Cobertura del Master Record ✅
- **Proyección legacy→canónica** `services/data_layer/master/legacy_projection.py` (`project_and_build`): proyecta identidades legacy ausentes a `norm_company` (etiquetadas `source='companies_master_projection'`, `projection_batch`) y reconstruye vía `rebuild_master(scope='cif_list')`. Preserva invariantes de `master_builder`; **reversible por batch** (`rollback_projection`).
- **Requisitos respetados**: `companies_master` intacto (solo lectura), sin cambio en producción, motor canónico NO activado, sin migrar tráfico, sin borrar datos, sin matcher fuzzy, sin reanudar M2.
- **Resultado**: universo canónico 1.000→**6.259** (5.259 proyectados, 2 batches). Bridge re-ejecutado (`erb_202d8224d594`): **cobertura 0 % → 98,17 %** (5.255 enlazadas / 5.353; 21 conflictos, 4 ambiguas, 73 huérfanas, 25 revisión manual, 0 duplicados). Overlap por CIF: legacy 99,02 %. **Objetivo ≥95 % superado.**
- **Recomendación**: bloqueante de cobertura RESUELTO. **NO activar `canonical`** hasta resolver los 25 casos de revisión manual + huérfanas y aprobar nuevo informe. M2 queda desbloqueado para retomarse. Ver `M3_PHASE2B_REPORT.md`.

## 2026-06-26 — Sprint 8.5 · M3 Fase 2 · Entity Bridge & Master Record Quality Tool ✅
- **Herramienta permanente** `services/data_layer/master/entity_bridge.py` (+ rutas admin `/api/v1/master/bridge/*`): construye el bridge canónico `master_company_id`↔`master_id` en `entity_xref` (origin='er_bridge') y mide calidad. **Idempotente, auditable, reversible** (rollback por run_id), histórico en `er_bridge_runs`, clasificación por entidad en `er_bridge_results`.
- **Requisitos respetados**: legacy nunca modificado, sin cambio en producción, motor canónico NO activado, sin migrar tráfico, sin eliminar datos.
- **Medición**: 5350 legacy vs 1000 canónicos → **cobertura 0 %** (100% huérfanos; datasets disjuntos por cif/domain/name). Golden suite 106→**111 verde**. Detector de conflictos/ambigüedades/duplicados implementado y probado.
- **Recomendación**: **NO activar `canonical`** (orfanaría el 100% de Valuo.pro). Prerrequisito: ampliar la ingesta canónica al universo real y re-ejecutar el bridge hasta cobertura objetivo. `M3_PHASE2_BRIDGE_REPORT.md`.

## 2026-06-26 — Sprint 8.4 · M3 (Entity Resolution) Fase 1 ✅ (motor canónico + red de seguridad, sin migrar)
- **Contrato CONGELADO** `entity-resolution-v1` (DER1–DER9 aprobadas). `ENTITY_RESOLUTION_CONTRACT.md`.
- **Motor canónico unificado**: `services/data_layer/master/identity_resolver.py` — `resolve_identity` (shape legacy-compatible), `deterministic_master_id` (DER5), `link_legacy_master` (DER3 bridge legacy↔canónico en `entity_xref`), umbrales congelados DER4, auditoría append-only DER6.
- **Provider de convivencia** `services/entity_resolution_provider.py` (flag interno `ENTITY_RESOLUTION_SOURCE`, default `legacy`), cableado en `valuo_integration`/`master`/`procurement` vía alias (call sites intactos). Contrato público único (DER7); rollback inmediato.
- **Red de seguridad**: snapshot-diff de `resolve_entity` (cif_exact/domain_exact/discovered) + guards del provider. Golden suite 96 → **106 tests verde**. Smoke **203/203** (cero regresión en ruta Valuo.pro).
- **NO** se retira legacy, **NO** se migra tráfico, **NO** backfill masivo (→ M3-fase-2, DER8). Default legacy = byte-identical.

## 2026-06-26 — Sprint 8.3 · M2 inicio → DETENIDA EN VALIDACIÓN (bloqueante de cobertura) ⛔
- **Infraestructura de convivencia interna (contrato público único)**: flag `MASTER_RECORD_SOURCE` (default `legacy`), `services/intelligence_engine/master_provider.py` (legacy byte-identical / canónico con fallback transparente), cableado en `enrich_company`. Sin `?source=` público; rollback inmediato; el canónico nunca causa `master_not_found`.
- **Golden dataset ampliado**: 9→**14 empresas** / 18→**28 snapshots** con casos límite (micro/pyme/holding/incompletos/sin_web/baja_calidad/discovered). Golden suite 82 → **96 tests verde**. Smoke **203/203** (cero regresión en ruta crítica de Valuo.pro).
- **BLOQUEANTE**: `companies_master` (5338) y `master_companies` (1000) son **DISJUNTOS** (overlap `cif_normalized`=0; resolución canónica 0/14). Paridad estructuralmente imposible → legacy NO retirado, tráfico NO migrado. Ver `MASTER_SOURCE_PARITY_REPORT.md`.
- **Re-secuenciación recomendada**: M2 depende de cobertura del Master canónico ⇒ priorizar **M3 (Entity Resolution)** + **M2-pre (backfill/linkage)** antes de reanudar M2. Infra de M2 lista y desactivada, sin riesgo.

## 2026-06-26 — Sprint 8.2b · Preparación M2 (snapshot-diff + golden dataset) 🟡
- **Red de paridad para M2**: golden dataset congelado de 9 empresas × {valuo, arroba} = **18 snapshots** (`tests/golden/data/enrich_golden_snapshots.json`); generador `tests/golden/gen_enrich_golden.py`; util `enrich_snapshot_util.py` (normalización order-insensitive); test `test_enrich_snapshot_diff.py` (paridad byte-level de `fields`/`sources_with_data`/`found_map`/`engine_version`).
- **Suite golden: 62 → 82 tests** (todas verdes, idempotentes). **Sin cambios de código de producción** (solo harness de prueba).
- Propósito: detectar cualquier deriva de cálculo cuando M2 cambie el origen de datos interno (`companies_master` → `master_companies`) sin tocar el contrato externo.

## 2026-06-26 — Sprint 8.2 · M1 migración piloto (relocalización Signal legacy) ✅
- **Componente migrado**: `services/signal_engine.py` (legacy master-signals: `signal_score`, `signals[]`, `signal_similarity` sobre `companies_master`) → **relocalizado byte-for-byte** a `services/engines/signal/master_signals.py` (md5 idéntico).
- **Implementación retirada**: ninguna (fase CONVIVENCIA). `services/signal_engine.py` permanece como **shim** que re-exporta `compute_signals/rebuild_signals/signal_similarity`. Retirada diferida.
- **Consumidores migrados a la ruta canónica**: `routes/data_layer.py` (`rebuild_signals`), `services/skills_recommend.py` (`signal_similarity`).
- **Impacto**: 🟢 nulo en Valuo.pro y arroba.com; `rebuild-signals` (Console) y `skills/recommend` (arroba) con contrato idéntico.
- **Riesgo real observado**: BAJO/nulo. Sin cambios de contrato, sin regresiones.
- **Validación**: Golden 62/62 (incl. paridad shim↔canónico), Smoke 203/203, snapshot determinista (`signal_score=71`) congelado.
- **Lección aprendida**: sin equivalente funcional, "migrar" = **relocalizar + shim** (consolidar ubicación), no sustituir lógica. La sustitución semántica (consumir entidades canónicas del `engines/signal.engine`) queda como trabajo futuro con su propio contrato.

## 2026-06-26 — Sprint 8.1 · Golden Contract Tests (red de seguridad)
- Suite black-box `/app/backend/tests/golden/` congelando 19 endpoints 🔴 Legacy crítico (47 tests). Sin cambios de código de producción.

## 2026-06-26 — Sprint 8 · Auditoría final + plan de migración
- `AGENCY_TOOL_AUDIT_FINAL.md`, `LEGACY_MIGRATION_PLAN.md`, `INTELLIGENCE_API_REFERENCE.md`, `PLATFORM_GOVERNANCE_AND_CONSUMER_AUDIT.md`. 0 componentes retirables.

## 2026-06-26 — Sprint 7 · Transaction OS + Transaction Intelligence Engine
- `transaction-os-v1` / `transaction-intelligence-v1` (DTX1–DTX13). Cima del DAG. Smoke 203/203.
