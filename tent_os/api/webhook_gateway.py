import json
import logging
import sqlite3
from fastapi import FastAPI, Request
import uvicorn

logger = logging.getLogger("tent_os.webhook")


class WebhookGateway:
    """统一Webhook入口，接收外部回调后转发到NATS"""
    
    def __init__(self, bus, db_path: str = "./tent_scheduler.db", port: int = 8002):
        self.bus = bus
        self.db = sqlite3.connect(db_path)
        self.port = port
        self.app = FastAPI()
        self._register_routes()
    
    def _register_routes(self):
        @self.app.post("/webhook/{task_id}")
        async def handle_webhook(task_id: str, request: Request):
            result = await request.json()
            cursor = self.db.execute("SELECT reply_to FROM tasks WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return {"status": "error", "message": f"任务不存在: {task_id}"}
            reply_to = row[0]
            self.db.execute("UPDATE tasks SET status = 'completed', result = ? WHERE task_id = ?",
                           (json.dumps(result), task_id))
            self.db.commit()
            await self.bus.publish(reply_to, json.dumps({
                "task_id": task_id, "status": result.get("status", "completed"), "result": result
            }).encode())
            return {"status": "ok"}
    
    async def start(self):
        config = uvicorn.Config(self.app, host="0.0.0.0", port=self.port, log_level="info")
        server = uvicorn.Server(config)
        try:
            await server.serve()
        except (OSError, SystemExit) as e:
            logger.warning(f"Webhook Gateway 端口 {self.port} 无法启动，跳过: {e}")
