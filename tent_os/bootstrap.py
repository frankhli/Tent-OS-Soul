"""Tent OS 组件引导器 —— 抽取公共的组件创建逻辑，支持单组件独立启动"""

import asyncio
import os
from pathlib import Path
from typing import Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

from tent_os.message_bus import MessageBus
from tent_os.state.interface import SessionStateStore
from tent_os.state.redis_store import RedisSessionStateStore
from tent_os.state.mock_store import MockSessionStateStore
from tent_os.memory.worker import MemoryWorker
from tent_os.memory.tiered_store import TieredMemoryStore
from tent_os.governance.worker import GovernanceWorker
from tent_os.scheduler.worker import SchedulerWorker
from tent_os.scheduler.router import SchedulerRouter
from tent_os.api.webhook_gateway import WebhookGateway
from tent_os.llm.kimi_coding import KimiCodingLLM
from tent_os.llm.embedding import EmbeddingClient
from tent_os.plugins.manager import PluginManager
from tent_os.tools.executor import ToolExecutor
from tent_os.skills.router import SkillRouter
from tent_os.logging_config import setup_logging, get_logger

# 初始化默认日志（在 setup_logging 被显式调用前使用）
_logger = get_logger()


async def create_local_executor(config: Dict):
    """创建本地执行者（供 Governance 和 Scheduler 共享）
    
    模式：auto（自动检测 Docker）| sandbox（强制沙箱）| local（强制本地）
    """
    from tent_os.scheduler.executors.local import LocalExecutor
    from tent_os.scheduler.executors.sandbox import SandboxExecutor
    
    local_config = config.get("local_executor", {})
    mode = local_config.get("mode", "auto")
    
    # 注入 workspace 配置到 local_executor
    workspace_config = config.get("workspace", {})
    if workspace_config:
        local_config["workspace_mode"] = workspace_config.get("mode", "unrestricted")
        local_config["workspace_path"] = workspace_config.get("path", "")
    
    # 注入超时配置（从顶层 timeouts 读取，兼容旧配置）
    timeouts = config.get("timeouts", {})
    if "timeout_seconds" not in local_config:
        local_config["timeout_seconds"] = timeouts.get("local_executor", 60)
    sandbox_cfg = local_config.get("sandbox", {})
    if "timeout_seconds" not in sandbox_cfg:
        sandbox_cfg["timeout_seconds"] = timeouts.get("sandbox_executor", 60)
        local_config["sandbox"] = sandbox_cfg
    
    executor = None
    executor_id = "local"
    
    if mode == "sandbox":
        executor = SandboxExecutor()
        executor_id = "sandbox"
        await executor.initialize(local_config)
        _logger.info("执行者: Sandbox (强制模式)")
    elif mode == "auto":
        if SandboxExecutor.is_docker_available():
            try:
                executor = SandboxExecutor()
                executor_id = "sandbox"
                await executor.initialize(local_config)
                _logger.info("执行者: Sandbox (auto 检测 Docker 可用)")
            except Exception as e:
                _logger.warning(f"Sandbox 初始化失败，回退到 Local: {e}")
                executor = LocalExecutor()
                await executor.initialize(local_config)
                _logger.info("执行者: Local (Sandbox 回退)")
        else:
            executor = LocalExecutor()
            await executor.initialize(local_config)
            _logger.info("执行者: Local (auto 检测 Docker 不可用)")
    else:
        executor = LocalExecutor()
        await executor.initialize(local_config)
        _logger.info("执行者: Local (本地模式)")
    
    return executor, executor_id


