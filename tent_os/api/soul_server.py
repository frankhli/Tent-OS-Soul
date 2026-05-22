"""Tent OS Soul Intercom — API Server Entry Point

精简版：路由已拆分到 soul_routes.py，状态管理在 soul_state.py
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import uvicorn

from tent_os.bootstrap import load_config
from tent_os.logging_config import get_logger
from tent_os.api.soul_state import state, logger

# Default config path
_DEFAULT_CONFIG = os.environ.get("TENT_OS_CONFIG", "./config/tent_os.yaml")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config(_DEFAULT_CONFIG)
    await state.setup(config)
    yield
    await state.cleanup()


app = FastAPI(title="Tent OS Soul Intercom API", version="3.0.0", lifespan=lifespan)

# Mount static file directories
_TTS_DIR = Path(__file__).parent.parent.parent / "tent_memory" / "tts"
_TTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/tts", StaticFiles(directory=str(_TTS_DIR)), name="tts")

_PHOTO_DIR = Path("./tent_memory/soul/appearance_samples")
if _PHOTO_DIR.exists():
    app.mount("/photos", StaticFiles(directory=str(_PHOTO_DIR)), name="photos")

# Register API routes
from tent_os.api.soul_routes import router as soul_router
app.include_router(soul_router)
# 注意：前端静态文件服务已在 soul_routes.py 的 serve_ui 中实现


def run_server(host: str = "0.0.0.0", port: int = 8000, config_path: str = ""):
    """启动 Soul Intercom API Server（同步版本，在新线程中运行 uvicorn）
    
    注意：state.setup() 由 lifespan 管理器在 uvicorn 启动时调用。
    使用新线程避免与 main.py 的事件循环冲突。
    """
    import threading
    
    def _serve():
        uvicorn.run(app, host=host, port=port, log_level="info")
    
    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    return t

# 兼容旧导入名
run_api_server = run_server


if __name__ == "__main__":
    import sys
    cfg = sys.argv[1] if len(sys.argv) > 1 else ""
    port = 8003
    if cfg and cfg.isdigit():
        port = int(cfg)
    # 独立运行时直接在主线程运行 uvicorn（无需 threading）
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
