# Verification Gate

This is the completion gate for implementation work.

The rule is simple:

**No implementation is complete until it passes a context-derived functionality review, not just unit or standard tests.**

**The verification for a slice must be created on the spot from that slice's actual context.**

## Principle

Verification must be derived from the actual change:

- files touched
- product surfaces changed
- user-visible flows affected
- backend services affected
- integrations affected
- data transformations affected
- failure modes introduced

That means the verification plan is **not** a static checklist.

It must be inferred from context each time.

Static reusable docs may define safety expectations, but they do **not** define the actual test plan for a change.

## Required Verification Modes

Depending on the change, the verification plan must include the relevant mix of:

- backend behavior validation
- API contract validation
- database or persistence validation
- integration validation
- frontend rendering validation
- real click-through flow validation
- upload / input / form behavior validation
- parser / transformation / normalization validation
- regression validation on previously working behavior
- error-path validation
- empty-state validation
- permission / auth validation
- mobile / responsive validation when UI changes are involved

## Minimum Standard

For any implementation, the reviewer or builder must ask:

1. What changed for the user?
2. What changed in the system?
3. What could silently break even if unit tests pass?
4. What realistic flow would a customer actually click through or execute?
5. What failure path would matter most in production?

If the verification plan does not answer those questions, it is incomplete.

## Dynamic Derivation Rules

The verification plan must be inferred from context.

Examples:

- If frontend files changed, require actual UI interaction checks, not just snapshot or component tests.
- If backend or API files changed, require endpoint or service behavior checks with realistic inputs and failure cases.
- If data mapping or normalization code changed, require fixture-based regression checks on known mappings, ambiguous inputs, and unmapped cases.
- If auth, permissions, uploads, or external integrations changed, require end-to-end validation of those specific flows.
- If no UI changed, do not force browser click-throughs just to satisfy process theater.

## Per-Slice Rule

For every phase and every addition:

- create a new change record
- derive a fresh verification plan from that record
- execute tests and functional checks chosen for that slice
- record the exact commands, flows, results, and residual risk for that slice

Do not rely on a generic preplanned test file as the primary verification artifact.

## Completion Rule

A change can be marked complete only if all of the following are true:

- the verification scope was derived from the actual change context
- the highest-risk user flows were exercised
- the highest-risk backend or data paths were exercised
- critical error paths were exercised
- evidence was recorded
- residual risk was stated explicitly if anything could not be verified

## Anti-Patterns

These do **not** count as sufficient verification on their own:

- unit tests only
- lint only
- build passes only
- static typing only
- screenshot-only frontend review
- API happy-path only
- manual spot-check with no error-path coverage

## Evidence To Record

For each implementation, capture:

- what changed
- why those surfaces were selected for verification
- exact commands run
- exact flows exercised
- pass / fail result per verification mode
- unverified areas
- residual risk

Use [change_record_template.json](/C:/Users/me/Desktop/longevb2b/operating_system/change_record_template.json) as the input to derive the plan.

Store the resulting verification evidence under [project_memory/verifications/](/C:/Users/me/Desktop/longevb2b/project_memory/verifications).
