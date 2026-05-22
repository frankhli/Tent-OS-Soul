"""
World API —— 2D 世界状态持久化与管理

端点:
  GET    /ui/api/world/state          获取世界状态
  POST   /ui/api/world/state          保存世界状态
  POST   /ui/api/world/artifact       添加智慧藏品
  POST   /ui/api/world/room/unlock    解锁房间
  GET    /ui/api/world/stats          获取世界统计
"""

import json
import sqlite3
import time
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

# 全局数据库连接（由 server.py 注入）
_db: Optional[sqlite3.Connection] = None


def set_world_db(db: sqlite3.Connection):
    """注入数据库连接"""
    global _db
    _db = db
    _init_world_tables()


def _init_world_tables():
    """初始化世界系统相关表"""
    if not _db:
        return
    _db.execute("""
        CREATE TABLE IF NOT EXISTS world_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            avatar_room_id TEXT DEFAULT 'living_room',
            avatar_position_x REAL DEFAULT 350,
            avatar_position_y REAL DEFAULT 300,
            avatar_action TEXT DEFAULT 'idle',
            avatar_facing INTEGER DEFAULT 1,
            experience INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            tasks_completed INTEGER DEFAULT 0,
            tasks_failed INTEGER DEFAULT 0,
            streak_days INTEGER DEFAULT 0,
            active_time_today INTEGER DEFAULT 0,
            time_of_day TEXT DEFAULT 'afternoon',
            last_update INTEGER DEFAULT 0,
            achievements TEXT DEFAULT '[]',
            decorations TEXT DEFAULT '[]',
            updated_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    """)
    _db.execute("""
        CREATE TABLE IF NOT EXISTS world_artifacts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            task_id TEXT,
            category TEXT,
            visual_type TEXT,
            rarity TEXT,
            room_id TEXT NOT NULL,
            position_x REAL,
            position_y REAL,
            description TEXT,
            created_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    """)
    _db.execute("""
        CREATE TABLE IF NOT EXISTS world_room_unlocks (
            room_id TEXT PRIMARY KEY,
            unlocked_at INTEGER DEFAULT (strftime('%s', 'now')),
            unlock_reason TEXT
        )
    """)
    # 插入默认世界状态（如果不存在）
    _db.execute("""
        INSERT OR IGNORE INTO world_state (id) VALUES (1)
    """)
    _db.commit()


# ========== Pydantic 模型 ==========

class WorldStateUpdate(BaseModel):
    avatar_room_id: Optional[str] = None
    avatar_position_x: Optional[float] = None
    avatar_position_y: Optional[float] = None
    avatar_action: Optional[str] = None
    avatar_facing: Optional[int] = None
    experience: Optional[int] = None
    level: Optional[int] = None
    tasks_completed: Optional[int] = None
    tasks_failed: Optional[int] = None
    streak_days: Optional[int] = None
    time_of_day: Optional[str] = None
    achievements: Optional[List[str]] = None
    decorations: Optional[List[str]] = None


class ArtifactCreate(BaseModel):
    name: str = Field(..., description="藏品名称")
    task_id: Optional[str] = None
    category: str = Field(default="code", description="类别: code/writing/design/analysis/creative")
    visual_type: str = Field(default="crystal", description="视觉类型: book/crystal/scroll/gear/plant/painting")
    rarity: str = Field(default="common", description="稀有度: common/rare/epic/legendary")
    room_id: str = Field(default="living_room", description="所属房间")
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    description: Optional[str] = None


class RoomUnlock(BaseModel):
    room_id: str = Field(..., description="房间 ID")
    reason: Optional[str] = None


# ========== API 路由 ==========

@router.get("/ui/api/world/state")
async def get_world_state():
    """获取世界状态"""
    if not _db:
        raise HTTPException(status_code=503, detail="数据库未就绪")

    row = _db.execute("SELECT * FROM world_state WHERE id = 1").fetchone()
    if not row:
        return {"world": None}

    return {
        "world": {
            "avatar": {
                "room_id": row["avatar_room_id"],
                "position": {"x": row["avatar_position_x"], "y": row["avatar_position_y"]},
                "action": row["avatar_action"],
                "facing": row["avatar_facing"],
            },
            "experience": row["experience"],
            "level": row["level"],
            "tasks_completed": row["tasks_completed"],
            "tasks_failed": row["tasks_failed"],
            "streak_days": row["streak_days"],
            "time_of_day": row["time_of_day"],
            "achievements": json.loads(row["achievements"]),
            "decorations": json.loads(row["decorations"]),
            "last_update": row["last_update"],
        }
    }


