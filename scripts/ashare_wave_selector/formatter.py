from __future__ import annotations

from datetime import datetime

from .scoring import ScoreResult
from .selector import SelectionReport


def _metric(result, key: str, default="-"):
    value = result.metrics.get(key, default)
    if value is None:
        return default
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _status_label(result: ScoreResult) -> str:
    if result.passed and result.score >= 80:
        return "强观察"
    if result.passed:
        return "轻观察"
    hard_keywords = ("环境定仓", "基础行情", "基本面", "技术筛选", "止损")
    if any(flag.startswith(hard_keywords) for flag in result.risk_flags):
        return "仅复盘"
    return "轻观察"


def _metric_float(result: ScoreResult, key: str) -> float | None:
    value = result.metrics.get(key)
    return value if isinstance(value, (int, float)) else None


def _condition_result(text: str) -> str:
    return "通过" if text and text != "-" else "待确认"


def _condition_rows(report: SelectionReport, result: ScoreResult) -> list[tuple[str, str, str, str]]:
    env_value = f"{report.env_level}级"
    return [
        ("市场环境", "非3级环境", env_value, "通过" if report.env_level < 3 else "未通过"),
        ("市值", "50亿-200亿", _metric(result, "总市值亿元"), _condition_result(_metric(result, "总市值亿元"))),
        ("盈利代理", "PE > 0", _metric(result, "市盈率"), _condition_result(_metric(result, "市盈率"))),
        ("日线趋势", "MA13向上", _metric(result, "日线MA13斜率%/日"), _condition_result(_metric(result, "日线MA13斜率%/日"))),
        ("周线趋势", "MA13向上", _metric(result, "周线MA13斜率%/周"), _condition_result(_metric(result, "周线MA13斜率%/周"))),
        ("60分钟", "MA13未破且MACD>0", _metric(result, "60分钟MA13斜率%"), _condition_result(_metric(result, "60分钟MA13斜率%"))),
        ("量能", "温和放大", _metric(result, "近期量能比"), _condition_result(_metric(result, "近期量能比"))),
        ("活跃度", "年涨停次数>3", _metric(result, "近一年涨停次数"), _condition_result(_metric(result, "近一年涨停次数"))),
    ]


def _trend_summary(result: ScoreResult) -> str:
    daily = _metric(result, "日线MA13斜率%/日")
    weekly = _metric(result, "周线MA13斜率%/周")
    return f"日线{daily} / 周线{weekly}"


def _intraday_summary(result: ScoreResult) -> str:
    return f"60分钟MA13斜率{_metric(result, '60分钟MA13斜率%')}"


def _volume_summary(result: ScoreResult) -> str:
    return f"量能比{_metric(result, '近期量能比')}"


def _badge_list(values: list[str]) -> str:
    if not values:
        return "-"
    return " ".join(f"[{value}]" for value in values)


def _decision_sentence(report: SelectionReport, result: ScoreResult) -> str:
    status = _status_label(result)
    strengths = "；".join(result.reasons[:2]) if result.reasons else "核心条件仍需继续验证"
    risk = result.risk_flags[0] if result.risk_flags else "暂无本模型识别出的主要风险"
    return f"{status}：{strengths}；主要风险/待确认项：{risk}"


def _format_compact(report: SelectionReport, *, title: str) -> str:
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 市场环境：{report.env_level}级。{report.env_reason}")
    lines.append(f"- 说明：所有行情、题材和K线判断均来自本次 API 返回数据；候选不足时不会补编股票。")
    lines.append("")

    if not report.candidates:
        lines.append("未筛选出候选股。请检查 AKShare 接口、交易日日期或放宽候选池参数。")
    else:
        lines.append("| 排名 | 代码 | 名称 | 通过 | 分数 | 现价 | 涨跌幅% | PE | 总市值(亿) | 核心入选理由 |")
        lines.append("|---:|---|---|---|---:|---:|---:|---:|---:|---|")
        for idx, item in enumerate(report.candidates, start=1):
            reason = "；".join(item.reasons[:3]) or "未满足核心条件，仅作风险观察"
            lines.append(
                "| {idx} | {symbol} | {name} | {passed} | {score} | {price} | {pct} | {pe} | {mv} | {reason} |".format(
                    idx=idx,
                    symbol=item.symbol,
                    name=item.name,
                    passed="是" if item.passed else "否",
                    score=item.score,
                    price=_metric(item, "现价"),
                    pct=_metric(item, "涨跌幅%"),
                    pe=_metric(item, "市盈率"),
                    mv=_metric(item, "总市值亿元"),
                    reason=reason.replace("|", "/"),
                )
            )
        lines.append("")
        for idx, item in enumerate(report.candidates, start=1):
            lines.append(f"## {idx}. {item.name}（{item.symbol}）")
            lines.append("")
            lines.append(f"- 综合评分：{item.score}；是否通过：{'是' if item.passed else '否'}")
            if item.reasons:
                lines.append("- 入选理由：")
                for reason in item.reasons:
                    lines.append(f"  - {reason}")
            if item.risk_flags:
                lines.append("- 风险/未满足项：")
                for flag in item.risk_flags:
                    lines.append(f"  - {flag}")
            if item.metrics:
                metric_text = "；".join(f"{key}={value}" for key, value in item.metrics.items())
                lines.append(f"- 关键指标：{metric_text}")
            lines.append("")

    lines.append("## 当前逻辑风险提示")
    lines.append("")
    lines.append("- 该 Skill 是选股辅助工具，不构成投资建议；A 股数据可能受停牌、复权、接口延迟和板块口径影响。")
    lines.append("- 文档中的“MA13斜率>45度”等图形语言已转换为归一化斜率近似，输出会明确展示对应指标。")
    lines.append("- 若市场环境被判定为3级，强势波段模型原则上暂停，只能作为观察池，不应机械买入。")
    if report.errors:
        lines.append("")
        lines.append("## 数据获取异常")
        lines.append("")
        for error in report.errors:
            lines.append(f"- {error}")
    return "\n".join(lines).rstrip() + "\n"


