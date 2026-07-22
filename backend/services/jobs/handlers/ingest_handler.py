"""Ingest handler — first registered job handler. Wraps the P0.7 ingestion with
per-file checkpointing so the job resumes exactly where it stopped.

The JobRunner stays generic; this is the only place that knows about ingestion.
"""

import os
from typing import Dict

from services.data_layer.ingestion.iberinform_ingest import (
    ensure_indexes, list_ingestable, ingest_file,
)


async def run_ingest(ctx) -> Dict:
    directory = ctx.params["directory"]
    source_version = ctx.params.get("source_version") or \
        os.path.basename(directory.rstrip("/")).split("_")[0]
    ingestion_job_id = ctx.params.get("ingestion_job_id") or ctx.job_id

    await ensure_indexes()
    files = list_ingestable(directory)
    done = set(ctx.checkpoint.get("completed_files", []))
    results = ctx.checkpoint.get("results", [])
    total = len(files)
    processed = len(done)

    await ctx.heartbeat(progress={"processed": processed, "failed": 0,
                                  "total_estimated": total, "message": "starting"})

    for fname in files:
        if fname in done:
            continue
        if await ctx.should_cancel():
            break
        r = await ingest_file(os.path.join(directory, fname), source_version, ingestion_job_id)
        results.append(r)
        done.add(fname)
        processed += 1
        await ctx.heartbeat(
            progress={"processed": processed, "failed": 0, "total_estimated": total, "message": fname},
            checkpoint={"completed_files": sorted(done), "results": results})

    return {"ingestion_job_id": ingestion_job_id, "source_version": source_version,
            "files": results, "files_done": len(done), "files_total": total}
