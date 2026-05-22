"""Onboarding 向导 —— 交互式首次配置

运行: tent-os onboard

流程:
1. 欢迎语 + 项目介绍
2. 配置 LLM API Key（必需）
3. 选择基础设施部署方式（Docker / 已有 / 跳过）
4. 创建目录结构
5. 生成配置文件
6. 最终 doctor 检查
7. 启动指引

零 API key 之外的成本：所有基础设置都可以免费完成。
"""

import asyncio
import os
from pathlib import Path

import yaml

from tent_os.doctor import Doctor, print_report

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ████████╗███████╗███╗   ██╗████████╗     ██████╗ ███████╗  ║
║   ╚══██╔══╝██╔════╝████╗  ██║╚══██╔══╝    ██╔═══██╗██╔════╝  ║
║      ██║   █████╗  ██╔██╗ ██║   ██║       ██║   ██║███████╗  ║
║      ██║   ██╔══╝  ██║╚██╗██║   ██║       ██║   ██║╚════██║  ║
║      ██║   ███████╗██║ ╚████║   ██║       ╚██████╔╝███████║  ║
║      ╚═╝   ╚══════╝╚═╝  ╚═══╝   ╚═╝        ╚═════╝ ╚══════╝  ║
║                                                              ║
║     去AI化的智能体内核 —— 人类想干的，AI 都能干              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

WELCOME = """
👋 欢迎安装 Tent OS！

Tent OS 是一个"去AI化"的智能体内核。你不需要理解复杂的
Prompt Engineering，也不需要配置一堆云服务。只需要一个
LLM API Key，其他全部免费：

  • Embedding → 纯 Python 哈希算法（免费）
  • 搜索     → DuckDuckGo（免费）
  • 抓取     → httpx + 正文提取（免费）
  • 语音     → 浏览器 Web Speech API（免费）
  • 存储     → SQLite（免费）
  • 消息总线 → NATS（免费，本地运行）
  • 会话状态 → Redis（免费，本地运行）

接下来我会帮你完成首次配置，大概需要 2 分钟。
"""


def _ask(prompt: str, default: str = "") -> str:
    """同步提问"""
    if default:
        val = input(f"{prompt} [{default}]: ").strip()
        return val if val else default
    return input(f"{prompt}: ").strip()


def _ask_yn(prompt: str, default: bool = True) -> bool:
    """是/否提问"""
    suffix = " [Y/n]" if default else " [y/N]"
    val = input(f"{prompt}{suffix}: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes", "是", "1")


def _ask_choice(prompt: str, choices: list, default: int = 0) -> int:
    """多选一"""
    print(f"\n{prompt}")
    for i, c in enumerate(choices, 1):
        marker = " (默认)" if i - 1 == default else ""
        print(f"  {i}. {c}{marker}")
    val = input("选择: ").strip()
    if not val:
        return default
    try:
        idx = int(val) - 1
        if 0 <= idx < len(choices):
            return idx
    except ValueError:
        pass
    print(f"无效选择，使用默认值: {choices[default]}")
    return default


def _mask_key(key: str) -> str:
    """脱敏显示 API key"""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


async def run_onboarding():
    """交互式首次配置"""
    print(BANNER)
    print(WELCOME)
    
    config = {
        "llm": {},
        "nats_url": "nats://localhost:4222",
        "redis_url": "redis://localhost:6379",
        "scheduler": {
            "db_path": "./tent_scheduler.db"
        }
    }
    
    # ── 步骤 1: LLM API Key ───────────────────────────────
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📌 步骤 1 / 5: 配置 LLM API Key")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("""
Tent OS 只需要一个 API Key 就能工作。目前支持的提供商：

  1. Kimi Coding (推荐) —— 月之暗面开发者平台
     获取地址: https://platform.moonshot.cn
  
  2. OpenAI 兼容 —— 任何兼容 OpenAI API 格式的服务
  
  3. Anthropic Claude —— Claude API
""")
    
    provider_idx = _ask_choice(
        "选择你的 LLM 提供商:",
        ["Kimi Coding (推荐)", "OpenAI 兼容", "Anthropic Claude"],
        default=0
    )
    providers = ["kimi_coding", "openai_compatible", "anthropic"]
    config["llm"]["provider"] = providers[provider_idx]
    
    if provider_idx == 0:
        config["llm"]["base_url"] = "https://api.moonshot.cn"
        config["llm"]["model"] = "kimi-k2.6"
    elif provider_idx == 1:
        config["llm"]["base_url"] = _ask("API Base URL", "https://api.openai.com/v1")
        config["llm"]["model"] = _ask("模型名称", "gpt-4o")
    else:
        config["llm"]["base_url"] = "https://api.anthropic.com"
        config["llm"]["model"] = _ask("模型名称", "claude-3-sonnet-20240229")
    
    # 获取 API Key
    while True:
        api_key = _ask("API Key").strip()
        if api_key:
            break
        print("❌ API Key 不能为空，请重新输入")
    
    config["llm"]["api_key"] = api_key
    print(f"✓ API Key 已设置: {_mask_key(api_key)}")
    
    # ── 步骤 2: 基础设施部署 ──────────────────────────────
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📌 步骤 2 / 5: 部署基础设施 (NATS + Redis)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("""
Tent OS 需要两个本地服务：

  • NATS  —— 消息总线，进程间通信
  • Redis —— 会话状态缓存

