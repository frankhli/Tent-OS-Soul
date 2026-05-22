"""Skill Router —— 智能技能路由系统

De-keywordization: 从 triggers 关键词匹配 → LLM 语义扩展 + 倒排索引

核心设计原则：
1. 先过滤闲聊（90% 的对话不需要 skill）
2. LLM 语义扩展 triggers（加载时一次性，零运行时成本）
3. 倒排索引 O(k) 快速命中（k=用户输入关键词数）
4. 最多同时激活 2 个 skill，避免 prompt 膨胀
5. Skill 只引用 tool name，不定义 tool 格式

三层路由：
  用户输入 → [闲聊过滤] → 是闲聊？→ 直接返回 []，不走 skill
            ↓ 否
         [倒排索引命中] → 候选 skill 集（通常 1~5 个）
            ↓
         [精确评分 Top-2] → 最终激活的 skills（最多 2 个）
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Set, Any

from tent_os.skills.loader import Skill, SkillLoader
from tent_os.logging_config import get_logger

logger = get_logger()


# ========== 闲聊过滤词 ==========
_CHITCHAT_PATTERNS = re.compile(
    r'^(你好|嗨|hello|hi|hey|在吗|在不在|谢谢|感谢|拜拜|再见|goodbye|bye|'
    r'哈哈|呵呵|嘿嘿|可爱|好看|不错|好的|ok|okay|嗯|哦|啊)[!！.。]*$',
    re.IGNORECASE
)

_CHITCHAT_KEYWORDS = {
    '天气', '吃饭', '睡', '累', '忙', '闲', '无聊', '开心', '难过', '生气',
    '笑话', '故事', '聊天', '聊什么', '随便', '都行', '随便聊',
}


class SkillRouter:
    """技能路由器 —— De-keywordization：LLM 语义扩展 triggers
    
    FIX Phase 5: 四层路由架构
    Layer 1: 闲聊过滤 (90% 对话)
    Layer 2: 倒排索引快速命中 (5% 对话)
    Layer 3: TF-IDF 语义匹配 (4% 对话，0ms，零成本)
    Layer 4: LLM 语义路由 (1% 对话，真正的歧义)
    """
    
    def __init__(self, skills_dir: str = "./skills", llm: Any = None,
                 expand_triggers: bool = True):
        self.skills_dir = Path(skills_dir)
        self.skills: Dict[str, Skill] = {}
        # 倒排索引: word -> set(skill_name)
        self._index: Dict[str, Set[str]] = {}
        self.llm = llm
        self._expand_triggers = expand_triggers
        
        # FIX Phase 5: TF-IDF 语义匹配层
        self._tfidf = None
        self._skill_vectors: Dict[str, List[float]] = {}
        
        self._load_all()
        self._build_tfidf_vectors()  # 加载后预计算向量
    
    def set_llm(self, llm: Any):
        """延迟设置 LLM（用于初始化顺序调整）"""
        self.llm = llm
    
    def _build_tfidf_vectors(self):
        """FIX Phase 5: 预计算所有 skill 的 TF-IDF 向量
        
        加载时一次性计算，运行时 0ms 匹配。
        """
        try:
            from tent_os.llm.embedding_tfidf import TfidfEmbeddingProvider
            
            # 收集所有 skill 的文本（name + description + triggers）
            skill_texts = []
            skill_names = []
            for name, skill in self.skills.items():
                text = f"{name} {skill.description or ''} {' '.join(skill.triggers)}"
                skill_texts.append(text)
                skill_names.append(name)
            
            if not skill_texts:
                return
            
            # 拟合 TF-IDF
            self._tfidf = TfidfEmbeddingProvider()
            self._tfidf.fit(skill_texts)
            
            # 预计算每个 skill 的向量
            for name, text in zip(skill_names, skill_texts):
                vec = self._tfidf.embed(text)
                self._skill_vectors[name] = vec.tolist() if hasattr(vec, 'tolist') else vec
            
            logger.info(f"[SkillRouter] TF-IDF 向量预计算完成: {len(skill_names)} 个 skills")
        except Exception as e:
            logger.warning(f"[SkillRouter] TF-IDF 预计算失败: {e}")
    
    def _tfidf_route(self, text: str, top_k: int = 2, threshold: float = 0.15) -> List[Skill]:
        """FIX Phase 5: TF-IDF 语义匹配层
        
        用户输入和 skill 描述做语义相似度匹配。
        0ms，零 API 成本，效果优于纯关键词匹配。
        """
        if not self._tfidf or not self._skill_vectors:
            return []
        
        query_vec = self._tfidf.embed(text)
        query_vec = query_vec.tolist() if hasattr(query_vec, 'tolist') else query_vec
        
        import numpy as np
        scored = []
        for name, skill_vec in self._skill_vectors.items():
            # 余弦相似度
            dot = sum(a * b for a, b in zip(query_vec, skill_vec))
            norm_q = sum(a * a for a in query_vec) ** 0.5
            norm_s = sum(a * a for a in skill_vec) ** 0.5
            if norm_q > 0 and norm_s > 0:
                sim = dot / (norm_q * norm_s)
                if sim >= threshold:
                    scored.append((sim, name))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        result = []
        for _, name in scored[:top_k]:
            if name in self.skills:
                result.append(self.skills[name])
        
        if result:
            logger.debug(f"[SkillRouter] TF-IDF 命中: {[s.name for s in result]}")
        
        return result
    
    def _load_all(self):
        """加载 skills 并构建倒排索引"""
        if not self.skills_dir.exists():
            return
        
        for item in self.skills_dir.iterdir():
            if item.is_dir():
                skill = SkillLoader.load_from_directory(item)
                if skill:
                    self.skills[skill.name] = skill
                    self._index_skill(skill)
        
        logger.info(
            f"SkillRouter 加载 {len(self.skills)} 个 skills，索引 {len(self._index)} 个关键词"
        )
    
    async def expand_all_triggers(self, max_concurrent: int = 5) -> Dict[str, List[str]]:
        """用 LLM 为所有 skill 扩展语义等价的 triggers
        
        De-keywordization 核心：让 LLM 根据 skill description 生成更多
        用户可能的表达方式，覆盖关键词字典无法穷尽的语义空间。
        
        并行处理：max_concurrent 控制并发数，避免同时发起过多 LLM 请求。
        
        例如：presentation skill 的 triggers 包含"生成PPT"
        LLM 扩展 → "生成幻灯片、制作演示文稿、创建 pitch deck..."
        
        Returns:
            {skill_name: [扩展 trigger1, 扩展 trigger2, ...]}
        """
        if not self.llm:
            logger.info("[SkillRouter] 无 LLM，跳过 triggers 扩展")
            return {}
        
        import asyncio
        expanded: Dict[str, List[str]] = {}
        skills_list = list(self.skills.items())
        
        # 分批并行处理
        for i in range(0, len(skills_list), max_concurrent):
            batch = skills_list[i:i + max_concurrent]
            tasks = [
                self._llm_expand_triggers(skill)
                for _, skill in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for (name, skill), result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.warning(f"[SkillRouter] 扩展 {name} triggers 失败: {result}")
                    continue
                if result:
                    expanded[name] = result
                    skill.triggers = list(skill.triggers) + result
                    self._index_skill(skill, is_expansion=True)
        
        total_new = sum(len(v) for v in expanded.values())
        logger.info(
            f"[SkillRouter] LLM 扩展完成：{len(expanded)} 个 skill，"
            f"新增 {total_new} 个 triggers，索引 {len(self._index)} 个关键词"
        )
        return expanded
    
    async def _llm_expand_triggers(self, skill: Skill) -> List[str]:
        """调用 LLM 为单个 skill 扩展 triggers"""
        prompt = f"""你是技能分析专家。根据以下 skill 的 description 和现有 triggers，
