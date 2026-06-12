import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from ashare_wave_selector.formatter import format_markdown
from ashare_wave_selector.scoring import ScoreResult
from ashare_wave_selector.selector import SelectionReport


class FormatterDepthTest(unittest.TestCase):
    def sample_report(self):
        return SelectionReport(
            env_level=2,
            env_reason="指数围绕MA13震荡或量能一般，判定为2级环境。",
            candidates=[
                ScoreResult(
                    symbol="600000",
                    name="示例股份",
                    score=82,
                    passed=True,
                    reasons=[
                        "环境定仓：指数处于2级环境，只适合轻度参与和高抛低吸。",
                        "题材定级：命中S级/国家意志方向（S级:人工智能）。",
                    ],
                    risk_flags=["量能验证：近期量能未明显放大。"],
                    metrics={
                        "现价": 12.34,
                        "涨跌幅%": 3.21,
                        "市盈率": 22.0,
                        "总市值亿元": 126.0,
                        "成交额亿元": 8.5,
                        "日线MA13斜率%/日": 0.12,
                        "周线MA13斜率%/周": 0.04,
                        "60分钟MA13斜率%": 0.03,
                        "近期量能比": 1.23,
                        "近一年涨停次数": 5,
                    },
                    tags=["环境2级", "S级题材:人工智能", "市值合规", "日线MA13向上", "60分钟趋势未破"],
                    risk_tags=["量能待确认"],
                    sources=["S级题材池", "涨幅榜"],
                    score_breakdown={"环境": 8, "题材": 20, "基本面": 16, "技术": 24, "60分钟": 16},
                )
            ],
            rejected_count=4,
            errors=["概念板块接口失败：concepts down"],
        )

    def test_full_report_contains_decision_sections_and_evidence_card(self):
        markdown = format_markdown(self.sample_report(), depth="full")

        self.assertIn("## 1. 本次筛选结论", markdown)
        self.assertIn("## 2. 候选总览表", markdown)
        self.assertIn("### 一句话结论", markdown)
        self.assertIn("### 条件通过情况", markdown)
        self.assertIn("### 下一步观察", markdown)
        self.assertIn("强观察", markdown)
        self.assertIn("数据完整度", markdown)
        self.assertIn("概念板块接口失败", markdown)
        self.assertIn("### 命中标签", markdown)
        self.assertIn("[S级题材:人工智能]", markdown)
        self.assertIn("### 入池来源", markdown)
        self.assertIn("[S级题材池]", markdown)
        self.assertIn("### 分数构成", markdown)
        self.assertIn("| 题材 | +20 |", markdown)

    def test_compact_report_remains_default_shape(self):
        markdown = format_markdown(self.sample_report())

        self.assertIn("| 排名 | 代码 | 名称 | 通过 | 分数 |", markdown)
        self.assertNotIn("## 1. 本次筛选结论", markdown)


if __name__ == "__main__":
    unittest.main()
