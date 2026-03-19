# Medication Reconciliation & Conflict Reporting Service

A robust FastAPI-based service that ingests medication lists from multiple clinical sources, detects conflicts, maintains versioned history, and surfaces unresolved conflicts for clinical review.

## Overview

This service solves a critical healthcare problem: **medication reconciliation across disparate clinical systems**. When a patient's medication information comes from multiple sources (clinic EMRs, hospital discharge summaries, patient reports), discrepancies are inevitable. This service:

- **Normalizes** medication data from different sources
- **Detects conflicts** across sources using clinical rules
- **Maintains audit trails** with full version history
- **Surfaces actionable insights** through reporting endpoints

### Quick Links

- 🔗 **Repository**: [github.com/DigvijayPatel1/med-reconciliation](https://github.com/DigvijayPatel1/med-reconciliation.git)
- 🚀 **Live Demo**: [med-reconciliation-7320.onrender.com](https://med-reconciliation-7320.onrender.com)
- 📖 **API Docs**: [Swagger UI](https://med-reconciliation-7320.onrender.com/docs)

## Key Features

### 1. **Multi-Source Medication Ingestion**

- Accept medication lists from three source types:
  - `clinic_emr` — Local clinic electronic health records
  - `hospital_discharge` — Hospital discharge summaries
  - `patient_reported` — Patient-provided medication lists
- Validate and normalize all incoming data

### 2. **Intelligent Conflict Detection**

The service detects 5 types of medication conflicts:

| Conflict Type               | Description                                    | Example                                |
| --------------------------- | ---------------------------------------------- | -------------------------------------- |
| **Dose Mismatch**           | Same drug, different doses across sources      | Metformin 500mg vs 1000mg              |
| **Status Mismatch**         | Conflicting medication status (active/stopped) | Lisinopril active vs stopped           |
| **Blacklisted Combination** | Dangerous drug-drug interactions               | Warfarin + aspirin (bleeding risk)     |
| **Class Combination**       | Conflicting drug classes                       | ACE inhibitor + ARB (redundant/unsafe) |
| **Out of Range**            | Dose outside safe clinical range               | Lisinopril 100mg (normal max: 40mg)    |

All rules are configurable in `rules.json`.

### 3. **Versioned History & Audit Trail**

- Every medication list submission creates an immutable snapshot
- Full audit trail: who submitted, when, from which source
- Time-machine capability: review medication lists at any point in time

### 4. **Clinical Reporting**

Pre-built aggregation queries:

- **Unresolved Conflicts Report** — All patients in a clinic with unresolved conflicts
- **30-Day Conflict Summary** — Per-clinic conflict metrics (high-volume identification)

### 5. **Conflict Resolution Workflow**

- Mark conflicts as resolved with full context:
  - Who resolved it
  - Why (clinical reasoning)
  - Which source was trusted
  - Supporting notes
- Resolution preserves the full audit trail (no data deletion)

## System Architecture

```
Medication Reconciliation Service
│
├─ app/
│  ├─ main.py                          # FastAPI app initialization & routes
│  │
│  ├─ api/routes/
│  │  ├─ ingestion.py                  # POST /api/v1/ingest, conflict resolution
│  │  └─ reports.py                    # GET /api/v1/reports/* (aggregation queries)
│  │
│  ├─ services/
│  │  ├─ ingestion.py                  # Business logic: ingest → normalize → detect
│  │  ├─ normalizer.py                 # Medication data normalization
│  │  └─ conflict_detector.py           # Core conflict detection logic
│  │
│  ├─ models/
│  │  └─ schemas.py                    # Pydantic models (validation & serialization)
│  │
│  ├─ db/
│  │  └─ database.py                   # MongoDB connection, indexes
│  │
│  └─ resources/
│     └─ messages.py                   # Standardized response messages
│
├─ tests/
│  ├─ conftest.py                      # Pytest fixtures and setup
│  ├─ test_api.py                      # Integration tests
│  ├─ test_conflict_detector.py         # Unit tests for conflict logic
│  └─ test_normalizer.py                # Unit tests for normalization
│
├─ rules.json                          # Clinical rules (drugs, classes, combos, ranges)
├─ seed.py                             # Script to populate test data
└─ requirements.txt                    # Python dependencies
```

## Installation & Setup

### Prerequisites

- Python 3.10+
- MongoDB (local or Atlas)
- pip / virtualenv

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/DigvijayPatel1/med-reconciliation.git
cd med-reconciliation
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root:

```env
# MongoDB connection
MONGODB_URL=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
DATABASE_NAME=med_reconciliation
```

**For MongoDB Atlas:**

1. Create a cluster at https://www.mongodb.com/cloud/atlas
2. Create a database user (in "Database Access")
3. Add your IP to the IP allowlist
4. Copy the connection string and paste into `MONGODB_URL`

**For Local MongoDB:**

```env
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=med_reconciliation
```

### 3. Initialize Database

The database schema (indexes) is created automatically when the app starts. To seed test data:

```bash
python seed.py
```

This creates sample patients and medication lists with various conflict scenarios (for testing/demo).

## Running the Application

### Development Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API documentation automatically available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health check**: http://localhost:8000/health

### Deployed Service

The application is live and publicly accessible:

- 🌐 **[https://med-reconciliation-7320.onrender.com](https://med-reconciliation-7320.onrender.com)**
- 📚 **[API Docs (Swagger)](https://med-reconciliation-7320.onrender.com/docs)**
- ❤️ **[Health Check](https://med-reconciliation-7320.onrender.com/health)**

### Production

```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000
```

Or use the included `Procfile` for deployment platforms (Render, Heroku, etc.)

## API Endpoints

### Ingestion Endpoints

#### `POST /api/v1/ingest`

Submit a medication list from a source.

**Request Body:**

```json
{
  "patient_id": "P001",
  "clinic_id": "CLINIC_A",
  "source": "clinic_emr",
  "medications": [
    {
      "name": "Metformin",
      "dose": 500,
      "unit": "mg",
      "frequency": "twice daily",
      "status": "active",
      "notes": "Optional clinical notes"
    }
  ],
  "recorded_by": "Dr. Smith",
  "notes": "Optional submission notes"
}
```

**Response (201 Created):**

```json
{
  "message": "Ingested medication list for patient P001 from clinic_emr",
  "snapshot_id": "507f1f77bcf86cd799439011",
  "version": 1,
  "conflicts_detected": 2,
  "conflicts": [
    {
      "conflict_id": "507f1f77bcf86cd799439012",
      "patient_id": "P001",
      "clinic_id": "CLINIC_A",
      "conflict_type": "dose_mismatch",
      "status": "unresolved",
      "description": "Metformin: dose 500mg (clinic_emr) vs 1000mg (hospital_discharge)",
      "involved_drugs": ["Metformin"],
      "sources_involved": ["clinic_emr", "hospital_discharge"],
      "severity": "medium",
      "detected_at": "2024-03-19T12:34:56Z",
      "resolved_at": null,
      "resolution": null
    }
  ]
}
```

#### `GET /api/v1/ingest/patients/{patient_id}/history`

Retrieve all medication snapshots for a patient (version history).

**Response:**

```json
{
  "patient_id": "P001",
  "snapshots": [
    {
      "_id": "507f...",
      "patient_id": "P001",
      "clinic_id": "CLINIC_A",
      "source": "clinic_emr",
      "version": 1,
      "medications": [...],
      "submitted_at": "2024-03-19T12:34:56Z"
    }
  ]
}
```

#### `GET /api/v1/ingest/patients/{patient_id}/conflicts?status=unresolved`

Get all conflicts for a patient (optionally filtered by status).

**Query Parameters:**

- `status` (optional): `unresolved` or `resolved`

**Response:**

```json
{
  "patient_id": "P001",
  "conflicts": [
    {
      "conflict_id": "...",
      "conflict_type": "dose_mismatch",
      "status": "unresolved",
      "severity": "high",
      ...
    }
  ]
}
```

#### `PATCH /api/v1/ingest/conflicts/{conflict_id}/resolve`

Mark a conflict as resolved and add context.

**Request Body:**

```json
{
  "resolved_by": "Dr. Johnson",
  "resolution_reason": "Clinic EMR dose verified with patient; hospital discharge was data entry error",
  "chosen_source": "clinic_emr",
  "notes": "Patient confirmed 500mg is correct"
}
```

**Response:**

```json
{
  "conflict_id": "507f...",
  "status": "resolved",
  "resolved_at": "2024-03-19T13:00:00Z",
  "resolution": {
    "resolved_by": "Dr. Johnson",
    "resolution_reason": "...",
    "chosen_source": "clinic_emr",
    "notes": "...",
    "resolved_at": "2024-03-19T13:00:00Z"
  }
}
```

### Reporting Endpoints

#### `GET /api/v1/reports/clinics/{clinic_id}/unresolved-conflicts`

List all patients in a clinic with at least one unresolved conflict.

**Response:**

```json
{
  "clinic_id": "CLINIC_A",
  "patient_count": 3,
  "patients": [
    {
      "patient_id": "P001",
      "name": "John Doe",
      "unresolved_conflict_count": 2,
      "conflict_types": ["dose_mismatch", "status_mismatch"],
      "severities": ["medium", "high"],
      "oldest_conflict": "2024-03-18T10:00:00Z",
      "latest_conflict": "2024-03-19T14:00:00Z"
    }
  ]
}
```

#### `GET /api/v1/reports/clinics/conflict-summary/30-days?min_conflicts=2`

Per-clinic summary of patients with >= N conflicts in the last 30 days.

**Query Parameters:**

- `min_conflicts` (optional, default=2): Minimum conflict count to include

**Response:**

```json
{
  "clinic_summary": [
    {
      "clinic_id": "CLINIC_A",
      "patients_with_conflicts": 12,
      "total_conflicts": 34,
      "total_unresolved": 18,
      "avg_conflicts_per_patient": 2.8
    }
  ]
}
```

## Database Schema

### Collections

#### `patients`

Stores patient master data.

```
{
  "_id": ObjectId,
  "patient_id": "P001",
  "clinic_id": "CLINIC_A",
  "name": "John Doe",
  "created_at": ISODate,
  "updated_at": ISODate
}
```

**Indexes:**

- `patient_id` (unique)
- `clinic_id`

#### `snapshots`

Immutable medication list submissions (one per source per patient).

```
{
  "_id": ObjectId,
  "patient_id": "P001",
  "clinic_id": "CLINIC_A",
  "source": "clinic_emr",
  "version": 1,
  "medications": [
    {
      "name": "Metformin",
      "dose": 500,
      "unit": "mg",
      "frequency": "twice daily",
      "status": "active",
      "notes": "..."
    }
  ],
  "recorded_by": "Dr. Smith",
  "submitted_at": ISODate
}
```

**Indexes:**

- `patient_id`
- `clinic_id`
- `source`
- `(patient_id, source)` (compound)

#### `conflicts`

Detected medication conflicts with audit trail.

```
{
  "_id": ObjectId,
  "patient_id": "P001",
  "clinic_id": "CLINIC_A",
  "conflict_type": "dose_mismatch",
  "status": "unresolved" | "resolved",
  "description": "Metformin: 500mg vs 1000mg",
  "involved_drugs": ["Metformin"],
  "sources_involved": ["clinic_emr", "hospital_discharge"],
  "severity": "high" | "medium" | "low",
  "detected_at": ISODate,
  "resolved_at": ISODate | null,
  "resolution": {
    "resolved_by": "Dr. Johnson",
    "resolution_reason": "...",
    "chosen_source": "clinic_emr",
    "notes": "...",
    "resolved_at": ISODate
  } | null
}
```

**Indexes:**

- `patient_id`
- `clinic_id`
- `status`
- `detected_at`
- `(patient_id, status)`

## Configuration: `rules.json`

This file contains all clinical intelligence. You can modify it without restarting (rules are loaded once at startup, but you can update them between deployments).

### Structure

#### `dose_ranges`

Safe clinical dose ranges per drug.

```json
{
  "metformin": {
    "min_mg": 500,
    "max_mg": 2550,
    "unit": "mg"
  }
}
```

#### `blacklisted_combinations`

Dangerous drug-drug interactions.

```json
{
  "drugs": ["warfarin", "aspirin"],
  "reason": "Concurrent use significantly increases bleeding risk",
  "severity": "high"
}
```

#### `drug_classes`

Group drugs by therapeutic class.

```json
{
  "ace_inhibitors": ["lisinopril", "enalapril", "ramipril"],
  "arbs": ["losartan", "valsartan"],
  ...
}
```

#### `class_combination_rules`

Dangerous class-level interactions (e.g., dual RAS blockade).

#### `dose_tolerance_percent`

Threshold for dose matching (default 10%). Doses within 10% are considered equivalent.

## Testing

### Run All Tests

```bash
pytest
```

### Run Specific Test Suite

```bash
# Unit tests
pytest tests/test_normalizer.py -v
pytest tests/test_conflict_detector.py -v

# Integration tests
pytest tests/test_api.py -v
```

### Test Configuration

Tests are configured in `pytest.ini`:

- `asyncio_mode = auto` — Automatic async handling
- `testpaths = tests` — Test discovery root
- Deprecation warnings filtered

Test fixtures (database mocks, sample data) are in `tests/conftest.py`.

## Deployment

### Render.com (Current Deployment)

The application is currently deployed on Render at: **[https://med-reconciliation-7320.onrender.com](https://med-reconciliation-7320.onrender.com)**

**Deployment Setup:**

The `render.yaml` file is pre-configured:

1. Connect your GitHub repo to Render
2. Create a new Web Service pointing to this repo
3. Set environment variables:
   - `MONGODB_URL` — Your MongoDB Atlas connection string
   - `DATABASE_NAME` — Database name (default: `med_reconciliation`)

The service will automatically:

- Install dependencies from `requirements.txt`
- Run migrations/schema setup
- Start the FastAPI server

**GitHub Integration:**
- Repository: [github.com/DigvijayPatel1/med-reconciliation](https://github.com/DigvijayPatel1/med-reconciliation.git)
- Render automatically deploys on every push to the main branch

### Heroku

Use the included `Procfile`:

```bash
heroku create my-med-service
heroku config:set MONGODB_URL=<your-atlas-url>
git push heroku main
```

### Docker

```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Core Algorithm: Conflict Detection

The conflict detection engine (`app/services/conflict_detector.py`) is the heart of the service.

### How It Works

When a new medication list arrives:

1. **Combine all sources** — Build a unified view of all medications from this patient across all sources
2. **Cross-source comparison** — For each pair of sources, compare drugs by name
3. **Apply rules** — Check each combination against:
   - Dose tolerance (default ±10%)
   - Status consistency (active vs stopped)
   - Blacklisted drug combos (from `rules.json`)
   - Drug class conflicts (e.g., ACE + ARB)
   - Dose ranges (safety bounds from `rules.json`)
4. **Return conflicts** — List all detected conflicts with severity and context

### Complexity

- **Time:** O(n² × m) where n = number of sources, m = average medications per source
- **Space:** O(n × m)

Typically very fast since patients have 5-20 medications across 2-4 sources.

## Understanding the Data Flow

```
1. Client submits medication list
   ↓
2. API validates payload (Pydantic schemas)
   ↓
3. Service normalizes medication names/units
   ↓
4. Conflict detector compares against existing snapshots
   ↓
5. Conflict records created in MongoDB
   ↓
6. New snapshot (version) stored
   ↓
7. Response returned with conflict details
```

## Troubleshooting

### Issue: "MONGODB_URL is not set"

**Solution:** Ensure `.env` file exists in project root with:

```env
MONGODB_URL=mongodb+srv://...
DATABASE_NAME=med_reconciliation
```

### Issue: Connection timeout to MongoDB

**Solution:**

- Verify IP is added to MongoDB Atlas "Network Access"
- Check credentials in connection string
- Test locally: connect with MongoDB Compass using the same URL

### Issue: Tests fail with database errors

**Solution:** Tests use `mongomock-motor` (in-memory mock). If still failing:

```bash
pytest tests/ -v --tb=short
```

### Issue: Conflicts not being detected

**Solution:**

- Verify `rules.json` has the drugs/classes in question
- Check conflict severity thresholds
- Review conflict detector logs with `-v` flag

## Contributing

Contributions are welcome! To contribute to the project:

1. Fork the repository: [github.com/DigvijayPatel1/med-reconciliation](https://github.com/DigvijayPatel1/med-reconciliation)
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes and add tests
4. Run `pytest` to validate all tests pass
5. Commit with a clear message: `git commit -m "Add feature X"`
6. Push to your fork and create a Pull Request
7. Ensure your PR includes:
   - Clear description of changes
   - Tests for new functionality
   - Updated documentation if needed

## License

[Specify your license, e.g., MIT, Apache 2.0]

## Support

For issues, questions, or feature requests, please open an issue on GitHub:

🔗 **[github.com/DigvijayPatel1/med-reconciliation/issues](https://github.com/DigvijayPatel1/med-reconciliation/issues)**

You can also reach out through the following channels:
- 📧 Create an issue in the repository
- 🌐 Visit the live deployment: [https://med-reconciliation-7320.onrender.com](https://med-reconciliation-7320.onrender.com)
- 📚 Check the API documentation: [https://med-reconciliation-7320.onrender.com/docs](https://med-reconciliation-7320.onrender.com/docs)
