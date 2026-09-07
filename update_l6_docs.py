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


def update_readme() -> None:
    text = read("README.md")
    text = replace_once(
        text,
        "> 当前研究对象：LLM / agent 在输入、缓存、压缩、工具、记忆、重取、重试、延迟与任务成功之间的成本—质量权衡。",
        "> 当前研究对象：LLM / agent 在输入、缓存、压缩、工具、记忆、重取、重试、延迟、任务成功与自适应上下文控制之间的成本—质量权衡。",
        "README current object",
    )
    text = replace_once(text, "## 1. 六层结构", "## 1. 七层结构", "README layer count")
    text = replace_once(
        text,
        """L5 Task Economics & Observability
   billed cost + tool/reacquisition/retry/latency/failure + task success
```""",
        """L5 Task Economics & Observability
   billed cost + tool/reacquisition/retry/latency/failure + task success

L6 Adaptive Context Control
   admission / residency / locator / prefetch / vector budget feedback /
   mutation amplification / shared immutable base
```""",
        "README L6 layer",
    )
    l6_section = r'''## 9. `adaptive_control.py`：L6 变成可运行 shadow control plane

L6 将前面各层的观测量变成一组**有界、非自动执行**的 context-control 建议。它不使用 THM 的 T0–T3 作为自己的层级；Context Economics 的 `L0–L6` 是分析/控制 Layer，THM 的 `T0–T3` 是独立 memory residency/access Tier。

当前控制面覆盖：

```text
context_hit / soft_miss / hard_miss / stale_hit
admission / residency
locator-token economics
speculative prefetch
vector budget feedback
context mutation amplification
immutable shared base + private delta
```

其中核心控制向量是：

```text
u_t = (
  B_history,
  B_retrieval,
  B_memory,
  B_tools,
  B_repo_map,
  B_prefetch,
  r_compression_retained
)
```

运行 synthetic reference：

```bash
python adaptive_control.py telemetry \
  --events fixtures/context_access_events.json

python adaptive_control.py residency \
  --events fixtures/context_access_events.json \
  --catalog fixtures/context_assets.json \
  --budget 14 \
  --min-demand-tasks 4 \
  --min-asset-demands 2

python adaptive_control.py prefetch \
  --events fixtures/context_access_events.json \
  --catalog fixtures/context_assets.json \
  --seed repo-map \
  --budget 4

python adaptive_control.py budget \
  --state fixtures/context_budget_state.json
```

完整定义与边界见 `L6-adaptive-context-control.md`。当前 L6 的证据等级仍是 `analytic + simulation/contract`；没有真实 held-out runtime/task A/B 时，不把 shadow proposal 称为生产最优，也不自动写回 harness/provider 配置。

'''
    text = replace_once(
        text,
        "## 9. 可复现性与 CI",
        l6_section + "## 10. 可复现性与 CI",
        "README L6 section",
    )
    text = replace_once(
        text,
        """python task_economics.py \
  --receipts fixtures/run_receipts.json \
  --control no-compression \
  --treatment aggressive-compression
```""",
        """python task_economics.py \
  --receipts fixtures/run_receipts.json \
  --control no-compression \
  --treatment aggressive-compression
python adaptive_control.py telemetry \
  --events fixtures/context_access_events.json
python adaptive_control.py budget \
  --state fixtures/context_budget_state.json
```""",
        "README reproducibility",
    )
    write("README.md", text)


def update_l5() -> None:
    text = read("L5-task-economics.md")
    insert = r'''### 当前 receipt parser 的故障安全边界

`task_economics.py` 现在把上面的 schema 当作数据合同，而不是宽松 JSON：

- `success` 必须是真正 boolean，字符串 `"false"` 不会被 Python truthiness 错算为成功；
- 未知字段直接失败，避免 `provider_bil_usd` 之类 typo 被静默丢弃；
- `run_id` 必须唯一；
- token、call、cost、latency 必须是有限且非负的对应类型；
- 当前 schema 下 `cached_input_tokens <= input_tokens`；
- `reacquisition_calls <= retrieval_calls`；
- pairing report 显式报告 missing arm、duplicate arm 与 paired coverage，不把未配对任务静默藏掉。

聚合结果同时给出 token/cache、task score、p50/p95 TTFT/wall time 和 failure-class 计数。CLI 输出仍标记为 `observed-run-receipts-not-causal-inference`：严格 schema 只能提高数据完整性，不能替代实验设计。

'''
    text = replace_once(
        text,
        "## 五、reacquisition 怎么定义",
        insert + "## 五、reacquisition 怎么定义",
        "L5 parser note",
    )
    write("L5-task-economics.md", text)


def update_changelog() -> None:
    text = read("CHANGELOG.md")
    insert = '''## Unreleased — L6 Adaptive Context Control

### L5 accounting hardening

- receipt ingestion now rejects ambiguous booleans, unknown fields, duplicate run IDs, non-finite/negative accounting fields, impossible cached-token counts and reacquisition counts above retrieval counts;
- policy aggregation now reports token/cache totals, task scores, latency percentiles and failure classes;
- paired treatment/control output now exposes pairing coverage plus missing/duplicate-arm exclusions.

### L6 control plane

- adds `adaptive_control.py` with generic `context_hit / soft_miss / hard_miss / stale_hit` telemetry;
- adds evidence-gated admission/residency with explicit counterfactual-value handling and bounded exact 0/1 packing;
- adds locator-token economics, co-demand speculative prefetch with anti-self-training, bounded vector context-budget feedback, context mutation amplification and immutable shared-base economics;
- adds synthetic L6 fixtures, contract tests and CI smoke coverage;
- preserves the hard boundary between Context Economics `L0-L6` Layers and THM `T0-T3` memory Tiers; no production policy mutation is enabled.

'''
    text = replace_once(text, "# Changelog\n\n", "# Changelog\n\n" + insert, "CHANGELOG L6")
    write("CHANGELOG.md", text)


