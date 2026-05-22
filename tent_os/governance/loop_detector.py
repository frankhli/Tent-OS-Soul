"""Loop Detector —— Tool Loop 循环检测器

检测 LLM 在 ReAct Tool Loop 中陷入循环的多种模式。

核心设计哲学（Tent OS 风格）：
- 不只看"调了几次"，而要看"每次调用是否产生了新信息"
- 有数据（结果变化）才允许继续，无数据（结果重复）才判定为循环
- 宁可漏杀，不可误杀——误中断正常流程比漏检循环更糟

检测维度：
1. 参数重复 + 结果无变化 —— 同一工具+相同参数，结果每次都一样
2. 工具序列重复 + 结果无变化 —— A→B→A→B，每轮结果都一样
3. 响应重复 —— LLM 反复输出相似内容（没有工具调用时也算）
4. 停滞检测 —— 多轮后没有产生新信息
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Any

logger = logging.getLogger("tent_os.loop_detector")


@dataclass
class LoopDetectionResult:
    """循环检测结果"""
    is_loop: bool = False
    loop_type: str = ""           # parameter_repeat | tool_sequence_repeat | response_repeat | stagnation
    confidence: float = 0.0       # 0-1
    details: str = ""             # 人类可读的说明
    suggestion: str = ""          # 给用户的建议
    iteration: int = 0            # 检测到的迭代次数


@dataclass
class LoopHistory:
    """单次迭代的循环检测历史记录"""
    iteration: int
    content: str                  # LLM 的文本回复
    tool_names: List[str]         # 本轮调用的工具名列表
    tool_signatures: List[str]    # 工具签名的 hash 列表 (name:args_hash)
    tool_results: List[str]       # 工具结果的原始字符串（用于比较是否有新信息）
    
    def tool_results_summary(self) -> str:
        """生成工具结果的摘要字符串"""
        return ";".join(self.tool_results)


class LoopDetector:
    """Tool Loop 循环检测器
    
    设计原则：
    1. 信息价值优先于调用次数——结果有变化就不算循环
    2. 多层检测，从确定性高到低排序
    3. 所有检测记录到 state_store，供后续分析
    """
    
    def __init__(self,
                 response_repeat_threshold: float = 0.85,
                 response_repeat_window: int = 3,
                 tool_sequence_window: int = 4,
                 parameter_repeat_threshold: int = 3,  # 同一参数组合最多3次
                 stagnation_window: int = 3,
                 stagnation_similarity: float = 0.90,
                 result_similarity_threshold: float = 0.85):
        """
        Args:
            response_repeat_threshold: 响应相似度阈值
            response_repeat_window: 检测最近 N 轮响应的重复
            tool_sequence_window: 检测最近 N 轮的工具序列
            parameter_repeat_threshold: 同一参数组合最多允许调用次数
            stagnation_window: 停滞检测窗口大小
            stagnation_similarity: 停滞检测结果相似度阈值
            result_similarity_threshold: 工具结果相似度阈值（低于此值认为有新信息）
        """
        self.response_repeat_threshold = response_repeat_threshold
        self.response_repeat_window = response_repeat_window
        self.tool_sequence_window = tool_sequence_window
        self.parameter_repeat_threshold = parameter_repeat_threshold
        self.stagnation_window = stagnation_window
        self.stagnation_similarity = stagnation_similarity
        self.result_similarity_threshold = result_similarity_threshold
        
        self._histories: Dict[str, List[LoopHistory]] = {}
    
    def _get_history(self, session_id: str) -> List[LoopHistory]:
        return self._histories.get(session_id, [])
    
    def _record(self, session_id: str, history: LoopHistory):
        if session_id not in self._histories:
            self._histories[session_id] = []
        self._histories[session_id].append(history)
        if len(self._histories[session_id]) > 100:
            self._histories[session_id] = self._histories[session_id][-50:]
    
    def reset_session(self, session_id: str):
        self._histories.pop(session_id, None)
    
    def check(self, session_id: str, iteration: int,
              content: str, tool_calls: List[Dict],
              tool_results: List[Any]) -> LoopDetectionResult:
        """执行循环检测
        
        优先级（从高到低确定性）：
        1. 参数重复 + 结果无变化（最确定）
        2. 工具序列重复 + 结果无变化
        3. 响应重复（可能误杀，阈值调高）
        4. 停滞检测（兜底）
        """
        tool_names = []
        tool_signatures = []
        tool_results_str = []
        
        for i, tc in enumerate(tool_calls):
            name = tc.get("function", {}).get("name", tc.get("name", ""))
            args = tc.get("function", {}).get("arguments", tc.get("arguments", "{}"))
            if isinstance(args, str):
                args_str = args
            else:
                args_str = json.dumps(args, sort_keys=True, ensure_ascii=False)
            sig = hashlib.md5(f"{name}:{args_str}".encode()).hexdigest()[:16]
            
            tool_names.append(name)
            tool_signatures.append(sig)
            
            # 记录工具结果
            result = tool_results[i] if i < len(tool_results) else {}
            if isinstance(result, dict):
                tool_results_str.append(json.dumps(result, sort_keys=True, ensure_ascii=False))
            else:
                tool_results_str.append(str(result))
        
        history = LoopHistory(
            iteration=iteration,
            content=content or "",
            tool_names=tool_names,
            tool_signatures=tool_signatures,
            tool_results=tool_results_str,
        )
        self._record(session_id, history)
        
        hist = self._get_history(session_id)
        
        # 检测 1: 参数重复 + 结果无变化
        param_result = self._check_parameter_repeat(hist)
        if param_result.is_loop:
            logger.warning(f"[LOOP] 参数重复+结果无变化 [{session_id}] iter={iteration}: {param_result.details}")
            return param_result
        
        # 检测 2: 工具序列重复 + 结果无变化
        seq_result = self._check_tool_sequence_repeat(hist)
        if seq_result.is_loop:
            logger.warning(f"[LOOP] 工具序列重复+结果无变化 [{session_id}] iter={iteration}: {seq_result.details}")
            return seq_result
        
        # 检测 3: 响应重复
        resp_result = self._check_response_repeat(hist)
        if resp_result.is_loop:
            logger.warning(f"[LOOP] 响应重复 [{session_id}] iter={iteration}: {resp_result.details}")
            return resp_result
        
        # 检测 4: 停滞检测
        stag_result = self._check_stagnation(hist)
        if stag_result.is_loop:
            logger.warning(f"[LOOP] 停滞检测 [{session_id}] iter={iteration}: {stag_result.details}")
            return stag_result
        
        return LoopDetectionResult(is_loop=False)
    
    def _results_are_similar(self, results_a: List[str], results_b: List[str]) -> bool:
        """比较两轮的工具结果是否高度相似（无新信息）"""
        if not results_a or not results_b:
            return False
        if len(results_a) != len(results_b):
            return False
        for a, b in zip(results_a, results_b):
            sim = SequenceMatcher(None, a, b).ratio()
            if sim < self.result_similarity_threshold:
                return False
        return True
    
    def _check_parameter_repeat(self, hist: List[LoopHistory]) -> LoopDetectionResult:
        """检测同一工具+相同参数被反复调用，且结果无变化
        
        关键改进：不只计数，还比较结果是否有变化。
        如果结果每次都不一样（有新信息），不算循环。
        """
        if len(hist) < self.parameter_repeat_threshold:
            return LoopDetectionResult(is_loop=False)
        
        # 统计每个签名出现的轮次（带完整结果）
        sig_occurrences: Dict[str, List[tuple]] = {}  # sig -> [(tool_name, results, iteration)]
        
        for h in hist[-self.parameter_repeat_threshold - 1:]:
            for i, sig in enumerate(h.tool_signatures):
                name = h.tool_names[i] if i < len(h.tool_names) else "unknown"
                results = h.tool_results[i] if i < len(h.tool_results) else ""
                if sig not in sig_occurrences:
                    sig_occurrences[sig] = []
                sig_occurrences[sig].append((name, results, h.iteration))
        
        for sig, occurrences in sig_occurrences.items():
            if len(occurrences) >= self.parameter_repeat_threshold:
                # 检查最近两次的结果是否相似（无新信息）
                last_two = occurrences[-2:]
                if len(last_two) == 2:
                    results_similar = SequenceMatcher(None, last_two[0][1], last_two[1][1]).ratio()
                    if results_similar >= self.result_similarity_threshold:
                        tool_name = occurrences[0][0]
                        count = len(occurrences)
                        return LoopDetectionResult(
                            is_loop=True,
                            loop_type="parameter_repeat",
                            confidence=min(0.4 + count * 0.15, 0.95),
                            details=f"工具 `{tool_name}` 以相同参数调用 {count} 次，最近两次结果相似度 {results_similar:.2f}（无新信息）",
                            suggestion=f"工具 `{tool_name}` 反复执行相同操作但未获得新信息。建议换一种方式实现需求，或检查该工具是否能完成任务。",
                            iteration=hist[-1].iteration if hist else 0,
                        )
        
        return LoopDetectionResult(is_loop=False)
    
    def _check_tool_sequence_repeat(self, hist: List[LoopHistory]) -> LoopDetectionResult:
        """检测工具调用序列的周期性重复，且结果无变化"""
        if len(hist) < self.tool_sequence_window:
            return LoopDetectionResult(is_loop=False)
        
        recent = hist[-self.tool_sequence_window:]
        recent_sequences = [tuple(h.tool_names) for h in recent if h.tool_names]
        
        if len(recent_sequences) < 4:
            return LoopDetectionResult(is_loop=False)
        
        # 检测周期为 2 的重复：X, Y, X, Y（要求 pattern 中有变化，排除 X,X,X,X）
        for period in [2, 3]:
            if len(recent_sequences) >= period * 2:
                pattern = recent_sequences[-period:]
                previous = recent_sequences[-period * 2:-period]
                # FIX: 周期为2时，要求 pattern 不是全相同的工具（A,A,A,A 不算周期重复）
                if period == 2 and len(set(pattern)) == 1:
                    continue
                if pattern == previous:
                    # 额外检查：对应轮次的结果是否也相似
                    pattern_results = [recent[-period + i].tool_results for i in range(period)]
                    previous_results = [recent[-period * 2 + i].tool_results for i in range(period)]
                    all_similar = all(
                        self._results_are_similar(pr, cr)
                        for pr, cr in zip(previous_results, pattern_results)
                    )
                    if all_similar:
                        seq_str = " → ".join([",".join(s) for s in pattern])
                        return LoopDetectionResult(
                            is_loop=True,
                            loop_type="tool_sequence_repeat",
                            confidence=0.92,
                            details=f"检测到周期为 {period} 的工具序列重复，且结果无变化: {seq_str}",
                            suggestion="LLM 在工具调用中陷入了循环——反复执行相同的工具序列且未获得新信息。建议用户明确指定下一步操作，或简化任务目标。",
                            iteration=hist[-1].iteration if hist else 0,
                        )
        
        # 检测同一工具被调用超过 4 次（不同参数也算），且最近结果趋于停滞
        tool_name_counts: Dict[str, List[LoopHistory]] = {}
        for h in recent:
            for name in h.tool_names:
                if name not in tool_name_counts:
                    tool_name_counts[name] = []
                tool_name_counts[name].append(h)
        
        for name, rounds in tool_name_counts.items():
            if len(rounds) >= 4:
                # 检查最近两次调用该工具的结果是否相似
                tool_rounds = [h for h in rounds if name in h.tool_names]
                if len(tool_rounds) >= 2:
                    last = tool_rounds[-1]
                    second_last = tool_rounds[-2]
                    idx_last = last.tool_names.index(name)
                    idx_sl = second_last.tool_names.index(name)
                    if idx_last < len(last.tool_results) and idx_sl < len(second_last.tool_results):
                        sim = SequenceMatcher(None, last.tool_results[idx_last], second_last.tool_results[idx_sl]).ratio()
                        if sim >= self.result_similarity_threshold:
                            return LoopDetectionResult(
                                is_loop=True,
                                loop_type="tool_sequence_repeat",
                                confidence=0.85,
                                details=f"工具 `{name}` 在最近 {self.tool_sequence_window} 轮中被调用 {len(rounds)} 次，最近两次结果相似度 {sim:.2f}",
                                suggestion=f"工具 `{name}` 被频繁调用且结果无变化。建议检查是否有更高效的方式完成任务，或确认该工具返回的结果是否有用。",
                                iteration=hist[-1].iteration if hist else 0,
                            )
        
        return LoopDetectionResult(is_loop=False)
    
    def _check_response_repeat(self, hist: List[LoopHistory]) -> LoopDetectionResult:
        """检测 LLM 响应内容的重复"""
        if len(hist) < self.response_repeat_window + 1:
            return LoopDetectionResult(is_loop=False)
        
        tool_rounds = [h for h in hist if h.tool_names]
        if len(tool_rounds) < self.response_repeat_window + 1:
            return LoopDetectionResult(is_loop=False)
        
        recent = tool_rounds[-self.response_repeat_window - 1:]
        
        similarities = []
        for i in range(len(recent) - 1):
            for j in range(i + 1, len(recent)):
                sim = SequenceMatcher(None, recent[i].content, recent[j].content).ratio()
                similarities.append(sim)
        
        if not similarities:
            return LoopDetectionResult(is_loop=False)
        
        avg_sim = sum(similarities) / len(similarities)
        max_sim = max(similarities)
        
        if max_sim >= self.response_repeat_threshold and avg_sim >= 0.70:
            return LoopDetectionResult(
                is_loop=True,
                loop_type="response_repeat",
                confidence=max_sim,
                details=f"LLM 在最近 {self.response_repeat_window} 轮工具调用后的响应相似度: 最大={max_sim:.2f}, 平均={avg_sim:.2f}",
                suggestion="LLM 似乎在重复相似的推理和回答。建议用户提供更明确的指令，或检查任务是否可以通过其他方式完成。",
                iteration=hist[-1].iteration if hist else 0,
            )
        
        return LoopDetectionResult(is_loop=False)
    
    def _check_stagnation(self, hist: List[LoopHistory]) -> LoopDetectionResult:
        """停滞检测：多轮后工具结果没有新信息"""
        if len(hist) < self.stagnation_window + 1:
            return LoopDetectionResult(is_loop=False)
        
        tool_rounds = [h for h in hist if h.tool_names]
        if len(tool_rounds) < self.stagnation_window + 1:
            return LoopDetectionResult(is_loop=False)
        
        recent = tool_rounds[-self.stagnation_window:]
        
        similarities = []
        for i in range(len(recent) - 1):
            sim = SequenceMatcher(None, recent[i].tool_results_summary(), recent[i + 1].tool_results_summary()).ratio()
            similarities.append(sim)
        
        if not similarities:
            return LoopDetectionResult(is_loop=False)
        
        avg_sim = sum(similarities) / len(similarities)
        
        if avg_sim >= self.stagnation_similarity:
            seq_changed = any(
                recent[i].tool_names != recent[i + 1].tool_names
                for i in range(len(recent) - 1)
            )
            
            if not seq_changed:
                return LoopDetectionResult(
                    is_loop=True,
                    loop_type="stagnation",
                    confidence=0.95,
                    details=f"连续 {self.stagnation_window} 轮调用相同工具序列，且结果高度相似（相似度={avg_sim:.2f}）",
                    suggestion="工具执行陷入了停滞——相同操作反复产生相同结果。建议用户换一种思路或检查数据源是否有问题。",
                    iteration=hist[-1].iteration if hist else 0,
                )
            else:
                return LoopDetectionResult(
                    is_loop=True,
                    loop_type="stagnation",
                    confidence=0.75,
                    details=f"连续 {self.stagnation_window} 轮工具结果高度相似（相似度={avg_sim:.2f}），但工具序列有变化",
                    suggestion="工具结果没有产生新信息，可能在做冗余操作。建议用户确认任务目标是否可实现。",
                    iteration=hist[-1].iteration if hist else 0,
                )
        
        return LoopDetectionResult(is_loop=False)
    
    def get_session_stats(self, session_id: str) -> Dict:
        hist = self._get_history(session_id)
        if not hist:
            return {"total_iterations": 0, "loops_detected": 0}
        return {
            "total_iterations": len(hist),
            "loops_detected": 0,
            "last_iteration": hist[-1].iteration,
            "tool_calls_total": sum(len(h.tool_names) for h in hist),
        }
