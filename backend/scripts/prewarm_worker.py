"""Worker de precalentamiento de descripciones IA en segundo plano.

- Resumable: salta lo ya cacheado (usa `_candidates`, que excluye lo generado).
- Tope de tiempo configurable (por defecto 12h) persistido en disco, sobrevive a
  reinicios del pod (supervisor lo relanza y reanuda hasta agotar el deadline).
- Robusto ante caídas de NVIDIA: backoff en vez de morir; captura excepciones por empresa.
- Escribe progreso legible a disco para revisar al final sin estar pendiente.

Gestionado por supervisor: autostart, autorestart=unexpected, exitcodes=0.
Estado:    /app/backend/prewarm_state.json
Progreso:  /app/backend/prewarm_progress.json
Log:       /app/backend/prewarm_worker.log
"""
import asyncio
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from database import db
from services.company_summary import resolve_description
from services.cnae_es import cnae_label_es
from scripts.prewarm_company_descriptions import _candidates
from docstudio.model_provider import (COMPANY_DESCRIPTION_PROMPT_VERSION,
                                      NVIDIA_FALLBACK_MODEL)

BASE = Path(__file__).resolve().parents[1]
STATE = BASE / "prewarm_state.json"
PROGRESS = BASE / "prewarm_progress.json"
LOG = BASE / "prewarm_worker.log"

RUN_HOURS = float(os.environ.get("PREWARM_RUN_HOURS", "12"))
DELAY = float(os.environ.get("PREWARM_DELAY", "2"))
CHUNK = int(os.environ.get("PREWARM_CHUNK", "200"))
SEED = int(os.environ.get("PREWARM_SEED", "150926"))
OUTAGE_SLEEP = 60      # segundos de backoff cuando NVIDIA parece caído
OUTAGE_EVERY = 8       # cada N fallos seguidos, aplica backoff


def _now():
    return time.time()


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    try:
        with LOG.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            return None
    return None


def save_state(st):
    STATE.write_text(json.dumps(st, indent=2))


