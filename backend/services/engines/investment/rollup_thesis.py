"""Roll-up / Platform Thesis (E6 — Investment Intelligence, evolución).

Consume el índice de fragmentación real de E7 (`fragmentation.py::compute_fragmentation`)
y el mapa de consolidación real de T3 (`graph_traversal.py::sector_consolidation_map`)
para responder la pregunta que el roadmap describe para E6: "¿es este sector un buen
candidato a estrategia de roll-up, y si lo es, quién lideraría (plataforma) y a quién se
compraría primero (targets)?"

Explícitamente dependiente de E7 (documentado en el docstring de `fragmentation.py`:
"la siguiente iniciativa natural que CONSUME este índice") — sin `compute_fragmentation()`
no había forma de saber si un sector ya está consolidado (Q2) o realmente disperso, y una
tesis de roll-up sobre un sector ya consolidado no sería una tesis de roll-up real.

Investigado antes de construir (ver memoria de sesión): no existía ningún motor de
"plataforma"/roll-up sectorial. Lo más cercano eran tres señales PER-COMPANY dispersas
(`strategy/engine.py`'s thesis "consolidation", `recommendation/engine.py::_is_consolidator`,
el composite `opportunity.consolidation_candidate`) — todas usan el mismo proxy real
`ownership.investees >= 2` para "ya actúa como consolidador", pero ninguna rankea targets
ni identifica una plataforma a nivel de sector. E6 es terreno nuevo que solo reutiliza
datos ya reales de E7/T3/E2/Q2, no una extensión de esas señales.

Metodología (rules-based, sin IA, mismo contrato D-style que `mandates.py` — 3
dimensiones independientes con pesos versionados, siempre visibles):

1. **Viabilidad de roll-up**: reutiliza `compute_fragmentation()` sin recalcular HHI ni
   targets por su cuenta (regla explícita heredada de E7). Un sector es "roll-up viable"
   si (a) su HHI real no está ya altamente/moderadamente concentrado (mismo umbral
   DOJ/FTC que ya usa `fragmentation.py`, `HHI_MODERATE`) y (b) tiene al menos
   `MIN_STANDALONE_TARGETS` candidatos standalone reales (sin `ownership.group_id`, Q2).
   Si `fragmentation.py` no pudo calcular HHI (sin datos de facturación en el sector), la
   viabilidad es `None` — nunca se infiere sin esa base real.
2. **Candidato a plataforma**: el actor de mercado real (facturación agrupada por
   `ownership.group_id`, mismo criterio que `fragmentation._market_actors`) con mayor
   facturación agregada. Se marca `platform_type="existing"` solo si su cuota de mercado
   real supera `PLATFORM_SHARE_THRESHOLD`; si no hay ningún actor dominante,
   `platform_type="external_needed"` — nunca se inventa una empresa plataforma que no
   tiene ni cerca la escala real para serlo.
3. **Ranking de targets add-on**: SOLO empresas standalone reales (sin
   `ownership.group_id`) del universo de `sector_consolidation_map()` (T3). Tres
   dimensiones independientes vía `scoring.fit_dimension`/`derive_score_with_weights`
   (mismo contrato que E1):
   - `size_fit`: cuanto más pequeña respecto al mayor actor real del sector, más fácil/
     barata de integrar como primer add-on (proxy estructural de tamaño relativo, nunca
     una preferencia de comprador inventada).
   - `succession_ease`: LEE (no recalcula) el `succession_risk_score` ya calculado por
     E2 (`succession_intelligence.build_profile()`).
   - `synergy_proximity`: 0.8 si el target ya tiene una arista real `competitor_of` (Q2)
     con el candidato a plataforma dentro del propio `sector_consolidation_map()` —
     solapamiento estructural real, nunca un € de sinergia estimado.
   Si una dimensión no tiene dato real (sin facturación, sin administradores en
   `norm_officers`), cae a un valor neutral 0.3 — mismo patrón que `_opportunity_fit` en
   `mandates.py` — nunca excluye al target del ranking por eso.

**Deliberadamente fuera de alcance:** ninguna estimación de sinergia económica (ahorro de
costes, cross-sell) — no hay dato real que la respalde hoy, `synergy_proximity` es solo
solapamiento estructural detectado por Q2. Tampoco se calcula un football-field de
valoración del roll-up combinado — consumiría Q6 más allá de su cobertura real hoy
(agencias, división 73), esa extensión de Q6 sigue pendiente y documentada aparte.
"""

from typing import Dict, List, Optional

from database import db
from services.engines.investment import fragmentation as F
from services.data_layer.master.graph_traversal import sector_consolidation_map
from services.engines.signal import succession_intelligence as SI
from services.engines.recommendation import scoring as S

ENGINE_VERSION = "rollup-thesis-v1"
MIN_STANDALONE_TARGETS = 3
PLATFORM_SHARE_THRESHOLD = 0.20  # >=20% de la facturación real de los actores del sector
ROLLUP_FIT_WEIGHTS = {"size_fit": 0.40, "succession_ease": 0.35, "synergy_proximity": 0.25}


def _size_fit(candidate_revenue: Optional[float], max_actor_revenue: Optional[float]):
    if not candidate_revenue or candidate_revenue <= 0:
        return 0.3, ["facturación del candidato desconocida"]
    if not max_actor_revenue or max_actor_revenue <= 0:
        return 0.3, ["sin actor de referencia real para comparar tamaño"]
    ratio = candidate_revenue / max_actor_revenue
    value = max(0.0, 1 - min(1.0, ratio))
    return value, [f"facturación {candidate_revenue:,.0f} vs. mayor actor real del sector {max_actor_revenue:,.0f}"]


