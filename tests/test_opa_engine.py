"""Tests for OPAPolicyEngine —— OPA 风格策略引擎"""

import pytest

from tent_os.governance.opa_engine import (
    ConditionEvaluator,
    OPAPolicyEngine,
    Package,
    Rule,
    PolicyDecision,
    PolicyEngineCompat,
)


@pytest.fixture
def evaluator():
    return ConditionEvaluator()


@pytest.fixture
def engine(tmp_path):
    # Create a test policy file
    policy_file = tmp_path / "opa_policies.yaml"
    policy_file.write_text("""
packages:
  security:
    default: deny
    rules:
      - name: "reject_short_task"
        conditions: ["len(input.task) < 3"]
        decision: deny
        params:
          reason: "Too short"

      - name: "dangerous_action"
        conditions: ["input.action in ['delete', 'rm']"]
        decision: require_approval
        priority: 100
        params:
          reason: "Dangerous"

      - name: "physical_night"
        conditions:
          - "input.is_physical"
          - "input.hour >= 22 or input.hour <= 6"
        type: set_intersection
        decision: deny
        params:
          reason: "Night physical"

      - name: "default_allow"
        conditions: ["true"]
        decision: allow
        priority: -100

  compliance:
    default: allow
    rules:
      - name: "pii_detect"
        conditions: ["contains(input.result, 'PII')"]
        decision: redact
        params:
          reason: "PII found"
""")
    return OPAPolicyEngine(str(policy_file))


@pytest.mark.unit
class TestConditionEvaluator:
    def test_true_false(self, evaluator):
        assert evaluator.evaluate("true", {}) is True
        assert evaluator.evaluate("false", {}) is False

    def test_simple_comparison(self, evaluator):
        ctx = {"value": 5}
        assert evaluator.evaluate("input.value > 3", ctx) is True
        assert evaluator.evaluate("input.value < 3", ctx) is False
        assert evaluator.evaluate("input.value == 5", ctx) is True
        assert evaluator.evaluate("input.value >= 5", ctx) is True

    def test_not_prefix(self, evaluator):
        ctx = {"flag": True}
        assert evaluator.evaluate("not input.flag", ctx) is False
        assert evaluator.evaluate("not input.missing", ctx) is True

    def test_and_or(self, evaluator):
        ctx = {"a": 5, "b": 10}
        assert evaluator.evaluate("input.a > 3 and input.b > 8", ctx) is True
        assert evaluator.evaluate("input.a > 3 and input.b < 8", ctx) is False
        assert evaluator.evaluate("input.a > 10 or input.b > 8", ctx) is True

    def test_in_operation(self, evaluator):
        ctx = {"action": "delete"}
        assert evaluator.evaluate("input.action in ['delete', 'rm']", ctx) is True
        assert evaluator.evaluate("input.action in ['read', 'write']", ctx) is False

    def test_nested_path(self, evaluator):
        ctx = {"executor": {"consecutive_failures": 5}}
        assert evaluator.evaluate("input.executor.consecutive_failures >= 3", ctx) is True

    def test_contains_function(self, evaluator):
        ctx = {"result": "This has PII data"}
        assert evaluator.evaluate("contains(input.result, 'PII')", ctx) is True
        assert evaluator.evaluate("contains(input.result, 'SECRET')", ctx) is False

    def test_regex_match(self, evaluator):
        ctx = {"action": "rm -rf /data"}
        assert evaluator.evaluate("regex_match(input.action, 'rm.*')", ctx) is True
        assert evaluator.evaluate("regex_match(input.action, '^ls')", ctx) is False

    def test_in_range(self, evaluator):
        ctx = {"hour": 14}
        assert evaluator.evaluate("in_range(input.hour, 9, 18)", ctx) is True
        assert evaluator.evaluate("in_range(input.hour, 0, 6)", ctx) is False

    def test_exists(self, evaluator):
        ctx = {"field": "value"}
        assert evaluator.evaluate("exists(input.field)", ctx) is True
        assert evaluator.evaluate("exists(input.missing)", ctx) is False

    def test_len(self, evaluator):
        ctx = {"task": "ab"}
        assert evaluator.evaluate("len(input.task) < 3", ctx) is True
        assert evaluator.evaluate("len(input.task) >= 3", ctx) is False

    def test_parentheses(self, evaluator):
        ctx = {"hour": 23, "is_physical": True}
        assert evaluator.evaluate("(input.hour >= 22 or input.hour <= 6) and input.is_physical", ctx) is True


