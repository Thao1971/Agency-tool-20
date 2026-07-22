"""Taxonomy Master — Full CRUD with audit, aliases, soft-delete, and CIS sync endpoints."""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from models import (
    TaxonomyCategoryCreate, TaxonomyCategoryUpdate,
    TaxonomySubcategoryCreate, TaxonomySubcategoryUpdate,
    TaxonomyImportRequest, new_id, now_iso
)
from auth_utils import get_current_user
from database import db
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/taxonomy", tags=["taxonomy"])

TAXONOMY_VERSION = "v2.1-2026"


# ── Alias models ──
class AliasCreate(BaseModel):
    alias: str
    target_type: str  # "category" | "subcategory"
    target_id: str

class AliasUpdate(BaseModel):
    alias: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    active: Optional[bool] = None


# ── Audit helper ──
async def _audit(action: str, entity_type: str, entity_id: str, old_value=None, new_value=None, user=None):
    await db.taxonomy_audit_logs.insert_one({
        "log_id": new_id(),
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "old_value": old_value,
        "new_value": new_value,
        "updated_by": user.get("email", user.get("id")) if user else "system",
        "timestamp": now_iso(),
    })


# ══════════════════════════════════════════
# PUBLIC READ (CIS consumption)
# ══════════════════════════════════════════

@router.get("")
async def get_taxonomy(include_inactive: bool = False, user=Depends(get_current_user)):
    """Get taxonomy tree (categories + subcategories)."""
    cat_filter = {} if include_inactive else {"active": True}
    categories = await db.taxonomy_categories.find(cat_filter, {"_id": 0}).sort("order", 1).to_list(100)

    for cat in categories:
        sub_filter = {"category_id": cat["id"]}
        if not include_inactive:
            sub_filter["active"] = True
        subs = await db.taxonomy_subcategories.find(sub_filter, {"_id": 0}).sort("order", 1).to_list(100)
        cat["subcategories"] = subs

    return {"categories": categories}


@router.get("/all")
async def get_taxonomy_all(include_inactive: bool = False):
    """Full taxonomy export for CIS sync — public, no auth required.
    
    Contract (frozen for CIS consumption):
    - categories[]: cat_id, name, description, order, active
    - subcategories[]: sub_id, parent_cat_id, name, definition, order, active
    - aliases[]: alias_id, alias, target_type, target_id, active
    - version: string
    - last_updated_at: ISO datetime
    - counts: {categories_active, subcategories_active, aliases_active}
    """
    cat_filter = {} if include_inactive else {"active": True}
    raw_cats = await db.taxonomy_categories.find(cat_filter, {"_id": 0}).sort("order", 1).to_list(100)

    sub_filter = {} if include_inactive else {"active": True}
    raw_subs = await db.taxonomy_subcategories.find(sub_filter, {"_id": 0}).sort("order", 1).to_list(500)

    alias_filter = {} if include_inactive else {"active": True}
    aliases = await db.taxonomy_aliases.find(alias_filter, {"_id": 0}).to_list(500)

    # Map to CIS contract field names
    categories = [{
        "cat_id": c["id"],
        "name": c["name"],
        "description": c.get("description"),
        "order": c.get("order", 0),
        "active": c.get("active", True),
    } for c in raw_cats]

    subcategories = [{
        "sub_id": s["id"],
        "parent_cat_id": s["category_id"],
        "name": s["name"],
        "definition": s.get("definition"),
        "order": s.get("order", 0),
        "active": s.get("active", True),
    } for s in raw_subs]

    # Last update
    last_cat = await db.taxonomy_categories.find_one({}, {"_id": 0, "updated_at": 1}, sort=[("updated_at", -1)])
    last_sub = await db.taxonomy_subcategories.find_one({}, {"_id": 0, "updated_at": 1}, sort=[("updated_at", -1)])
    last_updated = max(
        last_cat.get("updated_at", "") if last_cat else "",
        last_sub.get("updated_at", "") if last_sub else ""
    )

    return {
        "categories": categories,
        "subcategories": subcategories,
        "aliases": aliases,
        "version": TAXONOMY_VERSION,
        "last_updated_at": last_updated,
        "counts": {
            "categories_active": len([c for c in categories if c.get("active", True)]),
            "subcategories_active": len([s for s in subcategories if s.get("active", True)]),
            "aliases_active": len([a for a in aliases if a.get("active", True)]),
        }
    }


