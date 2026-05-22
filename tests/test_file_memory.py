"""Tests for FileMemory —— 文件记忆召回系统"""

import os
import tempfile
from unittest.mock import AsyncMock

import pytest

from tent_os.memory.file_memory import FileMemory, FileMemoryStore


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def store(tmp_dir):
    return FileMemoryStore(base_dir=tmp_dir)


@pytest.mark.unit
class TestFileMemory:
    def test_dataclass_fields(self):
        import pathlib
        fm = FileMemory(
            path=pathlib.Path("/tmp/test.md"),
            frontmatter={"title": "Test Doc", "tags": ["tag1"]},
            content="A test",
            relevance_score=0.9,
        )
        assert fm.path.name == "test.md"
        assert fm.frontmatter["title"] == "Test Doc"


@pytest.mark.unit
class TestFileMemoryStore:
    def test_create_and_read(self, store):
        path = store.create(
            memory_type="doc",
            memory_id="m1",
            title="Hello",
            content="World content",
            tags=["greeting"],
        )
        assert path is not None

        read_fm = store.read("m1")
        assert read_fm is not None
        assert read_fm.frontmatter.get("title") == "Hello"

    def test_read_not_found(self, store):
        assert store.read("nonexistent") is None

    def test_update(self, store):
        store.create("doc", "m2", "Old", "Old content")
        # Note: memory_type=None searches all subdirs; "doc" would look in wrong dir
        success = store.update("m2", content="New content")
        assert success is True

    def test_update_not_found(self, store):
        assert store.update("nope", content="X") is False

    def test_delete(self, store):
        store.create("doc", "m3", "ToDelete", "content")
        assert store.delete("m3") is True
        assert store.read("m3") is None

    def test_list_all(self, store):
        store.create("doc", "a1", "A", "content")
        store.create("doc", "b1", "B", "content")
        items = store.list_all()
        assert len(items) == 2

    def test_format_for_injection(self, store):
        store.create("doc", "spec1", "Spec", "Important spec content")
        read_fm = store.read("spec1")
        text = store.format_for_injection([read_fm])
        assert "Spec" in text
        assert "Important spec content" in text

    @pytest.mark.asyncio
    async def test_recall_basic(self, store):
        store.create("doc", "api1", "Booking API", "API for hotel bookings")
        store.create("doc", "guide1", "User Guide", "How to use the system")

        results = await store.recall("hotel booking API")
        assert len(results) > 0
        assert any("Booking API" in r.frontmatter.get("title", "") for r in results)

    @pytest.mark.asyncio
    async def test_recall_no_match_returns_all(self, store):
        store.create("doc", "x1", "X", "xyz")
        results = await store.recall("something completely unrelated")
        # Implementation falls back to all files when no heuristic match
        assert len(results) >= 1

    def test_scan_files(self, store, tmp_dir):
        subdir = os.path.join(tmp_dir, "experiences")
        os.makedirs(subdir, exist_ok=True)
        with open(os.path.join(subdir, "test.md"), "w") as f:
            f.write("---\ntype: doc\nid: scan1\ntitle: Scanned\n---\n\n# Scanned\n\nContent here\n")

        items = store.list_all()
        assert len(items) >= 1