生成 8-12 个用户可能使用的**不同表达方式**（同义词、近义词、常见说法）。

Skill: {skill.name}
Description: {skill.description}
现有 triggers: {', '.join(skill.triggers[:10])}

要求：
- 生成的表达应与现有 triggers **语义等价但措辞不同**
- 包含中文和英文表达
- 不要重复现有 triggers
- 只输出 JSON 数组

示例输出：["生成幻灯片", "制作 pitch deck", "做路演材料", "创建演示文稿"]"""
        
        response = await self.llm.chat([
            {"role": "system", "content": "你只输出 JSON 数组，不要其他内容。"},
            {"role": "user", "content": prompt},
        ])
        
        return self._parse_trigger_expansion(response)
    
    def _parse_trigger_expansion(self, response: str) -> List[str]:
        """解析 LLM 返回的 triggers 扩展"""
        try:
            text = response.strip()
            # 提取 JSON
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(text)
            if isinstance(data, list):
                return [str(t).strip() for t in data if len(str(t).strip()) > 1]
            elif isinstance(data, dict) and "triggers" in data:
                return [str(t).strip() for t in data["triggers"] if len(str(t).strip()) > 1]
            return []
        except Exception:
            return []
    
    def _index_skill(self, skill: Skill, is_expansion: bool = False):
        """把 skill 的 triggers + description 关键词加入倒排索引"""
        words: Set[str] = set()
        
        # 从 triggers 提取关键词
        for trigger in skill.triggers:
            words.update(self._tokenize(trigger))
        
        # 从 description 提取关键词（取前 20 个有效词）
        if not is_expansion:
            # 扩展时只索引 triggers，避免重复索引 description
            words.update(self._tokenize(skill.description)[:20])
            words.update(self._tokenize(skill.name))
        
        for word in words:
            if word not in self._index:
                self._index[word] = set()
            self._index[word].add(skill.name)
    
    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """简单分词：提取 2~4 字中文滑动窗口 + 3+ 字母英文词
        
        使用滑动窗口确保短 trigger（如'架构'）能从长文本中命中。
        """
        text = text.lower()
        words = []
        
        # 中文：2~4 字滑动窗口（确保短 trigger 能命中）
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        n = len(chinese_chars)
        for length in (2, 3, 4):
            for i in range(n - length + 1):
                words.append(''.join(chinese_chars[i:i+length]))
        
        # 英文词（3+ 字母）
        english_words = re.findall(r'[a-z]{3,}', text)
        words.extend(english_words)
        
        return words
    
    @staticmethod
    def is_chitchat(text: str) -> bool:
        """判断是否是闲聊（不需要激活任何 skill）
        
        规则：
        1. 纯问候/感谢/告别短句
        2. 长度 < 8 且没有业务关键词
        3. 包含明显闲聊关键词
        """
        text = text.strip()
        if not text:
            return True
        
        # 纯模式匹配
        if _CHITCHAT_PATTERNS.match(text):
            return True
        
        # 短句检查
        if len(text) < 8:
            # 如果包含连续中文字符或英文业务词，不算闲聊
            business_hints = re.findall(r'[\u4e00-\u9fff]{2,}', text)
            english_business = re.findall(r'[a-z]{3,}', text.lower())
            if not business_hints and not english_business:
                return True
        
        # 闲聊关键词检查（只检查短句）
        if len(text) < 30:
            for kw in _CHITCHAT_KEYWORDS:
                if kw in text:
                    return True
        
        return False
    
    def _query_index(self, text: str) -> Dict[str, float]:
        """通过倒排索引查询候选 skills，返回 {skill_name: hit_count}"""
        words = self._tokenize(text)
        scores: Dict[str, int] = {}
        
        for word in words:
            for skill_name in self._index.get(word, set()):
                scores[skill_name] = scores.get(skill_name, 0) + 1
        
        return scores
    
    def _score_skill(self, skill: Skill, text: str, hit_count: int) -> float:
        """精确评分
        
        评分公式：
        - trigger 命中：每个 +0.3（核心判断依据）
        - 基础分 0.15
        - 倒排命中加成：上限 0.15
        - 上限 1.0
        """
        text_lower = text.lower()
        score = 0.15  # 基础分
        
        # trigger 精确匹配（权重最高）
        for trigger in skill.triggers:
            if trigger.lower() in text_lower:
                score += 0.3
        
        # 倒排命中次数（辅助加分）
        score += min(hit_count * 0.05, 0.15)
        
        return min(score, 1.0)
    
    async def route(self, text: str, top_k: int = 2, threshold: float = 0.35) -> List[Skill]:
        """路由：根据用户输入返回应激活的 skills
        
        FIX Phase 5: 四层路由架构
        Layer 1: 闲聊过滤 → 90% 对话
        Layer 2: 倒排索引 → 关键词命中
        Layer 3: TF-IDF 语义匹配 → 语义相近，0ms
        Layer 4: LLM 语义路由 → 真正歧义
        
        Args:
            text: 用户输入
            top_k: 最多返回几个 skill（默认 2）
            threshold: 激活阈值（默认 0.35）
        
        Returns:
            按匹配度排序的 skill 列表，空表示不需要 skill
        """
        # Layer 1: 闲聊过滤
        if self.is_chitchat(text):
            return []
        
        # 先用倒排索引快速筛选候选
        hit_counts = self._query_index(text)
        
        # 如果有高置信度命中（trigger 精确匹配），直接返回
        direct_hits = self._check_direct_trigger_hits(text, hit_counts)
        if direct_hits:
            return direct_hits[:top_k]
        
        # Layer 3: TF-IDF 语义匹配（0ms，零成本）
        tfidf_hits = self._tfidf_route(text, top_k)
        if tfidf_hits:
            return tfidf_hits
        
        # Layer 4: LLM 语义路由（真正的歧义/新表达）
        if self.llm and (not hit_counts or max(hit_counts.values()) < 2):
            return await self._semantic_route(text, top_k)
        
        # 回退：倒排索引关键词路由
        return self._keyword_route(text, top_k, threshold)
    
    def _check_direct_trigger_hits(self, text: str, hit_counts: Dict[str, int]) -> List[Skill]:
        """检查是否有 trigger 精确命中（高置信度，直接返回）"""
        text_lower = text.lower()
        direct_hits = []
        for skill_name in hit_counts:
            skill = self.skills.get(skill_name)
            if not skill:
                continue
            for trigger in skill.triggers:
                if trigger.lower() in text_lower:
                    direct_hits.append(skill)
                    break
        return direct_hits
    
    def _keyword_route(self, text: str, top_k: int, threshold: float) -> List[Skill]:
        """基于倒排索引的关键词路由（回退方案）"""
        hit_counts = self._query_index(text)
        if not hit_counts:
            return []
        
        scored = []
        for skill_name, hit_count in hit_counts.items():
            skill = self.skills.get(skill_name)
            if not skill:
                continue
            score = self._score_skill(skill, text, hit_count)
            if score >= threshold:
                scored.append((score, skill))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:top_k]]
    
    async def _semantic_route(self, text: str, top_k: int) -> List[Skill]:
        """LLM 语义路由 —— 去关键词化核心
        
        当倒排索引无法高置信度匹配时，用 LLM 做语义判断。
        输入所有 skill 的 name + description，让 LLM 选择最匹配的。
        """
        # 构造精简的 skills 列表
        skills_info = []
        for name, skill in self.skills.items():
            desc = skill.description[:80] if skill.description else ""
            skills_info.append(f"- {name}: {desc}")
        
        prompt = f"""你是 Skill 路由专家。根据用户输入，判断应激活哪些 skills。

