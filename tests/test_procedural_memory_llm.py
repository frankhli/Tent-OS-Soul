#!/usr/bin/env python3
"""Procedural Memory LLM 提取路径测试"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tent_os.memory.procedural import ProceduralMemoryStore, ExperienceExtractor


class MockLLM:
    """模拟 LLM，返回结构化规则文本"""

    def __init__(self, response_text: str):
        self.response_text = response_text

    async def complete(self, prompt: str) -> str:
        return self.response_text


async def test_llm_extract():
    print("=" * 60)
    print("Procedural Memory LLM 提取路径测试")
    print("=" * 60)

    # 测试 1: LLM 返回有效规则
    print("\n🧠 测试 1: LLM 返回有效规则")
    llm_response = """
trigger_condition: 执行涉及文件删除的操作
action_rule: 必须先创建备份到 /tmp/backup 目录，然后人工确认后再删除
category: safety
"""
    extractor = ExperienceExtractor(llm=MockLLM(llm_response))
    rule = await extractor.extract_from_evaluation(
        task="删除旧的日志文件",
        plan={"steps": [{"action": "delete", "executor": "local"}]},
        result={"status": "failed", "error": "误删了重要文件"},
        evaluation={"passed": False, "overall_score": 0.2, "criteria_scores": {"safety": 0.1}, "feedback": "文件被误删"},
    )
    assert rule is not None
    assert "删除" in rule.trigger_condition
    assert "备份" in rule.action_rule
    assert rule.category == "safety"
    print(f"  ✅ 提取规则: [{rule.category}] {rule.trigger_condition[:40]}...")

    # 测试 2: LLM 返回"无"
    print("\n🧠 测试 2: LLM 返回'无'（无法提取规则）")
    extractor2 = ExperienceExtractor(llm=MockLLM("无法提取有效规则。\n无"))
    rule2 = await extractor2.extract_from_evaluation(
        task="简单查询",
        plan={},
        result={},
        evaluation={"passed": False, "overall_score": 0.3, "criteria_scores": {}, "feedback": ""},
    )
    assert rule2 is None
    print("  ✅ 正确返回 None")

    # 测试 3: 评估通过时不提取
    print("\n🧠 测试 3: 评估通过（高分）时不提取")
    extractor3 = ExperienceExtractor(llm=MockLLM("trigger_condition: xxx"))
    rule3 = await extractor3.extract_from_evaluation(
        task="查询天气",
        plan={},
        result={"status": "completed"},
        evaluation={"passed": True, "overall_score": 0.9, "criteria_scores": {}, "feedback": ""},
    )
    assert rule3 is None
    print("  ✅ 高分评估正确跳过提取")

    # 测试 4: 端到端流程（提取 → 入库 → 检索 → 注入）
    print("\n🧠 测试 4: 端到端流程")
    db_path = "/tmp/test_procedural_llm.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    store = ProceduralMemoryStore(db_path)
    extractor4 = ExperienceExtractor(llm=MockLLM("""
trigger_condition: 调用外部 API 获取数据
action_rule: 必须验证 HTTP 状态码为 200，否则重试最多 3 次
category: correctness
"""))

    rule4 = await extractor4.extract_from_evaluation(
        task="获取股票数据",
        plan={"steps": [{"action": "fetch", "executor": "http_api"}]},
        result={"status": "failed", "error": "API 返回 500"},
        evaluation={"passed": False, "overall_score": 0.3, "criteria_scores": {"correctness": 0.2}, "feedback": "API 错误未处理"},
    )
    assert rule4 is not None

    rule_id = store.add_rule(
        trigger_condition=rule4.trigger_condition,
        action_rule=rule4.action_rule,
        category=rule4.category,
        confidence=rule4.confidence,
    )

    # 检索
    found = store.find_relevant("获取远程 API 数据")
    assert len(found) >= 1
    assert "验证 HTTP 状态码" in found[0].action_rule
    print(f"  ✅ 规则入库并检索成功 (ID: {rule_id})")

    # 注入渲染
    from tent_os.memory.procedural import ProceduralMemoryInjector
    injector = ProceduralMemoryInjector(store)
    text = injector.render_rules("调用外部 API")
    assert "验证 HTTP 状态码" in text
    print(f"  ✅ 注入渲染成功")

    os.remove(db_path)

    print("\n" + "=" * 60)
    print("✅ Procedural Memory LLM 提取路径全部测试通过")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_llm_extract())
