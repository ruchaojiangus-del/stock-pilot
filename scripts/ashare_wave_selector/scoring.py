from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import pandas as pd

from .indicators import (
    as_float,
    is_pullback_near_ma,
    latest_ma,
    latest_macd_state,
    limit_up_count,
    ma_cross_or_above,
    ma_slope_pct,
    normalize_numeric,
    price_position,
    volume_ratio,
)


@dataclass(frozen=True)
class ScoreConfig:
    min_market_cap: float = 5_000_000_000
    max_market_cap: float = 20_000_000_000
    min_score: int = 68
    min_amount: float = 50_000_000
    min_limit_up_count: int = 3
    daily_ma_window: int = 13
    weekly_ma_window: int = 13
    intraday_ma_window: int = 13
    # 文档中的“MA13向上斜率>45度”在量化里用归一化斜率近似，避免用像素角度伪造判断。
    min_daily_ma13_slope_pct: float = 0.08
    min_weekly_ma13_slope_pct: float = 0.02


@dataclass
class ScoreResult:
    symbol: str
    name: str
    score: int
    passed: bool
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    metrics: dict[str, float | int | str | None] = field(default_factory=dict)


def _theme_score(theme_matches: Sequence[str]) -> tuple[int, str | None]:
    if not theme_matches:
        return 0, None
    joined = "、".join(theme_matches[:6])
    if any(item.startswith("S级") for item in theme_matches):
        return 20, f"题材定级：命中S级/国家意志方向（{joined}）。"
    if any(item.startswith("A级") for item in theme_matches):
        return 14, f"题材定级：命中A级行业爆发方向（{joined}）。"
    return 8, f"题材定级：命中B级消息刺激或相关主题（{joined}）。"


def _append_metric(metrics: dict, key: str, value):
    if value is not None:
        metrics[key] = round(value, 4) if isinstance(value, float) else value


