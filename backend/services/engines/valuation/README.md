# Motor de valoración de Arroba — Intel

**Versión documentada:** arroba-dcf-v1
**Reglas sectoriales:** sector-valuation-seed-v1
**Fecha efectiva:** 20 de septiembre de 2026
**Responsable de cálculo:** Intel
**Consumidor:** Beta, mediante la API de Intel

## 1. Finalidad y perímetro

Este módulo calcula una valoración indicativa de empresas españolas a partir de cuentas
normalizadas de Iberinform. Intel es el único responsable de clasificación, supuestos,
cálculos, controles, confianza y trazabilidad. Beta representa el resultado recibido y no
recalcula ninguna magnitud financiera.

La versión actual es una herramienta de screening. Las bandas sectoriales son semillas de
política de Arroba, no percentiles observados del universo de Iberinform. Cada salida se
identifica como provisional_policy_seed y screen_grade hasta completar el procedimiento de
[calibración](CALIBRATION_RUNBOOK.md).

## 2. Arquitectura y separación Intel–Beta

~~~mermaid
flowchart LR
    A[Iberinform] --> B[Normalización financiera]
    B --> C[Serie histórica canónica]
    D[CNAE y tamaño] --> E[Regla sectorial]
    C --> F[Motor DCF]
    E --> F
    F --> G[valuation.dcf]
    G --> H[API Intel]
    H --> I[Beta]
~~~

Intel localiza la empresa, obtiene CNAE y cuentas, construye la serie histórica, resuelve
arquetipo y tamaño, selecciona supuestos, calcula la valoración y devuelve trazabilidad.
Beta consume valuation.dcf, formatea el resultado y muestra advertencias. Beta no calcula
WACC, flujos, valor terminal ni ajustes sectoriales.

## 3. Componentes

| Archivo | Responsabilidad |
|---|---|
| sector_rules.py | Mapeo CNAE–arquetipo, tamaños y bandas provisionales |
| calibration.py | Cálculo puro de cohortes, percentiles y calidad |
| calibration_job.py | Lectura por lotes y publicación de candidatos Iberinform |
| wacc.py | Coste de capital, beta, deuda y estructura objetivo |
| dcf.py | Supuestos, proyección FCFF, escenarios y sensibilidad |
| ../financial/engine.py | Orquestación con Master Layer e Iberinform |
| tests/test_dcf.py | Pruebas del cálculo y datos ausentes |
| tests/test_sector_rules.py | Pruebas de CNAE, arquetipos y tamaños |
| routes/engine_schemas.py | Contrato público valuation.dcf |

## 4. Datos de entrada

calculate_dcf recibe una serie ordenada del ejercicio más reciente al más antiguo.

| Campo | Uso | Tratamiento |
|---|---|---|
| year | Fecha de referencia | Se conserva en trazabilidad |
| revenue | Base de proyección | Debe ser positivo |
| operating_income | EBIT | Margen histórico |
| depreciation | Amortización | Valor absoluto |
| cf_capex | Inversión | Valor absoluto |
| current_assets | Capital circulante | Junto con pasivo corriente |
| current_liabilities | Capital circulante | Se resta del activo corriente |
| working_capital | Capital circulante directo | Prioridad si existe |
| financial_debt | Puente EV–equity | Sin deuda no se calcula equity |
| cash | Puente EV–equity | Se suma al valor del capital |
| currency | Unidad | EUR por defecto |

La fuente financiera declarada es Iberinform. El puente a Equity Value exige financial_debt y cash. Si cualquiera no consta, el motor
entrega equity_value nulo y una advertencia; nunca supone un valor cero.

## 5. Resolución sectorial

Se extraen los dos primeros dígitos numéricos del CNAE.

| Arquetipo | Divisiones CNAE |
|---|---|
| Inmobiliario | 68 |
| Construcción | 41–43 |
| Medios y contenidos | 58–60 |
| Publicidad | 73 |
| Software y datos | 62–63 |
| Servicios profesionales | 69–72 y 74 |
| Industria | 10–33 |
| Mayorista | 46 |
| Comercio minorista | 47 |
| Hostelería | 55–56 |
| Transporte y logística | 49–53 |
| Energía y utilities | 35 |
| Sanidad | 86–88 |
| Empresa general | CNAE ausente o sin regla |

Banca, seguros, SOCIMI, concesiones, holdings y promotoras por proyecto necesitan modelos
especiales antes de poder considerarse preparados para decisión.

### Tramos de tamaño

| Tramo | Facturación |
|---|---:|
| micro | Menos de 2 M€ |
| small | 2 M€ a menos de 10 M€ |
| medium | 10 M€ a menos de 50 M€ |
| large | 50 M€ o más |
| unknown | Sin facturación |

La semilla provisional añade al WACC: micro +2,50%; pequeña +1,50%; mediana +0,75%;
grande 0%; desconocida +1,50%. Es una regla de política pendiente de calibración, no una
prima observada.

## 6. Jerarquía de supuestos

