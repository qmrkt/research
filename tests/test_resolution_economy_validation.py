import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from research.resolution_trust.economy_validation import cases, paired_interval, run, wilson
from research.resolution_trust.economy_audit import audit


class EconomyValidationTests(unittest.TestCase):
    def test_frozen_family_counts_and_distinct_complete_controls(self):
        selected = cases()
        self.assertEqual(len(selected), 171)
        self.assertEqual(len({c.key for c in selected}), 171)
        self.assertEqual(sum(c.family == "compensation" for c in selected), 24)
        self.assertEqual(sum(c.family == "honest_griefing" for c in selected), 12)
        for case in selected:
            if case.family not in {"compensation", "honest_griefing"}:
                self.assertGreaterEqual(case.config.proposer_fee,
                    case.config.proposer_work + case.config.proposer_opportunity_cost + 1)

    def test_paired_interval_respects_common_noise(self):
        values = [.2, .1, -.1, .3]
        result = paired_interval(values)
        self.assertAlmostEqual(result["difference"], .125)
        self.assertLess(result["ci_low"], .125)
        self.assertGreater(result["ci_high"], .125)
        self.assertEqual(paired_interval([0.] * 20)["se"], 0)
        self.assertGreater(wilson(0, 5000)[1], 0)
        self.assertLess(wilson(5000, 5000)[0], 1)

    def test_raw_reaggregation_hashes_and_reproducibility(self):
        selected = [c for c in cases() if c.family == "selection" and c.group == "lazy-uniform"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with contextlib.redirect_stdout(io.StringIO()):
                summary, contrasts = run(root/"a", [17,18], 12, selected)
                again, _ = run(root/"b", [17,18], 12, selected)
            self.assertEqual(summary, again)
            self.assertEqual(audit(root/"a")["audited_episodes"], 48)
            self.assertTrue(contrasts)
            with gzip.open(root/"a/episodes.jsonl.gz", "rt") as handle:
                episodes = [json.loads(line) for line in handle]
            self.assertEqual(len(episodes), 48)
            for row in summary:
                subset = [e for e in episodes if e["case"] == row["case"]]
                self.assertEqual(row["wrong"], sum(e["final_wrong"] for e in subset))
                self.assertEqual(row["submitted"], sum(e["status"] != "deferred" for e in subset))
            manifest = json.loads((root/"a/manifest.json").read_text())
            for name, entry in manifest.items():
                blob = (root/"a"/name).read_bytes()
                self.assertEqual(len(blob), entry["bytes"])
                self.assertEqual(hashlib.sha256(blob).hexdigest(), entry["sha256"])


if __name__ == "__main__":
    unittest.main()
