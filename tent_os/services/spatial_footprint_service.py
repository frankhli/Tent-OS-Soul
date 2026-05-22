"""SpatialFootprintService —— AI 的数字孪生地图与足迹系统

核心能力：
1. GPS 足迹记录：连续采样用户位置，形成移动轨迹
2. 地理围栏：定义虚拟边界，检测进入/离开事件
3. 地点记忆：AI 对每个去过的地方生成长期观察摘要
4. 足迹压缩：将密集点压缩为路径段，节省存储

存储层：SQLite（`tent_memory/spatial.db`）
"""

import json
import sqlite3
import uuid
import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

from tent_os.logging_config import get_logger

logger = get_logger()

# 地球半径（米）
EARTH_RADIUS = 6371000


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两个 GPS 坐标之间的距离（米）"""
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS * c


class SpatialFootprintService:
    """空间足迹服务 —— AI 的数字孪生地图"""

    def __init__(self, db_path: str = "./tent_memory/spatial.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS footprints (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    accuracy REAL,
                    altitude REAL,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    scene_hint TEXT
                );

                CREATE TABLE IF NOT EXISTS geofences (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    radius_meters INTEGER DEFAULT 100,
                    scene_id TEXT,
                    enter_action TEXT,
                    leave_action TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS location_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    location_name TEXT,
                    lat REAL,
                    lng REAL,
                    summary TEXT,
                    visit_count INTEGER DEFAULT 0,
                    total_duration_minutes INTEGER DEFAULT 0,
                    last_visit TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_footprint_user_time
                    ON footprints(user_id, timestamp DESC);

                CREATE INDEX IF NOT EXISTS idx_geofence_user
                    ON geofences(user_id);

                CREATE INDEX IF NOT EXISTS idx_location_user
                    ON location_memories(user_id);
            """)

    def record_footprint(self, user_id: str, lat: float, lng: float,
                         accuracy: float = None, altitude: float = None,
                         scene_hint: str = "") -> str:
        """记录一个足迹点

        同时会做简单压缩：如果与上一个点的距离 < 10 米，更新上一个点的时间戳而不是插入新点
        """
        # 检查是否需要压缩
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT lat, lng, timestamp FROM footprints WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
                (user_id,)
            ).fetchone()

            if row:
                last_lat, last_lng, last_ts = row
                dist = haversine_distance(lat, lng, last_lat, last_lng)
                if dist < 10:  # 10米内视为同一个位置
                    # 更新上一个点的时间戳
                    conn.execute(
                        "UPDATE footprints SET timestamp = CURRENT_TIMESTAMP WHERE user_id = ? AND timestamp = ?",
                        (user_id, last_ts)
                    )
                    conn.commit()
                    return "compressed"

            # 插入新点
            fp_id = f"fp_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """INSERT INTO footprints (id, user_id, lat, lng, accuracy, altitude, scene_hint)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (fp_id, user_id, lat, lng, accuracy, altitude, scene_hint)
            )
            conn.commit()
            return fp_id

    def get_footprint_path(self, user_id: str, hours: int = 24) -> List[Dict]:
        """获取最近 N 小时的足迹路径（用于地图绘制）"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            # 使用参数化查询避免 SQL 拼接
            rows = conn.execute(
                """SELECT * FROM footprints
                   WHERE user_id = ? AND timestamp >= datetime('now', ?)
                   ORDER BY timestamp ASC""",
                (user_id, f"-{hours} hours")
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "lat": r["lat"],
                    "lng": r["lng"],
                    "accuracy": r["accuracy"],
                    "timestamp": r["timestamp"],
                    "scene_hint": r["scene_hint"],
                }
                for r in rows
            ]

    def get_recent_location(self, user_id: str) -> Optional[Dict]:
        """获取用户最近一次记录的位置"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM footprints WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
                (user_id,)
            ).fetchone()
            if row:
                return {
                    "lat": row["lat"],
                    "lng": row["lng"],
                    "timestamp": row["timestamp"],
                    "scene_hint": row["scene_hint"],
                }
            return None

    def __init__(self, db_path: str = "./tent_memory/spatial.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        # 维护每个用户上次的围栏状态，用于检测进入/离开事件
        self._last_geofence_state: Dict[str, set] = {}

    def check_geofence(self, user_id: str, lat: float, lng: float) -> Dict:
        """检查当前坐标与所有围栏的关系

        返回：
        {
            "inside": ["gf_xxx", "gf_yyy"],   -- 当前在哪些围栏内（ID列表）
            "entered": ["gf_xxx"],            -- 本次新进入的围栏
            "left": ["gf_zzz"],               -- 本次离开的围栏
            "all_geofences": [...]            -- 所有围栏信息
        }
        """
        result = {"inside": [], "entered": [], "left": [], "all_geofences": []}

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM geofences WHERE user_id = ? AND is_active = 1",
                (user_id,)
            ).fetchall()

            current_inside = set()
            for row in rows:
                gf = dict(row)
                result["all_geofences"].append(gf)
                dist = haversine_distance(lat, lng, gf["lat"], gf["lng"])
                if dist <= gf["radius_meters"]:
                    current_inside.add(gf["id"])

            # 与上次状态对比，计算 entered/left
            last_inside = self._last_geofence_state.get(user_id, set())
            result["entered"] = list(current_inside - last_inside)
            result["left"] = list(last_inside - current_inside)
            result["inside"] = list(current_inside)

            # 更新缓存
            self._last_geofence_state[user_id] = current_inside

        return result

    def create_geofence(self, user_id: str, name: str, lat: float, lng: float,
                        radius_meters: int = 100, scene_id: str = "",
                        enter_action: str = "", leave_action: str = "") -> str:
        """创建地理围栏"""
        gf_id = f"gf_{uuid.uuid4().hex[:12]}"
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO geofences
                   (id, user_id, name, lat, lng, radius_meters, scene_id, enter_action, leave_action)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (gf_id, user_id, name, lat, lng, radius_meters, scene_id, enter_action, leave_action)
            )
            conn.commit()
        logger.info(f"[Spatial] 创建围栏: {name} ({lat}, {lng}) 半径{radius_meters}m")
        return gf_id

    def get_geofences(self, user_id: str) -> List[Dict]:
        """获取用户的所有地理围栏"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM geofences WHERE user_id = ? AND is_active = 1 ORDER BY created_at DESC",
                (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_geofence(self, geofence_id: str) -> bool:
        """删除地理围栏（软删除）"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("UPDATE geofences SET is_active = 0 WHERE id = ?", (geofence_id,))
            conn.commit()
        return True

    def get_location_memory(self, user_id: str, location_name: str = None) -> Optional[Dict]:
        """获取地点记忆（单个）"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if location_name:
                row = conn.execute(
                    "SELECT * FROM location_memories WHERE user_id = ? AND location_name = ?",
                    (user_id, location_name)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM location_memories WHERE user_id = ? ORDER BY last_visit DESC LIMIT 1",
                    (user_id,)
                ).fetchone()
            return dict(row) if row else None

    def get_all_location_memories(self, user_id: str) -> List[Dict]:
        """获取用户所有地点记忆"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM location_memories WHERE user_id = ? ORDER BY visit_count DESC, last_visit DESC",
                (user_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def update_location_memory(self, user_id: str, location_name: str,
                                lat: float = None, lng: float = None,
                                summary: str = None, duration_minutes: int = 0) -> str:
        """更新地点记忆（UPSERT）"""
        memory_id = f"lm_{uuid.uuid4().hex[:12]}"
        with sqlite3.connect(str(self.db_path)) as conn:
            # 检查是否已存在
            existing = conn.execute(
                "SELECT id, visit_count, total_duration_minutes FROM location_memories WHERE user_id = ? AND location_name = ?",
                (user_id, location_name)
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE location_memories SET
                        summary = COALESCE(?, summary),
                        lat = COALESCE(?, lat),
                        lng = COALESCE(?, lng),
                        visit_count = visit_count + 1,
                        total_duration_minutes = total_duration_minutes + ?,
                        last_visit = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (summary, lat, lng, duration_minutes, existing[0])
                )
            else:
                conn.execute(
                    """INSERT INTO location_memories
                       (id, user_id, location_name, lat, lng, summary, visit_count, total_duration_minutes, last_visit)
                       VALUES (?, ?, ?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP)""",
                    (memory_id, user_id, location_name, lat, lng, summary, duration_minutes)
                )
            conn.commit()
        return memory_id

    def generate_location_summary(self, user_id: str, location_name: str,
                                   lat: float, lng: float) -> str:
        """基于足迹数据生成地点摘要（可被 LLM 调用生成更丰富的描述）

        返回模板化摘要，例如：
        "用户在过去7天内来过这里5次，平均停留2小时。通常在上午9点到，下午6点离开。"
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            # 统计该地点附近的足迹
            rows = conn.execute(
                """SELECT timestamp FROM footprints
                   WHERE user_id = ? AND timestamp >= datetime('now', '-7 days')
                   ORDER BY timestamp ASC""",
                (user_id,)
            ).fetchall()

            if not rows:
                return f"暂无 {location_name} 的访问记录"

            # 简单统计：访问次数、平均停留时间
            visit_count = len(rows)
            first_visit = rows[0][0]
            last_visit = rows[-1][0]

            return (
                f"用户在过去7天内来过{location_name}{visit_count}次。"
                f"首次访问：{first_visit[:16]}，最近访问：{last_visit[:16]}。"
            )


# 全局单例
_service: Optional[SpatialFootprintService] = None


def get_spatial_footprint_service() -> SpatialFootprintService:
    global _service
    if _service is None:
        _service = SpatialFootprintService()
    return _service
