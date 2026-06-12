from __future__ import annotations

import math
from typing import Iterable

import pandas as pd


def as_float(value, default: float | None = None) -> float | None:
    """Best-effort numeric conversion for values returned by Chinese data APIs."""
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return default


def normalize_numeric(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def moving_average(series: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(window=window, min_periods=window).mean()


def latest_ma(df: pd.DataFrame, column: str = "close", window: int = 13) -> float | None:
    if column not in df or len(df) < window:
        return None
    value = moving_average(df[column], window).iloc[-1]
    return None if pd.isna(value) else float(value)


def ma_slope_pct(df: pd.DataFrame, column: str = "close", window: int = 13, lookback: int = 5) -> float | None:
    """Return average daily slope of MA as percent of the prior MA value."""
    if column not in df or len(df) < window + lookback:
        return None
    ma = moving_average(df[column], window)
    current = ma.iloc[-1]
    previous = ma.iloc[-1 - lookback]
    if pd.isna(current) or pd.isna(previous) or previous == 0:
        return None
    return float((current - previous) / previous / lookback * 100)


def macd(df: pd.DataFrame, column: str = "close", fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    close = pd.to_numeric(df[column], errors="coerce")
    dif = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = (dif - dea) * 2
    return pd.DataFrame({"dif": dif, "dea": dea, "hist": hist})


def latest_macd_state(df: pd.DataFrame, column: str = "close") -> tuple[float | None, float | None, float | None]:
    if column not in df or len(df) < 35:
        return None, None, None
    data = macd(df, column)
    row = data.iloc[-1]
    if row.isna().any():
        return None, None, None
    return float(row["dif"]), float(row["dea"]), float(row["hist"])


def limit_up_count(df: pd.DataFrame, lookback: int = 250) -> int:
    if "pct_chg" not in df:
        return 0
    pct = pd.to_numeric(df.tail(lookback)["pct_chg"], errors="coerce")
    # A 股不同板块涨停阈值不同；这里以普通 10% 板作为保守活跃度近似。
    return int((pct >= 9.5).sum())


def price_position(df: pd.DataFrame, lookback: int = 250) -> float | None:
    """Return close position in recent range, 0=range low, 1=range high."""
    if "close" not in df or len(df) < 20:
        return None
    close = pd.to_numeric(df.tail(lookback)["close"], errors="coerce").dropna()
    if close.empty:
        return None
    low = float(close.min())
    high = float(close.max())
    current = float(close.iloc[-1])
    if math.isclose(high, low):
        return 0.5
    return (current - low) / (high - low)


def volume_ratio(df: pd.DataFrame, recent: int = 5, base: int = 20) -> float | None:
    if "volume" not in df or len(df) < recent + base:
        return None
    volume = pd.to_numeric(df["volume"], errors="coerce")
    recent_avg = volume.tail(recent).mean()
    base_avg = volume.iloc[-recent - base : -recent].mean()
    if pd.isna(recent_avg) or pd.isna(base_avg) or base_avg == 0:
        return None
    return float(recent_avg / base_avg)


def is_pullback_near_ma(df: pd.DataFrame, ma_window: int = 13, tolerance: float = 0.04) -> bool:
    ma = latest_ma(df, "close", ma_window)
    if ma is None or "close" not in df:
        return False
    close = as_float(df["close"].iloc[-1])
    low = as_float(df["low"].iloc[-1] if "low" in df else close)
    if close is None or low is None:
        return False
    return low <= ma * (1 + tolerance) and close >= ma * (1 - tolerance)


def ma_cross_or_above(df: pd.DataFrame, fast: int = 5, slow: int = 13) -> bool:
    if "close" not in df or len(df) < slow + 2:
        return False
    ma_fast = moving_average(df["close"], fast)
    ma_slow = moving_average(df["close"], slow)
    latest_above = ma_fast.iloc[-1] >= ma_slow.iloc[-1]
    crossed_recently = ma_fast.iloc[-2] < ma_slow.iloc[-2] and ma_fast.iloc[-1] >= ma_slow.iloc[-1]
    return bool(latest_above or crossed_recently)
