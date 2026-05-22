"""形象建模引擎 —— 采集并建模用户视觉形象

Phase 2 增强：
- 照片质量评估
- 颜色特征提取（肤色、发色、瞳色）
- 个性化 Avatar 配置生成
- 为未来 3D 重建保留数据接口
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from tent_os.logging_config import get_logger

logger = get_logger()


class AppearanceModeler:
    """
    形象建模引擎

    当前阶段（Phase 2）：
    - 采集照片/视频
    - 提取颜色特征，生成个性化 2D Avatar 配置
    - 照片质量评估

    未来阶段（Phase 3+）：
    - 接入 DECA/FLAME 3D 重建
    - LivePortrait / SadTalker 驱动
    """

    def __init__(self, storage_path: str = "./tent_memory/soul"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.photo_dir = self.storage_path / "appearance_samples"
        self.photo_dir.mkdir(exist_ok=True)
        self.db_path = self.storage_path / "appearance_models.db"
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS appearance_profiles (
                    user_id TEXT PRIMARY KEY,
                    photo_count INTEGER DEFAULT 0,
                    video_count INTEGER DEFAULT 0,
                    face_shape TEXT,
                    expression_tags TEXT DEFAULT '[]',
                    action_style TEXT DEFAULT '{}',
                    model_path TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS appearance_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    sample_path TEXT NOT NULL,
                    sample_type TEXT DEFAULT 'photo',
                    quality_score REAL DEFAULT 0,
                    face_detected INTEGER DEFAULT 0,
                    dominant_colors TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS avatar_configs (
                    user_id TEXT PRIMARY KEY,
                    config_json TEXT DEFAULT '{}',
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_samples_user ON appearance_samples(user_id);
            """)

    async def ingest_photo(self, user_id: str, photo_path: str) -> Dict:
        """摄入一张照片，评估质量，提取颜色特征"""
        import shutil
        src = Path(photo_path)
        if not src.exists():
            return {"status": "error", "error": "照片文件不存在"}

        user_dir = self.photo_dir / user_id
        user_dir.mkdir(exist_ok=True)
        dst = user_dir / f"photo_{int(__import__('time').time())}{src.suffix}"
        shutil.copy2(src, dst)

        # 分析照片
        analysis = self._analyze_image(dst)

        with sqlite3.connect(self.db_path) as conn:
            # 记录样本
            conn.execute(
                """INSERT INTO appearance_samples
                   (user_id, sample_path, sample_type, quality_score, face_detected, dominant_colors)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, str(dst), 'photo', analysis.get('quality', 0),
                 1 if analysis.get('has_face') else 0,
                 json.dumps(analysis.get('colors', {}))),
            )
            # 更新档案
            row = conn.execute(
                "SELECT photo_count FROM appearance_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE appearance_profiles SET photo_count = photo_count + 1, updated_at = datetime('now') WHERE user_id = ?",
                    (user_id,)
                )
            else:
                conn.execute(
                    "INSERT INTO appearance_profiles (user_id, photo_count) VALUES (?, ?)",
                    (user_id, 1)
                )
            conn.commit()

        # 如果检测到人脸，尝试更新 Avatar 配置
        if analysis.get('has_face'):
            self._update_avatar_config_from_photos(user_id)

        logger.info(f"[SOUL] 形象照片已采集 [{user_id}]: {dst.name}, 质量={analysis.get('quality', 0):.0%}")
        return {
            "status": "ok",
            "photo_path": str(dst),
            "analysis": analysis,
        }

    async def ingest_video(self, user_id: str, video_path: str) -> Dict:
        """摄入一段视频（用于表情/动作采集）"""
        import shutil
        src = Path(video_path)
        if not src.exists():
            return {"status": "error", "error": "视频文件不存在"}

        user_dir = self.photo_dir / user_id
        user_dir.mkdir(exist_ok=True)
        dst = user_dir / f"video_{int(__import__('time').time())}{src.suffix}"
        shutil.copy2(src, dst)

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT video_count FROM appearance_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE appearance_profiles SET video_count = video_count + 1, updated_at = datetime('now') WHERE user_id = ?",
                    (user_id,)
                )
            else:
                conn.execute(
                    "INSERT INTO appearance_profiles (user_id, video_count) VALUES (?, ?)",
                    (user_id, 1)
                )
            conn.commit()

        logger.info(f"[SOUL] 形象视频已采集 [{user_id}]: {dst.name}")
        return {"status": "ok", "video_path": str(dst)}

    def _analyze_image(self, image_path: Path) -> Dict:
        """分析图片：质量、颜色、人脸检测（轻量级）"""
        result = {"quality": 0, "has_face": False, "colors": {}}

        try:
            from PIL import Image
            img = Image.open(image_path)
            w, h = img.size

            # 质量评估：分辨率 + 清晰度（简单方差估算）
            resolution_score = min(1.0, (w * h) / (640 * 480))

            # 尝试计算清晰度（拉普拉斯方差）
            sharpness = 0.5
            try:
                import cv2
                import numpy as np
                cv_img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
                if cv_img is not None:
                    lap_var = cv2.Laplacian(cv_img, cv2.CV_64F).var()
                    sharpness = min(1.0, lap_var / 500)
            except Exception:
                pass

            result["quality"] = round(resolution_score * 0.4 + sharpness * 0.6, 2)

            # 提取主色调（简化：取图像中心区域和四角区域的平均色）
            img_small = img.convert('RGB').resize((100, 100))
            pixels = list(img_small.getdata())

            # 肤色估算：找偏暖的中等亮度颜色
            skin_candidates = [(r, g, b) for r, g, b in pixels
                               if 80 < r < 240 and 50 < g < 200 and 40 < b < 180 and r > g > b - 30]
            if skin_candidates:
                sr = sum(c[0] for c in skin_candidates) / len(skin_candidates)
                sg = sum(c[1] for c in skin_candidates) / len(skin_candidates)
                sb = sum(c[2] for c in skin_candidates) / len(skin_candidates)
                result["colors"]["skin"] = {"r": int(sr), "g": int(sg), "b": int(sb)}

            # 头发色估算：偏暗的颜色（上半部分）
            top_pixels = pixels[:500]  # 简化：取前500像素
            hair_candidates = [(r, g, b) for r, g, b in top_pixels
                               if r + g + b < 350 and max(r, g, b) < 180]
            if hair_candidates:
                hr = sum(c[0] for c in hair_candidates) / len(hair_candidates)
                hg = sum(c[1] for c in hair_candidates) / len(hair_candidates)
                hb = sum(c[2] for c in hair_candidates) / len(hair_candidates)
                result["colors"]["hair"] = {"r": int(hr), "g": int(hg), "b": int(hb)}

            # 简单人脸检测：如果中心区域有肤色，认为可能有人脸
            center_pixels = pixels[4500:5500]  # 中心区域
            center_skin = [p for p in center_pixels
                           if 100 < p[0] < 230 and 60 < p[1] < 190 and 50 < p[2] < 170]
            result["has_face"] = len(center_skin) > len(center_pixels) * 0.3

        except Exception as e:
            logger.debug(f"[Appearance] 图片分析失败: {e}")

        return result

    def _update_avatar_config_from_photos(self, user_id: str):
        """根据所有照片更新 Avatar 配置"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT dominant_colors FROM appearance_samples WHERE user_id = ? AND sample_type = 'photo' ORDER BY created_at DESC LIMIT 10",
                (user_id,)
            ).fetchall()

        if not rows:
            return

        # 聚合颜色
        all_skin = []
        all_hair = []
        for row in rows:
            try:
                colors = json.loads(row[0] or '{}')
                if 'skin' in colors:
                    all_skin.append(colors['skin'])
                if 'hair' in colors:
                    all_hair.append(colors['hair'])
            except Exception:
                pass

        config = self._build_avatar_config(all_skin, all_hair)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO avatar_configs (user_id, config_json, updated_at)
                   VALUES (?, ?, datetime('now'))""",
                (user_id, json.dumps(config)),
            )
            conn.commit()

    def _build_avatar_config(self, skin_colors: List[Dict], hair_colors: List[Dict]) -> Dict:
        """根据颜色数据构建 Avatar 配置"""
        def avg_color(colors: List[Dict]) -> Optional[Tuple[int, int, int]]:
            if not colors:
                return None
            return (
                int(sum(c['r'] for c in colors) / len(colors)),
                int(sum(c['g'] for c in colors) / len(colors)),
                int(sum(c['b'] for c in colors) / len(colors)),
            )

        def rgb_to_hex(r: int, g: int, b: int) -> str:
            return f'#{r:02x}{g:02x}{b:02x}'

        def darken(hex_color: str, factor: float = 0.7) -> str:
            c = int(hex_color[1:], 16)
            r = int(((c >> 16) & 255) * factor)
            g = int(((c >> 8) & 255) * factor)
            b = int((c & 255) * factor)
            return f'#{r:02x}{g:02x}{b:02x}'

        def lighten(hex_color: str, factor: float = 1.3) -> str:
            c = int(hex_color[1:], 16)
            r = min(255, int(((c >> 16) & 255) * factor))
            g = min(255, int(((c >> 8) & 255) * factor))
            b = min(255, int((c & 255) * factor))
            return f'#{r:02x}{g:02x}{b:02x}'

        skin_avg = avg_color(skin_colors)
        hair_avg = avg_color(hair_colors)

        config = {
            "version": 2,
            "generated_at": datetime.now().isoformat(),
            "source": "photo_analysis",
        }

        if skin_avg:
            skin_hex = rgb_to_hex(*skin_avg)
            config["skin"] = {
                "base": skin_hex,
                "shadow": darken(skin_hex, 0.85),
                "highlight": lighten(skin_hex, 1.15),
                "blush": lighten(skin_hex, 1.1),  # 偏暖
            }

        if hair_avg:
            hair_hex = rgb_to_hex(*hair_avg)
            config["hair"] = {
                "base": hair_hex,
                "dark": darken(hair_hex, 0.75),
                "light": lighten(hair_hex, 1.2),
            }
        else:
            # 默认品牌色
            config["hair"] = {
                "base": "#4ecdc4",
                "dark": "#2d8a82",
                "light": "#7eede5",
            }

        # 眼睛默认绿色系（较难从照片提取，保留默认值）
        config["eyes"] = {
            "iris": "#2d6a4f",
            "pupil": "#0f172a",
            "highlight": "#ffffff",
        }

        return config

    def get_avatar_config(self, user_id: str) -> Optional[Dict]:
        """获取用户的 Avatar 配置"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT config_json FROM avatar_configs WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except Exception:
                    pass
        return None

    def set_avatar_config(self, user_id: str, config: Dict) -> Dict:
        """手动设置 Avatar 配置"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO avatar_configs (user_id, config_json, updated_at)
                   VALUES (?, ?, datetime('now'))""",
                (user_id, json.dumps(config)),
            )
            conn.commit()
        return {"status": "ok"}

    def get_profile(self, user_id: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM appearance_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def get_samples(self, user_id: str, limit: int = 50) -> List[Dict]:
        """获取用户的所有形象样本"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM appearance_samples
                   WHERE user_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self, user_id: str) -> Dict:
        """获取详细的形象统计"""
        profile = self.get_profile(user_id)
        samples = self.get_samples(user_id, limit=100)
        config = self.get_avatar_config(user_id)

        # 计算质量分布
        quality_buckets = {"高 (>0.7)": 0, "中 (0.4-0.7)": 0, "低 (<0.4)": 0}
        face_detected_count = 0
        for s in samples:
            q = s.get("quality_score", 0)
            if q > 0.7:
                quality_buckets["高 (>0.7)"] += 1
            elif q >= 0.4:
                quality_buckets["中 (0.4-0.7)"] += 1
            else:
                quality_buckets["低 (<0.4)"] += 1
            if s.get("face_detected"):
                face_detected_count += 1

        # Phase 2 评估：样本收集进度（非 3D 建模就绪度）
        photo_count = profile.get("photo_count", 0) if profile else 0
        collection_progress = min(1.0, photo_count / 5)  # 5张为理想目标

        return {
            "user_id": user_id,
            "photo_count": photo_count,
            "video_count": profile.get("video_count", 0) if profile else 0,
            "face_detected_count": face_detected_count,
            "has_avatar_config": config is not None,
            "avatar_config": config,
            "collection_progress": round(collection_progress, 2),
            "phase": "2d_color_extraction",
            "modeling_ready": False,
            "modeling_note": "照片已收集并提取颜色特征用于 Avatar 着色。真正的 3D 形象重建需要 Phase 3 GPU 环境。",
            "quality_distribution": quality_buckets,
            "recent_samples": [
                {
                    "id": s["id"],
                    "type": s["sample_type"],
                    "quality": s["quality_score"],
                    "has_face": bool(s["face_detected"]),
                    "created_at": s["created_at"],
                }
                for s in samples[:10]
            ],
        }

    async def generate_avatar(self, user_id: str) -> Dict:
        """生成数字形象（Phase 2：返回个性化 Avatar 配置）
        
        当前阶段：仅提取颜色特征用于 2D Avatar 着色。
        真正的 3D 形象重建（DECA/FLAME + 表情绑定）需要 Phase 3 GPU 环境。
        """
        profile = self.get_profile(user_id)
        config = self.get_avatar_config(user_id)

        if not profile or profile["photo_count"] < 1:
            return {"status": "insufficient_data", "message": "需要至少1张照片"}

        if not config:
            return {
                "status": "no_config",
                "message": "尚未生成个性化配置，请重新上传照片",
                "photo_count": profile["photo_count"],
            }

        return {
            "status": "ok",
            "config": config,
            "photo_count": profile["photo_count"],
            "phase": "2d_color_extraction",
            "modeling_ready": False,
            "message": "个性化 Avatar 配色已生成。当前处于 Phase 2（颜色特征提取阶段），真正的 3D 形象重建（面部 mesh、表情 blendshape、动态习惯建模）需要 Phase 3 在 GPU 环境中部署 DECA/FLAME 后启用。",
        }
