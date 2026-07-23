# MASTER_LAYER_CONTRACT.md
**Contrato canónico oficial del Master Layer — Agency Tool ↔ arroba.com**
_Versión: `master-v1` · 2026-06-25 · Estado: ESTABLE_

> Este documento es la **única referencia** para cualquier consumidor externo (arroba.com u otros servicios). Los consumidores dependen EXCLUSIVAMENTE de este contrato, nunca de detalles internos de implementación ni de las fuentes originales.
>
> **`master_companies` = colección canónica oficial.** `companies_master` = colección **legacy en retirada** (ver Política de evolución). Criterio de deprecación: cuando todos los engines consuman exclusivamente `master_companies`.

---

## 1. Modelo de Master Company (`master_companies`)

```jsonc
{
  "master_id": "mc_<hex12>",        // identificador interno PERMANENTE, independiente de proveedor
  "cif_normalized": "B59022921",     // clave natural (única). Mayúsculas, sin separadores
  "status": "active",                // ciclo de vida: active | merged | deprecated
  "identity": {
    "legal_name": "string|null",
    "commercial_name": "string|null",
    "aliases": ["string"],
    "cif": "string|null",            // CIF original tal cual
    "country": "string|null"
  },
  "classification": {
    "cnae_code": "string|null",
    "cnae_description": "string|null",
    "cnae_division": "string|null",
    "cnae_section": "string|null"
  },
  "location": { "provincia": "…", "municipio": "…", "codigo_postal": "…", "pais": "…" },
  "contact": { "web": "string|null", "domain": "string|null" },
  "name_key": "string",              // razón social normalizada (deaccent+lower, sin forma jurídica)
  "size": { "employees_total": "int|null", "capital_social": "float|null" },
  "financials": {
    "latest": { "year": "int", "basis": "individual|consolidated",
                "revenue": "float|null", "ebitda": "float|null", "ebitda_margin": "float|null",
                "equity": "float|null", "total_assets": "float|null",
                "net_income": "float|null", "operating_income": "float|null" } /* | null */,
    "history": [ { "year": "int", "basis": "…", "revenue": "…", "ebitda": "…", "net_income": "…" } ]
  },
  "ownership": {
    "shareholders": [ { "cif": "…|null", "name": "…", "pct": "float|null" } ],
    "parents":      [ { "cif": "…|null", "name": "…", "pct": "float|null" } ],
    "ultimate_parent": { "cif": "…|null", "name": "…", "pct": "…" } /* | null */,
    "investees":    [ { "cif": "…|null", "name": "…", "pct": "float|null" } ],
    "group_id": "grp_<id>|null"      // componente conexa (union-find) sobre parent/ultimate-parent
  },
  "officers_count": "int",
  "objeto_social": "string|null",    // texto rico (base del futuro Company Semantic Profile)
  "provenance": { "<field>": [ { "source": "…", "value": "…", "observed_at": "ISO", "confidence": 0.9 } ] },
  "sources": [ { "source": "iberinform", "external_id": "<cif>", "source_version": "20260519",
                 "source_file_id": "uuid", "ingested_at": "ISO" } ],
  "pipeline_version": "master-v1",
  "source_hash": "sha256",           // hash del perfil de entrada → idempotencia / incrementales
  "dirty": "bool",                   // pendiente de recálculo aguas abajo (signals/embeddings/KG)
  "created_at": "ISO", "updated_at": "ISO", "built_at": "ISO"
}
```

## 2. Esquema de `entity_xref` (mapa fuente → master, NO destructivo)
```jsonc
{ "source": "iberinform", "id_type": "cif|iberinform_id|domain",
  "external_id": "<valor>", "master_id": "mc_…",
  "source_version": "20260519", "created_at": "ISO", "updated_at": "ISO" }
```
Clave única: `(source, id_type, external_id)`. **Las fuentes originales nunca se modifican**; toda relación proveedor↔entidad se mantiene por referencia aquí.