def load_config(config_path: str = "./config/tent_os.yaml") -> Dict:
    if yaml is None:
        raise ImportError("pyyaml is required")
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    # 环境变量覆盖（Docker / K8s / 服务器部署兼容）
    # 格式：TENT_OS_<KEY> 映射到顶层配置项
    env_mappings = {
        "TENT_OS_NATS_URL": "nats_url",
        "TENT_OS_REDIS_URL": "redis_url",
        "TENT_OS_USE_REDIS": "use_redis",
    }
    for env_key, config_key in env_mappings.items():
        val = os.environ.get(env_key)
        if val is not None:
            if config_key == "use_redis":
                config[config_key] = val.lower() in ("true", "1", "yes", "on")
            else:
                config[config_key] = val

    # TENT_OS_DATA_DIR：统一数据目录前缀
    data_dir = os.environ.get("TENT_OS_DATA_DIR")
    if data_dir:
        if "memory" not in config:
            config["memory"] = {}
        if "scheduler" not in config:
            config["scheduler"] = {}
        # 如果路径是相对路径，则前缀化；如果是绝对路径则保持不变
        for key in ["storage_path"]:
            path = config["memory"].get(key, f"./{key}")
            if not os.path.isabs(path):
                config["memory"][key] = os.path.join(data_dir, os.path.basename(path))
        for key in ["db_path", "heartbeat_path"]:
            path = config["scheduler"].get(key, f"./{key}")
            if not os.path.isabs(path):
                config["scheduler"][key] = os.path.join(data_dir, os.path.basename(path))

    # API Key 安全：优先从环境变量读取，避免硬编码在配置文件中
    api_key = os.environ.get("TENT_OS_API_KEY")
    if api_key:
        if "llm" not in config:
            config["llm"] = {}
        config["llm"]["api_key"] = api_key
    
    # 通用环境变量替换：支持 ${VAR} 语法（递归遍历配置树）
    import re
    _ENV_RE = re.compile(r"\$\{([^}]+)\}")
    
    def _substitute_env_vars(obj):
        if isinstance(obj, str):
            def _replacer(m):
                var_name = m.group(1)
                return os.environ.get(var_name, m.group(0))
            return _ENV_RE.sub(_replacer, obj)
        elif isinstance(obj, dict):
            return {k: _substitute_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_substitute_env_vars(v) for v in obj]
        return obj
    
    config = _substitute_env_vars(config)

    return config


def create_message_bus(config: Dict) -> MessageBus:
    return MessageBus(config.get("nats_url", "nats://localhost:4222"))


def create_state_store(config: Dict) -> SessionStateStore:
    if config.get("use_redis"):
        return RedisSessionStateStore(config["redis_url"])
    return MockSessionStateStore()


def create_memory_worker(bus: MessageBus, config: Dict, llm=None) -> MemoryWorker:
    store = TieredMemoryStore(
        config.get("memory", {}).get("storage_path", "./tent_memory"),
        llm=llm
    )
    # 使用 EmbeddingClient：优先 OpenAI，回退到 TF-IDF / HashEmbedding
    llm_config = config.get("llm", {})
    openai_api_key = llm_config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
    # FIX: 检测占位符/无效 key（如 ${OPENAI_API_KEY}），自动回退 TF-IDF
    if openai_api_key and (openai_api_key.startswith("${") or openai_api_key.strip() == ""):
        openai_api_key = None
    embed_client = EmbeddingClient(
        openai_api_key=openai_api_key,
        dim=1536,
    )
    logger = get_logger()
    logger.info(f"Embedding provider: {embed_client.provider_name} (semantic={embed_client.is_semantic})")
    return MemoryWorker(bus, store, embed_client.embed, config=config, llm=llm)


def _create_single_llm(llm_config: Dict, timeout: float = 180.0) -> "LLMProvider":
    """创建单个 LLM Provider（不含 failover 包装）"""
    provider = llm_config.get("provider", "kimi_coding")
    api_key = llm_config.get("api_key", "")
    
    if provider == "kimi_coding" and api_key:
        return KimiCodingLLM(
            api_key=api_key,
            model=llm_config.get("model", "kimi-k2.6"),
            base_url=llm_config.get("base_url", "https://api.kimi.com/coding/v1"),
            user_agent=llm_config.get("user_agent", "claude-code/0.1"),
            temperature=llm_config.get("temperature", 0.3),
            max_concurrent=llm_config.get("max_concurrent", 8),
            timeout=timeout,
        )
    
    elif provider in ("openai_compatible", "openai") and api_key:
        from tent_os.llm.openai_provider import OpenAICompatibleProvider
        return OpenAICompatibleProvider(
            api_key=api_key,
            model=llm_config.get("model", "gpt-4o"),
            base_url=llm_config.get("base_url", "https://api.openai.com/v1"),
            temperature=llm_config.get("temperature", 0.3),
            extra_headers=llm_config.get("extra_headers"),
            timeout=timeout,
        )
    
    elif provider == "anthropic" and api_key:
        from tent_os.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(
            api_key=api_key,
            model=llm_config.get("model", "claude-3-5-sonnet-20241022"),
            base_url=llm_config.get("base_url", "https://api.anthropic.com/v1"),
            temperature=llm_config.get("temperature", 0.3),
            max_tokens=llm_config.get("max_tokens", 4096),
            timeout=timeout,
        )
    
    elif provider == "ollama":
        from tent_os.llm.ollama_provider import OllamaProvider
        return OllamaProvider(
            model=llm_config.get("model", "llama3"),
            base_url=llm_config.get("base_url", "http://localhost:11434"),
            temperature=llm_config.get("temperature", 0.3),
            timeout=timeout,
        )
    
    return None


