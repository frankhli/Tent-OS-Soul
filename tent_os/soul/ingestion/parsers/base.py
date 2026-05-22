"""外部语料解析器抽象基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path


@dataclass
class ParsedMessage:
    """一条解析后的消息/段落"""
    
    # 内容
    content: str
    
    # 说话者/作者（如果可识别）
    speaker: str = ""
    
    # 时间戳（如果可识别）
    timestamp: Optional[datetime] = None
    
    # 消息类型：chat / email / diary / note
    msg_type: str = "chat"
    
    # 元数据：原始文件名、位置、主题等
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 原始文本（用于调试和去重）
    raw_text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "speaker": self.speaker,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "msg_type": self.msg_type,
            "metadata": self.metadata,
        }


@dataclass
class ParseResult:
    """解析结果"""
    
    # 解析出的所有消息
    messages: List[ParsedMessage]
    
    # 解析统计
    total_lines: int = 0
    parsed_messages: int = 0
    skipped_lines: int = 0
    
    # 解析器识别的说话者列表
    speakers: List[str] = field(default_factory=list)
    
    # 时间范围
    earliest_time: Optional[datetime] = None
    latest_time: Optional[datetime] = None
    
    # 解析过程中的警告
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_messages": len(self.messages),
            "total_lines": self.total_lines,
            "parsed_messages": self.parsed_messages,
            "skipped_lines": self.skipped_lines,
            "speakers": self.speakers,
            "time_range": {
                "earliest": self.earliest_time.isoformat() if self.earliest_time else None,
                "latest": self.latest_time.isoformat() if self.latest_time else None,
            },
            "warnings": self.warnings,
        }


class BaseParser(ABC):
    """语料解析器抽象基类"""
    
    # 支持的文件扩展名
    SUPPORTED_EXTENSIONS: List[str] = []
    
    # 解析器名称
    NAME: str = "base"
    
    @abstractmethod
    def parse(self, file_path: Path, target_speaker: Optional[str] = None) -> ParseResult:
        """解析文件
        
        Args:
            file_path: 文件路径
            target_speaker: 如果指定，只保留该说话者的消息（用于聚焦逝者本人的语料）
        
        Returns:
            ParseResult
        """
        pass
    
    @abstractmethod
    def parse_text(self, text: str, filename: str = "", target_speaker: Optional[str] = None) -> ParseResult:
        """直接解析文本内容
        
        Args:
            text: 原始文本
            filename: 原始文件名（用于元数据）
            target_speaker: 如果指定，只保留该说话者的消息
        
        Returns:
            ParseResult
        """
        pass
    
    def can_parse(self, file_path: Path) -> bool:
        """检查是否能解析该文件"""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS
    
    def _detect_encoding(self, file_path: Path) -> str:
        """检测文件编码"""
        # 尝试常见编码
        for encoding in ["utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030", "latin-1"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    f.read(1024)
                return encoding
            except (UnicodeDecodeError, UnicodeError):
                continue
        return "utf-8"  # 兜底
