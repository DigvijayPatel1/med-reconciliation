# This is the BRAIN of the service.
# When a new medication list arrives, this function compares it against
# all existing medication lists for the same patient and finds:
#
#   1. DOSE MISMATCH      — same drug, different doses across sources
#   2. STATUS MISMATCH    — one source says active, another says stopped
#   3. BLACKLISTED COMBO  — two drugs that must never be combined
#   4. CLASS COMBINATION  — two drug classes that conflict (e.g., ACE + ARB)
#   5. OUT OF RANGE       — a dose outside the clinically safe range

import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.resources.messages import (
    DOSE_MISMATCH_DESC, STATUS_MISMATCH_DESC,
    BLACKLISTED_COMBO_DESC, CLASS_COMBO_DESC, OUT_OF_RANGE_DESC,
)

# Load rules.json once when the module is first imported.
# We don't want to re-read the file on every API call.
_RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "rules.json")

def _load_rules() -> Dict:
    with open(os.path.abspath(_RULES_PATH)) as f:
        return json.load(f)

RULES = _load_rules()


def _drug_class(name: str) -> Optional[str]:
    """Return the drug class for a given drug name, or None if unknown."""
    for cls, members in RULES["drug_classes"].items():
        if name in members:
            return cls
    return None


def _doses_conflict(dose_a: Optional[float], dose_b: Optional[float]) -> bool:
    """
    Return True if the two doses differ by more than the tolerance threshold.
    
    Example: tolerance=10%, dose_a=500, dose_b=560
      difference = 60, max = 560, ratio = 60/560 = 10.7% → CONFLICT
      
    We skip comparison if either dose is missing (None).
    """
    if dose_a is None or dose_b is None:
        return False
    if dose_a == 0 and dose_b == 0:
        return False
    tolerance = RULES.get("dose_tolerance_percent", 10) / 100
    ref = max(dose_a, dose_b)
    return abs(dose_a - dose_b) / ref > tolerance


