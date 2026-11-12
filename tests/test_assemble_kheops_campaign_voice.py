import json
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def load_module():
    path = Path(__file__).resolve().parents[1] / "tools" / "assemble_kheops_campaign.py"
    spec = importlib.util.spec_from_file_location("assemble_kheops_campaign", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class AssembleKheopsVoiceTests(unittest.TestCase):
    def test_script_language_must_match_voice_culture_prefix(self):
        mod = load_module()
        with self.assertRaises(ValueError):
            mod.validate_script_voice_language("fr-FR", "en-US")
        with self.assertRaises(ValueError):
            mod.validate_script_voice_language("en-US", "fr-FR")
        self.assertTrue(mod.validate_script_voice_language("fr-FR", "fr-FR"))
        self.assertTrue(mod.validate_script_voice_language("fr", "fr-CA"))

    def test_utf8_accents_roundtrip_to_powershell_payload(self):
        mod = load_module()
        text = "Test accents: é, è, ç, œ — pyramide de Khéops."
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            source = out / "scenes.json"
            blob = json.dumps([text], ensure_ascii=False)
            source.write_text(blob, encoding="utf-8")
            script = (
                "$items = Get-Content -Raw -Encoding UTF8 -LiteralPath '" + str(source).replace("'", "''") + "' | ConvertFrom-Json; "
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "Write-Output ([string]$items[0])"
            )
            import subprocess
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            self.assertEqual(res.returncode, 0, res.stderr or res.stdout)
            got = (res.stdout or "").strip()
            self.assertIn("é, è, ç, œ", got)
            self.assertIn("Khéops", got)

    def test_compute_scene_timings_never_slows_voice_and_derives_from_real_narration(self):
        mod = load_module()
        # voice shorter than min visual slot -> natural speed (1.0), padded by silence, not slowed
        timings = mod.compute_scene_timings([1.0, 5.0], {1: 2, 2: 1})
        self.assertAlmostEqual(timings[0]["slot_duration_seconds"], 6.0, places=3)  # 3s * 2 images
        self.assertAlmostEqual(timings[0]["image_duration_seconds"], 3.0, places=3)
        self.assertEqual(timings[0]["atempo_factor"], 1.0)
        # voice tient dans le créneau -> vitesse naturelle + silence (pas d'accélération artificielle)
        self.assertAlmostEqual(timings[1]["slot_duration_seconds"], 5.3, places=3)
        self.assertEqual(timings[1]["atempo_factor"], 1.0)

    def test_compute_scene_timings_refuses_when_cap_imposes_but_110_insufficient(self):
        mod = load_module()
        # voice very long, 1 image => cap 7s, even atempo 1.10 cannot fit within 7s -> refuse
        with self.assertRaises(mod.AssemblyRefused):
            mod.compute_scene_timings([20.0], {1: 1})


if __name__ == "__main__":
    unittest.main()