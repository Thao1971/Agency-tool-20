"""Master Layer job handlers (Sprint 1). Run on the generic JobRunner infra."""

from typing import Dict

from services.data_layer.master.master_builder import rebuild_master
from services.data_layer.master.ownership_graph import rebuild_ownership_graph


async def run_rebuild_master(ctx) -> Dict:
    scope = ctx.params.get("scope", "full")
    cif_list = ctx.params.get("cif_list")
    force = bool(ctx.params.get("force"))

    async def hb(progress):
        await ctx.heartbeat(progress=progress)

    return await rebuild_master(scope=scope, cif_list=cif_list, force=force, heartbeat=hb)


async def run_rebuild_ownership_graph(ctx) -> Dict:
    async def hb(progress):
        await ctx.heartbeat(progress=progress)
    return await rebuild_ownership_graph(heartbeat=hb)
