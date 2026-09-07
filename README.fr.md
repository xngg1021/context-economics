# Context Economics

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)

**Context Economics est un cadre reproductible de mesure, d’expérimentation et de contrôle borné pour étudier l’économie du contexte des LLM et des agents.**

> Réduire les tokens ne signifie pas forcément réduire le coût total. L’unité pertinente est la tâche réussie.

Version actuelle du dépôt : **0.6.1**. L’historique détaillé est dans [`CHANGELOG.md`](CHANGELOG.md) et la politique de versionnement dans [`VERSIONING.md`](VERSIONING.md). La page d’accueil décrit uniquement l’état actuel du produit et de la recherche ; les anciens journaux de debug, de review et de chantier sont déplacés vers les documents historiques appropriés.

## Quel problème ce projet traite-t-il ?

Un agent de longue durée transporte, met en cache, compresse, récupère, reconstruit et parfois perd du contexte. Une politique peut réduire fortement les input tokens tout en augmentant le coût total si elle provoque davantage de retries, de recherches, de latence, d’échecs, d’écritures de cache ou d’erreurs de tâche.

Context Economics traite donc le contexte comme un actif opérationnel avec un coût continu, et non comme un simple nombre de tokens. La décision centrale se décompose en trois familles de coûts :

```text
Carry Cost
  input bill / cache read-write-storage / prefill / latency / mutation amplification

Transformation Cost
  compression / summarization / indexing / serialization / transformation-induced quality loss

Absence Cost
  reacquisition / retry / tool calls / latency / failure / wrong answer / constraint violation
```

Une action sur le contexte n’est économiquement justifiée que si son coût total attendu par tâche est inférieur à celui des alternatives, sous une contrainte explicite de qualité minimale.

## Modèle de recherche et d’ingénierie en sept Layers

| Layer | Périmètre |
| --- | --- |
| **L0 Pricing** | Tarification provider input/output, cached read, cache write/storage, long-context tiers, classes de service |
| **L1 Serving & KV** | Prefill, KV/prefix reuse, stabilité du cache, réutilisation côté serving |
| **L2 Compression** | Truncation, résumé, externalisation, RAG, rétention par type de contenu et pertes de transformation |
| **L3 Harness** | Prompt assembly, tool schemas, compaction, subagents, repo maps, scheduling et reacquisition |
| **L4 Memory & Profile** | Contexte persistant, frozen session snapshots, scope, coût de résidence, sémantique source/version |
| **L5 Task Economics & Observability** | Provider bill, outils, coûts externes, latence, échec, task success, `cost_per_success` |
| **L6 Adaptive Context Control** | Admission, residency, locator, prefetch, budgets vectoriels bornés, mutation amplification, shared immutable base |

Les `L0–L6` de Context Economics sont des **Layers**. Les `T0–T3` de THM sont des **Tiers** indépendants de résidence/accès mémoire. Les taxonomies restent séparées ; seuls les contrats et mesures qui se recoupent — miss, locator, prefetch, budget, task economics — peuvent être échangés.

## Ce qui est implémenté aujourd’hui

### Modèles déterministes et Task Economics

- `model.py` : modèles reproductibles de coût et de sensibilité, y compris la tarification non linéaire du long contexte.
- `real_model.py` : replay de fixtures publiques ou de traces fournies ; les sorties dépendant d’hypothèses restent explicitement des proxies.
- `task_economics.py` : agrégation des run receipts en success, provider bill, coût additif, latence, retry, retrieval/reacquisition et `cost_per_success`.
- Les grilles finies sont décrites uniquement comme **`lowest-cost point in THIS GRID`**, jamais comme un optimum global.

### Runtime instrumentation et contrats d’expérience

