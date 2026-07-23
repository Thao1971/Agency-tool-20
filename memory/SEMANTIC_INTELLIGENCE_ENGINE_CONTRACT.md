# SEMANTIC_INTELLIGENCE_ENGINE_CONTRACT.md
**Contrato oficial (PROPUESTA) — Semantic Intelligence Engine**
_Versión: `semantic-intelligence-v1` · 2026-06-26 · Estado: **CONGELADO (FROZEN)** — D-S1…D-S6 aprobadas. Cualquier cambio posterior requiere versionado; no se permiten cambios incompatibles sin versión mayor._

> El producto principal de este motor es el **Company Semantic Profile**: la representación canónica de **qué es realmente una empresa**. Embeddings, Atlas Vector Search, búsqueda semántica, similitud, comparables y matching son **herramientas derivadas** del perfil, **no** el objetivo. El perfil es **independiente de cualquier tecnología concreta de embeddings**.

---

## 0. Lugar en la Intelligence Layer
Tercer **PRODUCTOR de conocimiento** (tras Financial y Signal), según `INTELLIGENCE_LAYER_ARCHITECTURE.md`.
- **Consume**: Master Layer (`master-v1`) — fuente única; opcionalmente Financial (`financial-intelligence-v1`) y Signal (`signal-intelligence-v1`) para enriquecer el perfil.
- **No consume**: Recommendation/Strategy/Transaction (DAG acíclico) ni fuentes originales/Normalized.
- **Desbloquea**: Recommendation (comparables/matching), Strategy y Transaction; y Universal Search para consumidores.

---

## 1. Filosofía
- **Pregunta que responde**: *¿Qué es realmente una empresa?* (Financial: cómo funciona económicamente · Signal: qué está ocurriendo · Semantic: qué es).
- **Profile First, embeddings después**: primero se construye una representación **estructurada, explicable y tecnología-agnóstica**; los embeddings son **una implementación** del perfil, versionada y sustituible.
- **Boundary / Contract / Explainability First**: el motor es la frontera; los consumidores obtienen semántica solo vía su contrato; cada elemento del perfil es trazable a su evidencia y método.
- **Master como única verdad**: el perfil y **todos** los embeddings se construyen **exclusivamente** desde el Master consolidado (nunca sobre entidades sin consolidar ni sobre fuentes crudas).

---

## 2. Responsabilidades
1. Construir y mantener el **Company Semantic Profile** canónico por `master_id`.
2. Derivar y versionar **embeddings** a partir del perfil (no de datos crudos).
3. Ofrecer **similitud** entre empresas y **búsqueda semántica** (Universal Search) sobre el perfil/embedding.
4. Exponer **relaciones semánticas** (similares, competidores potenciales, vecinos sectoriales) — distintas de las relaciones estructurales de ownership (KG).
5. Garantizar **explicabilidad y linaje** por cada campo del perfil y por cada embedding (versión, modelo, fuentes, checksum).

> **No** es responsabilidad de este motor: comparables financieros (Financial), señales (Signal), matching de operaciones (Recommendation/Transaction). Aporta la **capa semántica** que esos motores reutilizan.

---

## 3. Entradas
- **Master Layer (`master-v1`)** — `objeto_social` (texto rico), `classification` (CNAE code/section/division/description), `location`, `ownership` (+ `group_id`), `size`, `identity`, `contact.domain`. **Obligatorio y único origen de identidad.**
- **Financial Engine (opcional)** — tamaño/segmento, intensidad de capital, perfil de márgenes → enriquece "posicionamiento"/"contexto económico".
- **Signal Engine (opcional)** — señales activas → enriquecen "contexto"/"momento" del perfil.
- **Catálogos internos** — taxonomía CNAE/sectores y (futuro) taxonomía de capacidades/tecnologías.
- **Prohibido**: leer fuentes originales (web crawler, Iberinform, etc.) o `norm_*` directamente. Si se requiere texto web, debe haber sido consolidado previamente en el Master por el Foundation Engine.

---