用户输入：{text}

可用 skills：
{chr(10).join(skills_info)}

请输出 JSON：
{{"skills": ["skill_name1", "skill_name2"], "reasoning": "简要说明"}}

规则：
- 最多选 {top_k} 个 skill
- 如果用户意图不明确或不需要 skill，返回空数组 []
- 只从上面的 skills 列表中选择"""
        
        try:
            response = await self.llm.chat([
                {"role": "system", "content": "你是 Skill 路由专家，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ])
            return self._parse_semantic_response(response, top_k)
        except Exception as e:
            logger.warning(f"[SkillRouter] LLM 语义路由失败: {e}")
            return []
    
    def _parse_semantic_response(self, response: str, top_k: int) -> List[Skill]:
        """解析 LLM 语义路由的 JSON 响应"""
        try:
            text = response.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(text)
            selected = data.get("skills", [])
            
            result = []
            for name in selected[:top_k]:
                if name in self.skills:
                    result.append(self.skills[name])
            return result
        except Exception as e:
            logger.warning(f"[SkillRouter] 解析语义路由响应失败: {e}")
            return []
    
    def reload(self):
        """热重新加载"""
        self.skills.clear()
        self._index.clear()
        self._load_all()
    
    def list_skills(self) -> List[Dict]:
        """列出所有 skills"""
        return [
            {
                "name": s.name,
                "description": s.description[:80],
                "triggers": s.triggers[:5],
            }
            for s in self.skills.values()
        ]
