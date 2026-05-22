"""Plugin Manager —— 动态加载外部插件

支持两种加载方式：
1. 配置驱动：从 tent_os.yaml 的 plugins 列表加载
2. 目录扫描：自动扫描 plugins/ 目录下的 Python 文件

安全规则：
- 外部插件必须通过 plugins/ 目录加载
- 内置插件（tent_os/plugins/）和外部插件隔离
- 插件初始化后注册到 Scheduler 作为执行者
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Optional

from tent_os.logging_config import get_logger
from tent_os.plugins.base import ExecutorPlugin

logger = get_logger()


class PluginLoadError(Exception):
    """插件加载失败"""
    pass


class PluginManager:
    def __init__(self, plugin_dirs: List[str] = None):
        """
        Args:
            plugin_dirs: 插件目录列表，默认 ["./plugins"]
        """
        self.plugin_dirs = [Path(d) for d in (plugin_dirs or ["./plugins"])]
        self.executors: Dict[str, ExecutorPlugin] = {}
        self._loaded_modules: set = set()
    
    async def scan_and_load(self, config: Dict = None) -> int:
        """扫描所有插件目录并加载
        
        Returns:
            加载的插件数量
        """
        count = 0
        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                logger.info(f"插件目录不存在，跳过: {plugin_dir}")
                continue
            count += await self._scan_directory(plugin_dir, config)
        
        # 同时加载内置插件（tent_os/plugins/ 下的模块）
        builtin_dir = Path(__file__).parent
        count += await self._load_builtin_plugins(builtin_dir, config)
        
        logger.info(f"共加载 {count} 个插件执行者: {list(self.executors.keys())}")
        return count
    
    async def _scan_directory(self, plugin_dir: Path, config: Dict = None) -> int:
        """扫描目录下的 Python 文件并加载"""
        count = 0
        for py_file in plugin_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                executor = await self._load_from_file(py_file, config)
                if executor:
                    self.executors[executor.name()] = executor
                    count += 1
                    logger.info(f"加载外部插件: {executor.name()} v{executor.version()}")
            except Exception as e:
                logger.warning(f"加载插件失败 {py_file}: {e}")
        return count
    
    async def _load_from_file(self, py_file: Path, config: Dict = None) -> Optional[ExecutorPlugin]:
        """从单个 Python 文件加载插件"""
        module_name = f"tent_os_external_plugin_{py_file.stem}"
        
        # 避免重复加载
        if module_name in self._loaded_modules:
            return None
        
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if not spec or not spec.loader:
            raise PluginLoadError(f"无法读取文件: {py_file}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        self._loaded_modules.add(module_name)
        
        # 查找 ExecutorPlugin 子类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, ExecutorPlugin) and 
                attr is not ExecutorPlugin):
                plugin = attr()
                plugin_config = config.get(plugin.name(), {}) if config else {}
                await plugin.initialize(plugin_config)
                return plugin
        
        return None
    
    async def _load_builtin_plugins(self, builtin_dir: Path, config: Dict = None) -> int:
        """加载内置插件（tent_os/plugins/ 下的模块）"""
        count = 0
        # 内置插件通过 import 方式加载
        for py_file in builtin_dir.glob("*.py"):
            if py_file.name.startswith(("_", "base", "manager")):
                continue
            try:
                module_name = f"tent_os.plugins.{py_file.stem}"
                if module_name in self._loaded_modules:
                    continue
                module = importlib.import_module(module_name)
                self._loaded_modules.add(module_name)
                
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, ExecutorPlugin) and 
                        attr is not ExecutorPlugin):
                        plugin = attr()
                        plugin_config = config.get(plugin.name(), {}) if config else {}
                        await plugin.initialize(plugin_config)
                        self.executors[plugin.name()] = plugin
                        count += 1
                        logger.info(f"加载内置插件: {plugin.name()} v{plugin.version()}")
            except Exception as e:
                logger.debug(f"加载内置插件失败 {py_file}: {e}")
        return count
    
    async def load_from_config(self, config_path: str):
        """从配置文件加载（兼容旧接口）"""
        try:
            import yaml
            config = yaml.safe_load(Path(config_path).read_text())
            await self.scan_and_load(config)
        except Exception as e:
            logger.warning(f"从配置文件加载插件失败: {e}")
    
    def get_executor(self, name: str) -> Optional[ExecutorPlugin]:
        return self.executors.get(name)
    
    def list_plugins(self) -> List[Dict]:
        """列出所有已加载的插件"""
        return [
            {
                "name": name,
                "version": ex.version(),
                "actions": ex.supported_actions(),
            }
            for name, ex in self.executors.items()
        ]