## 4. Salida — Company Semantic Profile (producto principal)

Representación **estructurada y tecnología-agnóstica**. Cada dimensión lleva valor + evidencia + método + confianza (Explainability First):

```jsonc
{
  "master_id": "mc_<hex12>", "cif_normalized": "…",
  "profile_version": "semantic-profile-v1",
  "semantic_profile": {
    "economic_activity":    { "value": "…", "status":"available|partial|unavailable", "evidence": ["objeto_social","cnae_code"], "method": "rules|ai", "confidence": 0.0-1.0 },
    "capabilities":         [ { "value":"…","status":"…","evidence":[…],"method":"…","confidence":… } ],
    "products_services":    [ { "value":"…","status":"…","evidence":[…],"method":"…","confidence":… } ],
    "technologies":         [ { "value":"…","status":"…","evidence":[…],"method":"…","confidence":… } ],
    "customers":            [ { "value":"…","status":"…","evidence":[…],"method":"…","confidence":… } ],
    "suppliers":            [ { "value":"…","status":"…","evidence":[…],"method":"…","confidence":… } ],
    "sectors":              [ { "value":"…","cnae":"…","status":"…","confidence":… } ],
    "subsectors":           [ { "value":"…","status":"…","confidence":… } ],
    "value_chain":          { "position":"upstream|midstream|downstream|integrated","status":"…","evidence":[…],"confidence":… },
    "value_proposition":    { "value":"…","status":"…","method":"ai|rules","confidence":… },
    "competitive_advantages":[ { "value":"…","status":"…","evidence":[…],"confidence":… } ],
    "positioning":          { "value":"…","segment":"…","status":"…","confidence":… },
    "economic_context":     { "value":"…","status":"…","evidence":["financial-intelligence-v1","signal-intelligence-v1"],"confidence":… },
    "semantic_relationships":[ { "master_id":"…","type":"similar|peer|potential_competitor","score":0.0-1.0,"basis":"embedding|sector" } ]
  },
  "semantic_summary": { "text": "…", "method": "ai|rules", "model": "<model|null>", "confidence": … },
  "coverage": { "score": 0-100, "fields_present": n, "fields_total": 14,
                "by_status": { "available": n, "partial": n, "unavailable": n } },   // completitud explicable
  "embedding": {                          // ARTEFACTO DERIVADO (no es el perfil)
    "embedding_version": "emb-v1", "provider": "<provider>", "model": "<model-name>", "dimension": 768,
    "sources": ["semantic_profile.economic_activity","…"],   // qué partes del perfil lo generan
    "profile_checksum": "sha256",          // del perfil que lo originó → reproducibilidad/recálculo
    "generated_at": "ISO"
  } /* | null si aún no generado */,
  "lineage": { "master_source_version":"…","engines_used":["financial-intelligence-v1","signal-intelligence-v1"],
               "ai_used": true|false, "ai_model": "<model|null>" },
  "engine_version": "semantic-intelligence-v1", "generated_at": "ISO", "confidence": 0.0-1.0
}
```

> El **perfil** es estable y agnóstico. El bloque **`embedding`** puede cambiar de modelo/versión **sin alterar el contrato del perfil** (sustituibilidad: D-S2).

---

## 5. Contratos / API (contrato público del motor)
Auth: `X-API-Key` (service key). Prefijo: `/api/v1/semantic-intelligence`. Agnóstico de UI (D8 de la capa).

| Método | Endpoint | Propósito |
|---|---|---|
| `POST` | `/profile` | **Company Semantic Profile** — `{identifier}` → perfil canónico completo (producto principal). |
| `POST` | `/embedding` | **Embedding derivado** — `{identifier}` → vector + metadatos (`embedding_version/model/sources/profile_checksum`). |
| `POST` | `/similar` | **Similitud / comparables semánticos** — `{identifier, limit, filters?}` → empresas similares con score + base explicable. |
| `POST` | `/search` | **Universal Search semántica** — `{query, limit, filters?}` → empresas por significado (no keyword). |
| `GET`  | `/profile/schema` | **Esquema del perfil** — dimensiones, métodos admitidos, versión. |
| `GET`  | `/catalog` | Versiones (`profile/embedding/engine`) + taxonomías usadas + modelo de embeddings activo. |

