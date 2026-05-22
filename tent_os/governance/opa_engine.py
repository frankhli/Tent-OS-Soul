"""OPA-style Policy Engine —— 设计即合规

将 Harness 的 "Policy as Code" 理念移植到 Tent OS：
- Package: 按域组织策略（security / compliance / ops）
- Default: 显式默认决策（allow/deny）
- Set operations: 规则并/交/差组合
- Rule composition: 策略引用其他策略
- Context pathing: 丰富的数据上下文解析

与现有 PolicyEngine 的关系：
- OPAPolicyEngine 是增强版，兼容 evaluate(context) 接口
- GovernanceWorker 优先使用 OPA，回退到旧引擎
- 现有 YAML 策略文件自动升级兼容
"""

import json
import logging
import operator
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union

logger = logging.getLogger("tent_os.opa")

# ======== OPA 核心数据模型 ========

@dataclass
class Package:
    """策略包 —— OPA package 概念"""
    name: str
    default_decision: str = "deny"  # OPA 风格：默认拒绝
    rules: List["Rule"] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)  # 引用其他包
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Rule:
    """OPA 风格规则
    
    与旧 PolicyRule 的区别：
    - 支持集合操作（union/intersection/difference）
    - 支持引用其他规则
    - 支持多层条件嵌套
    """
    name: str
    # 三种规则类型：
    # 1. direct: 直接条件判断（原 PolicyRule 模式）
    # 2. set_union: 多个条件的并集（任一满足）
    # 3. set_intersection: 多个条件的交集（全部满足）
    # 4. reference: 引用其他规则/包
    rule_type: str = "direct"
    # 条件表达式列表（set 操作时使用多个）
    conditions: List[str] = field(default_factory=list)
    # 动作决策
    decision: str = "allow"
    # 参数
    params: Dict[str, Any] = field(default_factory=dict)
    # 规则权重（优先级）
    priority: int = 0
    enabled: bool = True
    # 引用其他规则名
    references: List[str] = field(default_factory=list)
    # 生效时间窗口（可选）
    time_window: Optional[Dict[str, int]] = None  # {"start_hour": 9, "end_hour": 18}


@dataclass
class PolicyDecision:
    """策略决策结果"""
    decision: str  # allow/deny/require_approval/circuit_break/redact/audit
    rule: str
    package: str
    reason: str
    params: Dict[str, Any]
    eval_time_ms: float
    matched_conditions: List[str] = field(default_factory=list)
    audit_level: str = "info"  # debug/info/warn/error


# ======== 条件评估器 ========

