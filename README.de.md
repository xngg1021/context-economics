# Context Economics

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)

**Context Economics ist ein reproduzierbares Mess-, Experiment- und begrenztes Steuerungsframework für die Ökonomie von LLM-/Agent-Kontext.**

> Weniger Tokens bedeuten nicht automatisch geringere Gesamtkosten. Die relevante Einheit ist die erfolgreich abgeschlossene Aufgabe.

Aktuelle Repository-Version: **0.6.1**. Die vollständige Versionshistorie steht in [`CHANGELOG.md`](CHANGELOG.md), die Versionsregeln in [`VERSIONING.md`](VERSIONING.md). Die Startseite beschreibt nur den aktuellen Produkt- und Forschungsstand; frühere Debug-, Review- und Bauprotokolle gehören nicht hierher.

## Welches Problem löst das Projekt?

Lang laufende Agents tragen Kontext wiederholt mit, cachen ihn, komprimieren ihn, holen ihn erneut, bauen ihn neu auf oder verlieren Teile davon. Eine Strategie kann Input-Tokens reduzieren und trotzdem teurer werden, wenn dadurch mehr Retries, Retrievals, Latenz, Fehler, Cache-Schreibvorgänge oder Task-Fehler entstehen.

Context Economics behandelt Kontext deshalb als Betriebsvermögen mit laufenden Kosten und nicht als reine Tokenzahl. Die Kernentscheidung wird in drei Kostenklassen zerlegt:

```text
Carry Cost
  input bill / cache read-write-storage / prefill / latency / mutation amplification

Transformation Cost
  compression / summarization / indexing / serialization / transformation-induced quality loss

Absence Cost
  reacquisition / retry / tool calls / latency / failure / wrong answer / constraint violation
```

Eine Context-Aktion ist nur dann ökonomisch sinnvoll, wenn ihre erwarteten Gesamtkosten pro Aufgabe niedriger sind als die Alternativen und eine explizite Qualitätsuntergrenze erhalten bleibt.

## Forschungs- und Engineering-Modell mit sieben Layern

| Layer | Bereich |
| --- | --- |
| **L0 Pricing** | Provider-Input/Output, cached reads, cache write/storage, Long-Context-Tiers, Serviceklassen |
| **L1 Serving & KV** | Prefill, KV-/Prefix-Reuse, Cache-Stabilität und Serving-seitige Wiederverwendung |
| **L2 Compression** | Truncation, Summarization, Externalization, RAG, Content-Type-Retention und Transformationsverlust |
| **L3 Harness** | Prompt Assembly, Tool-Schemas, Compaction, Subagents, Repo Maps, Scheduling und Reacquisition |
| **L4 Memory & Profile** | Persistenter Kontext, frozen session snapshots, Scope, Residency-Kosten, Source-/Version-Semantik |
| **L5 Task Economics & Observability** | Provider Bill, Tools, externe Kosten, Latenz, Fehler, Task Success, `cost_per_success` |
| **L6 Adaptive Context Control** | Admission, Residency, Locator, Prefetch, begrenzte Vektorbudgets, Mutation Amplification, Shared Immutable Base |

Context Economics `L0–L6` sind **Layer**. Die `T0–T3` von THM sind unabhängige Memory-Residency-/Access-**Tiers**. Beide Taxonomien bleiben getrennt und tauschen nur Messungen/Verträge in überlappenden Bereichen wie Misses, Locator, Prefetch, Budget und Task Economics aus.

## Was ist heute implementiert?

### Deterministische Modelle und Task Economics

- `model.py`: reproduzierbare Kosten- und Sensitivitätsmodelle einschließlich nichtlinearer Long-Context-Preise.
- `real_model.py`: Replay öffentlicher Fixtures oder bereitgestellter Traces; modellierte Qualitätswerte werden explizit als Proxy bezeichnet.
- `task_economics.py`: aggregiert Run Receipts zu Success, Provider Bill, additiven Kosten, Latenz, Retry, Retrieval/Reacquisition und `cost_per_success`.
- Endliche Grids werden nur als **`lowest-cost point in THIS GRID`** berichtet und nie als globales Optimum bezeichnet.

### Runtime Instrumentation und Experiment Contracts

- `context_runtime.py`: strikte request/tool/context/compression/outcome-Schemas, Collection, Validation, Redaction und Normalization.
- `runtime_experiment.py`: verknüpft L5 Receipts und L6 Telemetrie über exakte run/task/policy-Identitäten und Version Pins.
- `experiment_runner.py`: paired-fixed oder counterbalanced AB/BA mit atomarer Artifact-Publikation.
- `experiment_analysis.py`: Paired Statistics, deterministischer Bootstrap, Coverage und Candidate Gates.
- `controller_calibration.py`: trennt Calibration von Held-out Acceptance.

