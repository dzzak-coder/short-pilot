"""Test mock reproductible du diagnostic de planification — aucun service, aucune image.

Ce test ne contacte ni Ollama ni ComfyUI. Il fabrique un faux paquet `core/` dans un
dossier temporaire, y copie le script, et vérifie son comportement par sous-processus.

Exécution (à la racine du dépôt ShortPilot) :

    .venv\\Scripts\\python.exe -m unittest tests.test_diagnose_line_planning -v

ou directement :

    .venv\\Scripts\\python.exe tests\\test_diagnose_line_planning.py

Ce qu'il prouve :
  - les modules sont résolus quel que soit le point d'entrée (racine ou tools/) ;
  - `--dry-run` n'entre JAMAIS dans `text_phase` (sentinelle absente) ;
  - une exécution simulée produit le rapport attendu et un JSON structuré ;
  - les quatre détections fonctionnent : ancrage répété, prompts identiques,
    personnes non demandées, continuité rompue ;
  - l'absence de fichier d'entrée est refusée hors `--dry-run`.

Ce qu'il ne prouve PAS : que le vrai planificateur produit ces sorties. Il valide le
câblage et l'affichage, pas la qualité des plans.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT_NAME = "diagnose_line_planning.py"

# Chemin du script testé : par défaut tools/, surchargeable par variable d'environnement.
_HERE = Path(__file__).resolve().parent
_CANDIDATES = [
    _HERE.parent / "tools" / SCRIPT_NAME,
    _HERE.parent / SCRIPT_NAME,
    _HERE / SCRIPT_NAME,
]
SCRIPT_PATH = next((p for p in _CANDIDATES if p.exists()), _CANDIDATES[0])

STUB_INIT = ""

# Faux content : reproduit les quatre défauts que le diagnostic doit savoir montrer.
STUB_CONTENT = '''
"""Faux planificateur pour le test. Aucun acces reseau."""
F = lambda **k: k


def visual_plan_bundle(scenes, *, title="", niche="", language=""):
    plans, controls = [], []
    for i, _scene in enumerate(scenes):
        if i == 0:
            facts = [
                F(category="subject", entity="timer", source_span="minuteur", english="a timer"),
                F(category="color", entity="timer", source_span="rouge", english="red timer"),
            ]
            plans.append("A realistic documentary photograph of a red timer.")
            controls.append({"kind": "explicit", "subject_type": "object",
                             "human_mode": "forbidden", "still_life": True,
                             "source_facts": facts, "reason": "stub"})
        elif i == 1:
            facts = [
                F(category="subject", entity="timer", source_span="minuteur",
                  english="a chronometer device"),
                F(category="secondary", entity="planner", source_span="planning",
                  english="a planner"),
            ]
            plans.append("A realistic documentary photograph of a chronometer device.")
            controls.append({"kind": "explicit", "subject_type": "person",
                             "human_mode": "required", "still_life": False,
                             "source_facts": facts, "reason": "stub"})
        else:
            plans.append(plans[0])
            controls.append({"kind": "contextual", "subject_type": "object",
                             "human_mode": "forbidden", "still_life": True,
                             "source_facts": [F(category="subject", entity="timer",
                                                source_span="minuteur", english="a timer")],
                             "reason": "continuite"})
    return {"visual_plans": plans, "visual_controls": controls,
            "visual_plan_fingerprint": "stub-fingerprint"}
'''

# Faux local_resources : écrit une sentinelle si text_phase est réellement ouvert.
STUB_RESOURCES = '''
"""Faux coordinateur. Toute entree dans text_phase est tracee sur disque."""
import os
from contextlib import contextmanager

SENTINEL = os.environ.get("TEXT_PHASE_SENTINEL")


@contextmanager
def text_phase(*, model=None, **kwargs):
    if SENTINEL:
        with open(SENTINEL, "a", encoding="utf-8") as handle:
            handle.write(str(model) + "\\n")
    yield
'''

SCRIPT_FIXTURE = {
    "title": "Le minuteur rouge",
    "niche": "productivite",
    "language": "fr",
    "scenes": [
        "Un minuteur rouge pose sur un bureau en bois.",
        "Le minuteur indique combien de temps reste avant la fin de la pause.",
        "Abonne-toi pour d'autres astuces.",
    ],
}


class DiagnosticMockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCRIPT_PATH.exists():
            raise unittest.SkipTest(f"script introuvable : {SCRIPT_PATH}")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="diag_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        core = self.tmp / "core"
        core.mkdir()
        (core / "__init__.py").write_text(STUB_INIT, encoding="utf-8")
        (core / "content.py").write_text(textwrap.dedent(STUB_CONTENT), encoding="utf-8")
        (core / "local_resources.py").write_text(textwrap.dedent(STUB_RESOURCES),
                                                 encoding="utf-8")

        tools = self.tmp / "tools"
        tools.mkdir()
        self.script = tools / SCRIPT_NAME
        shutil.copy2(SCRIPT_PATH, self.script)

        self.script_json = self.tmp / "script.json"
        self.script_json.write_text(json.dumps(SCRIPT_FIXTURE, ensure_ascii=False),
                                    encoding="utf-8")
        self.sentinel = self.tmp / "text_phase_called.txt"

    def _run(self, *args, cwd=None):
        env_sentinel = str(self.sentinel)
        return subprocess.run(
            [sys.executable, str(self.script), *args],
            cwd=str(cwd or self.tmp), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
            env={
                **__import__("os").environ,
                "PYTHONIOENCODING": "utf-8",
                "TEXT_PHASE_SENTINEL": env_sentinel,
            },
        )

    # --- câblage -----------------------------------------------------------

    def test_dry_run_without_input_file_contacts_nothing(self):
        result = self._run("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("core.content", result.stdout)
        self.assertIn("core.local_resources", result.stdout)
        self.assertFalse(self.sentinel.exists(),
                         "text_phase a ete ouvert pendant --dry-run")

    def test_dry_run_from_tools_directory_also_resolves(self):
        result = self._run("--dry-run", cwd=self.script.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("core.content", result.stdout)
        self.assertFalse(self.sentinel.exists())

    def test_dry_run_with_input_file_reports_line_count(self):
        result = self._run(str(self.script_json), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("lignes", result.stdout)
        self.assertFalse(self.sentinel.exists())

    def test_missing_input_file_outside_dry_run_is_refused(self):
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requis", (result.stdout + result.stderr).lower())

    # --- exécution simulée -------------------------------------------------

    def test_full_run_produces_report(self):
        result = self._run(str(self.script_json))
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        self.assertIn("Diagnostic de planification visuelle".lower(), out.lower())
        self.assertIn("LIGNE 1", out)
        self.assertIn("SYNTHÈSE", out)
        self.assertIn("ne prouve RIEN sur l'image", out)

    def test_full_run_enters_text_phase_exactly_once(self):
        self._run(str(self.script_json))
        self.assertTrue(self.sentinel.exists(), "text_phase n'a pas ete ouvert")
        calls = self.sentinel.read_text(encoding="utf-8").split()
        self.assertEqual(len(calls), 1, f"appels text_phase : {calls}")

    def test_detects_duplicated_anchor_and_identical_prompts(self):
        out = self._run(str(self.script_json)).stdout
        self.assertIn("Ancrages répétés", out)
        self.assertIn("timer", out)
        self.assertIn("PROMPTS COMPILÉS IDENTIQUES", out)
        self.assertIn("lignes 1, 3", out)

    def test_detects_unrequested_people(self):
        out = self._run(str(self.script_json)).stdout
        self.assertIn("PERSONNES NON DEMANDÉES", out)
        self.assertIn("lignes 2", out)

    def test_detects_broken_continuity(self):
        out = self._run(str(self.script_json)).stdout
        self.assertIn("CONTINUITÉ ROMPUE", out)
        self.assertIn("a chronometer device", out)

    # --- JSON --------------------------------------------------------------

    def test_out_writes_structured_json(self):
        target = self.tmp / "rapports" / "diag.json"
        result = self._run(str(self.script_json), "--out", str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.exists(), "le JSON n'a pas ete ecrit")
        payload = json.loads(target.read_text(encoding="utf-8"))
        for key in ("plans", "controls", "analysis", "script", "fingerprint"):
            self.assertIn(key, payload)
        analysis = payload["analysis"]
        self.assertEqual(analysis["scene_count"], 3)
        self.assertIn("identical_prompt_groups", analysis)
        self.assertNotIn("identical_image_groups", analysis,
                         "l'ancienne cle trompeuse ne doit plus exister")
        self.assertEqual(analysis["person_rows_suspect"], [1])
        self.assertEqual(analysis["distinct_anchors"], 1)

    def test_json_only_prints_valid_json(self):
        result = self._run(str(self.script_json), "--json-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["analysis"]["scene_count"], 3)

    # --- garde-fou ---------------------------------------------------------

    def test_script_never_calls_prompt_endpoint(self):
        """Le texte du script ne doit contenir aucun envoi a /prompt."""
        source = self.script.read_text(encoding="utf-8")
        for forbidden in ('"/prompt"', "'/prompt'", "/prompt\""):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
