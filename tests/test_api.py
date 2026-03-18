# tests/test_api.py
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db import database as db_module


@pytest_asyncio.fixture
async def client(monkeypatch):
    """
    Creates a test HTTP client connected to the FastAPI app.
    Replaces the real MongoDB with an in-memory mock so tests are
    fast and isolated — no real database needed.
    """
    import mongomock_motor
    mock_client = mongomock_motor.AsyncMongoMockClient()
    mock_db = mock_client["test_db"]

    monkeypatch.setattr(db_module, "db", mock_db)
    monkeypatch.setattr(db_module, "client", mock_client)

    async def noop_connect():
        db_module.db = mock_db
        db_module.client = mock_client

    async def noop_close():
        pass

    monkeypatch.setattr(db_module, "connect_db", noop_connect)
    monkeypatch.setattr(db_module, "close_db", noop_close)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Ingest endpoint tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_success(client):
    resp = await client.post("/api/v1/ingest/", json={
        "patient_id": "T001", "clinic_id": "C1", "source": "clinic_emr",
        "medications": [{"name": "Metformin", "dose": 500, "unit": "mg", "status": "active"}],
    })
    assert resp.status_code == 201
    assert resp.json()["version"] == 1


@pytest.mark.asyncio
async def test_second_ingest_increments_version(client):
    payload = {"patient_id": "T002", "clinic_id": "C1", "source": "clinic_emr",
               "medications": [{"name": "Aspirin", "dose": 81, "unit": "mg", "status": "active"}]}
    r1 = await client.post("/api/v1/ingest/", json=payload)
    r2 = await client.post("/api/v1/ingest/", json=payload)
    assert r1.json()["version"] == 1
    assert r2.json()["version"] == 2


@pytest.mark.asyncio
async def test_ingest_detects_dose_mismatch(client):
    await client.post("/api/v1/ingest/", json={
        "patient_id": "T003", "clinic_id": "C1", "source": "clinic_emr",
        "medications": [{"name": "Metformin", "dose": 500, "unit": "mg", "status": "active"}],
    })
    resp = await client.post("/api/v1/ingest/", json={
        "patient_id": "T003", "clinic_id": "C1", "source": "hospital_discharge",
        "medications": [{"name": "Metformin", "dose": 1000, "unit": "mg", "status": "active"}],
    })
    types = [c["conflict_type"] for c in resp.json()["conflicts"]]
    assert "dose_mismatch" in types


@pytest.mark.asyncio
async def test_ingest_detects_blacklisted_combo(client):
    resp = await client.post("/api/v1/ingest/", json={
        "patient_id": "T004", "clinic_id": "C1", "source": "clinic_emr",
        "medications": [
            {"name": "Warfarin", "dose": 5,  "unit": "mg", "status": "active"},
            {"name": "Aspirin",  "dose": 81, "unit": "mg", "status": "active"},
        ],
    })
    types = [c["conflict_type"] for c in resp.json()["conflicts"]]
    assert "blacklisted_combination" in types


