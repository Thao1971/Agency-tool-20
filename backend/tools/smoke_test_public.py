#!/usr/bin/env python3
"""Smoke Test Público Oficial · Arroba ↔ Intelligence Engine.

Verifica en < 2 min que un despliegue del Intelligence Engine sigue siendo compatible con Arroba,
usando EXCLUSIVAMENTE la Base URL pública + X-API-Key (sin JWT, sin /master/*, sin Mongo).

Uso:
    python tools/smoke_test_public.py                      # producción por defecto
    BASE_URL=https://intel-agency.emergent.host \
    ARROBA_API_KEY=<key> python tools/smoke_test_public.py
    python tools/smoke_test_public.py --base <url> --key <key>

Salida: una línea PASS/FAIL por comprobación + un veredicto final PASS o FAIL. Exit code 0=PASS, 1=FAIL.
"""
import argparse
import json
import os
import sys
import urllib.request

DEFAULT_BASE = "https://intel-agency.emergent.host"
CANONICAL_CIF = "A87803862"           # TOTALENERGIES ELECTRICIDAD Y GAS ESPAÑA
EXPECTED_CONTRACT = "arroba-integration-contract-v2"


def _post(base, path, key, body):
    req = urllib.request.Request(
        base + path, data=json.dumps(body).encode(),
        headers={"X-API-Key": key, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode())


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return r.status, json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("BASE_URL", DEFAULT_BASE))
    ap.add_argument("--key", default=os.environ.get("ARROBA_API_KEY", os.environ.get("ARROBA_SERVICE_API_KEY", "")))
    args = ap.parse_args()
    base, key = args.base.rstrip("/"), args.key
    if not key:
        print("FAIL · missing X-API-Key (set ARROBA_API_KEY or --key)")
        sys.exit(1)

    print(f"# Smoke Test Público · base={base} · cif={CANONICAL_CIF}\n")
    checks = []

    def check(name, ok, detail=""):
        checks.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' · ' + detail) if detail else ''}")

    try:
        # 1) resolve CIF -> master_id
        s1, resolve = _post(base, "/api/v2/company-intelligence/resolve", key, {"cif": CANONICAL_CIF})
        check("resolve HTTP 200", s1 == 200, f"http={s1}")
        m = (resolve.get("matches") or [{}])[0]
        master_id = m.get("master_id", "")
        check("resolve → master_id devuelto", bool(master_id) and master_id.startswith("mc_"), f"master_id={master_id}")
        check("resolve match_type=cif_exact score=1.0", m.get("match_type") == "cif_exact" and m.get("score") == 1.0)

        # 2) identity
        s2, ident = _post(base, "/api/v2/company-intelligence/identity", key, {"identifier": CANONICAL_CIF})
        check("identity HTTP 200", s2 == 200, f"http={s2}")
        check("identity · legal_name presente", bool(ident.get("legal_name")), ident.get("legal_name", ""))
        check("identity · cnae_primary presente", bool((ident.get("cnae_primary") or {}).get("code")))
        check("identity · data_coverage presente", isinstance(ident.get("data_coverage"), dict))
        check("identity · master_id coincide con resolve", ident.get("master_id") == master_id)

        # 3) financial-analyze
        s3, fin = _post(base, "/api/v1/financial-intelligence/analyze", key, {"identifier": CANONICAL_CIF})
        check("financial-analyze HTTP 200", s3 == 200, f"http={s3}")
        kpis = fin.get("kpis") or {}
        check("financials reales (revenue>0)", (kpis.get("revenue") or 0) > 0, f"revenue={kpis.get('revenue')}")
        check("financials L2 (ebitda + net_income presentes)",
              kpis.get("ebitda") is not None and kpis.get("net_income") is not None,
              f"ebitda={kpis.get('ebitda')} net_income={kpis.get('net_income')}")
        ev = fin.get("evolution") or {}
        years = [p.get("year") for p in (ev.get("points") or [])]
        check("histórico real (≥2 ejercicios)", (ev.get("years") or 0) >= 2, f"years={years}")
        expl = fin.get("explainability") or {}
        check("data_source trazable", bool(expl.get("data_source")), expl.get("data_source", ""))
        check("explainability presente", bool(expl.get("source_version") and expl.get("basis")))
        check("has_financials=true", fin.get("has_financials") is True)

        # 4) compatibilidad con arroba.v2
        s4, v2 = _get(base, "/api/v1/openapi/arroba.v2.json")
        paths = v2.get("paths", {})
        check("arroba.v2 contrato accesible (200)", s4 == 200)
        check("arroba.v2 versión esperada", v2.get("info", {}).get("version") == EXPECTED_CONTRACT,
              v2.get("info", {}).get("version", ""))
        check("arroba.v2 incluye /resolve, /identity, /financial-intelligence/analyze",
              "/api/v2/company-intelligence/resolve" in paths
              and "/api/v2/company-intelligence/identity" in paths
              and "/api/v1/financial-intelligence/analyze" in paths)
    except Exception as e:  # noqa: BLE001
        check(f"excepción durante el flujo: {str(e)[:160]}", False)

    verdict = "PASS" if all(checks) else "FAIL"
    print(f"\n=== RESULTADO: {verdict} ({sum(checks)}/{len(checks)} comprobaciones) ===")
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
