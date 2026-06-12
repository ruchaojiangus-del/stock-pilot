from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
from typing import Iterable, TextIO

import pandas as pd

from .data_source import AKShareDataSource, DataSourceError, normalize_symbol
from .indicators import latest_ma, ma_slope_pct, volume_ratio
from .scoring import ScoreConfig, ScoreResult, score_candidate


@dataclass(frozen=True)
class SelectionConfig:
    top_n: int = 5
    max_candidates: int = 60
    deep_candidates: int | None = None
    workers: int = 4
    adjust: str = "qfq"
    include_concepts: bool = True
    watchlist: tuple[str, ...] = field(default_factory=tuple)
    score_config: ScoreConfig = field(default_factory=ScoreConfig)
    progress: bool = False
    progress_stream: TextIO | None = None


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


@dataclass
class CandidateSeed:
    symbol: str
    sources: list[str] = field(default_factory=list)


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
) -> list[CandidateSeed]:
    chosen: dict[str, CandidateSeed] = {}
    spot_symbols = set(spot["symbol"])

    def add_many(values, source: str):
        for value in values:
            code = normalize_symbol(value)
            if code in spot_symbols:
                seed = chosen.setdefault(code, CandidateSeed(symbol=code))
                if source not in seed.sources:
                    seed.sources.append(source)
            if len(chosen) >= max_candidates:
                return

    add_many(watchlist, "自选股")
    add_many(limit_up_codes, "涨停池")
    # 题材池优先，避免只选涨幅榜造成题材逻辑失真。
    for symbol, labels in theme_map.items():
        label = labels[0] if labels else "题材池"
        tier = label.split(":", 1)[0] if ":" in label else "题材"
        add_many([symbol], f"{tier}题材池")
    if len(chosen) < max_candidates:
        pct_rank = base.sort_values("pct_chg", ascending=False)["symbol"].head(max_candidates // 2)
        add_many(pct_rank, "涨幅榜")
    if len(chosen) < max_candidates:
        amount_rank = base.sort_values("amount", ascending=False)["symbol"].head(max_candidates)
        add_many(amount_rank, "成交额榜")
    return list(chosen.values())[:max_candidates]


def run_selection(source: AKShareDataSource | None = None, config: SelectionConfig | None = None) -> SelectionReport:
    config = config or SelectionConfig()
    source = source or AKShareDataSource()
    errors: list[str] = []

    def progress(message: str):
        if config.progress:
            print(f"[StockPilot] {message}", file=config.progress_stream or sys.stderr)

    progress("获取实时行情...")
    spot = source.spot()
    progress("评估市场环境...")
    env_level, env_reason = assess_environment(source)
    progress("构建候选池...")
    limit_up_codes = source.limit_up_pool()
    theme_map = source.theme_matches() if config.include_concepts else {}
    base = _base_filter(spot, config.score_config)

    seeds = _prefilter_symbols(
        spot=spot,
        base=base,
        limit_up_codes=limit_up_codes,
        theme_map=theme_map,
        watchlist=config.watchlist,
        max_candidates=config.max_candidates,
    )
    if config.deep_candidates is not None:
        seeds = seeds[: max(1, config.deep_candidates)]
    progress(f"深度评分 {len(seeds)} 只候选，workers={max(1, config.workers)}...")

    def score_seed(seed: CandidateSeed) -> ScoreResult:
        symbol = seed.symbol
        row = spot[spot["symbol"] == symbol].iloc[0]
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
        result.sources = seed.sources
        return result

    results: list[ScoreResult] = []
    worker_count = max(1, config.workers)
    if worker_count == 1 or len(seeds) <= 1:
        for seed in seeds:
            try:
                results.append(score_seed(seed))
            except DataSourceError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f"{seed.symbol} 评分失败：{exc}")
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {executor.submit(score_seed, seed): seed for seed in seeds}
            for future in as_completed(future_map):
                seed = future_map[future]
                try:
                    results.append(future.result())
                except DataSourceError as exc:
                    errors.append(str(exc))
                except Exception as exc:
                    errors.append(f"{seed.symbol} 评分失败：{exc}")

    passed = sorted((item for item in results if item.passed), key=lambda item: item.score, reverse=True)
    if len(passed) < min(3, config.top_n):
        # 真实市场或接口异常时可能不足3只；不补编造，只附上高分未通过项的风险供排查。
        fallback = sorted((item for item in results if not item.passed), key=lambda item: item.score, reverse=True)
        candidates = passed + fallback[: max(0, config.top_n - len(passed))]
    else:
        candidates = passed[: config.top_n]

    errors = source.warnings[:20] + errors
    progress("生成报告数据...")
    return SelectionReport(
        env_level=env_level,
        env_reason=env_reason,
        candidates=candidates[: config.top_n],
        rejected_count=max(0, len(results) - len(passed)),
        errors=errors[:20],
    )
