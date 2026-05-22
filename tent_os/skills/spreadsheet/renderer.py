"""Spreadsheet Excel 渲染引擎 —— xlsxwriter

将 ExcelWorkbook 数据结构渲染为 .xlsx 文件。
支持：多 sheet、格式、图表、条件格式、公式、冻结窗格。
"""

from pathlib import Path
from typing import Dict, Any

from tent_os.skills.spreadsheet.schema import ExcelWorkbook, ExcelSheet, CellFormat, ChartConfig


def _to_cell_notation(row: int, col: int) -> str:
    """行列索引转 Excel 单元格标记，如 (0, 0) -> A1"""
    col_str = ""
    c = col
    while c >= 0:
        col_str = chr(65 + (c % 26)) + col_str
        c = c // 26 - 1
    return f"{col_str}{row + 1}"


def _cell_format_to_xlsx(fmt_dict: Dict[str, Any], workbook) -> Any:
    """将 CellFormat dict 转为 xlsxwriter Format 对象"""
    if not fmt_dict:
        return None
    props = {}
    if fmt_dict.get("bold"):
        props["bold"] = True
    if fmt_dict.get("italic"):
        props["italic"] = True
    if fmt_dict.get("font_color"):
        props["font_color"] = fmt_dict["font_color"]
    if fmt_dict.get("bg_color"):
        props["bg_color"] = fmt_dict["bg_color"]
    if fmt_dict.get("num_format"):
        props["num_format"] = fmt_dict["num_format"]
    if fmt_dict.get("align"):
        props["align"] = fmt_dict["align"]
    if fmt_dict.get("valign"):
        props["valign"] = fmt_dict["valign"]
    return workbook.add_format(props)


