import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class DocumentationContractTests(unittest.TestCase):
    def test_readme_does_not_claim_grid_endpoint_is_global_optimum(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("θ=0.15（本负载最优）", text)
        self.assertIn("lowest-cost point in THIS GRID", text)

    def test_memory_write_cache_tax_is_not_presented_as_current_fact(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        l4 = (ROOT / "L4-memory-profile.md").read_text(encoding="utf-8")
        self.assertIn("frozen", readme.lower())
        self.assertIn("frozen", l4.lower())
        self.assertNotIn("中途写记忆断缓存前缀", readme)

    def test_task_economics_layer_exists_and_is_executable(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        l5 = (ROOT / "L5-task-economics.md").read_text(encoding="utf-8")
        self.assertIn("cost_per_success", l5)
        self.assertIn("reacquisition", l5)
        self.assertIn("task_economics.py", readme)
        self.assertTrue((ROOT / "task_economics.py").is_file())
        self.assertTrue((ROOT / "fixtures" / "run_receipts.json").is_file())

    def test_research_addendum_is_linked(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        path = ROOT / "RESEARCH-ADDENDUM-2026-09-07.md"
        self.assertTrue(path.is_file())
        self.assertIn(path.name, readme)
        text = path.read_text(encoding="utf-8")
        self.assertIn("ReCache", text)
        self.assertIn("Token Reduction Is Not Cost Reduction", text)

    def test_public_replay_fixture_is_synthetic(self):
        fixture = (ROOT / "fixtures" / "sample_sessions.json").read_text(encoding="utf-8")
        receipts = (ROOT / "fixtures" / "run_receipts.json").read_text(encoding="utf-8")
        self.assertIn("Synthetic, non-private fixture", fixture)
        self.assertIn("Synthetic run receipts", receipts)

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

    def test_runtime_experiment_contract_is_linked_and_evidence_bounded(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        path = ROOT / "RUNTIME-EXPERIMENT-CONTRACT.md"
        self.assertTrue(path.is_file())
        self.assertIn(path.name, readme)
        doc = path.read_text(encoding="utf-8")
        self.assertIn("Version-Pinned Runtime Experiment Contract", doc)
        self.assertIn("declared_evidence_class", doc)
        self.assertIn("not sufficient evidence", doc)
        self.assertIn("causal", doc)

    def test_runtime_experiment_public_fixtures_are_synthetic(self):
        for name in (
            "runtime_experiment_manifest.json",
            "runtime_ab_receipts.json",
            "runtime_context_events.json",
        ):
            text = (ROOT / "fixtures" / name).read_text(encoding="utf-8")
            self.assertIn("Synthetic", text)

    def test_productized_localized_homepages_are_complete_and_current(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(version, "0.6.1")
        names = (
            "README.md",
            "README.zh-CN.md",
            "README.zh-TW.md",
            "README.ja.md",
            "README.ko.md",
            "README.de.md",
            "README.fr.md",
            "README.es.md",
        )
        language_links = (
            "README.md",
            "README.zh-CN.md",
            "README.zh-TW.md",
            "README.ja.md",
            "README.ko.md",
            "README.de.md",
            "README.fr.md",
            "README.es.md",
        )
        for name in names:
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertGreater(len(text), 6000, name)
            self.assertIn("0.6.1", text, name)
            self.assertIn("L0", text, name)
            self.assertIn("L6 Adaptive Context Control", text, name)
            self.assertIn("cost_per_success", text, name)
            self.assertIn("CHANGELOG.md", text, name)
            self.assertIn("VERSIONING.md", text, name)
            self.assertIn("FINAL-EVIDENCE-BOUNDARY.md", text, name)
            for link in language_links:
                self.assertIn(link, text, f"{name} missing {link}")

    def test_changelog_uses_versioned_release_sections(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        for version in ("0.6.1", "0.6.0", "0.5.0", "0.4.0", "0.3.0", "0.2.0", "0.1.0"):
            self.assertIn(f"## {version}", changelog)
        self.assertNotIn("## Unreleased —", changelog)
        self.assertTrue((ROOT / "VERSIONING.md").is_file())


if __name__ == "__main__":
    unittest.main()