@router.get("/version")
async def get_taxonomy_version():
    """Current taxonomy version."""
    cats = await db.taxonomy_categories.count_documents({"active": True})
    subs = await db.taxonomy_subcategories.count_documents({"active": True})
    last_cat = await db.taxonomy_categories.find_one({}, {"_id": 0, "updated_at": 1}, sort=[("updated_at", -1)])
    return {
        "version": TAXONOMY_VERSION,
        "categories_active": cats,
        "subcategories_active": subs,
        "last_updated_at": last_cat.get("updated_at") if last_cat else None,
    }


@router.get("/status")
async def get_taxonomy_status(user=Depends(get_current_user)):
    """Admin diagnostic — taxonomy health."""
    cats_active = await db.taxonomy_categories.count_documents({"active": True})
    cats_inactive = await db.taxonomy_categories.count_documents({"active": False})
    subs_active = await db.taxonomy_subcategories.count_documents({"active": True})
    subs_inactive = await db.taxonomy_subcategories.count_documents({"active": False})
    aliases_active = await db.taxonomy_aliases.count_documents({"active": True})
    aliases_inactive = await db.taxonomy_aliases.count_documents({"active": False})

    # Check inconsistencies
    inconsistencies = []
    # Active subs with inactive parent
    active_subs = await db.taxonomy_subcategories.find({"active": True}, {"_id": 0, "id": 1, "category_id": 1, "name": 1}).to_list(500)
    for sub in active_subs:
        parent = await db.taxonomy_categories.find_one({"id": sub["category_id"]}, {"_id": 0, "active": 1})
        if parent and not parent.get("active", True):
            inconsistencies.append(f"Subcategory '{sub['name']}' is active but parent category is inactive")

    last_cat = await db.taxonomy_categories.find_one({}, {"_id": 0, "updated_at": 1}, sort=[("updated_at", -1)])

    return {
        "version": TAXONOMY_VERSION,
        "categories_active": cats_active,
        "categories_inactive": cats_inactive,
        "subcategories_active": subs_active,
        "subcategories_inactive": subs_inactive,
        "aliases_active": aliases_active,
        "aliases_inactive": aliases_inactive,
        "last_updated_at": last_cat.get("updated_at") if last_cat else None,
        "inconsistencies": inconsistencies,
    }


# ══════════════════════════════════════════
# CATEGORIES CRUD
# ══════════════════════════════════════════

@router.post("/categories")
async def create_category(req: TaxonomyCategoryCreate, user=Depends(get_current_user)):
    # Check unique name among active
    existing = await db.taxonomy_categories.find_one({"name": req.name, "active": True})
    if existing:
        raise HTTPException(400, f"Category '{req.name}' already exists")

    now = now_iso()
    cat = {
        "id": new_id(),
        "name": req.name,
        "description": req.description,
        "order": req.order,
        "active": req.active,
        "source": "manual",
        "external_id": None,
        "taxonomy_version": TAXONOMY_VERSION,
        "created_at": now,
        "updated_at": now,
        "updated_by": user.get("email", user.get("id")),
    }
    await db.taxonomy_categories.insert_one({**cat})
    await _audit("category_created", "category", cat["id"], new_value={"name": req.name}, user=user)
    return cat


