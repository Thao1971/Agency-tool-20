# Parche Fase 1: terminar de migrar DocStudio (2 endpoints legacy)

**Contexto:** de todo lo que lee DocStudio, solo quedaban 2 endpoints tocando el modelo legacy (`iberinform_financials`) — el resto (`composer.py`, vía `docstudio/data_access.py`) ya está migrado al modelo moderno (`master_companies`/`norm_financials`) desde el plan `DOCUMENT_STUDIO_UNIFICATION_PLAN`.

**Hallazgo importante (2026-09-01), cambia el riesgo de esta fase a la baja:** ninguno de los dos endpoints tiene ningún caller — ni dentro de Intel (`composer.py` usa su propio adaptador moderno, no estos endpoints), ni en el frontend de Beta, ni en los tests. Son rutas expuestas pero no usadas hoy por nada del sistema. Aun así merece la pena migrarlas en vez de borrarlas — quedan disponibles y coherentes con el resto por si algo las empieza a usar.

**Archivo a modificar (solo estas 2 funciones, no el resto del archivo):** `backend/docstudio/routes.py` (1461 líneas — sustitución localizada, no archivo completo).

## 1. `GET /financial/company/{company_id}`

**Buscar** (bloque actual, sección "FINANCIAL ENGINE"):
```python
@router.get("/financial/company/{company_id}")
async def financial_analysis_company(company_id: str, user=Depends(get_current_user)):
    """Run full financial analysis for a company (deterministic, no AI)."""
    t0 = time.time()
    from docstudio.financial_engine import analyze_company_financials

    financials = await db.iberinform_financials.find(
        {"company_id": company_id}, {"_id": 0}
    ).sort("year", 1).to_list(10)

    if not financials:
        raise HTTPException(404, "No financial data for this company")

    analysis = analyze_company_financials(financials)
    return {**_meta(t0), "company_id": company_id, "analysis": analysis}
```

**Sustituir por:**
```python
@router.get("/financial/company/{company_id}")
async def financial_analysis_company(company_id: str, user=Depends(get_current_user)):
    """Run full financial analysis for a company (deterministic, no AI).

    Fase 1 (DOCUMENT_STUDIO_UNIFICATION_PLAN, 2026-09-01): deja de leer la
    colección legacy `iberinform_financials` y delega en el motor financiero
    canónico moderno (services/engines/financial/engine.analyze, vía
    docstudio/data_access.py), el mismo que ya usa compose_company_profile()
    y el resto del composer. `company_id` acepta master_id o cif_normalized.

    Nota de contrato: el shape de "analysis" cambia respecto a la versión
    legacy (antes: latest_year/revenue_yoy/ebitda_yoy/employee_yoy/
    revenue_cagr/ebitda_margin/net_margin/revenue_per_employee/
    ebitda_per_employee/revenue_series). Ahora es el perfil completo del
    motor moderno (KPIs, ratios, evolución, comparables, valoración) — más
    rico, no un subconjunto. Sin problema de compatibilidad: no hay ningún
    caller de este endpoint en Intel ni en Beta (verificado por grep), ni en
    los tests.
    """
    t0 = time.time()
    from docstudio import data_access as DA

    company = await DA.resolve_company(identifier=company_id)
    if not company:
        raise HTTPException(404, "No financial data for this company")

    analysis = await DA.financial_profile(company_id)
    if not analysis:
        raise HTTPException(404, "No financial data for this company")

    return {**_meta(t0), "company_id": company_id, "analysis": analysis}
```

## 2. `GET /financial/compare`