### Shadow Adaptive Context Control

`adaptive_control.py` bietet deterministische, ausschließlich advisory genutzte Oberflächen für:

- `context_hit / soft_miss / hard_miss / stale_hit / planned_retrieval / prefetch` Telemetrie;
- Miss-Kosten und Counterfactual Value;
- resource-bounded exact 0/1 Admission/Residency Packing;
- Locator-Token Economics;
- Anti-Self-Training-Prefetch-Metriken;
- begrenztes Vektor-Budget-Feedback;
- Context Mutation Amplification;
- Immutable Shared Base + Scoped Delta Economics.

Es werden keine Production-Einstellungen für Provider, Harness, Budget, Cache oder Compression automatisch verändert.

### Real-Provider Campaign Engineering

0.6.x stellt einen abgesicherten Pfad für reale Provider-Experimente bereit:

- native Parser/Executors für OpenAI Chat Completions und Anthropic Messages;
- eingefrorene Smoke-/Pilot-/Train-/Holdout-Campaigns mit öffentlichen Tasks;
- exact dated model preflight;
- Bindung von Pricing, Tasks, Policy, Scorer sowie Source Commit/Tree;
- trusted isolated credentialed bootstrap, der Source und Campaign vor der Key-Übergabe validiert;
- unveränderliche Records für abgebrochene Campaigns und validierte Partial Telemetry;
- Offline-Verifier für externe Attestation-Referenzen.

Der geprüfte Credential-Pfad unterstützt derzeit nur den reviewten POSIX-Deployment-Weg. Nicht unterstützte Plattformen failen geschlossen statt Source-Integrity-Prüfungen abzuschwächen.

### Hermes Component Replay und Retention Fixtures

Das Repository enthält exact-source/hash-pinned Replay ausgewählter Hermes-Komponenten sowie deterministische Retention-/Reacquisition-Fixtures. Diese belegen strukturelles Verhalten, aber **keinen vollständigen Hermes-`compress()`-Lauf und keine reale Modellqualität**.

## Aktueller Evidence-Status

| Frage | Status |
| --- | --- |
| Deterministische Kosten-/Accounting-/Contract-Tests | **Implementiert und CI-validiert** |
| Local HTTP Contract E2E | **Implementiert** |
| OpenAI / Anthropic native Adapter | **Fixture-tested** |
| Credential-backed Smoke / Pilot / Holdout | **Im öffentlichen Evidence-Set noch nicht ausgeführt** |
| Request-level observed monetary bill | **Nicht etabliert**; Schätzungen bleiben als estimated markiert |
| Real L6 Train/Holdout Calibration | **Nicht etabliert** |
| Real Cache × Compression Factorial | **Nicht etabliert** |
| Full Hermes Compressor + Host Prompt Replay | **Unvollständig** |
| Independent external trust root | **Nicht provisioniert** |
| `evidence_eligible` / Promotion | **False** |
| Automatische Production Mutation | **Disabled** |

Die aktuelle öffentliche Evidence-Grenze liegt bei Simulation / deterministic contract E2E plus exact-source component trace-replay. Details: [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) und [`PROVENANCE.md`](PROVENANCE.md).

## Quick Start

```bash
python model.py
python real_model.py --fixture fixtures/sample_sessions.json

python task_economics.py \
  --receipts fixtures/run_receipts.json \
  --control no-compression \
  --treatment aggressive-compression

python experiment_runner.py --local-demo --output-root artifacts
```

Version-pinned Joint Contract prüfen:

```bash
python runtime_experiment.py \
  --manifest artifacts/local-e2e/manifest.json \
  --receipts artifacts/local-e2e/l5-receipts.json \
  --events artifacts/local-e2e/l6-events.json \
  --require-complete
```

Real-Provider-Smoke vorbereiten, ohne Credentials in CLI oder Repository abzulegen:

```bash
python runtime_campaign.py prepare \
  --provider openai \
  --revision gpt-4.1-mini-2025-04-14 \
  --pricing pricing/official-20260907-runtime-stage.json \
  --output artifacts/staged-smoke \
  --experiment-id runtime-smoke-UNIQUE \
  --split smoke \
  --count 2
```

Credentialed Execution muss dem geprüften Trusted-Bootstrap-Verfahren in [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) folgen. API Keys gehören nicht in Issues, Kommandoargumente, Commits oder Experiment-Artefakte.

## Experimentdisziplin

Für einen interpretierbaren Vergleich bleiben Task, Model, Revision, Harness, Scorer und Task Set konstant; pro Experiment wird nur eine Context Policy verändert.

