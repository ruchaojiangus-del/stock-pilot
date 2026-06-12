# StockPilot

StockPilot is a Codex skill for screening Chinese A-share strong-wave candidates with a deterministic, data-backed workflow.

It fetches real market data through AKShare, applies the bundled strong-wave selection logic, and produces compact, full, or audit Markdown reports. The output is an observation pool and does not constitute investment advice.

## Install

Clone this skill into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/YOUR_USERNAME/stockpilot.git ~/.codex/skills/stockpilot
python3 -m pip install -r ~/.codex/skills/stockpilot/scripts/requirements.txt
```

Restart Codex or start a new thread if `$stockpilot` does not appear.

## Use In Codex

```text
$stockpilot 帮我筛选今天的 A 股强势波段候选
```

## Run Directly

Compact report:

```bash
python3 ~/.codex/skills/stockpilot/scripts/run_selector.py --top-n 5
```

Decision-style full report:

```bash
python3 ~/.codex/skills/stockpilot/scripts/run_selector.py --top-n 5 --report-depth full --output /tmp/stockpilot-full-report.md
```

Faster full report with controlled parallelism, fewer deep-scored candidates, short-lived cache, and progress logs:

```bash
python3 ~/.codex/skills/stockpilot/scripts/run_selector.py --top-n 5 --report-depth full --deep-candidates 30 --workers 4 --cache-ttl-minutes 15 --progress --output /tmp/stockpilot-full-report.md
```

Audit report with raw metric snapshots:

```bash
python3 ~/.codex/skills/stockpilot/scripts/run_selector.py --top-n 5 --report-depth audit --output /tmp/stockpilot-audit-report.md
```

Fallback mode when Eastmoney endpoints are unstable:

```bash
python3 ~/.codex/skills/stockpilot/scripts/run_selector.py --fast-fallback --no-concepts --watchlist 600000,000001,300750 --top-n 3
```

## Test

```bash
python3 -m unittest discover -s ~/.codex/skills/stockpilot/scripts/tests
```

## Notes

- The selector does not invent missing stock data. Missing fields and API failures are surfaced as warnings or risk flags.
- The script can be slow because it fetches daily, weekly, and 60-minute data for each candidate.
- Use `--max-candidates`, `--deep-candidates`, `--workers`, and `--cache-ttl-minutes` to tune runtime during quick checks.
- Full reports include hit tags, risk tags, candidate-pool sources, and score breakdowns for each stock.
