import json
import tempfile
import unittest
from pathlib import Path

import real_model


FIXTURE = {
    "schema_version": 1,
    "sessions": [
        {
            "profile": "test",
            "sid": "s1",
            "model": "kimi-k3",
            "api_call_count": 8,
            "input_tokens": 100000,
            "cache_read_tokens": 200000,
            "compacted": 0,
            "messages": [
                {"role": "user", "chars": 6000},
                {"role": "assistant", "chars": 8000},
                {"role": "tool", "chars": 22000},
                {"role": "user", "chars": 6200},
                {"role": "assistant", "chars": 8200},
                {"role": "tool", "chars": 23000},
                {"role": "user", "chars": 6100},
                {"role": "assistant", "chars": 8100},
                {"role": "tool", "chars": 24000},
                {"role": "user", "chars": 5900},
                {"role": "assistant", "chars": 7900},
                {"role": "tool", "chars": 21000},
                {"role": "user", "chars": 6300},
                {"role": "assistant", "chars": 8300},
                {"role": "tool", "chars": 25000},
                {"role": "user", "chars": 6000},
                {"role": "assistant", "chars": 8000},
                {"role": "tool", "chars": 22000},
                {"role": "user", "chars": 6200},
                {"role": "assistant", "chars": 8150},
                {"role": "tool", "chars": 23500},
                {"role": "user", "chars": 6100},
                {"role": "assistant", "chars": 8050},
            ],
        }
    ],
}


class RealModelTests(unittest.TestCase):
    def test_portable_fixture_loader(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.json"
            path.write_text(json.dumps(FIXTURE), encoding="utf-8")
            sessions = real_model.load_sessions_from_fixture(path)
        self.assertEqual(len(sessions), 1)
        self.assertAlmostEqual(sessions[0]["rho"], 2 / 3, places=6)

    def test_threshold_parser(self):
        self.assertEqual(real_model.parse_thresholds("none,0.12,0.5"), [None, 0.12, 0.5])

    def test_proxy_labels_are_explicit(self):
        session = real_model.load_sessions_from_fixture(
            Path(__file__).parents[1] / "fixtures" / "sample_sessions.json"
        )[0]
        result = real_model.replay(session, 2.3, 0.12)
        self.assertIn("proxy_final_recall", result)
        self.assertIn("proxy_ux_failures", result)
        self.assertNotIn("recall", result)

    def test_none_means_no_compression(self):
        session = real_model.load_sessions_from_fixture(
            Path(__file__).parents[1] / "fixtures" / "sample_sessions.json"
        )[0]
        result = real_model.replay(session, 2.3, None)
        self.assertEqual(result["n_cmp"], 0)


if __name__ == "__main__":
    unittest.main()
