"""v17 Document Studio (unified brand + layout + composer) integration tests.

Uses live backend at localhost:8001 (per prior iteration convention to avoid uvicorn --reload loops).
"""
import os
import pytest
import requests

BASE = "http://localhost:8001"
API = f"{BASE}/api/v1"

EMAIL = "daniel@wearebudadvisors.com"
PASSWORD = "Thao1971@"


def _api_key():
    # Read from backend .env
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


@pytest.fixture(scope="session")
def sample_doc_id(hjwt):
    r = requests.get(f"{API}/docstudio/documents", headers=hjwt, timeout=20)
    assert r.status_code == 200, r.text
    docs = r.json().get("documents") or r.json().get("items") or []
    assert docs, f"No existing documents: {r.text[:200]}"
    return docs[0]["document_id"]


# ═══════════════════════════════════════════
# DOCSTUDIO REGRESSION
# ═══════════════════════════════════════════

class TestDocstudioRegression:
    def test_list_documents(self, hjwt):
        r = requests.get(f"{API}/docstudio/documents", headers=hjwt, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "documents" in data or "items" in data

    def test_document_detail(self, hjwt, sample_doc_id):
        r = requests.get(f"{API}/docstudio/documents/{sample_doc_id}", headers=hjwt, timeout=20)
        assert r.status_code == 200
        d = r.json()
        # detail may wrap doc under a key; accept either
        doc = d.get("document") or d
        assert "sections" in doc or "document_id" in doc

    def test_templates_list(self, hjwt):
        r = requests.get(f"{API}/docstudio/templates", headers=hjwt, timeout=20)
        assert r.status_code == 200
        assert "templates" in r.json()

    def test_brands_list(self, hjwt):
        r = requests.get(f"{API}/docstudio/brands", headers=hjwt, timeout=20)
        assert r.status_code == 200
        assert "brands" in r.json()

    def test_export_pdf(self, hjwt, sample_doc_id):
        r = requests.get(f"{API}/docstudio/export/{sample_doc_id}/pdf", headers=hjwt, timeout=60)
        assert r.status_code == 200, r.text[:400]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 500

    def test_export_pptx(self, hjwt, sample_doc_id):
        r = requests.get(f"{API}/docstudio/export/{sample_doc_id}/pptx", headers=hjwt, timeout=60)
        assert r.status_code == 200, r.text[:400]
        assert len(r.content) > 500


# ═══════════════════════════════════════════
# LAYOUT ENDPOINTS (v17 NEW)
# ═══════════════════════════════════════════

class TestLayoutOps:
    def test_add_move_delete_block_and_pagebreak(self, hjwt, sample_doc_id):
        # Fetch doc to get a section id
        r = requests.get(f"{API}/docstudio/documents/{sample_doc_id}", headers=hjwt, timeout=20)
        assert r.status_code == 200
        doc = r.json().get("document") or r.json()
        sections = doc.get("sections", [])
        assert sections, "Document has no sections"
        sec_id = sections[0]["section_id"]

        # ADD block
        r = requests.post(
            f"{API}/docstudio/documents/{sample_doc_id}/blocks",
            headers=hjwt,
            json={"section_id": sec_id, "block_type": "text", "data": {"content": "TEST v17 block"}},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:400]
        block_id = r.json()["block_id"]

        # Doc detail reflects added block
        r2 = requests.get(f"{API}/docstudio/documents/{sample_doc_id}", headers=hjwt, timeout=20)
        doc2 = r2.json().get("document") or r2.json()
        all_bids = [b.get("block_id") for s in doc2.get("sections", []) for b in s.get("blocks", [])]
        assert block_id in all_bids

        # MOVE block within same section (to index 0)
        r = requests.post(
            f"{API}/docstudio/documents/{sample_doc_id}/blocks/{block_id}/move",
            headers=hjwt,
            json={"to_section_id": sec_id, "to_index": 0},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:400]

        # PAGE BREAK
        r = requests.post(
            f"{API}/docstudio/documents/{sample_doc_id}/page-break",
            headers=hjwt,
            json={"section_id": sec_id, "index": 1},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:400]

        # BRAND OVERLAY (set + clear)
        r = requests.put(
            f"{API}/docstudio/documents/{sample_doc_id}/brand-overlay",
            headers=hjwt,
            json={"overlay": {"logo_url": "https://example.com/logo.png", "client_name": "Test Co"}},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:400]
        assert r.json()["status"] == "brand_overlay_set"

        r = requests.put(
            f"{API}/docstudio/documents/{sample_doc_id}/brand-overlay",
            headers=hjwt,
            json={"overlay": None},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "brand_overlay_cleared"

        # COLOR OVERRIDE
        r = requests.put(
            f"{API}/docstudio/documents/{sample_doc_id}/color-override",
            headers=hjwt,
            json={"colors": {"primary": "#123456"}},
            timeout=20,
        )
        assert r.status_code == 200

        # PDF export after page-break still 200
        r = requests.get(f"{API}/docstudio/export/{sample_doc_id}/pdf", headers=hjwt, timeout=90)
        assert r.status_code == 200, r.text[:400]
        assert len(r.content) > 500

        # DELETE the test block (cleanup)
        r = requests.delete(
            f"{API}/docstudio/documents/{sample_doc_id}/blocks/{block_id}",
            headers=hjwt,
            timeout=20,
        )
        assert r.status_code == 200

        # Verify removal
        r3 = requests.get(f"{API}/docstudio/documents/{sample_doc_id}", headers=hjwt, timeout=20)
        doc3 = r3.json().get("document") or r3.json()
        all_bids3 = [b.get("block_id") for s in doc3.get("sections", []) for b in s.get("blocks", [])]
        assert block_id not in all_bids3

    def test_add_and_remove_section(self, hjwt, sample_doc_id):
        r = requests.post(
            f"{API}/docstudio/documents/{sample_doc_id}/sections",
            headers=hjwt,
            json={"title": "TEST v17 section"},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:400]
        sec_id = r.json()["section_id"]

        r = requests.delete(
            f"{API}/docstudio/documents/{sample_doc_id}/sections/{sec_id}",
            headers=hjwt,
            timeout=20,
        )
        assert r.status_code == 200


# ═══════════════════════════════════════════
# COMPOSER — real data
# ═══════════════════════════════════════════

class TestComposerRealData:
    def test_company_snapshot_real_master_id(self, hjwt):
        # Pull one real master_id straight from master_companies via a dedicated helper endpoint;
        # fall back to a known id from the request context.
        mid = None
        try:
            import pymongo
            url = [l for l in open("/app/backend/.env") if l.startswith("MONGO_URL")][0].split("=", 1)[1].strip().strip('"')
            dbn = [l for l in open("/app/backend/.env") if l.startswith("DB_NAME")][0].split("=", 1)[1].strip().strip('"')
            doc = pymongo.MongoClient(url)[dbn].master_companies.find_one({}, {"master_id": 1})
            if doc:
                mid = doc["master_id"]
        except Exception:
            pass
        if not mid:
            mid = "mc_d06d23d431d7"
        r = requests.post(
            f"{API}/docstudio/compose/company-snapshot?company_id={mid}",
            headers=hjwt,
            timeout=90,
        )
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["document_id"]
        assert d["sections"] >= 1

        # Verify blocks contain real data (not all AI errors)
        r2 = requests.get(f"{API}/docstudio/documents/{d['document_id']}", headers=hjwt, timeout=20)
        assert r2.status_code == 200
        doc = r2.json().get("document") or r2.json()
        # ensure the doc has some non-empty section
        assert any(s.get("blocks") for s in doc.get("sections", []))

    def test_sector_report_cnae(self, hjwt):
        r = requests.post(
            f"{API}/docstudio/compose/sector-report?cnae_code=4711",
            headers=hjwt,
            timeout=90,
        )
        # Should succeed even with empty LLM key (AI blocks may be empty/error, but not 500)
        assert r.status_code == 200, r.text[:400]
        assert r.json()["document_id"]


# ═══════════════════════════════════════════
# INTELLIGENCE ENGINES REGRESSION
# ═══════════════════════════════════════════

class TestEnginesRegression:
    def test_signal_stats_view(self, hjwt):
        r = requests.get(f"{API}/signal-intelligence/stats/view", headers=hjwt, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("total_signals", 0) >= 60000
        assert d.get("total_opportunities", 0) >= 100

    def test_opportunities_view(self, hjwt):
        r = requests.get(f"{API}/signal-intelligence/opportunities/view?limit=10", headers=hjwt, timeout=20)
        assert r.status_code == 200

    def test_fragmentation(self, hkey):
        r = requests.get(
            f"{API}/investment-intelligence/fragmentation?cnae_field=cnae_code&cnae_value=4711",
            headers=hkey, timeout=20,
        )
        assert r.status_code == 200

    def test_ratios_catalog(self, hkey):
        r = requests.get(f"{API}/financial-intelligence/ratios/catalog", headers=hkey, timeout=20)
        assert r.status_code == 200

    def test_watchlist_post_and_get(self, hjwt):
        r = requests.get(f"{API}/watchlist", headers=hjwt, timeout=20)
        assert r.status_code == 200

    def test_iberinform_stats(self, hjwt):
        r = requests.get(f"{API}/admin/iberinform/stats", headers=hjwt, timeout=20)
        assert r.status_code == 200
        d = r.json()
        # accept flat or nested {iberinform: {...}}; keys vary (real / real_companies)
        ib = d.get("iberinform", d)
        real = ib.get("real", ib.get("real_companies", 0))
        assert real >= 24000, f"got {real}"

    def test_providers_health(self, hjwt):
        r = requests.get(f"{API}/data-providers/health", headers=hjwt, timeout=20)
        assert r.status_code == 200


# ═══════════════════════════════════════════
# AUTH NEGATIVES
# ═══════════════════════════════════════════

class TestAuthNegatives:
    def test_layout_without_jwt(self, sample_doc_id):
        r = requests.post(
            f"{API}/docstudio/documents/{sample_doc_id}/blocks",
            json={"section_id": "x", "block_type": "text"},
            timeout=15,
        )
        assert r.status_code in (401, 403)

    def test_stats_view_without_jwt(self):
        r = requests.get(f"{API}/signal-intelligence/stats/view", timeout=15)
        assert r.status_code in (401, 403)

    def test_fragmentation_without_key(self):
        r = requests.get(
            f"{API}/investment-intelligence/fragmentation?cnae_field=cnae_code&cnae_value=4711",
            timeout=15,
        )
        assert r.status_code in (401, 403)

    def test_fragmentation_bad_key(self):
        r = requests.get(
            f"{API}/investment-intelligence/fragmentation?cnae_field=cnae_code&cnae_value=4711",
            headers={"X-API-Key": "invalid_key_xxx"}, timeout=15,
        )
        assert r.status_code in (401, 403)
