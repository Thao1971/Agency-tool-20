"""Contract <-> runtime validation matrix for arroba.v2 typed DTOs.

For every captured 200 runtime sample, compares the documented response DTO against the real
runtime payload: (1) undocumented top-level fields present at runtime, (2) required documented
fields missing at runtime, (3) pydantic type validation. Emits MATCH / MISMATCH. Does NOT fix.
"""
import json
import pydantic

from routes import engine_schemas as S
from routes.company_intelligence import CompanyIdentityResponse

SAMPLES = json.load(open("/app/backend/tools/runtime_samples.json"))

MAP = {
    "financial.analyze": S.FinancialAnalyzeResponse,
    "financial.valuation": S.FinancialValuationResponse,
    "financial.ratios_catalog": S.RatiosCatalogResponse,
    "signal.analyze": S.SignalAnalyzeResponse,
    "signal.sector": S.SignalAggregateResponse,
    "signal.territory": S.SignalAggregateResponse,
    "signal.opportunities": S.SignalOpportunitiesResponse,
    "signal.catalog": S.SignalCatalogResponse,
    "signal.history": S.SignalHistoryResponse,
    "semantic.profile": S.SemanticProfileResponse,
    "semantic.embedding": S.SemanticEmbeddingResponse,
    "semantic.similar": S.SemanticSimilarResponse,
    "semantic.search": S.SemanticSearchResponse,
    "semantic.profile_schema": S.SemanticProfileSchemaResponse,
    "semantic.catalog": S.SemanticCatalogResponse,
    "recommendation.comparables": S.RecommendationSetResponse,
    "recommendation.buyers": S.RecommendationSetResponse,
    "recommendation.sellers": S.RecommendationSetResponse,
    "recommendation.opportunities": S.RecommendationSetResponse,
    "recommendation.investors": S.RecommendationUnavailableResponse,
    "recommendation.advisors": S.RecommendationUnavailableResponse,
    "recommendation.matching": S.RecommendationMatchingResponse,
    "recommendation.memory": S.RecommendationMemoryResponse,
    "recommendation.explain": S.RecommendationExplainResponse,
    "recommendation.catalog": S.RecommendationCatalogResponse,
    "strategy.thesis": S.StrategyThesisResponse,
    "strategy.scenarios": S.StrategyScenariosResponse,
    "strategy.growth": S.StrategyThesisResponse,
    "strategy.acquisition": S.StrategyThesisResponse,
    "strategy.divestment": S.StrategyThesisResponse,
    "strategy.partnership": S.StrategyThesisResponse,
    "strategy.capital": S.StrategyThesisResponse,
    "strategy.risk": S.StrategyThesisResponse,
    "strategy.decision": S.StrategyDecisionResponse,
    "strategy.memory": S.StrategyMemoryResponse,
    "strategy.lifecycle": S.StrategyThesisResponse,
    "strategy.catalog": S.StrategyCatalogResponse,
    "transaction.catalog": S.TransactionCatalogResponse,
    "transaction.transaction": S.TransactionEndpointResponse,
    "transaction.transaction_create": S.TransactionEndpointResponse,
    "transaction.workflow": S.WorkflowResponse,
    "transaction.workflow_template": S.WorkflowResponse,
    "transaction.stage": S.StageResponse,
    "transaction.task": S.TaskResponse,
    "transaction.next_action": S.NextActionResponse,
    "transaction.risk": S.TransactionRiskResponse,
    "transaction.documents": S.DocumentsResponse,
    "transaction.participants": S.ParticipantsResponse,
    "transaction.timeline": S.TimelineResponse,
    "transaction.decision": S.TransactionDecisionResponse,
    "transaction.memory": S.TransactionMemoryResponse,
    "transaction.workspace": S.WorkspaceResponse,
    "company.identity": CompanyIdentityResponse,
}


def declared_names(model):
    names = set()
    for fname, f in model.model_fields.items():
        names.add(f.alias or fname)
        names.add(fname)
    return names


rows = []
for key in sorted(MAP):
    model = MAP[key]
    s = SAMPLES.get(key)
    if not s:
        rows.append((key, model.__name__, "NO_SAMPLE", "endpoint not captured", []))
        continue
    if s.get("status") != 200 or not isinstance(s.get("sample"), dict):
        rows.append((key, model.__name__, "NO_200_SAMPLE", f"status={s.get('status')}", []))
        continue
    sample = s["sample"]
    decl = declared_names(model)
    runtime_fields = set(sample.keys())
    undocumented = sorted(runtime_fields - decl)
    required_missing = sorted(
        (f.alias or n) for n, f in model.model_fields.items()
        if f.is_required() and (f.alias or n) not in runtime_fields and n not in runtime_fields
    )
    try:
        model.model_validate(sample)
        type_ok = True
        type_err = ""
    except pydantic.ValidationError as e:
        type_ok = False
        type_err = "; ".join(f"{'.'.join(str(x) for x in er['loc'])}: {er['type']}" for er in e.errors()[:6])
    problems = []
    if undocumented:
        problems.append(f"undocumented_fields={undocumented}")
    if required_missing:
        problems.append(f"required_missing={required_missing}")
    if not type_ok:
        problems.append(f"type_errors[{type_err}]")
    result = "MATCH" if not problems else "MISMATCH"
    rows.append((key, model.__name__, result, "; ".join(problems) if problems else "-",
                 sorted(decl)))

# Print matrix
matches = sum(1 for r in rows if r[2] == "MATCH")
mismatches = [r for r in rows if r[2] == "MISMATCH"]
print(f"\n{'ENDPOINT':38} {'DTO':34} {'RESULT'}")
print("-" * 100)
for key, dto, res, detail, _ in rows:
    print(f"{key:38} {dto:34} {res}")
    if detail != "-":
        print(f"    -> {detail}")
print("-" * 100)
print(f"TOTAL: {len(rows)}  MATCH: {matches}  MISMATCH: {len(mismatches)}  "
      f"OTHER: {len(rows)-matches-len(mismatches)}")

json.dump([{"endpoint": r[0], "dto": r[1], "result": r[2], "detail": r[3]} for r in rows],
          open("/app/backend/tools/validation_matrix.json", "w"), indent=1)
