#!/usr/bin/env python3
"""批量标准化所有 skills —— 添加 YAML frontmatter + 改进格式

策略：
1. 已有 YAML frontmatter 的：跳过
2. 没有 frontmatter 的：根据 skill 内容自动生成
3. 保留原有 Prompt 内容
4. 添加标准化的 section headers
"""

import re
from pathlib import Path
from typing import Dict

SKILLS_DIR = Path("./skills")

# 常见 skill 的元数据映射（手动维护的核心 skills）
CORE_METADATA: Dict[str, Dict] = {
    "presentation": {
        "description": "Generate professional HTML slide decks from structured content. Use when user asks to create PPT/presentation/slides.",
        "category": "content-generation",
        "triggers": ["PPT", "演示", "pitch", "幻灯片", "路演", "演示文稿", "生成PPT", "写PPT", "做汇报"],
    },
    "document-skills": {
        "description": "Generate professional documents (Word, PDF) from structured content. Use when user asks to write/create documents, reports, or proposals.",
        "category": "content-generation",
        "triggers": ["文档", "报告", "word", "docx", "写文档", "生成文档", "合同", "proposal"],
    },
    "business-writing": {
        "description": "Professional business communication including emails, reports, proposals. Use when user needs business correspondence or formal writing.",
        "category": "writing",
        "triggers": ["邮件", "报告", "proposal", "商务写作", "公文", "商务文书", "写邮件"],
    },
    "data-analysis": {
        "description": "Data analysis and visualization. Use when user asks to analyze data, create charts, or generate Excel/CSV reports.",
        "category": "data",
        "triggers": ["数据", "分析", "图表", "excel", "报表", "统计", "可视化", "dashboard"],
    },
    "code_reviewer": {
        "description": "Code review and quality analysis. Use when user asks to review code, find bugs, or improve code quality.",
        "category": "development",
        "triggers": ["review", "代码审查", "review code", "检查代码", "code review"],
    },
    "contract-drafting": {
        "description": "Legal contract drafting and review. Use when user needs to create, review, or analyze contracts and legal documents.",
        "category": "legal",
        "triggers": ["合同", "contract", "法律", "协议", "法务", "起草合同"],
    },
    "tavily-search": {
        "description": "Web search via Tavily API. Use when user needs real-time information, current events, or facts not in training data.",
        "category": "search",
        "triggers": ["搜索", "查一下", "网上", "最新", "新闻", "搜索网页", "web search"],
    },
    "browser-use": {
        "description": "Browser automation and web interaction. Use when user needs to browse websites, fill forms, or extract web data.",
        "category": "automation",
        "triggers": ["浏览器", "网页", "打开网站", "浏览", "browser", "website"],
    },
    "devops": {
        "description": "DevOps operations including deployment, monitoring, and infrastructure management. Use when user needs CI/CD, Docker, K8s operations.",
        "category": "operations",
        "triggers": ["部署", "docker", "k8s", "kubernetes", "CI/CD", "运维", "devops"],
    },
    "security": {
        "description": "Security auditing and configuration. Use when user needs security checks, vulnerability scans, or compliance verification.",
        "category": "security",
        "triggers": ["安全", "漏洞", "扫描", "合规", "security", "audit", "渗透测试"],
    },
    "sales": {
        "description": "Sales enablement and customer acquisition. Use when user needs sales scripts, CRM operations, or lead generation.",
        "category": "sales",
        "triggers": ["销售", "客户", "CRM", "线索", "跟进", "成交", "sales"],
    },
    "finance": {
        "description": "Financial analysis and reporting. Use when user needs financial calculations, budgeting, or investment analysis.",
        "category": "finance",
        "triggers": ["财务", "预算", "投资", "报表", "finance", "financial", "accounting"],
    },
    "marketing-strategy": {
        "description": "Marketing strategy and campaign planning. Use when user needs marketing plans, content strategy, or campaign design.",
        "category": "marketing",
        "triggers": ["营销", "市场", "推广", "campaign", "marketing", "品牌", "投放"],
    },
    "product-manager": {
        "description": "Product management and roadmap planning. Use when user needs PRD writing, feature prioritization, or user research.",
        "category": "product",
        "triggers": ["产品", "PRD", "需求", " roadmap", "feature", "产品经理", "product"],
    },
    "project-management": {
        "description": "Project management and task tracking. Use when user needs project planning, task assignment, or progress tracking.",
        "category": "project",
        "triggers": ["项目", "任务", "进度", "甘特图", "project", "planning", "milestone"],
    },
    "software-engineer": {
        "description": "Software development and engineering. Use when user needs to write code, debug, or design software architecture.",
        "category": "development",
        "triggers": ["代码", "编程", "开发", "debug", "coding", "software", "工程"],
    },
    "ux-design": {
        "description": "UX/UI design and user research. Use when user needs wireframes, design systems, or usability analysis.",
        "category": "design",
        "triggers": ["设计", "UX", "UI", "原型", "wireframe", "用户研究", "可用性"],
    },
    "copywriting": {
        "description": "Copywriting and content creation. Use when user needs marketing copy, slogans, or social media content.",
        "category": "writing",
        "triggers": ["文案", "slogan", "广告语", "copywriting", "内容", "社交媒体"],
    },
    "crm-system": {
        "description": "CRM operations and customer data management. Use when user needs customer data queries, lead tracking, or sales pipeline.",
        "category": "sales",
        "triggers": ["CRM", "客户", "线索", "跟进", "客户数据", "sales pipeline"],
    },
}


