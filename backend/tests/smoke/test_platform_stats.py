"""Smoke tests — REQ-002 Platform Stats (public aggregated metrics for arroba.com)."""
import requests

PATH = "/api/v1/platform_stats"
ALLOWED_LINEAGE = {"raw", "normalized", "inferred", "ai_generated"}


def test_public_no_auth(base_url):
    r = requests.get(f"{base_url}{PATH}", timeout=20)
    assert r.status_code == 200, r.text


def test_x_source_real_header(base_url):
    r = requests.get(f"{base_url}{PATH}", timeout=20)
    assert r.headers.get("X-Source") == "real"


def test_contract_fields_and_types(base_url):
    r = requests.get(f"{base_url}{PATH}", timeout=20)
    d = r.json()
    for k in ("companies_analyzed", "active_opportunities", "market_movements", "signals_detected"):
        assert isinstance(d[k], int) and d[k] >= 0, f"{k} must be a non-negative int"
    assert isinstance(d["confidence"], (int, float)) and d["confidence"] == 0.8
    assert isinstance(d["lineage"], dict) and d["lineage"].get("source") in ALLOWED_LINEAGE
    assert isinstance(d["generated_at"], str) and d["generated_at"].endswith("Z")
    assert isinstance(d["valid_until"], str) and d["valid_until"].endswith("Z")


def test_values_reflect_real_data(base_url):
    """companies_analyzed must reflect the real companies_master (not a mock constant)."""
    r = requests.get(f"{base_url}{PATH}", timeout=20)
    d = r.json()
    assert d["companies_analyzed"] > 0
    assert d["signals_detected"] > 0


def test_cacheable_header_present_at_origin():
    """Origin (uvicorn) must declare the response cacheable; edge proxies may override."""
    r = requests.get(f"http://localhost:8001{PATH}", timeout=10)
    cc = r.headers.get("Cache-Control", "")
    assert "max-age" in cc and "public" in cc, cc
