import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import hermes_component_replay as h

class SourceBoundaryTests(unittest.TestCase):
    def test_tampered_source_rejected_before_ast_or_execution(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'source.py';p.write_text("raise RuntimeError('MUST NOT EXECUTE')")
            with patch.object(h.ast,'parse') as parse:
                with self.assertRaisesRegex(ValueError,'fingerprint'):h.load(p)
                parse.assert_not_called()
