"""Document Engine routes — templates, projects, generation, AI, assets."""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from typing import Optional
from datetime import datetime, timezone
from database import db
from auth_utils import get_current_user
from models import new_id, now_iso
from documents import (
    TemplateCreate, TemplateUpdate, ProjectCreate, ProjectUpdate,
    GenerateRequest, AIBlockRequest, AIRewriteRequest
)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


# ══════════════════════════════════════════
# TEMPLATES
# ══════════════════════════════════════════

@router.get("/templates")
async def list_templates(status: Optional[str] = None, user=Depends(get_current_user)):
    query = {}
    if status:
        query["status"] = status
    templates = await db.document_templates.find(query, {"_id": 0}).sort("updated_at", -1).to_list(100)
    return {"templates": templates}


@router.get("/templates/{template_id}")
async def get_template(template_id: str, user=Depends(get_current_user)):
    t = await db.document_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Template not found")
    versions = await db.document_template_versions.find(
        {"template_id": template_id}, {"_id": 0}
    ).sort("version", -1).to_list(20)
    t["versions"] = versions
    return t


@router.post("/templates")
async def create_template(req: TemplateCreate, user=Depends(get_current_user)):
    now = now_iso()
    template_id = f"tpl_{new_id()[:12]}"
    doc = {
        "template_id": template_id,
        "name": req.name,
        "document_type": req.document_type,
        "supported_formats": req.supported_formats,
        "description": req.description,
        "status": "draft",
        "version": 1,
        "schema_version": req.schema_version,
        "allowed_components": req.allowed_components,
        "default_brand_id": req.default_brand_id,
        "legal_disclaimer": req.legal_disclaimer,
        "html_template": req.html_template,
        "css_template": req.css_template,
        "sections": req.sections,
        "created_by": user.get("email", user["id"]),
        "created_at": now,
        "updated_at": now
    }
    await db.document_templates.insert_one({**doc})
    # Create version 1
    await db.document_template_versions.insert_one({
        "id": new_id(),
        "template_id": template_id,
        "version": 1,
        "html_template": req.html_template,
        "css_template": req.css_template,
        "sections": req.sections,
        "created_by": user.get("email", user["id"]),
        "created_at": now
    })
    return doc


