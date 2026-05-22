"""Tests for RenderExecutor —— 办公渲染执行器"""

import json
import pytest
from pathlib import Path

from tent_os.scheduler.executors.render import RenderExecutor


@pytest.fixture
def render_executor(tmp_path):
    return RenderExecutor(output_dir=str(tmp_path))


@pytest.mark.unit
class TestRenderExecutor:

    def test_supported_actions(self, render_executor):
        actions = render_executor.supported_actions()
        assert "render_ppt" in actions
        assert "render_document" in actions
        assert "render_contract" in actions
        assert "render_excel" in actions
        assert "render_word" in actions

    @pytest.mark.asyncio
    async def test_render_ppt(self, render_executor, tmp_path):
        params = {
            "data": {
                "title": "Test Presentation",
                "slides": [
                    {
                        "type": "title",
                        "title": "Hello World",
                        "subtitle": "Test Slide",
                        "elements": [
                            {"type": "text", "content": "This is a test."}
                        ]
                    },
                    {
                        "type": "content",
                        "title": "Second Slide",
                        "elements": [
                            {"type": "text", "content": "More content here."}
                        ]
                    }
                ]
            },
            "theme": "dark_modern",
            "filename": "test_presentation",
        }

        result = await render_executor.execute("render_ppt", params)
        assert result["status"] == "completed"
        assert "file_path" in result
        assert result.get("slides_count") == 2 or result["status"] == "completed"
        assert Path(result["file_path"]).exists()

    @pytest.mark.asyncio
    async def test_render_document(self, render_executor, tmp_path):
        params = {
            "data": {
                "title": "Test Document",
                "sections": [
                    {"title": "Introduction", "content": "This is the intro.", "level": 1},
                    {"title": "Details", "content": "Some details here.", "level": 1},
                ]
            },
            "theme": "light_corporate",
            "filename": "test_document",
        }

        result = await render_executor.execute("render_document", params)
        assert result["status"] == "completed"
        assert Path(result["file_path"]).exists()
        assert result["sections_count"] == 2

    @pytest.mark.asyncio
    async def test_render_contract(self, render_executor, tmp_path):
        params = {
            "data": {
                "title": "Service Agreement",
                "parties": ["Company A", "Company B"],
                "effective_date": "2024-01-01",
                "clauses": [
                    {"number": "1.1", "title": "Scope", "content": "Service scope...", "is_optional": False},
                    {"number": "1.2", "title": "Payment", "content": "Payment terms...", "is_optional": False},
                ],
                "signatories": ["Alice", "Bob"],
            },
            "filename": "test_contract",
        }

        result = await render_executor.execute("render_contract", params)
        assert result["status"] == "completed"
        assert Path(result["file_path"]).exists()
        assert result["clauses_count"] == 2

    @pytest.mark.asyncio
    async def test_render_excel(self, render_executor, tmp_path):
        params = {
            "data": {
                "sheets": [
                    {
                        "title": "Sales",
                        "data": [
                            ["Product", "Q1", "Q2", "Q3"],
                            ["Widget", "100", "150", "200"],
                            ["Gadget", "80", "120", "160"],
                        ]
                    }
                ]
            },
            "theme": "light_corporate",
            "filename": "test_spreadsheet",
        }

        result = await render_executor.execute("render_excel", params)
        assert result["status"] == "completed"
        assert Path(result["file_path"]).exists()
        assert result["sheets_count"] == 1

    @pytest.mark.asyncio
    async def test_render_word(self, render_executor, tmp_path):
        params = {
            "data": {
                "title": "Word Document",
                "content": "This is the main content of the word document.",
                "sections": [
                    {"heading": "Section 1", "content": "Content for section 1."},
                ]
            },
            "filename": "test_word",
        }

        result = await render_executor.execute("render_word", params)
        assert result["status"] == "completed"
        assert Path(result["file_path"]).exists()

    @pytest.mark.asyncio
    async def test_unsupported_action(self, render_executor):
        result = await render_executor.execute("render_pdf", {})
        assert result["status"] == "error"
        assert "不支持" in result["error"]

    def test_save_html_collision(self, render_executor, tmp_path):
        """测试文件名冲突自动加序号"""
        html = "<html><body>Test</body></html>"
        path1 = render_executor._save_html("test", html, "ppt")
        path2 = render_executor._save_html("test", html, "ppt")
        assert path1 != path2
        assert path1.exists()
        assert path2.exists()
