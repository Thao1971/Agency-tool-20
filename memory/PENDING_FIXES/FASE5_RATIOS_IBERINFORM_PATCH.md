# Parche "ratios Iberinform" (Intel): exponer los 28 ratios acordados el 24/07

**Qué es esto:** el hallazgo de la auditoría de hoy (`memory/AUDITORIA_DATOS_IBERINFORM_NO_EXPUESTOS.md`, punto 2) es que la ingesta YA guarda los 31 ratios precalculados de Iberinform, íntegros, desde el 24 de julio (`services/data_layer/ingestion/iberinform_tab_ingest.py::ingest_ratios_file`, campo `norm_financials.<doc>.ratios`) — pero nada los lee de vuelta. Este parche expone los 28 acordados (Tier 1+2+3 de `memory/IBERINFORM_RATIOS_PRIORITY.md`; fuera quedan los 3 de Tier 4 — riesgo de crédito comercial) en el bloque `finances` de la Ficha, como campo nuevo `iberinform_ratios`, sin tocar ni pisar el campo `ratios` que ya usa arroba para sus propios ratios calculados.

**Importante — esto NO requiere backfill para EMPEZAR a funcionar en empresas nuevas o re-ingeridas**, pero si el dataset actual de 25.000 empresas fue cargado antes del 24/07 con la ingesta anterior (Valu8 CSV), es posible que `norm_financials.ratios` esté vacío para la mayoría — verificar con una consulta rápida (`db.norm_financials.count_documents({"ratios_source": "iberinform"})`) antes de dar esto por incompleto; si sale bajo, hace falta re-ingerir el dataset 25k con el pipeline `.tab` actual (mismo paso pendiente que ya está anotado para los 27 ratios en `IBERINFORM_RATIOS_PRIORITY.md`).

**Archivos:**

## 1. Archivo nuevo: `backend/services/engines/financial/iberinform_ratios.py`

Copiar tal cual desde `memory/PENDING_FIXES/iberinform_ratios.py` — módulo de solo funciones puras (mapa de 28 códigos → nombre/etiqueta ES/tier + función `curate()`), no toca nada existente.

## 2. `backend/services/engines/financial/engine.py`

**Buscar** (imports, arriba del archivo):
```python
from services.engines.financial import metrics as M
from services.engines.financial import ratios_library as R
from services.engines.financial import market_multiples as MM
```

**Sustituir por:**
```python
from services.engines.financial import metrics as M
from services.engines.financial import ratios_library as R
from services.engines.financial import market_multiples as MM
from services.engines.financial import iberinform_ratios as IR
```

**Buscar** (dentro de `async def analyze(...)`, justo antes de `return {`, al final de la función):
```python
    return {
        "master_id": master["master_id"], "cif_normalized": cif,
        "identity": {"name": (master.get("identity") or {}).get("legal_name"),
                     "cnae_code": (master.get("classification") or {}).get("cnae_code"),
                     "cnae_section": (master.get("classification") or {}).get("cnae_section"),
                     "provincia": (master.get("location") or {}).get("provincia"),
                     **_identity_descriptors(master)},
        "has_financials": True,
        "ranking": ranking_block,
        "statements": statements,
        "kpis": kpis,
        "kpis_prior": kpis_prior,
        "ratios": ratios,
        "provenance": provenance,
```

**Sustituir por:**
```python
    # Fase 5 (2026-09-01) · ratios oficiales de Iberinform (28 acordados el 24/07,
    # ver memory/IBERINFORM_RATIOS_PRIORITY.md) para el mismo año/basis que `latest`.
    # Campo separado de `ratios` (los propios de arroba) — nunca se pisan entre sí.
    _latest_norm_doc = next(
        (f for f in norm if f.get("year") == latest.get("year") and f.get("basis") == latest.get("basis")),
        None,
    )
    _raw_iberinform_ratios = (
        (_latest_norm_doc or {}).get("ratios")
        if (_latest_norm_doc or {}).get("ratios_source") == "iberinform" else None
    )
    iberinform_ratios = IR.curate(_raw_iberinform_ratios)

    return {
        "master_id": master["master_id"], "cif_normalized": cif,
        "identity": {"name": (master.get("identity") or {}).get("legal_name"),
                     "cnae_code": (master.get("classification") or {}).get("cnae_code"),
                     "cnae_section": (master.get("classification") or {}).get("cnae_section"),
                     "provincia": (master.get("location") or {}).get("provincia"),
                     **_identity_descriptors(master)},
        "has_financials": True,
        "ranking": ranking_block,
        "statements": statements,
        "kpis": kpis,
        "kpis_prior": kpis_prior,
        "ratios": ratios,
        "iberinform_ratios": iberinform_ratios,
        "provenance": provenance,
```

**No tocar nada más de la función** — el resto del `return` (evolution, financial_quality, comparables, valuation, assessment, explainability, engine_version, etc.) sigue igual.

**Nota sobre el "sin datos" (early return):** la función `analyze()` tiene un `return` temprano cuando `not series` (empresa sin estados financieros normalizados, más arriba en la función) — ese camino no incluye `iberinform_ratios` en absoluto (ni `None` explícito). Es intencional y coherente con el resto de ese bloque de respuesta (tampoco incluye `kpis`, `statements`, etc. en ese caso) — Beta ya trata la ausencia de esas claves como "sin datos financieros" vía `has_financials: False`, así que no hace falta ningún cambio ahí.

## Notas para Neo

- No toca `master_builder.py`, `docstudio/`, ni ningún otro consumidor de `norm_financials` — solo el motor financiero que alimenta `/ficha` (`FE.analyze()`, usado en `routes/company_ficha.py`).
- No toca los ratios propios de arroba (`ratios`, `ratios_library.py`) — campo nuevo y separado, `iberinform_ratios`.
- Verificar en preview: llamar a `/{identifier}/ficha` de una empresa con `Datos_RATIOS.tab` ingerido (comprobar antes con la consulta de conteo de arriba) y confirmar que `finances.iberinform_ratios` trae algunos de los 28 códigos con `value`/`label_es`/`tier`/`verified`; y de una empresa sin ratios ingeridos, confirmar que el campo es `null` (degradado limpio, no error).
- Si el conteo de `ratios_source: "iberinform"` sale bajo o cero para el dataset actual, avisar a Daniel — significa que hace falta re-ingerir el dataset 25k con el pipeline `.tab` actual antes de que esto se vea con datos reales en producción (ver nota de backfill al principio de este documento).