1. Valor explícito: user_supplied.
2. Histórico Iberinform combinado con sector: iberinform_historical_sector_blend.
3. Mediana sectorial sin histórico: sector_policy_seed.
4. Histórico sin regla: iberinform_historical.
5. Valor general de Arroba: arroba_default.

### Mezcla empresa–sector

~~~text
valor_mezclado = 70% × valor_empresa + 30% × mediana_sector
valor_final = máximo(P25, mínimo(P75, valor_mezclado))
~~~

La salida conserva valor empresarial, mediana sectorial, peso, banda P25/P75, valor final y
procedencia. Esto reduce el efecto de un ejercicio extremo sin reemplazar los datos propios.

## 7. Cálculo de los drivers

### Crecimiento

~~~text
CAGR = (Ingresos_recientes / Ingresos_antiguos) ^ (1 / (n - 1)) - 1
~~~

Se mezcla con el sector y se limita globalmente entre -10% y +25%.

### Margen EBIT

~~~text
Margen EBIT = mediana(EBIT_t / Ingresos_t)
~~~

Se mezcla con el sector y se limita entre -25% y +60%.

### Amortización y capex

~~~text
Amortización / ventas = mediana(abs(amortización_t) / ingresos_t)
Capex / ventas = mediana(abs(capex_t) / ingresos_t)
~~~

El valor absoluto normaliza el signo contable. Capex se mezcla con sector; amortización aún
no.

### Capital circulante

Si existe working_capital se usa directamente. En otro caso:

~~~text
Capital circulante = Activo corriente - Pasivo corriente
Capital circulante / ventas = mediana(Capital circulante_t / ingresos_t)
~~~

Es una aproximación. La calibración deberá preferir clientes + inventarios - proveedores.

## 8. Fórmula DCF

Para cada año proyectado:

~~~text
Ingresos_t = Ingresos_(t-1) × (1 + crecimiento)
EBIT_t = Ingresos_t × margen_EBIT
Amortización_t = Ingresos_t × amortización_sobre_ventas
Capex_t = Ingresos_t × capex_sobre_ventas
ΔNWC_t = (Ingresos_t - Ingresos_(t-1)) × NWC_sobre_ventas

FCFF_t = EBIT_t × (1 - tipo_impositivo)
         + Amortización_t - Capex_t - ΔNWC_t
PV(FCFF_t) = FCFF_t / (1 + WACC)^t
~~~

Valor terminal:

~~~text
FCFF_terminal = FCFF_último × (1 + g)
Valor_terminal = FCFF_terminal / (WACC - g)
PV_terminal = Valor_terminal / (1 + WACC)^n
~~~

Es obligatorio que WACC sea mayor que g.

~~~text
Enterprise value = suma de PV(FCFF_t) + PV_terminal
Equity value = Enterprise value - Deuda financiera + Caja
~~~

## 9. Escenarios y sensibilidad

Horizonte base: cinco años.

| Parámetro | Conservador | Base | Optimista |
|---|---:|---:|---:|
| Crecimiento | Base −2,00% | Base | Base +2,00% |
| Margen EBIT | Base −2,00% | Base | Base +2,00% |
| WACC | Base +2,00% | Base | Base −1,00% |
| g terminal | Base −1,00%, mínimo 0% | Base | Base +0,50% |

La sensibilidad es una matriz 3 × 3 con WACC base ±1% y g base ±0,50%. Las combinaciones
WACC menor o igual que g se devuelven nulas.

## 10. Confianza

Parte de 0,90 y aplica:

| Condición | Penalización |
|---|---:|
| Cada supuesto general de Arroba | −0,08 |
| Deuda ausente | −0,12 |
| Menos de tres ejercicios | −0,08 |
| Regla sectorial provisional | −0,10 |

El mínimo es 0,20. Mide suficiencia y procedencia, no la probabilidad de acertar.

La salida seguirá siendo screen_grade mientras las bandas sean semillas, el WACC no se
calcule con mercado y comparables, o no exista una cohorte Iberinform suficiente.

## 11. Contrato de salida

~~~json
{
  "status": "available",
  "engine_version": "arroba-dcf-v1",
  "method": "FCFF_Gordon_growth",
  "currency": "EUR",
  "as_of": 2025,
  "assumptions": {
    "wacc": {
      "value": 0.1125,
      "source": "sector_policy_seed",
      "sector_median": 0.1125,
      "sector_band": [0.0975, 0.1375]
    }
  },
  "scenarios": {
    "base": {
      "enterprise_value": 10435380.71,
      "equity_value": 8435380.71,
      "projections": []
    }
  },
  "confidence": 0.64,
  "warnings": [],
  "sector_rule": {
    "archetype": "media_content",
    "size_band": "medium",
    "calibration_status": "provisional_policy_seed"
  },
  "decision_readiness": "screen_grade",
  "lineage": {
    "financial_source": "Iberinform",
    "calculation_engine": "Intel",
    "input_years": [2025, 2024, 2023]
  }
}
~~~

La lista vacía abrevia las proyecciones que en la respuesta real llegan completas.

### API

~~~http
POST /api/v1/financial-intelligence/analyze
POST /api/v1/financial-intelligence/valuation
X-API-Key: <service-key>

{"identifier": "<master_id o CIF>"}
~~~