class SpreadsheetRenderer:
    """Excel 渲染器"""
    
    # 复用 PPT 主题色板
    from tent_os.skills.presentation.renderer import PresentationRenderer
    THEMES = PresentationRenderer.THEMES
    
    def __init__(self, theme: str = "light_corporate"):
        self.theme = theme
        self.colors = self.THEMES.get(theme, self.THEMES["light_corporate"])
    
    def render(self, workbook_data: ExcelWorkbook, output_path: str) -> str:
        """渲染 ExcelWorkbook 为 .xlsx 文件"""
        try:
            import xlsxwriter
        except ImportError:
            raise ImportError("xlsxwriter 未安装，请运行: pip install xlsxwriter")
        
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        wb = xlsxwriter.Workbook(str(output))
        wb.set_properties({"title": workbook_data.title, "author": workbook_data.author})
        
        for sheet_data in workbook_data.sheets:
            self._render_sheet(wb, sheet_data)
        
        wb.close()
        return str(output)
    
    def _render_sheet(self, wb, sheet_data: ExcelSheet):
        """渲染单个 sheet"""
        ws = wb.add_worksheet(sheet_data.name)
        
        # 预定义格式缓存
        format_cache: Dict[str, Any] = {}
        
        # 列宽
        for col_idx, width in sheet_data.column_widths.items():
            ws.set_column(col_idx, col_idx, width)
        
        # 写入表头（如果有）
        row_offset = 0
        if sheet_data.headers:
            header_format = wb.add_format({
                "bold": True,
                "bg_color": self.colors.get("accent", "#2563eb"),
                "font_color": "#FFFFFF",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
            })
            for col_idx, header in enumerate(sheet_data.headers):
                ws.write(0, col_idx, header, header_format)
            row_offset = 1
        
        # 写入数据行
        for r_idx, row in enumerate(sheet_data.rows):
            excel_row = r_idx + row_offset
            for c_idx, value in enumerate(row):
                cell_ref = _to_cell_notation(excel_row, c_idx)
                fmt_dict = sheet_data.cell_formats.get(cell_ref)
                fmt = _cell_format_to_xlsx(fmt_dict, wb) if fmt_dict else None
                ws.write(excel_row, c_idx, value, fmt)
        
        # 写入公式
        for cell_ref, formula in sheet_data.formulas.items():
            ws.write_formula(cell_ref, formula)
        
        # 合并单元格
        for merge in sheet_data.merges:
            if len(merge) == 4:
                ws.merge_range(*merge)
        
        # 条件格式
        for cond in sheet_data.conditional_formats:
            def _cget(obj, attr, default=None):
                if isinstance(obj, dict):
                    return obj.get(attr, default)
                return getattr(obj, attr, default)
            
            fmt_props = _cget(cond, "format", {})
            cond_fmt = wb.add_format({
                "bg_color": fmt_props.get("bg_color", "#FFC7CE") if isinstance(fmt_props, dict) else getattr(fmt_props, "bg_color", "#FFC7CE"),
                "font_color": fmt_props.get("font_color", "#9C0006") if isinstance(fmt_props, dict) else getattr(fmt_props, "font_color", "#9C0006"),
            })
            # 简化：全表范围的条件格式
            if _cget(cond, "type") == "cell":
                ws.conditional_format(
                    f"A1:Z1000",
                    {"type": "cell", "criteria": _cget(cond, "criteria", ">"), "value": _cget(cond, "value", 0), "format": cond_fmt}
                )
        
        # 内嵌图表
        for chart_cfg in sheet_data.charts:
            self._render_chart(ws, wb, chart_cfg, row_offset, len(sheet_data.rows))
        
        # 冻结窗格
        if sheet_data.freeze_panes:
            ws.freeze_panes(*sheet_data.freeze_panes)
    
    def _render_chart(self, ws, wb, chart_cfg, row_offset: int, data_rows: int):
        """渲染内嵌图表（兼容 ChartConfig 对象和 dict）"""
        import xlsxwriter
        
        # 统一提取属性（兼容对象和 dict）
        def _get(attr, default=None):
            if isinstance(chart_cfg, dict):
                return chart_cfg.get(attr, default)
            return getattr(chart_cfg, attr, default)
        
        y_columns = _get("y_columns", [])
        # FIX: 如果图表没有指定数据系列，跳过渲染（避免 xlsxwriter 报错）
        if not y_columns:
            return
        
        chart_types = {
            "column": {"type": "column", "subtype": "clustered"},
            "bar": {"type": "bar", "subtype": "clustered"},
            "line": {"type": "line", "subtype": None},
            "pie": {"type": "pie", "subtype": None},
            "area": {"type": "area", "subtype": "stacked"},
            "scatter": {"type": "scatter", "subtype": "straight_with_markers"},
        }
        
        ct = chart_types.get(_get("chart_type", "column"), chart_types["column"])
        chart = wb.add_chart(ct)
        
        title = _get("title", "")
        if title:
            chart.set_title({"name": title})
        
        # 数据范围：从 row_offset 开始，共 data_rows 行
        first_data_row = row_offset
        last_data_row = row_offset + data_rows
        
        x_column = _get("x_column", 0)
        series_names = _get("series_names", [])
        
        for y_col in y_columns:
            series_name = series_names[y_col] if y_col < len(series_names) else f"Series {y_col}"
            chart.add_series({
                "name": series_name,
                "categories": [ws.name, first_data_row, x_column, last_data_row, x_column],
                "values": [ws.name, first_data_row, y_col, last_data_row, y_col],
            })
        
        chart.set_x_axis({"name": ""})
        chart.set_y_axis({"name": ""})
        
        # 插入到数据右侧
        insert_col = max(list(y_columns) + [x_column], default=0) + 2
        ws.insert_chart(row_offset, insert_col, chart)


def render_excel(workbook: ExcelWorkbook, output_path: str) -> str:
    """便捷函数：渲染 Excel 并保存"""
    renderer = SpreadsheetRenderer(theme=workbook.theme)
    return renderer.render(workbook, output_path)
