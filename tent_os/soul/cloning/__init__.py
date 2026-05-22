"""
Tent OS Soul Cloning — Phase 3 预留接口

本包包含声音克隆、形象克隆、视频对话的架构预留接口。
当前（Phase 2）仅提供数据格式定义和适配器基类，
真正的建模能力需要 Phase 3 GPU 环境部署后启用。
"""

from .voice_clone_adapter import VoiceCloneAdapter, VoiceCloneResult
from .avatar_3d_adapter import Avatar3DAdapter, Avatar3DResult
from .video_call_engine import VideoCallEngine, VideoCallSession

__all__ = [
    "VoiceCloneAdapter", "VoiceCloneResult",
    "Avatar3DAdapter", "Avatar3DResult",
    "VideoCallEngine", "VideoCallSession",
]