Formal Campaigns verlangen, soweit anwendbar:

- exaktes Control/Treatment Pairing;
- counterbalanced AB/BA;
- frozen policy und frozen task set;
- Trennung von Calibration und Held-out Acceptance;
- explizites `observed` vs. `estimated` Billing;
- gleichzeitige Berichterstattung von Cost und Task Success/Score;
- Erhalt von Retry, Reacquisition, Latenz und Failure;
- keine Promotion allein durch Caller-Declared Evidence.

`performance_candidate`, structural readiness, independently authenticated evidence und production promotion sind getrennte Zustände.

## Kernziel

```text
J(policy) =
    E[task_value]
  - E[provider/cache bill
      + tool cost
      + external cost
      + latency cost
      + failure cost]
```

`reacquisition` und `retry` können als überlappende Attribution-Subsets verfolgt werden; sie werden im additiven Ledger nicht doppelt gezählt.

Falls Task Value nicht monetarisiert werden kann, sollten mindestens folgende Größen nebeneinander berichtet werden:

```text
success_rate
 task_score
 provider_bill
 total_cost
 cost_per_success
 p50/p95/p99 wall latency
 input/output/cached tokens
 tool/retrieval/reacquisition/retry counts
 compression count
 context miss/stale metrics
 prefetch coverage/pollution
```

## Repository Guide

| Dokument / Modul | Zweck |
| --- | --- |
| [`CHANGELOG.md`](CHANGELOG.md) | Versionshistorie; alte Bau-/Review-/Debug-Chronologie gehört hierher |
| [`VERSIONING.md`](VERSIONING.md) | Versionspolitik und Milestone Map |
| [`PROVENANCE.md`](PROVENANCE.md) | Evidence Classes, Source Identity, Provenance |
| [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) | Exakte 0.6.x Closeout-Grenze |
| [`RUNTIME-INSTRUMENTATION.md`](RUNTIME-INSTRUMENTATION.md) | Canonical Runtime Telemetry |
| [`RUNTIME-EXPERIMENT-CONTRACT.md`](RUNTIME-EXPERIMENT-CONTRACT.md) | Version-pinned Experiment Contract |
| [`EXPERIMENT-ACCEPTANCE.md`](EXPERIMENT-ACCEPTANCE.md) | Statistical/Evidence Acceptance |
| [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) | Provider Campaign und Security Boundaries |
| [`RESEARCH-ADDENDUM-2026-09-07.md`](RESEARCH-ADDENDUM-2026-09-07.md) | Datierte Forschungs-/Quellenupdates |
| `L0-pricing.md` … `L6-adaptive-context-control.md` | Layer-spezifische Details |
| `context_runtime.py` | Event Collection/Normalization |
| `task_economics.py` | Task-Level Cost Ledger |
| `adaptive_control.py` | Deterministic Shadow Control |
| `experiment_runner.py` | Paired Experiment Orchestration |
| `runtime_campaign.py` | Frozen Real-Provider Campaign |
| `trusted_runtime_bootstrap.py` | Isolated Credential Boundary |

## Projektgrenzen

Context Economics ist keine Memory Database, keine Compressor-Implementierung und kein neuer Agent Harness. Es misst, vergleicht und bewertet **Context Policies externer Systeme**.

Hermes, Claude Code, Codex, Gemini CLI, OpenAI Agents, LangGraph, THM und andere Systeme können Forschungsobjekte sein. Dokumentierte Forschung bedeutet jedoch nicht automatisch, dass ein Live Adapter existiert; dafür müssen Code und explizite Validation vorhanden sein.

Normale Hermes Mid-Session-Memory-Writes persistieren auf Disk, schreiben aber den bereits **frozen** System-Prompt-Snapshot der laufenden Session nicht neu. Cache-Effekte müssen deshalb aus dem tatsächlichen serialisierten Runtime-Verhalten beobachtet werden.

## Validation

Der 0.6.0 Engineering Milestone bestand nach dem Merge die vollständige Python-3.11-/3.13-Validation-Matrix. 0.6.1 ist ein Productization-Patch für Homepage, Versionshistorie und Lokalisierung und muss denselben CI-Gates genügen.

## Versionshistorie

Die Homepage zeigt nur die aktuelle Release-Linie. Detaillierte Änderungen, PR-Zuordnung, Review Findings, Forward Fixes und Evidence-Boundary-Änderungen stehen in [`CHANGELOG.md`](CHANGELOG.md).

Aktuelle Version: **0.6.1**.

---

Context Economics ist weiterhin Research Software vor 1.0. Eine Versionsnummer ersetzt niemals die Evidence Class.
