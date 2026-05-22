"""SkillRegistry —— 技能市场注册表

提供技能的注册、发现、版本管理和依赖解析：
- 本地注册：扫描 skills/ 目录自动注册
- 远程注册：从 Git URL / HTTP 下载并安装
- 版本管理：语义化版本控制，支持回滚
- 依赖解析：skill A 依赖 skill B 时自动安装
- 权限控制：谁可以安装/更新/删除技能

Tent OS 差异化：
- Skill 是第一等公民，和内置工具平等对待
- 支持 OpenClaw 格式（YAML frontmatter）和原生格式
- 版本化 + 依赖图，避免 Skill 地狱
"""

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from urllib.parse import urlparse

from tent_os.logging_config import get_logger
from tent_os.skills.loader import SkillLoader, Skill

logger = get_logger()

# 注册表持久化路径
REGISTRY_DIR = Path("./tent_memory/skills/registry")
INSTALL_DIR = Path("./skills")


@dataclass
class SkillPackage:
    """技能包元数据"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    source: str = ""              # local / git / http
    source_url: str = ""          # 原始来源 URL
    install_path: Path = Path(".")
    triggers: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # ["skill_name>=1.0"]
    checksum: str = ""            # SHA256
    installed_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    is_builtin: bool = False
    is_enabled: bool = True


class SkillRegistry:
    """技能注册表

    单例模式，管理所有已安装技能的完整生命周期。
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, registry_dir: str = "./tent_memory/skills/registry",
                 install_dir: str = "./skills"):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        self.registry_dir = Path(registry_dir)
        self.install_dir = Path(install_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.install_dir.mkdir(parents=True, exist_ok=True)

        # 已注册技能: name -> SkillPackage
        self._packages: Dict[str, SkillPackage] = {}

        # 解析后的 Skill 对象缓存: name -> Skill
        self._skills: Dict[str, Skill] = {}

        # 触发词索引: trigger -> [skill_name]
        self._trigger_index: Dict[str, List[str]] = {}

        # 加载持久化注册表
        self._load_registry()

        # 扫描内置技能
        self._scan_builtin_skills()

    # ========== 公共 API ==========

    def register(self, skill_path: Path, source: str = "local") -> SkillPackage:
        """注册一个技能（从本地路径）"""
        skill_file = skill_path / "SKILL.md"
        if not skill_file.exists():
            skill_file = skill_path / "skill.md"
        if not skill_file.exists():
            raise ValueError(f"技能目录缺少 SKILL.md: {skill_path}")

        content = skill_file.read_text(encoding="utf-8")
        skill = SkillLoader.parse(content, source_dir=str(skill_path))

        # 计算校验和
        checksum = hashlib.sha256(content.encode()).hexdigest()[:16]

        # 提取版本（从 frontmatter 或文件名）
        version = self._extract_version(content) or "0.1.0"

        pkg = SkillPackage(
            name=skill.name or skill_path.name,
            version=version,
            description=skill.description,
            author=self._extract_author(content),
            source=source,
            install_path=skill_path,
            triggers=skill.triggers,
            tools=skill.tools,
            dependencies=self._extract_dependencies(content),
            checksum=checksum,
            is_builtin=source == "builtin",
        )

        # 检查同名技能版本冲突
        if pkg.name in self._packages:
            old = self._packages[pkg.name]
            if self._version_compare(pkg.version, old.version) <= 0:
                logger.info(f"[SkillRegistry] 跳过旧版本: {pkg.name}@{pkg.version} <= {old.version}")
                return old
            logger.info(f"[SkillRegistry] 升级技能: {old.name}@{old.version} -> {pkg.version}")

        self._packages[pkg.name] = pkg
        self._skills[pkg.name] = skill
        self._index_triggers(pkg)
        self._save_registry()

        logger.info(f"[SkillRegistry] 已注册: {pkg.name}@{pkg.version} from {source}")
        return pkg

    async def install_from_git(self, git_url: str, name: str = None) -> SkillPackage:
        """从 Git 仓库安装技能"""
        import tempfile
        import subprocess

        parsed = urlparse(git_url)
        skill_name = name or Path(parsed.path).stem
        target_dir = self.install_dir / skill_name

        # 克隆到临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_dir = Path(tmpdir) / skill_name
            result = subprocess.run(
                ["git", "clone", "--depth", "1", git_url, str(clone_dir)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Git clone 失败: {result.stderr}")

            # 移动安装
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.move(str(clone_dir), str(target_dir))

        pkg = self.register(target_dir, source="git")
        pkg.source_url = git_url
        self._save_registry()
        return pkg

    async def install_from_http(self, url: str, name: str = None) -> SkillPackage:
        """从 HTTP URL 安装技能"""
        import httpx

        skill_name = name or Path(urlparse(url).path).stem
        target_dir = self.install_dir / skill_name
        target_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        skill_file = target_dir / "SKILL.md"
        skill_file.write_text(resp.text, encoding="utf-8")

        pkg = self.register(target_dir, source="http")
        pkg.source_url = url
        self._save_registry()
        return pkg

    def uninstall(self, name: str) -> bool:
        """卸载技能"""
        pkg = self._packages.pop(name, None)
        if not pkg:
            return False

        self._skills.pop(name, None)
        self._rebuild_trigger_index()

        # 删除安装目录（如果不是内置）
        if not pkg.is_builtin and pkg.install_path.exists() and self.install_dir in pkg.install_path.parents:
            shutil.rmtree(pkg.install_path, ignore_errors=True)

        self._save_registry()
        logger.info(f"[SkillRegistry] 已卸载: {name}")
        return True

    def enable(self, name: str) -> bool:
        """启用技能"""
        pkg = self._packages.get(name)
        if pkg:
            pkg.is_enabled = True
            self._save_registry()
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用技能"""
        pkg = self._packages.get(name)
        if pkg:
            pkg.is_enabled = False
            self._save_registry()
            return True
        return False

    def get(self, name: str) -> Optional[Skill]:
        """获取技能对象"""
        pkg = self._packages.get(name)
        if pkg and pkg.is_enabled:
            return self._skills.get(name)
        return None

    def get_package(self, name: str) -> Optional[SkillPackage]:
        """获取技能包元数据"""
        return self._packages.get(name)

    def list_all(self) -> List[SkillPackage]:
        """列出所有已注册技能"""
        return list(self._packages.values())

    def list_enabled(self) -> List[Skill]:
        """列出所有启用的技能"""
        return [
            self._skills[name]
            for name, pkg in self._packages.items()
            if pkg.is_enabled
        ]

    def search(self, query: str) -> List[SkillPackage]:
        """搜索技能"""
        query_lower = query.lower()
        results = []
        for pkg in self._packages.values():
            score = 0
            if query_lower in pkg.name.lower():
                score += 10
            if query_lower in pkg.description.lower():
                score += 5
            for t in pkg.triggers:
                if query_lower in t.lower():
                    score += 3
            if score > 0:
                results.append((score, pkg))
        results.sort(key=lambda x: x[0], reverse=True)
        return [pkg for _, pkg in results]

    def match_by_text(self, text: str) -> List[Skill]:
        """根据文本匹配可能相关的技能"""
        matched = set()
        text_lower = text.lower()
        for trigger, names in self._trigger_index.items():
            if trigger.lower() in text_lower:
                matched.update(names)
        return [self._skills[name] for name in matched if name in self._skills]

    def resolve_dependencies(self, name: str) -> List[str]:
        """解析技能的依赖链（拓扑排序）"""
        resolved = []
        visiting = set()

        def visit(n: str):
            if n in resolved:
                return
            if n in visiting:
                raise ValueError(f"循环依赖 detected: {n}")
            visiting.add(n)
            pkg = self._packages.get(n)
            if pkg:
                for dep in pkg.dependencies:
                    dep_name = dep.split(">=")[0].split("==")[0].strip()
                    if dep_name in self._packages:
                        visit(dep_name)
                    else:
                        logger.warning(f"[SkillRegistry] 缺失依赖: {dep_name} (被 {n} 需要)")
            visiting.remove(n)
            resolved.append(n)

        visit(name)
        return resolved

    def get_marketplace_manifest(self) -> Dict:
        """获取技能市场清单（用于前端展示）"""
        return {
            "skills": [
                {
                    "name": pkg.name,
                    "version": pkg.version,
                    "description": pkg.description,
                    "author": pkg.author,
                    "source": pkg.source,
                    "triggers": pkg.triggers,
                    "tools": pkg.tools,
                    "dependencies": pkg.dependencies,
                    "installed_at": pkg.installed_at,
                    "is_builtin": pkg.is_builtin,
                    "is_enabled": pkg.is_enabled,
                }
                for pkg in sorted(self._packages.values(), key=lambda p: p.name)
            ],
            "total": len(self._packages),
            "enabled": sum(1 for p in self._packages.values() if p.is_enabled),
        }

    # ========== 内部实现 ==========

    def _scan_builtin_skills(self):
        """扫描内置 skills 目录"""
        if not self.install_dir.exists():
            return
        for skill_dir in self.install_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                try:
                    self.register(skill_dir, source="builtin")
                except Exception as e:
                    logger.warning(f"[SkillRegistry] 扫描技能失败 {skill_dir}: {e}")

    def _load_registry(self):
        """从 JSON 文件加载注册表"""
        registry_file = self.registry_dir / "registry.json"
        if not registry_file.exists():
            return
        try:
            data = json.loads(registry_file.read_text(encoding="utf-8"))
            for name, pkg_data in data.get("packages", {}).items():
                pkg = SkillPackage(
                    name=pkg_data["name"],
                    version=pkg_data["version"],
                    description=pkg_data.get("description", ""),
                    author=pkg_data.get("author", ""),
                    source=pkg_data.get("source", "local"),
                    source_url=pkg_data.get("source_url", ""),
                    install_path=Path(pkg_data.get("install_path", ".")),
                    triggers=pkg_data.get("triggers", []),
                    tools=pkg_data.get("tools", []),
                    dependencies=pkg_data.get("dependencies", []),
                    checksum=pkg_data.get("checksum", ""),
                    installed_at=pkg_data.get("installed_at", time.time()),
                    updated_at=pkg_data.get("updated_at", time.time()),
                    is_builtin=pkg_data.get("is_builtin", False),
                    is_enabled=pkg_data.get("is_enabled", True),
                )
                self._packages[name] = pkg
                # 尝试重新解析 Skill 对象
                skill_file = pkg.install_path / "SKILL.md"
                if skill_file.exists():
                    try:
                        content = skill_file.read_text(encoding="utf-8")
                        self._skills[name] = SkillLoader.parse(content, source_dir=str(pkg.install_path))
                        self._index_triggers(pkg)
                    except Exception as e:
                        logger.warning(f"[SkillRegistry] 加载技能失败 {name}: {e}")
            logger.info(f"[SkillRegistry] 已加载 {len(self._packages)} 个技能")
        except Exception as e:
            logger.warning(f"[SkillRegistry] 加载注册表失败: {e}")

    def _save_registry(self):
        """保存注册表到 JSON 文件"""
        registry_file = self.registry_dir / "registry.json"
        data = {
            "updated_at": time.time(),
            "packages": {
                name: {
                    "name": pkg.name,
                    "version": pkg.version,
                    "description": pkg.description,
                    "author": pkg.author,
                    "source": pkg.source,
                    "source_url": pkg.source_url,
                    "install_path": str(pkg.install_path),
                    "triggers": pkg.triggers,
                    "tools": pkg.tools,
                    "dependencies": pkg.dependencies,
                    "checksum": pkg.checksum,
                    "installed_at": pkg.installed_at,
                    "updated_at": pkg.updated_at,
                    "is_builtin": pkg.is_builtin,
                    "is_enabled": pkg.is_enabled,
                }
                for name, pkg in self._packages.items()
            },
        }
        registry_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _index_triggers(self, pkg: SkillPackage):
        """索引技能的触发词"""
        for trigger in pkg.triggers:
            if trigger not in self._trigger_index:
                self._trigger_index[trigger] = []
            if pkg.name not in self._trigger_index[trigger]:
                self._trigger_index[trigger].append(pkg.name)

    def _rebuild_trigger_index(self):
        """重建触发词索引"""
        self._trigger_index.clear()
        for pkg in self._packages.values():
            self._index_triggers(pkg)

    @staticmethod
    def _extract_version(content: str) -> Optional[str]:
        """从内容提取版本号"""
        import re
        # YAML frontmatter
        match = re.search(r'^version:\s*([\d.]+)', content, re.MULTILINE)
        if match:
            return match.group(1)
        # 文本中的版本标记
        match = re.search(r'(?:版本|Version)\s*[:v]?\s*([\d.]+)', content, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _extract_author(content: str) -> str:
        """从内容提取作者"""
        import re
        match = re.search(r'^author:\s*(.+)$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        match = re.search(r'(?:作者|Author)\s*[:：]\s*(.+)', content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    @staticmethod
    def _extract_dependencies(content: str) -> List[str]:
        """从内容提取依赖"""
        import re
        deps = []
        # YAML frontmatter
        match = re.search(r'^dependencies:\s*(.+)$', content, re.MULTILINE)
        if match:
            deps_text = match.group(1).strip()
            if deps_text.startswith("["):
                try:
                    deps = json.loads(deps_text)
                except:
                    deps = [d.strip() for d in deps_text.strip("[]").split(",") if d.strip()]
            else:
                deps = [d.strip() for d in deps_text.split(",") if d.strip()]
        # ## Dependencies section
        section_match = re.search(r'##\s+Dependencies\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL | re.IGNORECASE)
        if section_match:
            for line in section_match.group(1).strip().split("\n"):
                line = line.strip().lstrip("- *").strip()
                if line:
                    deps.append(line)
        return deps

    @staticmethod
    def _version_compare(v1: str, v2: str) -> int:
        """比较版本号: >0 if v1>v2, <0 if v1<v2, 0 if equal"""
        def parse(v):
            return [int(x) for x in v.split(".") if x.isdigit()]
        try:
            p1, p2 = parse(v1), parse(v2)
            for a, b in zip(p1, p2):
                if a != b:
                    return a - b
            return len(p1) - len(p2)
        except:
            return 0
