---
name: code_reviewer
description: |
  Code review and quality analysis. Use when user asks to review code, find bugs, or improve code quality.
  Triggers on: "review", "代码审查", "review code", "检查代码", "code review"
version: "1.0.0"
author: Tent OS
category: development
---

# Code_Reviewer

## Description
审查代码质量、发现潜在问题、提供改进建议。

## Triggers
- 审查
- review
- 代码
- code
- 优化
- refactor
- bug
- 漏洞
- 质量

## Tools
- shell
- file_read


## Prompt
当用户要求审查代码时：
1. 检查常见陷阱（空指针、资源泄漏、SQL 注入等）
2. 关注可读性和命名规范
3. 指出性能瓶颈
4. 给出具体修改建议（而非笼统评价）
5. 区分 "必须修复" 和 "建议优化"
