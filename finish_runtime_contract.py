#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def write(name: str, text: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    (ROOT / name).write_text(text, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing anchor for {label}")
    return text.replace(old, new, 1)


def patch_runtime_code() -> None:
    text = read("runtime_experiment.py")
    text = replace_once(
        text,
        "import argparse\nimport json\n",
        "import argparse\nimport json\nimport math\nimport re\nfrom datetime import datetime\n",
        "runtime imports",
    )
    text = replace_once(
        text,
        '    "harness_revision",\n    "input_tokens",',
        '    "harness_revision",\n    "started_at",\n    "ended_at",\n    "task_score",\n    "input_tokens",',
        "runtime explicit timing fields",
    )
    text = replace_once(
        text,
        '    "provider_bill_usd",\n    "tool_calls",',
        '    "provider_bill_usd",\n    "tool_cost_usd",\n    "reacquisition_cost_usd",\n    "retry_cost_usd",\n    "latency_cost_usd",\n    "failure_cost_usd",\n    "tool_calls",',
        "runtime explicit cost fields",
    )
    text = replace_once(
        text,
        '    "compression_calls",\n    "wall_time_ms",\n}',
        '    "compression_calls",\n    "ttft_ms",\n    "wall_time_ms",\n    "failure_class",\n}',
        "runtime explicit latency/failure fields",
    )
    helper_anchor = '''def _string_list(value: object, name: str) -> tuple[str, ...]:\n'''
    helpers = '''def _git_sha(value: object, name: str) -> str:\n    text = _text(value, name)\n    if re.fullmatch(r"[0-9a-f]{40}", text) is None:\n        raise ExperimentError(f"{name} must be an exact 40-character lowercase Git SHA")\n    return text\n\n\ndef _timestamp(value: object, name: str) -> datetime:\n    text = _text(value, name)\n    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text\n    try:\n        parsed = datetime.fromisoformat(normalized)\n    except ValueError as exc:\n        raise ExperimentError(f"{name} must be an ISO-8601 timestamp") from exc\n    if parsed.tzinfo is None or parsed.utcoffset() is None:\n        raise ExperimentError(f"{name} must include an explicit timezone offset")\n    return parsed\n\n\n'''
    text = replace_once(text, helper_anchor, helpers + helper_anchor, "runtime helpers")
    text = replace_once(
        text,
        'repository_commit=_text(row["repository_commit"], "repository_commit"),',
        'repository_commit=_git_sha(row["repository_commit"], "repository_commit"),',
        "manifest exact commit",
    )
    pin_anchor = '''    for name, wanted in expected.items():\n        actual = getattr(receipt, name)\n        if actual != wanted:\n            raise ExperimentError(\n                f"run {receipt.run_id}: {name} mismatch: {actual!r} != {wanted!r}"\n            )\n'''
    pin_new = pin_anchor + '''\n    started = _timestamp(receipt.started_at, f"run {receipt.run_id}.started_at")\n    ended = _timestamp(receipt.ended_at, f"run {receipt.run_id}.ended_at")\n    if ended < started:\n        raise ExperimentError(f"run {receipt.run_id}: ended_at precedes started_at")\n'''
    text = replace_once(text, pin_anchor, pin_new, "receipt timestamp validation")
    parser_anchor = '''def build_parser() -> argparse.ArgumentParser:\n'''
    json_helper = '''def _json_safe(value: object) -> object:\n    if isinstance(value, float) and not math.isfinite(value):\n        return None\n    if isinstance(value, dict):\n        return {key: _json_safe(item) for key, item in value.items()}\n    if isinstance(value, list):\n        return [_json_safe(item) for item in value]\n    return value\n\n\n'''
    text = replace_once(text, parser_anchor, json_helper + parser_anchor, "runtime json safe")
    text = replace_once(
        text,
        'print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))',
        'print(json.dumps(_json_safe(report), ensure_ascii=False, indent=2, allow_nan=False))',
        "runtime json output",
    )
    write("runtime_experiment.py", text)


