from fastapi import APIRouter, HTTPException, Depends, Query, Response
from typing import Optional
from models import AgencyResultResponse, ResultUpdateRequest, new_id, now_iso
from auth_utils import get_current_user
from database import db
import io
import json

router = APIRouter(prefix="/api/v1/results", tags=["results"])


@router.get("")
async def list_results(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    review_status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    user=Depends(get_current_user)
):
    query = {}
    if status:
        query["status"] = status
    if review_status:
        query["review_status"] = review_status
    if category:
        query["category"] = category
    if search:
        query["$or"] = [
            {"company_name": {"$regex": search, "$options": "i"}},
            {"input_url": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]

    skip = (page - 1) * limit
    total = await db.agency_results.count_documents(query)
    results = await db.agency_results.find(
        query, {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    return {
        "results": results,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if total > 0 else 0
    }


@router.get("/by-url")
async def get_result_by_url(
    url: str = Query(...),
    user=Depends(get_current_user)
):
    result = await db.agency_results.find_one(
        {"input_url": {"$regex": f"^{url}", "$options": "i"}},
        {"_id": 0}
    )
    if not result:
        raise HTTPException(status_code=404, detail="No result found for this URL")

    evidence = await db.evidence_items.find(
        {"result_id": result["id"]}, {"_id": 0}
    ).to_list(200)
    result["evidence"] = evidence
    return result


@router.get("/export")
async def export_results(
    format: str = Query("json", regex="^(json|csv|excel)$"),
    status: Optional[str] = None,
    review_status: Optional[str] = None,
    category: Optional[str] = None,
    user=Depends(get_current_user)
):
    query = {}
    if status:
        query["status"] = status
    if review_status:
        query["review_status"] = review_status
    if category:
        query["category"] = category

    # Export with projection to reduce memory footprint
    export_fields = {
        "_id": 0, "id": 1, "input_url": 1, "company_name": 1, "description": 1,
        "category": 1, "subcategory": 1, "tags": 1, "has_awards": 1,
        "awards_evidence": 1, "main_clients": 1, "main_contact_name": 1,
        "main_contact_role": 1, "main_contact_email": 1, "phone": 1,
        "address_street": 1, "address_city": 1, "address_province": 1,
        "postal_code": 1, "country": 1, "confidence_overall": 1,
        "confidence_category": 1, "status": 1, "review_status": 1,
        "validated": 1, "taxonomy_version": 1, "created_at": 1,
        "cis_company_id": 1, "cif": 1
    }
    results = await db.agency_results.find(query, export_fields).limit(5000).to_list(5000)

    if format == "json":
        return Response(
            content=json.dumps(results, indent=2, default=str),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=agency_results.json"}
        )

    elif format == "csv":
        import pandas as pd
        if not results:
            return Response(content="", media_type="text/csv")
        df = pd.json_normalize(results)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=agency_results.csv"}
        )

    elif format == "excel":
        import pandas as pd
        if not results:
            return Response(content=b"", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        df = pd.json_normalize(results)
        buf = io.BytesIO()
        df.to_excel(buf, index=False, engine="xlsxwriter")
        buf.seek(0)
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=agency_results.xlsx"}
        )


@router.get("/{result_id}")
async def get_result(result_id: str, user=Depends(get_current_user)):
    result = await db.agency_results.find_one({"id": result_id}, {"_id": 0})
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    evidence = await db.evidence_items.find(
        {"result_id": result_id}, {"_id": 0}
    ).to_list(200)
    result["evidence"] = evidence
    return result


@router.put("/{result_id}")
async def update_result(
    result_id: str,
    req: ResultUpdateRequest,
    user=Depends(get_current_user)
):
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_data["last_edited_by"] = user["id"]
    update_data["last_edited_at"] = now_iso()
    update_data["review_status"] = "reviewed"

    result = await db.agency_results.update_one(
        {"id": result_id},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Result not found")

    updated = await db.agency_results.find_one({"id": result_id}, {"_id": 0})
    return updated


@router.post("/{result_id}/validate")
async def validate_result(result_id: str, user=Depends(get_current_user)):
    now = now_iso()
    result = await db.agency_results.update_one(
        {"id": result_id},
        {"$set": {
            "validated": True,
            "validated_by": user["id"],
            "validated_at": now,
            "review_status": "validated"
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Result not found")
    return {"status": "validated", "validated_at": now}


@router.get("/{result_id}/evidence")
async def get_evidence(result_id: str, user=Depends(get_current_user)):
    evidence = await db.evidence_items.find(
        {"result_id": result_id}, {"_id": 0}
    ).to_list(200)
    return evidence


@router.get("/{result_id}/pdf")
async def export_pdf(result_id: str, user=Depends(get_current_user)):
    """Export result as PDF report."""
    from services.pdf_generator import generate_result_pdf
    from services.storage import get_object

    result = await db.agency_results.find_one({"id": result_id}, {"_id": 0})
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    # Try to get screenshot bytes
    screenshot_bytes = None
    if result.get("screenshot_path"):
        try:
            screenshot_bytes, _ = get_object(result["screenshot_path"])
        except Exception:
            pass

    pdf_bytes = generate_result_pdf(result, screenshot_bytes)
    company = (result.get("company_name") or "agency").replace(" ", "_")
    filename = f"{company}_report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/{result_id}/send")
async def send_to_consumer(result_id: str, body: dict, user=Depends(get_current_user)):
    """Send result to a specific consumer (CIS, Arroba, etc.)."""
    destination = body.get("destination")
    if not destination:
        raise HTTPException(status_code=400, detail="destination is required (e.g. 'cis', 'arroba')")

    result = await db.agency_results.find_one({"id": result_id}, {"_id": 0})
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    # Find consumer config
    consumer = await db.consumers.find_one({"consumer_id": destination}, {"_id": 0})
    if not consumer:
        raise HTTPException(status_code=404, detail=f"Consumer '{destination}' not found")

    environment = body.get("environment", "production")
    env_config = consumer.get("environments", {}).get(environment, {})
    allowed_domains = env_config.get("allowed_callback_domains", [])

    if not allowed_domains:
        raise HTTPException(status_code=400, detail=f"No callback domains configured for {destination}/{environment}")

    callback_url = f"https://{allowed_domains[0]}/api/admin/enrichment/callback"

    # Update result with send metadata
    await db.agency_results.update_one(
        {"id": result_id},
        {"$set": {
            "callback_url": callback_url,
            "callback_status": "pending",
            "consumer_id": destination,
            "environment": environment
        }}
    )

    # Fire callback
    from services.enrichment_helpers import fire_enrichment_callback
    await fire_enrichment_callback(result_id)

    # Get updated status
    updated = await db.agency_results.find_one(
        {"id": result_id},
        {"_id": 0, "callback_status": 1, "callback_sent_at": 1, "callback_error": 1}
    )

    # Log send action
    await db.send_log.insert_one({
        "id": new_id(),
        "result_id": result_id,
        "destination": destination,
        "environment": environment,
        "callback_url": callback_url,
        "callback_status": updated.get("callback_status"),
        "callback_error": updated.get("callback_error"),
        "sent_by": user.get("email") or user.get("id"),
        "sent_at": now_iso()
    })

    return {
        "status": updated.get("callback_status"),
        "destination": destination,
        "callback_url": callback_url,
        "sent_at": updated.get("callback_sent_at"),
        "error": updated.get("callback_error")
    }


@router.get("/{result_id}/send-log")
async def get_send_log(result_id: str, user=Depends(get_current_user)):
    """Get send history for a result."""
    logs = await db.send_log.find(
        {"result_id": result_id}, {"_id": 0}
    ).sort("sent_at", -1).to_list(50)
    return logs