## 3. Reglas de Entity Resolution (explicables, en orden de prioridad)
1. **`exact_cif`** — `cif_normalized` vía `entity_xref` o `master_companies` (confianza 1.0).
2. **`domain`** — dominio web normalizado (0.9).
3. **`name_province`** — `name_key` + `provincia` como bloque (0.7).
4. Sin match → nuevo `master_id` permanente.
> Arquitectura preparada para añadir reglas **probabilísticas/IA** como pasos adicionales sin cambiar a los consumidores. Cada resolución registra `match_rule` + `confidence`.

## 4. Reglas de Merge (no destructivo)
- Cada campo conflictuable conserva **todos** los candidatos en `provenance[field]` = `[{source, value, observed_at, confidence}]`.
- **Valor canónico** = `max(confidence, prioridad_de_fuente, recencia)`. Prioridad: `manual(200) > iberinform(100) > bme(60) > web(50)`.
- Re-ejecutar una fuente reemplaza **solo** su candidato para ese campo; **nunca** destruye los de otras fuentes.
- Cuando las fuentes discrepan, se conservan ambos valores y la decisión es posterior y reproducible.

## 5. Estados del ciclo de vida
`active` (canónico vigente) · `merged` (fusionado en otro `master_id`; conserva `merged_into`) · `deprecated` (retirado). Transiciones no destructivas.

## 6. Versionado
- **`pipeline_version`** (`master-v1`): versión del pipeline que produjo el doc → permite rebuild selectivo (`version < N`).
- **`source_version`** (p.ej. `20260519`): versión/entrega de la fuente.
- **`source_hash`**: hash del perfil de entrada; si no cambia, el rebuild es no-op (idempotente) y habilita incrementales.
- **`dirty`**: marca de recálculo aguas abajo.

## 7. Contratos de entrada y salida
- **Entrada** (interno, NO expuesto): Normalized Layer (`norm_company`, `norm_financials`, `norm_ownership`, `norm_officers`).
- **Salida** (consumida por engines/arroba): los documentos de `master_companies` + aristas de `master_relationships` (ver §9). Solo lectura para consumidores.

## 8. Compatibilidad hacia atrás
- Los campos publicados en este contrato **no se eliminan ni se renombran** dentro de una misma `pipeline_version` mayor.
- Se permiten **adiciones** de campos (aditivo, no rompe consumidores).
- Cambios incompatibles ⇒ nueva versión mayor (`master-v2`) con periodo de convivencia.

## 9. Knowledge Graph estructural (`master_relationships`, fase 1)
```jsonc
{ "src_master_id": "mc_…", "dst_master_id": "mc_…|null", "relationship_type": "shareholder_of|parent_of|ultimate_parent_of|investee_of",
  "year": "int|null", "pct": "float|null", "counterparty_name": "…", "counterparty_external": "bool",
  "source": "iberinform", "origin": "ownership", "confidence": 0.95 }
```
Solo relaciones **objetivas de ownership real**. `same_group` NO se materializa como aristas pairwise (evita O(n²)); se expresa con `ownership.group_id` (union-find). NO incluye similitud/embeddings (diferido).

## 10. Política de evolución del esquema
- `master_companies` es la **fuente de verdad oficial**. `companies_master` queda **legacy en retirada**.
- Migración controlada: (1) validación de paridad funcional → (2) migración engine por engine → (3) retirada progresiva de dependencias sobre `companies_master` → (4) eliminación definitiva cuando ningún consumidor dependa de ella.
- Objetivo final: **una única fuente de verdad** para Company Intelligence.

## 11. Reconstrucción (jobs)
- `rebuild_master` (scope `full | incremental | cif_list`, `force`) y `rebuild_ownership_graph` corren como **handlers** sobre la infra de jobs reanudables (`data_layer_jobs`), nunca dentro de un request HTTP. Idempotentes y reanudables.
