"""示例插件：HTTP API 执行者

展示如何编写 Tent OS 外部插件。
此插件将外部 HTTP API 封装为执行者，可被调度进程调用。

使用场景：
- 对接第三方 SaaS 服务
- 调用内部微服务
- 封装专有硬件 API
"""

import httpx
from typing import Dict, Any

from tent_os.plugins.base import ExecutorPlugin


class HttpApiExecutor(ExecutorPlugin):
    """HTTP API 执行者 —— 调用外部 REST API"""
    
    def __init__(self):
        self.base_url = ""
        self.headers = {}
        self.timeout = 30
    
    def name(self) -> str:
        return "http_api"
    
    def version(self) -> str:
        return "1.0.0"
    
    async def initialize(self, config: Dict) -> None:
        self.base_url = config.get("base_url", "")
        self.headers = config.get("headers", {})
        self.timeout = config.get("timeout", 30)
    
    def supported_actions(self) -> list:
        return ["get", "post", "put", "delete"]
    
    async def execute(self, action: str, params: Dict) -> Dict:
        url = params.get("url", "")
        if not url.startswith("http"):
            url = self.base_url + url
        
        headers = {**self.headers, **params.get("headers", {})}
        body = params.get("body")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if action == "get":
                resp = await client.get(url, headers=headers)
            elif action == "post":
                resp = await client.post(url, headers=headers, json=body)
            elif action == "put":
                resp = await client.put(url, headers=headers, json=body)
            elif action == "delete":
                resp = await client.delete(url, headers=headers)
            else:
                return {"status": "failed", "error": f"不支持的动作: {action}"}
            
            return {
                "status": "completed",
                "status_code": resp.status_code,
                "content": resp.text[:5000],
                "headers": dict(resp.headers),
            }
    
    async def get_status(self, task_id: str) -> Dict:
        return {"task_id": task_id, "status": "completed", "executor": "http_api"}
