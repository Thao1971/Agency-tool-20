"""Test v24: Information Memorandum PDF export fix (landscape, ~27 pages, >300KB).
Also verifies preview HTML endpoint contains new visual blocks and regression endpoints.
"""
import os, re, io
import pytest
import requests
from dotenv import dotenv_values

be = dotenv_values("/app/backend/.env")
API_KEY = be.get("ARROBA_SERVICE_API_KEY")
BASE = "http://localhost:8001/api/v1"
LOGIN = {"email": "daniel@wearebudadvisors.com", "password": "Thao1971@"}
COMPANY = "mc_36c100bcee4a"


@pytest.fixture(scope="session")
def jwt():
    r = requests.post(f"{BASE}/auth/login", json=LOGIN, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    j = r.json()
    return j.get("access_token") or j["token"]


@pytest.fixture(scope="session")
def jwt_headers(jwt):
    return {"Authorization": f"Bearer {jwt}"}


@pytest.fixture(scope="session")
def svc_headers():
    return {"X-API-Key": API_KEY}


@pytest.fixture(scope="session")
def infomemo_id(jwt_headers):
    r = requests.post(
        f"{BASE}/docstudio/compose/information-memorandum",
        headers=jwt_headers,
        params={"company_id": COMPANY},
        timeout=180,
    )
    assert r.status_code == 200, f"compose {r.status_code} {r.text[:400]}"
    doc_id = r.json().get("document_id") or r.json().get("document", {}).get("document_id")
    assert doc_id, r.json()
    return doc_id


# ---------- PDF EXPORT ----------
class TestPDFExport:
    def test_export_pdf_landscape_and_pages(self, jwt_headers, infomemo_id):
        r = requests.get(f"{BASE}/docstudio/export/{infomemo_id}/pdf", headers=jwt_headers, timeout=180)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert r.headers.get("content-type", "").startswith("application/pdf")
        data = r.content
        size = len(data)
        print(f"PDF size: {size} bytes")
        assert size > 300_000, f"PDF too small ({size} bytes), likely WeasyPrint fallback"
        assert data[:4] == b"%PDF", "not a PDF"

        # Parse MediaBoxes
        boxes = re.findall(rb"/MediaBox\s*\[\s*([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s*\]", data)
        assert boxes, "no MediaBox found"
        landscape_ct = 0
        ratios = []
        for a, b, c, d in boxes:
            w = float(c) - float(a)
            h = float(d) - float(b)
            if w > h:
                landscape_ct += 1
                ratios.append(round(w / h, 2))
        print(f"MediaBoxes: {len(boxes)}, landscape: {landscape_ct}, sample ratios: {ratios[:5]}")
        assert landscape_ct == len(boxes), f"not all pages landscape ({landscape_ct}/{len(boxes)})"
        # ratio ~1.78
        assert all(1.6 < r < 1.9 for r in ratios), f"unexpected ratios {ratios[:5]}"

        # page count via /Type /Page
        page_ct = len(re.findall(rb"/Type\s*/Page[^s]", data))
        print(f"PDF pages: {page_ct}")
        assert page_ct >= 10, f"too few pages ({page_ct})"


# ---------- HTML PREVIEW (new visual blocks) ----------
class TestPreviewHTML:
    def test_preview_contains_new_blocks(self, jwt_headers, infomemo_id):
        r = requests.get(f"{BASE}/docstudio/documents/{infomemo_id}/preview", headers=jwt_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        html = r.text
        assert "<svg" in html.lower(), "no SVG charts in preview HTML"
        # Look for new block indicators (best-effort)
        lower = html.lower()
        indicators = ["waterfall", "orgchart", "donut", "scatter", "working capital", "net financial", "bridge", "separator", "ebitda", "chart", "grouped-bars", "chart-svg"]
        found = [k for k in indicators if k in lower]
        print(f"Preview indicators found: {found}, svg count: {lower.count('<svg')}")
        assert lower.count("<svg") >= 3, "expected multiple SVG charts"
        assert len(found) >= 2, f"expected multiple new-block indicators, got {found}"


# ---------- REGRESSION: M&A engines and misc ----------
class TestRegression:
    def test_fragmentation(self, svc_headers):
        r = requests.get(f"{BASE}/investment-intelligence/fragmentation",
                         params={"cnae_field": "cnae_code", "cnae_value": "4711"},
                         headers=svc_headers, timeout=60)
        assert r.status_code == 200, r.text[:200]

    def test_rollup(self, svc_headers):
        r = requests.get(f"{BASE}/investment-intelligence/rollup-thesis",
                         params={"cnae_field": "cnae_code", "cnae_value": "4711"},
                         headers=svc_headers, timeout=60)
        assert r.status_code == 200, r.text[:200]

    def test_ratios_catalog(self, svc_headers):
        r = requests.get(f"{BASE}/financial-intelligence/ratios/catalog", headers=svc_headers, timeout=30)
        assert r.status_code == 200

    def test_control_synergy(self, jwt_headers):
        r = requests.get(f"{BASE}/data-layer/control-synergy/mc_36c100bcee4a/mc_d06d23d431d7",
                         headers=jwt_headers, timeout=60)
        assert r.status_code == 200, r.text[:200]

    def test_signal_stats_view(self, jwt_headers):
        r = requests.get(f"{BASE}/signal-intelligence/stats/view", headers=jwt_headers, timeout=60)
        assert r.status_code == 200

    def test_signal_ops_view(self, jwt_headers):
        r = requests.get(f"{BASE}/signal-intelligence/opportunities/view", headers=jwt_headers, timeout=60)
        assert r.status_code == 200

    def test_watchlist_post_get(self, jwt_headers):
        payload = {"master_id": COMPANY, "company_id": COMPANY, "note": "TEST_v24"}
        p = requests.post(f"{BASE}/watchlist", json=payload, headers=jwt_headers, timeout=30)
        assert p.status_code in (200, 201), p.text[:200]
        g = requests.get(f"{BASE}/watchlist", headers=jwt_headers, timeout=30)
        assert g.status_code == 200

    def test_iberinform_stats(self, jwt_headers):
        r = requests.get(f"{BASE}/admin/iberinform/stats", headers=jwt_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        print(f"iberinform stats: {j}")

    def test_data_providers_health(self, jwt_headers):
        r = requests.get(f"{BASE}/data-providers/health", headers=jwt_headers, timeout=30)
        assert r.status_code == 200


# ---------- AUTH NEGATIVES ----------
class TestAuthNegatives:
    def test_service_endpoint_rejects_missing_key(self):
        r = requests.get(f"{BASE}/investment-intelligence/fragmentation",
                         params={"cnae_field": "cnae_code", "cnae_value": "4711"}, timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_jwt_endpoint_rejects_missing_token(self):
        r = requests.get(f"{BASE}/signal-intelligence/stats/view", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_docstudio_compose_rejects_missing_token(self):
        r = requests.post(f"{BASE}/docstudio/compose/information-memorandum",
                          params={"company_id": COMPANY}, timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------- CHROMIUM FLAGS regression ----------
class TestChromiumFlags:
    def test_flags_present(self):
        import pathlib
        for name in ["bme_connector.py", "bme_enrichment.py", "datacomex_playwright.py"]:
            p = pathlib.Path("/app/backend/services") / name
            assert p.exists(), f"missing {p}"
            src = p.read_text()
            assert "--disable-dev-shm-usage" in src, f"{name} missing dev-shm flag"
            assert "--no-sandbox" in src, f"{name} missing no-sandbox flag"