**Buscar:**
```python
@router.get("/financial/compare")
async def compare_company_to_sector(
    company_id: str = Query(...),
    cnae_code: str = Query(...),
    user=Depends(get_current_user),
):
    """Compare a company against its sector peers (deterministic, no AI)."""
    t0 = time.time()
    from docstudio.financial_engine import (
        analyze_company_financials, analyze_sector_benchmark,
        sector_comparison, revenue_per_employee, ebitda_margin as calc_ebitda_margin,
    )

    financials = await db.iberinform_financials.find(
        {"company_id": company_id}, {"_id": 0}
    ).sort("year", -1).limit(1).to_list(1)

    if not financials:
        raise HTTPException(404, "No financial data")

    latest = financials[0]
    benchmark = await analyze_sector_benchmark(cnae_code)

    company_metrics = {
        "revenue": latest.get("revenue"),
        "ebitda": latest.get("ebitda"),
        "employees": latest.get("employees"),
        "ebitda_margin": latest.get("ebitda_margin"),
    }
    rev = latest.get("revenue", 0)
    emp = latest.get("employees", 0)
    if rev and emp:
        company_metrics["revenue_per_employee"] = revenue_per_employee(rev, emp)

    # Build comparison against sector benchmarks
    if benchmark.get("peers", 0) > 0:
        # Use quartile data as proxy for comparison
        for metric in ["revenue", "ebitda", "ebitda_margin", "revenue_per_employee"]:
            q = benchmark.get(metric, {})
            if q and company_metrics.get(metric) is not None:
                from docstudio.financial_engine import gap_vs_benchmark
                company_metrics[f"{metric}_vs_median"] = gap_vs_benchmark(
                    company_metrics[metric], q.get("median", 0)
                )

    return {
        **_meta(t0),
        "company_id": company_id,
        "cnae_code": cnae_code,
        "company_metrics": company_metrics,
        "sector_benchmark": benchmark,
    }
```

**Sustituir por:**
```python
@router.get("/financial/compare")
async def compare_company_to_sector(
    company_id: str = Query(...),
    cnae_code: str = Query(...),
    user=Depends(get_current_user),
):
    """Compare a company against its sector peers (deterministic, no AI).

    Fase 1 (DOCUMENT_STUDIO_UNIFICATION_PLAN, 2026-09-01): el dato de la
    empresa objetivo deja de venir de `iberinform_financials` (legacy) y pasa
    a leerse de `master_companies` (vía docstudio/data_access.py). El
    benchmark sectorial ya leía `master_companies` desde antes
    (analyze_sector_benchmark, comentario "Fase 2" previo de este mismo
    archivo). Mismo shape de respuesta que la versión legacy — sin cambios
    para quien lo llame (aunque, como con el endpoint anterior, no hay
    ningún caller hoy).
    """
    t0 = time.time()
    from docstudio import data_access as DA
    from docstudio.financial_engine import (
        analyze_sector_benchmark, revenue_per_employee, gap_vs_benchmark,
    )

    company = await DA.resolve_company(identifier=company_id)
    latest = (company.get("financials") or {}).get("latest") if company else None
    if not latest:
        raise HTTPException(404, "No financial data")

    employees = (company.get("size") or {}).get("employees_total")
    benchmark = await analyze_sector_benchmark(cnae_code)

    company_metrics = {
        "revenue": latest.get("revenue"),
        "ebitda": latest.get("ebitda"),
        "employees": employees,
        "ebitda_margin": latest.get("ebitda_margin"),
    }
    rev = latest.get("revenue") or 0
    emp = employees or 0
    if rev and emp:
        company_metrics["revenue_per_employee"] = revenue_per_employee(rev, emp)

    # Build comparison against sector benchmarks
    if benchmark.get("peers", 0) > 0:
        # Use quartile data as proxy for comparison
        for metric in ["revenue", "ebitda", "ebitda_margin", "revenue_per_employee"]:
            q = benchmark.get(metric, {})
            if q and company_metrics.get(metric) is not None:
                company_metrics[f"{metric}_vs_median"] = gap_vs_benchmark(
                    company_metrics[metric], q.get("median", 0)
                )

    return {
        **_meta(t0),
        "company_id": company_id,
        "cnae_code": cnae_code,
        "company_metrics": company_metrics,
        "sector_benchmark": benchmark,
    }
```

## Notas para Neo

- No toca nada de `composer.py` ni de los demás endpoints de `docstudio/routes.py` — cambio localizado a estas 2 funciones.
- El endpoint `/financial/sector-benchmark/{cnae_code}` (justo entre los dos) NO se toca — ya lee `master_companies` desde antes, nada que migrar ahí.
- Antes de aplicar, un grep rápido de `financial/company` y `financial/compare` en Intel + Beta + cualquier integración externa que conozcas, por si hay algún consumidor que no viéramos nosotros (nuestra búsqueda no encontró ninguno). **Si el grep encuentra algún consumidor real, NO aplicar este parche — avisar a Daniel y esperar su decisión, en vez de aplicarlo o adaptarlo por cuenta propia.**
- Verificar en preview: llamar a ambos endpoints con una empresa real (`company_id` = cif_normalized o master_id) y confirmar que devuelven datos donde antes devolvían 404 huérfano por colección vacía/desalineada, y que `/financial/compare` mantiene exactamente el mismo shape de respuesta (por si acaso hay un consumidor no detectado).