def create_llm(config: Dict):
    """根据配置创建 LLM Provider（支持故障转移）
    
    支持所有 OpenClaw 兼容的 Provider 模式 + fallback 链：
    - kimi_coding: Kimi Coding API（特殊 User-Agent）
    - openai_compatible: 通用 OpenAI API 兼容
    - anthropic: Claude API
    - ollama: 本地 Ollama 模型
    
    Fallback 配置示例：
        llm:
          provider: kimi_coding
          api_key: sk-xxx
          model: kimi-k2.6
          fallbacks:
            - provider: openai_compatible
              api_key: sk-openai
              model: gpt-4o-mini
              base_url: https://api.openai.com/v1
    """
    llm_config = config.get("llm", {})
    timeout = config.get("timeouts", {}).get("llm_request", 180)
    
    # 主 provider
    primary = _create_single_llm(llm_config, timeout=timeout)
    if primary is None:
        _logger.warning(f"未找到有效的 LLM 配置 (provider={llm_config.get('provider')})，使用 Mock LLM")
        class MockLLM:
            """Mock LLM —— 无配置时的回退，支持 AgentLoop 所需的接口"""
            model = "mock"
            
            async def chat(self, messages, **kwargs):
                return "[Mock LLM] 这是模拟回复。请配置真实 LLM 以获得完整体验。"
            
            async def chat_stream(self, messages, on_chunk, **kwargs):
                text = "[Mock LLM] 这是模拟流式回复。请配置真实 LLM 以获得完整体验。"
                for word in text:
                    on_chunk(word)
            
            async def chat_stream_with_tools(self, messages, tools, on_chunk, on_tool_calls, **kwargs):
                # Mock: 直接回复，不调用工具
                text = "[Mock LLM] 这是模拟回复（工具模式）。请配置真实 LLM 以获得完整体验。"
                for word in text:
                    on_chunk(word)
                on_tool_calls([])
            
            async def complete(self, prompt, **kwargs):
                if "fetch" in prompt or "获取" in prompt:
                    return '{"analysis": "Mock", "steps": [{"step": 1, "action": "fetch", "executor": "mock_http"}, {"step": 2, "action": "process", "executor": "mock_processor"}]}'
                elif "天气" in prompt:
                    return '{"analysis": "Mock", "steps": [{"step": 1, "action": "query", "executor": "mock_api"}]}'
                else:
                    return '{"analysis": "Mock", "steps": [{"step": 1, "action": "chat", "executor": "default"}]}'
        
        return MockLLM()
    
    # 创建 fallback providers
    fallbacks = []
    for fb_config in llm_config.get("fallbacks", []):
        fb_llm = _create_single_llm(fb_config, timeout=timeout)
        if fb_llm:
            fallbacks.append(fb_llm)
    
    if fallbacks:
        from tent_os.llm.failover import FailoverLLM
        return FailoverLLM(primary, fallbacks, config=llm_config)
    
    return primary


def create_vision_llm(config: Dict):
    """创建视觉专用 LLM（支持多模态图片分析）
    
    如果配置了 vision_llm，使用它；否则回退到主 llm
    """
    vision_config = config.get("vision_llm")
    if not vision_config:
        return None
    
    timeout = config.get("timeouts", {}).get("llm_request", 180)
    llm = _create_single_llm(vision_config, timeout=timeout)
    if llm:
        _logger.info(f"Vision LLM: {getattr(llm, 'model_id', getattr(llm, 'model', 'unknown'))}")
    return llm


