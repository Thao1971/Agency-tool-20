# SIGNAL_INTELLIGENCE_ENGINE_CONTRACT.md
**Contrato oficial — Signal Intelligence Engine**
_Versión: `signal-intelligence-v1` · 2026-06-25 · Estado: **CONGELADO (FROZEN)** — D1–D8 aprobadas. Cualquier cambio futuro requiere nueva versión del contrato; no se permiten cambios incompatibles sin versión mayor._

> Este motor convierte arroba.com de **analítica pasiva** en **inteligencia proactiva**: detecta oportunidades, riesgos y cambios relevantes en la economía española. Es un **producto independiente** con su propio contrato y APIs. Ningún consumidor accede a fuentes ni al Master directamente; toda la inteligencia de señales se obtiene **exclusivamente** a través de este motor.

---

## 0. Principios
- **Boundary First**: el motor es la frontera. Consumidores (arroba, APIs, Copilots, otros motores) solo invocan la API del Signal Engine.
- **No es una lista de alertas**: es un motor reutilizable de señales explicables, versionadas, persistidas y reproducibles.
- **Determinista y explicable (sin IA)** en `v1`. Toda señal es 100% trazable a dato + regla + umbral resuelto.
- **Idempotente y reproducible**: misma entrada (mismo `master` + misma versión de motor + misma config de umbrales) ⇒ misma señal con el mismo `signal_id`.
- **Parametrizable, no hardcodeado** (D1): umbrales, taxonomía (D6), acciones (D4) y ventanas temporales (D3) viven en configuración versionada, fuera de la lógica del motor.

---

## 1. Taxonomía Canónica de Señales (D6 — oficial y versionada)

La taxonomía es **cerrada y versionada** (`taxonomy_version`). Los tipos NO crecen libremente: añadir una nueva fuente (BORME, CNMV, PLACSP, ayudas públicas, M&A…) consiste **únicamente** en añadir nuevos `signal_type` dentro de estas categorías, **sin romper contratos ni APIs**.

**Categorías canónicas (9):**

| `category` | Responsabilidad | Fuente de datos |
|---|---|---|
| `financial` | Salud y rendimiento financiero | Financial Engine |
| `growth` | Expansión (ingresos, EBITDA, empleo) | Financial Engine + Master history |
| `risk` | Deterioro, anomalías, insolvencia, liquidez | Financial Engine + Master |
| `ownership` | Estructura de propiedad y grupo | Master ownership + KG estructural |
| `corporate` | Cambios societarios y eventos corporativos | Master (diffs) + ⏳ BORME |
| `market` | Posición y dinámica sectorial/territorial | Financial Engine (comparables) + agregados |
| `opportunity` | Tesis accionables (composición de señales) | Composición |
| `transaction` | Operaciones / M&A / cambios de control | ⏳ BME/M&A (fuente pendiente) |
| `operational` | Productividad, eficiencia, plantilla, datos | Financial Engine + Master |

**Catálogo inicial de tipos** (`category.subtype`). Los **umbrales NO aparecen aquí fijos** (ver §2/D1): se resuelven por contexto.

- **financial**: `financial.margin_strong`, `financial.margin_weak`, `financial.low_liquidity`, `financial.high_leverage`, `financial.negative_equity`, `financial.net_loss`, `financial.quality_low`
- **growth**: `growth.revenue_surge`, `growth.ebitda_expansion`, `growth.sustained`, `growth.headcount_expansion`
- **risk**: `risk.revenue_decline`, `risk.margin_compression`, `risk.sustained_decline`, `risk.balance_inconsistency`, `risk.revenue_anomaly`, `risk.data_gap`
- **ownership**: `ownership.foreign_parent`, `ownership.group_member`, `ownership.consolidator`, `ownership.standalone`
- **corporate**: `corporate.officers_change`, `corporate.capital_change`, `corporate.group_change`, `corporate.borme_event` ⏳
- **market**: `market.sector_leader`, `market.outperforms_peers`, `market.underperforms_peers`, `market.fragmented_sector`
- **opportunity**: `opportunity.acquisition_target`, `opportunity.distressed`, `opportunity.roll_up_candidate`, `opportunity.investment_thesis`
- **transaction**: `transaction.ma_event` ⏳, `transaction.control_change` ⏳
- **operational**: `operational.productivity_high`, `operational.productivity_low`, `operational.capital_intensive`

> ⏳ = tipo declarado en la taxonomía pero **pendiente de fuente** (no se emite hasta ingerir BORME/BME/M&A). Honesto: existe el contrato, no se inventa el dato.

