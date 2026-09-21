"""Resolve latest observed ECB and public-comparable inputs from Intel storage."""
from __future__ import annotations
from .wacc import MARKET_SNAPSHOT, beta_from_comparables

async def resolve_market_inputs(db, archetype: str):
    market={key:(dict(value) if isinstance(value,dict) else value)
            for key,value in MARKET_SNAPSHOT.items()}
    ecb=await db.valuation_market_snapshots.find_one(
        {"series_key":"YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"},
        {"_id":0},sort=[("observation_date",-1)])
    if ecb:
        market["as_of"]=ecb["observation_date"]
        market["risk_free_rate"]={"value":ecb["value"],"source":"ECB",
                                  "status":"observed","series_key":ecb["series_key"],
                                  "observation_date":ecb["observation_date"],
                                  "source_url":ecb.get("source_url")}
    peers=await db.valuation_public_comparables.find(
        {"archetype":archetype,"active":True,"quality.beta_ready":True},{"_id":0}).to_list(500)
    return market,beta_from_comparables(peers),peers
