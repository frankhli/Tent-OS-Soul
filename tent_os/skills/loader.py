"""Skill Loader —— 加载和解析 SKILL.md

SKILL.md 格式：
```markdown
# Skill Name

## Description
简要描述这个技能做什么

## Triggers
- 关键词1
- 关键词2

## Tools
- tool_name: 描述

## Prompt
添加到 system prompt 的额外指令
```
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional


@dataclass
class Skill:
    """单个 Skill 的定义"""
    name: str
    description: str
    triggers: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)  # tool name 列表，引用 tool registry
    prompt: str = ""
    source_dir: str = ""
    
    def matches(self, text: str) -> float:
        """计算文本与 skill 的匹配度 (0.0 - 1.0)
        
        只要有任意 trigger 匹配就返回基础分 0.5，
        额外匹配每个加 0.05，最高 1.0。
        """
        if not self.triggers:
            return 0.0
        
        text_lower = text.lower()
        matched = 0
        for trigger in self.triggers:
            if trigger.lower() in text_lower:
                matched += 1
        
        if matched == 0:
            return 0.0
        
        # 基础分 0.5 + 额外匹配加分，最高 1.0
        return min(0.5 + (matched - 1) * 0.05, 1.0)


class SkillLoader:
    """SKILL.md 加载器"""
    
    @classmethod
    def load_from_directory(cls, skill_dir: Path) -> Optional[Skill]:
        """从目录加载 Skill"""
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return None
        
        try:
            content = skill_md.read_text(encoding="utf-8")
            return cls.parse(content, str(skill_dir))
        except Exception as e:
            print(f"加载 Skill 失败 {skill_dir}: {e}")
            return None
    
    @classmethod
    def parse(cls, content: str, source_dir: str = "") -> Skill:
        """解析 SKILL.md 内容

        兼容两种格式：
        1. Tent OS 原生格式: ## Description / ## Triggers / ## Tools / ## Prompt
        2. OpenClaw 格式: YAML frontmatter + ## Description / ## When to Use / ## Key Capabilities
        """
        # 解析 YAML frontmatter（OpenClaw 风格）
        frontmatter = cls._parse_frontmatter(content)

        # 提取名称（优先 frontmatter，然后是第一行 # 标题）
        name = frontmatter.get("name", "")
        if not name:
            name_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if name_match:
                name = name_match.group(1).strip()
        if not name:
            name = "Unknown"

        # 提取描述（优先原生格式，然后 frontmatter，然后 OpenClaw Description）
        description = cls._extract_section(content, "Description", "描述")
        if not description:
            description = frontmatter.get("description", "")

        # 提取 triggers（优先原生 Triggers，然后 OpenClaw When to Use）
        triggers = cls._extract_list(content, "Triggers", "触发")
        if not triggers:
            triggers = cls._extract_list(content, "When to Use")

        # 提取 tools（原生格式）
        tools = cls._extract_tools(content)

        # 提取 prompt（优先原生 Prompt，然后 OpenClaw Key Capabilities）
        prompt = cls._extract_section(content, "Prompt", "提示")
        if not prompt:
            capabilities = cls._extract_section(content, "Key Capabilities")
            if capabilities:
                prompt = f"# 核心能力\n\n{capabilities}"

        return Skill(
            name=name,
            description=description,
            triggers=triggers,
            tools=tools,
            prompt=prompt,
            source_dir=source_dir,
        )

    @classmethod
    def _parse_frontmatter(cls, content: str) -> Dict[str, str]:
        """解析 YAML frontmatter（OpenClaw 风格）

        格式:
        ---
        name: skill_name
        description: skill description
        ---
        """
        if not content.startswith("---"):
            return {}
        end = content.find("---", 3)
        if end == -1:
            return {}
        fm_text = content[3:end].strip()
        result = {}
        for line in fm_text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                result[key.strip()] = val.strip()
        return result
    
    @classmethod
    def _extract_section(cls, content: str, *section_names: str) -> str:
        """提取 markdown section 内容

        注意：前瞻使用 (?=\\n##\\s|\\Z) 而不是 (?=\\n##|\\Z)，
        避免将 \\n### 误判为 \\n## 的匹配。
        """
        for section_name in section_names:
            # 使用普通字符串拼接，避免 raw string 中 \s 的 SyntaxWarning
            esc = re.escape(section_name)
            pattern = r'##\s+' + esc + r'\s*\n(.*?)(?=\n##\s|\Z)'
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""
    
    @classmethod
    def _extract_list(cls, content: str, *section_names: str) -> List[str]:
        """提取列表形式的 section"""
        section = cls._extract_section(content, *section_names)
        items = []
        for line in section.split('\n'):
            line = line.strip()
            if line.startswith('- ') or line.startswith('* '):
                items.append(line[2:].strip())
            elif line.startswith('1. ') or line.startswith('2. '):
                items.append(line[3:].strip())
        return items
    
    @classmethod
    def _extract_tools(cls, content: str) -> List[str]:
        """提取 Tools section —— 返回 tool name 列表
        
        格式:
        - tool_name          # 直接是 tool name
        - tool_name: 描述    # 冒号前是 tool name
        """
        section = cls._extract_section(content, "Tools", "工具")
        tools = []
        for line in section.split('\n'):
            line = line.strip()
            if line.startswith('- ') or line.startswith('* '):
                tool_text = line[2:].strip()
                # 格式: tool_name: description 或只写 tool_name
                if ':' in tool_text:
                    name = tool_text.split(':', 1)[0].strip()
                    tools.append(name)
                else:
                    tools.append(tool_text)
        return tools