class ConditionEvaluator:
    """条件表达式评估器 —— 增强版，支持 OPA 风格路径"""

    # 比较操作符映射
    COMP_OPS: Dict[str, Callable] = {
        ">": operator.gt, ">=": operator.ge,
        "<": operator.lt, "<=": operator.le,
        "==": operator.eq, "!=": operator.ne,
        "=": operator.eq,
    }

    # 集合操作符
    SET_OPS: Dict[str, Callable] = {
        "union": lambda sets: set().union(*sets),
        "intersection": lambda sets: set.intersection(*sets) if sets else set(),
        "difference": lambda sets: sets[0].difference(*sets[1:]) if len(sets) > 1 else sets[0],
    }

    def __init__(self):
        self._functions: Dict[str, Callable] = {
            "contains": self._fn_contains,
            "startswith": self._fn_startswith,
            "endswith": self._fn_endswith,
            "regex_match": self._fn_regex_match,
            "in_range": self._fn_in_range,
            "all": self._fn_all,
            "any": self._fn_any,
            "exists": self._fn_exists,
        }

    def evaluate(self, condition: str, context: Dict[str, Any]) -> bool:
        """评估单条条件表达式"""
        condition = condition.strip()
        if not condition or condition == "true":
            return True
        if condition == "false":
            return False

        # 括号包裹的表达式
        if condition.startswith("(") and condition.endswith(")"):
            return self.evaluate(condition[1:-1], context)

        # not 前缀
        if condition.lower().startswith("not "):
            return not self.evaluate(condition[4:], context)

        # 逻辑组合（and/or）—— 优先于比较
        top_and = self._split_top_level(condition, " and ")
        if len(top_and) > 1:
            return all(self.evaluate(p.strip(), context) for p in top_and)

        top_or = self._split_top_level(condition, " or ")
        if len(top_or) > 1:
            return any(self.evaluate(p.strip(), context) for p in top_or)

        # 函数调用: contains(result, "PII") or regex_match(action, "rm.*")
        func_match = re.match(r"(\w+)\s*\((.*)\)\s*$", condition)
        if func_match:
            fn_name = func_match.group(1)
            args_str = func_match.group(2)
            args = self._parse_args(args_str)
            if fn_name in self._functions:
                return self._functions[fn_name](args, context)

        # in 操作: action in ["delete", "rm"]
        in_match = re.match(r"(.+?)\s+in\s+\[(.+)\]", condition)
        if in_match:
            left = self._resolve_value(in_match.group(1).strip(), context)
            right = [v.strip().strip("'\"") for v in in_match.group(2).split(",")]
            return left in right

        # len 比较: "len(task) < 3"
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

        # 比较: executor.consecutive_failures >= 3
        comp_match = re.match(r"(.+?)\s*([><=!]+)\s*(.+)", condition)
        if comp_match:
            left_expr = comp_match.group(1).strip()
            op_str = comp_match.group(2).strip()
            right_expr = comp_match.group(3).strip()
            left_val = self._resolve_value(left_expr, context)
            right_val = self._resolve_value(right_expr, context)
            op = self.COMP_OPS.get(op_str)
            if op and left_val is not None:
                try:
                    return op(float(left_val), float(right_val))
                except (ValueError, TypeError):
                    return op(str(left_val), str(right_val))

        # 布尔值: is_physical
        val = self._resolve_value(condition, context)
        if val is not None:
            return bool(val)

        logger.warning(f"[OPA] 无法解析条件: {condition}")
        return False

    def _resolve_value(self, expr: str, context: Dict[str, Any]) -> Any:
        """解析值表达式 —— 支持 OPA 风格路径和字面量"""
        expr = expr.strip()
        # 字符串字面量
        if (expr.startswith('"') and expr.endswith('"')) or \
           (expr.startswith("'") and expr.endswith("'")):
            return expr[1:-1]
        # 数字
        try:
            if "." in expr:
                return float(expr)
            return int(expr)
        except ValueError:
            pass
        # 路径解析: executor.consecutive_failures or input.action
        if expr.startswith("input."):
            expr = expr[6:]  # 去掉 input. 前缀
        parts = expr.split(".")
        current = context
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    def _split_top_level(self, condition: str, keyword: str) -> List[str]:
        """在顶层（不在括号内）按关键词分割"""
        parts = []
        current = []
        depth = 0
        tokens = re.split(r'(\s+|\(|\))', condition)
        for tok in tokens:
            if tok == "(":
                depth += 1
                current.append(tok)
            elif tok == ")":
                depth -= 1
                current.append(tok)
            elif depth == 0 and tok.lower() == keyword.strip().lower():
                parts.append("".join(current))
                current = []
            else:
                current.append(tok)
        if current:
            parts.append("".join(current))
        return parts

    def _parse_args(self, args_str: str) -> List[str]:
        """解析函数参数（支持嵌套括号）"""
        args = []
        current = []
        depth = 0
        for c in args_str:
            if c == '(':
                depth += 1
                current.append(c)
            elif c == ')':
                depth -= 1
                current.append(c)
            elif c == ',' and depth == 0:
                args.append("".join(current).strip())
                current = []
            else:
                current.append(c)
        if current:
            args.append("".join(current).strip())
        return args

    # ===== 内置函数 =====

    def _fn_contains(self, args: List[str], context: Dict) -> bool:
        if len(args) != 2:
            return False
        haystack = self._resolve_value(args[0], context)
        needle = self._resolve_value(args[1], context)
        if haystack is None or needle is None:
            return False
        return needle in str(haystack)

    def _fn_startswith(self, args: List[str], context: Dict) -> bool:
        if len(args) != 2:
            return False
        s = self._resolve_value(args[0], context)
        prefix = self._resolve_value(args[1], context)
        if s is None or prefix is None:
            return False
        return str(s).startswith(str(prefix))

    def _fn_endswith(self, args: List[str], context: Dict) -> bool:
        if len(args) != 2:
            return False
        s = self._resolve_value(args[0], context)
        suffix = self._resolve_value(args[1], context)
        if s is None or suffix is None:
            return False
        return str(s).endswith(str(suffix))

    def _fn_regex_match(self, args: List[str], context: Dict) -> bool:
        if len(args) != 2:
            return False
        s = self._resolve_value(args[0], context)
        pattern = self._resolve_value(args[1], context)
        if s is None or pattern is None:
            return False
        return bool(re.search(str(pattern), str(s)))

    def _fn_in_range(self, args: List[str], context: Dict) -> bool:
        if len(args) != 3:
            return False
        val = self._resolve_value(args[0], context)
        low = self._resolve_value(args[1], context)
        high = self._resolve_value(args[2], context)
        try:
            return float(low) <= float(val) <= float(high)
        except (ValueError, TypeError):
            return False

    def _fn_all(self, args: List[str], context: Dict) -> bool:
        return all(self.evaluate(a, context) for a in args)

    def _fn_any(self, args: List[str], context: Dict) -> bool:
        return any(self.evaluate(a, context) for a in args)

    def _fn_exists(self, args: List[str], context: Dict) -> bool:
        if not args:
            return False
        return self._resolve_value(args[0], context) is not None