def patch_runtime_fixtures() -> None:
    import json
    path = ROOT / "fixtures" / "runtime_ab_receipts.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    schedule = {
        "c-a": ("2026-09-07T00:00:00+00:00", "2026-09-07T00:00:10+00:00"),
        "c-b": ("2026-09-07T00:01:00+00:00", "2026-09-07T00:01:10.500000+00:00"),
        "t-a": ("2026-09-07T00:02:00+00:00", "2026-09-07T00:02:09.800000+00:00"),
        "t-b": ("2026-09-07T00:03:00+00:00", "2026-09-07T00:03:09.900000+00:00"),
    }
    for row in payload["runs"]:
        row["started_at"], row["ended_at"] = schedule[row["run_id"]]
        row["tool_cost_usd"] = 0.0
        row["reacquisition_cost_usd"] = 0.0
        row["retry_cost_usd"] = 0.0
        row["latency_cost_usd"] = 0.0
        row["failure_cost_usd"] = 0.0
        row["failure_class"] = None
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def patch_runtime_tests() -> None:
    text = read("tests/test_runtime_experiment.py")
    anchor = '''    def test_receipt_revision_mismatch_fails(self):\n'''
    methods = '''    def test_zero_success_report_serializes_without_nonstandard_infinity(self):\n        failed = [\n            rexp.ReceiptRecord(\n                replace(row.receipt, success=False, task_score=0.0),\n                row.explicit_fields,\n            )\n            for row in self.receipts\n        ]\n        report = rexp.build_joint_report(\n            self.manifest, failed, self.events, require_complete=True\n        )\n        safe = rexp._json_safe(report)\n        encoded = json.dumps(safe, allow_nan=False)\n        self.assertIn('"cost_per_success_usd": null', encoded)\n\n    def test_timestamp_order_and_timezone_are_validated(self):\n        broken = list(self.receipts)\n        broken[0] = rexp.ReceiptRecord(\n            replace(\n                broken[0].receipt,\n                started_at="2026-09-07T00:00:10+00:00",\n                ended_at="2026-09-07T00:00:00+00:00",\n            ),\n            broken[0].explicit_fields,\n        )\n        with self.assertRaises(rexp.ExperimentError):\n            rexp.build_joint_report(self.manifest, broken, self.events)\n\n        naive = list(self.receipts)\n        naive[0] = rexp.ReceiptRecord(\n            replace(naive[0].receipt, started_at="2026-09-07T00:00:00"),\n            naive[0].explicit_fields,\n        )\n        with self.assertRaises(rexp.ExperimentError):\n            rexp.build_joint_report(self.manifest, naive, self.events)\n\n'''
    text = replace_once(text, anchor, methods + anchor, "runtime new tests")
    write("tests/test_runtime_experiment.py", text)