@pytest.mark.unit
class TestOPAPolicyEngine:
    def test_load_packages(self, engine):
        assert "security" in engine.packages
        assert "compliance" in engine.packages

    def test_default_decision(self, engine):
        assert engine.packages["security"].default_decision == "deny"
        assert engine.packages["compliance"].default_decision == "allow"

    def test_evaluate_allow(self, engine):
        result = engine.evaluate({
            "task": "正常运行任务",
            "action": "read",
            "executor": {"status": "online", "authorized": True},
            "hour": 14,
        })
        assert result["decision"] == "allow"

    def test_evaluate_deny_short_task(self, engine):
        result = engine.evaluate({
            "task": "x",
            "action": "read",
            "executor": {"status": "online"},
            "hour": 14,
        })
        assert result["decision"] == "deny"
        assert "reject_short_task" in result["rule"]

    def test_evaluate_require_approval(self, engine):
        result = engine.evaluate({
            "task": "删除数据",
            "action": "delete",
            "executor": {"status": "online", "authorized": True},
            "hour": 14,
        })
        assert result["decision"] == "require_approval"
        assert "dangerous_action" in result["rule"]

    def test_evaluate_physical_night(self, engine):
        result = engine.evaluate({
            "task": "物理操作",
            "action": "move",
            "is_physical": True,
            "executor": {"status": "online"},
            "hour": 23,
        })
        assert result["decision"] == "deny"
        assert "physical_night" in result["rule"]

    def test_evaluate_physical_day(self, engine):
        result = engine.evaluate({
            "task": "物理操作",
            "action": "move",
            "is_physical": True,
            "executor": {"status": "online"},
            "hour": 14,
        })
        assert result["decision"] == "allow"

    def test_evaluate_redact(self, engine):
        result = engine.evaluate({
            "task": "处理数据",
            "action": "read",
            "result": "用户手机号包含 PII 信息",
            "executor": {"status": "online"},
            "hour": 14,
        })
        assert result["decision"] == "redact"
        assert "pii_detect" in result["rule"]

    def test_evaluate_with_packages(self, engine):
        result = engine.evaluate({
            "task": "删除数据",
            "action": "delete",
            "executor": {"status": "online"},
        }, packages=["security"])
        assert result["decision"] == "require_approval"

    def test_get_rules_summary(self, engine):
        summary = engine.get_rules_summary()
        assert len(summary) >= 3
        names = [r["name"] for r in summary]
        assert "reject_short_task" in names
        assert "dangerous_action" in names

    def test_get_package_stats(self, engine):
        stats = engine.get_package_stats("security")
        assert stats is not None
        assert stats["default_decision"] == "deny"
        assert stats["rule_count"] >= 2

    def test_reload(self, engine):
        engine.reload()
        assert "security" in engine.packages


@pytest.mark.unit
class TestLegacyMigration:
    def test_migrate_legacy_format(self, tmp_path):
        legacy_file = tmp_path / "legacy.yaml"
        legacy_file.write_text("""
policies:
  - name: "test_rule"
    condition: "input.action == 'delete'"
    action: deny
    params:
      reason: "test"
""")
        engine = OPAPolicyEngine(str(legacy_file))
        assert "legacy" in engine.packages

        result = engine.evaluate({"action": "delete"})
        assert result["decision"] == "deny"


@pytest.mark.unit
class TestPolicyEngineCompat:
    def test_compat_interface(self, tmp_path):
        policy_file = tmp_path / "opa.yaml"
        policy_file.write_text("""
packages:
  default:
    default: allow
    rules:
      - name: "block_delete"
        conditions: ["input.action == 'delete'"]
        decision: deny
""")
        compat = PolicyEngineCompat(str(policy_file))
        result = compat.evaluate({"action": "delete"})
        assert result["decision"] == "deny"

        result = compat.evaluate({"action": "read"})
        assert result["decision"] == "allow"
