from app.models.schemas import MedicationItem, MedicationStatus
from app.services.normalizer import (
    normalize_name, normalize_unit, normalize_frequency,
    normalize_medication, normalize_list
)


class TestNormalizeName:
    def test_lowercases(self):
        assert normalize_name("METFORMIN") == "metformin"

    def test_strips_whitespace(self):
        assert normalize_name("  aspirin  ") == "aspirin"

    def test_collapses_internal_spaces(self):
        assert normalize_name("insulin  glargine") == "insulin glargine"

    def test_mixed_case_with_dosage(self):
        assert normalize_name("Tylenol 500MG") == "tylenol 500mg"


class TestNormalizeUnit:
    def test_mg_aliases(self):
        for alias in ["mg", "MG", "milligrams", "Milligram"]:
            assert normalize_unit(alias) == "mg"

    def test_mcg_aliases(self):
        for alias in ["mcg", "micrograms", "ug"]:
            assert normalize_unit(alias) == "mcg"

    def test_units_aliases(self):
        for alias in ["units", "unit", "u"]:
            assert normalize_unit(alias) == "units"

    def test_none_returns_none(self):
        assert normalize_unit(None) is None

    def test_unknown_unit_passes_through(self):
        assert normalize_unit("drops") == "drops"


class TestNormalizeFrequency:
    def test_bid_to_twice_daily(self):
        assert normalize_frequency("BID") == "twice daily"

    def test_qd_to_once_daily(self):
        assert normalize_frequency("QD") == "once daily"

    def test_prn_to_as_needed(self):
        assert normalize_frequency("PRN") == "as needed"

    def test_none_returns_none(self):
        assert normalize_frequency(None) is None

    def test_unknown_passes_through(self):
        assert normalize_frequency("every 4 hours") == "every 4 hours"


class TestNormalizeMedication:
    def test_full_normalization(self):
        med = MedicationItem(
            name="  METFORMIN  ",
            dose=500,
            unit="MG",
            frequency="BID",
            status=MedicationStatus.active,
        )
        result = normalize_medication(med)
        assert result["name"] == "metformin"
        assert result["unit"] == "mg"
        assert result["frequency"] == "twice daily"
        assert result["dose"] == 500

    def test_missing_optional_fields(self):
        med = MedicationItem(name="Aspirin", status=MedicationStatus.active)
        result = normalize_medication(med)
        assert result["name"] == "aspirin"
        assert result["dose"] is None
        assert result["unit"] is None


class TestNormalizeList:
    def test_normalizes_all_items(self):
        meds = [
            MedicationItem(name="WARFARIN", dose=5,  unit="MG", status=MedicationStatus.active),
            MedicationItem(name="Aspirin",  dose=81, unit="mg", status=MedicationStatus.active),
        ]
        result = normalize_list(meds)
        assert len(result) == 2
        assert result[0]["name"] == "warfarin"
        assert result[1]["name"] == "aspirin"