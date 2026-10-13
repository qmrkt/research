"""Ensure the historical safety artifact is reproducible from its saved runner."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research.active_lp.safety_validation import run


class SafetyValidationTests(unittest.TestCase):
    def test_artifact_replays_failures_without_losing_quotes_or_cash(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            summary = run(output)
            self.assertTrue(summary['all_checks_passed'])
            self.assertEqual(summary['claim_orders'], 60)
            rows = [json.loads(line) for line in (output / 'events.jsonl').read_text().splitlines()]
            rejected = [row for row in rows if row['rejection']]
            self.assertEqual(len(rejected), 2)
            for row in rejected:
                self.assertEqual(row['label'], 'request_6')
                self.assertFalse(row['quote']['executable'])
                self.assertAlmostEqual(float(row['rejection']['shortfall']), 22.4487554176, places=8)
                self.assertEqual(float(row['actual_cash_change']), 0)
            original = json.loads((output / 'low_tail.json').read_text())
            self.assertAlmostEqual(float(original[-1]['cohorts']['creator:bootstrap'][0]), -189.4643089367, places=8)
            self.assertAlmostEqual(float(original[-1]['cohorts']['creator:bootstrap'][1]), 60.5356910633, places=8)
            self.assertTrue(all(check['passed'] for row in original for check in row['checks']))
            manifest = json.loads((output / 'manifest.json').read_text())
            for name, metadata in manifest.items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), metadata['sha256'])


if __name__ == '__main__':
    unittest.main()
