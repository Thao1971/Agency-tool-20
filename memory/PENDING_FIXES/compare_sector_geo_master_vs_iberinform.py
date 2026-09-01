"""Fase 4 QA (2026-09-01): compara los `dynamism_score` de Sector Intelligence
y Geo Intelligence si el conteo de empresas que alimenta el sub-score
"iberinform" de `activity_score` se leyera de `master_companies` en vez de
`iberinform_companies` — el cambio que describe la Fase 4 del plan de
reorganización (`Intel-140826/memory/PLAN_REORGANIZACION_DATOS_IBERINFORM.md`).

Por qué existe este script en vez de tocar `sector_intelligence_v2.py` /
`geo_intelligence.py` directamente: Daniel pidió explícitamente hacer esta
comparación ANTES de decidir si migrar, porque el recuento de empresas no es
igual entre las dos colecciones (dedupe/resolución de entidades distinta) y
eso puede mover silenciosamente scores que el usuario ya ve. Este script no
migra nada — es de solo lectura, no escribe en ninguna colección, y no toca
ningún archivo de producción.

Cero riesgo de que la fórmula usada aquí diverja de la real: en vez de
reimplementar el cálculo, este script IMPORTA y reutiliza directamente las
funciones puras de `sector_intelligence_v2.py` y `geo_intelligence.py`
(`_aggregate_size`, `_aggregate_growth`, `_aggregate_activity`,
`_build_sector_doc`, `_compute_size`, `_compute_growth`, `_compute_activity`,
`_build_geo_doc`, etc.) — lo único que cambia es de dónde sale el conteo de
empresas ("iberinform" gathering), todo lo demás (demografía INE, BORME,
contratación pública) es idéntico en ambos casos porque no depende de
`iberinform_companies` ni de `master_companies`.

R15 — no fabricar datos: los nombres de provincia de `master_companies` que
no resuelvan a un código INE (vía el mismo mapa que ya usa BORME,
`resolve_borme_province`) se listan aparte como "unmapped", nunca se
descartan en silencio ni se estima nada en su lugar.

Uso: cd backend && python -m scripts.compare_sector_geo_master_vs_iberinform
Salida: informe en texto a stdout (resumen + top movers) + volcado JSON
completo (todas las secciones/divisiones/grupos/provincias/CCAA, antes y
después) en `/tmp/fase4_sector_geo_comparison.json`, para adjuntar o revisar
con calma.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import db  # noqa: E402

from services.cnae_catalog import (  # noqa: E402
    CNAE_SECTIONS, CNAE_DIVISIONS, CNAE_GROUPS, get_section_for_division,
)
from services.geo_catalog import CCAA, PROVINCES, resolve_borme_province  # noqa: E402

import services.sector_intelligence_v2 as sec  # noqa: E402
import services.geo_intelligence as geo  # noqa: E402


# ══════════════════════════════════════════
# Gathering "candidato" desde master_companies (equivalente a
# `_gather_iberinform()` de cada módulo, pero sobre la colección moderna)
# ══════════════════════════════════════════

async def _gather_iberinform_sector_from_master() -> dict:
    data = {"by_division": {}, "total": 0}
    pipeline = [
        {"$match": {"classification.cnae_code": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": {"$substr": ["$classification.cnae_code", 0, 2]},
            "count": {"$sum": 1},
        }},
    ]
    by_cnae = await db.master_companies.aggregate(pipeline).to_list(200)
    for item in by_cnae:
        code = str(item["_id"])
        data["by_division"][code] = {"count": item["count"], "avg_revenue": 0}
    data["total"] = sum(d["count"] for d in data["by_division"].values())
    return data


async def _gather_iberinform_geo_from_master() -> tuple[dict, list]:
    data = {"by_province": {}, "total": 0}
    unmapped: dict[str, int] = {}
    pipeline = [
        {"$match": {"location.provincia": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {"_id": "$location.provincia", "count": {"$sum": 1}}},
    ]
    by_name = await db.master_companies.aggregate(pipeline).to_list(3000)
    for item in by_name:
        name = (item["_id"] or "").strip()
        code = resolve_borme_province(name)
        if code:
            cur = data["by_province"].get(code, {"count": 0})
            cur["count"] += item["count"]
            data["by_province"][code] = cur
        else:
            unmapped[name] = unmapped.get(name, 0) + item["count"]
    data["total"] = sum(d["count"] for d in data["by_province"].values())
    return data, sorted(unmapped.items(), key=lambda x: -x[1])


# ══════════════════════════════════════════
# Sector: recorre section/division/group con iberinform viejo vs nuevo
# ══════════════════════════════════════════

async def compare_sector(ib_old: dict, ib_new: dict) -> list[dict]:
    demography = await sec._gather_demography()
    procurement = await sec._gather_procurement()
    borme = await sec._gather_borme()
    now = "qa-comparison"

    rows = []

    def _run(code, level, label, div_codes, taxonomy_type="official_cnae",
             parent_section=None, parent_division=None):
        size = sec._aggregate_size(demography, div_codes, code)
        growth = sec._aggregate_growth(demography, div_codes, code)
        act_old = sec._aggregate_activity(procurement, borme, ib_old, div_codes, code)
        act_new = sec._aggregate_activity(procurement, borme, ib_new, div_codes, code)
        doc_old = sec._build_sector_doc(
            cnae_code=code, cnae_level=level, cnae_label=label,
            size=size, growth=growth, activity=act_old, now=now,
            taxonomy_type=taxonomy_type, parent_section=parent_section,
            parent_division=parent_division,
        )
        doc_new = sec._build_sector_doc(
            cnae_code=code, cnae_level=level, cnae_label=label,
            size=size, growth=growth, activity=act_new, now=now,
            taxonomy_type=taxonomy_type, parent_section=parent_section,
            parent_division=parent_division,
        )
        rows.append({
            "level": level, "code": code, "label": label,
            "score_old": doc_old["dynamism_score"], "score_new": doc_new["dynamism_score"],
            "delta": doc_new["dynamism_score"] - doc_old["dynamism_score"],
            "trend_old": doc_old["trend_direction"], "trend_new": doc_new["trend_direction"],
            "ib_count_old": act_old["iberinform_companies"],
            "ib_count_new": act_new["iberinform_companies"],
        })

    for s in CNAE_SECTIONS:
        _run(s["code"], "section", s["label"], s["divisions"])
    for div_code, div_info in CNAE_DIVISIONS.items():
        _run(div_code, "division", div_info["label"], [div_code], parent_section=div_info["section"])
    for grp_code, grp_info in CNAE_GROUPS.items():
        div_code = grp_info["division"]
        _run(grp_code, "group", grp_info["label"], [grp_code],
             parent_section=get_section_for_division(div_code), parent_division=div_code)

    # Rank antes/después dentro de cada nivel
    for level in ("section", "division", "group"):
        subset = [r for r in rows if r["level"] == level]
        for rank, r in enumerate(sorted(subset, key=lambda x: -x["score_old"]), start=1):
            r["rank_old"] = rank
        for rank, r in enumerate(sorted(subset, key=lambda x: -x["score_new"]), start=1):
            r["rank_new"] = rank
    for r in rows:
        r["rank_delta"] = r["rank_old"] - r["rank_new"]

    return rows


# ══════════════════════════════════════════
# Geo: provincia + CCAA con iberinform viejo vs nuevo
# ══════════════════════════════════════════

async def compare_geo(ib_old: dict, ib_new: dict) -> list[dict]:
    demography = await geo._gather_demography()
    borme = await geo._gather_borme()
    procurement = await geo._gather_procurement()
    now = "qa-comparison"

    province_docs_old, province_docs_new = {}, {}
    rows = []

    for prov_code, prov_info in PROVINCES.items():
        prov_label = prov_info["label"]
        ccaa_code = prov_info["ccaa"]
        size = geo._compute_size(demography, prov_code, "province")
        growth = geo._compute_growth(demography, prov_code, "province")
        act_old = geo._compute_activity(borme, procurement, ib_old, prov_code, "province")
        act_new = geo._compute_activity(borme, procurement, ib_new, prov_code, "province")
        doc_old = geo._build_geo_doc(prov_code, "province", prov_label, ccaa_code, size, growth, act_old, now)
        doc_new = geo._build_geo_doc(prov_code, "province", prov_label, ccaa_code, size, growth, act_new, now)
        province_docs_old[prov_code] = doc_old
        province_docs_new[prov_code] = doc_new
        rows.append({
            "level": "province", "code": prov_code, "label": prov_label,
            "score_old": doc_old["dynamism_score"], "score_new": doc_new["dynamism_score"],
            "delta": doc_new["dynamism_score"] - doc_old["dynamism_score"],
            "trend_old": doc_old["trend_direction"], "trend_new": doc_new["trend_direction"],
            "ib_count_old": act_old["iberinform_companies"],
            "ib_count_new": act_new["iberinform_companies"],
        })

    for ccaa in CCAA:
        ccaa_code, ccaa_label, prov_codes = ccaa["code"], ccaa["label"], ccaa["provinces"]
        size = geo._compute_size_ccaa(demography, province_docs_old, prov_codes)
        growth = geo._compute_growth_ccaa(demography, province_docs_old, prov_codes)
        act_old = geo._compute_activity_ccaa(borme, procurement, ib_old, prov_codes)
        act_new = geo._compute_activity_ccaa(borme, procurement, ib_new, prov_codes)
        doc_old = geo._build_geo_doc(ccaa_code, "ccaa", ccaa_label, None, size, growth, act_old, now)
        doc_new = geo._build_geo_doc(ccaa_code, "ccaa", ccaa_label, None, size, growth, act_new, now)
        rows.append({
            "level": "ccaa", "code": ccaa_code, "label": ccaa_label,
            "score_old": doc_old["dynamism_score"], "score_new": doc_new["dynamism_score"],
            "delta": doc_new["dynamism_score"] - doc_old["dynamism_score"],
            "trend_old": doc_old["trend_direction"], "trend_new": doc_new["trend_direction"],
            "ib_count_old": act_old["iberinform_companies"],
            "ib_count_new": act_new["iberinform_companies"],
        })

    for level in ("province", "ccaa"):
        subset = [r for r in rows if r["level"] == level]
        for rank, r in enumerate(sorted(subset, key=lambda x: -x["score_old"]), start=1):
            r["rank_old"] = rank
        for rank, r in enumerate(sorted(subset, key=lambda x: -x["score_new"]), start=1):
            r["rank_new"] = rank
    for r in rows:
        r["rank_delta"] = r["rank_old"] - r["rank_new"]

    return rows


# ══════════════════════════════════════════
# Informe
# ══════════════════════════════════════════

def _print_summary(title: str, rows: list[dict]) -> None:
    print(f"\n=== {title} ===")
    print(f"Total items: {len(rows)}")
    deltas = [r["delta"] for r in rows]
    big = [r for r in rows if abs(r["delta"]) >= 10]
    moderate = [r for r in rows if 5 <= abs(r["delta"]) < 10]
    trend_flips = [r for r in rows if r["trend_old"] != r["trend_new"]]
    rank_swaps = [r for r in rows if r["rank_delta"] != 0]
    avg_abs_delta = round(sum(abs(d) for d in deltas) / len(deltas), 2) if deltas else 0
    print(f"Delta medio (abs): {avg_abs_delta} puntos")
    print(f"Cambios grandes (|delta|>=10): {len(big)}")
    print(f"Cambios moderados (5<=|delta|<10): {len(moderate)}")
    print(f"Cambios de trend_direction (up/down/stable): {len(trend_flips)}")
    print(f"Items con cambio de ranking dentro de su nivel: {len(rank_swaps)}")

    top = sorted(rows, key=lambda r: -abs(r["delta"]))[:15]
    if top:
        print("\nTop 15 movers (por |delta| de dynamism_score):")
        for r in top:
            flag = "⚠️ " if abs(r["delta"]) >= 10 else ("· " if abs(r["delta"]) >= 5 else "  ")
            trend = f" [{r['trend_old']}→{r['trend_new']}]" if r["trend_old"] != r["trend_new"] else ""
            print(f"  {flag}{r['level']:9s} {r['code']:6s} {r['label'][:38]:38s} "
                  f"{r['score_old']:3d} → {r['score_new']:3d} ({r['delta']:+d}){trend}  "
                  f"[ib_count {r['ib_count_old']} → {r['ib_count_new']}]  "
                  f"rank #{r['rank_old']} → #{r['rank_new']}")


async def main() -> None:
    print("Fase 4 QA — comparación de scores Sector/Geo Intelligence "
          "(iberinform_companies vs master_companies), solo lectura.\n")

    ib_sector_old = await sec._gather_iberinform()
    ib_sector_new = await _gather_iberinform_sector_from_master()
    print(f"Empresas contabilizadas (Sector) — iberinform_companies: {ib_sector_old['total']}  "
          f"· master_companies: {ib_sector_new['total']}  "
          f"(diferencia: {ib_sector_new['total'] - ib_sector_old['total']:+d})")

    ib_geo_old = await geo._gather_iberinform()
    ib_geo_new, unmapped_provincias = await _gather_iberinform_geo_from_master()
    print(f"Empresas contabilizadas (Geo)    — iberinform_companies: {ib_geo_old['total']}  "
          f"· master_companies: {ib_geo_new['total']}  "
          f"(diferencia: {ib_geo_new['total'] - ib_geo_old['total']:+d})")
    if unmapped_provincias:
        total_unmapped = sum(c for _, c in unmapped_provincias)
        print(f"\n⚠️  {len(unmapped_provincias)} nombres de provincia en master_companies "
              f"no resuelven a código INE ({total_unmapped} empresas sin provincia asignable "
              f"en esta comparación). Top 10:")
        for name, count in unmapped_provincias[:10]:
            print(f"   {count:6d}  {name!r}")

    sector_rows = await compare_sector(ib_sector_old, ib_sector_new)
    geo_rows = await compare_geo(ib_geo_old, ib_geo_new)

    _print_summary("Sector Intelligence (section + division + group)", sector_rows)
    _print_summary("Geo Intelligence (province + ccaa)", geo_rows)

    out_path = "/tmp/fase4_sector_geo_comparison.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "sector_company_counts": {"iberinform_companies": ib_sector_old["total"],
                                       "master_companies": ib_sector_new["total"]},
            "geo_company_counts": {"iberinform_companies": ib_geo_old["total"],
                                    "master_companies": ib_geo_new["total"]},
            "unmapped_provincias": unmapped_provincias,
            "sector": sector_rows,
            "geo": geo_rows,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nInforme completo (JSON) escrito en: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
