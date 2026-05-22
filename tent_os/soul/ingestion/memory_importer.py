"""将外部语料导入记忆系统

将解析后的消息转换为记忆条目，存入 TieredMemoryStore（L0/L1/L2）。
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from tent_os.logging_config import get_logger

logger = get_logger()


class ExternalMemoryImporter:
    """外部语料记忆导入器"""
    
    def __init__(self, memory_store=None, embedding_client=None):
        self.memory_store = memory_store
        self.embedding_client = embedding_client
    
    async def import_messages(self, messages: List[Dict], user_id: str,
                               source_type: str = "external") -> Dict[str, Any]:
        """将消息导入记忆系统
        
        Args:
            messages: 解析后的消息列表
            user_id: 用户ID
            source_type: 来源类型（wechat/email/diary）
        
        Returns:
            {"inserted": int, "skipped": int, "failed": int, "errors": List[str]}
        """
        if not self.memory_store:
            logger.warning("[MemoryImporter] 记忆存储未配置")
            return {"inserted": 0, "skipped": 0, "failed": 0, "errors": ["记忆存储未配置"]}
        
        inserted = 0
        skipped = 0
        failed = 0
        errors = []
        
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if not content or not content.strip():
                skipped += 1
                continue
            
            # 构建 URI
            timestamp = msg.get("timestamp")
            ts_str = ""
            if timestamp:
                if isinstance(timestamp, datetime):
                    ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
                else:
                    ts_str = str(timestamp)[:15]
            
            speaker = msg.get("speaker", "")
            uri = f"external://{source_type}/{user_id}/{ts_str}_{i}"
            
            # 为内容添加来源上下文
            enriched_content = self._enrich_content(msg)
            
            try:
                await self.memory_store.ingest(
                    content=enriched_content,
                    uri=uri,
                    memory_type=source_type,
                    user_id=user_id,
                    embedding_model=self.embedding_client.embed if self.embedding_client else None,
                    persona="__external__",  # 标记为外部语料
                )
                inserted += 1
            except Exception as e:
                failed += 1
                error_msg = f"导入消息 {i} 失败: {e}"
                errors.append(error_msg)
                logger.warning(f"[MemoryImporter] {error_msg}")
        
        logger.info(
            f"[MemoryImporter] 外部语料导入完成 [{user_id}] "
            f"来源={source_type}, 成功={inserted}, 跳过={skipped}, 失败={failed}"
        )
        
        return {
            "inserted": inserted,
            "skipped": skipped,
            "failed": failed,
            "errors": errors,
        }
    
    def _enrich_content(self, msg: Dict) -> str:
        """为记忆内容添加上下文信息"""
        content = msg.get("content", "")
        speaker = msg.get("speaker", "")
        timestamp = msg.get("timestamp")
        msg_type = msg.get("msg_type", "external")
        metadata = msg.get("metadata", {})
        
        parts = []
        
        # 添加来源标记（帮助记忆检索时识别）
        source_label = metadata.get("source", msg_type)
        parts.append(f"【来源：{source_label}】")
        
        # 添加时间
        if timestamp:
            if isinstance(timestamp, datetime):
                parts.append(f"【时间：{timestamp.strftime('%Y年%m月%d日')}】")
            else:
                parts.append(f"【时间：{timestamp}】")
        
        # 添加说话者
        if speaker:
            parts.append(f"【说话者：{speaker}】")
        
        # 添加元数据中的主题
        subject = metadata.get("subject", "")
        if subject:
            parts.append(f"【主题：{subject}】")
        
        parts.append("")
        parts.append(content)
        
        return "\n".join(parts)
