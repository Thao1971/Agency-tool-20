# Parche Fase 2 (redefinida): bloque nuevo "Mercados de capitales" (CNMV/BME) en la Ficha

**Qué es esto realmente:** no es una migración de `companies_master` a `master_companies` (esa migración no tenía ningún efecto visible — ver nota más abajo). Es un **bloque nuevo** en la Ficha: si la empresa cotiza en Bolsa (BME), si está registrada como entidad regulada por la CNMV (gestora/fondo — poco común en un target M&A típico, pero real cuando aplica), y cuántos inversores institucionales CNMV (fondos de capital riesgo, gestoras) están activos en su sector como compradores potenciales. Dato que hoy no llega a ningún sitio de la Ficha.

**Por qué no era una simple migración:** investigado a fondo, ninguno de los dos mecanismos legacy alimenta la Ficha real:
- El matching batch (`match_cnmv_to_companies`, `bme_connector._match_companies`) que escribe en `companies_master` no lo lee ninguna pantalla de empresa — solo un panel admin interno.
- El segundo motor (`services/intelligence_engine/`) sí hace un lookup en vivo correcto, pero solo lo usa el pipeline de Valuo.pro, no arroba.

Así que en vez de "arreglar" cualquiera de los dos, se reutiliza la MISMA lógica de búsqueda en vivo que ya funciona en producción para Valuo (`services/intelligence_engine/sources/cnmv.py` y `sources/bme.py`), pero apuntada al modelo moderno (`master_companies`) en vez del legacy, como un bloque nuevo de `routes/company_ficha.py` (el mismo patrón que ya usan `ownership`, `governance`, `events`, `market`, etc.).

**Archivo a modificar:** `backend/routes/company_ficha.py` (no se toca ningún otro archivo — no hace falta tocar `services/cnmv_connector.py`, `services/bme_connector.py` ni `services/intelligence_engine/`, se dejan tal cual, sirviendo a Valuo).

## 1. Insertar 2 helpers + la función del bloque nuevo

**Insertar justo después de la función `market()`** (justo antes del comentario `# ── Propiedad / grafo de control (mockup): ...` que ya existe en el archivo):

```python
def _norm_bme_name(s: str) -> str:
    """Misma normalización que ya usa el matching en vivo de BME para Valuo
    (services/intelligence_engine/sources/bme.py) — reutilizada tal cual."""
    s = (s or "").upper()
    s = re.sub(r"[,\.]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


async def _bme_listing_for(legal_name: Optional[str]) -> Optional[Dict]:
    """Busca en vivo si la empresa cotiza en BME, por nombre (mismo criterio que el
    matching de Valuo: prefijo del nombre sin sufijo societario, primeros 12 caracteres)."""
    if not legal_name:
        return None
    name_norm = _norm_bme_name(legal_name)
    base = re.sub(r"\b(S\s*A|S\s*L|SA|SL|SAU|SLU)\b\s*$", "", name_norm).strip()
    if len(base) < 3:
        return None
    pattern = f"^{re.escape(base[:12])}"
    return await db.bme_companies.find_one(
        {"company_name": {"$regex": pattern, "$options": "i"}},
        {"_id": 0, "company_name": 1, "isin": 1, "ticker": 1, "market_segment": 1,
         "market_cap": 1, "sector": 1, "share_price": 1, "annual_performance": 1})


async def _cnmv_entity_for(nif: Optional[str]) -> Optional[Dict]:
    """Busca en vivo si la propia empresa está registrada como entidad regulada por
    la CNMV (gestora/fondo), por NIF exacto (mismo criterio que el matching de Valuo)."""
    if not nif:
        return None
    return await db.cnmv_entities.find_one(
        {"nif": nif},
        {"_id": 0, "entity_type": 1, "entity_type_label": 1, "name": 1, "registration_number": 1})


@router.get("/{identifier}/capital-markets")
async def capital_markets(identifier: str, _key=Depends(require_service_key)):
    """Mercados de capitales (CNMV/BME): si la empresa cotiza en Bolsa (BME), si está
    registrada como entidad regulada por la CNMV, y compradores institucionales CNMV
    activos en su CNAE (fondos/gestoras). Bloque nuevo (2026-09-01) — no existía
    ninguna fuente de este dato en la Ficha hasta ahora. Null-safe por sub-bloque
    (available), igual que el resto de bloques de esta Ficha."""
    master = await _master(identifier)
    if not master:
        raise HTTPException(status_code=404, detail="Company not found")
    ident = master.get("identity") or {}
    cls = master.get("classification") or {}
    cif_raw = ident.get("cif") or master["cif_normalized"]
    legal_name = ident.get("legal_name")
    cnae_code = cls.get("cnae_code")

    listing = await _bme_listing_for(legal_name)
    listing_block = ({"available": True,
                       "company_name": listing.get("company_name"),
                       "isin": listing.get("isin"),
                       "ticker": listing.get("ticker"),
                       "market_segment": listing.get("market_segment"),
                       "market_cap": listing.get("market_cap"),
                       "share_price": listing.get("share_price"),
                       "annual_performance": listing.get("annual_performance"),
                       "sector": listing.get("sector")}
                      if listing else {"available": False, "reason": "not_listed"})

    entity = await _cnmv_entity_for(cif_raw)
    regulated_block = ({"available": True,
                         "entity_type": entity.get("entity_type"),
                         "entity_type_label": entity.get("entity_type_label"),
                         "name": entity.get("name"),
                         "registration_number": entity.get("registration_number")}
                        if entity else {"available": False, "reason": "not_cnmv_registered"})

    buyers_block = {"available": False, "reason": "no_cnae"}
    if cnae_code:
        try:
            from services.cnmv_investor_intelligence import get_buyers_for_cnae
            buyers = await get_buyers_for_cnae(cnae_code)
            total = (buyers.get("total_buyers", 0) or 0) + (buyers.get("total_managers", 0) or 0)
            buyers_block = {"available": total > 0, "total": total,
                             "buyers": buyers.get("total_buyers", 0),
                             "managers": buyers.get("total_managers", 0)}
            if total == 0:
                buyers_block["reason"] = "no_buyers_in_cnae"
        except Exception:
            buyers_block = {"available": False, "reason": "engine_error"}

    return {
        "identifier": identifier, "cif": master["cif_normalized"], "master_id": master["master_id"],
        "available": listing_block["available"] or regulated_block["available"] or buyers_block["available"],
        "listing": listing_block,
        "cnmv_regulated": regulated_block,
        "potential_buyers": buyers_block,
        "is_public_company": listing_block["available"],
        "engine_version": ENGINE_VERSION,
    }

```

