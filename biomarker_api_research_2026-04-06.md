# Biomarker Normalization API Research

Date: 2026-04-06

## Executive Take

The route is viable, but only if you define it narrowly.

A generic healthcare interoperability platform is already crowded with well-capitalized infrastructure companies. Current official materials from Redox, Health Gorilla, Junction, and 1upHealth all show broad coverage across EHR connectivity, lab ordering/results, FHIR exchange, and clinical data retrieval:

- Redox positions itself as a general interoperability platform with data normalization across FHIR, HL7, X12, JSON, and custom APIs, with 90+ EHRs and 10K+ integrations: <https://redoxengine.com/use-cases/normalize-data-for-custom-healthcare-workflows/>
- Health Gorilla offers FHIR APIs, Patient360 retrieval, diagnostic ordering, and "normalized results through a standardized integration": <https://developer.healthgorilla.com/> and <https://developer.healthgorilla.com/docs/diagnostic-network>
- Junction offers a unified API for nationwide lab testing and 300+ devices, and says it has helped deliver 6M+ lab tests: <https://www.junction.com/> and <https://www.junction.com/app/careers>
- 1upHealth positions itself as a FHIR-first platform for acquiring, normalizing, managing, and exchanging clinical and claims data: <https://1up.health/products/1up-fhir-platform>

My inference from those sources: the open slot is not "Plaid for healthcare." The open slot is a more specific layer for biomarker data normalization from ugly, heterogeneous sources:

- vendor-specific lab catalogs and aliases
- unit harmonization
- reference-range normalization
- LOINC mapping
- canonical FHIR Observation output
- ingest from PDFs, HL7, CSVs, and bespoke vendor feeds

That narrower wedge is more defensible than trying to outcompete general interoperability vendors.

## Why the wedge is still real

Regenstrief still actively maintains LOINC mapping tools and a community mapping repository, which is strong evidence that local-to-LOINC mapping remains an ongoing operational problem rather than a solved commodity:

- RELMA exists specifically to help map local codes to LOINC: <https://loinc.org/relma/>
- Regenstrief publishes mapping resources specifically for large lab catalogs: <https://loinc.org/get-started/mapping-resources/>
- Regenstrief also maintains a community mapping repository for local-code-to-LOINC mappings: <https://loinc.org/mappings/>

My inference: if buyers still need dedicated tooling and shared repositories for local mapping, then a product that turns messy biomarker data into clean canonical observations still has room, especially if it specializes in longitudinal biomarker use cases rather than whole-record interoperability.

## Compliance Answer

Yes. You would need compliance for this route. The amount depends on exactly which route you take.

### 1. Pure B2B normalization API for providers, payers, labs, or their vendors

If you create, receive, maintain, or transmit PHI on behalf of a covered entity, you are very likely a HIPAA business associate.

Primary sources:

- HHS: a business associate is a person or entity that performs functions involving protected health information on behalf of, or provides services to, a covered entity: <https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/business-associates/index.html>
- HHS: BA contracts must define permitted uses, require safeguards, breach reporting, subcontractor flow-downs, return/destruction, etc.: <https://www.hhs.gov/hipaa/for-professionals/covered-entities/sample-business-associate-agreement-provisions/index.html>
- HHS: risk analysis is foundational under the Security Rule: <https://www.hhs.gov/hipaa/for-professionals/security/guidance/guidance-risk-analysis/index.html>
- HHS: OCR is actively auditing covered entities and business associates in the 2024-2025 audit cycle: <https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/audit/index.html>
- HHS: recent OCR enforcement confirms business associates are directly in scope: <https://www.hhs.gov/press-room/hhs-ocr-bst-hipaa-settlement.html>

Practical meaning:

- You need BAAs with HIPAA customers before production PHI.
- Your cloud vendors and subprocessors that handle ePHI also need compliant contractual flow-downs where required.
- You need an actual HIPAA program, not just a privacy policy.

