import sys
import unittest
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from ashare_wave_selector.scoring import ScoreConfig, score_candidate


def rising_daily_frame(limit_up_days=5):
    rows = []
    close = 10.0
    for i in range(80):
        close *= 1.006
        open_price = close * 0.992
        high = close * 1.03
        low = close * 0.985
        pct = 10.1 if i >= 80 - limit_up_days else 0.6
        rows.append(
            {
                "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                "open": open_price,
                "close": close,
                "high": high,
                "low": low,
                "volume": 1000000 + i * 30000,
                "amount": 100000000 + i * 2000000,
                "pct_chg": pct,
            }
        )
    return pd.DataFrame(rows)


def rising_weekly_frame():
    rows = []
    close = 9.0
    for i in range(30):
        close *= 1.012
        rows.append(
            {
                "date": pd.Timestamp("2025-01-03") + pd.Timedelta(days=i * 7),
                "close": close,
                "volume": 5000000 + i * 100000,
            }
        )
    return pd.DataFrame(rows)


def rising_intraday_frame():
    rows = []
    close = 11.0
    for i in range(60):
        close *= 1.004
        rows.append(
            {
                "datetime": pd.Timestamp("2026-04-01 10:30") + pd.Timedelta(hours=i),
                "open": close * 0.997,
                "close": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "volume": 10000 + i * 100,
            }
        )
    return pd.DataFrame(rows)


class ScoreCandidateTest(unittest.TestCase):
    def test_scores_stock_that_matches_wave_logic(self):
        result = score_candidate(
            symbol="600000",
            name="示例股份",
            spot={
                "price": 12.5,
                "pct_chg": 3.2,
                "pe": 22.0,
                "total_mv": 12_000_000_000,
                "amount": 850_000_000,
            },
            daily=rising_daily_frame(),
            weekly=rising_weekly_frame(),
            intraday=rising_intraday_frame(),
            theme_matches=["人工智能", "低空经济"],
            is_limit_up_pool=True,
            env_level=1,
            config=ScoreConfig(),
        )

        self.assertTrue(result.passed)
        self.assertGreaterEqual(result.score, 70)
        self.assertTrue(any("题材定级" in reason for reason in result.reasons))
        self.assertTrue(any("技术筛选" in reason for reason in result.reasons))
        self.assertTrue(any("核心交易系统" in reason for reason in result.reasons))

    def test_rejects_stock_with_broken_trend_and_negative_profit_proxy(self):
        daily = rising_daily_frame()
        daily.loc[daily.index[-10:], "close"] = daily["close"].iloc[-10] * 0.92
        intraday = rising_intraday_frame()
        intraday.loc[intraday.index[-15:], "close"] = intraday["close"].iloc[-15] * 0.9

        result = score_candidate(
            symbol="000000",
            name="弱势股份",
            spot={
                "price": 8.1,
                "pct_chg": -2.8,
                "pe": -5.0,
                "total_mv": 30_000_000_000,
                "amount": 120_000_000,
            },
            daily=daily,
            weekly=rising_weekly_frame(),
            intraday=intraday,
            theme_matches=[],
            is_limit_up_pool=False,
            env_level=3,
            config=ScoreConfig(),
        )

        self.assertFalse(result.passed)
        self.assertTrue(any("市值" in flag or "盈利" in flag for flag in result.risk_flags))
        self.assertTrue(any("60分钟MA13" in flag or "环境" in flag for flag in result.risk_flags))


if __name__ == "__main__":
    unittest.main()
