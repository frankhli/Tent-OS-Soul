"""Skills REST API —— 用户自主管理 Skills

端点:
  GET    /api/v1/skills           列出所有已安装 skills
  POST   /api/v1/skills/install   安装 skill（上传文件或粘贴内容）
  DELETE /api/v1/skills/{name}    卸载 skill
  POST   /api/v1/skills/{name}/reload  重新加载单个 skill

原则:
  • Skill 是纯 markdown，安装零成本、零 key
  • 安装后热加载，无需重启系统
  • 用户可自由添加/删除，系统预装的保留
"""

import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from tent_os.skills.loader import SkillLoader
from tent_os.skills.router import SkillRouter

router = APIRouter(prefix="/api/v1/skills")

# 全局 SkillRouter 实例（由 API Server 注入）
_skill_router: Optional[SkillRouter] = None


def set_skill_router(sr: SkillRouter):
    """注入 SkillRouter 实例"""
    global _skill_router
    _skill_router = sr


class SkillInstallRequest(BaseModel):
    content: str
    name: Optional[str] = None


class SkillResponse(BaseModel):
    name: str
    description: str
    triggers: List[str]
    tools: List[str]
    installed: bool
    is_builtin: bool


@router.get("")
async def list_skills():
    """列出所有已安装的 skills"""
    if not _skill_router:
        return {"skills": [], "count": 0}
    
    skills = []
    for name, skill in _skill_router.skills.items():
        skills.append({
            "name": skill.name,
            "description": skill.description[:200],
            "triggers": skill.triggers,
            "tools": skill.tools,
            "installed": True,
        })
    
    return {"skills": skills, "count": len(skills)}


@router.post("/install")
async def install_skill(
    content: str = Form(None),
    name: str = Form(None),
    file: UploadFile = File(None),
):
    """安装 skill
    
    两种方式：
    1. 上传文件：multipart/form-data，file 字段
    2. 粘贴内容：content 字段（markdown 文本）
    
    如果提供了 name，使用指定名称；否则从内容中解析。
    """
    if not _skill_router:
        raise HTTPException(status_code=503, detail="SkillRouter 未初始化")
    
    # 获取内容
    if file:
        content = (await file.read()).decode("utf-8")
    elif not content:
        raise HTTPException(status_code=400, detail="请提供 content 或 file")
    
    # 解析 skill
    skill = SkillLoader.parse(content)
    if not skill.name or skill.name == "Unknown":
        raise HTTPException(status_code=400, detail="无法解析 skill 名称，请检查 SKILL.md 格式")
    
    # 使用指定名称或解析出的名称
    skill_name = name or skill.name
    # 清理名称（用于目录名）
    dir_name = skill_name.lower().replace(" ", "_").replace("-", "_")
    
    # 保存到 skills 目录
    skills_dir = _skill_router.skills_dir
    skill_dir = skills_dir / dir_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(content, encoding="utf-8")
    
    # 热加载
    _skill_router.reload()
    
    return {
        "status": "installed",
        "name": skill_name,
        "dir": str(skill_dir),
        "triggers": skill.triggers,
        "tools": skill.tools,
    }


@router.delete("/{skill_name}")
async def uninstall_skill(skill_name: str):
    """卸载 skill"""
    if not _skill_router:
        raise HTTPException(status_code=503, detail="SkillRouter 未初始化")
    
    # 查找 skill 目录（支持名称变体）
    skills_dir = _skill_router.skills_dir
    target_dir = None
    
    # 尝试直接匹配
    for item in skills_dir.iterdir():
        if item.is_dir():
            if item.name == skill_name or item.name.lower() == skill_name.lower():
                target_dir = item
                break
    
    # 尝试清理后的名称
    if not target_dir:
        clean_name = skill_name.lower().replace(" ", "_").replace("-", "_")
        for item in skills_dir.iterdir():
            if item.is_dir() and item.name.lower() == clean_name:
                target_dir = item
                break
    
    if not target_dir or not target_dir.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")
    
    # 删除目录
    shutil.rmtree(target_dir)
    
    # 热加载
    _skill_router.reload()
    
    return {"status": "uninstalled", "name": skill_name}


@router.post("/{skill_name}/reload")
async def reload_skill(skill_name: str):
    """重新加载指定 skill"""
    if not _skill_router:
        raise HTTPException(status_code=503, detail="SkillRouter 未初始化")
    
    _skill_router.reload()
    
    # 检查是否成功加载
    found = None
    for name, skill in _skill_router.skills.items():
        if name.lower() == skill_name.lower():
            found = skill
            break
    
    if not found:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 加载失败或不存在")
    
    return {
        "status": "reloaded",
        "name": found.name,
        "triggers": found.triggers,
        "tools": found.tools,
    }


@router.post("/test-match")
async def test_skill_match(text: str = Form(...)):
    """测试输入会匹配哪些 skills（调试用）"""
    if not _skill_router:
        raise HTTPException(status_code=503, detail="SkillRouter 未初始化")
    
    is_chitchat = _skill_router.is_chitchat(text)
    skills = await _skill_router.route(text)
    
    return {
        "text": text,
        "is_chitchat": is_chitchat,
        "matched_skills": [
            {"name": s.name, "description": s.description[:100]}
            for s in skills
        ],
        "all_skills_count": len(_skill_router.skills),
    }
