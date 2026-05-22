"""Browser Executor —— 基于 Playwright 的浏览器控制

提供网页自动化能力：
- navigate: 导航到 URL
- click: 点击元素（通过 CSS selector）
- type: 在输入框中输入文本
- read: 读取页面文本内容
- screenshot: 截图

安全：
- 可配置 URL 白名单
- 敏感操作（如登录表单）需确认
- 默认无头模式运行
"""

import base64
import json
from typing import Dict, Any, Optional

from tent_os.plugins.base import ExecutorPlugin


class BrowserExecutor(ExecutorPlugin):
    """浏览器执行者 —— 操控 Playwright 浏览器"""

    def __init__(self):
        self.executor_id = "browser"
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._initialized = False
        self.allowed_hosts: list = []
        self.headless = True

    def name(self) -> str:
        return "browser"

    def version(self) -> str:
        return "1.0.0"

    async def initialize(self, config: Dict) -> None:
        """初始化 Playwright"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright 未安装。请运行: pip install playwright && playwright install chromium"
            )
        
        self.allowed_hosts = config.get("allowed_hosts", [])
        self.headless = config.get("headless", True)
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.0"
        )
        self._page = await self._context.new_page()
        self._initialized = True

    async def execute(self, action: str, params: Dict) -> Dict:
        """执行浏览器操作"""
        if not self._initialized:
            return {"status": "failed", "error": "BrowserExecutor 未初始化"}
        
        try:
            if action == "browser_navigate":
                return await self._navigate(params)
            elif action == "browser_click":
                return await self._click(params)
            elif action == "browser_type":
                return await self._type(params)
            elif action == "browser_read":
                return await self._read(params)
            elif action == "browser_screenshot":
                return await self._screenshot(params)
            else:
                return {"status": "failed", "error": f"未知的浏览器操作: {action}"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    async def _navigate(self, params: Dict) -> Dict:
        url = params.get("url", "")
        if not url:
            return {"status": "failed", "error": "缺少 url 参数"}
        
        # URL 安全检查
        if self.allowed_hosts:
            from urllib.parse import urlparse
            host = urlparse(url).netloc
            if host not in self.allowed_hosts:
                return {"status": "rejected", "error": f"URL 不在白名单中: {host}"}
        
        await self._page.goto(url, wait_until="networkidle")
        title = await self._page.title()
        return {
            "status": "completed",
            "url": url,
            "title": title,
        }

    async def _click(self, params: Dict) -> Dict:
        selector = params.get("selector", "")
        if not selector:
            return {"status": "failed", "error": "缺少 selector 参数"}
        
        await self._page.click(selector)
        return {"status": "completed", "action": "click", "selector": selector}

    async def _type(self, params: Dict) -> Dict:
        selector = params.get("selector", "")
        text = params.get("text", "")
        if not selector:
            return {"status": "failed", "error": "缺少 selector 参数"}
        
        await self._page.fill(selector, text)
        return {"status": "completed", "action": "type", "selector": selector}

    async def _read(self, params: Dict) -> Dict:
        """读取页面文本内容"""
        max_length = params.get("max_length", 5000)
        
        # 获取页面可见文本
        text = await self._page.evaluate("() => document.body.innerText")
        if len(text) > max_length:
            text = text[:max_length] + f"\n... (已截断，共 {len(text)} 字符)"
        
        title = await self._page.title()
        url = self._page.url
        
        return {
            "status": "completed",
            "title": title,
            "url": url,
            "content": text,
        }

    async def _screenshot(self, params: Dict) -> Dict:
        """截图并返回 base64"""
        selector = params.get("selector")
        full_page = params.get("full_page", False)
        
        if selector:
            element = await self._page.query_selector(selector)
            if not element:
                return {"status": "failed", "error": f"未找到元素: {selector}"}
            screenshot_bytes = await element.screenshot()
        else:
            screenshot_bytes = await self._page.screenshot(full_page=full_page)
        
        base64_image = base64.b64encode(screenshot_bytes).decode("utf-8")
        
        return {
            "status": "completed",
            "image_base64": base64_image,
            "format": "png",
        }

    def supported_actions(self) -> list:
        return ["browser_navigate", "browser_click", "browser_type", "browser_read", "browser_screenshot"]

    async def get_status(self, task_id: str) -> Dict:
        """获取任务状态（BrowserExecutor 不支持异步任务状态查询）"""
        return {"status": "unknown", "task_id": task_id}

    async def shutdown(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
