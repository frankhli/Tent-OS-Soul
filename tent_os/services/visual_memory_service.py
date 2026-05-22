"""
VisualMemoryService —— AI 的空间记忆系统

核心能力：
1. 视觉记忆存储：每次视觉输入 → 描述 + 物体列表 → 存入数据库
2. 物体追踪：记录物体最后出现的位置和时间
3. 语义检索：文字查询 → 匹配相关视觉记忆
4. 空间地图：逐步构建房间内的物体分布

存储层：当前用 SQLite（MVP），未来可无缝迁移到 PostgreSQL + pgvector
"""

import json
import sqlite3
import uuid
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

from tent_os.logging_config import get_logger

logger = get_logger()


class VisualMemoryService:
    """
    视觉记忆服务 —— AI 的眼睛看到的一切都在这里记录
    """

    # 物体 → 2D 世界映射规则（虚实映射核心）
    OBJECT_TO_WORLD_TAXONOMY = {
        "plant":     {"visual_type": "plant",  "room_id": "greenhouse", "rarity": "common",  "name_prefix": "发现植物"},
        "flower":    {"visual_type": "plant",  "room_id": "greenhouse", "rarity": "common",  "name_prefix": "发现花朵"},
        "tree":      {"visual_type": "plant",  "room_id": "greenhouse", "rarity": "rare",    "name_prefix": "发现树木"},
        "book":      {"visual_type": "book",   "room_id": "library",    "rarity": "common",  "name_prefix": "发现书籍"},
        "laptop":    {"visual_type": "gear",   "room_id": "workshop",   "rarity": "common",  "name_prefix": "发现设备"},
        "computer":  {"visual_type": "gear",   "room_id": "workshop",   "rarity": "common",  "name_prefix": "发现设备"},
        "phone":     {"visual_type": "crystal","room_id": "living_room","rarity": "common",  "name_prefix": "发现物品"},
        "cup":       {"visual_type": "crystal","room_id": "living_room","rarity": "common",  "name_prefix": "发现物品"},
        "bottle":    {"visual_type": "crystal","room_id": "living_room","rarity": "common",  "name_prefix": "发现物品"},
        "chair":     {"visual_type": "scroll", "room_id": "living_room","rarity": "common",  "name_prefix": "发现家具"},
        "table":     {"visual_type": "scroll", "room_id": "living_room","rarity": "common",  "name_prefix": "发现家具"},
        "painting":  {"visual_type": "painting","room_id": "greenhouse","rarity": "rare",    "name_prefix": "发现画作"},
        "photo":     {"visual_type": "painting","room_id": "greenhouse","rarity": "common",  "name_prefix": "发现照片"},
    }

    def __init__(self, db_path: str = "./tent_memory/visual_memory.db",
                 world_db_path: str = "./tent_scheduler.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.world_db_path = Path(world_db_path)
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS visual_memory (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    image_url TEXT,
                    description TEXT,
                    scene_type TEXT,
                    objects_json TEXT,  -- JSON array of {name, location, confidence}
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS object_inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    object_name TEXT NOT NULL,
                    last_seen_location TEXT,
                    last_seen_memory_id TEXT,
                    confidence REAL,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, object_name)
                );
                
                CREATE INDEX IF NOT EXISTS idx_memory_user_time 
                    ON visual_memory(user_id, created_at DESC);
                
                CREATE INDEX IF NOT EXISTS idx_object_user 
                    ON object_inventory(user_id, object_name);
                
                CREATE INDEX IF NOT EXISTS idx_memory_description 
                    ON visual_memory(description);
            """)

    def store_memory(
        self,
        user_id: str,
        image_url: str,
        description: str,
        scene_type: str = "",
        objects: Optional[List[Dict]] = None,
    ) -> str:
        """
        存储一次视觉记忆
        
        Args:
            user_id: 用户ID
            image_url: 图片URL或base64
            description: 场景描述
            scene_type: 场景类型（客厅/卧室/办公室等）
            objects: 检测到的物体列表 [{name, location, confidence}]
            
        Returns:
            memory_id: 记忆ID
        """
        memory_id = f"vm_{uuid.uuid4().hex[:12]}"
        objects = objects or []
        
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO visual_memory 
                   (id, user_id, image_url, description, scene_type, objects_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (memory_id, user_id, image_url, description, scene_type, 
                 json.dumps(objects, ensure_ascii=False))
            )
            
            # 更新物体清单
            for obj in objects:
                obj_name = obj.get("name", "").strip().lower()
                if not obj_name:
                    continue
                location = obj.get("location", "")
                confidence = obj.get("confidence", 0.5)
                
                conn.execute(
                    """INSERT INTO object_inventory 
                       (user_id, object_name, last_seen_location, last_seen_memory_id, confidence)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(user_id, object_name) DO UPDATE SET
                       last_seen_location = excluded.last_seen_location,
                       last_seen_memory_id = excluded.last_seen_memory_id,
                       confidence = excluded.confidence,
                       updated_at = CURRENT_TIMESTAMP""",
                    (user_id, obj_name, location, memory_id, confidence)
                )
        
        # FIX Gap 5: 虚实映射 — 将检测到的真实物体同步到 2D 世界
        self._sync_objects_to_world(user_id, objects, memory_id)
        
        logger.info(f"[VisualMemory] 存储记忆: {user_id} → {scene_type or '未知场景'} ({len(objects)}个物体)")
        return memory_id

    def query_memory(
        self,
        user_id: str,
        keyword: str,
        limit: int = 10,
    ) -> List[Dict]:
        """
        语义查询视觉记忆（当前用文本匹配，未来升级为向量搜索）
        
        Args:
            user_id: 用户ID
            keyword: 查询关键词（如"遥控器"、"客厅"、"昨天"）
            limit: 返回数量
            
        Returns:
            匹配的记忆列表
        """
        keyword_lower = keyword.lower()
        
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            
            # 策略1：描述文本匹配
            rows = conn.execute(
                """SELECT * FROM visual_memory 
                   WHERE user_id = ? AND (
                       LOWER(description) LIKE ? 
                       OR LOWER(scene_type) LIKE ?
                   )
                   ORDER BY created_at DESC LIMIT ?""",
                (user_id, f"%{keyword_lower}%", f"%{keyword_lower}%", limit)
            ).fetchall()
            
            results = []
            seen_ids = set()
            
            for row in rows:
                memory_id = row["id"]
                seen_ids.add(memory_id)
                results.append(self._row_to_dict(row))
            
            # 策略2：物体名称匹配（如果没找到足够的）
            if len(results) < limit:
                obj_rows = conn.execute(
                    """SELECT m.* FROM visual_memory m
                       JOIN object_inventory o ON m.id = o.last_seen_memory_id
                       WHERE o.user_id = ? AND LOWER(o.object_name) LIKE ?
                       ORDER BY m.created_at DESC LIMIT ?""",
                    (user_id, f"%{keyword_lower}%", limit - len(results))
                ).fetchall()
                
                for row in obj_rows:
                    if row["id"] not in seen_ids:
                        seen_ids.add(row["id"])
                        results.append(self._row_to_dict(row))
            
            return results

    def find_object(self, user_id: str, object_name: str) -> Optional[Dict]:
        """
        查找物体最后出现的位置
        
        Args:
            user_id: 用户ID
            object_name: 物体名称（如"遥控器"）
            
        Returns:
            物体信息，包含位置、时间、相关图片
        """
        object_name_lower = object_name.lower().strip()
        
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            
            # 精确匹配
            row = conn.execute(
                """SELECT o.*, m.image_url, m.description, m.scene_type
                   FROM object_inventory o
                   LEFT JOIN visual_memory m ON o.last_seen_memory_id = m.id
                   WHERE o.user_id = ? AND o.object_name = ?
                   ORDER BY o.updated_at DESC LIMIT 1""",
                (user_id, object_name_lower)
            ).fetchone()
            
            if row:
                return {
                    "object_name": row["object_name"],
                    "location": row["last_seen_location"],
                    "confidence": row["confidence"],
                    "last_seen": row["updated_at"],
                    "image_url": row["image_url"],
                    "scene_description": row["description"],
                    "scene_type": row["scene_type"],
                    "found": True,
                }
            
            # 模糊匹配
            fuzzy_row = conn.execute(
                """SELECT o.*, m.image_url, m.description, m.scene_type
                   FROM object_inventory o
                   LEFT JOIN visual_memory m ON o.last_seen_memory_id = m.id
                   WHERE o.user_id = ? AND o.object_name LIKE ?
                   ORDER BY o.updated_at DESC LIMIT 1""",
                (user_id, f"%{object_name_lower}%")
            ).fetchone()
            
            if fuzzy_row:
                return {
                    "object_name": fuzzy_row["object_name"],
                    "location": fuzzy_row["last_seen_location"],
                    "confidence": fuzzy_row["confidence"],
                    "last_seen": fuzzy_row["updated_at"],
                    "image_url": fuzzy_row["image_url"],
                    "scene_description": fuzzy_row["description"],
                    "scene_type": fuzzy_row["scene_type"],
                    "found": True,
                    "fuzzy_match": True,
                }
            
            return {"found": False, "object_name": object_name}

    def get_object_inventory(self, user_id: str) -> List[Dict]:
        """获取用户当前已知的所有物体清单"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT o.*, m.image_url 
                   FROM object_inventory o
                   LEFT JOIN visual_memory m ON o.last_seen_memory_id = m.id
                   WHERE o.user_id = ?
                   ORDER BY o.updated_at DESC""",
                (user_id,)
            ).fetchall()
            
            return [
                {
                    "object_name": r["object_name"],
                    "location": r["last_seen_location"],
                    "confidence": r["confidence"],
                    "last_seen": r["updated_at"],
                    "image_url": r["image_url"],
                }
                for r in rows
            ]

    def get_recent_memories(self, user_id: str, limit: int = 20) -> List[Dict]:
        """获取最近的视觉记忆"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM visual_memory 
                   WHERE user_id = ? 
                   ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        return {
            "id": row["id"],
            "image_url": row["image_url"],
            "description": row["description"],
            "scene_type": row["scene_type"],
            "objects": json.loads(row["objects_json"]) if row["objects_json"] else [],
            "created_at": row["created_at"],
        }

    # ========== 空间记忆系统：模式发现 + 异常检测 ==========

    def get_spatial_summary(self, user_id: str, hours: int = 24) -> List[Dict]:
        """获取最近 N 小时的空间观察摘要（按时间线排序）"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM visual_memory 
                   WHERE user_id = ? AND created_at >= datetime('now', '-{} hours')
                   ORDER BY created_at DESC LIMIT 50""".format(hours),
                (user_id,)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def discover_patterns(self, user_id: str, days: int = 7) -> List[Dict]:
        """发现物理世界中的时间重复模式
        
        算法：按 object_name + hour 分组统计，出现次数/总天数 >= 阈值 视为模式
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            
            # 1. 从 object_inventory 获取所有追踪中的物体
            objects = conn.execute(
                "SELECT object_name FROM object_inventory WHERE user_id = ?",
                (user_id,)
            ).fetchall()
            
            patterns = []
            min_occurrences = max(2, days // 2)  # 至少出现 N 次（默认7天至少4次）
            
            for obj_row in objects:
                obj_name = obj_row["object_name"]
                
                # 统计该物体在过去 N 天内每个小时段的出现次数
                hour_stats = conn.execute(
                    """SELECT strftime('%H', created_at) as hour, COUNT(*) as cnt
                       FROM visual_memory 
                       WHERE user_id = ? 
                         AND created_at >= datetime('now', '-{} days')
                         AND objects_json LIKE ?
                       GROUP BY hour
                       ORDER BY cnt DESC""".format(days),
                    (user_id, f'%"name": "{obj_name}"%')
                ).fetchall()
                
                # 也匹配模糊（description 中包含物体名）
                if not hour_stats:
                    hour_stats = conn.execute(
                        """SELECT strftime('%H', created_at) as hour, COUNT(*) as cnt
                           FROM visual_memory 
                           WHERE user_id = ? 
                             AND created_at >= datetime('now', '-{} days')
                             AND LOWER(description) LIKE ?
                           GROUP BY hour
                           ORDER BY cnt DESC""".format(days),
                        (user_id, f'%{obj_name}%')
                    ).fetchall()
                
                for stat in hour_stats:
                    hour = stat["hour"]
                    cnt = stat["cnt"]
                    confidence = min(0.99, cnt / days)
                    
                    if cnt >= min_occurrences and confidence >= 0.5:
                        # 生成人类可读的模式描述
                        hour_int = int(hour)
                        time_desc = f"每天{hour_int}点左右" if 6 <= hour_int <= 22 else f"凌晨{hour_int}点左右"
                        
                        patterns.append({
                            "object": obj_name,
                            "pattern": f"{time_desc}出现",
                            "hour": hour_int,
                            "occurrences": cnt,
                            "total_days": days,
                            "confidence": round(confidence, 2),
                        })
                        break  # 每个物体只取最强模式
            
            # 2. 也分析 scene_type 的模式
            scene_stats = conn.execute(
                """SELECT scene_type, strftime('%H', created_at) as hour, COUNT(*) as cnt
                   FROM visual_memory 
                   WHERE user_id = ? 
                     AND created_at >= datetime('now', '-{} days')
                     AND scene_type != ''
                   GROUP BY scene_type, hour
                   HAVING cnt >= ?
                   ORDER BY cnt DESC""".format(days),
                (user_id, min_occurrences)
            ).fetchall()
            
            for stat in scene_stats:
                patterns.append({
                    "object": stat["scene_type"],
                    "pattern": f"每天{int(stat['hour'])}点左右处于{stat['scene_type']}场景",
                    "hour": int(stat["hour"]),
                    "occurrences": stat["cnt"],
                    "total_days": days,
                    "confidence": round(min(0.99, stat["cnt"] / days), 2),
                    "type": "scene",
                })
            
            # 去重并按置信度排序
            seen = set()
            unique_patterns = []
            for p in patterns:
                key = (p["object"], p.get("hour"))
                if key not in seen:
                    seen.add(key)
                    unique_patterns.append(p)
            
            unique_patterns.sort(key=lambda x: x["confidence"], reverse=True)
            return unique_patterns[:20]

    def _sync_objects_to_world(self, user_id: str, objects: List[Dict], memory_id: str):
        """将检测到的物体同步到 2D 世界作为动态道具
        
        虚实映射核心：摄像头看到 "plant" → 2D 世界的 greenhouse 出现植物道具
        """
        if not self.world_db_path.exists():
            return
        
        try:
            with sqlite3.connect(str(self.world_db_path)) as wconn:
                for obj in objects:
                    obj_name = obj.get("name", "").strip().lower()
                    taxonomy = self.OBJECT_TO_WORLD_TAXONOMY.get(obj_name)
                    if not taxonomy:
                        continue
                    
                    # 去重：同一物体不重复创建
                    existing = wconn.execute(
                        "SELECT 1 FROM world_artifacts WHERE name = ? AND task_id = ?",
                        (f"{taxonomy['name_prefix']}: {obj_name}", memory_id)
                    ).fetchone()
                    if existing:
                        continue
                    
                    artifact_id = f"vm_{memory_id}_{obj_name}"
                    pos_x = 50 + (hash(artifact_id) % 300)
                    pos_y = 50 + (hash(artifact_id[::-1]) % 200)
                    
                    wconn.execute("""
                        INSERT INTO world_artifacts
                        (id, name, task_id, category, visual_type, rarity, room_id, position_x, position_y, description)
                        VALUES (?, ?, ?, 'visual_memory', ?, ?, ?, ?, ?, ?)
                    """, (
                        artifact_id,
                        f"{taxonomy['name_prefix']}: {obj_name}",
                        memory_id,
                        taxonomy["visual_type"],
                        taxonomy["rarity"],
                        taxonomy["room_id"],
                        pos_x, pos_y,
                        f"由视觉感知检测到: {obj_name} (置信度: {obj.get('confidence', 0.5):.2f})"
                    ))
                wconn.commit()
        except Exception as e:
            logger.warning(f"[VisualMemory] 同步到 2D 世界失败: {e}")
    
    def get_world_props(self, user_id: str) -> List[Dict]:
        """获取由视觉记忆生成的 2D 世界道具"""
        if not self.world_db_path.exists():
            return []
        try:
            with sqlite3.connect(str(self.world_db_path)) as wconn:
                wconn.row_factory = sqlite3.Row
                rows = wconn.execute(
                    "SELECT * FROM world_artifacts WHERE category = 'visual_memory' ORDER BY created_at DESC"
                ).fetchall()
                return [
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
        except Exception as e:
            logger.warning(f"[VisualMemory] 获取世界道具失败: {e}")
            return []

    def detect_anomalies(self, user_id: str, window_hours: int = 24) -> List[Dict]:
        """检测与历史模式偏离的异常
        
        逻辑：
        1. 先 discover_patterns(days=7) 建立基线
        2. 检查 window_hours 内的视觉记忆
        3. 如果某个物体/场景的模式应该出现但未出现 → 标记为 missing_pattern
        4. 如果出现了不常见的物体（首次出现或低频） → 标记为 unexpected_object
        """
        anomalies = []
        
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            
            # 1. 建立基线模式
            patterns = self.discover_patterns(user_id, days=7)
            high_conf_patterns = [p for p in patterns if p["confidence"] >= 0.6]
            
            # 2. 检查最近 window_hours 内的记录
            recent = conn.execute(
                """SELECT * FROM visual_memory 
                   WHERE user_id = ? AND created_at >= datetime('now', '-{} hours')
                   ORDER BY created_at DESC""".format(window_hours),
                (user_id,)
            ).fetchall()
            
            # 收集最近出现过的物体
            recent_objects = set()
            recent_hours = set()
            for row in recent:
                recent_hours.add(int(row["created_at"][11:13]) if len(row["created_at"]) >= 13 else 0)
                objects = json.loads(row["objects_json"]) if row["objects_json"] else []
                for obj in objects:
                    name = obj.get("name", "").strip().lower()
                    if name:
                        recent_objects.add(name)
            
            # 3. 检查缺失的模式
            for pattern in high_conf_patterns:
                if "hour" in pattern:
                    expected_hour = pattern["hour"]
                    # 如果最近时间窗口覆盖了该小时段，但物体未出现
                    window_covers_hour = any(
                        abs(h - expected_hour) <= 1 for h in recent_hours
                    )
                    if window_covers_hour and pattern["object"] not in recent_objects:
                        anomalies.append({
                            "type": "missing_pattern",
                            "object": pattern["object"],
                            "expected": pattern["pattern"],
                            "actual": "未出现",
                            "confidence": pattern["confidence"],
                            "severity": "warning" if pattern["confidence"] > 0.8 else "info",
                        })
            
            # 4. 检查首次出现的物体（不常见物体）
            all_known_objects = set()
            all_known_rows = conn.execute(
                "SELECT object_name FROM object_inventory WHERE user_id = ?",
                (user_id,)
            ).fetchall()
            for r in all_known_rows:
                all_known_objects.add(r["object_name"])
            
            # 找出最近出现但历史记录很少（<3次）的物体
            for obj_name in recent_objects:
                count_row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM visual_memory 
                       WHERE user_id = ? AND objects_json LIKE ?""",
                    (user_id, f'%"name": "{obj_name}"%')
                ).fetchone()
                total_count = count_row["cnt"] if count_row else 0
                
                if total_count > 0 and total_count <= 3:
                    anomalies.append({
                        "type": "unexpected_object",
                        "object": obj_name,
                        "expected": "该物体历史出现次数很少",
                        "actual": f"最近{window_hours}小时内出现（历史共{total_count}次）",
                        "confidence": 0.7,
                        "severity": "info",
                    })
        
        # 按严重程度排序
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        anomalies.sort(key=lambda x: severity_order.get(x.get("severity", "info"), 2))
        return anomalies


# 全局单例
_service: Optional[VisualMemoryService] = None

def get_visual_memory_service() -> VisualMemoryService:
    global _service
    if _service is None:
        _service = VisualMemoryService()
    return _service