- `context_runtime.py` : schémas stricts request/tool/context/compression/outcome, collecte, validation, redaction et normalisation.
- `runtime_experiment.py` : jointure des receipts L5 et de la télémétrie L6 sous des identités exactes run/task/policy et des versions figées.
- `experiment_runner.py` : expériences paired-fixed ou counterbalanced AB/BA et publication atomique des artifacts.
- `experiment_analysis.py` : statistiques appariées, bootstrap déterministe, coverage et candidate gates.
- `controller_calibration.py` : séparation entre calibration et held-out acceptance.

### Shadow Adaptive Context Control

`adaptive_control.py` fournit des surfaces déterministes, uniquement advisory, pour :

- la télémétrie `context_hit / soft_miss / hard_miss / stale_hit / planned_retrieval / prefetch` ;
- miss cost et counterfactual value ;
- exact 0/1 admission/residency packing avec limites de ressources ;
- locator-token economics ;
- métriques de speculative prefetch sans auto-apprentissage ;
- bounded vector budget feedback ;
- context mutation amplification ;
- immutable shared base + scoped delta economics.

Aucun réglage production de provider, harness, budget, cache ou compression n’est modifié automatiquement.

### Real-provider campaign engineering

La ligne 0.6.x ajoute une voie sécurisée pour les expériences sur des providers réels :

- parsers/executors natifs OpenAI Chat Completions et Anthropic Messages ;
- campagnes publiques frozen smoke / pilot / train / holdout ;
- exact dated model preflight ;
- liaison des pricing, tasks, policy, scorer et source commit/tree ;
- trusted isolated credentialed bootstrap validant source et campaign avant de transmettre la clé provider ;
- enregistrements immuables des campagnes interrompues et de la partial telemetry validée ;
- offline external-reference attestation verifier.

Le chemin credential de confiance prend actuellement en charge le deployment POSIX reviewé ; les plateformes non prises en charge fail closed au lieu d’affaiblir les contrôles d’intégrité de source.

### Hermes component replay et retention fixtures

Le dépôt contient un replay exact-source/hash-pinned de composants Hermes sélectionnés ainsi que des fixtures déterministes de retention/reacquisition. Elles prouvent des propriétés structurelles, **pas un exécution complète de Hermes `compress()` ni la qualité d’un modèle réel**.

## État actuel des preuves

| Question | État |
| --- | --- |
| Tests déterministes de coût/accounting/contract | **Implémentés et validés par CI** |
| Local HTTP contract E2E | **Implémenté** |
| Adapters natifs OpenAI / Anthropic | **Fixture-tested** |
| Smoke / pilot / holdout credential-backed | **Pas encore exécutés dans l’evidence public** |
| Request-level observed monetary bill | **Non établi** ; les estimations restent marquées estimated |
| Real L6 train/holdout calibration | **Non établie** |
| Real cache × compression factorial | **Non établi** |
| Full Hermes compressor + host prompt replay | **Incomplet** |
| Independent external trust root | **Non provisionné** |
| `evidence_eligible` / promotion | **False** |
| Automatic production mutation | **Disabled** |

Le plafond actuel des preuves publiques est simulation / deterministic contract E2E + exact-source component trace-replay. Voir [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) et [`PROVENANCE.md`](PROVENANCE.md).

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

Vérifier le joint contract version-pinned :

```bash
python runtime_experiment.py \
  --manifest artifacts/local-e2e/manifest.json \
  --receipts artifacts/local-e2e/l5-receipts.json \
  --events artifacts/local-e2e/l6-events.json \
  --require-complete
```

Préparer un real-provider smoke sans mettre les credentials dans la ligne de commande ou le dépôt :

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

Toute exécution credentialed doit suivre la procédure trusted-bootstrap décrite dans [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md). Ne placez jamais une API key dans une issue, un argument CLI, un commit ou un artifact d’expérience.

## Discipline expérimentale

Pour une comparaison interprétable, task, model, revision, harness, scorer et task set restent fixes ; une seule context policy change à la fois.

Une formal campaign exige, lorsque c’est applicable :

