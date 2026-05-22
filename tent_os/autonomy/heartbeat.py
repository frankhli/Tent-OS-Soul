"""Heartbeat 自主机制 —— OpenClaw 风格

设计：
1. 定时唤醒（默认 30 分钟）
2. 读取 HEARTBEAT.md 任务清单
3. 检查每个任务的触发条件
4. 条件满足 → 生成 governance.request
5. 无事 → HEARTBEAT_OK

HEARTBEAT.md 格式：
    # Heartbeat 任务清单
    
    ## 高频检查（每次心跳）
    - [ ] 检查待审批任务
    - [ ] 检查 OFFLINE 执行者恢复
    
    ## 中频检查（每 2 次心跳）
    - [ ] 检查任务队列深度
    
    ## 低频检查（每 48 次心跳）
    - [ ] 记忆压缩归档
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from tent_os.autonomy.intention import IntentionRegistry, Intention

logger = logging.getLogger("tent_os.heartbeat")


class HeartbeatTask:
    """心跳任务定义"""
    def __init__(self, name: str, description: str, frequency: int = 1,
                 condition: str = "always", action: str = ""):
        self.name = name
        self.description = description
        self.frequency = frequency  # 每 N 次心跳执行一次
        self.condition = condition  # 触发条件描述
        self.action = action        # 执行的动作描述
        self.run_count = 0
        self.last_run = None


class HeartbeatEngine:
    """心跳引擎
    
    不依赖外部 Cron 服务，纯 Python 实现：
    - 定时器触发
    - 条件判断
    - 通过 NATS 发布任务
    """
    
    DEFAULT_INTERVAL = 1800  # 30 分钟（秒）
    
    def __init__(self, bus, heartbeat_path: str = "./HEARTBEAT.md",
                 interval: int = DEFAULT_INTERVAL):
        self.bus = bus
        self.heartbeat_path = Path(heartbeat_path)
        self.interval = interval
        self.tasks: List[HeartbeatTask] = []
        self.tick_count = 0
        self.intention_registry = IntentionRegistry()
        self._parse_heartbeat()
    
    def _parse_heartbeat(self):
        """解析 HEARTBEAT.md"""
        if not self.heartbeat_path.exists():
            self._create_default_heartbeat()
        
        content = self.heartbeat_path.read_text()
        
        # 解析频率段
        frequency_map = {
            "高频": 1,
            "中频": 2,
            "低频": 48,
        }
        
        current_freq = 1
        for line in content.split("\n"):
            line = line.strip()
            
            # 识别频率段
            if line.startswith("## "):
                for key, freq in frequency_map.items():
                    if key in line:
                        current_freq = freq
                        break
            
            # 解析任务项
            match = re.match(r'- \[[ x]\] (.+)', line)
            if match:
                desc = match.group(1).strip()
                self.tasks.append(HeartbeatTask(
                    name=desc[:50],
                    description=desc,
                    frequency=current_freq,
                    action=desc,
                ))
        
        logger.info(f"Heartbeat 解析完成: {len(self.tasks)} 个任务")
    
    def _create_default_heartbeat(self):
        """创建默认心跳文件"""
        default = """# Tent OS 心跳任务清单

> 心跳间隔: 30 分钟
> 上次运行: {last_run}

## 高频检查（每次心跳）
- [ ] 检查是否有待审批的任务（governance.approval.request 状态）
- [ ] 检查 OFFLINE 执行者是否需要自动恢复
- [ ] 检查全局紧急停止状态

## 中频检查（每 2 次心跳 = 1小时）
- [ ] 检查任务队列深度是否异常（>100 告警）
- [ ] 生成系统健康简报
- [ ] 检查执行者状态分布

## 低频检查（每 48 次心跳 = 24小时）
- [ ] 记忆压缩：将过期 L0/L1 归档到 COLD
- [ ] 记忆整合：合并零散观察，消除矛盾
- [ ] 生成系统日报
- [ ] 自动升温/降温记忆指针

