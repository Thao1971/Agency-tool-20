# PARA INTEL — Desplegar narrativa financiera + purgar caché (HARDENING-004)

> Objetivo: que beta.arroba.com pinte **"Veredicto de ARROBA"** y **"Lectura financiera de ARROBA"**
> (hoy `<Empty/>`). Todo lo de abajo está **verificado en preview**; requiere **redeploy a prod** +
> purga de caché. No hay que tocar Beta.

## Diagnóstico
- La narrativa (`assessment` / `verdict` / `weaknesses[]` / `risks[]`) **ya está en el código**
  (`services/engines/financial/engine.py::_financial_narrative`), NO en un `analyze.py`.
- `intel.arroba.com` (prod, Atlas) corre **código antiguo** → no genera la narrativa; y además puede
  servir **payloads cacheados** en Mongo previos a la narrativa. Un restart solo limpia la **LRU en
  memoria**, no el **TTL de Mongo**.

## Pasos (acción del usuario/ops en prod)

1. **Redeploy** del código de preview a producción (`intel.arroba.com`).
   Incluye la narrativa + el nuevo router `/api/v1/admin/cache`.

2. **Purgar la caché Mongo de análisis** (JWT admin sobre prod):
   ```bash
   # (opcional) ver qué caché tiene realmente prod y su nombre exacto:
   curl -s https://intel.arroba.com/api/v1/admin/cache/inspect \
     -H "Authorization: Bearer <JWT_ADMIN_PROD>"

   # purgar analyze_cache + intelligence_cache (idempotente, conserva índices):
   curl -s -X POST https://intel.arroba.com/api/v1/admin/cache/purge-analyze \
     -H "Authorization: Bearer <JWT_ADMIN_PROD>"
   ```
   Si `inspect` revela otro nombre de colección de caché, purgarla también:
   `.../purge-analyze?extra=<nombre_coleccion>`

3. **Verificar en prod** (X-API-Key de servicio):
   ```bash
   # SERVIER → assessment + verdict (empresa sólida; weaknesses/risks vacíos = correcto)
   curl -s -X POST https://intel.arroba.com/api/v1/financial-intelligence/analyze \
     -H "X-API-Key: <SERVICE_KEY>" -H "Content-Type: application/json" \
     -d '{"identifier":"B28184687"}' | jq '.financial_quality | {assessment, verdict}'

   # COPISA → verdict + risks[] (empresa frágil)
   curl -s -X POST https://intel.arroba.com/api/v1/financial-intelligence/analyze \
     -H "X-API-Key: <SERVICE_KEY>" -H "Content-Type: application/json" \
     -d '{"identifier":"A01006394"}' | jq '.financial_quality | {assessment, verdict, risks}'
   ```
   Cuando eso salga en prod, Beta pintará las dos secciones sin tocar nada de Beta.

## Referencia — resultado esperado (verificado en preview)
- **SERVIER (B28184687)**: `assessment` = "Calidad financiera sólida (100/100). Margen EBITDA
  moderado del 11.3%. Ingresos al alza (11.7%) interanual. Autonomía financiera (PN/Activo) del 73.5%."
  · `verdict` = "Perfil financiero sólido y consistente; candidato atractivo para operaciones
  corporativas." · `weaknesses` = [] · `risks` = [] (correcto).
- **COPISA INFRASTRUCTURES (A01006394)**: `verdict` = "Perfil frágil: resultado neto negativo.
  Requiere análisis y due diligence adicionales." · `risks` = ["Resultado neto negativo"].

## Después de esto (acordado)
- (b) Enriquecer reglas de `weaknesses[]`/`risks[]` (márgenes en caída, deuda/EBITDA, working
  capital negativo, ROE bajo). Solo tras confirmar (a) en prod.
