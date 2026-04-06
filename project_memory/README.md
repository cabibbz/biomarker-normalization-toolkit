# Project Memory

This folder stores compressed but detailed handoff context.

## Purpose

At each 10% progress milestone, record:

- what was completed
- what decisions were locked
- what was verified
- what remains open
- exactly where the next session should resume

## Files

- [manifest.json](/C:/Users/me/Desktop/longevb2b/project_memory/manifest.json): machine-readable milestone index
- [current_context.md](/C:/Users/me/Desktop/longevb2b/project_memory/current_context.md): latest compressed handoff state
- [roadmap.md](/C:/Users/me/Desktop/longevb2b/project_memory/roadmap.md): 10-step progress map
- [verifications/](/C:/Users/me/Desktop/longevb2b/project_memory/verifications): per-slice derived verification records
- [checkpoints/](/C:/Users/me/Desktop/longevb2b/project_memory/checkpoints): milestone summaries

## Rule

If work crosses a new 10% milestone and no checkpoint is recorded, the work is not operationally complete.

If the verified work has not also been committed and pushed after the checkpoint, the handoff is incomplete.

If a slice has no dedicated verification record, the verification process is incomplete.