@router.post("/ui/api/world/state")
async def save_world_state(req: WorldStateUpdate):
    """保存世界状态（增量更新）"""
    if not _db:
        raise HTTPException(status_code=503, detail="数据库未就绪")

    fields = []
    values = []
    if req.avatar_room_id is not None:
        fields.append("avatar_room_id = ?")
        values.append(req.avatar_room_id)
    if req.avatar_position_x is not None:
        fields.append("avatar_position_x = ?")
        values.append(req.avatar_position_x)
    if req.avatar_position_y is not None:
        fields.append("avatar_position_y = ?")
        values.append(req.avatar_position_y)
    if req.avatar_action is not None:
        fields.append("avatar_action = ?")
        values.append(req.avatar_action)
    if req.avatar_facing is not None:
        fields.append("avatar_facing = ?")
        values.append(req.avatar_facing)
    if req.experience is not None:
        fields.append("experience = ?")
        values.append(req.experience)
    if req.level is not None:
        fields.append("level = ?")
        values.append(req.level)
    if req.tasks_completed is not None:
        fields.append("tasks_completed = ?")
        values.append(req.tasks_completed)
    if req.tasks_failed is not None:
        fields.append("tasks_failed = ?")
        values.append(req.tasks_failed)
    if req.streak_days is not None:
        fields.append("streak_days = ?")
        values.append(req.streak_days)
    if req.time_of_day is not None:
        fields.append("time_of_day = ?")
        values.append(req.time_of_day)
    if req.achievements is not None:
        fields.append("achievements = ?")
        values.append(json.dumps(req.achievements))
    if req.decorations is not None:
        fields.append("decorations = ?")
        values.append(json.dumps(req.decorations))

    if not fields:
        return {"status": "no_change"}

    fields.append("updated_at = strftime('%s', 'now')")
    fields.append("last_update = ?")
    values.append(int(time.time()))

    sql = f"UPDATE world_state SET {', '.join(fields)} WHERE id = 1"
    _db.execute(sql, values)
    _db.commit()

    return {"status": "saved", "updated_fields": len(fields) - 2}


