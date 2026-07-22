"""Capture real runtime JSON of every public engine endpoint (v1 + v2 company).

Writes /app/backend/tools/runtime_samples.json: {endpoint_key: {status, keys, sample}}.
Used to author faithful response DTOs and the contract<->runtime validation matrix.
"""
import json
import os
import requests

BASE = "http://localhost:8001"
KEY = os.environ.get("ARROBA_SERVICE_API_KEY")
H = {"X-API-Key": KEY, "Content-Type": "application/json"}
IDENT = "mc_457c000acfd3"

samples = {}


def rec(name, method, path, body=None):
    url = BASE + path
    try:
        if method == "GET":
            r = requests.get(url, headers=H, timeout=60)
        else:
            r = requests.post(url, headers=H, json=body or {}, timeout=90)
        data = r.json() if r.content else None
    except Exception as e:
        samples[name] = {"status": "ERR", "error": str(e), "path": path, "method": method}
        return None
    samples[name] = {"status": r.status_code, "path": path, "method": method,
                     "body": body, "sample": data}
    return data


# Financial
rec("financial.analyze", "POST", "/api/v1/financial-intelligence/analyze", {"identifier": IDENT})
rec("financial.valuation", "POST", "/api/v1/financial-intelligence/valuation", {"identifier": IDENT})
rec("financial.ratios_catalog", "GET", "/api/v1/financial-intelligence/ratios/catalog")

# Signal
rec("signal.analyze", "POST", "/api/v1/signal-intelligence/analyze", {"identifier": IDENT})
rec("signal.sector", "POST", "/api/v1/signal-intelligence/sector", {"cnae_section": "H", "limit": 5})
rec("signal.territory", "POST", "/api/v1/signal-intelligence/territory", {"provincia": "Barcelona", "limit": 5})
rec("signal.opportunities", "POST", "/api/v1/signal-intelligence/opportunities", {"limit": 5})
rec("signal.catalog", "GET", "/api/v1/signal-intelligence/catalog")
rec("signal.history", "POST", "/api/v1/signal-intelligence/history", {"identifier": IDENT})

# Semantic
rec("semantic.profile", "POST", "/api/v1/semantic-intelligence/profile", {"identifier": IDENT})
rec("semantic.embedding", "POST", "/api/v1/semantic-intelligence/embedding", {"identifier": IDENT})
rec("semantic.similar", "POST", "/api/v1/semantic-intelligence/similar", {"identifier": IDENT, "limit": 5})
rec("semantic.search", "POST", "/api/v1/semantic-intelligence/search", {"query": "transporte", "limit": 5})
rec("semantic.profile_schema", "GET", "/api/v1/semantic-intelligence/profile/schema")
rec("semantic.catalog", "GET", "/api/v1/semantic-intelligence/catalog")

# Recommendation
rec("recommendation.comparables", "POST", "/api/v1/recommendation-intelligence/comparables", {"identifier": IDENT, "limit": 5})
rec("recommendation.buyers", "POST", "/api/v1/recommendation-intelligence/buyers", {"identifier": IDENT, "limit": 5})
rec("recommendation.sellers", "POST", "/api/v1/recommendation-intelligence/sellers", {"identifier": IDENT, "limit": 5})
rec("recommendation.opportunities", "POST", "/api/v1/recommendation-intelligence/opportunities", {"identifier": IDENT, "limit": 5})
rec("recommendation.investors", "POST", "/api/v1/recommendation-intelligence/investors", {"identifier": IDENT})
rec("recommendation.advisors", "POST", "/api/v1/recommendation-intelligence/advisors", {"identifier": IDENT})
rec("recommendation.matching", "POST", "/api/v1/recommendation-intelligence/matching", {"a": IDENT, "b": IDENT})
rec("recommendation.memory", "POST", "/api/v1/recommendation-intelligence/memory", {"target": IDENT})
rec("recommendation.catalog", "GET", "/api/v1/recommendation-intelligence/catalog")

# comparables to grab candidate for explain
comp = samples.get("recommendation.comparables", {}).get("sample") or {}
cand = None
for k in ("recommendations", "comparables", "results"):
    lst = comp.get(k) if isinstance(comp, dict) else None
    if lst:
        cand = (lst[0].get("master_id") or lst[0].get("candidate")) if isinstance(lst[0], dict) else None
        break
if cand:
    rec("recommendation.explain", "POST", "/api/v1/recommendation-intelligence/explain",
        {"target": IDENT, "candidate": cand})
rec("recommendation.feedback", "POST", "/api/v1/recommendation-intelligence/feedback",
    {"recommendation_id": "nonexistent", "event": "viewed"})

