# Mnemosyne Forge - Unified Check Command
# Usage: py -m scripts.check
# Or:    python scripts/check.py
#
# Environment variables:
#   NODE_EXE - path to the Node.js executable (default: "node")

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd, label):
    print(f"[{label}]", end=" ", flush=True)
    try:
        subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True, errors="replace")
        print("OK")
        return True
    except subprocess.CalledProcessError as e:
        print("FAIL")
        print(e.stdout or "", end="")
        print(e.stderr or "", end="")
        return False
    except OSError as e:
        print(f"FAIL: {e}")
        return False


def main():
    ok = True
    node_exe = os.environ.get("NODE_EXE", "node")
    ok &= run([node_exe, "--check", "web/app.js"], "JS Syntax")
    python = sys.executable
    ok &= run([python, "-m", "compileall", "app", "scripts"], "Python Compile")
    ok &= run([python, "scripts/test_selected_assets_export.py"], "Smoke Test")
    ok &= run([python, "scripts/test_voice_safety_and_performance.py"], "Voice Safety")
    ok &= run([python, "scripts/test_voice_sample_endpoint.py"], "Voice Endpoint Guard")
    ok &= run([python, "scripts/test_image_retry.py"], "Image Retry")
    ok &= run([python, "-m", "pytest", "-q", "scripts/test_image_providers.py", "scripts/test_search_providers.py"], "Image & Search Providers")
    ok &= run([python, "scripts/test_voice_unit_feedback.py"], "Voice Unit Feedback")
    ok &= run([python, "-m", "scripts.test_project_regressions"], "Project Workflow")

    ok &= run([python, "scripts/cleanup_orphan_exports.py", "--dry-run"], "Export Cleanup")
    ok &= run([python, "scripts/index_legacy_exports.py"], "Legacy Index")
    print(f"\n=== {'ALL OK' if ok else 'SOME FAILED'} ===")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
