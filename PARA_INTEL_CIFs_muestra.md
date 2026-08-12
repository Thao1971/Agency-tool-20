# PARA INTEL — CIFs de muestra (existen en master, verificados)

> Sustituye a los 5 de prueba (4 daban 404 = no están en el master de Intel).
> Todos verificados vía `GET /api/v1/company/{cif}/ficha` (200) en prod `intel.arroba.com`.

## Holdings con participadas (árbol completo de Propiedad up + down)

| CIF | Nombre | Rol | Participadas | Ingresos | Sede | Notas |
|-----|--------|-----|:---:|---:|------|-------|
| **B28184687** | LABORATORIOS SERVIER | holding | 2 (DANVAL, LAB. LESTRAL, 100%) | ~145 M€ | Madrid | 2 accionistas (SERVIER INTERNATIONAL BV 73,35% = UBO). Caso rico up+down. |
| **A08678823** | BIOSYSTEMS | holding | 18 | 55,3 M€ | Barcelona | Grupo grande, buen árbol descendente. |
| **A28287092** | NESGAR PROMOCIONES | holding | 27 | 15,9 M€ | Madrid | Holding inmobiliario. |
| **A61351540** | GRUPO INVERSOR HESPERIA | holding | 29 | 4,9 M€ | Hospitalet de Llobregat | Holding hotelero, 11 consejeros. |
| **B59510453** | MEDITERRANEAN SEARCH | holding | 34 | s/d | Barcelona | Matriz GRUPO ADLANTER 100% (UBO). Máximo nº de participadas. |

## Casos DPD / degradado

| CIF | Nombre | Rol | Para qué |
|-----|--------|-----|----------|
| **A07040223** | (grupo ALZA) | holding | Accionistas **personas físicas** (2) + parent + 7 participadas → probar `authenticated=false` (anónimo) vs `true` (nominal). |
| **A03006897** | CONSTRUCCIONES Y URBANIZACIONES SAN RAFAEL | target | Solo 2 accionistas, **sin participadas** → caso degradado (only upstream). |

## Verificación rápida
```bash
# árbol nominal (autenticado)
curl -s "https://intel.arroba.com/api/v1/company/A61351540/control-graph?authenticated=true" -H "X-API-Key: <KEY>"
# árbol anónimo (sin nombres)
curl -s "https://intel.arroba.com/api/v1/company/A07040223/control-graph" -H "X-API-Key: <KEY>"
```

> Nota: SERVIER **sí** tiene 2 participadas reales (role=holding), no "sin ellas". Para un leaf sin
> participadas usar **A03006897**.
