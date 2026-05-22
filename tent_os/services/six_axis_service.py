"""六维成长系统 —— 为AI角色建立可量化的成长维度

成长维度基于PAIMM 6维框架设计，涵盖个性、工具使用、感知等关键方向。
六维数据从两个来源融合：
1. 基础经验值（存储在 user_profiles.six_axis_exp）
2. 实时系统数据（记忆总量、任务成功率、规则数等）动态计算

核心公式: score = min(100, exp^(1/3) * 10)
"""

from enum import Enum
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path
import math
import sqlite3

from tent_os.memory.user_profile import UserProfileStore
from tent_os.logging_config import get_logger

logger = get_logger()


class GrowthDimension(Enum):
    """六维成长维度"""
    KNOWLEDGE = "knowledge"      # 认知/知识 - 学习能力、信息处理
    SKILL = "skill"              # 技能/执行 - 任务完成效率
    SOCIAL = "social"            # 社交/情商 - 用户交互亲和力
    CREATIVITY = "creativity"    # 创造力/创新 - 开放性、想象力
    TOOL_USE = "tool_use"        # 工具使用 - MCP集成、Agent调度
    AWARENESS = "awareness"      # 感知/觉知 - 摄像头视觉理解


class SixAxisService:
    """六维成长服务：追踪AI角色的6项核心能力
    
    通过用户在Tent平台上的行为自动驱动成长值变化。
    成长是系统演化记录，不是能力锁——所有功能默认全开。
    """

    # 成长增量映射: 平台行为 → 各维度增加值
    DELTA_MAP = {
        # 任务发布类
        "publish_task": {
            GrowthDimension.KNOWLEDGE: 0.5,
            GrowthDimension.CREATIVITY: 1.0,
            GrowthDimension.TOOL_USE: 0.3,
        },
        "publish_complex_requirement": {
            GrowthDimension.KNOWLEDGE: 1.5,
            GrowthDimension.CREATIVITY: 2.0,
            GrowthDimension.TOOL_USE: 1.0,
        },
        # 任务执行类
        "accept_task": {
            GrowthDimension.SKILL: 0.5,
            GrowthDimension.SOCIAL: 0.5,
        },
        "submit_verification": {
            GrowthDimension.SKILL: 1.5,
            GrowthDimension.TOOL_USE: 0.8,
        },
        # 任务完成获奖（高好评）
        "task_passed_with_praise": {
            GrowthDimension.SKILL: 2.5,
            GrowthDimension.SOCIAL: 4.0,
            GrowthDimension.KNOWLEDGE: 1.0,
        },
        # 任务失败（少量成长，避免惩罚感）
        "task_failed": {
            GrowthDimension.SKILL: 0.3,
            GrowthDimension.KNOWLEDGE: 0.5,
        },
        # 视觉感知相关
        "camera_scan_success": {
            GrowthDimension.AWARENESS: 1.5,
            GrowthDimension.TOOL_USE: 0.5,
        },
        "emotion_detected": {
            GrowthDimension.AWARENESS: 1.0,
            GrowthDimension.SOCIAL: 1.5,
        },
        # 对话交互
        "chat_message": {
            GrowthDimension.SOCIAL: 0.1,
            GrowthDimension.KNOWLEDGE: 0.05,
        },
        # 工具调用
        "tool_call_success": {
            GrowthDimension.TOOL_USE: 0.5,
            GrowthDimension.SKILL: 0.3,
        },
        # 记忆摄入
        "memory_ingested": {
            GrowthDimension.KNOWLEDGE: 0.2,
        },
    }

    @staticmethod
    def _exp_to_score(exp: float) -> tuple:
        """经验值 → 0-100评分 + 等级
        
        level = ⌊exp^(1/3)⌋ 立方根曲线，初期成长快、后期趋缓
        """
        score = round(min(100, math.pow(max(0, exp), 1 / 3) * 10), 1)
        level = int(score // 10) + 1
        next_needed = ((level + 1) ** 3 - level ** 3) if level < 10 else 0
        return score, min(level, 10), next_needed

    @classmethod
    def update_by_task_action(
        cls,
        user_id: str,
        task_action: str,
        task_data: Optional[Dict] = None
    ) -> Dict:
        """根据用户在Tent平台完成的任务动作，更新AI角色的六维属性
        
        Returns:
            更新后的六维经验值字典
        """
        store = UserProfileStore()
        delta = cls.DELTA_MAP.get(task_action, {})
        
        for dim, d in delta.items():
            # 可以在这里根据task_data做动态调整（如复杂度加成）
            multiplier = 1.0
            if task_data:
                complexity = task_data.get("complexity", 1.0)
                multiplier = max(0.5, min(3.0, complexity))
            store.update_six_axis(user_id, dim.value, d * multiplier)
        
        return store.get_six_axis(user_id)

    @classmethod
    def get_radar_data(cls, user_id: str) -> Dict:
        """获取六维雷达图数据，融合存储值与实时系统数据
        
        Returns:
            {
                "knowledge": {"exp": 120, "score": 49.3, "level": 5, "next_level_exp_needed": 91},
                ...
            }
        """
        store = UserProfileStore()
        base_exp = store.get_six_axis(user_id)
        
        # 用现有系统实时数据增强
        enhanced = cls._enhance_with_realtime_data(user_id, base_exp)
        
        result = {}
        for dim in GrowthDimension:
            exp = enhanced.get(dim.value, 0)
            score, level, next_needed = cls._exp_to_score(exp)
            result[dim.value] = {
                "exp": round(exp, 1),
                "score": score,
                "level": level,
                "next_level_exp_needed": next_needed,
            }
        return result

    @classmethod
    def get_summary(cls, user_id: str) -> Dict:
        """获取六维成长摘要（用于前端展示）"""
        radar = cls.get_radar_data(user_id)
        total_exp = sum(v["exp"] for v in radar.values())
        avg_score = sum(v["score"] for v in radar.values()) / 6
        max_dim = max(radar, key=lambda k: radar[k]["score"])
        min_dim = min(radar, key=lambda k: radar[k]["score"])
        
        return {
            "radar": radar,
            "total_exp": round(total_exp, 1),
            "avg_score": round(avg_score, 1),
            "max_dimension": max_dim,
            "min_dimension": min_dim,
            "title": cls._get_title(avg_score),
        }

    @staticmethod
    def _get_title(avg_score: float) -> str:
        """根据平均分返回称号"""
        if avg_score >= 90:
            return "传说"
        if avg_score >= 80:
            return "大师"
        if avg_score >= 70:
            return "专家"
        if avg_score >= 60:
            return "资深"
        if avg_score >= 50:
            return "熟练"
        if avg_score >= 40:
            return "进阶"
        if avg_score >= 30:
            return "中级"
        if avg_score >= 20:
            return "初级"
        if avg_score >= 10:
            return "入门"
        return "新手"

    @classmethod
    def _enhance_with_realtime_data(cls, user_id: str, base_exp: Dict) -> Dict:
        """用现有系统数据增强六维经验值
        
        核心原则：成长反映系统真实演化，不是虚假数字。
        """
        enhanced = dict(base_exp)
        mem_path = Path("./tent_memory")
        
        try:
            # KNOWLEDGE: 记忆总量 + 图谱节点
            total_memories = 0
            graph_nodes = 0
            if (mem_path / "index.db").exists():
                try:
                    conn = sqlite3.connect(str(mem_path / "index.db"))
                    # FIX: 之前查询 `memories` 表（该表不存在），实际数据在 `l0_index` 中
                    total_memories = conn.execute("SELECT COUNT(*) FROM l0_index").fetchone()[0]
                    conn.close()
                except Exception:
                    pass
            if (mem_path / "graph.db").exists():
                try:
                    conn = sqlite3.connect(str(mem_path / "graph.db"))
                    graph_nodes = conn.execute("SELECT COUNT(*) FROM memory_nodes").fetchone()[0]
                    conn.close()
                except Exception:
                    pass
            enhanced["knowledge"] = enhanced.get("knowledge", 0) + total_memories * 0.5 + graph_nodes * 0.3
            
            # SKILL: 从scheduler.db统计任务成功率
            completed_tasks = 0
            failed_tasks = 0
            if Path("./tent_scheduler.db").exists():
                try:
                    conn = sqlite3.connect("./tent_scheduler.db")
                    row = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'").fetchone()
                    completed_tasks = row[0] if row else 0
                    row = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'failed'").fetchone()
                    failed_tasks = row[0] if row else 0
                    conn.close()
                except Exception:
                    pass
            total = completed_tasks + failed_tasks
            success_rate = completed_tasks / total if total > 0 else 1.0
            enhanced["skill"] = enhanced.get("skill", 0) + completed_tasks * 2.0 * success_rate
            
            # SOCIAL: 用户好评率
            profile = UserProfileStore().get_or_create(user_id)
            pos = profile.feedback_positive
            neg = profile.feedback_negative
            total_fb = pos + neg
            if total_fb > 0:
                enhanced["social"] = enhanced.get("social", 0) + pos * 3.0 + (pos / total_fb) * 10.0
            
            # CREATIVITY: 程序记忆规则数 + skills数
            rules_count = 0
            if (mem_path / "procedural.db").exists():
                try:
                    conn = sqlite3.connect(str(mem_path / "procedural.db"))
                    row = conn.execute("SELECT COUNT(*) FROM procedural_rules").fetchone()
                    rules_count = row[0] if row else 0
                    conn.close()
                except Exception:
                    pass
            skills_count = 0
            skills_dir = Path("./skills")
            if skills_dir.exists():
                skills_count = len(list(skills_dir.glob("*/SKILL.md")))
            enhanced["creativity"] = enhanced.get("creativity", 0) + rules_count * 1.5 + skills_count * 5.0
            
            # TOOL_USE: skills数作为代理指标（MVP），Phase 5后从audit.db精确统计
            enhanced["tool_use"] = enhanced.get("tool_use", 0) + skills_count * 3.0
            
            # AWARENESS: 基础值为主，Phase 3接入摄像头后增强
            enhanced["awareness"] = enhanced.get("awareness", 0)
            
        except Exception as e:
            logger.warning(f"[SixAxis] 实时数据增强失败: {e}")
        
        # 基础能力保底：AI 一上来就是功能完备的六边形战士
        # 每项维度给予基础经验值，确保 score ≈ 25（level 3）
        BASE_EXP = 15.0
        for dim in GrowthDimension:
            if enhanced.get(dim.value, 0) < BASE_EXP:
                enhanced[dim.value] = BASE_EXP
        
        return enhanced
