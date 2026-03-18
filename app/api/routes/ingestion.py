from fastapi import APIRouter, HTTPException, status
from bson import ObjectId
from datetime import datetime, timezone

from app.models.schemas import IngestPayload, IngestResponse, ConflictResolutionPayload
from app.services.ingestion import ingest_medication_list
from app.db.database import get_db
from app.resources.messages import (
    INGEST_SUCCESS, PATIENT_NOT_FOUND, CONFLICT_NOT_FOUND,
    CONFLICT_ALREADY_RESOLVED, CONFLICT_RESOLVED,
)

router = APIRouter(prefix="/ingest", tags=["Ingestion"])


@router.post("/", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest(payload: IngestPayload):
    """
    Submit a medication list from a source for a patient.
    The service will normalise, version, and detect conflicts automatically.
    """
    result = await ingest_medication_list(payload)
    return IngestResponse(
        message=INGEST_SUCCESS.format(
            patient_id=payload.patient_id,
            source=payload.source.value
        ),
        **result,
    )


@router.get("/patients/{patient_id}/history")
async def get_patient_history(patient_id: str):
    """
    Return every snapshot version for this patient across all sources.
    This is the "time machine" — you can see how the medication list
    changed over time.
    """
    db = get_db()
    patient = await db.patients.find_one({"patient_id": patient_id})
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=PATIENT_NOT_FOUND.format(patient_id=patient_id),
        )
    cursor = db.snapshots.find(
        {"patient_id": patient_id},
        sort=[("source", 1), ("version", -1)]
    )
    snapshots = await cursor.to_list(length=None)
    for s in snapshots:
        s["_id"] = str(s["_id"])
    return {"patient_id": patient_id, "snapshots": snapshots}


@router.get("/patients/{patient_id}/conflicts")
async def get_patient_conflicts(patient_id: str, status: str = None):
    """
    Return all conflicts for a patient.
    Filter by ?status=unresolved or ?status=resolved
    """
    db = get_db()
    query = {"patient_id": patient_id}
    if status:
        query["status"] = status
    cursor = db.conflicts.find(query, sort=[("detected_at", -1)])
    conflicts = await cursor.to_list(length=None)
    for c in conflicts:
        c["conflict_id"] = str(c.pop("_id"))
    return {"patient_id": patient_id, "conflicts": conflicts}


@router.patch("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: str, payload: ConflictResolutionPayload):
    """
    Mark a conflict as resolved.

    DESIGN DECISION: We do NOT delete the conflict or create a new version.
    Instead, we add a resolution sub-document to the existing conflict record.
    This preserves the full audit trail:
      - When was it detected?
      - When was it resolved?
      - Who resolved it and why?
      - Which source did they trust?
    """
    db = get_db()

    # ObjectId is MongoDB's unique ID format — validate it first
    try:
        oid = ObjectId(conflict_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid conflict_id format.")

    conflict = await db.conflicts.find_one({"_id": oid})
    if not conflict:
        raise HTTPException(
            status_code=404,
            detail=CONFLICT_NOT_FOUND.format(conflict_id=conflict_id),
        )
    if conflict["status"] == "resolved":
        raise HTTPException(
            status_code=409,
            detail=CONFLICT_ALREADY_RESOLVED.format(conflict_id=conflict_id),
        )

    now = datetime.now(timezone.utc)
    resolution_doc = {
        "resolved_by":       payload.resolved_by,
        "resolution_reason": payload.resolution_reason,
        "chosen_source":     payload.chosen_source.value if payload.chosen_source else None,
        "notes":             payload.notes,
        "resolved_at":       now,
    }

    # Atomic update: set status, timestamp, and full resolution detail in one operation
    await db.conflicts.update_one(
        {"_id": oid},
        {"$set": {
            "status":      "resolved",
            "resolved_at": now,
            "resolution":  resolution_doc,
        }},
    )
    return {
        "message":    CONFLICT_RESOLVED.format(conflict_id=conflict_id),
        "resolution": resolution_doc,
    }