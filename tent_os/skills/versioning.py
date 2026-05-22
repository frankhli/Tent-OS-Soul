"""Skill 版本管理 —— 支持 Skill 的版本控制、回滚和 A/B 测试

版本格式：semantic versioning (major.minor.patch)
- major: 不兼容的 API 变更
- minor: 向后兼容的功能添加
- patch: 向后兼容的问题修复

功能：
1. 版本存储（保留历史版本）
2. A/B 测试框架
3. 快速回滚
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("tent_os.skills.versioning")


@dataclass
class SkillVersion:
    """Skill 版本"""
    skill_name: str
    version: str           # 语义版本号
    prompt: str
    tools: List[str]
    created_at: str
    created_by: str        # "user" / "auto_evolution" / "manual"
    parent_version: Optional[str] = None  # 父版本
    metrics_snapshot: Dict = None         # 版本创建时的指标快照


class SkillVersionManager:
    """Skill 版本管理器"""
    
    def __init__(self, storage_path: str = "./tent_memory/skill_versions"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._versions: Dict[str, List[SkillVersion]] = {}
        self._active_versions: Dict[str, str] = {}  # skill_name → version
        self._load_index()
    
    def _load_index(self):
        """加载版本索引"""
        index_file = self.storage_path / "index.json"
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text())
                self._active_versions = data.get("active_versions", {})
            except Exception as e:
                logger.warning(f"版本索引加载失败: {e}")
    
    def _save_index(self):
        """保存版本索引"""
        index_file = self.storage_path / "index.json"
        index_file.write_text(json.dumps({
            "active_versions": self._active_versions,
            "updated_at": datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2))
    
    def save_version(self, version: SkillVersion):
        """保存版本"""
        skill_dir = self.storage_path / version.skill_name
        skill_dir.mkdir(exist_ok=True)
        
        version_file = skill_dir / f"{version.version}.json"
        version_file.write_text(json.dumps({
            "skill_name": version.skill_name,
            "version": version.version,
            "prompt": version.prompt,
            "tools": version.tools,
            "created_at": version.created_at,
            "created_by": version.created_by,
            "parent_version": version.parent_version,
            "metrics_snapshot": version.metrics_snapshot,
        }, ensure_ascii=False, indent=2))
        
        # 更新索引
        if version.skill_name not in self._versions:
            self._versions[version.skill_name] = []
        self._versions[version.skill_name].append(version)
        
        logger.info(f"Skill 版本已保存: {version.skill_name}@{version.version}")
    
    def get_version(self, skill_name: str, version: str) -> Optional[SkillVersion]:
        """获取特定版本"""
        version_file = self.storage_path / skill_name / f"{version}.json"
        if not version_file.exists():
            return None
        
        try:
            data = json.loads(version_file.read_text())
            return SkillVersion(**data)
        except Exception as e:
            logger.warning(f"版本加载失败: {e}")
            return None
    
    def get_active_version(self, skill_name: str) -> Optional[str]:
        """获取当前活跃版本"""
        return self._active_versions.get(skill_name)
    
    def set_active_version(self, skill_name: str, version: str):
        """设置活跃版本"""
        # 检查版本是否存在
        v = self.get_version(skill_name, version)
        if not v:
            raise ValueError(f"版本不存在: {skill_name}@{version}")
        
        self._active_versions[skill_name] = version
        self._save_index()
        logger.info(f"活跃版本切换: {skill_name} → {version}")
    
    def list_versions(self, skill_name: str) -> List[SkillVersion]:
        """列出所有版本"""
        skill_dir = self.storage_path / skill_name
        if not skill_dir.exists():
            return []
        
        versions = []
        for f in sorted(skill_dir.glob("*.json")):
            if f.name == "index.json":
                continue
            try:
                data = json.loads(f.read_text())
                versions.append(SkillVersion(**data))
            except Exception:
                pass
        
        # 按版本号排序
        versions.sort(key=lambda v: self._parse_version(v.version), reverse=True)
        return versions
    
    def rollback(self, skill_name: str, steps: int = 1) -> Optional[str]:
        """回滚到之前的版本
        
        Args:
            steps: 回滚步数（1=上一个版本）
            
        Returns:
            str: 回滚后的版本号，或 None（无法回滚）
        """
        versions = self.list_versions(skill_name)
        if len(versions) <= steps:
            logger.warning(f"无法回滚 {skill_name}: 历史版本不足")
            return None
        
        current = self.get_active_version(skill_name)
        target = versions[steps]  # 第 steps 个历史版本
        
        self.set_active_version(skill_name, target.version)
        logger.info(f"回滚完成: {skill_name} {current} → {target.version}")
        
        return target.version
    
    def _parse_version(self, version_str: str) -> tuple:
        """解析语义版本号"""
        parts = version_str.split(".")
        return tuple(int(p) for p in parts)
    
    def bump_version(self, current_version: str, change_type: str = "patch") -> str:
        """递增版本号
        
        Args:
            change_type: "major" / "minor" / "patch"
        """
        major, minor, patch = self._parse_version(current_version)
        
        if change_type == "major":
            return f"{major + 1}.0.0"
        elif change_type == "minor":
            return f"{major}.{minor + 1}.0"
        else:
            return f"{major}.{minor}.{patch + 1}"
    
    def compare_versions(self, v1: str, v2: str) -> int:
        """比较两个版本号
        
        Returns:
            -1: v1 < v2
             0: v1 == v2
             1: v1 > v2
        """
        p1 = self._parse_version(v1)
        p2 = self._parse_version(v2)
        
        if p1 < p2:
            return -1
        elif p1 > p2:
            return 1
        return 0


class ABTestManager:
    """A/B 测试管理器"""
    
    def __init__(self, version_manager: SkillVersionManager):
        self.version_manager = version_manager
        self._tests: Dict[str, Dict] = {}  # skill_name → test_config
    
    def start_test(self, skill_name: str, version_a: str, version_b: str,
                   traffic_split: float = 0.5) -> str:
        """开始 A/B 测试
        
        Args:
            traffic_split: 版本 A 的流量占比（0-1）
            
        Returns:
            str: 测试 ID
        """
        test_id = f"ab-{skill_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        self._tests[skill_name] = {
            "test_id": test_id,
            "version_a": version_a,
            "version_b": version_b,
            "traffic_split": traffic_split,
            "started_at": datetime.now().isoformat(),
            "a_invocations": 0,
            "b_invocations": 0,
            "a_success": 0,
            "b_success": 0,
        }
        
        logger.info(f"A/B 测试开始: {skill_name} {version_a} vs {version_b}")
        return test_id
    
    def select_version(self, skill_name: str, session_id: str = None) -> str:
        """根据流量分配选择版本"""
        test = self._tests.get(skill_name)
        if not test:
            # 没有 A/B 测试，返回活跃版本
            return self.version_manager.get_active_version(skill_name)
        
        # 基于 session_id 的哈希决定版本（确保同一会话始终用同一版本）
        if session_id:
            import hashlib
            hash_val = int(hashlib.md5(session_id.encode()).hexdigest(), 16)
            use_a = (hash_val % 100) < (test["traffic_split"] * 100)
        else:
            import random
            use_a = random.random() < test["traffic_split"]
        
        return test["version_a"] if use_a else test["version_b"]
    
    def record_result(self, skill_name: str, version: str, success: bool):
        """记录 A/B 测试结果"""
        test = self._tests.get(skill_name)
        if not test:
            return
        
        if version == test["version_a"]:
            test["a_invocations"] += 1
            if success:
                test["a_success"] += 1
        elif version == test["version_b"]:
            test["b_invocations"] += 1
            if success:
                test["b_success"] += 1
    
    def get_test_result(self, skill_name: str) -> Optional[Dict]:
        """获取 A/B 测试结果"""
        test = self._tests.get(skill_name)
        if not test:
            return None
        
        a_total = test["a_invocations"]
        b_total = test["b_invocations"]
        
        a_rate = test["a_success"] / max(a_total, 1)
        b_rate = test["b_success"] / max(b_total, 1)
        
        return {
            "test_id": test["test_id"],
            "version_a": test["version_a"],
            "version_b": test["version_b"],
            "a_invocations": a_total,
            "b_invocations": b_total,
            "a_success_rate": a_rate,
            "b_success_rate": b_rate,
            "winner": test["version_a"] if a_rate > b_rate else test["version_b"],
            "significant": abs(a_rate - b_rate) > 0.1 and min(a_total, b_total) > 10,
        }
    
    def end_test(self, skill_name: str, promote_winner: bool = True) -> Optional[str]:
        """结束 A/B 测试
        
        Returns:
            str: 胜出版本号，或 None
        """
        result = self.get_test_result(skill_name)
        if not result:
            return None
        
        winner = result["winner"]
        
        if promote_winner and result["significant"]:
            self.version_manager.set_active_version(skill_name, winner)
            logger.info(f"A/B 测试结束，胜出版本已上线: {skill_name}@{winner}")
        
        del self._tests[skill_name]
        return winner
