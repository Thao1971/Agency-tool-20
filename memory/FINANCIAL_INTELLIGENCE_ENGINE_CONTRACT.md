# FINANCIAL_INTELLIGENCE_ENGINE_CONTRACT.md
**Contrato oficial — Financial Intelligence Engine** · Versión `financial-intelligence-v1` · 2026-06-25 · ESTABLE

> Motor **desacoplado y reutilizable**. Toda la inteligencia financiera del ecosistema (arroba, APIs, Copilots, otros motores) se obtiene **exclusivamente a través de este motor**, nunca leyendo `master_companies` directamente. La **valoración es una capacidad más**, no el motor.

## Arquitectura / frontera
- **Entradas (internas)**: Master Layer (`master_companies`, resumen canónico) + Normalized Layer (`norm_financials`, estados detallados) + `norm_company` (auditado/empleados). El motor es la frontera; los consumidores no acceden a estas colecciones.
- **No depende de**: arroba.com, Copilot, APIs públicas, pantallas. Servicio reutilizable.
- **Determinista, sin IA** en esta fase.

## API (contrato público del motor)
Auth: cabecera `X-API-Key` (service key). 
- `POST /api/v1/financial-intelligence/analyze` — `{identifier}` (master_id|cif) → perfil completo.
- `POST /api/v1/financial-intelligence/valuation` — `{identifier}` → solo valoración (superficie de paridad con el Value Engine legacy).
- `GET  /api/v1/financial-intelligence/ratios/catalog` — librería de ratios (fórmula + explicación + categoría).

## Salida (`/analyze`)
```jsonc
{
  "master_id","cif_normalized",
  "identity": { "name","cnae_code","cnae_section","provincia" },
  "has_financials": true,
  "statements": { "year","basis","income_statement":{…},"balance_sheet":{…},"cashflow":null,"employees" },
  "kpis": { "revenue","ebitda","ebit","net_income","revenue_growth_yoy","ebitda_growth_yoy",
            "revenue_cagr","ebitda_margin","net_margin","roe","roa","solvency","current_ratio",
            "debt_to_equity","revenue_per_employee","capital_intensity" },
  "ratios": { "<key>": { "value","name","category","formula","explanation","source","available" } },
  "evolution": { "trend":"growth|stable|deterioration|insufficient_history","years","anomaly","points":[…] },
  "financial_quality": { "score":0-100,"max":100,"rules":[{rule,points,max,passed}],"method":"rules_based","ai_used":false },
  "comparables": { "criteria":{cnae_section,size_band,geography},"count","peers":[…],
                   "subject_ebitda_margin_percentile","method","embeddings_used":false },
  "valuation": { "method":"ev_ebitda|ev_revenue|book_value|insufficient_data","multiple","multiple_basis":"inferred_reference",
                 "enterprise_value","equity_value","range":{low,high},"confidence","hypotheses":[…],"lineage":{…} },
  "assessment": { "strengths":[…],"weaknesses":[…],"risks":[…] },
  "explainability": { "data_source","source_version","basis","year","rules_applied","ai_used":false },
  "engine_version":"financial-intelligence-v1","generated_at","confidence":0-1
}
```

## Capacidades
- **Estados normalizados**: cuenta de resultados + balance (cashflow N/D en cuentas individuales).
- **KPIs**: crecimiento, CAGR, márgenes (EBITDA/EBIT/neto), rentabilidad (ROA/ROE), solvencia, liquidez, endeudamiento, productividad, intensidad de capital.
- **Ratios**: librería reutilizable (13 ratios), cada uno con fórmula + explicación + categoría + fuente + trazabilidad.
- **Evolución**: tendencia entre ejercicios (crecimiento/deterioro/estable) + detección de anomalías.
- **Financial Quality Score**: 0-100, 100% explicable por reglas (sin IA), con desglose por regla.
- **Comparables financieros**: por sector (sección CNAE) + tamaño + geografía. Sin embeddings.
- **Valoración**: EV/EBITDA → EV/Ingresos → valor en libros → insufficient_data. Consume el Master Layer; múltiplos **inferidos** (documentados como referencia, no de mercado); hipótesis + confianza + linaje explícitos.

## Explicabilidad
Toda salida indica origen del dato, fecha/ejercicio, fuente, base (individual/consolidado), reglas aplicadas y nivel de confianza. `ai_used:false`.

## Versionado y compatibilidad
- `engine_version` = `financial-intelligence-v1`. Adiciones de campos = compatibles; cambios incompatibles ⇒ versión mayor con convivencia.
- Múltiplos `multiple_basis:"inferred_reference"` hasta conectar múltiplos reales (BME/transacciones) — se actualizará sin romper el contrato.

## Migración controlada (Value Engine legacy)
Los contratos públicos actuales (`/api/v1/skills/value`) se mantienen este sprint. Migración: (1) validación de paridad → (2) sustitución del Value Engine legacy por este motor → (3) retirada progresiva de dependencias de `companies_master`.
