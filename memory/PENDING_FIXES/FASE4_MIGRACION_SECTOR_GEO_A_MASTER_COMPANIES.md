# Fase 4 (Intel) · Migración real: Sector/Geo Intelligence pasa a contar empresas desde `master_companies`

**Fecha:** 2026-09-01
**Decisión de Daniel:** migrar ya, sin esperar al resultado del script de comparación — "migrar sin condiciones". El script de comparación (`memory/PENDING_FIXES/FASE4_SECTOR_GEO_QA_COMPARISON.md`) se ejecuta igualmente, pero solo para dejar constancia del resultado — no bloquea ni condiciona este parche.

## Qué cambia exactamente

`services/sector_intelligence_v2.py` y `services/geo_intelligence.py` calculan `dynamism_score` combinando varias fuentes; una de ellas (`activity_score`, 25% del peso en Sector, 20% en Geo) incluye un sub-conteo de "cuántas empresas de Iberinform hay en este sector/provincia". Hoy ese conteo sale de `iberinform_companies` (modelo legado); este parche lo cambia para que salga de `master_companies` (modelo moderno, el mismo que alimenta la Ficha real).

**El cambio está más contenido de lo que parece:** las dos funciones que hay que tocar (`_gather_iberinform()`, una en cada archivo) tienen exactamente un punto de llamada cada una, y su resultado solo se usa para `_aggregate_activity(...)` — nada más del cálculo depende de ellas. El resto de fuentes del `dynamism_score` (demografía INE, contratación pública, BORME) no cambian, porque no dependen de ninguna de las dos colecciones de empresas.

**Limpieza incluida (decisión de Daniel, 2026-09-01: "la limpiaría ya, si no seguimos aumentando la basura"):** en `sector_intelligence_v2.py::_gather_demography()` (líneas 190-198) había una segunda consulta a `iberinform_companies` con un comentario que decía "Override with actual counts... if higher" — pero el cuerpo del bucle era literalmente un `pass`, no hacía nada. Una consulta a base de datos en cada cálculo sin ningún efecto — código muerto, no un bug funcional (el `by_division` de demografía siempre salió 100% de la distribución DIRCE, nunca de Iberinform). Se retira en el Paso 3 de abajo: cero cambio de comportamiento (ya no hacía nada), solo se ahorra la consulta.

## Por qué el riesgo es bajo

- `avg_revenue` (el otro campo que devuelve `_gather_iberinform()` además del conteo) se confirma sin ningún uso en ninguno de los dos archivos — se calculaba y se guardaba, pero nada lo leía. Puede quedar a `0` sin ningún efecto en `dynamism_score`.
- La función nueva reutiliza la misma lógica de agregación ya escrita y usada en el script de comparación (`_gather_iberinform_sector_from_master()` / `_gather_iberinform_geo_from_master()` de `compare_sector_geo_master_vs_iberinform.py`) — no es código nuevo sin probar, es el mismo que ya se preparó para comparar.
- El shape de salida de ambas funciones se mantiene idéntico al de hoy (`{"by_division"/"by_province": {...}, "total": N}`) — el resto del código de cada archivo (`_aggregate_activity`, `_build_sector_doc`, `_build_geo_doc`, etc.) no necesita ningún cambio.
- **Diferencia real que sí puede importar:** `iberinform_companies` ya trae `province_code` resuelto; `master_companies.location.provincia` es un nombre libre (p.ej. "Madrid", "Illes Balears") que hay que resolver a código INE con el mismo mapa que ya usa BORME (`resolve_borme_province`, `services/geo_catalog.py`). Los nombres que no resuelvan no se descartan en silencio (R15) — quedan registrados en el log con `logger.warning(...)`, incluyendo cuántas empresas afectan.

## Paso 1 — `backend/services/sector_intelligence_v2.py`

