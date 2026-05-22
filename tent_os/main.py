"""Tent OS 主入口 —— 支持全组件模式（开发测试用）"""

import asyncio

from tent_os.bootstrap import (
    load_config, create_message_bus, create_state_store,
    create_memory_worker, create_governance_worker, create_llm,
    create_scheduler_worker, create_webhook_gateway,
    create_local_executor, ToolExecutor, SkillRouter,
)
from tent_os.memory.tiered_store import TieredMemoryStore
from tent_os.autonomy.dreaming import DreamingEngine
from tent_os.logging_config import setup_logging, get_logger
from tent_os.soul import (
    ThoughtExtractor, VoiceModeler, AppearanceModeler,
    StyleFinetuner, TTSSynthesizer, AuthorizationEngine, SoulEncryption,
    PersonaProfiler,
)


class TentOS:
    """Tent OS 主类 —— 一键启动所有组件（含 Tool Calling + Skills）"""
    
    def __init__(self, config_path: str = "./config/tent_os.yaml"):
        self.config_path = config_path
        self.config = load_config(config_path)
        self.bus = create_message_bus(self.config)
        self.state_store = None
        self.memory_worker = None
        self.governance_worker = None
        self.scheduler = None
        self.webhook_gateway = None
        self.dreaming = None
        self.tool_executor = None
        self.skill_manager = None
        # [SOUL] 灵魂积累层
        self.soul_layer = None
    
    async def start(self):
        # 统一日志配置
        setup_logging(process_name="tent-os", level="INFO")
        logger = get_logger()
        
        await self.bus.connect()
        
        # 状态存储
        self.state_store = create_state_store(self.config)
        
        # 记忆Worker
        self.memory_worker = create_memory_worker(self.bus, self.config)
        asyncio.create_task(self.memory_worker.start())
        
        # 创建本地执行者（用于 Tool Calling）
        local_executor, _ = await create_local_executor(self.config)
        
        # 尝试创建 BrowserExecutor（Playwright 可选）
        browser_executor = None
        try:
            from tent_os.scheduler.executors.browser import BrowserExecutor
            browser_executor = BrowserExecutor()
            await browser_executor.initialize(self.config.get("browser_executor", {}))
            logger.info("BrowserExecutor 已启用")
        except ImportError:
            logger.info("Playwright 未安装，BrowserExecutor 不可用")
        except Exception as e:
            logger.warning(f"BrowserExecutor 初始化失败: {e}")
        
        # 创建 TieredMemoryStore 供 ToolExecutor 使用
        tiered_memory_store = TieredMemoryStore(
            self.config.get("memory", {}).get("storage_path", "./tent_memory")
        )
        
        # 创建 ToolExecutor
        self.tool_executor = ToolExecutor(
            local_executor=local_executor,
            memory_store=tiered_memory_store,
            browser_executor=browser_executor,
        )
        
        # 加载 Skills（使用智能路由）
        self.skill_manager = SkillRouter(self.config.get("skills_dir", "./skills"))
        
        # 创建 LLM（共享给 dreaming engine）
        self._llm = create_llm(self.config)
        
        # 为 SkillRouter 注入 LLM，并扩展 triggers（De-keywordization）
        self.skill_manager.set_llm(self._llm)
        
        # 治理Worker（传入 tool_executor 和 skill_manager）
        self.governance_worker = create_governance_worker(
            self.bus, self.config, self.state_store,
            tool_executor=self.tool_executor,
            skill_manager=self.skill_manager,
        )
        asyncio.create_task(self.governance_worker.start())
        
        # 调度Worker
        self.scheduler = await create_scheduler_worker(self.bus, self.config, local_executor=local_executor)
        
        # 加载外部插件
        from tent_os.plugins.manager import PluginManager
        self.plugin_manager = PluginManager()
        plugin_count = await self.plugin_manager.scan_and_load(self.config.get("plugins"))
        
        # 注册插件执行者到调度器
        for name, executor in self.plugin_manager.executors.items():
            from tent_os.scheduler.router import ExecutorState, ExecutorStatus
            self.scheduler.register_executor(name, executor)
            self.scheduler.router.register(ExecutorState(
                executor_id=name,
                executor_type="plugin",
                status=ExecutorStatus.IDLE,
                queue_depth=0,
                failure_rate_24h=0.0,
                avg_completion_seconds=5,
                cost_per_task=0.0,
                capabilities=executor.supported_actions(),
            ))
            logger.info(f"注册插件执行者: {name}")
        
        asyncio.create_task(self.scheduler.start())
        
        # Webhook Gateway
        self.webhook_gateway = create_webhook_gateway(self.bus, self.config)
        self.webhook_gateway.port = self.config.get("webhook", {}).get("port", 8003)
        asyncio.create_task(self.webhook_gateway.start())
        
        # 梦境引擎（默认禁用，与 Brain v2/PlasticityEngine 冲突）
        if self.config.get("dreaming", {}).get("enabled", False):
            db_path = self.config.get("scheduler", {}).get("db_path", "./tent_scheduler.db")
            memory_db = self.config.get("memory", {}).get("db_path", "./tent_memory/memory.db")
            dreaming_config = self.config.get("dreaming", {})
            self.dreaming = DreamingEngine(
                self.bus, dreaming_config, db_path,
                llm=getattr(self, '_llm', None),
                memory_store_path=memory_db
            )
            asyncio.create_task(self.dreaming.start())
            logger.info("DreamingEngine 已启动")
        else:
            logger.info("DreamingEngine 已禁用（默认），使用 PlasticityEngine (brain_v2) 替代")
        
        # [SOUL] 初始化灵魂积累层
        soul_config = self.config.get("soul", {})
        soul_storage = soul_config.get("storage_path", "./tent_memory/soul")
        self.soul_layer = {
            "thought_extractor": ThoughtExtractor(soul_storage),
            "voice_modeler": VoiceModeler(soul_storage),
            "appearance_modeler": AppearanceModeler(soul_storage),
            "style_finetuner": StyleFinetuner(soul_storage),
            "tts_synthesizer": TTSSynthesizer(soul_storage),
            "authorization": AuthorizationEngine(soul_storage),
            "encryption": SoulEncryption(soul_config.get("password")),
            "persona_profiler": PersonaProfiler(llm=self._llm, storage_path=soul_storage),
        }
        logger.info("[SOUL] 灵魂积累层已初始化（含人格画像引擎）")
        
        # API Server（使用精简版 Soul Server）
        from tent_os.api.soul_server import run_api_server, state as api_state
        port = self.config.get("api", {}).get("port", 8002)
        # 将 dreaming 引擎注入 API server state，使 UI 能读取/控制
        api_state._dreaming = self.dreaming
        # Phase 3: 将 governance_worker 注入 API server state，使记忆整理日志可被读取
        api_state.governance_worker = self.governance_worker
        # [SOUL] 将灵魂层注入 API server state
        api_state.soul_layer = self.soul_layer
        # 将 LLM 注入 API server state，避免 lifespan setup 异常导致 _llm 为 None
        api_state._llm = self._llm
        self._api_thread = run_api_server(config_path=self.config_path, port=port)
        
        logger.info("Tent OS 已就绪")
    
    async def shutdown(self):
        logger = get_logger()
        logger.info("Tent OS 正在关闭...")
        await self.bus.close()


async def main():
    tent = TentOS("./config/tent_os.yaml")
    await tent.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await tent.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
