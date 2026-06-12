from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
from typing import Iterable

import pandas as pd


class DataSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ThemeCatalog:
    s_tier: tuple[str, ...] = ("航空航天", "人工智能", "可控核聚变", "6G", "量子科技", "脑机接口", "低空经济", "国防军工", "海南封关", "海南")
    a_tier: tuple[str, ...] = ("存储芯片", "PCB", "固态电池")
    b_tier: tuple[str, ...] = ("特斯拉", "英伟达", "苹果", "关税", "战争", "降息")


def _load_akshare():
    try:
        import akshare as ak
    except ModuleNotFoundError as exc:
        raise DataSourceError(
            "缺少 akshare。请在当前 Python 环境安装：python -m pip install akshare pandas numpy"
        ) from exc
    return ak


def _today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _date_days_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")


def normalize_symbol(value) -> str:
    text = str(value).strip()
    if text.lower().startswith(("sh", "sz", "bj")):
        text = text[2:]
    if "." in text and text.split(".")[-1].isdigit():
        text = text.split(".")[-1]
    if text.endswith(".0"):
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    return digits[-6:].zfill(6) if digits else text


def prefixed_symbol(symbol: str) -> str:
    code = normalize_symbol(symbol)
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("8", "4", "9")):
        return f"bj{code}"
    return f"sz{code}"


