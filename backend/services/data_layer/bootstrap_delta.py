"""
services/data_layer/bootstrap_delta.py

Delta-scoped replacement for bootstrap.run_bootstrap_tab() — Fase 3 (modern_ingest)
of the Iberinform delivery pipeline.

WHY THIS EXISTS
----------------
bootstrap.run_bootstrap_tab() is the confirmed 24-30h bottleneck on every delivery,
entirely because two of its steps iterate the FULL 25,603-company universe on every
run, even when a delivery only touches a few hundred/thousand companies:
  - build_signals_canonical()
  - build_semantic_canonical()
Everything else in the real chain (verbatim, bootstrap.py L237-304+, confirmed by
Emergent read-only on 2026-09-14) is either already delta-safe or already cheap:

    ingestion -> master_builder(scope="full", force=True) -> ownership_graph
              -> build_signals_canonical (FULL, bottleneck)
              -> build_semantic_canonical (FULL, bottleneck)
              -> verify -> select_canonical_set

This module reproduces that exact chain but:
  1. keeps `ingestion` unchanged (it must run first — see below),
  2. swaps master_builder's scope from "full" to "incremental",
  3. keeps `ownership_graph` full (cheap: ~2.8k edges today, no incremental path
     exists in the real code either),
  4. scopes the two canonical-build loops to the delivery's delta company set only,
  5. within the semantic loop, adds a checksum pre-check (see step 6's comment
     below) that skips the OpenAI embedding call entirely for companies whose
     rules-based semantic profile hasn't actually changed since last time —
     something the real build_profile() does NOT do on its own (confirmed:
     it re-embeds unconditionally, see semantic/engine.py L82-88),
  6. keeps verify()/select_canonical_set() as in the original (cheap reads + a
     top-N re-rank, not delta-dependent, safe to call unchanged).

CRITICAL FACT THIS DESIGN DEPENDS ON (verified verbatim, not assumed)
------------------------------------------------------------------------
`rebuild_master(scope="incremental")` filters norm_company on {"dirty": True}
(master_builder.py L210-214). That flag is NOT set ahead of time by Fase 1 —
Fase 1 (`process_real_iberinform_tab_directory`, the legacy rail) writes ONLY to
`iberinform_companies` / `iberinform_financials` / `companies_master` and never
touches `norm_company` at all (confirmed via grep, 2026-09-14).

The ONLY thing that stamps `dirty=True` + `source_version=<run_id>` on
`norm_company` is the "ingestion" step INSIDE run_bootstrap_tab itself
(bootstrap.py L254-272, verbatim):

    from services.data_layer.ingestion.iberinform_tab_ingest import (
        ingest_tab_directory, ingest_tab_delivery)
    ...
    ingestion = (ingest_tab_delivery(delivery, source_version=source_version)
                 if delivery is not None
                 else ingest_tab_directory(directory, source_version=source_version))
    await _step(run_id, steps, "ingestion", ingestion)
    await _step(run_id, steps, "master_builder", rebuild_master(scope="full", force=True))

So this wrapper MUST call ingest_tab_directory/ingest_tab_delivery itself, first,
exactly like the original — skipping it would leave nothing `dirty` for
`rebuild_master(scope="incremental")` to pick up. (My first draft of this file
missed this and would have been a silent no-op on every run. Caught before
delivery by asking Emergent for run_bootstrap_tab's real body instead of guessing.)

Because ingestion always (re-)marks exactly this delivery's rows dirty (and
rebuild_master always clears dirty:False on whatever it processes, whether it
skipped a company via the source_hash short-circuit or actually rebuilt it),
`scope="incremental"` after a fresh ingestion IS this delivery's delta — no
separate full-vs-delta mode is needed. On a brand-new DB, ingestion marks
everything dirty, so this degrades naturally to a full run the first time.

TWO SHARP EDGES (confirmed by Emergent, both load-bearing — do not change)
------------------------------------------------------------------------
1. Do NOT pass force=True to rebuild_master here. With force=False (the
   default), a re-delivered company whose data is byte-identical is skipped via
   the source_hash short-circuit (master_builder.py L118) but STILL gets
   dirty:False cleared — exactly the delta behavior we want. force=True would
   defeat that short-circuit and is only appropriate for the original full-scope
   call (which this module intentionally does not replicate).
2. Do NOT combine scope="incremental" with cif_list. In master_builder.py
   (L210-214), `if cif_list:` OVERRIDES the `dirty` filter entirely — passing
   both silently ignores the incremental scoping. This module never sets
   cif_list; keep it that way.

INTEGRATION POINT — scripts/run_delivery_worker.py, Fase 3 (verbatim L67-75 today)
------------------------------------------------------------------------
Current:
    67:        # ── Fase 3 · moderno (master_companies + ratios + ownership + señales + semántico) ──
    68:        from services.data_layer import bootstrap as bootstrap_svc
    69:        if mode == "r2":
    70:            modern = await bootstrap_svc.run_bootstrap_tab(
    71:                run_id=f"{run_id}_modern", source_version=run_id, delivery=delivery)
    72:        else:
    73:            modern = await bootstrap_svc.run_bootstrap_tab(
    74:                directory=data_dir, run_id=f"{run_id}_modern", source_version=run_id)
    75:        steps.append({"step": "modern_ingest", "status": "ok" if modern.get("status") != "failed" else "error", "result": modern})

Replace L67-74 with (L75 stays IDENTICAL — this module's return shape matches
run_bootstrap_tab's closely enough that the existing status check keeps working):
    67:        # ── Fase 3 · moderno (delta-scoped: master_companies + ratios + ownership + señales + semántico) ──
    68:        from services.data_layer import bootstrap_delta
    69:        if mode == "r2":
    70:            modern = await bootstrap_delta.run_bootstrap_delta(
    71:                run_id=f"{run_id}_modern", source_version=run_id, delivery=delivery,
    72:                steps=steps, set_fn=_set)
    73:        else:
    74:            modern = await bootstrap_delta.run_bootstrap_delta(
    75:                directory=data_dir, run_id=f"{run_id}_modern", source_version=run_id,
    76:                steps=steps, set_fn=_set)

Passing the SAME `steps` list and `_set` closure that `_run()` already has in
scope (L37/39) means this module's own sub-steps (ingestion, master_builder,
ownership_graph, signal_builder, semantic_builder, verification, canonical_set)
get appended live into the exact same `iberinform_delivery_runs.steps` array the
"Historial de cargas" panel already reads — no separate bootstrap_runs doc, no
more panel stuck at "En curso" with only 2 steps. Each sub-step is `await
_set({"steps": steps})`'d as it completes, same pattern Fase 1/Fase 2 already use
at L56/65.

Written by Claude, not Emergent, per standing instruction. Emergent's role is
read-only fetches to verify facts (all cited above with line numbers) and,
once Daniel approves this file, mechanically applying it — never designing.
"""

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from services.data_layer import bootstrap as bootstrap_svc
from services.data_layer.ingestion.iberinform_tab_ingest import (
    ingest_tab_directory,
    ingest_tab_delivery,
)
from services.data_layer.master import master_builder
from services.data_layer.master import ownership_graph
from services.engines.signal import engine as sig_engine
from services.engines.semantic import engine as sem_engine

