"""Control & Synergy Score (roadmap: parte de T3, dueño "Ownership & Control
Intelligence / Buyer Intelligence", dependiente de Q2).

El roadmap (`docs/strategic-intelligence-architecture/07_DECISION_INTELLIGENCE.md`,
línea 51-53) solo define el NOMBRE y el propósito de este score — nunca una fórmula:
"Resuelve parte de G5, aplicado a sinergias de comprador estratégico (solapamiento/
complementariedad vía `competitor_of`, `supplier_candidate`)". `supplier_candidate`
está confirmado sin datos reales en ninguna fuente conectada (mismo hallazgo que Q2),
así que este módulo mide solo la mitad real y disponible: solapamiento HORIZONTAL
(competencia/mercado), nunca complementariedad VERTICAL (proveedor/cliente).

Dado que no hay fórmula prescrita, se diseñan aquí DOS scores independientes y
explicables (nunca combinados en un único número opaco) entre un par de empresas real
(`master_id_a`, `master_id_b`), reutilizando exclusivamente datos ya reales de Q2/T3/E2:

1. **Control score** — grado real de control societario entre las dos empresas, usando
   el campo `pct` real de `master_relationships` (Iberinform vía `norm_ownership`,
   `ownership_graph.py`), NUNCA usado hasta ahora para nada más que agrupar
   binariamente (`same_group` vía union-find ignora el `pct`). Si hay una arista
   directa de propiedad con `pct` real, se clasifica por umbrales estándar de control
   societario (>=50% control total, 25-50% influencia significativa, <25% participación
   minoritaria). Si solo comparten `ownership.group_id` (Q2) sin una arista directa con
   `pct`, se reporta honestamente como tal — nunca se inventa un porcentaje. Si hay un
   camino indirecto multi-salto (T3 `traverse`) y CADA arista del camino tiene `pct`
   real, se calcula el `implied_effective_pct` como el producto real de las
   participaciones de la cadena (matemática estándar de participación indirecta, no
   inventada) — si falta un `pct` en cualquier tramo, se deja `None` con caveat.
2. **Synergy score** — solapamiento estructural real entre las dos empresas: arista
   `competitor_of` real (Q2, peso 0.5), mismo `cnae_code` exacto (0.3, solapamiento de
   mercado directo) o misma `cnae_division` si no coincide el código exacto (0.15,
   sector adyacente), misma provincia (0.2, proximidad operativa real). Nunca un €
   de sinergia estimado — es un proxy de solapamiento estructural, documentado así en
   `data_caveat`.

Reutiliza `graph_traversal.py` (T3) para el camino multi-salto y `master_relationships`
(Q2) directamente para la arista directa — ningún dato nuevo, ninguna fuente nueva.
"""

from typing import Dict, List, Optional

from database import db
from services.data_layer.master.graph_traversal import traverse

ENGINE_VERSION = "control-synergy-v1"
OWNERSHIP_EDGE_TYPES = ["shareholder_of", "parent_of", "ultimate_parent_of", "investee_of"]
FULL_CONTROL_PCT = 50.0
SIGNIFICANT_INFLUENCE_PCT = 25.0


async def _direct_edge(master_id_a: str, master_id_b: str) -> Optional[Dict]:
    return await db.master_relationships.find_one(
        {"$or": [
            {"src_master_id": master_id_a, "dst_master_id": master_id_b},
            {"src_master_id": master_id_b, "dst_master_id": master_id_a},
        ], "relationship_type": {"$in": OWNERSHIP_EDGE_TYPES}},
        {"_id": 0},
    )


def _classify_pct(pct: Optional[float]) -> str:
    if pct is None:
        return "control_edge_sin_pct_real"
    if pct >= FULL_CONTROL_PCT:
        return "full_control"
    if pct >= SIGNIFICANT_INFLUENCE_PCT:
        return "significant_influence"
    return "minority_stake"


async def _company_group_id(master_id: str) -> Optional[str]:
    doc = await db.master_companies.find_one({"master_id": master_id}, {"_id": 0, "ownership.group_id": 1})
    return (doc or {}).get("ownership", {}).get("group_id") if doc else None


def _find_ownership_path(master_id_a: str, master_id_b: str, edges: List[Dict]) -> Optional[List[Dict]]:
    """BFS restringido a los tipos de arista de propiedad ya devueltos por `traverse()`
    (T3) — encuentra UN camino real (el de menos saltos, por construcción de BFS) de
    a a b para el cálculo de la cadena de pct."""
    adjacency: Dict[str, List[Dict]] = {}
    for e in edges:
        if e["relationship_type"] not in OWNERSHIP_EDGE_TYPES:
            continue
        adjacency.setdefault(e["src_master_id"], []).append(e)
        adjacency.setdefault(e["dst_master_id"], []).append(e)

    if master_id_a not in adjacency:
        return None

    visited = {master_id_a}
    frontier: List[tuple] = [(master_id_a, [])]
    while frontier:
        node, path = frontier.pop(0)
        for e in adjacency.get(node, []):
            other = e["dst_master_id"] if e["src_master_id"] == node else e["src_master_id"]
            if other in visited:
                continue
            new_path = path + [e]
            if other == master_id_b:
                return new_path
            visited.add(other)
            frontier.append((other, new_path))
    return None


