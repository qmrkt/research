"""Build and validate the installed research package in a fresh temporary environment.

Run from any directory with Python 3.10+: python scripts/check_active_lp.py
Only the pinned build backend is downloaded; the installed package and tests use
the standard library. No source paths or adjacent contracts repository are added
to the test interpreter's import path.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv


def main() -> None:
    if sys.version_info < (3, 10):
        raise SystemExit("Use Python 3.10 or newer (the simulator uses dataclass slots).")
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="active-lp-check-") as directory:
        work = Path(directory)
        source = work / "source"
        source.mkdir()
        for name in ("pyproject.toml", "LICENSE"):
            shutil.copy2(root / name, source / name)
        shutil.copytree(
            root / "01-active-lp" / "simulation",
            source / "01-active-lp" / "simulation",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "output", "*.egg-info"),
        )
        shutil.copytree(
            root / "02-trust-explicit-resolution" / "simulation",
            source / "02-trust-explicit-resolution" / "simulation",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "output", "*.egg-info"),
        )
        shutil.copytree(
            root / "03-verified-execution" / "simulation",
            source / "03-verified-execution" / "simulation",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "output", "*.egg-info"),
        )
        tests = work / "tests"
        shutil.copytree(root / "tests", tests, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        venv.EnvBuilder(with_pip=True).create(work / "venv")
        executable = work / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        wheels = work / "wheels"
        subprocess.run(
            [str(executable), "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheels), str(source)],
            check=True, cwd=work, env=env,
        )
        wheel, = wheels.glob("question_market_research-*.whl")
        subprocess.run(
            [str(executable), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)],
            check=True, cwd=work, env=env,
        )
        subprocess.run(
            [str(executable), "-m", "unittest", "discover", "-s", str(tests), "-v"],
            check=True, cwd=work, env=env,
        )
        print(json.dumps({
            "status": "passed",
            "python": sys.version,
            "wheel": wheel.name,
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "source_import_path_injected": False,
            "checks": sorted(path.name for path in tests.glob("test_*.py")),
            "scope": "Installed-package test suite. This does not regenerate or validate every historical paper artifact.",
        }, indent=2))


if __name__ == "__main__":
    main()
