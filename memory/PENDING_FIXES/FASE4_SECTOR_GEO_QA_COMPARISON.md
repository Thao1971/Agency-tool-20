# Fase 4 — Script de QA: comparación de scores Sector/Geo (antes de migrar)

**Qué es esto:** NO es la migración de Fase 4 en sí. Es la comparación "antes/después" que Daniel pidió hacer primero, para ver si migrar el conteo de empresas de `iberinform_companies` a `master_companies` movería silenciosamente `dynamism_score`, rankings sectoriales o territoriales que el usuario ya ve hoy.

**Archivo nuevo, no toca nada existente:** `backend/scripts/compare_sector_geo_master_vs_iberinform.py` — de solo lectura, no escribe en ninguna colección, no modifica `services/sector_intelligence_v2.py` ni `services/geo_intelligence.py` (los importa y reutiliza tal cual, para garantizar que la fórmula de comparación es exactamente la misma que la real, no una reimplementación que pueda divergir).

**Qué compara exactamente:** el único ingrediente que cambiaría en la Fase 4 real es de dónde sale el conteo de empresas por CNAE (Sector) y por provincia (Geo) que alimenta el sub-score "iberinform" de `activity_score` (25 % del peso en Sector, 20 % en Geo). El resto de fuentes — demografía INE, contratación pública, BORME — no depende de `iberinform_companies` ni de `master_companies`, así que son idénticas en ambos cálculos. El script recalcula `dynamism_score` completo (Section/Division/Group para Sector; Province/CCAA para Geo) con el conteo viejo y con el conteo nuevo, y compara.

## Instrucciones para Neo

1. Copiar `memory/PENDING_FIXES/compare_sector_geo_master_vs_iberinform.py` a `backend/scripts/compare_sector_geo_master_vs_iberinform.py` (mismo directorio que los demás scripts de un solo uso, ej. `scripts/coverage_dn_ebitda.py`).
2. Ejecutar: `cd backend && python -m scripts.compare_sector_geo_master_vs_iberinform`
3. El script imprime en pantalla:
   - Total de empresas contabilizadas en cada colección (Sector y Geo por separado, porque el campo de provincia puede no resolver igual de bien que el de CNAE).
   - Si hay nombres de provincia en `master_companies` que no resuelven a un código INE (`location.provincia` no coincide con el mapa `BORME_PROVINCE_MAP` de `services/geo_catalog.py`) — se listan aparte, nunca se descartan en silencio.
   - Resumen por bloque (Sector / Geo): delta medio, cuántos ítems cambian ≥10 puntos, ≥5 puntos, cuántos cambian de `trend_direction` (up/down/stable), cuántos cambian de puesto en el ranking de su nivel.
   - Top 15 "movers" (mayor cambio absoluto de `dynamism_score`) de cada bloque, con el detalle: código, etiqueta, score antes → después, trend antes → después, conteo de empresas antes → después, ranking antes → después.
4. Además deja un volcado completo en JSON en `/tmp/fase4_sector_geo_comparison.json` (todas las secciones/divisiones/grupos/provincias/CCAA, no solo el top 15) — pégaselo a Daniel o adjúntaselo si quiere revisarlo con calma en una hoja de cálculo.
5. **No desplegar nada de Sector/Geo a partir de este script.** Es solo diagnóstico. La decisión de migrar (o no) la toma Daniel después de ver el informe — si hay muchos cambios grandes o cambios de trend, probablemente NO conviene migrar tal cual y haría falta investigar por qué difieren los conteos antes de tocar producción.

## Notas

- El script tarda un poco más que los otros de `scripts/` porque recorre las ~1.100 combinaciones de CNAE (secciones + divisiones + grupos) y las 52 provincias + 17 CCAA, cada una con su propio cálculo — es normal que tarde uno o dos minutos.
- Si `master_companies` está mucho menos poblado que `iberinform_companies` en este momento (ingesta parcial, etc.), es esperable ver diferencias grandes de conteo — eso no es necesariamente un bug del script, pero si el hueco es muy grande, avisa antes de que Daniel decida sobre la migración: la comparación solo es representativa cuando ambas colecciones tienen cobertura comparable.
- Este script vive en `Intel-140826` (backend) — no toca nada de Beta.