async def main():
    st = load_state()
    now = _now()
    if not st:
        st = {"started_at": now, "deadline": now + RUN_HOURS * 3600,
              "done": False, "started_iso": datetime.now(timezone.utc).isoformat()}
        save_state(st)
        log(f"NUEVO run de precalentamiento: deadline en {RUN_HOURS}h")
    else:
        log(f"REANUDANDO run (iniciado {st.get('started_iso')}); "
            f"horas_restantes={(st['deadline'] - now) / 3600:.1f} done={st.get('done')}")

    if st.get("done"):
        log("Run marcado como DONE; nada que hacer. Exit 0.")
        return 0
    if now >= st["deadline"]:
        st["done"] = True
        save_state(st)
        log("Deadline alcanzado. Marcando DONE. Exit 0.")
        return 0
    if not os.environ.get("NVIDIA_API_KEY"):
        st["done"] = True
        save_state(st)
        log("ERROR: NVIDIA_API_KEY no configurada. Exit 0 (sin reintentos).")
        return 0
    model = os.environ.get("NVIDIA_DESC_MODEL")
    if not model or model == NVIDIA_FALLBACK_MODEL:
        st["done"] = True
        save_state(st)
        log("ERROR: NVIDIA_DESC_MODEL no configurado con un modelo probado. Exit 0.")
        return 0
    log(f"Config: primario={model} fallback={os.environ.get('NVIDIA_MODEL_FALLBACK')} "
        f"delay={DELAY}s chunk={CHUNK}")

    prog = {}
    if PROGRESS.exists():
        try:
            prog = json.loads(PROGRESS.read_text())
        except Exception:
            prog = {}
    ok = int(prog.get("generadas", 0))
    fail = int(prog.get("fallidas", 0))
    models = Counter(prog.get("reparto_por_modelo", {}))
    fb_count = int(prog.get("fallback_used", 0))
    motivos = Counter(prog.get("motivos_fallo", {}))
    failed_ids = set()   # no reintentar la misma empresa dentro de este proceso

    def flush(last_cif=None, total_cache=None):
        data = {
            "started_iso": st.get("started_iso"),
            "updated_iso": datetime.now(timezone.utc).isoformat(),
            "deadline_iso": datetime.fromtimestamp(st["deadline"], timezone.utc).isoformat(),
            "horas_restantes": round((st["deadline"] - _now()) / 3600, 2),
            "done": st.get("done", False),
            "generadas": ok, "fallidas": fail,
            "reparto_por_modelo": dict(models), "fallback_used": fb_count,
            "motivos_fallo": dict(motivos),
            "ultimo_cif": last_cif,
        }
        if total_cache is not None:
            data["total_cache"] = total_cache
        PROGRESS.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    consecutive = 0
    flush()
    while _now() < st["deadline"]:
        pending = await _candidates(SEED, [])
        pending = [r for r in pending if r["master_id"] not in failed_ids]
        if not pending:
            st["done"] = True
            save_state(st)
            log("Universo pendiente agotado en este run. DONE.")
            break
        log(f"Chunk nuevo: pendientes(sin fallidos-de-este-run)={len(pending)} procesando <= {CHUNK}")
        for row in pending[:CHUNK]:
            if _now() >= st["deadline"]:
                break
            mid = row["master_id"]
            cif = row.get("cif_normalized")
            try:
                objeto = (row.get("objeto_social") or "").strip()
                wd = row.get("web_description")
                web_text = wd.get("description") if isinstance(wd, dict) else wd
                identity = {"objeto_social": objeto, "description": web_text,
                            "legal_name": (row.get("identity") or {}).get("legal_name")}
                cnae = cnae_label_es((row.get("classification") or {}).get("cnae_code"))
                t = _now()
                res = await resolve_description(mid, identity, cnae, generate_if_missing=True)
                dur = _now() - t
                if res.get("description_source") == "ai":
                    ok += 1
                    consecutive = 0
                    doc = await db.company_descriptions.find_one(
                        {"master_id": mid, "prompt_version": COMPANY_DESCRIPTION_PROMPT_VERSION},
                        {"_id": 0, "model": 1, "fallback_used": 1}) or {}
                    m = doc.get("model")
                    models[m] += 1
                    if doc.get("fallback_used"):
                        fb_count += 1
                    log(f"OK cif={cif} model={m} fb={doc.get('fallback_used')} "
                        f"dur={dur:.1f} ok={ok} fail={fail}")
                else:
                    fail += 1
                    consecutive += 1
                    failed_ids.add(mid)
                    motivos[res.get("description_source") or "none"] += 1
                    log(f"FAIL cif={cif} source={res.get('description_source')} "
                        f"dur={dur:.1f} ok={ok} fail={fail} consec={consecutive}")
            except Exception as e:
                fail += 1
                consecutive += 1
                failed_ids.add(mid)
                motivos["exception"] += 1
                log(f"EXC cif={cif} {type(e).__name__}: {e} consec={consecutive}")
            flush(cif)
            if consecutive and consecutive % OUTAGE_EVERY == 0:
                log(f"{consecutive} fallos seguidos: backoff {OUTAGE_SLEEP}s (posible caída NVIDIA)")
                slept = 0
                while slept < OUTAGE_SLEEP and _now() < st["deadline"]:
                    await asyncio.sleep(min(5, OUTAGE_SLEEP - slept))
                    slept += 5
            elif _now() < st["deadline"]:
                await asyncio.sleep(DELAY)

    if _now() >= st["deadline"] and not st.get("done"):
        st["done"] = True
        save_state(st)
        log("Deadline de tiempo alcanzado durante el proceso. DONE.")
    total = await db.company_descriptions.count_documents({})
    flush(total_cache=total)
    log(f"FIN ciclo. generadas={ok} fallidas={fail} total_cache={total} "
        f"reparto={dict(models)} fb={fb_count} motivos={dict(motivos)}")
    return 0


if __name__ == "__main__":
    code = asyncio.run(main())
    raise SystemExit(code or 0)
