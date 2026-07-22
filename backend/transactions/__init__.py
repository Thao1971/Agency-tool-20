"""Transaction Intelligence — Models, constants, normalization."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from models import new_id, now_iso
import re
import unicodedata
import hashlib
import json
from difflib import SequenceMatcher


# ── Constants ──
TX_STATUSES = ["completed", "ongoing", "cancelled", "unknown"]
TX_TYPES = ["takeover", "private_equity", "venture_capital", "asset_acquisition", "minority_stake", "merger", "other"]
BUYER_TYPES = ["strategic", "financial", "private_equity", "venture_capital", "private_shareholders", "unknown"]
CONFIDENCE_LEVELS = ["low", "medium", "high"]
SOURCE_TYPES = ["press_article", "press_release", "company_website", "borme", "linkedin", "database", "internal_research", "other"]
AMOUNT_STATUSES = ["confirmed", "estimated", "approximate", "rumored", "undisclosed"]
VALUATION_BASES = ["enterprise_value", "equity_value", "investment_amount", "post_money_valuation", "minority_stake_price", "asset_value", "unknown"]
WITHDRAWAL_REASONS = ["incorrect_information", "duplicate_operation", "unconfirmed_operation", "out_of_scope", "import_error", "other"]
CIS_SYNC_STATUSES = ["not_published", "ready_for_cis", "approved_for_cis", "pending_update", "removed_from_cis"]

# Fields that trigger pending_update when changed on a published tx
CIS_CRITICAL_FIELDS = {
    "target_name", "buyer_name", "seller_name", "announcement_date", "transaction_type",
    "cis_category_suggested", "cis_subcategory_suggested", "value_eurm", "amount_status",
    "valuation_basis", "ve_sales", "ve_ebitda", "revenue_eurm", "ebitda_eurm",
    "ev_eurm", "summary", "strategic_rationale", "geography_primary",
}

VISIBLE_STATES = [
    "draft", "incomplete", "needs_review", "ready_for_cis",
    "published_in_cis", "pending_sync", "withdrawn_from_cis", "archived",
]

STATUS_MAP = {
    "completed": "completed", "cerrada": "completed", "closed": "completed", "done": "completed",
    "ongoing": "ongoing", "en curso": "ongoing", "pending": "ongoing", "announced": "ongoing",
    "cancelled": "cancelled", "cancelada": "cancelled", "withdrawn": "cancelled",
}

TYPE_MAP = {
    "takeover": "takeover", "adquisición": "takeover", "acquisition": "takeover", "take over": "takeover",
    "privateequity": "private_equity", "private equity": "private_equity", "pe": "private_equity",
    "venturecapital": "venture_capital", "venture capital": "venture_capital", "vc": "venture_capital",
    "assetacquisition": "asset_acquisition", "asset deal": "asset_acquisition", "asset acquisition": "asset_acquisition",
    "minoritystake": "minority_stake", "minority stake": "minority_stake", "participación minoritaria": "minority_stake",
    "merger": "merger", "fusión": "merger", "fusion": "merger",
}


# ── Request Models ──
class TransactionCreate(BaseModel):
    announcement_date: Optional[str] = None
    conclusion_date: Optional[str] = None
    status: str = "unknown"
    target_name: Optional[str] = None
    buyer_name: Optional[str] = None
    seller_name: Optional[str] = None
    transaction_type: str = "other"
    buyer_type: str = "unknown"
    geography_primary: Optional[str] = None
    geographies: Optional[List[str]] = None
    is_cross_border: bool = False
    value_raw: Optional[str] = None
    value_eurm: Optional[float] = None
    value_disclosed: bool = False
    approximate_value: bool = False
    amount_status: str = "undisclosed"
    valuation_basis: str = "unknown"
    stake_acquired_percent: Optional[float] = None
    includes_debt: Optional[bool] = None
    includes_earnout: Optional[bool] = None
    is_full_company_acquisition: Optional[bool] = None
    revenue_eurm: Optional[float] = None
    ebitda_eurm: Optional[float] = None
    ev_eurm: Optional[float] = None
    ve_sales: Optional[float] = None
    ve_ebitda: Optional[float] = None
    multiple_quality: Optional[str] = None
    multiple_notes: Optional[str] = None
    financial_year_used: Optional[str] = None
    sector_original: Optional[str] = None
    sector_original_code: Optional[str] = None
    sector_original_label: Optional[str] = None
    cis_category_suggested: Optional[str] = None
    cis_subcategory_suggested: Optional[str] = None
    outside_cis_taxonomy: bool = False
    source: Optional[str] = None
    source_url: Optional[str] = None
    summary: Optional[str] = None
    strategic_rationale: Optional[str] = None
    editorial_notes: Optional[str] = None
    observations: Optional[str] = None
    internal_notes: Optional[str] = None
    confidence_level: str = "medium"


class TransactionUpdate(BaseModel):
    announcement_date: Optional[str] = None
    conclusion_date: Optional[str] = None
    status: Optional[str] = None
    target_name: Optional[str] = None
    buyer_name: Optional[str] = None
    seller_name: Optional[str] = None
    transaction_type: Optional[str] = None
    buyer_type: Optional[str] = None
    geography_primary: Optional[str] = None
    value_raw: Optional[str] = None
    value_eurm: Optional[float] = None
    value_disclosed: Optional[bool] = None
    approximate_value: Optional[bool] = None
    amount_status: Optional[str] = None
    valuation_basis: Optional[str] = None
    stake_acquired_percent: Optional[float] = None
    includes_debt: Optional[bool] = None
    includes_earnout: Optional[bool] = None
    is_full_company_acquisition: Optional[bool] = None
    revenue_eurm: Optional[float] = None
    ebitda_eurm: Optional[float] = None
    ev_eurm: Optional[float] = None
    ve_sales: Optional[float] = None
    ve_ebitda: Optional[float] = None
    multiple_quality: Optional[str] = None
    multiple_notes: Optional[str] = None
    financial_year_used: Optional[str] = None
    sector_original: Optional[str] = None
    cis_category_suggested: Optional[str] = None
    cis_subcategory_suggested: Optional[str] = None
    outside_cis_taxonomy: Optional[bool] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    summary: Optional[str] = None
    strategic_rationale: Optional[str] = None
    editorial_notes: Optional[str] = None
    observations: Optional[str] = None
    internal_notes: Optional[str] = None
    confidence_level: Optional[str] = None
    review_status: Optional[str] = None
    publish_status: Optional[str] = None


class SourceCreate(BaseModel):
    title: Optional[str] = None
    publisher: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[str] = None
    source_type: str = "press_article"
    is_primary: bool = False
    summary: Optional[str] = None
    notes: Optional[str] = None


class SourceUpdate(BaseModel):
    title: Optional[str] = None
    publisher: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[str] = None
    source_type: Optional[str] = None
    is_primary: Optional[bool] = None
    summary: Optional[str] = None
    notes: Optional[str] = None


# ── Normalization ──
def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.strip()
    n = unicodedata.normalize('NFD', n)
    n = ''.join(c for c in n if unicodedata.category(c) != 'Mn')
    n = n.lower()
    for suffix in [' sl', ' s.l.', ' sa', ' s.a.', ' slu', ' s.l.u.', ' ltd', ' limited', ' inc', ' llc', ' gmbh', ' ag', ' bv', ' nv']:
        if n.endswith(suffix):
            n = n[:-len(suffix)]
    n = re.sub(r'[.,;:\-\'\"()\[\]]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def normalize_status(raw: str) -> str:
    if not raw: return "unknown"
    return STATUS_MAP.get(raw.strip().lower(), "unknown")


def normalize_type(raw: str) -> str:
    if not raw: return "other"
    return TYPE_MAP.get(raw.strip().lower().replace("_", ""), "other")


def parse_float(val) -> Optional[float]:
    if val is None: return None
    if isinstance(val, (int, float)): return float(val)
    s = str(val).strip().replace(",", ".").replace(" ", "")
    if s.upper() in ("ND", "N/D", "N.A.", "NA", "", "-", "UNKNOWN"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(val) -> Optional[str]:
    if val is None: return None
    if hasattr(val, 'isoformat'): return val.isoformat()[:10]
    s = str(val).strip()[:10]
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s): return s
    return s if s else None


def make_transaction_key(target: str, buyer: str, date: str, tx_type: str = "") -> str:
    parts = [normalize_name(target or ""), normalize_name(buyer or ""), (date or "")[:7], normalize_type(tx_type)]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def normalize_transaction(raw: Dict) -> Dict:
    """Normalize a raw transaction dict into clean fields."""
    target = raw.get("target") or raw.get("target_name") or ""
    buyer = raw.get("buyer") or raw.get("buyer_name") or ""
    seller = raw.get("seller") or raw.get("seller_name") or ""
    ann_date = parse_date(raw.get("announcement_date"))
    conc_date = parse_date(raw.get("conclusion_date"))
    val_eurm = parse_float(raw.get("value_eurm"))

    return {
        "announcement_date": ann_date,
        "conclusion_date": conc_date,
        "year": int(ann_date[:4]) if ann_date and len(ann_date) >= 4 else None,
        "status": normalize_status(raw.get("status")),
        "status_raw": raw.get("status"),
        "target_name": target,
        "target_name_normalized": normalize_name(target),
        "buyer_name": buyer,
        "buyer_name_normalized": normalize_name(buyer),
        "seller_name": seller,
        "seller_name_normalized": normalize_name(seller),
        "transaction_type": normalize_type(raw.get("transaction_type")),
        "transaction_type_raw": raw.get("transaction_type"),
        "buyer_type": raw.get("buyer_type", "unknown"),
        "buyer_type_raw": raw.get("buyer_type"),
        "geography_primary": raw.get("geography_primary"),
        "geography_raw": raw.get("geography_detail_raw"),
        "geographies": raw.get("geographies", []),
        "is_cross_border": raw.get("is_cross_border", False),
        "value_raw": raw.get("value_raw"),
        "value_eurm": val_eurm,
        "value_disclosed": bool(val_eurm) if raw.get("value_disclosed") is None else raw.get("value_disclosed"),
        "approximate_value": raw.get("approximate_value", False),
        "amount_status": raw.get("amount_status", "undisclosed" if not val_eurm else "confirmed"),
        "valuation_basis": raw.get("valuation_basis", "unknown"),
        "stake_acquired_percent": parse_float(raw.get("stake_acquired_percent")),
        "includes_debt": raw.get("includes_debt"),
        "includes_earnout": raw.get("includes_earnout"),
        "is_full_company_acquisition": raw.get("is_full_company_acquisition"),
        "revenue_eurm": parse_float(raw.get("revenue_eurm")),
        "ebitda_eurm": parse_float(raw.get("ebitda_eurm")),
        "ev_eurm": parse_float(raw.get("ev_eurm")),
        "ve_sales": parse_float(raw.get("ve_sales")),
        "ve_ebitda": parse_float(raw.get("ve_ebitda")),
        "multiple_quality": raw.get("multiple_quality"),
        "multiple_notes": raw.get("multiple_notes"),
        "financial_year_used": raw.get("financial_year_used"),
        "sector_original": raw.get("sector_target") or raw.get("sector_original"),
        "sector_original_code": raw.get("sector_original_code"),
        "sector_original_label": raw.get("sector_original_label") or raw.get("subsector_objective"),
        "cis_category_suggested": raw.get("cis_category_suggested"),
        "cis_subcategory_suggested": raw.get("cis_subcategory_suggested"),
        "outside_cis_taxonomy": raw.get("outside_cis_taxonomy", False),
        "summary": raw.get("summary") or raw.get("observations"),
        "strategic_rationale": raw.get("strategic_rationale"),
        "editorial_notes": raw.get("editorial_notes") or raw.get("review_notes") or raw.get("internal_notes"),
        "observations": raw.get("observations"),
        "internal_notes": raw.get("review_notes") or raw.get("internal_notes"),
        "source": raw.get("source"),
        "confidence_level": raw.get("confidence_level", "medium"),
        "normalization_status": "completed",
        "transaction_key": make_transaction_key(target, buyer, ann_date, raw.get("transaction_type")),
    }


# ── Deduplication ──
def calculate_similarity(a: Dict, b: Dict) -> Dict:
    """Compare two normalized transactions for similarity."""
    target_sim = SequenceMatcher(None, a.get("target_name_normalized", ""), b.get("target_name_normalized", "")).ratio()
    buyer_sim = SequenceMatcher(None, a.get("buyer_name_normalized", ""), b.get("buyer_name_normalized", "")).ratio()
    seller_sim = SequenceMatcher(None, a.get("seller_name_normalized", ""), b.get("seller_name_normalized", "")).ratio() if a.get("seller_name_normalized") and b.get("seller_name_normalized") else 0

    date_dist = 999
    if a.get("announcement_date") and b.get("announcement_date"):
        try:
            from datetime import datetime
            da = datetime.fromisoformat(a["announcement_date"])
            db = datetime.fromisoformat(b["announcement_date"])
            date_dist = abs((da - db).days)
        except:
            pass

    type_compat = a.get("transaction_type") == b.get("transaction_type")
    score = (target_sim * 0.4 + buyer_sim * 0.3 + (1 if date_dist <= 30 else 0) * 0.2 + (1 if type_compat else 0) * 0.1)

    reasons = []
    if target_sim >= 0.85: reasons.append(f"target_similar({target_sim:.2f})")
    if buyer_sim >= 0.85: reasons.append(f"buyer_similar({buyer_sim:.2f})")
    if date_dist <= 30: reasons.append(f"date_close({date_dist}d)")
    if type_compat: reasons.append("type_match")

    recommendation = "do_not_merge"
    if target_sim >= 0.95 and buyer_sim >= 0.95 and date_dist <= 30:
        recommendation = "merge"
    elif target_sim >= 0.85 and buyer_sim >= 0.70 and date_dist <= 60:
        recommendation = "review"
    elif target_sim >= 0.85 and date_dist <= 30:
        recommendation = "review"

    return {
        "similarity_score": round(score, 3),
        "similarity_reasons": reasons,
        "target_similarity": round(target_sim, 3),
        "buyer_similarity": round(buyer_sim, 3),
        "seller_similarity": round(seller_sim, 3),
        "date_distance_days": date_dist,
        "transaction_type_compatible": type_compat,
        "recommendation": recommendation,
    }


# ── Visible Status (computed, not persisted) ──
async def compute_visible_status(tx: Dict, db) -> str:
    """Compute user-facing visible status from technical states."""
    if tx.get("deleted"):
        return "archived"

    ps = tx.get("publish_status", "not_published")
    sync = tx.get("cis_sync_status")

    # Published states (approved_for_cis OR visible_in_cis)
    if ps == "approved_for_cis" or tx.get("visible_in_cis"):
        if sync == "pending_update":
            return "pending_sync"
        return "published_in_cis"

    if ps == "removed_from_cis":
        return "withdrawn_from_cis"

    # Manually marked as ready
    if ps == "ready_to_publish":
        return "ready_for_cis"

    # Check if ready for CIS (validation would pass)
    has_target = bool(tx.get("target_name"))
    has_date = bool(tx.get("announcement_date") or tx.get("year"))
    has_type = bool(tx.get("transaction_type") and tx["transaction_type"] != "other")
    has_category = bool(tx.get("cis_category_suggested") or tx.get("outside_cis_taxonomy"))
    has_review = tx.get("review_status") in ("reviewed", "approved")
    has_dedupe = tx.get("dedupe_status") not in ("possible_duplicate",)

    # Check sources
    src_count = await db.transaction_sources.count_documents({"transaction_id": tx["transaction_id"]})
    has_source_new = src_count > 0
    has_source_legacy = bool(tx.get("source") or tx.get("source_url"))
    has_source = has_source_new or has_source_legacy

    has_primary = False
    if has_source_new:
        has_primary = await db.transaction_sources.count_documents(
            {"transaction_id": tx["transaction_id"], "is_primary": True}
        ) > 0
    elif has_source_legacy:
        has_primary = True

    # Check entity
    target_link = await db.transaction_company_links.find_one(
        {"transaction_id": tx["transaction_id"], "entity_role": "target",
         "match_status": {"$in": ["manual_confirmed", "auto_strong_candidate", "needs_new_company", "external_entity"]}},
        {"_id": 0}
    )
    has_entity = target_link is not None

    has_summary = bool(tx.get("summary"))

    all_ok = all([has_target, has_date, has_type, has_category, has_source,
                  has_primary, has_review, has_dedupe, has_entity, has_summary])

    if all_ok:
        return "ready_for_cis"

    # Needs review? (has issues)
    issues = []
    if tx.get("dedupe_status") == "possible_duplicate":
        issues.append("duplicate")
    if tx.get("matching_status") == "needs_review":
        issues.append("entity")
    if not has_category:
        issues.append("category")
    if not has_source:
        issues.append("source")
    if has_review and not all_ok:
        issues.append("validation")

    if issues or has_review:
        return "needs_review"

    # Incomplete (missing basic fields)
    if not has_target or not has_date:
        return "incomplete"

    return "draft"


# Country translation map
COUNTRY_ES = {
    "spain": "España", "mexico": "México", "united states": "Estados Unidos",
    "united kingdom": "Reino Unido", "france": "Francia", "germany": "Alemania",
    "italy": "Italia", "portugal": "Portugal", "brazil": "Brasil",
    "argentina": "Argentina", "colombia": "Colombia", "chile": "Chile",
    "peru": "Perú", "netherlands": "Países Bajos", "belgium": "Bélgica",
    "switzerland": "Suiza", "sweden": "Suecia", "denmark": "Dinamarca",
    "norway": "Noruega", "ireland": "Irlanda", "poland": "Polonia",
    "austria": "Austria", "japan": "Japón", "china": "China",
    "india": "India", "australia": "Australia", "canada": "Canadá",
    "uk": "Reino Unido", "us": "Estados Unidos", "usa": "Estados Unidos",
}

def translate_country(country: str) -> str:
    if not country:
        return ""
    return COUNTRY_ES.get(country.strip().lower(), country)


def compute_cis_payload_hash(tx: Dict, sources: list) -> str:
    """Compute hash of the CIS-published payload to detect changes."""
    payload = {
        "target_name": tx.get("target_name"),
        "buyer_name": tx.get("buyer_name"),
        "seller_name": tx.get("seller_name"),
        "announcement_date": tx.get("announcement_date"),
        "transaction_type": tx.get("transaction_type"),
        "cis_category_suggested": tx.get("cis_category_suggested"),
        "cis_subcategory_suggested": tx.get("cis_subcategory_suggested"),
        "value_eurm": tx.get("value_eurm"),
        "amount_status": tx.get("amount_status"),
        "valuation_basis": tx.get("valuation_basis"),
        "geography_primary": tx.get("geography_primary"),
        "summary": tx.get("summary"),
        "strategic_rationale": tx.get("strategic_rationale"),
        "sources": [{"url": s.get("url"), "publisher": s.get("publisher"), "title": s.get("title")} for s in sources],
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def compute_incidences(tx: Dict, has_source: bool, has_primary_source: bool, entity_reviewed: bool) -> list:
    """Compute list of incidences for display in the table."""
    inc = []
    if not tx.get("target_name"):
        inc.append("falta_target")
    if not (tx.get("announcement_date") or tx.get("year")):
        inc.append("falta_fecha")
    if not (tx.get("cis_category_suggested") or tx.get("outside_cis_taxonomy")):
        inc.append("falta_categoria")
    if not has_source:
        inc.append("falta_fuente")
    if not has_primary_source:
        inc.append("falta_fuente_principal")
    if not tx.get("summary"):
        inc.append("falta_descripcion")
    if tx.get("dedupe_status") == "possible_duplicate":
        inc.append("posible_duplicado")
    if not entity_reviewed:
        inc.append("entidad_pendiente")
    if tx.get("review_status") not in ("reviewed", "approved"):
        inc.append("review_pendiente")
    if tx.get("cis_sync_status") == "pending_update":
        inc.append("pendiente_sincronizar")
    return inc