@router.post("/ui/api/world/artifact")
async def add_artifact(req: ArtifactCreate):
    """添加智慧藏品（任务成果）"""
    if not _db:
        raise HTTPException(status_code=503, detail="数据库未就绪")

    artifact_id = f"art_{int(time.time() * 1000)}_{req.task_id or 'manual'}"

    # 如果没有指定位置，在房间内随机分配
    pos_x = req.position_x if req.position_x is not None else 50 + (hash(artifact_id) % 300)
    pos_y = req.position_y if req.position_y is not None else 50 + (hash(artifact_id[::-1]) % 200)

    _db.execute("""
        INSERT INTO world_artifacts
        (id, name, task_id, category, visual_type, rarity, room_id, position_x, position_y, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        artifact_id, req.name, req.task_id, req.category, req.visual_type,
        req.rarity, req.room_id, pos_x, pos_y, req.description
    ))
    _db.commit()

    # 增加经验值
    exp_gain = {"common": 10, "rare": 25, "epic": 50, "legendary": 100}.get(req.rarity, 10)
    _db.execute("""
        UPDATE world_state
        SET experience = experience + ?, tasks_completed = tasks_completed + 1, updated_at = strftime('%s', 'now')
        WHERE id = 1
    """, (exp_gain,))
    _db.commit()

    return {
        "status": "created",
        "artifact_id": artifact_id,
        "exp_gain": exp_gain,
    }


@router.get("/ui/api/world/artifacts")
async def list_artifacts(room_id: Optional[str] = None):
    """列出所有智慧藏品"""
    if not _db:
        raise HTTPException(status_code=503, detail="数据库未就绪")

    if room_id:
        rows = _db.execute(
            "SELECT * FROM world_artifacts WHERE room_id = ? ORDER BY created_at DESC",
            (room_id,)
        ).fetchall()
    else:
        rows = _db.execute("SELECT * FROM world_artifacts ORDER BY created_at DESC").fetchall()

    return {
        "artifacts": [
            {
                "id": r["id"],
                "name": r["name"],
                "task_id": r["task_id"],
                "category": r["category"],
                "visual_type": r["visual_type"],
                "rarity": r["rarity"],
                "room_id": r["room_id"],
                "position": {"x": r["position_x"], "y": r["position_y"]},
                "description": r["description"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }


@router.post("/ui/api/world/room/unlock")
async def unlock_room(req: RoomUnlock):
    """解锁房间"""
    if not _db:
        raise HTTPException(status_code=503, detail="数据库未就绪")

    _db.execute("""
        INSERT OR REPLACE INTO world_room_unlocks (room_id, unlocked_at, unlock_reason)
        VALUES (?, strftime('%s', 'now'), ?)
    """, (req.room_id, req.reason))
    _db.commit()

    return {"status": "unlocked", "room_id": req.room_id}


@router.get("/ui/api/world/rooms")
async def list_unlocked_rooms():
    """获取已解锁房间列表"""
    if not _db:
        raise HTTPException(status_code=503, detail="数据库未就绪")

    rows = _db.execute("SELECT room_id, unlocked_at, unlock_reason FROM world_room_unlocks").fetchall()
    return {
        "unlocked_rooms": [
            {"room_id": r["room_id"], "unlocked_at": r["unlocked_at"], "reason": r["unlock_reason"]}
            for r in rows
        ]
    }


@router.get("/ui/api/world/visual-props")
async def get_visual_props():
    """获取由视觉记忆映射的 2D 世界道具"""
    if not _db:
        raise HTTPException(status_code=503, detail="数据库未就绪")
    
    rows = _db.execute(
        "SELECT * FROM world_artifacts WHERE category = 'visual_memory' ORDER BY created_at DESC"
    ).fetchall()
    
    return {
        "props": [
            {
                "id": r["id"],
                "name": r["name"],
                "visual_type": r["visual_type"],
                "room_id": r["room_id"],
                "position": {"x": r["position_x"], "y": r["position_y"]},
                "description": r["description"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }


@router.get("/ui/api/world/stats")
async def get_world_stats():
    """获取世界统计信息"""
    if not _db:
        raise HTTPException(status_code=503, detail="数据库未就绪")

    world_row = _db.execute("SELECT * FROM world_state WHERE id = 1").fetchone()
    artifact_count = _db.execute("SELECT COUNT(*) as c FROM world_artifacts").fetchone()["c"]
    room_count = _db.execute("SELECT COUNT(*) as c FROM world_room_unlocks").fetchone()["c"]

    if not world_row:
        return {"stats": None}

    return {
        "stats": {
            "level": world_row["level"],
            "experience": world_row["experience"],
            "tasks_completed": world_row["tasks_completed"],
            "tasks_failed": world_row["tasks_failed"],
            "streak_days": world_row["streak_days"],
            "artifact_count": artifact_count,
            "unlocked_room_count": room_count,
            "active_time_today": world_row["active_time_today"],
        }
    }


# ===== 任务完成 Hook =====

LEVEL_THRESHOLDS = [0, 50, 120, 250, 450, 700, 1000, 1400, 1900, 2500, 3200, 4000]

ROOM_UNLOCK_REQUIREMENTS = {
    'workshop': {'level': 2, 'tasks': 5, 'category': 'code'},
    'library': {'level': 3, 'tasks': 10, 'category': 'knowledge'},
    'greenhouse': {'level': 2, 'tasks': 3, 'category': 'creative'},
}


def _get_level_from_exp(exp: int) -> int:
    """根据经验值计算等级"""
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if exp < threshold:
            return max(1, i)
    return len(LEVEL_THRESHOLDS)


def on_task_completed(session_id: str, result_text: str) -> dict:
    """任务完成时的世界系统回调 —— 自动掉落藏品、增加经验、检查升级/解锁

    返回: {"artifact_created": bool, "leveled_up": bool, "unlocked_rooms": list}
    """
    if not _db:
        return {"artifact_created": False, "leveled_up": False, "unlocked_rooms": []}

    # 1. 推断任务类型和稀有度
    category, rarity = _infer_task_type_and_rarity(result_text)

    # 2. 创建藏品
    artifact_id = f"art_{int(time.time() * 1000)}_{session_id[:16]}"
    artifact_name = _generate_artifact_name(category, result_text)
    visual_type = _category_to_visual(category)
    room_id = _category_to_room(category)

    pos_x = 50 + (hash(artifact_id) % 300)
    pos_y = 50 + (hash(artifact_id[::-1]) % 200)

    _db.execute("""
        INSERT INTO world_artifacts
        (id, name, task_id, category, visual_type, rarity, room_id, position_x, position_y)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (artifact_id, artifact_name, session_id, category, visual_type, rarity, room_id, pos_x, pos_y))

    # 3. 增加经验值和任务计数
    exp_gain = {"common": 10, "rare": 25, "epic": 50, "legendary": 100}.get(rarity, 10)
    _db.execute("""
        UPDATE world_state
        SET experience = experience + ?, tasks_completed = tasks_completed + 1,
            updated_at = strftime('%s', 'now')
        WHERE id = 1
    """, (exp_gain,))

    # 4. 检查升级
    row = _db.execute("SELECT experience, level FROM world_state WHERE id = 1").fetchone()
    old_level = row["level"]
    new_level = _get_level_from_exp(row["experience"])
    leveled_up = new_level > old_level
    if leveled_up:
        _db.execute("UPDATE world_state SET level = ? WHERE id = 1", (new_level,))

    # 5. 检查房间解锁
    unlocked_rooms = []
    if leveled_up:
        for room_id, req in ROOM_UNLOCK_REQUIREMENTS.items():
            # 检查是否已解锁
            existing = _db.execute("SELECT 1 FROM world_room_unlocks WHERE room_id = ?", (room_id,)).fetchone()
            if existing:
                continue
            # 检查是否满足条件
            tasks_in_category = _db.execute(
                "SELECT COUNT(*) as c FROM world_artifacts WHERE category = ?",
                (req['category'],)
            ).fetchone()["c"]
            if new_level >= req['level'] and tasks_in_category >= req['tasks']:
                _db.execute("""
                    INSERT INTO world_room_unlocks (room_id, unlocked_at, unlock_reason)
                    VALUES (?, strftime('%s', 'now'), ?)
                """, (room_id, f"达到等级 {new_level} 且完成 {req['tasks']} 个 {req['category']} 任务"))
                unlocked_rooms.append(room_id)

    _db.commit()

    return {
        "artifact_created": True,
        "artifact_id": artifact_id,
        "exp_gain": exp_gain,
        "leveled_up": leveled_up,
        "new_level": new_level if leveled_up else old_level,
        "unlocked_rooms": unlocked_rooms,
    }


