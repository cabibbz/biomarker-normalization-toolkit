# Route Decision

Date: 2026-04-06

## Decision

The best route to take now is:

**Sell a productized B2B mapping service first, delivered through a customer-run biomarker normalization toolkit.**

In plain terms:

- do **not** launch a consumer app
- do **not** launch a hosted PHI SaaS first
- do **not** try to become a broad interoperability platform
- start by selling **local-code / vendor-alias / unit / reference-range / LOINC normalization** for labs and biomarker data
- package the repeatable part as a **CLI / Docker image / SDK** the customer runs in their own environment
- sell **implementation + mapping updates + support** as the monetization layer

This is the highest-probability route **right now** given the current market, your apparent constraints, and the compliance/cost concerns already discussed.

## Why this wins now

### 1. The broad interoperability layer is real, but too crowded

Current official signals show that broad health-data interoperability is already being consolidated by well-funded infrastructure vendors:

- Redox says it has **14,600+ live connections** and is joining CommonWell / TEFCA-oriented workflows: <https://redoxengine.com/blog/redox-joins-commonwell-health-alliance-advance-data-interoperability/>
- Health Gorilla is a federally designated **QHIN** and offers record retrieval, lab ordering from **120+ vendors**, MPI, and a normalization engine: <https://www.healthgorilla.com/blog/health-gorilla-achieves-federal-designation-as-a-qualified-health-information-network> and <https://healthgorilla.com/home/policies/product-documentation>
- Junction raised **$18M**, serves **140+ healthcare organizations**, and says it supports **500K+ lab tests annually** and **2M+ connected devices**: <https://www.junction.com/series-a>

My inference: there is demand here, but the generic infrastructure layer is already occupied by companies with network scale, compliance teams, and implementation teams.

### 2. Integration pain is still severe, which is good for a narrower wedge

Official Junction materials say:

- it still takes **6+ months** to integrate labs and devices in many cases
- lab workflows remain full of manual follow-up and unfulfilled orders
- onboarding is complex enough that Junction is hiring dedicated implementation engineers to manage mapping, testing, compendia updates, and edge cases

Sources:

- <https://www.junction.com/series-a>
- <https://www.junction.com/app/careers/7f310a6d-3091-45c0-acbe-e3a81d769762>

My inference: buyers still experience the exact class of mess you are targeting. That supports a focused wedge around biomarker normalization and mapping rather than a full platform build.

### 3. Buyers already pay for implementation and profiling work

Current official pricing from Health Samurai shows the market already accepts high-value spending on interoperability software plus services:

- Aidbox Base starts at **$19,000/year**
- deployment starts at **$2,900 one-time**
- maintenance starts at **$5,000/year**
- training is **$6,000**
- integration / profiling work is sold separately

Source:

- <https://www.health-samurai.io/price>

My inference: you do not need to start with a pure software-only product. A productized service is not a fallback here; it matches how buyers already purchase this kind of infrastructure.

### 4. DTC is getting stronger, but that makes it worse for you

The direct-to-consumer biomarker and preventive-health market is clearly real, but it is moving toward vertically integrated, well-capitalized players:

- Function now markets **160+ lab tests/year** at **$365/year**, says members have completed **50M+ lab results**, and is adding imaging and AI-backed protocols: <https://www.functionhealth.com/> and <https://www.functionhealth.com/article/function-announcement>
- Hims & Hers reported **2.5M+ subscribers** and **$2.35B** revenue for 2025, while also acquiring Trybe Labs to expand into at-home testing: <https://investors.hims.com/news/news-details/2026/Hims--Hers-Health-Inc--Reports-Fourth-Quarter-and-Full-Year-2025-Financial-Results/default.aspx> and <https://news.hims.com/newsroom/hims-hers-acquires-at-home-lab-testing-facility-expanding-capabilities-to-ultimately-deliver-integrated-offerings-that-include-at-cost-whole-body-testing-personalized-care-for-subscribers>

My inference: consumer opportunity exists, but the winning shape is now testing + care + distribution + brand. A small team should not enter there first.

### 5. Compliance pressure favors staying out of hosted PHI and consumer health apps

The regulatory trend is not getting lighter for small operators:

- HHS says business associates handling PHI on behalf of covered entities need written assurances and safeguards, and OCR has **initiated 2024-2025 HIPAA audits** focused on ransomware and Security Rule compliance: <https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/business-associates/index.html> and <https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/audit/index.html>
- FTC says the Health Breach Notification Rule applies to many non-HIPAA health apps and similar technologies, including vendors of personal health records and related entities: <https://www.ftc.gov/business-guidance/resources/complying-ftcs-health-breach-notification-rule-0>
- FDA says software that only transfers, stores, converts, or displays data is much lower risk than software that interprets or analyzes it: <https://www.fda.gov/medical-devices/digital-health-center-excellence/step-5-software-function-intended-transferring-storing-converting-formats-or-displaying-data-and>

My inference: if you want speed and low burn, your first product should stay outside hosted PHI and outside consumer health-app workflows.

## Best Route, Precisely

### Phase 1: Productized service

Sell:

- local test name to canonical biomarker mapping
- unit normalization
- reference-range normalization
- LOINC assignment
- FHIR Observation transformation
- vendor catalog cleanup
- test menu / compendia update handling

Operational rule:

- the customer sends you vendor compendia, local test dictionaries, and de-identified examples
- you do not require live patient data
- deliver mapping specs, config, tests, and a runnable toolkit

### Phase 2: Customer-run toolkit

Package the reusable work into:

- a CLI
- a Docker image
- or an embeddable SDK

Why customer-run matters:

- lower compliance exposure
- lower ops cost
- easier to launch under a small budget
- easier to sell to teams that do not want another hosted PHI processor

### Phase 3: Recurring revenue

Charge for:

- annual license
- mapping updates
- support / SLA
- custom vendor onboarding

This gives you recurring revenue without needing to become a full PHI-hosting platform immediately.

## What not to do now

### 1. Do not start with a DTC app

Reason:

- crowded
- expensive acquisition
- heavier FTC / state privacy exposure
- strong incumbents now bundle labs + clinicians + AI + brand

### 2. Do not start with a hosted API for live PHI

Reason:

- HIPAA / BAA / security program / buyer diligence become immediate blockers
- the market has strong incumbents already
- your budget constraint is too low for this to be the first move

### 3. Do not start with clinic SaaS

Reason:

- clinics want workflows, not just data
- support burden is high
- onboarding is messy
- you would get pulled into EHR, scheduling, billing, messaging, and provider workflow sprawl

## Why this route fits your constraint best

If your real goal is:

- lowest compliance
- lowest cash required
- fastest path to first revenue
- still aligned with where the market is headed

then this route is the best one.

It uses the market signal that:

- clean health data infrastructure is valuable
- implementation is still painful
- buyers pay for both tooling and services

while avoiding the parts of the market that now require:

- heavy compliance
- network scale
- large sales teams
- large consumer acquisition budgets

## Final verdict

**Absolute best route now:**

**Start as a productized B2B mapping + normalization service, delivered through a customer-run biomarker normalization toolkit, using no live PHI whenever possible.**

That is the best balance of:

- market need
- competitive position
- launch speed
- compliance risk
- budget discipline

If this works, you can later expand in one of two directions:

1. hosted B2B normalization API, once revenue can fund HIPAA/SOC2 work
2. vertical clinic / longevity tooling, once repeated workflows are clear
