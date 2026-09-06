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

    def test_task_economics_layer_exists(self):
        l5 = (ROOT / "L5-task-economics.md").read_text(encoding="utf-8")
        self.assertIn("cost_per_success", l5)
        self.assertIn("reacquisition", l5)

    def test_public_replay_fixture_is_synthetic(self):
        fixture = (ROOT / "fixtures" / "sample_sessions.json").read_text(encoding="utf-8")
        self.assertIn("Synthetic, non-private fixture", fixture)


if __name__ == "__main__":
    unittest.main()