# Strategy
rec("strategy.thesis", "POST", "/api/v1/strategy-intelligence/thesis", {"identifier": IDENT})
rec("strategy.scenarios", "POST", "/api/v1/strategy-intelligence/scenarios", {"identifier": IDENT})
rec("strategy.growth", "POST", "/api/v1/strategy-intelligence/growth", {"identifier": IDENT})
rec("strategy.acquisition", "POST", "/api/v1/strategy-intelligence/acquisition", {"identifier": IDENT})
rec("strategy.divestment", "POST", "/api/v1/strategy-intelligence/divestment", {"identifier": IDENT})
rec("strategy.partnership", "POST", "/api/v1/strategy-intelligence/partnership", {"identifier": IDENT})
rec("strategy.capital", "POST", "/api/v1/strategy-intelligence/capital", {"identifier": IDENT})
rec("strategy.risk", "POST", "/api/v1/strategy-intelligence/risk", {"identifier": IDENT})
rec("strategy.decision", "POST", "/api/v1/strategy-intelligence/decision", {"identifier": IDENT, "type_a": "growth", "type_b": "acquisition"})
rec("strategy.memory", "POST", "/api/v1/strategy-intelligence/memory", {"company_master_id": IDENT})
rec("strategy.catalog", "GET", "/api/v1/strategy-intelligence/catalog")

# grab thesis_id
th = samples.get("strategy.thesis", {}).get("sample") or {}
thesis_id = th.get("thesis_id") if isinstance(th, dict) else None
if thesis_id:
    rec("strategy.lifecycle", "POST", "/api/v1/strategy-intelligence/lifecycle",
        {"thesis_id": thesis_id, "state": "validated"})

# Transaction — need to create a transaction from thesis
tx_catalog = rec("transaction.catalog", "GET", "/api/v1/transaction-intelligence/catalog")
wf = None
if isinstance(tx_catalog, dict):
    tmpls = tx_catalog.get("workflow_templates") or []
    wf = tmpls[0] if tmpls else None
tx_id = None
if thesis_id and wf:
    created = rec("transaction.transaction_create", "POST", "/api/v1/transaction-intelligence/transaction",
                  {"thesis_id": thesis_id, "workflow_name": wf})
    if isinstance(created, dict):
        tx = created.get("transaction") or {}
        tx_id = tx.get("transaction_id") or created.get("transaction_id")
if tx_id:
    rec("transaction.transaction", "POST", "/api/v1/transaction-intelligence/transaction", {"transaction_id": tx_id})
    rec("transaction.workflow", "POST", "/api/v1/transaction-intelligence/workflow", {"transaction_id": tx_id})
    rec("transaction.stage", "POST", "/api/v1/transaction-intelligence/stage", {"transaction_id": tx_id})
    rec("transaction.task", "POST", "/api/v1/transaction-intelligence/task", {"transaction_id": tx_id})
    rec("transaction.next_action", "POST", "/api/v1/transaction-intelligence/next-action", {"transaction_id": tx_id})
    rec("transaction.risk", "POST", "/api/v1/transaction-intelligence/risk", {"transaction_id": tx_id})
    rec("transaction.documents", "POST", "/api/v1/transaction-intelligence/documents", {"transaction_id": tx_id})
    rec("transaction.participants", "POST", "/api/v1/transaction-intelligence/participants", {"transaction_id": tx_id})
    rec("transaction.timeline", "POST", "/api/v1/transaction-intelligence/timeline", {"transaction_id": tx_id})
    rec("transaction.decision", "POST", "/api/v1/transaction-intelligence/decision", {"transaction_id": tx_id})
    rec("transaction.memory", "POST", "/api/v1/transaction-intelligence/memory", {"transaction_id": tx_id})
    rec("transaction.workspace", "POST", "/api/v1/transaction-intelligence/workspace", {"transaction_id": tx_id})
else:
    rec("transaction.workflow_template", "POST", "/api/v1/transaction-intelligence/workflow", {"workflow_name": wf})

# V2 Company
rec("company.identity", "POST", "/api/v2/company-intelligence/identity", {"identifier": IDENT})

out = "/app/backend/tools/runtime_samples.json"
with open(out, "w") as f:
    json.dump(samples, f, indent=1, default=str)

print("captured", len(samples), "endpoints ->", out)
for k, v in samples.items():
    st = v.get("status")
    keys = list(v["sample"].keys()) if isinstance(v.get("sample"), dict) else type(v.get("sample")).__name__
    print(f"  {st}  {k}: {keys}")
