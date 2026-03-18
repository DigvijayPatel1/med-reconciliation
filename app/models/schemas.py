from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MedicationStatus(str, Enum):
    active = "active"
    stopped = "stopped"
    on_hold = "on_hold"


class SourceType(str, Enum):
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


class MedicationItem(BaseModel):
    name: str = Field(..., min_length=1, description="Drug name")
    dose: Optional[float] = Field(None, ge=0, description="Numeric dose value")
    unit: Optional[str] = Field(None, description="e.g. mg, mcg, units")
    frequency: Optional[str] = Field(None, description="e.g. once daily, twice daily")
    status: MedicationStatus = Field(default=MedicationStatus.active)
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v):
        if not v.strip():
            raise ValueError("Medication name cannot be blank")
        return v


class IngestPayload(BaseModel):
    patient_id: str = Field(..., min_length=1)
    clinic_id: str = Field(..., min_length=1)
    source: SourceType
    medications: List[MedicationItem] = Field(..., min_length=1)
    recorded_by: Optional[str] = None
    notes: Optional[str] = None


class ConflictResolutionPayload(BaseModel):
    resolved_by: str = Field(..., min_length=1)
    resolution_reason: str = Field(..., min_length=1)
    chosen_source: Optional[SourceType] = Field(None)
    notes: Optional[str] = None


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