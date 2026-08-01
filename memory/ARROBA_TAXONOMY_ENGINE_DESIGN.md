# ARROBA Taxonomy Registry v1 + Company Classification Engine — Diseño técnico

> Cómo convertir `ARROBA_COMPANY_TAXONOMY_v1.md` (canon congelado) en infraestructura: un **Registry**
> versionado y un **motor de clasificación** que asigna a cada empresa su clasificación ARROBA
> multiclase + Fingerprint, con evidencia y confianza. Diseño ANTES del código (patrón de la casa).
> Estado: DISEÑO para validar. Boundary First: reutiliza lo que ya existe, no recrea.

## 0. Principios
- **Determinista y auditable primero**; IA solo como refuerzo acotado y fact-lock (§4).
- **Evidencia + confianza en todo**: ninguna clasificación sin `evidence[]` y `confidence`.
- **Versionado**: el árbol evoluciona sin romper histórico (`taxonomy_version`).
- **Reutiliza**: `services/cnae_catalog.py`, Semantic Engine (`services/engines/semantic/*`), el bundle de
  `company_intelligence`/`financial_enrich`. No se duplica inteligencia.
- **Idempotente**: misma empresa + misma versión + misma evidencia ⇒ misma clasificación.

## 1. Taxonomy Registry (modelo de datos versionado)
Colección `taxonomy_nodes` (árbol) — un documento por nodo:
```
{ id,                      # estable: "S03", "IND-S03-ADTECH", "CAT-...-CONTEXTUAL"
  level,                   # sector | industry | category
  parent_id,               # None para sector
  label_es, aliases[],     # sinónimos/keywords para el matching
  status,                  # active | deprecated | merged_into:<id>
  taxonomy_version,        # "v1.0"
  created_at, updated_at }
```
Registros canónicos transversales (misma forma, colección `taxonomy_dimensions`, `dimension` ∈
verticals | capabilities | business_models | client_types | technologies | value_chain):
```
{ id, dimension, label_es, aliases[], status, taxonomy_version }
```
Notas: los **ids son estables** (no se reciclan); fusionar = `status: merged_into`; dividir = nuevos ids
+ deprecación. `build_registry_v1()` siembra los 11 sectores + industrias + dimensiones del canon
(idempotente por `id`). El nivel *categoría* se siembra parcial y se completa tras la auditoría.

## 2. Clasificación empresa↔taxonomía (multiclase)
Colección `company_classifications` — una fila por (empresa, nodo/dimensión):
```
{ company_id, axis,            # sector|industry|category|vertical|capability|business_model|client_type|technology|value_chain
  taxonomy_id, label_es,
  role,                        # primary | secondary | adjacent   (solo sector/industry/category)
  confidence,                  # 0..1
  evidence: [{source, detail, weight}],
  core_technology,             # solo axis=technology: true/false (vs technology_used)
  source,                      # rules | semantic | ai | manual
  classified_by, classified_at, taxonomy_version }
```
Más un documento agregado por empresa `company_fingerprint` (§5).

## 3. Company Classification Engine — pipeline
`classify(company_id, opts) -> ClassificationResult` (determinista salvo el paso 5 opcional):
- **P0 · Evidencia:** reúne señales del bundle existente — CNAE(s), razón social/nombre comercial,
  perfil semántico/web (Semantic Engine), objeto social si lo hay, KPIs (tamaño), geografía.
- **P1 · Base determinista:**
  - *CNAE → ARROBA*: puente `cnae_to_arroba` (mapa CNAE división/grupo → sector/industria candidatos)
    apoyado en `cnae_catalog`. Da un ancla, no la última palabra.
  - *Reglas por alias/keywords*: match de `aliases[]` del Registry contra nombre + perfil semántico →
    candidatos de industria/categoría y dimensiones transversales.
- **P2 · Scoring y roles:** combina señales por candidato → `confidence`; el de mayor confianza por eje
  jerárquico = `primary`; resto por umbrales → `secondary` (≥0.6) / `adjacent` (≥0.4). Config versionada.
- **P3 · Tecnología core vs used:** regla dura — una tecnología solo es `core_technology=true` si es el
  centro del producto/modelo (evidencia fuerte en perfil semántico/objeto), no por mención de uso.
- **P4 · Fingerprint (§5).**
- **P5 · Refuerzo IA (OPCIONAL, off por defecto):** ver §4.

Salida: lista de `company_classifications` + `company_fingerprint` + `coverage`/`overall_confidence`.