def _infer_task_type_and_rarity(text: str) -> tuple:
    """根据任务结果推断类型和稀有度"""
    text_lower = text.lower()
    category = 'creative'
    # 类型推断
    if any(k in text_lower for k in ['code', 'python', 'script', 'function', 'class', 'def ', 'import ', 'api', 'debug', 'bug']):
        category = 'code'
    elif any(k in text_lower for k in ['ppt', 'slide', 'presentation', 'design', 'ui', 'figma', 'color', 'layout']):
        category = 'design'
    elif any(k in text_lower for k in ['excel', 'csv', 'data', 'analysis', 'chart', 'graph', 'statistics', 'report']):
        category = 'analysis'
    elif any(k in text_lower for k in ['write', 'essay', 'article', 'doc', 'summary', 'translate', 'email', 'letter']):
        category = 'writing'

    # 稀有度推断（基于内容长度和复杂度关键词）
    rarity = 'common'
    if len(text) > 2000:
        rarity = 'rare'
    if len(text) > 5000 or any(k in text_lower for k in ['complex', 'architecture', 'system', 'framework', 'optimization']):
        rarity = 'epic'
    if len(text) > 10000 or any(k in text_lower for k in ['breakthrough', 'innovation', 'revolutionary']):
        rarity = 'legendary'

    return category, rarity


def _generate_artifact_name(category: str, text: str) -> str:
    """生成藏品名称"""
    # 尝试提取前10个字符作为标题
    title = text.strip().replace('\n', ' ')[:20].strip()
    if len(title) < 5:
        titles = {
            'code': '代码成果', 'writing': '文字作品', 'design': '设计方案',
            'analysis': '数据分析', 'creative': '创意成果',
        }
        title = titles.get(category, '智慧结晶')
    return title


def _category_to_visual(category: str) -> str:
    """类别映射到视觉类型"""
    return {
        'code': 'gear', 'writing': 'scroll', 'design': 'painting',
        'analysis': 'crystal', 'creative': 'plant',
    }.get(category, 'book')


def _category_to_room(category: str) -> str:
    """类别映射到默认存放房间"""
    return {
        'code': 'workshop', 'writing': 'library', 'design': 'greenhouse',
        'analysis': 'library', 'creative': 'greenhouse',
    }.get(category, 'living_room')
