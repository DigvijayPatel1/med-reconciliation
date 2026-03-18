from app.services.conflict_detector import detect_conflicts


def make_med(name, dose=None, unit="mg", status="active", frequency="once daily"):
    return {"name": name, "dose": dose, "unit": unit,
            "status": status, "frequency": frequency, "notes": None}

def make_snapshot(source, meds):
    return {"source": source, "medications": meds}


class TestDoseMismatch:
    def test_detects_dose_mismatch(self):
        new_meds = [make_med("metformin", dose=500)]
        existing = [make_snapshot("hospital_discharge", [make_med("metformin", dose=1000)])]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, existing)
        assert any(c["conflict_type"] == "dose_mismatch" for c in conflicts)

    def test_no_conflict_within_tolerance(self):
        # 500 vs 505 is only 1% difference — within the 10% tolerance
        new_meds = [make_med("metformin", dose=500)]
        existing = [make_snapshot("hospital_discharge", [make_med("metformin", dose=505)])]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, existing)
        assert not any(c["conflict_type"] == "dose_mismatch" for c in conflicts)

    def test_no_conflict_when_dose_missing(self):
        # If one source doesn't report a dose, we can't say it's wrong
        new_meds = [make_med("metformin", dose=None)]
        existing = [make_snapshot("hospital_discharge", [make_med("metformin", dose=500)])]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, existing)
        assert not any(c["conflict_type"] == "dose_mismatch" for c in conflicts)

    def test_three_sources_different_doses(self):
        new_meds = [make_med("metformin", dose=500)]
        existing = [
            make_snapshot("hospital_discharge", [make_med("metformin", dose=850)]),
            make_snapshot("patient_reported",   [make_med("metformin", dose=1000)]),
        ]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, existing)
        dose_conflicts = [c for c in conflicts if c["conflict_type"] == "dose_mismatch"]
        # clinic vs hospital AND clinic vs patient = at least 2
        assert len(dose_conflicts) >= 2


class TestStatusMismatch:
    def test_detects_active_vs_stopped(self):
        new_meds = [make_med("metoprolol", dose=50, status="active")]
        existing = [make_snapshot("hospital_discharge", [make_med("metoprolol", dose=50, status="stopped")])]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, existing)
        assert any(c["conflict_type"] == "status_mismatch" for c in conflicts)

    def test_no_conflict_same_status(self):
        new_meds = [make_med("metoprolol", dose=50, status="active")]
        existing = [make_snapshot("hospital_discharge", [make_med("metoprolol", dose=50, status="active")])]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, existing)
        assert not any(c["conflict_type"] == "status_mismatch" for c in conflicts)


class TestBlacklistedCombination:
    def test_warfarin_aspirin_flagged(self):
        new_meds = [make_med("warfarin", dose=5), make_med("aspirin", dose=81)]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, [])
        assert any(c["conflict_type"] == "blacklisted_combination" for c in conflicts)

    def test_stopped_drug_not_flagged(self):
        # A stopped warfarin + active aspirin should NOT trigger the combo
        new_meds = [make_med("warfarin", dose=5, status="stopped"), make_med("aspirin", dose=81)]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, [])
        assert not any(c["conflict_type"] == "blacklisted_combination" for c in conflicts)

    def test_combination_across_sources(self):
        # Warfarin from clinic + aspirin from patient report = still a conflict
        new_meds = [make_med("aspirin", dose=81)]
        existing = [make_snapshot("clinic_emr", [make_med("warfarin", dose=5)])]
        conflicts = detect_conflicts("P1", "C1", "patient_reported", new_meds, existing)
        assert any(c["conflict_type"] == "blacklisted_combination" for c in conflicts)


class TestClassCombination:
    def test_ace_inhibitor_plus_arb(self):
        new_meds = [make_med("lisinopril", dose=10)]
        existing = [make_snapshot("hospital_discharge", [make_med("losartan", dose=50)])]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, existing)
        assert any(c["conflict_type"] == "class_combination" for c in conflicts)

    def test_anticoagulant_plus_nsaid(self):
        new_meds = [make_med("apixaban", dose=5), make_med("ibuprofen", dose=400)]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, [])
        assert any(c["conflict_type"] == "class_combination" for c in conflicts)


class TestOutOfRange:
    def test_atorvastatin_above_max(self):
        new_meds = [make_med("atorvastatin", dose=120)]  # max is 80
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, [])
        assert any(c["conflict_type"] == "out_of_range" for c in conflicts)

    def test_atorvastatin_within_range(self):
        new_meds = [make_med("atorvastatin", dose=40)]  # 40 is fine
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, [])
        assert not any(c["conflict_type"] == "out_of_range" for c in conflicts)

    def test_unknown_drug_no_range_error(self):
        # A drug not in rules.json should not trigger out_of_range
        new_meds = [make_med("unknowndrug", dose=9999)]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, [])
        assert not any(c["conflict_type"] == "out_of_range" for c in conflicts)


class TestDeduplication:
    def test_no_duplicate_conflicts(self):
        # warfarin in new_meds + aspirin in existing should produce exactly 1 blacklisted conflict
        new_meds = [make_med("warfarin", dose=5)]
        existing = [make_snapshot("hospital_discharge", [make_med("aspirin", dose=81)])]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, existing)
        blacklisted = [c for c in conflicts if c["conflict_type"] == "blacklisted_combination"]
        assert len(blacklisted) == 1


class TestEdgeCases:
    def test_empty_new_meds_does_not_crash(self):
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", [], [])
        assert isinstance(conflicts, list)

    def test_no_existing_snapshots(self):
        new_meds = [make_med("atorvastatin", dose=40)]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, [])
        assert isinstance(conflicts, list)

    def test_missing_dose_key_does_not_crash(self):
        # Simulates a document where "dose" key is absent entirely
        new_meds = [{"name": "metformin", "unit": "mg", "status": "active", "frequency": None, "notes": None}]
        existing = [make_snapshot("hospital_discharge", [make_med("metformin", dose=1000)])]
        conflicts = detect_conflicts("P1", "C1", "clinic_emr", new_meds, existing)
        assert isinstance(conflicts, list)