"""Promise Tracker —— 任务承诺跟踪器

FIX Phase 2.5: 解决 AI "说一套做一套" 的假忙碌问题。

问题：AI 承诺"我会帮你完成这个开发任务"，但实际上没有进展，
只是回复"我正在弄"——这是典型的"装忙"。

设计哲学：
- 人类承诺做事后，会在心里记着这个承诺，定期检查进展
- 如果发现停滞，会主动想办法推进，而不是等别人追问
- AI 也应该这样：承诺即责任，不装忙，不拖延

检测机制：
1. 承诺识别：从 LLM 回复中提取承诺性语言
2. 进度跟踪：通过 Tool Loop 检查是否有实质性进展
3. 自动重试：检测到停滞时，自动重新规划
4. 静默同步：有进展时更新状态，不打扰用户

注意：这个模块是"刻在骨子里"的 System 1，不是每次 LLM 调用都要提醒的。
"""

import asyncio
import json
import time
from typing import Dict, List, Optional
import logging

logger = logging.getLogger("tent_os.promise_tracker")


class Promise:
    """一个承诺"""
    def __init__(self, session_id: str, task_description: str, 
                 created_at: float, deadline_at: Optional[float] = None):
        self.session_id = session_id
        self.task_description = task_description
        self.created_at = created_at
        self.deadline_at = deadline_at
        self.last_progress_at = created_at
        self.progress_count = 0  # tool call / 实质性动作次数
        self.status = "active"  # active | stalled | completed | failed
        self.replan_count = 0  # 重新规划次数


class PromiseTracker:
    """任务承诺跟踪器 —— 防止 AI 假忙碌
    
    像人的 TODO 清单 + 责任心：
    - 记下承诺
    - 定期检查进展
    - 发现停滞时主动推进
    - 完成后打勾
    """
    
    def __init__(self):
        self._promises: Dict[str, Promise] = {}  # session_id -> Promise
        self._notify_threshold_seconds = 20  # 20 秒无进展发送提醒
        self._stalled_threshold_seconds = 60  # 1 分钟无进展视为停滞
        self._max_replan = 3  # 最多重新规划 3 次
    
    def record_promise(self, session_id: str, task_description: str) -> None:
        """记录一个新承诺"""
        self._promises[session_id] = Promise(
            session_id=session_id,
            task_description=task_description,
            created_at=time.time(),
        )
        logger.info(f"[PROMISE] 记录承诺 [{session_id}]: {task_description[:50]}")
    
    def record_progress(self, session_id: str, action_type: str = "tool_call") -> None:
        """记录进展"""
        promise = self._promises.get(session_id)
        if promise and promise.status == "active":
            promise.last_progress_at = time.time()
            promise.progress_count += 1
            logger.debug(f"[PROMISE] 进展记录 [{session_id}]: {action_type} #{promise.progress_count}")
    
    def check_stalled(self, session_id: str) -> Optional[str]:
        """检查任务是否停滞
        
        返回: 停滞原因（前缀"提醒:"或"停滞:"），或 None（正常）
        """
        promise = self._promises.get(session_id)
        if not promise or promise.status != "active":
            return None
        
        elapsed = time.time() - promise.last_progress_at
        
        # 规则优先级：放弃 > 停滞 > 提醒
        
        # 规则1：多次重新规划后仍无进展 → 放弃（最高优先级）
        if promise.replan_count >= self._max_replan and promise.progress_count == 0:
            promise.status = "failed"
            return f"放弃：重新规划 {promise.replan_count} 次仍无进展"
        
        # 规则2：长时间无 tool call → 停滞
        if elapsed > self._stalled_threshold_seconds and promise.progress_count == 0:
            promise.status = "stalled"
            return f"停滞：承诺后 {elapsed:.0f}s 无任何实质性进展"
        
        # 规则3：短时间无进展 → 发送提醒（最低优先级，不改变状态）
        if elapsed > self._notify_threshold_seconds and promise.progress_count == 0:
            return f"提醒：已执行 {elapsed:.0f}s，暂无实质性进展"
        
        return None
    
    def mark_completed(self, session_id: str) -> None:
        """标记承诺完成"""
        promise = self._promises.get(session_id)
        if promise:
            promise.status = "completed"
            duration = time.time() - promise.created_at
            logger.info(f"[PROMISE] 承诺完成 [{session_id}]: {duration:.1f}s, {promise.progress_count} 个动作")
    
    def get_active_promises(self) -> List[Promise]:
        """获取所有活跃承诺"""
        return [p for p in self._promises.values() if p.status == "active"]
    
    def should_replan(self, session_id: str) -> bool:
        """判断是否需要重新规划"""
        promise = self._promises.get(session_id)
        if not promise:
            return False
        
        # 停滞且未超过最大重试次数
        if promise.status == "stalled" and promise.replan_count < self._max_replan:
            promise.replan_count += 1
            promise.status = "active"  # 重置状态，给一次机会
            promise.last_progress_at = time.time()
            logger.info(f"[PROMISE] 重新规划 [{session_id}] (第 {promise.replan_count} 次)")
            return True
        
        return False