def update_provenance() -> None:
    text = read("PROVENANCE.md")
    text = replace_once(
        text,
        "- hardening branch: `chat/context-economics-hardening-20260907`\n",
        "- hardening branch: `chat/context-economics-hardening-20260907`\n"
        "- merged hardening commit: `1f7a71b6ab930183c5f05c40065149d3839a6e23`\n"
        "- L6 successor branch: `chat/context-l6-adaptive-control-20260907`\n",
        "provenance successor",
    )
    insert = r'''## L6 implementation evidence boundary

`adaptive_control.py` is a deterministic standard-library **reference/control implementation**. Its public fixtures are synthetic. Current claims are limited to analytic, simulation and contract behavior:

- event/schema validation;
- miss taxonomy and explicit avoidability;
- evidence-gated admission/residency;
- locator/prefetch/budget arithmetic;
- bounded exact packing;
- anti-self-training prefetch semantics;
- mutation/share accounting.

It has not yet been promoted to `runtime-A/B` or `task-economic` evidence. In particular, the repository does not claim that any proposed context budget, prefetch or admission policy improves a real provider/harness workload until version-pinned held-out tasks produce the corresponding L5 receipts.

Context Economics `L0-L6` and THM `T0-T3` are independent taxonomies. Cross-repository measurements may be exchanged, but neither hierarchy is rewritten as the other.

'''
    text = replace_once(text, "## Reproduction", insert + "## Reproduction", "provenance L6")
    text = replace_once(
        text,
        """python model.py
python real_model.py --fixture fixtures/sample_sessions.json
```""",
        """python model.py
python real_model.py --fixture fixtures/sample_sessions.json
python task_economics.py --receipts fixtures/run_receipts.json --control no-compression --treatment aggressive-compression
python adaptive_control.py telemetry --events fixtures/context_access_events.json
python adaptive_control.py budget --state fixtures/context_budget_state.json
```""",
        "provenance reproduction",
    )
    write("PROVENANCE.md", text)


def update_docs_test() -> None:
    text = read("tests/test_docs.py")
    methods = r'''
    def test_l6_control_layer_exists_and_stays_distinct_from_thm_tiers(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        l6 = (ROOT / "L6-adaptive-context-control.md").read_text(encoding="utf-8")
        self.assertIn("L6 Adaptive Context Control", readme)
        self.assertIn("adaptive_control.py", readme)
        self.assertIn("L6 不是 THM 的 T0–T3", l6)
        self.assertIn("Admission、Residency、Prefetch 与 Budget Control", l6)
        self.assertTrue((ROOT / "adaptive_control.py").is_file())

    def test_l6_public_fixtures_are_synthetic(self):
        for name in (
            "context_access_events.json",
            "context_assets.json",
            "context_budget_state.json",
        ):
            text = (ROOT / "fixtures" / name).read_text(encoding="utf-8")
            self.assertIn("Synthetic", text)

    def test_l6_docs_preserve_shadow_acceptance_boundary(self):
        l6 = (ROOT / "L6-adaptive-context-control.md").read_text(encoding="utf-8")
        provenance = (ROOT / "PROVENANCE.md").read_text(encoding="utf-8")
        self.assertIn("shadow/advisory only", l6)
        self.assertIn("runtime-A/B", l6)
        self.assertIn("task-economic", provenance)
'''
    text = replace_once(
        text,
        '\n\nif __name__ == "__main__":',
        methods + '\n\nif __name__ == "__main__":',
        "docs tests L6",
    )
    write("tests/test_docs.py", text)


def update_workflow() -> None:
    text = read(".github/workflows/validate.yml")
    anchor = '''      - name: Task economics smoke test
        run: >-
          python task_economics.py
          --receipts fixtures/run_receipts.json
          --control no-compression
          --treatment aggressive-compression
'''
    replacement = anchor + '''      - name: L6 telemetry smoke test
        run: python adaptive_control.py telemetry --events fixtures/context_access_events.json
      - name: L6 residency smoke test
        run: >-
          python adaptive_control.py residency
          --events fixtures/context_access_events.json
          --catalog fixtures/context_assets.json
          --budget 14
          --min-demand-tasks 4
          --min-asset-demands 2
      - name: L6 prefetch smoke test
        run: >-
          python adaptive_control.py prefetch
          --events fixtures/context_access_events.json
          --catalog fixtures/context_assets.json
          --seed repo-map
          --budget 4
          --min-seed-demands 3
          --min-joint-tasks 2
      - name: L6 budget smoke test
        run: python adaptive_control.py budget --state fixtures/context_budget_state.json
'''
    text = replace_once(text, anchor, replacement, "workflow L6")
    write(".github/workflows/validate.yml", text)


def main() -> None:
    update_readme()
    update_l5()
    update_changelog()
    update_provenance()
    update_docs_test()
    update_workflow()


if __name__ == "__main__":
    main()