# ======== OPA 策略引擎 ========

class OPAPolicyEngine:
    """OPA 风格策略引擎

    使用方式：
        engine = OPAPolicyEngine("./config/opa_policies.yaml")
        result = engine.evaluate({
            "task": "删除数据库",
            "action": "delete",
            "executor": {"status": "online", "authorized": True},
        })
        # result: PolicyDecision
    """

    def __init__(self, policy_path: str = "./config/opa_policies.yaml"):
        self.policy_path = Path(policy_path)
        self.packages: Dict[str, Package] = {}
        self.evaluator = ConditionEvaluator()
        self._last_load_time = 0.0
        self._load_policies()

    def _load_policies(self):
        """加载策略文件"""
        if not self.policy_path.exists():
            self._create_default_policies()
            return

        try:
            import yaml
            with open(self.policy_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._parse_yaml(data)
            self._last_load_time = time.time()
            logger.info(f"[OPA] 加载 {len(self.packages)} 个策略包, "
                        f"{sum(len(p.rules) for p in self.packages.values())} 条规则")
        except Exception as e:
            logger.warning(f"[OPA] 加载策略失败: {e}, 使用默认策略")
            self._use_defaults()

    def _parse_yaml(self, data: Dict):
        """解析 YAML 策略定义"""
        # 支持旧格式（直接 policies 列表）自动升级
        if "policies" in data and "packages" not in data:
            self._migrate_legacy_format(data)
            return

        for pkg_name, pkg_data in data.get("packages", {}).items():
            pkg = Package(
                name=pkg_name,
                default_decision=pkg_data.get("default", "deny"),
                imports=pkg_data.get("import", []),
                metadata=pkg_data.get("metadata", {}),
            )
            for rule_data in pkg_data.get("rules", []):
                rule = Rule(
                    name=rule_data["name"],
                    rule_type=rule_data.get("type", "direct"),
                    conditions=rule_data.get("conditions", [rule_data.get("condition", "true")]),
                    decision=rule_data.get("decision", "allow"),
                    params=rule_data.get("params", {}),
                    priority=rule_data.get("priority", 0),
                    enabled=rule_data.get("enabled", True),
                    references=rule_data.get("references", []),
                    time_window=rule_data.get("time_window"),
                )
                pkg.rules.append(rule)
            # 按优先级排序（高优先级在前）
            pkg.rules.sort(key=lambda r: r.priority, reverse=True)
            self.packages[pkg_name] = pkg

    def _migrate_legacy_format(self, data: Dict):
        """将旧版 policies 格式迁移为 OPA 包格式"""
        legacy_rules = data.get("policies", [])
        pkg = Package(name="legacy", default_decision="allow")
        for rule_data in legacy_rules:
            rule = Rule(
                name=rule_data["name"],
                rule_type="direct",
                conditions=[rule_data.get("condition", "true")],
                decision=rule_data.get("action", "allow"),
                params=rule_data.get("params", {}),
                enabled=rule_data.get("enabled", True),
            )
            pkg.rules.append(rule)
        self.packages["legacy"] = pkg
        logger.info(f"[OPA] 已迁移 {len(legacy_rules)} 条旧格式策略到 legacy 包")

    def _create_default_policies(self):
        """创建默认 OPA 策略"""
        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        default = self._default_policy_yaml()
        with open(self.policy_path, "w", encoding="utf-8") as f:
            f.write(default)
        self._use_defaults()

    def _default_policy_yaml(self) -> str:
        return '''# Tent OS OPA 策略配置
# 设计理念: 默认拒绝，显式允许

packages:
  # === 安全包: 动作安全策略 ===
  security:
    default: deny
    metadata:
      owner: "security-team"
      version: "1.0"
    rules:
      - name: "空任务拒绝"
        conditions: ["len(input.task) < 3"]
        decision: deny
        params:
          reason: "任务描述太短"
          audit_level: warn

      - name: "高危操作需审批"
        conditions: ["input.action in ['delete', 'rm', 'format', 'shutdown']"]
        decision: require_approval
        priority: 100
        params:
          min_approvers: 1
          reason: "破坏性操作需要人工确认"

      - name: "物理操作夜间限制"
        conditions:
          - "input.is_physical"
          - "input.hour >= 22 or input.hour <= 6"
        type: set_intersection
        decision: deny
        params:
          reason: "夜间禁止物理执行者操作"

      - name: "未授权拒绝"
        conditions: ["not input.executor.authorized"]
        decision: deny
        priority: 200
        params:
          reason: "执行者未授权"

      - name: "熔断保护"
        conditions: ["input.executor.consecutive_failures >= 3"]
        decision: circuit_break
        priority: 200
        params:
          cooldown: 300
          reason: "执行者连续失败过多"

  # === 合规矩: 数据合规策略 ===
  compliance:
    default: allow
    import: ["security"]
    rules:
      - name: "PII 数据脱敏"
        conditions: ["contains(input.result, 'PII') or regex_match(input.result, '\\d{11}')"]
        decision: redact
        params:
          fields: ["phone", "email", "id_card"]
          reason: "检测到敏感信息"

      - name: "工作时间限制"
        conditions: ["not in_range(input.hour, 9, 18)"]
        type: set_union
        decision: audit
        time_window:
          start_hour: 0
          end_hour: 24
        params:
          reason: "非工作时间操作已记录"

  # === 运维包: 运维策略 ===
  ops:
    default: allow
    rules:
      - name: "队列深度限制"
        conditions: ["input.executor.queue_depth >= 10"]
        decision: deny
        params:
          reason: "执行者队列已满"

      - name: "默认允许"
        conditions: ["true"]
        decision: allow
        priority: -100
        params:
          reason: "无安全策略匹配，默认允许"
'''

    def _use_defaults(self):
        """使用内存默认策略"""
        pkg = Package(name="default", default_decision="allow")
        pkg.rules = [
            Rule(name="default_allow", rule_type="direct",
                 conditions=["true"], decision="allow"),
        ]
        self.packages["default"] = pkg

    # ======== 核心评估接口 ========

    def evaluate(self, context: Dict[str, Any],
                 packages: Optional[List[str]] = None) -> Dict[str, Any]:
        """评估上下文是否符合策略

        兼容旧 PolicyEngine.evaluate() 接口，返回 Dict。
        内部使用 PolicyDecision，但输出保持兼容。
        """
        start_time = time.perf_counter()

        # 热加载检查
        if time.time() - self._last_load_time > 60:
            self._load_policies()

        # 规范化上下文：添加 input. 前缀以支持 OPA 风格路径
        if "input" not in context:
            context = {"input": context, **context}

        # 默认决策（按包优先级叠加）
        target_packages = packages or list(self.packages.keys())
        overall_decision = "allow"
        matched_rule = "default"
        matched_pkg = ""
        reason = "默认允许"
        params: Dict[str, Any] = {}
        matched_conditions: List[str] = []
        audit_level = "info"

        # 安全包优先，合规次之，运维最后
        priority_order = ["security", "compliance", "ops", "legacy", "default"]
        target_packages.sort(key=lambda p: priority_order.index(p)
                             if p in priority_order else 99)

        for pkg_name in target_packages:
            pkg = self.packages.get(pkg_name)
            if not pkg:
                continue

            decision = self._evaluate_package(pkg, context)
            if decision:
                # 决策优先级: deny > circuit_break > require_approval > redact > audit > allow
                if self._decision_priority(decision.decision) > \
                   self._decision_priority(overall_decision):
                    overall_decision = decision.decision
                    matched_rule = decision.rule
                    matched_pkg = pkg_name
                    reason = decision.reason
                    params = decision.params
                    matched_conditions = decision.matched_conditions
                    audit_level = decision.audit_level

                # 如果是 deny/circuit_break，立即返回（短路）
                if overall_decision in ("deny", "circuit_break"):
                    break

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return {
            "decision": overall_decision,
            "rule": matched_rule,
            "package": matched_pkg,
            "reason": reason,
            "params": params,
            "eval_time_ms": round(elapsed_ms, 3),
            "matched_conditions": matched_conditions,
            "audit_level": audit_level,
        }

    def _evaluate_package(self, pkg: Package,
                          context: Dict[str, Any]) -> Optional[PolicyDecision]:
        """评估单个策略包"""
        for rule in pkg.rules:
            if not rule.enabled:
                continue

            # 时间窗口检查
            if rule.time_window and not self._check_time_window(rule.time_window):
                continue

            matched, conditions = self._evaluate_rule(rule, context)
            if matched:
                return PolicyDecision(
                    decision=rule.decision,
                    rule=rule.name,
                    package=pkg.name,
                    reason=rule.params.get("reason", f"匹配规则: {rule.name}"),
                    params=rule.params,
                    eval_time_ms=0.0,
                    matched_conditions=conditions,
                    audit_level=rule.params.get("audit_level", "info"),
                )

        # 无匹配，返回包的默认决策
        return PolicyDecision(
            decision=pkg.default_decision,
            rule="default",
            package=pkg.name,
            reason=f"包 {pkg.name} 默认决策",
            params={},
            eval_time_ms=0.0,
        ) if pkg.default_decision != "allow" else None

    def _evaluate_rule(self, rule: Rule,
                       context: Dict[str, Any]) -> tuple[bool, List[str]]:
        """评估单条规则，返回 (是否匹配, 匹配的条件列表)"""
        if not rule.conditions:
            return True, []

        matched = []

        if rule.rule_type == "direct":
            # 单条件直接判断
            cond = rule.conditions[0]
            if self.evaluator.evaluate(cond, context):
                matched.append(cond)
            return len(matched) > 0, matched

        elif rule.rule_type == "set_union":
            # 并集：任一条件满足
            for cond in rule.conditions:
                if self.evaluator.evaluate(cond, context):
                    matched.append(cond)
            return len(matched) > 0, matched

        elif rule.rule_type == "set_intersection":
            # 交集：全部条件满足
            for cond in rule.conditions:
                if not self.evaluator.evaluate(cond, context):
                    return False, []
                matched.append(cond)
            return True, matched

        elif rule.rule_type == "reference":
            # 引用其他规则
            for ref in rule.references:
                ref_matched, ref_conds = self._evaluate_reference(ref, context)
                if ref_matched:
                    matched.extend(ref_conds)
            return len(matched) > 0, matched

        return False, []

    def _evaluate_reference(self, ref: str,
                            context: Dict[str, Any]) -> tuple[bool, List[str]]:
        """评估规则引用"""
        # 格式: "package.rule" 或 "rule"
        if "." in ref:
            pkg_name, rule_name = ref.split(".", 1)
        else:
            pkg_name, rule_name = None, ref

        for name, pkg in self.packages.items():
            if pkg_name and name != pkg_name:
                continue
            for rule in pkg.rules:
                if rule.name == rule_name:
                    return self._evaluate_rule(rule, context)
        return False, []

    def _check_time_window(self, window: Dict[str, int]) -> bool:
        """检查当前时间是否在窗口内"""
        import datetime
        now = datetime.datetime.now()
        start = window.get("start_hour", 0)
        end = window.get("end_hour", 24)
        return start <= now.hour < end

    def _decision_priority(self, decision: str) -> int:
        """决策优先级排序（数值越大越优先）"""
        return {
            "allow": 0,
            "audit": 1,
            "redact": 2,
            "require_approval": 3,
            "circuit_break": 4,
            "deny": 5,
        }.get(decision, 0)

    # ======== 管理接口 ========

    def get_rules_summary(self) -> List[Dict]:
        """获取所有规则的摘要"""
        result = []
        for pkg in self.packages.values():
            for rule in pkg.rules:
                result.append({
                    "package": pkg.name,
                    "name": rule.name,
                    "type": rule.rule_type,
                    "decision": rule.decision,
                    "priority": rule.priority,
                    "enabled": rule.enabled,
                    "conditions": rule.conditions,
                })
        return result

    def get_packages(self) -> List[str]:
        """获取所有包名"""
        return list(self.packages.keys())

    def get_package_stats(self, pkg_name: str) -> Optional[Dict]:
        """获取包统计信息"""
        pkg = self.packages.get(pkg_name)
        if not pkg:
            return None
        return {
            "name": pkg.name,
            "default_decision": pkg.default_decision,
            "rule_count": len(pkg.rules),
            "imports": pkg.imports,
            "metadata": pkg.metadata,
        }

    def reload(self):
        """手动重新加载策略"""
        self._load_policies()
        logger.info("[OPA] 策略已手动重新加载")


# ======== 兼容性包装器 ========

class PolicyEngineCompat:
    """兼容层：让旧代码无缝切换到 OPA 引擎

    使用方式：
        from tent_os.governance.opa_engine import PolicyEngineCompat as PolicyEngine
    """

    def __init__(self, policy_path: str = "./config/opa_policies.yaml"):
        self._engine = OPAPolicyEngine(policy_path)

    def evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._engine.evaluate(context)

    def get_rules_summary(self) -> List[Dict]:
        return self._engine.get_rules_summary()

    def reload(self):
        self._engine.reload()