def _rename_existing(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    return df.rename(columns={src: dst for src, dst in mapping.items() if src in df.columns})


def normalize_spot(df: pd.DataFrame) -> pd.DataFrame:
    df = _rename_existing(
        df,
        {
            "代码": "symbol",
            "名称": "name",
            "最新价": "price",
            "涨跌幅": "pct_chg",
            "市盈率-动态": "pe",
            "市盈率": "pe",
            "总市值": "total_mv",
            "成交额": "amount",
        },
    )
    required = ["symbol", "name", "price", "pct_chg", "pe", "total_mv", "amount"]
    for column in required:
        if column not in df.columns:
            df[column] = pd.NA
    df["symbol"] = df["symbol"].map(normalize_symbol)
    for column in ["price", "pct_chg", "pe", "total_mv", "amount"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df[required].copy()


def normalize_daily(df: pd.DataFrame) -> pd.DataFrame:
    df = _rename_existing(
        df,
        {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "涨跌幅": "pct_chg",
            "outstanding_share": "outstanding_share",
        },
    )
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for column in ["open", "close", "high", "low", "volume", "amount", "pct_chg", "outstanding_share"]:
        if column not in df.columns:
            df[column] = pd.NA
        df[column] = pd.to_numeric(df[column], errors="coerce")
    if df["pct_chg"].isna().all() and "close" in df:
        df["pct_chg"] = df["close"].pct_change() * 100
    return df[["date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "outstanding_share"]].dropna(subset=["close"]).copy()


def normalize_intraday(df: pd.DataFrame) -> pd.DataFrame:
    df = _rename_existing(
        df,
        {
            "时间": "datetime",
            "日期": "datetime",
            "day": "datetime",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
        },
    )
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    for column in ["open", "close", "high", "low", "volume"]:
        if column not in df.columns:
            df[column] = pd.NA
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df[["datetime", "open", "close", "high", "low", "volume"]].dropna(subset=["close"]).copy()


def _resample_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty or "date" not in daily:
        return daily
    frame = daily.dropna(subset=["date"]).set_index("date").sort_index()
    weekly = pd.DataFrame(
        {
            "open": frame["open"].resample("W-FRI").first(),
            "high": frame["high"].resample("W-FRI").max(),
            "low": frame["low"].resample("W-FRI").min(),
            "close": frame["close"].resample("W-FRI").last(),
            "volume": frame["volume"].resample("W-FRI").sum(),
            "amount": frame["amount"].resample("W-FRI").sum(),
        }
    ).dropna(subset=["close"])
    weekly["date"] = weekly.index
    weekly["pct_chg"] = weekly["close"].pct_change() * 100
    weekly["outstanding_share"] = pd.NA
    return weekly.reset_index(drop=True)[["date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "outstanding_share"]]


@dataclass
class AKShareDataSource:
    """Thin wrapper around AKShare with column normalization and explicit errors."""

    prefer_fallback: bool = False
    warnings: list[str] = field(default_factory=list)
    _daily_cache: dict[tuple[str, str, str], pd.DataFrame] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        self.ak = _load_akshare()

    def _fallback_daily(self, symbol: str, start_date: str, adjust: str) -> pd.DataFrame:
        key = (normalize_symbol(symbol), start_date, adjust)
        if key not in self._daily_cache:
            raw = self.ak.stock_zh_a_daily(
                symbol=prefixed_symbol(symbol),
                start_date=start_date,
                end_date=_today_yyyymmdd(),
                adjust=adjust,
            )
            self._daily_cache[key] = normalize_daily(raw)
        return self._daily_cache[key].copy()

    def spot(self) -> pd.DataFrame:
        if self.prefer_fallback:
            self.warnings.append("已启用fast-fallback：实时行情直接使用Sina接口，PE等字段可能缺失。")
            try:
                return normalize_spot(self.ak.stock_zh_a_spot())
            except Exception as exc:
                raise DataSourceError(f"获取A股实时行情失败：Sina实时行情={exc}") from exc
        try:
            return normalize_spot(self.ak.stock_zh_a_spot_em())
        except Exception as em_exc:
            self.warnings.append(f"东方财富实时行情失败，改用Sina实时行情兜底：{em_exc}")
            try:
                return normalize_spot(self.ak.stock_zh_a_spot())
            except Exception as fallback_exc:
                raise DataSourceError(f"获取A股实时行情失败：东方财富={em_exc}；Sina={fallback_exc}") from fallback_exc

    def daily(self, symbol: str, period: str = "daily", start_date: str | None = None, adjust: str = "qfq") -> pd.DataFrame:
        start_date = start_date or _date_days_ago(500)
        if self.prefer_fallback:
            try:
                daily = self._fallback_daily(symbol, start_date, adjust)
                return _resample_weekly(daily) if period == "weekly" else daily
            except Exception as exc:
                raise DataSourceError(f"获取{symbol} {period}行情失败：备用历史接口={exc}") from exc
        try:
            raw = self.ak.stock_zh_a_hist(
                symbol=normalize_symbol(symbol),
                period=period,
                start_date=start_date,
                end_date=_today_yyyymmdd(),
                adjust=adjust,
            )
            return normalize_daily(raw)
        except Exception as em_exc:
            self.warnings.append(f"{symbol} 东方财富{period}行情失败，改用备用历史接口：{em_exc}")
            try:
                daily = self._fallback_daily(symbol, start_date, adjust)
                return _resample_weekly(daily) if period == "weekly" else daily
            except Exception as fallback_exc:
                raise DataSourceError(f"获取{symbol} {period}行情失败：东方财富={em_exc}；备用={fallback_exc}") from fallback_exc

    def intraday_60m(self, symbol: str, adjust: str = "qfq") -> pd.DataFrame:
        if self.prefer_fallback:
            try:
                raw = self.ak.stock_zh_a_minute(symbol=prefixed_symbol(symbol), period="60", adjust=adjust)
                return normalize_intraday(raw)
            except Exception as exc:
                raise DataSourceError(f"获取{symbol} 60分钟行情失败：Sina分钟接口={exc}") from exc
        try:
            raw = self.ak.stock_zh_a_hist_min_em(symbol=normalize_symbol(symbol), period="60", adjust=adjust)
            return normalize_intraday(raw)
        except Exception as em_exc:
            self.warnings.append(f"{symbol} 东方财富60分钟行情失败，改用Sina分钟接口：{em_exc}")
            try:
                raw = self.ak.stock_zh_a_minute(symbol=prefixed_symbol(symbol), period="60", adjust=adjust)
                return normalize_intraday(raw)
            except Exception as fallback_exc:
                raise DataSourceError(f"获取{symbol} 60分钟行情失败：东方财富={em_exc}；Sina={fallback_exc}") from fallback_exc

    def index_daily(self, symbol: str = "sh000001") -> pd.DataFrame:
        if self.prefer_fallback:
            self.warnings.append("已启用fast-fallback：指数日线直接使用Sina接口。")
            try:
                raw = self.ak.stock_zh_index_daily(symbol=symbol)
            except Exception as exc:
                raise DataSourceError(f"获取指数{symbol}日线失败：Sina指数日线={exc}") from exc
            raw = _rename_existing(raw, {"date": "date", "open": "open", "close": "close", "high": "high", "low": "low", "volume": "volume"})
            if "date" in raw.columns:
                raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            for column in ["open", "close", "high", "low", "volume"]:
                if column not in raw.columns:
                    raw[column] = pd.NA
                raw[column] = pd.to_numeric(raw[column], errors="coerce")
            return raw[["date", "open", "close", "high", "low", "volume"]].dropna(subset=["close"]).copy()
        try:
            raw = self.ak.stock_zh_index_daily_em(symbol=symbol)
        except Exception as em_exc:
            self.warnings.append(f"{symbol} 东方财富指数日线失败，改用Sina指数日线：{em_exc}")
            try:
                raw = self.ak.stock_zh_index_daily(symbol=symbol)
            except Exception as fallback_exc:
                raise DataSourceError(f"获取指数{symbol}日线失败：东方财富={em_exc}；Sina={fallback_exc}") from fallback_exc
        raw = _rename_existing(raw, {"date": "date", "open": "open", "close": "close", "high": "high", "low": "low", "volume": "volume"})
        if "date" in raw.columns:
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
        for column in ["open", "close", "high", "low", "volume"]:
            if column not in raw.columns:
                raw[column] = pd.NA
            raw[column] = pd.to_numeric(raw[column], errors="coerce")
        return raw[["date", "open", "close", "high", "low", "volume"]].dropna(subset=["close"]).copy()

    def limit_up_pool(self, date: str | None = None) -> set[str]:
        if self.prefer_fallback:
            self.warnings.append("已启用fast-fallback：跳过东方财富涨停池接口。")
            return set()
        try:
            raw = self.ak.stock_zt_pool_em(date=date or _today_yyyymmdd())
        except Exception as exc:
            self.warnings.append(f"涨停池接口失败，候选池缺少涨停来源：{exc}")
            return set()
        code_column = "代码" if "代码" in raw.columns else "code" if "code" in raw.columns else None
        if code_column is None:
            self.warnings.append("涨停池接口返回字段缺少代码列，候选池缺少涨停来源。")
            return set()
        return {normalize_symbol(value) for value in raw[code_column].dropna()}

    def theme_matches(self, catalog: ThemeCatalog | None = None, max_concepts_per_tier: int = 6) -> dict[str, list[str]]:
        catalog = catalog or ThemeCatalog()
        try:
            concepts = self.ak.stock_board_concept_name_em()
        except Exception as exc:
            self.warnings.append(f"概念板块接口失败，题材命中可能缺失：{exc}")
            return {}
        name_col = "板块名称" if "板块名称" in concepts.columns else "name" if "name" in concepts.columns else None
        if name_col is None:
            self.warnings.append("概念板块接口返回字段缺少板块名称列，题材命中可能缺失。")
            return {}

        matches: dict[str, list[str]] = {}
        tiers: list[tuple[str, Iterable[str]]] = [
            ("S级", catalog.s_tier),
            ("A级", catalog.a_tier),
            ("B级", catalog.b_tier),
        ]
        for tier, keywords in tiers:
            picked = []
            for concept_name in concepts[name_col].dropna().astype(str):
                if any(keyword in concept_name for keyword in keywords):
                    picked.append(concept_name)
                if len(picked) >= max_concepts_per_tier:
                    break
            for concept_name in picked:
                try:
                    cons = self.ak.stock_board_concept_cons_em(symbol=concept_name)
                except Exception as exc:
                    self.warnings.append(f"概念板块成份接口失败（{concept_name}），该题材成份可能缺失：{exc}")
                    continue
                code_col = "代码" if "代码" in cons.columns else "code" if "code" in cons.columns else None
                if code_col is None:
                    self.warnings.append(f"概念板块成份接口返回字段缺少代码列（{concept_name}），该题材成份可能缺失。")
                    continue
                label = f"{tier}:{concept_name}"
                for code in cons[code_col].dropna():
                    matches.setdefault(normalize_symbol(code), []).append(label)
        return matches
