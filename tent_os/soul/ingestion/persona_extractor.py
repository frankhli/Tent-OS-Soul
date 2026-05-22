"""从外部语料中提取人格特征

将解析后的消息批量提交给 LLM，提取人格画像的各个维度。
与 persona_profiler 的区别：
- persona_profiler 分析的是 Tent OS 内的对话（user/assistant 角色明确）
- persona_extractor 分析的是外部语料（微信、邮件、日记），需要 LLM 从文本中推断人格
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from tent_os.logging_config import get_logger

logger = get_logger()


class ExternalPersonaExtractor:
    """从外部语料中提取人格特征"""
    
    def __init__(self, llm=None):
        self.llm = llm
    
    async def extract_from_messages(self, messages: List[Dict], user_id: str,
                                     source_type: str = "external") -> Dict[str, Any]:
        """从一批消息中提取人格特征
        
        Args:
            messages: 解析后的消息列表，每项为 dict，包含 content, speaker, timestamp
            user_id: 用户ID
            source_type: 语料来源类型（wechat/email/diary）
        
        Returns:
            人格特征字典，结构与 persona_profiler 的 analysis_result 一致
        """
        if not self.llm:
            logger.warning("[PersonaExtractor] LLM 未配置，无法提取人格特征")
            return {}
        
        if not messages:
            return {}
        
        # 准备语料文本
        corpus_text = self._format_corpus(messages)
        
        # 截断到合理长度
        max_chars = 12000
        if len(corpus_text) > max_chars:
            # 保留开头和结尾
            head = corpus_text[:4000]
            tail = corpus_text[-8000:]
            corpus_text = f"【语料开头】\n{head}\n\n...[中间省略]...\n\n【语料结尾（最近的内容）】\n{tail}"
        
        try:
            analysis = await self._call_llm_for_extraction(corpus_text, source_type)
            logger.info(
                f"[PersonaExtractor] 从 {source_type} 语料提取人格特征完成 "
                f"[{user_id}] 消息数={len(messages)}"
            )
            return analysis
        except Exception as e:
            logger.warning(f"[PersonaExtractor] 提取人格特征失败 [{user_id}]: {e}")
            return {}
    
    def _format_corpus(self, messages: List[Dict]) -> str:
        """将消息格式化为 LLM 可读的语料文本"""
        lines = []
        
        for msg in messages:
            speaker = msg.get("speaker", "")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp")
            
            if not content or not content.strip():
                continue
            
            # 截断过长内容
            if len(content) > 800:
                content = content[:800] + "...[截断]"
            
            time_str = ""
            if timestamp:
                if isinstance(timestamp, datetime):
                    time_str = timestamp.strftime("%Y-%m-%d")
                else:
                    time_str = str(timestamp)[:10]
            
            if speaker:
                lines.append(f"[{time_str}] {speaker}: {content}")
            else:
                lines.append(f"[{time_str}] {content}")
        
        return "\n".join(lines)
    
    async def _call_llm_for_extraction(self, corpus_text: str, source_type: str) -> Dict[str, Any]:
        """调用 LLM 从语料中提取人格特征"""
        
        system_prompt = """你是一位精通人格分析的心理学家和语言学家。
你的任务是从一段真实的生活语料（微信聊天记录、邮件或日记）中，提取说话者/作者的人格特征。

分析要求：
1. 基于文本中的实际用词、句式、反应方式，不要推测或编造
2. 如果文本中某方面的信息不足，请明确说"信息不足"
3. 如果文本中有自相矛盾的地方，请如实记录
4. 关注"不完美"：犹豫、重复、跑题、情绪波动——这些才是真实人格的印记

输出格式：严格JSON，包含以下字段（如果某字段信息不足，值设为空字符串""或空列表[]）：
{
  "language_style": "说话方式的自然语言描述",
  "sentence_pattern": "句式结构描述",
  "humor_style": "幽默风格描述",
  "catchphrases": ["口头禅1", "口头禅2"],
  "speaking_quirks": ["说话习惯1", "说话习惯2"],
  "decision_pattern": "决策模式描述",
  "thinking_depth": "思维深度描述",
  "argument_style": "争论/反驳方式描述",
  "emotion_pattern": "情绪模式描述",
  "stress_response": "压力反应描述",
  "joy_expression": "快乐表达方式描述",
  "core_values": ["价值观1", "价值观2"],
  "value_conflicts": "价值观冲突描述",
  "relationship_style": "关系处理方式描述",
  "social_energy": "社交能量描述",
  "imperfections": ["不完美特征1", "不完美特征2"],
  "blind_spots": ["盲区1", "盲区2"],
  "unknown_topics": ["不熟悉的领域1"],
  "taboo_topics": ["回避话题1", "回避话题2"],
  "growth_notes": "从语料中观察到的人格变化",
  "life_phases": "语料反映的人生阶段",
  "confidence": "high|medium|low — 整体分析置信度"
}"""
        
        user_prompt = f"""请分析以下{source_type}语料，提取作者的人格特征。

【语料内容】
{corpus_text}

请严格按JSON格式输出分析结果。"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        response = await self.llm.chat(messages, temperature=0.3, max_tokens=2000, thinking={"type": "disabled"})
        
        if not response:
            raise ValueError("LLM 返回空响应")
        
        # 提取 JSON
        analysis = self._extract_json(response)
        
        if not analysis:
            raise ValueError(f"无法从 LLM 响应中解析 JSON: {response[:200]}")
        
        return analysis
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """从文本中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 尝试提取 ```json ... ``` 代码块
        import re
        json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 尝试提取 { ... } 最外层
        brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(1))
            except json.JSONDecodeError:
                pass
        
        return None
