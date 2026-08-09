from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epistemic_ci.cli import main


class CLITestCase(unittest.TestCase):
    def test_missing_config_writes_fail_closed_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("builtins.print"):
                returncode = main(
                    [
                        "run",
                        "--root",
                        str(root),
                        "--config",
                        "missing.json",
                        "--output",
                        "result.json",
                    ]
                )
            self.assertEqual(returncode, 1)
            result = json.loads((root / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["checks"][0]["name"], "configuration")


if __name__ == "__main__":
    unittest.main()