### 2. Are you required to get CLIA?

Usually no, not for a normalization API alone.

CMS says a facility is a laboratory under CLIA if it performs even one test on human specimens for diagnosis, prevention, treatment, or health assessment. CMS also states that facilities only collecting or preparing specimens, or only serving as a mailing service, are not laboratories, and facilities only collecting specimens without performing testing do not need a certificate:

- <https://www.cms.gov/medicare/quality/clinical-laboratory-improvement-amendments/apply>

So:

- If you only ingest, normalize, store, and route lab results, you are generally not the testing laboratory.
- If you start actually performing testing, or operating a testing lab workflow yourself, CLIA becomes relevant.

### 3. FDA risk for the B2B normalization layer

If the software only transfers, stores, converts formats, or displays lab/device data, FDA materials indicate it is likely not a device.

Primary sources:

- FDA Step 5 says software solely intended to transfer, store, convert formats, or display clinical laboratory test or device data is not a device; interpretation/analysis changes that: <https://www.fda.gov/medical-devices/digital-health-center-excellence/step-5-software-function-intended-transferring-storing-converting-formats-or-displaying-data-and>
- FDA Medical Device Data Systems page says software solely intended to transfer, store, convert formats, and display medical device data is not subject to device requirements: <https://www.fda.gov/medical-devices/general-hospital-devices-and-supplies/medical-device-data-systems>

But the line moves if you add interpretation.

- FDA Step 6 says software intended for patients or caregivers does not meet the statutory CDS exclusion used for HCP-facing decision support: <https://www.fda.gov/medical-devices/digital-health-center-excellence/step-6-software-function-intended-provide-clinical-decision-support>
- FDA's January 2026 CDS guidance confirms that FDA still analyzes software functions differently when they are intended for patients/caregivers: <https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software>

Practical meaning:

- Pure normalization and canonicalization: lower FDA risk.
- Patient-specific interpretation, risk scoring, or "you should do X" outputs: materially higher FDA and medical-practice risk.

### 4. DTC showcase app: HIPAA usually does not save you

If your direct-to-consumer product is not operating on behalf of a covered entity, HIPAA often does not apply to that DTC data flow.

HHS says that when a consumer uses an app for the consumer's own purposes, and the app is not provided by or on behalf of a covered entity, that app developer is not likely subject to HIPAA as a covered entity or business associate:

- <https://www.hhs.gov/sites/default/files/ocr-health-app-developer-scenarios-2-2016.pdf>
- <https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/access-right-health-apps-apis/index.html>

But that does not mean "no compliance."

For non-HIPAA health apps, the FTC Health Breach Notification Rule and FTC Act become relevant:

- FTC HBNR applies to vendors of personal health records, PHR related entities, and service providers: <https://www.ftc.gov/business-guidance/resources/complying-ftcs-health-breach-notification-rule-0>
- FTC clarified in 2024 that HBNR applies to health apps and similar technologies not covered by HIPAA: <https://www.ftc.gov/news-events/news/press-releases/2024/04/ftc-finalizes-changes-health-breach-notification-rule>
- FTC guidance warns that unauthorized disclosure of health data, including via tracking technologies, can trigger FTC Act and HBNR issues: <https://www.ftc.gov/business-guidance/resources/collecting-using-or-sharing-consumer-health-information-look-hipaa-ftc-act-health-breach>
- FTC's Premom action is a concrete example: <https://www.ftc.gov/news-events/news/press-releases/2023/05/ovulation-tracking-app-premom-will-be-barred-sharing-health-data-advertising-under-proposed-ftc-order>

Practical meaning:

- A DTC upload-and-interpret app should be treated as a regulated health-data product even if HIPAA does not apply.
- Do not use ad pixels or SDKs casually on health-data flows.
- Build breach-notification processes up front.

### 5. State privacy laws matter immediately for DTC

