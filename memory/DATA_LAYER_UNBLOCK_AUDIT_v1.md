# INFORME TÉCNICO — Auditoría Data Layer / Ingestión (desbloqueo Master Layer para Arroba)
_Versión: `datalayer-unblock-audit-v1` · 2026-07-12 · Solo diagnóstico (sin código). Pendiente de aprobación del plan._

## 0. Aclaración de entorno (crítica)
- **Preview (donde trabajo):** el Master Layer **SÍ** devuelve entidades. Verificado: 6.261 `master_companies`,
  `POST /api/v2/company-intelligence/identity` y `POST /api/v1/financial-intelligence/analyze` responden 200 con datos.
- **Producción (`https://intel-agency.emergent.host`):** despliegue independiente con **su propia MongoDB**.
  No tengo acceso. El síntoma "company not found para TODAS" es **coherente con una BD de producción vacía**.
- **Acción de confirmación (usuario):** `curl -s -X POST https://intel-agency.emergent.host/api/v2/company-intelligence/identity -H "X-API-Key: <prod_key>" -H "Content-Type: application/json" -d '{"identifier":"B59022921"}'` → si devuelve 404, se confirma BD de producción sin dataset.

## 1. Respuestas a las 8 preguntas
1. **¿Por qué "company not found" para todas?** Porque el entorno donde se observa (producción) tiene la
   **base de datos vacía**: nunca se ejecutó ingesta/construcción allí y el arranque **no siembra**
   `master_companies` (solo taxonomía, CNAE, arquetipos, proveedor Iberinform e inteligencia territorial/sectorial).
   El dataset de 6.261 empresas **vive únicamente en la BD de preview** y no viaja con el despliegue.
2. **¿Existe dataset cargado?** En **preview: SÍ** (raw Iberinform 5.000 empresas + 11.657 financieros;
   6.261 `norm_company`; 6.261 `master_companies`; `entity_xref` 13.048; `er_bridge_results` 16.065;
   `signals` 470; `semantic_profiles` 63; `strategic_theses` 109). En **producción: presumiblemente NO**.
3. **¿Ingestión funcionando?** **SÍ** (funcional). Vía carga de proveedor → `iberinform_ingest` (bulk upsert
   idempotente). Evidencia: colecciones raw pobladas, `raw_ingestion_manifest` con 696 entradas + lineage,
   ficheros fuente almacenados en `provider_file_contents` (4). No corre en arranque; es proceso disparado.
4. **¿Normalización funcionando?** **PARCIAL.** Corre y produce `norm_company` (6.261), pero con **gaps de
   mapeo**: campos presentes en el raw NO se propagan al Master (ver §2, causa raíz secundaria).
   `norm_financials` solo 1.027 filas.
5. **¿Entity Resolution funcionando?** **SÍ.** `identity_resolver` genera `master_id` canónico; `entity_xref`
   13.048, `er_bridge_results` 16.065, `er_audit_logs` 600. No es el bloqueante.
6. **¿Se generan Master Records?** **SÍ.** 6.261 `master_companies`; último job `rebuild_master` (scope full)
   **completado** sin error. Cobertura: **6.261/6.261 con `legal_name`** (identidad OK) pero **solo 355 con
   `revenue`** en `financials.latest` (financieros muy limitados).
7. **¿Qué componente exacto impide que una empresa llegue a los endpoints?**
   - **En producción (bloqueante primario):** la **BD vacía** → no hay `master_companies` que consultar → 404 en
     `identity` y en `analyze` para todas. No es un bug de código; es ausencia de datos/build en ese entorno.
   - **Para que `financial-intelligence/analyze` devuelva NÚMEROS (bloqueante secundario, incluso con datos):**
     el paso **Normalización → construcción de `financials.latest` del Master**. El raw Iberinform tiene
     `revenue_latest` (ej. CIF `J2476475C`: revenue 1.304.780,09, legal_form 'SL', status 'active') pero el
     master mapeado tiene `financials.latest = null`, `identity.legal_form` ausente y `capital_social = null`.
     `identity` funciona para todas; `analyze` devuelve 200 con `has_financials=false` para ~94%.
8. **¿Qué trabajo queda para un dataset canónico mínimo?** Ver §4 (Plan). Resumen: (A) poblar la BD de
   producción; (B) cerrar los gaps de mapeo para un conjunto curado de ~20–50 empresas reales de modo que la
   cadena completa (identidad + financieros + ratios + histórico + señales + semántica + estrategia) sea sólida.

