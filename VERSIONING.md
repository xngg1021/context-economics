# Versioning

Context Economics uses a pre-1.0 semantic milestone scheme.

- `MAJOR` remains `0` while public contracts and evidence interfaces are still evolving.
- `MINOR` marks a coherent research/engineering milestone that changes the public capability surface or experiment contract.
- `PATCH` is reserved for correctness, documentation, provenance, compatibility, or evidence-boundary fixes that do not add a new capability class.

The canonical current version is stored in [`VERSION`](VERSION). Historical milestone identity is recorded in [`CHANGELOG.md`](CHANGELOG.md) with exact merge commits and evidence boundaries. The homepage describes only the current release line; implementation history and review/debug chronology belong in the changelog, provenance, and evidence-boundary documents.

## Milestone map

| Version | Milestone | Merge commit |
| --- | --- | --- |
| `0.6.0` | Secure real-runtime campaign engineering and evidence-boundary closeout | `2aef1e7043273637adff1453d22dafc83d5e0e94` |
| `0.5.0` | Runtime correctness recovery and full experiment runner | `79447daafd365edb228c4864fc630f6265dc6287` |
| `0.4.0` | Runtime telemetry, paired analysis, and adaptive calibration | `1c9afadac48f32bfbd34df5c148d17702d60aaf6` |
| `0.3.0` | Version-pinned runtime experiment contract | `1979c22840559162897ed7d1e48ea5bd2a9153a1` |
| `0.2.0` | L6 Adaptive Context Control | `029b375a21ad81f8d062cf33e37348a82f34b4eb` |
| `0.1.0` | L5 Task Economics, evidence discipline, and model hardening | `1f7a71b6ab930183c5f05c40065149d3839a6e23` |

The 2026-08-19 L0–L3 research snapshot predates this version line and remains historical source material rather than a retroactively tagged release.

## Evidence is not a version number

A higher repository version does not imply a higher evidence class. Each version must separately state the strongest evidence actually reached. In particular, `0.6.0` adds a reviewed and secured real-runtime campaign path, but credential-backed provider A/B and task-economic evidence remain pending until such runs actually occur.