---

## 6. Capacidades
1. **Company Semantic Profile** canónico (las 14 dimensiones del §4) — producto principal.
2. **Embeddings versionados** derivados del perfil (no de datos crudos), con `profile_checksum` para recálculo idempotente.
3. **Similitud entre empresas** y **comparables semánticos** (insumo para Recommendation).
4. **Búsqueda semántica / Universal Search** por significado.
5. **Relaciones semánticas** (similares/peers/competidores potenciales) — distintas del KG estructural de ownership.
6. **Coverage/quality score** del perfil (completitud y confianza, explicable).

> Comparables financieros, matching de operaciones y tesis NO se hacen aquí: los construyen los consumidores reutilizando esta capa.

---

## 7. Explicabilidad (obligatoria)
- **Por cada dimensión del perfil**: `evidence` (qué datos del Master la sustentan), `method` (`rules` o `ai`), `confidence`.
- **Distinción honesta rules vs AI**: si una dimensión se infiere con IA (p. ej. value_proposition, summary, extracción de capacidades desde `objeto_social`), se marca `method:"ai"` + `ai_model`, con la evidencia textual de origen. Lo determinista se marca `method:"rules"`.
- **Por cada embedding**: `embedding_version`, `model`, `sources` (partes del perfil), `profile_checksum`, `generated_at` → reproducible y recalculable.
- **`coverage`**: completitud del perfil cuantificada (no caja negra sobre lo que falta).
- **Strict Master sourcing**: `lineage.master_source_version` garantiza "as-of"; ningún campo proviene de fuentes crudas.

---

## 8. Versionado y reproducibilidad
- **Versiones independientes**: `engine_version` (`semantic-intelligence-v1`), `profile_version` (`semantic-profile-v1`), `embedding_version` (`emb-v1`). El perfil y el embedding evolucionan **por separado**.
- **`profile_checksum`**: hash del perfil → si no cambia, no se recalcula el embedding (idempotente, incremental). Si cambia el modelo de embeddings, sube `embedding_version` **sin tocar** `profile_version`.
- **Compatibilidad**: añadir dimensiones/relaciones = aditivo (compatible); cambios incompatibles ⇒ versión mayor con convivencia (gobernanza de la capa).
- **Persistencia**: perfil + embedding persistidos por `master_id` (colección propia), regenerables como **handler de job** (nunca en request) sobre el Master consolidado, marcando `dirty` aguas abajo.

---

## 9. Dependencias estrictas
Consume **solo** Master (`master-v1`) + opcionalmente Financial/Signal (vía sus contratos). **Embeddings SOLO sobre el Master consolidado** (nunca sobre entidades sin resolver ni fuentes crudas). Migración legacy: `taxonomy_embeddings` (LSA local) + parte semántica de `skills_search` → absorbidos por este motor.

---

## 10. Criterios de aceptación

### Definition of Ready (para congelar el contrato) — requiere resolver D-S1…D-S6
1. Perfil canónico (14 dimensiones del §4) aprobado como **producto principal**, agnóstico de tecnología.
2. Embedding como **artefacto derivado y versionado**, sustituible sin cambiar el contrato del perfil.
3. Estrategia de **explicabilidad rules vs AI** aprobada (qué dimensiones admiten IA y cómo se traza).
4. Dependencias limitadas a Master (+ opc. Financial/Signal); embeddings solo sobre Master.
5. Endpoints (§5) y modelo de salida (§4) aprobados.
6. Tecnología de embeddings y de búsqueda vectorial decididas (ver D-S4) o marcadas como sustituibles.

