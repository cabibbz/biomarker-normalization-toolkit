# Medical Disclaimer

## Not Medical Advice

The Biomarker Normalization Toolkit is a data-processing library. It is not a medical device and does not diagnose, treat, cure, or prevent disease.

## No Clinical Decision Support

Features such as PhenoAge, derived metrics, optimal-range evaluation, and plausibility checks are provided for research, data review, and software integration purposes. They are not a substitute for clinician judgment.

- PhenoAge is a published research formula.
- Optimal ranges are interpretive targets, not diagnostic thresholds.
- Derived metrics reflect published calculations and should be reviewed in context.
- Plausibility checks are data-quality warnings, not clinical findings.

## Data Accuracy

This project is tested, but no normalization layer is perfect. Mapping errors, unit errors, source-format issues, and alias gaps are still possible. Users are responsible for validating normalized output against source data before using it in production, research, or clinical workflows.

## User Responsibility

Users are responsible for:

- validating output quality against source systems
- meeting legal and regulatory obligations in their own deployment
- protecting any patient or regulated data they process
- not treating normalized output as medical advice

## Warranty

This software is provided on an "as is" basis under the terms of the Apache-2.0 license. See [LICENSE](LICENSE).