# CONFIRM: import path/module that exposes `db` in this codebase. Every excerpt
# you've pasted uses bare `db.<collection>` inside route/worker/service files —
# adjust this single import if the real module name/path differs.
from database import db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_delta_master_ids(source_version: str) -> List[str]:
    """
    Delta = companies whose CURRENT master doc carries this delivery's
    source_version in sources[].source_version. Same pattern already used
    successfully in the 2026-09 manual "rebuild dirigido".

    Queried AFTER master_builder.rebuild_master() runs, so it reflects any CIFs
    newly resolved to a master_id during that step, not just pre-existing ones.
    """
    cursor = db.master_companies.find(
        {"sources.source_version": source_version, "status": "active"},
        {"master_id": 1},
    )
    return [doc["master_id"] async for doc in cursor]


async def run_bootstrap_delta(
    run_id: str,
    source_version: str,
    directory: Optional[str] = None,
    delivery: Optional[object] = None,
    canonical_n: int = 50,
    steps: Optional[List[Dict]] = None,
    set_fn: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
) -> Dict:
    """
    Delta-scoped drop-in for bootstrap.run_bootstrap_tab(). Same call convention
    (directory=/delivery=/run_id=/source_version=) so the two call sites in
    run_delivery_worker.py's Fase 3 need no other changes than the function name
    and passing `steps`/`set_fn` through.

    steps: the CALLER's existing steps list (e.g. run_delivery_worker.py's own
    `steps`, already carrying legacy_ingest/legacy_intelligence entries). Sub-steps
    from this function are appended into it directly, so the caller's own
    `_set({"steps": steps})` calls (and the final `steps.append({"step":
    "modern_ingest", ...})` at the call site) see them too. If None, a local list
    is used instead (still returned in the result dict under "steps").

    set_fn: async callable taking a patch dict, e.g. run_delivery_worker.py's
    `_set`. Called after every sub-step below so the /data-providers/
    iberinform-delivery panel gets live progress instead of jumping straight from
    "running" to "completed" (this is the fix for the panel getting stuck showing
    only 2 steps while Fase 3 ran).
    """
    local_steps = steps if steps is not None else []

    async def _step(name: str, status: str, result: Optional[Dict] = None) -> None:
        entry: Dict[str, Any] = {"step": f"modern:{name}", "status": status, "at": _now_iso()}
        if result is not None:
            entry["result"] = result
        local_steps.append(entry)
        if set_fn:
            await set_fn({"steps": local_steps})

    t0 = datetime.now(timezone.utc)

    # 1. Ingestion — MUST run first. This is what stamps dirty=True +
    #    source_version=<run_id> on norm_company (and norm_financials/ownership/
    #    officers). Without this, rebuild_master(scope="incremental") below has
    #    nothing dirty to pick up. Same call the original full bootstrap makes
    #    (bootstrap.py L268-272) — unchanged.
    await _step("ingestion", "running")
    try:
        if delivery is not None:
            ingestion_result = await ingest_tab_delivery(delivery, source_version=source_version)
        else:
            ingestion_result = await ingest_tab_directory(directory, source_version=source_version)
        await _step("ingestion", "ok", ingestion_result)
    except Exception as exc:
        await _step("ingestion", "error", {"error": str(exc)})
        raise

    # 2. Master rebuild — incremental scope, force=False (see module docstring:
    #    force=True or cif_list here would both silently break delta scoping).
    await _step("master_builder", "running")
    try:
        master_result = await master_builder.rebuild_master(scope="incremental", force=False)
        await _step("master_builder", "ok", master_result)
    except Exception as exc:
        await _step("master_builder", "error", {"error": str(exc)})
        raise

    # 3. Ownership graph — kept FULL on purpose. ~2.8k edges today; cheap
    #    regardless of delta size, and the real code has no incremental path for
    #    it either (rebuild_ownership_graph() always deletes+rebuilds all
    #    source="iberinform" edges) — this module doesn't diverge from bootstrap here.
    await _step("ownership_graph", "running")
    try:
        graph_result = await ownership_graph.rebuild_ownership_graph()
        await _step("ownership_graph", "ok", graph_result)
    except Exception as exc:
        await _step("ownership_graph", "error", {"error": str(exc)})
        raise

    # 4. Resolve the delta set (post ingestion+master-rebuild, so newly-created
    #    master_ids from this delivery are included).
    delta_ids = await _get_delta_master_ids(source_version)
    await _step("delta_resolution", "ok", {"delta_company_count": len(delta_ids)})

    # 5. Signal engine — delta only, replacing build_signals_canonical()'s full
    #    db.master_companies.distinct("master_id", {"status":"active"}) loop.
    #    sig_engine.analyze() persists internally via
    #    services/engines/signal/persistence.persist(master_id, source_version,
    #    signals), keyed (master_id, signal_type) and scoped per master_id — safe
    #    to call one company at a time.
    await _step("signal_builder", "running")
    signal_errors: List[Dict] = []
    signal_cache: Dict[str, Any] = {}
    for mid in delta_ids:
        try:
            signal_cache[mid] = await sig_engine.analyze(mid, persist=True)
        except Exception as exc:
            signal_errors.append({"master_id": mid, "error": str(exc)})
    await _step(
        "signal_builder",
        "ok" if not signal_errors else "completed_with_errors",
        {"processed": len(delta_ids), "error_count": len(signal_errors), "errors": signal_errors[:20]},
    )

    # 6. Semantic engine — delta only, replacing build_semantic_canonical()'s full
    #    loop, WITH a checksum pre-check that skips the (expensive, OpenAI-backed)
    #    embedding call for companies whose rules-based semantic profile hasn't
    #    actually changed.
    #
    #    CONFIRMED (semantic/engine.py L56-101 + L26-27, semantic/profile.py L14-19,
    #    verbatim from Emergent, 2026-09-14): build_profile() itself re-embeds
    #    UNCONDITIONALLY — it computes profile_checksum (L91, over PB.DIMENSIONS
    #    minus "semantic_relationships") and saves it (L93/99), but never compares
    #    against the stored value before calling E.get_provider().embed() (L84-88).
    #    That's why the manual delta rebuild took ~1h on ~1,000 companies: every one
    #    got re-embedded regardless of whether anything semantically relevant
    #    changed (e.g. a delivery that only updates financials touches nothing in
    #    PB.DIMENSIONS).
    #
    #    The pre-check below reproduces engine.py's own checksum computation
    #    byte-for-byte (same _checksum() = sha256 of json.dumps(profile,
    #    sort_keys=True, default=str)), reusing engine.py's OWN already-imported
    #    dependencies via module attribute access (sem_engine.PB, sem_engine.
    #    fin_engine, sem_engine._load_master, sem_engine._checksum) instead of
    #    re-importing them under possibly-wrong paths — if engine.py's internals
    #    change, this pre-check tracks them automatically. enrich=False is used on
    #    both sides deliberately (build_profile's default): _apply_ai would mutate
    #    sem_profile and desync the checksum from what's actually stored.
    #
    #    Residual cost (honest accounting): the pre-check still runs
    #    fin_engine.analyze + a signal analysis + build_rules_profile per company —
    #    DB/CPU work, zero OpenAI calls. What it saves is exactly the embedding call
    #    and the semantic_profiles write for companies whose profile is unchanged.
    #    The signal analysis is reused from step 5 above (signal_cache) rather than
    #    computed twice.
    await _step("semantic_builder", "running")
    semantic_errors: List[Dict] = []
    semantic_skipped = 0
    semantic_rebuilt = 0
    for mid in delta_ids:
        skip = False
        try:
            master_doc = await sem_engine._load_master(mid)
            if master_doc:
                try:
                    financial = await sem_engine.fin_engine.analyze(mid)
                except Exception:
                    financial = None
                signal = signal_cache.get(mid)
                if signal is None:
                    try:
                        signal = await sig_engine.analyze(mid, persist=False)
                    except Exception:
                        signal = None
                sem_profile = sem_engine.PB.build_rules_profile(master_doc, financial, signal)
                profile_only = {
                    k: sem_profile[k] for k in sem_engine.PB.DIMENSIONS if k != "semantic_relationships"
                }
                new_checksum = sem_engine._checksum(profile_only)
                prev_doc = await db.semantic_profiles.find_one(
                    {"master_id": mid}, {"profile_checksum": 1}
                )
                if prev_doc and prev_doc.get("profile_checksum") == new_checksum:
                    skip = True
        except Exception:
            # Pre-check itself failed for any reason -> never skip on uncertain
            # state, fall through to a normal rebuild below.
            skip = False

        if skip:
            semantic_skipped += 1
            continue

        try:
            await sem_engine.build_profile(mid, enrich=False, with_relationships=False, persist=True)
            semantic_rebuilt += 1
        except Exception as exc:
            semantic_errors.append({"master_id": mid, "error": str(exc)})
    await _step(
        "semantic_builder",
        "ok" if not semantic_errors else "completed_with_errors",
        {
            "processed": len(delta_ids),
            "rebuilt": semantic_rebuilt,
            "skipped_unchanged": semantic_skipped,
            "error_count": len(semantic_errors),
            "errors": semantic_errors[:20],
        },
    )

    # 7. Orphan signal sweep — cheap, keeps `signals` consistent.
    await _step("sweep_orphan_signals", "running")
    try:
        sweep_result = await master_builder.sweep_orphan_signals()
        await _step("sweep_orphan_signals", "ok", sweep_result)
    except Exception as exc:
        # Non-fatal: don't fail the whole delivery over a housekeeping sweep.
        await _step("sweep_orphan_signals", "error", {"error": str(exc)})

    # 8. verify() / select_canonical_set() — same calls the original full
    #    bootstrap makes at the end of its chain. Both read master_companies
    #    directly (not a full-universe cache), so they're safe to call unchanged
    #    regardless of delta size — verify() is pure counts, select_canonical_set()
    #    is a top-N re-rank over companies with >=2 years of history (not delta-
    #    dependent: a new delivery's companies only enter the canonical set if
    #    they outrank the current top N by history depth + revenue).
    await _step("verification", "running")
    try:
        verify_result = await bootstrap_svc.verify()
        await _step("verification", "ok", verify_result)
    except Exception as exc:
        await _step("verification", "error", {"error": str(exc)})

    await _step("canonical_set", "running")
    try:
        canonical_result = await bootstrap_svc.select_canonical_set(n=canonical_n)
        await _step("canonical_set", "ok", canonical_result)
    except Exception as exc:
        await _step("canonical_set", "error", {"error": str(exc)})

    duration_s = (datetime.now(timezone.utc) - t0).total_seconds()
    overall_status = "completed" if not (signal_errors or semantic_errors) else "completed_with_errors"

    return {
        "run_id": run_id,
        "mode": "delta",
        "delta_company_count": len(delta_ids),
        "steps": local_steps,
        "duration_s": duration_s,
        "status": overall_status,
    }


