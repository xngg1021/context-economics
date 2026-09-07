# Context Economics

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)

**Context Economics es un marco reproducible de medición, experimentación y control acotado para estudiar la economía del contexto en LLM y agentes.**

> Reducir tokens no equivale necesariamente a reducir el coste total. La unidad que importa es la tarea completada con éxito.

Versión actual del repositorio: **0.6.1**. El historial completo está en [`CHANGELOG.md`](CHANGELOG.md) y la política de versionado en [`VERSIONING.md`](VERSIONING.md). La portada describe únicamente la superficie actual del producto/investigación; los antiguos registros de debug, review y construcción se mantienen fuera de la página principal.

## ¿Qué problema resuelve?

Los agentes de larga duración transportan, almacenan en caché, comprimen, vuelven a adquirir, reconstruyen y a veces pierden contexto. Una política puede ahorrar muchos input tokens y aun así ser más cara si aumenta retries, retrieval, latencia, fallos, cache writes o errores de tarea.

Context Economics trata el contexto como un activo operativo con coste continuo, no como un simple número de tokens. La decisión central se descompone en tres familias de coste:

```text
Carry Cost
  input bill / cache read-write-storage / prefill / latency / mutation amplification

Transformation Cost
  compression / summarization / indexing / serialization / transformation-induced quality loss

Absence Cost
  reacquisition / retry / tool calls / latency / failure / wrong answer / constraint violation
```

Una acción sobre el contexto solo se considera económicamente justificada si reduce el coste total esperado de la tarea frente a las alternativas y mantiene un umbral explícito de calidad.

## Modelo de investigación e ingeniería en siete Layers

| Layer | Alcance |
| --- | --- |
| **L0 Pricing** | Precios input/output del provider, cached read, cache write/storage, long-context tiers, clases de servicio |
| **L1 Serving & KV** | Prefill, KV/prefix reuse, estabilidad del cache, reutilización del lado de serving |
| **L2 Compression** | Truncation, resumen, externalización, RAG, retención por tipo de contenido y pérdida de transformación |
| **L3 Harness** | Prompt assembly, tool schemas, compaction, subagents, repo maps, scheduling y reacquisition |
| **L4 Memory & Profile** | Contexto persistente, frozen session snapshots, scope, residency cost, semántica source/version |
| **L5 Task Economics & Observability** | Provider bill, herramientas, costes externos, latencia, fallos, task success, `cost_per_success` |
| **L6 Adaptive Context Control** | Admission, residency, locator, prefetch, presupuestos vectoriales acotados, mutation amplification, shared immutable base |

Los `L0–L6` de Context Economics son **Layers**. Los `T0–T3` de THM son **Tiers** independientes de residency/access de memoria. Las taxonomías no se fusionan; solo intercambian métricas/contratos en áreas comunes como miss, locator, prefetch, budget y task economics.

## ¿Qué está implementado hoy?

### Modelos deterministas y Task Economics

- `model.py`: modelos reproducibles de costes y sensibilidad, incluido pricing no lineal para long context.
- `real_model.py`: replay de fixtures públicas o traces proporcionadas; las salidas basadas en supuestos se etiquetan como proxy.
- `task_economics.py`: agrega run receipts en success, provider bill, coste aditivo, latencia, retry, retrieval/reacquisition y `cost_per_success`.
- Las grids finitas se describen únicamente como **`lowest-cost point in THIS GRID`**, nunca como óptimo global.

### Runtime instrumentation y experiment contracts

- `context_runtime.py`: schemas estrictos request/tool/context/compression/outcome, collection, validation, redaction y normalization.
- `runtime_experiment.py`: une L5 receipts y L6 telemetry bajo identidad exacta run/task/policy y version pins.
- `experiment_runner.py`: ejecuta paired-fixed o counterbalanced AB/BA y publica artifacts de forma atómica.
- `experiment_analysis.py`: estadísticas pareadas, bootstrap determinista, coverage y candidate gates.
- `controller_calibration.py`: separa calibration de held-out acceptance.

### Shadow Adaptive Context Control

`adaptive_control.py` ofrece superficies deterministas y solo advisory para:

- telemetría `context_hit / soft_miss / hard_miss / stale_hit / planned_retrieval / prefetch`;
- miss cost y counterfactual value;
- exact 0/1 admission/residency packing con límites de recursos;
- locator-token economics;
- métricas de speculative prefetch sin autoentrenamiento;
- bounded vector budget feedback;
- context mutation amplification;
- immutable shared base + scoped delta economics.

No modifica automáticamente ninguna configuración production de provider, harness, budget, cache o compression.

### Real-provider campaign engineering

La línea 0.6.x incorpora una ruta controlada para experimentos con providers reales:

- parsers/executors nativos de OpenAI Chat Completions y Anthropic Messages;
- campañas públicas frozen smoke / pilot / train / holdout;
- exact dated model preflight;
- binding de pricing, tasks, policy, scorer y source commit/tree;
- trusted isolated credentialed bootstrap que valida source y campaign antes de entregar la clave del provider;
- registros inmutables de campañas abortadas y partial telemetry validada;
- offline external-reference attestation verifier.

La ruta trusted credential soporta actualmente el deployment POSIX reviewado. Las plataformas no soportadas fail closed en lugar de debilitar las comprobaciones de source integrity.

### Hermes component replay y retention fixtures

El repositorio incluye exact-source/hash-pinned replay de componentes Hermes seleccionados y fixtures deterministas de retention/reacquisition. Esto aporta evidencia estructural, **no una ejecución completa de Hermes `compress()` ni evidencia de calidad de un modelo real**.

## Estado actual de la evidencia

