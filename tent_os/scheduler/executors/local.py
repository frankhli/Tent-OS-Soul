"""LocalExecutor —— 本地执行者

在 Tent OS 运行的电脑上执行本地操作：
- shell: 受限命令执行（白名单+模式检查）
- file_read: 读取文件内容
- file_write: 写入文件内容
- directory_list: 列出目录内容
- http_request: 发送 HTTP 请求

安全模型：
1. 命令白名单：只允许显式配置的命令
2. 路径限制：只能访问 allowed_paths 下的路径
3. 模式黑名单：禁止危险模式（rm -rf、格式化等）
4. PolicyEngine 前置审批：高风险操作需策略引擎批准
"""

import asyncio
import json
import logging
import os
import re
import shlex
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

import httpx

from tent_os.plugins.base import ExecutorPlugin

logger = logging.getLogger(__name__)


class AuditLogger:
    """本地执行审计日志 —— 记录所有 shell/file/http 操作"""
    
    def __init__(self, db_path: str = "./tent_memory/audit.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA busy_timeout = 5000")
            db.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    session_id TEXT,
                    action TEXT NOT NULL,
                    params TEXT,
                    status TEXT NOT NULL,
                    result_summary TEXT,
                    duration_ms INTEGER,
                    security_violation INTEGER DEFAULT 0
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_session 
                ON audit_log(session_id, timestamp)
            """)
            db.commit()
    
    def log(self, session_id: str, action: str, params: Dict, 
            status: str, result_summary: str, duration_ms: int,
            security_violation: bool = False):
        try:
            with sqlite3.connect(self.db_path) as db:
                db.execute("PRAGMA busy_timeout = 5000")
                db.execute("""
                    INSERT INTO audit_log 
                    (timestamp, session_id, action, params, status, result_summary, duration_ms, security_violation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    time.time(), session_id or "", action,
                    json.dumps(params, ensure_ascii=False, default=str)[:4000],
                    status, result_summary[:2000], duration_ms,
                    1 if security_violation else 0
                ))
                db.commit()
        except Exception:
            # 审计日志失败不能阻塞主流程
            pass


class SecurityError(Exception):
    """本地执行安全违规"""
    pass


class RequireApprovalError(Exception):
    """危险操作需要用户二次确认"""
    def __init__(self, message: str, operation: str, details: Dict = None):
        super().__init__(message)
        self.operation = operation
        self.details = details or {}


