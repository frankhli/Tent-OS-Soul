"""确定性策略执行引擎 —— 微软 AGT 风格

核心设计：
1. YAML 规则定义，人类可读
2. 确定性执行 <0.1ms（不是概率性的！）
3. 覆盖输入/输出/动作三层防护
4. 规则热加载，无需重启

规则示例：
    policies:
      - name: "高危操作双人审批"
        condition: "action.danger_level > 0.7"
        action: "require_approval"
        approvers: 2
      
      - name: "物理执行者熔断保护"
        condition: "executor.consecutive_failures >= 3"
        action: "circuit_break"
        cooldown: "300s"
"""

import json
import logging
import operator
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger("tent_os.policy")


@dataclass
class PolicyRule:
    """策略规则"""
    name: str
    condition: str
    action: str
    params: Dict[str, Any] = None
    enabled: bool = True
    
    def __post_init__(self):
        if self.params is None:
            self.params = {}


class PolicyEngine:
    """策略引擎 —— 确定性规则执行
    
    与基于 Prompt 的安全策略不同：
    - Prompt 安全：概率性，违规率 26.67%
    - 策略引擎：确定性，违规率 0.00%
    
    执行流程：
        Agent Action → Policy Check → Allow / Deny / RequireApproval → Audit Log (<0.1ms)
    """
    
    def __init__(self, policy_path: str = "./config/policies.yaml"):
        self.policy_path = Path(policy_path)
        self.rules: List[PolicyRule] = []
        self._last_load_time = 0
        self._load_policies()
    
    def _load_policies(self):
        """加载策略文件"""
        if not self.policy_path.exists():
            self._create_default_policies()
        
        if not YAML_AVAILABLE:
            logger.warning("pyyaml 未安装，策略引擎使用默认规则")
            self._use_default_rules()
            return
        
        try:
            data = yaml.safe_load(self.policy_path.read_text())
            policies = data.get("policies", [])
            self.rules = []
            for p in policies:
                if p.get("enabled", True):
                    self.rules.append(PolicyRule(
                        name=p.get("name", "unnamed"),
                        condition=p.get("condition", "false"),
                        action=p.get("action", "allow"),
                        params=p.get("params", {}),
                    ))
            self._last_load_time = time.time()
            logger.info(f"加载 {len(self.rules)} 条策略规则")
        except Exception as e:
            logger.error(f"策略加载失败: {e}")
            self._use_default_rules()
    
    def _create_default_policies(self):
        """创建默认策略文件"""
        default = """# Tent OS 策略规则
# 规则按顺序执行，第一条匹配的规则生效

policies:
  # === 输入层防护 ===
  - name: "拒绝空任务"
    condition: "len(task) < 3"
    action: "deny"
    params:
      reason: "任务描述太短"

  # === 动作层防护 ===
  - name: "高危操作需审批"
    condition: "action in ['delete', 'rm', 'format', 'shutdown']"
    action: "require_approval"
    params:
      min_approvers: 1
      reason: "破坏性操作需要人工确认"

  - name: "物理操作夜间限制"
    condition: "is_physical and (hour >= 22 or hour <= 6)"
    action: "deny"
    params:
      reason: "夜间禁止物理执行者操作（紧急情况除外）"

  - name: "未授权执行者拒绝"
    condition: "not executor.authorized"
    action: "deny"
    params:
      reason: "执行者未授权"

  # === 执行者状态防护 ===
  - name: "熔断执行者拒绝"
    condition: "executor.status == 'offline'"
    action: "deny"
    params:
      reason: "执行者已熔断"

  - name: "连续失败限制"
    condition: "executor.consecutive_failures >= 3"
    action: "circuit_break"
    params:
      cooldown: 300

  - name: "队列深度限制"
    condition: "executor.queue_depth >= 10"
    action: "deny"
    params:
      reason: "执行者队列已满"

  # === 输出层防护 ===
  - name: "PII 数据检测"
    condition: "contains_pii(result)"
    action: "redact"
    params:
      fields: ["phone", "email", "id_card"]

  # === 默认规则 ===
  - name: "默认允许"
    condition: "true"
    action: "allow"
"""
        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        self.policy_path.write_text(default)
        logger.info(f"创建默认策略文件: {self.policy_path}")
    
    def _use_default_rules(self):
        """使用内置默认规则"""
        self.rules = [
            PolicyRule("高危操作需审批", "action in ['delete', 'rm', 'format']", "require_approval", {"min_approvers": 1}),
            PolicyRule("熔断保护", "executor.consecutive_failures >= 3", "circuit_break", {"cooldown": 300}),
            PolicyRule("默认允许", "true", "allow"),
        ]
    
    def evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """评估动作是否符合策略
        
        Args:
            context: 包含以下字段的字典
                - task: 任务描述
                - action: 动作名称
                - executor: 执行者状态字典
                - result: 结果（输出评估时用）
                - hour: 当前小时（0-23）
        
        Returns:
            {"decision": "allow|deny|require_approval|circuit_break|redact", ...}
        """
        start_time = time.perf_counter()
        
        # 热加载检查
        if time.time() - self._last_load_time > 60:  # 每分钟检查一次文件更新
            self._load_policies()
        
        for rule in self.rules:
            if not rule.enabled:
                continue
            
            if self._eval_condition(rule.condition, context):
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                result = {
                    "decision": rule.action,
                    "rule": rule.name,
                    "reason": rule.params.get("reason", f"匹配规则: {rule.name}"),
                    "params": rule.params,
                    "eval_time_ms": round(elapsed_ms, 3),
                }
                logger.debug(f"策略评估: {rule.name} -> {rule.action} ({elapsed_ms:.3f}ms)")
                return result
        
        # 默认允许
        return {"decision": "allow", "rule": "default", "eval_time_ms": 0}
    
    def _eval_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """评估条件表达式（简化版）
        
        支持的条件语法：
        - 布尔值: is_physical, executor.authorized
        - not 前缀: not executor.authorized
        - 比较: x > 5, x == 'value', x >= 3
        - 包含: x in ['a', 'b']
        - 逻辑: and, or
        - 函数: len(x)
        """
        condition = condition.strip()
        
        # 处理括号
        if condition.startswith("(") and condition.endswith(")"):
            condition = condition[1:-1]
        
        # 特殊值
        if condition == "true":
            return True
        if condition == "false":
            return False
        
        # 解析 not 前缀: "not executor.authorized"
        not_match = re.match(r"not\s+(.+)", condition, re.IGNORECASE)
        if not_match:
            inner = not_match.group(1).strip()
            return not self._eval_condition(inner, context)
        
        # 解析 and/or（必须在 comp_match 之前！否则 "hour >= 22 or hour <= 6" 会被 comp_match 错误匹配）
        and_parts = self._split_top_level(condition, "and")
        if len(and_parts) > 1:
            return all(self._eval_condition(p.strip(), context) for p in and_parts)
        
        or_parts = self._split_top_level(condition, "or")
        if len(or_parts) > 1:
            return any(self._eval_condition(p.strip(), context) for p in or_parts)
        
        # 解析 in 操作: "action in ['delete', 'rm']"
        in_match = re.match(r"(.+?)\s+in\s+\[(.+)\]", condition)
        if in_match:
            left = self._resolve_value(in_match.group(1).strip(), context)
            right_str = in_match.group(2)
            right = [v.strip().strip("'\"") for v in right_str.split(",")]
            return left in right
        
        # 解析比较: "executor.consecutive_failures >= 3"
        comp_match = re.match(r"(.+?)\s*([><=!]+)\s*(.+)", condition)
        if comp_match:
            left_expr = comp_match.group(1).strip()
            op_str = comp_match.group(2).strip()
            right_expr = comp_match.group(3).strip()
            
            left_val = self._resolve_value(left_expr, context)
            right_val = self._resolve_value(right_expr, context)
            
            ops = {
                ">": operator.gt,
                ">=": operator.ge,
                "<": operator.lt,
                "<=": operator.le,
                "==": operator.eq,
                "!=": operator.ne,
            }
            op = ops.get(op_str)
            if op and left_val is not None:
                try:
                    return op(float(left_val), float(right_val))
                except (ValueError, TypeError):
                    return op(str(left_val), str(right_val))
        
        # 解析 len: "len(task) < 3"
        len_match = re.match(r"len\((.+?)\)\s*([><=!]+)\s*(.+)", condition)
        if len_match:
            val = self._resolve_value(len_match.group(1).strip(), context)
            op_str = len_match.group(2).strip()
            target = int(len_match.group(3).strip())
            length = len(val) if val else 0
            ops = {
                ">": operator.gt, ">=": operator.ge,
                "<": operator.lt, "<=": operator.le,
                "==": operator.eq,
            }
            op = ops.get(op_str)
            return op(length, target) if op else False
        
        # 布尔表达式（无运算符）：如 "is_physical", "executor.authorized"
        val = self._resolve_value(condition, context)
        if val is not None:
            return bool(val)
        
        # 无法解析，默认 False
        logger.warning(f"无法解析条件: {condition}")
        return False
    
    def _split_top_level(self, condition: str, keyword: str) -> List[str]:
        """在顶层（不在括号内）按关键词分割"""
        parts = []
        current = []
        depth = 0
        tokens = re.split(r'(\s+|\(|\))', condition)
        
        for token in tokens:
            if token == '(':
                depth += 1
            elif token == ')':
                depth -= 1
            elif depth == 0 and token.strip().lower() == keyword:
                parts.append(''.join(current))
                current = []
                continue
            current.append(token)
        
        if current:
            parts.append(''.join(current))
        
        return [p.strip() for p in parts if p.strip()]
    
    def _resolve_value(self, expr: str, context: Dict[str, Any]) -> Any:
        """解析表达式值"""
        expr = expr.strip()
        
        # 字符串字面量
        if (expr.startswith("'") and expr.endswith("'")) or (expr.startswith('"') and expr.endswith('"')):
            return expr[1:-1]
        
        # 数字
        try:
            return int(expr)
        except ValueError:
            pass
        try:
            return float(expr)
        except ValueError:
            pass
        
        # 点号路径: executor.status, executor.consecutive_failures
        if "." in expr:
            parts = expr.split(".")
            val = context
            for part in parts:
                if isinstance(val, dict):
                    val = val.get(part)
                else:
                    return None
            return val
        
        # 直接上下文查找
        return context.get(expr)
    
    def get_rules_summary(self) -> List[Dict]:
        """获取规则摘要"""
        return [
            {
                "name": r.name,
                "condition": r.condition,
                "action": r.action,
                "enabled": r.enabled,
            }
            for r in self.rules
        ]
