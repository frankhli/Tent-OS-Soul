"""PPT 数据结构定义 —— Presentation Schema v2.0

纯 Python 数据结构，用于描述幻灯片的完整内容。
渲染器（renderer.py）将这些数据转换为 HTML。

v2.0 新增：
- svg 元素类型：LLM 直接生成 SVG 代码嵌入幻灯片
- icon 元素类型：调用内置图标库
- visual / infographic / process_flow / comparison 新 slide 类型
- style_override：LLM 自定义任意 CSS
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class ChartData:
    """图表数据"""
    labels: List[str] = field(default_factory=list)
    values: List[float] = field(default_factory=list)
    colors: List[str] = field(default_factory=list)
    title: str = ""
    chart_type: str = "bar"  # bar, line, pie, area, donut, radar, progress, funnel


@dataclass
class SlideElement:
    """幻灯片中的单个元素"""
    type: str = "text"  # text, image, chart, quote, kpi, table, svg, icon
    content: str = ""
    style: Dict[str, Any] = field(default_factory=dict)
    # chart 类型时使用
    chart_data: Optional[ChartData] = None
    # table 类型时使用
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    # svg 类型：content 字段直接放 SVG 代码字符串
    # icon 类型：content 字段放图标名称（如 "rocket", "chart"）


@dataclass
class Slide:
    """单页幻灯片"""
    type: str = "content"
    # 支持的类型：
    # title(封面), content(内容页), two_column(双栏), chart(图表),
    # timeline(时间线), quote(引用), data(KPI), section_divider(章节分隔),
    # visual(全屏视觉), infographic(信息图), process_flow(流程图),
    # comparison(对比页), gallery(画廊), statement(金句/声明页)
    title: str = ""
    subtitle: str = ""
    # content 类型：bullet points
    bullets: List[str] = field(default_factory=list)
    # two_column / comparison 类型
    left_elements: List[SlideElement] = field(default_factory=list)
    right_elements: List[SlideElement] = field(default_factory=list)
    # 通用元素列表（svg, icon, chart, kpi, text, image 等）
    elements: List[SlideElement] = field(default_factory=list)
    # 背景样式覆盖：可以是颜色、渐变、或 "custom" 表示用 style_override
    background: str = ""
    # 动画效果
    animation: str = "fade"  # fade, slide, zoom, none
    # 备注（演讲者备注，不显示在幻灯片上）
    notes: str = ""
    # LLM 自定义 CSS 覆盖（用于高级视觉设计）
    style_override: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Section:
    """章节"""
    title: str = ""
    subtitle: str = ""
    slides: List[Slide] = field(default_factory=list)


@dataclass
class Presentation:
    """完整的演示文稿"""
    title: str = ""
    subtitle: str = ""
    author: str = "Tent OS"
    date: str = ""
    theme: str = "dark_modern"
    # 章节列表
    sections: List[Section] = field(default_factory=list)
    # 全局配置
    config: Dict[str, Any] = field(default_factory=lambda: {
        "show_progress": True,
        "show_navigation": True,
        "show_page_numbers": True,
        "animation_duration": 600,
    })
    
    def total_slides(self) -> int:
        """计算总页数"""
        return sum(len(s.slides) for s in self.sections)
    
    def to_dict(self) -> Dict:
        """序列化为字典（用于 LLM 生成 JSON）"""
        from dataclasses import asdict
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Presentation":
        """从字典反序列化（兼容平铺和嵌套格式）"""
        sections = []
        raw_sections = data.get("sections")
        
        # 兼容平铺格式：直接把 slides 包进一个 section
        if not raw_sections:
            slides_raw = data.get("slides", [])
            if slides_raw:
                raw_sections = [{"title": "", "slides": slides_raw}]
        
        for sec_data in (raw_sections or []):
            slides = []
            for slide_data in sec_data.get("slides", []):
                elements = []
                for elem_data in slide_data.get("elements", []):
                    chart_data = None
                    if "chart_data" in elem_data and elem_data["chart_data"]:
                        chart_data = ChartData(**elem_data["chart_data"])
                    elements.append(SlideElement(
                        type=elem_data.get("type", "text"),
                        content=elem_data.get("content", ""),
                        style=elem_data.get("style", {}),
                        chart_data=chart_data,
                        headers=elem_data.get("headers", []),
                        rows=elem_data.get("rows", []),
                    ))
                
                # 处理 style_override
                style_override = slide_data.get("style_override", {})
                
                slides.append(Slide(
                    type=slide_data.get("type", "content"),
                    title=slide_data.get("title", ""),
                    subtitle=slide_data.get("subtitle", ""),
                    bullets=slide_data.get("bullets", []),
                    left_elements=[SlideElement(**e) for e in slide_data.get("left_elements", [])],
                    right_elements=[SlideElement(**e) for e in slide_data.get("right_elements", [])],
                    elements=elements,
                    background=slide_data.get("background", ""),
                    animation=slide_data.get("animation", "fade"),
                    notes=slide_data.get("notes", ""),
                    style_override=style_override,
                ))
            sections.append(Section(
                title=sec_data.get("title", ""),
                subtitle=sec_data.get("subtitle", ""),
                slides=slides,
            ))
        
        return cls(
            title=data.get("title", ""),
            subtitle=data.get("subtitle", ""),
            author=data.get("author", "Tent OS"),
            date=data.get("date", ""),
            theme=data.get("theme", "dark_modern"),
            sections=sections,
            config=data.get("config", {}),
        )
