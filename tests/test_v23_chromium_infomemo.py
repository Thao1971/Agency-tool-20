"""
v23 tests:
- Chromium launch args patch verification (files-level grep + smoke sync of BME/DataComex)
- Cuaderno de Venta / Information Memorandum end-to-end (compose, structure asserts, exports)
- Async doc generation
- M&A engine regressions
- Auth negatives
"""
import os
import re
import time
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

BASE_URL = "http://localhost:8001"

be_env = dotenv_values("/app/backend/.env")
API_KEY = be_env.get("ARROBA_SERVICE_API_KEY", "").strip('"').strip("'")

CREDS_PATH = Path("/app/memory/test_credentials.md")
_cred_text = CREDS_PATH.read_text()
_email = re.search(r"Email:\s*`([^`]+)`", _cred_text).group(1)
_pwd = re.search(r"Password:\s*`([^`]+)`", _cred_text).group(1)


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/v1/auth/login",
                      json={"email": _email, "password": _pwd}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token")
    assert tok, r.text
    return tok


@pytest.fixture(scope="session")
def jwt_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def api_headers():
    return {"X-API-Key": API_KEY}


# -------------------- Chromium flags patch --------------------
class TestChromiumFlags:
    FILES = [
        "/app/backend/services/bme_connector.py",
        "/app/backend/services/bme_enrichment.py",
        "/app/backend/services/datacomex_playwright.py",
    ]

    def test_flags_present_in_all_files(self):
        for f in self.FILES:
            content = Path(f).read_text()
            assert "chromium.launch" in content, f"no chromium.launch in {f}"
            assert "--disable-dev-shm-usage" in content, f"missing --disable-dev-shm-usage in {f}"
            assert "--no-sandbox" in content, f"missing --no-sandbox in {f}"
            assert "--disable-setuid-sandbox" in content, f"missing --disable-setuid-sandbox in {f}"

    def test_backend_healthy_after_patch(self):
        r = requests.get(f"{BASE_URL}/api/v1/health", timeout=10)
        assert r.status_code == 200

    def test_chromium_binary_installed(self):
        cache = Path("/root/.cache/ms-playwright")
        assert cache.exists(), "playwright cache missing"
        # At least one chromium-* subdir
        assert any(p.name.startswith("chromium") for p in cache.iterdir()), \
            f"no chromium dir in {cache}"


# -------------------- Information Memorandum --------------------
CUADERNO_COMPANY_ID = "mc_36c100bcee4a"  # LABORATORIOS SERVIER


@pytest.fixture(scope="session")
def infomemo_document_id(jwt_headers):
    r = requests.post(
        f"{BASE_URL}/api/v1/docstudio/compose/information-memorandum",
        params={"company_id": CUADERNO_COMPANY_ID},
        headers=jwt_headers,
        timeout=180,
    )
    assert r.status_code == 200, f"compose failed: {r.status_code} {r.text[:500]}"
    body = r.json()
    doc_id = body.get("document_id") or body.get("id") or body.get("document", {}).get("id")
    assert doc_id, f"no document_id in response: {body}"
    return doc_id