@router.put("/templates/{template_id}")
async def update_template(template_id: str, req: TemplateUpdate, user=Depends(get_current_user)):
    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "No fields to update")
    update["updated_at"] = now_iso()

    result = await db.document_templates.update_one(
        {"template_id": template_id}, {"$set": update}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Template not found")

    return await db.document_templates.find_one({"template_id": template_id}, {"_id": 0})


@router.post("/templates/{template_id}/publish")
async def publish_template(template_id: str, user=Depends(get_current_user)):
    t = await db.document_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Template not found")

    new_version = t.get("version", 0) + 1
    now = now_iso()

    await db.document_template_versions.insert_one({
        "id": new_id(),
        "template_id": template_id,
        "version": new_version,
        "html_template": t.get("html_template"),
        "css_template": t.get("css_template"),
        "sections": t.get("sections"),
        "created_by": user.get("email", user["id"]),
        "created_at": now
    })

    await db.document_templates.update_one(
        {"template_id": template_id},
        {"$set": {"version": new_version, "status": "published", "updated_at": now}}
    )

    return {"template_id": template_id, "version": new_version, "status": "published"}


# ══════════════════════════════════════════
# PROJECTS
# ══════════════════════════════════════════

@router.post("/projects")
async def create_project(req: ProjectCreate, user=Depends(get_current_user)):
    t = await db.document_templates.find_one({"template_id": req.template_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Template not found")

    now = now_iso()
    project_id = f"prj_{new_id()[:12]}"
    project = {
        "project_id": project_id,
        "template_id": req.template_id,
        "template_version": req.template_version or t.get("version", 1),
        "brand_id": req.brand_id or t.get("default_brand_id"),
        "name": req.name,
        "output_format": req.output_format,
        "locale": req.locale,
        "source_app": req.source_app,
        "source_entity_type": req.source_entity_type,
        "source_entity_id": req.source_entity_id,
        "data_payload": req.data_payload or {},
        "generated_blocks": {},
        "manual_overrides": req.manual_overrides or {},
        "status": "draft",
        "created_by": user.get("email", user["id"]),
        "created_at": now,
        "updated_at": now
    }
    await db.document_projects.insert_one({**project})
    return project


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user=Depends(get_current_user)):
    p = await db.document_projects.find_one({"project_id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.put("/projects/{project_id}")
async def update_project(project_id: str, req: ProjectUpdate, user=Depends(get_current_user)):
    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "No fields to update")
    update["updated_at"] = now_iso()

    result = await db.document_projects.update_one(
        {"project_id": project_id}, {"$set": update}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Project not found")
    return await db.document_projects.find_one({"project_id": project_id}, {"_id": 0})


@router.post("/projects/{project_id}/freeze")
async def freeze_project(project_id: str, user=Depends(get_current_user)):
    result = await db.document_projects.update_one(
        {"project_id": project_id},
        {"$set": {"status": "frozen", "frozen_at": now_iso()}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Project not found")
    return {"status": "frozen"}


@router.post("/projects/{project_id}/preview")
async def preview_project(project_id: str, user=Depends(get_current_user)):
    """Generate HTML preview of the document without creating a final PDF."""
    from documents.renderers import build_agency_report
    from fastapi.responses import HTMLResponse

    project = await db.document_projects.find_one({"project_id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(404, "Project not found")

    template = await db.document_templates.find_one(
        {"template_id": project["template_id"]}, {"_id": 0}
    )
    brand = None
    if project.get("brand_id"):
        brand = await db.document_brand_profiles.find_one(
            {"brand_id": project["brand_id"]}, {"_id": 0}
        )

    html, css = build_agency_report(
        project.get("data_payload", {}),
        project.get("generated_blocks", {}),
        project.get("manual_overrides", {}),
        brand
    )

    full_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{css}</style></head>{html.split('</head>')[-1] if '</head>' in html else '<body>' + html + '</body></html>'}"""

    return HTMLResponse(content=full_html)


@router.post("/preview")
async def preview_inline(req: GenerateRequest, user=Depends(get_current_user)):
    """Generate HTML preview from inline data (no project needed)."""
    from fastapi.responses import HTMLResponse

    template = None
    if req.template_id:
        template = await db.document_templates.find_one(
            {"template_id": req.template_id}, {"_id": 0}
        )

    brand = None
    if req.brand_id or (template and template.get("default_brand_id")):
        bid = req.brand_id or template.get("default_brand_id")
        brand = await db.document_brand_profiles.find_one({"brand_id": bid}, {"_id": 0})

    doc_type = template.get("document_type", "report") if template else "report"

    if doc_type == "valuation":
        from documents.renderers.valuation_renderer import build_valuation_report
        html, css = build_valuation_report(req.data_payload or {}, brand)
    else:
        from documents.renderers import build_agency_report
        html, css = build_agency_report(
            req.data_payload or {},
            req.generated_blocks or {},
            req.manual_overrides or {},
            brand
        )

    full_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{css}</style></head>{html.split('</head>')[-1] if '</head>' in html else '<body>' + html + '</body></html>'}"""

    return HTMLResponse(content=full_html)


# ══════════════════════════════════════════
# GENERATION
# ══════════════════════════════════════════

@router.post("/generate")
async def generate_document(req: GenerateRequest, user=Depends(get_current_user)):
    """Queue a document generation job. Returns job_id immediately."""
    now = now_iso()
    job_id = f"docjob_{new_id()[:12]}"

    # Resolve project or inline request
    template_id = req.template_id
    data_payload = req.data_payload or {}
    generated_blocks = req.generated_blocks or {}
    manual_overrides = req.manual_overrides or {}
    brand_id = req.brand_id

    if req.project_id:
        project = await db.document_projects.find_one({"project_id": req.project_id}, {"_id": 0})
        if project:
            template_id = template_id or project.get("template_id")
            data_payload = data_payload or project.get("data_payload", {})
            generated_blocks = generated_blocks or project.get("generated_blocks", {})
            manual_overrides = manual_overrides or project.get("manual_overrides", {})
            brand_id = brand_id or project.get("brand_id")

    if not template_id:
        raise HTTPException(400, "template_id is required")

    template = await db.document_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not template:
        raise HTTPException(404, "Template not found")

    job = {
        "job_id": job_id,
        "job_type": "document_generation",
        "template_id": template_id,
        "template_version": req.template_version or template.get("version", 1),
        "brand_id": brand_id or template.get("default_brand_id"),
        "output_format": req.output_format,
        "locale": req.locale,
        "source_app": req.source_app,
        "source_entity_type": req.source_entity_type,
        "source_entity_id": req.source_entity_id,
        "project_id": req.project_id,
        "data_payload": data_payload,
        "generated_blocks": generated_blocks,
        "manual_overrides": manual_overrides,
        "callback_url": req.callback_url,
        "status": "queued",
        "phase": None,
        "output_id": None,
        "error_message": None,
        "created_by": user.get("email", user["id"]),
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "heartbeat_at": None
    }
    await db.document_jobs.insert_one({**job})

    # Audit
    await db.document_audit_logs.insert_one({
        "id": new_id(), "action": "generate_requested", "job_id": job_id,
        "template_id": template_id, "output_format": req.output_format,
        "source_app": req.source_app, "user": user.get("email", user["id"]),
        "timestamp": now
    })

    return {"job_id": job_id, "status": "queued", "output_format": req.output_format}


@router.get("/jobs/{job_id}")
async def get_doc_job(job_id: str, user=Depends(get_current_user)):
    job = await db.document_jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/jobs")
async def list_doc_jobs(
    status: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user)
):
    query = {"job_type": "document_generation"}
    if status:
        query["status"] = status
    jobs = await db.document_jobs.find(query, {"_id": 0, "data_payload": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"jobs": jobs}


@router.get("/outputs/{output_id}")
async def get_output(output_id: str, user=Depends(get_current_user)):
    output = await db.document_outputs.find_one({"output_id": output_id}, {"_id": 0})
    if not output:
        raise HTTPException(404, "Output not found")
    return output


@router.get("/outputs")
async def list_outputs(limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user)):
    outputs = await db.document_outputs.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"outputs": outputs}


# ══════════════════════════════════════════
# AI BLOCKS
# ══════════════════════════════════════════

@router.post("/ai/generate-blocks")
async def ai_generate_blocks(req: AIBlockRequest, user=Depends(get_current_user)):
    """Generate a text block using LLM."""
    from documents.ai_engine import generate_block
    result = await generate_block(req.block_type, req.context, req.locale, req.model)
    return result


@router.post("/ai/rewrite-block")
async def ai_rewrite_block(req: AIRewriteRequest, user=Depends(get_current_user)):
    """Rewrite/shorten a text block."""
    from documents.ai_engine import rewrite_block
    result = await rewrite_block(req.text, req.instruction, req.locale, req.model)
    return result


# ══════════════════════════════════════════
# BRAND PROFILES
# ══════════════════════════════════════════

@router.get("/brands")
async def list_brands(user=Depends(get_current_user)):
    """List all brand profiles."""
    from documents.design_system import BRANDS
    brands = await db.document_brand_profiles.find({}, {"_id": 0}).to_list(50)
    if not brands:
        brands = [{"brand_id": b["brand_id"], "name": b["name"], "logo_text": b["logo_text"],
                    "is_default": b["is_default"], "logo_light": b.get("logo_light"),
                    "logo_dark": b.get("logo_dark")} for b in BRANDS.values()]
    return {"brands": brands}

@router.get("/brands/{brand_id}")
async def get_brand(brand_id: str, user=Depends(get_current_user)):
    from documents.design_system import BRANDS, get_brand_or_default
    brand = await db.document_brand_profiles.find_one({"brand_id": brand_id}, {"_id": 0})
    if not brand:
        brand = get_brand_or_default(brand_id)
    return brand

@router.put("/brands/{brand_id}")
async def update_brand(brand_id: str, body: dict, user=Depends(get_current_user)):
    """Update a brand profile. Stores in DB (overrides hardcoded defaults)."""
    from documents.design_system import BRANDS, get_brand_or_default

    existing = await db.document_brand_profiles.find_one({"brand_id": brand_id}, {"_id": 0})
    if not existing:
        # Initialize from hardcoded default
        existing = get_brand_or_default(brand_id)
        if not existing:
            raise HTTPException(404, "Brand not found")

    # Merge updates
    for key in ["name", "logo_text", "logo_light", "logo_dark", "is_default"]:
        if key in body:
            existing[key] = body[key]

    # Merge token updates
    if "tokens" in body:
        if "tokens" not in existing:
            existing["tokens"] = {}
        for section in ["colors", "fonts", "cover", "closing"]:
            if section in body["tokens"]:
                if section not in existing["tokens"]:
                    existing["tokens"][section] = {}
                existing["tokens"][section].update(body["tokens"][section])

    existing["updated_at"] = now_iso()
    existing["updated_by"] = user.get("email", user["id"])

    await db.document_brand_profiles.update_one(
        {"brand_id": brand_id},
        {"$set": existing},
        upsert=True
    )
    return existing

@router.get("/brands/{brand_id}/preview-css")
async def preview_brand_css(brand_id: str, user=Depends(get_current_user)):
    from documents.design_system import generate_css_tokens
    from fastapi.responses import PlainTextResponse
    # Check DB first
    brand = await db.document_brand_profiles.find_one({"brand_id": brand_id}, {"_id": 0})
    css = generate_css_tokens(brand_id, brand)
    return PlainTextResponse(content=css, media_type="text/css")


# ══════════════════════════════════════════
# ASSETS
# ══════════════════════════════════════════

@router.get("/assets")
async def list_assets(asset_type: Optional[str] = None, user=Depends(get_current_user)):
    query = {}
    if asset_type:
        query["asset_type"] = asset_type
    assets = await db.document_assets.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"assets": assets}


@router.post("/assets/upload")
async def upload_asset(
    file: UploadFile = File(...),
    asset_type: str = "image",
    user=Depends(get_current_user)
):
    from services.storage import upload_file
    content = await file.read()
    path = upload_file(content, file.filename, file.content_type or "application/octet-stream", user["id"])

    asset = {
        "asset_id": f"ast_{new_id()[:12]}",
        "filename": file.filename,
        "storage_path": path,
        "content_type": file.content_type,
        "size": len(content),
        "asset_type": asset_type,
        "uploaded_by": user.get("email", user["id"]),
        "created_at": now_iso()
    }
    await db.document_assets.insert_one({**asset})
    return asset


# ══════════════════════════════════════════
# INTEGRATIONS (CIS, Arroba)
# ══════════════════════════════════════════

@router.post("/integrations/{consumer}/generate")
async def integration_generate(consumer: str, req: GenerateRequest, user=Depends(get_current_user)):
    """Integration endpoint for CIS/Arroba to generate documents."""
    req.source_app = consumer
    return await generate_document(req, user)
