"""热重载 —— 开发模式自动重启

用法:
    tent-os run --reload

监控 tent_os/ 目录下的 .py 文件变化，变化时自动重启整个进程。
零额外依赖，跨平台。
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional


class FileWatcher:
    """纯 Python 文件监控器"""
    
    def __init__(self, paths: List[str], interval: float = 1.0, patterns: tuple = (".py",)):
        self.paths = [Path(p) for p in paths]
        self.interval = interval
        self.patterns = patterns
        self._mtimes: dict = {}
        self._running = False
    
    def _collect_files(self) -> List[Path]:
        """收集所有监控的文件"""
        files = []
        for p in self.paths:
            if p.is_file() and p.suffix in self.patterns:
                files.append(p)
            elif p.is_dir():
                for pattern in self.patterns:
                    files.extend(p.rglob(f"*{pattern}"))
        return files
    
    def _get_mtime(self, path: Path) -> float:
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0
    
    def snapshot(self):
        """创建当前文件状态快照"""
        self._mtimes = {}
        for f in self._collect_files():
            self._mtimes[str(f)] = self._get_mtime(f)
    
    def has_changed(self) -> bool:
        """检查是否有文件发生变化"""
        current_files = {str(f) for f in self._collect_files()}
        
        # 检查新增或修改的文件
        for f in current_files:
            mtime = self._get_mtime(Path(f))
            if f not in self._mtimes or self._mtimes[f] != mtime:
                return True
        
        # 检查删除的文件
        for f in list(self._mtimes.keys()):
            if f not in current_files:
                return True
        
        return False
    
    async def watch(self, on_change: Callable):
        """开始监控循环"""
        self.snapshot()
        self._running = True
        while self._running:
            await asyncio.sleep(self.interval)
            if self.has_changed():
                self.snapshot()
                on_change()
    
    def stop(self):
        self._running = False


async def run_with_reload(target: Callable, watch_paths: Optional[List[str]] = None):
    """运行目标函数，文件变化时自动重启
    
    Args:
        target: 异步函数，会被反复调用直到进程退出
        watch_paths: 监控的目录/文件列表，默认 ["./tent_os"]
    """
    paths = watch_paths or ["./tent_os"]
    watcher = FileWatcher(paths, interval=1.0)
    
    restart_event = asyncio.Event()
    
    def on_change():
        print("\n🔁 文件变化检测到，正在重启...\n")
        restart_event.set()
    
    # 启动监控任务
    watch_task = asyncio.create_task(watcher.watch(on_change))
    
    try:
        while True:
            restart_event.clear()
            
            # 创建目标任务的 future
            task_future = asyncio.ensure_future(target())
            
            # 等待任务完成或重启事件
            done, pending = await asyncio.wait(
                [task_future, asyncio.ensure_future(restart_event.wait())],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消未完成的任务
            for fut in pending:
                fut.cancel()
            
            # 如果目标任务完成了（不是重启触发的），直接退出
            if task_future in done:
                try:
                    await task_future
                except asyncio.CancelledError:
                    pass
                break
            
            # 重启：取消目标任务
            if not task_future.done():
                task_future.cancel()
                try:
                    await task_future
                except asyncio.CancelledError:
                    pass
            
            # 给进程一点时间清理
            await asyncio.sleep(0.5)
    
    finally:
        watcher.stop()
        watch_task.cancel()
        try:
            await watch_task
        except asyncio.CancelledError:
            pass
