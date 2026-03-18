# PROBLEM: Different systems enter the same drug in different ways.
#   "METFORMIN 500MG"  vs  "metformin 500mg"  vs  "Metformin  500 mg"
# These are all the same drug, but a string comparison would say they differ.
#
# SOLUTION: Before storing or comparing anything, we normalise:
#   - drug name   → lowercase, extra spaces collapsed
#   - unit        → "Milligrams" → "mg", "BID" → "twice daily", etc.
#   - frequency   → standardised phrases

import re
from typing import List, Dict, Any, Optional
from app.models.schemas import MedicationItem


# Maps every known spelling of a unit to its canonical short form
UNIT_ALIASES: Dict[str, str] = {
    "milligrams": "mg", "milligram": "mg", "mg": "mg",
    "micrograms": "mcg", "microgram": "mcg", "mcg": "mcg", "ug": "mcg",
    "grams": "g", "gram": "g", "g": "g",
    "milliliters": "ml", "milliliter": "ml", "ml": "ml",
    "units": "units", "unit": "units", "u": "units",
    "iu": "iu", "international units": "iu",
    "meq": "meq", "mEq": "meq",
    "percent": "%", "%": "%",
}

# Maps medical abbreviations to readable frequency strings
FREQUENCY_ALIASES: Dict[str, str] = {
    "once daily": "once daily", "od": "once daily", "qd": "once daily", "q24h": "once daily",
    "twice daily": "twice daily", "bid": "twice daily", "bd": "twice daily", "q12h": "twice daily",
    "three times daily": "three times daily", "tid": "three times daily",
    "tds": "three times daily", "q8h": "three times daily",
    "four times daily": "four times daily", "qid": "four times daily", "q6h": "four times daily",
    "every other day": "every other day", "qod": "every other day",
    "weekly": "weekly", "once weekly": "weekly",
    "as needed": "as needed", "prn": "as needed",
}


def normalize_name(name: str) -> str:
    """'  METFORMIN  ' → 'metformin'"""
    return re.sub(r"\s+", " ", name.strip().lower())


def normalize_unit(unit: Optional[str]) -> Optional[str]:
    """'Milligrams' → 'mg',  None → None"""
    if unit is None:
        return None
    cleaned = re.sub(r"\s+", " ", unit.strip().lower())
    return UNIT_ALIASES.get(cleaned, cleaned)  # fallback: return as-is


def normalize_frequency(freq: Optional[str]) -> Optional[str]:
    """'BID' → 'twice daily',  'PRN' → 'as needed'"""
    if freq is None:
        return None
    cleaned = re.sub(r"\s+", " ", freq.strip().lower())
    return FREQUENCY_ALIASES.get(cleaned, cleaned)


def normalize_medication(med: MedicationItem) -> Dict[str, Any]:
    """
    Takes a MedicationItem (Pydantic model from the request)
    and returns a plain dict with everything normalised.
    This dict is what gets stored in MongoDB.
    """
    return {
        "name":      normalize_name(med.name),
        "dose":      med.dose,
        "unit":      normalize_unit(med.unit),
        "frequency": normalize_frequency(med.frequency),
        "status":    med.status.value,
        "notes":     med.notes,
    }


def normalize_list(medications: List[MedicationItem]) -> List[Dict[str, Any]]:
    """Normalise an entire list of medications."""
    return [normalize_medication(m) for m in medications]