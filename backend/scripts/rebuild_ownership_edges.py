"""One-off: repopulate master_relationships from norm_ownership with the new
counterparty_key so external counterparties no longer collapse (34-vs-1 gap)."""
import asyncio
from services.data_layer.master.ownership_graph import rebuild_ownership_graph


async def main():
    stats = await rebuild_ownership_graph()
    print("REBUILD_STATS:", stats)


if __name__ == "__main__":
    asyncio.run(main())