El **catálogo completo** (categoría → tipos → regla → dimensiones por defecto → acciones recomendadas → dependencias) se expone vía `GET /catalog` y se versiona con `taxonomy_version`.

---

## 2. Umbrales parametrizables (D1 — nunca hardcodeados)

El motor **no contiene umbrales fijos**. Cada tipo de señal se evalúa mediante un **Threshold Resolver** que resuelve el umbral aplicable en función de un **contexto** y un conjunto de **baselines**:

```jsonc
// Config versionada (colección `signal_thresholds`, fuera del código)
{
  "signal_type": "growth.revenue_surge",
  "metric": "revenue_growth_yoy",
  "operator": ">",
  "baselines": {                 // de qué se compara; orden de prioridad configurable
    "self_history": { "window": "yoy" },        // histórico de la propia empresa
    "sector":       { "dimension": "cnae_section", "stat": "p75" },
    "size_band":    { "dimension": "revenue_band", "stat": "median" },
    "territory":    { "dimension": "provincia", "stat": "median" }   // cuando aplique
  },
  "default_threshold": 0.20,     // fallback explícito si no hay baseline contextual
  "thresholds_version": "thr-v1"
}
```

- Cada señal puede evaluarse respecto a: **histórico propio**, **sector**, **tamaño**, **territorio** (cuando aplique) y **configuración futura** (extensible sin tocar el motor).
- El umbral **resuelto** y su **origen** quedan registrados en la señal (`rule.threshold` + `rule.threshold_source` + `rule.baseline`), garantizando explicabilidad total.
- Cambiar políticas de umbrales = cambiar config (`thresholds_version`), nunca el código.

---

## 3. Modelo de respuesta (objeto Señal)

Cada señal expone **exactamente** estos campos (no caja negra). Incorpora las **cuatro dimensiones independientes** (D2) y la **acción canónica** (D4):

```jsonc
{
  "signal_id": "sig_<hash12>",          // determinista (ver §6)
  "master_id": "mc_<hex12>",
  "signal_type": "growth.revenue_surge",
  "category": "growth",                  // ∈ taxonomía canónica (§1)
  "severity": "opportunity",             // etiqueta derivada (legible); el detalle vive en las 4 dimensiones
  "dimensions": {                        // D2 — cuatro dimensiones INDEPENDIENTES, siempre presentes
    "impact":      0.0-1.0,              // magnitud del efecto económico/estratégico
    "confidence":  0.0-1.0,              // fiabilidad del dato + de la regla
    "urgency":     0.0-1.0,              // cómo de pronto requiere acción
    "persistence": 0.0-1.0               // cuán estable/recurrente es la señal en el tiempo
  },
  "confidence": 0.0-1.0,                 // espejo de dimensions.confidence (compatibilidad/lectura rápida)
  "detected_at": "ISO-8601",
  "source": {                            // de dónde sale el dato que la dispara
    "engine": "financial-intelligence-v1 | master-v1 | knowledge-graph-v1",
    "fields": ["financials.history.revenue"],
    "source_version": "20260519"
  },
  "evidence": {                          // datos concretos que la disparan (valores reales)
    "metric": "revenue_growth_yoy",
    "value": 0.27,
    "window": "yoy",                     // ventana temporal evaluada (D3)
    "comparison": { "prev": 1000000, "current": 1270000, "years": [2023, 2024] }
  },
  "rule": {                              // regla evaluada + umbral RESUELTO (D1)
    "id": "growth.revenue_surge",
    "expression": "revenue_growth_yoy > threshold",
    "threshold": 0.20,
    "threshold_source": "self_history|sector|size_band|territory|default",
    "baseline": { "type": "sector", "dimension": "cnae_section:C", "stat": "p75", "value": 0.18 },
    "thresholds_version": "thr-v1",
    "passed": true
  },
  "recommended_actions": ["add_to_watchlist", "analyze", "contact"],  // D4 — solo del catálogo canónico
  "explanation": "Los ingresos crecieron un 27% interanual (1.000.000€ → 1.270.000€), por encima del umbral sectorial (P75 = 18%).",
  "engine_version": "signal-intelligence-v1",
  "taxonomy_version": "tax-v1"
}
```

> `severity` se conserva como etiqueta legible **derivada** de las dimensiones (regla de mapeo documentada), pero **las cuatro dimensiones se preservan siempre** para que otros motores (Recommendation/Strategy/Transaction) las usen de forma independiente.