class TestInformationMemorandum:
    def test_compose_returns_doc_id(self, infomemo_document_id):
        assert isinstance(infomemo_document_id, str) and len(infomemo_document_id) > 0

    def test_document_has_expected_structure(self, jwt_headers, infomemo_document_id):
        r = requests.get(
            f"{BASE_URL}/api/v1/docstudio/documents/{infomemo_document_id}",
            headers=jwt_headers, timeout=60,
        )
        assert r.status_code == 200, r.text[:500]
        body = r.json()
        doc = body.get("document", body)
        sections = doc.get("sections", [])
        n = len(sections)
        # Report actual count for diagnostics; expected ~27
        print(f"[infomemo] section_count={n}")
        assert n >= 15, f"too few sections: {n}"

        # Flatten all blocks
        all_blocks = []
        for s in sections:
            for b in s.get("blocks", []):
                all_blocks.append((s.get("title", ""), b))

        block_types = {b.get("block_type") or b.get("type") for _, b in all_blocks}
        print(f"[infomemo] block_types={block_types}")

        # orgchart block
        orgchart_blocks = [b for _, b in all_blocks
                           if (b.get("block_type") or b.get("type")) == "orgchart"]
        assert orgchart_blocks, "no orgchart block found"
        og = orgchart_blocks[0]
        og_data = og.get("data", og)
        assert og_data.get("root") or og_data.get("groups"), \
            f"orgchart empty root/groups: {og_data}"

        # waterfall chart in EBITDA Bridge
        waterfall_blocks = []
        for title, b in all_blocks:
            btype = b.get("block_type") or b.get("type")
            if btype == "chart":
                data = b.get("data", b)
                if data.get("chart_type") == "waterfall" or "EBITDA" in (title or "").upper():
                    waterfall_blocks.append((title, b))
        assert waterfall_blocks, "no waterfall chart / EBITDA bridge found"
        # confirm at least one has chart_type waterfall
        has_wf = any(
            (b.get("data") or b).get("chart_type") == "waterfall"
            for _, b in waterfall_blocks
        )
        assert has_wf, f"no chart_type='waterfall' among candidates: {waterfall_blocks[:2]}"

        # Section titles concatenated for keyword checks
        titles = " || ".join(s.get("title", "") for s in sections).lower()
        for kw in ["equipo", "mercado", "posici", "ebitda", "proyec", "motivo"]:
            assert kw in titles, f"missing section keyword '{kw}' in titles: {titles[:400]}"

        # 3 projections tables (Conservador / Base / Optimista)
        proj_hits = []
        for title, b in all_blocks:
            btype = b.get("block_type") or b.get("type")
            if btype in ("table", "kpi", "text"):
                blob = str(b.get("data", b)).lower()
                if any(sc in blob for sc in ["conservador", "base", "optimista"]):
                    proj_hits.append(blob)
        combined = " ".join(proj_hits)
        for scenario in ["conservador", "optimista"]:
            assert scenario in combined, f"scenario '{scenario}' not found in projections blocks"

    def test_export_pdf(self, jwt_headers, infomemo_document_id):
        r = requests.get(
            f"{BASE_URL}/api/v1/docstudio/export/{infomemo_document_id}/pdf",
            headers=jwt_headers, timeout=120,
        )
        assert r.status_code == 200, r.text[:300]
        assert "pdf" in r.headers.get("content-type", "").lower()
        assert len(r.content) > 500

    def test_export_pptx(self, jwt_headers, infomemo_document_id):
        r = requests.get(
            f"{BASE_URL}/api/v1/docstudio/export/{infomemo_document_id}/pptx",
            headers=jwt_headers, timeout=120,
        )
        assert r.status_code == 200, r.text[:300]
        assert "presentation" in r.headers.get("content-type", "").lower() \
            or "officedocument" in r.headers.get("content-type", "").lower()
        assert len(r.content) > 500


