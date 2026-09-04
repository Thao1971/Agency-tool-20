# FIX · Signo negativo en periodos medios de `iberinform_ratios.py` (2026-06)

## Contexto
Las cuentas de coste (p.ej. 40400 · Aprovisionamientos) se guardan en negativo en BD por
convención contable. Los ratios de "periodo medio" (días) que dividen por esas cuentas
arrastraban el signo y salían negativos, lo cual no tiene sentido de negocio (un periodo
medio es siempre no-negativo por definición).

Daniel ya aplicó `abs()` a la cuenta de coste en `ratios_library.py` (ratios propios de
arroba). Este fix replica la MISMA lógica en el módulo nuevo de Fase 5
`services/engines/financial/iberinform_ratios.py`, que hace passthrough de los 28 ratios
oficiales precalculados de Iberinform sin normalizar signo.

## Cambio aplicado
`iberinform_ratios.py`:
- Nueva whitelist `POSITIVE_PERIOD_CODES = {"SF021", "SF022", "SF023"}` (los tres periodos
  medios: cobro, pago, aprovisionamiento).
- En `curate()`, se aplica `abs(val)` SOLO a esos tres códigos.
- Alcance confirmado con Daniel = opción (a): se incluye SF021 (divide por ingresos, hoy no
  afectado) por robustez, para tratar todas las métricas de "días" igual y no dejar un caso
  especial que podría romperse en el futuro.

## Lo que NO se toca (pueden ser legítimamente negativos)
Márgenes (REN005/REN006/REN007), ROA/ROE (REN001/REN003), variación de ventas (REN010) y
fondo de maniobra / capital circulante (PRO001) pasan tal cual, sin `abs()`.

## Lo que NO se hace (instrucción explícita de Daniel)
- NO se documenta ni expone ninguna explicación de "proveedores prepagados" en tooltips
  (fue una traza del bug, no un insight real).
- NO se despliega a producción. Solo preview.

## Verificación
1. Unit (`curate()` con negativos simulados): SF021/22/23 → 45/60/30 positivos;
   REN010=-15.4, PRO001=-1200, REN005=-3.2 intactos. OK.
2. Smoke E2E (ficha real de Servier `mc_36c100bcee4a`, `/api/v1/company/{id}/ficha`):
   inyectados temporalmente SF021=-45/SF022=-60/SF023=-30 + `ratios_source:"iberinform"`
   en el doc individual 2024 → la ficha devolvió avg_collection=45, avg_payment=60,
   avg_supply=30 (positivos) y net_margin_iberinform=-3.2 (negativo, correcto). Estado de BD
   RESTAURADO exactamente (ratios:None, source:None). OK.

## Nota de datos (pendiente, no bloquea el fix)
Hoy 0 documentos en BD tienen `ratios_source:"iberinform"` → la re-ingesta del dataset .tab
de 25k sigue pendiente. El fix ya está en su sitio para cuando esos datos se ingesten.
