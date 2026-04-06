from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class BiomarkerDefinition:
    biomarker_id: str
    canonical_name: str
    loinc: str
    normalized_unit: str
    allowed_specimens: frozenset[str]
    aliases: tuple[str, ...]


def normalize_key(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def normalize_specimen(specimen: str | None) -> str | None:
    if specimen is None:
        return None

    specimen_key = normalize_key(specimen)
    mapping = {
        "serum": "serum",
        "plasma": "plasma",
        "serum plasma": "serum",
        "whole blood": "whole_blood",
        "blood": "whole_blood",
        "urine": "urine",
    }
    return mapping.get(specimen_key, specimen_key or None)


BIOMARKER_CATALOG: dict[str, BiomarkerDefinition] = {
    "glucose_serum": BiomarkerDefinition(
        biomarker_id="glucose_serum",
        canonical_name="Glucose",
        loinc="2345-7",
        normalized_unit="mg/dL",
        allowed_specimens=frozenset({"serum", "plasma"}),
        aliases=("Glucose", "Glucose, Serum", "Glucose, Plasma", "Serum Glucose", "GLU"),
    ),
    "glucose_urine": BiomarkerDefinition(
        biomarker_id="glucose_urine",
        canonical_name="Urine Glucose",
        loinc="53328-1",
        normalized_unit="mg/dL",
        allowed_specimens=frozenset({"urine"}),
        aliases=("Glucose", "Urine Glucose", "GLU"),
    ),
    "hba1c": BiomarkerDefinition(
        biomarker_id="hba1c",
        canonical_name="Hemoglobin A1c",
        loinc="4548-4",
        normalized_unit="%",
        allowed_specimens=frozenset({"whole_blood"}),
        aliases=("Hemoglobin A1c", "A1C", "HbA1c", "Glycated Hemoglobin"),
    ),
    "total_cholesterol": BiomarkerDefinition(
        biomarker_id="total_cholesterol",
        canonical_name="Total Cholesterol",
        loinc="2093-3",
        normalized_unit="mg/dL",
        allowed_specimens=frozenset({"serum", "plasma"}),
        aliases=("Total Cholesterol", "Cholesterol, Total"),
    ),
    "ldl_cholesterol": BiomarkerDefinition(
        biomarker_id="ldl_cholesterol",
        canonical_name="LDL Cholesterol",
        loinc="2089-1",
        normalized_unit="mg/dL",
        allowed_specimens=frozenset({"serum", "plasma"}),
        aliases=("LDL Cholesterol", "LDL-C", "LDL"),
    ),
    "hdl_cholesterol": BiomarkerDefinition(
        biomarker_id="hdl_cholesterol",
        canonical_name="HDL Cholesterol",
        loinc="2085-9",
        normalized_unit="mg/dL",
        allowed_specimens=frozenset({"serum", "plasma"}),
        aliases=("HDL Cholesterol", "HDL-C", "HDL"),
    ),
    "triglycerides": BiomarkerDefinition(
        biomarker_id="triglycerides",
        canonical_name="Triglycerides",
        loinc="2571-8",
        normalized_unit="mg/dL",
        allowed_specimens=frozenset({"serum", "plasma"}),
        aliases=("Triglycerides", "Triglyceride", "TG"),
    ),
    "creatinine": BiomarkerDefinition(
        biomarker_id="creatinine",
        canonical_name="Creatinine",
        loinc="2160-0",
        normalized_unit="mg/dL",
        allowed_specimens=frozenset({"serum", "plasma"}),
        aliases=("Creatinine", "Creatinine, Serum", "Creatinine, Plasma", "Creat"),
    ),
}


ALIAS_INDEX: dict[str, list[str]] = {}
for biomarker_id, biomarker in BIOMARKER_CATALOG.items():
    for alias in biomarker.aliases:
        alias_key = normalize_key(alias)
        ALIAS_INDEX.setdefault(alias_key, []).append(biomarker_id)