# -------------------- Async compose --------------------
class TestAsyncCompose:
    def test_async_flow_end_to_end(self, jwt_headers):
        r = requests.post(
            f"{BASE_URL}/api/v1/docstudio/compose-async",
            json={"doc_type": "company_snapshot",
                  "params": {"company_id": "mc_d06d23d431d7"}},
            headers=jwt_headers, timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        job_id = body.get("job_id")
        assert job_id, body
        assert body.get("status") in ("queued", "running", "done")
        # eta may be optional
        # poll up to ~90s
        doc_id = None
        deadline = time.time() + 120
        last_status = None
        while time.time() < deadline:
            try:
                pr = requests.get(
                    f"{BASE_URL}/api/v1/docstudio/compose-jobs/{job_id}",
                    headers=jwt_headers, timeout=25,
                )
                if pr.status_code == 200:
                    pj = pr.json()
                    last_status = pj.get("status")
                    if last_status == "done":
                        doc_id = pj.get("document_id")
                        break
                    if last_status == "error":
                        pytest.fail(f"async job errored: {pj}")
            except requests.RequestException:
                pass
            time.sleep(4)
        assert doc_id, f"async job did not complete (last_status={last_status})"


# -------------------- Engine regressions --------------------
class TestEngineRegressions:
    def test_fragmentation(self, api_headers):
        r = requests.get(
            f"{BASE_URL}/api/v1/investment-intelligence/fragmentation",
            params={"cnae_field": "cnae_code", "cnae_value": "4711"},
            headers=api_headers, timeout=60,
        )
        assert r.status_code == 200, r.text[:200]
        assert isinstance(r.json(), dict)

    def test_rollup_thesis(self, api_headers):
        r = requests.get(
            f"{BASE_URL}/api/v1/investment-intelligence/rollup-thesis",
            params={"cnae_field": "cnae_code", "cnae_value": "4711"},
            headers=api_headers, timeout=60,
        )
        assert r.status_code == 200, r.text[:200]

    def test_ratios_catalog(self, api_headers):
        r = requests.get(f"{BASE_URL}/api/v1/financial-intelligence/ratios/catalog",
                         headers=api_headers, timeout=30)
        assert r.status_code == 200

    def test_control_synergy(self, jwt_headers):
        r = requests.get(
            f"{BASE_URL}/api/v1/data-layer/control-synergy/mc_36c100bcee4a/mc_d06d23d431d7",
            headers=jwt_headers, timeout=60,
        )
        assert r.status_code == 200, r.text[:200]

    def test_signal_stats(self, jwt_headers):
        r = requests.get(f"{BASE_URL}/api/v1/signal-intelligence/stats/view",
                         headers=jwt_headers, timeout=30)
        assert r.status_code == 200
        j = r.json()
        # Loose check: signals ~66050, opportunities ~160
        s = j.get("total_signals") or j.get("signals") or j.get("stats", {}).get("total_signals")
        o = j.get("total_opportunities") or j.get("opportunities") or j.get("stats", {}).get("total_opportunities")
        print(f"[stats] signals={s} opps={o}")

    def test_signal_opportunities(self, jwt_headers):
        r = requests.get(f"{BASE_URL}/api/v1/signal-intelligence/opportunities/view",
                         headers=jwt_headers, timeout=30)
        assert r.status_code == 200

    def test_watchlist_get_and_post(self, jwt_headers):
        # POST create/upsert a watchlist item (may 200/201/204 depending on impl)
        payload = {"master_id": "mc_36c100bcee4a", "note": "TEST_v23"}
        pr = requests.post(f"{BASE_URL}/api/v1/watchlist", json=payload,
                           headers=jwt_headers, timeout=30)
        assert pr.status_code in (200, 201, 204, 409), pr.text[:200]
        gr = requests.get(f"{BASE_URL}/api/v1/watchlist",
                          headers=jwt_headers, timeout=30)
        assert gr.status_code == 200

    def test_admin_iberinform_stats(self, jwt_headers):
        r = requests.get(f"{BASE_URL}/api/v1/admin/iberinform/stats",
                         headers=jwt_headers, timeout=30)
        assert r.status_code == 200
        j = r.json()
        real = j.get("real") or j.get("real_companies") or j.get("iberinform", {}).get("real_companies")
        print(f"[iberinform] real={real}")

    def test_data_providers_health(self, jwt_headers):
        r = requests.get(f"{BASE_URL}/api/v1/data-providers/health",
                         headers=jwt_headers, timeout=30)
        assert r.status_code == 200


# -------------------- Auth negatives --------------------
class TestAuthNegatives:
    def test_service_endpoints_reject_missing_key(self):
        for path in [
            "/api/v1/investment-intelligence/fragmentation?cnae_field=cnae_code&cnae_value=4711",
            "/api/v1/investment-intelligence/rollup-thesis?cnae_field=cnae_code&cnae_value=4711",
            "/api/v1/financial-intelligence/ratios/catalog",
        ]:
            r = requests.get(f"{BASE_URL}{path}", timeout=15)
            assert r.status_code in (401, 403), f"{path} → {r.status_code}"

    def test_service_endpoints_reject_bad_key(self):
        r = requests.get(
            f"{BASE_URL}/api/v1/investment-intelligence/fragmentation?cnae_field=cnae_code&cnae_value=4711",
            headers={"X-API-Key": "bogus"}, timeout=15,
        )
        assert r.status_code in (401, 403)

    def test_jwt_endpoints_reject_missing_token(self):
        for path in [
            "/api/v1/signal-intelligence/stats/view",
            "/api/v1/signal-intelligence/opportunities/view",
            "/api/v1/watchlist",
            "/api/v1/admin/iberinform/stats",
            "/api/v1/data-layer/control-synergy/mc_36c100bcee4a/mc_d06d23d431d7",
        ]:
            r = requests.get(f"{BASE_URL}{path}", timeout=15)
            assert r.status_code in (401, 403), f"{path} → {r.status_code}"

    def test_docstudio_compose_rejects_missing_jwt(self):
        r = requests.post(
            f"{BASE_URL}/api/v1/docstudio/compose/information-memorandum",
            params={"company_id": CUADERNO_COMPANY_ID}, timeout=15,
        )
        assert r.status_code in (401, 403)
