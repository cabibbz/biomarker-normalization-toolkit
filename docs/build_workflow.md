# Build Workflow

This is the operational workflow for all future work in this repo.

## Before Work

1. Read [project_memory/current_context.md](/C:/Users/me/Desktop/longevb2b/project_memory/current_context.md)
2. Review [constraints.md](/C:/Users/me/Desktop/longevb2b/operating_system/constraints.md)
3. If the idea is new, score it with [review_rubric.md](/C:/Users/me/Desktop/longevb2b/operating_system/review_rubric.md)

## During Work

1. State what is being changed
2. Record the changed surfaces
3. Derive a verification plan from actual context
4. Implement
5. Create the phase-specific verification record for that exact slice
6. Run the derived verification, including UI click-through and backend behavior if relevant
7. When the public CLI or packaging surface changes, prefer verifying the installed entry point instead of only `python -m`

## Before Marking Done

1. Confirm relevant verification modes were executed
2. Capture evidence in the slice-specific verification record
3. State residual risk
4. If progress crossed a 10% milestone, record a checkpoint
5. Commit the verified slice
6. Push to `origin/main`

## Resume Rule

Any new session should begin by reading:

1. [project_memory/current_context.md](/C:/Users/me/Desktop/longevb2b/project_memory/current_context.md)
2. the latest checkpoint under [project_memory/checkpoints/](/C:/Users/me/Desktop/longevb2b/project_memory/checkpoints)
3. the active build decision docs under [docs/](/C:/Users/me/Desktop/longevb2b/docs)

## Mandatory Sequence

The required close-out order for any implementation slice is:

1. derive verification scope from actual change context
2. create the slice-specific verification record
3. run verification
4. record checkpoint
5. commit
6. push

If commit and push have not happened, the slice is not fully closed.