class LocalExecutor(ExecutorPlugin):
    """本地执行者——在运行 Tent OS 的电脑上执行操作"""

    # 默认允许的基础命令（跨平台：Unix + Windows）
    DEFAULT_ALLOWED_COMMANDS_UNIX = {
        "ls", "cat", "head", "tail", "grep", "find", "pwd", "echo",
        "curl", "wget", "python3", "python", "date", "whoami", "uname",
        "ps", "top", "df", "du", "wc", "sort", "uniq", "diff",
        "git", "npm", "pip", "pytest", "python -m",
        "rm", "mv", "cp", "mkdir", "touch", "chmod", "chown",
    }
    DEFAULT_ALLOWED_COMMANDS_WIN = {
        "dir", "type", "findstr", "find", "cd", "echo", "date", "time",
        "curl", "python", "python3", "git", "npm", "pip", "pytest", "python -m",
    }
    # 通用命令（跨平台都存在）
    DEFAULT_ALLOWED_COMMANDS_COMMON = {
        "git", "npm", "pip", "pytest", "python", "python3", "python -m",
        "curl", "echo", "date",
    }

    @classmethod
    def _get_default_allowed_commands(cls) -> set:
        """根据平台返回默认允许命令集合"""
        if os.name == "nt":
            return cls.DEFAULT_ALLOWED_COMMANDS_WIN | cls.DEFAULT_ALLOWED_COMMANDS_COMMON
        return cls.DEFAULT_ALLOWED_COMMANDS_UNIX | cls.DEFAULT_ALLOWED_COMMANDS_COMMON

    # 默认禁止的危险模式（跨平台）
    DEFAULT_BLOCKED_PATTERNS = [
        r"rm\s+-[rf]*[rf]",           # rm -rf, rm -fr
        r">\s*/dev/\w+",               # 重定向到设备
        r"mkfs",                        # 格式化
        r"dd\s+if=",                   # dd 写盘
        r":\(\)\{\s*:\|:&\};:",       # fork bomb
        r"chmod\s+-[R]*\s*777",        # 全开权限
        r"curl\s+.*\s*\|\s*sh",        # curl | sh
        r"wget\s+.*\s*\|\s*sh",        # wget | sh
        r"sudo",                        # sudo（默认禁止）
        r">\s*~/.\w+",                 # 覆盖 home 下隐藏文件
    ]
    DEFAULT_BLOCKED_PATTERNS_WIN = [
        r"rmdir\s+/s\s+/q",
        r"del\s+/f\s+/s\s+/q",
        r"format\s+",
        r"diskpart",
        r"rd\s+/s",
        r"erase\s+/s",
    ]

    @classmethod
    def _get_default_blocked_patterns(cls) -> List[str]:
        if os.name == "nt":
            return cls.DEFAULT_BLOCKED_PATTERNS_WIN
        return cls.DEFAULT_BLOCKED_PATTERNS

    def __init__(self):
        self.executor_id = "local"
        self.allowed_commands: set = set()
        self.blocked_patterns: List[str] = []
        self.allowed_paths: List[str] = []
        self.allow_write: bool = False
        self.max_output_size: int = 65536  # 64KB 输出上限
        self.timeout_seconds: int = 30
        # Workspace 安全模式
        self.workspace_mode: str = "unrestricted"  # unrestricted | workspace | readonly
        self.workspace_path: Optional[Path] = None
        self.auto_approve: bool = False  # P1-2: 自动化模式，自动批准低风险操作
        # 审计日志
        self.audit_logger: Optional[AuditLogger] = None

    def name(self) -> str:
        return "local"

    def version(self) -> str:
        return "1.0.0"

    async def initialize(self, config: Dict) -> None:
        """初始化安全配置

        config 示例:
        {
            "workspace_mode": "workspace",      # unrestricted | workspace | readonly
            "workspace_path": "/home/user/project",
            "allowed_commands": ["ls", "cat", "python3"],
            "blocked_patterns": ["rm -rf"],
            "allowed_paths": ["/tmp", "/home/user/project"],
            "allow_write": false,
            "timeout_seconds": 30,
        }
        """
        self.executor_id = config.get("executor_id", "local")
        # FIX: 使用跨平台默认命令和白名单
        self.allowed_commands = set(config.get("allowed_commands", self._get_default_allowed_commands()))
        self.blocked_patterns = config.get("blocked_patterns", self._get_default_blocked_patterns())
        self.timeout_seconds = config.get("timeout_seconds", 30)
        
        # 初始化审计日志
        audit_db_path = config.get("audit_db_path", "./tent_memory/audit.db")
        self.audit_logger = AuditLogger(audit_db_path)
        
        # Workspace 模式解析
        self.workspace_mode = config.get("workspace_mode", "unrestricted")
        self.auto_approve = config.get("auto_approve", False)
        ws_path = config.get("workspace_path", "")
        if ws_path:
            self.workspace_path = Path(ws_path).expanduser().resolve()
            self.workspace_path.mkdir(parents=True, exist_ok=True)
        
        # FIX: 跨平台临时目录
        default_temp = tempfile.gettempdir()
        home_path = str(Path.home())
        
        # 根据模式设置 allowed_paths 和 allow_write
        if self.workspace_mode == "unrestricted":
            self.allowed_paths = config.get("allowed_paths", [home_path, default_temp])
            self.allow_write = config.get("allow_write", False)
        elif self.workspace_mode == "workspace":
            # 限制在 workspace 内，允许读写
            if self.workspace_path:
                self.allowed_paths = [str(self.workspace_path)]
            else:
                self.allowed_paths = [home_path, default_temp]
            self.allow_write = config.get("allow_write", True)
        elif self.workspace_mode == "readonly":
            # 限制在 workspace 内，只读
            if self.workspace_path:
                self.allowed_paths = [str(self.workspace_path)]
            else:
                self.allowed_paths = [home_path, default_temp]
            self.allow_write = False
        else:
            self.allowed_paths = config.get("allowed_paths", [home_path, default_temp])
            self.allow_write = config.get("allow_write", False)

    def supported_actions(self) -> list:
        actions = ["shell", "file_read", "directory_list", "http_request"]
        if self.allow_write:
            actions.append("file_write")
        return actions

    async def execute(self, action: str, params: Dict) -> Dict:
        """执行本地操作（带审计日志包装）"""
        task_id = params.get("task_id", "unknown")
        session_id = params.get("session_id", "")
        start_time = time.time()
        
        status = "failed"
        result_summary = ""
        security_violation = False
        result = None
        
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
                result = {"error": f"不支持的本地操作: {action}"}
                result_summary = f"不支持的操作: {action}"
                status = "failed"
                if self.audit_logger:
                    self.audit_logger.log(session_id, action, params, status, result_summary,
                                          int((time.time() - start_time) * 1000), security_violation)
                return {"status": "failed", "error": f"不支持的本地操作: {action}", "task_id": task_id}
            
            status = "completed"
            # 生成结果摘要（避免记录完整大内容）
            if isinstance(result, dict):
                if "error" in result:
                    status = "failed"
                    result_summary = result.get("error", "")[:500]
                elif action == "shell":
                    result_summary = f"cmd={result.get('command','')[:100]} rc={result.get('returncode')} stdout_len={len(result.get('stdout',''))}"
                elif action == "file_read":
                    result_summary = f"path={result.get('path','')} size={result.get('size')} truncated={result.get('truncated')}"
                elif action == "file_write":
                    result_summary = f"path={result.get('path','')} bytes={result.get('bytes_written')}"
                elif action == "directory_list":
                    result_summary = f"path={result.get('path','')} entries={len(result.get('entries',[]))}"
                elif action == "http_request":
                    result_summary = f"url={result.get('url','')[:100]} status={result.get('status_code')}"
                else:
                    result_summary = str(result)[:200]
            
            if self.audit_logger:
                self.audit_logger.log(session_id, action, params, status, result_summary,
                                      int((time.time() - start_time) * 1000), security_violation)
            return {"status": "completed", "task_id": task_id, "result": result}
            
        except RequireApprovalError as e:
            status = "require_approval"
            result_summary = f"需要确认: {e}"[:500]
            if self.audit_logger:
                self.audit_logger.log(session_id, action, params, status, result_summary,
                                      int((time.time() - start_time) * 1000), security_violation)
            return {
                "status": "require_approval",
                "error": str(e),
                "task_id": task_id,
                "operation": e.operation,
                "details": e.details,
            }
        except SecurityError as e:
            status = "failed"
            security_violation = True
            result_summary = f"安全拦截: {e}"[:500]
            if self.audit_logger:
                self.audit_logger.log(session_id, action, params, status, result_summary,
                                      int((time.time() - start_time) * 1000), security_violation)
            return {"status": "failed", "error": f"安全拦截: {e}", "task_id": task_id, "security_violation": True}
        except Exception as e:
            status = "failed"
            result_summary = str(e)[:500]
            if self.audit_logger:
                self.audit_logger.log(session_id, action, params, status, result_summary,
                                      int((time.time() - start_time) * 1000), security_violation)
            return {"status": "failed", "error": str(e), "task_id": task_id}

    async def get_status(self, task_id: str) -> Dict:
        """本地操作是同步的，直接返回完成状态"""
        return {"task_id": task_id, "status": "completed", "executor": "local"}

    # ── 安全检查 ───────────────────────────────────────────────

    def _resolve_path(self, path: str) -> Path:
        """解析路径：展开 ~ 并在 workspace 模式下，相对路径相对于 workspace 解析"""
        p = Path(path).expanduser()  # FIX: 展开 ~ 为用户 home 目录
        if self.workspace_mode in ("workspace", "readonly") and self.workspace_path:
            if not p.is_absolute():
                # 相对路径 → 相对于 workspace
                return (self.workspace_path / p).resolve()
            # 绝对路径 → 保持原样（后续 _check_path_allowed 会检查是否在允许范围内）
            return p.resolve()
        # unrestricted / full 模式：按原样解析
        return p.resolve()

    def _check_path_allowed(self, path: str) -> Path:
        """检查路径是否在允许范围内"""
        target = self._resolve_path(path)
        
        # full 模式：完全开放，任何路径都允许
        if self.workspace_mode == "full":
            return target
        
        # workspace / readonly 模式：限制在 allowed_paths 内
        for allowed in self.allowed_paths:
            allowed_p = Path(allowed).resolve()
            try:
                target.relative_to(allowed_p)
                return target
            except ValueError:
                continue
        raise SecurityError(f"路径越界: {path} -> {target} (只允许: {self.allowed_paths})")

    def _check_command_safe(self, command: str) -> None:
        """检查命令是否安全"""
        # 1. 检查黑名单模式
        for pattern in self.blocked_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                raise SecurityError(f"命令包含禁止模式: {pattern}")

        # 2. 解析命令，检查是否在白名单
        # FIX: Windows 下 shlex.split 需要 posix=False
        try:
            tokens = shlex.split(command, posix=(os.name != "nt"))
        except ValueError:
            raise SecurityError("命令解析失败")

        if not tokens:
            raise SecurityError("空命令")

        base_cmd = tokens[0]

        # 处理 "python -m pytest" 这样的情况
        if base_cmd in ("python", "python3") and len(tokens) >= 3 and tokens[1] == "-m":
            module_cmd = tokens[2]
            full_cmd = f"{base_cmd} -m {module_cmd}"
        else:
            full_cmd = base_cmd

        # 检查命令是否在白名单
        if full_cmd not in self.allowed_commands and base_cmd not in self.allowed_commands:
            raise SecurityError(f"命令未授权: {base_cmd} (白名单: {self.allowed_commands})")

    # ── 操作实现 ───────────────────────────────────────────────

    def _check_dangerous_operation(self, action: str, params: Dict) -> None:
        """检测危险操作，需要用户二次确认
        
        触发条件（unrestricted 模式下）：
        - shell: rm, mv, 重定向覆盖 (>)
        - file_write: 覆盖已存在文件
        
        如果 params 中包含 __confirmed: true，说明用户已确认，跳过检查。
        P1-2 FIX: 自动化模式下（auto_approve=true），只记录警告日志，不阻塞执行。
        """
        if params.get("__confirmed"):
            return
        
        if self.workspace_mode in ("workspace", "readonly"):
            # workspace/readonly 模式下，路径已限制在 workspace 内，风险较低
            return
        
        def _maybe_approve(msg: str, operation: str, details: Dict):
            """根据 auto_approve 配置决定是抛出异常还是记录日志"""
            if self.auto_approve:
                logger.warning(f"[AUTO-APPROVE] {msg}")
                return
            raise RequireApprovalError(msg, operation=operation, details=details)
        
        if action == "shell":
            command = params.get("command", "")
            # 检测 rm / mv
            if re.search(r"\brm\b", command, re.IGNORECASE):
                _maybe_approve(
                    f"检测到删除命令，需要确认: {command[:100]}",
                    operation="dangerous_shell",
                    details={"command": command, "reason": "delete_operation"}
                )
            if re.search(r"\bmv\b", command, re.IGNORECASE):
                _maybe_approve(
                    f"检测到移动/重命名命令，需要确认: {command[:100]}",
                    operation="dangerous_shell",
                    details={"command": command, "reason": "move_operation"}
                )
            # 检测重定向覆盖（排除无害的 stream redirect）
            # 先排除已知安全的模式：2>&1, 1>&2, &>, 2>/dev/null 等
            safe_redirect_patterns = [r"2>&1", r"1>&2", r"&>", r"2>/dev/null", r"1>/dev/null", r">/dev/null"]
            command_without_safe = command
            for pat in safe_redirect_patterns:
                command_without_safe = re.sub(pat, "", command_without_safe)
            
            # 只检测向实际文件的重定向（> file, >> file, ; > file），排除 >&fd
            if re.search(r"[^&]>[>\s]*\S+", command_without_safe) and not re.search(r"echo\s+.*\s*>", command):
                match = re.search(r"[^&]>[>\s]*(\S+)", command_without_safe)
                if match:
                    redirect_target = match.group(1)
                    if not redirect_target.startswith("/dev/"):
                        _maybe_approve(
                            f"检测到文件覆盖操作，需要确认: {command[:100]}",
                            operation="dangerous_shell",
                            details={"command": command, "reason": "overwrite_redirect"}
                        )
        
        elif action == "file_write":
            path = params.get("path", "")
            target = self._resolve_path(path)
            if target.exists() and target.is_file():
                _maybe_approve(
                    f"文件已存在，覆盖需要确认: {path}",
                    operation="file_overwrite",
                    details={"path": str(target), "size": target.stat().st_size}
                )

    async def _execute_shell(self, params: Dict) -> Dict:
        """执行受限 shell 命令"""
        command = params.get("command", "")
        if not command:
            raise SecurityError("空命令")

        self._check_command_safe(command)
        self._check_dangerous_operation("shell", params)

        # 设置执行目录
        cwd = None
        if self.workspace_mode in ("workspace", "readonly") and self.workspace_path:
            # workspace 模式：在 workspace 目录内执行
            cwd = str(self.workspace_path)
        else:
            # unrestricted / full 模式：在用户 home 目录执行（避免默认在 tent_os 源码目录里）
            cwd = str(Path.home())

        # 使用 asyncio 异步执行，避免阻塞
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise SecurityError(f"命令超时 (>{self.timeout_seconds}s)")

        stdout_str = stdout.decode("utf-8", errors="replace")[:self.max_output_size]
        stderr_str = stderr.decode("utf-8", errors="replace")[:self.max_output_size]

        return {
            "command": command,
            "returncode": proc.returncode,
            "stdout": stdout_str,
            "stderr": stderr_str,
        }

    async def _execute_file_read(self, params: Dict) -> Dict:
        """读取文件（线程池执行，避免阻塞事件循环）"""
        path = params.get("path", "")
        target = self._check_path_allowed(path)

        if not target.exists():
            return {"error": f"文件不存在: {path}"}
        if target.is_dir():
            return {"error": f"路径是目录: {path}"}

        content = await asyncio.to_thread(
            target.read_text, encoding="utf-8", errors="replace"
        )
        # 限制输出大小
        truncated = len(content) > self.max_output_size
        content = content[:self.max_output_size]

        file_size = await asyncio.to_thread(lambda: target.stat().st_size)

        return {
            "path": str(target),
            "size": file_size,
            "content": content,
            "truncated": truncated,
        }

    async def _execute_file_write(self, params: Dict) -> Dict:
        """写入文件（线程池执行，避免阻塞事件循环）"""
        if not self.allow_write:
            raise SecurityError("file_write 未启用 (allow_write=false)")

        path = params.get("path", "")
        content = params.get("content", "")
        self._check_dangerous_operation("file_write", params)
        target = self._check_path_allowed(path)

        # 确保父目录存在（线程池执行）
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        # 写入文件（线程池执行）
        await asyncio.to_thread(target.write_text, content, encoding="utf-8")

        return {
            "path": str(target),
            "bytes_written": len(content.encode("utf-8")),
        }

    async def _execute_directory_list(self, params: Dict) -> Dict:
        """列出目录内容（线程池执行，避免阻塞事件循环）"""
        path = params.get("path", ".")
        target = self._check_path_allowed(path)

        if not target.exists():
            return {"error": f"目录不存在: {path}"}
        if not target.is_dir():
            return {"error": f"路径不是目录: {path}"}

        entries = await asyncio.to_thread(self._sync_list_directory, target)

        return {
            "path": str(target),
            "entries": entries,
        }

    def _sync_list_directory(self, target: Path) -> List[Dict]:
        """同步目录遍历（在线程池中执行）"""
        entries = []
        for item in target.iterdir():
            stat = item.stat()
            entries.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": stat.st_size if item.is_file() else None,
            })
        return entries

    async def _execute_http_request(self, params: Dict) -> Dict:
        """发送 HTTP 请求"""
        method = params.get("method", "GET").upper()
        url = params.get("url", "")
        headers = params.get("headers", {})
        body = params.get("body")
        timeout = params.get("timeout", 30)

        if not url:
            raise SecurityError("URL 不能为空")

        # 简单校验 URL
        parsed = urlparse(url)
        if not parsed.scheme in ("http", "https"):
            raise SecurityError(f"不支持的协议: {parsed.scheme}")

        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=body)
            elif method == "PUT":
                resp = await client.put(url, headers=headers, json=body)
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers)
            else:
                raise SecurityError(f"不支持的 HTTP 方法: {method}")

            content = resp.text[:self.max_output_size]
            return {
                "url": url,
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "content": content,
                "truncated": len(resp.text) > self.max_output_size,
            }