## 4. Recomendación de motor (respuesta a "lo decides tú")
**Backbone determinista: Reglas + Semantic Engine.** Para 24.992 empresas (y cientos de miles después)
es barato, auditable, reproducible y sin coste por empresa; además el Semantic Engine ya extrae perfil
de negocio. La IA generativa por empresa a esa escala es cara y difícil de auditar como capa base.

**IA como refuerzo acotado (fase posterior, opt-in):** activable por `TAXONOMY_AI_PROVIDER` solo para
los casos de **baja confianza** o **empate** tras P1–P2 (p. ej. `overall_confidence < 0.6`). Reutiliza
`docstudio/model_provider`, fact-lock: la IA elige entre los **nodos existentes** del Registry a partir
de la evidencia dada; NO inventa categorías ni cifras. Se marca `source: ai`. Esto acota coste y mantiene
determinismo en el grueso.

## 5. Classification Fingerprint
`company_fingerprint`: `{ company_id, axes: {sector, industry, vertical, capabilities, business_model,
client, technology}: 0..100, taxonomy_version, computed_at }`. Vector normalizado para **similitud**
(coseno sobre los ejes + solapamiento de ids). Alimenta Similar Companies, Comparables, Matching, Buyer
Fit, Roll-up, Peer Universe, Recommendation y Copilot.

## 6. Peer Universe Resolver
`peers(company_id, k, filters) -> [company_id...]`: no todos los del sector. Puntúa candidatos por
**Categoría + Industria + Capacidades + Modelo de negocio + Vertical + Tamaño + Geografía + similitud de
Fingerprint/semántica**, con pesos versionados; devuelve top-k + `why[]` (por qué es comparable). Es la
base para que percentiles, márgenes, múltiplos y benchmarks tengan sentido (evita comparar una agencia de
8 M€ con Publicis).

## 7. API (service-key + JWT interno, patrón Copilot)
Registry (lectura): `GET /taxonomy/tree`, `GET /taxonomy/dimensions`, `GET /taxonomy/node/{id}`.
Clasificación: `POST /taxonomy/classify` (una empresa), `POST /taxonomy/classify-batch` (async, cola),
`GET /taxonomy/company/{id}` (clasificación + fingerprint), `POST /taxonomy/peers` (Peer Universe).
Admin/gobernanza: alta/deprecación/fusión de nodos (audit), `bump` de `taxonomy_version`.

## 8. Versionado y gobernanza
- `taxonomy_version` en Registry y en cada clasificación. Cambios menores de categorías → v1.x; cambios
  estructurales → v2. Reclasificación por lotes al subir versión; el histórico se conserva.
- Auditoría de cada alta/fusión/split y de las clasificaciones `manual`/`ai`.

## 9. ADRs
1. **Ids estables, nunca reciclados** (fusión/split preservan histórico).
2. **Determinista primero, IA como refuerzo opt-in fact-lock** (coste/auditoría a escala).
3. **Evidencia+confianza obligatorias**; sin evidencia no hay clasificación.
4. **Boundary First**: CNAE, Semantic, financials y company_intelligence se reutilizan.
5. **Multiclase con role** (primary/secondary/adjacent) + doble modo de búsqueda (Primary Industry).
6. **Fingerprint como vector de similitud** — activo diferencial; peers no por sector plano.

## 10. Plan por fases
- **F1 · Registry v1:** modelos + `build_registry_v1()` (siembra 11 sectores, industrias y dimensiones) +
  API de lectura + tests. Sin clasificar aún.
- **F2 · Classification Engine (determinista):** puente CNAE→ARROBA + reglas alias/semántica + scoring +
  roles + core-vs-used + persistencia idempotente; `classify` de una empresa + tests deterministas.
- **F3 · Primera pasada + auditoría:** `classify-batch` sobre las 24.992 de Iberinform + informe +
  auditoría de 100–200 (huecos/solapamientos/splits) → iterar árbol (v1.x).
- **F4 · Fingerprint + Peer Universe Resolver** + tests.
- **F5 · Integración:** búsqueda por taxonomía (doble modo), comparables/peers reales, y consumo por el
  Copilot (capabilities/atribución) y los documentos.
- **Futuro:** refuerzo IA opt-in para baja confianza; UI de curación del Registry.

## 11. Decisiones abiertas (para validar antes de F1)
1. Ámbito de F1: ¿sembrar solo sectores+industrias, o también un primer set de categorías por industria?
2. ¿`company_id` de clasificación = master_id del esquema legacy o cif normalizado? (coherencia con el
   resto de motores).
3. Umbrales de rol (primary/secondary≥0.6/adjacent≥0.4) — validar valores.