def create_governance_worker(bus: MessageBus, config: Dict, state_store: SessionStateStore,
                              tool_executor: ToolExecutor = None,
                              skill_manager: SkillRouter = None,
                              embedding_model=None):
    logger = get_logger()
    llm = create_llm(config)
    if hasattr(llm, "model"):
        logger.info(f"LLM: {getattr(llm, 'model_id', llm.model)}")
    else:
        logger.info("LLM: Mock (Fallback)")
    threshold = config.get("governance", {}).get("approval_threshold", 0.5)
    
    # 如果未传入 embedding_model，自动创建（与 memory worker 保持一致）
    if embedding_model is None:
        llm_config = config.get("llm", {})
        openai_api_key = llm_config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        # FIX: 检测占位符/无效 key，自动回退 TF-IDF
        if openai_api_key and (openai_api_key.startswith("${") or openai_api_key.strip() == ""):
            openai_api_key = None
        embed_client = EmbeddingClient(
            openai_api_key=openai_api_key,
            dim=1536,
        )
        embedding_model = embed_client.embed
        logger.info(f"Procedural Memory embedding: {embed_client.provider_name}")
    
    return GovernanceWorker(
        bus, llm, state_store,
        approval_threshold=threshold,
        tool_executor=tool_executor,
        skill_manager=skill_manager,
        config=config,
        embedding_model=embedding_model,
    )


async def create_scheduler_worker(bus: MessageBus, config: Dict,
                                     local_executor=None) -> SchedulerWorker:
    logger = get_logger()
    from tent_os.autonomy.self_healing import SelfHealing
    self_healing = SelfHealing() if config.get("scheduler", {}).get("enable_self_healing", True) else None
    worker = SchedulerWorker(
        bus, SchedulerRouter(),
        config.get("scheduler", {}).get("db_path", "./tent_scheduler.db"),
        config.get("scheduler", {}).get("heartbeat_path", "./HEARTBEAT.md"),
        self_healing=self_healing,
    )
    
    from tent_os.scheduler.router import ExecutorState, ExecutorStatus
    
    # 1. 注册通用 Mock 执行者（用于测试和开发）
    from tent_os.scheduler.executors.mock import MockExecutor
    mock = MockExecutor()
    worker.register_executor("mock", mock)
    worker.router.register(ExecutorState(
        executor_id="mock",
        executor_type="builtin",
        status=ExecutorStatus.IDLE,
        queue_depth=0,
        failure_rate_24h=0.0,
        avg_completion_seconds=2,
        cost_per_task=0.01,
        capabilities=mock.supported_actions(),
        standardization=0.9,
        social=0.1,
        risk_tolerance=0.5,
    ))
    
    # 2. 注册本地/沙箱执行者
    if local_executor is None:
        local_executor, executor_id = await create_local_executor(config)
    else:
        executor_id = getattr(local_executor, 'executor_id', 'local')
    
    worker.register_executor(executor_id, local_executor)
    worker.router.register(ExecutorState(
        executor_id=executor_id,
        executor_type="builtin",
        status=ExecutorStatus.IDLE,
        queue_depth=0,
        failure_rate_24h=0.0,
        avg_completion_seconds=1,
        cost_per_task=0.0,
        capabilities=local_executor.supported_actions(),
        standardization=0.95,
        social=0.0,
        risk_tolerance=0.3 if executor_id == "local" else 0.1,
        is_physical=False,
    ))
    
    # 3. [SOUL] 物理执行者已移除 —— Tent OS 灵魂对讲机不包含物理世界操作
    phys_loaded = 0
    
    # 4. 从插件配置加载额外执行者
    plugins_config = config.get("plugins", [])
    loaded_plugins = 0
    if plugins_config:
        pm = PluginManager()
        pm.load_from_dict(plugins_config)
        for name, plugin in pm.executors.items():
            worker.register_executor(name, plugin)
            worker.router.register(ExecutorState(
                executor_id=name,
                executor_type="plugin",
                status=ExecutorStatus.IDLE,
                queue_depth=0,
                failure_rate_24h=0.0,
                avg_completion_seconds=5,
                cost_per_task=0.1,
                capabilities=plugin.supported_actions()
            ))
            loaded_plugins += 1
    
    logger = get_logger()
    total = 1 + phys_loaded + loaded_plugins
    logger.info(f"已注册 {total} 个执行者 (builtin: mock, plugins: {loaded_plugins})")
    
    # [SOUL] 场景引擎已移除 —— 不再管理IoT设备和物理空间
    pass
    
    return worker


