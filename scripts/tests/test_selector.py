import sys
import time
import unittest
from io import StringIO
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from ashare_wave_selector.selector import SelectionConfig, run_selection


def frame_daily(rows=80):
    close = 10.0
    data = []
    for i in range(rows):
        close *= 1.006
        data.append(
            {
                "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                "open": close * 0.99,
                "close": close,
                "high": close * 1.02,
                "low": close * 0.98,
                "volume": 1000000 + i * 10000,
                "amount": 100000000 + i * 1000000,
                "pct_chg": 10.1 if i > rows - 5 else 0.6,
            }
        )
    return pd.DataFrame(data)


def frame_intraday(rows=60):
    close = 10.0
    data = []
    for i in range(rows):
        close *= 1.004
        data.append(
            {
                "datetime": pd.Timestamp("2026-01-01 10:30") + pd.Timedelta(hours=i),
                "open": close * 0.99,
                "close": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "volume": 10000 + i * 100,
            }
        )
    return pd.DataFrame(data)


class CountingSource:
    def __init__(self, delay=0.0):
        self.warnings = []
        self.daily_calls = 0
        self.intraday_calls = 0
        self.delay = delay

    def spot(self):
        rows = []
        for i in range(10):
            rows.append(
                {
                    "symbol": f"60000{i}",
                    "name": f"示例{i}",
                    "price": 10 + i,
                    "pct_chg": 9 - i * 0.1,
                    "pe": 20 + i,
                    "total_mv": 10_000_000_000 + i,
                    "amount": 500_000_000 - i,
                }
            )
        return pd.DataFrame(rows)

    def index_daily(self, symbol="sh000001"):
        return frame_daily()

    def limit_up_pool(self):
        return set()

    def theme_matches(self):
        return {}

    def daily(self, symbol, period="daily", adjust="qfq"):
        self.daily_calls += 1
        if self.delay:
            time.sleep(self.delay)
        return frame_daily() if period == "daily" else frame_daily(160).resample("W-FRI", on="date").last().dropna().reset_index()

    def intraday_60m(self, symbol, adjust="qfq"):
        self.intraday_calls += 1
        if self.delay:
            time.sleep(self.delay)
        return frame_intraday()


class SelectorPerformanceTest(unittest.TestCase):
    def test_deep_candidates_limits_expensive_scoring_calls(self):
        source = CountingSource()
        report = run_selection(source, SelectionConfig(top_n=3, max_candidates=10, deep_candidates=3, workers=1))

        self.assertLessEqual(len(report.candidates), 3)
        self.assertEqual(source.intraday_calls, 3)
        self.assertEqual(source.daily_calls, 6)

    def test_workers_score_candidates_concurrently(self):
        serial_source = CountingSource(delay=0.03)
        start = time.perf_counter()
        run_selection(serial_source, SelectionConfig(top_n=3, max_candidates=6, deep_candidates=6, workers=1))
        serial_elapsed = time.perf_counter() - start

        parallel_source = CountingSource(delay=0.03)
        start = time.perf_counter()
        run_selection(parallel_source, SelectionConfig(top_n=3, max_candidates=6, deep_candidates=6, workers=4))
        parallel_elapsed = time.perf_counter() - start

        self.assertLess(parallel_elapsed, serial_elapsed * 0.8)

    def test_progress_logs_selection_stages(self):
        output = StringIO()
        run_selection(
            CountingSource(),
            SelectionConfig(top_n=3, max_candidates=5, deep_candidates=2, workers=1, progress=True, progress_stream=output),
        )

        text = output.getvalue()
        self.assertIn("获取实时行情", text)
        self.assertIn("深度评分", text)


if __name__ == "__main__":
    unittest.main()
