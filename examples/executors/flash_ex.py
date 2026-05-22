import httpx
from typing import Dict, Any

from tent_os.plugins.base import ExecutorPlugin


class FlashExExecutor(ExecutorPlugin):
    """闪送人类执行者——通过闪送 Open API 下单，由人类骑手完成物理配送"""
    
    def __init__(self):
        self.api_key = ""
        self.base_url = "https://open.ishansong.com"
        self.webhook_base = "http://localhost:8002/webhook"
    
    def name(self) -> str:
        return "flashex"
    
    def version(self) -> str:
        return "1.0.0"
    
    async def initialize(self, config: Dict) -> None:
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://open.ishansong.com")
        self.webhook_base = config.get("webhook_base", "http://localhost:8002/webhook")
    
    def supported_actions(self) -> list:
        return ["deliver", "pickup"]
    
    async def execute(self, action: str, params: Dict) -> Dict:
        if action not in ("deliver", "pickup"):
            return {"status": "failed", "error": f"不支持的action: {action}", "task_id": params.get("task_id")}
        
        webhook_url = f"{self.webhook_base}/{params.get('task_id', '')}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/api/v1/order/create",
                    json={
                        "pickup_address": params.get("pickup_address", ""),
                        "delivery_address": params.get("delivery_address", ""),
                        "item_description": params.get("item_description", ""),
                        "contact_name": params.get("contact_name", ""),
                        "contact_phone": params.get("contact_phone", ""),
                        "webhook_url": webhook_url
                    },
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                data = resp.json()
                return {
                    "task_id": data.get("order_id"),
                    "status": "pending",
                    "tracking_url": data.get("tracking_url")
                }
        except Exception as e:
            return {"status": "failed", "error": str(e), "task_id": params.get("task_id")}
    
    async def get_status(self, task_id: str) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/api/v1/order/{task_id}",
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                return resp.json()
        except Exception as e:
            return {"task_id": task_id, "status": "unknown", "error": str(e)}