def _synergy_proximity(master_id: str, platform_master_id: Optional[str], edges: List[Dict]):
    if not platform_master_id:
        return 0.3, ["sin candidato a plataforma con quien comparar solapamiento"]
    related = any(
        e["relationship_type"] == "competitor_of" and
        {e["src_master_id"], e["dst_master_id"]} == {master_id, platform_master_id}
        for e in edges
    )
    if related:
        return 0.8, ["arista competitor_of real (Q2) con el candidato a plataforma"]
    return 0.3, ["sin solapamiento estructural real detectado con el candidato a plataforma"]


async def compute_rollup_thesis(cnae_field: str, cnae_value: str, limit_companies: int = 300) -> Dict:
    frag = await F.compute_fragmentation(cnae_field, cnae_value, limit_companies=limit_companies)
    consolidation = await sector_consolidation_map(cnae_field, cnae_value, limit_companies=limit_companies)

    rollup_viable: Optional[bool] = None
    viability_reasons: List[str] = []
    if frag["hhi"] is not None:
        concentrated = frag["hhi"] >= F.HHI_MODERATE
        enough_targets = frag["standalone_targets_count"] >= MIN_STANDALONE_TARGETS
        rollup_viable = (not concentrated) and enough_targets
        viability_reasons.append(f"HHI={frag['hhi']} ({frag['concentration_label']})")
        viability_reasons.append(
            f"{frag['standalone_targets_count']} targets standalone reales "
            f"(mínimo requerido: {MIN_STANDALONE_TARGETS})")
    else:
        viability_reasons.append(
            "sin datos de facturación suficientes para calcular HHI (E7) — "
            "viabilidad de roll-up no determinable, no inferida")

    # Candidato a plataforma: facturación real agrupada por ownership.group_id (Q2),
    # mismo criterio que fragmentation.py._market_actors — nunca recalculado distinto.
    revenue_by_actor: Dict[str, float] = {}
    actor_members: Dict[str, List[Dict]] = {}
    for n in consolidation["nodes"]:
        rev = n.get("revenue")
        if not rev or rev <= 0:
            continue
        gid = n.get("group_id") or f"solo_{n['master_id']}"
        revenue_by_actor[gid] = revenue_by_actor.get(gid, 0) + rev
        actor_members.setdefault(gid, []).append(n)

    platform: Optional[Dict] = None
    total_rev = sum(revenue_by_actor.values())
    if revenue_by_actor and total_rev > 0:
        top_gid = max(revenue_by_actor, key=revenue_by_actor.get)
        share = revenue_by_actor[top_gid] / total_rev
        members = actor_members[top_gid]
        lead = max(members, key=lambda m: m.get("revenue") or 0)
        platform = {
            "master_id": lead["master_id"], "name": lead.get("name"),
            "group_id": lead.get("group_id"), "group_revenue": round(revenue_by_actor[top_gid], 2),
            "market_share": round(share, 4),
            "platform_type": "existing" if share >= PLATFORM_SHARE_THRESHOLD else "external_needed",
        }

    # Ranking de targets add-on: solo empresas standalone reales (sin group_id, Q2).
    standalone_nodes = [n for n in consolidation["nodes"] if not n.get("group_id")]
    max_actor_revenue = max(revenue_by_actor.values()) if revenue_by_actor else None
    targets: List[Dict] = []
    for n in standalone_nodes:
        mid = n["master_id"]
        if platform and mid == platform["master_id"]:
            continue
        sf, sf_ev = _size_fit(n.get("revenue"), max_actor_revenue)
        master_doc = await db.master_companies.find_one(
            {"master_id": mid}, {"_id": 0, "master_id": 1, "cif_normalized": 1, "ownership": 1})
        profile = await SI.build_profile(master_doc) if master_doc else None
        if profile:
            se = profile["succession_risk_score"] / 100
            se_ev = [f"succession_risk_score={profile['succession_risk_score']} (E2)"]
        else:
            se, se_ev = 0.3, ["sin perfil de sucesión disponible (sin administradores en norm_officers)"]
        sy, sy_ev = _synergy_proximity(
            mid, platform["master_id"] if platform else None, consolidation["edges"])
        fit = {
            "size_fit": S.fit_dimension(sf, sf_ev, ["master-v1", "fragmentation-v1"]),
            "succession_ease": S.fit_dimension(se, se_ev, ["succession-v1"]),
            "synergy_proximity": S.fit_dimension(sy, sy_ev, ["graph-traversal-v1"]),
        }
        score = S.derive_score_with_weights(fit, ROLLUP_FIT_WEIGHTS)
        targets.append({
            "master_id": mid, "name": n.get("name"), "revenue": n.get("revenue"),
            "addon_score": score, "fit_dimensions": fit,
        })
    targets.sort(key=lambda t: t["addon_score"], reverse=True)

    return {
        "cnae_field": cnae_field, "cnae_value": cnae_value,
        "fragmentation": frag,
        "rollup_viable": rollup_viable, "viability_reasons": viability_reasons,
        "platform_candidate": platform,
        "addon_targets_ranked": targets,
        "addon_targets_count": len(targets),
        "score_method": "weighted-blend-v1", "fit_weights": ROLLUP_FIT_WEIGHTS,
        "truncated": frag["truncated"] or consolidation["truncated"],
        "engine_version": ENGINE_VERSION,
    }