Respuesta de `/analyze`:
```jsonc
{
  "master_id", "cif_normalized",
  "identity": { "name","cnae_code","cnae_section","provincia" },
  "signals": [ { …objeto Señal… } ],
  "score": {                              // D2 — derivado, NO sustituye a las dimensiones
    "signal_score": 0-100,                // composición documentada de las 4 dimensiones agregadas
    "aggregate_dimensions": { "impact","confidence","urgency","persistence" },
    "method": "derived_from_dimensions", "formula_version": "score-v1"
  },
  "counts_by_category": { "opportunity": n, "risk": n, … },
  "dependencies": ["master-v1","financial-intelligence-v1","knowledge-graph-v1"],
  "engine_version": "signal-intelligence-v1", "taxonomy_version": "tax-v1",
  "thresholds_version": "thr-v1", "generated_at", "confidence": 0-1
}
```

---

## 4. Catálogo canónico de acciones recomendadas (D4)

El motor **no genera texto libre de acciones**. `recommended_actions` solo contiene valores de este **enum canónico versionado** (`actions_version`). Arroba decide después cómo presentarlas.

```
analyze · monitor · value · compare · investigate · contact ·
buy · sell · raise_capital · add_to_watchlist · request_due_diligence · consult_advisor
```

Cada `signal_type` declara en el catálogo su conjunto de acciones recomendadas por defecto. Añadir nuevas acciones = ampliar el enum (`actions_version`), sin romper el contrato.

---

## 5. Explicabilidad (obligatoria — ninguna señal es caja negra)
Cada señal responde **siempre** a:
1. **Qué dato la disparó** → `source.fields` + `evidence.value` (valores reales).
2. **Contra qué regla se evaluó** → `rule.id` + `rule.expression`.
3. **Qué umbral se aplicó y de dónde sale** → `rule.threshold` + `rule.threshold_source` + `rule.baseline` (D1).
4. **Qué confianza/impacto/urgencia/persistencia tiene** → `dimensions` (D2).
5. **Qué acciones recomienda** → `recommended_actions` (catálogo canónico, D4).

`GET /signal/{signal_id}` devuelve la señal completa **reproducible**: dado el mismo Master + versiones (engine/taxonomy/thresholds), regenera idéntico `signal_id` y evidencia.

---

## 6. Endpoints (contrato público del motor)
Auth: cabecera `X-API-Key` (service key). Prefijo: `/api/v1/signal-intelligence`.

| Método | Endpoint | Propósito |
|---|---|---|
| `POST` | `/analyze` | **Señales por empresa** — `{identifier, windows?}` → señales activas + `score`. |
| `POST` | `/sector` | **Señales por sector** — `{cnae_section\|cnae_code, limit}` → agregados y empresas destacadas. |
| `POST` | `/territory` | **Señales por territorio** — `{provincia\|municipio\|ccaa, limit}` → agregados por geografía. |
| `POST` | `/opportunities` | **Ranking de oportunidades** — `{filters, sort_by_dimension?, limit}` → empresas ordenadas (explicable). |
| `GET`  | `/catalog` | **Taxonomía + tipos** — categorías, tipos, regla, dimensiones por defecto, acciones, dependencias; con `taxonomy_version`/`thresholds_version`/`actions_version`. |
| `GET`  | `/signal/{signal_id}` | **Explicación de una señal concreta** — evidencia, regla, umbral resuelto, dimensiones, linaje (reproducible). |
| `POST` | `/history` | **Histórico de señales** (D5) — `{identifier, signal_type?}` → línea temporal: aparición, duración activa, repeticiones, evolución, desaparición. |

### 6.1 Extensión aditiva v1.1 (2026-07-23) — listado general, conteos reales, variantes JWT

Añadidos **sin romper el contrato congelado** (compatibilidad D10/§10: adiciones dentro de la misma versión mayor). Motivo: exponer el motor de forma segura al navegador de arroba.com (patrón `/view`, JWT en vez de `X-API-Key` de servicio) y separar "listado general de señales" de "ranking de oportunidades" (que solo cubre `severity=="opportunity"`).

| Método | Endpoint | Auth | Propósito |
|---|---|---|---|
| `POST` | `/signals` | `X-API-Key` | **Listado general de señales** — sin restricción de severidad (a diferencia de `/opportunities`), filtrable por `category`/`severity`/`status`/`signal_types`/`provincia`/`cnae_section`/`master_id`, orden por dimensión o timestamp. |
| `GET` | `/signals/view` | JWT | Variante de `/signals` para consumo directo desde el navegador. |
| `GET` | `/signal/{signal_id}/view` | JWT | Variante JWT de `GET /signal/{signal_id}`. |
| `GET` | `/history/view` | JWT | Variante JWT de `POST /history` (query params `identifier`/`signal_type`). |
| `POST` | `/stats` | `X-API-Key` | **Conteos reales no acotados por paginación** (`count_documents`, nunca `len(rows)` capado por `limit`): `total_signals`, `total_opportunities` (`severity=="opportunity"`), desglose `by_severity`, `by_category`, `opportunities_by_type`. |
| `GET` | `/stats/view` | JWT | Variante JWT de `/stats`. |
| `POST` | `/migrate-dedupe` | `X-API-Key` | **Migración de una sola vez** (`migrate_dedupe_and_reindex`) — fusiona duplicados de señales generados antes del fix de identidad de §8.1; idempotente. |