**Buscar:**
```python
async def _gather_iberinform() -> Dict:
    """Gather Iberinform company data by CNAE."""
    data = {"by_division": {}, "total": 0}

    pipeline = [
        {"$match": {"cnae_code": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": {"$substr": ["$cnae_code", 0, 2]},
            "count": {"$sum": 1},
            "avg_revenue": {"$avg": {"$ifNull": ["$revenue", 0]}},
        }},
    ]
    by_cnae = await db.iberinform_companies.aggregate(pipeline).to_list(100)
    for item in by_cnae:
        data["by_division"][item["_id"]] = {
            "count": item["count"],
            "avg_revenue": item.get("avg_revenue", 0),
        }
    data["total"] = sum(d["count"] for d in data["by_division"].values())

    return data
```

**Sustituir por:**
```python
async def _gather_iberinform() -> Dict:
    """Fase 4 (2026-09-01) · Conteo de empresas por CNAE desde `master_companies`
    (modelo moderno) en vez de `iberinform_companies` (modelo legado) — decisión
    de Daniel, ver memory/PENDIENTE_ENVIAR_A_NEO_INTEL.md punto 4. Mismo shape de
    salida que antes, nada más de este archivo cambia. `avg_revenue` se deja a 0:
    no se lee en ningún otro punto de este módulo (nunca alimentó el cálculo de
    `dynamism_score`, solo se guardaba sin consumir)."""
    data = {"by_division": {}, "total": 0}

    pipeline = [
        {"$match": {"classification.cnae_code": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": {"$substr": ["$classification.cnae_code", 0, 2]},
            "count": {"$sum": 1},
        }},
    ]
    by_cnae = await db.master_companies.aggregate(pipeline).to_list(200)
    for item in by_cnae:
        data["by_division"][str(item["_id"])] = {
            "count": item["count"],
            "avg_revenue": 0,
        }
    data["total"] = sum(d["count"] for d in data["by_division"].values())

    return data
```

## Paso 2 — `backend/services/geo_intelligence.py`

**Buscar:**
```python
async def _gather_iberinform() -> Dict:
    """Iberinform company data by province."""
    data = {"by_province": {}, "total": 0}

    pipeline = [
        {"$match": {"province_code": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": "$province_code",
            "count": {"$sum": 1},
            "avg_revenue": {"$avg": {"$ifNull": ["$revenue", 0]}},
        }},
    ]
    by_prov = await db.iberinform_companies.aggregate(pipeline).to_list(60)
    for item in by_prov:
        data["by_province"][str(item["_id"])] = {
            "count": item["count"],
            "avg_revenue": item.get("avg_revenue", 0),
        }
    data["total"] = sum(d["count"] for d in data["by_province"].values())
    return data
```

**Sustituir por:**
```python
async def _gather_iberinform() -> Dict:
    """Fase 4 (2026-09-01) · Conteo de empresas por provincia desde
    `master_companies` (modelo moderno) en vez de `iberinform_companies`
    (modelo legado) — decisión de Daniel, ver
    memory/PENDIENTE_ENVIAR_A_NEO_INTEL.md punto 4. Mismo shape de salida que
    antes (`by_province` con claves = código INE), nada más de este archivo
    cambia. `avg_revenue` se deja a 0: no se lee en ningún otro punto de este
    módulo. A diferencia de `iberinform_companies` (que ya traía `province_code`
    resuelto), `master_companies.location.provincia` es un nombre libre — se
    resuelve con el mismo mapa que usa BORME (`resolve_borme_province`, ya
    importado en este archivo). R15: los nombres que no resuelvan no se
    descartan en silencio, quedan en el log de la aplicación."""
    data = {"by_province": {}, "total": 0}

    pipeline = [
        {"$match": {"location.provincia": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {"_id": "$location.provincia", "count": {"$sum": 1}}},
    ]
    by_name = await db.master_companies.aggregate(pipeline).to_list(3000)
    unmapped: Dict[str, int] = {}
    for item in by_name:
        name = (item["_id"] or "").strip()
        code = resolve_borme_province(name)
        if code:
            cur = data["by_province"].get(code, {"count": 0, "avg_revenue": 0})
            cur["count"] += item["count"]
            data["by_province"][code] = cur
        else:
            unmapped[name] = unmapped.get(name, 0) + item["count"]
    data["total"] = sum(d["count"] for d in data["by_province"].values())
    if unmapped:
        logger.warning(
            "geo_intelligence._gather_iberinform: %d nombres de provincia de "
            "master_companies no resuelven a código INE (%d empresas en total) — "
            "no se cuentan en dynamism_score. Detalle: %s",
            len(unmapped), sum(unmapped.values()), unmapped,
        )
    return data
```