## 2. Causa raíz
- **PRIMARIA (producción devuelve 404 a todo):** entorno de producción con **MongoDB propia y vacía**. El
  dataset se construyó de forma interactiva en preview (uploads + jobs `rebuild_master`) y **no se migró ni se
  siembra** en el despliegue. El arranque no crea `master_companies`.
- **SECUNDARIA (completitud del dato, también en preview):** la normalización/`master_builder` propaga
  identidad básica (nombre, alias, país, CNAE) pero **no** mapea de forma completa: `legal_form`,
  estado mercantil, `capital_social`, y sobre todo **los financieros** (`revenue_latest`/serie histórica) al
  `financials.latest/history` del Master. Resultado: solo 355 empresas "financiables".

## 3. Diagnóstico (estado real por etapa)
| Etapa | Estado | Evidencia | Nota |
|---|---|---|---|
| Ingestión (raw) | 🟢 Funcional | iberinform_companies 5.000 · iberinform_financials 11.657 · manifest 696 | Idempotente; ficheros fuente guardados en BD |
| Normalización | 🟡 Parcial | norm_company 6.261 · norm_financials 1.027 | No propaga financieros/atributos al Master |
| Entity Resolution | 🟢 Funcional | entity_xref 13.048 · er_bridge 16.065 | master_id canónico estable |
| Master build | 🟢 Funcional (cobertura baja) | master_companies 6.261 · con revenue 355 | job rebuild_master completado |
| Intelligence (signals/semantic/strategy) | 🟡 Parcial | signals 470 · semantic 63 · theses 109 | No reconstruido para todo el universo |
| **Producción (datos)** | 🔴 Vacío (hipótesis) | 404 para todas | BD independiente sin ingesta/build |

## 4. Plan de actuación (propuesto — NO ejecutar hasta aprobación)
### Track A — Desbloquear producción (rápido)
- **A1 · Migración de datos (mongodump/mongorestore):** exportar de preview e importar en producción las
  colecciones canónicas (`master_companies`, `norm_*`, `entity_xref`, `master_relationships`, `iberinform_*`,
  `signals`, `semantic_profiles`, `strategic_theses`, `cnae_catalog`). Deja las 6.261 vivas de inmediato.
  *Requiere:* cadena de conexión de la MongoDB de producción (usuario/Emergent Support).
- **A2 · Bootstrap reproducible (preferido):** versionar el/los fichero(s) fuente Iberinform (ya guardados en
  `provider_file_contents`) como artefacto de seed + un endpoint/script *one-shot* protegido que en producción
  ejecute: upload → ingest → normalize → `rebuild-master` → `rebuild-embeddings`/`rebuild-signals`.
  Repetible en cualquier entorno, sin acceso manual a la BD.

### Track B — Dataset canónico de validación (calidad de la cadena completa)
- Seleccionar un **conjunto curado de ~20–50 empresas reales** (con financieros presentes en el raw).
- **Cerrar los gaps de mapeo** en normalización/`master_builder`: propagar `legal_form`, estado mercantil,
  `capital_social`, `employees`, y **financieros con histórico** (`financials.latest` + `history[]`) al Master.
- Reconstruir para ese subconjunto: **ratios** (Financial), **señales** (Signal), **perfil semántico**
  (Semantic) y **tesis** (Strategy) para validar identidad → financieros → ratios → histórico → inteligencia.
- Verificación end-to-end con `testing_agent` sobre `identity` + `analyze` + `signals` + `semantic` + `strategy`.

### Orden recomendado
1) Confirmar entorno (404 en producción). 2) Track A2 (bootstrap) para poblar producción con las 6.261 de
identidad. 3) Track B (curar + cerrar mapeo financiero) para el set de validación. 4) Verificación + smoke Arroba.

## 5. Estimación
| Bloque | Estimación |
|---|---|
| A1 migración directa (si hay acceso a Mongo prod) | 0,25–0,5 día |
| A2 bootstrap reproducible (endpoint/script + seed del fichero) | 0,5–1 día |
| B mapeo financiero + atributos + rebuild set curado | 1,5–2,5 días |
| Verificación (testing_agent + smoke Arroba) | 0,5 día |
| **Total (A2 + B + verificación)** | **~2,5–4 días** |

## 6. Necesito de ti para avanzar
- Confirmar que el 404 se ve en **producción** (`https://intel-agency.emergent.host`).
- Elegir Track A1 (migración; necesito acceso a Mongo prod) **o** A2 (bootstrap reproducible; recomendado).
- Aprobar Track B y el tamaño del set canónico (¿20, 30, 50 empresas?).
- Si hay serie financiera **plurianual** requerida (histórico), confirmar que el raw Iberinform la contiene o
  la fuente de la que traerla.
