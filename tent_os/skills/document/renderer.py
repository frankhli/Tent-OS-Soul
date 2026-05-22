"""Document HTML 渲染引擎 —— 复用 PPT 主题系统

生成可打印为 PDF 的干净 HTML 文档。
"""

import html
import re
from pathlib import Path
from typing import List

from tent_os.skills.document.schema import Document, DocumentSection, Contract, ContractClause


class DocumentRenderer:
    """文档 HTML 渲染器"""
    
    # 复用 PPT 的主题色板
    from tent_os.skills.presentation.renderer import PresentationRenderer
    THEMES = PresentationRenderer.THEMES
    
    def __init__(self, theme: str = "light_corporate"):
        self.theme = theme
        self.colors = self.THEMES.get(theme, self.THEMES["light_corporate"])
    
    def render_document(self, doc: Document) -> str:
        """渲染通用文档为 HTML"""
        c = self.colors
        
        # 生成目录
        toc_html = ""
        if doc.config.get("show_toc", True):
            toc_items = ""
            for sec in doc.sections:
                if sec.title:
                    toc_items += f'<li><a href="#sec-{self._slug(sec.title)}">{self._escape(sec.title)}</a></li>'
            if toc_items:
                toc_html = f'''
                <nav class="toc">
                    <h2>目录</h2>
                    <ul>{toc_items}</ul>
                </nav>
                '''
        
        # 生成章节内容
        sections_html = ""
        for sec in doc.sections:
            sections_html += self._render_doc_section(sec)
        
        return self._build_html(doc.title, doc.author, doc.date, toc_html, sections_html, doc.config)
    
    def render_contract(self, contract: Contract) -> str:
        """渲染合同为 HTML"""
        c = self.colors
        
        # 合同头部
        header_html = f'''
        <div class="contract-header">
            <h1>{self._escape(contract.title)}</h1>
            {f'<div class="contract-no">合同编号：{self._escape(contract.contract_no)}</div>' if contract.contract_no else ''}
            {f'<div class="contract-date">签订日期：{self._escape(contract.date)}</div>' if contract.date else ''}
        </div>
        '''
        
        # 签署方
        parties_html = '<div class="contract-parties">'
        for party in contract.parties:
            parties_html += f'''
            <div class="party">
                <div class="party-role">{self._escape(party.role)}</div>
                <div class="party-name">{self._escape(party.name)}</div>
                {f'<div class="party-detail">地址：{self._escape(party.address)}</div>' if party.address else ''}
                {f'<div class="party-detail">联系方式：{self._escape(party.contact)}</div>' if party.contact else ''}
            </div>
            '''
        parties_html += '</div>'
        
        # 条款
        clauses_html = '<div class="clauses">'
        for clause in contract.clauses:
            clauses_html += self._render_clause(clause)
        clauses_html += '</div>'
        
        # 签字区
        signature_html = ""
        if contract.config.get("show_seal_placeholder", True):
            sig_boxes = ""
            for party in contract.parties:
                sig_boxes += f'''
                <div class="sig-box">
                    <div class="sig-role">{self._escape(party.role)}</div>
                    <div class="sig-name">{self._escape(party.name)}</div>
                    <div class="sig-line">签字/盖章：</div>
                    <div class="sig-date">日期：&nbsp;&nbsp;&nbsp;&nbsp;年&nbsp;&nbsp;&nbsp;&nbsp;月&nbsp;&nbsp;&nbsp;&nbsp;日</div>
                </div>
                '''
            signature_html = f'''
            <div class="signature-section">
                <h2>签字盖章</h2>
                <div class="sig-grid">{sig_boxes}</div>
                {f'<div class="sig-place">签订地点：{self._escape(contract.signature_place)}</div>' if contract.signature_place else ''}
            </div>
            '''
        
        body = header_html + parties_html + clauses_html + signature_html
        return self._build_html(contract.title, "", contract.date, "", body, contract.config)
    
    def _render_doc_section(self, sec: DocumentSection) -> str:
        """渲染文档章节（支持 Markdown 子集）"""
        tag = f"h{min(max(sec.level, 1), 6)}"
        title_html = f'<{tag} id="sec-{self._slug(sec.title)}">{self._escape(sec.title)}</{tag}>' if sec.title else ''
        content_html = self._markdown_to_html(sec.content)
        return f'<section class="doc-section">{title_html}{content_html}</section>'
    
    def _render_clause(self, clause: ContractClause) -> str:
        """渲染合同条款"""
        return f'''
        <div class="clause">
            <div class="clause-number">{self._escape(clause.number)}</div>
            <div class="clause-title">{self._escape(clause.title)}</div>
            <div class="clause-content">{self._markdown_to_html(clause.content)}</div>
        </div>
        '''
    
    def _markdown_to_html(self, text: str) -> str:
        """简单的 Markdown → HTML 转换"""
        if not text:
            return ""
        
        # 代码块
        text = re.sub(r'```(\w+)?\n(.*?)```', r'<pre><code>\2</code></pre>', text, flags=re.DOTALL)
        
        # 粗体
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        # 斜体
        text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
        
        # 有序列表
        def _ol_replace(match):
            items = re.findall(r'^\d+\.\s+(.*)$', match.group(1), re.MULTILINE)
            li_html = ''.join(f'<li>{self._escape(item)}</li>' for item in items)
            return f'<ol>{li_html}</ol>'
        text = re.sub(r'(^\d+\.\s+.*$(?:\n^\d+\.\s+.*$)*)', _ol_replace, text, flags=re.MULTILINE)
        
        # 无序列表
        def _ul_replace(match):
            items = re.findall(r'^[-*]\s+(.*)$', match.group(1), re.MULTILINE)
            li_html = ''.join(f'<li>{self._escape(item)}</li>' for item in items)
            return f'<ul>{li_html}</ul>'
        text = re.sub(r'(^[-*]\s+.*$(?:\n^[-*]\s+.*$)*)', _ul_replace, text, flags=re.MULTILINE)
        
        # 段落
        paragraphs = text.split('\n\n')
        result = []
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            if p.startswith('<pre>') or p.startswith('<ol>') or p.startswith('<ul>'):
                result.append(p)
            else:
                result.append(f'<p>{p}</p>')
        return '\n'.join(result)
    
    def _build_html(self, title: str, author: str, date: str, toc_html: str, body_html: str, config: dict) -> str:
        """构建完整 HTML"""
        c = self.colors
        show_page_numbers = config.get("page_numbers", True)
        page_num_css = "" if show_page_numbers else ".page-number { display: none; }"
        
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self._escape(title)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: {c["bg_primary"]};
            color: {c["text_primary"]};
            line-height: 1.8;
            max-width: 900px;
            margin: 0 auto;
            padding: 60px 40px;
        }}
        
        /* 文档头部 */
        .doc-header {{
            text-align: center;
            margin-bottom: 48px;
            padding-bottom: 24px;
            border-bottom: 2px solid {c["accent"]};
        }}
        .doc-header h1 {{ font-size: 2rem; font-weight: 700; margin-bottom: 8px; }}
        .doc-header .meta {{ color: {c["text_secondary"]}; font-size: 0.9rem; }}
        
        /* 目录 */
        .toc {{
            background: {c["card_bg"]};
            border: 1px solid {c["border"]};
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 40px;
        }}
        .toc h2 {{ font-size: 1.1rem; margin-bottom: 16px; color: {c["accent"]}; }}
        .toc ul {{ list-style: none; }}
        .toc li {{ padding: 6px 0; }}
        .toc a {{ color: {c["text_primary"]}; text-decoration: none; }}
        .toc a:hover {{ color: {c["accent"]}; }}
        
        /* 章节 */
        .doc-section {{ margin-bottom: 40px; }}
        .doc-section h1, .doc-section h2, .doc-section h3 {{
            margin: 32px 0 16px;
            color: {c["text_primary"]};
        }}
        .doc-section h1 {{ font-size: 1.6rem; border-bottom: 1px solid {c["border"]}; padding-bottom: 8px; }}
        .doc-section h2 {{ font-size: 1.3rem; color: {c["accent"]}; }}
        .doc-section h3 {{ font-size: 1.1rem; }}
        .doc-section p {{ margin-bottom: 16px; text-align: justify; }}
        .doc-section ul, .doc-section ol {{ margin: 16px 0 16px 24px; }}
        .doc-section li {{ margin-bottom: 8px; }}
        .doc-section pre {{
            background: {c["bg_secondary"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
            padding: 16px;
            overflow-x: auto;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.9rem;
            margin: 16px 0;
        }}
        
        /* 合同专用 */
        .contract-header {{ text-align: center; margin-bottom: 40px; }}
        .contract-header h1 {{ font-size: 1.8rem; margin-bottom: 12px; }}
        .contract-no, .contract-date {{ color: {c["text_secondary"]}; font-size: 0.9rem; margin: 4px 0; }}
        
        .contract-parties {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            margin-bottom: 40px;
            padding: 24px;
            background: {c["card_bg"]};
            border-radius: 12px;
        }}
        .party-role {{ font-weight: 700; color: {c["accent"]}; margin-bottom: 8px; }}
        .party-name {{ font-size: 1.1rem; margin-bottom: 8px; }}
        .party-detail {{ font-size: 0.9rem; color: {c["text_secondary"]}; }}
        
        .clauses {{ margin-bottom: 40px; }}
        .clause {{
            margin-bottom: 24px;
            padding-left: 16px;
            border-left: 3px solid {c["accent"]};
        }}
        .clause-number {{
            font-weight: 700;
            color: {c["accent"]};
            margin-bottom: 4px;
        }}
        .clause-title {{ font-weight: 600; margin-bottom: 8px; }}
        .clause-content {{ color: {c["text_secondary"]}; }}
        
        .signature-section {{ margin-top: 60px; page-break-before: always; }}
        .sig-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 40px;
            margin-top: 32px;
        }}
        .sig-box {{
            border: 1px solid {c["border"]};
            border-radius: 8px;
            padding: 24px;
        }}
        .sig-role {{ font-weight: 700; color: {c["accent"]}; margin-bottom: 16px; }}
        .sig-line {{ margin: 24px 0; padding-bottom: 8px; border-bottom: 1px solid {c["border"]}; }}
        .sig-date {{ margin-top: 16px; }}
        .sig-place {{ margin-top: 24px; text-align: center; color: {c["text_secondary"]}; }}
        
        .seal-placeholder {{
            width: 120px;
            height: 120px;
            border: 2px dashed {c["border"]};
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: {c["text_secondary"]};
            font-size: 0.8rem;
            margin-top: 16px;
        }}
        
        /* 页码 */
        .page-number {{
            position: fixed;
            bottom: 20px;
            right: 40px;
            font-size: 0.8rem;
            color: {c["text_secondary"]};
        }}
        
        {page_num_css}
        
        /* 打印 */
        @media print {{
            body {{ padding: 0; max-width: 100%; }}
            .signature-section {{ page-break-before: always; }}
            .page-number {{ position: static; text-align: center; margin-top: 40px; }}
        }}
    </style>
</head>
<body>
    <div class="doc-header">
        <h1>{self._escape(title)}</h1>
        <div class="meta">
            {f'<span>{self._escape(author)}</span>' if author else ''}
            {f'<span> · {self._escape(date)}</span>' if date else ''}
        </div>
    </div>
    
    {toc_html}
    
    <main>
        {body_html}
    </main>
    
    <div class="page-number"></div>
</body>
</html>'''
    
    @staticmethod
    def _escape(text: str) -> str:
        return html.escape(str(text))
    
    @staticmethod
    def _slug(text: str) -> str:
        """生成 URL 友好的锚点 ID"""
        return re.sub(r'[^\w\-]', '-', text)[:40]


def render_document(doc: Document, output_path: str) -> str:
    """便捷函数：渲染文档并保存"""
    renderer = DocumentRenderer(theme=doc.theme)
    html_content = renderer.render_document(doc)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_content, encoding="utf-8")
    return str(output)


def render_contract(contract: Contract, output_path: str) -> str:
    """便捷函数：渲染合同并保存"""
    renderer = DocumentRenderer(theme=contract.theme)
    html_content = renderer.render_contract(contract)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_content, encoding="utf-8")
    return str(output)