# ---------------------------------------------------------------------------
# Remaining open items (small, non-blocking — none of these stop this file from
# being applied and run correctly as written):
#
# 1. `db` import path (line ~110) — adjust `from database import db` if this
#    codebase's actual module/path differs; every excerpt so far only shows bare
#    `db.<collection>` usage inside call sites, never the import itself.
#
# 2. I have NOT seen the full ingest_tab_directory/ingest_tab_delivery return
#    shape beyond the entry-point signatures (L583-611 of
#    iberinform_tab_ingest.py) — the `ingestion_result` stored in the "ingestion"
#    step is whatever those functions return verbatim, same as the original
#    bootstrap chain does. No assumption made about its internal shape.
#
# 3. The checksum pre-check (step 6) reaches into engine.py's private helpers
#    (_load_master, _checksum) and its module-level `fin_engine` name via plain
#    attribute access on the imported module (sem_engine._load_master, etc.)
#    rather than re-importing them under a guessed path. This is deliberate —
#    Python guarantees these names live in engine.py's own namespace since
#    build_profile() calls them unqualified — but it does mean this file is
#    coupled to engine.py's internals in a way a public API wouldn't be. If a
#    future engine.py refactor renames/removes any of these, this pre-check
#    (not the rest of the delta pipeline) is what would break; the fallback
#    inside step 6 (any exception in the pre-check -> never skip, always
#    rebuild) means that failure mode is "loses the cost optimization", not
#    "corrupts or skips real work".
# ---------------------------------------------------------------------------
