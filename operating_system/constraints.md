# Constraints

Date locked: 2026-04-06

These are hard business constraints, not suggestions.

## Route Lock

The business is optimized for:

- B2B only at the start
- customer-run toolkit or productized service
- biomarker normalization and mapping only
- no hosted PHI by default
- no consumer product by default
- no clinical recommendation engine

## Hard Constraints

An idea is rejected immediately if any of the following are true:

1. It requires a consumer-facing app at launch.
2. It requires us to host live PHI at launch.
3. It requires HIPAA business-associate operations before first revenue.
4. It requires physician review, medical licensure, MSO/PC structure, or treatment workflows.
5. It requires CLIA laboratory operations.
6. It requires FDA-regulated interpretation or patient-specific recommendation behavior.
7. It cannot launch for less than or equal to `$1,000` incremental cash spend.
8. It cannot produce customer value without real patient records in our environment.
9. It does not increase the quality, depth, or coverage of the biomarker normalization corpus.
10. It creates ongoing custom work that cannot be turned into a repeatable asset.

## Preferred Constraints

Among ideas that survive the hard constraints, prefer ones that:

- can be sold as a service before the software is perfect
- can be delivered from compendia, dictionaries, and de-identified samples
- improve alias coverage, unit conversion rules, reference-range handling, or LOINC mapping
- can be deployed as a CLI, Docker image, or SDK
- produce recurring revenue from mapping updates and support
- reduce the odds of becoming a general-purpose interoperability vendor

## Hard No List

Do not build any of these as the first product:

- DTC lab upload app
- hosted interpretation dashboard
- clinic EHR / CRM / scheduling platform
- lab ordering or specimen logistics system
- telehealth workflow
- supplement recommendation engine
- AI health coach that tells patients what to do
- cross-customer data exchange network

## One-Sentence Product Boundary

We normalize and standardize biomarker data into canonical machine-readable output; we do not diagnose, prescribe, or recommend treatment.

