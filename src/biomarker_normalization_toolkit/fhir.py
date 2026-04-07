from __future__ import annotations

import uuid

from biomarker_normalization_toolkit.models import NormalizationResult, NormalizedRecord
from biomarker_normalization_toolkit.units import parse_reference_range


FHIR_VERSION = "4.0.1"
_BNT_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

UCUM_CODES: dict[str, str] = {
    "mg/dL": "mg/dL",
    "mmol/L": "mmol/L",
    "umol/L": "umol/L",
    "%": "%",
    "U/L": "U/L",
    "g/dL": "g/dL",
    "g/L": "g/L",
    "mIU/L": "m[IU]/L",
    "ng/dL": "ng/dL",
    "ng/mL": "ng/mL",
    "pg/mL": "pg/mL",
    "ug/dL": "ug/dL",
    "mg/L": "mg/L",
    "K/uL": "10*3/uL",
    "10^9/L": "10*9/L",
    "L/L": "L/L",
    "pmol/L": "pmol/L",
    "nmol/L": "nmol/L",
    "mEq/L": "meq/L",
    "M/uL": "10*6/uL",
    "10^12/L": "10*12/L",
    "fL": "fL",
    "pg": "pg",
    "sec": "s",
    "ratio": "{ratio}",
    "mL/min/1.73m2": "mL/min/{1.73_m2}",
    "mmHg": "mm[Hg]",
    "pH": "[pH]",
    "units": "[pH]",
    "ng/L": "ng/L",
    "ug/mL": "ug/mL",
    "IU/mL": "[IU]/mL",
    "kPa": "kPa",
    "pg/dL": "pg/dL",
    "#/uL": "/uL",
    "mIU/mL": "m[IU]/mL",
    "uIU/mL": "u[IU]/mL",
    "IU/L": "[IU]/L",
    "mm/hr": "mm/h",
    "mOsm/kg": "mOsm/kg",
    "mg/g": "mg/g",
    "ug/L": "ug/L",
    "nmol/min/mL": "nmol/min/mL",
    "ug/mL": "ug/mL",
    "#/hpf": "/[HPF]",
    "U/mL": "U/mL",
    "nm": "nm",
}


def _ucum_code(display_unit: str) -> str:
    return UCUM_CODES.get(display_unit, display_unit)


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
                "code": _ucum_code(parsed.unit),
            },
            "high": {
                "value": float(parsed.high),
                "unit": parsed.unit,
                "system": "http://unitsofmeasure.org",
                "code": _ucum_code(parsed.unit),
            },
            "text": record.normalized_reference_range,
        }
    ]


def _build_value_quantity(record: NormalizedRecord) -> dict:
    vq: dict = {"value": float(record.normalized_value)}
    if record.normalized_unit:
        vq["unit"] = record.normalized_unit
        vq["system"] = "http://unitsofmeasure.org"
        vq["code"] = _ucum_code(record.normalized_unit)
    return vq


def _observation_uuid(record: NormalizedRecord, input_file: str = "") -> str:
    key = record.source_row_id or f"row-{record.source_row_number}"
    seed = f"observation-{input_file}-{key}" if input_file else f"observation-{key}"
    return str(uuid.uuid5(_BNT_NAMESPACE, seed))


def build_observation(record: NormalizedRecord, input_file: str = "", effective_datetime: str | None = None) -> dict | None:
    if record.mapping_status != "mapped":
        return None

    obs_id = _observation_uuid(record, input_file)
    observation = {
        "resourceType": "Observation",
        "id": obs_id,
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
        **({"effectiveDateTime": effective_datetime} if effective_datetime else {}),
        "valueQuantity": _build_value_quantity(record),
        "note": [
            {
                "text": (
                    f"Mapped from source test '{record.source_test_name}' "
                    f"using rule '{record.mapping_rule}'."
                )
            }
        ],
    }

    if record.source_row_id:
        observation["identifier"] = [
            {
                "system": "urn:source-row-id",
                "value": record.source_row_id,
            }
        ]

    ref_range = _build_reference_range(record)
    if ref_range:
        observation["referenceRange"] = ref_range

    if record.specimen_type:
        observation["specimen"] = {"display": record.specimen_type}

    return observation


def build_bundle(result: NormalizationResult) -> dict:
    entries = []
    for record in result.records:
        observation = build_observation(record, input_file=result.input_file)
        if observation is None:
            continue
        entries.append(
            {
                "fullUrl": f"urn:uuid:{observation['id']}",  # id is already a valid UUID
                "resource": observation,
            }
        )

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "total": len(entries),
        "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/Bundle"]},
        "identifier": {
            "system": "urn:input-file",
            "value": result.input_file,
        },
        "entry": entries,
    }
