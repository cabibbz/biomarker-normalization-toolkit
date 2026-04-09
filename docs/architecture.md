# Architecture

The toolkit has four main layers:

1. Ingest
   Parses CSV, FHIR, HL7, C-CDA, and Excel into a canonical row structure.

2. Normalization
   Resolves aliases, applies specimen rules, converts units, assigns LOINC, and records provenance.

3. Reporting
   Produces normalized JSON, CSV, Markdown summaries, and optional FHIR bundles.

4. Analysis
   Builds derived metrics, optimal-range summaries, PhenoAge output, and longitudinal comparisons from normalized records.

The core design goal is deterministic behavior with explicit ambiguity handling.
