import json
from typing import List, Dict, Optional, Any


class PlanExecuteExecutor:
    def __init__(self, llm, approval_threshold: float = 0.5):
        self.llm = llm
        self.approval_threshold = approval_threshold

    async def needs_plan(self, task: str, tools: List[Dict],
                          classifier: Optional[Any] = None) -> bool:
        """判断任务是否需要 Plan 模式（多步骤执行）
        
        FIX v5: 关闭 Plan-Evaluate 路由。当前实现下 Plan 生成慢（60s+超时降级）、
        只执行1步无 Evaluate 循环，不如直接走 Tool Loop 让 LLM 自行规划。
        未来如需恢复，移除下面的 return False 即可。
        """
        # 暂时关闭 Plan-Execute，所有任务直接走 Tool Loop
        return False
    
    def _heuristic_needs_plan(self, task: str) -> bool:
        """启发式判断是否需要 Plan 模式（零成本，不依赖关键词）
        
        逻辑：基于通用特征而非关键词字典
        - 任务长度（超长文本通常复杂）
        - 动词/动作密度（多动词暗示多步骤）
        - 时序连接词密度（非精确匹配，而是统计密度）
        """
        task_lower = task.lower()
        
        # 特征 1: 任务长度
        # FIX: 阈值从 1000 降到 600——中等长度任务也可能需要 Plan
        if len(task) > 600:
            return True
        
        # 特征 2: 动词密度（FIX: 增加"开发/新建/制作/构建"等开发类动词）
        action_words = ["读取", "写入", "修改", "删除", "创建", "生成", "分析",
                       "搜索", "下载", "上传", "发送", "执行", "运行", "开发", "新建",
                       "制作", "构建", "搭建", "设计", "实现", "编写", "撰写",
                       "read", "write", "modify", "delete", "create", "generate",
                       "analyze", "search", "download", "upload", "send", "execute",
                       "develop", "build", "make", "design", "implement", "write"]
        verb_count = sum(1 for w in action_words if w in task_lower)
        if verb_count >= 3:  # FIX: 从 4 降到 3，降低触发门槛
            return True
        
        # 特征 3: 时序/条件词密度（统计而非精确匹配）
        connectors = ["先", "再", "然后", "之后", "接着", "最后", "第一步",
                     "如果", "除非", "当", "取决于",
                     "first", "then", "next", "after", "finally", "if", "unless"]
        connector_count = sum(1 for c in connectors if c in task_lower)
        # 时序词密度高 = 隐含步骤依赖
        if connector_count >= 3:
            return True
        
        return False
    
    def risk_level(self, plan: Dict) -> float:
        """评估 Plan 的风险等级
        
        风险因子：
        - 涉及物理世界或人类的执行者（+0.3）
        - delete/rm/format 等破坏性操作（+0.5）
        - 多步骤 Plan 步骤数 > 3（+0.1/步）
        """
        risk = 0.0
        steps = plan.get("steps", [])
        for step in steps:
            executor_id = step.get("executor", "")
            # 高风险执行者：物理执行者、涉及人类的执行者
            if executor_id.startswith(("physical_", "human_")) or executor_id in ["local"]:
                risk += 0.3
            if step.get("action") in ["delete", "rm", "format"]:
                risk += 0.5
        # 步骤越多，风险累积
        if len(steps) > 3:
            risk += (len(steps) - 3) * 0.1
        return min(risk, 1.0)
    
    async def generate_plan(self, task: str, tools: List[Dict], extra_context: str = "") -> Dict:
        """生成执行计划 —— 带认知预算（15秒超时）
        
        FIX v3: Plan生成不是无限时间的，超过15秒强制降级为单步计划。
        像人做计划：如果一个问题想了几分钟还想不清楚，就简化计划先干起来。
        """
        import asyncio
        
        async def _do_generate():
            if hasattr(self.llm, "generate_plan"):
                return await self.llm.generate_plan(task, tools, extra_context=extra_context)
            # Fallback: 使用通用 complete 接口
            context_block = f"\n\n额外上下文（从过往经验中学到的规则）：\n{extra_context}" if extra_context else ""
            prompt = f"""为以下任务制定执行方案，输出JSON格式：
任务：{task}
可用工具：{json.dumps(tools, ensure_ascii=False)}{context_block}
输出格式：{{"analysis": "...", "steps": [{{"step": 1, "action": "...", "executor": "...", "params": {{}}}}]}}"""
            result = await self.llm.complete(prompt)
            try:
                if isinstance(result, str):
                    return json.loads(result)
                return result
            except Exception:
                return {"analysis": "Fallback plan", "steps": [{"step": 1, "action": "chat", "executor": "default", "params": {}}]}
        
        try:
            # 认知预算：plan生成最多60秒（大prompt+LLM响应慢需要更长时间）
            return await asyncio.wait_for(_do_generate(), timeout=60.0)
        except asyncio.TimeoutError:
            # 超时降级：直接返回单步chat计划，不阻塞用户
            return {
                "analysis": "任务复杂度过高，系统选择直接对话处理（plan生成超时）",
                "steps": [{"step": 1, "action": "chat", "executor": "default", "params": {}}]
            }
