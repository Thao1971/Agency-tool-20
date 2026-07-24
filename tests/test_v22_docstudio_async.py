"""v22 Document Studio unified + ASYNC compose + notifications integration tests."""
import time
import pytest
import requests

BASE = "http://localhost:8001"
API = f"{BASE}/api/v1"

EMAIL = "daniel@wearebudadvisors.com"
PASSWORD = "Thao1971@"
MASTER_ID = "mc_d06d23d431d7"
EXISTING_DOC_ID = "301ebd25-8c55-4c1d-b387-3c7608b32c3e"


def _api_key():
    with open("/app/backend/.env") as f:
        for line in f:
            if line.startswith("ARROBA_SERVICE_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


@pytest.fixture(scope="session")
def jwt():
    r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def hjwt(jwt):
    return {"Authorization": f"Bearer {jwt}"}


@pytest.fixture(scope="session")
def hkey():
    return {"X-API-Key": _api_key()}


def _get_doc(doc_id, hjwt):
    r = requests.get(f"{API}/docstudio/documents/{doc_id}", headers=hjwt, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("document", body)


def _ai_content_ok(doc):
    for s in doc.get("sections", []):
        for b in s.get("blocks", []):
            if b.get("data_lineage", {}).get("source") == "ai":
                if (b.get("data", {}).get("content") or "").strip():
                    return True
    return False


# ═════════ ASYNC COMPOSE (v22 core) ═════════

class TestAsyncCompose:
    def test_compose_async_enqueue_and_poll(self, hjwt):
        payload = {"doc_type": "company_snapshot",
                   "params": {"company_id": MASTER_ID},
                   "brand_id": "brand_bud"}
        r = requests.post(f"{API}/docstudio/compose-async", json=payload, headers=hjwt, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "job_id" in data
        assert "eta_ms" in data
        job_id = data["job_id"]

        completed = None
        for _ in range(90):
            time.sleep(2)
            try:
                jr = requests.get(f"{API}/docstudio/compose-jobs/{job_id}", headers=hjwt, timeout=45)
            except requests.exceptions.ReadTimeout:
                continue
            assert jr.status_code == 200, jr.text
            j = jr.json()
            if j.get("status") in ("done", "error"):
                completed = j
                break
        assert completed is not None, "Job did not complete in 180s"
        assert completed["status"] == "done", completed
        doc_id = completed.get("document_id")
        assert doc_id

        doc = _get_doc(doc_id, hjwt)
        assert doc.get("sections"), f"No sections in doc: {list(doc.keys())}"
        assert _ai_content_ok(doc), "No AI narrative block with non-empty content"

    def test_eta_endpoint(self, hjwt):
        r = requests.get(f"{API}/docstudio/eta", params={"doc_type": "company_snapshot"},
                         headers=hjwt, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["doc_type"] == "company_snapshot"
        assert "eta_ms" in d

    def test_notifications_list(self, hjwt):
        r = requests.get(f"{API}/docstudio/notifications", headers=hjwt, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "notifications" in d and "unread" in d
        assert isinstance(d["notifications"], list)


# ═════════ SYNC COMPOSE REGRESSION ═════════

class TestSyncCompose:
    def test_company_snapshot_with_ai_content(self, hjwt):
        r = requests.post(f"{API}/docstudio/compose/company-snapshot",
                          params={"company_id": MASTER_ID}, headers=hjwt, timeout=120)
        assert r.status_code == 200, r.text
        doc_id = r.json().get("document_id")
        assert doc_id
        doc = _get_doc(doc_id, hjwt)
        assert _ai_content_ok(doc), "No AI narrative content in company-snapshot"


# ═════════ LAYOUT ENDPOINTS ═════════

class TestLayout:
    @pytest.fixture(scope="class")
    def section_id(self):
        # login manually since fixtures scope is class
        r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
        tok = r.json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        doc = _get_doc(EXISTING_DOC_ID, h)
        return doc["sections"][0]["section_id"]

    def test_add_delete_block(self, hjwt, section_id):
        r = requests.post(f"{API}/docstudio/documents/{EXISTING_DOC_ID}/blocks",
                          json={"section_id": section_id, "block_type": "text",
                                "data": {"content": "TEST_v22"}},
                          headers=hjwt, timeout=15)
        assert r.status_code == 200, r.text
        bid = r.json()["block_id"]
        dl = requests.delete(f"{API}/docstudio/documents/{EXISTING_DOC_ID}/blocks/{bid}",
                             headers=hjwt, timeout=10)
        assert dl.status_code == 200

    def test_page_break(self, hjwt, section_id):
        r = requests.post(f"{API}/docstudio/documents/{EXISTING_DOC_ID}/page-break",
                          json={"section_id": section_id}, headers=hjwt, timeout=10)
        assert r.status_code == 200

    def test_brand_overlay(self, hjwt):
        r = requests.put(f"{API}/docstudio/documents/{EXISTING_DOC_ID}/brand-overlay",
                         json={"overlay": {"logo_url": "https://example.com/logo.png"}},
                         headers=hjwt, timeout=10)
        assert r.status_code == 200
        # Clear
        r2 = requests.put(f"{API}/docstudio/documents/{EXISTING_DOC_ID}/brand-overlay",
                          json={"overlay": None}, headers=hjwt, timeout=10)
        assert r2.status_code == 200

    def test_color_override(self, hjwt):
        r = requests.put(f"{API}/docstudio/documents/{EXISTING_DOC_ID}/color-override",
                         json={"colors": {"primary": "#123456"}}, headers=hjwt, timeout=10)
        assert r.status_code == 200


# ═════════ EXPORT ═════════

class TestExport:
    def test_export_pdf(self, hjwt):
        r = requests.get(f"{API}/docstudio/export/{EXISTING_DOC_ID}/pdf",
                         headers=hjwt, timeout=30)
        assert r.status_code == 200
        assert "pdf" in r.headers.get("content-type", "").lower()
        assert len(r.content) > 500

    def test_export_pptx(self, hjwt):
        r = requests.get(f"{API}/docstudio/export/{EXISTING_DOC_ID}/pptx",
                         headers=hjwt, timeout=30)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "").lower()
        assert "presentation" in ct or "pptx" in ct or "officedocument" in ct
        assert len(r.content) > 500


# ═════════ REGRESSION: engines untouched ═════════

class TestRegression:
    def test_signal_stats(self, hjwt):
        r = requests.get(f"{API}/signal-intelligence/stats/view", headers=hjwt, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("total_signals", 0) > 60000
        assert d.get("total_opportunities", 0) >= 100

    def test_opportunities_view(self, hjwt):
        r = requests.get(f"{API}/signal-intelligence/opportunities/view", headers=hjwt, timeout=15)
        assert r.status_code == 200

    def test_fragmentation(self, hkey):
        r = requests.get(f"{API}/investment-intelligence/fragmentation",
                         params={"cnae_field": "cnae_code", "cnae_value": "4711"},
                         headers=hkey, timeout=20)
        assert r.status_code == 200

    def test_ratios_catalog(self, hkey):
        r = requests.get(f"{API}/financial-intelligence/ratios/catalog", headers=hkey, timeout=15)
        assert r.status_code == 200

    def test_watchlist_get(self, hjwt):
        r = requests.get(f"{API}/watchlist", headers=hjwt, timeout=15)
        assert r.status_code == 200

    def test_iberinform_stats(self, hjwt):
        r = requests.get(f"{API}/admin/iberinform/stats", headers=hjwt, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("iberinform", {}).get("real_companies") == 24992

    def test_providers_health(self, hjwt):
        r = requests.get(f"{API}/data-providers/health", headers=hjwt, timeout=15)
        assert r.status_code == 200


# ═════════ AUTH NEGATIVES ═════════

class TestAuthNegatives:
    def test_docstudio_no_jwt(self):
        r = requests.get(f"{API}/docstudio/documents", timeout=10)
        assert r.status_code in (401, 403)

    def test_stats_view_no_jwt(self):
        r = requests.get(f"{API}/signal-intelligence/stats/view", timeout=10)
        assert r.status_code in (401, 403)

    def test_fragmentation_no_key(self):
        r = requests.get(f"{API}/investment-intelligence/fragmentation",
                         params={"cnae_field": "cnae_code", "cnae_value": "4711"}, timeout=10)
        assert r.status_code in (401, 403)