Beta debe tolerar status unavailable, equity_value nulo, nuevos parámetros, advertencias,
arquetipos y versiones.

## 12. Indisponibilidad

| Motivo | Código o respuesta |
|---|---|
| Ingresos no positivos | positive_revenue_required |
| Horizonte menor de un año | invalid_dcf_assumptions |
| WACC menor o igual que g | invalid_dcf_assumptions |
| Empresa no localizada | HTTP 404 |
| Sin cuentas normalizadas | insufficient_data |

## 13. Fuentes

1. Iberinform: universo, identidad, CNAE y cuentas.
2. MarketScreener / Capital IQ: comparables cotizados.
3. CNMV: contraste financiero público.
4. BCE: referencia temporal libre de riesgo.
5. TTR: operaciones privadas cuando se conecte.
6. Arroba: clasificación, reglas, cálculo y confianza.

Referencias metodológicas:

- Damodaran: https://pages.stern.nyu.edu/adamodar/New_Home_Page/datacurrent.html
- Drivers sectoriales: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/cfbasics.html
- BCE: https://data.ecb.europa.eu/methodology/yield-curves
- CNMV: https://www.cnmv.es/portal/publicaciones/pub_estadisticas?id=SC1

No se atribuirán a Iberinform estadísticas no calculadas efectivamente sobre sus datos.

## 14. Pruebas

Desde backend:

~~~bash
python3 -m pytest services/engines/valuation/tests -q
~~~

Actualmente se comprueban DCF, escenarios, sensibilidad, deuda ausente, WACC/g inválidos,
ingresos, fallbacks, signos contables, capital circulante, CNAE, tamaños y trazabilidad.

## 15. Limitaciones

1. Bandas provisionales, aún sin agregación Iberinform.
2. WACC de referencia, aún sin cálculo completo de mercado.
3. Crecimiento y margen constantes durante la proyección.
4. Sin modelo integrado de tres estados.
5. Sin créditos fiscales explícitos.
6. Sin separación entre capex de mantenimiento y crecimiento.
7. Sin ajustes de arrendamientos, pensiones o minoritarios.
8. Sin operaciones privadas TTR.
9. Sectores especiales pendientes.
10. Valoración combinada DCF–cotizadas–transacciones pendiente.

## 16. Criterios de calibración

Una regla solo podrá llamarse calibrated_iberinform cuando tenga cohorte reproducible,
muestra mínima, fecha de corte, población inicial y final, exclusiones, percentiles,
controles, revisión de negocio, versión inmutable y pruebas de regresión.

## 17. Política de cambios

Cada cambio material debe actualizar versión, fecha, documentación, pruebas, fuentes,
comparación antes/después y compatibilidad con Beta. Las versiones publicadas no se
sobrescriben: una valoración debe reconstruirse con la versión exacta usada.

## 18. Documentación para informes

- [Metodología financiera](FINANCIAL_METHODOLOGY.md): explicación para profesionales
  financieros de los métodos, parámetros, conciliación e interpretación.
- [Texto estándar para informes](VALUATION_REPORT_STANDARD.md): bloques condicionales y
  textos obligatorios para PDF y otras entregas.


## 19. Calibrador Iberinform

El calibrador implementado genera candidatos versionados y nunca activa reglas
automáticamente. Procesa Master Layer y norm_financials por lotes, forma cohortes por
división CNAE o arquetipo y tamaño, calcula una observación temporal por empresa, conserva
una muestra determinística máxima de 20.000 compañías por métrica, winsoriza en P5/P95 y
calcula P25, mediana y P75.

Umbrales:

- 20 observaciones: mediana publicable como candidata.
- 40 observaciones: banda P25/P75 publicable.
- 150 observaciones: muestra marcada como de alta confianza.
- Todos los resultados permanecen candidate_iberinform y review_required hasta revisión.

Previsualización limitada, sin escrituras:

~~~bash
cd backend
python3 -m scripts.calibrate_valuation_sectors --max-companies 10000   --cutoff-date 2026-09-20 --output /tmp/valuation-calibration-preview.json
~~~

Publicación de candidatos inmutables:

~~~bash
cd backend
python3 -m scripts.calibrate_valuation_sectors --cutoff-date 2026-09-20   --publish --output /tmp/valuation-calibration-published.json
~~~

La publicación escribe valuation_sector_calibration_runs y
valuation_sector_rule_candidates. No modifica sector_rules.py ni las reglas activas.


## 20. WACC

El DCF utiliza el motor source-aware arroba-wacc-v1. La metodología completa, las fórmulas,
las fuentes y los componentes provisionales se describen en
[WACC_METHODOLOGY.md](WACC_METHODOLOGY.md). El bloque completo se expone como wacc_analysis.

## 21. Captura BCE y cotizadas

El scheduler captura diariamente la serie oficial BCE AAA EUR spot a diez años. Los exports
de MarketScreener y Capital IQ se importan mediante scripts.import_public_comparables y se
normalizan en valuation_public_comparables. Intel utiliza la última observación BCE y los
comparables activos del arquetipo para calcular beta y estructura financiera objetivo.