def detect_conflicts(
    patient_id: str,
    clinic_id: str,
    new_source: str,
    new_meds: List[Dict[str, Any]],
    existing_snapshots: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Parameters
    ----------
    patient_id         : the patient we're checking
    clinic_id          : their clinic
    new_source         : which source just submitted data (e.g. "clinic_emr")
    new_meds           : the normalised medication list just received
    existing_snapshots : latest snapshots from ALL OTHER sources for this patient

    Returns
    -------
    A list of conflict dicts (not yet saved to MongoDB — saving happens in ingestion.py)
    """
    conflicts: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    # Build a combined view: source_name → list of medication dicts
    # This lets us compare any two sources against each other
    all_source_meds: Dict[str, List[Dict]] = {new_source: new_meds}
    for snap in existing_snapshots:
        src = snap["source"]
        if src not in all_source_meds:
            all_source_meds[src] = snap["medications"]

    # ── Check 1 & 2: Cross-source dose and status mismatches ─────────────────
    # We compare every pair of sources (clinic_emr vs hospital, clinic vs patient, etc.)
    sources = list(all_source_meds.keys())
    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            src_a, src_b = sources[i], sources[j]

            # Index each source's medications by drug name for O(1) lookup
            meds_a = {m["name"]: m for m in all_source_meds[src_a]}
            meds_b = {m["name"]: m for m in all_source_meds[src_b]}

            # Only compare drugs that appear in BOTH sources
            common_drugs = set(meds_a) & set(meds_b)

            for drug in common_drugs:
                med_a, med_b = meds_a[drug], meds_b[drug]

                # ── Dose mismatch ──────────────────────────────────────────
                if _doses_conflict(med_a.get("dose"), med_b.get("dose")):
                    conflicts.append({
                        "patient_id":       patient_id,
                        "clinic_id":        clinic_id,
                        "conflict_type":    "dose_mismatch",
                        "status":           "unresolved",
                        "severity":         "medium",
                        "description":      DOSE_MISMATCH_DESC.format(
                            drug=drug,
                            source_a=src_a, dose_a=med_a.get("dose"), unit=med_a.get("unit", ""),
                            source_b=src_b, dose_b=med_b.get("dose"),
                        ),
                        "involved_drugs":   [drug],
                        "sources_involved": [src_a, src_b],
                        "source_details": {
                            src_a: {"dose": med_a.get("dose"), "unit": med_a.get("unit")},
                            src_b: {"dose": med_b.get("dose"), "unit": med_b.get("unit")},
                        },
                        "detected_at": now,
                        "resolved_at": None,
                        "resolution":  None,
                    })

                # ── Status mismatch ────────────────────────────────────────
                status_a = med_a.get("status", "active")
                status_b = med_b.get("status", "active")
                if status_a != status_b:
                    conflicts.append({
                        "patient_id":       patient_id,
                        "clinic_id":        clinic_id,
                        "conflict_type":    "status_mismatch",
                        "status":           "unresolved",
                        "severity":         "high",
                        "description":      STATUS_MISMATCH_DESC.format(
                            drug=drug,
                            source_a=src_a, status_a=status_a,
                            source_b=src_b, status_b=status_b,
                        ),
                        "involved_drugs":   [drug],
                        "sources_involved": [src_a, src_b],
                        "source_details":   {src_a: {"status": status_a}, src_b: {"status": status_b}},
                        "detected_at": now,
                        "resolved_at": None,
                        "resolution":  None,
                    })

    # ── Check 3: Blacklisted drug combinations ────────────────────────────────
    # Collect all ACTIVE drugs across ALL sources combined
    all_active_drugs = set()
    for src, meds in all_source_meds.items():
        for m in meds:
            if m.get("status", "active") == "active":
                all_active_drugs.add(m["name"])

    # Check each blacklisted pair against the combined active drug set
    for rule in RULES["blacklisted_combinations"]:
        pair = rule["drugs"]
        if all(d in all_active_drugs for d in pair):
            conflicts.append({
                "patient_id":       patient_id,
                "clinic_id":        clinic_id,
                "conflict_type":    "blacklisted_combination",
                "status":           "unresolved",
                "severity":         rule.get("severity", "high"),
                "description":      BLACKLISTED_COMBO_DESC.format(
                    drugs=" + ".join(pair), reason=rule["reason"]
                ),
                "involved_drugs":   pair,
                "sources_involved": list(all_source_meds.keys()),
                "source_details":   {},
                "detected_at": now,
                "resolved_at": None,
                "resolution":  None,
            })

    # ── Check 4: Drug class combination rules ─────────────────────────────────
    # Map each active drug to its class
    active_classes: Dict[str, List[str]] = {}
    for drug in all_active_drugs:
        cls = _drug_class(drug)
        if cls:
            active_classes.setdefault(cls, []).append(drug)

    # Check if any forbidden class pair is present
    for rule in RULES["class_combination_rules"]:
        cls_pair = rule["classes"]
        if all(c in active_classes for c in cls_pair):
            involved = active_classes[cls_pair[0]] + active_classes[cls_pair[1]]
            conflicts.append({
                "patient_id":       patient_id,
                "clinic_id":        clinic_id,
                "conflict_type":    "class_combination",
                "status":           "unresolved",
                "severity":         rule.get("severity", "high"),
                "description":      CLASS_COMBO_DESC.format(
                    classes=" + ".join(cls_pair), reason=rule["reason"]
                ),
                "involved_drugs":   involved,
                "sources_involved": list(all_source_meds.keys()),
                "source_details":   {},
                "detected_at": now,
                "resolved_at": None,
                "resolution":  None,
            })

    # ── Check 5: Out-of-range dose ────────────────────────────────────────────
    # Only check the NEW medications being submitted, not existing ones
    # (existing ones were checked when they were first ingested)
    for med in new_meds:
        drug = med["name"]
        dose = med.get("dose")
        if dose is None:
            continue
        if drug in RULES["dose_ranges"]:
            r = RULES["dose_ranges"][drug]
            if not (r["min_mg"] <= dose <= r["max_mg"]):
                conflicts.append({
                    "patient_id":       patient_id,
                    "clinic_id":        clinic_id,
                    "conflict_type":    "out_of_range",
                    "status":           "unresolved",
                    "severity":         "medium",
                    "description":      OUT_OF_RANGE_DESC.format(
                        drug=drug, dose=dose, unit=med.get("unit", ""),
                        min=r["min_mg"], max=r["max_mg"],
                    ),
                    "involved_drugs":   [drug],
                    "sources_involved": [new_source],
                    "source_details":   {new_source: {"dose": dose, "unit": med.get("unit")}},
                    "detected_at": now,
                    "resolved_at": None,
                    "resolution":  None,
                })

    return _deduplicate(conflicts)


def _deduplicate(conflicts: List[Dict]) -> List[Dict]:
    """
    The nested loop above can produce duplicate entries for the same conflict
    (e.g., warfarin+aspirin appearing once for each source-pair combination).
    This removes duplicates while preserving order.
    
    Two conflicts are considered the same if they have the same:
      - conflict_type
      - involved_drugs (sorted so order doesn't matter)
      - sources_involved (sorted)
    """
    seen = set()
    result = []
    for c in conflicts:
        key = (
            c["conflict_type"],
            frozenset(c["involved_drugs"]),
            frozenset(c["sources_involved"]),
        )
        if key not in seen:
            seen.add(key)
            result.append(c)
    return result