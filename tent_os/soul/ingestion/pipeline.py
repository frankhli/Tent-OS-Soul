"""外部语料导入统一管道

串联解析器 → 记忆导入 → 人格提取 → 人格画像更新
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from tent_os.soul.ingestion.parsers.base import BaseParser, ParseResult
from tent_os.soul.ingestion.parsers.wechat import WeChatParser
from tent_os.soul.ingestion.parsers.email import EmailParser
from tent_os.soul.ingestion.parsers.diary import DiaryParser
from tent_os.soul.ingestion.persona_extractor import ExternalPersonaExtractor
from tent_os.soul.ingestion.memory_importer import ExternalMemoryImporter
from tent_os.soul.persona_profiler import OralStyleAnalyzer
from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class IngestionResult:
    """导入结果"""
    
    status: str  # "success" | "partial" | "failed"
    
    # 解析阶段
    parse_result: Optional[ParseResult] = None
    parser_used: str = ""
    
    # 记忆导入阶段
    memory_inserted: int = 0
    memory_skipped: int = 0
    memory_failed: int = 0
    memory_errors: List[str] = field(default_factory=list)
    
    # 人格提取阶段
    persona_extracted: bool = False
    persona_fields_updated: int = 0
    persona_analysis: Dict[str, Any] = field(default_factory=dict)
    
    # 画像更新阶段
    profile_updated: bool = False
    profile_rebuilt: bool = False
    
    # 时间
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    
    # 警告
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "parser_used": self.parser_used,
            "parse_summary": self.parse_result.to_dict() if self.parse_result else None,
            "memory": {
                "inserted": self.memory_inserted,
                "skipped": self.memory_skipped,
                "failed": self.memory_failed,
                "errors": self.memory_errors,
            },
            "persona": {
                "extracted": self.persona_extracted,
                "fields_updated": self.persona_fields_updated,
                "analysis_summary": {k: v for k, v in (self.persona_analysis or {}).items() 
                                     if k in ["confidence", "language_style", "catchphrases", "core_values"]},
            },
            "profile": {
                "updated": self.profile_updated,
                "rebuilt": self.profile_rebuilt,
            },
            "timing": {
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "duration_seconds": round(self.duration_seconds, 2),
            },
            "warnings": self.warnings,
        }


class ExternalIngestionPipeline:
    """外部语料导入管道"""
    
    # 注册所有解析器
    PARSERS: List[type] = [WeChatParser, EmailParser, DiaryParser]
    
    def __init__(self, memory_store=None, persona_profiler=None,
                 embedding_client=None, llm=None):
        self.memory_store = memory_store
        self.persona_profiler = persona_profiler
        self.embedding_client = embedding_client
        self.llm = llm
        
        self._memory_importer = ExternalMemoryImporter(
            memory_store=memory_store,
            embedding_client=embedding_client,
        )
        self._persona_extractor = ExternalPersonaExtractor(llm=llm)
    
    async def ingest_file(self, file_path: str, user_id: str,
                          source_type: Optional[str] = None,
                          target_speaker: Optional[str] = None,
                          update_mode: str = "incremental") -> IngestionResult:
        """导入单个文件
        
        Args:
            file_path: 文件路径
            user_id: 用户ID
            source_type: 强制指定来源类型（wechat/email/diary），如果为 None 则自动检测
            target_speaker: 如果指定，只保留该说话者的消息（用于聚焦逝者本人的语料）
            update_mode: "incremental"（增量更新人格画像）或 "rebuild"（全量重建）
        
        Returns:
            IngestionResult
        """
        start_time = time.time()
        result = IngestionResult(
            status="failed",
            started_at=datetime.now().isoformat(),
        )
        
        path = Path(file_path)
        if not path.exists():
            result.status = "failed"
            result.warnings.append(f"文件不存在: {file_path}")
            return result
        
        # === 阶段1: 自动检测解析器 ===
        parser = self._detect_parser(path, source_type)
        if not parser:
            result.status = "failed"
            result.warnings.append(f"无法找到合适的解析器: {path.suffix}")
            return result
        
        result.parser_used = parser.NAME
        
        # === 阶段2: 解析 ===
        try:
            parse_result = parser.parse(path, target_speaker=target_speaker)
            result.parse_result = parse_result
            
            if not parse_result.messages:
                result.status = "partial"
                result.warnings.append(f"解析成功但未提取到有效消息")
                return result
            
            logger.info(
                f"[IngestionPipeline] 解析完成 [{user_id}] 解析器={parser.NAME}, "
                f"消息数={len(parse_result.messages)}, 说话者={parse_result.speakers}"
            )
        except Exception as e:
            result.status = "failed"
            result.warnings.append(f"解析失败: {e}")
            logger.error(f"[IngestionPipeline] 解析失败 [{user_id}]: {e}")
            return result
        
        # === 阶段3: 导入记忆 ===
        messages_dict = [m.to_dict() for m in parse_result.messages]
        
        if self.memory_store:
            try:
                mem_result = await self._memory_importer.import_messages(
                    messages=messages_dict,
                    user_id=user_id,
                    source_type=parser.NAME,
                )
                result.memory_inserted = mem_result.get("inserted", 0)
                result.memory_skipped = mem_result.get("skipped", 0)
                result.memory_failed = mem_result.get("failed", 0)
                result.memory_errors = mem_result.get("errors", [])
            except Exception as e:
                result.warnings.append(f"记忆导入失败: {e}")
                logger.error(f"[IngestionPipeline] 记忆导入失败 [{user_id}]: {e}")
        else:
            result.warnings.append("记忆存储未配置，跳过记忆导入")
        
        # === 阶段4: 提取人格特征 ===
        if self.llm and parse_result.messages:
            try:
                persona_analysis = await self._persona_extractor.extract_from_messages(
                    messages=messages_dict,
                    user_id=user_id,
                    source_type=parser.NAME,
                )
                result.persona_extracted = bool(persona_analysis)
                result.persona_analysis = persona_analysis or {}
                
                # 统计更新的字段数
                if persona_analysis:
                    fields = [
                        "language_style", "sentence_pattern", "humor_style",
                        "decision_pattern", "thinking_depth", "argument_style",
                        "emotion_pattern", "stress_response", "joy_expression",
                        "value_conflicts", "relationship_style", "social_energy",
                        "growth_notes", "life_phases",
                    ]
                    result.persona_fields_updated = sum(
                        1 for f in fields 
                        if persona_analysis.get(f) and str(persona_analysis.get(f)).strip()
                    )
            except Exception as e:
                result.warnings.append(f"人格特征提取失败: {e}")
                logger.error(f"[IngestionPipeline] 人格提取失败 [{user_id}]: {e}")
        else:
            if not self.llm:
                result.warnings.append("LLM 未配置，跳过人格特征提取")
        
        # === 阶段4.5: 口语风格量化分析（从 target_speaker 的真实消息中统计）===
        oral_style_updated = False
        if self.persona_profiler and parse_result.messages:
            try:
                # 提取 target_speaker（死者本人）的消息文本
                speaker_texts = []
                for msg in parse_result.messages:
                    # 如果有 target_speaker，只分析他的消息；否则分析所有消息
                    if not target_speaker or (target_speaker.lower() in msg.speaker.lower() or msg.speaker.lower() in target_speaker.lower()):
                        speaker_texts.append(msg.content)
                
                if speaker_texts:
                    analyzer = OralStyleAnalyzer()
                    new_oral = analyzer.analyze(speaker_texts)
                    
                    if new_oral:
                        profile = self.persona_profiler.get_or_create_profile(user_id)
                        old_oral = profile.get_oral_style()
                        old_weight = old_oral.get("sample_sentences", 0)
                        new_weight = new_oral.get("sample_sentences", 0)
                        
                        merged_oral = analyzer.merge(old_oral, new_oral, old_weight, new_weight)
                        profile.oral_style = json.dumps(merged_oral, ensure_ascii=False)
                        self.persona_profiler._save_profile(profile)
                        oral_style_updated = True
                        
                        logger.info(
                            f"[IngestionPipeline] 口语风格已更新 [{user_id}] "
                            f"样本句={merged_oral.get('sample_sentences', 0)}, "
                            f"平均句长={merged_oral.get('avg_sentence_length', 0)}, "
                            f"口头禅={list(merged_oral.get('filler_words', {}).keys())[:3]}"
                        )
            except Exception as e:
                result.warnings.append(f"口语风格分析失败: {e}")
                logger.error(f"[IngestionPipeline] 口语风格分析失败 [{user_id}]: {e}")
        
        # === 阶段5: 更新人格画像 ===
        if self.persona_profiler and (result.persona_analysis or oral_style_updated):
            try:
                profile = self.persona_profiler.get_or_create_profile(user_id)
                
                if result.persona_analysis:
                    profile = self.persona_profiler._merge_analysis_into_profile(
                        profile, result.persona_analysis
                    )
                
                if update_mode == "rebuild":
                    self.persona_profiler._save_profile(profile)
                    result.profile_rebuilt = True
                    result.profile_updated = True
                    logger.info(f"[IngestionPipeline] 人格画像已全量重建 [{user_id}]")
                else:
                    self.persona_profiler._save_profile(profile)
                    result.profile_updated = True
                    logger.info(f"[IngestionPipeline] 人格画像已增量更新 [{user_id}]")
            except Exception as e:
                result.warnings.append(f"人格画像更新失败: {e}")
                logger.error(f"[IngestionPipeline] 画像更新失败 [{user_id}]: {e}")
        else:
            if not self.persona_profiler:
                result.warnings.append("人格画像引擎未配置，跳过画像更新")
        
        # === 完成 ===
        result.status = "success" if not result.warnings else "partial"
        result.completed_at = datetime.now().isoformat()
        result.duration_seconds = time.time() - start_time
        
        return result
    
    async def ingest_multiple(self, file_paths: List[str], user_id: str,
                              target_speaker: Optional[str] = None,
                              update_mode: str = "incremental") -> List[IngestionResult]:
        """批量导入多个文件"""
        results = []
        for path in file_paths:
            result = await self.ingest_file(
                file_path=path,
                user_id=user_id,
                target_speaker=target_speaker,
                update_mode=update_mode,
            )
            results.append(result)
        return results
    
    def _detect_parser(self, path: Path, source_type: Optional[str] = None) -> Optional[BaseParser]:
        """检测适用的解析器"""
        if source_type:
            # 强制指定
            for parser_cls in self.PARSERS:
                if parser_cls.NAME == source_type:
                    return parser_cls()
            return None
        
        # 自动检测
        for parser_cls in self.PARSERS:
            parser = parser_cls()
            if parser.can_parse(path):
                return parser
        
        return None
