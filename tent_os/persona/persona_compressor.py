"""人格压缩器 —— 将完整人格压缩为适合当前对话的 prompt 片段

核心策略：
1. 根据对话上下文选择压缩级别
2. 长对话用"简洁版"，新对话用"完整版"
3. 根据用户当前情绪调整语气
4. 根据用户注意力水平调整长度
"""

import logging
from typing import Dict, Optional

from tent_os.persona.soul_evolution import SoulEvolution, SoulDimensions
from tent_os.persona.user_model import UserModel

logger = logging.getLogger("tent_os.persona.compressor")


class PersonaCompressor:
    """人格压缩器"""
    
    def __init__(self, soul: SoulEvolution):
        self.soul = soul
        # FIX v4: 缓存机制——人格不是每次说话前都重新压缩的
        self._cache_key = None
        self._cache_result = None
    
    def compress(self, 
                 context: Dict = None,
                 user_model: UserModel = None,
                 message_count: int = 0,
                 max_tokens: int = 300) -> str:
        """将完整人格压缩为 prompt 片段
        
        FIX v4: 添加缓存——人格是稳定的，不需要每次请求都重新生成。
        只有当 message_count 跨越级别边界（0→5→20）时才重新生成。
        
        Args:
            context: 对话上下文
            user_model: 用户模型
            message_count: 当前对话消息数
            max_tokens: 最大 token 预算
            
        Returns:
            str: 压缩后的人格 prompt
        """
        context = context or {}
        
        # 判断压缩级别
        if message_count > 20:
            level = "minimal"  # 极简版
        elif message_count > 5:
            level = "brief"    # 简洁版
        else:
            level = "full"     # 完整版
        
        # 根据用户注意力调整
        if user_model and user_model.attention_level < 0.3:
            level = "minimal"  # 用户注意力不集中 → 极简
        
        # FIX v4: 缓存检查——人格是稳定的，不每次重新生成
        # 缓存键：级别 + soul维度哈希 + 用户目标
        soul_hash = hash(tuple(vars(self.soul.dimensions).values()))
        user_goal = user_model.current_goal if user_model else ""
        cache_key = (level, soul_hash, user_goal)
        
        if cache_key == self._cache_key and self._cache_result is not None:
            return self._cache_result
        
        # 生成对应级别的 prompt
        if level == "minimal":
            result = self._minimal_persona(user_model)
        elif level == "brief":
            result = self._brief_persona(user_model)
        else:
            result = self._full_persona(user_model, max_tokens)
        
        # 缓存结果
        self._cache_key = cache_key
        self._cache_result = result
        return result
    
    def _minimal_persona(self, user_model: UserModel = None) -> str:
        """极简版（<50 tokens）"""
        d = self.soul.dimensions
        
        traits = []
        if d.formality > 0.7:
            traits.append("正式")
        elif d.formality < 0.3:
            traits.append("随意")
        
        if d.humor > 0.6:
            traits.append("幽默")
        
        if d.verbosity < 0.3:
            traits.append("简洁")
        elif d.verbosity > 0.7:
            traits.append("详尽")
        
        if d.empathy > 0.6:
            traits.append("共情")
        
        if d.directness > 0.6:
            traits.append("直接")
        
        if not traits:
            traits.append("专业")
        
        base = f"你是一个{'、'.join(traits)}的 AI 助手。"
        
        if user_model and user_model.current_goal:
            base += f" 当前协助用户完成：{user_model.current_goal[:30]}。"
        
        return base
    
    def _brief_persona(self, user_model: UserModel = None) -> str:
        """简洁版（~100 tokens）"""
        d = self.soul.dimensions
        
        parts = ["## 你的性格"]
        
        # 语气
        if d.formality > 0.7:
            parts.append("- 保持正式、专业的语气")
        elif d.formality < 0.3:
            parts.append("- 语气随意、亲和")
        
        if d.humor > 0.6:
            parts.append("- 适当使用幽默")
        elif d.humor < 0.2:
            parts.append("- 保持严肃")
        
        if d.verbosity < 0.3:
            parts.append("- 回答简洁，直击要点")
        elif d.verbosity > 0.7:
            parts.append("- 提供详尽的解释和背景")
        
        if d.empathy > 0.6:
            parts.append("- 展现理解和共情")
        
        if d.proactivity > 0.6:
            parts.append("- 主动提供相关建议")
        elif d.proactivity < 0.3:
            parts.append("- 仅在用户询问时提供信息")
        
        if user_model:
            parts.append("")
            parts.append("## 用户当前状态")
            parts.append(f"- 情绪: {user_model.current_mood}")
            if user_model.current_goal:
                parts.append(f"- 目标: {user_model.current_goal}")
            if user_model.attention_level < 0.3:
                parts.append("- 用户当前注意力不集中，回答需更加简洁")
        
        return "\n".join(parts)
    
    def _full_persona(self, user_model: UserModel = None, max_tokens: int = 300) -> str:
        """完整版（~200 tokens）"""
        d = self.soul.dimensions
        
        parts = ["## 你的身份与性格"]
        parts.append(f"你是一个 {self.soul.get_persona_text()} 的 AI 助手。")
        parts.append("")
        
        # 行为准则
        parts.append("### 行为准则")
        
        if d.formality > 0.7:
            parts.append("- 使用正式称呼和敬语")
        elif d.formality < 0.3:
            parts.append("- 使用轻松的口语化表达")
        
        if d.humor > 0.6:
            parts.append("- 在适当场合使用幽默，但保持尊重")
        elif d.humor < 0.2:
            parts.append("- 避免玩笑，保持专业")
        
        if d.verbosity < 0.3:
            parts.append("- 优先给出结论，细节按需展开")
        elif d.verbosity > 0.7:
            parts.append("- 提供全面、详尽的回答，包括背景信息")
        
        if d.empathy > 0.6:
            parts.append("- 关注用户的情绪和感受，给予理解和支持")
        else:
            parts.append("- 保持客观，聚焦于事实和解决方案")
        
        if d.directness > 0.7:
            parts.append("- 直接表达观点，不绕弯子")
        elif d.directness < 0.3:
            parts.append("- 委婉表达，注意措辞的柔和度")
        
        if d.proactivity > 0.6:
            parts.append("- 主动预测用户需求，提前提供相关信息")
        elif d.proactivity < 0.3:
            parts.append("- 响应用户请求，不主动扩展话题")
        
        if d.precision > 0.7:
            parts.append("- 确保信息的准确性和精确性，不确定时明确说明")
        
        # 用户画像
        if user_model:
            parts.append("")
            parts.append("## 用户画像")
            
            if user_model.preferences:
                parts.append("### 已知偏好")
                for pref, strength in list(user_model.preferences.items())[:5]:
                    parts.append(f"- {pref}")
            
            if user_model.expertise_areas:
                parts.append("### 专业领域")
                for area in user_model.expertise_areas[:3]:
                    parts.append(f"- {area}")
            
            if user_model.communication_style:
                parts.append(f"### 沟通风格: {user_model.communication_style}")
            
            parts.append("")
            parts.append("### 当前状态")
            parts.append(f"- 情绪: {user_model.current_mood}")
            if user_model.current_goal:
                parts.append(f"- 目标: {user_model.current_goal}")
            parts.append(f"- 注意力水平: {'高' if user_model.attention_level > 0.7 else '中' if user_model.attention_level > 0.3 else '低'}")
            
            if user_model.trust_level > 0.7:
                parts.append("- 用户信任度较高")
            elif user_model.trust_level < 0.3:
                parts.append("- 用户信任度较低，重要决策需确认")
        
        result = "\n".join(parts)
        
        # 如果超出 token 预算，回退到简洁版
        # 简单估算：中文 ~2 chars/token，英文 ~4 chars/token
        estimated_tokens = len(result) // 3
        if estimated_tokens > max_tokens:
            return self._brief_persona(user_model)
        
        return result
