# Versioning

Context Economics uses a pre-1.0 semantic milestone scheme.

- `MAJOR` remains `0` while public contracts and evidence interfaces are still evolving.
- `MINOR` marks a coherent research/engineering milestone that changes the public capability surface or experiment contract.
- `PATCH` is reserved for correctness, documentation, provenance, compatibility, localization, or evidence-boundary fixes that do not add a new capability class.

The canonical current version is stored in [`VERSION`](VERSION). Historical milestone identity is recorded in [`CHANGELOG.md`](CHANGELOG.md). The homepage describes only the current release line; implementation history, review findings, debug chronology, and exact closeout evidence belong in the changelog, provenance, and evidence-boundary documents.

## Current line

Current version: **0.6.1**.

`0.6.1` is a documentation/productization patch: it establishes a current-facing multilingual homepage family, moves historical change chronology out of the homepage, and formalizes versioned release notes. It does **not** upgrade the evidence class or runtime capability surface of 0.6.0.

## Milestone map

| Version | Milestone | Accepted anchor |
| --- | --- | --- |
| `0.6.1` | Productized homepage, full localization, and versioned release-history structure | docs-only successor; final PR/merge identity is recorded in the release closeout |
| `0.6.0` | Secure real-runtime campaign engineering and evidence-boundary closeout | merge `2aef1e7043273637adff1453d22dafc83d5e0e94` |
| `0.5.0` | Runtime correctness recovery and full experiment runner | merge `79447daafd365edb228c4864fc630f6265dc6287` |
| `0.4.0` | Runtime telemetry, paired analysis, and adaptive calibration | merge `1c9afadac48f32bfbd34df5c148d17702d60aaf6` |
| `0.3.0` | Version-pinned runtime experiment contract | merge `1979c22840559162897ed7d1e48ea5bd2a9153a1` |
| `0.2.0` | L6 Adaptive Context Control | merge `029b375a21ad81f8d062cf33e37348a82f34b4eb` |
| `0.1.0` | L5 Task Economics, evidence discipline, and model hardening | merge `1f7a71b6ab930183c5f05c40065149d3839a6e23` |

The 2026-08-19 L0–L3 research snapshot predates this version line and remains historical source material rather than a retroactively tagged release.

## Evidence is not a version number

A higher repository version does not imply a higher evidence class. Each release must separately state the strongest evidence actually reached.

In particular, the 0.6.x line includes a reviewed and secured real-runtime campaign path, but credential-backed provider A/B, request-level observed monetary evidence, real L6 calibration, and task-economic promotion remain pending until such experiments actually occur.

## Release hygiene

For future milestones:

1. advance `VERSION` only for an intentional public milestone or patch;
2. update `CHANGELOG.md` with user-facing changes, exact PR/merge identity when available, and the evidence boundary;
3. keep detailed security/debug review chronology in release notes, `PROVENANCE.md`, or the relevant evidence-boundary document rather than the homepage;
4. synchronize all maintained README languages before acceptance;
5. run repository CI on the exact final head and again after merge for substantive engineering releases.
