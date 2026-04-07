# Medical Disclaimer

## Not Medical Advice

The Biomarker Normalization Toolkit (BNT) is a **data processing tool**, not a medical device or diagnostic system. It normalizes laboratory test data into standardized formats. It does **not** diagnose, treat, cure, or prevent any disease or medical condition.

## No Clinical Decision Support

BNT's features — including PhenoAge biological age estimation, optimal longevity ranges, derived metabolic metrics, and plausibility checks — are provided **for informational and research purposes only**. They are **not** intended to be used as the basis for clinical decisions.

- **PhenoAge** is a research tool based on the Levine 2018 published formula. It has not been validated for individual clinical decision-making.
- **Optimal ranges** reflect published longevity research and are more restrictive than standard laboratory reference ranges. They are not diagnostic thresholds.
- **Derived metrics** (HOMA-IR, TG/HDL ratio, etc.) are computed from published formulas. They should be interpreted by a qualified healthcare provider.
- **Plausibility checks** flag likely data entry errors, not clinical abnormalities.

## Data Accuracy

While BNT is tested against hundreds of thousands of real-world laboratory records, **no normalization tool is 100% accurate**. Mapping errors, unit conversion errors, and alias mismatches are possible. Users must validate BNT's output against their source data before using it in any clinical, research, or commercial context.

BNT processes data deterministically. The same input always produces the same output. However, the correctness of that output depends on the quality and format of the input data.

## User Responsibility

Users of BNT are solely responsible for:
- Validating the accuracy of normalized output against their source data
- Ensuring their use of BNT complies with applicable laws and regulations (HIPAA, GDPR, etc.)
- Not using BNT output as a substitute for professional medical advice
- Maintaining the security and privacy of any patient data they process

## No Warranty

BNT is provided "as is" without warranty of any kind, express or implied. The developers are not liable for any damages arising from the use of this software, including but not limited to clinical decisions made based on its output.

## Contact

For questions about BNT's capabilities and limitations, contact the development team before deploying in a clinical or commercial context.
