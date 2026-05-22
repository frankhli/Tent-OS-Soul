#!/usr/bin/env python3
"""SLO 与错误预算系统测试"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tent_os.governance.slo import SLOTracker, AutoThrottle, SLORule


def test_slo():
    print("=" * 60)
    print("SLO 与错误预算系统测试")
    print("=" * 60)

    db_path = "/tmp/test_slo.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    # 1. 创建 SLO Tracker
    print("\n📊 测试 1: 记录任务指标")
    tracker = SLOTracker(db_path=db_path)

    # 模拟 100 个任务，5 个失败
    for i in range(100):
        status = "failed" if i < 5 else "completed"
        latency = 100 + i * 10  # 100ms - 1090ms
        tracker.record_task(
            task_id=f"task_{i}",
            session_id=f"sess_{i // 10}",
            executor_id="mock",
            action="fetch",
            status=status,
            latency_ms=latency,
            error_type="timeout" if status == "failed" else None,
        )
    print("  ✅ 记录 100 个任务（5 失败）")

    # 2. 计算 SLI
    print("\n📊 测试 2: 计算 SLI")
    sli = tracker.calculate_sli(tracker.rules[0])  # 任务成功率
    print(f"  成功率: {sli.current_value:.2%} (目标: {sli.target_value:.0%})")
    print(f"  剩余预算: {sli.budget_remaining:.2%}")
    print(f"  状态: {sli.status}")
    print(f"  总任务: {sli.total_tasks}, 失败: {sli.failed_tasks}")
    assert sli.current_value == 0.95  # 95/100
    assert sli.status == "breached"  # 95% < 99% 目标
    print("  ✅ SLI 计算正确")

    # 3. 摘要报告
    print("\n📊 测试 3: 摘要报告")
    summary = tracker.get_summary()
    print(f"  整体状态: {summary['overall_status']}")
    assert summary["overall_status"] == "breached"
    print("  ✅ 摘要报告正确")

    # 4. AutoThrottle 限流
    print("\n📊 测试 4: 自动限流")
    throttle = AutoThrottle(tracker)

    # 低风险任务
    result = throttle.check_task_allowed(risk_score=0.1)
    print(f"  低风险(0.1): {result}")
    assert not result["allowed"]  # breached 状态拒绝所有新任务

    # 5. 清理旧数据
    print("\n📊 测试 5: 清理旧数据")
    # 先手动插入一条"旧"数据
    tracker.db.execute(
        "INSERT INTO slo_metrics (task_id, session_id, executor_id, action, status, latency_ms, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-2 hours'))",
        ("old_task", "old_sess", "mock", "fetch", "completed", 100),
    )
    tracker.db.commit()
    deleted = tracker.cleanup_old_metrics(retain_hours=1)
    print(f"  清理记录数: {deleted}")
    assert deleted >= 1  # 至少清理了那条旧数据
    print("  ✅ 清理逻辑正确")

    # 6. 自定义 SLO 规则
    print("\n📊 测试 6: 自定义 SLO 规则")
    custom_db = "/tmp/test_slo_custom.db"
    if os.path.exists(custom_db):
        os.remove(custom_db)
    custom_tracker = SLOTracker(
        db_path=custom_db,
        rules=[
            SLORule("高可用性", 0.999, 1, "success_rate"),
            SLORule("快速响应", 0.99, 1, "latency_p99"),
        ],
    )
    # 添加 1000 个任务，5 个失败
    for i in range(1000):
        status = "failed" if i < 5 else "completed"
        custom_tracker.record_task(
            task_id=f"task_ok_{i}", session_id="sess_ok",
            executor_id="mock", action="fetch",
            status=status, latency_ms=200,
        )
    sli2 = custom_tracker.calculate_sli(custom_tracker.rules[0])
    print(f"  995成功 / 1000 = {sli2.current_value:.4f}")
    assert abs(sli2.current_value - 0.995) < 0.001
    print("  ✅ 自定义规则计算正确")

    os.remove(db_path)
    os.remove(custom_db)

    print("\n" + "=" * 60)
    print("✅ SLO 与错误预算系统测试全部通过")
    print("=" * 60)


if __name__ == "__main__":
    test_slo()