def create_contract_doc() -> None:
    text = '''# Version-Pinned Runtime Experiment Contract\n\n> Added: 2026-09-07. Executable contract: `runtime_experiment.py`.\n> Current public fixtures are **synthetic contract fixtures**. This file does not claim that a real provider/harness A/B has already been executed.\n\n## 1. Purpose\n\nL5 records task economics and L6 records context-access/control telemetry. A real policy comparison is only interpretable if both streams refer to the same run, task, arm and runtime identity. This contract makes that join explicit.\n\nThe validator consumes three files:\n\n```text\nmanifest\n  -> experiment identity + provider/model/harness/repository/task/policy pins\n\nrun receipts\n  -> L5 success, billed tokens/cost, tool/retrieval/reacquisition/retry/latency\n\ncontext events\n  -> L6 hit/miss/stale/planned-retrieval/prefetch telemetry linked to run_id\n```\n\n## 2. Version pins\n\nEvery manifest must explicitly pin:\n\n```text\nprovider\nmodel\nmodel_revision\nharness_revision\nrepository_commit\nruntime_environment_ref\ntask_set_ref\npricing_snapshot_ref\npolicy_bundle_ref\ncontrol_policy\ntreatment_policy\nexpected_task_ids\n```\n\n`repository_commit` must be an exact lowercase 40-character Git SHA. Other references are opaque versioned identifiers because different runtimes may use image digests, fixture IDs, release IDs or content-addressed manifests rather than Git.\n\nEach receipt must repeat provider/model/model_revision/harness_revision. A mismatch fails instead of being averaged into the experiment. `started_at` and `ended_at` must be timezone-aware ISO-8601 timestamps and `ended_at >= started_at`.\n\n## 3. Runtime receipts are stricter than generic L5 fixtures\n\nFor this contract, fields that generic `RunReceipt` can default are required to be explicit. The runtime receipt must include:\n\n```text\nrun/task/policy/success/task_score\nprovider/model/model_revision/harness_revision\nstarted_at/ended_at\ninput/cached-input/cache-write/output tokens\nprovider bill\ntool/reacquisition/retry/latency/failure cost components\ntool/retrieval/reacquisition/retry/compression counts\nTTFT/wall time\nfailure_class\n```\n\nZero is allowed when it is an observed or deliberately assigned zero. Missing is not silently converted to zero by the runtime-experiment loader.\n\n## 4. L6 telemetry must be run-linked\n\nEvery context event adds:\n\n```text\nrun_id\npolicy_id\n```\n\nto the normal L6 event contract. The validator checks that:\n\n- `run_id` exists in the receipt set;\n- event `policy_id` equals the receipt arm;\n- event `task_id` equals the receipt task;\n- event IDs remain globally unique.\n\nAn orphan or cross-arm event fails.\n\n## 5. Structural completeness\n\nFor every `expected_task_id`, the contract expects exactly one control and one treatment run. It separately reports:\n\n```text\nmissing_arms\nduplicate_arms\nruns_without_context_events\npaired_coverage\n```\n\n`--require-complete` turns any of these structural gaps into a hard failure.\n\n## 6. Evidence-class boundary\n\nThe manifest contains `declared_evidence_class`:\n\n```text\nsynthetic-contract\ntrace-replay\nruntime-A/B\n```\n\nThis value is a **declaration by the experiment producer**. The parser cannot prove that a provider was contacted, that billing came from a provider invoice, that assignment was randomized, or that task scoring is trustworthy.\n\nLikewise:\n\n```text\nruntime_design_structurally_ready = true\n```\n\nmeans only that the manifest declares `runtime-A/B`, the pairing is structurally complete, and the assignment method is one of `paired-fixed / counterbalanced / randomized`. It is not a causal certificate. Every report therefore includes:\n\n```text\ncausal_claim = "not inferred by this validator"\n```\n\n## 7. Joint report\n\nA successful join returns both evidence streams without collapsing them into one synthetic score:\n\n```text\nby_policy_task_economics\nby_policy_context_telemetry\npaired_task_report\n```\n\nThis preserves the distinction between "the agent missed context" and "the task failed/cost more". Causal interpretation remains an experimental-design step.\n\nIf a policy has zero successes, L5 correctly represents `cost_per_success` as infinity internally. The runtime-contract CLI serializes non-finite derived values as JSON `null` rather than emitting non-standard `Infinity` or crashing.\n\n## 8. Public synthetic reproduction\n\n```bash\npython runtime_experiment.py \\\n  --manifest fixtures/runtime_experiment_manifest.json \\\n  --receipts fixtures/runtime_ab_receipts.json \\\n  --events fixtures/runtime_context_events.json \\\n  --require-complete\n```\n\nThe three public files are labeled synthetic and exist only to test the contract. Their numeric deltas are not product/runtime benchmark results.\n\n## 9. Promotion rule\n\nA future result may be described as a real `runtime-A/B` only when the run producer supplies real version-pinned runtime records and provenance. A stronger `task-economic` claim additionally requires interpretable real task outcomes plus billed cost and interaction/retry/latency accounting.\n\nPassing this parser is necessary data hygiene for that experiment; it is not sufficient evidence that the treatment is better.\n'''
    write("RUNTIME-EXPERIMENT-CONTRACT.md", text)


