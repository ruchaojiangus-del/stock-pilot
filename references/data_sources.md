# 数据源参考

默认数据源为 AKShare。它是免费开源数据接口，但上游页面结构、交易日和网络状态可能影响可用性。运行时必须以实际 API 返回为准。

## 使用的 AKShare 接口

- `stock_zh_a_spot_em()`：东方财富 A 股实时行情，用于股票代码、名称、最新价、涨跌幅、动态市盈率、总市值、成交额。
- `stock_zh_a_spot()`：Sina 实时行情 fallback；字段较少，通常缺少 PE 和总市值。
- `stock_zh_a_hist(symbol, period="daily"|"weekly", adjust="qfq")`：个股日线/周线历史行情，用于MA13、MA5、MACD、量能、涨停次数和区间位置。
- `stock_zh_a_daily(symbol="sh600000")`：个股日线 fallback；周线可由日线重采样生成。
- `stock_zh_a_hist_min_em(symbol, period="60", adjust="qfq")`：个股60分钟行情，用于60分钟MA13和MACD。
- `stock_zh_a_minute(symbol="sh600000", period="60")`：个股60分钟 fallback。
- `stock_zh_index_daily_em(symbol="sh000001")`：上证指数日线，用于市场环境定级。
- `stock_zh_index_daily(symbol="sh000001")`：上证指数日线 fallback。
- `stock_zt_pool_em(date="YYYYMMDD")`：涨停池，用于波段鱼池候选。
- `stock_board_concept_name_em()` 与 `stock_board_concept_cons_em(symbol=概念名)`：概念板块及成份股，用于S/A/B题材匹配。

官方文档入口：

- AKShare 官方文档：https://akshare.akfamily.xyz/
- AKShare 股票数据文档：https://akshare.akfamily.xyz/data/stock/stock.html

## Tushare 说明

Tushare Pro 覆盖面稳定，但通常需要 token。为保持默认免费开箱，本 Skill 不默认使用 Tushare。若用户提供 token，可在后续扩展一个 `TushareDataSource`，复用当前 `score_candidate` 打分层。
