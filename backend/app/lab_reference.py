"""
Lab result normal reference ranges and parser.
Covers 30+ common lab tests: CBC, BMP, lipids, LFTs, thyroid, coagulation, kidney, HbA1c, PSA.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Format: "canonical_name": (unit, normal_low, normal_high, critical_low, critical_high)
# None means the boundary does not apply (e.g., HDL has no upper limit).
# All ranges are for adults. Sex-specific ranges are not differentiated here.
LAB_REFERENCE_RANGES: Dict[str, Tuple] = {
    # --- Complete Blood Count (CBC) ---
    "hemoglobin":               ("g/dL",   12.0,  17.5,  7.0,   None),
    "hematocrit":               ("%",       36.0,  50.0,  21.0,  None),
    "rbc":                      ("M/uL",    4.2,   5.9,   None,  None),
    "wbc":                      ("K/uL",    4.5,   11.0,  2.0,   30.0),
    "platelets":                ("K/uL",    150.0, 400.0, 50.0,  1000.0),
    "mcv":                      ("fL",      80.0,  100.0, None,  None),
    "mch":                      ("pg",      27.0,  33.0,  None,  None),
    "mchc":                     ("g/dL",    32.0,  36.0,  None,  None),
    "rdw":                      ("%",       11.5,  14.5,  None,  None),
    "neutrophils":              ("%",       50.0,  70.0,  None,  None),
    "lymphocytes":              ("%",       20.0,  40.0,  None,  None),
    "monocytes":                ("%",       2.0,   8.0,   None,  None),
    "eosinophils":              ("%",       1.0,   4.0,   None,  None),
    "basophils":                ("%",       0.0,   1.0,   None,  None),

    # --- Basic / Comprehensive Metabolic Panel ---
    "sodium":                   ("mEq/L",  136.0, 145.0, 120.0, 160.0),
    "potassium":                ("mEq/L",  3.5,   5.0,   2.5,   6.5),
    "chloride":                 ("mEq/L",  98.0,  107.0, None,  None),
    "bicarbonate":              ("mEq/L",  22.0,  29.0,  None,  None),
    "bun":                      ("mg/dL",  7.0,   20.0,  None,  None),
    "creatinine":               ("mg/dL",  0.6,   1.2,   None,  10.0),
    "glucose":                  ("mg/dL",  70.0,  99.0,  40.0,  500.0),
    "calcium":                  ("mg/dL",  8.5,   10.5,  6.0,   13.0),
    "magnesium":                ("mg/dL",  1.7,   2.2,   None,  None),
    "phosphorus":               ("mg/dL",  2.5,   4.5,   None,  None),

    # --- Lipid Panel ---
    "total cholesterol":        ("mg/dL",  None,  200.0, None,  None),
    "ldl":                      ("mg/dL",  None,  100.0, None,  None),
    "hdl":                      ("mg/dL",  40.0,  None,  None,  None),
    "triglycerides":            ("mg/dL",  None,  150.0, None,  500.0),
    "vldl":                     ("mg/dL",  None,  30.0,  None,  None),

    # --- Liver Function Tests (LFT) ---
    "alt":                      ("U/L",    7.0,   56.0,  None,  None),
    "ast":                      ("U/L",    10.0,  40.0,  None,  None),
    "alkaline phosphatase":     ("U/L",    44.0,  147.0, None,  None),
    "ggt":                      ("U/L",    9.0,   48.0,  None,  None),
    "bilirubin total":          ("mg/dL",  0.2,   1.2,   None,  None),
    "bilirubin direct":         ("mg/dL",  None,  0.3,   None,  None),
    "bilirubin indirect":       ("mg/dL",  None,  0.9,   None,  None),
    "albumin":                  ("g/dL",   3.5,   5.0,   None,  None),
    "total protein":            ("g/dL",   6.0,   8.3,   None,  None),

    # --- Thyroid Panel ---
    "tsh":                      ("mIU/L",  0.4,   4.0,   None,  None),
    "free t4":                  ("ng/dL",  0.8,   1.8,   None,  None),
    "free t3":                  ("pg/mL",  2.3,   4.2,   None,  None),
    "t4 total":                 ("ug/dL",  4.5,   12.0,  None,  None),
    "t3 total":                 ("ng/dL",  80.0,  200.0, None,  None),

    # --- Kidney / Renal ---
    "uric acid":                ("mg/dL",  2.4,   7.0,   None,  None),
    "egfr":                     ("mL/min", 60.0,  None,  None,  None),
    "urea":                     ("mg/dL",  15.0,  45.0,  None,  None),

    # --- Diabetes / Glycemic ---
    "hba1c":                    ("%",      None,  5.7,   None,  None),
    "fasting glucose":          ("mg/dL",  70.0,  99.0,  40.0,  500.0),
    "random glucose":           ("mg/dL",  None,  140.0, 40.0,  500.0),

    # --- Coagulation ---
    "pt":                       ("sec",    11.0,  13.5,  None,  None),
    "inr":                      ("ratio",  0.8,   1.1,   None,  None),
    "aptt":                     ("sec",    25.0,  35.0,  None,  None),
    "fibrinogen":               ("mg/dL",  200.0, 400.0, None,  None),

    # --- Other ---
    "psa":                      ("ng/mL",  None,  4.0,   None,  None),
    "esr":                      ("mm/hr",  None,  20.0,  None,  None),
    "crp":                      ("mg/L",   None,  10.0,  None,  None),
    "ferritin":                 ("ng/mL",  12.0,  300.0, None,  None),
    "iron":                     ("ug/dL",  60.0,  170.0, None,  None),
    "transferrin saturation":   ("%",      20.0,  50.0,  None,  None),
    "vitamin b12":              ("pg/mL",  200.0, 900.0, None,  None),
    "folate":                   ("ng/mL",  2.0,   20.0,  None,  None),
    "vitamin d":                ("ng/mL",  30.0,  100.0, None,  None),
    "amylase":                  ("U/L",    23.0,  85.0,  None,  None),
    "lipase":                   ("U/L",    0.0,   160.0, None,  None),
    "troponin i":               ("ng/mL",  None,  0.04,  None,  None),
    "bnp":                      ("pg/mL",  None,  100.0, None,  None),
    "d-dimer":                  ("ug/mL",  None,  0.5,   None,  None),
}

# Map common abbreviations and alternate names to canonical keys in LAB_REFERENCE_RANGES
LAB_ALIASES: Dict[str, str] = {
    # Hemoglobin
    "hgb": "hemoglobin", "hb": "hemoglobin",
    # Hematocrit
    "hct": "hematocrit", "pcv": "hematocrit", "packed cell volume": "hematocrit",
    # RBC
    "rbc count": "rbc", "red blood cells": "rbc", "red cell count": "rbc",
    "erythrocytes": "rbc",
    # WBC
    "white blood cells": "wbc", "leukocytes": "wbc", "white cell count": "wbc",
    "wbc count": "wbc",
    # Platelets
    "plt": "platelets", "thrombocytes": "platelets", "platelet count": "platelets",
    # MCH/MCV/MCHC
    "mean corpuscular volume": "mcv",
    "mean corpuscular hemoglobin": "mch",
    "mean corpuscular hemoglobin concentration": "mchc",
    "red cell distribution width": "rdw",
    # Differentials
    "neutrophil": "neutrophils", "lymphocyte": "lymphocytes",
    "monocyte": "monocytes", "eosinophil": "eosinophils", "basophil": "basophils",
    "segs": "neutrophils", "polys": "neutrophils",
    # Electrolytes
    "na": "sodium", "na+": "sodium",
    "k": "potassium", "k+": "potassium",
    "cl": "chloride", "cl-": "chloride",
    "co2": "bicarbonate", "hco3": "bicarbonate", "hco3-": "bicarbonate",
    # BUN/Creatinine
    "blood urea nitrogen": "bun", "blood urea": "bun",
    "creat": "creatinine", "scr": "creatinine", "serum creatinine": "creatinine",
    # Glucose
    "fbs": "fasting glucose", "fpg": "fasting glucose", "blood glucose": "glucose",
    "blood sugar": "glucose", "rbs": "random glucose", "ppbs": "random glucose",
    # Calcium/Magnesium
    "ca": "calcium", "ca2+": "calcium",
    "mg": "magnesium", "phosphate": "phosphorus",
    # Lipids
    "total chol": "total cholesterol", "chol": "total cholesterol",
    "low density lipoprotein": "ldl", "ldl-c": "ldl", "ldl cholesterol": "ldl",
    "high density lipoprotein": "hdl", "hdl-c": "hdl", "hdl cholesterol": "hdl",
    "tg": "triglycerides", "trigs": "triglycerides",
    # LFTs
    "sgpt": "alt", "alanine aminotransferase": "alt", "alanine transaminase": "alt",
    "sgot": "ast", "aspartate aminotransferase": "ast", "aspartate transaminase": "ast",
    "alp": "alkaline phosphatase", "alk phos": "alkaline phosphatase",
    "gamma gt": "ggt", "gamma-gt": "ggt", "gamma glutamyl transferase": "ggt",
    "total bilirubin": "bilirubin total", "tbil": "bilirubin total", "tbilirubin": "bilirubin total",
    "direct bilirubin": "bilirubin direct", "dbil": "bilirubin direct",
    "indirect bilirubin": "bilirubin indirect",
    "alb": "albumin", "serum albumin": "albumin",
    "tp": "total protein", "serum total protein": "total protein",
    # Thyroid
    "thyroid stimulating hormone": "tsh",
    "ft4": "free t4", "thyroxine": "free t4", "t4": "t4 total",
    "ft3": "free t3", "triiodothyronine": "free t3", "t3": "t3 total",
    # Kidney
    "uric acid level": "uric acid", "serum uric acid": "uric acid",
    "glomerular filtration rate": "egfr", "gfr": "egfr",
    "blood urea urea": "urea",
    # Glycemic
    "glycated hemoglobin": "hba1c", "a1c": "hba1c", "glycosylated hemoglobin": "hba1c",
    "haemoglobin a1c": "hba1c", "hemoglobin a1c": "hba1c",
    # Coagulation
    "prothrombin time": "pt",
    "international normalized ratio": "inr",
    "activated partial thromboplastin time": "aptt", "ptt": "aptt",
    # Other
    "prostate specific antigen": "psa",
    "erythrocyte sedimentation rate": "esr", "sed rate": "esr",
    "c reactive protein": "crp", "c-reactive protein": "crp",
    "serum ferritin": "ferritin",
    "serum iron": "iron",
    "transferrin sat": "transferrin saturation", "tsat": "transferrin saturation",
    "b12": "vitamin b12", "cobalamin": "vitamin b12",
    "folic acid": "folate",
    "25-oh vitamin d": "vitamin d", "25 oh vitamin d": "vitamin d",
    "25-hydroxyvitamin d": "vitamin d",
    "serum amylase": "amylase",
    "serum lipase": "lipase",
    "troponin": "troponin i", "trop i": "troponin i",
    "brain natriuretic peptide": "bnp",
}


def normalize_name(raw_name: str) -> Optional[str]:
    """
    Convert a raw test name from extracted text to a canonical LAB_REFERENCE_RANGES key.
    Lowercases, strips extra spaces and punctuation, checks aliases, then direct match.
    Returns None if not recognized.
    """
    cleaned = raw_name.lower().strip()
    cleaned = re.sub(r"[^a-z0-9 /().,-]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Direct match first
    if cleaned in LAB_REFERENCE_RANGES:
        return cleaned

    # Alias lookup
    if cleaned in LAB_ALIASES:
        alias = LAB_ALIASES[cleaned]
        if alias in LAB_REFERENCE_RANGES:
            return alias

    # Partial / prefix matching for common truncations
    for alias_key, canonical in LAB_ALIASES.items():
        if cleaned == alias_key:
            return canonical if canonical in LAB_REFERENCE_RANGES else None

    # Try direct substring: e.g. "serum glucose" → check if "glucose" is a key
    words = cleaned.split()
    for word in words:
        if word in LAB_REFERENCE_RANGES:
            return word

    return None


def _classify_status(
    value: float,
    normal_low: Optional[float],
    normal_high: Optional[float],
    critical_low: Optional[float],
    critical_high: Optional[float],
) -> str:
    """Return status string based on value vs normal/critical bounds."""
    if critical_low is not None and value < critical_low:
        return "critical_low"
    if critical_high is not None and value > critical_high:
        return "critical_high"
    if normal_low is not None and value < normal_low:
        return "low"
    if normal_high is not None and value > normal_high:
        return "high"
    return "normal"


# Regex to match a line with: test name, numeric value, optional unit
_LINE_PATTERN = re.compile(
    r"^([A-Za-z][A-Za-z0-9 /().,:%-]{1,60}?)\s+([\d.,<>]+)\s*([A-Za-z%/]+(?:/[A-Za-z]+)?)?",
    re.IGNORECASE,
)


def _parse_numeric(raw: str) -> Optional[float]:
    """Parse values like '12.5', '<0.1', '>100', '1,234', '1,2' into float."""
    raw = raw.strip().lstrip("<>").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_lab_text(extracted_text: str) -> List[dict]:
    """
    Parse raw extracted text from a lab report into a list of recognized lab value dicts.

    Each dict contains:
        test_name (str), value (float), unit (str),
        normal_low (float|None), normal_high (float|None), status (str)

    Lines that don't match the pattern or whose test name is not recognized
    are silently skipped.
    """
    results = []
    seen_names = set()

    for raw_line in extracted_text.splitlines():
        line = raw_line.strip()
        if not line or len(line) < 5:
            continue

        match = _LINE_PATTERN.match(line)
        if not match:
            continue

        raw_name, raw_value, raw_unit = match.group(1), match.group(2), match.group(3) or ""

        canonical = normalize_name(raw_name)
        if canonical is None:
            continue

        numeric_val = _parse_numeric(raw_value)
        if numeric_val is None:
            continue

        # Deduplicate: keep first occurrence of each test name
        if canonical in seen_names:
            continue
        seen_names.add(canonical)

        ref = LAB_REFERENCE_RANGES[canonical]
        unit, normal_low, normal_high, critical_low, critical_high = ref
        # Use extracted unit if available, otherwise fall back to reference unit
        display_unit = raw_unit.strip() if raw_unit.strip() else unit

        status = _classify_status(numeric_val, normal_low, normal_high, critical_low, critical_high)

        results.append({
            "test_name": canonical.title(),
            "value": numeric_val,
            "unit": display_unit,
            "normal_low": normal_low,
            "normal_high": normal_high,
            "status": status,
        })

    return results


def format_lab_table_as_context(lab_values: List[dict]) -> str:
    """
    Convert parsed lab values into a structured text block suitable for the LLM prompt.
    Highlights abnormal and critical values.
    """
    if not lab_values:
        return ""

    lines = ["=== PATIENT LAB RESULTS ==="]
    lines.append(f"{'TEST':<30} {'VALUE':<10} {'UNIT':<12} {'NORMAL RANGE':<20} STATUS")
    lines.append("-" * 90)

    abnormal = []
    critical = []

    for lv in lab_values:
        lo = lv["normal_low"]
        hi = lv["normal_high"]
        if lo is not None and hi is not None:
            range_str = f"{lo} – {hi}"
        elif lo is not None:
            range_str = f">= {lo}"
        elif hi is not None:
            range_str = f"<= {hi}"
        else:
            range_str = "N/A"

        status = lv["status"].upper().replace("_", " ")
        lines.append(
            f"{lv['test_name']:<30} {lv['value']:<10} {lv['unit']:<12} {range_str:<20} {status}"
        )

        if "CRITICAL" in status:
            critical.append(f"{lv['test_name']} ({status})")
        elif status in ("HIGH", "LOW"):
            abnormal.append(f"{lv['test_name']} ({status})")

    lines.append("")
    if critical:
        lines.append(f"⚠️  CRITICAL VALUES: {', '.join(critical)}")
    if abnormal:
        lines.append(f"ABNORMAL VALUES: {', '.join(abnormal)}")
    if not critical and not abnormal:
        lines.append("All values within normal range.")

    return "\n".join(lines)
