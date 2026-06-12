#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from ashare_wave_selector.data_source import AKShareDataSource, DataSourceError, normalize_symbol
from ashare_wave_selector.formatter import format_markdown
from ashare_wave_selector.selector import SelectionConfig, run_selection


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按强势波段逻辑筛选A股候选股。")
    parser.add_argument("--top-n", type=int, default=5, help="输出股票数量，建议3-5，默认5。")
    parser.add_argument("--max-candidates", type=int, default=60, help="最多评估的候选池数量，默认60。")
    parser.add_argument("--watchlist", default="", help="逗号分隔的自选股代码，会优先进入候选池。")
    parser.add_argument("--no-concepts", action="store_true", help="跳过概念板块抓取，仅用涨停池/涨幅/成交额候选。")
    parser.add_argument("--fast-fallback", action="store_true", help="直接使用Sina/备用接口，适合东方财富被网络阻断时。")
    parser.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"], help="复权方式：空字符串/qfq/hfq，默认qfq。")
    parser.add_argument("--report-depth", default="compact", choices=["compact", "full", "audit"], help="报告详细度：compact简版/full决策深度版/audit含原始指标。")
    parser.add_argument("--output", default="", help="可选：把Markdown结果写入指定文件。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    top_n = min(max(args.top_n, 3), 5)
    watchlist = tuple(normalize_symbol(item) for item in args.watchlist.split(",") if item.strip())
    config = SelectionConfig(
        top_n=top_n,
        max_candidates=max(10, args.max_candidates),
        adjust=args.adjust,
        include_concepts=not args.no_concepts,
        watchlist=watchlist,
    )
    try:
        report = run_selection(AKShareDataSource(prefer_fallback=args.fast_fallback), config)
    except DataSourceError as exc:
        print(f"数据源错误：{exc}", file=sys.stderr)
        return 2
    markdown = format_markdown(report, depth=args.report_depth)
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
