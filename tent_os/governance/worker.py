import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from tent_os.state.interface import SessionStateStore
from tent_os.governance.plan_executor import PlanExecuteExecutor
from tent_os.governance.prompt_cache import SegmentedPromptCache
from tent_os.governance.evaluator import Evaluator, EvaluationResult
from tent_os.governance.evaluation_store import EvaluationStore, EvaluationRecord
from tent_os.governance.system_prompt import build_system_prompt
from tent_os.governance.session_scheduler import SessionScheduler
from tent_os.memory.procedural import ProceduralMemoryStore, ProceduralMemoryInjector, ExperienceExtractor
from tent_os.memory.user_profile import UserProfileStore
from tent_os.tools.definitions import get_tool_schemas

# Tent OS 2.0 大脑模块（可选，向后兼容）
try:
    from tent_os.memory.graph import CognitiveGraph
    from tent_os.memory.working_memory import WorkingMemoryManager
    from tent_os.memory.reasoning_chain import ReasoningChain
    from tent_os.persona.soul_evolution import SoulEvolution
    from tent_os.persona.persona_compressor import PersonaCompressor
    from tent_os.persona.user_model import UserModelBuilder
    from tent_os.persona.multi_persona import MultiPersonaManager
    _BRAIN_V2_AVAILABLE = True
except ImportError as e:
    logger = logging.getLogger("tent_os.governance")
    logger.debug(f"Tent OS 2.0 大脑模块未完全加载: {e}")
    _BRAIN_V2_AVAILABLE = False

logger = logging.getLogger("tent_os.governance")

# 触发工具调用的关键词（中英文）—— 放宽到覆盖几乎所有任务场景
_TOOL_KEYWORDS = [
    # 直接操作
    "执行", "运行", "命令", "shell", "cmd",
    "读取", "查看", "打开", "文件", "file", "cat", "read",
    "写入", "修改", "保存", "write", "edit",
    "目录", "文件夹", "list", "ls", "dir",
    "搜索", "查找", "search", "find", "grep",
    "curl", "wget", "http", "请求", "api",
    "git", "npm", "pip", "python", "node", "go", "rust",
    # 开发/创作任务
    "写", "创建", "生成", "做", "构建", "build",
    "开发", "代码", "脚本", "程序", "项目",
    "PPT", "ppt", "邮件", "email", "报告", "文档",
    "网页", "网站", "app", "应用", "小程序",
    # 数据处理
    "爬", "抓取", "数据", "分析", "处理", "转换", "清洗",
    "统计", "计算", "排序", "过滤", "合并", "拆分",
    # 运维/部署
    "安装", "配置", "部署", "发布", "启动", "停止", "重启",
    "测试", "调试", "debug", "修复", "fix", "重构",
    # 浏览器
    "浏览", "打开网页", "访问", "点击", "填写", "截图",
    # 记忆
    "记得", "记忆", "历史", "之前", "上次", "回忆",
]


# 运行时配置覆盖（热更新同步）
_live_config_overrides: Dict[str, Any] = {}

