# PARA INTEL — Resultado: Armonización de contrato + Cobertura

> Respuesta a `PARA_INTEL_armonizacion_cobertura.md`. Todo additivo, solo dato real, prosa CF.
> Verificado con `X-API-Key`. En **preview**; requiere **redeploy** para producción.

## BLOQUE A — Armonización de contrato (✅ COMPLETO)

| # | Qué pedía Beta | Estado | Detalle |
|---|---|---|---|
| A1 | `identity` con `description` + `objeto_social` no nulos | ✅ | `POST /api/v2/company-intelligence/identity` devuelve `corporate_purpose` (objeto social) y `description` (enriquecimiento web). |
| A2 | `valuation` con `benchmark` + `methodology` | ✅ | `POST /api/v1/financial-intelligence/valuation` ahora incluye `scenarios`, `benchmark` y `methodology`. |
| A3 | `section/signal` (hoy 404) → señales por empresa | ✅ NUEVO | `GET /api/v1/company/{id}/signals`: `[{type,category,date,polarity,severity,title,confidence,trend}]`. **Cobertura: 24.989 empresas.** Incluido también en el agregador `/ficha`. |
| A4 | `balance_sheet` con desglose de deuda | ✅ | `statements.balance_sheet` añade `st_debt`, `lt_debt` (+ `financial_debt`). Se poblan donde el dato existe. |

## BLOQUE B — Cobertura

| # | Objetivo | Estado | Cobertura / nota |
|---|---|---|---|
| B7 | Poblar `financial_quality.assessment` + `weaknesses` + `risks` | ✅ HECHO | `financial_quality` ahora trae `label`, `assessment` ("Lectura financiera de ARROBA", prosa), `verdict` ("Veredicto de ARROBA"), `strengths`, `weaknesses`, `risks`. **Cobertura: 9.593 empresas** (todas las que tienen financieros). |
| B5 | Activar cash flow + percentiles de liquidez/WC a escala | ⛔ BLOQUEADO (dato upstream) | Los códigos EAV de balance/EFE (current_assets, current_liabilities, st/lt_debt, existencias, deudores, EFE…) tienen **~0 cobertura en `norm_financials` (5-8 de 13.501)**. No es mapeo: **falta ingerir el EAV completo de Iberinform**. El código ya está cableado → se activará automáticamente al ingerir. |
| B6 | Enriquecimiento web a escala (`description`) | 🟡 PENDIENTE | Hoy 29/24.992. Requiere un run del pipeline de scraping+LLM (pesado). Recomendado: job en background por lotes. |

## BLOQUE C — Futuro (no bloquea)
- Innovación desde patentes/OEPM (viable, hay que construir el motor).
- Árbol societario multinivel desde `/graph/{id}/traverse` (hoy `ownership` es de 1 nivel).

## Cobertura global (transparencia)
- Total empresas: **24.992**
- Con estados financieros (→ ratios, ranking, valoración, **assessment/verdict**): **9.593**
- Con Estado de Flujos de Efectivo (cash flow): **5** ← B5
- Con `description` web: **29** ← B6
- Con señales activas (section/signal): **24.989**

## Pendiente accionable (prioridad)
1. **Redeploy** para publicar Bloque A + B7 en `intel.arroba.com`.
2. **B5 — Re-ingesta del EAV de balance de Iberinform** (mayor impacto: activa cash flow + liquidez/WC en miles de fichas). Es trabajo de ingesta upstream.
3. **B6 — Enriquecimiento web por lotes** (subir `description` y la clasificación fintech/biotech).

*Verificado en preview con `X-API-Key` sobre Servier `B28184687`. Additivo, sin regresión.*
