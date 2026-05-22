"""VisualObservationEngine —— AI 的主动观察引擎

设计：
1. 定时唤醒（默认 10 分钟）
2. 读取最近时间窗口的视觉记忆
3. 检测异常（与历史模式对比）
4. 有异常 → 生成摘要 → NATS 发布 alert + 存入记忆系统
5. 无异常 → 静默（不调用 LLM，控制成本）

这是 HeartbeatEngine 的视觉世界对应物：
- Heartbeat 检查系统内部状态
- VisualObservation 检查物理世界状态
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from tent_os.logging_config import get_logger

logger = get_logger()


class VisualObservationEngine:
    """主动观察引擎 —— AI 自己睁着眼睛看世界"""
    
    DEFAULT_INTERVAL = 600  # 10 分钟（秒）
    
    def __init__(self, bus, interval: int = DEFAULT_INTERVAL, llm=None):
        self.bus = bus
        self.interval = interval
        self.llm = llm
        self.tick_count = 0
        self._last_alert_time: Dict[str, float] = {}  # user_id -> last_alert_timestamp
    
    async def start(self):
        """启动观察循环"""
        logger.info(f"[VisualObservation] 启动，间隔 {self.interval} 秒")
        while True:
            await self._observe_cycle()
            await asyncio.sleep(self.interval)
    
    async def _observe_cycle(self):
        """单次观察周期"""
        self.tick_count += 1
        logger.debug(f"[VisualObservation] tick #{self.tick_count}")
        
        try:
            from tent_os.services.visual_memory_service import get_visual_memory_service
            vm = get_visual_memory_service()
            
            # 默认监控用户（未来可扩展为多用户）
            user_id = "frank"
            
            # 1. 异常检测（低成本：纯 SQLite 统计）
            anomalies = vm.detect_anomalies(user_id, window_hours=24)
            
            if not anomalies:
                logger.debug("[VisualObservation] 无异常，静默")
                return
            
            # 过滤：同一异常 1 小时内不重复告警
            new_anomalies = []
            now = asyncio.get_event_loop().time()
            for a in anomalies:
                key = f"{user_id}:{a.get('object')}:{a.get('type')}"
                last_alert = self._last_alert_time.get(key, 0)
                if now - last_alert > 3600:  # 1 小时去重
                    new_anomalies.append(a)
                    self._last_alert_time[key] = now
            
            if not new_anomalies:
                logger.debug("[VisualObservation] 异常已告警过，跳过")
                return
            
            logger.info(f"[VisualObservation] 发现 {len(new_anomalies)} 个新异常")
            
            # 2. 获取空间摘要（用于生成人类可读的报告）
            spatial_memories = vm.get_spatial_summary(user_id, hours=24)
            
            # 3. 生成观察摘要（只在有异常时调用 LLM）
            summary = await self._generate_summary(user_id, new_anomalies, spatial_memories)
            
            # 4. 通过 NATS 发布告警
            await self._publish_alert(user_id, new_anomalies, summary)
            
            # 5. 将摘要存入文本记忆系统（作为 system 消息，被记忆注入引用）
            await self._ingest_to_memory(user_id, summary)
            
        except Exception as e:
            logger.warning(f"[VisualObservation] 观察周期失败: {e}")
    
    async def _generate_summary(self, user_id: str, anomalies: List[Dict],
                                 spatial_memories: List[Dict]) -> str:
        """生成观察摘要
        
        策略：
        - 如果有 LLM，调用 LLM 生成摘要
        - 否则生成模板化摘要
        """
        # 构建上下文
        anomaly_lines = []
        for a in anomalies:
            obj = a.get("object", "")
            expected = a.get("expected", "")
            actual = a.get("actual", "")
            severity = a.get("severity", "info")
            anomaly_lines.append(f"- [{severity}] {obj}: {expected}，实际{actual}")
        
        # 最近观察
        recent_lines = []
        for mem in spatial_memories[:5]:
            desc = mem.get("description", "")
            created = mem.get("created_at", "")
            time_label = created[11:16] if len(created) >= 16 else created
            recent_lines.append(f"[{time_label}] {desc[:50]}")
        
        if self.llm:
            try:
                prompt = f"""你是一个24小时监控物理世界的AI助手。请根据以下观察记录，生成一段简洁的中文观察摘要（100字以内）：

异常告警：
{chr(10).join(anomaly_lines)}

最近观察：
{chr(10).join(recent_lines)}

要求：
- 用第一人称"我"来写
- 像一个人在汇报自己看到的情况
- 包含异常的严重程度和具体对象
- 不需要建议，只描述事实"""
                
                if hasattr(self.llm, 'complete'):
                    summary = await self.llm.complete(prompt)
                else:
                    summary = await self.llm(prompt)
                return summary.strip()[:200]
            except Exception as e:
                logger.warning(f"[VisualObservation] LLM 摘要生成失败: {e}")
        
        # Fallback: 模板化摘要
        summary_parts = [f"[视觉观察] 检测到 {len(anomalies)} 项异常："]
        for a in anomalies:
            obj = a.get("object", "")
            actual = a.get("actual", "")
            summary_parts.append(f"- {obj}{actual}")
        return " ".join(summary_parts)
    
    async def _publish_alert(self, user_id: str, anomalies: List[Dict], summary: str):
        """通过 NATS 发布视觉告警"""
        try:
            await self.bus.publish_raw("visual.observation.alert", json.dumps({
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "tick": self.tick_count,
                "anomaly_count": len(anomalies),
                "anomalies": anomalies,
                "summary": summary,
            }).encode())
            logger.info(f"[VisualObservation] 告警已发布: {len(anomalies)} 个异常")
        except Exception as e:
            logger.warning(f"[VisualObservation] 告警发布失败: {e}")
    
    async def _ingest_to_memory(self, user_id: str, summary: str):
        """将观察摘要存入记忆系统"""
        try:
            session_id = f"visual_observation_{datetime.now().strftime('%Y%m%d_%H%M')}"
            await self.bus.publish("memory.ingest", json.dumps({
                "messages": [
                    {"role": "system", "content": f"[物理世界观察] {summary}"}
                ],
                "session_id": session_id,
                "user_id": user_id,
            }).encode())
            logger.debug(f"[VisualObservation] 摘要已存入记忆: {session_id}")
        except Exception as e:
            logger.warning(f"[VisualObservation] 记忆摄入失败: {e}")
    
    def get_status(self) -> Dict:
        """获取观察引擎状态"""
        return {
            "tick_count": self.tick_count,
            "interval_seconds": self.interval,
            "last_alert_count": len(self._last_alert_time),
        }
