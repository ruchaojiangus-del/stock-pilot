import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from run_selector import parse_args


class CliTest(unittest.TestCase):
    def test_report_depth_argument_accepts_full(self):
        args = parse_args(["--report-depth", "full"])

        self.assertEqual(args.report_depth, "full")

    def test_performance_arguments(self):
        args = parse_args(["--workers", "4", "--deep-candidates", "30", "--cache-ttl-minutes", "15", "--progress"])

        self.assertEqual(args.workers, 4)
        self.assertEqual(args.deep_candidates, 30)
        self.assertEqual(args.cache_ttl_minutes, 15)
        self.assertTrue(args.progress)


if __name__ == "__main__":
    unittest.main()
