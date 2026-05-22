"""Agent 管理器 —— Multi-Agent System 的核心管理模块"""

import sqlite3
import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from tent_os.soul.agent_models import AgentConfig, AgentState, AgentRoom, AgentMessage, get_role_template
from tent_os.logging_config import get_logger

logger = get_logger()


class AgentManager:
    """Agent 管理器：负责 Agent 的CRUD、状态管理和运行时调度"""

    def __init__(self, storage_path: str = "./tent_memory/agents"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_path / "agents.db"
        self._init_db()
        self._state_cache: Dict[str, AgentState] = {}

    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    config JSON NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_by TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_agents_created_by ON agents(created_by);
                CREATE INDEX IF NOT EXISTS idx_agents_role ON agents(role);

                CREATE TABLE IF NOT EXISTS agent_rooms (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    topic TEXT,
                    participants JSON,
                    host_agent_id TEXT,
                    status TEXT DEFAULT 'idle',
                    summary TEXT,
                    created_by TEXT,
                    created_at TEXT,
                    closed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS agent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT,
                    from_agent_id TEXT,
                    to_agent_id TEXT,
                    message_type TEXT DEFAULT 'text',
                    content TEXT,
                    metadata JSON,
                    created_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_messages_room ON agent_messages(room_id);
                CREATE INDEX IF NOT EXISTS idx_messages_from ON agent_messages(from_agent_id);

                -- P5: Agent间关系与协作网络
                CREATE TABLE IF NOT EXISTS agent_relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_a_id TEXT NOT NULL,
                    agent_b_id TEXT NOT NULL,
                    relationship_type TEXT DEFAULT 'collaborator',
                    trust_score REAL DEFAULT 0.5,
                    collaboration_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    last_interaction TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(agent_a_id, agent_b_id)
                );
                CREATE INDEX IF NOT EXISTS idx_rel_a ON agent_relationships(agent_a_id);
                CREATE INDEX IF NOT EXISTS idx_rel_b ON agent_relationships(agent_b_id);

                CREATE TABLE IF NOT EXISTS agent_collaboration_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_a_id TEXT NOT NULL,
                    agent_b_id TEXT NOT NULL,
                    room_id TEXT,
                    task_type TEXT,
                    result TEXT,
                    quality_score REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_colab_a ON agent_collaboration_logs(agent_a_id);
                CREATE INDEX IF NOT EXISTS idx_colab_b ON agent_collaboration_logs(agent_b_id);
            """)

    # ========== Agent CRUD ==========

    def create_agent(self, config: AgentConfig) -> AgentConfig:
        """创建新 Agent"""
        config.updated_at = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO agents (id, name, role, config, is_active, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (config.id, config.name, config.role,
                 json.dumps(config.to_dict(), ensure_ascii=False),
                 1 if config.is_active else 0,
                 config.created_by, config.created_at, config.updated_at)
            )
        logger.info(f"[AgentManager] 创建 Agent: {config.name} ({config.id})")
        return config

    def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        """获取 Agent 配置"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT config FROM agents WHERE id = ?", (agent_id,)
            ).fetchone()
            if row:
                return AgentConfig.from_dict(json.loads(row["config"]))
        return None

    def list_agents(self, created_by: str = "", role: str = "") -> List[AgentConfig]:
        """列出 Agent"""
        query = "SELECT config FROM agents WHERE is_active = 1"
        params = []
        if created_by:
            query += " AND created_by = ?"
            params.append(created_by)
        if role:
            query += " AND role = ?"
            params.append(role)
        query += " ORDER BY updated_at DESC"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [AgentConfig.from_dict(json.loads(r["config"])) for r in rows]

    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> Optional[AgentConfig]:
        """更新 Agent"""
        agent = self.get_agent(agent_id)
        if not agent:
            return None

        # 应用更新
        for key, value in updates.items():
            if hasattr(agent, key):
                setattr(agent, key, value)
            elif key == "identity" and isinstance(value, dict):
                for ik, iv in value.items():
                    if hasattr(agent.identity, ik):
                        setattr(agent.identity, ik, iv)
            elif key == "skills" and isinstance(value, list):
                from tent_os.soul.agent_models import AgentSkill
                agent.skills = [AgentSkill(**s) if isinstance(s, dict) else s for s in value]

        agent.updated_at = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE agents SET name = ?, role = ?, config = ?, updated_at = ? WHERE id = ?",
                (agent.name, agent.role,
                 json.dumps(agent.to_dict(), ensure_ascii=False),
                 agent.updated_at, agent_id)
            )
        logger.info(f"[AgentManager] 更新 Agent: {agent.name} ({agent_id})")
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        """删除 Agent（软删除）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE agents SET is_active = 0 WHERE id = ?", (agent_id,)
            )
            return conn.total_changes > 0

    def create_from_template(self, template_key: str, name: str = "",
                             created_by: str = "") -> Optional[AgentConfig]:
        """从预设模板创建 Agent"""
        template = get_role_template(template_key)
        if not template:
            return None

        config = AgentConfig.create(
            name=name or template["name"],
            role=template["role"],
            created_by=created_by,
            system_prompt=template["system_prompt"],
            tools_allowed=template.get("tools_allowed", []),
            identity=template.get("identity", {}),
            skills=template.get("skills", []),
        )
        return self.create_agent(config)

    # ========== Agent 状态管理 ==========

    def get_state(self, agent_id: str) -> AgentState:
        """获取 Agent 运行时状态"""
        if agent_id not in self._state_cache:
            self._state_cache[agent_id] = AgentState()
        return self._state_cache[agent_id]

    def update_state(self, agent_id: str, **kwargs):
        """更新 Agent 状态"""
        state = self.get_state(agent_id)
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)

    def get_all_states(self) -> Dict[str, AgentState]:
        """获取所有 Agent 状态"""
        return dict(self._state_cache)

    # ========== 会议室管理 ==========

    def create_room(self, name: str, topic: str = "", participants: List[str] = None,
                    host_agent_id: str = "", created_by: str = "") -> AgentRoom:
        """创建会议室"""
        import uuid
        room = AgentRoom(
            id=f"room_{uuid.uuid4().hex[:12]}",
            name=name,
            topic=topic,
            participants=participants or [],
            host_agent_id=host_agent_id,
            status="idle",
            created_by=created_by,
            created_at=datetime.now().isoformat(),
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO agent_rooms (id, name, topic, participants, host_agent_id, status, summary, created_by, created_at, closed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (room.id, room.name, room.topic,
                 json.dumps(room.participants),
                 room.host_agent_id, room.status, room.summary,
                 room.created_by, room.created_at, room.closed_at)
            )
        logger.info(f"[AgentManager] 创建会议室: {name} ({room.id})")
        return room

    def get_room(self, room_id: str) -> Optional[AgentRoom]:
        """获取会议室"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM agent_rooms WHERE id = ?", (room_id,)
            ).fetchone()
            if row:
                return AgentRoom(
                    id=row["id"],
                    name=row["name"],
                    topic=row["topic"],
                    participants=json.loads(row["participants"] or "[]"),
                    host_agent_id=row["host_agent_id"],
                    status=row["status"],
                    summary=row["summary"] or "",
                    created_by=row["created_by"],
                    created_at=row["created_at"],
                    closed_at=row["closed_at"],
                )
        return None

    def list_rooms(self, status: str = "") -> List[AgentRoom]:
        """列出会议室"""
        query = "SELECT * FROM agent_rooms"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [
                AgentRoom(
                    id=r["id"], name=r["name"], topic=r["topic"],
                    participants=json.loads(r["participants"] or "[]"),
                    host_agent_id=r["host_agent_id"], status=r["status"],
                    summary=r["summary"] or "", created_by=r["created_by"],
                    created_at=r["created_at"], closed_at=r["closed_at"],
                ) for r in rows
            ]

    def update_room(self, room_id: str, **kwargs) -> Optional[AgentRoom]:
        """更新会议室状态"""
        room = self.get_room(room_id)
        if not room:
            return None
        for key, value in kwargs.items():
            if hasattr(room, key):
                setattr(room, key, value)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE agent_rooms SET status = ?, summary = ?, closed_at = ? WHERE id = ?",
                (room.status, room.summary, room.closed_at, room_id)
            )
        return room

    # ========== 消息管理 ==========

    def add_message(self, room_id: str, from_agent_id: str, content: str,
                    to_agent_id: str = None, message_type: str = "text",
                    metadata: Dict = None) -> AgentMessage:
        """添加消息"""
        msg = AgentMessage(
            room_id=room_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            message_type=message_type,
            content=content,
            metadata=metadata or {},
            created_at=datetime.now().isoformat(),
        )
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO agent_messages (room_id, from_agent_id, to_agent_id, message_type, content, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (msg.room_id, msg.from_agent_id, msg.to_agent_id,
                 msg.message_type, msg.content,
                 json.dumps(msg.metadata, ensure_ascii=False),
                 msg.created_at)
            )
            msg.id = str(cursor.lastrowid)
        return msg

    def get_messages(self, room_id: str, limit: int = 100) -> List[AgentMessage]:
        """获取房间消息"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM agent_messages WHERE room_id = ? ORDER BY created_at DESC LIMIT ?",
                (room_id, limit)
            ).fetchall()
            return [
                AgentMessage(
                    id=str(r["id"]), room_id=r["room_id"],
                    from_agent_id=r["from_agent_id"], to_agent_id=r["to_agent_id"],
                    message_type=r["message_type"], content=r["content"],
                    metadata=json.loads(r["metadata"] or "{}"),
                    created_at=r["created_at"],
                ) for r in reversed(rows)
            ]

    # ========== P5: Agent间关系与协作网络 ==========

    def record_collaboration(self, agent_a_id: str, agent_b_id: str,
                             room_id: str = None, task_type: str = "",
                             result: str = "success", quality_score: float = 0.0):
        """记录一次协作事件，更新关系数据"""
        # 确保 agent_a_id < agent_b_id 以保持一致性
        a, b = sorted([agent_a_id, agent_b_id])
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            # 1. 插入协作日志
            conn.execute(
                "INSERT INTO agent_collaboration_logs (agent_a_id, agent_b_id, room_id, task_type, result, quality_score, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (a, b, room_id, task_type, result, quality_score, now)
            )
            # 2. 更新或创建关系记录
            row = conn.execute(
                "SELECT * FROM agent_relationships WHERE agent_a_id = ? AND agent_b_id = ?",
                (a, b)
            ).fetchone()
            if row:
                new_count = row["collaboration_count"] + 1
                new_success = row["success_count"] + (1 if result == "success" else 0)
                new_rate = new_success / new_count
                # 信任度基于成功率和质量平滑更新
                old_trust = row["trust_score"]
                quality_boost = quality_score * 0.1  # 质量分额外加成
                new_trust = old_trust * 0.7 + new_rate * 0.3 + quality_boost
                new_trust = max(0.0, min(1.0, new_trust))
                conn.execute(
                    "UPDATE agent_relationships SET collaboration_count = ?, success_count = ?, trust_score = ?, last_interaction = ? WHERE agent_a_id = ? AND agent_b_id = ?",
                    (new_count, new_success, new_trust, now, a, b)
                )
            else:
                success = 1 if result == "success" else 0
                trust = 0.5 + quality_score * 0.1
                trust = max(0.0, min(1.0, trust))
                conn.execute(
                    "INSERT INTO agent_relationships (agent_a_id, agent_b_id, relationship_type, trust_score, collaboration_count, success_count, last_interaction) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (a, b, "collaborator", trust, 1, success, now)
                )
            conn.commit()

    def get_relationships(self, agent_id: str) -> List[Dict]:
        """获取某个Agent的所有关系"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM agent_relationships
                   WHERE agent_a_id = ? OR agent_b_id = ?
                   ORDER BY trust_score DESC""",
                (agent_id, agent_id)
            ).fetchall()
            result = []
            for r in rows:
                other_id = r["agent_b_id"] if r["agent_a_id"] == agent_id else r["agent_a_id"]
                result.append({
                    "agent_id": agent_id,
                    "other_agent_id": other_id,
                    "relationship_type": r["relationship_type"],
                    "trust_score": round(r["trust_score"], 3),
                    "collaboration_count": r["collaboration_count"],
                    "success_rate": round(r["success_count"] / max(r["collaboration_count"], 1), 3),
                    "last_interaction": r["last_interaction"],
                })
            return result

    def get_relationship_matrix(self) -> Dict:
        """获取团队完整的关系矩阵"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM agent_relationships ORDER BY trust_score DESC"
            ).fetchall()
            agents = self.list_agents()
            agent_map = {a.id: {"name": a.name, "role": a.role} for a in agents}
            links = []
            for r in rows:
                links.append({
                    "source": r["agent_a_id"],
                    "target": r["agent_b_id"],
                    "type": r["relationship_type"],
                    "trust": round(r["trust_score"], 3),
                    "count": r["collaboration_count"],
                })
            return {
                "agents": [{"id": a.id, "name": a.name, "role": a.role} for a in agents],
                "links": links,
            }

    def get_collaboration_stats(self, agent_id: str = None) -> Dict:
        """获取协作统计"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if agent_id:
                total = conn.execute(
                    "SELECT COUNT(*) as c FROM agent_collaboration_logs WHERE agent_a_id = ? OR agent_b_id = ?",
                    (agent_id, agent_id)
                ).fetchone()["c"]
                success = conn.execute(
                    "SELECT COUNT(*) as c FROM agent_collaboration_logs WHERE (agent_a_id = ? OR agent_b_id = ?) AND result = 'success'",
                    (agent_id, agent_id)
                ).fetchone()["c"]
                avg_quality = conn.execute(
                    "SELECT AVG(quality_score) as q FROM agent_collaboration_logs WHERE agent_a_id = ? OR agent_b_id = ?",
                    (agent_id, agent_id)
                ).fetchone()["q"] or 0
                return {
                    "total_collaborations": total,
                    "success_rate": round(success / max(total, 1), 3),
                    "avg_quality": round(avg_quality, 3),
                }
            else:
                total = conn.execute("SELECT COUNT(*) as c FROM agent_collaboration_logs").fetchone()["c"]
                success = conn.execute("SELECT COUNT(*) as c FROM agent_collaboration_logs WHERE result = 'success'").fetchone()["c"]
                avg_quality = conn.execute("SELECT AVG(quality_score) as q FROM agent_collaboration_logs").fetchone()["q"] or 0
                return {
                    "total_collaborations": total,
                    "success_rate": round(success / max(total, 1), 3),
                    "avg_quality": round(avg_quality, 3),
                }
