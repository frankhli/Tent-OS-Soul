"""RenderExecutor —— 办公渲染执行器

连接工具定义 (render_ppt/render_document/render_contract/render_excel/render_word)
与渲染器 (skills/presentation/document/spreadsheet/word)，实现端到端自动化。

执行流程:
1. 接收工具调用参数 (JSON 格式数据 + 主题/文件名)
2. 校验并反序列化为对应 Schema
3. 调用渲染器生成 HTML
4. 保存到输出目录
5. 返回文件路径和预览链接

Tent OS 差异化：
- 纯 Python，零外部依赖（如 LibreOffice/pandoc）
- 生成的是精美 HTML，可直接浏览器打开或转 PDF
- 支持主题切换、CSS 动画、响应式布局
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

from tent_os.logging_config import get_logger
from tent_os.plugins.base import ExecutorPlugin

logger = get_logger()

# 输出目录
RENDER_OUTPUT_DIR = Path("./tent_memory/renders")


class RenderExecutor(ExecutorPlugin):
    """办公渲染执行器

    支持 action:
    - render_ppt: 渲染 PPT 为 HTML
    - render_document: 渲染通用文档为 HTML
    - render_contract: 渲染合同为 HTML
    - render_excel: 渲染表格为 HTML
    - render_word: 渲染 Word 风格文档为 HTML
    """

    def __init__(self, output_dir: str = "./tent_memory/renders"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 懒加载渲染器
        self._renderers: Dict[str, Any] = {}

    def name(self) -> str:
        return "render"

    def version(self) -> str:
        return "1.0.0"

    async def initialize(self, config: Dict) -> None:
        self.output_dir = Path(config.get("output_dir", "./tent_memory/renders"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def supported_actions(self) -> list:
        return ["render_ppt", "render_document", "render_contract",
                "render_excel", "render_word"]

    async def execute(self, action: str, params: Dict) -> Dict:
        """执行渲染任务"""
        start_time = time.time()

        try:
            if action == "render_ppt":
                return await self._render_ppt(params, start_time)
            elif action == "render_document":
                return await self._render_document(params, start_time)
            elif action == "render_contract":
                return await self._render_contract(params, start_time)
            elif action == "render_excel":
                return await self._render_excel(params, start_time)
            elif action == "render_word":
                return await self._render_word(params, start_time)
            else:
                return {"status": "error", "error": f"不支持的渲染类型: {action}"}
        except Exception as e:
            logger.error(f"[Render] 渲染失败 [{action}]: {e}")
            return {"status": "error", "error": str(e)}

    async def get_status(self, task_id: str) -> Dict:
        return {"status": "completed"}

    # ========== 内部实现 ==========

    async def _render_ppt(self, params: Dict, start_time: float) -> Dict:
        """渲染 PPT"""
        from tent_os.skills.presentation.schema import Presentation, Slide, SlideElement
        from tent_os.skills.presentation.renderer import PresentationRenderer

        data = params.get("data", params)
        theme = params.get("theme", "dark_modern")
        filename = params.get("filename", f"presentation_{int(time.time())}")

        # 构建 Presentation 对象
        presentation = self._build_presentation(data, theme)

        # 渲染
        renderer = PresentationRenderer()
        html = renderer.render(presentation)

        # 保存
        output_path = self._save_html(filename, html, "ppt")

        return {
            "status": "completed",
            "file_path": str(output_path),
            "file_url": f"/renders/{output_path.name}",
            "slides_count": presentation.total_slides(),
            "theme": theme,
            "elapsed_ms": round((time.time() - start_time) * 1000, 1),
        }

    async def _render_document(self, params: Dict, start_time: float) -> Dict:
        """渲染通用文档"""
        from tent_os.skills.document.schema import Document, DocumentSection
        from tent_os.skills.document.renderer import DocumentRenderer

        data = params.get("data", params)
        theme = params.get("theme", "light_corporate")
        filename = params.get("filename", f"document_{int(time.time())}")

        doc = self._build_document(data, theme)
        renderer = DocumentRenderer(theme=theme)
        html = renderer.render_document(doc)

        output_path = self._save_html(filename, html, "document")

        return {
            "status": "completed",
            "file_path": str(output_path),
            "file_url": f"/renders/{output_path.name}",
            "sections_count": len(doc.sections),
            "theme": theme,
            "elapsed_ms": round((time.time() - start_time) * 1000, 1),
        }

    async def _render_contract(self, params: Dict, start_time: float) -> Dict:
        """渲染合同"""
        from tent_os.skills.document.schema import Contract, ContractClause, ContractParty, ContractParty
        from tent_os.skills.document.renderer import DocumentRenderer

        data = params.get("data", params)
        theme = params.get("theme", "light_corporate")
        filename = params.get("filename", f"contract_{int(time.time())}")

        contract = self._build_contract(data, theme)
        renderer = DocumentRenderer(theme=theme)
        html = renderer.render_contract(contract)

        output_path = self._save_html(filename, html, "contract")

        return {
            "status": "completed",
            "file_path": str(output_path),
            "file_url": f"/renders/{output_path.name}",
            "clauses_count": len(contract.clauses),
            "theme": theme,
            "elapsed_ms": round((time.time() - start_time) * 1000, 1),
        }

    async def _render_excel(self, params: Dict, start_time: float) -> Dict:
        """渲染表格（HTML 格式）"""
        data = params.get("data", params)
        theme = params.get("theme", "light_corporate")
        filename = params.get("filename", f"spreadsheet_{int(time.time())}")

        sheets = data.get("sheets", [data]) if isinstance(data, dict) else [{"title": "Sheet1", "data": data}]

        html = self._build_excel_html(sheets, theme)
        output_path = self._save_html(filename, html, "excel")

        return {
            "status": "completed",
            "file_path": str(output_path),
            "file_url": f"/renders/{output_path.name}",
            "sheets_count": len(sheets),
            "theme": theme,
            "elapsed_ms": round((time.time() - start_time) * 1000, 1),
        }

    async def _render_word(self, params: Dict, start_time: float) -> Dict:
        """渲染 Word 风格文档（HTML 输出，不依赖 python-docx）"""
        data = params.get("data", params)
        theme = params.get("theme", "light_corporate")
        filename = params.get("filename", f"word_{int(time.time())}")

        # 生成 Word 风格 HTML（纯 Python，零外部依赖）
        html = self._build_word_html(data, theme)
        output_path = self._save_html(filename, html, "word")
        return {
            "status": "completed",
            "file_path": str(output_path),
            "file_url": f"/renders/{output_path.name}",
            "theme": theme,
            "format": "html",
            "elapsed_ms": round((time.time() - start_time) * 1000, 1),
        }

    # ========== 构建器 ==========

    def _build_presentation(self, data: Dict, theme: str):
        """从 dict 构建 Presentation 对象"""
        from tent_os.skills.presentation.schema import Presentation, Section, Slide, SlideElement, ChartData

        slides = []
        for s_data in data.get("slides", []):
            elements = []
            for e_data in s_data.get("elements", []):
                chart_data = None
                if e_data.get("chart_data"):
                    cd = e_data["chart_data"]
                    chart_data = ChartData(
                        labels=cd.get("labels", []),
                        values=cd.get("values", []),
                        colors=cd.get("colors", []),
                        title=cd.get("title", ""),
                        chart_type=cd.get("chart_type", "bar"),
                    )
                elements.append(SlideElement(
                    type=e_data.get("type", "text"),
                    content=e_data.get("content", ""),
                    style=e_data.get("style", {}),
                    chart_data=chart_data,
                    headers=e_data.get("headers", []),
                    rows=e_data.get("rows", []),
                ))
            slides.append(Slide(
                type=s_data.get("type", "content"),
                title=s_data.get("title", ""),
                subtitle=s_data.get("subtitle", ""),
                elements=elements,
                notes=s_data.get("notes", ""),
                style_override=s_data.get("style_override", {}),
            ))

        return Presentation(
            title=data.get("title", "Untitled"),
            subtitle=data.get("subtitle", ""),
            author=data.get("author", "Tent OS"),
            theme=theme,
            sections=[Section(title="", slides=slides)],
            config=data.get("config", {}),
        )

    def _build_document(self, data: Dict, theme: str):
        """从 dict 构建 Document 对象"""
        from tent_os.skills.document.schema import Document, DocumentSection

        sections = []
        for s_data in data.get("sections", []):
            sections.append(DocumentSection(
                title=s_data.get("title", ""),
                content=s_data.get("content", ""),
                level=s_data.get("level", 1),
            ))

        return Document(
            title=data.get("title", "Untitled"),
            subtitle=data.get("subtitle", ""),
            author=data.get("author", "Tent OS"),
            theme=theme,
            sections=sections,
            config=data.get("config", {}),
        )

    def _build_contract(self, data: Dict, theme: str):
        """从 dict 构建 Contract 对象"""
        from tent_os.skills.document.schema import Contract, ContractClause, ContractParty

        clauses = []
        for c_data in data.get("clauses", []):
            clauses.append(ContractClause(
                number=c_data.get("number", ""),
                title=c_data.get("title", ""),
                content=c_data.get("content", ""),
            ))

        parties = []
        for p in data.get("parties", []):
            if isinstance(p, str):
                parties.append(ContractParty(name=p))
            else:
                parties.append(ContractParty(**p))

        return Contract(
            title=data.get("title", "合同"),
            contract_no=data.get("contract_no", ""),
            date=data.get("date", data.get("effective_date", "")),
            theme=theme,
            parties=parties,
            clauses=clauses,
        )

    def _build_excel_html(self, sheets: list, theme: str) -> str:
        """构建 Excel 风格 HTML 表格"""
        colors = {
            "header_bg": "#2563eb" if theme == "light_corporate" else "#6366f1",
            "header_text": "#ffffff",
            "row_odd": "#f8fafc" if theme == "light_corporate" else "#1e1e2e",
            "row_even": "#ffffff" if theme == "light_corporate" else "#252535",
            "text": "#1e293b" if theme == "light_corporate" else "#f0f0f5",
            "border": "#e2e8f0" if theme == "light_corporate" else "#333",
        }

        sheets_html = ""
        for sheet in sheets:
            title = sheet.get("title", "Sheet")
            rows = sheet.get("data", [])
            if not rows:
                continue

            header = rows[0] if rows else []
            body_rows = rows[1:] if len(rows) > 1 else []

            header_html = "".join(
                f'<th style="padding:10px;border:1px solid {colors["border"]};'
                f'background:{colors["header_bg"]};color:{colors["header_text"]};'
                f'font-weight:600;text-align:left">{h}</th>'
                for h in header
            )

            body_html = ""
            for i, row in enumerate(body_rows):
                bg = colors["row_odd"] if i % 2 == 0 else colors["row_even"]
                cells = "".join(
                    f'<td style="padding:8px 10px;border:1px solid {colors["border"]};'
                    f'background:{bg};color:{colors["text"]}">{cell}</td>'
                    for cell in row
                )
                body_html += f"<tr>{cells}</tr>"

            sheets_html += f'''
            <h2 style="margin:20px 0 10px;color:{colors['text']};font-size:18px">{title}</h2>
            <table style="width:100%;border-collapse:collapse;font-family:system-ui,sans-serif">
                <thead><tr>{header_html}</tr></thead>
                <tbody>{body_html}</tbody>
            </table>
            '''

        return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Spreadsheet</title>
<style>body{{margin:20px;font-family:system-ui,sans-serif;background:{colors["row_even"]}}}</style>
</head><body>{sheets_html}</body></html>'''

    def _build_word_html(self, data: Dict, theme: str) -> str:
        """构建 Word 风格 HTML 文档"""
        colors = {
            "bg": "#ffffff" if theme == "light_corporate" else "#1a1a2e",
            "text": "#1e293b" if theme == "light_corporate" else "#f0f0f5",
            "heading": "#2563eb" if theme == "light_corporate" else "#6366f1",
            "border": "#e2e8f0" if theme == "light_corporate" else "#333",
        }

        title = data.get("title", "Untitled")
        content = data.get("content", "")
        sections = data.get("sections", [])

        body_html = f'<h1 style="color:{colors["heading"]};font-size:24px;margin-bottom:20px">{title}</h1>'
        if content:
            body_html += f'<p style="color:{colors["text"]};line-height:1.8;font-size:14px">{content}</p>'

        for sec in sections:
            heading = sec.get("heading", sec.get("title", ""))
            sec_content = sec.get("content", "")
            if heading:
                body_html += f'<h2 style="color:{colors["heading"]};font-size:18px;margin-top:24px">{heading}</h2>'
            if sec_content:
                body_html += f'<p style="color:{colors["text"]};line-height:1.8;font-size:14px">{sec_content}</p>'

        return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>body{{margin:40px;font-family:"Segoe UI",system-ui,sans-serif;background:{colors["bg"]}}}</style>
</head><body>{body_html}</body></html>'''

    def _save_html(self, filename: str, html: str, subdir: str) -> Path:
        """保存 HTML 文件"""
        # 清理文件名
        safe_name = "".join(c for c in filename if c.isalnum() or c in "-_.")
        if not safe_name.endswith(".html"):
            safe_name += ".html"

        # 按类型分子目录
        out_dir = self.output_dir / subdir
        out_dir.mkdir(exist_ok=True)

        output_path = out_dir / safe_name
        # 如果存在，加序号
        counter = 1
        orig_path = output_path
        while output_path.exists():
            stem = orig_path.stem
            suffix = orig_path.suffix
            output_path = out_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        output_path.write_text(html, encoding="utf-8")
        logger.info(f"[Render] 已保存: {output_path}")
        return output_path