> **Nota importante — bug de identidad corregido (2026-07-23)**: la clave única de una señal (§8) era `(master_id, signal_type, source_version)`. Como `source_version` cambia en cada entrega de datos, cada entrega generaba un documento nuevo para la misma situación continuada (duplicados en Oportunidades, avisos repetidos en Watchlist). **Corregido**: la clave pasa a `(master_id, signal_type)`; `source_version` es ahora un campo del documento (última entrega que la confirmó), no parte de la identidad. `signal_id` (§10) ya NO incluye `source_version` en su hash. Ver `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md` §17 para el detalle completo y la migración a ejecutar en cualquier entorno con datos anteriores a este fix.

---

## 7. Estrategia temporal y de cambios (D3 — snapshots versionados)
El motor se diseña para operar sobre **snapshots versionados**, no solo contra la versión anterior. Cada evaluación puede calcular cambios sobre **ventanas** configurables:

```
windows = [ "last_period", "3y", "5y", "full_history", "sector_reference" ]
```

- **`last_period`** — variación contra el ejercicio/`source_version` inmediatamente anterior.
- **`3y` / `5y`** — tendencias plurianuales (CAGR, dirección sostenida).
- **`full_history`** — todo el histórico disponible.
- **`sector_reference`** — comparación contra baselines sectoriales cuando existan.

La arquitectura queda preparada para análisis temporales **sin rediseñar el motor**: cada señal registra la `window` evaluada en `evidence.window`. Las señales de *cambio* (`corporate.*_change`, `ownership.group_change`) se obtienen del **diff entre snapshots** del Master/KG versionados por `source_version`.

---

## 8. Persistencia e histórico de señales (D5 — desde v1)
Las señales son **conocimiento del sistema** y se persisten **desde la primera versión** en la colección `signals`:

```jsonc
{
  "signal_id", "master_id", "signal_type", "category",
  "dimensions", "evidence", "rule", "recommended_actions", "explanation",
  "status": "active|resolved|disappeared",   // ciclo de vida
  "first_detected_at": "ISO",                 // cuándo apareció
  "last_seen_at": "ISO",                       // última vez observada
  "occurrences": 3,                            // cuántas veces se ha repetido
  "trend": "worsening|improving|stable",       // si ha empeorado/mejorado
  "history": [ { "observed_at", "source_version", "dimensions", "evidence" } ],
  "engine_version", "taxonomy_version", "thresholds_version", "actions_version"
}
```
Clave única: `(master_id, signal_type, source_version)`. Permite responder: **cuándo apareció, cuánto lleva activa, cuántas veces se repitió, si ha empeorado, si desapareció y cómo ha evolucionado** (vía `POST /history`).

---

## 9. Dependencias (estrictas)
Consume **exclusivamente**: **Master Layer** (`master-v1`), **Financial Intelligence Engine** (`financial-intelligence-v1`) y **Knowledge Graph estructural** (`master_relationships`). **Prohibido** leer fuentes originales o `norm_*` directamente. Tipos sin fuente (BORME/M&A) → declarados en taxonomía como ⏳ pendientes, no se emiten ni se inventan.

---

## 10. Versionado, reproducibilidad y trazabilidad
- **Versiones independientes**: `engine_version` (`signal-intelligence-v1`), `taxonomy_version` (`tax-v1`), `thresholds_version` (`thr-v1`), `actions_version` (`act-v1`), `score formula_version` (`score-v1`). Cada señal las propaga.
- **`signal_id` determinista**: `hash(master_id + signal_type + engine_version + thresholds_version)` → misma situación = mismo id **estable entre entregas** (idempotente, deduplicable, comparable). **Corrección v1.1 (2026-07-23)**: antes incluía también `source_version`, lo que generaba un id distinto en cada entrega de datos para la misma situación continuada — ver §6.1.
- **`source_version`** se conserva como campo del documento (última entrega que confirmó la señal) para trazabilidad "as-of", pero ya no forma parte de la identidad de la señal.
- **Compatibilidad**: adiciones (nuevos tipos dentro de la taxonomía, nuevas acciones, nuevos baselines) = compatibles; cambios incompatibles ⇒ versión mayor con convivencia.