async def _control(master_id_a: str, master_id_b: str) -> Dict:
    direct = await _direct_edge(master_id_a, master_id_b)
    if direct:
        return {
            "relationship": "direct",
            "relationship_type": direct["relationship_type"],
            "pct": direct.get("pct"),
            "control_level": _classify_pct(direct.get("pct")),
            "evidence": [f"arista real {direct['relationship_type']} (Q2/Iberinform)"],
        }

    gid_a, gid_b = await _company_group_id(master_id_a), await _company_group_id(master_id_b)
    same_group = bool(gid_a and gid_a == gid_b)

    graph = await traverse(master_id_a, max_hops=3, max_nodes=200, relationship_types=OWNERSHIP_EDGE_TYPES)
    path = _find_ownership_path(master_id_a, master_id_b, graph["edges"]) if master_id_b in \
        {n["master_id"] for n in graph["nodes"]} else None

    if path:
        pcts = [e.get("pct") for e in path]
        if all(p is not None for p in pcts):
            implied = 1.0
            for p in pcts:
                implied *= (p / 100.0)
            implied_pct = round(implied * 100, 2)
            return {
                "relationship": "indirect", "hops": len(path),
                "path_relationship_types": [e["relationship_type"] for e in path],
                "implied_effective_pct": implied_pct,
                "control_level": _classify_pct(implied_pct),
                "evidence": [f"camino real de {len(path)} salto(s) vía T3, "
                             f"pct efectivo = producto real de participaciones de la cadena"],
            }
        return {
            "relationship": "indirect", "hops": len(path),
            "path_relationship_types": [e["relationship_type"] for e in path],
            "implied_effective_pct": None,
            "control_level": "indirect_path_pct_incompleto",
            "evidence": ["camino real detectado (T3) pero al menos un tramo no tiene pct real "
                         "— no se infiere un porcentaje sin esa base"],
        }

    if same_group:
        return {
            "relationship": "same_group", "group_id": gid_a,
            "implied_effective_pct": None, "control_level": "same_group_sin_camino_pct",
            "evidence": ["mismo ownership.group_id real (Q2, unión de aristas parent_of/"
                         "ultimate_parent_of) pero sin una arista directa con pct que lo explique"],
        }

    return {"relationship": "unrelated", "control_level": "unrelated",
            "evidence": ["sin relación societaria real detectada en master_relationships (Q2/T3)"]}


async def _synergy(master_id_a: str, master_id_b: str) -> Dict:
    a = await db.master_companies.find_one(
        {"master_id": master_id_a},
        {"_id": 0, "classification.cnae_code": 1, "classification.cnae_division": 1, "location.provincia": 1})
    b = await db.master_companies.find_one(
        {"master_id": master_id_b},
        {"_id": 0, "classification.cnae_code": 1, "classification.cnae_division": 1, "location.provincia": 1})
    a, b = a or {}, b or {}

    score = 0.0
    evidence: List[str] = []

    competitor_edge = await db.master_relationships.find_one(
        {"$or": [
            {"src_master_id": master_id_a, "dst_master_id": master_id_b},
            {"src_master_id": master_id_b, "dst_master_id": master_id_a},
        ], "relationship_type": "competitor_of"}, {"_id": 0})
    if competitor_edge:
        score += 0.5
        evidence.append("arista competitor_of real (Q2)")

    a_code = (a.get("classification") or {}).get("cnae_code")
    b_code = (b.get("classification") or {}).get("cnae_code")
    a_div = (a.get("classification") or {}).get("cnae_division")
    b_div = (b.get("classification") or {}).get("cnae_division")
    if a_code and a_code == b_code:
        score += 0.3
        evidence.append(f"mismo cnae_code exacto ({a_code}) — solapamiento de mercado directo")
    elif a_div and a_div == b_div:
        score += 0.15
        evidence.append(f"misma cnae_division ({a_div}) — sector adyacente, no el mismo código exacto")

    a_prov = (a.get("location") or {}).get("provincia")
    b_prov = (b.get("location") or {}).get("provincia")
    if a_prov and a_prov == b_prov:
        score += 0.2
        evidence.append(f"misma provincia ({a_prov}) — proximidad operativa real")

    if not evidence:
        evidence.append("sin solapamiento estructural real detectado")

    return {
        "synergy_score": round(min(1.0, score), 4),
        "evidence": evidence,
        "data_caveat": ("Proxy de solapamiento ESTRUCTURAL/horizontal real (competencia, sector, "
                        "geografía) — NUNCA un € de sinergia económica estimado. supplier_candidate "
                        "(complementariedad vertical proveedor/cliente) está confirmado sin datos "
                        "reales en ninguna fuente conectada, no se mide aquí."),
    }


async def compute_control_synergy(master_id_a: str, master_id_b: str) -> Dict:
    a_doc = await db.master_companies.find_one({"master_id": master_id_a}, {"_id": 0, "master_id": 1})
    b_doc = await db.master_companies.find_one({"master_id": master_id_b}, {"_id": 0, "master_id": 1})
    if not a_doc or not b_doc:
        raise ValueError("master_id_a y master_id_b deben existir en master_companies")

    control = await _control(master_id_a, master_id_b)
    synergy = await _synergy(master_id_a, master_id_b)
    return {
        "master_id_a": master_id_a, "master_id_b": master_id_b,
        "control": control, "synergy": synergy,
        "engine_version": ENGINE_VERSION,
    }
