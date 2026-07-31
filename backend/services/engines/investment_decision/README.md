# Investment Decision Engine (`investment-decision-engine-v1`)

Comité de Inversiones como Intelligence Engine. **Consumer engine**: reutiliza los motores
existentes (no recrea), puntúa de forma determinista por especialista y construye un consenso
explicable con vetos. Ver `memory/INVESTMENT_DECISION_ENGINE_CONSTITUTION.md` (modelo de decisión)
y `..._DESIGN.md` (diseño técnico).

## Estado — Fase 2 (comité completo)
- Núcleo completo y determinista: modelos, scoring (config validada), evidencia, consenso, engine, API.
- **Los 10 especialistas implementados** y activos: CFO, Valuation, Strategy, Market, Commercial,
  Operations, HR, Legal (veto), Risk (veto), Investment Director. Cada uno se abstiene si no tiene
  datos (regla dura: sin evidencia ⇒ abstención). La evidencia se enriquece con fragmentación (HHI) y
  propiedad (cap table) además del bundle de `company_intelligence`.
- IA narrativa: **diferida a Fase 6**; hoy el `executive_summary`/`thesis` son plantilla reglada.

## Uso
```python
from services.engines.investment_decision import analyze
result = await analyze({"opportunity_id": "...", "company_id"|"cif": "...",
                        "buyer_profile": {"type": "private_equity"}, "inputs": {}})
```

## API (auth service-key)
- `GET  /api/v1/investment-decision/health`
- `POST /api/v1/investment-decision/analyze`   → ConsensusResult
- `POST /api/v1/investment-decision/committee`  → solo opiniones
- `GET  /api/v1/investment-decision/decision/{id}`
- `POST /api/v1/investment-decision/compare`    → ranking + matriz comité×oportunidad
- `POST /api/v1/investment-decision/portfolio`  → score agregado + diversificación + flags
- `POST /api/v1/investment-decision/recommendations` → oportunidades rankeadas por mandato
- `POST /api/v1/investment-decision/decision/{id}/ask` → Copilot Q&A fact-lock
- `GET  /api/v1/investment-decision/decision/{id}/export-payload` → estructura render-ready (sin binario)

## Cómo recalibrar / extender
- Pesos, bandas y moduladores por perfil: `scoring.py` (config versionada; no tocar lógica).
- Nuevo especialista: crear `committee/<x>.py` (subclase de `Specialist`), registrarlo en
  `committee/__init__.py`. Debe devolver `models.opinion(...)` con evidencia; si no hay datos → `abstain`.

## Próximas fases
2 especialistas restantes · 3 consenso avanzado · 4 confianza/explainability · 5 API+persistencia
· 6 IA narrativa fact-lock · 7 perfiles · 8 capacidades (compare/portfolio/recommend/copilot/export)
· 9 hardening. El render PDF/Word y la UI/React quedan FUERA de este módulo.
