"""Tests for the prompt file loader."""

import pytest

from prompts import load as load_prompt


class TestPromptLoader:
    def test_load_existing_prompt(self):
        """Loading an existing .prompt file returns non-empty string."""
        content = load_prompt("story_character")
        assert isinstance(content, str)
        assert len(content) > 100
        assert "{character_cognition}" in content

    def test_load_another_prompt(self):
        content = load_prompt("suggest_meta")
        assert isinstance(content, str)
        assert len(content) > 50

    def test_load_world_draft_topic(self):
        """world v2 通用起草模板：占位符与 ai_router .format 键对齐。"""
        content = load_prompt("world_draft_topic")
        assert isinstance(content, str)
        for key in ("{topic}", "{world}", "{shape_line}", "{format_line}", "{topic_line}"):
            assert key in content

    def test_load_story_stage(self):
        content = load_prompt("story_stage")
        assert isinstance(content, str)
        assert len(content) > 50

    # ------------------------------------------------------------------
    # Security: path traversal protection
    # ------------------------------------------------------------------

    def test_load_rejects_dot_dot(self):
        """Path traversal via '..' is rejected."""
        with pytest.raises(ValueError, match="Invalid prompt name"):
            load_prompt("../../etc/passwd")

    def test_load_rejects_absolute_path(self):
        """Absolute path is rejected."""
        with pytest.raises(ValueError, match="Invalid prompt name"):
            load_prompt("/etc/passwd")

    def test_load_rejects_relative_path_with_slash(self):
        """Name containing '/' is rejected."""
        with pytest.raises(ValueError, match="Invalid prompt name"):
            load_prompt("subdir/file")

    def test_load_rejects_empty_string(self):
        """Empty name is rejected (doesn't match regex)."""
        with pytest.raises(ValueError, match="Invalid prompt name"):
            load_prompt("")

    def test_accepts_hyphenated_name_raises_filenotfound(self):
        """Hyphenated names match the allowed pattern, so ValueError is NOT raised."""
        with pytest.raises(FileNotFoundError):
            load_prompt("anti-ai")