def patch_readme() -> None:
    text = read("README.md")
    section = '''## 10. `runtime_experiment.py`：version-pinned L5/L6 join contract\n\nL5 receipts 与 L6 context telemetry 现在有独立的运行实验数据合同：`runtime_experiment.py` 要求 experiment manifest 固定 provider/model/model revision/harness revision/repository commit/runtime environment/task set/pricing snapshot/policy bundle，并将每个 L6 event 通过 `run_id + policy_id + task_id` 与 L5 receipt 对齐。\n\n它显式报告 missing/duplicate arms、没有 context events 的 run、paired coverage，并可用 `--require-complete` 把结构不完整直接变成失败。Runtime receipt 中时间戳、token/cache、provider bill、各类成本、interaction counts、TTFT/wall time 等字段必须显式提供，不能靠默认零掩盖缺失。\n\n`declared_evidence_class` 仍只是 experiment producer 的声明。即使报告显示 `runtime_design_structurally_ready=true`，validator 也不会推断 provider 真正被调用、账单真实、任务分配随机或 treatment 具有因果优势；输出固定保留 `causal_claim = not inferred by this validator`。完整合同见 `RUNTIME-EXPERIMENT-CONTRACT.md`。\n\n公开 fixtures 只用于 synthetic contract CI，不能升级为 runtime benchmark。\n\n'''
    text = replace_once(
        text,
        "## 10. 可复现性与 CI",
        section + "## 11. 可复现性与 CI",
        "README runtime section",
    )
    text = replace_once(text, "## 10. 仓库结构", "## 12. 仓库结构", "README structure number")
    text = replace_once(text, "## 11. 当前仍未解决的问题", "## 13. 当前仍未解决的问题", "README unresolved number")
    text = replace_once(
        text,
        "  --treatment aggressive-compression\n```",
        "  --treatment aggressive-compression\npython adaptive_control.py telemetry --events fixtures/context_access_events.json\npython runtime_experiment.py --manifest fixtures/runtime_experiment_manifest.json --receipts fixtures/runtime_ab_receipts.json --events fixtures/runtime_context_events.json --require-complete\n```",
        "README reproduction commands",
    )
    text = replace_once(text, "L5-task-economics.md\n", "L5-task-economics.md\nL6-adaptive-context-control.md\nRUNTIME-EXPERIMENT-CONTRACT.md\n", "README structure docs")
    text = replace_once(text, "task_economics.py\n", "task_economics.py\nadaptive_control.py\nruntime_experiment.py\n", "README structure code")
    text = replace_once(text, "fixtures/run_receipts.json\n", "fixtures/run_receipts.json\nfixtures/context_access_events.json\nfixtures/context_assets.json\nfixtures/context_budget_state.json\nfixtures/runtime_experiment_manifest.json\nfixtures/runtime_ab_receipts.json\nfixtures/runtime_context_events.json\n", "README structure fixtures")
    text = replace_once(text, "tests/test_task_economics.py\n", "tests/test_task_economics.py\ntests/test_adaptive_control.py\ntests/test_runtime_experiment.py\n", "README structure tests")
    text = replace_once(
        text,
        "3. 用真实任务 A/B 校准 quality loss，替换 `real_model.py` 中的 proxy retention curve。\n4. 将 tool/reacquisition/retry/latency 自动写入统一 run receipt，而不是只接受离线 JSON。",
        "3. 用 `runtime_experiment.py` 的 contract 真正执行 version-pinned held-out task A/B，并用真实 task outcome 校准 `real_model.py` 中的 proxy retention curve。\n4. 将 tool/reacquisition/retry/latency 与 L6 context events 自动采集进同一 run，而不是只接受离线 JSON。",
        "README next work",
    )
    write("README.md", text)


def patch_l6() -> None:
    text = read("L6-adaptive-context-control.md")
    old = "下一阶段应使用真实、版本固定的 runtime/task A/B，把 L5 receipts 与 L6 telemetry 接起来，再决定哪些 shadow recommendation 可以升级。"
    new = "`runtime_experiment.py` 现已完成这一步的**结构化数据合同**：它把 version-pinned L5 receipts 与 run-linked L6 telemetry 对齐，并检查 arm completeness，但公开 fixture 仍是 synthetic。下一阶段仍是执行真实、版本固定的 runtime/task A/B，再决定哪些 shadow recommendation 可以升级。详见 [Runtime Experiment Contract](RUNTIME-EXPERIMENT-CONTRACT.md)。"
    text = replace_once(text, old, new, "L6 next stage")
    write("L6-adaptive-context-control.md", text)


