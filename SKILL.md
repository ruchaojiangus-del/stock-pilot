---
name: stockpilot
description: Use when selecting A-share stocks with the user's strong-wave logic, screening Chinese A股 candidates, fetching AKShare market data, explaining stock-selection reasons, or producing a Markdown watchlist with price, change, PE, market-cap, technical, theme, and risk details.
---

# StockPilot

## Overview

Use StockPilot to run a deterministic A股 strong-wave selector based on the provided logic document. The bundled Python script fetches real AKShare data, scores candidates, and outputs a Markdown report with 3-5 stocks when the data supports them.

Never invent stock data, codes, prices, PE, market cap, theme membership, or technical indicators. If data is missing or an API fails, surface the error or risk flag.

## Quick Start

Install runtime dependencies in the Python environment you will use:

```bash
python -m pip install -r ~/.codex/skills/stockpilot/scripts/requirements.txt
```

Run the selector:

```bash
python ~/.codex/skills/stockpilot/scripts/run_selector.py --top-n 5
```

Use a watchlist first, then let the script add strong stocks, limit-up pool names, theme names,涨幅榜 and成交额榜 candidates:

```bash
python ~/.codex/skills/stockpilot/scripts/run_selector.py --watchlist 600519,000858,300750 --top-n 3
```

If Eastmoney endpoints are blocked in the current network, use the verified fallback path:

```bash
python ~/.codex/skills/stockpilot/scripts/run_selector.py --fast-fallback --no-concepts --watchlist 600000,000001,300750 --top-n 3
```

Write the Markdown report to a file:

```bash
python ~/.codex/skills/stockpilot/scripts/run_selector.py --top-n 5 --output /tmp/stockpilot-report.md
```

Generate a decision-style deep report with richer evidence cards:

```bash
python ~/.codex/skills/stockpilot/scripts/run_selector.py --top-n 5 --report-depth full --output /tmp/stockpilot-full-report.md
```

Run faster with controlled parallel scoring, fewer deep candidates, disk cache, and progress logs:

```bash
python ~/.codex/skills/stockpilot/scripts/run_selector.py --top-n 5 --report-depth full --deep-candidates 30 --workers 4 --cache-ttl-minutes 15 --progress --output /tmp/stockpilot-full-report.md
```

## Workflow

1. Read `references/selection_logic.md` when you need the exact mapping from the user's document to the scoring rules.
2. Run `scripts/run_selector.py`; do not manually create stock recommendations when the script can fetch data.
3. Inspect the report:
   - Prefer stocks marked `通过=是`.
   - If fewer than 3 pass, explain that the model did not find enough qualified names instead of filling the list artificially.
   - Include the report's risk section in any user-facing summary.
   - If `--output` writes a report file, include a Codex-clickable Markdown file link in the final response, for example `[stockpilot-full-report.md](/tmp/stockpilot-full-report.md)`. Do not wrap the path in backticks or show it only as plain text.
4. If AKShare is unavailable, say exactly which dependency/API failed and provide the install or retry command.

## What the Script Checks

- Market environment: 上证指数MA13, MA13 slope, and volume classify 1/2/3级环境.
- Theme: AKShare concept boards are matched to S/A/B keywords from the document.
- Basics: 50亿<总市值<200亿, positive PE as the available proxy for positive profitability, and minimum成交额.
- Daily/weekly technicals: MA13 uptrend, MA5/MA13 relation, MACD not below zero, volume expansion, year limit-up count, price position.
- 60-minute technicals: MA13 trend not broken and MACD above zero.
- Output: Markdown table plus per-stock reasons, risk flags, and raw metrics.
- Deep output: conclusion summary, candidate overview, per-stock evidence cards, hit tags, candidate-pool sources, score breakdown, condition matrix, next observations, and data-quality warnings.

## Important Constraints

- Treat AKShare response columns as authoritative; if a field is absent, mark it missing.
- Do not call the result “买入建议”. Describe it as a候选股/观察池/辅助筛选结果.
- Do not promise returns or safety. Always include model and data risks.
- The script may be slow because it fetches individual daily, weekly, and 60-minute data for each candidate. Reduce `--max-candidates` for faster checks.
- For offline tests, use `python -m unittest discover -s ~/.codex/skills/stockpilot/scripts/tests`.

## Optional Parameters

- `--top-n 3..5`: number of names to display.
- `--max-candidates N`: cap API-heavy scoring candidates.
- `--deep-candidates N`: cap candidates that enter daily/weekly/60-minute deep scoring after prefiltering.
- `--workers N`: parallel worker count for deep scoring; lower it when data endpoints are unstable.
- `--cache-ttl-minutes N`: enable local disk cache for reusable normalized daily bars.
- `--progress`: print progress logs to stderr.
- `--watchlist 600000,000001`: priority self-selected stock pool.
- `--no-concepts`: skip concept-board API calls if they are slow or unstable.
- `--fast-fallback`: skip Eastmoney first attempts and use Sina/backup endpoints where available; PE may be missing.
- `--adjust qfq|hfq|""`: adjust historical bars; default is qfq.
- `--output path.md`: write Markdown output while still printing it.
- `--report-depth compact|full|audit`: report detail level; `full` is the decision report, `audit` also lists raw metric snapshots.
