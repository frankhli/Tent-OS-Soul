"""Spreadsheet Schema —— Excel 数据结构定义

支持多 sheet、图表、条件格式、公式。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class CellFormat:
    """单元格格式"""
    bold: bool = False
    italic: bool = False
    font_color: str = ""  # hex, 如 #FF0000
    bg_color: str = ""    # hex
    num_format: str = ""  # 如 "0.00", "#,##0", "0%", "yyyy-mm-dd"
    align: str = ""       # left, center, right
    valign: str = ""      # top, middle, bottom


@dataclass
class ChartConfig:
    """内嵌图表配置"""
    chart_type: str = "column"  # column, bar, line, pie, area, scatter
    title: str = ""
    x_column: int = 0  # 作为 X 轴的数据列索引
    y_columns: List[int] = field(default_factory=list)  # 作为 Y 轴的数据列索引
    series_names: List[str] = field(default_factory=list)


@dataclass
class ConditionalFormat:
    """条件格式规则"""
    type: str = ""  # cell, top, bottom, formula
    criteria: str = ""  # >, <, >=, <=, ==, between
    value: Any = None
    value2: Any = None
    format: Dict[str, Any] = field(default_factory=dict)  # bg_color, font_color


@dataclass
class ExcelSheet:
    """单个工作表"""
    name: str = "Sheet1"
    headers: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    # 列宽: {列索引: 宽度}
    column_widths: Dict[int, int] = field(default_factory=dict)
    # 单元格格式: {"A1": CellFormat, "B2": CellFormat}
    cell_formats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # 合并单元格: [(start_row, start_col, end_row, end_col), ...]
    merges: List[tuple] = field(default_factory=list)
    # 公式: {"C3": "=A1+B1"}
    formulas: Dict[str, str] = field(default_factory=dict)
    # 条件格式
    conditional_formats: List[ConditionalFormat] = field(default_factory=list)
    # 内嵌图表
    charts: List[ChartConfig] = field(default_factory=list)
    # 冻结窗格: (row, col)
    freeze_panes: Optional[tuple] = None


@dataclass
class ExcelWorkbook:
    """Excel 工作簿"""
    title: str = ""
    author: str = "Tent OS"
    sheets: List[ExcelSheet] = field(default_factory=list)
    # 主题色（复用 PPT 主题名）
    theme: str = "light_corporate"
    
    def to_dict(self) -> Dict:
        from dataclasses import asdict
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ExcelWorkbook":
        sheets = []
        for s in data.get("sheets", []):
            # FIX: 过滤掉 dataclass 不认识的字段（LLM 可能生成额外字段如 'type'）
            charts = [ChartConfig(**{k: v for k, v in c.items() if k in ChartConfig.__dataclass_fields__}) for c in s.get("charts", [])]
            conds = [ConditionalFormat(**{k: v for k, v in c.items() if k in ConditionalFormat.__dataclass_fields__}) for c in s.get("conditional_formats", [])]
            sheets.append(ExcelSheet(
                name=s.get("name", "Sheet1"),
                headers=s.get("headers", []),
                rows=s.get("rows", []),
                column_widths=s.get("column_widths", {}),
                cell_formats=s.get("cell_formats", {}),
                merges=[tuple(m) for m in s.get("merges", [])],
                formulas=s.get("formulas", {}),
                conditional_formats=conds,
                charts=charts,
                freeze_panes=tuple(s["freeze_panes"]) if s.get("freeze_panes") else None,
            ))
        return cls(
            title=data.get("title", ""),
            author=data.get("author", "Tent OS"),
            sheets=sheets,
            theme=data.get("theme", "light_corporate"),
        )
