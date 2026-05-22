"""Word Schema —— Word 文档数据结构定义

支持段落、表格、图片、页眉页脚、目录。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class WordParagraph:
    """段落"""
    text: str = ""
    style: str = "Normal"  # Normal, Heading 1-3, Quote, List Bullet, List Number
    bold: bool = False
    italic: bool = False
    font_size: int = 0  # 0 = 使用样式默认
    font_color: str = ""  # hex, 如 #FF0000
    alignment: str = ""  # left, center, right, justify
    page_break_before: bool = False


@dataclass
class WordTable:
    """表格"""
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    style: str = "Table Grid"  # python-docx 内置表格样式
    column_widths: List[int] = field(default_factory=list)  # 单位: 毫米


@dataclass
class WordImage:
    """图片（URL 或 base64）"""
    source: str = ""  # URL 或 base64 data URI
    width: int = 0   # 毫米
    height: int = 0  # 毫米
    caption: str = ""


@dataclass
class WordHeaderFooter:
    """页眉页脚"""
    header_text: str = ""
    footer_text: str = ""
    show_page_numbers: bool = True


@dataclass
class WordDocument:
    """Word 文档"""
    title: str = ""
    subtitle: str = ""
    author: str = "Tent OS"
    date: str = ""
    # 内容块：段落、表格、图片
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    # 页眉页脚
    header_footer: Optional[WordHeaderFooter] = None
    # 全局配置
    config: Dict[str, Any] = field(default_factory=lambda: {
        "font_name": "微软雅黑",
        "font_size": 10.5,  # 五号字 ≈ 10.5pt
        "line_spacing": 1.5,
        "page_margin_top": 25,    # 毫米
        "page_margin_bottom": 25,
        "page_margin_left": 30,
        "page_margin_right": 30,
        "show_toc": False,  # 自动生成目录
    })
    
    def to_dict(self) -> Dict:
        from dataclasses import asdict
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "WordDocument":
        blocks = []
        for b in data.get("blocks", []):
            b_type = b.get("type", "paragraph")
            if b_type == "paragraph":
                blocks.append({"type": "paragraph", "data": WordParagraph(**b.get("data", {}))})
            elif b_type == "table":
                blocks.append({"type": "table", "data": WordTable(**b.get("data", {}))})
            elif b_type == "image":
                blocks.append({"type": "image", "data": WordImage(**b.get("data", {}))})
            else:
                blocks.append(b)
        
        hf_data = data.get("header_footer")
        hf = WordHeaderFooter(**hf_data) if hf_data else None
        
        return cls(
            title=data.get("title", ""),
            subtitle=data.get("subtitle", ""),
            author=data.get("author", "Tent OS"),
            date=data.get("date", ""),
            blocks=blocks,
            header_footer=hf,
            config=data.get("config", {}),
        )
