# SMOKE TEST PÚBLICO OFICIAL — Arroba ↔ Intelligence Engine
**Artefacto permanente del proyecto. Verifica en < 2 min que cualquier despliegue del Intelligence
Engine sigue siendo compatible con Arroba, usando EXCLUSIVAMENTE Base URL pública + X-API-Key.**

> Regla de gobierno: **antes de cada despliegue de Arroba o del Intelligence Engine debe ejecutarse
> este Smoke Test Público.** Si el resultado es **FAIL** → NO se despliega Arroba, NO se despliega el
> Intelligence Engine; se considera una **regresión de integración**.

---

## Objetivo
Confirmar, sin privilegios administrativos, que el flujo canónico de integración funciona y que el
contrato público consumido por Arroba permanece estable.

## Entorno
| Campo | Valor |
|---|---|
| **Base URL (producción)** | `https://intel-agency.emergent.host` |
| **Versión del contrato** | `arroba-integration-contract-v2` (`/api/v1/openapi/arroba.v2.json`) |
| **Auth** | Cabecera `X-API-Key` (clave de Arroba). Sin JWT, sin `/master/*`, sin acceso a Mongo. |
| **Última validación** | **2026-07-12 → PASS (18/18)** |

## Caso canónico
| Campo | Valor |
|---|---|
| **CIF** | `A87803862` |
| **Empresa** | `TOTALENERGIES ELECTRICIDAD Y GAS ESPAÑA` |

> El identificador **oficial de entrada es el CIF** (los contratos son agnósticos: aceptan CIF o
> `master_id`). El `master_id` es específico de cada entorno; **no** debe hardcodearse (en producción
> hoy es `mc_80e03f1e1627`, pero puede cambiar entre entornos/despliegues). Usar siempre el CIF.

## Flujo oficial
```
1. POST /api/v2/company-intelligence/resolve      body {"cif":"A87803862"}
        ↓  (obtiene master_id canónico)
2. POST /api/v2/company-intelligence/identity     body {"identifier":"A87803862"}
        ↓
3. POST /api/v1/financial-intelligence/analyze    body {"identifier":"A87803862"}
```
Todas las llamadas con cabecera `X-API-Key: <clave de Arroba>`.

## Verificaciones (qué debe comprobarse exactamente)
| # | Comprobación | Criterio |
|---|---|---|
| 1 | **HTTP 200** | Los 3 endpoints devuelven `200`. |
| 2 | **master_id devuelto** | `resolve.matches[0].master_id` existe y empieza por `mc_`; `identity.master_id` coincide. |
| 3 | **Identidad** | `identity.legal_name` no nulo; `cnae_primary.code` presente; `data_coverage` presente. |
| 4 | **Financials** | `financial-analyze.has_financials == true`; `kpis.revenue > 0`; `kpis.ebitda` y `kpis.net_income` presentes (Nivel 2). |
| 5 | **Histórico** | `evolution.years >= 2`, con `points[]` de ejercicios reales (sin interpolar). |
| 6 | **data_source** | `explainability.data_source` presente y trazable (p. ej. `master_companies + norm_financials (Iberinform)`). |
| 7 | **Explainability** | `explainability.source_version` y `explainability.basis` presentes. |
| 8 | **Compatibilidad arroba.v2** | `arroba.v2.json` accesible, `info.version == arroba-integration-contract-v2`, e incluye las rutas `/resolve`, `/identity` y `/financial-intelligence/analyze`. |

## Resultado esperado
**PASS** — todas las comprobaciones se cumplen.
**FAIL** — cualquier comprobación falla. (Sin interpretaciones intermedias.)

## Cómo ejecutarlo (script oficial)
```bash
# Script versionado: backend/tools/smoke_test_public.py
ARROBA_API_KEY=<clave_de_arroba> python backend/tools/smoke_test_public.py
# o contra otro entorno:
python backend/tools/smoke_test_public.py --base https://intel-agency.emergent.host --key <clave>
```
- Imprime una línea `[PASS]/[FAIL]` por comprobación y un veredicto final `RESULTADO: PASS|FAIL`.
- **Exit code:** `0` = PASS, `1` = FAIL (apto para CI / gate de despliegue).

### Comando cURL mínimo (verificación manual rápida)
```bash
BASE=https://intel-agency.emergent.host ; KEY=<clave_de_arroba>
curl -s -X POST "$BASE/api/v2/company-intelligence/resolve"  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{"cif":"A87803862"}'
curl -s -X POST "$BASE/api/v2/company-intelligence/identity" -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{"identifier":"A87803862"}'
curl -s -X POST "$BASE/api/v1/financial-intelligence/analyze" -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{"identifier":"A87803862"}'
```

## Registro de ejecuciones
| Fecha | Entorno | Contrato | Resultado | Notas |
|---|---|---|---|---|
| 2026-07-12 | producción (`intel-agency.emergent.host`) | `arroba-integration-contract-v2` | **PASS (18/18)** | Desbloqueo oficial de F0.2. |

## Estado
- Integración **oficialmente desbloqueada**. **F0.2 autorizado.**
- **CIF `A87803862`** es el **caso canónico de validación de F0**.
- **Contrato congelado durante F0.2** (identificador de entrada, resolución e `identity`/`financial-analyze` estables).
- Mejoras **V2.1** (búsqueda tolerante nombre+provincia, `data_coverage` en resolve) **NO** se implementan durante F0.2.