| Pregunta | Estado |
| --- | --- |
| Tests deterministas de cost/accounting/contract | **Implementados y validados por CI** |
| Local HTTP contract E2E | **Implementado** |
| Adapters nativos OpenAI / Anthropic | **Fixture-tested** |
| Credential-backed smoke / pilot / holdout | **Aún no ejecutados en la evidencia pública** |
| Request-level observed monetary bill | **No establecido**; las estimaciones siguen marcadas estimated |
| Real L6 train/holdout calibration | **No establecido** |
| Real cache × compression factorial | **No establecido** |
| Full Hermes compressor + host prompt replay | **Incompleto** |
| Independent external trust root | **No provisionado** |
| `evidence_eligible` / promotion | **False** |
| Automatic production mutation | **Disabled** |

El techo de evidencia pública actual es simulation / deterministic contract E2E + exact-source component trace-replay. Véanse [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) y [`PROVENANCE.md`](PROVENANCE.md).

## Quick start

```bash
python model.py
python real_model.py --fixture fixtures/sample_sessions.json

python task_economics.py \
  --receipts fixtures/run_receipts.json \
  --control no-compression \
  --treatment aggressive-compression

python experiment_runner.py --local-demo --output-root artifacts
```

Validar el joint contract version-pinned:

```bash
python runtime_experiment.py \
  --manifest artifacts/local-e2e/manifest.json \
  --receipts artifacts/local-e2e/l5-receipts.json \
  --events artifacts/local-e2e/l6-events.json \
  --require-complete
```

Preparar una campaña real-provider smoke sin colocar credentials en CLI o repositorio:

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

La ejecución credentialed debe seguir el procedimiento trusted-bootstrap de [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md). No coloque API keys en issues, argumentos de comando, commits ni artifacts de experimento.

## Disciplina experimental

Una comparación interpretable mantiene fijos task, model, revision, harness, scorer y task set, cambiando una sola context policy cada vez.

Una formal campaign exige, cuando corresponda:

- exact control/treatment pairing;
- counterbalanced AB/BA;
- frozen policy y frozen task set;
- separación entre calibration y held-out acceptance;
- billing explícito `observed` frente a `estimated`;
- reporting conjunto de cost y task success/score;
- conservación de retry, reacquisition, latency y failure;
- ninguna promotion basada solo en caller-declared evidence.

`performance_candidate`, structural readiness, independently authenticated evidence y production promotion son estados distintos.

## Objetivo central

```text
J(policy) =
    E[task_value]
  - E[provider/cache bill
      + tool cost
      + external cost
      + latency cost
      + failure cost]
```

`reacquisition` y `retry` pueden seguirse como attribution subsets solapados, pero no se cuentan dos veces en el ledger aditivo.

Si task value no puede monetizarse, se deben reportar al menos en paralelo:

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

## Guía del repositorio

| Documento / módulo | Finalidad |
| --- | --- |
| [`CHANGELOG.md`](CHANGELOG.md) | Historia por versión; la cronología de Review/debug antiguo va aquí, no en la homepage |
| [`VERSIONING.md`](VERSIONING.md) | Política de versiones y milestone map |
| [`PROVENANCE.md`](PROVENANCE.md) | Evidence classes, source identity y provenance |
| [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) | Boundary actual de 0.6.x y gaps empíricos restantes |
| [`RUNTIME-INSTRUMENTATION.md`](RUNTIME-INSTRUMENTATION.md) | Canonical runtime telemetry |
| [`RUNTIME-EXPERIMENT-CONTRACT.md`](RUNTIME-EXPERIMENT-CONTRACT.md) | Version-pinned experiment contract |
| [`EXPERIMENT-ACCEPTANCE.md`](EXPERIMENT-ACCEPTANCE.md) | Statistical/evidence acceptance |
| [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) | Provider campaign y security boundaries |
| [`RESEARCH-ADDENDUM-2026-09-07.md`](RESEARCH-ADDENDUM-2026-09-07.md) | Actualizaciones fechadas de investigación/fuentes |
| `L0-pricing.md` … `L6-adaptive-context-control.md` | Detalle por Layer |
| `context_runtime.py` | Event collection/normalization |
| `task_economics.py` | Task-level cost ledger |
| `adaptive_control.py` | Deterministic shadow control |
| `experiment_runner.py` | Paired experiment orchestration |
| `runtime_campaign.py` | Frozen real-provider campaign |
| `trusted_runtime_bootstrap.py` | Isolated credential boundary |

## Límites del proyecto

Context Economics no es una memory database, una implementación de compressor ni un nuevo Agent harness. Su función es **medir, comparar y evaluar context policies de sistemas externos**.

Hermes, Claude Code, Codex, Gemini CLI, OpenAI Agents, LangGraph, THM y otros sistemas pueden ser objeto de investigación. Que un sistema aparezca en la documentación no significa que exista un live adapter; solo se considera implementado cuando existen código y validación explícita.

Un ordinary Hermes mid-session memory write persiste en disco, pero no reescribe el system-prompt snapshot ya **frozen** de la sesión actual. Los efectos sobre cache deben observarse en el comportamiento runtime serializado real.

## Validación

La superficie de ingeniería standard-library soportada se valida en Python 3.11 y 3.13. Las identidades concretas de CI, Reviews y cronología de acceptance de cada versión se mantienen en [`CHANGELOG.md`](CHANGELOG.md), no en la homepage.

## Historial de versiones

La homepage muestra solo la línea actual. Los cambios detallados, PR mappings, Review findings, forward fixes y cambios de evidence boundary se mantienen en [`CHANGELOG.md`](CHANGELOG.md).

Versión actual: **0.6.1**.

---

Context Economics sigue siendo research software pre-1.0. Un número de versión nunca sustituye a la evidence class.
