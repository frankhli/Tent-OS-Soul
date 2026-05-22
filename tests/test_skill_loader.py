"""Tests for SkillLoader —— OpenClaw format compatibility"""

import pytest

from tent_os.skills.loader import SkillLoader, Skill


@pytest.mark.unit
class TestSkillLoaderNative:
    def test_parse_native_format(self):
        content = """# Test Skill

## Description
A test skill for unit testing.

## Triggers
- test trigger
- unit test

## Tools
- shell: execute commands
- file_read: read files

## Prompt
You are a test assistant.
"""
        skill = SkillLoader.parse(content, "/tmp/test")
        assert skill.name == "Test Skill"
        assert "unit testing" in skill.description
        assert "test trigger" in skill.triggers
        assert "shell" in skill.tools
        assert "You are a test assistant" in skill.prompt

    def test_parse_minimal(self):
        content = "# Minimal\n"
        skill = SkillLoader.parse(content)
        assert skill.name == "Minimal"
        assert skill.description == ""
        assert skill.triggers == []


@pytest.mark.unit
class TestSkillLoaderOpenClaw:
    def test_parse_openclaw_format(self):
        content = """---
name: hospitality
description: Comprehensive hospitality expertise
---

# Hospitality & Hotel Management

## Description

Comprehensive hospitality expertise covering hotel operations.

## When to Use
- Hotel operations: front office, housekeeping
- Revenue management: pricing, distribution
- Guest experience and service design

## Key Capabilities

### Revenue Management
- Dynamic pricing strategies

### Operations Excellence
- Standard Operating Procedures
"""
        skill = SkillLoader.parse(content, "/tmp/hospitality")
        assert skill.name == "hospitality"
        assert "hospitality expertise" in skill.description
        assert len(skill.triggers) == 3
        assert "Hotel operations: front office, housekeeping" in skill.triggers
        assert "核心能力" in skill.prompt
        assert "Revenue Management" in skill.prompt
        assert "Operations Excellence" in skill.prompt
        assert skill.tools == []

    def test_parse_openclaw_fallback_name(self):
        """If frontmatter has no name, fall back to # title"""
        content = """---
description: Some description
---

# My Skill Title

## When to Use
- trigger one
"""
        skill = SkillLoader.parse(content)
        assert skill.name == "My Skill Title"
        assert skill.triggers == ["trigger one"]

    def test_frontmatter_description_fallback(self):
        """If no ## Description, use frontmatter description"""
        content = """---
name: test
description: From frontmatter
---

# Test

## When to Use
- trigger
"""
        skill = SkillLoader.parse(content)
        assert "From frontmatter" in skill.description

    def test_native_takes_priority_over_openclaw(self):
        """Native Triggers/Prompt should override OpenClaw equivalents"""
        content = """---
name: mixed
description: Frontmatter desc
---

# Mixed

## Description
Native desc

## Triggers
- native trigger

## When to Use
- openclaw trigger

## Prompt
Native prompt

## Key Capabilities
OpenClaw capabilities
"""
        skill = SkillLoader.parse(content)
        assert skill.description == "Native desc"
        assert skill.triggers == ["native trigger"]
        assert skill.prompt == "Native prompt"


@pytest.mark.unit
class TestSkillMatches:
    def test_matches_trigger(self):
        skill = Skill(name="test", description="test", triggers=["hotel", "booking"])
        assert skill.matches("I need a hotel room") > 0
        assert skill.matches("random text") == 0.0

    def test_matches_no_triggers(self):
        skill = Skill(name="test", description="test", triggers=[])
        assert skill.matches("anything") == 0.0
