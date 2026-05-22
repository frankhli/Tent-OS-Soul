import httpx
from typing import Dict, Any

from tent_os.plugins.base import ExecutorPlugin


class RealManExecutor(ExecutorPlugin):
    """睿尔曼机械臂执行者——通过 MCP Server 操控物理机械臂"""
    
    def __init__(self):
        self.mcp_server_url = ""
        self._supported_actions = ["move", "pick", "place", "observe", "diagnose"]
    
    def name(self) -> str:
        return "realman"
    
    def version(self) -> str:
        return "1.0.0"
    
    async def initialize(self, config: Dict) -> None:
        self.mcp_server_url = config.get("mcp_server_url", "")
    
    def supported_actions(self) -> list:
        return self._supported_actions
    
    async def execute(self, action: str, params: Dict) -> Dict:
        tool_map = {
            "move": "move_to_position",
            "pick": "force_control_grasp",
            "place": "move_to_position",
            "observe": "camera_capture",
            "diagnose": "ai_diagnosis"
        }
        tool_name = tool_map.get(action)
        if not tool_name:
            return {"status": "failed", "error": f"不支持的action: {action}", "task_id": params.get("task_id")}
        
        mcp_params = self._build_mcp_params(action, params)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.mcp_server_url}/tools/{tool_name}",
                    json={"parameters": mcp_params}
                )
                return resp.json()
        except Exception as e:
            return {"status": "failed", "error": str(e), "task_id": params.get("task_id")}
    
    async def get_status(self, task_id: str) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.mcp_server_url}/tasks/{task_id}")
                return resp.json()
        except Exception as e:
            return {"task_id": task_id, "status": "unknown", "error": str(e)}
    
    def _build_mcp_params(self, action: str, params: Dict) -> Dict:
        if action == "move":
            return {"x": params.get("x", 0), "y": params.get("y", 0), "z": params.get("z", 0)}
        elif action == "pick":
            return {"object_description": params.get("object", "")}
        return params
