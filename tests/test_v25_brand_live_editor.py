"""v25 tests: LIVE brand preview editor + PPTX/PDF regression + brand CRUD + auth negatives."""
import os, re, requests, pytest

BASE = "http://localhost:8001"
LOGIN = {"email": "daniel@wearebudadvisors.com", "password": "Thao1971@"}


def _read_env(key):
    for line in open("/app/backend/.env"):
        line = line.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


API_KEY = _read_env("ARROBA_SERVICE_API_KEY")


@pytest.fixture(scope="module")
def jwt():
    r = requests.post(f"{BASE}/api/v1/auth/login", json=LOGIN, timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def jwt_headers(jwt):
    return {"Authorization": f"Bearer {jwt}"}


# ══════════════════════ LIVE BRAND PREVIEW ══════════════════════
class TestBrandPreviewLive:
    def test_preview_live_full_tokens(self, jwt_headers):
        body = {"brand": {"brand_id": "bud", "tokens": {
            "colors": {"accent": "#E4002B", "primary": "#111111"},
            "fonts": {"heading": "Playfair Display", "body": "Inter"},
            "cover": {"title": "Prueba Marca"}}}}
        r = requests.post(f"{BASE}/api/v1/docstudio/brands/preview-live", json=body, headers=jwt_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "text/html" in r.headers.get("content-type", "")
        html = r.text
        svg_count = html.count("<svg")
        assert svg_count >= 3, f"expected >=3 SVG charts, got {svg_count}"
        assert "#E4002B" in html or "#e4002b" in html.lower(), "accent color missing"
        assert "Playfair Display" in html, "heading font missing"

    def test_preview_live_partial_brand(self, jwt_headers):
        body = {"brand": {"brand_id": "bud", "colors": {"accent": "#00AA55"}}}
        r = requests.post(f"{BASE}/api/v1/docstudio/brands/preview-live", json=body, headers=jwt_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "<svg" in r.text or "<html" in r.text.lower()

    def test_preview_live_requires_jwt(self):
        r = requests.post(f"{BASE}/api/v1/docstudio/brands/preview-live", json={"brand": {"brand_id": "bud"}}, timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


# ══════════════════════ PPTX / PDF regression ══════════════════════
class TestExportRegression:
    @pytest.fixture(scope="class")
    def doc_id(self, jwt_headers):
        r = requests.post(f"{BASE}/api/v1/docstudio/compose/information-memorandum",
                          params={"company_id": "mc_36c100bcee4a"}, headers=jwt_headers, timeout=180)
        assert r.status_code == 200, r.text
        data = r.json()
        did = data.get("document_id") or data.get("id")
        assert did
        return did

    def test_pptx_export(self, jwt_headers, doc_id):
        r = requests.get(f"{BASE}/api/v1/docstudio/export/{doc_id}/pptx", headers=jwt_headers, timeout=180)
        assert r.status_code == 200, r.text[:500]
        ct = r.headers.get("content-type", "")
        assert "presentationml.presentation" in ct, ct
        assert len(r.content) > 20_000, f"size {len(r.content)}"

    def test_pdf_export(self, jwt_headers, doc_id):
        r = requests.get(f"{BASE}/api/v1/docstudio/export/{doc_id}/pdf", headers=jwt_headers, timeout=240)
        assert r.status_code == 200
        assert "pdf" in r.headers.get("content-type", "").lower()
        assert len(r.content) > 300_000, f"pdf too small {len(r.content)}"
        # landscape check
        mb = re.findall(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", r.content)
        assert mb, "no MediaBox"
        w, h = float(mb[0][2]) - float(mb[0][0]), float(mb[0][3]) - float(mb[0][1])
        assert w > h, f"expected landscape got {w}x{h}"


# ══════════════════════ BRAND CRUD PERSIST ══════════════════════
class TestBrandCRUD:
    def test_list_and_update_brand(self, jwt_headers):
        r = requests.get(f"{BASE}/api/v1/documents/brands", headers=jwt_headers, timeout=15)
        assert r.status_code == 200, r.text
        brands = r.json()
        if isinstance(brands, dict):
            brands = brands.get("brands") or brands.get("items") or []
        assert brands, "no brands"
        # find BUD
        bud = next((b for b in brands if str(b.get("brand_id", b.get("id", ""))).lower().startswith("bud")), brands[0])
        bid = bud.get("brand_id") or bud.get("id") or bud.get("_id")
        assert bid

        # get single
        rg = requests.get(f"{BASE}/api/v1/documents/brands/{bid}", headers=jwt_headers, timeout=15)
        assert rg.status_code == 200, rg.text
        original = rg.json()

        # deep copy + change accent + heading font
        import copy
        payload = copy.deepcopy(original)
        payload.pop("_id", None)
        tokens = payload.setdefault("tokens", {})
        colors = tokens.setdefault("colors", {})
        fonts = tokens.setdefault("fonts", {})
        prev_accent = colors.get("accent")
        prev_head = fonts.get("heading")
        new_accent = "#AB12CD" if prev_accent != "#AB12CD" else "#123456"
        new_head = "Montserrat" if prev_head != "Montserrat" else "Inter"
        colors["accent"] = new_accent
        fonts["heading"] = new_head

        rp = requests.put(f"{BASE}/api/v1/documents/brands/{bid}", json=payload, headers=jwt_headers, timeout=20)
        assert rp.status_code == 200, rp.text

        # verify persist
        rg2 = requests.get(f"{BASE}/api/v1/documents/brands/{bid}", headers=jwt_headers, timeout=15)
        assert rg2.status_code == 200
        d2 = rg2.json()
        t2 = d2.get("tokens", {})
        assert t2.get("colors", {}).get("accent") == new_accent, "accent not persisted"
        assert t2.get("fonts", {}).get("heading") == new_head, "heading font not persisted"

        # restore if previously set
        if prev_accent:
            colors["accent"] = prev_accent
        if prev_head:
            fonts["heading"] = prev_head
        requests.put(f"{BASE}/api/v1/documents/brands/{bid}", json=payload, headers=jwt_headers, timeout=20)


# ══════════════════════ M&A regression ══════════════════════
class TestMAEndpoints:
    def test_fragmentation(self):
        r = requests.get(f"{BASE}/api/v1/investment-intelligence/fragmentation",
                         params={"cnae_field": "cnae_code", "cnae_value": "4711"},
                         headers={"X-API-Key": API_KEY}, timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_ratios_catalog(self):
        r = requests.get(f"{BASE}/api/v1/financial-intelligence/ratios/catalog",
                         headers={"X-API-Key": API_KEY}, timeout=15)
        assert r.status_code == 200

    def test_signal_stats(self, jwt_headers):
        r = requests.get(f"{BASE}/api/v1/signal-intelligence/stats/view", headers=jwt_headers, timeout=15)
        assert r.status_code == 200

    def test_signal_opportunities(self, jwt_headers):
        r = requests.get(f"{BASE}/api/v1/signal-intelligence/opportunities/view", headers=jwt_headers, timeout=30)
        assert r.status_code == 200

    def test_iberinform_stats(self, jwt_headers):
        r = requests.get(f"{BASE}/api/v1/admin/iberinform/stats", headers=jwt_headers, timeout=20)
        assert r.status_code == 200
        d = r.json()
        # tolerate different key structures
        s = str(d)
        assert "24992" in s or "24,992" in s, s[:300]

    def test_data_providers_health(self, jwt_headers):
        r = requests.get(f"{BASE}/api/v1/data-providers/health", headers=jwt_headers, timeout=30)
        assert r.status_code == 200

    def test_watchlist_flow(self, jwt_headers):
        body = {"master_id": "mc_36c100bcee4a", "note": "TEST_v25"}
        r = requests.post(f"{BASE}/api/v1/watchlist", json=body, headers=jwt_headers, timeout=15)
        assert r.status_code in (200, 201), r.text
        rg = requests.get(f"{BASE}/api/v1/watchlist", headers=jwt_headers, timeout=15)
        assert rg.status_code == 200


# ══════════════════════ AUTH NEGATIVES ══════════════════════
class TestAuthNegatives:
    def test_stats_view_no_jwt(self):
        r = requests.get(f"{BASE}/api/v1/signal-intelligence/stats/view", timeout=10)
        assert r.status_code in (401, 403)

    def test_watchlist_no_jwt(self):
        r = requests.get(f"{BASE}/api/v1/watchlist", timeout=10)
        assert r.status_code in (401, 403)

    def test_fragmentation_no_apikey(self):
        r = requests.get(f"{BASE}/api/v1/investment-intelligence/fragmentation",
                         params={"cnae_field": "cnae_code", "cnae_value": "4711"}, timeout=10)
        assert r.status_code in (401, 403)

    def test_ratios_bad_apikey(self):
        r = requests.get(f"{BASE}/api/v1/financial-intelligence/ratios/catalog",
                         headers={"X-API-Key": "bad"}, timeout=10)
        assert r.status_code in (401, 403)
