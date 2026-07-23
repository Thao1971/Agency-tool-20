"""Final data-integrity verification after purge operations.

Verifies:
- companies_master, master_companies, iberinform_companies all == 24992
- companies_master cif set == iberinform_companies cif set
- master_companies cif set == iberinform_companies cif set
- master_companies has no duplicate master_id or cif_normalized
- No synthetic remnants in iberinform_companies / iberinform_financials
- Backend health endpoint returns 200
"""
import os
import requests
import pytest
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
BASE_URL = "http://localhost:8001"

EXPECTED = 24992


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


def test_companies_master_count(db):
    c = db.companies_master.count_documents({})
    print(f"companies_master count: {c}")
    assert c == EXPECTED, f"expected {EXPECTED}, got {c}"


def test_master_companies_count(db):
    c = db.master_companies.count_documents({})
    print(f"master_companies count: {c}")
    assert c == EXPECTED, f"expected {EXPECTED}, got {c}"


def test_iberinform_companies_count(db):
    c = db.iberinform_companies.count_documents({})
    print(f"iberinform_companies count: {c}")
    assert c == EXPECTED, f"expected {EXPECTED}, got {c}"


def test_companies_master_cif_set_equals_iberinform(db):
    real = set(d["cif_normalized"] for d in db.iberinform_companies.find({}, {"cif_normalized": 1}) if d.get("cif_normalized"))
    legacy = set(d["cif_normalized"] for d in db.companies_master.find({}, {"cif_normalized": 1}) if d.get("cif_normalized"))
    print(f"real={len(real)} legacy={len(legacy)}")
    diff_legacy_extra = legacy - real
    diff_real_missing = real - legacy
    print(f"legacy_extra={len(diff_legacy_extra)} real_missing_from_legacy={len(diff_real_missing)}")
    assert legacy == real, f"mismatch: extra_in_legacy={len(diff_legacy_extra)}, missing_from_legacy={len(diff_real_missing)}"


def test_master_companies_cif_set_equals_iberinform(db):
    real = set(d["cif_normalized"] for d in db.iberinform_companies.find({}, {"cif_normalized": 1}) if d.get("cif_normalized"))
    modern = set(d["cif_normalized"] for d in db.master_companies.find({}, {"cif_normalized": 1}) if d.get("cif_normalized"))
    print(f"real={len(real)} modern={len(modern)}")
    diff_modern_extra = modern - real
    diff_real_missing = real - modern
    print(f"modern_extra={len(diff_modern_extra)} real_missing_from_modern={len(diff_real_missing)}")
    assert modern == real, f"mismatch: extra_in_modern={len(diff_modern_extra)}, missing_from_modern={len(diff_real_missing)}"


def test_master_companies_no_duplicate_master_id(db):
    pipeline = [
        {"$group": {"_id": "$master_id", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
    ]
    dups = list(db.master_companies.aggregate(pipeline))
    print(f"duplicate master_ids: {len(dups)}")
    assert len(dups) == 0


def test_master_companies_no_duplicate_cif_normalized(db):
    pipeline = [
        {"$group": {"_id": "$cif_normalized", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
    ]
    dups = list(db.master_companies.aggregate(pipeline))
    print(f"duplicate cif_normalized: {len(dups)}")
    assert len(dups) == 0


def test_no_synthetic_iberinform_companies(db):
    c = db.iberinform_companies.count_documents({"source": "iberinform_synthetic"})
    c2 = db.iberinform_companies.count_documents({"data_source": "iberinform_synthetic"})
    print(f"iberinform_companies synthetic source={c} data_source={c2}")
    assert c == 0 and c2 == 0


def test_no_synthetic_iberinform_financials(db):
    c = db.iberinform_financials.count_documents({"source": "iberinform_synthetic"})
    c2 = db.iberinform_financials.count_documents({"data_source": "iberinform_synthetic"})
    print(f"iberinform_financials synthetic source={c} data_source={c2}")
    assert c == 0 and c2 == 0


def test_health_endpoint():
    r = requests.get(f"{BASE_URL}/api/v1/health", timeout=10)
    print(f"health status={r.status_code} body={r.text[:200]}")
    assert r.status_code == 200
