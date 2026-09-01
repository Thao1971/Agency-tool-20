# Parche Fase 0: campos dormidos a la Ficha (dirección, situación mercantil, auditado, modelo de balance, último ejercicio depositado)

**Qué hace:** proyecta a `master_companies` 5 campos que Iberinform ya entrega y que se guardan en `norm_company` desde la ingesta (`domicilio`, `sit_mercantil`, `audited`, `balance_model`, `last_balance_year`), pero que nunca se copiaban a la capa que lee la Ficha. Es aditivo: no cambia ningún dato ni cálculo que ya se ve hoy, solo añade 5 campos nuevos que hoy llegan vacíos.

**Por qué basta con 2 archivos:** `/api/v2/company-intelligence/identity` (`_build()` en `company_intelligence.py`) es la misma función que usa `routes/company_ficha.py::ficha()` para montar el bloque `identity` de la Ficha (`from routes.company_intelligence import _build as _build_identity`, línea 21 de `company_ficha.py`). Arreglando `_build()` una vez, se arregla también la Ficha real — no hace falta tocar `company_ficha.py`.

## Archivo 1 — reemplazar entero

`backend/services/data_layer/master/master_builder.py` → sustituir por el contenido de `memory/PENDING_FIXES/master_builder.fixed.py` (mismo directorio que este documento).

Resumen del cambio (dentro de `_process_batch`):
- `fields = {...}` gana 5 claves nuevas: `domicilio`, `sit_mercantil`, `audited`, `balance_model`, `last_balance_year` — leídas de `nc` (el doc de `norm_company`), mismo patrón que los campos ya existentes.
- El dict `location` del `doc` final gana `"domicilio": canonical(prov["domicilio"])`.
- El `doc` final gana una clave nueva, hermana de `location`/`identity`/`contact`: `"registry": {"mercantile_status": ..., "audited": ..., "balance_model": ..., "last_balance_year": ...}`.
- No se toca ninguna otra función del archivo (`purge_fixture_sample`, `sweep_orphan_signals`, `rebuild_master`, etc. quedan idénticas).

## Archivo 2 — reemplazar entero

`backend/routes/company_intelligence.py` → sustituir por el contenido de `memory/PENDING_FIXES/company_intelligence.fixed.py`.

Resumen del cambio:
- `CompanyIdentityResponse` gana 3 campos nuevos: `audited`, `balance_model`, `last_balance_year` (los otros 2 — `address` y `mercantile_status` — YA estaban declarados en el contrato, solo no se rellenaban).
- `_build()` lee el nuevo `doc.get("registry")` y rellena `address`, `mercantile_status`, `audited`, `balance_model`, `last_balance_year` en la respuesta.
- La lista `present` (que alimenta `data_coverage`) gana `"address"`, `"audited"`, `"balance_model"`, `"last_balance_year"`.
- Nada más del archivo cambia (`/resolve`, `CompanyResolveResponse`, etc. quedan idénticos).

## Después de aplicar

Los 5 campos nuevos solo aparecen en empresas que se reconstruyan en `master_companies` después del cambio (`rebuild_master`, scope `incremental` o `full`) — igual que cualquier otro cambio de proyección de este builder. Si Neo lo aplica y no ve los campos en el preview para una empresa concreta, probablemente hace falta forzar un rebuild de esa ficha (o esperar al ciclo normal de `dirty`), no es señal de que el parche esté mal.

## Notas para Neo

- Puramente aditivo: no borra ni renombra ningún campo existente en `master_companies` ni en el contrato de `/identity`. No toca `companies_master` (la colección legacy que usa Valuo.pro) — solo `master_companies`.
- No requiere cambios en Beta/frontend para esta entrega — es exposición de datos en el backend de Intel. Si más adelante se quiere pintar estos 5 campos en la Ficha visual, eso es un cambio de Beta aparte (fuera de este parche).
- Verificar en preview: llamar a `/api/v2/company-intelligence/identity` (o `/ficha`) para una empresa con datos de Iberinform recientes y comprobar que `address`, `mercantile_status`, `audited`, `balance_model`, `last_balance_year` dejan de ser `null` cuando el dato exista en `norm_company`.