def score_candidate(
    *,
    symbol: str,
    name: str,
    spot: Mapping[str, float | int | str | None],
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    intraday: pd.DataFrame,
    theme_matches: Sequence[str],
    is_limit_up_pool: bool,
    env_level: int,
    config: ScoreConfig,
) -> ScoreResult:
    """Score one stock strictly against the strong-wave document.

    The function never invents missing market data: missing required series becomes a risk flag or
    hard rejection, and all reasons are derived from the provided API rows.
    """
    score = 0
    reasons: list[str] = []
    risk_flags: list[str] = []
    metrics: dict[str, float | int | str | None] = {}

    daily = normalize_numeric(daily, ["open", "close", "high", "low", "volume", "amount", "pct_chg"])
    weekly = normalize_numeric(weekly, ["close", "volume"])
    intraday = normalize_numeric(intraday, ["open", "close", "high", "low", "volume"])

    price = as_float(spot.get("price"))
    pct_chg = as_float(spot.get("pct_chg"))
    pe = as_float(spot.get("pe"))
    total_mv = as_float(spot.get("total_mv"))
    amount = as_float(spot.get("amount"))
    _append_metric(metrics, "现价", price)
    _append_metric(metrics, "涨跌幅%", pct_chg)
    _append_metric(metrics, "市盈率", pe)
    _append_metric(metrics, "总市值亿元", total_mv / 100_000_000 if total_mv else None)
    _append_metric(metrics, "成交额亿元", amount / 100_000_000 if amount else None)

    # 1. 环境定仓：3级环境不做强势波段选股，只输出风险。
    if env_level == 1:
        score += 18
        reasons.append("环境定仓：指数处于1级环境，适合跟随强势波段。")
    elif env_level == 2:
        score += 8
        reasons.append("环境定仓：指数处于2级环境，只适合轻度参与和高抛低吸。")
    else:
        risk_flags.append("环境定仓：指数或量能处于3级风险环境，强势波段逻辑暂停。")

    # 2. 基本面/市值硬约束：严格对应“50亿<市值<200亿、盈利能力为正”。
    if total_mv is None:
        risk_flags.append("基础行情：总市值缺失，无法验证50亿-200亿约束。")
    elif not (config.min_market_cap <= total_mv <= config.max_market_cap):
        risk_flags.append("基础行情：市值不在50亿-200亿区间。")
    else:
        score += 8
        reasons.append("基本面：市值位于50亿-200亿区间。")

    if pe is None:
        risk_flags.append("基础行情：市盈率缺失，无法验证盈利能力为正。")
    elif pe <= 0:
        risk_flags.append("基本面：市盈率为负或为0，不满足盈利能力为正。")
    else:
        score += 8
        reasons.append("基本面：市盈率为正，作为盈利能力为正的可得代理指标。")

    if amount is not None and amount >= config.min_amount:
        score += 4
    elif amount is not None:
        risk_flags.append("流动性：成交额偏低，可能影响买卖执行。")

    theme_points, theme_reason = _theme_score(theme_matches)
    if theme_reason:
        score += theme_points
        reasons.append(theme_reason)
    elif not is_limit_up_pool:
        risk_flags.append("题材定级：未命中文档列出的S/A/B级题材，也不在涨停波段鱼池。")

    if len(daily) < 35:
        risk_flags.append("技术筛选：日线数据不足，无法计算MA13/MACD。")
    else:
        daily_ma13 = latest_ma(daily, "close", config.daily_ma_window)
        daily_slope = ma_slope_pct(daily, "close", config.daily_ma_window, 5)
        ma5_above_ma13 = ma_cross_or_above(daily, 5, config.daily_ma_window)
        pullback = is_pullback_near_ma(daily, config.daily_ma_window)
        dif, dea, hist = latest_macd_state(daily)
        pos = price_position(daily)
        vol_ratio = volume_ratio(daily)
        active_count = limit_up_count(daily)

        _append_metric(metrics, "日线MA13", daily_ma13)
        _append_metric(metrics, "日线MA13斜率%/日", daily_slope)
        _append_metric(metrics, "近一年涨停次数", active_count)
        _append_metric(metrics, "价格区间位置", pos)
        _append_metric(metrics, "近期量能比", vol_ratio)

        latest_close = as_float(daily["close"].iloc[-1])
        if daily_slope is not None and daily_slope >= config.min_daily_ma13_slope_pct and latest_close and daily_ma13 and latest_close >= daily_ma13 * 0.97:
            score += 12
            reasons.append("技术筛选：日线MA13向上且股价未有效跌破MA13。")
        else:
            risk_flags.append("技术筛选：日线MA13斜率不足或股价跌破MA13。")

        if ma5_above_ma13:
            score += 6
            reasons.append("核心交易系统：MA5上穿或保持在MA13上方。")
        if pullback:
            score += 6
            reasons.append("核心交易系统：股价回踩MA13附近后仍有承接。")
        if dif is not None and dif >= 0:
            score += 6
            reasons.append("核心交易系统：日线MACD未下0轴。")
        if vol_ratio is not None and vol_ratio >= 1.15:
            score += 6
            reasons.append("量能验证：近期量能温和放大，具备多堆量/承接迹象。")
        if pos is not None and pos <= 0.75:
            score += 4
            reasons.append("技术筛选：股价仍处于阶段区间偏低或中低位置。")
        if active_count >= config.min_limit_up_count:
            score += 6
            reasons.append("股性活跃：近一年涨停次数超过3次，辨识度较高。")
        if is_limit_up_pool:
            score += 6
            reasons.append("选股池：来自当日涨停波段鱼池。")

    if len(weekly) < 18:
        risk_flags.append("技术筛选：周线数据不足，无法验证周线MA13。")
    else:
        weekly_slope = ma_slope_pct(weekly, "close", config.weekly_ma_window, 3)
        _append_metric(metrics, "周线MA13斜率%/周", weekly_slope)
        if weekly_slope is not None and weekly_slope >= config.min_weekly_ma13_slope_pct:
            score += 8
            reasons.append("技术筛选：周线MA13向上，符合波段延续条件。")
        else:
            risk_flags.append("技术筛选：周线MA13没有确认向上。")

    if len(intraday) < 25:
        risk_flags.append("持股/买点：60分钟数据不足，无法验证60分钟MA13/MACD。")
    else:
        intraday_ma13 = latest_ma(intraday, "close", config.intraday_ma_window)
        intraday_slope = ma_slope_pct(intraday, "close", config.intraday_ma_window, 4)
        intraday_dif, _, _ = latest_macd_state(intraday)
        intraday_close = as_float(intraday["close"].iloc[-1])
        _append_metric(metrics, "60分钟MA13", intraday_ma13)
        _append_metric(metrics, "60分钟MA13斜率%", intraday_slope)
        if intraday_close and intraday_ma13 and intraday_close >= intraday_ma13 * 0.98 and intraday_slope is not None and intraday_slope >= 0:
            score += 10
            reasons.append("持股：60分钟MA13趋势未破，适合动态监控持有。")
        else:
            risk_flags.append("止损：60分钟MA13趋势被破坏或重新拐头失败。")
        if intraday_dif is not None and intraday_dif >= 0:
            score += 6
            reasons.append("买点：60分钟MACD位于0轴上方。")
        else:
            risk_flags.append("买点：60分钟MACD未确认在0轴上方。")

    hard_blockers = [
        flag
        for flag in risk_flags
        if flag.startswith(("环境定仓", "基础行情", "基本面", "技术筛选", "止损"))
    ]
    passed = score >= config.min_score and not hard_blockers
    return ScoreResult(symbol=symbol, name=name, score=int(score), passed=passed, reasons=reasons, risk_flags=risk_flags, metrics=metrics)
