"""Auditoría de la clasificación (F3). Resume la calidad de la primera pasada sobre los fingerprints
persistidos: distribución por sector, confianza media, baja confianza, sin clasificar, y una muestra
para revisión manual (100–200). Sirve para detectar huecos/solapamientos antes de escalar el árbol.
"""

from typing import Dict, List
from services.taxonomy import registry as REG

_SECTOR_LABEL = {n["id"]: n["label_es"] for n in REG.build_nodes() if n["level"] == "sector"}


async def audit_report(sample_n: int = 150) -> Dict:
    from database import db
    fps: List[Dict] = [f async for f in db.company_fingerprint.find({}, {"_id": 0})]
    total = len(fps)
    by_sector: Dict[str, int] = {}
    low = unclassified = 0
    conf = 0.0
    for f in fps:
        ps = f.get("primary_sector")
        if ps:
            by_sector[ps] = by_sector.get(ps, 0) + 1
        else:
            unclassified += 1
        oc = f.get("overall_confidence") or 0
        conf += oc
        if oc < 0.5:
            low += 1
    dist = sorted(({"sector": s, "label": _SECTOR_LABEL.get(s, s), "count": c,
                    "pct": round(100 * c / total, 1) if total else 0}
                   for s, c in by_sector.items()), key=lambda x: -x["count"])
    sample = [{"company_id": f.get("company_id"), "primary_sector": f.get("primary_sector"),
               "label": _SECTOR_LABEL.get(f.get("primary_sector"), None),
               "overall_confidence": f.get("overall_confidence")} for f in fps[:sample_n]]
    return {"taxonomy_version": REG.TAXONOMY_VERSION, "total_classified": total,
            "avg_confidence": round(conf / total, 3) if total else 0.0,
            "low_confidence": low, "unclassified": unclassified,
            "distribution_by_sector": dist, "sample": sample}


async def list_unclassified(limit: int = 300) -> Dict:
    """Empresas sin sector principal (primary_sector nulo), enriquecidas con nombre/CNAE de
    master_companies, para revisión manual en la Platform Console. Mayoría: autónomos/personas
    físicas sin CNAE ni objeto social."""
    from database import db
    ids: List[str] = [f.get("company_id") async for f in db.company_fingerprint.find(
        {"primary_sector": None}, {"company_id": 1, "_id": 0})]
    total = len(ids)
    ids = [i for i in ids if i][:limit]
    by_id: Dict[str, Dict] = {}
    if ids:
        async for m in db.master_companies.find(
                {"master_id": {"$in": ids}},
                {"_id": 0, "master_id": 1, "identity.legal_name": 1, "identity.cif": 1,
                 "classification.cnae_code": 1, "classification.cnae_description": 1,
                 "objeto_social": 1, "location.provincia": 1}):
            by_id[m["master_id"]] = m
    items = []
    for cid in ids:
        m = by_id.get(cid) or {}
        idn = m.get("identity") or {}
        cls = m.get("classification") or {}
        os_v = m.get("objeto_social")
        os_txt = os_v if isinstance(os_v, str) else ""
        items.append({
            "company_id": cid,
            "legal_name": idn.get("legal_name"),
            "cif": idn.get("cif"),
            "cnae_code": cls.get("cnae_code"),
            "cnae_description": cls.get("cnae_description"),
            "provincia": (m.get("location") or {}).get("provincia"),
            "has_objeto_social": bool(os_txt),
            "objeto_social_preview": os_txt[:160] if os_txt else None,
        })
    return {"taxonomy_version": REG.TAXONOMY_VERSION, "total_unclassified": total,
            "returned": len(items), "items": items}



def render_audit_md(rep: Dict) -> str:
    lines = ["# Auditoría de clasificación — ARROBA Company Taxonomy", "",
             f"- Versión taxonomía: {rep.get('taxonomy_version')}",
             f"- Empresas clasificadas: {rep.get('total_classified')}",
             f"- Confianza media: {rep.get('avg_confidence')}",
             f"- Baja confianza (<0,5): {rep.get('low_confidence')}",
             f"- Sin clasificar: {rep.get('unclassified')}", "", "## Distribución por sector"]
    for d in rep.get("distribution_by_sector", []):
        lines.append(f"- {d['sector']} · {d['label']}: {d['count']} ({d['pct']}%)")
    lines += ["", f"## Muestra para revisión ({len(rep.get('sample', []))})"]
    for s in rep.get("sample", []):
        lines.append(f"- {s['company_id']}: {s.get('label') or 'sin sector'} "
                     f"(conf {s.get('overall_confidence')})")
    return "\n".join(lines)
