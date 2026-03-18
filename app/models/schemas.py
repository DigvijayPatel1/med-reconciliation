from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ── Enums keep string values constrained to known options ──────────────────

class MedicationStatus(str, Enum):
    active = "active"
    stopped = "stopped"
    on_hold = "on_hold"


class SourceType(str, Enum):
    # These are the three sources a medication list can come from
    clinic_emr = "clinic_emr"
    hospital_discharge = "hospital_discharge"
    patient_reported = "patient_reported"


class ConflictStatus(str, Enum):
    unresolved = "unresolved"
    resolved = "resolved"


class ConflictType(str, Enum):
    dose_mismatch = "dose_mismatch"
    blacklisted_combination = "blacklisted_combination"
    status_mismatch = "status_mismatch"
    class_combination = "class_combination"
    out_of_range = "out_of_range"


# ── Request Models (data coming IN from the API caller) ────────────────────

class MedicationItem(BaseModel):
    """A single drug entry inside a medication list."""
    name: str = Field(..., min_length=1, description="Drug name")
    dose: Optional[float] = Field(None, ge=0, description="Numeric dose value")
    unit: Optional[str] = Field(None, description="e.g. mg, mcg, units")
    frequency: Optional[str] = Field(None, description="e.g. once daily, twice daily")
    status: MedicationStatus = Field(default=MedicationStatus.active)
    notes: Optional[str] = None

    @validator("name")
    def name_must_not_be_blank(cls, v):
        # This catches names that are all spaces e.g. "   "
        if not v.strip():
            raise ValueError("Medication name cannot be blank")
        return v


class IngestPayload(BaseModel):
    """
    The body of a POST /ingest/ request.
    A clinician or system submits: who is the patient, which system is
    sending this, and what medications are listed.
    """
    patient_id: str = Field(..., min_length=1)
    clinic_id: str = Field(..., min_length=1)
    source: SourceType
    medications: List[MedicationItem] = Field(..., min_items=1)
    recorded_by: Optional[str] = None
    notes: Optional[str] = None


class ConflictResolutionPayload(BaseModel):
    """
    Body of a PATCH /conflicts/{id}/resolve request.
    A clinician explains WHY the conflict is resolved and which
    source they trust.
    """
    resolved_by: str = Field(..., min_length=1)
    resolution_reason: str = Field(..., min_length=1)
    chosen_source: Optional[SourceType] = Field(
        None,
        description="Which source was deemed the truth. Can be null if resolution is independent."
    )
    notes: Optional[str] = None


# ── Response Models (data going OUT to the API caller) ────────────────────

class ConflictResponse(BaseModel):
    conflict_id: str
    patient_id: str
    clinic_id: str
    conflict_type: str
    status: str
    description: str
    involved_drugs: List[str]
    sources_involved: List[str]
    severity: str
    detected_at: datetime
    resolved_at: Optional[datetime]
    resolution: Optional[dict]


class IngestResponse(BaseModel):
    message: str
    snapshot_id: str
    version: int
    conflicts_detected: int
    conflicts: List[ConflictResponse]