def _format_full(report: SelectionReport, *, title: str, audit: bool = False) -> str:
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 1. 本次筛选结论")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 市场环境：{report.env_level}级。{report.env_reason}")
    lines.append(f"- 候选数量：通过 {report.passed_count} 只 / 观察 {report.observed_count} 只 / 淘汰 {report.rejected_count} 只")
    lines.append(f"- 数据完整度：{report.data_quality}")
    if report.env_level == 1:
        lines.append("- 今日结论：市场环境支持积极观察强势波段候选。")
    elif report.env_level == 2:
        lines.append("- 今日结论：市场环境只支持轻仓观察和高抛低吸验证。")
    else:
        lines.append("- 今日结论：市场处于3级风险环境，本模型原则上暂停强势波段参与。")
    lines.append("")

    if not report.candidates:
        lines.append("未筛选出候选股。请检查 AKShare 接口、交易日日期或放宽候选池参数。")
    else:
        lines.append("## 2. 候选总览表")
        lines.append("")
        lines.append("| 排名 | 代码 | 名称 | 状态 | 分数 | 命中标签 | 入池来源 | 技术趋势 | 60分钟 | 量能 | 主要风险 |")
        lines.append("|---:|---|---|---|---:|---|---|---|---|---|---|")
        for idx, item in enumerate(report.candidates, start=1):
            risk = item.risk_flags[0] if item.risk_flags else "-"
            lines.append(
                "| {idx} | {symbol} | {name} | {status} | {score} | {tags} | {sources} | {trend} | {intraday} | {volume} | {risk} |".format(
                    idx=idx,
                    symbol=item.symbol,
                    name=item.name,
                    status=_status_label(item),
                    score=item.score,
                    tags=_badge_list(item.tags[:5]).replace("|", "/"),
                    sources=_badge_list(item.sources).replace("|", "/"),
                    trend=_trend_summary(item).replace("|", "/"),
                    intraday=_intraday_summary(item).replace("|", "/"),
                    volume=_volume_summary(item).replace("|", "/"),
                    risk=risk.replace("|", "/"),
                )
            )
        lines.append("")

        for idx, item in enumerate(report.candidates, start=1):
            lines.append(f"## {idx}. {item.name}（{item.symbol}）")
            lines.append("")
            lines.append("### 一句话结论")
            lines.append("")
            lines.append(_decision_sentence(report, item))
            lines.append("")
            if item.tags or item.risk_tags:
                lines.append("### 命中标签")
                lines.append("")
                if item.tags:
                    lines.append(_badge_list(item.tags))
                if item.risk_tags:
                    lines.append(f"风险标签：{_badge_list(item.risk_tags)}")
                lines.append("")
            if item.sources:
                lines.append("### 入池来源")
                lines.append("")
                lines.append(_badge_list(item.sources))
                lines.append("")
            if item.score_breakdown:
                lines.append("### 分数构成")
                lines.append("")
                lines.append("| 模块 | 得分 |")
                lines.append("|---|---:|")
                for module, points in item.score_breakdown.items():
                    lines.append(f"| {module} | +{points} |")
                lines.append("")
            lines.append("### 条件通过情况")
            lines.append("")
            lines.append("| 模块 | 要求 | 当前数据 | 结果 |")
            lines.append("|---|---|---:|---|")
            for module, requirement, current, result_text in _condition_rows(report, item):
                lines.append(f"| {module} | {requirement} | {current} | {result_text} |")
            lines.append("")
            if item.reasons:
                lines.append("### 入选理由")
                lines.append("")
                for reason in item.reasons:
                    lines.append(f"- {reason}")
                lines.append("")
            if item.risk_flags:
                lines.append("### 风险与未满足项")
                lines.append("")
                for flag in item.risk_flags:
                    lines.append(f"- {flag}")
                lines.append("")
            lines.append("### 下一步观察")
            lines.append("")
            lines.append("- 观察是否继续站稳日线MA13，避免有效跌破后仍按强势波段处理。")
            lines.append("- 观察60分钟MA13是否维持向上，以及MACD是否继续位于0轴上方。")
            lines.append("- 观察量能是否维持温和放大，避免缩量冲高或放量滞涨。")
            if audit and item.metrics:
                lines.append("")
                lines.append("### 原始指标快照")
                lines.append("")
                for key, value in item.metrics.items():
                    lines.append(f"- {key}：{value}")
            lines.append("")

    lines.append("## 当前逻辑风险提示")
    lines.append("")
    lines.append("- 该 Skill 是选股辅助工具，不构成投资建议；A 股数据可能受停牌、复权、接口延迟和板块口径影响。")
    lines.append("- 本报告只增强展示和证据链，不改变原有强势波段评分逻辑。")
    lines.append("- 若数据完整度为“降级”或“严重缺失”，候选只能作为观察池，不能视为确认信号。")
    if report.errors:
        lines.append("")
        lines.append("## 数据获取异常")
        lines.append("")
        for error in report.errors:
            lines.append(f"- {error}")
    return "\n".join(lines).rstrip() + "\n"


def format_markdown(report: SelectionReport, *, title: str = "StockPilot A股强势波段选股结果", depth: str = "compact") -> str:
    if depth == "full":
        return _format_full(report, title=title)
    if depth == "audit":
        return _format_full(report, title=title, audit=True)
    return _format_compact(report, title=title)