def create_webhook_gateway(bus: MessageBus, config: Dict) -> WebhookGateway:
    return WebhookGateway(bus, config.get("scheduler", {}).get("db_path"))


async def run_worker_forever(worker_name: str, config_path: str = "./config/tent_os.yaml"):
    """启动单个 Worker 并保持运行"""
    config = load_config(config_path)
    bus = create_message_bus(config)
    await bus.connect()
    
    state_store = None
    
    if worker_name == "memory":
        _logger.info("启动记忆进程 (海马体)")
        worker = create_memory_worker(bus, config)
        await worker.start()
    
    elif worker_name == "governance":
        _logger.info("启动治理进程 (前额叶)")
        state_store = create_state_store(config)
        # 创建本地执行者（用于 Tool Calling）
        local_executor, _ = await create_local_executor(config)
        # 尝试创建 BrowserExecutor（Playwright 可选）
        browser_executor = None
        try:
            from tent_os.scheduler.executors.browser import BrowserExecutor
            browser_executor = BrowserExecutor()
            await browser_executor.initialize(config.get("browser_executor", {}))
            _logger.info("BrowserExecutor 已启用")
        except ImportError:
            _logger.info("Playwright 未安装，BrowserExecutor 不可用")
        except Exception as e:
            _logger.warning(f"BrowserExecutor 初始化失败: {e}")
        
        # 创建 TieredMemoryStore 供 ToolExecutor 使用（memory_search / memory_get）
        tiered_memory_store = TieredMemoryStore(
            config.get("memory", {}).get("storage_path", "./tent_memory")
        )
        
        tool_executor = ToolExecutor(
            local_executor=local_executor,
            memory_store=tiered_memory_store,
            browser_executor=browser_executor,
        )
        # 加载 Skills
        skill_manager = SkillRouter(config.get("skills_dir", "./skills"))
        worker = create_governance_worker(
            bus, config, state_store,
            tool_executor=tool_executor,
            skill_manager=skill_manager,
        )
        
        # De-keywordization: 为 SkillRouter 注入 LLM 并扩展 triggers
        if skill_manager and worker.llm:
            skill_manager.set_llm(worker.llm)
            await skill_manager.expand_all_triggers()
        
        await worker.start()
    
    elif worker_name == "scheduler":
        _logger.info("启动调度进程 (神经-肌肉)")
        worker = await create_scheduler_worker(bus, config)
        await worker.start()
    
    elif worker_name == "webhook":
        _logger.info("启动 Webhook Gateway")
        gateway = create_webhook_gateway(bus, config)
        await gateway.start()
    
    else:
        raise ValueError(f"未知 Worker 类型: {worker_name}")
    
    # 保持运行
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await bus.close()


async def init_project():
    """初始化 Tent OS 项目文件"""
    config_dir = Path("./config")
    config_dir.mkdir(exist_ok=True)
    
    config_path = config_dir / "tent_os.yaml"
    if not config_path.exists():
        config_path.write_text("""nats_url: nats://localhost:4222
redis_url: redis://localhost:6379
use_redis: false

memory:
  storage_path: ./tent_memory

scheduler:
  db_path: ./tent_scheduler.db
  heartbeat_path: ./HEARTBEAT.md

llm:
  provider: kimi_coding
  api_key: YOUR_API_KEY_HERE
  model: kimi-k2.6
  base_url: https://api.kimi.com/coding/v1
  user_agent: claude-code/0.1
  temperature: 0.3
""")
        _logger.info(f"创建配置文件: {config_path}")
    else:
        _logger.info(f"配置文件已存在: {config_path}")
    
    heartbeat_path = Path("./HEARTBEAT.md")
    if not heartbeat_path.exists():
        heartbeat_path.write_text("""# Tent OS 后台任务清单

## 定时任务
- [ ] 每日数据备份 (cron: 0 2 * * *)
- [ ] 每周记忆压缩 (cron: 0 3 * * 0)

## 待办事项
- [ ] 审查系统运行状态报告
""")
        _logger.info(f"创建 HEARTBEAT.md: {heartbeat_path}")
    else:
        _logger.info(f"HEARTBEAT.md 已存在: {heartbeat_path}")