- un appariement control/treatment exact ;
- un ordre counterbalanced AB/BA ;
- une frozen policy et un frozen task set ;
- la séparation calibration / held-out acceptance ;
- un statut explicite `observed` ou `estimated` pour le billing ;
- un reporting conjoint du coût et du task success/score ;
- la conservation des retry, reacquisition, latency et failure ;
- aucune promotion fondée uniquement sur une déclaration du caller.

`performance_candidate`, structural readiness, independently authenticated evidence et production promotion sont des états distincts.

## Objectif central

```text
J(policy) =
    E[task_value]
  - E[provider/cache bill
      + tool cost
      + external cost
      + latency cost
      + failure cost]
```

`reacquisition` et `retry` peuvent être suivis comme attribution subsets qui se recouvrent, mais ne sont pas double-comptés dans le ledger additif.

Si task value ne peut pas être monétisé, il faut au minimum publier en parallèle :

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

## Guide du dépôt

| Document / module | Rôle |
| --- | --- |
| [`CHANGELOG.md`](CHANGELOG.md) | Historique version par version ; la chronologie Review/debug n’est plus sur la homepage |
| [`VERSIONING.md`](VERSIONING.md) | Politique de version et milestone map |
| [`PROVENANCE.md`](PROVENANCE.md) | Evidence classes, source identity, provenance |
| [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) | Frontière actuelle 0.6.x et lacunes empiriques restantes |
| [`RUNTIME-INSTRUMENTATION.md`](RUNTIME-INSTRUMENTATION.md) | Télémétrie runtime canonique |
| [`RUNTIME-EXPERIMENT-CONTRACT.md`](RUNTIME-EXPERIMENT-CONTRACT.md) | Contrat d’expérience version-pinned |
| [`EXPERIMENT-ACCEPTANCE.md`](EXPERIMENT-ACCEPTANCE.md) | Acceptance statistique/evidence |
| [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) | Campaign provider et frontières de sécurité |
| [`RESEARCH-ADDENDUM-2026-09-07.md`](RESEARCH-ADDENDUM-2026-09-07.md) | Mises à jour datées de recherche/sources |
| `L0-pricing.md` … `L6-adaptive-context-control.md` | Détails par Layer |
| `context_runtime.py` | Event collection/normalization |
| `task_economics.py` | Task-level cost ledger |
| `adaptive_control.py` | Deterministic shadow control |
| `experiment_runner.py` | Paired experiment orchestration |
| `runtime_campaign.py` | Frozen real-provider campaign |
| `trusted_runtime_bootstrap.py` | Isolated credential boundary |

## Limites du projet

Context Economics n’est ni une memory database, ni un compressor, ni un nouveau Agent harness. Il sert à **mesurer, comparer et évaluer les context policies de systèmes externes**.

Hermes, Claude Code, Codex, Gemini CLI, OpenAI Agents, LangGraph, THM ou d’autres systèmes peuvent être étudiés, mais une étude documentaire ne signifie pas qu’un live adapter existe. Une capability n’est considérée implémentée que si le code et sa validation explicite sont présents.

Un ordinary Hermes mid-session memory write persiste sur disque mais ne réécrit pas le system-prompt snapshot déjà **frozen** de la session courante. Les effets de cache doivent donc être observés dans le comportement runtime sérialisé réel.

## Validation

La surface d’ingénierie standard-library prise en charge est validée sur Python 3.11 et 3.13. Les identités CI, Reviews et chronologies d’acceptance propres à chaque version sont conservées dans [`CHANGELOG.md`](CHANGELOG.md), pas sur la homepage.

## Historique des versions

La homepage ne montre que la ligne actuelle. Les changements détaillés, PR mappings, Review findings, forward fixes et évolutions d’evidence boundary sont centralisés dans [`CHANGELOG.md`](CHANGELOG.md).

Version actuelle : **0.6.1**.

---

Context Economics reste un logiciel de recherche pré-1.0. Un numéro de version ne remplace jamais une evidence class.
