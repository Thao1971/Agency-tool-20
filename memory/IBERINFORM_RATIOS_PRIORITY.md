# IBERINFORM_RATIOS_PRIORITY.md
**Ratios de Iberinform a ingerir — prioridad acordada con Daniel (2026-07-24)**

Iberinform entrega 31 ratios precalculados por empresa/año en `Datos_RATIOS.tab`
(verificado en la muestra real `tests/fixtures/iberinform_sample/ES_Financial_Detail_Valu8.csv`).
Hoy la ingesta (`services/data_layer/ingestion/iberinform_tab_ingest.py`) los descarta
("no consumer") y solo usa REN007 como control en `account_map.py`.

**Criterio de priorización (lente de analista M&A):** priorizar por INFORMACIÓN NUEVA —
lo que hoy no podemos calcular con las 6 partidas que guardamos, y los scores
propietarios de Iberinform (imposibles de derivar). Los que ya calculamos se ingieren
solo como validación cruzada.

**Decisión de Daniel:** ingerir **Tier 1 + 2 + 3 (28 ratios)**. Fuera el Tier 4
(riesgo de crédito comercial, poco relevante en sell-side): `OC1`, `SF019`, `SF024`.

> Pendiente al implementar la ampliación de ingesta: (a) ampliar el filtro de
> `Datos_BALANCES.tab` para guardar además ~14 partidas (40400, 40600, 40700, 41400,
> 41500, 11xxx/12xxx corrientes, 31000/32000, 32500, 94705…) que habilitan los ratios
> propios hoy N/D; (b) crear colección/campo `norm_financials.ratios` (o `norm_ratios`)
> con los 28 códigos; (c) exponerlos en el bundle y en `financial_enrich.py`. Requiere
> re-ingesta del dataset 25k (deploy + backfill).
> ⚠️ Verificar los nombres canónicos ES contra `Diccionario_Datos_Financial_Info.pdf`
> antes de fijarlos — SF021/22/23 (periodos medios de cobro/pago/aprovisionamiento) y
> SF006/007 (endeudamiento A/B) tienen etiquetas en inglés ambiguas en la muestra.

## Tier 1 — Máxima prioridad (nuevo e imprescindible; hoy imposible o score propietario)

| Código | Ratio (fuente EN) | Nombre canónico propuesto | Uso en cuaderno |
|---|---|---|---|
| R01 | Rating | `rating_iberinform` | Score propietario — validación independiente de crédito/solvencia. Teaser/IM. |
| S01 | Solvency | `solvency_score` | Score propietario de solvencia. Sello de tercero. |
| SF025 | Interest coverage | `interest_coverage` | Riesgo de deuda. Hoy N/D (falta gasto financiero 41500). |
| SF021 | Average payment deadline | `avg_collection_period` (verificar) | Ciclo de circulante / working capital al cierre. |
| SF022 | Average payment term | `avg_payment_period` (verificar) | Ídem. |
| SF023 | Average supply term | `avg_supply_period` (verificar) | Ídem. |
| PRO001 | Working capital | `working_capital` | Capital circulante. N/D hoy. |
| SF003 | Immediate liquidity | `immediate_liquidity` | Caja/pasivo corriente. N/D hoy. |
| SF004 | Treasury coefficient | `treasury_ratio` | Tesorería. N/D hoy. |
| SF008 | Quality of the debt | `debt_quality` | Peso de deuda C/P. Relevante en negociación. |
| SF009 | Long-term debt ratio | `lt_debt_ratio` | Estructura de deuda L/P. |
| SF010 | Short-term debt ratio | `st_debt_ratio` | Estructura de deuda C/P. |

## Tier 2 — Alta (eficiencia/productividad; diferencial en servicios y agencias)

| Código | Ratio | Nombre canónico | Uso |
|---|---|---|---|
| EFI008 | Personnel expenses per employee | `personnel_expense_per_employee` | Coste de personal/empleado — highlight en agencias. |
| EFI006 | Sales per employee | `sales_per_employee` | Productividad comercial. |
| PRO002 | Productivity | `productivity` | Productividad global. |
| PRO005 | Leverage | `leverage` | Apalancamiento operativo/financiero. |
| EFI001 | Active rotation | `asset_turnover` | Rotación de activo. |
| EFI003 | Rotation of working capital | `working_capital_turnover` | Rotación del circulante. |

## Tier 3 — Media (ya los calculamos; ingerir el oficial como validación cruzada)

| Código | Ratio | Nombre canónico | Nota |
|---|---|---|---|
| REN007 | Ebitda / sales | `ebitda_margin` | = nuestro `ebitda_margin`. |
| REN005 | Net margin | `net_margin` | = nuestro `net_margin`. |
| REN006 | Margin on sales | `margin_on_sales` | Margen sobre ventas. |
| REN001 | Economic profitability | `roa` | = nuestro `roa`. |
| REN003 | Financial profit | `roe` | = nuestro `roe`. |
| REN010 | Sales variation | `sales_variation` | ≈ crecimiento de ingresos. |
| SF001 | Solvency ratio | `solvency_ratio` | = nuestra `solvency` (aprox). |
| SF006 | Debt ratio A | `debt_ratio_a` (verificar) | Endeudamiento. |
| SF007 | Debt ratio B | `debt_ratio_b` (verificar) | Endeudamiento. |
| SF011 | Coefficient of guarantee | `guarantee_ratio` | Coeficiente de garantía. |

## Tier 4 — EXCLUIDOS del cuaderno (riesgo de crédito, no sell-side)

`OC1` (Credit Limit), `SF019` (Financing stocks), `SF024` (Availability ratio).