你可以：
""")
    
    infra_idx = _ask_choice(
        "选择部署方式:",
        [
            "用 Docker 一键启动 (推荐，已安装 Docker 时)",
            "手动启动（我已经有 NATS/Redis）",
            "跳过，稍后自行配置"
        ],
        default=0
    )
    
    if infra_idx == 0:
        print("\n正在启动 Docker 容器...")
        commands = [
            "docker run -d --name tent-nats --rm -p 4222:4222 nats:2.11-alpine 2>/dev/null || echo 'NATS 已存在或启动失败'",
            "docker run -d --name tent-redis --rm -p 6379:6379 redis:7-alpine 2>/dev/null || echo 'Redis 已存在或启动失败'",
        ]
        for cmd in commands:
            print(f"  $ {cmd}")
            os.system(cmd)
        print("\n等待服务就绪...")
        await asyncio.sleep(3)
        print("✓ Docker 容器已启动")
    elif infra_idx == 1:
        nats_url = _ask("NATS URL", "nats://localhost:4222")
        redis_url = _ask("Redis URL", "redis://localhost:6379")
        config["nats_url"] = nats_url
        config["redis_url"] = redis_url
        print(f"✓ 使用已有服务: {nats_url}, {redis_url}")
    else:
        print("⚠ 已跳过，请稍后手动配置")
    
    # ── 步骤 3: 创建目录结构 ───────────────────────────────
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📌 步骤 3 / 5: 创建项目目录")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    dirs = ["plugins", "skills", "workspace", "config"]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {d}/")
    
    # 写入示例插件
    example_plugin = Path("plugins/example_http_executor.py")
    if not example_plugin.exists():
        example_plugin.write_text('''"""示例插件：HTTP 请求执行器"""

from tent_os.plugins.base import ExecutorPlugin

class ExampleHttpExecutor(ExecutorPlugin):
    name = "example_http"
    version = "1.0.0"
    
    async def initialize(self, config: dict):
        pass
    
    async def execute(self, task: dict) -> dict:
        return {"status": "executed", "plugin": self.name}
    
    def describe(self) -> str:
        return "HTTP 请求执行器（示例插件）"
''')
        print(f"  ✓ {example_plugin}")
    
    # 写入示例 skill
    example_skill = Path("skills/hello_world.py")
    if not example_skill.exists():
        example_skill.write_text('''"""示例 Skill：Hello World"""

SKILL = {
    "name": "hello_world",
    "description": "打招呼示例",
    "version": "1.0.0",
    "triggers": ["你好", "hello"],
    "handler": "run"
}

def run(context: dict) -> str:
    name = context.get("user_name", "朋友")
    return f"你好，{name}！我是 Tent OS，很高兴为你服务。"
''')
        print(f"  ✓ {example_skill}")
    
    # ── 步骤 4: 生成配置文件 ───────────────────────────────
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📌 步骤 4 / 5: 生成配置文件")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    config_path = Path("config/tent_os.yaml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    yaml_text = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
    config_path.write_text(yaml_text)
    print(f"  ✓ {config_path}")
    print(f"\n配置文件内容预览:")
    print(f"  llm.provider: {config['llm']['provider']}")
    print(f"  llm.model: {config['llm']['model']}")
    print(f"  llm.api_key: {_mask_key(config['llm']['api_key'])}")
    print(f"  nats_url: {config['nats_url']}")
    print(f"  redis_url: {config['redis_url']}")
    
    # ── 步骤 5: Doctor 检查 ────────────────────────────────
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📌 步骤 5 / 5: 系统诊断检查")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    await asyncio.sleep(1)
    doctor = Doctor(str(config_path))
    results = await doctor.run_all()
    exit_code = print_report(results)
    
    # ── 完成 ────────────────────────────────────────────────
    if exit_code == 0:
        print("\n" + "=" * 50)
        print("🎉 配置完成！你可以通过以下命令启动 Tent OS:")
        print("")
        print("   tent-os run          # 开发模式，单进程启动")
        print("   tent-os doctor       # 随时运行诊断")
        print("")
        print("   打开浏览器访问: http://localhost:8002")
        print("=" * 50)
    else:
        print("\n⚠ 配置尚未完全就绪，请根据上方错误信息修复后重试。")
        print("   你可以随时运行: tent-os doctor")
    
    return exit_code


if __name__ == "__main__":
    asyncio.run(run_onboarding())
