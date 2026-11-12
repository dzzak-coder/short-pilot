import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT / "outputs" / "kheops_campaign_2026-11-11-v2"
LEGACY_MARKER = ROOT / "outputs" / "qwen_turbo_visual_validation" / "generation_once.json"

plan = json.loads((FOLDER / "plan.json").read_text(encoding="utf-8"))
before = plan["code_hash"]

def code_hash() -> str:
    files = [ROOT / "app.py", *sorted((ROOT / "core").glob("*.py")),
             *sorted((ROOT / "tests").glob("*.py")), *sorted((ROOT / "tools").glob("*.py")),
             *sorted((ROOT / "templates").glob("*.html")), *sorted((ROOT / "workflows").glob("*.json"))]
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()

if code_hash() != before:
    raise RuntimeError("Le code a changé depuis la prévalidation")

result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        encoding="utf-8", errors="replace")
(FOLDER / "final_tests.log").write_text(result.stdout, encoding="utf-8")
after = code_hash()
stamp = {
    "returncode": result.returncode,
    "code_hash": before,
    "unchanged_during_tests": before == after,
    "legacy_marker_sha256_after_tests": hashlib.sha256(LEGACY_MARKER.read_bytes()).hexdigest(),
}
(FOLDER / "final_tests.json").write_text(json.dumps(stamp, ensure_ascii=False, indent=2), encoding="utf-8")
print("---TAIL---")
print("\n".join(result.stdout.splitlines()[-12:]))
print("RC", result.returncode, "UNCHANGED", stamp["unchanged_during_tests"])
if result.returncode or not stamp["unchanged_during_tests"]:
    raise SystemExit(result.returncode or 1)