@pytest.mark.asyncio
async def test_ingest_missing_medications_returns_422(client):
    resp = await client.post("/api/v1/ingest/", json={
        "patient_id": "T005", "clinic_id": "C1", "source": "clinic_emr",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_invalid_source_returns_422(client):
    resp = await client.post("/api/v1/ingest/", json={
        "patient_id": "T006", "clinic_id": "C1", "source": "invalid_source",
        "medications": [{"name": "Aspirin", "dose": 81, "unit": "mg", "status": "active"}],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_blank_name_returns_422(client):
    resp = await client.post("/api/v1/ingest/", json={
        "patient_id": "T007", "clinic_id": "C1", "source": "clinic_emr",
        "medications": [{"name": "   ", "dose": 10, "unit": "mg", "status": "active"}],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_negative_dose_returns_422(client):
    resp = await client.post("/api/v1/ingest/", json={
        "patient_id": "T008", "clinic_id": "C1", "source": "clinic_emr",
        "medications": [{"name": "Metformin", "dose": -100, "unit": "mg", "status": "active"}],
    })
    assert resp.status_code == 422


# ── History & Conflict retrieval ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_history_returns_snapshots(client):
    await client.post("/api/v1/ingest/", json={
        "patient_id": "H001", "clinic_id": "C1", "source": "clinic_emr",
        "medications": [{"name": "Omeprazole", "dose": 20, "unit": "mg", "status": "active"}],
    })
    resp = await client.get("/api/v1/ingest/patients/H001/history")
    assert resp.status_code == 200
    assert len(resp.json()["snapshots"]) == 1


@pytest.mark.asyncio
async def test_get_history_unknown_patient_returns_404(client):
    resp = await client.get("/api/v1/ingest/patients/NOBODY/history")
    assert resp.status_code == 404


# ── Conflict resolution ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_conflict_succeeds(client):
    ingest = await client.post("/api/v1/ingest/", json={
        "patient_id": "R001", "clinic_id": "C1", "source": "clinic_emr",
        "medications": [
            {"name": "Warfarin", "dose": 5,  "unit": "mg", "status": "active"},
            {"name": "Aspirin",  "dose": 81, "unit": "mg", "status": "active"},
        ],
    })
    conflict_id = ingest.json()["conflicts"][0]["conflict_id"]
    resp = await client.patch(f"/api/v1/ingest/conflicts/{conflict_id}/resolve", json={
        "resolved_by": "Dr. Smith",
        "resolution_reason": "Acceptable short-term risk, monitoring in place",
        "chosen_source": "clinic_emr",
    })
    assert resp.status_code == 200
    assert resp.json()["resolution"]["resolved_by"] == "Dr. Smith"


@pytest.mark.asyncio
async def test_resolve_same_conflict_twice_returns_409(client):
    ingest = await client.post("/api/v1/ingest/", json={
        "patient_id": "R002", "clinic_id": "C1", "source": "clinic_emr",
        "medications": [
            {"name": "Warfarin", "dose": 5,  "unit": "mg", "status": "active"},
            {"name": "Aspirin",  "dose": 81, "unit": "mg", "status": "active"},
        ],
    })
    conflict_id = ingest.json()["conflicts"][0]["conflict_id"]
    resolution = {"resolved_by": "Dr. X", "resolution_reason": "Accepted"}
    await client.patch(f"/api/v1/ingest/conflicts/{conflict_id}/resolve", json=resolution)
    second = await client.patch(f"/api/v1/ingest/conflicts/{conflict_id}/resolve", json=resolution)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_resolve_invalid_id_returns_400(client):
    resp = await client.patch("/api/v1/ingest/conflicts/not_valid_id/resolve", json={
        "resolved_by": "Dr. X", "resolution_reason": "test",
    })
    assert resp.status_code == 400


# ── Reporting endpoints ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_unresolved_conflicts(client):
    await client.post("/api/v1/ingest/", json={
        "patient_id": "RPT01", "clinic_id": "CLINIC_RPT", "source": "clinic_emr",
        "medications": [
            {"name": "Warfarin", "dose": 5,  "unit": "mg", "status": "active"},
            {"name": "Aspirin",  "dose": 81, "unit": "mg", "status": "active"},
        ],
    })
    resp = await client.get("/api/v1/reports/clinics/CLINIC_RPT/unresolved-conflicts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["patient_count"] >= 1


@pytest.mark.asyncio
async def test_report_30_day_summary(client):
    await client.post("/api/v1/ingest/", json={
        "patient_id": "RPT02", "clinic_id": "CLINIC_RPT2", "source": "clinic_emr",
        "medications": [
            {"name": "Warfarin", "dose": 5,  "unit": "mg", "status": "active"},
            {"name": "Aspirin",  "dose": 81, "unit": "mg", "status": "active"},
        ],
    })
    resp = await client.get("/api/v1/reports/clinics/conflict-summary/30-days?min_conflicts=1")
    assert resp.status_code == 200
    data = resp.json()
    assert "clinics" in data
    assert "period_days" in data
    assert data["period_days"] == 30

@pytest.mark.asyncio
async def test_report_empty_clinic_returns_zero(client):
    resp = await client.get("/api/v1/reports/clinics/EMPTY_CLINIC/unresolved-conflicts")
    assert resp.status_code == 200
    assert resp.json()["patient_count"] == 0