## 2. Enganchar el bloque nuevo en el agregador `ficha()`

**Buscar** (dentro de `async def ficha(...)`):
```python
    governance_block = await governance(identifier, _key=None)
    market_block = await market(identifier, _key=None)
    signals_block = await signals(identifier, _key=None)
    control_graph_block = await _control_graph_block(master)
```

**Sustituir por:**
```python
    governance_block = await governance(identifier, _key=None)
    market_block = await market(identifier, _key=None)
    capital_markets_block = await capital_markets(identifier, _key=None)
    signals_block = await signals(identifier, _key=None)
    control_graph_block = await _control_graph_block(master)
```

**Buscar** (el diccionario de retorno de `ficha()`):
```python
        "signals": signals_block,
        "market": market_block,
        "control_graph": control_graph_block,
```

**Sustituir por:**
```python
        "signals": signals_block,
        "market": market_block,
        "capital_markets": capital_markets_block,
        "control_graph": control_graph_block,
```

## 3. Bonus de un momento: enciende un chip que YA existe en la cabecera de Beta, gratis

Beta tiene desde hace tiempo un chip de cabecera "Cotizada · {mercado}" (`CompanyPublicStatus.tsx`, COMP-1003) que lee `identity.registry_status.is_listed` / `.listed_market` — pero como `master_companies` nunca traía ese dato, el chip nunca se veía. Con el bloque nuevo ya calculado, es una línea más aprovecharlo:

**Buscar** (dentro de `ficha()`, justo debajo de donde ya se rellena `identity["auditor"]`):
```python
    identity["verified"] = bool((finances or {}).get("has_financials"))
    identity["auditor"] = _first_auditor(governance_block)
```

**Sustituir por:**
```python
    identity["verified"] = bool((finances or {}).get("has_financials"))
    identity["auditor"] = _first_auditor(governance_block)
    # Fase 2 (2026-09-01) · alimenta el chip "Cotizada" de cabecera (COMP-1003),
    # que ya existía en Beta pero nunca recibía dato.
    identity["is_listed"] = capital_markets_block["listing"]["available"]
    identity["is_listed_label_es"] = "Cotizada" if identity["is_listed"] else "No cotizada"
    identity["listed_market"] = capital_markets_block["listing"].get("market_segment")
```

(Este bloque ya se ejecuta después de `capital_markets_block = await capital_markets(...)` del punto 2, así que la variable está disponible.)

## Notas para Neo

- No toca `services/cnmv_connector.py`, `services/bme_connector.py` ni nada de `services/intelligence_engine/` — esos siguen sirviendo a Valuo.pro exactamente igual que hoy. Cero riesgo de compatibilidad con Valuo (el propio Daniel ha pedido expresamente que Valuo y arroba no compartan nada).
- No toca `companies_master` en ningún momento — todo el bloque nuevo lee `master_companies` (vía `_master()`, ya existente en este archivo) y consulta `cnmv_entities`/`bme_companies` directamente, en vivo, sin pasar por ninguna colección intermedia.
- El bloque nuevo `capital-markets` sigue exactamente el mismo patrón `available`/`reason` que ya usan `ownership`, `governance`, `market`, etc. en este mismo archivo — nada inventado, "no disponible" cuando no hay dato.
- Verificar en preview: llamar a `/{identifier}/ficha` para una empresa que SÍ cotice en BME (para ver `listing.available: true`) y para una que no (para ver el degradado limpio). El listado de empresas en `bme_companies` está en la propia base — Neo puede consultarlo para elegir un ejemplo real antes de enseñárselo a Daniel.
- Este bloque es solo backend (Intel). Para que se vea en la Ficha visual de Beta hace falta un pequeño añadido de frontend aparte (ver mockup enviado a Daniel) — se prepara como parche de Beta cuando él lo confirme.