## 条件触发（非定时）
- [ ] 当连续失败 > 5 次时，通知管理员
- [ ] 当物理执行者失联 > 10 分钟时，标记 OFFLINE
"""
        self.heartbeat_path.write_text(default)
        logger.info(f"创建默认 HEARTBEAT.md: {self.heartbeat_path}")
    
    async def start(self):
        """启动心跳循环"""
        logger.info(f"Heartbeat 启动，间隔 {self.interval} 秒")
        await self.bus.subscribe("intention.completed", "heartbeat-intention", self._handle_intention_completed)
        while True:
            await self._tick()
            await asyncio.sleep(self.interval)
    
    async def _handle_intention_completed(self, msg):
        """处理意图完成通知"""
        data = json.loads(msg.data)
        intention_id = data.get("intention_id")
        result = data.get("result")
        if intention_id:
            self.intention_registry.update_status(intention_id, "completed", result)
    
    def get_intention_registry(self) -> IntentionRegistry:
        """获取意图注册表（供 API 查询）"""
        return self.intention_registry
    
    async def _tick(self):
        """单次心跳"""
        self.tick_count += 1
        logger.debug(f"Heartbeat tick #{self.tick_count}")
        
        triggered_tasks = []
        
        for task in self.tasks:
            # 检查频率
            if self.tick_count % task.frequency != 0:
                continue
            
            # 检查条件（简化版：目前只有 always 和特定关键词）
            if not self._check_condition(task.condition):
                continue
            
            task.run_count += 1
            task.last_run = datetime.now().isoformat()
            triggered_tasks.append(task)
        
        if triggered_tasks:
            await self._execute_tasks(triggered_tasks)
        else:
            logger.debug("HEARTBEAT_OK — 无任务触发")
    
    def _check_condition(self, condition: str) -> bool:
        """检查任务条件（简化实现）"""
        condition = condition.lower()
        
        # always 条件总是满足
        if condition == "always" or "检查" in condition:
            return True
        
        # 条件触发任务（需要状态查询）
        if "连续失败" in condition:
            # TODO: 查询数据库判断
            return False
        if "失联" in condition:
            # TODO: 查询执行者状态
            return False
        
        return True
    
    async def _execute_tasks(self, tasks: List[HeartbeatTask]):
        """执行触发的心跳任务
        
        FIX Phase 2: Heartbeat 不是"定时找活干"，而是"定期检查是否有活"。
        像人：不会每 30 分钟定个闹钟问自己"我要不要干点啥？"
        人只在有预约、有 deadline、有异常时才行动。
        
        策略：
        1. 轻量级本地检查（不调用 LLM）—— 只查状态，不执行
        2. 只有发现异常/待处理事项时，才发布治理任务
        3. Heartbeat 任务最多 1 个并发槽位，绝不和用户聊天抢资源
        """
        # 先过滤：只保留真正需要处理的任务
        actionable_tasks = []
        for task in tasks:
            if self._is_actionable(task):
                actionable_tasks.append(task)
        
        if not actionable_tasks:
            logger.info("HEARTBEAT_OK — 无待处理事项")
            await self._publish_status(0, tasks)
            return
        
        logger.info(f"Heartbeat 发现 {len(actionable_tasks)} 个待处理事项")
        await self._publish_status(len(actionable_tasks), actionable_tasks)
        
        # 串行发布，每个间隔 3 秒，避免涌入 governance worker
        for i, task in enumerate(actionable_tasks):
            if i > 0:
                await asyncio.sleep(3)
            
            task_id = f"heartbeat_{self.tick_count}_{task.name[:20]}"
            
            await self.bus.publish("governance.request", json.dumps({
                "session_id": task_id,
                "user_id": "system_heartbeat",
                "content": f"[Heartbeat] {task.action}",
                "tools": [],
                "source": "heartbeat",
                "tick_count": self.tick_count,
            }).encode())
            
            logger.info(f"  → 发布任务: {task.name}")
    
    def _is_actionable(self, task: HeartbeatTask) -> bool:
        """判断任务是否真正需要执行（轻量级本地检查，不调用 LLM）
        
        原则：没活不找活。只有发现异常/积压/待办时才返回 True。
        """
        # TODO: 实现真正的状态检查（查询 Redis/数据库）
        # 目前先简单过滤掉 obviously-noop 的任务
        
        name_lower = task.name.lower()
        
        # 健康检查：总是执行（轻量级）
        if "健康" in name_lower or "health" in name_lower:
            return True
        
        # 数据备份：每 24 小时最多一次（检查上次备份时间）
        if "备份" in name_lower or "backup" in name_lower:
            # TODO: 查询上次备份时间
            # 暂时：tick_count % 48 == 0 时执行（每 24 小时，假设 30min interval）
            return self.tick_count % 48 == 0
        
        # 记忆压缩：每周一次
        if "压缩" in name_lower or "compact" in name_lower:
            return self.tick_count % 336 == 0  # 每周（30min * 336 = 7 天）
        
        # 待办事项：只检查，不自动执行
        # 待办事项需要人工确认或条件触发，heartbeat 只做提醒
        if "审查" in name_lower or "更新" in name_lower:
            # TODO: 查询是否有新的报告/状态需要审查
            return False  # 暂时跳过，避免没活找活
        
        return False
    
    async def _publish_status(self, triggered_count: int, tasks: List[HeartbeatTask]):
        """发布心跳状态事件"""
        try:
            await self.bus.nats.publish("heartbeat.status", json.dumps({
                "tick": self.tick_count,
                "timestamp": datetime.now().isoformat(),
                "tasks_triggered": triggered_count,
                "task_names": [t.name for t in tasks],
            }).encode())
        except Exception:
            pass
    
    def get_status(self) -> Dict:
        """获取心跳状态"""
        return {
            "tick_count": self.tick_count,
            "interval_seconds": self.interval,
            "total_tasks": len(self.tasks),
            "tasks": [
                {
                    "name": t.name,
                    "frequency": t.frequency,
                    "run_count": t.run_count,
                    "last_run": t.last_run,
                }
                for t in self.tasks
            ]
        }
