from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
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
        "ser plas": "serum",
        "ser plasma": "serum",
        "serum plas": "serum",
        "whole blood": "whole_blood",
        "blood": "whole_blood",
        "bld": "whole_blood",
        "wb": "whole_blood",
        "urine": "urine",
    }
    return mapping.get(specimen_key, specimen_key or None)


_BLOOD = frozenset({"serum", "plasma", "whole_blood"})
_WHOLE_BLOOD = frozenset({"whole_blood"})
_URINE = frozenset({"urine"})

BIOMARKER_CATALOG: dict[str, BiomarkerDefinition] = {
    "glucose_serum": BiomarkerDefinition(
        biomarker_id="glucose_serum",
        canonical_name="Glucose",
        loinc="2345-7",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=(
            "Glucose",
            "Glucose, Serum",
            "Glucose, Plasma",
            "Serum Glucose",
            "GLU",
            "Fasting Glucose",
            "Glucose SerPl",
            "Glucose [Mass/volume] in Blood",
            "Glucose [Mass/volume] in Serum or Plasma",
            "Glucose [Moles/volume] in Blood",
        ),
    ),
    "glucose_urine": BiomarkerDefinition(
        biomarker_id="glucose_urine",
        canonical_name="Urine Glucose",
        loinc="53328-1",
        normalized_unit="mg/dL",
        allowed_specimens=_URINE,
        aliases=("Glucose", "Urine Glucose", "GLU"),
    ),
    "hba1c": BiomarkerDefinition(
        biomarker_id="hba1c",
        canonical_name="Hemoglobin A1c",
        loinc="4548-4",
        normalized_unit="%",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=(
            "Hemoglobin A1c",
            "A1C",
            "HbA1c",
            "Glycated Hemoglobin",
            "Hgb A1C",
            "Glycohemoglobin A1C",
            "Hemoglobin A1c/Hemoglobin.total in Blood",
        ),
    ),
    "total_cholesterol": BiomarkerDefinition(
        biomarker_id="total_cholesterol",
        canonical_name="Total Cholesterol",
        loinc="2093-3",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("Total Cholesterol", "Cholesterol, Total", "Cholesterol Total", "CHOL TOTAL",
                 "Cholesterol [Mass/volume] in Serum or Plasma"),
    ),
    "ldl_cholesterol": BiomarkerDefinition(
        biomarker_id="ldl_cholesterol",
        canonical_name="LDL Cholesterol",
        loinc="2089-1",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("LDL Cholesterol", "LDL-C", "LDL", "LDL Chol Calc", "LDL Cholesterol Calculated", "LDL Calc",
                 "Low Density Lipoprotein Cholesterol",
                 "Cholesterol in LDL [Mass/volume] in Serum or Plasma by Direct assay"),
    ),
    "hdl_cholesterol": BiomarkerDefinition(
        biomarker_id="hdl_cholesterol",
        canonical_name="HDL Cholesterol",
        loinc="2085-9",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("HDL Cholesterol", "HDL-C", "HDL", "HDL Chol", "HDL Cholesterol Direct",
                 "High Density Lipoprotein Cholesterol",
                 "Cholesterol in HDL [Mass/volume] in Serum or Plasma"),
    ),
    "triglycerides": BiomarkerDefinition(
        biomarker_id="triglycerides",
        canonical_name="Triglycerides",
        loinc="2571-8",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("Triglycerides", "Triglyceride", "TG", "TRIG", "Triglyc",
                 "Triglycerides [Mass/volume] in Serum or Plasma",
                 "Triglyceride [Mass/volume] in Serum or Plasma"),
    ),
    "creatinine": BiomarkerDefinition(
        biomarker_id="creatinine",
        canonical_name="Creatinine",
        loinc="2160-0",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("Creatinine", "Creatinine, Serum", "Creatinine, Plasma", "Creat", "Crea", "Creatinine SerPl",
                 "Creatinine [Mass/volume] in Blood", "Creatinine [Mass/volume] in Serum or Plasma"),
    ),
    "creatinine_urine": BiomarkerDefinition(
        biomarker_id="creatinine_urine",
        canonical_name="Urine Creatinine",
        loinc="2161-8",
        normalized_unit="mg/dL",
        allowed_specimens=_URINE,
        aliases=("Creatinine", "Urine Creatinine", "Creat", "Crea", "Creatinine, Urine"),
    ),
    # --- Wave 2: Liver panel ---
    "alt": BiomarkerDefinition(
        biomarker_id="alt",
        canonical_name="ALT",
        loinc="1742-6",
        normalized_unit="U/L",
        allowed_specimens=_BLOOD,
        aliases=("ALT", "SGPT", "Alanine Aminotransferase", "ALT/SGPT",
                 "Alanine Aminotransferase (ALT)",
                 "Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma"),
    ),
    "ast": BiomarkerDefinition(
        biomarker_id="ast",
        canonical_name="AST",
        loinc="1920-8",
        normalized_unit="U/L",
        allowed_specimens=_BLOOD,
        aliases=("AST", "SGOT", "Aspartate Aminotransferase", "AST/SGOT",
                 "Asparate Aminotransferase (AST)",
                 "Aspartate aminotransferase [Enzymatic activity/volume] in Serum or Plasma"),
    ),
    "alp": BiomarkerDefinition(
        biomarker_id="alp",
        canonical_name="Alkaline Phosphatase",
        loinc="6768-6",
        normalized_unit="U/L",
        allowed_specimens=_BLOOD,
        aliases=("ALP", "Alk Phos", "Alkaline Phosphatase", "Alkaline Phosph",
                 "Alkaline phosphatase [Enzymatic activity/volume] in Serum or Plasma"),
    ),
    "total_bilirubin": BiomarkerDefinition(
        biomarker_id="total_bilirubin",
        canonical_name="Total Bilirubin",
        loinc="1975-2",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("Total Bilirubin", "Bilirubin", "TBIL", "Bili", "Bilirubin Total",
                 "Bilirubin, Total", "Bilirubin.total [Mass/volume] in Serum or Plasma"),
    ),
    "albumin": BiomarkerDefinition(
        biomarker_id="albumin",
        canonical_name="Albumin",
        loinc="1863-0",
        normalized_unit="g/dL",
        allowed_specimens=_BLOOD,
        aliases=("Albumin", "Alb", "Serum Albumin", "Albumin, Blood",
                 "Albumin [Mass/volume] in Serum or Plasma"),
    ),
    # --- Wave 2: Thyroid ---
    "tsh": BiomarkerDefinition(
        biomarker_id="tsh",
        canonical_name="TSH",
        loinc="3016-3",
        normalized_unit="mIU/L",
        allowed_specimens=_BLOOD,
        aliases=("TSH", "Thyroid Stimulating Hormone", "Thyrotropin"),
    ),
    "free_t4": BiomarkerDefinition(
        biomarker_id="free_t4",
        canonical_name="Free T4",
        loinc="3024-7",
        normalized_unit="ng/dL",
        allowed_specimens=_BLOOD,
        aliases=("Free T4", "FT4", "Thyroxine Free", "Free Thyroxine"),
    ),
    # --- Wave 2: Renal expansion ---
    "bun": BiomarkerDefinition(
        biomarker_id="bun",
        canonical_name="BUN",
        loinc="3094-0",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("BUN", "Urea Nitrogen", "Blood Urea Nitrogen",
                 "Urea nitrogen [Mass/volume] in Blood", "Urea nitrogen [Mass/volume] in Serum or Plasma"),
    ),
    # --- Wave 2: Inflammation ---
    "hscrp": BiomarkerDefinition(
        biomarker_id="hscrp",
        canonical_name="hs-CRP",
        loinc="30522-7",
        normalized_unit="mg/L",
        allowed_specimens=_BLOOD,
        aliases=("CRP", "C-Reactive Protein", "hs-CRP", "hsCRP", "High Sensitivity CRP"),
    ),
    # --- Wave 2: CBC ---
    "wbc": BiomarkerDefinition(
        biomarker_id="wbc",
        canonical_name="WBC",
        loinc="6690-2",
        normalized_unit="K/uL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("WBC", "White Blood Cells", "Leukocytes", "White Cell Count",
                 "Leukocytes [#/volume] in Blood by Automated count"),
    ),
    "hemoglobin": BiomarkerDefinition(
        biomarker_id="hemoglobin",
        canonical_name="Hemoglobin",
        loinc="718-7",
        normalized_unit="g/dL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("Hemoglobin", "Hgb", "HGB", "Hb",
                 "Hemoglobin [Mass/volume]", "Hemoglobin [Mass/volume] in Blood"),
    ),
    "hematocrit": BiomarkerDefinition(
        biomarker_id="hematocrit",
        canonical_name="Hematocrit",
        loinc="4544-0",
        normalized_unit="%",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("Hematocrit", "Hct", "HCT", "PCV", "Packed Cell Volume",
                 "Hematocrit, Calculated",
                 "Hematocrit [Volume Fraction] of Blood by Automated count"),
    ),
    "platelets": BiomarkerDefinition(
        biomarker_id="platelets",
        canonical_name="Platelets",
        loinc="777-3",
        normalized_unit="K/uL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("Platelets", "PLT", "Platelet Count", "Thrombocytes",
                 "Platelets [#/volume] in Blood",
                 "Platelets [#/volume] in Blood by Automated count"),
    ),
    # --- Wave 3: Vitamins ---
    "vitamin_d": BiomarkerDefinition(
        biomarker_id="vitamin_d",
        canonical_name="Vitamin D 25-OH",
        loinc="14979-9",
        normalized_unit="ng/mL",
        allowed_specimens=_BLOOD,
        aliases=("Vitamin D", "25-OH Vitamin D", "25-Hydroxyvitamin D", "Vit D", "D 25-OH"),
    ),
    "vitamin_b12": BiomarkerDefinition(
        biomarker_id="vitamin_b12",
        canonical_name="Vitamin B12",
        loinc="2132-9",
        normalized_unit="pg/mL",
        allowed_specimens=_BLOOD,
        aliases=("Vitamin B12", "B12", "Cobalamin"),
    ),
    "folate": BiomarkerDefinition(
        biomarker_id="folate",
        canonical_name="Folate",
        loinc="2155-0",
        normalized_unit="ng/mL",
        allowed_specimens=_BLOOD,
        aliases=("Folate", "Folic Acid", "Vitamin B9"),
    ),
    # --- Wave 3: Minerals ---
    "iron": BiomarkerDefinition(
        biomarker_id="iron",
        canonical_name="Iron",
        loinc="2498-4",
        normalized_unit="ug/dL",
        allowed_specimens=_BLOOD,
        aliases=("Iron", "Serum Iron", "Fe"),
    ),
    "ferritin": BiomarkerDefinition(
        biomarker_id="ferritin",
        canonical_name="Ferritin",
        loinc="2516-1",
        normalized_unit="ng/mL",
        allowed_specimens=_BLOOD,
        aliases=("Ferritin", "Serum Ferritin"),
    ),
    "magnesium": BiomarkerDefinition(
        biomarker_id="magnesium",
        canonical_name="Magnesium",
        loinc="2635-3",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("Magnesium", "Mag", "Mg", "Serum Magnesium"),
    ),
    # --- Wave 4: CBC sub-components ---
    "rbc": BiomarkerDefinition(
        biomarker_id="rbc",
        canonical_name="Red Blood Cells",
        loinc="789-8",
        normalized_unit="M/uL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("Red Blood Cells", "RBC", "RBC Count", "Erythrocytes",
                 "Erythrocytes [#/volume] in Blood",
                 "Erythrocytes [#/volume] in Blood by Automated count"),
    ),
    "mcv": BiomarkerDefinition(
        biomarker_id="mcv",
        canonical_name="MCV",
        loinc="787-2",
        normalized_unit="fL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("MCV", "Mean Corpuscular Volume",
                 "MCV [Entitic mean volume] in Red Blood Cells by Automated count",
                 "MCV [Entitic volume] by Automated count"),
    ),
    "mch": BiomarkerDefinition(
        biomarker_id="mch",
        canonical_name="MCH",
        loinc="785-6",
        normalized_unit="pg",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("MCH", "Mean Corpuscular Hemoglobin",
                 "MCH [Entitic mass] by Automated count"),
    ),
    "mchc": BiomarkerDefinition(
        biomarker_id="mchc",
        canonical_name="MCHC",
        loinc="786-4",
        normalized_unit="g/dL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("MCHC", "Mean Corpuscular Hemoglobin Concentration",
                 "MCHC [Entitic Mass/volume] in Red Blood Cells by Automated count",
                 "MCHC [Mass/volume] by Automated count"),
    ),
    "rdw": BiomarkerDefinition(
        biomarker_id="rdw",
        canonical_name="RDW",
        loinc="788-0",
        normalized_unit="%",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("RDW", "Red Cell Distribution Width", "RDW-CV",
                 "Erythrocyte distribution width [Ratio] by Automated count"),
    ),
    "rdw_sd": BiomarkerDefinition(
        biomarker_id="rdw_sd",
        canonical_name="RDW-SD",
        loinc="21000-5",
        normalized_unit="fL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("RDW-SD",
                 "Erythrocyte [DistWidth] in Blood by Automated count"),
    ),
    "mpv": BiomarkerDefinition(
        biomarker_id="mpv",
        canonical_name="MPV",
        loinc="32623-1",
        normalized_unit="fL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("MPV", "Mean Platelet Volume",
                 "Platelet [Entitic mean volume] in Blood by Automated count"),
    ),
    "pdw": BiomarkerDefinition(
        biomarker_id="pdw",
        canonical_name="PDW",
        loinc="32207-3",
        normalized_unit="fL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("PDW", "Platelet Distribution Width",
                 "Platelet distribution width [Entitic volume] in Blood by Automated count"),
    ),
    # --- Wave 4: Coagulation ---
    "pt": BiomarkerDefinition(
        biomarker_id="pt",
        canonical_name="Prothrombin Time",
        loinc="5902-2",
        normalized_unit="sec",
        allowed_specimens=_BLOOD,
        aliases=("PT", "Prothrombin Time", "Pro Time"),
    ),
    "inr": BiomarkerDefinition(
        biomarker_id="inr",
        canonical_name="INR",
        loinc="6301-6",
        normalized_unit="ratio",
        allowed_specimens=_BLOOD,
        aliases=("INR", "INR(PT)", "International Normalized Ratio",
                 "INR in Platelet poor plasma by Coagulation assay"),
    ),
    "ptt": BiomarkerDefinition(
        biomarker_id="ptt",
        canonical_name="PTT",
        loinc="3173-2",
        normalized_unit="sec",
        allowed_specimens=_BLOOD,
        aliases=("PTT", "aPTT", "Partial Thromboplastin Time",
                 "Activated Partial Thromboplastin Time"),
    ),
    # --- Wave 4: Other high-frequency ---
    "anion_gap": BiomarkerDefinition(
        biomarker_id="anion_gap",
        canonical_name="Anion Gap",
        loinc="33037-3",
        normalized_unit="mEq/L",
        allowed_specimens=_BLOOD,
        aliases=("Anion Gap", "AG"),
    ),
    "lactate": BiomarkerDefinition(
        biomarker_id="lactate",
        canonical_name="Lactate",
        loinc="2524-7",
        normalized_unit="mmol/L",
        allowed_specimens=_BLOOD,
        aliases=("Lactate", "Lactic Acid", "Lactate [Moles/volume] in Blood"),
    ),
    # --- Wave 4: Electrolytes (from MIMIC/Synthea analysis) ---
    "sodium": BiomarkerDefinition(
        biomarker_id="sodium",
        canonical_name="Sodium",
        loinc="2951-2",
        normalized_unit="mEq/L",
        allowed_specimens=_BLOOD,
        aliases=("Sodium", "Na", "Serum Sodium", "Sodium, Whole Blood",
                 "Sodium [Moles/volume] in Blood",
                 "Sodium [Moles/volume] in Serum or Plasma"),
    ),
    "potassium": BiomarkerDefinition(
        biomarker_id="potassium",
        canonical_name="Potassium",
        loinc="2823-3",
        normalized_unit="mEq/L",
        allowed_specimens=_BLOOD,
        aliases=("Potassium", "K", "Serum Potassium", "Potassium, Whole Blood",
                 "Potassium [Moles/volume] in Blood",
                 "Potassium [Moles/volume] in Serum or Plasma"),
    ),
    "chloride": BiomarkerDefinition(
        biomarker_id="chloride",
        canonical_name="Chloride",
        loinc="2075-0",
        normalized_unit="mEq/L",
        allowed_specimens=_BLOOD,
        aliases=("Chloride", "Cl", "Serum Chloride", "Chloride, Whole Blood",
                 "Chloride [Moles/volume] in Blood",
                 "Chloride [Moles/volume] in Serum or Plasma"),
    ),
    "bicarbonate": BiomarkerDefinition(
        biomarker_id="bicarbonate",
        canonical_name="Bicarbonate",
        loinc="1963-8",
        normalized_unit="mEq/L",
        allowed_specimens=_BLOOD,
        aliases=("Bicarbonate", "CO2", "Total CO2", "Carbon Dioxide", "HCO3",
                 "Calculated Total CO2",
                 "Carbon dioxide total [Moles/volume] in Blood",
                 "Carbon dioxide  total [Moles/volume] in Blood",
                 "Carbon dioxide  total [Moles/volume] in Serum or Plasma"),
    ),
    "calcium": BiomarkerDefinition(
        biomarker_id="calcium",
        canonical_name="Calcium",
        loinc="17861-6",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("Calcium", "Ca", "Calcium, Total", "Serum Calcium", "Total Calcium",
                 "Calcium [Mass/volume] in Blood", "Calcium [Mass/volume] in Serum or Plasma"),
    ),
    "phosphate": BiomarkerDefinition(
        biomarker_id="phosphate",
        canonical_name="Phosphate",
        loinc="2777-1",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("Phosphate", "Phosphorus", "Phos", "Inorganic Phosphate"),
    ),
    "uric_acid": BiomarkerDefinition(
        biomarker_id="uric_acid",
        canonical_name="Uric Acid",
        loinc="3084-1",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("Uric Acid", "Urate"),
    ),
    # --- Wave 6: Enzymes ---
    "ldh": BiomarkerDefinition(
        biomarker_id="ldh",
        canonical_name="Lactate Dehydrogenase",
        loinc="2532-0",
        normalized_unit="U/L",
        allowed_specimens=_BLOOD,
        aliases=("LDH", "Lactate Dehydrogenase", "Lactate Dehydrogenase (LD)", "LD"),
    ),
    "lipase": BiomarkerDefinition(
        biomarker_id="lipase",
        canonical_name="Lipase",
        loinc="3040-3",
        normalized_unit="U/L",
        allowed_specimens=_BLOOD,
        aliases=("Lipase",),
    ),
    "ck": BiomarkerDefinition(
        biomarker_id="ck",
        canonical_name="Creatine Kinase",
        loinc="2157-6",
        normalized_unit="U/L",
        allowed_specimens=_BLOOD,
        aliases=("CK", "Creatine Kinase", "Creatine Kinase (CK)", "CPK"),
    ),
    "ck_mb": BiomarkerDefinition(
        biomarker_id="ck_mb",
        canonical_name="CK-MB",
        loinc="2154-3",
        normalized_unit="ng/mL",
        allowed_specimens=_BLOOD,
        aliases=("CK-MB", "Creatine Kinase, MB Isoenzyme", "CK MB", "CKMB"),
    ),
    # --- Wave 6: Cardiac ---
    "troponin_t": BiomarkerDefinition(
        biomarker_id="troponin_t",
        canonical_name="Troponin T",
        loinc="6598-7",
        normalized_unit="ng/mL",
        allowed_specimens=_BLOOD,
        aliases=("Troponin T", "Troponin-T", "cTnT", "Cardiac Troponin T"),
    ),
    # --- Wave 6: Blood gases ---
    "pco2": BiomarkerDefinition(
        biomarker_id="pco2",
        canonical_name="pCO2",
        loinc="2019-8",
        normalized_unit="mmHg",
        allowed_specimens=_BLOOD,
        aliases=("pCO2", "PCO2", "Carbon Dioxide Partial Pressure",
                 "Carbon dioxide [Partial pressure] in Arterial blood",
                 "Carbon dioxide [Partial pressure] in Blood",
                 "Carbon dioxide [Partial pressure] in Venous blood"),
    ),
    "po2": BiomarkerDefinition(
        biomarker_id="po2",
        canonical_name="pO2",
        loinc="2703-7",
        normalized_unit="mmHg",
        allowed_specimens=_BLOOD,
        aliases=("pO2", "PO2", "Oxygen Partial Pressure",
                 "Oxygen [Partial pressure] in Arterial blood",
                 "Oxygen [Partial pressure] in Blood"),
    ),
    "base_excess": BiomarkerDefinition(
        biomarker_id="base_excess",
        canonical_name="Base Excess",
        loinc="11555-0",
        normalized_unit="mEq/L",
        allowed_specimens=_BLOOD,
        aliases=("Base Excess", "BE",
                 "Base excess in Blood by calculation"),
    ),
    # --- Wave 6: Other ---
    "globulin": BiomarkerDefinition(
        biomarker_id="globulin",
        canonical_name="Globulin",
        loinc="10834-0",
        normalized_unit="g/dL",
        allowed_specimens=_BLOOD,
        aliases=("Globulin", "Globulin [Mass/volume] in Serum by calculation"),
    ),
    "ionized_calcium": BiomarkerDefinition(
        biomarker_id="ionized_calcium",
        canonical_name="Ionized Calcium",
        loinc="1994-3",
        normalized_unit="mmol/L",
        allowed_specimens=_BLOOD,
        aliases=("Ionized Calcium", "Free Calcium", "Calcium Ionized", "iCa"),
    ),
    "fibrinogen": BiomarkerDefinition(
        biomarker_id="fibrinogen",
        canonical_name="Fibrinogen",
        loinc="3255-7",
        normalized_unit="mg/dL",
        allowed_specimens=_BLOOD,
        aliases=("Fibrinogen", "Fibrinogen, Functional", "Fibrinogen Activity"),
    ),
    "eag": BiomarkerDefinition(
        biomarker_id="eag",
        canonical_name="Estimated Average Glucose",
        loinc="27353-2",
        normalized_unit="mg/dL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("eAG", "Estimated Average Glucose"),
    ),
    "blood_ph": BiomarkerDefinition(
        biomarker_id="blood_ph",
        canonical_name="Blood pH",
        loinc="2744-1",
        normalized_unit="pH",
        allowed_specimens=_BLOOD,
        aliases=("pH", "Blood pH", "Arterial pH"),
    ),
    "oxygen_saturation": BiomarkerDefinition(
        biomarker_id="oxygen_saturation",
        canonical_name="Oxygen Saturation",
        loinc="2708-6",
        normalized_unit="%",
        allowed_specimens=_BLOOD,
        aliases=("Oxygen Saturation", "O2 Sat", "SpO2", "SaO2", "O2Sat"),
    ),
    # --- Urinalysis ---
    "urine_specific_gravity": BiomarkerDefinition(
        biomarker_id="urine_specific_gravity",
        canonical_name="Urine Specific Gravity",
        loinc="5811-5",
        normalized_unit="",
        allowed_specimens=_URINE,
        aliases=("Specific Gravity", "Urine Specific Gravity", "SG",
                 "Specific gravity of Urine by Test strip"),
    ),
    "urine_ph": BiomarkerDefinition(
        biomarker_id="urine_ph",
        canonical_name="Urine pH",
        loinc="5803-2",
        normalized_unit="pH",
        allowed_specimens=_URINE,
        aliases=("pH", "Urine pH",
                 "pH of Urine by Test strip"),
    ),
    "urine_protein": BiomarkerDefinition(
        biomarker_id="urine_protein",
        canonical_name="Urine Protein",
        loinc="2888-6",
        normalized_unit="mg/dL",
        allowed_specimens=_URINE,
        aliases=("Protein", "Urine Protein",
                 "Protein [Mass/volume] in Urine by Test strip"),
    ),
    "urine_ketones": BiomarkerDefinition(
        biomarker_id="urine_ketones",
        canonical_name="Urine Ketones",
        loinc="2514-8",
        normalized_unit="mg/dL",
        allowed_specimens=_URINE,
        aliases=("Ketones", "Urine Ketones",
                 "Ketones [Mass/volume] in Urine by Test strip"),
    ),
    "urine_bilirubin": BiomarkerDefinition(
        biomarker_id="urine_bilirubin",
        canonical_name="Urine Bilirubin",
        loinc="1977-8",
        normalized_unit="mg/dL",
        allowed_specimens=_URINE,
        aliases=("Bilirubin", "Urine Bilirubin",
                 "Bilirubin.total [Mass/volume] in Urine by Test strip"),
    ),
    # --- Wave 5: WBC differentials ---
    "neutrophils": BiomarkerDefinition(
        biomarker_id="neutrophils",
        canonical_name="Neutrophils",
        loinc="26499-4",
        normalized_unit="K/uL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("Neutrophils", "Neutrophil Count", "ANC", "Absolute Neutrophil Count",
                 "Neutrophils [#/volume] in Blood",
                 "Neutrophils/100 leukocytes in Blood by Automated count"),
    ),
    "lymphocytes": BiomarkerDefinition(
        biomarker_id="lymphocytes",
        canonical_name="Lymphocytes",
        loinc="26474-7",
        normalized_unit="K/uL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("Lymphocytes", "Lymphocyte Count", "Lymph",
                 "Absolute Lymphocyte Count",
                 "Lymphocytes [#/volume] in Blood",
                 "Lymphocytes/100 leukocytes in Blood by Automated count"),
    ),
    "monocytes": BiomarkerDefinition(
        biomarker_id="monocytes",
        canonical_name="Monocytes",
        loinc="26484-6",
        normalized_unit="K/uL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("Monocytes", "Monocyte Count", "Mono",
                 "Absolute Monocyte Count",
                 "Monocytes [#/volume] in Blood",
                 "Monocytes/100 leukocytes in Blood by Automated count"),
    ),
    "eosinophils": BiomarkerDefinition(
        biomarker_id="eosinophils",
        canonical_name="Eosinophils",
        loinc="26449-9",
        normalized_unit="K/uL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("Eosinophils", "Eosinophil Count", "Eos",
                 "Absolute Eosinophil Count",
                 "Eosinophils [#/volume] in Blood",
                 "Eosinophils/100 leukocytes in Blood by Automated count"),
    ),
    "basophils": BiomarkerDefinition(
        biomarker_id="basophils",
        canonical_name="Basophils",
        loinc="26444-0",
        normalized_unit="K/uL",
        allowed_specimens=_WHOLE_BLOOD,
        aliases=("Basophils", "Basophil Count", "Baso",
                 "Absolute Basophil Count",
                 "Basophils [#/volume] in Blood",
                 "Basophils/100 leukocytes in Blood by Automated count"),
    ),
    # --- Wave 5: Other ---
    "total_protein": BiomarkerDefinition(
        biomarker_id="total_protein",
        canonical_name="Total Protein",
        loinc="2885-2",
        normalized_unit="g/dL",
        allowed_specimens=_BLOOD,
        aliases=("Total Protein", "Protein, Total", "TP",
                 "Protein [Mass/volume] in Serum or Plasma"),
    ),
    "egfr": BiomarkerDefinition(
        biomarker_id="egfr",
        canonical_name="eGFR",
        loinc="33914-3",
        normalized_unit="mL/min/1.73m2",
        allowed_specimens=_BLOOD,
        aliases=("eGFR", "GFR", "Estimated GFR", "Estimated Glomerular Filtration Rate",
                 "Glomerular filtration rate/1.73 sq M.predicted",
                 "Glomerular filtration rate [Volume Rate/Area] in Serum or Plasma by Creatinine-based formula (MDRD)/1.73 sq M"),
    ),
}


