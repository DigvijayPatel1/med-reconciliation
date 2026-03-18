PATIENT_NOT_FOUND = "Patient with id '{patient_id}' not found."
SNAPSHOT_NOT_FOUND = "No snapshot found for patient '{patient_id}' from source '{source}'."
CONFLICT_NOT_FOUND = "Conflict with id '{conflict_id}' not found."
CONFLICT_ALREADY_RESOLVED = "Conflict '{conflict_id}' is already resolved."
INVALID_PAYLOAD = "Invalid request payload: {detail}"
DATABASE_ERROR = "A database error occurred. Please try again."
INTERNAL_ERROR = "An unexpected error occurred."

INGEST_SUCCESS = "Medication list ingested successfully for patient '{patient_id}' from source '{source}'."
CONFLICT_RESOLVED = "Conflict '{conflict_id}' has been resolved."
PATIENT_CREATED = "New patient record created for '{patient_id}'."

# These are f-string templates used by the conflict detector
DOSE_MISMATCH_DESC = (
    "Drug '{drug}' has conflicting doses: {source_a} reports {dose_a} {unit}, "
    "{source_b} reports {dose_b} {unit}."
)
STATUS_MISMATCH_DESC = (
    "Drug '{drug}' has conflicting statuses: {source_a} reports '{status_a}', "
    "{source_b} reports '{status_b}'."
)
BLACKLISTED_COMBO_DESC = "Drugs {drugs} should not be combined: {reason}"
CLASS_COMBO_DESC = "Drug classes {classes} should not be combined: {reason}"
OUT_OF_RANGE_DESC = (
    "Drug '{drug}' dose {dose} {unit} is outside the safe range "
    "({min}–{max} {unit})."
)