### Definition of Done (implementación, cuando arranque)
- Motor `semantic-intelligence-v1` desacoplado en `services/engines/semantic/`, API `/api/v1/semantic-intelligence/*` con `X-API-Key`.
- Perfil construido **solo** desde Master; cada dimensión con evidencia/método/confianza; `coverage` calculado.
- Embedding derivado con `profile_checksum` reproducible; similitud + Universal Search funcionando.
- Regeneración como job idempotente; persistencia versionada; suite smoke verde + verificación end-to-end contra URL externa.
- `SEMANTIC_INTELLIGENCE_ENGINE_CONTRACT.md` pasa a estado ESTABLE.

---

## Decisiones arquitectónicas cerradas (D-S1…D-S6) — congeladas en `semantic-intelligence-v1`

- **D-S1 — IA híbrida y trazable**: reglas primero; IA permitida **solo** cuando aporte extracción semántica real (p. ej. `value_proposition`, `semantic_summary`, extracción de `capabilities`/`technologies` desde `objeto_social`). Toda salida IA es **trazable** (`method:"ai"` + `ai_model` + `evidence` textual de origen). **Cada dimensión declara `method`**. **Nunca se aceptan afirmaciones sin evidencia**: la IA no inventa capacidades, clientes, proveedores ni ventajas competitivas; sin evidencia → `status:"unavailable"`.
- **D-S2 — `EmbeddingProvider` intercambiable**: el contrato **no se acopla a ningún proveedor**. Se define una abstracción `EmbeddingProvider`; en `v1` se usa la opción más estable disponible en el entorno actual, y el modelo puede cambiar **sin romper consumidores**. Todo embedding guarda: `provider`, `model`, `embedding_version`, `profile_checksum`, `generated_at`.
- **D-S3 — `VectorSearchBackend` (Atlas no obligatorio)**: `v1` **no se bloquea por Atlas**. Mientras el entorno use Mongo local, la similitud se calcula por **cómputo controlado top-k** (cosine) sobre perfiles ya generados, con blocking (D-S5). El contrato habla de `VectorSearchBackend` abstracto; **Atlas Vector Search (HNSW)** queda como backend futuro cuando exista clúster adecuado.
- **D-S4 — 14 dimensiones desde v1, cobertura parcial explícita**: se mantienen las **14 dimensiones** en el contrato. Cada una incluye `status: available|partial|unavailable` + `evidence` + `confidence` + `method`. **No se elimina ninguna dimensión por falta de datos**; la ausencia de evidencia es **explícita** (`unavailable`).
- **D-S5 — Relaciones semánticas on-demand (evita O(n²))**: en `v1` se calculan **on-demand**, **top-k**, con **blocking por sector/tamaño/actividad**. Materialización **solo de relaciones de alta confianza** queda diferida al futuro.
- **D-S6 — Alcance v1 (sin Universal Search completo)**: `v1` construye solo las capacidades semánticas necesarias — `/profile`, `/embedding`, `/similar`, `/search` (semántico básico), `/profile/schema`, `/catalog`. **Universal Search completo** (combinando Financial + Signal + Master) se construirá **después**, una vez validado Semantic.

### Abstracciones del contrato (estables, agnósticas)
- **`EmbeddingProvider`** — interfaz: `embed(text) -> {vector, provider, model, dimension}`. Implementación de `v1` sustituible; consumidores nunca dependen del proveedor concreto.
- **`VectorSearchBackend`** — interfaz: `top_k(vector, k, block) -> [(master_id, score)]`. `v1`: cómputo local controlado. Futuro: Atlas Vector Search. El cambio de backend **no altera** el contrato de `/similar` ni `/search`.

> **Recordatorio del objetivo del sprint**: construir el **Company Semantic Profile** como representación semántica canónica de cada empresa. Los embeddings son una **implementación derivada**, no el objetivo.

---

## Histórico de decisiones (referencia)
Las decisiones se cerraron así antes de la congelación: D-S1 (IA híbrida trazable), D-S2 (EmbeddingProvider intercambiable), D-S3 (VectorSearchBackend; Atlas no obligatorio), D-S4 (14 dimensiones + cobertura parcial explícita), D-S5 (relaciones on-demand top-k con blocking), D-S6 (alcance v1 acotado, sin Universal Search completo).
