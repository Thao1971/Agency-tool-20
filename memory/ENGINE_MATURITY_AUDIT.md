# Auditoría de Madurez de Motores — Agency Tool (Intelligence Engine)
_Fecha: 2026-06-24 · Read-only audit · Datos reales de preview (5.308 master records)_

> Objetivo: consolidar Agency Tool como infraestructura de inteligencia madura y desacoplada
> ANTES de definir la experiencia de arroba.com. P4/P5/P6 PAUSADOS por decisión de producto.

---

## 0. Hallazgo raíz (transversal a todos los motores)

**El dataset son dos universos casi disjuntos que no se solapan:**

| Universo | Volumen | Tiene | NO tiene | confidence |
|----------|---------|-------|----------|------------|
| **Iberinform (sintético)** | ~5.000 (94,2%) | CNAE, sector, categoría, financieros + 2 años historia, cluster | dominio, web/descripción, nombre real | 0,9 |
| **Agencias (scrapeadas, reales)** | ~307 (5,8%) | dominio, descripción web, tags | financieros, CNAE en muchos casos | 0,3 |

- Solapamiento financieros×categoría real ≈ **0** (los 5.000 con financieros son los sintéticos).
- Solo **4,1%** del master tiene descripción web; solo **5,8%** tiene dominio.
- Entity resolution encontró **0 duplicados** no porque esté resuelto, sino porque **los dos conjuntos nunca colisionan** (las agencias reales no traen CIF en la tabla de financieros).
- Distribución de confidence **bimodal**: 5.000 @ 0,9 (sintéticos) · 307 @ 0,3 (reales) · 1 @ 0,7.

**Implicación**: los motores están **arquitectónicamente completos** pero **limitados por datos**. La calidad "de producto" depende de un único desbloqueo: **datos reales de identidad + financieros para las empresas que de verdad le importan a arroba** (fichero Iberinform real 3,3M). Sin eso, Value/comparables/narrativa operan sobre datos sintéticos.

---

## 1. Master Database / Data Layer

- **Madurez: ALTA (producción).**
- **Calidad**: esquema canónico unificado (`identity`/`classification`/`financials`/`sources`/`signals`/`lineage`), idempotente, backward-compat. Normalización de CIF/nombre/sección CNAE robusta. HTML-entities saneadas en origen.
- **Limitaciones**: entity resolution **no probado en condiciones reales** (0 dups por dataset disjunto, no por madurez). `lineage`/`confidence` correctos pero confidence es bimodal artificial. Solo 5,8% con dominio.
- **Dependencias pendientes**: fichero Iberinform real (3,3M) → desbloquea cross-matching real, dedupe real y poblará financieros de empresas reales. Es **la dependencia maestra**.

## 2. Search Engine (`POST /skills/search`)

- **Madurez: ALTA (producción para su alcance).**
- **Calidad**: léxico + semántico (LSA) híbrido `0,6·léxico + 0,4·semántico`, p95≈5–16ms sobre 5,3k docs. Filtros category/tags/cnae/cluster_id, paginación, fallback automático. Contrato estable.
- **Limitaciones**: ranking semántico limitado por **texto pobre** (solo 4% tiene descripción) → para empresas sintéticas el semántico aporta poco. Escala: a 3,3M habrá que migrar a índice de texto/Atlas Search (pre-rank cap 500 actual).
- **Dependencias pendientes**: más texto descriptivo (scraping/enriquecimiento) para que el semántico brille; índice escalable para 3,3M.

## 3. Value Engine (`POST /skills/value`)

- **Madurez: MEDIA (funcional pero acotada).**
- **Calidad**: cuando hay EBITDA → `ev_ebitda` con múltiplos sectoriales por sección CNAE, 5 comparables reales del sector, confidence 0,8. Cascada robusta (ev_ebitda → ev_revenue → book_value → insufficient_data). Verificado funcionando.
- **Limitaciones CRÍTICAS**:
  1. **Múltiplos son de referencia (inferred), hardcodeados por sección** — no observados de mercado. BME tiene múltiplos reales por sector pero **no están conectados** a este motor.
  2. **Cobertura real ≈ 0**: las empresas reales (agencias) caen en `insufficient_data`; solo valora el universo sintético.
  3. Comparables solo dentro del universo con financieros (sintético).
- **Dependencias pendientes**: (a) conectar múltiplos reales de **BME Market Intel** (ya existen, 254 cotizadas) → sube precisión inmediatamente; (b) financieros reales (Iberinform real) → cobertura real.

## 4. Recommendation Engine (`POST /skills/recommend`)

- **Madurez: MEDIA-ALTA.**
- **Calidad**: modo `similar` (estructural sector+tamaño+señales) + `thesis` (léxico). Blend `0,6·estructural + 0,25·semántico + 0,15·signal` + boost de grafo `+0,10·g`. Contrato inmutable, fallback limpio.
- **Limitaciones**: **muy dependiente del sector/categoría** (si falta categoría, cae a proximidad por tamaño). El componente de grafo es hoy `similar_to`/`same_cluster`, ambos derivados de los **mismos embeddings** → riesgo de **circularidad** (semántico y grafo miden casi lo mismo). Aporta poca señal independiente hasta que el grafo tenga relaciones de otras fuentes (ownership, co-licitación, etc.).
- **Dependencias pendientes**: relaciones de grafo de **fuentes distintas a embeddings** (ownership BORME/CNMV, co-ocurrencia en licitaciones PLACSP) para que el boost de grafo sea ortogonal y no redundante.