def extract_existing_content(filepath: Path) -> str:
    """提取现有 SKILL.md 的内容（去掉旧的 frontmatter 如果有的话）"""
    content = filepath.read_text(encoding="utf-8")
    
    # 如果已有 YAML frontmatter，跳过
    if content.strip().startswith("---"):
        return None  # 已有 frontmatter，跳过
    
    return content


def build_frontmatter(skill_name: str, metadata: Dict) -> str:
    """构建 YAML frontmatter"""
    triggers = metadata.get("triggers", [])
    triggers_str = ", ".join(f'"{t}"' for t in triggers[:10])
    
    return f"""---
name: {skill_name}
description: |
  {metadata.get("description", "Tent OS skill")}
  Triggers on: {triggers_str}
version: "1.0.0"
author: Tent OS
category: {metadata.get("category", "general")}
---

"""


def standardize_skill(skill_dir: Path):
    """标准化单个 skill"""
    skill_name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    
    if not skill_md.exists():
        print(f"  ⚠️ {skill_name}: 无 SKILL.md，跳过")
        return
    
    content = extract_existing_content(skill_md)
    if content is None:
        print(f"  ⏭️ {skill_name}: 已有 frontmatter，跳过")
        return
    
    metadata = CORE_METADATA.get(skill_name, {
        "description": f"Tent OS skill: {skill_name}",
        "category": "general",
        "triggers": [],
    })
    
    frontmatter = build_frontmatter(skill_name, metadata)
    
    # 保留原有内容，添加 frontmatter
    new_content = frontmatter + content
    
    skill_md.write_text(new_content, encoding="utf-8")
    print(f"  ✅ {skill_name}: 已标准化")


def main():
    print("=" * 50)
    print("批量标准化 Skills")
    print("=" * 50)
    
    skills = sorted([d for d in SKILLS_DIR.iterdir() if d.is_dir()])
    
    processed = 0
    skipped = 0
    
    for skill_dir in skills:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        
        content = skill_md.read_text(encoding="utf-8")
        if content.strip().startswith("---"):
            skipped += 1
            print(f"  ⏭️ {skill_dir.name}: 已有 frontmatter")
            continue
        
        standardize_skill(skill_dir)
        processed += 1
    
    print()
    print(f"处理完成: {processed} 个 skills 标准化, {skipped} 个已跳过")


if __name__ == "__main__":
    main()
