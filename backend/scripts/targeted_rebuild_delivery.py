"""Rebuild DIRIGIDO de señales + semántico SOLO para las empresas nuevas/modificadas de una
entrega Iberinform (las que llevan `sources.source_version == RUN_ID`).

Motivo: el worker de entregas (run_delivery_worker) recomputa señales+semántico de TODO el
universo (25.603) una a una contra Atlas (~0,5/s → ~24-30 h). Para una entrega incremental de
~1.000 empresas eso es innecesario: las 25k existentes ya tienen señales/embeddings de despliegues
previos. Este script:
  1. Captura la config de Atlas (MONGO_URL/DB_NAME/OPENAI_API_KEY) del proceso worker en curso.
  2. Para el worker (SIGTERM→SIGKILL) para detener el recompute completo.
  3. Recomputa señales + perfil semántico + embedding SOLO de las empresas de la entrega.
  4. Marca el run como completado (data + targeted intelligence) en iberinform_delivery_runs.

NUNCA imprime la URI de Atlas. Uso:
  python -m scripts.targeted_rebuild_delivery --worker-pid <pid> --run-id <run_id>
"""
import argparse
import os
import signal
import sys
import time
from pathlib import Path


def _read_worker_env(pid: str) -> dict:
    env = {}
    with open(f"/proc/{pid}/environ", "rb") as f:
        for chunk in f.read().split(b"\x00"):
            if b"=" in chunk:
                k, _, v = chunk.partition(b"=")
                env[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
    return env


def _kill_worker(pid: int) -> str:
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode()
    except FileNotFoundError:
        return "worker already gone"
    if "run_delivery_worker" not in cmd:
        return f"REFUSING to kill pid {pid}: not the delivery worker (cmd={cmd!r})"
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return "worker stopped (SIGTERM)"
        os.kill(pid, signal.SIGKILL)
        return "worker stopped (SIGKILL)"
    except ProcessLookupError:
        return "worker already gone"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-pid", required=True)
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    wenv = _read_worker_env(args.worker_pid)
    mongo_url = wenv.get("MONGO_URL")
    db_name = wenv.get("DB_NAME")
    if not mongo_url or not db_name:
        print("FATAL: worker env has no MONGO_URL/DB_NAME", flush=True)
        sys.exit(2)
    is_atlas = mongo_url.startswith("mongodb+srv://") or "mongodb.net" in mongo_url
    print(f"captured worker config: target_is_atlas={is_atlas} db_name={db_name}", flush=True)

    # Config de Atlas ANTES de importar database (load_dotenv usa override=False → no la pisa).
    os.environ["MONGO_URL"] = mongo_url
    os.environ["DB_NAME"] = db_name
    for k in ("OPENAI_API_KEY",):
        if wenv.get(k):
            os.environ[k] = wenv[k]

    # 2) parar el worker (recompute completo)
    print("kill worker:", _kill_worker(int(args.worker_pid)), flush=True)

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import asyncio
    from database import db
    from models import now_iso
    from services.engines.signal import engine as sig_engine
    from services.engines.semantic import engine as sem_engine

    run_id = args.run_id

    async def _run():
        t0 = time.time()
        ids = await db.master_companies.distinct("master_id", {"sources.source_version": run_id})
        n = len(ids)
        print(f"target companies (sources.source_version=={run_id}): {n}", flush=True)
        await db.iberinform_delivery_runs.update_one(
            {"run_id": run_id},
            {"$set": {"targeted_rebuild": {"status": "running", "targets": n,
                                           "started_at": now_iso()}}}, upsert=True)

        sig_ok = sig_err = 0
        for i, mid in enumerate(ids, 1):
            try:
                await sig_engine.analyze(mid, persist=True)
                sig_ok += 1
            except Exception as e:  # noqa: BLE001
                sig_err += 1
                if sig_err <= 5:
                    print(f"  sig err {mid}: {e}", flush=True)
            if i % 100 == 0:
                dt = time.time() - t0
                print(f"  signals {i}/{n} ok={sig_ok} err={sig_err} ({i/dt:.2f}/s)", flush=True)
                await db.iberinform_delivery_runs.update_one(
                    {"run_id": run_id},
                    {"$set": {"targeted_rebuild.signals_done": i,
                              "targeted_rebuild.signals_ok": sig_ok}})
        print(f"SIGNALS DONE: ok={sig_ok} err={sig_err} in {time.time()-t0:.0f}s", flush=True)

        t1 = time.time()
        sem_ok = sem_err = sem_emb = 0
        for i, mid in enumerate(ids, 1):
            try:
                r = await sem_engine.build_profile(mid, persist=True)
                sem_ok += 1
                if r and (r.get("embedding") or {}).get("dimension"):
                    sem_emb += 1
            except Exception as e:  # noqa: BLE001
                sem_err += 1
                if sem_err <= 5:
                    print(f"  sem err {mid}: {e}", flush=True)
            if i % 100 == 0:
                dt = time.time() - t1
                print(f"  semantic {i}/{n} ok={sem_ok} emb={sem_emb} err={sem_err} ({i/dt:.2f}/s)", flush=True)
                await db.iberinform_delivery_runs.update_one(
                    {"run_id": run_id},
                    {"$set": {"targeted_rebuild.semantic_done": i,
                              "targeted_rebuild.semantic_emb": sem_emb}})
        print(f"SEMANTIC DONE: ok={sem_ok} emb={sem_emb} err={sem_err} in {time.time()-t1:.0f}s", flush=True)

        await db.iberinform_delivery_runs.update_one(
            {"run_id": run_id},
            {"$set": {"status": "completed_targeted",
                      "finished_at": now_iso(),
                      "targeted_rebuild.status": "completed",
                      "targeted_rebuild.targets": n,
                      "targeted_rebuild.signals_ok": sig_ok,
                      "targeted_rebuild.semantic_ok": sem_ok,
                      "targeted_rebuild.semantic_emb": sem_emb,
                      "targeted_rebuild.duration_s": round(time.time() - t0, 1)}})
        # also mark the modern sub-run so its status isn't stuck at "running"
        await db.bootstrap_runs.update_one(
            {"run_id": f"{run_id}_modern"},
            {"$set": {"status": "stopped_after_data_phases",
                      "note": "signal_builder/semantic_index full-universe recompute stopped; "
                              "replaced by targeted rebuild of delivery companies only"}})
        print(f"ALL DONE in {time.time()-t0:.0f}s (targets={n})", flush=True)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
