# This is the ORCHESTRATOR — it coordinates all the steps when a
# medication list arrives

from datetime import datetime, timezone
from typing import Any, Dict, List
from bson import ObjectId
from app.db.database import get_db
from app.models.schemas import IngestPayload
from app.services.normalizer import normalize_list
from app.services.conflict_detector import detect_conflicts


async def ingest_medication_list(payload: IngestPayload) -> Dict[str, Any]:
    db = get_db()
    now = datetime.now(timezone.utc)

    # ── Step 1: Upsert patient ─────────────────────────────────────────────
    # $setOnInsert only runs if this is a NEW document (insert, not update)
    # $set always runs, so last_updated always gets refreshed
    await db.patients.update_one(
        {"patient_id": payload.patient_id},
        {
            "$setOnInsert": {
                "patient_id": payload.patient_id,
                "clinic_id":  payload.clinic_id,
                "created_at": now,
            },
            "$set": {"last_updated": now},
        },
        upsert=True,
    )

    # ── Step 2: Determine next version for this patient+source ────────────
    # Find the highest existing version for this patient from this source
    last = await db.snapshots.find_one(
        {"patient_id": payload.patient_id, "source": payload.source.value},
        sort=[("version", -1)],
    )
    next_version = (last["version"] + 1) if last else 1

    # ── Step 3: Normalise medications ─────────────────────────────────────
    normalised_meds = normalize_list(payload.medications)

    # ── Step 4: Save snapshot ─────────────────────────────────────────────
    # We ALWAYS insert a new document — never update an existing one.
    # This preserves the full history of every medication list ever submitted.
    snapshot_doc = {
        "patient_id":  payload.patient_id,
        "clinic_id":   payload.clinic_id,
        "source":      payload.source.value,
        "version":     next_version,
        "medications": normalised_meds,
        "recorded_by": payload.recorded_by,
        "notes":       payload.notes,
        "ingested_at": now,
    }
    result = await db.snapshots.insert_one(snapshot_doc)
    snapshot_id = str(result.inserted_id)

    # ── Step 5: Load latest snapshot from every OTHER source ──────────────
    # We use an aggregation pipeline to get only the highest-version
    # snapshot per source (not all historical versions)
    pipeline = [
        # Only look at snapshots for this patient, excluding the source we just ingested
        {"$match": {"patient_id": payload.patient_id, "source": {"$ne": payload.source.value}}},
        # Sort newest first so $first picks the latest version
        {"$sort": {"version": -1}},
        # Group by source, keeping only the first (latest) document per source
        {"$group": {"_id": "$source", "doc": {"$first": "$$ROOT"}}},
        # Unwrap the grouped structure back to plain documents
        {"$replaceRoot": {"newRoot": "$doc"}},
    ]
    cursor = db.snapshots.aggregate(pipeline)
    existing_snapshots = await cursor.to_list(length=None)

    # ── Step 6: Run conflict detection ────────────────────────────────────
    new_conflicts = detect_conflicts(
        patient_id=payload.patient_id,
        clinic_id=payload.clinic_id,
        new_source=payload.source.value,
        new_meds=normalised_meds,
        existing_snapshots=existing_snapshots,
    )

    # ── Step 7: Persist conflicts (skip existing unresolved duplicates) ───
    # Idempotency: if the same conflict type for the same drugs already
    # exists as unresolved, we don't create a duplicate record.
    saved_conflicts = []
    for c in new_conflicts:
        existing = await db.conflicts.find_one({
            "patient_id":    c["patient_id"],
            "conflict_type": c["conflict_type"],
            "involved_drugs": sorted(c["involved_drugs"]),
            "status":        "unresolved",
        })
        if existing:
            c["_id"] = existing["_id"]
        else:
            c["involved_drugs"] = sorted(c["involved_drugs"])
            ins = await db.conflicts.insert_one(c)
            c["_id"] = ins.inserted_id

        saved_conflicts.append(_format_conflict(c))

    # ── Step 8: Return structured result ─────────────────────────────────
    return {
        "snapshot_id":        snapshot_id,
        "version":            next_version,
        "conflicts_detected": len(saved_conflicts),
        "conflicts":          saved_conflicts,
    }


def _format_conflict(c: Dict) -> Dict:
    """Convert a raw MongoDB conflict doc to a clean response dict."""
    return {
        "conflict_id":      str(c["_id"]),
        "patient_id":       c["patient_id"],
        "clinic_id":        c["clinic_id"],
        "conflict_type":    c["conflict_type"],
        "status":           c["status"],
        "description":      c["description"],
        "involved_drugs":   c["involved_drugs"],
        "sources_involved": c["sources_involved"],
        "severity":         c["severity"],
        "detected_at":      c["detected_at"],
        "resolved_at":      c.get("resolved_at"),
        "resolution":       c.get("resolution"),
    }