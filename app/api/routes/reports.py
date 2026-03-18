from fastapi import APIRouter, Query
from datetime import datetime, timezone, timedelta
from app.db.database import get_db

router = APIRouter(prefix="/reports", tags=["Reports & Aggregations"])


@router.get("/clinics/{clinic_id}/unresolved-conflicts")
async def patients_with_unresolved_conflicts(clinic_id: str):
    """
    Report 1: All patients in a clinic with at least 1 unresolved conflict.

    Pipeline stages explained:
      $match  → filter to only unresolved conflicts for this clinic
      $group  → count conflicts per patient, collect types and severities
      $lookup → join with patients collection to get patient name
      $unwind → flatten the joined array (one patient per document)
      $project → shape the output fields
      $sort   → most conflicted patients first
    """
    db = get_db()
    pipeline = [
        {"$match": {"clinic_id": clinic_id, "status": "unresolved"}},
        {
            "$group": {
                "_id":              "$patient_id",
                "unresolved_count": {"$sum": 1},
                "conflict_types":   {"$addToSet": "$conflict_type"},
                "severities":       {"$addToSet": "$severity"},
                "oldest_conflict":  {"$min": "$detected_at"},
                "latest_conflict":  {"$max": "$detected_at"},
            }
        },
        {
            # Join with patients collection to get patient name
            "$lookup": {
                "from":         "patients",
                "localField":   "_id",        # patient_id from group
                "foreignField": "patient_id", # patient_id in patients collection
                "as":           "patient_info",
            }
        },
        # $lookup returns an array; unwind makes it a single object
        {"$unwind": {"path": "$patient_info", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id":                    0,
                "patient_id":             "$_id",
                "name":                   "$patient_info.name",
                "unresolved_conflict_count": "$unresolved_count",
                "conflict_types":         1,
                "severities":             1,
                "oldest_conflict":        1,
                "latest_conflict":        1,
            }
        },
        {"$sort": {"unresolved_conflict_count": -1}},
    ]
    cursor = db.conflicts.aggregate(pipeline)
    results = await cursor.to_list(length=None)
    return {
        "clinic_id":     clinic_id,
        "patient_count": len(results),
        "patients":      results,
    }


@router.get("/clinics/conflict-summary/30-days")
async def conflict_summary_last_30_days(
    min_conflicts: int = Query(default=2, ge=1)
):
    """
    Report 2: Per-clinic count of patients with >= N conflicts in last 30 days.
    """
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    pipeline = [
        {"$match": {"detected_at": {"$gte": cutoff}}},
        {
            "$group": {
                "_id": {
                    "clinic_id":  "$clinic_id",
                    "patient_id": "$patient_id",
                },
                "conflict_count":   {"$sum": 1},
                "unresolved_count": {
                    "$sum": {"$cond": [{"$eq": ["$status", "unresolved"]}, 1, 0]}
                },
            }
        },
        {"$match": {"conflict_count": {"$gte": min_conflicts}}},
        {
            "$group": {
                "_id":                       "$_id.clinic_id",
                "patients_with_conflicts":   {"$sum": 1},
                "total_conflicts":           {"$sum": "$conflict_count"},
                "total_unresolved":          {"$sum": "$unresolved_count"},
                "avg_conflicts_per_patient": {"$avg": "$conflict_count"},
            }
        },
        {
            "$project": {
                "_id":                       0,
                "clinic_id":                 "$_id",
                "patients_with_conflicts":   1,
                "total_conflicts":           1,
                "total_unresolved":          1,
                "avg_conflicts_per_patient": 1,
            }
        },
        {"$sort": {"patients_with_conflicts": -1}},
    ]

    cursor = db.conflicts.aggregate(pipeline)
    results = await cursor.to_list(length=None)

    for r in results:
        if r.get("avg_conflicts_per_patient") is not None:
            r["avg_conflicts_per_patient"] = round(r["avg_conflicts_per_patient"], 2)

    return {
        "period_days":             30,
        "min_conflicts_threshold": min_conflicts,
        "since":                   cutoff.isoformat(),
        "clinics":                 results,
    }


@router.get("/patients/{patient_id}/timeline")
async def patient_conflict_timeline(patient_id: str):
    """Full conflict history with resolution audit trail for a single patient."""
    db = get_db()
    cursor = db.conflicts.find({"patient_id": patient_id}, sort=[("detected_at", -1)])
    conflicts = await cursor.to_list(length=None)
    for c in conflicts:
        c["conflict_id"] = str(c.pop("_id"))
    return {"patient_id": patient_id, "total": len(conflicts), "conflicts": conflicts}


@router.get("/clinics/{clinic_id}/conflict-types")
async def conflict_type_breakdown(clinic_id: str):
    """How many of each conflict type does a clinic have?"""
    db = get_db()
    pipeline = [
        {"$match": {"clinic_id": clinic_id}},
        {
            "$group": {
                "_id":   {"type": "$conflict_type", "status": "$status"},
                "count": {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id":           0,
                "conflict_type": "$_id.type",
                "status":        "$_id.status",
                "count":         1,
            }
        },
        {"$sort": {"count": -1}},
    ]
    cursor = db.conflicts.aggregate(pipeline)
    results = await cursor.to_list(length=None)
    return {"clinic_id": clinic_id, "breakdown": results}