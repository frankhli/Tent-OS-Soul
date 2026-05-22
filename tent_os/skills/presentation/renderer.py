"""PPT HTML 渲染引擎 v2.0 —— 纯 Python，零外部依赖

将 Presentation 数据结构渲染为精美的 HTML 幻灯片。
支持：主题切换、CSS 动画、键盘翻页、进度指示、SVG 内联、图标系统。

v2.0 新增：
- SVG 元素内联渲染（LLM 直接生成 SVG 代码嵌入）
- 内置图标库（40+ 常用图标，LLM 通过名称引用）
- 新 slide 类型：visual, infographic, process_flow, comparison, gallery, statement
- style_override 支持 LLM 自定义任意 CSS
"""

import html
import json
from pathlib import Path
from typing import Dict, List

from tent_os.skills.presentation.schema import Presentation, Slide, SlideElement, Section, ChartData


class PresentationRenderer:
    """HTML 幻灯片渲染器 v2.0"""
    
    # ═══════════════════════════════════════════════════════════════
    # 主题色板定义
    # ═══════════════════════════════════════════════════════════════
    THEMES = {
        "dark_modern": {
            "bg_primary": "#0a0a0f",
            "bg_secondary": "#12121a",
            "bg_gradient": "linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 50%, #16213e 100%)",
            "text_primary": "#f0f0f5",
            "text_secondary": "#a0a0b0",
            "accent": "#6366f1",
            "accent_gradient": "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
            "accent_secondary": "#ec4899",
            "border": "rgba(99, 102, 241, 0.2)",
            "card_bg": "rgba(255, 255, 255, 0.03)",
            "card_bg_hover": "rgba(255, 255, 255, 0.06)",
            "chart_colors": ["#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#3b82f6", "#ef4444", "#14b8a6"],
            "glass": "rgba(255, 255, 255, 0.05)",
        },
        "light_corporate": {
            "bg_primary": "#ffffff",
            "bg_secondary": "#f8fafc",
            "bg_gradient": "linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%)",
            "text_primary": "#1e293b",
            "text_secondary": "#64748b",
            "accent": "#2563eb",
            "accent_gradient": "linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)",
            "accent_secondary": "#0ea5e9",
            "border": "rgba(37, 99, 235, 0.15)",
            "card_bg": "rgba(241, 245, 249, 0.8)",
            "card_bg_hover": "rgba(241, 245, 249, 1)",
            "chart_colors": ["#2563eb", "#3b82f6", "#60a5fa", "#93c5fd", "#0ea5e9", "#22d3ee", "#f59e0b", "#10b981"],
            "glass": "rgba(255, 255, 255, 0.7)",
        },
        "gradient_bold": {
            "bg_primary": "#1a0a2e",
            "bg_secondary": "#2d1b4e",
            "bg_gradient": "linear-gradient(135deg, #1a0a2e 0%, #4a148c 50%, #6a1b9a 100%)",
            "text_primary": "#ffffff",
            "text_secondary": "#e1bee7",
            "accent": "#ff6f00",
            "accent_gradient": "linear-gradient(135deg, #ff6f00 0%, #ff8f00 100%)",
            "accent_secondary": "#ffc107",
            "border": "rgba(255, 111, 0, 0.3)",
            "card_bg": "rgba(255, 255, 255, 0.08)",
            "card_bg_hover": "rgba(255, 255, 255, 0.12)",
            "chart_colors": ["#ff6f00", "#ff8f00", "#ffc107", "#ffeb3b", "#cddc39", "#8bc34a", "#4caf50", "#009688"],
            "glass": "rgba(255, 255, 255, 0.08)",
        },
        "ocean_depth": {
            "bg_primary": "#001524",
            "bg_secondary": "#012a4a",
            "bg_gradient": "linear-gradient(180deg, #001524 0%, #013a63 50%, #014f86 100%)",
            "text_primary": "#e0fbfc",
            "text_secondary": "#90e0ef",
            "accent": "#00b4d8",
            "accent_gradient": "linear-gradient(135deg, #00b4d8 0%, #90e0ef 100%)",
            "accent_secondary": "#48cae4",
            "border": "rgba(0, 180, 216, 0.25)",
            "card_bg": "rgba(255, 255, 255, 0.04)",
            "card_bg_hover": "rgba(255, 255, 255, 0.08)",
            "chart_colors": ["#00b4d8", "#48cae4", "#90e0ef", "#ade8f4", "#0077b6", "#023e8a", "#f59e0b", "#ff6b6b"],
            "glass": "rgba(255, 255, 255, 0.05)",
        },
        "forest_moss": {
            "bg_primary": "#0d1f0d",
            "bg_secondary": "#1a2f1a",
            "bg_gradient": "linear-gradient(135deg, #0d1f0d 0%, #1b4332 50%, #2d6a4f 100%)",
            "text_primary": "#d8f3dc",
            "text_secondary": "#95d5b2",
            "accent": "#52b788",
            "accent_gradient": "linear-gradient(135deg, #52b788 0%, #74c69d 100%)",
            "accent_secondary": "#b7e4c7",
            "border": "rgba(82, 183, 136, 0.25)",
            "card_bg": "rgba(255, 255, 255, 0.04)",
            "card_bg_hover": "rgba(255, 255, 255, 0.08)",
            "chart_colors": ["#52b788", "#74c69d", "#95d5b2", "#b7e4c7", "#40916c", "#2d6a4f", "#f4a261", "#e76f51"],
            "glass": "rgba(255, 255, 255, 0.05)",
        },
    }
    
    # ═══════════════════════════════════════════════════════════════
    # 内置图标库（Heroicons 风格，MIT 许可）
    # LLM 通过名称引用，如 {"type": "icon", "content": "rocket"}
    # ═══════════════════════════════════════════════════════════════
    ICONS = {
        # 技术
        "code": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4'/>",
        "cpu": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z'/>",
        "database": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4'/>",
        "globe": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9'/>",
        "lock": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z'/>",
        "server": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01'/>",
        "shield": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z'/>",
        "terminal": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z'/>",
        "wifi": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0'/>",
        "cloud": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z'/>",
        # 商业
        "award": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z'/>",
        "briefcase": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z'/>",
        "chart-bar": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z'/>",
        "chart-line": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M13 7h8m0 0v8m0-8l-8 8-4-4-6 6'/>",
        "chart-pie": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z'/><path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z'/>",
        "dollar-sign": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z'/>",
        "medal": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z'/>",
        "target": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M15 12a3 3 0 11-6 0 3 3 0 016 0z'/><path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z'/>",
        "trend-up": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M13 7h8m0 0v8m0-8l-8 8-4-4-6 6'/>",
        "trend-down": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M13 17h8m0 0V9m0 8l-8-8-4 4-6-6'/>",
        "users": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z'/>",
        # 抽象
        "arrow-right": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M14 5l7 7m0 0l-7 7m7-7H3'/>",
        "arrow-up": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M5 10l7-7m0 0l7 7m-7-7v18'/>",
        "check": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M5 13l4 4L19 7'/>",
        "chevron-right": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M9 5l7 7-7 7'/>",
        "lightbulb": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z'/>",
        "plus": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M12 4v16m8-8H4'/>",
        "rocket": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M15.59 14.37a6 6 0 01-5.84 7.38v-4.8m5.84-2.58a14.98 14.98 0 006.16-12.12A14.98 14.98 0 009.631 8.41m5.96 5.96a14.926 14.926 0 01-5.841 2.58m-.119-8.54a6 6 0 00-7.381 5.84h4.8m2.581-5.84a14.927 14.927 0 00-2.58 5.84m2.699 2.7c-.103.021-.207.041-.311.06a15.09 15.09 0 01-2.448-2.448 14.9 14.9 0 01.06-.312m-2.24 2.39a4.493 4.493 0 00-1.757 4.306 4.493 4.493 0 004.306-1.758M16.5 9a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z'/>",
        "star": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z'/>",
        "x": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M6 18L18 6M6 6l12 12'/>",
        "zap": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M13 10V3L4 14h7v7l9-11h-7z'/>",
        # 系统
        "bell": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9'/>",
        "calendar": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z'/>",
        "clock": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z'/>",
        "home": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6'/>",
        "mail": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z'/>",
        "map-pin": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z'/><path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M15 11a3 3 0 11-6 0 3 3 0 016 0z'/>",
        "menu": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M4 6h16M4 12h16M4 18h16'/>",
        "search": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z'/>",
        "settings": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z'/><path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M15 12a3 3 0 11-6 0 3 3 0 016 0z'/>",
        # 数据
        "activity": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M13 10V3L4 14h7v7l9-11h-7z'/>",
        "layers": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10'/>",
        "grid": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z'/>",
        # 自然/装饰
        "droplet": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z'/>",
        "flame": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z'/><path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M9.879 16.121A3 3 0 1012.015 11L11 14H9c0 .768.293 1.536.879 2.121z'/>",
        "moon": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z'/>",
        "mountain": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M13 7h8m0 0v8m0-8l-8 8-4-4-6 6'/>",
        "sun": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z'/>",
        "wind": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M9.59 4.59A2 2 0 1111 8H2m10.59 11.41A2 2 0 1014 16H2m15.73-8.27A2.5 2.5 0 1119.5 12H2'/>",
        # 额外实用
        "check-circle": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z'/>",
        "alert": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z'/>",
        "info": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'/>",
        "help": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'/>",
        "book-open": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253'/>",
        "heart": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z'/>",
        "eye": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M15 12a3 3 0 11-6 0 3 3 0 016 0z'/><path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z'/>",
        "key": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z'/>",
        "link": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1'/>",
        "refresh": "<path stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15'/>",
    }
    
    def __init__(self, theme: str = "dark_modern"):
        self.theme = theme
        self.colors = self.THEMES.get(theme, self.THEMES["dark_modern"])
    
    # ═══════════════════════════════════════════════════════════════
    # 主渲染入口
    # ═══════════════════════════════════════════════════════════════
    def render(self, presentation: Presentation) -> str:
        """将 Presentation 渲染为完整 HTML"""
        if presentation.total_slides() == 0:
            return self._build_html(presentation, [self._render_error_slide("无内容")])
        
        slides_html = []
        slide_index = 0
        for section in presentation.sections:
            for slide in section.slides:
                slide_index += 1
                slides_html.append(self._render_slide(slide, slide_index, presentation.total_slides()))
        
        return self._build_html(presentation, slides_html)
    
    def _render_error_slide(self, message: str) -> str:
        """错误页"""
        return f'''
        <div class="slide active" data-index="1">
            <div class="slide-content">
                <div class="slide-title">
                    <h1>⚠️ {self._escape(message)}</h1>
                    <p class="subtitle">请检查内容后重试</p>
                </div>
            </div>
        </div>
        '''
    
    # ═══════════════════════════════════════════════════════════════
    # Slide 类型分发
    # ═══════════════════════════════════════════════════════════════
    def _render_slide(self, slide: Slide, index: int, total: int) -> str:
        """渲染单页幻灯片"""
        renderer = getattr(self, f"_render_{slide.type}", self._render_content)
        content = renderer(slide)
        
        bg_style = slide.background or self.colors["bg_gradient"]
        custom_style = slide.style_override.get("custom_css", "")
        
        # FIX: 动画字段生效 —— fade/slide/zoom/none
        anim_map = {"fade": "fadeIn", "slide": "slideIn", "zoom": "zoomIn", "none": "none"}
        anim_class = anim_map.get(slide.animation, "fadeIn")
        anim_attr = f'data-animation="{anim_class}"' if anim_class != "none" else ''
        
        return f'''
        <div class="slide" data-index="{index}" {anim_attr} style="background: {bg_style}; {custom_style}">
            <div class="slide-content">
                {content}
            </div>
            <div class="slide-footer">
                <span class="slide-number">{index} / {total}</span>
            </div>
        </div>
        '''
    
    # ═══════════════════════════════════════════════════════════════
    # 基础 Slide 类型渲染器
    # ═══════════════════════════════════════════════════════════════
    def _render_title(self, slide: Slide) -> str:
        """封面页"""
        # 检查是否有 SVG 装饰元素
        decor_svg = ""
        for elem in slide.elements:
            if elem.type == "svg":
                decor_svg = self._render_svg_element(elem, container_class="title-decoration")
        
        return f'''
        <div class="slide-title">
            {decor_svg}
            <h1>{self._escape(slide.title)}</h1>
            <p class="subtitle">{self._escape(slide.subtitle)}</p>
            <div class="accent-line"></div>
        </div>
        '''
    
    def _render_content(self, slide: Slide) -> str:
        """内容页"""
        bullets_html = ""
        if slide.bullets:
            bullets_html = '<ul class="bullet-list">' + "".join(
                f'<li><span class="bullet-dot"></span>{self._escape(b)}</li>'
                for b in slide.bullets
            ) + '</ul>'
        
        elements_html = ""
        for elem in slide.elements:
            elements_html += self._render_element(elem)
        
        return f'''
        <div class="slide-content-layout">
            <h2>{self._escape(slide.title)}</h2>
            {f'<p class="slide-subtitle">{self._escape(slide.subtitle)}</p>' if slide.subtitle else ''}
            {bullets_html}
            {elements_html}
        </div>
        '''
    
    def _render_two_column(self, slide: Slide) -> str:
        """双栏页"""
        left_html = "".join(self._render_element(e) for e in slide.left_elements)
        right_html = "".join(self._render_element(e) for e in slide.right_elements)
        
        return f'''
        <div class="slide-content-layout">
            <h2>{self._escape(slide.title)}</h2>
            <div class="two-column">
                <div class="column">{left_html}</div>
                <div class="column">{right_html}</div>
            </div>
        </div>
        '''
    
    def _render_chart(self, slide: Slide) -> str:
        """图表页"""
        charts_html = ""
        for elem in slide.elements:
            if elem.type == "chart" and elem.chart_data:
                charts_html += self._render_chart_element(elem.chart_data)
            elif elem.type == "svg":
                charts_html += self._render_svg_element(elem)
        
        return f'''
        <div class="slide-content-layout">
            <h2>{self._escape(slide.title)}</h2>
            {f'<p class="slide-subtitle">{self._escape(slide.subtitle)}</p>' if slide.subtitle else ''}
            <div class="charts-container">{charts_html}</div>
        </div>
        '''
    
    def _render_data(self, slide: Slide) -> str:
        """数据页（KPI 卡片）"""
        kpi_html = ""
        for elem in slide.elements:
            if elem.type == "kpi":
                kpi_html += self._render_kpi_element(elem)
            elif elem.type == "icon":
                kpi_html += self._render_icon_element(elem, size=48)
        
        return f'''
        <div class="slide-content-layout">
            <h2>{self._escape(slide.title)}</h2>
            <div class="kpi-grid">{kpi_html}</div>
        </div>
        '''
    
    def _render_quote(self, slide: Slide) -> str:
        """引用页"""
        quote_text = slide.elements[0].content if slide.elements else ""
        source = slide.elements[0].style.get("source", "") if slide.elements else ""
        
        return f'''
        <div class="slide-quote">
            <div class="quote-mark">"</div>
            <blockquote>{self._escape(quote_text)}</blockquote>
            <cite>{self._escape(source)}</cite>
        </div>
        '''
    
    def _render_timeline(self, slide: Slide) -> str:
        """时间线页"""
        items_html = ""
        for i, elem in enumerate(slide.elements):
            color = self.colors['chart_colors'][i % len(self.colors['chart_colors'])]
            icon_html = ""
            if elem.type == "icon":
                icon_html = self._render_icon_element(elem, size=20, color=color)
            items_html += f'''
            <div class="timeline-item">
                <div class="timeline-dot" style="background: {color}">
                    {icon_html}
                </div>
                <div class="timeline-content">
                    <div class="timeline-date">{self._escape(elem.style.get("date", ""))}</div>
                    <div class="timeline-text">{self._escape(elem.content)}</div>
                </div>
            </div>
            '''
        
        return f'''
        <div class="slide-content-layout">
            <h2>{self._escape(slide.title)}</h2>
            <div class="timeline">{items_html}</div>
        </div>
        '''
    
    def _render_section_divider(self, slide: Slide) -> str:
        """章节分隔页"""
        return f'''
        <div class="slide-section-divider">
            <div class="section-number">{self._escape(slide.subtitle)}</div>
            <h1>{self._escape(slide.title)}</h1>
            <div class="accent-line"></div>
        </div>
        '''
    
    # ═══════════════════════════════════════════════════════════════
    # v2.0 新增 Slide 类型
    # ═══════════════════════════════════════════════════════════════
    def _render_visual(self, slide: Slide) -> str:
        """全屏视觉页 —— 大 SVG/背景 + 文字叠加"""
        visual_html = ""
        text_elements = []
        
        for elem in slide.elements:
            if elem.type == "svg":
                visual_html = self._render_svg_element(elem, container_class="visual-bg")
            elif elem.type == "icon":
                visual_html = self._render_icon_element(elem, size=120)
            elif elem.type in ("text", "quote"):
                text_elements.append(elem)
        
        text_overlay = ""
        for elem in text_elements:
            if elem.type == "text":
                text_overlay += f'<p class="visual-text">{self._escape(elem.content)}</p>'
            elif elem.type == "quote":
                text_overlay += f'<blockquote class="visual-quote">{self._escape(elem.content)}</blockquote>'
        
        return f'''
        <div class="slide-visual">
            {visual_html}
            <div class="visual-overlay">
                <h1>{self._escape(slide.title)}</h1>
                {f'<p class="visual-subtitle">{self._escape(slide.subtitle)}</p>' if slide.subtitle else ''}
                {text_overlay}
            </div>
        </div>
        '''
    
    def _render_infographic(self, slide: Slide) -> str:
        """信息图页 —— 多元素自由组合"""
        elements_html = "".join(self._render_element(elem) for elem in slide.elements)
        
        return f'''
        <div class="slide-content-layout infographic-layout">
            <h2>{self._escape(slide.title)}</h2>
            {f'<p class="slide-subtitle">{self._escape(slide.subtitle)}</p>' if slide.subtitle else ''}
            <div class="infographic-grid">{elements_html}</div>
        </div>
        '''
    
    def _render_process_flow(self, slide: Slide) -> str:
        """流程图页 —— 横向步骤流程"""
        steps_html = ""
        step_count = len(slide.elements)
        
        for i, elem in enumerate(slide.elements):
            is_last = (i == step_count - 1)
            color = self.colors['chart_colors'][i % len(self.colors['chart_colors'])]
            
            icon_html = ""
            if elem.type == "icon":
                icon_html = self._render_icon_element(elem, size=32, color=color)
            elif elem.type == "svg":
                icon_html = self._render_svg_element(elem)
            
            arrow = "" if is_last else f'<div class="flow-arrow" style="color: {color}">→</div>'
            
            steps_html += f'''
            <div class="flow-step">
                <div class="flow-icon" style="background: {color}20; border-color: {color}40">
                    {icon_html or f'<span style="color: {color}">{i+1}</span>'}
                </div>
                <div class="flow-content">{self._escape(elem.content)}</div>
            </div>
            {arrow}
            '''
        
        return f'''
        <div class="slide-content-layout">
            <h2>{self._escape(slide.title)}</h2>
            {f'<p class="slide-subtitle">{self._escape(slide.subtitle)}</p>' if slide.subtitle else ''}
            <div class="process-flow">{steps_html}</div>
        </div>
        '''
    
    def _render_comparison(self, slide: Slide) -> str:
        """对比页 —— 左右对比布局"""
        left_html = "".join(self._render_element(e) for e in slide.left_elements)
        right_html = "".join(self._render_element(e) for e in slide.right_elements)
        
        left_title = slide.style_override.get("left_title", "方案 A")
        right_title = slide.style_override.get("right_title", "方案 B")
        left_accent = slide.style_override.get("left_accent", self.colors["accent"])
        right_accent = slide.style_override.get("right_accent", self.colors["accent_secondary"])
        
        return f'''
        <div class="slide-content-layout">
            <h2>{self._escape(slide.title)}</h2>
            <div class="comparison-layout">
                <div class="comparison-side" style="border-color: {left_accent}30">
                    <div class="comparison-header" style="color: {left_accent}">{self._escape(left_title)}</div>
                    <div class="comparison-body">{left_html}</div>
                </div>
                <div class="comparison-vs">VS</div>
                <div class="comparison-side" style="border-color: {right_accent}30">
                    <div class="comparison-header" style="color: {right_accent}">{self._escape(right_title)}</div>
                    <div class="comparison-body">{right_html}</div>
                </div>
            </div>
        </div>
        '''
    
    def _render_gallery(self, slide: Slide) -> str:
        """画廊页 —— 卡片网格展示"""
        cards_html = ""
        for elem in slide.elements:
            icon_html = ""
            if elem.type == "icon":
                icon_html = self._render_icon_element(elem, size=40)
            elif elem.type == "svg":
                icon_html = self._render_svg_element(elem)
            
            title = elem.style.get("title", "")
            desc = elem.content
            
            cards_html += f'''
            <div class="gallery-card">
                <div class="gallery-icon">{icon_html}</div>
                <div class="gallery-title">{self._escape(title)}</div>
                <div class="gallery-desc">{self._escape(desc)}</div>
            </div>
            '''
        
        return f'''
        <div class="slide-content-layout">
            <h2>{self._escape(slide.title)}</h2>
            {f'<p class="slide-subtitle">{self._escape(slide.subtitle)}</p>' if slide.subtitle else ''}
            <div class="gallery-grid">{cards_html}</div>
        </div>
        '''
    
    def _render_statement(self, slide: Slide) -> str:
        """金句/声明页 —— 极简大字"""
        decor_svg = ""
        for elem in slide.elements:
            if elem.type == "svg":
                decor_svg = self._render_svg_element(elem, container_class="statement-decoration")
        
        return f'''
        <div class="slide-statement">
            {decor_svg}
            <h1>{self._escape(slide.title)}</h1>
            {f'<p class="statement-subtitle">{self._escape(slide.subtitle)}</p>' if slide.subtitle else ''}
        </div>
        '''
    
    # ═══════════════════════════════════════════════════════════════
    # 元素渲染器
    # ═══════════════════════════════════════════════════════════════
    def _render_element(self, elem: SlideElement) -> str:
        """渲染单个元素 —— 类型分发"""
        if elem.type == "text":
            return f'<p class="element-text">{self._escape(elem.content)}</p>'
        elif elem.type == "quote":
            return f'<blockquote class="element-quote">{self._escape(elem.content)}</blockquote>'
        elif elem.type == "image":
            return f'<img src="{self._escape(elem.content)}" class="element-image" alt="">'
        elif elem.type == "chart":
            if elem.chart_data:
                return self._render_chart_element(elem.chart_data)
            return ""
        elif elem.type == "table":
            return self._render_table_element(elem)
        elif elem.type == "kpi":
            return self._render_kpi_element(elem)
        elif elem.type == "svg":
            return self._render_svg_element(elem)
        elif elem.type == "icon":
            size = elem.style.get("size", 24)
            color = elem.style.get("color")
            return self._render_icon_element(elem, size=size, color=color)
        return f'<p>{self._escape(elem.content)}</p>'
    
    def _render_svg_element(self, elem: SlideElement, container_class: str = "svg-container") -> str:
        """渲染 SVG 元素 —— LLM 生成的 SVG 代码直接内联"""
        svg_code = elem.content
        style = elem.style
        
        # 如果 LLM 忘记加 viewBox，给一个默认的
        if "viewBox" not in svg_code and "<svg" in svg_code:
            svg_code = svg_code.replace("<svg", '<svg viewBox="0 0 400 300"', 1)
        
        width = style.get("width", "100%")
        height = style.get("height", "auto")
        max_width = style.get("max_width", "none")
        
        style_attr = f"width: {width}; height: {height};"
        if max_width != "none":
            style_attr += f" max-width: {max_width};"
        
        return f'''
        <div class="{container_class}" style="{style_attr}">
            {svg_code}
        </div>
        '''
    
    def _render_icon_element(self, elem: SlideElement, size: int = 24, color: str = None) -> str:
        """渲染图标元素"""
        icon_name = elem.content
        icon_path = self.ICONS.get(icon_name, self.ICONS.get("star", ""))
        icon_color = color or elem.style.get("color", self.colors["accent"])
        icon_size = elem.style.get("size", size)
        
        return f'''
        <svg width="{icon_size}" height="{icon_size}" viewBox="0 0 24 24" fill="none" stroke="{icon_color}" class="inline-icon">
            {icon_path}
        </svg>
        '''
    
    def _get_icon_svg(self, name: str, size: int = 24, color: str = None) -> str:
        """获取图标 SVG 字符串（直接返回 SVG 标签）"""
        icon_path = self.ICONS.get(name, self.ICONS.get("star", ""))
        icon_color = color or self.colors["accent"]
        return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{icon_color}">{icon_path}</svg>'
    
    def _render_kpi_element(self, elem: SlideElement) -> str:
        """渲染 KPI 卡片"""
        icon_html = ""
        if "icon" in elem.style:
            icon_html = self._get_icon_svg(
                elem.style["icon"], 
                size=elem.style.get("icon_size", 32),
                color=elem.style.get("icon_color", self.colors["accent"])
            )
        
        trend = elem.style.get("trend", "")
        trend_html = ""
        if trend:
            trend_color = "#10b981" if trend.startswith("+") else "#ef4444"
            trend_icon = "↑" if trend.startswith("+") else "↓"
            trend_html = f'<span class="kpi-trend" style="color: {trend_color}">{trend_icon} {trend}</span>'
        
        return f'''
        <div class="kpi-card">
            {f'<div class="kpi-icon">{icon_html}</div>' if icon_html else ''}
            <div class="kpi-value">{self._escape(elem.content)}</div>
            <div class="kpi-label">{self._escape(elem.style.get("label", ""))}</div>
            {trend_html}
        </div>
        '''
    
    # ═══════════════════════════════════════════════════════════════
    # 图表渲染器
    # ═══════════════════════════════════════════════════════════════
    _chart_id_counter = 0
    
    def _render_chart_element(self, data: ChartData) -> str:
        """渲染图表 —— 优先 ECharts，降级 CSS"""
        # FIX: ECharts 内联渲染
        PresentationRenderer._chart_id_counter += 1
        chart_id = f"tent_chart_{PresentationRenderer._chart_id_counter}"
        
        try:
            echarts_html = self._render_echarts(data, chart_id)
            if echarts_html:
                return echarts_html
        except Exception:
            pass
        
        # Graceful 降级：CSS 图表
        if data.chart_type == "pie" or data.chart_type == "donut":
            return self._render_pie_chart(data)
        elif data.chart_type == "line" or data.chart_type == "area":
            return self._render_line_chart(data)
        elif data.chart_type == "progress":
            return self._render_progress_chart(data)
        return self._render_bar_chart(data)
    
    def _render_echarts(self, data: ChartData, chart_id: str) -> str:
        """生成 ECharts 图表 HTML + JS"""
        if not data.values:
            return ""
        
        colors = data.colors if data.colors else self.colors["chart_colors"]
        labels_json = json.dumps(data.labels, ensure_ascii=False)
        values_json = json.dumps(data.values, ensure_ascii=False)
        colors_json = json.dumps(colors[:len(data.values)], ensure_ascii=False)
        title = self._escape(data.title)
        
        chart_type = data.chart_type
        
        # 构建 ECharts option
        if chart_type in ("bar", "line", "area"):
            series_type = "bar" if chart_type == "bar" else "line"
            area_style = "areaStyle: {{ opacity: 0.2 }}," if chart_type == "area" else ""
            option = f"""
            {{
                title: {{ text: '{title}', left: 'center', textStyle: {{ color: '{self.colors["text_primary"]}', fontSize: 16 }} }},
                tooltip: {{ trigger: 'axis' }},
                grid: {{ left: '10%', right: '10%', bottom: '15%', top: '20%' }},
                xAxis: {{ type: 'category', data: {labels_json}, axisLabel: {{ color: '{self.colors["text_secondary"]}' }}, axisLine: {{ lineStyle: {{ color: '{self.colors["border"]}' }} }} }},
                yAxis: {{ type: 'value', axisLabel: {{ color: '{self.colors["text_secondary"]}' }}, splitLine: {{ lineStyle: {{ color: '{self.colors["border"]}' }} }} }},
                series: [{{
                    type: '{series_type}',
                    data: {values_json},
                    itemStyle: {{ color: '{colors[0]}' }},
                    {area_style}
                    smooth: true,
                    animationDuration: 1000
                }}]
            }}
            """
        elif chart_type in ("pie", "donut"):
            pie_data = json.dumps([{{"name": l, "value": v}} for l, v in zip(data.labels, data.values)], ensure_ascii=False)
            radius = "['40%', '70%']" if chart_type == "donut" else "'70%'"
            option = f"""
            {{
                title: {{ text: '{title}', left: 'center', textStyle: {{ color: '{self.colors["text_primary"]}', fontSize: 16 }} }},
                tooltip: {{ trigger: 'item' }},
                legend: {{ bottom: '5%', textStyle: {{ color: '{self.colors["text_secondary"]}' }} }},
                series: [{{
                    type: 'pie',
                    radius: {radius},
                    data: {pie_data},
                    emphasis: {{ itemStyle: {{ shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' }} }},
                    animationType: 'scale',
                    animationDuration: 1000
                }}]
            }}
            """
        else:
            # 不支持的类型回退到 CSS
            return ""
        
        return f'''
        <div class="chart-container">
            <div id="{chart_id}" style="width: 100%; height: 320px;"></div>
            <script>
                (function() {{
                    var chartDom = document.getElementById('{chart_id}');
                    if (!chartDom || typeof echarts === 'undefined') return;
                    var myChart = echarts.init(chartDom, null, {{ renderer: 'svg' }});
                    var option = {option};
                    myChart.setOption(option);
                }})();
            </script>
        </div>
        '''
    
    def _render_bar_chart(self, data: ChartData) -> str:
        """CSS 条形图"""
        max_val = max(data.values) if data.values else 1
        bars_html = ""
        for i, (label, value) in enumerate(zip(data.labels, data.values)):
            color = data.colors[i] if i < len(data.colors) else self.colors["chart_colors"][i % len(self.colors["chart_colors"])]
            pct = (value / max_val) * 100
            bars_html += f'''
            <div class="chart-bar">
                <div class="chart-label">{self._escape(label)}</div>
                <div class="chart-bar-track">
                    <div class="chart-bar-fill" style="width: {pct}%; background: {color}"></div>
                </div>
                <div class="chart-value">{value}</div>
            </div>
            '''
        
        return f'''
        <div class="chart-container">
            <div class="chart-title">{self._escape(data.title)}</div>
            <div class="bar-chart">{bars_html}</div>
        </div>
        '''
    
    def _render_pie_chart(self, data: ChartData) -> str:
        """CSS 饼图（conic-gradient）"""
        total = sum(data.values) if data.values else 1
        gradient_parts = []
        current_pct = 0
        
        for i, (label, value) in enumerate(zip(data.labels, data.values)):
            color = data.colors[i] if i < len(data.colors) else self.colors["chart_colors"][i % len(self.colors["chart_colors"])]
            pct = (value / total) * 100
            gradient_parts.append(f"{color} {current_pct}% {current_pct + pct}%")
            current_pct += pct
        
        legend_html = ""
        for i, (label, value) in enumerate(zip(data.labels, data.values)):
            color = data.colors[i] if i < len(data.colors) else self.colors["chart_colors"][i % len(self.colors["chart_colors"])]
            pct = round((value / total) * 100, 1)
            legend_html += f'''
            <div class="pie-legend-item">
                <div class="pie-legend-color" style="background: {color}"></div>
                <span>{self._escape(label)}: {value} ({pct}%)</span>
            </div>
            '''
        
        is_donut = data.chart_type == "donut"
        donut_hole = '<div class="pie-donut-hole"></div>' if is_donut else ''
        
        return f'''
        <div class="chart-container">
            <div class="chart-title">{self._escape(data.title)}</div>
            <div class="pie-chart-wrapper">
                <div class="pie-chart" style="background: conic-gradient({', '.join(gradient_parts)})">
                    {donut_hole}
                </div>
                <div class="pie-legend">{legend_html}</div>
            </div>
        </div>
        '''
    
    def _render_line_chart(self, data: ChartData) -> str:
        """CSS/SVG 折线图"""
        if not data.values:
            return ""
        
        max_val = max(data.values)
        min_val = min(data.values)
        range_val = max_val - min_val if max_val != min_val else 1
        n = len(data.values)
        
        # 计算 SVG polyline 点
        points = []
        for i, v in enumerate(data.values):
            x = (i / (n - 1)) * 300 if n > 1 else 150
            y = 150 - ((v - min_val) / range_val) * 120
            points.append(f"{x},{y}")
        
        # 区域填充路径
        area_points = "0,150 " + " ".join(points) + f" 300,150"
        
        color = data.colors[0] if data.colors else self.colors["accent"]
        
        is_area = data.chart_type == "area"
        area_path = f'<polygon points="{area_points}" fill="{color}" opacity="0.15"/>' if is_area else ''
        
        # 数据点圆圈
        dots_html = ""
        for i, (x_y, v) in enumerate(zip(points, data.values)):
            x, y = x_y.split(",")
            dots_html += f'<circle cx="{x}" cy="{y}" r="4" fill="{color}" stroke="white" stroke-width="2"/>'
            # 数值标签
            if n <= 8:
                dots_html += f'<text x="{x}" y="{float(y)-10}" text-anchor="middle" fill="{self.colors["text_secondary"]}" font-size="10">{v}</text>'
        
        # X 轴标签
        labels_html = ""
        for i, label in enumerate(data.labels):
            x = (i / (n - 1)) * 300 if n > 1 else 150
            labels_html += f'<text x="{x}" y="170" text-anchor="middle" fill="{self.colors["text_secondary"]}" font-size="10">{self._escape(label[:8])}</text>'
        
        return f'''
        <div class="chart-container">
            <div class="chart-title">{self._escape(data.title)}</div>
            <svg viewBox="0 0 300 180" class="line-chart-svg">
                {area_path}
                <polyline points="{' '.join(points)}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                {dots_html}
                {labels_html}
            </svg>
        </div>
        '''
    
    def _render_progress_chart(self, data: ChartData) -> str:
        """进度环/仪表盘"""
        value = data.values[0] if data.values else 0
        max_val = max(data.values) if len(data.values) > 1 else 100
        pct = min(value / max_val, 1)
        color = data.colors[0] if data.colors else self.colors["accent"]
        label = data.labels[0] if data.labels else "进度"
        
        # SVG 圆弧进度
        circumference = 2 * 3.14159 * 45
        offset = circumference * (1 - pct)
        
        return f'''
        <div class="chart-container progress-container">
            <div class="chart-title">{self._escape(data.title)}</div>
            <div class="progress-ring-wrapper">
                <svg viewBox="0 0 120 120" class="progress-ring">
                    <circle cx="60" cy="60" r="45" fill="none" stroke="{self.colors['border']}" stroke-width="8"/>
                    <circle cx="60" cy="60" r="45" fill="none" stroke="{color}" stroke-width="8" 
                        stroke-dasharray="{circumference}" stroke-dashoffset="{offset}" 
                        stroke-linecap="round" transform="rotate(-90 60 60)"
                        style="transition: stroke-dashoffset 1s ease;"/>
                    <text x="60" y="58" text-anchor="middle" fill="{self.colors['text_primary']}" font-size="22" font-weight="700">{int(pct*100)}%</text>
                    <text x="60" y="78" text-anchor="middle" fill="{self.colors['text_secondary']}" font-size="10">{self._escape(label)}</text>
                </svg>
            </div>
        </div>
        '''
    
    def _render_table_element(self, elem: SlideElement) -> str:
        """渲染表格"""
        headers_html = "".join(f"<th>{self._escape(h)}</th>" for h in elem.headers)
        rows_html = ""
        for row in elem.rows:
            cells_html = "".join(f"<td>{self._escape(c)}</td>" for c in row)
            rows_html += f"<tr>{cells_html}</tr>"
        
        return f'''
        <div class="table-wrapper">
            <table>
                <thead><tr>{headers_html}</tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
        '''
    
    # ═══════════════════════════════════════════════════════════════
    # HTML 构建
    # ═══════════════════════════════════════════════════════════════
    def _build_html(self, presentation: Presentation, slides_html: List[str]) -> str:
        """构建完整 HTML"""
        c = self.colors
        slides_str = "\n".join(slides_html)
        
        # 生成目录
        toc_html = ""
        slide_idx = 0
        section_idx = 0
        for sec in presentation.sections:
            section_idx += 1
            has_section_title = bool(sec.title.strip())
            if has_section_title:
                toc_html += f'<div class="toc-section">{self._escape(sec.title[:30])}</div>'
            for sli in sec.slides:
                slide_idx += 1
                toc_html += f'<div class="toc-item" onclick="goToSlide({slide_idx})">{slide_idx}. {self._escape(sli.title[:30])}</div>'
        
        # FIX: 从 config 读取显示选项和动画时长
        cfg = presentation.config
        show_progress = cfg.get("show_progress", True)
        show_navigation = cfg.get("show_navigation", True)
        show_page_numbers = cfg.get("show_page_numbers", True)
        anim_duration = cfg.get("animation_duration", 600)
        
        progress_html = '<div class="progress-bar" id="progressBar"></div>' if show_progress else ''
        nav_html = f'''<button class="nav-btn nav-prev" onclick="prevSlide()">‹</button>
        <button class="nav-btn nav-next" onclick="nextSlide()">›</button>''' if show_navigation else ''
        toc_btn_html = '<button class="toc-toggle" onclick="toggleToc()">目录</button>' if show_navigation else ''
        toc_panel_html = f'''<div class="toc-panel" id="tocPanel">
            <h3>目录</h3>
            {toc_html}
        </div>''' if show_navigation else ''
        page_num_css = '' if show_page_numbers else '.slide-number {{ display: none; }}'
        
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self._escape(presentation.title)}</title>
    <!-- FIX: 字体加载 —— Noto Sans SC 跨平台一致 -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700;900&display=swap" rel="stylesheet">
    <!-- FIX: ECharts 内联 CDN -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            background: {c["bg_primary"]};
            color: {c["text_primary"]};
            overflow: hidden;
            width: 100vw;
            height: 100vh;
        }}
        
        .presentation {{
            width: 100%;
            height: 100%;
            position: relative;
        }}
        
        .slide {{
            width: 100%;
            height: 100%;
            display: none;
            position: absolute;
            top: 0; left: 0;
            padding: 60px 80px;
        }}
        
        .slide.active {{ display: flex; flex-direction: column; }}
        
        /* FIX: 动画字段生效 —— 按 data-animation 应用不同动画 */
        .slide[data-animation="fadeIn"] {{ animation: fadeIn {anim_duration}ms ease; }}
        .slide[data-animation="slideIn"] {{ animation: slideIn {anim_duration}ms ease; }}
        .slide[data-animation="zoomIn"] {{ animation: zoomIn {anim_duration}ms ease; }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        @keyframes slideIn {{
            from {{ opacity: 0; transform: translateX(60px); }}
            to {{ opacity: 1; transform: translateX(0); }}
        }}
        
        @keyframes zoomIn {{
            from {{ opacity: 0; transform: scale(0.9); }}
            to {{ opacity: 1; transform: scale(1); }}
        }}
        
        /* FIX: 元素级 stagger 动画 —— bullet、KPI、元素逐个浮现 */
        .slide.active .slide-content > * {{
            animation: fadeIn {anim_duration}ms ease both;
        }}
        .slide.active .slide-content > *:nth-child(1) {{ animation-delay: 0ms; }}
        .slide.active .slide-content > *:nth-child(2) {{ animation-delay: 80ms; }}
        .slide.active .slide-content > *:nth-child(3) {{ animation-delay: 160ms; }}
        .slide.active .slide-content > *:nth-child(4) {{ animation-delay: 240ms; }}
        .slide.active .slide-content > *:nth-child(5) {{ animation-delay: 320ms; }}
        .slide.active .slide-content > *:nth-child(6) {{ animation-delay: 400ms; }}
        .slide.active .slide-content > *:nth-child(7) {{ animation-delay: 480ms; }}
        .slide.active .slide-content > *:nth-child(8) {{ animation-delay: 560ms; }}
        
        .slide.active .bullet-list li {{
            animation: fadeIn {anim_duration}ms ease both;
        }}
        .slide.active .bullet-list li:nth-child(1) {{ animation-delay: 0ms; }}
        .slide.active .bullet-list li:nth-child(2) {{ animation-delay: 80ms; }}
        .slide.active .bullet-list li:nth-child(3) {{ animation-delay: 160ms; }}
        .slide.active .bullet-list li:nth-child(4) {{ animation-delay: 240ms; }}
        .slide.active .bullet-list li:nth-child(5) {{ animation-delay: 320ms; }}
        .slide.active .bullet-list li:nth-child(6) {{ animation-delay: 400ms; }}
        .slide.active .bullet-list li:nth-child(7) {{ animation-delay: 480ms; }}
        .slide.active .bullet-list li:nth-child(8) {{ animation-delay: 560ms; }}
        
        .slide.active .kpi-card {{
            animation: fadeIn {anim_duration}ms ease both;
        }}
        .slide.active .kpi-card:nth-child(1) {{ animation-delay: 0ms; }}
        .slide.active .kpi-card:nth-child(2) {{ animation-delay: 100ms; }}
        .slide.active .kpi-card:nth-child(3) {{ animation-delay: 200ms; }}
        .slide.active .kpi-card:nth-child(4) {{ animation-delay: 300ms; }}
        .slide.active .kpi-card:nth-child(5) {{ animation-delay: 400ms; }}
        .slide.active .kpi-card:nth-child(6) {{ animation-delay: 500ms; }}
        
        @keyframes float {{
            0%, 100% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-10px); }}
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
        }}
        
        .slide-content {{
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
            max-width: 1200px;
            margin: 0 auto;
            width: 100%;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 封面页 */
        /* ═══════════════════════════════════════════════════════════ */
        .slide-title {{
            text-align: center;
            animation: fadeIn 0.8s ease;
        }}
        .slide-title h1 {{
            font-size: 4rem;
            font-weight: 800;
            line-height: 1.2;
            margin-bottom: 24px;
            background: {c["accent_gradient"]};
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        .slide-title .subtitle {{
            font-size: 1.5rem;
            color: {c["text_secondary"]};
            margin-bottom: 40px;
        }}
        .accent-line {{
            width: 80px;
            height: 4px;
            background: {c["accent_gradient"]};
            margin: 0 auto;
            border-radius: 2px;
        }}
        .title-decoration {{
            margin-bottom: 32px;
            display: flex;
            justify-content: center;
        }}
        .title-decoration svg {{
            max-width: 200px;
            max-height: 120px;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 内容页 */
        /* ═══════════════════════════════════════════════════════════ */
        .slide-content-layout h2 {{
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 16px;
            color: {c["text_primary"]};
        }}
        .slide-subtitle {{
            font-size: 1.2rem;
            color: {c["text_secondary"]};
            margin-bottom: 32px;
        }}
        .bullet-list {{
            list-style: none;
            padding: 0;
        }}
        .bullet-list li {{
            font-size: 1.3rem;
            line-height: 2;
            display: flex;
            align-items: flex-start;
            gap: 16px;
            margin-bottom: 12px;
        }}
        .bullet-dot {{
            width: 10px;
            height: 10px;
            min-width: 10px;
            background: {c["accent_gradient"]};
            border-radius: 50%;
            margin-top: 12px;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 双栏 */
        /* ═══════════════════════════════════════════════════════════ */
        .two-column {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 48px;
            margin-top: 24px;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* SVG 容器 */
        /* ═══════════════════════════════════════════════════════════ */
        .svg-container {{
            margin: 16px 0;
        }}
        .svg-container svg {{
            max-width: 100%;
            height: auto;
        }}
        .inline-icon {{
            display: inline-block;
            vertical-align: middle;
            margin-right: 8px;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 图表 */
        /* ═══════════════════════════════════════════════════════════ */
        .charts-container {{
            margin-top: 32px;
        }}
        .chart-container {{
            background: {c["card_bg"]};
            border: 1px solid {c["border"]};
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 24px;
        }}
        .chart-title {{
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 24px;
            color: {c["text_secondary"]};
        }}
        .bar-chart {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        .chart-bar {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}
        .chart-label {{
            min-width: 120px;
            font-size: 0.95rem;
            color: {c["text_secondary"]};
        }}
        .chart-bar-track {{
            flex: 1;
            height: 28px;
            background: {c["card_bg"]};
            border-radius: 14px;
            overflow: hidden;
        }}
        .chart-bar-fill {{
            height: 100%;
            border-radius: 14px;
            transition: width 1s ease;
        }}
        .chart-value {{
            min-width: 60px;
            text-align: right;
            font-weight: 600;
            font-size: 0.95rem;
        }}
        
        /* 饼图 */
        .pie-chart-wrapper {{
            display: flex;
            align-items: center;
            gap: 48px;
            flex-wrap: wrap;
        }}
        .pie-chart {{
            width: 200px;
            height: 200px;
            border-radius: 50%;
            position: relative;
        }}
        .pie-donut-hole {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: {c["bg_primary"]};
        }}
        .pie-legend {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .pie-legend-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 0.95rem;
        }}
        .pie-legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
        }}
        
        /* 折线图 */
        .line-chart-svg {{
            width: 100%;
            max-width: 500px;
            height: auto;
        }}
        
        /* 进度环 */
        .progress-container {{
            text-align: center;
        }}
        .progress-ring-wrapper {{
            display: flex;
            justify-content: center;
            margin-top: 16px;
        }}
        .progress-ring {{
            width: 150px;
            height: 150px;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* KPI 卡片 */
        /* ═══════════════════════════════════════════════════════════ */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 24px;
            margin-top: 32px;
        }}
        .kpi-card {{
            background: {c["card_bg"]};
            border: 1px solid {c["border"]};
            border-radius: 16px;
            padding: 32px;
            text-align: center;
            transition: all 0.3s ease;
        }}
        .kpi-card:hover {{
            background: {c["card_bg_hover"]};
            transform: translateY(-4px);
        }}
        .kpi-icon {{
            margin-bottom: 12px;
        }}
        .kpi-value {{
            font-size: 3rem;
            font-weight: 800;
            background: {c["accent_gradient"]};
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 8px;
        }}
        .kpi-label {{
            font-size: 1rem;
            color: {c["text_secondary"]};
        }}
        .kpi-trend {{
            display: inline-block;
            margin-top: 8px;
            font-size: 0.9rem;
            font-weight: 600;
            padding: 4px 12px;
            border-radius: 20px;
            background: rgba(16, 185, 129, 0.1);
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 引用页 */
        /* ═══════════════════════════════════════════════════════════ */
        .slide-quote {{
            text-align: center;
            max-width: 900px;
            margin: 0 auto;
        }}
        .quote-mark {{
            font-size: 8rem;
            line-height: 1;
            color: {c["accent"]};
            opacity: 0.3;
            font-family: Georgia, serif;
        }}
        .slide-quote blockquote {{
            font-size: 2rem;
            line-height: 1.6;
            font-style: italic;
            margin: -40px 0 24px 0;
        }}
        .slide-quote cite {{
            font-size: 1.1rem;
            color: {c["text_secondary"]};
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 时间线 */
        /* ═══════════════════════════════════════════════════════════ */
        .timeline {{
            display: flex;
            flex-direction: column;
            gap: 24px;
            margin-top: 32px;
            position: relative;
        }}
        .timeline::before {{
            content: '';
            position: absolute;
            left: 15px;
            top: 0;
            bottom: 0;
            width: 2px;
            background: {c["border"]};
        }}
        .timeline-item {{
            display: flex;
            align-items: flex-start;
            gap: 24px;
            padding-left: 8px;
        }}
        .timeline-dot {{
            width: 32px;
            height: 32px;
            border-radius: 50%;
            min-width: 32px;
            margin-top: 2px;
            z-index: 1;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .timeline-dot svg {{
            stroke: white;
        }}
        .timeline-date {{
            font-size: 0.9rem;
            color: {c["accent"]};
            font-weight: 600;
            margin-bottom: 4px;
        }}
        .timeline-text {{
            font-size: 1.1rem;
            line-height: 1.5;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 章节分隔页 */
        /* ═══════════════════════════════════════════════════════════ */
        .slide-section-divider {{
            text-align: center;
            animation: slideIn 0.8s ease;
        }}
        .slide-section-divider .section-number {{
            font-size: 1rem;
            color: {c["accent"]};
            font-weight: 600;
            letter-spacing: 4px;
            text-transform: uppercase;
            margin-bottom: 16px;
        }}
        .slide-section-divider h1 {{
            font-size: 3.5rem;
            font-weight: 800;
            margin-bottom: 32px;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* v2.0 新增：全屏视觉页 */
        /* ═══════════════════════════════════════════════════════════ */
        .slide-visual {{
            position: relative;
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}
        .visual-bg {{
            position: absolute;
            top: 0; left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            opacity: 0.6;
        }}
        .visual-bg svg {{
            width: 100%;
            height: 100%;
        }}
        .visual-overlay {{
            position: relative;
            z-index: 1;
            text-align: center;
            max-width: 800px;
            padding: 40px;
            background: {c["glass"]};
            backdrop-filter: blur(12px);
            border-radius: 24px;
            border: 1px solid {c["border"]};
        }}
        .visual-overlay h1 {{
            font-size: 3.5rem;
            font-weight: 800;
            margin-bottom: 16px;
            background: {c["accent_gradient"]};
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        .visual-subtitle {{
            font-size: 1.3rem;
            color: {c["text_secondary"]};
        }}
        .visual-text {{
            font-size: 1.1rem;
            color: {c["text_secondary"]};
            margin-top: 16px;
            line-height: 1.6;
        }}
        .visual-quote {{
            font-size: 1.5rem;
            font-style: italic;
            color: {c["text_primary"]};
            margin-top: 16px;
            border-left: 3px solid {c["accent"]};
            padding-left: 20px;
            text-align: left;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* v2.0 新增：信息图网格 */
        /* ═══════════════════════════════════════════════════════════ */
        .infographic-layout {{
            height: 100%;
        }}
        .infographic-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 24px;
            margin-top: 24px;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* v2.0 新增：流程图 */
        /* ═══════════════════════════════════════════════════════════ */
        .process-flow {{
            display: flex;
            align-items: flex-start;
            justify-content: center;
            gap: 16px;
            margin-top: 40px;
            flex-wrap: wrap;
        }}
        .flow-step {{
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            max-width: 180px;
        }}
        .flow-icon {{
            width: 64px;
            height: 64px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            font-weight: 700;
            border: 2px solid;
            margin-bottom: 16px;
        }}
        .flow-content {{
            font-size: 1rem;
            line-height: 1.5;
            color: {c["text_secondary"]};
        }}
        .flow-arrow {{
            font-size: 2rem;
            font-weight: 700;
            margin-top: 16px;
            opacity: 0.6;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* v2.0 新增：对比页 */
        /* ═══════════════════════════════════════════════════════════ */
        .comparison-layout {{
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            gap: 24px;
            margin-top: 32px;
            align-items: stretch;
        }}
        .comparison-side {{
            background: {c["card_bg"]};
            border: 1px solid;
            border-radius: 16px;
            padding: 32px;
        }}
        .comparison-header {{
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid;
        }}
        .comparison-body {{
            font-size: 1rem;
            line-height: 1.8;
        }}
        .comparison-vs {{
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
            font-weight: 800;
            color: {c["text_secondary"]};
            opacity: 0.5;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* v2.0 新增：画廊 */
        /* ═══════════════════════════════════════════════════════════ */
        .gallery-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-top: 32px;
        }}
        .gallery-card {{
            background: {c["card_bg"]};
            border: 1px solid {c["border"]};
            border-radius: 16px;
            padding: 28px;
            text-align: center;
            transition: all 0.3s ease;
        }}
        .gallery-card:hover {{
            background: {c["card_bg_hover"]};
            transform: translateY(-4px);
        }}
        .gallery-icon {{
            margin-bottom: 16px;
            display: flex;
            justify-content: center;
        }}
        .gallery-title {{
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 8px;
            color: {c["text_primary"]};
        }}
        .gallery-desc {{
            font-size: 0.9rem;
            color: {c["text_secondary"]};
            line-height: 1.5;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* v2.0 新增：金句页 */
        /* ═══════════════════════════════════════════════════════════ */
        .slide-statement {{
            text-align: center;
            max-width: 1000px;
            margin: 0 auto;
            position: relative;
        }}
        .statement-decoration {{
            position: absolute;
            top: -60px;
            left: 50%;
            transform: translateX(-50%);
            opacity: 0.15;
            z-index: 0;
        }}
        .statement-decoration svg {{
            width: 300px;
            height: 200px;
        }}
        .slide-statement h1 {{
            font-size: 3.2rem;
            font-weight: 800;
            line-height: 1.3;
            position: relative;
            z-index: 1;
        }}
        .statement-subtitle {{
            font-size: 1.4rem;
            color: {c["text_secondary"]};
            margin-top: 24px;
            position: relative;
            z-index: 1;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 表格 */
        /* ═══════════════════════════════════════════════════════════ */
        .table-wrapper {{
            margin-top: 24px;
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 1rem;
        }}
        th, td {{
            padding: 14px 18px;
            text-align: left;
            border-bottom: 1px solid {c["border"]};
        }}
        th {{
            font-weight: 600;
            color: {c["accent"]};
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        tr:hover td {{
            background: {c["card_bg"]};
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 底部 */
        /* ═══════════════════════════════════════════════════════════ */
        .slide-footer {{
            display: flex;
            justify-content: flex-end;
            padding-top: 20px;
        }}
        .slide-number {{
            font-size: 0.85rem;
            color: {c["text_secondary"]};
            opacity: 0.6;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 进度条 */
        /* ═══════════════════════════════════════════════════════════ */
        .progress-bar {{
            position: fixed;
            bottom: 0;
            left: 0;
            height: 3px;
            background: {c["accent_gradient"]};
            transition: width 0.3s ease;
            z-index: 100;
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 导航按钮 */
        /* ═══════════════════════════════════════════════════════════ */
        .nav-btn {{
            position: fixed;
            top: 50%;
            transform: translateY(-50%);
            background: {c["card_bg"]};
            border: 1px solid {c["border"]};
            color: {c["text_primary"]};
            width: 50px;
            height: 50px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 1.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
            z-index: 100;
        }}
        .nav-btn:hover {{
            background: {c["accent"]};
            border-color: {c["accent"]};
        }}
        .nav-prev {{ left: 20px; }}
        .nav-next {{ right: 20px; }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 目录 */
        /* ═══════════════════════════════════════════════════════════ */
        .toc-panel {{
            position: fixed;
            top: 0;
            right: -340px;
            width: 340px;
            height: 100%;
            background: {c["bg_secondary"]};
            border-left: 1px solid {c["border"]};
            padding: 40px 24px;
            transition: right 0.3s ease;
            z-index: 200;
            overflow-y: auto;
        }}
        .toc-panel.open {{ right: 0; }}
        .toc-panel h3 {{
            font-size: 1.1rem;
            margin-bottom: 20px;
            color: {c["text_secondary"]};
        }}
        .toc-section {{
            font-size: 0.75rem;
            font-weight: 700;
            color: {c["accent"]};
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-top: 20px;
            margin-bottom: 8px;
            padding-left: 12px;
        }}
        .toc-item {{
            padding: 10px 12px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            color: {c["text_secondary"]};
            transition: all 0.2s;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .toc-item:hover {{
            background: {c["card_bg"]};
            color: {c["text_primary"]};
        }}
        .toc-toggle {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: {c["card_bg"]};
            border: 1px solid {c["border"]};
            color: {c["text_primary"]};
            padding: 10px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            z-index: 200;
        }}
        
        /* FIX: Config 字段生效 —— show_page_numbers */
        {page_num_css}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 打印样式 */
        /* ═══════════════════════════════════════════════════════════ */
        @media print {{
            .slide {{
                display: block !important;
                page-break-after: always;
                position: static;
                height: auto;
                min-height: 100vh;
            }}
            .nav-btn, .toc-toggle, .toc-panel, .progress-bar {{ display: none !important; }}
        }}
        
        /* ═══════════════════════════════════════════════════════════ */
        /* 响应式 */
        /* ═══════════════════════════════════════════════════════════ */
        @media (max-width: 768px) {{
            .slide {{ padding: 30px 24px; }}
            .slide-title h1 {{ font-size: 2.5rem; }}
            .slide-content-layout h2 {{ font-size: 1.8rem; }}
            .two-column {{ grid-template-columns: 1fr; }}
            .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .comparison-layout {{ grid-template-columns: 1fr; }}
            .comparison-vs {{ display: none; }}
            .process-flow {{ flex-direction: column; align-items: center; }}
            .flow-arrow {{ transform: rotate(90deg); }}
            .visual-overlay h1 {{ font-size: 2rem; }}
            .slide-statement h1 {{ font-size: 2rem; }}
        }}
    </style>
</head>
<body>
    <div class="presentation" id="presentation">
        {slides_str}
    </div>
    
    {progress_html}
    {nav_html}
    {toc_btn_html}
    {toc_panel_html}
    
    <script>
        let currentSlide = 1;
        const totalSlides = {len(slides_html)};
        
        function showSlide(n) {{
            const slides = document.querySelectorAll('.slide');
            if (n > totalSlides) currentSlide = 1;
            if (n < 1) currentSlide = totalSlides;
            
            slides.forEach(s => s.classList.remove('active'));
            document.querySelector(`.slide[data-index="${{currentSlide}}"]`)?.classList.add('active');
            
            document.getElementById('progressBar').style.width = (currentSlide / totalSlides * 100) + '%';
        }}
        
        function nextSlide() {{ currentSlide++; showSlide(currentSlide); }}
        function prevSlide() {{ currentSlide--; showSlide(currentSlide); }}
        function goToSlide(n) {{ currentSlide = n; showSlide(currentSlide); toggleToc(); }}
        
        function toggleToc() {{
            document.getElementById('tocPanel').classList.toggle('open');
        }}
        
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'ArrowRight' || e.key === ' ') nextSlide();
            if (e.key === 'ArrowLeft') prevSlide();
            if (e.key === 'Escape') toggleToc();
        }});
        
        showSlide(1);
    </script>
</body>
</html>'''
    
    @staticmethod
    def _escape(text: str) -> str:
        """HTML 转义"""
        return html.escape(str(text))


def render_presentation(presentation: Presentation, output_path: str) -> str:
    """便捷函数：渲染并保存到文件"""
    renderer = PresentationRenderer(theme=presentation.theme)
    html_content = renderer.render(presentation)
    
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_content, encoding="utf-8")
    
    return str(output.resolve())
