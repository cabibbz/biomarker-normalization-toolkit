from __future__ import annotations

from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord
from biomarker_normalization_toolkit.units import parse_reference_range


FHIR_VERSION = "4.0.1"


def _build_reference_range(record: NormalizedRecord) -> list[dict]:
    parsed = parse_reference_range(record.normalized_reference_range, record.normalized_unit)
    if parsed is None:
        return []

    return [
        {
            "low": {
                "value": float(parsed.low),
                "unit": parsed.unit,
                "system": "http://unitsofmeasure.org",
                "code": parsed.unit,
            },
            "high": {
                "value": float(parsed.high),
                "unit": parsed.unit,
                "system": "http://unitsofmeasure.org",
                "code": parsed.unit,
            },
            "text": record.normalized_reference_range,
        }
    ]


def build_observation(record: NormalizedRecord) -> dict | None:
    if record.mapping_status != "mapped":
        return None

    observation = {
        "resourceType": "Observation",
        "id": f"observation-{record.source_row_id}",
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "laboratory",
                        "display": "Laboratory",
                    }
                ],
                "text": "Laboratory",
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": record.loinc,
                    "display": record.canonical_biomarker_name,
                }
            ],
            "text": record.canonical_biomarker_name,
        },
        "valueQuantity": {
            "value": float(record.normalized_value),
            "unit": record.normalized_unit,
            "system": "http://unitsofmeasure.org",
            "code": record.normalized_unit,
        },
        "referenceRange": _build_reference_range(record),
        "note": [
            {
                "text": (
                    f"Mapped from source test '{record.source_test_name}' "
                    f"using rule '{record.mapping_rule}'."
                )
            }
        ],
        "identifier": [
            {
                "system": "urn:source-row-id",
                "value": record.source_row_id,
            }
        ],
    }

    if record.specimen_type:
        observation["specimen"] = {"display": record.specimen_type}

    return observation


def build_bundle(result: NormalizationResult) -> dict:
    entries = []
    for record in result.records:
        observation = build_observation(record)
        if observation is None:
            continue
        entries.append(
            {
                "fullUrl": f"urn:uuid:{observation['id']}",
                "resource": observation,
            }
        )

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "meta": {"profile": [f"http://hl7.org/fhir/{FHIR_VERSION}/Bundle"]},
        "identifier": {
            "system": "urn:input-file",
            "value": result.input_file,
        },
        "entry": entries,
    }