Even if HIPAA does not apply, state consumer-health-data laws can.

Important official examples:

- Washington My Health My Data Act: applies broadly to businesses targeting Washington consumers and also applies to processors; requires privacy policy, consent, deletion rights, and has both AG enforcement and private action: <https://www.atg.wa.gov/protecting-washingtonians-personal-health-data-and-privacy>
- Nevada SB 370 summary: requires privacy policies, affirmative consent, deletion workflow, restrictions on sale and geofencing, and treats violations as deceptive trade practices: <https://epubs.nsla.nv.gov/statepubs/epubs/292049-2023.pdf>
- Connecticut AG explains CTDPA consumer health data controller obligations, including consent for sensitive data and processor contracting: <https://portal.ct.gov/ag/sections/privacy/the-connecticut-data-privacy-act/>
- California CCPA can apply if you hit thresholds; California treats health information as sensitive personal information and grants deletion / opt-out / limit-use rights: <https://www.oag.ca.gov/privacy/ccpa>

Practical meaning:

- National DTC rollout means state-law mapping, not just "HIPAA or not."
- The B2B-only route is simpler from a privacy-law surface-area standpoint than a public consumer app.

### 6. Information blocking risk if you evolve into an exchange layer

This is not your immediate blocker, but it matters if the platform becomes a multi-party exchange.

ASTP/ONC says a health information network or exchange includes entities that enable exchange of electronic health information among more than two unaffiliated entities for treatment, payment, or healthcare operations:

- <https://healthit.gov/resources/information-blocking-actors/>

My inference: a narrow normalization vendor serving one customer at a time is less exposed here. A broader network/exchange product can drift toward information-blocking obligations.

## What compliance is actually required at launch

### If you launch B2B-first and handle HIPAA PHI

Minimum serious baseline:

- BAA template for customers
- Subprocessor BAAs / HIPAA-ready vendor stack
- documented HIPAA risk analysis
- risk management plan
- access controls, least privilege, MFA
- audit logging and log review
- encryption in transit and at rest
- incident response and breach workflow
- retention / deletion / return-of-data controls
- workforce training

Not a statute, but likely demanded by buyers:

- SOC 2 Type II

### If you run a public DTC showcase

Minimum serious baseline:

- separate consumer health privacy policy
- explicit consent flows for collection and sharing
- deletion workflow
- breach-notification workflow
- no advertising trackers / pixels / SDKs on sensitive pages unless you are absolutely certain the use is lawful and disclosed
- state-law review for WA, NV, CT, CA at minimum

### If you keep the showcase strictly educational

This is the lowest-risk version:

- show raw results, trends, units, ranges, provenance
- show cited educational content and reference material
- avoid patient-specific treatment directives
- avoid disease diagnosis language unless you have counsel signoff and an appropriate clinical model

## Bottom Line

The business route can work, but the winning shape is narrower than the original memo suggested:

1. Sell a biomarker normalization layer, not a general interoperability platform.
2. Keep the core product in the lower-risk "ingest, normalize, standardize, route, display" lane.
3. Treat compliance as part of the product from day one.

Direct answer to the question:

- Yes, you would need compliance for that route.
- For B2B HIPAA customers, that means real HIPAA business-associate compliance.
- For a DTC showcase, that means FTC + state consumer-health-data compliance even when HIPAA does not apply.
- CLIA is usually not required unless you actually perform testing.
- FDA risk is manageable if you stay out of patient-specific interpretation and treatment recommendations.

## Next Moves I Would Recommend

1. Define the product boundary in writing:
   "We normalize and standardize lab data; we do not diagnose, prescribe, or recommend treatment."
2. Pilot with de-identified or synthetic data first where possible.
3. Build a HIPAA-ready security and contracting baseline before taking production PHI.
4. Keep any DTC showcase educational and tracker-free.
5. Have a healthcare privacy/regulatory attorney review the exact workflow before launch.
