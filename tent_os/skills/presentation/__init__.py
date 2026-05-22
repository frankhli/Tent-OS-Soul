"""Presentation Skill —— PPT 渲染引擎

将 JSON 格式的 Presentation 数据结构渲染为精美的 HTML 幻灯片。
"""

from tent_os.skills.presentation.schema import (
    Presentation, Slide, SlideElement, Section, ChartData
)
from tent_os.skills.presentation.renderer import (
    PresentationRenderer, render_presentation
)

__all__ = [
    "Presentation", "Slide", "SlideElement", "Section", "ChartData",
    "PresentationRenderer", "render_presentation",
]