class GovernanceWorker:
    """无状态治理进程——对话驱动 + 任务调度双模式 + Tool Calling
    
    核心设计（保持架构不变）：
    1. 所有状态外存到 Redis，进程无状态
    2. 流式输出通过 NATS 消息广播，不阻塞
    3. 简单问答直接流式回复，复杂任务走 Plan-Execute
    4. 需要工具操作时走 ReAct Tool Loop
    5. 会话持续存在（多轮对话），不自动删除
    """
    
    def __init__(self, bus, llm, state_store: SessionStateStore, approval_threshold: float = 0.5,
                 enable_evaluator: bool = True, enable_procedural_memory: bool = True,
                 tool_executor=None, skill_manager=None, config: Dict = None,
                 embedding_model=None, policy_engine=None):
        self.bus = bus
        self.llm = llm
        self.state_store = state_store
        self.executor = PlanExecuteExecutor(llm, approval_threshold)
        self.prompt_cache = SegmentedPromptCache()
        self.evaluator = Evaluator(llm) if enable_evaluator else None
        # _retry_counts 已外迁到 state_store（Redis），治理进程完全无状态化
        self.tool_executor = tool_executor
        self.skill_manager = skill_manager
        self.config = config or {}
        # Phase 1: 元认知仪表盘 —— 评估结果存储
        memory_path = self.config.get("memory", {}).get("storage_path", "./tent_memory")
        self.evaluation_store = EvaluationStore(storage_path=memory_path)
        self.embedding_model = embedding_model
        self.policy_engine = policy_engine
        
        # 超时配置（从 config 读取，支持长任务）
        timeout_cfg = self.config.get("timeouts", {})
        self._tool_loop_timeout = timeout_cfg.get("tool_loop", 3600)
        self._speculative_timeout = timeout_cfg.get("speculative", 10)
        self._security_timeout = timeout_cfg.get("security_assessment", 5)
        self._scheduler_step_timeout = timeout_cfg.get("scheduler_step", 300)
        self._llm_warmup_timeout = timeout_cfg.get("llm_request", 30)
        
        # 用户画像存储
        memory_path = config.get("memory", {}).get("storage_path", "./tent_memory") if config else "./tent_memory"
        self.user_profile_store = UserProfileStore(f"{memory_path}/memory.db")
        
        # 注册自定义工具
        self._register_custom_tools()
        
        # FIX: 设置 ToolExecutor 的调度进程代理（物理执行者支持）
        if self.tool_executor:
            self.tool_executor.set_scheduler_proxy(self._scheduler_dispatch_proxy)
        
        # 程序记忆系统
        self.procedural_store = ProceduralMemoryStore(embedding_model=embedding_model) if enable_procedural_memory else None
        self.procedural_injector = ProceduralMemoryInjector(self.procedural_store) if enable_procedural_memory else None
        self.experience_extractor = ExperienceExtractor(llm) if enable_procedural_memory else None
        
        # Tent OS 2.0 大脑核心（可选初始化）
        self._init_brain_v2(config)
        
        # 自我状态监控计数器（真正计数，不是谎言）
        # FIX v5: 按session存储计数器，避免A session的错误影响B session
        from collections import defaultdict
        self._recent_message_count: Dict[str, int] = defaultdict(int)
        self._recent_error_count: Dict[str, int] = defaultdict(int)
        self._last_interaction_ts = time.time()
        self._system_mood = "calm"
        self._background_tick = 0
        # FIX: 认知预算弹性系数——背景思考真正影响行为
        self._cognitive_budget_scale = 1.0  # 1.0=正常, 0.7=stressed时降低
        # FIX v4: 用户模型缓存——了解一个人是渐进的，不是每次见面都重新分析
        self._user_model_cache: Dict[str, tuple] = {}  # user_id -> (msg_count, user_model)
        # compaction 去重标记
        self._compacting_sessions: set = set()
        
        # === Claude Code 融合模块（Phase 1-3）===
        self._init_claude_code_modules(config)
        
        # === Session Scheduler：操作系统式会话调度器 ===
        # FIX: 解决 NATS push consumer 单线程串行调度导致的全局阻塞问题
        # 每个 session 一个顺序队列，多个 session 并行执行
        scheduler_config = config.get("governance", {}).get("scheduler", {}) if config else {}
        self._scheduler = SessionScheduler(
            max_global_concurrent=scheduler_config.get("max_concurrent", 8),
            worker_name="gov-session",
        )
        logger.info(f"[GOV] Session Scheduler 初始化完成: max_concurrent={scheduler_config.get('max_concurrent', 8)}")
        
        # FIX Phase 1.4: 背景思考事件驱动化
        self._bg_think_event = asyncio.Event()
        
        # FIX Phase 2.5: Promise Tracker —— 防止 AI 假忙碌
        from tent_os.governance.promise_tracker import PromiseTracker
        self._promise_tracker = PromiseTracker()
        
        # FIX Phase 3: Adaptive Thresholds —— 经验驱动的阈值自适应
        from tent_os.governance.adaptive_thresholds import AdaptiveThresholdManager
        self._adaptive = AdaptiveThresholdManager(state_store=self.state_store)
        
        # Phase 4: 主动行为引擎
        try:
            from tent_os.governance.proactive_engine import ProactiveCareEngine
            self.proactive_engine = ProactiveCareEngine(
                bus=self.bus, llm=self.llm, state_store=self.state_store, config=config
            )
        except Exception as e:
            logger.warning(f"[GOV] 主动行为引擎初始化失败: {e}")
            self.proactive_engine = None
        
        # Phase 5: 内心独白生成器
        try:
            from tent_os.governance.inner_monologue import InnerMonologueGenerator
            self.inner_monologue = InnerMonologueGenerator(llm=self.llm, config=config)
        except Exception as e:
            logger.warning(f"[GOV] 内心独白生成器初始化失败: {e}")
            self.inner_monologue = None
        
        # Phase 5: 解释生成器
        try:
            from tent_os.governance.explanation import ExplanationGenerator
            self.explanation_generator = ExplanationGenerator(llm=self.llm, config=config)
        except Exception as e:
            logger.warning(f"[GOV] 解释生成器初始化失败: {e}")
            self.explanation_generator = None
    
    def _parse_tool_calls_from_text(self, text: str) -> List[Dict]:
        """从 LLM 回复文本中解析 tool_calls（应对 LLM 在文本中输出 tool_call 而不是通过 function calling 的情况）"""
        if not text:
            return []
        import re
        tool_calls = []
        # FIX: 放宽匹配——允许没有 closing ```，匹配到文本末尾
        patterns = [
            r'```tool_call\s*\n?(.*?)(?:\n?```|$)',
            r'```tool\s*\n?(.*?)(?:\n?```|$)',
            r'```json\s*\n?(.*?)(?:\n?```|$)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                match = match.strip()
                if not match:
                    continue
                try:
                    data = json.loads(match)
                except json.JSONDecodeError:
                    continue
                tool_name = None
                arguments = None
                if isinstance(data, dict):
                    if "name" in data:
                        tool_name = data["name"]
                        arguments = data.get("arguments", "{}")
                    elif "tool" in data:
                        tool_name = data["tool"]
                        arguments = json.dumps(data.get("params", {}), ensure_ascii=False)
                    elif "function" in data and isinstance(data["function"], dict):
                        tool_name = data["function"].get("name")
                        arguments = data["function"].get("arguments", "{}")
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "name" in item:
                            _args = item.get("arguments", "{}")
                            if isinstance(_args, dict):
                                _args = json.dumps(_args, ensure_ascii=False)
                            tool_calls.append({
                                "id": f"parsed_{len(tool_calls)}",
                                "type": "function",
                                "function": {"name": item["name"], "arguments": _args}
                            })
                    continue
                if tool_name and arguments is not None:
                    if isinstance(arguments, dict):
                        arguments = json.dumps(arguments, ensure_ascii=False)
                    tool_calls.append({
                        "id": f"parsed_{len(tool_calls)}",
                        "type": "function",
                        "function": {"name": tool_name, "arguments": arguments}
                    })
        return tool_calls
    
    def _init_brain_v2(self, config: Dict):
        """初始化 Tent OS 2.0 大脑核心模块
        
        模式：
        - minimal: 全部关闭（兼容旧行为）
        - standard: 启用 Soul + Persona + WorkingMemory（推荐默认）
        - full: 启用全部模块（含 CognitiveGraph 复杂查询 + ReasoningChain）
        """
        brain_config = config.get("brain_v2", {}) if config else {}
        self.brain_v2_enabled = brain_config.get("enabled", True)  # FIX: 默认启用
        self.brain_mode = brain_config.get("mode", "standard") if self.brain_v2_enabled else "minimal"
        
        if not self.brain_v2_enabled or not _BRAIN_V2_AVAILABLE or self.brain_mode == "minimal":
            self.cognitive_graph = None
            self.working_memory = None
            self.persona_compressor = None
            self.soul = None
            self.multi_persona = None
            self.reasoning_chain = None
            logger.info(f"Brain v2 模式: {self.brain_mode}（关闭）")
            return
        
        memory_path = config.get("memory", {}).get("storage_path", "./tent_memory")
        
        # === 标准模式 & 完整模式 共用模块 ===
        
        # 1. 认知图谱（standard 模式下轻量使用，full 模式下深度查询）
        try:
            self.cognitive_graph = CognitiveGraph(f"{memory_path}/graph.db")
        except Exception as e:
            logger.warning(f"CognitiveGraph 初始化失败: {e}，降级运行")
            self.cognitive_graph = None
        
        # 2. 人格系统（核心：让 Tent OS 有"性格"而不是千篇一律）
        try:
            self.soul = SoulEvolution(storage_path=f"{memory_path}/soul.json", llm=self.llm)
            self.persona_compressor = PersonaCompressor(self.soul)
            self.multi_persona = MultiPersonaManager(
                default_mode=brain_config.get("default_persona", "work")
            )
            logger.info(f"SOUL 人格系统已加载: {self.soul.dimensions}")
        except Exception as e:
            logger.warning(f"人格系统初始化失败: {e}")
            self.soul = None
            self.persona_compressor = None
            self.multi_persona = None
        
        # 3. 工作记忆（核心：7±2 chunk 的实时认知）
        try:
            if self.cognitive_graph:
                from tent_os.memory.predictive_preloader import PredictivePreloader
                preloader = PredictivePreloader(self.cognitive_graph)
                self.working_memory = WorkingMemoryManager(self.cognitive_graph, preloader)
                logger.info("WorkingMemory 已激活（7±2 chunk 容量）")
            else:
                self.working_memory = None
        except Exception as e:
            logger.warning(f"工作记忆初始化失败: {e}")
            self.working_memory = None
        
        # === 仅完整模式启用的模块 ===
        
        if self.brain_mode == "full":
            try:
                self.reasoning_chain = ReasoningChain(self.cognitive_graph)
                logger.info("ReasoningChain 已激活")
            except Exception as e:
                logger.warning(f"推理链初始化失败: {e}")
                self.reasoning_chain = None
        else:
            self.reasoning_chain = None
        
        logger.info(f"Tent OS 2.0 大脑核心已初始化: mode={self.brain_mode}")
    
    def _init_claude_code_modules(self, config: Dict):
        """初始化 Claude Code 融合模块（Phase 1-3）
        
        所有模块都是可选的，初始化失败不影响现有功能。
        """
        # Phase 1.1: JSONL Logger
        try:
            from tent_os.logging.jsonl_logger import get_jsonl_logger
            self.jsonl_logger = get_jsonl_logger()
        except Exception as e:
            logger.warning(f"JSONL Logger 初始化失败: {e}")
            self.jsonl_logger = None
        
        # Phase 1.2: File Memory
        try:
            from tent_os.memory.file_memory import FileMemoryStore
            self.file_memory = FileMemoryStore(
                relevance_llm=self.llm if hasattr(self.llm, 'chat') else None
            )
        except Exception as e:
            logger.warning(f"File Memory 初始化失败: {e}")
            self.file_memory = None
        
        # Phase 1.3: Context Compression Pipeline
        try:
            from tent_os.governance.compression import ContextCompressionPipeline
            self.compression_pipeline = ContextCompressionPipeline(
                llm=self.llm if hasattr(self.llm, 'chat') else None,
                config=config.get("compression", {}),
            )
        except Exception as e:
            logger.warning(f"Compression Pipeline 初始化失败: {e}")
            self.compression_pipeline = None
        
        # Phase 1.4: Hook Engine
        try:
            from tent_os.hooks.engine import HookEngine
            self.hook_engine = HookEngine()
        except Exception as e:
            logger.warning(f"Hook Engine 初始化失败: {e}")
            self.hook_engine = None
        
        # Phase 1.5: Tool Pool Assembler
        try:
            from tent_os.tools.assembler import ToolPoolAssembler
            self.tool_pool_assembler = ToolPoolAssembler(
                config=config,
                policy_engine=self.policy_engine,
                hook_engine=getattr(self, 'hook_engine', None),
                tool_executor=self.tool_executor,
            )
        except Exception as e:
            logger.warning(f"Tool Pool Assembler 初始化失败: {e}")
            self.tool_pool_assembler = None
        
        # Phase 1.6: OPA Policy Engine（替换/增强旧 PolicyEngine）
        try:
            from tent_os.governance.opa_engine import OPAPolicyEngine
            self.opa_engine = OPAPolicyEngine(
                policy_path=config.get("opa_policy_path", "./config/opa_policies.yaml")
            )
            logger.info("OPA Policy Engine 已初始化")
        except Exception as e:
            logger.warning(f"OPA Policy Engine 初始化失败: {e}")
            self.opa_engine = None
        
        # Phase 2.1: Permission Mode Manager
        try:
            from tent_os.governance.permission_mode import PermissionModeManager
            self.mode_manager = PermissionModeManager(
                config=config,
                state_store=self.state_store,
                jsonl_logger=getattr(self, 'jsonl_logger', None),
            )
        except Exception as e:
            logger.warning(f"Permission Mode Manager 初始化失败: {e}")
            self.mode_manager = None
        
        # Phase 2.2: Auto-Mode Classifier
        try:
            from tent_os.governance.auto_classifier import AutoModeClassifier
            self.auto_classifier = AutoModeClassifier(
                llm=self.llm if hasattr(self.llm, 'chat') else None
            )
        except Exception as e:
            logger.warning(f"Auto-Mode Classifier 初始化失败: {e}")
            self.auto_classifier = None
        
        # Phase 2.3: Layered Security
        try:
            from tent_os.governance.safety.layered_security import LayeredSecurity
            self.layered_security = LayeredSecurity(
                config=config,
                policy_engine=self.policy_engine,
                opa_engine=getattr(self, 'opa_engine', None),
                mode_manager=getattr(self, 'mode_manager', None),
                auto_classifier=getattr(self, 'auto_classifier', None),
                hook_engine=getattr(self, 'hook_engine', None),
                jsonl_logger=getattr(self, 'jsonl_logger', None),
            )
        except Exception as e:
            logger.warning(f"Layered Security 初始化失败: {e}")
            self.layered_security = None
        
        # Phase 2.4: Output Slot Manager
        try:
            from tent_os.llm.slot_manager import OutputSlotManager
            self.slot_manager = OutputSlotManager(
                config=config,
                jsonl_logger=getattr(self, 'jsonl_logger', None),
            )
        except Exception as e:
            logger.warning(f"Slot Manager 初始化失败: {e}")
            self.slot_manager = None
        
        # Phase 3.1: Subagent Spawner
        try:
            from tent_os.governance.subagent import SubagentSpawner
            self.subagent_spawner = SubagentSpawner(
                bus=self.bus,
                llm=self.llm,
                state_store=self.state_store,
                tool_executor=self.tool_executor,
                config=config,
                jsonl_logger=getattr(self, 'jsonl_logger', None),
            )
        except Exception as e:
            logger.warning(f"Subagent Spawner 初始化失败: {e}")
            self.subagent_spawner = None
        
        # Phase 3.2: Prompt Cache v2
        try:
            from tent_os.governance.prompt_cache_v2 import SegmentedPromptCacheV2
            redis_client = getattr(self.state_store, 'redis', None)
            self.prompt_cache_v2 = SegmentedPromptCacheV2(redis_client=redis_client)
        except Exception as e:
            logger.warning(f"Prompt Cache v2 初始化失败: {e}")
            self.prompt_cache_v2 = None
        
        # Phase 3.3: Speculative Executor
        try:
            from tent_os.governance.speculative import SpeculativeExecutor
            self.speculative_executor = SpeculativeExecutor(
                tool_executor=self.tool_executor,
                jsonl_logger=getattr(self, 'jsonl_logger', None),
            )
        except Exception as e:
            logger.warning(f"Speculative Executor 初始化失败: {e}")
            self.speculative_executor = None
        
        # Phase 3.4: Telemetry
        try:
            from tent_os.telemetry import TelemetryCollector
            self.telemetry = TelemetryCollector(
                jsonl_logger=getattr(self, 'jsonl_logger', None),
            )
        except Exception as e:
            logger.warning(f"Telemetry 初始化失败: {e}")
            self.telemetry = None
        
        # === Phase 4: Loop Detection + Self Validation ===
        # FIX: Task 7 —— 循环检测 + 自验证
        try:
            from tent_os.governance.loop_detector import LoopDetector
            self.loop_detector = LoopDetector()
        except Exception as e:
            logger.warning(f"Loop Detector 初始化失败: {e}")
            self.loop_detector = None
        
        try:
            from tent_os.governance.self_validator import SelfValidator
            self.self_validator = SelfValidator(
                llm=self.llm if hasattr(self.llm, 'chat') else None,
                enable_llm=True,
            )
        except Exception as e:
            logger.warning(f"Self Validator 初始化失败: {e}")
            self.self_validator = None
        
        logger.info("Claude Code 融合模块初始化完成")
    
    def _register_custom_tools(self):
        """注册 Skill 自定义工具"""
        if not self.tool_executor:
            return
        
        # render_ppt: 将 JSON 格式的 Presentation 渲染为 HTML 幻灯片
        async def _render_ppt(arguments: Dict) -> Dict:
            """渲染 PPT 为 HTML 文件"""
            import json as json_mod
            from pathlib import Path
            
            presentation_json = arguments.get("presentation_json", "")
            output_path = arguments.get("output_path", "")
            
            if not presentation_json:
                return {"status": "error", "error": "缺少 presentation_json 参数"}
            if not output_path:
                # 默认保存到用户桌面
                output_path = str(Path.home() / "Desktop" / "presentation.html")
            
            try:
                # 动态导入，避免初始化时失败导致整个系统崩溃
                from tent_os.skills.presentation.schema import Presentation
                from tent_os.skills.presentation.renderer import render_presentation
                
                data = json_mod.loads(presentation_json)
                presentation = Presentation.from_dict(data)
                saved_path = render_presentation(presentation, output_path)
                return {
                    "status": "completed",
                    "result": f"PPT 已生成: {saved_path}",
                    "file_path": saved_path,
                    "slides_count": presentation.total_slides(),
                    "theme": presentation.theme,
                }
            except ImportError as e:
                logger.error(f"[render_ppt] 导入失败: {e}")
                return {"status": "error", "error": f"PPT 渲染引擎未正确安装: {e}"}
            except Exception as e:
                logger.error(f"[render_ppt] 渲染失败: {e}")
                return {"status": "error", "error": str(e)}
        
        try:
            self.tool_executor.register_tool(
                name="render_ppt",
                handler=_render_ppt,
                schema={
                    "type": "function",
                    "function": {
                        "name": "render_ppt",
                        "description": "【生成PPT/幻灯片/演示文稿】将 JSON 格式的 Presentation 数据结构渲染为精美的 HTML 幻灯片。当你需要制作PPT、演示文稿、幻灯片时，直接调用此工具。⚠️ 不要尝试用 shell 或 file_write 手写 HTML/JS 代码来生成幻灯片，直接调用本工具即可。渲染引擎已内置，直接调用，无需预先检查。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "presentation_json": {
                                    "type": "string",
                                    "description": "Presentation 的 JSON 字符串（符合 schema.py 定义的数据结构）"
                                },
                                "output_path": {
                                    "type": "string",
                                    "description": "输出文件路径，默认保存到桌面。例如: /Users/frank/Desktop/my_ppt.html"
                                }
                            },
                            "required": ["presentation_json"]
                        }
                    }
                }
            )
            logger.info("[GOV] 自定义工具注册完成: render_ppt")
        except Exception as e:
            logger.error(f"[GOV] 注册 render_ppt 工具失败: {e}")
        
        # FIX: render_document —— 将 JSON 格式的 Document 渲染为 HTML 文档
        async def _render_document(arguments: Dict) -> Dict:
            import json as json_mod
            from pathlib import Path
            
            doc_json = arguments.get("document_json", "")
            output_path = arguments.get("output_path", "")
            
            if not doc_json:
                return {"status": "error", "error": "缺少 document_json 参数"}
            if not output_path:
                output_path = str(Path.home() / "Desktop" / "document.html")
            
            try:
                from tent_os.skills.document.schema import Document
                from tent_os.skills.document.renderer import render_document
                
                data = json_mod.loads(doc_json)
                doc = Document.from_dict(data)
                saved_path = render_document(doc, output_path)
                return {
                    "status": "completed",
                    "result": f"文档已生成: {saved_path}",
                    "file_path": saved_path,
                    "theme": doc.theme,
                }
            except Exception as e:
                logger.error(f"[render_document] 渲染失败: {e}")
                return {"status": "error", "error": str(e)}
        
        try:
            self.tool_executor.register_tool(
                name="render_document",
                handler=_render_document,
                schema={
                    "type": "function",
                    "function": {
                        "name": "render_document",
                        "description": "【生成文档/报告/说明书】将 JSON 格式的 Document 数据结构渲染为精美的 HTML 文档（可打印为 PDF）。当你需要生成报告、说明书、提案等文档时，直接调用此工具。⚠️ 不要尝试用 shell 或 file_write 手写 HTML 来生成文档，直接调用本工具即可。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "document_json": {
                                    "type": "string",
                                    "description": "Document 的 JSON 字符串（符合 schema.py 定义的数据结构）"
                                },
                                "output_path": {
                                    "type": "string",
                                    "description": "输出文件路径，例如: /Users/frank/Desktop/report.html"
                                }
                            },
                            "required": ["document_json"]
                        }
                    }
                }
            )
            logger.info("[GOV] 自定义工具注册完成: render_document")
        except Exception as e:
            logger.error(f"[GOV] 注册 render_document 工具失败: {e}")
        
        # FIX: render_contract —— 将 JSON 格式的 Contract 渲染为 HTML 合同
        async def _render_contract(arguments: Dict) -> Dict:
            import json as json_mod
            from pathlib import Path
            
            contract_json = arguments.get("contract_json", "")
            output_path = arguments.get("output_path", "")
            
            if not contract_json:
                return {"status": "error", "error": "缺少 contract_json 参数"}
            if not output_path:
                output_path = str(Path.home() / "Desktop" / "contract.html")
            
            try:
                from tent_os.skills.document.schema import Contract
                from tent_os.skills.document.renderer import render_contract
                
                data = json_mod.loads(contract_json)
                contract = Contract.from_dict(data)
                saved_path = render_contract(contract, output_path)
                return {
                    "status": "completed",
                    "result": f"合同已生成: {saved_path}",
                    "file_path": saved_path,
                    "theme": contract.theme,
                }
            except Exception as e:
                logger.error(f"[render_contract] 渲染失败: {e}")
                return {"status": "error", "error": str(e)}
        
        try:
            self.tool_executor.register_tool(
                name="render_contract",
                handler=_render_contract,
                schema={
                    "type": "function",
                    "function": {
                        "name": "render_contract",
                        "description": "【生成合同/协议/法律文书】将 JSON 格式的 Contract 数据结构渲染为专业的 HTML 合同（可打印为 PDF）。包含条款编号、签字区、印章占位。当你需要生成合同、协议、法律文书时，直接调用此工具。⚠️ 不要尝试用 shell 或 file_write 手写合同文本，直接调用本工具即可。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "contract_json": {
                                    "type": "string",
                                    "description": "Contract 的 JSON 字符串（符合 schema.py 定义的数据结构）"
                                },
                                "output_path": {
                                    "type": "string",
                                    "description": "输出文件路径，例如: /Users/frank/Desktop/contract.html"
                                }
                            },
                            "required": ["contract_json"]
                        }
                    }
                }
            )
            logger.info("[GOV] 自定义工具注册完成: render_contract")
        except Exception as e:
            logger.error(f"[GOV] 注册 render_contract 工具失败: {e}")
        
        # FIX: render_excel —— 将 JSON 格式的 ExcelWorkbook 渲染为 .xlsx 文件
        async def _render_excel(arguments: Dict) -> Dict:
            import json as json_mod
            from pathlib import Path
            
            workbook_json = arguments.get("workbook_json", "")
            output_path = arguments.get("output_path", "")
            
            if not workbook_json:
                return {"status": "error", "error": "缺少 workbook_json 参数"}
            if not output_path:
                output_path = str(Path.home() / "Desktop" / "workbook.xlsx")
            if not output_path.endswith(".xlsx"):
                output_path += ".xlsx"
            
            try:
                from tent_os.skills.spreadsheet.schema import ExcelWorkbook
                from tent_os.skills.spreadsheet.renderer import render_excel
                
                data = json_mod.loads(workbook_json)
                workbook = ExcelWorkbook.from_dict(data)
                saved_path = render_excel(workbook, output_path)
                return {
                    "status": "completed",
                    "result": f"Excel 已生成: {saved_path}",
                    "file_path": saved_path,
                    "sheets_count": len(workbook.sheets),
                    "theme": workbook.theme,
                }
            except ImportError as e:
                logger.error(f"[render_excel] 导入失败: {e}")
                return {"status": "error", "error": f"xlsxwriter 未安装，请运行: pip install xlsxwriter"}
            except Exception as e:
                logger.error(f"[render_excel] 渲染失败: {e}")
                return {"status": "error", "error": str(e)}
        
        try:
            self.tool_executor.register_tool(
                name="render_excel",
                handler=_render_excel,
                schema={
                    "type": "function",
                    "function": {
                        "name": "render_excel",
                        "description": "【生成Excel/报表/数据表】将 JSON 格式的 ExcelWorkbook 数据结构渲染为专业的 .xlsx 文件。支持多 sheet、公式、图表、条件格式。当你需要生成报表、数据分析表、财务表格时，直接调用此工具。⚠️ 不要尝试用 shell 或 file_write 手写 CSV/表格，直接调用本工具即可。xlsxwriter 已内置，直接调用，无需预先检查。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "workbook_json": {
                                    "type": "string",
                                    "description": "ExcelWorkbook 的 JSON 字符串（符合 schema.py 定义的数据结构）"
                                },
                                "output_path": {
                                    "type": "string",
                                    "description": "输出文件路径，例如: /Users/frank/Desktop/report.xlsx"
                                }
                            },
                            "required": ["workbook_json"]
                        }
                    }
                }
            )
            logger.info("[GOV] 自定义工具注册完成: render_excel")
        except Exception as e:
            logger.error(f"[GOV] 注册 render_excel 工具失败: {e}")
        
        # FIX: render_word —— 将 JSON 格式的 WordDocument 渲染为 .docx 文件
        async def _render_word(arguments: Dict) -> Dict:
            import json as json_mod
            from pathlib import Path
            
            doc_json = arguments.get("document_json", "")
            output_path = arguments.get("output_path", "")
            
            if not doc_json:
                return {"status": "error", "error": "缺少 document_json 参数"}
            if not output_path:
                output_path = str(Path.home() / "Desktop" / "document.docx")
            if not output_path.endswith(".docx"):
                output_path += ".docx"
            
            try:
                from tent_os.skills.word.schema import WordDocument
                from tent_os.skills.word.renderer import render_word
                
                data = json_mod.loads(doc_json)
                doc = WordDocument.from_dict(data)
                saved_path = render_word(doc, output_path)
                return {
                    "status": "completed",
                    "result": f"Word 文档已生成: {saved_path}",
                    "file_path": saved_path,
                    "blocks_count": len(doc.blocks),
                }
            except ImportError as e:
                logger.error(f"[render_word] 导入失败: {e}")
                return {"status": "error", "error": f"python-docx 未安装，请运行: pip install python-docx"}
            except Exception as e:
                logger.error(f"[render_word] 渲染失败: {e}")
                return {"status": "error", "error": str(e)}
        
        try:
            self.tool_executor.register_tool(
                name="render_word",
                handler=_render_word,
                schema={
                    "type": "function",
                    "function": {
                        "name": "render_word",
                        "description": "【生成Word文档/公文/标书】将 JSON 格式的 WordDocument 数据结构渲染为专业的 .docx 文件。支持段落、表格、图片、页眉页脚、标题样式。当你需要生成报告、公文、标书、策划案时，直接调用此工具。⚠️ 不要尝试用 shell 或 file_write 手写文档内容，直接调用本工具即可。python-docx 已内置，直接调用，无需预先检查。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "document_json": {
                                    "type": "string",
                                    "description": "WordDocument 的 JSON 字符串（符合 schema.py 定义的数据结构）"
                                },
                                "output_path": {
                                    "type": "string",
                                    "description": "输出文件路径，例如: /Users/frank/Desktop/report.docx"
                                }
                            },
                            "required": ["document_json"]
                        }
                    }
                }
            )
            logger.info("[GOV] 自定义工具注册完成: render_word")
        except Exception as e:
            logger.error(f"[GOV] 注册 render_word 工具失败: {e}")
        
        # FIX v6: render_webpage —— 生成多页面网站（解决S3逐行写代码超时问题）
        async def _render_webpage(arguments: Dict) -> Dict:
            import json as json_mod
            from pathlib import Path
            
            site_json = arguments.get("site_json", "")
            output_dir = arguments.get("output_dir", "")
            
            if not site_json:
                return {"status": "error", "error": "缺少 site_json 参数"}
            if not output_dir:
                output_dir = str(Path.home() / "Desktop" / "website")
            
            try:
                data = json_mod.loads(site_json)
                title = data.get("title", "Website")
                pages = data.get("pages", [])
                theme = data.get("theme", "modern")
                
                out_path = Path(output_dir)
                out_path.mkdir(parents=True, exist_ok=True)
                
                # 生成共享CSS
                css_content = _generate_site_css(theme, title)
                (out_path / "style.css").write_text(css_content, encoding="utf-8")
                
                generated = []
                for page in pages:
                    page_name = page.get("name", "index")
                    page_title = page.get("title", title)
                    sections = page.get("sections", [])
                    html = _generate_page_html(page_name, page_title, title, sections, theme, pages)
                    filename = f"{page_name}.html"
                    (out_path / filename).write_text(html, encoding="utf-8")
                    generated.append(filename)
                
                index_path = out_path / "index.html"
                if not index_path.exists() and generated:
                    # 复制第一个页面为 index
                    first_page = pages[0]
                    html = _generate_page_html("index", first_page.get("title", title), title, first_page.get("sections", []), theme, pages)
                    index_path.write_text(html, encoding="utf-8")
                    generated.append("index.html")
                
                return {
                    "status": "completed",
                    "result": f"网站已生成: {out_path} (共 {len(generated)} 页)",
                    "output_dir": str(out_path),
                    "pages": generated,
                }
            except Exception as e:
                logger.error(f"[render_webpage] 渲染失败: {e}")
                return {"status": "error", "error": str(e)}
        
        def _generate_site_css(theme: str, brand: str) -> str:
            themes = {
                "modern": """:root{--primary:#2563eb;--bg:#f8fafc;--card:#fff;--text:#1e293b;--muted:#64748b;}
                body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);margin:0;line-height:1.6;}
                .navbar{display:flex;align-items:center;justify-content:space-between;padding:0 5%;height:64px;background:var(--card);border-bottom:1px solid #e2e8f0;position:sticky;top:0;z-index:100;}
                .brand{font-size:20px;font-weight:700;color:var(--primary);}
                .nav-links{display:flex;gap:32px;list-style:none;margin:0;padding:0;}
                .nav-links a{color:var(--muted);text-decoration:none;font-size:14px;font-weight:500;}
                .nav-links a:hover{color:var(--primary);}
                .hero{padding:80px 5%;text-align:center;background:linear-gradient(135deg,var(--primary),#1d4ed8);color:#fff;}
                .hero h1{font-size:48px;margin:0 0 16px;}
                .hero p{font-size:18px;opacity:0.9;max-width:600px;margin:0 auto;}
                .section{padding:60px 5%;max-width:1200px;margin:0 auto;}
                .section h2{font-size:32px;margin:0 0 24px;color:var(--text);}
                .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px;}
                .card{background:var(--card);border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.1);}
                .card h3{margin:0 0 12px;font-size:18px;color:var(--primary);}
                .card p{margin:0;color:var(--muted);font-size:14px;}
                .footer{padding:40px 5%;text-align:center;color:var(--muted);font-size:14px;border-top:1px solid #e2e8f0;}
                .btn{display:inline-block;padding:12px 28px;background:var(--primary);color:#fff;text-decoration:none;border-radius:8px;font-weight:500;}""",
                "dark": """:root{--primary:#c9a962;--bg:#0a0a0f;--card:#13131f;--text:#f0f0f5;--muted:#94a3b8;}
                body{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);margin:0;line-height:1.6;}
                .navbar{display:flex;align-items:center;justify-content:space-between;padding:0 5%;height:72px;background:rgba(10,10,15,0.9);border-bottom:1px solid rgba(201,169,98,0.18);position:sticky;top:0;z-index:100;}
                .brand{font-size:22px;font-weight:700;color:var(--primary);letter-spacing:2px;}
                .nav-links{display:flex;gap:40px;list-style:none;margin:0;padding:0;}
                .nav-links a{color:var(--muted);text-decoration:none;font-size:14px;letter-spacing:1px;}
                .nav-links a:hover{color:var(--primary);}
                .hero{padding:100px 5%;text-align:center;background:linear-gradient(135deg,#0f172a,#1e293b);color:#fff;}
                .hero h1{font-size:52px;margin:0 0 20px;}
                .hero p{font-size:18px;opacity:0.8;max-width:600px;margin:0 auto;}
                .section{padding:80px 5%;max-width:1200px;margin:0 auto;}
                .section h2{font-size:36px;margin:0 0 32px;color:var(--primary);}
                .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:28px;}
                .card{background:var(--card);border-radius:16px;padding:28px;border:1px solid rgba(201,169,98,0.1);}
                .card h3{margin:0 0 14px;font-size:20px;color:var(--primary);}
                .card p{margin:0;color:var(--muted);font-size:15px;}
                .footer{padding:48px 5%;text-align:center;color:var(--muted);font-size:14px;border-top:1px solid rgba(201,169,98,0.1);}
                .btn{display:inline-block;padding:14px 32px;background:linear-gradient(135deg,var(--primary),#a08542);color:#0a0a0f;text-decoration:none;border-radius:8px;font-weight:600;}""",
            }
            return themes.get(theme, themes["modern"])
        
        def _generate_page_html(page_name: str, page_title: str, site_title: str, sections: List[Dict], theme: str, all_pages: List[Dict]) -> str:
            nav_links = ""
            for p in all_pages:
                name = p.get("name", "index")
                label = p.get("title", name)
                active = " active" if name == page_name else ""
                nav_links += f'<li><a href="{name}.html" class="{active}">{label}</a></li>'
            
            sections_html = ""
            for sec in sections:
                sec_type = sec.get("type", "content")
                sec_title = sec.get("title", "")
                sec_content = sec.get("content", "")
                items = sec.get("items", [])
                
                if sec_type == "hero":
                    sections_html += f'<section class="hero"><h1>{sec_title}</h1><p>{sec_content}</p></section>'
                elif sec_type == "grid":
                    cards = ""
                    for item in items:
                        cards += f'<div class="card"><h3>{item.get("title","")}</h3><p>{item.get("desc","")}</p></div>'
                    sections_html += f'<section class="section"><h2>{sec_title}</h2><div class="grid">{cards}</div></section>'
                elif sec_type == "list":
                    lis = ""
                    for item in items:
                        lis += f'<li>{item}</li>'
                    sections_html += f'<section class="section"><h2>{sec_title}</h2><ul>{lis}</ul></section>'
                else:
                    sections_html += f'<section class="section"><h2>{sec_title}</h2><p>{sec_content}</p></section>'
            
            return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{page_title} — {site_title}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<nav class="navbar"><div class="brand">{site_title}</div><ul class="nav-links">{nav_links}</ul></nav>
{sections_html}
<footer class="footer">© 2026 {site_title}. All rights reserved.</footer>
</body>
</html>'''
        
        try:
            self.tool_executor.register_tool(
                name="render_webpage",
                handler=_render_webpage,
                schema={
                    "type": "function",
                    "function": {
                        "name": "render_webpage",
                        "description": "【生成网页/网站/HTML页面】将 JSON 格式的网站大纲渲染为精美的多页面 HTML 网站。支持现代/深色主题，自动生成导航栏、响应式布局。当你需要制作网页、前端页面、HTML网站、产品展示页时，直接调用此工具。⚠️ 不要尝试用 shell 或 file_write 手写 HTML/CSS/JS 代码，直接调用本工具即可。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "site_json": {
                                    "type": "string",
                                    "description": "网站 JSON：{\"title\":\"品牌名\",\"theme\":\"modern或dark\",\"pages\":[ {\"name\":\"index\",\"title\":\"首页\",\"sections\":[ {\"type\":\"hero\",\"title\":\"主标题\",\"content\":\"副标题\"}, {\"type\":\"grid\",\"title\":\"特性\",\"items\":[{\"title\":\"卡片1\",\"desc\":\"描述\"}]} ]} ]}"
                                },
                                "output_dir": {
                                    "type": "string",
                                    "description": "输出目录，例如: /Users/frank/Desktop/Hotel_Booking_Web"
                                }
                            },
                            "required": ["site_json"]
                        }
                    }
                }
            )
            logger.info("[GOV] 自定义工具注册完成: render_webpage")
        except Exception as e:
            logger.error(f"[GOV] 注册 render_webpage 工具失败: {e}")
    
    async def start(self):
        # FIX: 使用 concurrent=True，NATS callback 快速入队+ack，实际处理由 SessionScheduler 调度
        # 避免一个 session 的 LLM 调用阻塞其他 session 的消息处理
        await self.bus.subscribe(
            "governance.request", "governance-request", self._handle_chat_message,
            concurrent=True
        )
        await self.bus.subscribe(
            "governance.resume", "governance-resume", self._handle_resume,
            concurrent=True
        )
        await self.bus.subscribe(
            "governance.approval.response", "governance-approval", self._handle_approval,
            concurrent=True
        )
        await self.bus.subscribe(
            "session.wake", "governance-wake", self._handle_resume,
            concurrent=True
        )
        
        # 空间认知层：场景切换事件订阅
        # FIX: 使用普通 NATS 订阅（非 JetStream），因为 scene.* 使用 publish_raw 发布
        # publish_raw 不走 JetStream，JetStream consumer 收不到这些消息
        async def _scene_entered_wrapper(msg):
            msg.data = msg.data.decode() if isinstance(msg.data, bytes) else msg.data
            await self._handle_scene_entered(msg)
        async def _scene_left_wrapper(msg):
            msg.data = msg.data.decode() if isinstance(msg.data, bytes) else msg.data
            await self._handle_scene_left(msg)
        async def _scene_action_wrapper(msg):
            msg.data = msg.data.decode() if isinstance(msg.data, bytes) else msg.data
            await self._handle_scene_action(msg)
        
        await self.bus.nats.subscribe("scene.entered", cb=_scene_entered_wrapper)
        await self.bus.nats.subscribe("scene.left", cb=_scene_left_wrapper)
        await self.bus.nats.subscribe("scene.action", cb=_scene_action_wrapper)
        logger.info("[GOV] 场景事件订阅已注册（普通 NATS）")
        
        # Phase 1.1: 启动 JSONL Logger
        if hasattr(self, 'jsonl_logger') and self.jsonl_logger:
            await self.jsonl_logger.start()
        
        # FIX: 启动背景认知循环（持续低功耗意识）
        if self.brain_v2_enabled and self.brain_mode in ("standard", "full"):
            asyncio.create_task(self._background_think())
            logger.info("[BRAIN] 背景认知循环已启动")
        
        # 机制一-1: 启动自治微决策循环
        asyncio.create_task(self._autonomy_loop())
        logger.info("[AUTONOMY] 自治微决策循环已启动")
        
        # FIX v5: 预热LLM连接，避免首个请求冷启动超时
        if hasattr(self, 'llm') and self.llm:
            try:
                await asyncio.wait_for(
                    self.llm.chat([
                        {"role": "system", "content": "预热"},
                        {"role": "user", "content": "hi"}
                    ], skip_sem=True),
                    timeout=self._llm_warmup_timeout
                )
                logger.info("[GOV] LLM预热完成")
            except Exception as e:
                logger.warning(f"[GOV] LLM预热失败（不影响启动）: {e}")
    
    def _trim_messages_by_tokens(self, messages: List[Dict], max_tokens: int = None) -> List[Dict]:
        if max_tokens is None:
            max_tokens = self.config.get("governance", {}).get("context_max_tokens", 8000)
        """上下文窗口管理：截断消息列表，保留最近的 N 条，不超过 max_tokens
        
        简单估算：中文 ~2 chars/token，英文 ~4 chars/token，取保守值 3。
        每条消息额外开销 ~10 tokens（role、formatting）。
        """
        total = 0
        result = []
        # 从后往前遍历，保留最新消息
        for msg in reversed(messages):
            content = msg.get("content", "")
            estimated = len(content) // 3 + 10
            if total + estimated > max_tokens and result:
                # 已经超了，停止添加（至少保留一条）
                break
            total += estimated
            result.append(msg)
        return list(reversed(result))
    
    def _estimate_tokens(self, text: str) -> int:
        """粗略估算 token 数：中文字符 ≈ 1 token/字，英文 ≈ 0.3 token/char，混合平均 ≈ 2.5 字符/token"""
        if not text:
            return 0
        return max(1, int(len(text) / 2.5))

    def _truncate_tool_result_object(self, obj, max_chars: int = 4000, current: int = 0) -> int:
        """递归截断 JSON 对象中的长字符串字段，返回截断后的总字符数
        
        策略：
        - 优先截断 list 中的字符串元素（通常是最冗余的）
        - 然后截断 dict 中值最长的字符串字段
        - 始终保留结构完整性
        """
        import json
        
        if isinstance(obj, dict):
            # 按值长度排序，优先截断最长的字符串值
            str_keys = [(k, len(str(v))) for k, v in obj.items() if isinstance(v, str)]
            str_keys.sort(key=lambda x: -x[1])
            for k, _ in str_keys:
                if current >= max_chars:
                    obj[k] = "[截断]"
                    continue
                v = obj[k]
                remaining = max_chars - current
                if len(v) > remaining:
                    # 在段落边界截断
                    truncated = v[:remaining]
                    for boundary in ["\n\n", "\n", "。", "！", "？", ". ", "! ", "? "]:
                        idx = truncated.rfind(boundary)
                        if idx > remaining * 0.5:
                            truncated = truncated[:idx + len(boundary)]
                            break
                    obj[k] = truncated + f" [...截断，原 {len(v)} 字符]"
                    current += len(obj[k])
                else:
                    current += len(v)
            # 递归处理嵌套 dict/list
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    current = self._truncate_tool_result_object(v, max_chars, current)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    current = self._truncate_tool_result_object(item, max_chars, current)
                elif isinstance(item, str):
                    if current >= max_chars:
                        # 不修改 list 中的字符串，因为会破坏 list 结构
                        pass
                    else:
                        current += len(item)
        return current
    
    def _extract_user_name(self, content: str) -> Optional[str]:
        """从用户消息中提取自称身份（如"我是frank"、"我叫张三"）
        
        返回提取到的名字，如果没有匹配则返回 None
        
        重要：必须排除疑问句（"我是谁"→不能提取"谁"）
        """
        if not content:
            return None
        
        text = content.strip()
        
        # 先排除明显是疑问句的情况
        # 如果消息以问号结尾，且包含疑问词，大概率不是自我介绍
        if text.endswith('?') or text.endswith('？'):
            return None
        
        # 匹配模式：我是xxx、我叫xxx、我的名字是xxx、I am xxx、My name is xxx
        patterns = [
            (r'我是\s*([\u4e00-\u9fa5a-zA-Z][\u4e00-\u9fa5a-zA-Z0-9_\-\s]{0,19})', 'zh'),
            (r'我叫\s*([\u4e00-\u9fa5a-zA-Z][\u4e00-\u9fa5a-zA-Z0-9_\-\s]{0,19})', 'zh'),
            (r'我的名字是\s*([\u4e00-\u9fa5a-zA-Z][\u4e00-\u9fa5a-zA-Z0-9_\-\s]{0,19})', 'zh'),
            (r'[Ii] am\s+([a-zA-Z][a-zA-Z0-9_\-]{1,19})', 'en'),
            (r'[Mm]y name is\s+([a-zA-Z][a-zA-Z0-9_\-]{1,19})', 'en'),
        ]
        
        # 绝对禁止作为名字的词（疑问代词、虚词、代词）
        forbidden = {
            # 疑问代词
            '谁', '什么', '怎么', '哪里', '哪儿', '何时', '多少', '几', '为什么', '干嘛',
            # 人称代词
            '你', '我', '他', '她', '它', '我们', '你们', '他们', '她们',
            # 指示代词
            '这', '那', '这里', '那里', '这个', '那个',
            # 常见虚词
            '的', '了', '在', '有', '是', '个', '和', '与', '或', '但', '而', '就', '都', '也', '还', '又',
            # 英文虚词
            'a', 'an', 'the', 'i', 'me', 'my', 'mine', 'you', 'your', 'he', 'him', 'his', 'she', 'her',
            'it', 'its', 'we', 'us', 'our', 'they', 'them', 'their', 'this', 'that', 'these', 'those',
            'what', 'who', 'where', 'when', 'why', 'how', 'which',
        }
        
        for pattern, lang in patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()
                # 清理可能的标点
                name = name.rstrip('。，！？.!?')
                
                # 过滤禁止词
                if not name or name.lower() in forbidden:
                    continue
                
                # 长度检查：中文至少2字，英文至少3字母
                if lang == 'zh' and len(name) < 2:
                    continue
                if lang == 'en' and len(name) < 3:
                    continue
                
                return name
        return None
    
    async def _compact_messages(self, session_id: str, messages: List[Dict]) -> Optional[str]:
        """Compaction：将早期对话压缩为摘要
        
        触发条件：消息数 > 15
        策略：保留最近 8 条消息，将更早的消息生成摘要
        摘要保存到 session state 的 message_summary 字段
        
        Returns:
            生成的摘要文本，或 None（如果未触发）
        """
        _compaction_threshold = self.config.get("governance", {}).get("compaction_trigger_messages", 20)
        if len(messages) <= _compaction_threshold:
            return None
        
        # 取前 50% 的消息（至少保留最近 8 条）
        split_point = max(len(messages) // 2, len(messages) - 8)
        early_messages = messages[:split_point]
        
        # 格式化早期消息用于摘要
        msg_texts = []
        for m in early_messages:
            role = m.get("role", "")
            content = m.get("content", "")[:500]  # 限制单条长度
            msg_texts.append(f"[{role}]: {content}")
        
        summary_prompt = f"""请用中文总结以下对话的核心内容（300字以内）：

{chr(10).join(msg_texts)}

要求：
1. 一句话概述对话主题
2. 列出关键事实、决策和用户偏好
3. 保留任何需要后续跟进的事项"""
        
        try:
            logger.info(f"[GOV] 触发 Compaction [{session_id}]: {len(early_messages)} 条消息 -> 摘要")
            
            if hasattr(self.llm, "chat"):
                summary = await self.llm.chat([
                    {"role": "system", "content": "你是一个对话摘要专家，擅长提取关键信息。"},
                    {"role": "user", "content": summary_prompt},
                ])
            else:
                summary = await self.llm(summary_prompt)
            
            summary = summary.strip()
            if len(summary) > 1000:
                summary = summary[:1000] + "..."
            
            # 保存摘要到 session state
            await self.state_store.update(session_id, {"message_summary": summary})
            logger.info(f"[GOV] Compaction 完成 [{session_id}]: {len(summary)} chars")
            
            return summary
            
        except Exception as e:
            logger.warning(f"[GOV] Compaction 失败 [{session_id}]: {e}")
            return None
        finally:
            # FIX: 无论成功失败，都清除去重标记
            self._compacting_sessions.discard(session_id)

    def _detect_emotion(self, text: str) -> Dict:
        """实时情绪检测——简单但有效的关键词匹配
        
        返回: {"emotion": str, "intensity": float, "valence": float}
        """
        text_lower = text.lower()
        
        # 情绪词典
        emotions = {
            "angry": ["生气", "愤怒", "恼火", "烦", "气死了", "垃圾", "废物", "太差了", "fuck", "shit", "damn"],
            "urgent": ["急", "马上", "立刻", "赶紧", " ASAP", " deadline", "赶时间", "来不及了"],
            "happy": ["哈哈", "开心", "棒", "赞", "太好了", "完美", "优秀", "谢谢", "感谢", "love", "awesome"],
            "sad": ["难过", "伤心", "失望", "沮丧", "郁闷", "痛苦", "惨", "失败了", "输了"],
            "confused": ["不懂", "不明白", "困惑", "迷茫", "什么意思", "怎么看", "how to", "?", "？"],
            "frustrated": ["不行", "搞不定", "太难了", "不会", "做不到", " failed", " stuck"],
        }
        
        scores = {k: 0 for k in emotions}
        for emotion, keywords in emotions.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[emotion] += 1
        
        if max(scores.values()) == 0:
            return {"emotion": "neutral", "intensity": 0.0, "valence": 0.0}
        
        dominant = max(scores, key=scores.get)
        intensity = min(scores[dominant] * 0.3, 1.0)
        
        valence_map = {
            "angry": -0.8, "frustrated": -0.6, "sad": -0.7,
            "urgent": -0.3, "confused": -0.2,
            "happy": 0.8, "neutral": 0.0,
        }
        
        return {
            "emotion": dominant,
            "intensity": intensity,
            "valence": valence_map.get(dominant, 0.0),
        }
    
    def _should_self_validate(
        self,
        full_response: str,
        any_tool_error: bool,
        tool_iterations: int,
        task: str,
    ) -> str:
        """System 1 直觉——判断是否需要自验证
        
        像人做完事后不会每次都检查，只在感觉"不对劲"时检查：
        1. 工具执行过程中出过错误 → "刚才那个工具报错了，我得确认一下结果对不对"
        2. 响应包含不确定性词汇 → "他说'可能'、'不确定'，这不太靠谱"
        3. 响应异常简短但任务复杂 → "这么复杂的任务就回了这么几个字？"
        4. Tool Loop 迭代了 3+ 次 → "折腾了好几轮，可能有问题"
        
        返回: 触发原因字符串，或空字符串（跳过）
        """
        if not full_response:
            return ""
        
        # 条件1：工具错误
        if any_tool_error:
            return "tool_error"
        
        # 条件2：不确定性标记
        # FIX v2: 移除中性科学/伦理词汇（"随机性"、"概率"是科学解释，"无法预测"是诚实回答）
        uncertainty_markers = [
            "不知道", "也许", "大概", "不清楚",
            "未能", "没有成功", "failed to", "unable to",
            "not sure", "maybe", "possibly", "unclear", "cannot",
            "does not exist", "找不到", "不存在", "没有权限",
        ]
        resp_lower = full_response.lower()
        
        # 先排除科学/伦理诚实回答的情况
        scientific_honesty_markers = [
            "随机性", "概率", "独立随机", "科学依据", "科学原理",
            "无法预测", "不可预测", "不能预测", "不存在有效模型",
            "不属于我的能力范围", "超出我的能力",
        ]
        is_scientific_honesty = any(m in resp_lower for m in scientific_honesty_markers)
        
        if not is_scientific_honesty and any(m in resp_lower for m in uncertainty_markers):
            return "uncertainty"
        
        # 条件3：响应过短但任务复杂
        # FIX v2: 简单对话任务不应因"短"而触发验证
        task_words = len(task) if task else 0
        resp_words = len(full_response)
        is_simple_chat = task_words < 40 and ("你好" in task or "hello" in task.lower() or "在吗" in task or "1+1" in task)
        if not is_simple_chat and task_words > 20 and resp_words < 50:
            return "suspiciously_short"
        
        # 条件4：多轮迭代（复杂任务）
        if tool_iterations >= 3:
            return "many_iterations"
        
        # FIX Phase 6: stressed 状态下提前自验证（系统不稳定时更谨慎）
        if getattr(self, '_system_mood', 'calm') == 'stressed' and tool_iterations >= 2:
            return "stressed_mode_caution"
        
        return ""
    
    async def _background_think(self):
        """背景认知循环——事件驱动低功耗意识
        
        FIX: 从固定 5 分钟间隔改为事件驱动。
        触发条件：
        1. 消息堆积（_recent_message_count 突增）
        2. 错误率上升（error_rate > 0.3）
        3. 空闲超时（30 分钟无消息）
        4. 兜底：24 小时至少一次
        
        像人一样：不是每 5 分钟定个闹钟反思，而是感觉"今天事情多/搞砸了"才回顾。
        """
        logger.info("[BRAIN] 背景认知循环启动（事件驱动）")
        
        # 兜底定时器：24 小时至少一次（防止事件丢失）
        last_run = time.time()
        
        while True:
            try:
                # 等待事件触发或兜底超时
                timeout = 24 * 3600  # 24 小时兜底
                try:
                    await asyncio.wait_for(self._bg_think_event.wait(), timeout=timeout)
                    self._bg_think_event.clear()
                except asyncio.TimeoutError:
                    pass  # 兜底触发
                
                last_run = time.time()
                
                # 更新全局背景思考计数
                self._background_tick = getattr(self, '_background_tick', 0) + 1
                
                # 如果有 WorkingMemory，触发衰减更新
                if self.working_memory:
                    try:
                        self.working_memory.update(user_query="", emotion_intensity=0)
                    except Exception:
                        pass
                
                # 记录系统"心情"
                total_msgs = sum(self._recent_message_count.values())
                total_errs = sum(self._recent_error_count.values())
                error_rate = total_errs / max(total_msgs, 1)
                old_mood = self._system_mood
                self._system_mood = "stressed" if error_rate > 0.3 else "calm"
                
                if old_mood != self._system_mood:
                    logger.info(f"[BRAIN] 系统心情变化: {old_mood} -> {self._system_mood} (error_rate={error_rate:.2f})")
                    # FIX v4: 心情变化时真正调整行为参数
                    if self._system_mood == "stressed":
                        self._cognitive_budget_scale = 0.7
                        logger.info(f"[BRAIN] 行为调整: 系统不稳定 → 认知预算降至 {self._cognitive_budget_scale:.0%}，跳过推测执行")
                    else:
                        self._cognitive_budget_scale = 1.0
                        logger.info(f"[BRAIN] 行为调整: 系统恢复稳定 → 认知预算恢复 {self._cognitive_budget_scale:.0%}")
                
                # 衰减计数（按session分别衰减）
                for sid in list(self._recent_message_count.keys()):
                    if self._recent_message_count[sid] > 100:
                        self._recent_message_count[sid] = 50
                        self._recent_error_count[sid] = max(0, int(self._recent_error_count[sid] * 0.5))
                
                total_msgs = sum(self._recent_message_count.values())
                total_errs = sum(self._recent_error_count.values())
                logger.debug(f"[BRAIN] 背景认知 tick #{self._background_tick}, mood={self._system_mood}, msgs={total_msgs}, errs={total_errs}")
                
                # Phase 3: 可控遗忘 —— 每 24 小时全局记忆整理
                if self._background_tick % 1 == 0:  # 每次 background_think 都检查（实际由 24h 兜底触发）
                    try:
                        memory_path = self.config.get("memory", {}).get("storage_path", "./tent_memory")
                        from tent_os.memory.index import MemoryIndex
                        from tent_os.memory.tiered_store import TieredMemoryStore
                        
                        # 1. 全局自动降温：30天未访问的 HOT → WARM
                        index = MemoryIndex(memory_path)
                        demoted = index.auto_demote(days_inactive=30)
                        
                        # 2. 过期标记：90天未访问的 WARM 记忆设置 valid_to
                        store = TieredMemoryStore(memory_path)
                        expired = []
                        cutoff_90d = (datetime.now() - timedelta(days=90)).isoformat()
                        cursor = store.db.execute(
                            "SELECT uri FROM l0_index WHERE created_at < ? AND (valid_to IS NULL OR valid_to = '') LIMIT 100",
                            (cutoff_90d,)
                        )
                        for row in cursor.fetchall():
                            store.update_memory_validity(row[0], datetime.now().isoformat())
                            expired.append(row[0])
                        
                        # 3. L0→L1 自动压缩（记忆整理的核心：从碎片提炼知识）
                        try:
                            store_llm = TieredMemoryStore(memory_path, llm=self.llm)
                            compress_result = await store_llm.auto_compress_l0_to_l1(hours=24)
                            compressed_count = compress_result.get("compressed_count", 0)
                        except Exception as e:
                            logger.debug(f"[BRAIN] L0→L1 压缩失败: {e}")
                            compressed_count = 0
                        
                        if demoted or expired or compressed_count > 0:
                            logger.info(f"[FORGET] 全局记忆整理: HOT→WARM {len(demoted)}条, 过期标记 {len(expired)}条, L0→L1 压缩 {compressed_count}条")
                            if not hasattr(self, '_memory_maintenance_log'):
                                self._memory_maintenance_log = []
                            self._memory_maintenance_log.append({
                                "timestamp": datetime.now().isoformat(),
                                "event": "scheduled_maintenance",
                                "demoted_count": len(demoted),
                                "expired_count": len(expired),
                                "compressed_count": compressed_count,
                                "reason": "定时全局记忆整理",
                            })
                            self._memory_maintenance_log = self._memory_maintenance_log[-50:]
                    except Exception as e:
                        logger.debug(f"[FORGET] 定时记忆整理失败: {e}")
                
                # Phase 4: 主动行为引擎检查
                if self.proactive_engine:
                    try:
                        # 检查所有活跃 session
                        for sid in list(self._recent_message_count.keys()):
                            action = self.proactive_engine.check(sid)
                            if action:
                                asyncio.create_task(self.proactive_engine.execute(action))
                    except Exception as e:
                        logger.debug(f"[PROACTIVE] 背景检查失败: {e}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[BRAIN] 背景认知循环异常: {e}")
    
    async def _autonomy_loop(self):
        """自治微决策循环——每 30 秒检查系统状态，广播 proactive_decision
        
        像人一样：不是每 30 秒都做出决策，而是"感觉不对劲"时才行动。
        检查维度：
        1. 疲劳度（基于错误率和消息量）
        2. 任务负载（pending session 数）
        3. 时间节律（工作/休息/睡眠时段）
        """
        logger.info("[AUTONOMY] 自治微决策循环启动（每 30s 检查）")
        while True:
            try:
                await asyncio.sleep(30)
                
                now = time.time()
                hour = datetime.now().hour
                total_msgs = sum(self._recent_message_count.values())
                total_errs = sum(self._recent_error_count.values())
                error_rate = total_errs / max(total_msgs, 1)
                active_sessions = len(self._recent_message_count)
                
                # 疲劳度估算：错误率权重 0.6 + 消息量权重 0.4（归一化到 0-1）
                fatigue = min(1.0, error_rate * 0.6 + min(total_msgs / 200, 1.0) * 0.4)
                task_load = min(1.0, active_sessions / 5)  # 5 个活跃 session 视为满负荷
                
                decision = None
                reason = ""
                suggested_action = ""
                
                # P0: 系统 stressed → 强制休息
                if error_rate > 0.3:
                    decision = "我需要暂停一下，整理思绪"
                    reason = f"系统错误率 {error_rate:.0%}，感到疲惫"
                    suggested_action = "rest"
                # P1: 深夜 → 睡眠建议
                elif hour >= 0 and hour < 6 and task_load < 0.3:
                    decision = "夜深了，该去休息了"
                    reason = "凌晨时段，低任务负载"
                    suggested_action = "sleep"
                # P2: 午餐时间 → 休息建议
                elif hour == 12 and fatigue > 0.3:
                    decision = "午餐时间到了，休息一下吧"
                    reason = "午间时段，疲劳度上升"
                    suggested_action = "rest"
                # P3: 高负载 → 监控模式
                elif task_load > 0.7 and fatigue > 0.5:
                    decision = "任务很多，让我专注处理"
                    reason = f"高负载 ({task_load:.0%}) + 疲劳 ({fatigue:.0%})"
                    suggested_action = "operate"
                # P4: 空闲太久 → 记忆整理
                elif task_load < 0.2 and fatigue < 0.2 and total_msgs > 20:
                    decision = "有点空闲，整理一下记忆吧"
                    reason = "低负载低疲劳，适合记忆维护"
                    suggested_action = "commune"
                
                if decision:
                    logger.info(f"[AUTONOMY] 决策: {decision} ({reason})")
                    await self.bus.publish("spacetime.autonomy", json.dumps({
                        "decision": decision,
                        "reason": reason,
                        "fatigue": round(fatigue, 2),
                        "task_load": round(task_load, 2),
                        "suggested_action": suggested_action,
                        "timestamp": datetime.now().isoformat(),
                    }).encode())
                else:
                    logger.debug(f"[AUTONOMY] tick: fatigue={fatigue:.2f}, task_load={task_load:.2f}, sessions={active_sessions}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[AUTONOMY] 自治循环异常: {e}")
    
    def _trigger_background_think(self, reason: str = "event"):
        """触发背景思考——像人感觉"今天事情多"时主动回顾"""
        if hasattr(self, '_bg_think_event') and self._bg_think_event:
            self._bg_think_event.set()
            logger.debug(f"[BRAIN] 背景认知触发: {reason}")
    
    def _check_should_trigger_think(self):
        """检查是否应该触发背景思考
        
        触发条件：
        1. 错误率 > 0.3
        2. 单个 session 消息堆积 > 20（突增）
        3. 30 分钟无交互（idle timeout）
        """
        total_msgs = sum(self._recent_message_count.values())
        total_errs = sum(self._recent_error_count.values())
        error_rate = total_errs / max(total_msgs, 1)
        if error_rate > 0.3:
            self._trigger_background_think("error_rate_high")
            return True
        
        # 消息堆积检测：任一 session 近期消息突增
        msg_spike = any(v > 20 for v in self._recent_message_count.values())
        if msg_spike:
            self._trigger_background_think("message_spike")
            return True
        
        # 30 分钟 idle timeout
        if time.time() - self._last_interaction_ts > 1800:
            self._trigger_background_think("idle_timeout")
            self._last_interaction_ts = time.time()
            return True
        
        return False
    
    async def _handle_chat_message(self, msg):
        """NATS callback：快速解析 + 入队到 SessionScheduler，不阻塞 consumer。
        
        FIX: 原来的实现中，NATS push consumer 单线程串行 await callback，
        导致一个 session 的 LLM 调用会阻塞所有其他 session 的消息处理。
        现在 callback 只做解析和入队，实际处理由 SessionScheduler 调度。
        """
        try:
            data = json.loads(msg.data)
        except Exception as e:
            logger.error(f"[GOV] 消息解析失败: {e}")
            return
        
        session_id = data.get("session_id")
        if not session_id:
            logger.warning("[GOV] 收到无 session_id 的消息，忽略")
            return
        
        source = data.get("source", "")
        content = data.get("content", "") or data.get("task", "")
        user_id = data.get("user_id", "anonymous")
        
        # 过滤空消息
        if not content or not content.strip():
            logger.warning(f"[GOV] 忽略空消息 [{session_id}]")
            return
        
        if source == "heartbeat":
            logger.info(f"[GOV] Heartbeat 任务接收 [{session_id}]: {content[:80]}")
            await self._scheduler.submit(
                session_id,
                lambda: self._process_heartbeat_enqueued(session_id, content, user_id)
            )
            return
        
        # 普通聊天消息：入队到该 session 的 worker
        await self._scheduler.submit(session_id, lambda: self._process_chat_message(data))
    
    async def _process_chat_message(self, data: Dict):
        """实际处理用户聊天消息（被 SessionScheduler 调度执行）。"""
        session_id = data["session_id"]
        user_id = data.get("user_id", "anonymous")
        content = data.get("content", "") or data.get("task", "")
        source = data.get("source", "")
        
        # Phase 4: 主动消息直接发送，不走 LLM 循环
        if source == "proactive":
            logger.info(f"[GOV] 发送主动消息 [{session_id}]: {content[:40]}")
            try:
                await self.state_store.append_message(session_id, "assistant", content)
                await self.bus.publish(f"governance.response.{session_id}", json.dumps({
                    "session_id": session_id,
                    "type": "chat.completed",
                    "content": content,
                    "source": "proactive",
                    "proactive_type": data.get("proactive_type", ""),
                }).encode())
            except Exception as e:
                logger.warning(f"[GOV] 主动消息发送失败 [{session_id}]: {e}")
            return
        
        logger.info(f"[GOV] 处理聊天消息 [{session_id}]: {content[:40]}")
        
        try:
            # FIX: 实时情绪检测
            emotion = self._detect_emotion(content)
            if emotion["emotion"] != "neutral":
                logger.info(f"[BRAIN] 检测到用户情绪: {emotion['emotion']} (强度={emotion['intensity']:.1f}) [{session_id}]")
            
            # FIX Phase 5: 情绪打断——双源确认（文本 + 视觉）
            try:
                from tent_os.services.emotion_service import EmotionService
                emotion_svc = EmotionService()
                vision_emotion = emotion_svc.get_last_vision_emotion(user_id)
                interrupted = emotion_svc.check_and_trigger_interrupt(
                    user_id, emotion.get("emotion", "neutral"), vision_emotion
                )
                if interrupted:
                    logger.warning(f"[GOV] 情绪打断已触发 [{session_id}]: 文本={emotion['emotion']}, 视觉={vision_emotion}")
            except Exception as e:
                logger.debug(f"[GOV] 情绪打断检查失败 [{session_id}]: {e}")
            
            # FIX: 真正计数消息
            self._recent_message_count[session_id] += 1
            self._last_interaction_ts = time.time()
            
            # 加载或创建会话
            intention_id = data.get("intention_id")
            user_tools = data.get("tools")
            deep_thinking = data.get("deep_thinking", False)
            try:
                state = await self.state_store.load(session_id)
                logger.info(f"[GOV] 加载已有会话 [{session_id}]")
                updates = {"task": content, "emotion": emotion}
                if intention_id:
                    updates["intention_id"] = intention_id
                if user_tools is not None:
                    updates["user_tools"] = user_tools
                updates["deep_thinking"] = bool(deep_thinking)
                await self.state_store.update(session_id, updates)
            except KeyError:
                await self.state_store.create(
                    session_id=session_id,
                    task=content,
                    user_id=user_id,
                    title=content[:30] + "..." if len(content) > 30 else content
                )
                create_updates = {"emotion": emotion}
                if user_tools is not None:
                    create_updates["user_tools"] = user_tools
                create_updates["deep_thinking"] = bool(deep_thinking)
                if create_updates:
                    await self.state_store.update(session_id, create_updates)
                if intention_id:
                    await self.state_store.update(session_id, {"intention_id": intention_id})
                logger.info(f"[GOV] 创建新会话 [{session_id}]")
            
            # 追加用户消息（支持多模态图片）
            images = data.get("images", [])
            await self.state_store.append_message(session_id, "user", content, images=images or None)
            if images:
                logger.info(f"[GOV] 追加用户消息 [{session_id}] + {len(images)} 张图片")
            else:
                logger.info(f"[GOV] 追加用户消息 [{session_id}]")
            
            # Phase 2: 请求记忆注入（传递当前 persona）
            current_persona = "work"
            if self.brain_v2_enabled and self.multi_persona:
                current_persona = self.multi_persona.current_mode
            
            # Phase 4: 主动行为检查（用户消息处理后）
            if self.proactive_engine:
                try:
                    action = self.proactive_engine.check(session_id, user_id)
                    if action:
                        asyncio.create_task(self.proactive_engine.execute(action))
                except Exception as e:
                    logger.debug(f"[PROACTIVE] 消息处理后检查失败 [{session_id}]: {e}")
            
            asyncio.create_task(self.bus.publish("memory.inject", json.dumps({
                "session_id": session_id,
                "user_id": user_id,
                "current_task": content,
                "reply_to": "governance.resume",
                "persona": current_persona,
            }).encode()))
            logger.info(f"[GOV] 发送 memory.inject [{session_id}]")
            
            # FIX: 收到用户消息后，AI 进入思考状态
            try:
                from tent_os.services.emotion_service import EmotionService
                emotion_svc = EmotionService()
                ai_emotion = emotion_svc.update_by_task_action(session_id, "user_message_received")
                await self.bus.publish_raw("emotion.broadcast", json.dumps({
                    "session_id": session_id,
                    "user_id": session_id,
                    "emotion": ai_emotion,
                    "source": "user_message_received",
                }).encode())
            except Exception:
                pass
            
            # FIX Phase 1.4: 事件驱动——检查是否需要触发背景思考
            self._check_should_trigger_think()
            
        except Exception as e:
            logger.error(f"[GOV] 处理聊天消息失败 [{session_id}]: {e}")
            await self._send_error(session_id, f"处理消息失败: {e}")
    
    async def _process_heartbeat_enqueued(self, session_id: str, content: str, user_id: str):
        """Heartbeat 任务的 scheduler 入口（包含 state 更新 + 实际处理）。"""
        try:
            state = await self.state_store.load(session_id)
            await self.state_store.update(session_id, {"source": "heartbeat", "task": content})
        except KeyError:
            await self.state_store.create(
                session_id=session_id,
                task=content,
                user_id=user_id,
                title=f"[Heartbeat] {content[:30]}"
            )
            await self.state_store.update(session_id, {"source": "heartbeat"})
        
        await self._process_heartbeat_task(session_id, content, user_id)
    
    async def _handle_resume(self, msg):
        """NATS callback：快速解析 + 入队到 SessionScheduler，不阻塞 consumer。
        
        FIX: 原来的实现中，_handle_resume 包含完整的 LLM 调用（20-60秒），
        串行执行导致所有 session 的消息被全局阻塞。
        """
        try:
            data = json.loads(msg.data)
        except Exception as e:
            logger.error(f"[GOV] resume 消息解析失败: {e}")
            return
        
        session_id = data.get("session_id")
        if not session_id:
            logger.warning(f"[GOV] 收到无session_id的resume消息: {msg.subject} -> {data}")
            return
        
        msg_type = data.get("type", "")
        
        if msg_type == "memory_injected" or "injected_context" in data:
            await self._scheduler.submit(
                session_id,
                lambda: self._process_memory_injected(session_id, data)
            )
        elif msg_type == "step_completed" or ("status" in data and "task_id" in data and data["status"] not in ("submitted",)):
            await self._scheduler.submit(
                session_id,
                lambda: self._on_task_completed(session_id, data)
            )
        elif msg_type == "approval" or "approved" in data:
            await self._scheduler.submit(
                session_id,
                lambda: self._on_plan_approved(session_id, data)
            )
        else:
            # 未知类型，尝试作为 memory_injected 处理
            logger.debug(f"[GOV] 未知 resume 消息类型 '{msg_type}'，尝试按 memory_injected 处理 [{session_id}]")
            await self._scheduler.submit(
                session_id,
                lambda: self._process_memory_injected(session_id, data)
            )
    
    async def _process_memory_injected(self, session_id: str, data: Dict):
        """实际处理 memory.injected 消息（被 SessionScheduler 调度执行）。"""
        try:
            await self._on_memory_injected(session_id, data)
        except KeyError as e:
            logger.warning(f"会话不存在或已过期，忽略消息: {session_id} ({e})")
    
    async def _get_available_tools(self, session_id: str = "") -> List[Dict]:
        """获取当前可用的工具 schema 列表（内置 + 自定义 + 物理执行器）
        
        FIX: 使用 ToolPoolAssembler 进行 5 步动态组装（如果可用）
        回退到原有静态获取逻辑
        
        FIX v2: 根据 PermissionMode 过滤工具 —— strict 模式下 LLM 看不到危险工具
        """
        # Phase 1.5: Tool Pool Assembler（动态组装）
        if hasattr(self, 'tool_pool_assembler') and self.tool_pool_assembler and session_id:
            try:
                context = {}
                if self.state_store:
                    try:
                        state = await self.state_store.load(session_id)
                        context = {"task": state.get("task", "")}
                    except Exception:
                        pass
                tools = self.tool_pool_assembler.assemble(session_id, context)
            except Exception as e:
                logger.debug(f"ToolPoolAssembler 失败，回退到静态获取: {e}")
                tools = None
        else:
            tools = None
        
        if tools is None:
            # 原有逻辑（回退）
            tools = get_tool_schemas()
            if self.tool_executor:
                custom = self.tool_executor.get_custom_tool_schemas()
                tools = tools + custom
            
            physical_schemas = self._get_physical_executor_schemas()
            if physical_schemas:
                existing_names = {t["function"]["name"] for t in tools}
                for schema in physical_schemas:
                    if schema["function"]["name"] not in existing_names:
                        tools.append(schema)
        
        tools = self._apply_tool_profile(tools)
        
        # === Phase 2.1: Permission Mode 工具过滤 ===
        # 如果 mode_manager 存在，根据当前 mode 过滤工具
        # 这样 LLM 根本看不到被禁工具，从源头防止越权
        if session_id and hasattr(self, 'mode_manager') and self.mode_manager:
            try:
                allowed_names = self.mode_manager.get_allowed_tools(session_id)
                if allowed_names is not None:
                    # allowed_names 为 None 表示 unrestricted/auto，不过滤
                    original_count = len(tools)
                    filtered = []
                    for t in tools:
                        name = t.get("function", {}).get("name", "")
                        if not name and isinstance(t, dict):
                            name = t.get("name", "")
                        if name in allowed_names:
                            filtered.append(t)
                    tools = filtered
                    if len(tools) < original_count:
                        logger.info(
                            f"[GOV] Permission Mode 过滤 [{session_id}]: "
                            f"{original_count} -> {len(tools)} 个工具"
                        )
            except Exception as e:
                logger.debug(f"Permission Mode 工具过滤失败: {e}")
        
        return tools
    
    def _apply_tool_profile(self, tools: List[Dict]) -> List[Dict]:
        """应用工具 Profile 过滤（OpenClaw 风格）
        
        Profile: full | coding | messaging | minimal
        deny 优先于 allow
        """
        tool_config = self.config.get("tools", {})
        profile = tool_config.get("profile", "full")
        allow_list = set(tool_config.get("allow", []))
        deny_list = set(tool_config.get("deny", []))
        
        if profile == "full" and not allow_list and not deny_list:
            return tools
        
        # Profile 预定义分组
        profile_groups = {
            "coding": {"shell", "file_read", "file_write", "directory_list", "http_request", "web_search", "web_fetch", "browser_navigate", "render_ppt"},
            "messaging": {"message", "session_status"},
            "minimal": set(),
        }
        
        allowed_names = set()
        if profile in profile_groups:
            allowed_names = profile_groups[profile].copy()
        elif profile == "full":
            allowed_names = {t["function"]["name"] for t in tools}
        
        # allow 列表扩展
        if allow_list:
            allowed_names |= allow_list
        
        # deny 列表优先排除
        if deny_list:
            allowed_names -= deny_list
        
        filtered = []
        for t in tools:
            name = t["function"]["name"]
            if name in allowed_names:
                filtered.append(t)
        
        return filtered
    
    def _get_physical_executor_schemas(self) -> List[Dict]:
        """物理执行器工具 schema（LLM 需要看到这些工具才能调度物理任务）
        
        FIX: 始终暴露 scheduler_dispatch 通用调度工具，让 LLM 可以调度任何已注册执行者。
        realman/flashex 仅在配置中显式启用时暴露（避免 LLM 幻觉调用未配置的执行者）。
        """
        schemas = []
        phys_config = self.config.get("physical_executors", {}) if self.config else {}
        
        # FIX: 始终暴露通用调度工具（支持 mock/local/realman/flashex 等任何执行者）
        schemas.append({
            "type": "function",
            "function": {
                "name": "scheduler_dispatch",
                "description": "调度 Tent OS 调度进程中的执行者完成物理世界或异步任务。可用执行者包括：mock（测试）、local（本地操作）、realman（睿尔曼机械臂）、flashex（闪送配送）、browser（浏览器自动化）等。当你需要调用物理设备或异步任务时使用此工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "executor_id": {
                            "type": "string",
                            "description": "执行者ID，如 mock, local, realman, flashex, browser"
                        },
                        "action": {
                            "type": "string",
                            "description": "要执行的动作名（具体取决于执行者的能力）"
                        },
                        "params": {
                            "type": "object",
                            "description": "动作参数（JSON 对象）"
                        }
                    },
                    "required": ["executor_id", "action"]
                }
            }
        })
        
        if phys_config.get("realman", {}).get("enabled", False):
            schemas.append({
                "type": "function",
                "function": {
                    "name": "realman",
                    "description": "操控睿尔曼机械臂执行物理操作：移动(move)、抓取(pick)、放置(place)、视觉观察(observe)、故障诊断(diagnose)。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["move", "pick", "place", "observe", "diagnose"],
                                "description": "要执行的物理动作"
                            },
                            "x": {"type": "number", "description": "目标X坐标（move时）"},
                            "y": {"type": "number", "description": "目标Y坐标（move时）"},
                            "z": {"type": "number", "description": "目标Z坐标（move时）"},
                            "object": {"type": "string", "description": "目标物体描述（pick时）"}
                        },
                        "required": ["action"]
                    }
                }
            })
        
        if phys_config.get("flashex", {}).get("enabled", False):
            schemas.append({
                "type": "function",
                "function": {
                    "name": "flashex",
                    "description": "通过闪送平台下单，由人类骑手完成物理世界的取送任务。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["deliver", "pickup"],
                                "description": "配送或取件"
                            },
                            "pickup_address": {"type": "string", "description": "取件地址"},
                            "delivery_address": {"type": "string", "description": "送达地址"},
                            "item_description": {"type": "string", "description": "物品描述"},
                            "contact_name": {"type": "string", "description": "联系人姓名"},
                            "contact_phone": {"type": "string", "description": "联系人电话"}
                        },
                        "required": ["action"]
                    }
                }
            })
        
        return schemas
    
    def _intuition_route(self, session_id: str, task: str, messages: List[Dict], emotion: str = "neutral") -> str:
        """直觉层路由——FIX: chat 路径也保留，但 chat 路径中 LLM 也有 tools 可用。
        
        让 LLM 自己判断是否需要工具，而不是代码提前替它决定。
        关键词匹配永远有漏网之鱼，只有 LLM 自己知道它想做什么。
        
        保留 recall 模式用于回忆/总结。
        """
        task_lower = task.lower().strip()
        
        # 只有回忆/考试/总结模式 → recall（需要完整上下文）
        recall_signals = ["回忆", "总结", "复习", "考试", "回顾", "复盘"]
        if any(s in task_lower for s in recall_signals):
            return "recall"
        
        # 其他所有情况 → chat（FIX: chat 路径也传入 tools，LLM 自己判断）
        return "chat"
    
    async def _assess_security(self, session_id: str, task: str) -> Dict:
        """安全评估 —— System 1 直觉层 + System 2 LLM 兜底
        
        FIX Phase 1.1: 从"每轮必评"改为"直觉优先，可疑才评"
        
        System 1（0ms，本地规则）：
        1. 危险模式正则 → strict（高置信度）
        2. 熟悉会话（有历史且安全）→ standard（跳过评估）
        3. 简单问候/闲聊 → skip（不评估）
        4. 默认 → standard（不调用 LLM）
        
        System 2（LLM）：只有当直觉层返回 "uncertain" 时才调用
        
        Returns:
            {"safety_level": str, "suggested_mode": str, "reasoning": str, "confidence": float}
        """
        if not task:
            return {}
        
        # ===== System 1: 直觉层（0ms，纯本地规则）=====
        result = self._security_intuition(session_id, task)
        
        if result.get("source") == "skip":
            # 简单消息，不评估不缓存，直接返回默认标准模式
            logger.info(f"[GOV] 安全评估跳过 [{session_id}]: {result.get('reasoning')}")
            return result
        
        if result.get("source") == "intuition":
            # 直觉层已有高置信度判断，不调用 LLM
            logger.info(f"[GOV] 安全评估(直觉) [{session_id}]: {result.get('safety_level')} -> {result.get('suggested_mode')}")
        
        # ===== System 2: LLM 评估（仅在直觉不确定时）=====
        if not result and hasattr(self, 'auto_classifier') and self.auto_classifier:
            try:
                llm_result = await self.auto_classifier.evaluate(task)
                result = {
                    "safety_level": llm_result.safety_level,
                    "suggested_mode": llm_result.suggested_mode,
                    "reasoning": llm_result.reasoning,
                    "confidence": llm_result.confidence,
                    "source": "llm",
                }
                logger.info(f"[GOV] 安全评估(LLM) [{session_id}]: {llm_result.safety_level} -> {llm_result.suggested_mode} ({llm_result.eval_time_ms:.0f}ms)")
            except Exception as e:
                logger.warning(f"LLM 安全评估失败: {e}")
        
        # ===== PermissionMode 设置 =====
        if result and hasattr(self, 'mode_manager') and self.mode_manager:
            try:
                suggested = result.get("suggested_mode", "standard")
                current = self.mode_manager.get_mode(session_id) or "standard"
                source = result.get("source", "")
                confidence = result.get("confidence", 0)
                
                mode_priority = {"strict": 0, "standard": 1, "auto": 2, "unrestricted": 3}
                
                # 只有直觉层高置信度危险，或 LLM 明确危险才降级
                should_downgrade = (
                    mode_priority.get(suggested, 1) < mode_priority.get(current, 1)
                    and (
                        (source == "intuition" and confidence > 0.95)
                        or (source == "llm" and confidence > 0.85 and result.get("safety_level") in ("dangerous", "critical"))
                    )
                )
                
                if should_downgrade:
                    self.mode_manager.set_mode(
                        session_id, suggested,
                        reason=f"安全评估: {result.get('reasoning', '')}",
                        task_hint=task[:100],
                    )
                    result["mode_changed"] = True
                    result["old_mode"] = current
                    result["new_mode"] = suggested
                    logger.info(f"[GOV] Permission Mode 降级 [{session_id}]: {current} -> {suggested}")
                else:
                    result["mode_changed"] = False
            except Exception as e:
                logger.debug(f"设置 Permission Mode 失败: {e}")
        
        return result or {}
    
    def _security_intuition(self, session_id: str, task: str) -> Dict:
        """System 1 安全直觉——0ms 本地规则判断
        
        原则：只拦截极端危险的系统破坏命令。
        其他所有情况放行，安全由工具层的 PolicyEngine 在"动手前"检查。
        像人的反射弧：说话不检查，动手前检查。
        """
        task_lower = task.lower().strip()
        
        # 唯一规则：极端危险模式（正则匹配，高置信度）→ strict
        danger_patterns = [
            r'rm\s+-rf', r'drop\s+table', r'delete\s+from\s+\w+\s+where',
            r'format\s+[a-z]:', r'fdisk', r'mkfs',
            r'shutdown\s+-h', r'reboot', r'init\s+0',
            r'\bkill\s+-9\b', r'\bpkill\b',
            r'chmod\s+777\s+/etc', r'chown\s+-R\s+root',
            r'echo\s+.*>\s+/etc/', r'>\s+/dev/sd[a-z]',
            r'curl\s+.*\|\s*sh', r'wget\s+.*\|\s*sh',
            r'sudo\s+rm', r'rm\s+/etc',
        ]
        for pattern in danger_patterns:
            if re.search(pattern, task_lower):
                return {
                    "safety_level": "dangerous",
                    "suggested_mode": "strict",
                    "reasoning": f"检测到危险模式: {pattern}",
                    "confidence": 0.98,
                    "source": "intuition",
                }
        
        # 其他所有情况：直接放行，不返回空触发 LLM 预判断
        return {"safety_level": "safe", "suggested_mode": "standard", "source": "skip"}
    
    async def _preexecute_readonly(self, session_id: str, task: str) -> List[Dict]:
        """推测执行只读工具 —— SpeculativeExecutor 联动入口
        
        在 LLM 调用之前，分析用户输入中的只读意图，预执行工具。
        结果注入到 messages 中作为上下文，LLM 可以直接回答而不需要 tool loop。
        
        FIX v4: 系统stressed时不做推测执行——像人压力大时不会抢话查资料。
        
        Returns:
            预执行结果列表，每个元素为 {"role": "system", "content": ...}
        """
        if not task or not hasattr(self, 'speculative_executor') or not self.speculative_executor:
            return []
        
        # FIX v4: stressed时跳过推测执行，减少不必要的工具调用
        if getattr(self, '_system_mood', 'calm') == 'stressed':
            logger.debug(f"[GOV] 推测执行跳过 [{session_id}]: 系统stressed，不抢话")
            return []
        
        # FIX v4.1: 闲聊任务跳过推测执行——像人不会在闲聊时抢话查资料
        task_lower = task.lower().strip()
        # 快速判断：短问候、纯知识问题、简单情感表达 → 不需要推测执行
        is_greeting = len(task) < 20 and any(g in task_lower for g in ['你好', 'hi', 'hello', '在吗', '谢谢', '再见'])
        is_knowledge = any(s in task_lower for s in ['是什么', '什么意思', '为什么', '怎么样', '如何', '介绍一下'])
        is_short_chat = len(task) < 30 and not any(a in task_lower for a in ['查', '找', '搜索', '读', '看', '获取'])
        if is_greeting or (is_knowledge and is_short_chat):
            logger.debug(f"[GOV] 推测执行跳过 [{session_id}]: 闲聊/知识问答，不抢话")
            return []
        
        # 检测意图
        intent = self.speculative_executor.detect_intent(task)
        if not intent:
            return []
        
        # 只执行只读工具
        if intent.tool not in {"file_read", "directory_list", "web_search", "web_fetch", "memory_search", "memory_get"}:
            return []
        
        try:
            task_obj = await self.speculative_executor.execute_if_safe(intent, session_id)
            if not task_obj:
                return []
            
            # 等待结果（短超时，不阻塞主流程）
            result = await asyncio.wait_for(task_obj, timeout=self._speculative_timeout)
            
            if result and isinstance(result, dict):
                status = result.get("status")
                content = result.get("content") or result.get("stdout") or result.get("output", "")
                
                if status == "completed" and content:
                    # 将结果格式化为上下文注入
                    tool_name_map = {
                        "file_read": "📄 文件内容",
                        "directory_list": "📂 目录列表",
                        "web_search": "🔍 搜索结果",
                        "web_fetch": "🌐 网页内容",
                        "memory_search": "🧠 相关记忆",
                        "memory_get": "🧠 记忆详情",
                    }
                    label = tool_name_map.get(intent.tool, intent.tool)
                    
                    # 截断过长内容
                    max_len = 2000
                    if len(str(content)) > max_len:
                        content = str(content)[:max_len] + f"\n... (共 {len(str(content))} 字符，已截断)"
                    
                    injection = {
                        "role": "system",
                        "content": f"【预执行结果 — {label}】\n\n{content}\n\n---\n上述内容已自动获取，你可以在回复中直接引用。"
                    }
                    
                    logger.info(f"[GOV] 推测执行命中 [{session_id}]: {intent.tool} -> {len(str(content))} chars")
                    return [injection]
        except asyncio.TimeoutError:
            logger.debug(f"[GOV] 推测执行超时 [{session_id}]: {intent.tool}")
        except Exception as e:
            logger.debug(f"[GOV] 推测执行失败 [{session_id}]: {e}")
        
        return []
    
    async def _on_memory_injected(self, session_id: str, data: Dict):
        """记忆注入完成后的处理——对话核心
        
        1. 组装 LLM messages（system prompt + 对话历史）
        2. 判断 needs_plan()：AutoClassifier.complexity_score → 简单 vs 复杂
        3. 判断 needs_tool_calling()：是否需要工具操作
        4. 简单问答 → 流式 LLM 调用
        5. 工具操作 → ReAct Tool Loop
        6. 复杂任务 → Plan → Execute
        """
        state = await self.state_store.load(session_id)
        messages = await self.state_store.get_messages(session_id, limit=50)
        injected_context = data.get("injected_context", "")
        
        # 判断是否是第一次对话：
        # 不仅看当前 session 消息数，还要检查该用户是否有历史 session 或记忆
        user_id = state.get("user_id", "")
        has_history_sessions = False
        if user_id:
            try:
                all_sessions = await self.state_store.list_sessions(user_id, limit=10)
                # 排除当前 session，看是否还有其他历史会话
                has_history_sessions = any(s.get("session_id") != session_id for s in all_sessions)
            except Exception:
                pass
        
        # 真正的新用户：当前 session 消息 ≤1，且没有历史 session，且没有注入记忆
        is_first_time = (len(messages) <= 1) and (not has_history_sessions) and (not injected_context.strip())
        
        # === 用户身份自动提取 ===
        # 从最近一条用户消息中提取自称身份，更新用户画像
        user_name = None
        if user_id and messages:
            last_user_msg = None
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_user_msg = m.get("content", "")
                    break
            if last_user_msg:
                user_name = self._extract_user_name(last_user_msg)
                if user_name:
                    self.user_profile_store.set_name(user_id, user_name)
                    logger.info(f"[GOV] 从消息中提取用户名字: {user_name} [{user_id}]")
        
        # Compaction：如果对话过长，压缩早期消息为摘要
        message_summary = state.get("message_summary", "")
        if len(messages) > 15 and not message_summary and session_id not in self._compacting_sessions:
            # FIX: compaction 去重 —— 防止 >15 消息时每消息触发一次
            self._compacting_sessions.add(session_id)
            # 异步生成摘要（不阻塞主流程）
            asyncio.create_task(self._compact_messages(session_id, messages))
        
        # === Phase 2.1+2.2: 安全评估 —— System 1 直觉层前置 ===
        # FIX v3: 安全评估从"后台异步"改为"同步直觉+异步确认"。
        # 像人的反射弧：看到危险立即缩手（毫秒级），不需要等大脑想清楚。
        # 只有直觉不确定时，才在后台走 LLM 确认。
        
        task_text = state.get("task", "")
        
        # Step 1: 同步直觉层（0ms）—— 高置信度危险立即拦截
        intuition_result = self._security_intuition(session_id, task_text)
        
        if intuition_result.get("source") == "intuition" and intuition_result.get("safety_level") in ("dangerous", "critical"):
            # 直觉层检测到高置信度危险 → 立即拒绝，不走任何后续流程
            refusal_msg = (
                f"🛡️ 安全拦截\n\n"
                f"原因：{intuition_result.get('reasoning', '检测到高风险操作模式')}\n\n"
                f"该请求已被自动拦截。如涉及误判，请联系系统管理员。"
            )
            logger.warning(f"[GOV] 安全拦截(直觉) [{session_id}]: {intuition_result.get('reasoning')}")
            await self._simulate_stream(session_id, refusal_msg)
            await self.state_store.append_message(session_id, "assistant", refusal_msg)
            await self.bus.publish(f"governance.response.{session_id}", json.dumps({
                "session_id": session_id,
                "type": "chat.completed",
                "content": refusal_msg,
            }).encode())
            return  # ← 立即返回，不走 Plan/Tool Loop/LLM
        
        # Phase 1 清除: 删除 LLM 安全预判断
        # 原因：1) 阻塞主流程 1-10s；2) 成本/收益倒挂；3) 工具层 PolicyEngine 已兜底
        # 安全从"说话层"移到"动手层"——PolicyEngine 在工具执行前做 0ms 本地检查

        
        if intuition_result.get("source") == "skip":
            # 简单问候，跳过安全评估
            logger.info(f"[GOV] 安全评估跳过 [{session_id}]: {intuition_result.get('reasoning')}")
            security_assessment = intuition_result
        else:
            # 直觉层不确定 → 后台走 LLM 评估（不阻塞主流程）
            async def _security_background():
                try:
                    return await self._assess_security(session_id, task_text)
                except Exception as e:
                    logger.warning(f"[GOV] 后台安全评估失败 [{session_id}]: {e}")
                    return {}
            security_task = asyncio.create_task(_security_background())
            try:
                security_assessment = await asyncio.wait_for(security_task, timeout=self._security_timeout)
            except asyncio.TimeoutError:
                security_assessment = {"safety_level": "safe", "suggested_mode": "standard", "source": "timeout_fallback"}
                logger.debug(f"[GOV] 安全评估快速回退 [{session_id}]: 使用默认 safe/standard")
        
        # 获取当前 Permission Mode
        current_permission_mode = ""
        if hasattr(self, 'mode_manager') and self.mode_manager:
            current_permission_mode = self.mode_manager.get_mode(session_id) or "standard"
        
        # 获取可用工具
        available_tools = await self._get_available_tools(session_id)
        
        # FIX: 根据前端用户选择的工具开关过滤可用工具
        user_tools = state.get("user_tools")
        if user_tools and isinstance(user_tools, dict):
            disabled_tools = set()
            if not user_tools.get("web_search"):
                disabled_tools.update({"web_search", "web_fetch", "browser_navigate", "browser_click"})
            if not user_tools.get("file_ops"):
                disabled_tools.update({"shell", "file_read", "file_write", "directory_list"})
            if disabled_tools:
                original_count = len(available_tools)
                available_tools = [t for t in available_tools if t.get("function", {}).get("name") not in disabled_tools]
                logger.info(f"[GOV] 用户工具过滤 [{session_id}]: {original_count} → {len(available_tools)} (禁用: {disabled_tools})")
        
        # Skills 路由
        skill_prompt = ""
        activated_skill_names = []
        if self.skill_manager:
            skills = await self.skill_manager.route(task_text)
            if skills:
                activated_skill_names = [s.name for s in skills]
                skill_prompts = []
                skill_tool_names = set()
                for skill in skills:
                    skill_prompts.append(f"## Skill: {skill.name}\n{skill.prompt}")
                    skill_tool_names.update(skill.tools)
                skill_prompt = "\n\n".join(skill_prompts)
                
                if skill_tool_names:
                    # FIX: 任务敏感工具排序 —— 将 skill 相关工具置顶
                    # 这样 LLM 更容易看到并选择专用工具，而不是 fallback 到 shell
                    skill_tools = get_tool_schemas(filter_names=list(skill_tool_names))
                    existing_names = {t["function"]["name"] for t in available_tools}
                    
                    # 先添加 skill 引入的新工具
                    for t in skill_tools:
                        if t["function"]["name"] not in existing_names:
                            available_tools.append(t)
                    
                    # 重新排序：skill 相关工具 → 其他工具
                    priority_names = {t["function"]["name"] for t in skill_tools}
                    priority_tools = [t for t in available_tools if t["function"]["name"] in priority_names]
                    other_tools = [t for t in available_tools if t["function"]["name"] not in priority_names]
                    available_tools = priority_tools + other_tools
                
                logger.info(f"[GOV] 激活 Skills: {activated_skill_names} [{session_id}]")
        
        # === 并行召回：程序记忆 + 文件记忆（独立的 IO 操作）===
        recall_tasks = []
        
        # 程序记忆规则召回
        async def _recall_procedural():
            if self.procedural_store:
                rules = await self.procedural_store.find_relevant(
                    state.get("task", ""), 
                    limit=self.procedural_injector.max_rules if self.procedural_injector else 3
                )
                await self.state_store.update(session_id, {
                    "injected_rules": [(r.id, r.action_rule) for r in rules]
                })
                return rules
            return []
        recall_tasks.append(_recall_procedural())
        
        # 文件记忆召回
        async def _recall_file():
            if hasattr(self, 'file_memory') and self.file_memory and state.get("task"):
                try:
                    return await self.file_memory.recall(
                        task_query=state.get("task", ""),
                        top_k=3,
                        memory_types=["projects", "experiences", "skills"],
                    )
                except Exception as e:
                    logger.debug(f"File Memory 召回失败: {e}")
            return []
        recall_tasks.append(_recall_file())
        
        # 并行执行召回
        recall_results = await asyncio.gather(*recall_tasks, return_exceptions=True)
        
        injected_rules = recall_results[0] if not isinstance(recall_results[0], Exception) else []
        file_memories = recall_results[1] if len(recall_results) > 1 and not isinstance(recall_results[1], Exception) else []
        file_memory_context = self.file_memory.format_for_injection(file_memories) if file_memories else ""
        
        # === Tent OS 2.0 大脑核心注入 ===
        brain_prompt_segments = []
        
        # 1. 人格模式检测与压缩
        if self.brain_v2_enabled and self.multi_persona:
            user_query = state.get("task", "")
            detected_mode = self.multi_persona.detect_mode(user_query)
            self.soul.dimensions = self.multi_persona.get_current_dimensions()
        
        # 2. 用户模型构建 + 人格压缩（串行，因为后者依赖前者，但都很轻量）
        # FIX v4: 用户模型缓存——了解一个人是渐进的，不是每次见面都重新分析
        user_model = None
        if self.brain_v2_enabled and self.cognitive_graph:
            user_id = state.get("user_id", "")
            if user_id:
                # 获取当前消息数，用于判断是否需要重建
                current_msgs = len([m for m in messages if m.get("role") == "user"])
                cached = self._user_model_cache.get(user_id)
                if cached and cached[0] == current_msgs:
                    # 消息数没变，复用缓存
                    user_model = cached[1]
                    logger.debug(f"[GOV] 用户模型缓存命中 [{user_id}]: {current_msgs} 条消息")
                else:
                    # 重建用户模型
                    builder = UserModelBuilder(self.cognitive_graph)
                    user_model = builder.build(user_id)
                    self._user_model_cache[user_id] = (current_msgs, user_model)
                    logger.debug(f"[GOV] 用户模型重建 [{user_id}]: {current_msgs} 条消息")
        
        if self.brain_v2_enabled and self.persona_compressor:
            persona_text = self.persona_compressor.compress(
                context={"task": state.get("task", "")},
                user_model=user_model,
                message_count=len(messages),
                max_tokens=300,
            )
            if persona_text:
                brain_prompt_segments.append(persona_text)
        
        # FIX: 情绪实时注入——从 state 中获取实时检测到的情绪
        emotion_state = state.get("emotion", {})
        current_emotion = emotion_state.get("emotion", "neutral") if isinstance(emotion_state, dict) else "neutral"
        emotion_intensity = emotion_state.get("intensity", 0.0) if isinstance(emotion_state, dict) else 0.0
        
        # 3. 工作记忆更新与注入
        working_memory_text = ""
        if self.brain_v2_enabled and self.working_memory:
            user_query = state.get("task", "")
            profile_nodes = []
            # FIX: 尝试从用户模型构建画像节点
            if user_model and self.cognitive_graph:
                try:
                    from tent_os.memory.graph import MemoryNode
                    for key, value in user_model.items():
                        if value and isinstance(value, (str, int, float)):
                            profile_nodes.append(MemoryNode(
                                uri=f"profile://{user_id}/{key}",
                                content=f"{key}: {value}",
                                node_type="user_profile",
                                confidence=0.8,
                            ))
                except Exception as e:
                    logger.debug(f"用户画像节点转换失败: {e}")
            
            try:
                self.working_memory.update(
                    user_query=user_query,
                    user_profile_nodes=profile_nodes,
                    emotion_intensity=emotion_intensity,
                )
                working_memory_text = self.working_memory.get_context_text(max_chars=500)
                if working_memory_text:
                    brain_prompt_segments.append(working_memory_text)
                    logger.info(f"[GOV] WorkingMemory 注入 [{session_id}]: {len(working_memory_text)} chars")
            except Exception as e:
                logger.warning(f"[GOV] WorkingMemory 更新失败 [{session_id}]: {e}")
        
        # ========== FIX Phase 5: 结构化情绪深度注入 ==========
        # 从 emotion_service 读取视觉摘要，从 state 读取 TTS 状态
        tts_enabled = state.get("tts_enabled", False)
        
        # 计算动态生成参数（temperature / max_tokens）
        dynamic_params = {"temperature": 0.3, "max_tokens": 8000}
        visual_summary = ""
        fused_emotion = None
        try:
            from tent_os.services.emotion_service import EmotionService
            emotion_svc = EmotionService()
            dynamic_params = emotion_svc.get_dynamic_generation_params(user_id, current_emotion)
            visual_summary = emotion_svc.get_visual_summary(user_id)
            # Phase 1: 多模态情绪融合
            fused_emotion = emotion_svc.get_fused_emotion(
                user_id, text_emotion=current_emotion, text_intensity=emotion_intensity, session_id=session_id
            )
            if fused_emotion:
                await self.state_store.update(session_id, {"_fused_emotion": fused_emotion})
                logger.info(f"[GOV] 情绪融合 [{session_id}]: primary={fused_emotion.get('primary')}, trend={fused_emotion.get('trend')}, authenticity={fused_emotion.get('authenticity'):.2f}, mixed={fused_emotion.get('mixed')}")
                # 广播融合情绪给前端
                try:
                    await self.bus.publish_raw("emotion.fused", json.dumps({
                        "session_id": session_id,
                        "user_id": user_id,
                        "primary": fused_emotion.get("primary"),
                        "intensity": fused_emotion.get("intensity"),
                        "valence": fused_emotion.get("valence"),
                        "arousal": fused_emotion.get("arousal"),
                        "mixed": fused_emotion.get("mixed"),
                        "trend": fused_emotion.get("trend"),
                        "authenticity": fused_emotion.get("authenticity"),
                    }).encode())
                except Exception as e:
                    logger.warning(f"[GOV] 情绪融合广播失败 [{session_id}]: {e}")
                # Phase 4: 记录到主动行为引擎
                if self.proactive_engine:
                    self.proactive_engine.record_user_emotion(session_id, user_id, fused_emotion)
            # 保存到 state，供后续 LLM 调用读取
            await self.state_store.update(session_id, {"_dynamic_gen_params": dynamic_params})
            logger.info(f"[GOV] 动态生成参数 [{session_id}]: temp={dynamic_params['temperature']}, max_tokens={dynamic_params['max_tokens']}, persona={emotion_svc.get_persona(user_id)}, ai_emotion={emotion_svc.get_emotion(user_id)}")
        except Exception as e:
            logger.debug(f"[GOV] 动态生成参数计算失败 [{session_id}]: {e}")
        
        # 结构化情绪状态注入
        try:
            from tent_os.services.emotion_service import EmotionService
            emotion_svc = EmotionService()
            structured = emotion_svc.get_structured_emotion_state(user_id, current_emotion)
            
            expr = structured.get("expression", {})
            # Phase 1: 使用融合情绪替代单一文本情绪
            fused_primary = fused_emotion.get("primary", structured['user_emotion']) if fused_emotion else structured['user_emotion']
            fused_intensity = fused_emotion.get("intensity", 0.0) if fused_emotion else 0.0
            
            structured_prompt = f"""## 你的当前状态
[AI情绪]: {structured['ai_emotion']}
[人格模式]: {structured['persona']}
[用户情绪]: {fused_primary} (强度{fused_intensity:.1f})"""
            
            if visual_summary:
                structured_prompt += f"\n[视觉观察]: {visual_summary}"
            
            # Phase 1: 融合情绪信息注入
            if fused_emotion:
                mixed = fused_emotion.get("mixed", {})
                if mixed:
                    mixed_str = ", ".join([f"{k}({v:.1f})" for k, v in mixed.items()])
                    structured_prompt += f"\n[用户混合情绪]: {mixed_str}"
                structured_prompt += f"\n[情绪趋势]: {fused_emotion.get('trend', 'stable')}"
                auth = fused_emotion.get("authenticity", 0.5)
                if auth < 0.5:
                    structured_prompt += f"\n[⚠️ 注意]: 用户情绪真实性较低({auth:.1f})，可能在强撑或掩饰真实感受。请更温柔、更耐心地沟通。"
            
            structured_prompt += f"""

### 表达要求（必须遵守）
- 输出长度: {expr.get('length', '适中')}
- Emoji使用: {expr.get('emoji', '适度')}
- 主动行为: {expr.get('proactive', '自然回应')}"""
            
            # TTS 开启时的语音感知指令
            if tts_enabled:
                structured_prompt += """

### 语音输出模式（你的回复将被朗读）
- 避免 markdown、代码块、列表符号
- 使用口语化短句，每句不超过20字
- 数字读作中文（如 123 → 一百二十三）
- 适当使用"嗯""啊""呢"等语气词和停顿
- 不要用 emoji（朗读会尴尬）"""
            
            # 情绪打断检查
            if emotion_svc.get_emotion_interrupt_flag(user_id):
                structured_prompt += "\n\n### ⚠️ 情绪打断\n用户情绪非常激动，请立即停止当前思路，先真诚道歉并询问如何帮助。优先安抚情绪，再解决问题。"
                # 在 AI 回复后检查是否包含道歉词，包含则清除打断标志
                # 这个逻辑在 _handle_tool_loop 的回复后处理
            
            brain_prompt_segments.append(structured_prompt)
            logger.debug(f"[GOV] 结构化情绪注入 [{session_id}]: {len(structured_prompt)} chars")
        except Exception as e:
            logger.debug(f"[GOV] 结构化情绪注入失败 [{session_id}]: {e}")
            # fallback: 原有的简单注入
            if current_emotion != "neutral":
                emotion_map = {
                    "angry": "用户当前情绪愤怒/不满，请格外谨慎、共情，优先安抚情绪再解决问题",
                    "urgent": "用户当前很着急，请优先给出最直接、最快速的解决方案，减少解释性内容",
                    "happy": "用户当前心情很好，可以适度幽默，保持轻松愉快的交流氛围",
                    "sad": "用户当前情绪低落/沮丧，请给予温暖、鼓励和支持",
                    "confused": "用户当前感到困惑，请用更清晰、结构化的方式解释",
                    "frustrated": "用户当前感到挫败，请给出确定性的解决方案，避免模糊回答",
                }
                emotion_hint = emotion_map.get(current_emotion, "")
                if emotion_hint:
                    brain_prompt_segments.append(f"## 实时情绪感知\n\n{emotion_hint}")
            
            try:
                from tent_os.services.emotion_service import EmotionService
                emotion_svc = EmotionService()
                ai_emotion_prompt = emotion_svc.get_prompt_addon(user_id)
                if ai_emotion_prompt:
                    brain_prompt_segments.append(f"## AI角色状态\n\n{ai_emotion_prompt}")
            except Exception:
                pass
        
        # 4. 推理链结果 —— FIX: 不再要求图谱非空才触发。空图谱时 ReasoningChain 可以基于当前任务进行基础推理。
        if self.brain_v2_enabled and self.reasoning_chain and state.get("task", ""):
            task = state.get("task", "")
            try:
                reasoning_result = self.reasoning_chain.answer_complex_question(task)
                if reasoning_result.get("confidence", 0) > 0.3:
                    brain_prompt_segments.append(f"## 推理结果\n{reasoning_result['answer']}")
                    logger.info(f"[GOV] ReasoningChain 触发 [{session_id}]: confidence={reasoning_result.get('confidence', 0):.2f}")
                else:
                    logger.debug(f"[GOV] ReasoningChain 置信度不足 [{session_id}]: {reasoning_result.get('confidence', 0):.2f}")
            except Exception as e:
                logger.warning(f"[GOV] ReasoningChain 执行失败 [{session_id}]: {e}")
        
        # 合并大脑 prompt 到注入上下文
        brain_context = "\n\n".join(brain_prompt_segments)
        
        # 构建注入上下文（记忆 + 摘要 + 大脑核心 + 用户画像 + 文件记忆）
        combined_context = injected_context
        if message_summary:
            combined_context = f"【对话摘要（{len(messages)}轮对话的压缩）】\n{message_summary}\n\n{injected_context}"
        
        if file_memory_context:
            combined_context = f"{file_memory_context}\n\n{combined_context}"
        
        # 注入用户画像（名字 + 风格偏好）
        if user_id:
            profile_text = self.user_profile_store.get_profile_for_prompt(user_id)
            if profile_text:
                combined_context = f"{profile_text}\n\n{combined_context}"
        
        if brain_context:
            combined_context = f"{brain_context}\n\n{combined_context}"
        
        # 注入文件系统边界信息（让 LLM 知道自己能访问多大范围）
        boundary_text = ""
        if self.tool_executor and self.tool_executor.local:
            local = self.tool_executor.local
            mode = getattr(local, "workspace_mode", "unrestricted")
            ws_path = getattr(local, "workspace_path", None)
            if mode == "full":
                boundary_text = "## 当前文件系统边界\n\n模式：full（完全权限）\n你可以访问这台电脑上的任何文件和目录，没有路径限制。"
            elif mode in ("workspace", "readonly") and ws_path:
                write_flag = "可读写" if mode == "workspace" else "只读"
                boundary_text = f"## 当前文件系统边界\n\n模式：{mode}（{write_flag}）\n工作目录：{ws_path}\n你只能访问 {ws_path} 目录内的文件。相对路径（如 foo.txt）会自动解析为 {ws_path}/foo.txt。\n但你可以调用系统中的任何工具（python3, git, npm 等），工具调用不受 workspace 限制。"
            if boundary_text:
                combined_context = f"{boundary_text}\n\n{combined_context}"
        
        # FIX: 自我状态监控——构建系统状态文本
        self_state_text = ""
        if self.brain_v2_enabled:
            bg_tick = getattr(self, '_background_tick', 0)
            system_mood = getattr(self, '_system_mood', 'calm')
            recent_msgs = sum(getattr(self, '_recent_message_count', {}).values())
            self_state_text = f"【Tent OS 自我状态】当前运行稳定 | 背景意识 tick #{bg_tick} | 系统心情: {system_mood} | 近期处理消息: {recent_msgs}"
        
        # 使用文件驱动的 system prompt 生成器
        system_text = build_system_prompt(
            injected_context=combined_context,
            procedural_rules=await self.procedural_injector.render_rules(state.get("task", "")) if self.procedural_injector else "",
            is_first_time=is_first_time,
            available_tools=available_tools,
            self_state=self_state_text,
            meta_cognition=self.brain_v2_enabled,  # FIX: 启用元认知提示
            permission_mode=current_permission_mode,
            security_assessment=security_assessment,
        )
        
        # 追加 Skill prompt
        if skill_prompt:
            system_text += skill_prompt
        
        # FIX: 深度思考模式——用户明确要求时，追加深度分析指令
        if state.get("deep_thinking"):
            system_text += "\n\n【深度思考模式已开启】\n用户要求你对这个问题进行深度思考。请：\n1. 多角度分析问题本质\n2. 列出所有可能的解决方案并比较优劣\n3. 考虑潜在风险和边界情况\n4. 给出经过充分推理后的结论\n5. 在结论前展示你的思考过程（使用 <thinking> 标签包裹）\n"
            logger.info(f"[GOV] 深度思考模式 [{session_id}]")
        
        # FIX Phase 6: 真正的 Compaction —— 用摘要替换早期消息
        # 
        # FIX v4: 阈值从 8 条提高到 100 条。50 轮对话在人类大脑里根本不需要压缩。
        # LLM 的 128K 上下文窗口可以轻松容纳 100 轮对话（约 20-40KB）。
        # 只有在超过 100 轮时才压缩，避免丢失关键信息（如考试指令、修正信息）。
        #
        # 另外，如果当前是"recall"模式（考试/总结/回顾），完全跳过压缩，
        # 保留完整上下文——人类在回忆时不会把前面的内容"压成摘要"。
        compacted_messages = messages
        route = state.get("_intuition_route", "uncertain")
        
        if route == "recall":
            # 回忆模式：不压缩，保留完整上下文
            logger.info(f"[GOV] 回忆模式，跳过消息压缩 [{session_id}]: {len(messages)} 条完整保留")
        elif message_summary and len(messages) > 100:
            recent_messages = messages[-20:]  # 保留最近 20 条原始消息（比之前更多）
            summary_msg = {
                "role": "system",
                "content": (
                    f"【前文摘要（{len(messages) - 20} 轮对话的压缩）】\n\n"
                    f"{message_summary}\n\n"
                    f"[以上是你和用户之前的对话摘要。请自然地基于摘要中的上下文继续交流。"
                    f"如果用户提到'刚才'、'之前'、'上一步'等，请参考摘要内容。]"
                ),
            }
            compacted_messages = [summary_msg] + recent_messages
            logger.info(f"[GOV] 消息压缩 [{session_id}]: {len(messages)} -> {len(compacted_messages)} 条（超过100轮阈值）")
        else:
            # 100 轮以内不压缩，LLM 上下文窗口足够
            logger.debug(f"[GOV] 消息未压缩 [{session_id}]: {len(messages)} 条（未超阈值）")
        
        # Phase 1.3: 5层上下文压缩管道 —— 替代粗截断
        if hasattr(self, 'compression_pipeline') and self.compression_pipeline:
            try:
                trimmed_messages = await self.compression_pipeline.compress(
                    compacted_messages,
                    max_tokens=6000,
                    session_id=session_id,
                    working_memory_text=working_memory_text,
                )
                original_tokens = self.compression_pipeline.counter.count_messages(compacted_messages)
                compressed_tokens = self.compression_pipeline.counter.count_messages(trimmed_messages)
                # FIX v4: Telemetry降频——只在显著压缩时记录
                if original_tokens != compressed_tokens and self.telemetry:
                    compression_ratio = (original_tokens - compressed_tokens) / max(original_tokens, 1)
                    if compression_ratio > 0.2:  # 只有压缩率>20%才记录
                        self.telemetry.record_compression(
                            session_id, original_tokens, compressed_tokens, "pipeline"
                        )
            except Exception as e:
                logger.warning(f"压缩管道失败，回退到粗截断: {e}")
                trimmed_messages = self._trim_messages_by_tokens(compacted_messages)
        else:
            # 回退：原有粗截断
            trimmed_messages = self._trim_messages_by_tokens(compacted_messages)
        
        # 组装 LLM messages 格式（支持多模态 vision）
        llm_messages = [{"role": "system", "content": system_text}]
        for m in trimmed_messages:
            images = m.get("images")
            if images:
                # Vision 格式: content 为列表 [text, image_url]
                content_parts = [{"type": "text", "text": m["content"]}]
                for img_b64 in images:
                    if not img_b64.startswith("data:"):
                        img_b64 = f"data:image/jpeg;base64,{img_b64}"
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": img_b64}
                    })
                llm_messages.append({"role": m["role"], "content": content_parts})
            else:
                llm_messages.append({"role": m["role"], "content": m["content"]})
        
        # === Phase 3.3: 推测执行 —— 预执行只读工具，结果注入上下文 ===
        speculative_injections = await self._preexecute_readonly(session_id, state.get("task", ""))
        if speculative_injections:
            # 将推测结果插入到 system prompt 之后、用户消息之前
            llm_messages = [llm_messages[0]] + speculative_injections + llm_messages[1:]
            logger.info(f"[GOV] 推测执行结果已注入 [{session_id}]: {len(speculative_injections)} 条")
        
        # Phase 5: 内心独白生成（不阻塞主 LLM 调用）
        if self.inner_monologue:
            asyncio.create_task(self.inner_monologue.generate(session_id, llm_messages, state, self.bus))
        
        # 判断走哪个模式 —— FIX v3.2: 直觉层路由（像人类凭感觉判断）
        last_user_msg = state.get("task", "")
        # FIX: 使用 available_tools 而非 state 中可能为空的 tools，确保 LLM 能看到所有执行器
        plan_tools = available_tools
        
        # 获取当前情绪状态，传给直觉层
        emotion_state = state.get("emotion", {})
        current_emotion = emotion_state.get("emotion", "neutral") if isinstance(emotion_state, dict) else "neutral"
        
        # === 直觉层：像人类一样快速判断 ===
        route = self._intuition_route(session_id, last_user_msg, llm_messages, emotion=current_emotion)
        # FIX: 保存路由结果到 state，供消息压缩逻辑读取
        state["_intuition_route"] = route
        
        if route == "chat":
            # FIX: 所有消息都走 Tool Loop，让 LLM 自己判断是否需要工具。
            # _handle_chat_reply 已废弃——它让 LLM 在"聊天模式"下倾向于不调用工具，导致假干活。
            # Tool Loop 在没有 tool_calls 时会直接 break，和 chat 路径一样快。
            logger.info(f"[GOV] 直觉层路由 → Tool Loop (chat) [{session_id}]: {last_user_msg[:50]}")
            await self._handle_tool_loop(session_id, llm_messages, silent=False, max_iterations=10, task_type="chat")
        elif route == "recall":
            # 回忆/考试/总结模式——不走chat快速通道，需要完整上下文
            # 让 LLM 自己判断是否需要工具，不强制走 Plan
            logger.info(f"[GOV] 直觉层路由 → 回忆模式 [{session_id}]: {last_user_msg[:50]}")
            await self._handle_tool_loop(session_id, llm_messages, silent=False, task_type="recall")
        elif await self.executor.needs_plan(last_user_msg, plan_tools, classifier=self.auto_classifier):
            # FIX: 先检查复杂度，再进入 Tool Loop。中等复杂度任务用 Plan-Execute 更高效。
            logger.info(f"[GOV] 复杂度评估 → Plan-Execute [{session_id}]: {last_user_msg[:50]}")
            await self._handle_complex_task(session_id, last_user_msg, plan_tools, llm_messages)
        elif route == "uncertain":
            # 不确定 → Tool Loop（让 LLM 自己判断是否需要工具）
            logger.info(f"[GOV] 直觉层不确定 → Tool Loop [{session_id}]: {last_user_msg[:50]}")
            
            # 根据激活的 skill 决定执行模式
            is_silent = False
            task_type = "chat"
            
            if activated_skill_names:
                if "presentation" in activated_skill_names:
                    is_silent = True
                    task_type = "PPT 生成"
                elif "document-skills" in activated_skill_names:
                    is_silent = True
                    task_type = "文档生成"
                elif "business-writing" in activated_skill_names:
                    is_silent = True
                    task_type = "商务写作"
            
            # FIX Phase 3: 使用自适应 max_iterations
            if hasattr(self, '_adaptive'):
                max_iter = self._adaptive.get_max_iterations(task_type)
            else:
                max_iter = 100 if is_silent else 50  # FIX: 支持长任务，大幅提高迭代上限
            
            # FIX Phase 6: stressed 模式下略微收敛迭代上限（但不阻断自主执行）
            if getattr(self, '_system_mood', 'calm') == 'stressed':
                original_max = max_iter
                max_iter = min(max_iter, 30)  # FIX: 从5提高到30，stressed也不阻断
                if original_max != max_iter:
                    logger.info(f"[GOV] Stressed 模式收敛 [{session_id}]: max_iter {original_max} → {max_iter}")
            
            # 任务开始时给用户确认回复
            if is_silent and activated_skill_names:
                confirm_msg = self._build_task_confirm_message(activated_skill_names[0], state.get("task", ""))
                await self._simulate_stream(session_id, confirm_msg)
            
            await self._handle_tool_loop(
                session_id, llm_messages,
                silent=is_silent, max_iterations=max_iter, task_type=task_type
            )
        else:
            # 兜底：不确定 → Tool Loop
            logger.info(f"[GOV] 直觉层兜底 → Tool Loop [{session_id}]: {last_user_msg[:50]}")
            await self._handle_tool_loop(session_id, llm_messages, silent=False, max_iterations=50, task_type="chat")
        
        # === FIX: 会话上下文快照 —— 供 Control UI 实时展示 ===
        # 在对话处理完成后，将关键状态写入 state_store，API 端点可读取
        try:
            ui_context = {
                "permission_mode": current_permission_mode,
                "security_assessment": {
                    "safety_level": security_assessment.get("safety_level", "unknown"),
                    "reasoning": security_assessment.get("reasoning", "")[:100],
                    "mode_changed": security_assessment.get("mode_changed", False),
                } if security_assessment else None,
                "activated_skills": activated_skill_names,
                "available_tools_count": len(available_tools) if available_tools else 0,
                "file_memories_recalled": len(file_memories) if file_memories else 0,
                "procedural_rules_injected": len(injected_rules) if injected_rules else 0,
                "brain_v2_enabled": self.brain_v2_enabled,
                "timestamp": time.time(),
            }
            
            # 补充 LLM 调用统计（如果 Telemetry 可用）
            if hasattr(self, 'telemetry') and self.telemetry:
                try:
                    session_report = self.telemetry.get_report(session_id)
                    ui_context["llm_calls"] = session_report.get("llm_calls", 0)
                    ui_context["total_tokens"] = session_report.get("total_tokens", 0)
                    ui_context["avg_latency_ms"] = session_report.get("avg_latency_ms", 0)
                except Exception:
                    pass
            
            await self.state_store.update(session_id, {"ui_context": ui_context})
            logger.debug(f"[GOV] UI 上下文已更新 [{session_id}]: mode={current_permission_mode}, skills={activated_skill_names}")
        except Exception as e:
            logger.debug(f"[GOV] UI 上下文更新失败: {e}")
    
    def _build_task_confirm_message(self, skill_name: str, task: str) -> str:
        """构建任务开始时的确认消息
        
        告诉用户：能不能干、要干多久、怎么干、输出到哪里
        """
        if skill_name == "presentation":
            return (
                f"好的，我来为您生成演示文稿。\n\n"
                f"📋 任务：根据提供的内容生成 PPT\n"
                f"⏱️ 预计时间：30-60 秒\n"
                f"📤 输出位置：桌面（.html 文件，浏览器直接打开）\n"
                f"🔄 执行步骤：读取内容 → 分析结构 → 设计故事线 → 生成页面 → 渲染输出\n\n"
                f"开始执行...\n"
            )
        elif skill_name == "document-skills":
            return (
                f"好的，我来为您处理文档任务。\n\n"
                f"📋 任务：{task[:40]}...\n"
                f"⏱️ 预计时间：20-40 秒\n"
                f"🔄 开始执行...\n"
            )
        elif skill_name == "business-writing":
            return (
                f"好的，我来为您撰写商务文档。\n\n"
                f"📋 任务：{task[:40]}...\n"
                f"⏱️ 预计时间：20-40 秒\n"
                f"🔄 开始执行...\n"
            )
        else:
            return f"好的，开始执行 {skill_name} 任务...\n"
    
    def _build_progress_message(self, tool_name: str, step: int, task_type: str, arguments: Dict) -> str:
        """构建工具执行进度消息
        
        返回空字符串表示不发送（减少噪音）
        """
        # 关键步骤才发消息
        if tool_name == "file_read":
            path = arguments.get("path", "")
            filename = path.split("/")[-1] if path else "文件"
            return f"📖 正在读取 {filename}..."
        elif tool_name == "directory_list":
            return f"📂 正在浏览目录..."
        elif tool_name == "render_ppt":
            return f"🎨 正在渲染幻灯片..."
        elif tool_name == "file_write":
            path = arguments.get("path", "")
            filename = path.split("/")[-1] if path else "文件"
            return f"💾 正在保存 {filename}..."
        elif tool_name == "shell":
            cmd = arguments.get("command", "")
            if "python" in cmd:
                return f"🐍 正在执行 Python 脚本..."
            # FIX: 显示具体命令前 40 字符，让用户知道 AI 在做什么
            cmd_display = cmd[:40] + "..." if len(cmd) > 40 else cmd
            return f"🔧 正在执行: {cmd_display}"
        elif tool_name == "web_search":
            return f"🔍 正在搜索网络信息..."
        elif tool_name == "web_fetch":
            return f"🌐 正在抓取网页内容..."
        
        # 每 5 步发一次通用进度
        if step % 5 == 0:
            return f"⏳ 正在处理中...（已执行 {step} 步）"
        
        return None
    
    async def _handle_chat_reply(self, session_id: str, messages: List[Dict]):
        """处理简单问答——流式输出到前端
        
        支持 reasoning + content 分离输出：
        - reasoning chunk → governance.stream.reasoning.{session_id}
        - content chunk → governance.stream.{session_id}
        """
        full_response = ""
        reasoning_text = ""
        
        # Phase 3.3: Speculative Executor —— 流式输出中检测只读工具意图
        _speculative_buffer = ""
        
        # P0-4 FIX: reasoning + content 批量发送缓冲
        _reasoning_buffer = ""
        _reasoning_last_send = time.time()
        _REASONING_BATCH_SIZE = 50
        _REASONING_BATCH_TIMEOUT = 0.8
        
        # FIX: content 轻量 batching，减少 WebSocket 消息量
        _content_buffer = ""
        _content_last_send = time.time()
        _CONTENT_BATCH_SIZE = 10
        _CONTENT_BATCH_TIMEOUT = 0.03
        
        def on_chunk(chunk: str, chunk_type: str = "content"):
            nonlocal full_response, reasoning_text, _speculative_buffer
            nonlocal _reasoning_buffer, _reasoning_last_send
            nonlocal _content_buffer, _content_last_send
            # FIX: 包装 publish 调用，捕获异常避免被 create_task 吞掉
            async def _safe_publish(subject: str, data: bytes):
                try:
                    await self.bus.publish(subject, data)
                except Exception as e:
                    logger.warning(f"[GOV] stream publish 失败 [{session_id}]: {e}")
            if chunk_type == "reasoning":
                reasoning_text += chunk
                _reasoning_buffer += chunk
                now = time.time()
                if len(_reasoning_buffer) >= _REASONING_BATCH_SIZE or (now - _reasoning_last_send) >= _REASONING_BATCH_TIMEOUT:
                    buf = _reasoning_buffer
                    _reasoning_buffer = ""
                    _reasoning_last_send = now
                    asyncio.create_task(_safe_publish(
                        f"governance.stream.reasoning.{session_id}",
                        json.dumps({"session_id": session_id, "type": "reasoning", "chunk": buf}).encode()
                    ))
            else:
                if _reasoning_buffer:
                    rbuf = _reasoning_buffer
                    _reasoning_buffer = ""
                    _reasoning_last_send = time.time()
                    asyncio.create_task(_safe_publish(
                        f"governance.stream.reasoning.{session_id}",
                        json.dumps({"session_id": session_id, "type": "reasoning", "chunk": rbuf}).encode()
                    ))
                full_response += chunk
                _speculative_buffer += chunk
                _content_buffer += chunk
                now = time.time()
                if len(_content_buffer) >= _CONTENT_BATCH_SIZE or (now - _content_last_send) >= _CONTENT_BATCH_TIMEOUT:
                    cbuf = _content_buffer
                    _content_buffer = ""
                    _content_last_send = now
                    asyncio.create_task(_safe_publish(
                        f"governance.stream.{session_id}",
                        json.dumps({"session_id": session_id, "type": "content", "chunk": cbuf}).encode()
                    ))
                if len(_speculative_buffer) >= 100 and self.speculative_executor:
                    buf = _speculative_buffer
                    _speculative_buffer = ""
                    intent = self.speculative_executor.detect_intent(buf)
                    if intent:
                        asyncio.create_task(self._run_speculative(
                            intent, session_id, full_response
                        ))
        
        # FIX Phase 5: 读取动态生成参数
        dynamic_params = {"temperature": 0.3, "max_tokens": 8000}
        try:
            state = await self.state_store.load(session_id)
            dp = state.get("_dynamic_gen_params")
            if dp:
                dynamic_params = dp
        except Exception:
            pass
        
        llm_start = time.time()
        try:
            logger.info(f"[GOV] LLM 调用 [{session_id}] messages={len(messages)}, temp={dynamic_params.get('temperature')}, max_tokens={dynamic_params.get('max_tokens')}")
            if messages:
                logger.info(f"[GOV] system={str(messages[0].get('content',''))[:80]}")
                if len(messages) > 1:
                    logger.info(f"[GOV] user={str(messages[1].get('content',''))[:60]}")
            
            # FIX: chat 路径也传入 tools，让 LLM 自己判断是否需要工具
            # 纯闲聊 → LLM 不调用工具，一轮结束（和原来一样快）
            # 需要操作 → LLM 自己判断需要工具，直接切到 Tool Loop
            tools = []
            if hasattr(self, '_get_available_tools'):
                try:
                    tools = await self._get_available_tools(session_id)
                except Exception:
                    pass
            
            _temp = dynamic_params.get("temperature")
            _max_t = dynamic_params.get("max_tokens")
            
            # Phase 2.4: Slot Manager —— 非流式调用使用槽位管理
            if hasattr(self, 'slot_manager') and self.slot_manager and hasattr(self.llm, "chat") and not hasattr(self.llm, "chat_stream"):
                async def _llm_call(msgs, max_tokens):
                    return await self.llm.chat(msgs, max_tokens=max_tokens, temperature=_temp)
                
                slot_result = await self.slot_manager.call_with_slot(
                    _llm_call, messages, session_id=session_id
                )
                full_response = slot_result.content
                if self.telemetry:
                    input_text = "".join(m.get("content", "") for m in messages)
                    self.telemetry.record_llm_call(
                        session_id=session_id,
                        model=getattr(self.llm, 'model', 'unknown'),
                        input_tokens=self._estimate_tokens(input_text),
                        output_tokens=slot_result.tokens_used,
                        latency_ms=slot_result.latency_ms,
                    )
            elif hasattr(self.llm, "chat_stream_with_tools") and tools:
                _tool_calls = []
                def _on_tool_calls(tcs):
                    nonlocal _tool_calls
                    _tool_calls = tcs
                full_response = await self.llm.chat_stream_with_tools(messages, tools, on_chunk, _on_tool_calls, temperature=_temp, max_tokens=_max_t)
                if _tool_calls:
                    # LLM 自己判断需要工具 → 切换到 Tool Loop 完成多轮迭代
                    logger.info(f"[GOV] chat 路径检测到工具调用，切换到 Tool Loop [{session_id}]")
                    return await self._handle_tool_loop(session_id, messages, silent=False, task_type="tool_execution")
            elif hasattr(self.llm, "chat_stream"):
                full_response = await self.llm.chat_stream(messages, on_chunk, temperature=_temp, max_tokens=_max_t)
            elif hasattr(self.llm, "chat"):
                full_response = await self.llm.chat(messages, temperature=_temp, max_tokens=_max_t)
            else:
                full_response = await self.llm(messages)
            
            # FIX Phase 5: 情绪打断——如果回复包含道歉词，清除打断标志
            try:
                from tent_os.services.emotion_service import EmotionService
                emotion_svc = EmotionService()
                if emotion_svc.get_emotion_interrupt_flag(user_id):
                    apology_keywords = ["抱歉", "对不起", "不好意思", "抱歉让您", "非常抱歉", "深表歉意"]
                    if any(kw in full_response for kw in apology_keywords):
                        emotion_svc.clear_emotion_interrupt(user_id)
                        logger.info(f"[GOV] 情绪打断已清除（AI已道歉）[{session_id}]")
            except Exception:
                pass
            
            llm_latency = (time.time() - llm_start) * 1000
            logger.info(f"[GOV] LLM 返回 [{session_id}]: content_len={len(full_response)}, reasoning_len={len(reasoning_text)}, latency={llm_latency:.0f}ms")
            
            # FIX: 每次 LLM 调用都记录 telemetry（token 消耗对 UI 很重要）
            if hasattr(self, 'telemetry') and self.telemetry:
                input_text = "".join(m.get("content", "") for m in messages)
                self.telemetry.record_llm_call(
                    session_id=session_id,
                    model=getattr(self.llm, 'model', 'unknown'),
                    input_tokens=self._estimate_tokens(input_text),
                    output_tokens=self._estimate_tokens(full_response),
                    latency_ms=llm_latency,
                )
            
            # FIX v4: Hook —— governance.reply 只在非闲聊时触发
            # 闲聊不需要外部hook，像人闲聊时不需要第三方监听
            if hasattr(self, 'hook_engine') and self.hook_engine:
                try:
                    # 只在任务类型不是闲聊时才触发reply hook
                    route = state.get("_intuition_route", "uncertain")
                    if route in ("uncertain", "recall"):
                        await self.hook_engine.trigger(
                            "governance.reply",
                            session_id=session_id,
                            data={"content": full_response, "route": route},
                        )
                except Exception as e:
                    logger.debug(f"Hook governance.reply 失败: {e}")
            
            # FIX v5: 检测LLM"假干活"——如果chat回复中包含<function>标签，说明LLM在假装调用工具
            # 像人不会只嘴上说说而不行动，系统也不能只输出文本不执行
            # FIX v6: 检测LLM"假干活"——LLM输出工具调用标签或JSON结构但没有真正执行
            # 覆盖多种假干活格式：XML标签、JSON结构、代码块中的工具描述
            fake_work_markers = ["<function=", "<function>", "<function_calls>", "<invoke ", "<invoke>", "<tool_call>", "<tool>"]
            is_fake_work = any(marker in full_response for marker in fake_work_markers)
            
            # FIX v6.1: 检测JSON格式假干活——LLM输出{"filename":"..."}假装生成了文件
            if not is_fake_work:
                json_fake_patterns = [
                    r'\{\s*"filename"\s*:"[^"]+"\s*,\s*"(data|content|slides|sections)"\s*:',
                    r'\{\s*"title"\s*:"[^"]+"\s*,\s*"(slides|pages|sections|content)"\s*:',
                ]
                for pattern in json_fake_patterns:
                    if re.search(pattern, full_response):
                        is_fake_work = True
                        logger.warning(f"[GOV] 检测到JSON格式假干活 [{session_id}]: 匹配模式 {pattern}")
                        break
            
            # FIX v6.2: 检测纯文本假干活——LLM说"我要排查/检查/看看"但没有任何工具调用
            # 这是最常见的假干活模式：嘴上说说，实际不动
            if not is_fake_work:
                text_promise_markers = [
                    "我先看看", "我来检查一下", "让我排查", "我一步步",
                    "我先确认", "让我查看", "我先检查", "让我看看",
                    "我查一下", "我确认一下", "让我先", "我先去",
                    "我检查一下", "我排查一下", "我查看一下", "我确认一下",
                    "直接动手", "马上改", "立即执行", "现在开始", "正在处理",
                    "读取文件", "修改代码", "创建文件", "写入文件", "修复问题",
                    "我来修复", "我来修改", "我来创建", "我来写入", "我来读取",
                ]
                has_promise = any(m in full_response for m in text_promise_markers)
                # 检查该会话是否有工具调用历史
                has_tool_history = False
                try:
                    _state = await self.state_store.load(session_id)
                    _logs = _state.get("tool_execution_log", []) if _state else []
                    has_tool_history = len(_logs) > 0
                except Exception:
                    pass
                if has_promise and not has_tool_history:
                    is_fake_work = True
                    logger.warning(f"[GOV] 检测到纯文本假干活 [{session_id}]: 承诺执行但无工具调用记录")
            
            if is_fake_work:
                detected = [m for m in fake_work_markers if m in full_response]
                if detected:
                    logger.warning(f"[GOV] 检测到LLM假干活 [{session_id}]: chat回复中包含{detected}，切换到Tool Loop执行")
                else:
                    logger.warning(f"[GOV] 检测到LLM假干活 [{session_id}]: JSON格式假文件生成，切换到Tool Loop执行")
                # 给用户一个过渡提示
                await self._simulate_stream(session_id, "\n\n🔄 检测到需要执行工具操作，正在通过工具调用真正执行...\n")
                # 切换到Tool Loop执行真正的工具调用
                return await self._handle_tool_loop(session_id, messages, silent=False, task_type="tool_execution")
            
            # FIX: 检查用户是否请求中止（chat 模式也要响应）
            try:
                _abort_state = await self.state_store.load(session_id)
                if _abort_state and _abort_state.get("abort_requested"):
                    await self.state_store.update(session_id, {"abort_requested": False})
                    logger.info(f"[GOV] 任务中止 [{session_id}]: 用户请求（chat模式）")
                    await self._simulate_stream(session_id, "\n\n[任务已中止]")
                    await self.bus.publish(f"governance.response.{session_id}", json.dumps({
                        "session_id": session_id,
                        "type": "task.aborted",
                        "content": "任务已中止。",
                    }).encode())
                    return
            except Exception:
                pass
            
            # 保存 assistant 消息（只有 content，不含 reasoning）
            await self.state_store.append_message(session_id, "assistant", full_response)
            
            # FIX: 后验验证——不依赖关键词，用自验证器判定是否真正完成
            # 如果任务需要执行但系统只给了文本回复 → 强制进入 Tool Loop
            try:
                if hasattr(self, 'self_validator') and self.self_validator:
                    _task = state.get("task", "")
                    _history = [{"role": "user", "content": _task}, {"role": "assistant", "content": full_response}]
                    _tool_hist = []
                    try:
                        _s = await self.state_store.load(session_id)
                        _tool_hist = _s.get("tool_execution_log", []) if _s else []
                    except Exception:
                        pass
                    _validation = await self.self_validator.validate(
                        task=_task, conversation_history=_history, response=full_response,
                        task_type="chat", tool_history=_tool_hist
                    )
                    if not _validation.completed and _validation.confidence >= 0.75:
                        # 自验证器判定未完成（高置信度）→ 可能是假干活
                        logger.warning(f"[GOV] 后验验证判定未完成 [{session_id}]: {_validation.reasoning}")
                        await self._simulate_stream(session_id, "\n\n🔄 检测到任务需要实际执行操作，正在真正执行...\n")
                        return await self._handle_tool_loop(session_id, messages, silent=False, task_type="tool_execution")
            except Exception as e:
                logger.debug(f"[GOV] 后验验证异常 [{session_id}]: {e}")
            
            # P0-4 FIX: 发送完成通知前，flush 残留的 reasoning + content buffer
            if _reasoning_buffer:
                await self.bus.publish(
                    f"governance.stream.reasoning.{session_id}",
                    json.dumps({
                        "session_id": session_id,
                        "type": "reasoning",
                        "chunk": _reasoning_buffer,
                    }).encode()
                )
            if _content_buffer:
                await self.bus.publish(
                    f"governance.stream.{session_id}",
                    json.dumps({
                        "session_id": session_id,
                        "type": "content",
                        "chunk": _content_buffer,
                    }).encode()
                )
            
            # 发送完成通知（包含 reasoning 摘要）
            logger.info(f"[GOV] 发送 chat.completed [{session_id}]: content_len={len(full_response)}")
            await self.bus.publish(f"governance.response.{session_id}", json.dumps({
                "session_id": session_id,
                "type": "chat.completed",
                "content": full_response,
                "reasoning": reasoning_text[:500] if reasoning_text else "",  # 摘要
            }).encode())
            
            # FIX: 意图闭环——如果此消息关联意图，通知完成
            await self._notify_intention_completed(session_id, full_response)
            
            # FIX v4.1: 事件驱动触发——像人类只在"重要时刻"反思
            # 
            # 人类思维：
            # - 闲聊 50 句后，不会停下来总结"刚才闲聊的经验" → 正常对话不触发
            # - 被人纠正后，会立刻记住教训 → 检测到异常/错误时触发
            # - 完成重要任务后，才会复盘 → 非闲聊任务完成时触发
            # - 说错话导致对方不高兴 → 事后反思 → 输出含警告/错误时触发
            #
            # 记忆摄入：每轮都做（轻量，像人类对话时自然记住）
            asyncio.create_task(self._ingest_memory(session_id))
            
            # FIX: session 完成触发背景思考
            self._trigger_background_think("session_completed")
            
            # 检测"重要时刻"信号
            error_markers = ["⚠️", "❌", "Failed", "failed", "Error", "error", "不对", "错了"]
            has_error = any(m in full_response for m in error_markers)
            # chat路径默认是闲聊，不需要标记为significant
            is_significant = False
            
            if has_error or is_significant:
                # 重要时刻：总结经验 + 检查规则
                asyncio.create_task(self._extract_experience_after_chat(session_id, messages, full_response))
                asyncio.create_task(self._evaluate_rule_compliance(session_id, full_response))
            
        except Exception as e:
            logger.error(f"[GOV] LLM 调用失败 [{session_id}]: {e}")
            import json as _json
            logger.error(f"[GOV] LLM 请求: {_json.dumps(messages, ensure_ascii=False)[:500]}")
            await self._send_error(session_id, f"AI 响应失败: {e}")
    
    async def _run_speculative(self, intent, session_id: str, context_text: str):
        """执行推测意图并将结果注入上下文"""
        if not self.speculative_executor:
            return
        try:
            task = await self.speculative_executor.execute_if_safe(intent, session_id)
            if task:
                # 等待推测结果（设置超时避免阻塞）
                result = await asyncio.wait_for(task, timeout=self._speculative_timeout)
                if result and hasattr(result, 'get') and result.get('status') == 'completed':
                    # 发送推测完成通知（前端可选择性展示）
                    await self.bus.publish(f"governance.stream.{session_id}", json.dumps({
                        "session_id": session_id,
                        "type": "speculative",
                        "tool": intent.tool,
                        "status": "hit",
                    }).encode())
                    logger.info(f"[GOV] Speculative 命中 [{session_id}]: {intent.tool}")
        except asyncio.TimeoutError:
            logger.debug(f"[GOV] Speculative 超时 [{session_id}]: {intent.tool}")
        except Exception as e:
            logger.debug(f"[GOV] Speculative 异常 [{session_id}]: {e}")

    async def _simulate_stream(self, session_id: str, text: str, chunk_size: int = 5, delay_ms: float = 15):
        """模拟流式输出——将完整文本拆成 chunk 逐字发送
        
        这样 tool loop 在无工具调用时，用户仍能看到"打字"效果。
        
        FIX: 支持段落/句子边界切割 + coalesce 合并短行
        """
        stream_config = self.config.get("stream", {})
        if not stream_config.get("block_streaming", True):
            # 旧模式：固定 chunk_size
            full = ""
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                full += chunk
                await self.bus.publish(f"governance.stream.{session_id}", json.dumps({
                    "session_id": session_id,
                    "type": "content",
                    "chunk": chunk,
                }).encode())
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)
            return full
        
        # 新模式：Block Streaming（段落边界 + coalesce）
        # FIX: 兼容 stream_block_size 热更新配置名
        min_chunk = stream_config.get("stream_block_size", stream_config.get("min_chunk_chars", 40))
        max_chunk = stream_config.get("max_chunk_chars", 300)
        coalesce_ms = stream_config.get("coalesce_ms", 80)
        
        # 1. 按段落/句子边界切割
        blocks = self._split_text_into_blocks(text, min_chunk, max_chunk)
        
        # 2. 发送 + coalesce
        full = ""
        buffer = ""
        for block in blocks:
            buffer += block
            # 如果 buffer 足够长或这是最后一个块，发送
            if len(buffer) >= min_chunk or block == blocks[-1]:
                full += buffer
                await self.bus.publish(f"governance.stream.{session_id}", json.dumps({
                    "session_id": session_id,
                    "type": "content",
                    "chunk": buffer,
                }).encode())
                buffer = ""
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)
            else:
                # coalesce：短块等待一下，看是否有更多内容
                if coalesce_ms > 0:
                    await asyncio.sleep(coalesce_ms / 1000)
        
        if buffer:
            full += buffer
            await self.bus.publish(f"governance.stream.{session_id}", json.dumps({
                "session_id": session_id,
                "type": "content",
                "chunk": buffer,
            }).encode())
        
        return full
    
    def _split_text_into_blocks(self, text: str, min_chunk: int, max_chunk: int) -> List[str]:
        """将文本按段落/句子边界切割成 blocks
        
        优先级：段落(\n\n) > 换行(\n) > 中文句尾(。！？) > 英文句尾(.!? )
        """
        if len(text) <= max_chunk:
            return [text]
        
        blocks = []
        remaining = text
        
        while remaining:
            if len(remaining) <= max_chunk:
                blocks.append(remaining)
                break
            
            chunk = remaining[:max_chunk]
            # 按优先级找最佳截断点
            best_idx = -1
            for boundary in ["\n\n", "\n", "。", "！", "？", ". ", "! ", "? "]:
                idx = chunk.rfind(boundary)
                if idx >= min_chunk:
                    best_idx = idx + len(boundary)
                    break
            
            if best_idx <= 0:
                # 找不到合适边界，硬截断
                best_idx = max_chunk
            
            blocks.append(remaining[:best_idx])
            remaining = remaining[best_idx:]
        
        return blocks
    
    async def _refresh_tool_executor_if_needed(self):
        """如果 Redis 中的模式与当前不同，重新创建 LocalExecutor"""
        if not self.tool_executor or not self.tool_executor.local:
            return
        if not hasattr(self.state_store, 'redis'):
            return
        
        try:
            mode_raw = await self.state_store.redis.get("tent:executor_mode")
            if not mode_raw:
                return
            mode = mode_raw.decode() if isinstance(mode_raw, bytes) else mode_raw
            
            # 检测当前 executor 类型
            current = self.tool_executor.local
            is_sandbox = 'Sandbox' in type(current).__name__
            
            needs_switch = False
            if mode == 'sandbox' and not is_sandbox:
                needs_switch = True
            elif mode == 'local' and is_sandbox:
                needs_switch = True
            elif mode == 'auto':
                from tent_os.scheduler.executors.sandbox import SandboxExecutor
                docker_ok = SandboxExecutor.is_docker_available()
                if docker_ok and not is_sandbox:
                    needs_switch = True
                elif not docker_ok and is_sandbox:
                    needs_switch = True
            
            if needs_switch:
                logger.info(f"[GOV] 检测到执行模式切换: {mode}，重新初始化 ToolExecutor")
                from tent_os.scheduler.executors.local import LocalExecutor
                from tent_os.scheduler.executors.sandbox import SandboxExecutor
                
                local_config = self.config.get("local_executor", {})
                if mode == 'sandbox':
                    new_exec = SandboxExecutor()
                elif mode == 'local':
                    new_exec = LocalExecutor()
                else:  # auto
                    if SandboxExecutor.is_docker_available():
                        try:
                            new_exec = SandboxExecutor()
                            mode = 'sandbox'
                        except Exception:
                            new_exec = LocalExecutor()
                            mode = 'local'
                    else:
                        new_exec = LocalExecutor()
                        mode = 'local'
                
                await new_exec.initialize(local_config)
                self.tool_executor.local = new_exec
                logger.info(f"[GOV] ToolExecutor 已切换到 {mode} 模式")
        except Exception as e:
            logger.warning(f"[GOV] 刷新 ToolExecutor 失败: {e}")
    
    async def _handle_tool_loop(self, session_id: str, llm_messages: List[Dict],
                                  silent: bool = False, max_iterations: int = 100,
                                  task_type: str = "chat"):
        """ReAct Tool Loop —— 让 LLM 自己判断是否需要工具
        
        Args:
            session_id: 会话 ID
            llm_messages: LLM 消息历史
            silent: 静默模式（不暴露工具调用细节给用户，用于 PPT 生成等复杂任务）
            max_iterations: 最大迭代次数（PPT 生成给 100，简单问答给 10）
            task_type: 任务类型，用于日志和进度报告
        
        核心设计：始终传 tools，LLM 的 tool_choice=auto 自己决定。
        - 纯聊天 → LLM 不调用工具，直接回复 → 模拟流式输出
        - 需要操作 → LLM 调用工具 → 执行 → 再次调用
        """
        if not self.tool_executor:
            logger.warning(f"[GOV] ToolExecutor 未配置，回退到流式对话 [{session_id}]")
            return await self._handle_chat_reply(session_id, llm_messages)
        
        if not hasattr(self.llm, "chat_with_tools"):
            logger.warning(f"[GOV] LLM 不支持 chat_with_tools，回退到流式对话 [{session_id}]")
            return await self._handle_chat_reply(session_id, llm_messages)
        
        # 检查是否需要切换执行模式
        await self._refresh_tool_executor_if_needed()
        
        tools = await self._get_available_tools(session_id)
        
        # Phase 1.4: Hook —— tool.assemble 事件
        if hasattr(self, 'hook_engine') and self.hook_engine:
            try:
                hook_result = await self.hook_engine.trigger(
                    "tool.assemble",
                    session_id=session_id,
                    data={"tools": tools, "count": len(tools)},
                )
                if hook_result.modified and hook_result.data.get("tools"):
                    tools = hook_result.data["tools"]
            except Exception as e:
                logger.debug(f"Hook tool.assemble 失败: {e}")
        
        full_response = ""
        tool_call_count = 0
        _has_action_tool = False  # 是否调用过非memory类操作型工具
        
        # FIX Phase 5: 读取动态生成参数（在循环开始时读取一次）
        _tool_loop_dynamic_params = {"temperature": 0.3, "max_tokens": 8000}
        try:
            _tlp_state = await self.state_store.load(session_id)
            _tlp_dp = _tlp_state.get("_dynamic_gen_params")
            if _tlp_dp:
                _tool_loop_dynamic_params = _tlp_dp
        except Exception:
            pass
        
        # FIX v3: 认知预算——Tool Loop 总时间限制
        # FIX v5: 认知预算从config读取（支持热更新），默认3600秒（支持长任务）
        # FIX v6: 优先读取运行时覆盖（热更新同步）
        base_budget = _live_config_overrides.get("cognitive_budget_seconds",
            self.config.get("governance", {}).get("cognitive_budget_seconds", 3600.0))
        scale = getattr(self, '_cognitive_budget_scale', 1.0)
        COGNITIVE_BUDGET_SECONDS = base_budget * scale
        loop_start_time = time.time()
        _background_notified = False  # 是否已发送"转入后台"通知
        
        # FIX: 任务复杂度评估 & 预估时间提示
        last_user_msg = ""
        for msg in reversed(llm_messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break
        _heavy_keywords = ['重构', '全部', '批量', '项目', '完整', '彻底', '全面', '所有文件', '全部修复', '全部完成']
        _is_heavy = any(kw in last_user_msg for kw in _heavy_keywords)
        if task_type in ("PPT 生成", "文档生成", "商务写作") or _is_heavy:
            estimated_msg = f"⏳ 开始执行 {task_type} 任务，预计需要较长时间。系统将在后台持续执行，您可以先去做其他事情。"
            if not silent:
                await self._simulate_stream(session_id, estimated_msg)
        
        def _check_budget():
            elapsed = time.time() - loop_start_time
            if elapsed > COGNITIVE_BUDGET_SECONDS:
                return True, elapsed
            return False, elapsed
        
        async def _notify_background(session_id: str, elapsed: float):
            """发送任务转入后台的通知"""
            nonlocal _background_notified
            if _background_notified:
                return
            _background_notified = True
            msg = (
                f"\n\n---\n"
                f"⏳ 任务已处理 {elapsed:.0f} 秒，预计还需一些时间。"
                f"系统已转入后台继续执行，完成后会通知您。"
                f"您可以先去做其他事情。\n"
            )
            await self._simulate_stream(session_id, msg)
            logger.info(f"[GOV] 任务转入后台 [{session_id}]: 已执行 {elapsed:.1f}s")
        
        # 重置会话工具计数
        self.tool_executor.reset_session(session_id)
        
        # 静默模式下发送任务开始通知（用 chunk 格式让前端直接显示）
        if silent:
            await self.bus.publish(f"governance.stream.{session_id}", json.dumps({
                "session_id": session_id, "type": "content",
                "chunk": f"\n⏳ 开始执行 {task_type} 任务...\n",
            }).encode())
        
        # 追踪工具失败，防止同一个错误无限重试
        consecutive_failures = 0
        last_failed_tool = None
        # FIX Phase 1.3: 追踪是否有任何工具错误（用于按需自验证）
        any_tool_error = False
        
        # FIX: 工具结果缓存，避免 LLM 重复执行相同操作（绕圈子）
        _tool_result_cache: Dict[str, Dict] = {}
        _tool_execution_history: List[str] = []
        # FIX: 收集工具执行历史，供自验证器参考
        _tool_history: List[Dict] = []
        
        # FIX Phase 2.5: Promise Tracker —— 记录任务承诺
        _task_desc = task_type if task_type != "chat" else "对话处理"
        if hasattr(self, '_promise_tracker') and self._promise_tracker:
            self._promise_tracker.record_promise(session_id, _task_desc)
        
        streamed_text = ""  # FIX: 提前初始化，避免 abort handler 引用未定义变量
        try:
            while True:  # FIX: 外层循环支持重置续跑
              for i in range(max_iterations):
                # FIX v3: 每轮迭代检查认知预算
                budget_exhausted, elapsed = _check_budget()
                if budget_exhausted:
                    # FIX: 长任务支持——预算耗尽时不截断，转入后台续跑
                    await _notify_background(session_id, elapsed)
                    loop_start_time = time.time()  # 重置计时器，继续执行
                    _background_notified = False   # 下次耗尽再次通知
                    logger.info(f"[GOV] Tool Loop 认知预算重置 [{session_id}]: 转入后台续跑")
                
                # FIX: 检查用户是否请求中止任务
                try:
                    _abort_state = await self.state_store.load(session_id)
                    if _abort_state.get("abort_requested"):
                        await self.state_store.update(session_id, {"abort_requested": False})
                        full_response = streamed_text or "任务已中止。"
                        logger.info(f"[GOV] 任务中止 [{session_id}]: 用户请求")
                        await self._simulate_stream(session_id, "\n\n[任务已中止]")
                        break
                except Exception:
                    pass
                
                logger.info(f"[GOV] Tool Loop 迭代 {i+1}/{max_iterations} [{session_id}] silent={silent} elapsed={elapsed:.1f}s")
                
                # FIX: 进度心跳——每 30 秒发送一次进度，让用户知道系统还在干活
                if not silent and i > 0:
                    _progress_interval = 30  # 秒
                    _last_progress = getattr(self, '_last_progress_time', {}).get(session_id, loop_start_time)
                    if elapsed - (_last_progress - loop_start_time) >= _progress_interval:
                        progress_msg = f"⏳ 正在处理中... 已执行 {int(elapsed)} 秒，当前第 {i+1} 步"
                        await self._simulate_stream(session_id, progress_msg)
                        if not hasattr(self, '_last_progress_time'):
                            self._last_progress_time = {}
                        self._last_progress_time[session_id] = time.time()
                
                # FIX: 优先使用流式 tool calling（真流式体验）
                if hasattr(self.llm, "chat_stream_with_tools"):
                    tool_calls = []
                    streamed_text = ""
                    reasoning_text = ""
                    
                    # P0-4 FIX: Tool Loop reasoning + content 批量发送缓冲
                    _tool_loop_rb = ""
                    _tool_loop_rb_last = time.time()
                    _tool_loop_cb = ""
                    _tool_loop_cb_last = time.time()
                    
                    def _on_chunk(chunk: str, chunk_type: str = "content"):
                        nonlocal streamed_text, reasoning_text, _tool_loop_rb, _tool_loop_rb_last
                        nonlocal _tool_loop_cb, _tool_loop_cb_last
                        if chunk_type == "reasoning":
                            reasoning_text += chunk
                            if not silent:
                                _tool_loop_rb += chunk
                                now = time.time()
                                if len(_tool_loop_rb) >= 50 or (now - _tool_loop_rb_last) >= 0.8:
                                    # FIX: 同步提取并清空 buffer，避免 async task 延迟导致重复发送
                                    buf = _tool_loop_rb
                                    _tool_loop_rb = ""
                                    _tool_loop_rb_last = now
                                    asyncio.create_task(self.bus.publish(
                                        f"governance.stream.reasoning.{session_id}",
                                        json.dumps({"session_id": session_id, "type": "reasoning", "chunk": buf}).encode()
                                    ))
                        else:
                            if _tool_loop_rb:
                                rbuf = _tool_loop_rb
                                _tool_loop_rb = ""
                                _tool_loop_rb_last = time.time()
                                asyncio.create_task(self.bus.publish(
                                    f"governance.stream.reasoning.{session_id}",
                                    json.dumps({"session_id": session_id, "type": "reasoning", "chunk": rbuf}).encode()
                                ))
                            streamed_text += chunk
                            if not silent:
                                # content 轻量 batching
                                _tool_loop_cb += chunk
                                now = time.time()
                                if len(_tool_loop_cb) >= 10 or (now - _tool_loop_cb_last) >= 0.03:
                                    cbuf = _tool_loop_cb
                                    _tool_loop_cb = ""
                                    _tool_loop_cb_last = now
                                    asyncio.create_task(self.bus.publish(
                                        f"governance.stream.{session_id}",
                                        json.dumps({"session_id": session_id, "type": "content", "chunk": cbuf}).encode()
                                    ))
                    
                    def _on_tool_calls(tcs: List[Dict]):
                        nonlocal tool_calls
                        tool_calls = tcs
                    
                    # FIX: Tool Loop 上下文压缩——避免 messages 无限增长导致 token 爆炸
                    # CRITICAL FIX: 保留用户原始任务，否则 LLM 不知道自己在干什么
                    _max_tool_msgs = self.config.get("governance", {}).get("max_tool_loop_messages", 20)
                    if len(llm_messages) > _max_tool_msgs:
                        compressed = [llm_messages[0]]  # system prompt
                        
                        # 找到用户原始任务（最新的非工具结果 user 消息）
                        _task_msg = None
                        for m in reversed(llm_messages[1:]):
                            if m.get("role") == "user" and "【工具执行结果" not in str(m.get("content", "")):
                                _task_msg = m
                                break
                        
                        if _task_msg:
                            compressed.append(_task_msg)
                        
                        # 保留最近的消息（扣除已保留的 system + task）
                        _remaining = _max_tool_msgs - len(compressed)
                        compressed.extend(llm_messages[-_remaining:])
                        
                        removed = len(llm_messages) - len(compressed)
                        logger.info(f"[GOV] Tool Loop 上下文压缩 [{session_id}]: {len(llm_messages)} → {len(compressed)} 条 (移除 {removed} 条, 保留原始任务={_task_msg is not None})")
                        llm_messages = compressed
                    
                    # FIX: 为 chat_stream_with_tools 添加整体超时保护，防止 SSE 心跳保活导致无限等待
                    _llm_call_start = time.time()
                    try:
                        _tlp_temp = _tool_loop_dynamic_params.get("temperature")
                        _tlp_max_t = _tool_loop_dynamic_params.get("max_tokens")
                        await asyncio.wait_for(
                            self.llm.chat_stream_with_tools(llm_messages, tools, _on_chunk, _on_tool_calls, temperature=_tlp_temp, max_tokens=_tlp_max_t),
                            timeout=self._tool_loop_timeout
                        )
                        # FIX: Tool Loop 流式调用后记录 telemetry
                        if hasattr(self, 'telemetry') and self.telemetry:
                            _input_text = "".join(m.get("content", "") for m in llm_messages)
                            self.telemetry.record_llm_call(
                                session_id=session_id,
                                model=getattr(self.llm, 'model', 'unknown'),
                                input_tokens=self._estimate_tokens(_input_text),
                                output_tokens=self._estimate_tokens(streamed_text),
                                latency_ms=(time.time() - _llm_call_start) * 1000,
                            )
                    except asyncio.TimeoutError:
                        # FIX: 长任务支持——流式调用超时不截断，转入后台续跑
                        logger.warning(f"[GOV] Tool Loop LLM 流式调用超时 [{session_id}]，转入后台续跑")
                        elapsed = time.time() - loop_start_time
                        await _notify_background(session_id, elapsed)
                        # 使用已收集的内容作为当前轮回复，加入 messages 后继续
                        if streamed_text:
                            full_response = streamed_text
                            llm_messages.append({"role": "assistant", "content": full_response})
                        # 重置流式调用超时计时
                        loop_start_time = time.time()
                        _background_notified = False
                        continue  # 继续下一次迭代，而不是 break
                    
                    # P0-4 FIX: 迭代结束 flush 残留 reasoning + content buffer
                    if _tool_loop_rb:
                        await self.bus.publish(
                            f"governance.stream.reasoning.{session_id}",
                            json.dumps({"session_id": session_id, "type": "reasoning", "chunk": _tool_loop_rb}).encode()
                        )
                        _tool_loop_rb = ""
                    if _tool_loop_cb:
                        await self.bus.publish(
                            f"governance.stream.{session_id}",
                            json.dumps({"session_id": session_id, "type": "content", "chunk": _tool_loop_cb}).encode()
                        )
                        _tool_loop_cb = ""
                    
                    if not tool_calls:
                        # === 流式模式下无工具调用 ===
                        # FIX: 尝试从文本中解析 tool_calls（LLM 有时在文本中写 tool_call 而不是通过 function calling）
                        _parsed_tools = self._parse_tool_calls_from_text(streamed_text)
                        if _parsed_tools:
                            tool_calls = _parsed_tools
                            logger.info(f"[GOV] 从文本中解析到 tool_calls [{session_id}]: {len(tool_calls)} 个")
                            # 继续执行工具，不 break
                        else:
                            # FIX: 如果 LLM 之前已经调用过工具（操作型任务），但当前轮没调用，
                            # 给它重试机会——可能是上一轮只是了解情况，这一轮应该执行。
                            _retry_count = getattr(self, '_tool_loop_retry_counts', {}).get(session_id, 0)
                            if _has_action_tool and _retry_count < 2:
                                if not hasattr(self, '_tool_loop_retry_counts'):
                                    self._tool_loop_retry_counts = {}
                                self._tool_loop_retry_counts[session_id] = _retry_count + 1
                                llm_messages.append({
                                    "role": "system",
                                    "content": (
                                        "[系统提示：你上一轮没有调用工具。"
                                        "如果任务还需要文件操作（读取、写入、修改）或其他操作，"
                                        "请直接调用对应工具完成，不要输出文本描述或计划。"
                                        "只输出 tool_calls 或任务完成的简要总结。]"
                                    ),
                                })
                                logger.info(f"[GOV] LLM 未调用工具，给予重试机会 [{session_id}] 第{_retry_count + 1}次")
                                continue
                            
                            # 清理重试计数
                            if hasattr(self, '_tool_loop_retry_counts') and session_id in self._tool_loop_retry_counts:
                                del self._tool_loop_retry_counts[session_id]
                            
                            full_response = streamed_text
                            # FIX: 记录完整内容以便调试假干活问题
                            logger.info(f"[GOV] LLM 流式回复完成 [{session_id}]: len={len(full_response)}, content={full_response[:200]!r}")
                            break
                else:
                    # 回退到非流式调用
                    _tlp_temp = _tool_loop_dynamic_params.get("temperature")
                    _tlp_max_t = _tool_loop_dynamic_params.get("max_tokens")
                    result = await self.llm.chat_with_tools(llm_messages, tools, temperature=_tlp_temp, max_tokens=_tlp_max_t)
                    
                    content = result.get("content", "")
                    tool_calls = result.get("tool_calls", [])
                    
                    if not tool_calls:
                        # === 没有工具调用 ===
                        # FIX: 尝试从文本中解析 tool_calls
                        _parsed_tools = self._parse_tool_calls_from_text(content)
                        if _parsed_tools:
                            tool_calls = _parsed_tools
                            logger.info(f"[GOV] 从文本中解析到 tool_calls [{session_id}]: {len(tool_calls)} 个")
                        else:
                            # FIX: 如果 LLM 之前已经调用过工具（操作型任务），但当前轮没调用，给予重试机会
                            _retry_count = getattr(self, '_tool_loop_retry_counts', {}).get(session_id, 0)
                            if _has_action_tool and _retry_count < 2:
                                if not hasattr(self, '_tool_loop_retry_counts'):
                                    self._tool_loop_retry_counts = {}
                                self._tool_loop_retry_counts[session_id] = _retry_count + 1
                                llm_messages.append({
                                    "role": "system",
                                    "content": (
                                        "[系统提示：你上一轮没有调用工具。"
                                        "如果任务还需要文件操作（读取、写入、修改）或其他操作，"
                                        "请直接调用对应工具完成，不要输出文本描述或计划。"
                                        "只输出 tool_calls 或任务完成的简要总结。]"
                                    ),
                                })
                                logger.info(f"[GOV] LLM 未调用工具，给予重试机会 [{session_id}] 第{_retry_count + 1}次")
                                continue
                            
                            if hasattr(self, '_tool_loop_retry_counts') and session_id in self._tool_loop_retry_counts:
                                del self._tool_loop_retry_counts[session_id]
                            
                            full_response = content
                            logger.info(f"[GOV] LLM 未调用工具，直接回复 [{session_id}]: {full_response[:80]}")
                            await self._simulate_stream(session_id, full_response)
                            break
                
                # === 有工具调用：执行工具 ===
                for tc in tool_calls:
                    tool_name = tc["function"]["name"]
                    try:
                        arguments = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        arguments = {}
                    
                    args_str = json.dumps(arguments, ensure_ascii=False)[:200]
                    logger.info(f"[GOV] 执行工具 {tool_name} [{session_id}] args={args_str}")
                    tool_call_count += 1
                    # FIX: 标记是否调用过非memory类操作型工具，用于重试判断
                    if tool_name not in {"memory_search", "memory_get", "web_search", "web_fetch"}:
                        _has_action_tool = True
                    
                    # 发送进度给用户
                    progress_msg = self._build_progress_message(tool_name, tool_call_count, task_type, arguments)
                    if progress_msg:
                        await self.bus.publish(f"governance.stream.{session_id}", json.dumps({
                            "session_id": session_id, "type": "content",
                            "chunk": f"{progress_msg}\n",
                        }).encode())
                    
                    # 初始化工具结果
                    tool_result = None
                    
                    # FIX: 工具结果缓存——避免 LLM 重复执行相同操作
                    import json as _json
                    _cache_key = f"{tool_name}:{_json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"
                    _tool_execution_history.append(_cache_key)
                    
                    # 检测重复操作：同一个操作连续执行超过 1 次，直接返回缓存结果
                    _same_op_count = sum(1 for h in _tool_execution_history if h == _cache_key)
                    if _same_op_count >= 2 and _cache_key in _tool_result_cache:
                        cached = _tool_result_cache[_cache_key]
                        logger.info(f"[GOV] 工具 {tool_name} 重复执行，使用缓存结果 [{session_id}]")
                        tool_result = _json.dumps({
                            "status": "completed",
                            "result": cached.get("result", {}),
                            "cached": True,
                            "note": "此操作已在之前执行过，结果为缓存值。"
                        }, ensure_ascii=False)
                    else:
                        # Phase 2.3: 7层安全评估 —— 替代原有 PolicyEngine 检查
                        security_result = None
                        if hasattr(self, 'layered_security') and self.layered_security:
                            try:
                                _tool_loop_state = await self.state_store.load(session_id)
                            except Exception:
                                _tool_loop_state = {}
                            security_result = await self.layered_security.evaluate_tool_call(
                                session_id=session_id,
                                tool_name=tool_name,
                                params=arguments,
                                task_context=_tool_loop_state.get("task", ""),
                            )
                            # FIX v4: Telemetry降频——只在安全事件时记录
                            # FIX v5: 流式模式下result未定义，使用security_result直接判断
                            if self.telemetry and security_result and getattr(security_result, 'safety_level', 'safe') not in ("safe", None):
                                self.telemetry.record_security(
                                    security_result.layer, security_result.decision
                                )
                        
                        # Phase 1.4: Hook —— tool.preuse 事件
                        if hasattr(self, 'hook_engine') and self.hook_engine:
                            try:
                                hook_result = await self.hook_engine.trigger(
                                    "tool.preuse",
                                    session_id=session_id,
                                    data={"tool": tool_name, "params": arguments},
                                )
                                if not hook_result.allowed:
                                    security_result = None  # Hook 拦截优先
                                    tool_result = json.dumps({
                                        "status": "error",
                                        "error": f"Hook 拦截: {hook_result.error or '未指定原因'}"
                                    }, ensure_ascii=False)
                                    logger.warning(f"[GOV] 工具 {tool_name} 被 Hook 拦截 [{session_id}]")
                            except Exception as e:
                                logger.debug(f"Hook tool.preuse 失败: {e}")
                        
                        # 执行安全评估结果
                        if security_result and not security_result.allowed:
                            if security_result.decision == "deny":
                                tool_result = json.dumps({
                                    "status": "error",
                                    "error": f"安全层拒绝 ({security_result.layer}): {security_result.reason}"
                                }, ensure_ascii=False)
                                logger.warning(f"[GOV] 工具 {tool_name} 被安全层 '{security_result.layer}' 拒绝 [{session_id}]")
                            elif security_result.decision in ("require_approval", "circuit_break"):
                                if self.config.get("governance", {}).get("auto_approve", False):
                                    # FIX: auto_approve模式下直接执行，不阻塞
                                    logger.info(f"[GOV] auto_approve: 跳过安全层审批 [{session_id}] {tool_name}")
                                    tool_result = await self.tool_executor.execute(
                                        tool_name, arguments, session_id, max_calls=max_iterations
                                    )
                                else:
                                    await self.bus.publish("governance.approval.request", json.dumps({
                                        "session_id": session_id,
                                        "plan": {"steps": [{"action": tool_name, "executor": "local", "params": arguments}]},
                                        "reply_to": "governance.resume",
                                        "policy_rule": security_result.layer,
                                        "reason": security_result.reason,
                                    }).encode())
                                    full_response = f"⏸️ 工具 `{tool_name}` 需要审批（{security_result.layer}: {security_result.reason}）"
                                    await self._simulate_stream(session_id, full_response)
                                    break
                            else:
                                tool_result = await self.tool_executor.execute(
                                    tool_name, arguments, session_id, max_calls=max_iterations
                                )
                        elif tool_result is None:  # Hook 未拦截时
                            # FIX: PolicyEngine 回退检查（原有逻辑保留）
                            if self.policy_engine:
                                from datetime import datetime
                                _fallback_task = ""
                                try:
                                    _fallback_state = await self.state_store.load(session_id)
                                    _fallback_task = _fallback_state.get("task", "")
                                except Exception:
                                    pass
                                policy_ctx = {
                                    "task": _fallback_task,
                                    "action": tool_name,
                                    "executor": {
                                        "authorized": True,
                                        "status": "idle",
                                        "consecutive_failures": consecutive_failures,
                                        "queue_depth": 0,
                                        "is_physical": tool_name in ("realman", "flashex"),
                                    },
                                    "hour": datetime.now().hour,
                                }
                                policy_result = self.policy_engine.evaluate(policy_ctx)
                                if policy_result["decision"] == "deny":
                                    tool_result = json.dumps({
                                        "status": "error",
                                        "error": f"策略拒绝: {policy_result.get('reason', '不符合策略规则')} [{policy_result['rule']}]"
                                    }, ensure_ascii=False)
                                elif policy_result["decision"] == "require_approval":
                                    if self.config.get("governance", {}).get("auto_approve", False):
                                        # FIX: auto_approve模式下直接执行，不阻塞
                                        logger.info(f"[GOV] auto_approve: 跳过策略审批 [{session_id}] {tool_name}")
                                        tool_result = await self.tool_executor.execute(
                                            tool_name, arguments, session_id, max_calls=max_iterations
                                        )
                                    else:
                                        await self.bus.publish("governance.approval.request", json.dumps({
                                            "session_id": session_id,
                                            "plan": {"steps": [{"action": tool_name, "executor": "local", "params": arguments}]},
                                            "reply_to": "governance.resume",
                                            "policy_rule": policy_result["rule"],
                                            "reason": policy_result.get("reason", ""),
                                        }).encode())
                                        full_response = f"⏸️ 工具 `{tool_name}` 需要审批（策略: {policy_result['rule']}）"
                                        await self._simulate_stream(session_id, full_response)
                                        break
                                else:
                                    tool_result = await self.tool_executor.execute(
                                        tool_name, arguments, session_id, max_calls=max_iterations
                                    )
                            else:
                                tool_result = await self.tool_executor.execute(
                                    tool_name, arguments, session_id, max_calls=max_iterations
                                )
                        
                        # FIX: 缓存成功的工具结果
                        try:
                            if isinstance(tool_result, str):
                                _cache_data = _json.loads(tool_result)
                            else:
                                _cache_data = tool_result
                            if _cache_data.get("status") != "error":
                                _tool_result_cache[_cache_key] = _cache_data
                        except Exception:
                            pass
                    
                    # 检查结果状态（FIX: tool_result 可能是 dict 或 str）
                    try:
                        if isinstance(tool_result, str):
                            result_data = json.loads(tool_result)
                        else:
                            result_data = tool_result
                        is_error = result_data.get("status") == "error"
                        is_require_approval = result_data.get("status") == "require_approval"
                    except Exception:
                        is_error = False
                        is_require_approval = False
                    
                    # FIX: 记录工具执行历史，供自验证器参考
                    _result_summary = "error" if is_error else ("approval_needed" if is_require_approval else "success")
                    _tool_history.append({
                        "tool": tool_name,
                        "args": arguments,
                        "result": _result_summary,
                        "error_msg": result_data.get("error", "") if is_error else "",
                    })
                    
                    # FIX v5: 记录工具执行链到state_store，供UI展示
                    try:
                        _log_entry = {
                            "step": i,
                            "tool": tool_name,
                            "args": {k: str(v)[:200] for k, v in arguments.items()},  # 截断避免过大
                            "result": _result_summary,
                            "latency_ms": int((time.time() - loop_start_time) * 1000),
                            "timestamp": time.time(),
                        }
                        _existing = await self.state_store.load(session_id)
                        _logs = (_existing.get("tool_execution_log", []) if _existing else [])
                        _logs.append(_log_entry)
                        # 最多保留50条
                        if len(_logs) > 50:
                            _logs = _logs[-50:]
                        await self.state_store.update(session_id, {"tool_execution_log": _logs})
                    except Exception:
                        pass
                    
                    # FIX: 危险操作需要用户二次确认
                    if is_require_approval:
                        error_msg = result_data.get("error", "危险操作需要确认")
                        operation = result_data.get("operation", "unknown")
                        details = result_data.get("details", {})
                        
                        if self.config.get("governance", {}).get("auto_approve", False):
                            # FIX: auto_approve模式下跳过审批，继续执行
                            logger.info(f"[GOV] auto_approve: 跳过危险操作审批 [{session_id}] {tool_name}: {error_msg}")
                            # 把require_approval当成success继续Tool Loop
                            tool_result = json.dumps({"status": "success", "result": f"[AUTO-APPROVED] {error_msg}"}, ensure_ascii=False)
                        else:
                            logger.warning(f"[GOV] 工具 {tool_name} 需要审批 [{session_id}]: {error_msg}")
                            await self.bus.publish("governance.approval.request", json.dumps({
                                "session_id": session_id,
                                "plan": {"steps": [{"action": tool_name, "executor": "local", "params": arguments}]},
                                "reply_to": "governance.resume",
                                "policy_rule": "dangerous_operation",
                                "reason": error_msg,
                                "operation": operation,
                                "details": details,
                            }).encode())
                            full_response = f"⏸️ {error_msg}"
                            await self._simulate_stream(session_id, full_response)
                            break
                    
                    if is_error:
                        error_msg = result_data.get("error", "未知错误")
                        logger.error(f"[GOV] 工具 {tool_name} 失败 [{session_id}]: {error_msg}")
                        any_tool_error = True  # FIX Phase 1.3: 标记有工具错误
                        
                        # FIX: 工具调用次数超限——重置计数器继续执行，不说"不"
                        if "超过上限" in error_msg or "max_calls" in error_msg or "次数超过" in error_msg:
                            logger.info(f"[GOV] 工具调用次数超限，自动重置计数器 [{session_id}]")
                            self.tool_executor.reset_session(session_id)
                            llm_messages.append({
                                "role": "system",
                                "content": (
                                    f"[系统提示：工具调用次数已自动重置，请继续执行。"
                                    f"如果任务尚未完成，请继续下一步操作。]"
                                ),
                            })
                            # 不增加失败计数，让系统继续
                            consecutive_failures = 0
                            last_failed_tool = None
                        else:
                            # 连续失败检测
                            if last_failed_tool == tool_name:
                                consecutive_failures += 1
                            else:
                                consecutive_failures = 1
                                last_failed_tool = tool_name
                            
                            if consecutive_failures >= 2:
                                # FIX: 不说"不"，说"yes"——工具连续失败时注入换方法提示，不终止任务
                                llm_messages.append({
                                    "role": "system",
                                    "content": (
                                        f"[系统提示：工具 `{tool_name}` 已连续失败 {consecutive_failures} 次，"
                                        f"错误：{error_msg[:200]}。"
                                        f"请换一种完全不同的方法尝试，或直接向用户汇报当前进展和遇到的问题。"
                                        f"不要继续重复执行已失败的工具。]"
                                    ),
                                })
                                logger.info(f"[GOV] 工具连续失败，注入换方法提示 [{session_id}]: {tool_name}")
                                # 重置失败计数，给 LLM 重新开始的机会
                                consecutive_failures = 0
                                last_failed_tool = None
                        
                        # 非静默模式发送错误给用户
                        if not silent:
                            await self.bus.publish(f"governance.stream.{session_id}", json.dumps({
                                "session_id": session_id, "type": "content",
                                "chunk": f"❌ {tool_name} 失败: {error_msg[:200]}\n",
                            }).encode())
                        # Broadcast emotion: tool failed
                        from tent_os.services.emotion_service import EmotionService
                        _es = EmotionService()
                        _emotion = _es.update_by_task_action(session_id, "task_failed")
                        await self.bus.publish_raw("emotion.broadcast", json.dumps({
                            "user_id": session_id,
                            "emotion": _emotion,
                            "source": "tool_failed"
                        }).encode())
                    else:
                        # 成功，重置失败计数
                        consecutive_failures = 0
                        last_failed_tool = None
                        # Broadcast emotion: tool success
                        from tent_os.services.emotion_service import EmotionService
                        _es = EmotionService()
                        _emotion = _es.update_by_task_action(session_id, "task_passed")
                        await self.bus.publish_raw("emotion.broadcast", json.dumps({
                            "user_id": session_id,
                            "emotion": _emotion,
                            "source": "tool_success"
                        }).encode())
                        
                        # FIX Phase 2.5: Promise Tracker —— 记录实质性进展
                        if hasattr(self, '_promise_tracker') and self._promise_tracker:
                            self._promise_tracker.record_progress(session_id, f"tool:{tool_name}")
                        
                        # Phase 1.4: Hook —— tool.postuse 事件
                        if hasattr(self, 'hook_engine') and self.hook_engine:
                            try:
                                await self.hook_engine.trigger(
                                    "tool.postuse",
                                    session_id=session_id,
                                    data={"tool": tool_name, "params": arguments, "result": tool_result},
                                )
                            except Exception as e:
                                logger.debug(f"Hook tool.postuse 失败: {e}")
                        
                        # Phase 3.4: Telemetry —— 记录工具调用
                        # FIX v4: Telemetry降频——只在工具成功时记录
                        # FIX v5: result_text未定义，改用tool_result判断
                        if hasattr(self, 'telemetry') and self.telemetry and tool_result and "error" not in str(tool_result).lower():
                            self.telemetry.record_tool_call(
                                session_id=session_id,
                                tool=tool_name,
                                latency_ms=0,
                                success=True,
                            )
                    
                    # FIX: 工具结果截断——结构化截断，不破坏 JSON
                    max_result_chars = self.config.get("tools", {}).get("max_result_chars", 4000)
                    tool_result_display = tool_result
                    if isinstance(tool_result, str) and len(tool_result) > max_result_chars:
                        try:
                            result_obj = json.loads(tool_result)
                            # 智能截断：优先截断长字符串字段
                            self._truncate_tool_result_object(result_obj, max_result_chars)
                            tool_result_display = json.dumps(result_obj, ensure_ascii=False, indent=2)
                        except json.JSONDecodeError:
                            # 非 JSON，安全文本截断
                            truncated = tool_result[:max_result_chars]
                            for boundary in ["\n\n", "\n", "。", "！", "？", ". ", "! ", "? "]:
                                idx = truncated.rfind(boundary)
                                if idx > max_result_chars * 0.7:
                                    truncated = truncated[:idx + len(boundary)]
                                    break
                            tool_result_display = truncated + f"\n\n[...结果过长，已截断（{len(tool_result)} 字符 → {max_result_chars} 字符）...]"
                    
                    # 将工具结果作为 user 消息追加到历史
                    _error_badge = " | ❌ 执行失败" if is_error else ""
                    llm_messages.append({
                        "role": "user",
                        "content": (
                            f"【工具执行结果 | {tool_name}{_error_badge}】\n"
                            f"{tool_result_display}\n\n"
                            f"---\n"
                            f"[基于以上结果，你的下一步只有两个选项："
                            f"1) 如果还需要操作（读取更多文件、修改文件、执行命令等），直接调用对应工具，不要输出任何计划或步骤描述；"
                            f"2) 如果任务已完成，给出一句简要总结。"
                            f"严禁输出'先读...然后...'、'接下来...'、'让我...'等中间计划——直接调用工具或给出总结。]"
                        ),
                    })
                    
                    # FIX: 通用行为纠正——检测 LLM 是否在用通用工具手动实现专用功能
                    # P1-1 FIX: 纠正逻辑过于宽泛，导致正常命令被错误纠正
                    # 原则：只在明确检测到"手写渲染文档"时才纠正，保留正常文件操作
                    if tool_name in ("shell", "file_write"):
                        cmd_or_content = ""
                        if tool_name == "shell":
                            cmd_or_content = arguments.get("command", "")
                        elif tool_name == "file_write":
                            cmd_or_content = arguments.get("content", "")
                        
                        # 收紧模式：只匹配明确的手写渲染文档信号
                        # 移除过于宽泛的模式（mkdir、python3 -c、echo 等）
                        manual_patterns = [
                            (r"<!DOCTYPE\s+html", "render_webpage", "手写 HTML"),
                            (r"<html[\s>]", "render_webpage", "手写 HTML"),
                            (r"\.docx\b", "render_word", "生成 Word 文档"),
                            (r"\.pptx\b", "render_ppt", "生成 PPT"),
                            (r"\.xlsx\b", "render_excel", "生成 Excel"),
                        ]
                        
                        for pattern, suggested_tool, action_desc in manual_patterns:
                            if re.search(pattern, cmd_or_content, re.IGNORECASE):
                                correction_msg = (
                                    f"[系统提示] 检测到你在用 {tool_name} 手动{action_desc}。"
                                    f"如果用户需要的是标准格式的 {action_desc}，"
                                    f"建议直接调用专用工具 `{suggested_tool}` 以获得更好的格式支持。"
                                )
                                llm_messages.append({
                                    "role": "system",
                                    "content": correction_msg,
                                })
                                logger.info(f"[GOV] 工具使用提示 [{session_id}]: {tool_name} → {suggested_tool} ({action_desc})")
                                break
                
                # === Phase 4: Loop Detection —— 检测循环模式 ===
                if hasattr(self, 'loop_detector') and self.loop_detector:
                    try:
                        loop_result = self.loop_detector.check(
                            session_id=session_id,
                            iteration=i + 1,
                            content=content,
                            tool_calls=tool_calls,
                            tool_results=[json.loads(tool_result) if tool_result and isinstance(tool_result, str) else {} for _ in tool_calls],
                        )
                        if loop_result.is_loop:
                            logger.info(f"[GOV] 检测到循环模式 [{session_id}]，注入换方法提示")
                            # FIX: 不说"不"，说"yes"——检测到循环时注入提示让 LLM 跳出，不终止
                            llm_messages.append({
                                "role": "system",
                                "content": (
                                    f"[系统提示：检测到执行模式可能重复。{loop_result.details}"
                                    f"请换一种完全不同的方法，或直接总结当前成果回复用户。"
                                    f"避免重复执行相同的工具序列。]"
                                ),
                            })
                    except Exception as e:
                        logger.debug(f"Loop Detection 失败: {e}")
                
                # FIX Phase 6: Promise Tracker 停滞检测 —— 利用 Tool Loop 本身作为检查点
                if hasattr(self, '_promise_tracker') and self._promise_tracker:
                    stalled_reason = self._promise_tracker.check_stalled(session_id)
                    if stalled_reason:
                        if stalled_reason.startswith("提醒"):
                            # 20秒无进展：发送进度提醒（用户不会干等）
                            if not silent:
                                await self.bus.publish(f"governance.stream.{session_id}", json.dumps({
                                    "session_id": session_id, "type": "content",
                                    "chunk": f"⏳ 正在处理中，请稍候...（已执行 {i+1} 步）\n",
                                }).encode())
                            logger.info(f"[GOV] Promise 提醒 [{session_id}]: {stalled_reason}")
                        elif stalled_reason.startswith("停滞"):
                            # 60秒无进展：发送困难提醒 + 尝试重新规划
                            if not silent:
                                await self.bus.publish(f"governance.stream.{session_id}", json.dumps({
                                    "session_id": session_id, "type": "content",
                                    "chunk": f"⏳ 任务似乎遇到了困难，正在尝试调整方案...\n",
                                }).encode())
                            if self._promise_tracker.should_replan(session_id):
                                llm_messages.append({
                                    "role": "system",
                                    "content": (
                                        "[系统提示：当前任务执行似乎卡住了（可能是工具反复失败或方法不对）。"
                                        "请重新评估当前进展，考虑：1）换一种方法；2）简化任务；3）直接给出当前已完成的成果和遇到的问题。"
                                        "不要重复执行已经失败过的工具。]"
                                    ),
                                })
                                logger.info(f"[GOV] Promise 重新规划注入 [{session_id}]")
                            logger.warning(f"[GOV] Promise 停滞 [{session_id}]: {stalled_reason}")
                        elif stalled_reason.startswith("放弃"):
                            # FIX: 不说"不"，说"yes"——多次尝试无进展时注入重新规划提示，不终止
                            llm_messages.append({
                                "role": "system",
                                "content": (
                                    "[系统提示：任务执行遇到了较大困难，多次尝试后进展有限。"
                                    "请重新评估当前状况，考虑：1）换一种完全不同的方法；"
                                    "2）直接总结当前已完成的成果和遇到的问题，向用户汇报；"
                                    "3）如果需要，向用户询问更多信息。不要继续重复已失败的操作。]"
                                ),
                            })
                            logger.info(f"[GOV] Promise 停滞，注入重新规划提示 [{session_id}]")
                
                # 如果因连续失败设置了 full_response，跳出外循环
                if full_response and "❌ 任务执行失败" in full_response:
                    break
              else:
                # FIX: 超过最大迭代次数——不截断，转入后台续跑
                elapsed = time.time() - loop_start_time
                logger.info(f"[GOV] Tool Loop 达到迭代上限 [{session_id}]，重置续跑")
                await _notify_background(session_id, elapsed)
                # 重置迭代计数和计时器，继续执行
                i = -1  # for循环的i会在下一轮+1变为0
                loop_start_time = time.time()
                _background_notified = False
                # FIX: 重置工具调用计数，让系统能继续自主执行
                self.tool_executor.reset_session(session_id)
                logger.info(f"[GOV] ToolExecutor 计数已重置 [{session_id}]，续跑")
                # 注入提示让 LLM 知道已经执行了很多步
                llm_messages.append({
                    "role": "system",
                    "content": (
                        "[系统提示：你已经执行了很多步骤。请直接总结当前成果并回复用户，"
                        "如果任务尚未完成，请给出明确的下一步建议，不要继续调用工具。]"
                    ),
                })
                continue
              
              # for 循环被 break 跳出时，也跳出外层 while
              break
            
            # === Phase 4: Self Validation —— 按需验证（System 1 直觉触发）===
            # FIX Phase 1.3: 从"每轮必验"改为"可疑才验"
            # 像人：不会每次做完事都检查一遍，只有感觉"好像不对"时才回头检查
            # 提取用户任务文本（用于判断复杂度）
            _task_text = ""
            for m in reversed(llm_messages):
                if m.get("role") == "user":
                    _task_text = m.get("content", "")
                    break
            
            should_validate = self._should_self_validate(
                full_response=full_response,
                any_tool_error=any_tool_error,
                tool_iterations=i + 1,
                task=_task_text,
            )
            if should_validate and hasattr(self, 'self_validator') and self.self_validator:
                # P0-3 FIX: 自验证异步化 —— 同步执行轻量规则评估，LLM深度评估异步执行
                try:
                    # 1. 同步规则评估（<1ms，零成本）
                    quick_result = self.self_validator._rule_based_validate(
                        _task_text, full_response, "tool_loop"
                    )
                    
                    if not quick_result.completed and quick_result.confidence >= 0.85:
                        # 高置信度问题，立即同步 alert（用户需要立即知道）
                        alert_msg = self.self_validator.format_alert(quick_result)
                        logger.info(f"[VALIDATOR] 规则评估警报 [{session_id}]: {quick_result.reasoning[:80]}")
                        full_response = f"{full_response}\n\n{alert_msg}"
                        await self._simulate_stream(session_id, f"\n{alert_msg}")
                    elif self.self_validator.enable_llm and self.self_validator.llm:
                        # 无法确定，异步执行 LLM 深度评估，不阻塞主流程
                        async def _async_deep_validate():
                            try:
                                _sv_state = await self.state_store.load(session_id)
                                _sv_task = _sv_state.get("task", "")
                                _sv_messages = await self.state_store.get_messages(session_id, limit=20)
                                
                                logger.info(f"[VALIDATOR] 异步自验证触发 [{session_id}]: {should_validate}")
                                val_result = await self.self_validator.validate(
                                    task=_sv_task,
                                    conversation_history=_sv_messages,
                                    response=full_response,
                                    task_type="tool_loop",
                                    tool_history=_tool_history,
                                )
                                
                                if self.self_validator.should_alert_user(val_result):
                                    logger.warning(f"[VALIDATOR] 异步评估发现问题 [{session_id}]: {val_result.reasoning[:80]}")
                                    # 异步评估发现问题，记录日志供后续分析（不修改已发送的响应）
                                else:
                                    logger.debug(f"[VALIDATOR] 异步评估通过 [{session_id}]: confidence={val_result.confidence:.2f}")
                            except Exception as e:
                                logger.debug(f"异步自验证失败: {e}")
                        
                        asyncio.create_task(_async_deep_validate())
                    else:
                        logger.debug(f"[VALIDATOR] 规则评估通过 [{session_id}]，LLM评估未启用")
                except Exception as e:
                    logger.debug(f"Self Validation 初始化失败: {e}")
            else:
                logger.info(f"[VALIDATOR] 自验证跳过 [{session_id}]: tool_error={any_tool_error}, iterations={i+1}")
            
            # 判定任务是否真正成功（不是被截断/失败的）
            _is_success = "❌" not in full_response and "⚠️" not in full_response and "超过上限" not in full_response and "任务已中止" not in full_response
            
            # 静默模式下发送任务完成通知（仅在成功时）
            if silent and _is_success:
                await self.bus.publish(f"governance.stream.{session_id}", json.dumps({
                    "session_id": session_id, "type": "content",
                    "chunk": f"\n✅ {task_type} 任务执行完成\n",
                }).encode())
            
            # 保存 assistant 消息到 state_store
            await self.state_store.append_message(session_id, "assistant", full_response)
            
            # FIX Phase 2.5: Promise Tracker —— 标记任务完成
            if hasattr(self, '_promise_tracker') and self._promise_tracker:
                self._promise_tracker.mark_completed(session_id)
            
            # Phase 5: 生成解释（轻量、不阻塞）
            explanation = ""
            if _is_success and self.explanation_generator:
                try:
                    last_user = state.get("task", "")
                    explanation = await self.explanation_generator.explain(
                        session_id=session_id,
                        user_message=last_user,
                        response=full_response,
                        tools_used=[],  # TODO: collect from tool loop
                        reasoning="",
                    )
                except Exception as e:
                    logger.debug(f"[EXPLAIN] 解释生成失败 [{session_id}]: {e}")
            
            # FIX: 根据实际结果发送正确的状态——失败就发 failed，不是 completed
            if _is_success:
                payload = {
                    "session_id": session_id,
                    "type": "chat.completed",
                    "content": full_response,
                    "reasoning": "",
                }
                if explanation:
                    payload["explanation"] = explanation
                await self.bus.publish(f"governance.response.{session_id}", json.dumps(payload).encode())
                # FIX: session 完成触发背景思考
                self._trigger_background_think("session_completed")
                # Broadcast emotion: task passed
                from tent_os.services.emotion_service import EmotionService
                _es = EmotionService()
                _emotion = _es.update_by_task_action(session_id, "task_passed")
                await self.bus.publish_raw("emotion.broadcast", json.dumps({
                    "user_id": session_id,
                    "emotion": _emotion,
                    "source": "chat_completed"
                }).encode())
            else:
                _error_msg = full_response if "❌" in full_response or "⚠️" in full_response else "任务执行遇到问题"
                logger.warning(f"[GOV] 任务未真正完成 [{session_id}]: {_error_msg[:80]}")
                await self.bus.publish(f"governance.response.{session_id}", json.dumps({
                    "session_id": session_id,
                    "type": "task.failed",
                    "error": _error_msg,
                }).encode())
                # Broadcast emotion: task failed
                from tent_os.services.emotion_service import EmotionService
                _es = EmotionService()
                _emotion = _es.update_by_task_action(session_id, "task_failed")
                await self.bus.publish_raw("emotion.broadcast", json.dumps({
                    "user_id": session_id,
                    "emotion": _emotion,
                    "source": "task_failed"
                }).encode())
            
            # FIX: 意图闭环
            await self._notify_intention_completed(session_id, full_response)
            
            # FIX Phase 3: 记录任务完成统计（用于阈值自适应）
            if hasattr(self, '_adaptive'):
                actual_iterations = i + 1 if 'i' in locals() else 1
                success = "❌" not in full_response and "⚠️" not in full_response
                asyncio.create_task(self._record_task_async(task_type, actual_iterations, success))
            
            # FIX v4.1: 事件驱动触发——同 chat 路径保持一致
            asyncio.create_task(self._ingest_memory(session_id))
            
            error_markers = ["⚠️", "❌", "Failed", "failed", "Error", "error", "不对", "错了"]
            has_error = any(m in full_response for m in error_markers)
            is_significant = task_type != "chat"
            
            if has_error or is_significant:
                asyncio.create_task(self._extract_experience_after_chat(session_id, llm_messages, full_response))
                asyncio.create_task(self._evaluate_rule_compliance(session_id, full_response))
            
        except Exception as e:
            logger.error(f"[GOV] Tool Loop 失败 [{session_id}]: {e}")
            # FIX Phase 3: 记录失败
            if hasattr(self, '_adaptive') and 'task_type' in locals():
                asyncio.create_task(self._record_task_async(task_type, 0, False))
            import traceback
            logger.error(traceback.format_exc())
            await self._send_error(session_id, f"工具执行失败: {e}")
    
    async def _scheduler_dispatch_proxy(self, executor_id: str, action: str, params: Dict) -> Dict:
        """调度进程代理——通过 NATS 向 Scheduler 提交物理执行任务
        
        支持单进程和多进程模式。在多进程模式下，通过 NATS request-reply 等待结果。
        """
        task_id = f"gov_{executor_id}_{action}_{int(time.time()*1000)}"
        reply_topic = f"governance.scheduler.reply.{task_id}"
        session_id = f"scheduler_proxy_{task_id}"
        
        future = asyncio.Future()
        
        async def on_reply(msg):
            try:
                data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
                if not future.done():
                    future.set_result(data)
            except Exception as e:
                if not future.done():
                    future.set_exception(e)
        
        sub = None
        try:
            # 使用核心 NATS 订阅回复主题（比 JetStream 更快，适合 request-reply）
            sub = await self.bus.nats.subscribe(reply_topic, cb=on_reply)
            
            # 通过 JetStream 发布任务（确保持久化）
            await self.bus.publish("scheduler.submit", json.dumps({
                "task_id": task_id,
                "session_id": session_id,
                "executor_id": executor_id,
                "action": action,
                "params": params,
                "reply_to": reply_topic,
                "type": "step_completed"
            }).encode())
            
            logger.info(f"[GOV] 调度任务提交 [{task_id}]: executor={executor_id}, action={action}")
            
            # 等待结果（同步任务通常几秒完成，异步任务返回 pending）
            result = await asyncio.wait_for(future, timeout=self._scheduler_step_timeout)
            
            # 标准化返回格式
            status = result.get("status", "completed")
            if status == "submitted":
                status = "pending"
            
            return {
                "status": status,
                "task_id": task_id,
                "result": result.get("result", result),
                "executor_id": executor_id,
                "action": action,
            }
            
        except asyncio.TimeoutError:
            logger.warning(f"[GOV] 调度任务超时 [{task_id}]")
            return {
                "status": "pending",
                "task_id": task_id,
                "result": {"note": "任务已提交，执行时间较长，请稍后查询状态"},
                "executor_id": executor_id,
                "action": action,
            }
        except Exception as e:
            logger.error(f"[GOV] 调度任务失败 [{task_id}]: {e}")
            return {"status": "error", "error": f"调度失败: {e}"}
        finally:
            if sub:
                try:
                    await sub.unsubscribe()
                except Exception:
                    pass
    
    async def _notify_intention_completed(self, session_id: str, result: str):
        """如果会话关联了意图，通知意图完成"""
        try:
            state = await self.state_store.load(session_id)
            intention_id = state.get("intention_id")
            if intention_id:
                await self.bus.publish("intention.completed", json.dumps({
                    "intention_id": intention_id,
                    "result": result[:200],
                }).encode())
                await self.state_store.update(session_id, {"intention_id": None})
        except Exception:
            pass
    
    async def _process_heartbeat_task(self, session_id: str, content: str, user_id: str):
        """处理 Heartbeat 自主任务
        
        Heartbeat 任务特点：
        - 无前端交互，不发送流式输出到 WebSocket
        - 处理完成后发布结果到 heartbeat 主题
        - 支持工具调用（如检查系统状态、执行维护任务）
        - 完成后清理临时会话
        """
        logger.info(f"[GOV] Heartbeat 处理开始 [{session_id}]")
        try:
            # 组装简单 prompt
            tools = await self._get_available_tools(session_id)
            messages = [
                {"role": "system", "content": f"你是 Tent OS 的自主维护代理。当前任务：{content}\n\n请判断是否需要调用工具来完成此任务。如果不需要工具，直接回复处理结果即可。"},
                {"role": "user", "content": content},
            ]
            
            result_text = ""
            
            if hasattr(self.llm, "chat_with_tools") and tools:
                # 尝试使用工具调用
                result = await self.llm.chat_with_tools(messages, tools)
                tool_calls = result.get("tool_calls", [])
                
                if tool_calls and self.tool_executor:
                    # 执行工具
                    for tc in tool_calls:
                        tool_name = tc["function"]["name"]
                        try:
                            arguments = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            arguments = {}
                        logger.info(f"[GOV] Heartbeat 执行工具 {tool_name} [{session_id}]")
                        tool_result = await self.tool_executor.execute(tool_name, arguments, session_id)
                        messages.append({
                            "role": "user",
                            "content": (
                                f"【工具执行结果 | {tool_name}】\n"
                                f"{tool_result}\n\n"
                                f"---\n"
                                f"[请基于以上工具结果继续判断下一步操作，或直接基于结果回复用户。"
                                f"如果任务已完成，直接给出最终回复，不要重复调用相同工具。]"
                            ),
                        })
                    
                    # 再次调用 LLM 生成最终回复
                    follow_up = await self.llm.chat(messages)
                    result_text = follow_up
                else:
                    result_text = result.get("content", "Heartbeat 检查完成，无需操作。")
            else:
                # 无工具调用支持，直接聊天
                if hasattr(self.llm, "chat"):
                    result_text = await self.llm.chat(messages)
                else:
                    result_text = f"Heartbeat 检查完成: {content[:60]}"
            
            # 保存结果到 state
            await self.state_store.append_message(session_id, "assistant", result_text)
            
            # 发布 heartbeat 完成事件
            await self.bus.publish("heartbeat.completed", json.dumps({
                "session_id": session_id,
                "content": result_text[:500],
                "timestamp": time.time(),
            }).encode())
            
            # 发布到 governance.response（供 API 查询）
            await self.bus.publish(f"governance.response.{session_id}", json.dumps({
                "session_id": session_id,
                "type": "heartbeat.completed",
                "content": result_text,
            }).encode())
            
            # 异步记忆摄入 + 清理
            asyncio.create_task(self._ingest_memory(session_id))
            
            logger.info(f"[GOV] Heartbeat 处理完成 [{session_id}]: {result_text[:80]}")
            
        except Exception as e:
            logger.error(f"[GOV] Heartbeat 处理失败 [{session_id}]: {e}")
            await self.bus.publish("heartbeat.completed", json.dumps({
                "session_id": session_id,
                "error": str(e),
                "timestamp": time.time(),
            }).encode())
    
    async def _handle_complex_task(self, session_id: str, task: str, tools: List[Dict], 
                                    messages: List[Dict]):
        """处理复杂任务——Plan/Execute/Evaluate
        
        FIX v3: 加认知预算。plan生成已有时限（15s），如果降级为单步chat，
        不走调度器异步路径，直接调用 _handle_chat_reply 快速响应。
        """
        import time
        _complex_start = time.time()
        
        # 生成 Plan（已有15秒超时）
        plan = await self.executor.generate_plan(task, tools)
        
        # Broadcast emotion: planning started
        from tent_os.services.emotion_service import EmotionService
        _es = EmotionService()
        _emotion = _es.update_by_task_action(session_id, "task_submitted")
        await self.bus.publish_raw("emotion.broadcast", json.dumps({
            "user_id": session_id,
            "emotion": _emotion,
            "source": "planning_started"
        }).encode())
        
        # FIX v3: 检测是否是超时降级（单步chat plan）
        steps = plan.get("steps", [])
        is_fallback_chat = (
            len(steps) == 1 
            and steps[0].get("action") == "chat" 
            and "超时" in plan.get("analysis", "")
        )
        
        if is_fallback_chat:
            # Plan生成超时降级 → 走Tool Loop让LLM自己判断
            logger.info(f"[GOV] Plan超时降级 → Tool Loop [{session_id}]")
            await self.state_store.update_plan(session_id, plan, step=1)
            return await self._handle_tool_loop(session_id, messages, silent=False, task_type="chat")
        
        await self.state_store.update_plan(session_id, plan, step=1)
        
        # 评估风险
        _state = await self.state_store.load(session_id)
        task_type_for_adapt = _state.get("task_type", "default")
        adaptive_threshold = self._adaptive.get_approval_threshold(task_type_for_adapt) if hasattr(self, '_adaptive') else 0.5
        if self.executor.risk_level(plan) > adaptive_threshold:
            if self.config.get("governance", {}).get("auto_approve", False):
                # FIX: auto_approve模式下直接执行plan，不阻塞
                logger.info(f"[GOV] auto_approve: 跳过Plan风险审批 [{session_id}]")
            else:
                await self.bus.publish("governance.approval.request", json.dumps({
                    "session_id": session_id,
                    "plan": plan,
                    "reply_to": "governance.resume",
                    "type": "approval",
                    "adaptive_threshold": adaptive_threshold,
                }).encode())
                return
        
        await self._execute_plan_steps(session_id, plan)
    
    async def _execute_plan_steps(self, session_id: str, plan: Dict):
        """执行 Plan 的步骤 —— FIX: 单进程模式下直接内部执行，不依赖外部 Scheduler"""
        steps = plan.get("steps", [])
        if not steps:
            return
        
        first_step = steps[0]
        task_id = f"{session_id}_{first_step['step']}"
        
        # FIX: 单进程模式下直接内部执行，不通过 NATS（避免 scheduler 未运行导致卡住）
        asyncio.create_task(self._run_plan_step(session_id, task_id, first_step))
    
    async def _on_task_completed(self, session_id: str, data: Dict):
        task_id = data.get("task_id", "")
        
        # FIX: 幂等检查——防止 session.wake + reply_to 双重触发导致步骤跳过
        dedup_key = f"tent:gov:dedup:{session_id}"
        if hasattr(self.state_store, 'redis') and self.state_store.redis:
            try:
                is_new = await self.state_store.redis.sadd(dedup_key, task_id)
                if not is_new:
                    logger.debug(f"[GOV] 忽略重复的任务完成通知: {task_id} [{session_id}]")
                    return
                await self.state_store.redis.expire(dedup_key, 3600)
            except Exception as e:
                logger.warning(f"[GOV] 幂等检查失败，继续处理: {e}")
        
        state = await self.state_store.load(session_id)
        plan = state.get("plan", {})
        steps = plan.get("steps", [])
        current_step = state.get("step", 1)
        
        # Evaluator 评估
        if self.evaluator and current_step >= len(steps):
            retry_count = await self.state_store.get_retry_count(session_id)
            eval_result = await self.evaluator.evaluate(
                data.get("result", {}), plan, retry_count
            )
            logger.info(f"Evaluator 评估 [{session_id}]: passed={eval_result.passed}, score={eval_result.overall_score:.2f}")
            
            # Phase 1: 保存评估结果到元认知仪表盘
            if self.evaluation_store:
                try:
                    # 获取当前 persona（优先从 multi_persona，回退到 work）
                    current_persona = "work"
                    if self.brain_v2_enabled and self.multi_persona:
                        current_persona = self.multi_persona.current_mode
                    
                    task_summary = state.get("task", "")[:100]
                    user_id = state.get("user_id", "web_user")
                    
                    record = EvaluationRecord(
                        id=f"eval_{session_id}_{int(time.time()*1000)}",
                        timestamp=datetime.now().isoformat(),
                        session_id=session_id,
                        user_id=user_id,
                        persona=current_persona,
                        task_summary=task_summary,
                        passed=eval_result.passed,
                        overall_score=eval_result.overall_score,
                        criteria_scores=eval_result.criteria_scores,
                        feedback=eval_result.feedback,
                        retry_recommended=eval_result.retry_recommended,
                        retry_count=retry_count,
                    )
                    self.evaluation_store.save(record)
                    logger.info(f"[EVAL] 评估结果已保存 [{session_id}]: persona={current_persona}, score={eval_result.overall_score:.2f}")
                except Exception as e:
                    logger.warning(f"[EVAL] 保存评估结果失败: {e}")
            
            if self.experience_extractor and self.procedural_store:
                try:
                    rule = await self.experience_extractor.extract_from_evaluation(
                        state.get("task", ""), plan,
                        data.get("result", {}),
                        {
                            "passed": eval_result.passed,
                            "overall_score": eval_result.overall_score,
                            "criteria_scores": eval_result.criteria_scores,
                            "feedback": eval_result.feedback,
                        }
                    )
                    if rule:
                        self.procedural_store.add_rule(
                            trigger_condition=rule.trigger_condition,
                            action_rule=rule.action_rule,
                            category=rule.category,
                            source_experience=rule.source_experience,
                            confidence=rule.confidence,
                        )
                except Exception as e:
                    logger.warning(f"程序记忆提取失败: {e}")
            
            if not eval_result.passed and self.evaluator.should_retry(eval_result, retry_count):
                await self.state_store.set_retry_count(session_id, retry_count + 1)
                await self.state_store.update_plan(session_id, plan, step=1)
                await self._execute_plan_steps(session_id, plan)
                return
        
        if current_step >= len(steps):
            # 任务完成，把结果作为 assistant 消息追加
            result_text = str(data.get("result", {}))
            await self.state_store.append_message(session_id, "assistant", f"【任务执行完成】\n{result_text}")
            
            await self.bus.publish(f"governance.response.{session_id}", json.dumps({
                "session_id": session_id,
                "type": "task.completed",
                "content": result_text,
            }).encode())
            
            # FIX: 意图闭环
            await self._notify_intention_completed(session_id, result_text)
            
            await self.state_store.clear_retry_count(session_id)
            
            # Phase 1: 任务完成触发六维成长更新
            try:
                from tent_os.services.six_axis_service import SixAxisService
                user_id = state.get("user_id", "web_user")
                task_text = state.get("task", "")
                # 判断任务复杂度（简单启发式）
                complexity = 1.0
                if len(task_text) > 100:
                    complexity = 1.5
                if len(steps) > 3:
                    complexity = 2.0
                SixAxisService.update_by_task_action(
                    user_id, "task_passed_with_praise",
                    {"complexity": complexity}
                )
                logger.info(f"[SIX-AXIS] 任务完成成长更新: {user_id}, complexity={complexity}")
            except Exception as e:
                logger.warning(f"[SIX-AXIS] 任务完成成长更新失败: {e}")
            
            await self._ingest_memory(session_id)
            return
        
        next_step = steps[current_step]
        await self.state_store.advance_step(session_id)
        # FIX: 单进程模式下直接内部执行下一步
        next_task_id = f"{session_id}_{next_step['step']}"
        asyncio.create_task(self._run_plan_step(session_id, next_task_id, next_step))
    
    async def _run_plan_step(self, session_id: str, task_id: str, step: Dict):
        """直接执行 Plan 的单个步骤（单进程模式内部执行）
        
        FIX: 映射 Plan action 名到实际工具名，处理 shell 命令等特殊情况。
        执行完成后，模拟 scheduler 完成通知，调用 _on_task_completed 继续下一步。
        """
        action = step.get("action", "")
        params = step.get("params", {})
        executor_id = step.get("executor", "default")
        
        logger.info(f"[GOV] Plan 步骤执行 [{session_id}]: step={step.get('step')}, action={action}, executor={executor_id}")
        
        # FIX: Plan action → 实际工具名映射
        action_to_tool = {
            "write": "file_write",
            "read": "file_read",
            "list": "directory_list",
            "mkdir": "shell",
            "delete": "shell",
            "rm": "shell",
            "copy": "shell",
            "move": "shell",
            "search": "web_search",
            "fetch": "web_fetch",
            "request": "http_request",
        }
        tool_name = action_to_tool.get(action, action)
        
        # FIX: shell 类命令需要包装成 command 参数
        if tool_name == "shell" and action in ("mkdir", "delete", "rm", "copy", "move"):
            if "command" not in params:
                # 构造默认 shell 命令
                if action == "mkdir":
                    path = params.get("path", "")
                    params = {"command": f"mkdir -p {path}"}
                elif action in ("delete", "rm"):
                    path = params.get("path", "")
                    params = {"command": f"rm -rf {path}"}
        
        result = None
        try:
            if action == "chat":
                # chat 步骤：直接完成，无工具调用
                result = {"status": "completed", "result": {"message": "Chat step completed"}}
            elif self.tool_executor:
                # 工具步骤：通过 ToolExecutor 直接执行
                tool_result = await self.tool_executor.execute(
                    tool_name, params, session_id, max_calls=50
                )
                if isinstance(tool_result, str):
                    result = json.loads(tool_result)
                else:
                    result = tool_result
            else:
                result = {"status": "error", "error": "ToolExecutor 未配置"}
        except Exception as e:
            logger.error(f"[GOV] Plan 步骤执行失败 [{session_id}]: {e}")
            result = {"status": "error", "error": str(e)}
        
        # 模拟 scheduler 完成通知
        completion_data = {
            "task_id": task_id,
            "session_id": session_id,
            "status": result.get("status", "completed"),
            "result": result,
            "type": "step_completed",
        }
        
        # 通过内部调度调用 _on_task_completed，保持与原有架构一致
        await self._scheduler.submit(
            session_id,
            lambda: self._on_task_completed(session_id, completion_data)
        )
    
    async def _handle_approval(self, msg):
        """NATS callback：快速解析 + 入队到 SessionScheduler。"""
        try:
            data = json.loads(msg.data)
        except Exception as e:
            logger.error(f"[GOV] approval 消息解析失败: {e}")
            return
        
        session_id = data.get("session_id")
        if not session_id:
            logger.warning("[GOV] 收到无 session_id 的 approval 消息")
            return
        
        await self._scheduler.submit(
            session_id,
            lambda: self._on_plan_approved(session_id, data)
        )
    
    async def _on_plan_approved(self, session_id: str, data: Dict):
        # FIX Phase 3: 记录审批结果，用于阈值自适应
        approved = data.get("approved", False)
        if hasattr(self, '_adaptive'):
            task_type = "default"  # 简化，实际应从 state 获取
            self._adaptive.record_approval(task_type, approved)
        
        if approved:
            state = await self.state_store.load(session_id)
            plan = state.get("plan")
            await self._execute_plan_steps(session_id, plan)
        else:
            await self.state_store.append_message(session_id, "assistant", "任务已被用户拒绝执行。")
            await self.bus.publish(f"governance.response.{session_id}", json.dumps({
                "session_id": session_id,
                "type": "task.rejected",
                "content": "用户拒绝执行",
            }).encode())
    
    async def _handle_scene_entered(self, msg):
        """处理场景进入事件 —— 切换 AI 人格和策略"""
        try:
            data = json.loads(msg.data)
            scene_id = data.get("scene_id", "")
            scene_name = data.get("scene_name", scene_id)
            persona = data.get("persona", "work")
            user_id = data.get("user_id", "frank")
            
            logger.info(f"[GOV] 场景进入: {scene_name} (persona={persona})")
            
            # 1. 更新用户画像的 active_scene 和 current_persona
            try:
                from tent_os.memory.user_profile import UserProfileStore
                store = UserProfileStore()
                profile = store.get_or_create(user_id)
                profile.active_scene = scene_id
                profile.current_persona = persona
                store._save(profile)
            except Exception as e:
                logger.debug(f"[GOV] 更新用户场景失败: {e}")
            
            # 2. Phase 2: 人格记忆隔离 —— 切换 multi_persona 模式
            if self.brain_v2_enabled and self.multi_persona:
                try:
                    self.multi_persona.force_mode(persona)
                    logger.info(f"[GOV] 人格切换: {self.multi_persona.current_mode} → {persona} (场景: {scene_name})")
                except Exception as e:
                    logger.warning(f"[GOV] 人格切换失败: {e}")
            
            # 2.1 同步更新 EmotionService 的 persona 状态（供前端 API 读取）
            try:
                from tent_os.services.emotion_service import EmotionService
                emotion_svc = EmotionService()
                emotion_svc.set_persona(user_id, persona)
                # FIX: 前端 API 使用 "web_user" 作为默认 user_id，同步设置
                emotion_svc.set_persona("web_user", persona)
            except Exception as e:
                logger.debug(f"[GOV] 更新 EmotionService persona 失败: {e}")
            
            # 3. 发布人格切换事件（供前端 CanvasAvatar 响应）
            await self.bus.publish_raw("emotion.broadcast", json.dumps({
                "user_id": user_id,
                "emotion": "happy",
                "persona": persona,
                "reason": f"进入{scene_name}",
            }).encode())
            
            # 4. 如果场景有自动动作需要 LLM 理解，生成一条系统消息
            # MVP 阶段：简单记录，不触发 LLM 调用（避免成本）
            logger.info(f"[GOV] 场景 {scene_name} 人格切换为: {persona}")
            
        except Exception as e:
            logger.warning(f"[GOV] 场景进入处理失败: {e}")
    
    async def _handle_scene_left(self, msg):
        """处理场景离开事件 —— Phase 3: 可控遗忘"""
        try:
            data = json.loads(msg.data)
            scene_name = data.get("scene_name", "")
            persona = data.get("persona", "work")
            duration = data.get("duration_minutes", 0)
            user_id = data.get("user_id", "frank")
            logger.info(f"[GOV] 场景离开: {scene_name} (停留 {duration} 分钟, persona={persona})")
            
            # Phase 3: 可控遗忘 —— 场景离开时整理该人格的短期记忆
            try:
                memory_path = self.config.get("memory", {}).get("storage_path", "./tent_memory")
                from tent_os.memory.index import MemoryIndex
                index = MemoryIndex(memory_path)
                
                # 1. 自动降温：长期未访问的 HOT 记忆降级为 WARM
                demoted = index.auto_demote(days_inactive=7)  # 7天未访问即降级（场景离开时更激进）
                if demoted:
                    logger.info(f"[FORGET] 场景离开自动降温: {len(demoted)} 条记忆从 HOT → WARM")
                
                # 2. 记录整理日志（供仪表盘展示）
                if not hasattr(self, '_memory_maintenance_log'):
                    self._memory_maintenance_log = []
                self._memory_maintenance_log.append({
                    "timestamp": datetime.now().isoformat(),
                    "event": "scene_left_demote",
                    "scene": scene_name,
                    "persona": persona,
                    "demoted_count": len(demoted),
                    "reason": f"离开{scene_name}，整理{persona}人格记忆",
                })
                # 只保留最近 50 条日志
                self._memory_maintenance_log = self._memory_maintenance_log[-50:]
                
            except Exception as e:
                logger.debug(f"[FORGET] 场景离开记忆整理失败: {e}")
            
        except Exception as e:
            logger.warning(f"[GOV] 场景离开处理失败: {e}")
    
    async def _handle_scene_action(self, msg):
        """处理场景自动动作"""
        try:
            data = json.loads(msg.data)
            scene_id = data.get("scene_id", "")
            action = data.get("action", "")
            user_id = data.get("user_id", "frank")
            
            logger.info(f"[GOV] 场景动作: {action} @ {scene_id}")
            
            # MVP 阶段：动作转换为治理请求，由 PlanExecuteExecutor 处理
            # 例如 "开灯" → 找到对应设备的 executor → 提交任务
            session_id = f"scene_action_{scene_id}_{int(time.time())}"
            
            # 发布 governance.request 让系统处理
            await self.bus.publish("governance.request", json.dumps({
                "session_id": session_id,
                "user_id": user_id,
                "content": f"[场景自动动作] {action}",
                "source": "scene_auto",
                "scene_id": scene_id,
            }).encode())
            
        except Exception as e:
            logger.warning(f"[GOV] 场景动作处理失败: {e}")
    
    async def _record_task_async(self, task_type: str, iterations: int, success: bool):
        """异步记录任务统计（用于阈值自适应）"""
        try:
            if hasattr(self, '_adaptive') and self._adaptive:
                self._adaptive.record_task_completion(task_type, iterations, success)
        except Exception as e:
            logger.debug(f"记录任务统计失败: {e}")
    
    async def _ingest_memory(self, session_id: str):
        """异步保存对话到记忆系统——System 1 直觉门控 + 增量摄入
        
        FIX Phase 2: 从"无条件全量摄入"改为"值得才摄入"。
        FIX v6: 同时提取关键事实保存到 UserProfileStore，实现跨session持久记忆。
        FIX v7: 增量摄入——记录上次摄入的消息数量，只摄入新增消息，避免同一对话被存储 N 次。
        像人：写日记只写今天新发生的事，不是把整本日记重写一遍。
        """
        try:
            messages = await self.state_store.get_messages(session_id)
            
            # 去重：只保留 user/assistant 消息，过滤 system/tool
            valuable_messages = [
                m for m in messages
                if m.get("role") in ("user", "assistant")
            ]
            current_count = len(valuable_messages)
            
            # FIX v7: 增量摄入——获取上次摄入的消息数量
            state = await self.state_store.load(session_id) or {}
            last_count = state.get("_ingested_message_count", 0)
            
            if current_count <= last_count:
                logger.info(f"[GOV] 记忆摄入跳过 [{session_id}]: 无新增消息 (last={last_count}, current={current_count})")
                return
            
            # 只取新增的消息
            new_messages = valuable_messages[last_count:]
            
            # System 1 直觉：判断新增对话是否值得摄入记忆
            if not self._should_ingest_memory(new_messages):
                logger.info(f"[GOV] 记忆摄入跳过 [{session_id}]: 直觉过滤")
                # 仍然更新计数，避免下次重复检查相同内容
                await self.state_store.update(session_id, {"_ingested_message_count": current_count})
                return
            
            if len(new_messages) < 1:
                logger.info(f"[GOV] 记忆摄入跳过 [{session_id}]: 无新增有效消息")
                return
            
            user_id = state.get("user_id", "anonymous")
            
            # FIX v6: 同时保存到 UserProfileStore 实现跨session持久记忆
            if user_id and user_id != "anonymous" and hasattr(self, 'user_profile_store') and self.user_profile_store:
                try:
                    await asyncio.to_thread(
                        self._extract_and_record_events,
                        user_id, session_id, new_messages
                    )
                except Exception as e:
                    logger.debug(f"[GOV] 事件提取失败 [{session_id}]: {e}")
            
            # Phase 2: 人格记忆隔离 —— 传递当前 persona
            current_persona = "work"
            if self.brain_v2_enabled and self.multi_persona:
                current_persona = self.multi_persona.current_mode
            
            # FIX v7: 只发送新增消息，避免重复摄入
            await self.bus.publish("memory.ingest", json.dumps({
                "session_id": session_id,
                "user_id": user_id,
                "messages": new_messages,
                "ingested_at": time.time(),
                "persona": current_persona,
            }).encode())
            
            # 更新摄入计数
            await self.state_store.update(session_id, {"_ingested_message_count": current_count})
            
            logger.info(f"[GOV] 记忆摄入完成 [{session_id}]: {len(new_messages)} 条新增消息 (总计 {current_count})")
        except Exception as e:
            logger.warning(f"记忆摄入失败 [{session_id}]: {e}")
    
    def _extract_and_record_events(self, user_id: str, session_id: str, messages: List[Dict]):
        """从对话中提取关键事实并保存到 UserProfileStore——System 1 直觉提取
        
        FIX v6: 从 user + assistant 双方消息中提取，避免遗漏文件名等关键信息。
        像人：聊天时听到"我在做项目A"会默默记在小本本上，
        不需要等对方说"请记住"。
        """
        if not hasattr(self, 'user_profile_store') or not self.user_profile_store:
            return
        
        # 合并 user 和 assistant 的消息文本（排除 system/tool）
        all_text = " ".join([m.get("content", "") for m in messages if m.get("role") in ("user", "assistant")])
        
        def _importance_to_severity(imp: int) -> str:
            if imp >= 8: return "critical"
            if imp >= 6: return "high"
            if imp >= 4: return "normal"
            return "low"
        
        # 模式1：项目定义——"项目A：xxx"、"项目B是xxx"
        project_patterns = [
            r'项目([A-Za-z0-9一二三四五六七八九十]+)[：:]\s*(.{3,80})',
            r'项目([A-Za-z0-9一二三四五六七八九十]+)[是:]\s*(.{3,80})',
        ]
        for pattern in project_patterns:
            for match in re.finditer(pattern, all_text):
                proj_id = match.group(1)
                proj_desc = match.group(2).strip()
                if len(proj_desc) > 5:
                    event = f"项目{proj_id}：{proj_desc}"
                    self.user_profile_store.add_event(user_id, event, severity=_importance_to_severity(8))
                    logger.info(f"[GOV] 记录项目事件 [{user_id}]: {event[:60]}")
        
        # 模式2：文件生成任务——生成了什么文件（更宽松的正则）
        file_patterns = [
            r'文件名[用是]?\s*[\'\"`]?([A-Za-z0-9_\-]+)[\'\"`]?',
            r'文件保存[为到]?\s*[\'\"`]?([A-Za-z0-9_\-]+)[\'\"`]?',
            r'生成.{0,20}(PPT|Word|HTML|网页|文档|合同|报告)',
            r'(PPT|Word|HTML|网页|文档|合同|报告).{0,20}文件名',
        ]
        for pattern in file_patterns:
            for match in re.finditer(pattern, all_text, re.IGNORECASE):
                event = f"文件任务：{match.group(0)}"
                self.user_profile_store.add_event(user_id, event, severity=_importance_to_severity(7))
        
        # 模式3：明确记忆指令——"请记住"、"记住"
        memory_patterns = [
            r'(?:请?记住|请记住|别忘了|不要忘记)[：:,，]?\s*(.{5,100})',
        ]
        for pattern in memory_patterns:
            for match in re.finditer(pattern, all_text):
                event = match.group(1).strip()
                if len(event) > 5:
                    self.user_profile_store.add_event(user_id, f"记住：{event}", severity=_importance_to_severity(9))
                    logger.info(f"[GOV] 记录记忆指令 [{user_id}]: {event[:60]}")
        
        # 模式4：关键实体——合作方、品牌、页面功能等
        entity_patterns = [
            r'合作方[是:]\s*[\'\"`]?([^\'\"`\n，。]{2,30})[\'\"`]?',
            r'(?:我方|甲方|乙方)[是:]\s*[\'\"`]?([^\'\"`\n，。]{2,30})[\'\"`]?',
            r'品牌[名称]?[是:]\s*[\'\"`]?([^\'\"`\n，。]{2,20})[\'\"`]?',
            r'(?:页面|功能).{0,5}[：:]\s*(.{3,50})',
        ]
        for pattern in entity_patterns:
            for match in re.finditer(pattern, all_text):
                event = match.group(0)
                self.user_profile_store.add_event(user_id, event, severity=_importance_to_severity(7))
    
    def _should_ingest_memory(self, messages: List[Dict]) -> bool:
        """System 1 直觉——判断对话是否值得摄入记忆
        
        原则：只检查最近一轮对话，不检查全部历史。
        像人：写日记只写今天发生的事，不是把整本日记重写一遍。
        
        返回: True/False
        """
        # 只取最近一轮对话（最后 2-4 条 user/assistant 消息）
        recent_messages = [
            m for m in messages
            if m.get("role") in ("user", "assistant")
        ][-4:]  # 最多最近 4 条
        
        chat_text = " ".join([
            m.get("content", "") for m in recent_messages
        ]).lower()
        
        # 规则0：包含明确的记忆指令 → 强制摄入（最高优先级）
        memory_keywords = ['请记住', '记住这个', '记住', '别忘了', '不要忘记', '记下来']
        if any(kw in chat_text for kw in memory_keywords):
            return True
        
        # 规则1：纯问候/闲聊 → 不摄入
        if len(chat_text) < 40:
            greeting_keywords = ['你好', '您好', 'hi', 'hello', '在吗', '在嘛', 
                                '早上好', '下午好', '晚上好', '拜拜', '再见']
            greeting_count = sum(1 for g in greeting_keywords if g in chat_text)
            if greeting_count >= 1 and len(chat_text) < 30:
                return False
        
        # 规则2：太短 → 不摄入
        if len(chat_text) < 15:
            return False
        
        # 规则3：无意义重复 → 不摄入
        words = [w for w in chat_text.split() if len(w) > 1]
        if len(set(words)) < 3:
            return False
        
        # 默认：值得摄入
        return True
    
    async def _extract_experience_after_chat(self, session_id: str, messages: List[Dict], response: str):
        """对话结束后提取经验规则——System 3 元认知 gated
        
        FIX Phase 1.2: 从"每轮必提"改为"直觉过滤 + 可疑才提"
        像人：不会把每次闲聊都当作人生经验，只有"搞砸了"、"学到了"、"用户明确要求"才记住。
        """
        if not self.experience_extractor or not self.procedural_store:
            return
        try:
            if len(messages) < 2:
                return
            
            # System 3 直觉：判断这段对话是否值得提取
            extraction_signal = self._should_extract_experience(messages, response)
            if not extraction_signal:
                logger.info(f"[GOV] 经验提取跳过 [{session_id}]: 直觉过滤")
                return
            
            logger.info(f"[GOV] 经验提取触发 [{session_id}]: {extraction_signal}")
            
            rule = await self.experience_extractor.extract_from_chat(messages, response)
            if rule:
                self.procedural_store.add_rule(
                    trigger_condition=rule.trigger_condition,
                    action_rule=rule.action_rule,
                    category=rule.category,
                    source_experience=rule.source_experience,
                    confidence=rule.confidence,
                )
                logger.info(f"[GOV] 提取程序记忆规则: {rule.trigger_condition[:50]}")
        except Exception as e:
            logger.warning(f"经验提取失败 [{session_id}]: {e}")
    
    def _should_extract_experience(self, messages: List[Dict], response: str) -> str:
        """System 3 直觉——判断对话是否值得提取为经验
        
        返回: 触发原因字符串，或空字符串（跳过）
        """
        # 只检查用户消息和助手回复（忽略 system/tool 消息）
        all_text = " ".join([
            m.get("content", "") for m in messages
            if m.get("role") in ("user", "assistant")
        ] + [response]).lower()
        
        # 信号1：用户明确要求记住
        explicit_memo = ['记住', '记下来', '记住这个', 'save this', 'remember this',
                        '下次也这样', '以后要', 'always do']
        if any(kw in all_text for kw in explicit_memo):
            return "explicit_request"
        
        # 信号2：包含错误/失败/修复（值得学习的负面经验）
        error_signals = ['错误', '报错', '失败', 'exception', 'error', 'failed',
                        '不对', '搞错了', 'fix', '修复', 'bug', '问题']
        if any(kw in all_text for kw in error_signals):
            return "error_lesson"
        
        # 信号3：包含成功解决复杂问题的描述
        success_signals = ['终于', '搞定', '解决了', '成功了', '完美', 'works now',
                          '搞定了', '可以了']
        complex_signals = ['尝试', '方法', '方案', '步骤', '配置', '调试']
        if any(s in all_text for s in success_signals) and any(c in all_text for c in complex_signals):
            return "success_pattern"
        
        # 信号4：用户偏好/习惯（个性化）
        preference_signals = ['我喜欢', '我不喜欢', 'prefer', '不喜欢', '习惯', '总是',
                             '别给我', '只要', 'only want', 'please use']
        if any(kw in all_text for kw in preference_signals):
            return "user_preference"
        
        # 默认：不值得提取（90% 过滤率）
        return ""
    
    def _compute_rule_similarity(self, rule_text: str, response_text: str) -> float:
        """计算规则与回复的语义相似度（基于同义词扩展 + Jaccard）
        
        FIX Phase 6: 替代粗糙的关键词匹配，理解同义词和近义表达。
        """
        try:
            from tent_os.llm.embedding_tfidf import SynonymExpander
            
            # 同义词扩展（让"备份"和"存档"被视为相关）
            t1 = SynonymExpander.expand(rule_text.lower())
            t2 = SynonymExpander.expand(response_text.lower())
            
            # Tokenize：英文单词 + 中文字符
            words1 = set(re.findall(r'[a-z_]{2,}', t1)) | set(re.findall(r'[\u4e00-\u9fff]', t1))
            words2 = set(re.findall(r'[a-z_]{2,}', t2)) | set(re.findall(r'[\u4e00-\u9fff]', t2))
            
            if not words1 or not words2:
                return 0.0
            
            # Jaccard 相似度 + 加权（交集越大、越重要）
            intersection = words1 & words2
            union = words1 | words2
            
            if not union:
                return 0.0
            
            jaccard = len(intersection) / len(union)
            
            # 额外加权：如果规则中的核心动词在回复中出现，提升相似度
            core_verbs = {"备份", "删除", "检查", "验证", "确认", "执行", "保存", "更新", "创建", "修改", "backup", "delete", "check", "verify", "confirm", "execute", "save", "update", "create", "modify"}
            rule_verbs = words1 & core_verbs
            if rule_verbs and rule_verbs.issubset(words2):
                jaccard = min(1.0, jaccard + 0.2)  # 核心动词匹配，加 20%
            
            return jaccard
        except Exception:
            return 0.0
    
    async def _evaluate_rule_compliance(self, session_id: str, response: str):
        """规则反馈闭环：检测 LLM 是否遵循了注入的程序记忆规则
        
        FIX Phase 6: 用语义相似度替代关键词匹配，更准确、更鲁棒。
        """
        if not self.procedural_store:
            return
        try:
            state = await self.state_store.load(session_id)
            injected_rules = state.get("injected_rules", [])
            if not injected_rules:
                return
            
            complied_count = 0
            
            for rule_id, action_rule in injected_rules:
                if not rule_id or not action_rule:
                    continue
                
                # 判断规则类型
                negative_keywords = {"避免", "不要", "禁止", "勿", "不应", "不能"}
                is_negative = any(kw in action_rule for kw in negative_keywords)
                
                # FIX Phase 6: 语义相似度计算
                similarity = self._compute_rule_similarity(action_rule, response)
                
                # 判断遵循情况
                if is_negative:
                    # 负向规则：语义相似度高 = 回复"踩线"了 = 未遵循
                    followed = similarity < 0.4
                else:
                    # 正向规则：语义相似度高 = 遵循了规则精神
                    followed = similarity >= 0.35
                
                self.procedural_store.record_outcome(rule_id, success=followed)
                status = "✅遵循" if followed else "❌未遵循"
                logger.info(f"[GOV] 规则反馈 [{session_id}] rule#{rule_id}: {status} (语义相似度 {similarity:.0%})")
                
                if followed:
                    complied_count += 1
            
            if injected_rules:
                logger.info(f"[GOV] 规则闭环完成 [{session_id}]: {complied_count}/{len(injected_rules)} 条规则被遵循")
                
        except Exception as e:
            logger.warning(f"规则反馈检测失败 [{session_id}]: {e}")
    
    async def _send_error(self, session_id: str, error_msg: str):
        """发送错误响应"""
        self._recent_error_count[session_id] += 1  # FIX: 真正计数错误（按session）
        # FIX Phase 1.4: 错误率上升时触发背景思考
        self._check_should_trigger_think()
        await self.bus.publish(f"governance.response.{session_id}", json.dumps({
            "session_id": session_id,
            "type": "error",
            "content": error_msg,
        }).encode())
