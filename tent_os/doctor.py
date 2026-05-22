"""Doctor 诊断工具 —— tent-os doctor

自检项目：
1. 配置文件有效性
2. NATS 连通性
3. Redis 连通性
4. LLM API key 有效性
5. SQLite 数据库
6. 磁盘空间
7. 必要目录结构
8. 端口占用

输出：彩色诊断报告，问题标红，正常标绿。
"""

import asyncio
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import List, Dict

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

from tent_os.logging_config import get_logger

logger = get_logger()


class CheckResult:
    """单项检查结果"""
    def __init__(self, name: str, status: str, message: str, detail: str = ""):
        self.name = name
        self.status = status  # ok | warning | error
        self.message = message
        self.detail = detail


class Doctor:
    """系统诊断器"""
    
    def __init__(self, config_path: str = "./config/tent_os.yaml"):
        self.config_path = Path(config_path)
        self.results: List[CheckResult] = []
        self.config = None
    
    async def run_all(self) -> List[CheckResult]:
        """运行所有检查"""
        self.results = []
        
        await self._check_config()
        await self._check_nats()
        await self._check_redis()
        await self._check_llm()
        await self._check_sqlite()
        await self._check_disk()
        await self._check_dirs()
        await self._check_ports()
        
        return self.results
    
    async def _check_config(self):
        """检查配置文件"""
        try:
            if not self.config_path.exists():
                self.results.append(CheckResult(
                    "配置文件", "error",
                    f"配置文件不存在: {self.config_path}",
                    "运行 tent-os init 初始化配置"
                ))
                return
            
            import yaml
            self.config = yaml.safe_load(self.config_path.read_text())
            
            # 检查必填字段
            missing = []
            if not self.config.get("llm", {}).get("api_key"):
                missing.append("llm.api_key")
            if not self.config.get("llm", {}).get("provider"):
                missing.append("llm.provider")
            
            if missing:
                self.results.append(CheckResult(
                    "配置文件", "warning",
                    f"配置缺少字段: {', '.join(missing)}",
                    f"请检查 {self.config_path}"
                ))
            else:
                # 脱敏显示
                key = self.config["llm"]["api_key"]
                masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
                self.results.append(CheckResult(
                    "配置文件", "ok",
                    f"配置有效，LLM Provider: {self.config['llm'].get('provider', 'unknown')}",
                    f"API Key: {masked}"
                ))
        except Exception as e:
            self.results.append(CheckResult("配置文件", "error", str(e)))
    
    async def _check_nats(self):
        """检查 NATS 连通性"""
        try:
            nats_url = self.config.get("nats_url", "nats://localhost:4222") if self.config else "nats://localhost:4222"
            
            # 简单 TCP 连接测试
            import socket
            host, port = nats_url.replace("nats://", "").split(":")
            port = int(port)
            
            sock = socket.create_connection((host, port), timeout=3)
            sock.close()
            
            self.results.append(CheckResult(
                "NATS", "ok",
                f"NATS 可连接 ({nats_url})",
                "消息总线正常工作"
            ))
        except Exception as e:
            self.results.append(CheckResult(
                "NATS", "error",
                f"NATS 连接失败: {e}",
                "请确保 NATS Server 已启动: docker run -d --name tent-nats -p 4222:4222 nats:latest"
            ))
    
    async def _check_redis(self):
        """检查 Redis 连通性"""
        try:
            redis_url = self.config.get("redis_url", "redis://localhost:6379") if self.config else "redis://localhost:6379"
            
            import socket
            host_port = redis_url.replace("redis://", "").split("/")[0]
            host, port = host_port.split(":")
            port = int(port)
            
            sock = socket.create_connection((host, port), timeout=3)
            sock.send(b"PING\r\n")
            resp = sock.recv(1024)
            sock.close()
            
            if b"PONG" in resp:
                self.results.append(CheckResult(
                    "Redis", "ok",
                    f"Redis 可连接 ({redis_url})",
                    "会话状态存储正常工作"
                ))
            else:
                self.results.append(CheckResult(
                    "Redis", "warning",
                    "Redis 连接异常，返回非预期响应",
                    "请检查 Redis 配置"
                ))
        except Exception as e:
            self.results.append(CheckResult(
                "Redis", "error",
                f"Redis 连接失败: {e}",
                "请确保 Redis 已启动: docker run -d --name tent-redis -p 6379:6379 redis:latest"
            ))
    
    async def _check_llm(self):
        """检查 LLM API key 有效性"""
        if not self.config or not HTTPX_AVAILABLE:
            self.results.append(CheckResult(
                "LLM API", "warning",
                "跳过 LLM 检查（未配置或 httpx 未安装）"
            ))
            return
        
        try:
            llm_config = self.config.get("llm", {})
            provider = llm_config.get("provider", "kimi_coding")
            api_key = llm_config.get("api_key", "")
            base_url = llm_config.get("base_url", "")
            
            if not api_key:
                self.results.append(CheckResult("LLM API", "error", "未配置 API Key"))
                return
            
            # 根据 provider 发送测试请求
            if provider == "kimi_coding":
                url = f"{base_url}/models"
                headers = {"Authorization": f"Bearer {api_key}"}
            elif provider in ("openai_compatible", "openai"):
                url = f"{base_url}/models"
                headers = {"Authorization": f"Bearer {api_key}"}
            elif provider == "anthropic":
                url = f"{base_url}/v1/models"
                headers = {"x-api-key": api_key}
            else:
                self.results.append(CheckResult("LLM API", "warning", f"未知 Provider: {provider}，跳过测试"))
                return
            
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    self.results.append(CheckResult(
                        "LLM API", "ok",
                        f"{provider} API Key 有效",
                        f"HTTP {resp.status_code}"
                    ))
                elif resp.status_code == 401:
                    self.results.append(CheckResult(
                        "LLM API", "error",
                        "API Key 无效或已过期 (401)",
                        "请检查 API Key 是否正确"
                    ))
                else:
                    self.results.append(CheckResult(
                        "LLM API", "warning",
                        f"API 返回异常状态: {resp.status_code}",
                        resp.text[:200]
                    ))
        except Exception as e:
            self.results.append(CheckResult("LLM API", "warning", f"测试请求失败: {e}"))
    
    async def _check_sqlite(self):
        """检查 SQLite 数据库"""
        try:
            db_path = self.config.get("scheduler", {}).get("db_path", "./tent_scheduler.db") if self.config else "./tent_scheduler.db"
            
            if not Path(db_path).exists():
                # 创建测试数据库
                conn = sqlite3.connect(db_path)
                conn.execute("SELECT 1")
                conn.close()
                self.results.append(CheckResult(
                    "SQLite", "ok",
                    f"数据库已创建 ({db_path})",
                    "首次运行，数据库已自动初始化"
                ))
            else:
                conn = sqlite3.connect(db_path)
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                conn.close()
                self.results.append(CheckResult(
                    "SQLite", "ok",
                    f"数据库正常，{len(tables)} 张表",
                    f"表: {', '.join(tables[:5])}"
                ))
        except Exception as e:
            self.results.append(CheckResult("SQLite", "error", str(e)))
    
    async def _check_disk(self):
        """检查磁盘空间"""
        try:
            stat = shutil.disk_usage(".")
            free_gb = stat.free / (1024**3)
            total_gb = stat.total / (1024**3)
            used_pct = (stat.used / stat.total) * 100
            
            status = "ok"
            if free_gb < 1:
                status = "error"
            elif free_gb < 5:
                status = "warning"
            
            self.results.append(CheckResult(
                "磁盘空间", status,
                f"剩余 {free_gb:.1f} GB / 总计 {total_gb:.1f} GB ({used_pct:.0f}% 已用)",
                "磁盘空间不足" if status != "ok" else ""
            ))
        except Exception as e:
            self.results.append(CheckResult("磁盘空间", "warning", str(e)))
    
    async def _check_dirs(self):
        """检查必要目录"""
        required_dirs = ["plugins", "skills", "workspace", "config"]
        missing = []
        for d in required_dirs:
            if not Path(d).exists():
                missing.append(d)
        
        if missing:
            self.results.append(CheckResult(
                "目录结构", "warning",
                f"缺少目录: {', '.join(missing)}",
                "运行 tent-os init 可自动创建"
            ))
        else:
            self.results.append(CheckResult(
                "目录结构", "ok",
                "所有必要目录已存在",
                f"{', '.join(required_dirs)}"
            ))
    
    async def _check_ports(self):
        """检查端口占用"""
        try:
            import socket
            ports = [8002, 8003, 4222, 6379]
            occupied = []
            for port in ports:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(("127.0.0.1", port))
                sock.close()
                if result == 0:
                    occupied.append(port)
            
            if occupied:
                self.results.append(CheckResult(
                    "端口占用", "ok",
                    f"以下端口已占用（服务运行中）: {', '.join(map(str, occupied))}",
                    ""
                ))
            else:
                self.results.append(CheckResult(
                    "端口占用", "warning",
                    "Tent OS 服务未运行（端口 8002/8003 空闲）",
                    "运行 tent-os run 启动服务"
                ))
        except Exception as e:
            self.results.append(CheckResult("端口占用", "warning", str(e)))