## Paso 3 — Limpieza: retirar la consulta muerta de `sector_intelligence_v2.py::_gather_demography()`

Aditivo a la migración pero independiente de ella — no depende de los pasos 1 y 2 ni al revés, se puede aplicar en cualquier orden. Cero cambio de comportamiento: el bucle que se retira no hacía nada (ver "Limpieza incluida" arriba).

**Buscar:**
```python
    # Use DIRCE distribution to estimate per-division company counts
    total = data["active_total"] or 3_300_000
    for div_code, share in CNAE_DIVISION_DISTRIBUTION.items():
        data["by_division"][div_code] = round(total * share)

    # Override with actual counts from iberinform_companies if higher
    ib_pipeline = [
        {"$group": {"_id": "$cnae_division", "count": {"$sum": 1}}},
    ]
    ib_by_cnae = await db.iberinform_companies.aggregate(ib_pipeline).to_list(200)
    for item in ib_by_cnae:
        code = str(item["_id"])
        if code in data["by_division"]:
            # Keep the DIRCE estimate (it's the national reality)
            # but record actual Iberinform count for enrichment signal
            pass

    return data
```

**Sustituir por:**
```python
    # Use DIRCE distribution to estimate per-division company counts
    total = data["active_total"] or 3_300_000
    for div_code, share in CNAE_DIVISION_DISTRIBUTION.items():
        data["by_division"][div_code] = round(total * share)

    return data
```

(Este "Buscar" es dentro de `_gather_demography()`, función distinta de `_gather_iberinform()` del Paso 1 — mismo archivo, sin solapamiento con el otro bloque.)

## Instrucciones para Neo (orden)

1. Ejecutar primero el script de comparación (ya preparado, ver `FASE4_SECTOR_GEO_QA_COMPARISON.md`) — **no para decidir si migrar (Daniel ya decidió que sí), sino para dejar constancia documentada del efecto**: pegar el resumen de pantalla y adjuntar el JSON de `/tmp/fase4_sector_geo_comparison.json` en la respuesta a Daniel. Si el conteo total de `master_companies` sale muy por debajo del de `iberinform_companies` (cobertura de ingesta todavía parcial), avisarlo explícitamente aunque la migración se aplique igual — es información que Daniel debe tener, no un motivo para parar.
2. Aplicar los 2 pasos de arriba (`sector_intelligence_v2.py` y `geo_intelligence.py`).
3. `pytest` de `backend` limpio (en particular cualquier test de `services/sector_intelligence_v2.py` o `services/geo_intelligence.py`).
4. Recalcular/refrescar Sector e Geo Intelligence en preview (el mecanismo habitual de refresco de estas dos colecciones) y verificar que los endpoints responden sin error para un par de sectores y provincias conocidos.
5. Si el log muestra nombres de provincia sin resolver con un volumen relevante de empresas, incluirlo en el reporte a Daniel junto con el resultado del script de comparación — mismo aviso que el punto 1, no bloquea el despliegue.

## Qué NO cambia con este parche

- `master_builder.py`, `docstudio/`, y los conectores CNMV/BME/Valuo — siguen sin tocarse, ninguno depende de estas dos funciones.
- El resto de fuentes de `dynamism_score` (demografía INE, contratación pública, BORME) — sin cambios.
- El resto de `_gather_demography()` — sigue sacando el `by_division` 100% de la distribución DIRCE, exactamente igual que hoy; el Paso 3 solo retira una consulta que no tenía ningún efecto (ver "Limpieza incluida" arriba).
