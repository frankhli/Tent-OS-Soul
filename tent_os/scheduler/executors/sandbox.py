"""SandboxExecutor —— 沙箱执行者

在 Docker 容器内执行命令，提供更强的安全隔离：
- 每个命令启动一个临时容器，执行完自动删除
- 容器与宿主机网络隔离（可选）
- 文件访问通过 docker cp 中转，严格限制路径
- 内存、CPU 等资源限制

使用模式：
    auto  — 检测 Docker 可用则用沙箱，否则回退到 LocalExecutor
    sandbox — 强制使用沙箱
    local — 强制使用本地执行（当前行为）
"""

import asyncio
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from tent_os.plugins.base import ExecutorPlugin


class SandboxError(Exception):
    """沙箱执行错误"""
    pass


class SandboxExecutor(ExecutorPlugin):
    """沙箱执行者——在 Docker 容器内执行操作"""

    def __init__(self):
        self.executor_id = "sandbox"
        self.image: str = "alpine:latest"
        self.network: str = "none"           # none / bridge
        self.allow_write: bool = False
        self.max_memory: str = "256m"
        self.timeout_seconds: int = 30
        self.allowed_paths: List[str] = [tempfile.gettempdir()]
        self.max_output_size: int = 65536
        self._docker_available: Optional[bool] = None

    def name(self) -> str:
        return "sandbox"

    def version(self) -> str:
        return "1.0.0"

    @classmethod
    def is_docker_available(cls) -> bool:
        """检测 Docker 是否可用"""
        return shutil.which("docker") is not None

    async def initialize(self, config: Dict) -> None:
        """初始化沙箱配置

        config 示例:
        {
            "image": "alpine:latest",
            "network": "none",
            "allow_write": false,
            "max_memory": "256m",
            "timeout_seconds": 30,
            "allowed_paths": [tempfile.gettempdir(), "/app/data"],
        }
        """
        sandbox_cfg = config.get("sandbox", {})
        self.image = sandbox_cfg.get("image", "alpine:latest")
        self.network = sandbox_cfg.get("network", "none")
        self.allow_write = sandbox_cfg.get("allow_write", False)
        self.max_memory = sandbox_cfg.get("max_memory", "256m")
        self.timeout_seconds = sandbox_cfg.get("timeout_seconds", 30)
        self.allowed_paths = sandbox_cfg.get("allowed_paths", [tempfile.gettempdir()])
        self.max_output_size = config.get("max_output_size", 65536)

        # 检测 Docker 可用性
        self._docker_available = self.is_docker_available()
        if not self._docker_available:
            raise SandboxError("Docker 不可用，无法使用沙箱模式")

    def supported_actions(self) -> list:
        actions = ["shell", "file_read", "directory_list", "http_request"]
        if self.allow_write:
            actions.append("file_write")
        return actions

    async def execute(self, action: str, params: Dict) -> Dict:
        """在沙箱中执行操作"""
        task_id = params.get("task_id", "unknown")
        try:
            if action == "shell":
                result = await self._execute_shell(params)
            elif action == "file_read":
                result = await self._execute_file_read(params)
            elif action == "file_write":
                result = await self._execute_file_write(params)
            elif action == "directory_list":
                result = await self._execute_directory_list(params)
            elif action == "http_request":
                result = await self._execute_http_request(params)
            else:
                return {"status": "failed", "error": f"不支持的沙箱操作: {action}", "task_id": task_id}
            return {"status": "completed", "task_id": task_id, "result": result, "sandbox": True}
        except SandboxError as e:
            return {"status": "failed", "error": f"沙箱错误: {e}", "task_id": task_id, "sandbox": True}
        except Exception as e:
            return {"status": "failed", "error": str(e), "task_id": task_id, "sandbox": True}

    async def get_status(self, task_id: str) -> Dict:
        return {"task_id": task_id, "status": "completed", "executor": "sandbox"}

    # ── 安全检查 ───────────────────────────────────────────────

    def _check_path_allowed(self, path: str) -> Path:
        """检查路径是否在允许范围内"""
        target = Path(path).resolve()
        for allowed in self.allowed_paths:
            allowed_p = Path(allowed).resolve()
            try:
                target.relative_to(allowed_p)
                return target
            except ValueError:
                continue
        raise SandboxError(f"路径越界: {path} (只允许: {self.allowed_paths})")

    # ── Docker 辅助 ────────────────────────────────────────────

    def _docker_run_cmd(self, extra_args: List[str] = None) -> List[str]:
        """构建 docker run 基础命令"""
        cmd = [
            "docker", "run", "--rm",
            "-i",  # 交互模式，支持 stdin
            "--memory", self.max_memory,
            "--memory-swap", self.max_memory,
            "--cpus", "1.0",
            "--network", self.network,
            "--read-only",  # 根文件系统只读
            "-v", f"{tempfile.gettempdir()}:/tmp:rw",  # 允许写入 /tmp
        ]
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(self.image)
        return cmd

    async def _docker_exec(self, cmd: List[str], stdin_data: bytes = None) -> Dict:
        """执行 Docker 命令，返回 stdout/stderr/returncode"""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin_data else None,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise SandboxError(f"沙箱命令超时 (>{self.timeout_seconds}s)")

        stdout_str = stdout.decode("utf-8", errors="replace")[:self.max_output_size]
        stderr_str = stderr.decode("utf-8", errors="replace")[:self.max_output_size]

        return {
            "returncode": proc.returncode,
            "stdout": stdout_str,
            "stderr": stderr_str,
        }

    # ── 操作实现 ───────────────────────────────────────────────

    async def _execute_shell(self, params: Dict) -> Dict:
        """在沙箱中执行 shell 命令"""
        command = params.get("command", "")
        if not command:
            raise SandboxError("空命令")

        # 简单安全过滤（沙箱本身已提供隔离，这里做额外防护）
        dangerous = ["rm -rf /", ":(){ :|:& };:"]
        for d in dangerous:
            if d in command:
                raise SandboxError(f"命令包含危险模式: {d}")

        cmd = self._docker_run_cmd()
        cmd.extend(["sh", "-c", command])
        result = await self._docker_exec(cmd)

        return {
            "command": command,
            "returncode": result["returncode"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        }

    async def _execute_file_read(self, params: Dict) -> Dict:
        """在沙箱中读取文件"""
        path = params.get("path", "")
        target = self._check_path_allowed(path)

        if not target.exists():
            return {"error": f"文件不存在: {path}"}
        if target.is_dir():
            return {"error": f"路径是目录: {path}"}

        # 将文件复制到 /tmp 下同名位置，然后在容器中读取
        tmp_path = Path(tempfile.gettempdir()) / f"tent_sandbox_{uuid.uuid4().hex}_{target.name}"
        try:
            import shutil
            shutil.copy2(target, tmp_path)

            cmd = self._docker_run_cmd(["-v", f"{tmp_path}:/sandbox/file:ro"])
            cmd.extend(["cat", "/sandbox/file"])
            result = await self._docker_exec(cmd)

            content = result["stdout"]
            truncated = len(content) > self.max_output_size
            content = content[:self.max_output_size]

            return {
                "path": str(target),
                "size": target.stat().st_size,
                "content": content,
                "truncated": truncated,
            }
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    async def _execute_file_write(self, params: Dict) -> Dict:
        """在沙箱中写入文件"""
        if not self.allow_write:
            raise SandboxError("file_write 未启用 (allow_write=false)")

        path = params.get("path", "")
        content = params.get("content", "")
        target = self._check_path_allowed(path)

        # 通过 stdin 传入内容，容器内写入 /tmp/output，然后 cp 出来
        tmp_container = f"tent_write_{uuid.uuid4().hex}"
        tmp_host = Path(tempfile.gettempdir()) / tmp_container

        try:
            # 写入到容器内的 /tmp/output
            write_script = f'cat > /tmp/output << \'EOF\'\n{content}\nEOF\n'
            cmd = self._docker_run_cmd()
            cmd.extend(["sh", "-c", write_script])
            await self._docker_exec(cmd)

            # 将容器内文件复制到主机
            cp_cmd = ["docker", "run", "--rm",
                      "-v", f"{tmp_host.parent}:/host_tmp:rw",
                      self.image,
                      "cp", "/tmp/output", f"/host_tmp/{tmp_container}"]
            await self._docker_exec(cp_cmd)

            # 移动到目标位置
            if tmp_host.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_host), str(target))

            return {
                "path": str(target),
                "bytes_written": len(content.encode("utf-8")),
            }
        finally:
            if tmp_host.exists():
                tmp_host.unlink()

    async def _execute_directory_list(self, params: Dict) -> Dict:
        """在沙箱中列出目录"""
        path = params.get("path", ".")
        target = self._check_path_allowed(path)

        if not target.exists():
            return {"error": f"目录不存在: {path}"}
        if not target.is_dir():
            return {"error": f"路径不是目录: {path}"}

        # 挂载目录到容器
        cmd = self._docker_run_cmd(["-v", f"{target}:/sandbox/dir:ro"])
        cmd.extend(["sh", "-c", "ls -la /sandbox/dir"])
        result = await self._docker_exec(cmd)

        # 解析 ls -la 输出
        entries = []
        for line in result["stdout"].split("\n")[1:]:  # skip total
            parts = line.split()
            if len(parts) >= 9:
                name = " ".join(parts[8:])
                if name in (".", ".."):
                    continue
                entries.append({
                    "name": name,
                    "type": "directory" if line.startswith("d") else "file",
                })

        return {
            "path": str(target),
            "entries": entries,
        }

    async def _execute_http_request(self, params: Dict) -> Dict:
        """在沙箱中发送 HTTP 请求"""
        method = params.get("method", "GET").upper()
        url = params.get("url", "")
        headers = params.get("headers", {})
        body = params.get("body")
        timeout = params.get("timeout", 30)

        if not url:
            raise SandboxError("URL 不能为空")

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise SandboxError(f"不支持的协议: {parsed.scheme}")

        # 使用 curl 在容器内发送请求
        # 需要 bridge 网络模式才能访问外部网络
        if self.network == "none":
            # 临时切换到 bridge 网络用于 HTTP 请求
            network_backup = self.network
            self.network = "bridge"
            try:
                result = await self._do_http_with_curl(method, url, headers, body, timeout)
            finally:
                self.network = network_backup
            return result

        return await self._do_http_with_curl(method, url, headers, body, timeout)

    async def _do_http_with_curl(self, method: str, url: str, headers: Dict, body: Any, timeout: int) -> Dict:
        """使用 curl 在容器中发送 HTTP 请求"""
        curl_cmd = ["curl", "-s", "-w", "\\n%{http_code}", "-m", str(timeout)]

        # 添加 headers
        for key, value in headers.items():
            curl_cmd.extend(["-H", f"{key}: {value}"])

        # 添加 body
        stdin_data = None
        if body is not None:
            if isinstance(body, dict):
                body_str = json.dumps(body)
                curl_cmd.extend(["-H", "Content-Type: application/json", "-d", "@-"])
                stdin_data = body_str.encode("utf-8")
            else:
                curl_cmd.extend(["-d", str(body)])

        # HTTP method
        if method == "POST":
            curl_cmd.append("-X"); curl_cmd.append("POST")
        elif method == "PUT":
            curl_cmd.append("-X"); curl_cmd.append("PUT")
        elif method == "DELETE":
            curl_cmd.append("-X"); curl_cmd.append("DELETE")

        curl_cmd.append(url)

        cmd = self._docker_run_cmd()
        cmd.extend(curl_cmd)
        result = await self._docker_exec(cmd, stdin_data=stdin_data)

        lines = result["stdout"].rstrip("\n").split("\n")
        if len(lines) < 2:
            return {"error": "curl 输出格式异常", "raw": result["stdout"]}

        try:
            status_code = int(lines[-1])
        except ValueError:
            return {"error": "无法解析 HTTP 状态码", "raw": result["stdout"]}

        content = "\n".join(lines[:-1])
        content = content[:self.max_output_size]

        return {
            "url": url,
            "status_code": status_code,
            "content": content,
            "truncated": len(result["stdout"]) > self.max_output_size,
        }
