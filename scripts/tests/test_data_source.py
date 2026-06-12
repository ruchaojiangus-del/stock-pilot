import sys
import unittest
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from ashare_wave_selector.data_source import AKShareDataSource, DataSourceError


class FailingFallbackAK:
    def stock_zh_a_spot(self):
        raise RuntimeError("sina spot down")

    def stock_zh_a_daily(self, **kwargs):
        raise RuntimeError("sina daily down")

    def stock_zh_a_minute(self, **kwargs):
        raise RuntimeError("sina minute down")

    def stock_zh_index_daily(self, **kwargs):
        raise RuntimeError("sina index down")


class WarningAK:
    def stock_zt_pool_em(self, date):
        raise RuntimeError("limit pool down")

    def stock_board_concept_name_em(self):
        raise RuntimeError("concepts down")


class DailyCacheAK:
    def __init__(self):
        self.daily_calls = 0

    def stock_zh_a_daily(self, **kwargs):
        self.daily_calls += 1
        rows = []
        close = 10.0
        for i in range(40):
            close += 0.1
            rows.append(
                {
                    "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                    "open": close - 0.05,
                    "close": close,
                    "high": close + 0.1,
                    "low": close - 0.1,
                    "volume": 1000 + i,
                }
            )
        return pd.DataFrame(rows)


class DataSourceFallbackTest(unittest.TestCase):
    def make_source(self, ak):
        source = object.__new__(AKShareDataSource)
        source.prefer_fallback = True
        source.warnings = []
        source._daily_cache = {}
        source.ak = ak
        return source

    def test_fast_fallback_wraps_api_failures(self):
        source = self.make_source(FailingFallbackAK())

        with self.assertRaisesRegex(DataSourceError, "Sina实时行情"):
            source.spot()
        with self.assertRaisesRegex(DataSourceError, "备用历史接口"):
            source.daily("600000")
        with self.assertRaisesRegex(DataSourceError, "Sina分钟接口"):
            source.intraday_60m("600000")
        with self.assertRaisesRegex(DataSourceError, "Sina指数日线"):
            source.index_daily()

    def test_optional_pool_failures_are_reported_as_warnings(self):
        source = self.make_source(WarningAK())
        source.prefer_fallback = False

        self.assertEqual(source.limit_up_pool(), set())
        self.assertEqual(source.theme_matches(), {})
        self.assertTrue(any("涨停池" in warning for warning in source.warnings))
        self.assertTrue(any("概念板块" in warning for warning in source.warnings))

    def test_fast_fallback_reuses_daily_data_for_weekly_resample(self):
        ak = DailyCacheAK()
        source = self.make_source(ak)

        daily = source.daily("600000", "daily")
        weekly = source.daily("600000", "weekly")

        self.assertFalse(daily.empty)
        self.assertFalse(weekly.empty)
        self.assertEqual(ak.daily_calls, 1)


if __name__ == "__main__":
    unittest.main()
