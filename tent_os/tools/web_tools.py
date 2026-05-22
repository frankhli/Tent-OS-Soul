"""Web 工具 —— 搜索 + 抓取，零 API Key

原则：除了 LLM，其他功能都不应需要额外 API Key。
- web_search: Bing HTML 搜索（DuckDuckGo 在中国大陆网络不可达，改用 Bing）
- web_fetch: httpx 直接抓取 + 简单文本提取
"""

import json
import re
import urllib.parse
from typing import List, Dict, Optional

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


async def web_search(query: str, limit: int = 5) -> Dict:
    """Bing HTML 免费搜索
    
    无需 API Key，无配额限制。
    返回标题/URL/摘要列表。
    """
    if not HTTPX_AVAILABLE:
        return {"status": "error", "error": "httpx 未安装"}
    
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            # Bing HTML 搜索（中国大陆网络可达）
            params = {
                "q": query,
            }
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            resp = await client.get(
                "https://www.bing.com/search",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            html = resp.text
            
            # 解析结果
            results = _parse_bing_html(html, limit)
            
            return {
                "status": "completed",
                "query": query,
                "results": results,
                "total": len(results),
            }
    except Exception as e:
        return {"status": "error", "error": f"搜索失败: {e}"}


def _parse_bing_html(html: str, limit: int) -> List[Dict]:
    """解析 Bing HTML 搜索结果"""
    results = []
    
    # Bing 结果块: <li class="b_algo" ...>...</li>
    result_blocks = re.findall(
        r'<li class="b_algo"[^>]*>(.*?)</li>',
        html,
        re.DOTALL,
    )
    
    for block in result_blocks[:limit]:
        # 提取标题和链接
        title_match = re.search(
            r'<h2[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?</h2>',
            block,
            re.DOTALL,
        )
        if not title_match:
            continue
        
        url = title_match.group(1).strip()
        # Bing 有时返回相对路径或跳转链接，处理一下
        real_url = _normalize_url(url)
        
        title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()
        
        # 提取摘要
        snippet_match = re.search(
            r'<p[^>]*>(.*?)</p>',
            block,
            re.DOTALL,
        )
        snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip() if snippet_match else ""
        
        if title and real_url:
            results.append({
                "title": title,
                "url": real_url,
                "snippet": snippet,
            })
    
    return results


def _normalize_url(url: str) -> str:
    """规范化 URL（处理相对路径、Bing 跳转等）"""
    if not url:
        return ""
    # 已经是完整 URL
    if url.startswith('http'):
        return url
    # 协议相对路径
    if url.startswith('//'):
        return 'https:' + url
    # 相对路径（少见）
    if url.startswith('/'):
        return 'https://www.bing.com' + url
    return url


async def web_fetch(url: str, max_chars: int = 8000) -> Dict:
    """抓取网页内容
    
    用 httpx 获取 HTML，提取正文文本。
    无需 API Key。
    """
    if not HTTPX_AVAILABLE:
        return {"status": "error", "error": "httpx 未安装"}
    
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
            
            # 提取正文
            text = _extract_text_from_html(html, max_chars)
            
            # 提取标题
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ""
            
            return {
                "status": "completed",
                "url": url,
                "title": title,
                "content": text,
                "truncated": len(html) > max_chars * 2,
            }
    except Exception as e:
        return {"status": "error", "error": f"抓取失败: {e}"}


def _extract_text_from_html(html: str, max_chars: int) -> str:
    """从 HTML 中提取可读文本"""
    # 1. 移除 script/style 标签及其内容
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. 移除所有标签
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # 3. 解码 HTML 实体
    import html as html_module
    text = html_module.unescape(text)
    
    # 4. 规范化空白
    text = re.sub(r'\s+', ' ', text).strip()
    
    # 5. 截断
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[内容已截断，如需完整内容请直接访问原文]"
    
    return text