## 5. Analyze Engine (`POST /enrich_company`)

- **Madurez: MEDIA.**
- **Calidad narrativa**: rica y bien estructurada (summary + key_points + risks + opportunities en ES, Claude Sonnet 4.6, "no inventes nada"). Bloques determristas (financial_summary, growth, ratios, peers, relationships, signals) sólidos cuando hay datos.
- **Limitaciones CRÍTICAS**:
  1. **Latencia 4–16s por llamada** con narrativa (Claude). **SIN CACHÉ** → cada vista repite la llamada y el coste.
  2. **Coste por llamada** (Claude) en endpoint **público sin auth** → expuesto a abuso/coste descontrolado.
  3. Narrativa de calidad pero **sobre datos sintéticos** (nombres tipo "Tecnologias TOGA SA") → no fiable para producto hasta tener datos reales.
- **Dependencias pendientes**: (a) **caché de narrativa** persistida (clave = master_company_id + hash de facts) con TTL → elimina latencia/coste en repeticiones; (b) rate-limiting/auth en el endpoint público; (c) datos reales.

## 6. Signal Engine

- **Madurez: ALTA (para señales internas).**
- **Calidad**: 100% del master con `signals[]` + `signal_score` 0-100. 5 categorías: growth (historia 2y), profitability (márgenes/productividad), size (percentil de ingresos en cluster), activity (riqueza de datos), similarity (cluster). Determinista, persistido, consumido por Analyze/Recommend/Search.
- **Señales FALTANTES** (alto valor, requieren fuentes ya presentes pero no cableadas):
  - **Actividad de mercado**: eventos BORME (39k), corporate events BME, concursos — _no_ generan señales por empresa.
  - **Riesgo/solvencia**: CNMV, morosidad/Iberinform real.
  - **Contratación pública**: PLACSP (184k contratos) → señal de tracción comercial por empresa.
  - **Comercio exterior**: DataComex → señal de internacionalización.
- **Dependencias pendientes**: cablear BORME/PLACSP/BME-events/CNMV → señales por empresa (join por CIF). Las fuentes ya existen; falta el join a `companies_master`.

## 7. Knowledge Graph

- **Madurez: BAJA-MEDIA (esquema maduro, contenido incipiente).**
- **Calidad**: colección `company_relationships` independiente, idempotente, índice único. 84.8k relaciones (42,4k `similar_to` + 42,4k `same_cluster`). Cableado a Analyze (bloque `relationships`) y Recommend (boost).
- **Tipos existentes (poblados)**: `similar_to`, `same_cluster` — **ambos derivan de los mismos embeddings/clusters** → una sola dimensión de información.
- **Tipos reservados (NO poblados)**: `competitor_of`, `supplier_candidate`, `acquisition_candidate`, `shareholder_of`, `subsidiary_of`, `same_group`.
- **Fuentes necesarias para ownership** (Ownership Engine): **BORME** (constituciones, nombramientos, cambios societarios — 39k eventos ya ingeridos), **CNMV** (participaciones significativas), registros mercantiles. Para `competitor_of`/`supplier_candidate`: co-ocurrencia en **PLACSP**, sector+geo, comercio.
- **Dependencias pendientes**: parsear estructura societaria de BORME/CNMV → poblar `shareholder_of`/`subsidiary_of`/`same_group`. Esto convierte el grafo en una **segunda dimensión real** (no derivada de texto) y desbloquea P5 Matching con sentido.

---

## Síntesis ejecutiva

| Motor | Madurez | Cuello de botella principal |
|-------|---------|------------------------------|
| Data Layer / Master | ALTA | Datos reales (Iberinform 3,3M) |
| Search | ALTA | Texto descriptivo escaso; escala 3,3M |
| Value | MEDIA | Múltiplos reales (BME) + financieros reales |
| Recommend | MEDIA-ALTA | Grafo redundante con embeddings |
| Analyze | MEDIA | Caché + auth/rate-limit + datos reales |
| Signal | ALTA | Cablear BORME/PLACSP/CNMV/BME-events |
| Knowledge Graph | BAJA-MEDIA | Ownership desde BORME/CNMV |

### Las 4 palancas que más maduran la infraestructura (sin tocar contratos, sin asumir UX)
1. **Datos reales** (Iberinform 3,3M) — desbloquea Value, comparables, Analyze, dedupe real. _Palanca maestra._
2. **Conectar BME múltiplos reales** al Value Engine — ya existen 254 cotizadas con múltiplos sectoriales. _Quick win de precisión._
3. **Caché + protección del endpoint Analyze** — elimina latencia 4–16s repetida y coste/abuso. _Quick win de robustez/coste._
4. **Señales y grafo desde fuentes ya ingeridas** (BORME/PLACSP/CNMV) — añade una dimensión de información **independiente** de los embeddings (rompe la circularidad de Recommend/Graph).
