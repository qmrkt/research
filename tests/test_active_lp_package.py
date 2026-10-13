"""Checks against the installed package; no source-tree import workaround."""

from __future__ import annotations

import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class InstalledPackageTests(unittest.TestCase):
    def test_exact_api_does_not_import_layer_c(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", (
                "import sys; "
                "from research.active_lp import ExperimentRunner, ReferenceParallelLmsrEngine; "
                "assert 'research.active_lp.layer_c_fixed_point' not in sys.modules; "
                "assert 'smart_contracts' not in sys.modules"
            )],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_module_cli_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "research.active_lp", "--help"],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deterministic", result.stdout)

    def test_console_entrypoint(self) -> None:
        command = Path(sys.executable).parent / ("active-lp.exe" if os.name == "nt" else "active-lp")
        result = subprocess.run([str(command), "--help"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deterministic", result.stdout)

    def test_default_output_is_relative_to_working_directory(self) -> None:
        from research.active_lp.cli import build_parser

        arguments = build_parser().parse_args(["deterministic"])
        self.assertEqual(arguments.output_dir, Path("output/active_lp/deterministic"))

    def test_deterministic_cli_writes_results(self) -> None:
        from research.active_lp.scenarios import deterministic_scenario_names

        with tempfile.TemporaryDirectory(prefix="lp-cli-test-") as directory:
            result = subprocess.run(
                [sys.executable, "-m", "research.active_lp", "deterministic",
                 "--scenario", deterministic_scenario_names()[0], "--output-dir", directory],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            output = Path(directory)
            self.assertTrue((output / "summary.csv").is_file())
            rows = [json.loads(line) for line in (output / "results.jsonl").read_text().splitlines()]
            self.assertGreater(len(rows), 0)
            self.assertTrue((output / "manifest.json").is_file())

    def test_vendored_helper_is_exact_pinned_blob(self) -> None:
        vendor = files("research.active_lp._vendor")
        provenance = json.loads(vendor.joinpath("provenance.json").read_text())
        self.assertEqual(provenance["upstream_commit"], "0010101ecba7800db0f7737dcc5328a472e87694")
        self.assertEqual(hashlib.sha256(vendor.joinpath("lmsr_math.py").read_bytes()).hexdigest(), provenance["sha256"])
        self.assertEqual(hashlib.sha256(vendor.joinpath("LICENSE.lmsr_math").read_bytes()).hexdigest(), provenance["license_sha256"])

    def test_legacy_layer_c_is_importable_without_contracts_repo(self) -> None:
        from research.active_lp.layer_c_fixed_point import AVM_SCALE, LayerCFixedPointEngine

        self.assertEqual(AVM_SCALE, 1_000_000)
        self.assertIsNotNone(LayerCFixedPointEngine())
        self.assertNotIn("smart_contracts", sys.modules)


if __name__ == "__main__":
    unittest.main()
