"""关系提取器 —— 从对话中自动识别人际关系

核心设计：
- 零硬编码人名列表，从对话中自然涌现
- 快速路径：正则模式匹配中文姓名 + 关系词
- 深度路径：LLM 异步提取（不阻塞对话流）
- 所有结果存入认知图谱，可修正、可演进

关系类型（从对话中推断，不是预设标签）：
- family: 儿子/女儿/父亲/母亲/妻子/丈夫/兄弟/姐妹
- friend: 朋友/闺蜜/哥们/挚友
- colleague: 同事/搭档/合伙人
- partner: 男朋友/女朋友/未婚夫/未婚妻
- acquaintance: 邻居/同学/老乡
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from tent_os.memory.graph import CognitiveGraph, MemoryNode, MemoryEdge

logger = logging.getLogger("tent_os.soul.relation")


# 中文常见姓氏（用于快速识别可能的姓名）
COMMON_SURNAMES = set(
    "王李张刘陈杨黄赵周吴徐孙马朱胡郭何林罗高郑梁谢宋唐许韩冯邓曹彭曾肖田董潘袁蔡蒋余于杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏付方白邹孟熊秦邱江尹薛闫段雷侯龙史黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
)

# 关系词映射：从自然语言 → 关系类型
# 支持从环境变量/配置文件覆盖，适应不同文化背景的关系表达
import os

def _load_relation_patterns():
    """加载关系模式。可从环境变量 TENT_RELATION_PATTERNS_JSON 覆盖。"""
    env = os.environ.get("TENT_RELATION_PATTERNS_JSON", "")
    if env:
        try:
            return [(r["pattern"], r["type"], r["label"]) for r in json.loads(env)]
        except Exception:
            logger.warning("[RelationExtractor] 环境变量 TENT_RELATION_PATTERNS_JSON 格式错误，使用默认")
    
    return [
        # (正则模式, 关系类型, 关系名称提取组)
        (r"我(?:的)?(儿子|女儿|孩子)", "family", "child"),
        (r"我(?:的)?(爸爸|父亲|老爸|爹)", "family", "father"),
        (r"我(?:的)?(妈妈|母亲|老妈|娘)", "family", "mother"),
        (r"我(?:的)?(妻子|老婆|媳妇|太太)", "family", "wife"),
        (r"我(?:的)?(丈夫|老公|先生)", "family", "husband"),
        (r"我(?:的)?(兄弟|哥哥|弟弟|哥|弟)", "family", "brother"),
        (r"我(?:的)?(姐妹|姐姐|妹妹|姐|妹)", "family", "sister"),
        (r"我(?:的)?(朋友|好友|闺蜜|哥们|挚友|死党)", "friend", "friend"),
        (r"我(?:的)?(同事|搭档|合伙人| teammate)", "colleague", "colleague"),
        (r"我(?:的)?(男朋友|男友|女朋友|女友|未婚夫|未婚妻)", "partner", "partner"),
        (r"我(?:的)?(邻居|同学|老乡|校友)", "acquaintance", "acquaintance"),
        # 反向识别：X是我的Y
        (r"([\u4e00-\u9fa5]{2,3})是(?:我(?:的)?)?[\u4e00-\u9fa5]{0,4}(儿子|女儿|孩子)", "family", "child_reverse"),
        (r"([\u4e00-\u9fa5]{2,3})是(?:我(?:的)?)?[\u4e00-\u9fa5]{0,4}(爸爸|父亲|老爸)", "family", "father_reverse"),
        (r"([\u4e00-\u9fa5]{2,3})是(?:我(?:的)?)?[\u4e00-\u9fa5]{0,4}(妈妈|母亲|老妈)", "family", "mother_reverse"),
        (r"([\u4e00-\u9fa5]{2,3})是(?:我(?:的)?)?[\u4e00-\u9fa5]{0,4}(妻子|老婆|媳妇)", "family", "wife_reverse"),
        (r"([\u4e00-\u9fa5]{2,3})是(?:我(?:的)?)?[\u4e00-\u9fa5]{0,4}(丈夫|老公)", "family", "husband_reverse"),
        (r"([\u4e00-\u9fa5]{2,3})是(?:我(?:的)?)?[\u4e00-\u9fa5]{0,4}(朋友|好友|闺蜜|哥们|挚友)", "friend", "friend_reverse"),
        (r"([\u4e00-\u9fa5]{2,3})是(?:我(?:的)?)?[\u4e00-\u9fa5]{0,4}(同事|搭档|合伙人)", "colleague", "colleague_reverse"),
    ]

RELATION_PATTERNS = _load_relation_patterns()


class RelationExtractor:
    """从对话文本中提取实体（人名）和人际关系"""
    
    def __init__(self, graph: Optional[CognitiveGraph] = None, llm=None):
        self.graph = graph
        self.llm = llm
        # 用户中心节点 ID
        self.user_center_id = "entity://user/self"
    
    def extract_from_text(self, text: str, user_id: str = "web_user",
                          session_id: str = "", source_chunk: str = "") -> Dict:
        """从单条文本中提取实体和关系
        
        Returns:
            {"entities": [...], "relations": [...]}
        """
        entities = self._fast_extract_entities(text)
        relations = self._fast_extract_relations(text, user_id)
        
        return {
            "entities": entities,
            "relations": relations,
            "text_preview": text[:100],
        }
    
    def _fast_extract_entities(self, text: str) -> List[Dict]:
        """快速实体识别：中文姓名 + 可能的昵称"""
        entities = []
        seen = set()
        
        # 1. 识别 "我XXX" 模式中的称呼（通常是人名）
        # 例如："我儿子张三今天考试" → 张三
        # 使用更精确的正则：匹配2-3字人名，后面接标点/非汉字/句尾
        for m in re.finditer(r"我(?:的)?(?:儿子|女儿|孩子|爸爸|妈妈|妻子|丈夫|朋友|同事|同学)[，,、]?\s*([\u4e00-\u9fa5]{2,3}?)", text):
            name = m.group(1)
            if name not in seen and self._is_likely_name(name, allow_uncommon=True):
                seen.add(name)
                entities.append({
                    "name": name,
                    "confidence": 0.6 if self._is_likely_name(name) else 0.4,
                    "source": "context_pattern",
                    "span": m.span(),
                })
        
        # 2. 识别 "XXX是我的YYY" 模式
        for m in re.finditer(r"([\u4e00-\u9fa5]{2,3}?)是(?:我(?:的)?)?[\u4e00-\u9fa5]{0,4}(?:儿子|女儿|孩子|爸爸|妈妈|妻子|丈夫|朋友|同事|同学)", text):
            name = m.group(1)
            if self._is_likely_name(name) and name not in seen:
                seen.add(name)
                entities.append({
                    "name": name,
                    "confidence": 0.7,
                    "source": "reverse_pattern",
                    "span": m.span(),
                })
        
        # 3. 识别 "和XXX一起" 模式（可能是人名）
        for m in re.finditer(r"和([\u4e00-\u9fa5]{2,3}?)(?:一起|聊天|吃饭|见面|出差)", text):
            name = m.group(1)
            if self._is_likely_name(name) and name not in seen:
                seen.add(name)
                entities.append({
                    "name": name,
                    "confidence": 0.5,
                    "source": "companion_pattern",
                    "span": m.span(),
                })
        
        # 4. 识别重复出现的2-3字词（可能是人名或昵称）
        # 这里用简单的频率启发：如果某个2-3字组合在对话中多次出现，可能是人名
        # 但为了零硬编码，我们不在这里做频率分析，留给后续 LLM 深度提取
        
        return entities
    
    def _fast_extract_relations(self, text: str, user_id: str) -> List[Dict]:
        """快速关系提取：基于关系词模式"""
        relations = []
        
        for pattern, rel_type, rel_name in RELATION_PATTERNS:
            for m in re.finditer(pattern, text):
                groups = m.groups()
                if len(groups) >= 2 and "reverse" in rel_name:
                    # 反向模式："张三是我儿子" → 张三 -child→ 我
                    entity_name = groups[0]
                    relation_label = groups[1]
                    relations.append({
                        "source_name": entity_name,
                        "target_name": "__user__",
                        "relation_type": rel_type,
                        "relation_label": relation_label,
                        "confidence": 0.65,
                        "source": "reverse_pattern",
                        "evidence": text[m.start():m.end()],
                    })
                else:
                    # 正向模式："我儿子张三" → 我 -child→ 张三（需要从上下文推断人名）
                    relation_label = groups[0]
                    # 正向模式只记录关系类型，人名需要从上下文提取
                    # 这里我们标记为"待关联实体"
                    relations.append({
                        "source_name": "__user__",
                        "target_name": "__pending__",  # 需要在后续关联实体
                        "relation_type": rel_type,
                        "relation_label": relation_label,
                        "confidence": 0.5,
                        "source": "forward_pattern",
                        "evidence": text[m.start():m.end()],
                    })
        
        return relations
    
    def _is_likely_name(self, text: str, allow_uncommon: bool = False) -> bool:
        """判断一个字符串是否可能是中文姓名
        
        Args:
            text: 候选字符串
            allow_uncommon: 是否允许非常见姓氏（如昵称"小红"）
        """
        if not text or len(text) < 2 or len(text) > 4:
            return False
        # 排除常见非人名词
        exclude_words = {"我们", "我的", "他们", "她们", "人们", "大家", "公司", "工作", "今天", "明天", "昨天", "现在", "时候", "可能", "觉得", "认为", "知道", "非常", "特别", "其实", "还是", "但是", "因为", "所以", "然后", "那么", "这样", "那个", "这个", "什么", "怎么", "为什么", "帮我", "给他", "让她", "叫你", "问他", "她说", "他说", "我说", "来了", "去了", "走过", "看过", "吃过", "用过", "想着", "看着", "听着", "感觉", "心里", "身体", "家庭", "学校", "老师", "医生", "医院", "学生"}
        if text in exclude_words:
            return False
        # 首字是常见姓氏
        if text[0] in COMMON_SURNAMES:
            return True
        # 允许非常见姓氏（如昵称）
        if allow_uncommon:
            # 2-3字，纯汉字，不在排除词中即可
            return bool(re.match(r"^[\u4e00-\u9fa5]{2,3}$", text))
        return False
    
    def associate_entities_with_relations(self, entities: List[Dict],
                                           relations: List[Dict],
                                           text: str) -> List[Dict]:
        """将提取的实体与关系进行关联"""
        # 简单启发式：如果关系中有 __pending__，尝试用最近提取的实体填充
        entity_names = [e["name"] for e in entities]
        
        for rel in relations:
            if rel.get("target_name") == "__pending__":
                # 在关系的 evidence 附近寻找人名
                evidence = rel.get("evidence", "")
                # 找到 evidence 在原文中的位置
                pos = text.find(evidence)
                if pos >= 0:
                    # 在 evidence 前后 20 字内找人名
                    window = text[max(0, pos-20):min(len(text), pos+len(evidence)+20)]
                    for ent in entities:
                        if ent["name"] in window:
                            rel["target_name"] = ent["name"]
                            rel["confidence"] = min(0.8, rel["confidence"] + 0.15)
                            break
        
        return relations
    
    def save_to_graph(self, entities: List[Dict], relations: List[Dict],
                      user_id: str = "web_user", session_id: str = "",
                      source_chunk: str = "") -> Dict:
        """将提取的实体和关系存入认知图谱
        
        Returns:
            {"nodes_added": int, "edges_added": int, "errors": []}
        """
        if not self.graph:
            return {"nodes_added": 0, "edges_added": 0, "errors": ["graph not initialized"]}
        
        result = {"nodes_added": 0, "edges_added": 0, "errors": []}
        
        # 1. 确保用户中心节点存在
        user_node = MemoryNode(
            id=self.user_center_id,
            content=f"用户 {user_id}",
            content_hash=hashlib.md5(self.user_center_id.encode()).hexdigest(),
            confidence=1.0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            source_session=session_id,
            source_chunk=source_chunk,
            memory_type="entity",
        )
        self.graph.add_node(user_node)
        
        # 2. 添加实体节点
        entity_id_map = {self.user_center_id: "__user__"}
        for ent in entities:
            name = ent["name"]
            node_id = f"entity://person/{name}"
            entity_id_map[name] = node_id
            
            node = MemoryNode(
                id=node_id,
                content=name,
                content_hash=hashlib.md5(name.encode()).hexdigest(),
                confidence=ent.get("confidence", 0.5),
                created_at=datetime.now(),
                updated_at=datetime.now(),
                source_session=session_id,
                source_chunk=source_chunk,
                memory_type="entity",
            )
            if self.graph.add_node(node):
                result["nodes_added"] += 1
        
        # 3. 添加关系边
        # 预构建实体列表，用于解析 __pending__ 目标
        pending_targets = [ent["name"] for ent in entities if "name" in ent]
        
        for rel in relations:
            source_name = rel.get("source_name", "")
            target_name = rel.get("target_name", "")
            
            if source_name == "__user__":
                source_id = self.user_center_id
            else:
                source_id = entity_id_map.get(source_name)
            
            if target_name == "__user__":
                target_id = self.user_center_id
            elif target_name == "__pending__" and pending_targets:
                # 正向模式（如"我儿子张三"）：将 pending 关联到最近提取的实体
                target_id = entity_id_map.get(pending_targets[0])
            else:
                target_id = entity_id_map.get(target_name)
            
            if not source_id or not target_id or source_id == target_id:
                continue
            
            edge = MemoryEdge(
                source_id=source_id,
                target_id=target_id,
                relation_type=rel.get("relation_type", "related"),
                strength=rel.get("confidence", 0.5),
                evidence=rel.get("evidence", "")[:200],
                created_at=datetime.now(),
            )
            if self.graph.add_edge(edge):
                result["edges_added"] += 1
        
        return result
    
    async def extract_deep(self, text: str, user_id: str = "web_user",
                           session_id: str = "") -> Dict:
        """深度提取：使用 LLM 提取丰富的实体和关系
        
        扩展提取范围：不仅是人际关系，还包括技术概念、项目、产品、
        偏好、决策、目标等。聚合多回合上下文，发现隐含关联。
        """
        if not self.llm:
            return {"entities": [], "relations": [], "source": "no_llm"}
        
        prompt = (
            f"从以下对话中提取关键实体和它们之间的关系。只返回 JSON，不要其他内容。\n\n"
            f"文本（可能包含多个对话回合，用 --- 分隔）：\n{text[:2000]}\n\n"
            f"实体类型（必须标注）：\n"
            f"- person: 人名、昵称、角色称呼\n"
            f"- concept: 技术概念、方法论、理论\n"
            f"- technology: 具体技术、框架、工具、语言\n"
            f"- project: 项目名称、代码仓库、产品线\n"
            f"- product: 产品名、服务名、平台名\n"
            f"- organization: 公司、团队、组织、社区\n"
            f"- location: 地点、城市、国家\n"
            f"- preference: 用户的偏好、兴趣、习惯、厌恶\n"
            f"- decision: 用户做的决定、选择、判断\n"
            f"- goal: 目标、计划、意图、愿望\n"
            f"- event: 具体事件、会议、里程碑\n\n"
            f"关系类型：\n"
            f"- family/friend/colleague/partner: 人际关系\n"
            f"- related: 一般关联、提及\n"
            f"- uses: 使用、依赖（A uses B）\n"
            f"- part_of: 属于的一部分（A part_of B）\n"
            f"- created_by: 被创建（A created_by B）\n"
            f"- depends_on: 依赖（A depends_on B）\n"
            f"- opposes: 反对、对立（A opposes B）\n"
            f"- precedes: 在...之前发生（A precedes B）\n"
            f"- has_preference: 有偏好（人 has_preference 事物）\n"
            f"- made_decision: 做了决定（人 made_decision 决策）\n"
            f"- has_goal: 有目标（人 has_goal 目标）\n\n"
            f"要求：\n"
            f"1. 提取所有有意义的实体，不要遗漏技术术语、项目名、产品名\n"
            f"2. 发现实体之间的隐含关系（即使对话中没有明确说'是'）\n"
            f"3. 跨回合关联：如果多个回合提到同一主题，建立关系\n"
            f"4. 置信度 0-1\n"
            f"5. 如果没有明确关系，只返回 entities，relations 可为空\n\n"
            f"返回格式：\n"
            f'{{"entities": [{{"name": "张三", "type": "person", "confidence": 0.9}}], '
            f'"relations": [{{"source": "张三", "target": "李四", "type": "colleague", "label": "同事", "confidence": 0.85}}]}}'
        )
        
        try:
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm.chat(
                messages, temperature=0.3, max_tokens=800, thinking={"type": "disabled"}
            )
            # 移除可能的 Markdown 代码块标记
            clean = response.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
            data = json.loads(clean)
            entities = data.get("entities", [])
            relations = data.get("relations", [])
            # 标准化实体格式
            normalized_entities = []
            for e in entities:
                if isinstance(e, dict) and "name" in e:
                    normalized_entities.append({
                        "name": e["name"],
                        "type": e.get("type", "entity"),
                        "confidence": e.get("confidence", 0.5),
                    })
            # 标准化关系格式
            normalized_relations = []
            for r in relations:
                if isinstance(r, dict) and "source" in r and "target" in r:
                    normalized_relations.append({
                        "source": r["source"],
                        "target": r["target"],
                        "type": r.get("type", "related"),
                        "label": r.get("label", r.get("type", "关联")),
                        "confidence": r.get("confidence", 0.5),
                    })
            return {
                "entities": normalized_entities,
                "relations": normalized_relations,
                "source": "llm_deep",
            }
        except Exception as e:
            logger.debug(f"[RelationExtractor] LLM 深度提取失败: {e}")
            return {"entities": [], "relations": [], "source": "llm_error"}