---

## 11. Migración legacy
`services/signal_engine.py` (opera sobre `companies_master`, persiste `signals[]`/`signal_score`) queda **absorbido**: (1) paridad sobre `master_companies` → (2) migración de consumidores (Analyze/Recommend/Search) a la API del Signal Engine → (3) retirada de la dependencia de `companies_master`.

---

## D7 — Señales compuestas (Composite Signals)
El motor **construye señales compuestas a partir de señales ya detectadas** (no solo individuales). Ejemplos canónicos:
- `growth.sustained` + `financial.margin_strong` + `transaction.ma_event` → **`opportunity.consolidation_candidate`**
- `risk.*` (caída EBITDA) + `financial.high_leverage` + `corporate.group_change` → **`opportunity.potential_distress`**
- `financial.margin_strong` + `growth.sustained` + `market.fragmented_sector` → **`opportunity.hidden_gem`**
- `growth.revenue_surge` + `operational.productivity_high` + (expansión geográfica) → **`opportunity.expansion_opportunity`**

Reglas de las señales compuestas:
- **Reutilizan señales existentes como evidencia** → `evidence.components = [signal_id, …]` (no recalculan dato base).
- **Trazabilidad y explicabilidad completas** → heredan/agregan dimensiones de sus componentes; `explanation` cita los componentes.
- **Versionadas igual que el resto** (`engine_version`, `taxonomy_version`, `composites_version`).
- **Definición declarativa y versionada** (`composites_version`): cada compuesta declara sus componentes `requires` (obligatorios) y `optional` (refuerzo). Si un componente requiere una fuente ⏳ aún no disponible, la compuesta simplemente no se emite (honesto). Añadir nuevas compuestas = ampliar config, **sin tocar el contrato del motor**.
- **Dimensiones de la compuesta** (D2): derivadas de las de sus componentes (p. ej. `confidence = min`, `impact = max`, `urgency = max`, `persistence = media`), documentado en `composites_version`.

## D8 — Consumidores independientes (motor reutilizable, agnóstico de UI)
El Signal Engine **no se diseña para arroba.com en exclusiva**. Es un motor reutilizable por cualquier consumidor:
`arroba.com · Arroba Copilot · APIs externas · Recommendation Engine · Strategy Engine · Transaction Engine · futuros productos`.
- El contrato **nunca** contiene conceptos de interfaz de usuario (colores, iconos, textos de presentación, orden visual, etc.).
- El motor entrega **únicamente inteligencia estructurada** (señales + dimensiones + evidencia + acciones canónicas). La **presentación es responsabilidad del consumidor**.
- `severity` y `recommended_actions` son **etiquetas/enum estructurados**, no decisiones de UI.
- Auth uniforme por `X-API-Key`; ningún consumidor es privilegiado en el contrato.

---

## 12. Criterios de aceptación

### Definition of Ready (contrato congelable) — estado tras D1–D6
1. ✅ Taxonomía canónica versionada (D6) — 9 categorías cerradas; nuevas fuentes = nuevos tipos sin romper APIs.
2. ✅ Umbrales parametrizables por contexto (D1) — sin hardcodeo; baselines self/sector/size/territory + default explícito.
3. ✅ Cuatro dimensiones independientes (D2) — impact/confidence/urgency/persistence preservadas; score derivado, no sustituye.
4. ✅ Estrategia temporal sobre snapshots versionados (D3) — ventanas last/3y/5y/full/sector.
5. ✅ Catálogo canónico de acciones (D4) — enum cerrado, sin texto libre.
6. ✅ Persistencia e histórico desde v1 (D5) — ciclo de vida + línea temporal.
7. ✅ Dependencias limitadas a Master + Financial + KG; tipos sin fuente marcados ⏳.
8. ✅ Señales compuestas declarativas y versionadas (D7) — reutilizan señales como evidencia, trazables.
9. ✅ Motor agnóstico de UI, reutilizable por cualquier consumidor (D8).

### Definition of Done (implementación, cuando arranque)
- Motor `signal-intelligence-v1` desacoplado en `services/engines/signal/`, API `/api/v1/signal-intelligence/*` con `X-API-Key`.
- Cada señal cumple §3/§4/§5; umbrales resueltos por config (§2); dimensiones siempre presentes; `signal_id` determinista.
- Persistencia en `signals` con histórico funcional (`/history`); umbrales/taxonomía/acciones en config versionada.
- Suite smoke verde + verificación end-to-end contra URL externa; este documento pasa a estado **ESTABLE**.
- Sin lectura directa de fuentes ni `norm_*`; sin IA en `v1`.
