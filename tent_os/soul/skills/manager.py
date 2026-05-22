"""Agent 技能树管理器

职责：
1. 为每个 Agent 初始化技能树（基于角色）
2. 完成任务后奖励 XP
3. 自动升级判定和解锁子技能
4. 持久化技能数据到 SQLite
5. 为调度器提供技能权重加成
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from tent_os.soul.skills.skill_tree import SkillNode, get_skill_tree, get_default_tree

logger = logging.getLogger("tent_os.skills")


class AgentSkillManager:
    """Agent 技能管理器"""

    def __init__(self, db_path: str = "./tent_memory/agents/agent_skills.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化技能数据库"""
        with sqlite3.connect(self.db_path) as conn:
            # 技能树表：每个Agent的每个技能一行
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_skills (
                    agent_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    skill_name TEXT,
                    level INTEGER DEFAULT 1,
                    current_xp INTEGER DEFAULT 0,
                    max_level INTEGER DEFAULT 5,
                    parent_id TEXT,
                    children_ids TEXT,  -- JSON array
                    unlocked INTEGER DEFAULT 1,  -- 0=锁定, 1=解锁
                    unlocked_at TEXT,
                    category TEXT,
                    icon TEXT,
                    weight_bonus REAL DEFAULT 0.05,
                    PRIMARY KEY (agent_id, skill_id)
                )
            """)
            # XP 日志表：记录每次经验值来源
            conn.execute("""
                CREATE TABLE IF NOT EXISTS xp_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    skill_id TEXT,
                    xp_delta INTEGER NOT NULL,
                    source TEXT,  -- task_complete / meeting_contrib / heartbeat_growth
                    reason TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_xp_agent ON xp_logs(agent_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_xp_created ON xp_logs(created_at)")
            conn.commit()

    def init_agent_skills(self, agent_id: str, role: str) -> bool:
        """为 Agent 初始化技能树
        
        Args:
            agent_id: Agent ID
            role: 角色类型（tech_lead / product_manager / sci-fi novelist）
        """
        tree = get_skill_tree(role) or get_default_tree()
        if not tree:
            return False
        
        with sqlite3.connect(self.db_path) as conn:
            for skill_id, node in tree.items():
                conn.execute(
                    """INSERT OR REPLACE INTO agent_skills
                       (agent_id, skill_id, skill_name, level, current_xp, max_level,
                        parent_id, children_ids, unlocked, unlocked_at, category, icon, weight_bonus)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)""",
                    (
                        agent_id, skill_id, node.name, node.level, node.current_xp, node.max_level,
                        node.parent_id, json.dumps(node.children_ids),
                        1 if node.parent_id is None else 0,  # root技能默认解锁，子技能锁定
                        node.category, node.icon, node.weight_bonus_per_level,
                    )
                )
            conn.commit()
        logger.info(f"[SkillManager] Agent {agent_id} 技能树已初始化（角色: {role}）")
        return True

    def get_agent_skills(self, agent_id: str) -> List[Dict]:
        """获取 Agent 的所有技能"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM agent_skills WHERE agent_id = ? ORDER BY skill_id",
                (agent_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_skill(self, agent_id: str, skill_id: str) -> Optional[Dict]:
        """获取单个技能详情"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM agent_skills WHERE agent_id = ? AND skill_id = ?",
                (agent_id, skill_id)
            ).fetchone()
            return dict(row) if row else None

    def add_xp(self, agent_id: str, skill_id: str, xp: int, source: str = "task", reason: str = "") -> Dict:
        """为 Agent 的指定技能增加 XP，自动判定升级
        
        Returns:
            {"upgraded": bool, "new_level": int, "old_level": int, "skill_id": str, "xp_added": int}
        """
        skill = self.get_skill(agent_id, skill_id)
        if not skill:
            return {"upgraded": False, "error": "Skill not found"}
        
        old_level = skill["level"]
        new_xp = skill["current_xp"] + xp
        max_level = skill["max_level"]
        
        # 获取该技能的升级阈值（从技能树配置中读取）
        tree = get_skill_tree(skill.get("category", "")) or get_default_tree()
        node = tree.get(skill_id)
        xp_required = node.xp_required if node else [100, 300, 600, 1000]
        
        # 判定升级
        new_level = old_level
        while new_level < max_level and new_level - 1 < len(xp_required) and new_xp >= xp_required[new_level - 1]:
            new_level += 1
        
        with sqlite3.connect(self.db_path) as conn:
            # 更新技能（获得XP即视为已解锁）
            conn.execute(
                "UPDATE agent_skills SET level = ?, current_xp = ?, unlocked = 1 WHERE agent_id = ? AND skill_id = ?",
                (new_level, new_xp, agent_id, skill_id)
            )
            # 记录 XP 日志
            conn.execute(
                "INSERT INTO xp_logs (agent_id, skill_id, xp_delta, source, reason) VALUES (?, ?, ?, ?, ?)",
                (agent_id, skill_id, xp, source, reason)
            )
            conn.commit()
        
        result = {
            "upgraded": new_level > old_level,
            "new_level": new_level,
            "old_level": old_level,
            "skill_id": skill_id,
            "skill_name": skill["skill_name"],
            "xp_added": xp,
            "total_xp": new_xp,
        }
        
        # 如果升级了，尝试解锁子技能
        if new_level > old_level:
            unlocked = self._try_unlock_children(agent_id, skill_id, new_level)
            result["unlocked_skills"] = unlocked
            logger.info(f"[SkillManager] {agent_id} 的 {skill['skill_name']} 升级: {old_level} -> {new_level}")
        
        return result

    def add_xp_by_task(self, agent_id: str, task_type: str, task_quality: float = 1.0) -> List[Dict]:
        """根据任务类型自动分配 XP 到相关技能
        
        Args:
            task_type: 任务类型标识（如 "architecture", "code_review", "prd_writing"）
            task_quality: 任务质量系数（0.5-2.0）
        
        Returns:
            所有升级结果的列表
        """
        # 任务类型 -> 技能映射
        task_skill_map = {
            "architecture": [("architecture", 50), ("cloud_native", 30), ("high_concurrency", 30)],
            "cloud": [("cloud_native", 50), ("microservices", 30), ("container_orchestration", 30)],
            "code": [("code_review", 50), ("security_audit", 20), ("performance_opt", 20)],
            "security": [("security_audit", 60), ("code_review", 20)],
            "performance": [("performance_opt", 60), ("code_review", 20)],
            "tech_selection": [("tech_selection", 50), ("database_selection", 30), ("framework_selection", 30)],
            "tech": [("architecture", 40), ("code_review", 30), ("tech_selection", 30)],
            "product": [("requirement_analysis", 40), ("prd_writing", 40), ("competitive_analysis", 30)],
            "requirement": [("requirement_analysis", 50), ("user_story", 30)],
            "competitive": [("competitive_analysis", 50), ("market_positioning", 30)],
            "user_research": [("user_research", 50), ("data_analysis", 30)],
            "writing": [("world_building", 40), ("narrative", 40), ("character_design", 30)],
            "world_building": [("world_building", 50), ("hard_science", 30), ("alien_civilization", 30)],
            "narrative": [("narrative", 50), ("long_form", 30), ("multi_pov", 30)],
            "character": [("character_design", 50), ("dialogue_craft", 30)],
            "general": [("reasoning", 30), ("communication", 30)],
        }
        
        mappings = task_skill_map.get(task_type, task_skill_map.get("general", []))
        results = []
        
        for skill_id, base_xp in mappings:
            xp = int(base_xp * task_quality)
            if xp > 0:
                result = self.add_xp(agent_id, skill_id, xp, source="task", reason=f"完成任务: {task_type}")
                if result.get("upgraded"):
                    results.append(result)
        
        return results

    def get_skill_weight_bonus(self, agent_id: str) -> float:
        """获取 Agent 的总技能权重加成（用于调度器评分）"""
        skills = self.get_agent_skills(agent_id)
        total_bonus = 0.0
        for s in skills:
            if s.get("unlocked"):
                total_bonus += (s.get("level", 1) - 1) * s.get("weight_bonus", 0.05)
        return total_bonus

    def get_agent_stats(self, agent_id: str) -> Dict:
        """获取 Agent 技能统计"""
        skills = self.get_agent_skills(agent_id)
        unlocked = [s for s in skills if s.get("unlocked")]
        total_xp = sum(s.get("current_xp", 0) for s in skills)
        avg_level = sum(s.get("level", 1) for s in unlocked) / max(len(unlocked), 1)
        
        return {
            "total_skills": len(skills),
            "unlocked_skills": len(unlocked),
            "total_xp": total_xp,
            "avg_level": round(avg_level, 2),
            "weight_bonus": self.get_skill_weight_bonus(agent_id),
            "skills": skills,
        }

    def get_xp_history(self, agent_id: str, limit: int = 50) -> List[Dict]:
        """获取 XP 获取历史"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM xp_logs WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
                (agent_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def _try_unlock_children(self, agent_id: str, parent_skill_id: str, parent_level: int) -> List[str]:
        """尝试解锁子技能"""
        unlocked = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # 查找所有锁定且父技能匹配的技能
            rows = conn.execute(
                "SELECT skill_id, skill_name, parent_id, unlocked FROM agent_skills WHERE agent_id = ? AND unlocked = 0",
                (agent_id,)
            ).fetchall()
            for row in rows:
                if row["parent_id"] == parent_skill_id and parent_level >= 2:
                    conn.execute(
                        "UPDATE agent_skills SET unlocked = 1, unlocked_at = datetime('now') WHERE agent_id = ? AND skill_id = ?",
                        (agent_id, row["skill_id"])
                    )
                    unlocked.append(row["skill_name"])
            conn.commit()
        if unlocked:
            logger.info(f"[SkillManager] {agent_id} 解锁新技能: {', '.join(unlocked)}")
        return unlocked

    def reset_agent_skills(self, agent_id: str) -> bool:
        """重置 Agent 的所有技能（保留技能树结构，等级重置为1）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM agent_skills WHERE agent_id = ?", (agent_id,))
                conn.execute("DELETE FROM xp_logs WHERE agent_id = ?", (agent_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[SkillManager] 重置技能失败: {e}")
            return False