def patch_provenance() -> None:
    text = read("PROVENANCE.md")
    section = '''## Runtime experiment contract boundary\n\n`runtime_experiment.py` joins L5 receipts and L6 events under exact experiment pins. The public `runtime_*` fixtures are synthetic and validate only schema/alignment behavior.\n\n`declared_evidence_class` is producer-supplied metadata, not independently verified evidence. `runtime_design_structurally_ready=true` means the declared runtime design has complete arms/run-linked telemetry and an eligible assignment method; it does not prove provider contact, provider billing, randomization, scoring validity or causality. The validator therefore never emits a causal-success claim.\n\nReal runtime promotion still requires external provenance for the version-pinned provider/model/harness/runtime/task execution. See `RUNTIME-EXPERIMENT-CONTRACT.md`.\n\n'''
    text = replace_once(text, "## Reproduction", section + "## Reproduction", "provenance runtime contract")
    text = replace_once(
        text,
        "python adaptive_control.py budget --state fixtures/context_budget_state.json\n```",
        "python adaptive_control.py budget --state fixtures/context_budget_state.json\npython runtime_experiment.py --manifest fixtures/runtime_experiment_manifest.json --receipts fixtures/runtime_ab_receipts.json --events fixtures/runtime_context_events.json --require-complete\n```",
        "provenance runtime command",
    )
    write("PROVENANCE.md", text)


def patch_changelog() -> None:
    text = read("CHANGELOG.md")
    section = '''## Unreleased — Version-Pinned Runtime Experiment Contract\n\n- adds `runtime_experiment.py` to join L5 task-economics receipts with L6 context telemetry by exact run/task/policy identity;\n- pins provider/model/model revision/harness revision/repository commit/runtime environment/task set/pricing snapshot/policy bundle;\n- requires explicit runtime receipt timing/token/cache/cost/interaction/latency/failure fields and timezone-aware ordered timestamps;\n- reports missing/duplicate arms, runs without telemetry and paired coverage, with optional fail-closed `--require-complete`;\n- keeps `declared_evidence_class` as producer metadata and never upgrades structural validity into causal proof;\n- adds synthetic contract fixtures/tests only; no real provider runtime A/B result is claimed.\n\n'''
    text = replace_once(text, "# Changelog\n\n", "# Changelog\n\n" + section, "changelog runtime contract")
    write("CHANGELOG.md", text)


def patch_docs_tests() -> None:
    text = read("tests/test_docs.py")
    methods = '''\n    def test_runtime_experiment_contract_is_linked_and_evidence_bounded(self):\n        readme = (ROOT / "README.md").read_text(encoding="utf-8")\n        path = ROOT / "RUNTIME-EXPERIMENT-CONTRACT.md"\n        self.assertTrue(path.is_file())\n        self.assertIn(path.name, readme)\n        doc = path.read_text(encoding="utf-8")\n        self.assertIn("Version-Pinned Runtime Experiment Contract", doc)\n        self.assertIn("declared_evidence_class", doc)\n        self.assertIn("not sufficient evidence", doc)\n        self.assertIn("causal", doc)\n\n    def test_runtime_experiment_public_fixtures_are_synthetic(self):\n        for name in (\n            "runtime_experiment_manifest.json",\n            "runtime_ab_receipts.json",\n            "runtime_context_events.json",\n        ):\n            text = (ROOT / "fixtures" / name).read_text(encoding="utf-8")\n            self.assertIn("Synthetic", text)\n\n'''
    text = replace_once(text, '\n\nif __name__ == "__main__":', methods + '\n\nif __name__ == "__main__":', "docs runtime tests")
    write("tests/test_docs.py", text)


def main() -> None:
    patch_runtime_code()
    patch_runtime_fixtures()
    patch_runtime_tests()
    create_contract_doc()
    patch_readme()
    patch_l6()
    patch_provenance()
    patch_changelog()
    patch_docs_tests()


if __name__ == "__main__":
    main()
