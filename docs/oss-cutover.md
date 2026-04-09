# OSS Cutover

This document records the shift from the earlier private/open-core state to the public Apache-2.0 repository.

## What Changed

- the package license moved to Apache-2.0
- built-in feature gating and license-key enforcement were removed from the core app
- the CLI and REST API now ship as full-access in the open-source distribution
- internal operating-process directories and consensus tooling were removed from the public repo surface
- the maintainer/community surface was added: contribution docs, governance, support routing, issue templates, release docs

## Why The Cutover Matters

The goal of the public repository is to behave like a normal infrastructure project:

- contributors can inspect the full runtime behavior
- all documented endpoints are available by default
- packaging and CI validate the same product the repo describes

## Migration Notes

If you used an earlier internal or gated build:

- remove assumptions about `X-API-Key` enforcement in the built-in API
- do not expect `tier` fields in API responses
- review any local wrappers that implemented commercial-tier behavior on top of older builds

## What Did Not Change

- the core normalization model remains deterministic and provenance-preserving
- ambiguity handling is still explicit
- deployment-specific authentication, authorization, and compliance controls still belong in the surrounding system