ALIAS_INDEX: dict[str, list[str]] = {}
for biomarker_id, biomarker in BIOMARKER_CATALOG.items():
    for alias in biomarker.aliases:
        alias_key = normalize_key(alias)
        candidates = ALIAS_INDEX.setdefault(alias_key, [])
        if biomarker_id not in candidates:
            candidates.append(biomarker_id)


def load_custom_aliases(path: Path) -> int:
    """Load custom alias mappings from a JSON file and merge into ALIAS_INDEX.

    The JSON file should be a dict mapping biomarker_id to a list of alias strings:
    {
        "glucose_serum": ["Blood Sugar", "FBG", "Fasting Blood Sugar"],
        "hba1c": ["GHb", "Glycosylated Hemoglobin"]
    }

    Returns the number of aliases added.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Custom alias file must be a JSON object mapping biomarker_id to alias lists.")
    added = 0
    for biomarker_id, aliases in data.items():
        if biomarker_id not in BIOMARKER_CATALOG:
            continue
        if not isinstance(aliases, list):
            continue
        for alias in aliases:
            if not isinstance(alias, str):
                continue
            alias_key = normalize_key(alias)
            candidates = ALIAS_INDEX.setdefault(alias_key, [])
            if biomarker_id not in candidates:
                candidates.append(biomarker_id)
                added += 1
    return added
