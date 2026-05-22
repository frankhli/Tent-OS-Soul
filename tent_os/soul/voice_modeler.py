"""声纹建模引擎 —— 采集并建模用户声音特征"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from tent_os.logging_config import get_logger

logger = get_logger()


class VoiceModeler:
    """
    声纹建模引擎
    
    当前阶段（Phase 2）：
    - 采集和存储语音样本
    - 记录样本数量、时长、采集时间
    - 为未来的声音克隆模型准备数据
    
    未来阶段（Phase 3+）：
    - 接入 GPT-SoVITS / F5-TTS / CosyVoice 等克隆模型
    - 用积累的样本训练用户专属声纹模型
    - 实现真正的"就是他"的声音克隆
    """
    
    def __init__(self, storage_path: str = "./tent_memory/soul"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.voice_dir = self.storage_path / "voice_samples"
        self.voice_dir.mkdir(exist_ok=True)
        self.db_path = self.storage_path / "voice_models.db"
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS voice_profiles (
                    user_id TEXT PRIMARY KEY,
                    sample_count INTEGER DEFAULT 0,
                    total_duration_seconds REAL DEFAULT 0,
                    pitch_range TEXT DEFAULT '{}',
                    speed_wpm REAL DEFAULT 0,
                    timbre_tags TEXT DEFAULT '[]',
                    model_path TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS voice_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    sample_path TEXT NOT NULL,
                    duration_seconds REAL DEFAULT 0,
                    sample_quality REAL DEFAULT 0,
                    recorded_at TEXT DEFAULT (datetime('now')),
                    source TEXT DEFAULT 'manual',
                    transcript TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_samples_user ON voice_samples(user_id);
            """)
    
    async def ingest_sample(
        self,
        user_id: str,
        audio_path: str,
        duration_seconds: float = 0,
        source: str = "manual",
        transcript: str = "",
    ) -> Dict:
        """摄入一段语音样本"""
        import shutil
        src = Path(audio_path)
        if not src.exists():
            return {"status": "error", "error": "音频文件不存在"}
        
        user_dir = self.voice_dir / user_id
        user_dir.mkdir(exist_ok=True)
        dst = user_dir / f"{src.stem}_{int(__import__('time').time())}{src.suffix}"
        shutil.copy2(src, dst)
        
        # 尝试获取音频时长
        actual_duration = duration_seconds
        if actual_duration <= 0:
            actual_duration = self._estimate_duration(src)
        
        # 评估样本质量（基于时长）
        quality = self._estimate_quality(actual_duration)
        
        with sqlite3.connect(self.db_path) as conn:
            # 记录样本详情
            conn.execute(
                """INSERT INTO voice_samples 
                   (user_id, sample_path, duration_seconds, sample_quality, source, transcript)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, str(dst), actual_duration, quality, source, transcript),
            )
            
            # 更新用户档案
            row = conn.execute(
                "SELECT sample_count, total_duration_seconds FROM voice_profiles WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            if row:
                new_count = row[0] + 1
                new_duration = row[1] + actual_duration
                conn.execute(
                    "UPDATE voice_profiles SET sample_count = ?, total_duration_seconds = ?, updated_at = datetime('now') WHERE user_id = ?",
                    (new_count, new_duration, user_id)
                )
            else:
                new_count = 1
                new_duration = actual_duration
                conn.execute(
                    "INSERT INTO voice_profiles (user_id, sample_count, total_duration_seconds) VALUES (?, ?, ?)",
                    (user_id, 1, actual_duration)
                )
            conn.commit()
        
        logger.info(f"[SOUL] 声纹样本已采集 [{user_id}]: {dst.name}, 时长={actual_duration:.1f}s, 质量={quality:.0%}")
        
        # 评估克隆就绪状态
        readiness = self._check_clone_readiness(new_count, new_duration)
        
        return {
            "status": "ok",
            "sample_path": str(dst),
            "sample_count": new_count,
            "total_duration": new_duration,
            "quality": quality,
            "clone_readiness": readiness,
        }
    
    def _estimate_duration(self, audio_path: Path) -> float:
        """估算音频时长（回退方法：按文件大小估算）"""
        try:
            # 尝试用 mutagen 获取真实时长
            from mutagen.mp3 import MP3
            from mutagen.wave import WAVE
            
            suffix = audio_path.suffix.lower()
            if suffix == '.mp3':
                audio = MP3(str(audio_path))
                return audio.info.length
            elif suffix in ('.wav', '.wave'):
                audio = WAVE(str(audio_path))
                return audio.info.length
        except Exception:
            pass
        
        # 回退：按文件大小估算（webm ~ 16kbps, mp3 ~ 128kbps）
        size_bytes = audio_path.stat().st_size
        suffix = audio_path.suffix.lower()
        if suffix == '.webm':
            return size_bytes / 2000  # ~16kbps
        elif suffix == '.mp3':
            return size_bytes / 16000  # ~128kbps
        return size_bytes / 8000  # 默认 ~64kbps
    
    def _estimate_quality(self, duration: float) -> float:
        """估算样本质量（0-1）"""
        if duration < 2:
            return 0.3
        elif duration < 5:
            return 0.6
        elif duration < 10:
            return 0.8
        else:
            return min(1.0, 0.8 + (duration - 10) / 100)
    
    def _check_clone_readiness(self, sample_count: int, total_duration: float) -> Dict:
        """检查声音克隆的就绪状态
        
        当前阶段（Phase 2）：仅评估样本收集进度，不涉及真正的声纹建模。
        真正的声纹建模（speaker embedding、韵律分析）需要 Phase 3 的 GPU 环境。
        """
        # 最低门槛：2小时有效语音
        MIN_DURATION = 2 * 3600  # 7200秒
        # 最佳效果：10小时
        OPTIMAL_DURATION = 10 * 3600  # 36000秒
        # 最少样本数
        MIN_SAMPLES = 20
        
        duration_ratio = min(1.0, total_duration / MIN_DURATION)
        sample_ratio = min(1.0, sample_count / MIN_SAMPLES)
        collection_progress = (duration_ratio * 0.7 + sample_ratio * 0.3)
        
        # Phase 2: 样本收集进度（0-1）
        # Phase 3: 声纹建模就绪（需要 GPU + 克隆引擎）
        modeling_ready = False  # 当前硬件不支持真正的声纹建模
        
        if collection_progress >= 1.0:
            collection_status = "sufficient"
            collection_message = "声纹样本收集完成（满足最低门槛）"
        elif collection_progress >= 0.5:
            collection_status = "approaching"
            collection_message = f"声纹采集中，还需约 {max(0, MIN_DURATION - total_duration):.0f} 秒"
        else:
            collection_status = "insufficient"
            collection_message = f"声纹数据不足，建议继续采集（当前 {total_duration:.0f} 秒，目标 {MIN_DURATION} 秒）"
        
        return {
            "status": collection_status,
            "score": round(collection_progress, 2),
            "message": collection_message,
            "phase": "sample_collection",
            "modeling_ready": modeling_ready,
            "modeling_note": "声纹样本已收集，但真正的声纹建模（speaker embedding、韵律分析）需要 Phase 3 GPU 环境部署 GPT-SoVITS/F5-TTS",
            "min_required": MIN_DURATION,
            "optimal": OPTIMAL_DURATION,
            "current_duration": total_duration,
            "current_samples": sample_count,
        }
    
    def get_profile(self, user_id: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM voice_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row:
                return None
            return dict(row)
    
    def get_samples(self, user_id: str, limit: int = 50) -> List[Dict]:
        """获取用户的所有语音样本详情"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM voice_samples 
                   WHERE user_id = ? 
                   ORDER BY recorded_at DESC 
                   LIMIT ?""",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
    
    async def clone_voice(self, user_id: str) -> Dict:
        """触发声纹克隆（Phase 2: 仅验证样本收集状态；Phase 3: 集成真实克隆模型）"""
        profile = self.get_profile(user_id)
        samples = self.get_samples(user_id)
        
        if not profile or profile["sample_count"] < 3:
            return {
                "status": "insufficient_data",
                "message": "需要至少3段语音样本才能开始克隆",
                "sample_count": profile["sample_count"] if profile else 0,
            }
        
        readiness = self._check_clone_readiness(profile["sample_count"], profile["total_duration_seconds"])
        
        if readiness["status"] == "insufficient":
            return {
                "status": "insufficient_data",
                "message": readiness["message"],
                "readiness": readiness,
            }
        
        # Phase 2: 样本已收集，但真正的声纹建模尚未开始
        logger.info(f"[SOUL] 声纹样本已收集 [{user_id}]: {profile['sample_count']} 样本, {profile['total_duration_seconds']:.0f} 秒")
        
        return {
            "status": "data_collected",
            "message": "声纹样本已收集完成。当前处于 Phase 2（样本积累阶段），真正的声纹建模（speaker embedding、韵律分析、基频提取）需要 Phase 3 在 GPU 环境中部署 GPT-SoVITS、F5-TTS 或 CosyVoice 后启用。",
            "readiness": readiness,
            "phase": "sample_collection",
            "sample_count": profile["sample_count"],
            "total_duration": profile["total_duration_seconds"],
            "sample_paths": [s["sample_path"] for s in samples[:10]],
        }
    
    def delete_sample(self, user_id: str, sample_id: int) -> Dict:
        """删除指定样本"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT sample_path, duration_seconds FROM voice_samples WHERE id = ? AND user_id = ?",
                (sample_id, user_id),
            ).fetchone()
            if not row:
                return {"status": "error", "message": "样本不存在"}
            
            sample_path, duration = row
            conn.execute("DELETE FROM voice_samples WHERE id = ?", (sample_id,))
            
            # 更新用户档案
            conn.execute(
                "UPDATE voice_profiles SET sample_count = sample_count - 1, total_duration_seconds = total_duration_seconds - ?, updated_at = datetime('now') WHERE user_id = ?",
                (duration, user_id),
            )
            conn.commit()
            
            # 删除文件
            try:
                Path(sample_path).unlink(missing_ok=True)
            except Exception:
                pass
            
            return {"status": "ok", "deleted_duration": duration}
    
    def get_stats(self, user_id: str) -> Dict:
        """获取详细的声纹统计信息"""
        profile = self.get_profile(user_id)
        samples = self.get_samples(user_id, limit=100)
        
        if not profile:
            return {
                "user_id": user_id,
                "sample_count": 0,
                "total_duration": 0,
                "clone_ready": False,
                "samples": [],
            }
        
        readiness = self._check_clone_readiness(profile["sample_count"], profile["total_duration_seconds"])
        
        # 计算质量分布
        quality_buckets = {"高 (>8s)": 0, "中 (5-8s)": 0, "低 (<5s)": 0}
        for s in samples:
            d = s.get("duration_seconds", 0)
            if d > 8:
                quality_buckets["高 (>8s)"] += 1
            elif d >= 5:
                quality_buckets["中 (5-8s)"] += 1
            else:
                quality_buckets["低 (<5s)"] += 1
        
        return {
            "user_id": user_id,
            "sample_count": profile["sample_count"],
            "total_duration": profile["total_duration_seconds"],
            "total_duration_formatted": self._format_duration(profile["total_duration_seconds"]),
            "collection_complete": readiness["status"] == "sufficient",
            "clone_ready": False,  # Phase 2: 样本收集不等于建模就绪
            "modeling_phase": "sample_collection",
            "readiness": readiness,
            "quality_distribution": quality_buckets,
            "last_updated": profile.get("updated_at"),
            "recent_samples": [
                {
                    "id": s["id"],
                    "duration": s["duration_seconds"],
                    "quality": s["sample_quality"],
                    "source": s["source"],
                    "recorded_at": s["recorded_at"],
                }
                for s in samples[:10]
            ],
        }
    
    def _format_duration(self, seconds: float) -> str:
        """格式化时长显示"""
        if seconds < 60:
            return f"{seconds:.0f}秒"
        elif seconds < 3600:
            return f"{seconds/60:.1f}分钟"
        else:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            return f"{h}小时{m}分钟"
