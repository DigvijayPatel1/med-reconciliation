import asyncio
import argparse
import httpx

BASE_URL = "http://localhost:8000/api/v1"

# Each tuple: (patient_id, clinic_id, source, medications_list)
# Crafted to trigger specific conflict types
PAYLOADS = [
    # P001 — DOSE MISMATCH: clinic says 500mg, hospital says 1000mg
    ("P001", "CLINIC_A", "clinic_emr", [
        {"name": "Metformin", "dose": 500, "unit": "mg", "frequency": "twice daily", "status": "active"},
        {"name": "Lisinopril", "dose": 10,  "unit": "mg", "frequency": "once daily",  "status": "active"},
    ]),
    ("P001", "CLINIC_A", "hospital_discharge", [
        {"name": "Metformin", "dose": 1000, "unit": "MG", "frequency": "twice daily", "status": "active"},
        {"name": "Lisinopril", "dose": 10,  "unit": "mg", "frequency": "once daily",  "status": "active"},
    ]),
    ("P001", "CLINIC_A", "patient_reported", [
        {"name": "metformin 500mg", "dose": 500, "unit": "mg", "frequency": "BD", "status": "active"},
        {"name": "Aspirin",         "dose": 81,  "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),

    # P002 — BLACKLISTED COMBO: warfarin + aspirin
    ("P002", "CLINIC_A", "clinic_emr", [
        {"name": "Warfarin",     "dose": 5,  "unit": "mg", "frequency": "once daily", "status": "active"},
        {"name": "Atorvastatin", "dose": 40, "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),
    ("P002", "CLINIC_A", "patient_reported", [
        {"name": "Aspirin",  "dose": 81, "unit": "mg", "frequency": "QD",         "status": "active"},
        {"name": "Warfarin", "dose": 5,  "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),

    # P003 — STATUS MISMATCH: metoprolol active vs stopped
    ("P003", "CLINIC_A", "clinic_emr", [
        {"name": "Metoprolol", "dose": 50, "unit": "mg", "frequency": "twice daily", "status": "active"},
        {"name": "Amlodipine", "dose": 5,  "unit": "mg", "frequency": "once daily",  "status": "active"},
    ]),
    ("P003", "CLINIC_A", "hospital_discharge", [
        {"name": "Metoprolol", "dose": 50, "unit": "mg", "frequency": "twice daily", "status": "stopped"},
        {"name": "Amlodipine", "dose": 5,  "unit": "mg", "frequency": "once daily",  "status": "active"},
        {"name": "Furosemide", "dose": 40, "unit": "mg", "frequency": "once daily",  "status": "active"},
    ]),

    # P004 — CLASS COMBINATION: ACE inhibitor + ARB (both block the same system)
    ("P004", "CLINIC_B", "clinic_emr", [
        {"name": "Lisinopril", "dose": 10, "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),
    ("P004", "CLINIC_B", "hospital_discharge", [
        {"name": "Losartan",   "dose": 50, "unit": "mg", "frequency": "once daily", "status": "active"},
        {"name": "Lisinopril", "dose": 10, "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),

    # P005 — OUT OF RANGE: atorvastatin max is 80mg; 120mg is dangerous
    ("P005", "CLINIC_B", "clinic_emr", [
        {"name": "Atorvastatin", "dose": 120, "unit": "mg", "frequency": "once daily", "status": "active"},
        {"name": "Metformin",    "dose": 500, "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),

    # P006 — MULTIPLE: dose mismatch + blacklisted combo
    ("P006", "CLINIC_B", "clinic_emr", [
        {"name": "Warfarin",  "dose": 3,   "unit": "mg", "frequency": "once daily",       "status": "active"},
        {"name": "Ibuprofen", "dose": 400, "unit": "mg", "frequency": "three times daily", "status": "active"},
    ]),
    ("P006", "CLINIC_B", "hospital_discharge", [
        {"name": "Warfarin",   "dose": 5,  "unit": "mg", "frequency": "once daily", "status": "active"},
        {"name": "Omeprazole", "dose": 20, "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),

    # P007 — CLEAN: no conflicts, all sources agree
    ("P007", "CLINIC_C", "clinic_emr", [
        {"name": "Omeprazole",   "dose": 20,  "unit": "mg",  "frequency": "once daily", "status": "active"},
        {"name": "Levothyroxine","dose": 100, "unit": "mcg", "frequency": "once daily", "status": "active"},
    ]),
    ("P007", "CLINIC_C", "patient_reported", [
        {"name": "Omeprazole",   "dose": 20,  "unit": "mg",  "frequency": "once daily", "status": "active"},
        {"name": "Levothyroxine","dose": 100, "unit": "mcg", "frequency": "once daily", "status": "active"},
    ]),

    # P008 — dose mismatch lisinopril + status mismatch furosemide
    ("P008", "CLINIC_C", "clinic_emr", [
        {"name": "Lisinopril", "dose": 5,  "unit": "mg", "frequency": "once daily", "status": "active"},
        {"name": "Furosemide", "dose": 20, "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),
    ("P008", "CLINIC_C", "hospital_discharge", [
        {"name": "Lisinopril", "dose": 20, "unit": "mg", "frequency": "once daily", "status": "active"},
        {"name": "Furosemide", "dose": 20, "unit": "mg", "frequency": "once daily", "status": "stopped"},
    ]),

    # P009 — CLASS COMBINATION: anticoagulant + NSAID
    ("P009", "CLINIC_C", "clinic_emr", [
        {"name": "Apixaban", "dose": 5, "unit": "mg", "frequency": "twice daily", "status": "active"},
    ]),
    ("P009", "CLINIC_C", "patient_reported", [
        {"name": "Naproxen", "dose": 500, "unit": "mg", "frequency": "twice daily", "status": "active"},
        {"name": "Apixaban", "dose": 5,   "unit": "mg", "frequency": "twice daily", "status": "active"},
    ]),

    # P010 — CLEAN: single source, no conflicts
    ("P010", "CLINIC_A", "clinic_emr", [
        {"name": "Metformin",    "dose": 1000, "unit": "mg", "frequency": "twice daily", "status": "active"},
        {"name": "Atorvastatin", "dose": 20,   "unit": "mg", "frequency": "once daily",  "status": "active"},
    ]),

    # P011 — OUT OF RANGE + dose mismatch: amlodipine max is 10mg
    ("P011", "CLINIC_A", "clinic_emr", [
        {"name": "Amlodipine", "dose": 2.5, "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),
    ("P011", "CLINIC_A", "hospital_discharge", [
        {"name": "Amlodipine", "dose": 15, "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),

    # P012 — THREE-SOURCE dose conflict for metformin
    ("P012", "CLINIC_B", "clinic_emr", [
        {"name": "Metformin", "dose": 500,  "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),
    ("P012", "CLINIC_B", "hospital_discharge", [
        {"name": "Metformin", "dose": 850,  "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),
    ("P012", "CLINIC_B", "patient_reported", [
        {"name": "Metformin", "dose": 1000, "unit": "mg", "frequency": "OD",         "status": "active"},
    ]),

    # P013 — statin + clarithromycin (blacklisted combo)
    ("P013", "CLINIC_C", "clinic_emr", [
        {"name": "Warfarin",        "dose": 2,   "unit": "mg", "frequency": "once daily",  "status": "active"},
        {"name": "Clarithromycin",  "dose": 500, "unit": "mg", "frequency": "twice daily", "status": "active"},
        {"name": "Atorvastatin",    "dose": 40,  "unit": "mg", "frequency": "once daily",  "status": "active"},
    ]),

    # P014 — SSRI + tramadol (serotonin syndrome risk)
    ("P014", "CLINIC_C", "clinic_emr", [
        {"name": "Sertraline", "dose": 50, "unit": "mg", "frequency": "once daily",  "status": "active"},
        {"name": "Tramadol",   "dose": 50, "unit": "mg", "frequency": "as needed",   "status": "active"},
    ]),

    # P015 — CLASS COMBINATION: ACE inhibitor + ARB across sources
    ("P015", "CLINIC_B", "clinic_emr", [
        {"name": "Enalapril", "dose": 10, "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),
    ("P015", "CLINIC_B", "hospital_discharge", [
        {"name": "Valsartan", "dose": 80, "unit": "mg", "frequency": "once daily", "status": "active"},
        {"name": "Enalapril", "dose": 10, "unit": "mg", "frequency": "once daily", "status": "active"},
    ]),
]


async def seed(base_url: str):
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        total_conflicts = 0
        for patient_id, clinic_id, source, meds in PAYLOADS:
            payload = {
                "patient_id": patient_id,
                "clinic_id":  clinic_id,
                "source":     source,
                "medications": meds,
                "recorded_by": "seed_script",
            }
            resp = await client.post("/ingest/", json=payload)
            if resp.status_code == 201:
                data = resp.json()
                n = data.get("conflicts_detected", 0)
                total_conflicts += n
                print(f"  ✓ {patient_id} | {source:<25} | version {data['version']} | {n} conflicts")
            else:
                print(f"  ✗ {patient_id} | {source} | ERROR {resp.status_code}: {resp.text[:120]}")

        print(f"\nSeed complete. Total conflict records: {total_conflicts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    args = parser.parse_args()
    print(f"Seeding against {args.base_url} ...\n")
    asyncio.run(seed(args.base_url))