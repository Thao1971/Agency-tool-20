"""Re-embed all `semantic_profiles` with the active OpenAI provider (text-embedding-3-small).

Idempotent: re-run safely. By default only re-embeds docs NOT already on the active model;
pass --force to re-embed everything. Vectors are L2-normalized before storage.

Usage:
    python scripts/reembed_semantic_openai.py [--force]
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, "/app/backend")

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

from services.engines.semantic import embeddings as E
from services.engines.semantic import profile as PB
from models import now_iso

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
BATCH = 128
FORCE = "--force" in sys.argv

_MASTER_PROJ = {"_id": 0, "master_id": 1, "objeto_social": 1, "classification": 1,
                "size": 1, "identity": 1}


def _emb_text(master, fallback_name):
    if master:
        prof = PB.build_rules_profile(master, None, None)
        t = PB.embedding_text(prof).strip()
        if t:
            return t
    return (fallback_name or "").strip() or " "


async def _embed_with_retry(prov, texts, attempts=4):
    delay = 2.0
    for a in range(attempts):
        try:
            return await asyncio.to_thread(prov.embed_many, texts)
        except Exception as exc:  # rate limit / transient
            if a == attempts - 1:
                raise
            print(f"  retry {a + 1} after error: {exc.__class__.__name__} (sleep {delay}s)")
            await asyncio.sleep(delay)
            delay *= 2


async def main():
    prov = E.get_provider()
    if prov.name != "openai":
        print("ERROR: active embedding provider is not 'openai' (OPENAI_API_KEY missing?)")
        return
    model = prov.model
    q = {} if FORCE else {"embedding.model": {"$ne": model}}
    profiles = await db.semantic_profiles.find(
        q, {"_id": 0, "master_id": 1, "cnae_section": 1, "cif_normalized": 1,
            "identity_name": 1}).to_list(None)
    total = len(profiles)
    print(f"[reembed] provider={prov.name} model={model} dim={prov.dim} "
          f"to_process={total} force={FORCE}")
    if not total:
        print("[reembed] nothing to do.")
        return

    done = 0
    t0 = time.time()
    for i in range(0, total, BATCH):
        chunk = profiles[i:i + BATCH]
        ids = [p["master_id"] for p in chunk]
        masters = {}
        async for m in db.master_companies.find({"master_id": {"$in": ids}}, _MASTER_PROJ):
            masters[m["master_id"]] = m
        texts = [_emb_text(masters.get(p["master_id"]), p.get("identity_name")) for p in chunk]
        vectors = await _embed_with_retry(prov, texts)

        ops = []
        for p, vec in zip(chunk, vectors):
            ops.append(UpdateOne(
                {"master_id": p["master_id"]},
                {"$set": {
                    "embedding": {
                        "vector": vec, "provider": prov.name, "model": model,
                        "dimension": prov.dim, "embedding_version": prov.embedding_version,
                        "sources": PB.EMBEDDING_SOURCES, "generated_at": now_iso(),
                    },
                    "updated_at": now_iso(),
                }},
            ))
        if ops:
            await db.semantic_profiles.bulk_write(ops, ordered=False)
        done += len(chunk)
        rate = done / max(time.time() - t0, 0.001)
        print(f"[reembed] {done}/{total} ({rate:.0f}/s)")

    print(f"[reembed] DONE {done} profiles in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
