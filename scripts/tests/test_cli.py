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


if __name__ == "__main__":
    unittest.main()
