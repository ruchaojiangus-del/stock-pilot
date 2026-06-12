from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import pandas as pd

from .data_source import AKShareDataSource, DataSourceError, normalize_symbol
from .indicators import latest_ma, ma_slope_pct, volume_ratio
from .scoring import ScoreConfig, ScoreResult, score_candidate


@dataclass(frozen=True)
class SelectionConfig:
    top_n: int = 5
    max_candidates: int = 60
    adjust: str = "qfq"
    include_concepts: bool = True
    watchlist: tuple[str, ...] = field(default_factory=tuple)
    score_config: ScoreConfig = field(default_factory=ScoreConfig)


@dataclass
class SelectionReport:
    env_level: int
    env_reason: str
    candidates: list[ScoreResult]
    rejected_count: int
    errors: list[str] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.candidates if item.passed)

    @property
    def observed_count(self) -> int:
        return sum(1 for item in self.candidates if not item.passed)

    @property
    def data_quality(self) -> str:
        if not self.errors:
            return "完整"
        severe_markers = ("获取A股实时行情失败", "获取指数", "评分失败")
        if any(any(marker in error for marker in severe_markers) for error in self.errors):
            return "严重缺失"
        return "降级"


def assess_environment(source: AKShareDataSource) -> tuple[int, str]:
    """Estimate the document's 1/2/3 market environment with index MA13 and volume."""
    try:
        index = source.index_daily("sh000001").tail(80)
    except DataSourceError as exc:
        return 2, f"无法获取上证指数，按2级环境保守处理：{exc}"
    ma13 = latest_ma(index, "close", 13)
    slope = ma_slope_pct(index, "close", 13, 5)
    vol = volume_ratio(index, recent=3, base=13)
    close = float(index["close"].iloc[-1]) if len(index) else None
    if close and ma13 and slope is not None and close >= ma13 and slope > 0 and (vol is None or vol >= 0.95):
        return 1, "指数站上MA13且MA13向上，量能不弱，判定为1级环境。"
    if close and ma13 and close >= ma13 * 0.97:
        return 2, "指数围绕MA13震荡或量能一般，判定为2级环境。"
    return 3, "指数跌破MA13且趋势/量能偏弱，判定为3级风险环境。"


def _base_filter(spot: pd.DataFrame, config: ScoreConfig) -> pd.DataFrame:
    df = spot.copy()
    name = df["name"].fillna("").astype(str)
    df = df[~name.str.contains("ST|退", regex=True)]
    df = df[(df["price"] > 0)]
    if not df["pe"].isna().all():
        df = df[(df["pe"] > 0)]
    if not df["total_mv"].isna().all():
        df = df[(df["total_mv"] >= config.min_market_cap) & (df["total_mv"] <= config.max_market_cap)]
    df = df[(df["amount"].fillna(0) >= config.min_amount)]
    return df


def _prefilter_symbols(
    *,
    spot: pd.DataFrame,
    base: pd.DataFrame,
    limit_up_codes: set[str],
    theme_map: dict[str, list[str]],
    watchlist: Iterable[str],
    max_candidates: int,
) -> list[str]:
    chosen: list[str] = []

    def add_many(values):
        for value in values:
            code = normalize_symbol(value)
            if code not in chosen and code in set(spot["symbol"]):
                chosen.append(code)
            if len(chosen) >= max_candidates:
                return

    add_many(watchlist)
    add_many(limit_up_codes)
    # 题材池优先，避免只选涨幅榜造成题材逻辑失真。
    add_many(theme_map.keys())
    if len(chosen) < max_candidates:
        pct_rank = base.sort_values("pct_chg", ascending=False)["symbol"].head(max_candidates // 2)
        add_many(pct_rank)
    if len(chosen) < max_candidates:
        amount_rank = base.sort_values("amount", ascending=False)["symbol"].head(max_candidates)
        add_many(amount_rank)
    return chosen[:max_candidates]


def run_selection(source: AKShareDataSource | None = None, config: SelectionConfig | None = None) -> SelectionReport:
    config = config or SelectionConfig()
    source = source or AKShareDataSource()
    errors: list[str] = []

    spot = source.spot()
    env_level, env_reason = assess_environment(source)
    limit_up_codes = source.limit_up_pool()
    theme_map = source.theme_matches() if config.include_concepts else {}
    base = _base_filter(spot, config.score_config)

    symbols = _prefilter_symbols(
        spot=spot,
        base=base,
        limit_up_codes=limit_up_codes,
        theme_map=theme_map,
        watchlist=config.watchlist,
        max_candidates=config.max_candidates,
    )

    results: list[ScoreResult] = []
    for symbol in symbols:
        row = spot[spot["symbol"] == symbol].iloc[0]
        try:
            daily = source.daily(symbol, "daily", adjust=config.adjust)
            weekly = source.daily(symbol, "weekly", adjust=config.adjust)
            intraday = source.intraday_60m(symbol, adjust=config.adjust)
            spot_row = row.to_dict()
            if pd.isna(spot_row.get("total_mv")) and "outstanding_share" in daily.columns and not daily["outstanding_share"].dropna().empty:
                latest_shares = daily["outstanding_share"].dropna().iloc[-1]
                latest_price = spot_row.get("price") if not pd.isna(spot_row.get("price")) else daily["close"].iloc[-1]
                spot_row["total_mv"] = float(latest_shares) * float(latest_price)
            result = score_candidate(
                symbol=symbol,
                name=str(row["name"]),
                spot=spot_row,
                daily=daily,
                weekly=weekly,
                intraday=intraday,
                theme_matches=theme_map.get(symbol, []),
                is_limit_up_pool=symbol in limit_up_codes,
                env_level=env_level,
                config=config.score_config,
            )
            results.append(result)
        except DataSourceError as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append(f"{symbol} 评分失败：{exc}")

    passed = sorted((item for item in results if item.passed), key=lambda item: item.score, reverse=True)
    if len(passed) < min(3, config.top_n):
        # 真实市场或接口异常时可能不足3只；不补编造，只附上高分未通过项的风险供排查。
        fallback = sorted((item for item in results if not item.passed), key=lambda item: item.score, reverse=True)
        candidates = passed + fallback[: max(0, config.top_n - len(passed))]
    else:
        candidates = passed[: config.top_n]

    errors = source.warnings[:20] + errors
    return SelectionReport(
        env_level=env_level,
        env_reason=env_reason,
        candidates=candidates[: config.top_n],
        rejected_count=max(0, len(results) - len(passed)),
        errors=errors[:20],
    )