def print_report(results: List[CheckResult]):
    """打印彩色诊断报告"""
    # ANSI 颜色
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    ok_count = sum(1 for r in results if r.status == "ok")
    warning_count = sum(1 for r in results if r.status == "warning")
    error_count = sum(1 for r in results if r.status == "error")
    
    print()
    print(f"{BOLD}╔══════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║        Tent OS 系统诊断报告              ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════╝{RESET}")
    print()
    
    for r in results:
        if r.status == "ok":
            icon = f"{GREEN}✓{RESET}"
            color = GREEN
        elif r.status == "warning":
            icon = f"{YELLOW}⚠{RESET}"
            color = YELLOW
        else:
            icon = f"{RED}✗{RESET}"
            color = RED
        
        print(f"{icon} {BOLD}{r.name}{RESET}")
        print(f"   {color}{r.message}{RESET}")
        if r.detail:
            print(f"   {color}→ {r.detail}{RESET}")
        print()
    
    print(f"{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    print(f"  {GREEN}✓ 正常: {ok_count}{RESET}  |  {YELLOW}⚠ 警告: {warning_count}{RESET}  |  {RED}✗ 错误: {error_count}{RESET}")
    print()
    
    if error_count > 0:
        print(f"{RED}发现 {error_count} 个错误，请先修复后再启动 Tent OS。{RESET}")
        return 1
    elif warning_count > 0:
        print(f"{YELLOW}发现 {warning_count} 个警告，Tent OS 可以启动但部分功能可能受限。{RESET}")
        return 0
    else:
        print(f"{GREEN}所有检查通过！Tent OS 可以正常运行。{RESET}")
        return 0


async def main():
    """CLI 入口"""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "./config/tent_os.yaml"
    doctor = Doctor(config_path)
    results = await doctor.run_all()
    exit_code = print_report(results)
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
