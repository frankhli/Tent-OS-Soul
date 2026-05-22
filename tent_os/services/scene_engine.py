"""SceneEngine —— 场景自适应引擎

核心职责：
1. 场景检测：根据 GPS 坐标 + 地理围栏，判断当前处于哪个场景
2. 场景切换：进入新场景时，加载该场景的配置（设备清单、人格、权限）
3. 自动动作：执行 enter / leave 动作列表
4. 人格切换：通过 NATS 发布场景事件，通知治理进程切换人格

场景配置来源：config/tent_os.yaml 的 scenes: 段
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime

from tent_os.logging_config import get_logger

logger = get_logger()


class SceneEngine:
    """场景引擎 —— AI 的上下文感知层"""

    def __init__(self, bus, config: Dict):
        self.bus = bus
        self.scenes = config.get("scenes", {})
        # 多用户场景状态：user_id -> scene_id
        self.current_scene: Dict[str, str] = {}
        # 多用户进入时间：user_id -> datetime
        self._scene_entry_time: Dict[str, datetime] = {}

    def _is_inside_geofence(self, lat: float, lng: float, scene_cfg: Dict) -> bool:
        """判断坐标是否在场景围栏内"""
        from tent_os.services.spatial_footprint_service import haversine_distance
        location = scene_cfg.get("location", {})
        scene_lat = location.get("lat", 0)
        scene_lng = location.get("lng", 0)
        radius = scene_cfg.get("geofence_radius", 100)
        if scene_lat == 0 and scene_lng == 0:
            return False
        dist = haversine_distance(lat, lng, scene_lat, scene_lng)
        return dist <= radius

    async def on_location_update(self, user_id: str, lat: float, lng: float):
        """GPS 坐标更新时的场景检测入口"""
        # 1. 检查是否在任一已知场景围栏内
        matched_scene = None
        for scene_id, scene_cfg in self.scenes.items():
            if self._is_inside_geofence(lat, lng, scene_cfg):
                matched_scene = scene_id
                break

        current = self.current_scene.get(user_id)

        if matched_scene:
            if current != matched_scene:
                # 进入新场景
                if current is not None:
                    await self._leave_scene(user_id, current)
                await self._enter_scene(user_id, matched_scene, self.scenes[matched_scene])
        else:
            # 不在任何已知场景内 → 户外/通勤/未知
            if current is not None and current != "outdoor":
                await self._leave_scene(user_id, current)
            if current != "outdoor":
                self.current_scene[user_id] = "outdoor"
                logger.info(f"[Scene] 用户 {user_id} 进入户外/未知区域")

    async def _enter_scene(self, user_id: str, scene_id: str, scene_cfg: Dict):
        """进入场景"""
        self.current_scene[user_id] = scene_id
        self._scene_entry_time[user_id] = datetime.now()

        scene_name = scene_cfg.get("name", scene_id)
        persona = scene_cfg.get("persona", "work")
        devices = scene_cfg.get("devices", [])

        logger.info(f"[Scene] 进入场景: {scene_name} (persona={persona})")

        # 1. 发布场景进入事件
        if self.bus:
            await self.bus.publish_raw("scene.entered", json.dumps({
                "user_id": user_id,
                "scene_id": scene_id,
                "scene_name": scene_name,
                "persona": persona,
                "devices": devices,
                "timestamp": datetime.now().isoformat(),
            }).encode())

        # 2. 更新用户画像的 active_scene
        try:
            from tent_os.memory.user_profile import UserProfileStore
            store = UserProfileStore()
            profile = store.get_or_create(user_id)
            profile.active_scene = scene_id
            store._save(profile)
        except Exception as e:
            logger.debug(f"[Scene] 更新用户画像失败: {e}")

        # 3. 执行自动动作
        auto_actions = scene_cfg.get("auto_actions", {})
        for action in auto_actions.get("enter", []):
            await self._execute_scene_action(scene_id, action, user_id)

    async def _leave_scene(self, user_id: str, scene_id: str):
        """离开场景"""
        scene_cfg = self.scenes.get(scene_id, {})
        scene_name = scene_cfg.get("name", scene_id)

        # 计算停留时长
        duration_minutes = 0
        entry_time = self._scene_entry_time.get(user_id)
        if entry_time:
            duration = (datetime.now() - entry_time).total_seconds()
            duration_minutes = int(duration / 60)

        logger.info(f"[Scene] 离开场景: {scene_name} (停留 {duration_minutes} 分钟)")

        # 1. 发布场景离开事件
        if self.bus:
            # Phase 3: 传递 persona 用于可控遗忘
            persona = scene_cfg.get("persona", "work")
            await self.bus.publish_raw("scene.left", json.dumps({
                "user_id": user_id,
                "scene_id": scene_id,
                "scene_name": scene_name,
                "persona": persona,
                "duration_minutes": duration_minutes,
                "timestamp": datetime.now().isoformat(),
            }).encode())

        # 2. 执行离开动作
        auto_actions = scene_cfg.get("auto_actions", {})
        for action in auto_actions.get("leave", []):
            await self._execute_scene_action(scene_id, action, user_id)

        # 3. 更新地点记忆（停留时长）
        try:
            from tent_os.services.spatial_footprint_service import get_spatial_footprint_service
            sf = get_spatial_footprint_service()
            location = scene_cfg.get("location", {})
            sf.update_location_memory(
                user_id=user_id,
                location_name=scene_name,
                lat=location.get("lat"),
                lng=location.get("lng"),
                duration_minutes=duration_minutes,
            )
        except Exception as e:
            logger.debug(f"[Scene] 更新地点记忆失败: {e}")

        if user_id in self.current_scene:
            del self.current_scene[user_id]
        if user_id in self._scene_entry_time:
            del self._scene_entry_time[user_id]

    async def _execute_scene_action(self, scene_id: str, action: str, user_id: str):
        """执行场景自动动作

        将自然语言动作（如"开灯"）映射为 scheduler 可执行的任务
        MVP 阶段简化：直接发布到 NATS，由 governance 处理
        """
        logger.info(f"[Scene] 执行动作: {action} @ {scene_id}")

        if self.bus:
            await self.bus.publish_raw("scene.action", json.dumps({
                "user_id": user_id,
                "scene_id": scene_id,
                "action": action,
                "timestamp": datetime.now().isoformat(),
            }).encode())

    def get_current_scene(self, user_id: str = "frank") -> Optional[Dict]:
        """获取当前场景信息"""
        scene_id = self.current_scene.get(user_id)
        if not scene_id:
            return None
        if scene_id == "outdoor":
            return {"scene_id": "outdoor", "name": "户外", "type": "outdoor", "persona": "work"}
        cfg = self.scenes.get(scene_id, {})
        return {
            "scene_id": scene_id,
            "name": cfg.get("name", scene_id),
            "type": cfg.get("type", "unknown"),
            "persona": cfg.get("persona", "work"),
            "devices": cfg.get("devices", []),
            "permissions": cfg.get("permissions", []),
        }

    def get_all_scenes(self) -> List[Dict]:
        """获取所有配置的场景"""
        result = []
        for scene_id, cfg in self.scenes.items():
            result.append({
                "scene_id": scene_id,
                "name": cfg.get("name", scene_id),
                "type": cfg.get("type", "unknown"),
                "persona": cfg.get("persona", "work"),
                "location": cfg.get("location", {}),
                "geofence_radius": cfg.get("geofence_radius", 100),
                "device_count": len(cfg.get("devices", [])),
            })
        return result

    def get_scene_devices(self, scene_id: str) -> List[Dict]:
        """获取某个场景的设备清单"""
        cfg = self.scenes.get(scene_id, {})
        return cfg.get("devices", [])
