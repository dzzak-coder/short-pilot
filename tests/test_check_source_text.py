"""Offline CLI contract for the source-text hygiene tool used in CI."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "check_source_text.py"
NARRATION = (
    "La pyramide de Khéops, ou grande pyramide de Gizeh, est un monument "
    "construit par les Égyptiens de l'Antiquité."
)


class CheckSourceTextTests(unittest.TestCase):
    def test_file_mode_is_offline_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            source.write_text(NARRATION, encoding="utf-8")
            before = source.read_bytes()
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--file", str(source)],
                cwd=directory, capture_output=True, text=True, encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("lignes d'interface: 0", result.stdout)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual([path.name for path in Path(directory).iterdir()], [source.name])

    def test_file_mode_detects_joined_toolbar(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            source.write_text("modifier - modifier le code - modifier Wikidata " + NARRATION,
                              encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--file", str(source)],
                cwd=directory, capture_output=True, text=True, encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=False,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("lignes d'interface: 1", result.stdout)


if __name__ == "__main__":
    unittest.main()