@router.put("/categories/{cat_id}")
async def update_category(cat_id: str, req: TaxonomyCategoryUpdate, user=Depends(get_current_user)):
    existing = await db.taxonomy_categories.find_one({"id": cat_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Category not found")

    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "No fields to update")

    # Check unique name if renaming
    if "name" in update and update["name"] != existing["name"]:
        dup = await db.taxonomy_categories.find_one({"name": update["name"], "active": True, "id": {"$ne": cat_id}})
        if dup:
            raise HTTPException(400, f"Category '{update['name']}' already exists")

    update["updated_at"] = now_iso()
    update["updated_by"] = user.get("email", user.get("id"))

    await db.taxonomy_categories.update_one({"id": cat_id}, {"$set": update})
    await _audit("category_updated", "category", cat_id,
                 old_value={k: existing.get(k) for k in update if k not in ("updated_at", "updated_by")},
                 new_value={k: v for k, v in update.items() if k not in ("updated_at", "updated_by")},
                 user=user)
    return await db.taxonomy_categories.find_one({"id": cat_id}, {"_id": 0})


@router.delete("/categories/{cat_id}")
async def deactivate_category(cat_id: str, user=Depends(get_current_user)):
    """Soft-delete: deactivate category. Warns if has active subcategories."""
    existing = await db.taxonomy_categories.find_one({"id": cat_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Category not found")

    active_subs = await db.taxonomy_subcategories.count_documents({"category_id": cat_id, "active": True})
    if active_subs > 0:
        raise HTTPException(400, f"Cannot deactivate: category has {active_subs} active subcategories. Deactivate them first.")

    now = now_iso()
    await db.taxonomy_categories.update_one({"id": cat_id}, {"$set": {"active": False, "updated_at": now, "updated_by": user.get("email", user.get("id"))}})
    await _audit("category_deactivated", "category", cat_id, old_value={"active": True}, new_value={"active": False}, user=user)
    return {"status": "deactivated", "id": cat_id}


# ══════════════════════════════════════════
# SUBCATEGORIES CRUD
# ══════════════════════════════════════════

@router.post("/subcategories")
async def create_subcategory(req: TaxonomySubcategoryCreate, user=Depends(get_current_user)):
    cat = await db.taxonomy_categories.find_one({"id": req.category_id}, {"_id": 0})
    if not cat:
        raise HTTPException(404, "Parent category not found")
    if not cat.get("active", True):
        raise HTTPException(400, "Cannot add subcategory to inactive category")

    # Check unique name within same parent
    existing = await db.taxonomy_subcategories.find_one({"category_id": req.category_id, "name": req.name, "active": True})
    if existing:
        raise HTTPException(400, f"Subcategory '{req.name}' already exists in this category")

    now = now_iso()
    sub = {
        "id": new_id(),
        "category_id": req.category_id,
        "name": req.name,
        "definition": req.definition,
        "order": req.order,
        "active": req.active,
        "source": "manual",
        "external_id": None,
        "taxonomy_version": TAXONOMY_VERSION,
        "created_at": now,
        "updated_at": now,
        "updated_by": user.get("email", user.get("id")),
    }
    await db.taxonomy_subcategories.insert_one({**sub})
    await _audit("subcategory_created", "subcategory", sub["id"], new_value={"name": req.name, "parent": req.category_id}, user=user)
    return sub


@router.put("/subcategories/{sub_id}")
async def update_subcategory(sub_id: str, req: TaxonomySubcategoryUpdate, user=Depends(get_current_user)):
    existing = await db.taxonomy_subcategories.find_one({"id": sub_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Subcategory not found")

    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "No fields to update")

    # If changing parent, validate new parent exists and is active
    if "category_id" in update:
        new_parent = await db.taxonomy_categories.find_one({"id": update["category_id"]}, {"_id": 0})
        if not new_parent:
            raise HTTPException(404, "New parent category not found")
        if not new_parent.get("active", True):
            raise HTTPException(400, "Cannot move to inactive category")

    # Check unique name if renaming
    if "name" in update and update["name"] != existing["name"]:
        parent_id = update.get("category_id", existing["category_id"])
        dup = await db.taxonomy_subcategories.find_one({"category_id": parent_id, "name": update["name"], "active": True, "id": {"$ne": sub_id}})
        if dup:
            raise HTTPException(400, f"Subcategory '{update['name']}' already exists in this category")

    update["updated_at"] = now_iso()
    update["updated_by"] = user.get("email", user.get("id"))

    await db.taxonomy_subcategories.update_one({"id": sub_id}, {"$set": update})
    await _audit("subcategory_updated", "subcategory", sub_id,
                 old_value={k: existing.get(k) for k in update if k not in ("updated_at", "updated_by")},
                 new_value={k: v for k, v in update.items() if k not in ("updated_at", "updated_by")},
                 user=user)
    return await db.taxonomy_subcategories.find_one({"id": sub_id}, {"_id": 0})


@router.delete("/subcategories/{sub_id}")
async def deactivate_subcategory(sub_id: str, user=Depends(get_current_user)):
    """Soft-delete: deactivate subcategory."""
    existing = await db.taxonomy_subcategories.find_one({"id": sub_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Subcategory not found")

    # Check if in use (optional warning)
    in_use_count = await db.agency_results.count_documents({"subcategory": existing["name"]})
    tx_use_count = await db.transactions_normalized.count_documents({"cis_subcategory_suggested": existing["name"], "deleted": {"$ne": True}})

    now = now_iso()
    await db.taxonomy_subcategories.update_one({"id": sub_id}, {"$set": {"active": False, "updated_at": now, "updated_by": user.get("email", user.get("id"))}})
    await _audit("subcategory_deactivated", "subcategory", sub_id, old_value={"active": True}, new_value={"active": False}, user=user)

    return {"status": "deactivated", "id": sub_id, "in_use_by_companies": in_use_count, "in_use_by_transactions": tx_use_count}


# ══════════════════════════════════════════
# ALIASES
# ══════════════════════════════════════════

@router.get("/aliases")
async def list_aliases(include_inactive: bool = False, user=Depends(get_current_user)):
    query = {} if include_inactive else {"active": True}
    aliases = await db.taxonomy_aliases.find(query, {"_id": 0}).to_list(500)
    return {"aliases": aliases}


@router.post("/aliases")
async def create_alias(req: AliasCreate, user=Depends(get_current_user)):
    if req.target_type not in ("category", "subcategory"):
        raise HTTPException(400, "target_type must be 'category' or 'subcategory'")

    # Validate target exists
    if req.target_type == "category":
        target = await db.taxonomy_categories.find_one({"id": req.target_id}, {"_id": 0})
    else:
        target = await db.taxonomy_subcategories.find_one({"id": req.target_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, f"Target {req.target_type} not found")

    now = now_iso()
    alias = {
        "alias_id": new_id(),
        "alias": req.alias,
        "target_type": req.target_type,
        "target_id": req.target_id,
        "active": True,
        "created_at": now,
        "updated_at": now,
        "updated_by": user.get("email", user.get("id")),
    }
    await db.taxonomy_aliases.insert_one({**alias})
    await _audit("alias_created", "alias", alias["alias_id"], new_value={"alias": req.alias, "target": req.target_id}, user=user)
    return alias


@router.put("/aliases/{alias_id}")
async def update_alias(alias_id: str, req: AliasUpdate, user=Depends(get_current_user)):
    existing = await db.taxonomy_aliases.find_one({"alias_id": alias_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Alias not found")

    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "No fields to update")
    update["updated_at"] = now_iso()
    update["updated_by"] = user.get("email", user.get("id"))

    await db.taxonomy_aliases.update_one({"alias_id": alias_id}, {"$set": update})
    await _audit("alias_updated", "alias", alias_id, new_value=update, user=user)
    return await db.taxonomy_aliases.find_one({"alias_id": alias_id}, {"_id": 0})


@router.delete("/aliases/{alias_id}")
async def deactivate_alias(alias_id: str, user=Depends(get_current_user)):
    existing = await db.taxonomy_aliases.find_one({"alias_id": alias_id})
    if not existing:
        raise HTTPException(404, "Alias not found")
    await db.taxonomy_aliases.update_one({"alias_id": alias_id}, {"$set": {"active": False, "updated_at": now_iso()}})
    await _audit("alias_deactivated", "alias", alias_id, user=user)
    return {"status": "deactivated"}


# ══════════════════════════════════════════
# IMPORT (legacy)
# ══════════════════════════════════════════

@router.post("/import")
async def import_taxonomy(req: TaxonomyImportRequest, user=Depends(get_current_user)):
    now = now_iso()
    created_cats = 0
    created_subs = 0

    for i, item in enumerate(req.categories):
        cat_id = new_id()
        cat = {
            "id": cat_id, "name": item.name, "description": None,
            "order": i + 1, "active": True, "source": "import",
            "external_id": None, "taxonomy_version": req.version,
            "created_at": now, "updated_at": now,
            "updated_by": user.get("email", user.get("id")),
        }
        await db.taxonomy_categories.insert_one({**cat})
        created_cats += 1

        for j, sub_name in enumerate(item.subcategories):
            sub = {
                "id": new_id(), "category_id": cat_id,
                "name": sub_name, "definition": None,
                "order": j + 1, "active": True, "source": "import",
                "external_id": None, "taxonomy_version": req.version,
                "created_at": now, "updated_at": now,
                "updated_by": user.get("email", user.get("id")),
            }
            await db.taxonomy_subcategories.insert_one({**sub})
            created_subs += 1

    return {"status": "imported", "categories_created": created_cats, "subcategories_created": created_subs, "version": req.version}
