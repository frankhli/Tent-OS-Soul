"""日记/备忘录解析器

支持多种日记格式：
- 纯文本：每段以日期开头
- Markdown：# 日期 或 ## 日期 作为标题
- 结构化：日期 + 标题 + 正文

日期识别模式：
- 2024-01-15
- 2024/01/15
- 2024年01月15日
- Jan 15, 2024
- 15 Jan 2024
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from tent_os.soul.ingestion.parsers.base import BaseParser, ParsedMessage, ParseResult
from tent_os.logging_config import get_logger

logger = get_logger()


class DiaryParser(BaseParser):
    """日记/备忘录解析器"""
    
    NAME = "diary"
    SUPPORTED_EXTENSIONS = [".txt", ".md", ".markdown"]
    
    # 日期识别正则（从行首匹配）
    DATE_PATTERNS = [
        # YYYY-MM-DD
        (re.compile(r"^(?:#+\s*)?(\d{4}-\d{2}-\d{2})"), "%Y-%m-%d"),
        # YYYY/MM/DD
        (re.compile(r"^(?:#+\s*)?(\d{4}/\d{2}/\d{2})"), "%Y/%m/%d"),
        # YYYY年MM月DD日
        (re.compile(r"^(?:#+\s*)?(\d{4}年\d{1,2}月\d{1,2}日)"), "%Y年%m月%d日"),
        # YYYY.MM.DD
        (re.compile(r"^(?:#+\s*)?(\d{4}\.\d{2}\.\d{2})"), "%Y.%m.%d"),
        # Jan 15, 2024 / January 15, 2024
        (re.compile(r"^(?:#+\s*)?([A-Za-z]+\s+\d{1,2},?\s+\d{4})"), "%B %d, %Y"),
        # 15 Jan 2024
        (re.compile(r"^(?:#+\s*)?(\d{1,2}\s+[A-Za-z]+\s+\d{4})"), "%d %B %Y"),
    ]
    
    # 标题识别（markdown 标题或日期后的文字）
    TITLE_PATTERN = re.compile(r"^(?:#+\s*)?\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}[日]?\s*(.*)$")
    
    def parse(self, file_path: Path, target_speaker: Optional[str] = None) -> ParseResult:
        encoding = self._detect_encoding(file_path)
        try:
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                text = f.read()
        except Exception as e:
            logger.error(f"[DiaryParser] 读取文件失败 {file_path}: {e}")
            return ParseResult(messages=[], warnings=[f"读取文件失败: {e}"])
        
        return self.parse_text(text, filename=file_path.name, target_speaker=target_speaker)
    
    def parse_text(self, text: str, filename: str = "", target_speaker: Optional[str] = None) -> ParseResult:
        lines = text.split("\n")
        messages: List[ParsedMessage] = []
        warnings = []
        
        total_lines = len(lines)
        skipped = 0
        
        current_date: Optional[datetime] = None
        current_title = ""
        current_content_lines: List[str] = []
        
        def _flush_entry():
            nonlocal messages, current_date, current_title, current_content_lines
            if current_date and current_content_lines:
                content = "\n".join(current_content_lines).strip()
                if content and len(content) > 10:  # 过滤太短的内容
                    # 构建标题前缀
                    full_content = content
                    if current_title:
                        full_content = f"【{current_title}】\n\n{content}"
                    
                    msg = ParsedMessage(
                        content=full_content,
                        speaker=target_speaker or "",  # 日记没有说话者，用 target_speaker 或空
                        timestamp=current_date,
                        msg_type="diary",
                        metadata={
                            "source": "diary",
                            "filename": filename,
                            "title": current_title,
                            "parser": self.NAME,
                        },
                        raw_text=content,
                    )
                    messages.append(msg)
            
            current_date = None
            current_title = ""
            current_content_lines = []
        
        for line in lines:
            line = line.rstrip("\r")
            
            # 尝试识别日期行
            date_match = self._match_date_line(line)
            
            if date_match:
                # 先 flush 上一条
                _flush_entry()
                
                current_date = date_match[0]
                current_title = date_match[1] or ""
            else:
                # 普通内容行
                if line.strip():
                    current_content_lines.append(line)
        
        # 最后 flush
        _flush_entry()
        
        # 如果没识别到任何日期，把整个文件当作一篇日记
        if not messages and text.strip():
            # 尝试从文件名提取日期
            file_date = self._extract_date_from_filename(filename)
            
            msg = ParsedMessage(
                content=text.strip(),
                speaker=target_speaker or "",
                timestamp=file_date,
                msg_type="diary",
                metadata={
                    "source": "diary",
                    "filename": filename,
                    "title": filename,
                    "parser": self.NAME,
                    "note": "未识别到日期格式，整文件作为一篇日记",
                },
                raw_text=text.strip(),
            )
            messages.append(msg)
        
        # 排序
        messages.sort(key=lambda m: m.timestamp or datetime.min)
        
        # 时间范围
        earliest = None
        latest = None
        for m in messages:
            if m.timestamp:
                if earliest is None or m.timestamp < earliest:
                    earliest = m.timestamp
                if latest is None or m.timestamp > latest:
                    latest = m.timestamp
        
        return ParseResult(
            messages=messages,
            total_lines=total_lines,
            parsed_messages=len(messages),
            skipped_lines=skipped,
            speakers=[],
            earliest_time=earliest,
            latest_time=latest,
            warnings=warnings,
        )
    
    def _match_date_line(self, line: str) -> Optional[Tuple[Optional[datetime], str]]:
        """匹配日期行，返回 (datetime, title)"""
        line = line.strip()
        
        for pattern, fmt in self.DATE_PATTERNS:
            m = pattern.match(line)
            if m:
                date_str = m.group(1)
                try:
                    dt = datetime.strptime(date_str, fmt)
                    # 提取标题（日期后的文字）
                    title = line[m.end():].strip()
                    title = title.lstrip("-–—:：").strip()
                    return (dt, title)
                except ValueError:
                    continue
        
        return None
    
    def _extract_date_from_filename(self, filename: str) -> Optional[datetime]:
        """从文件名提取日期"""
        # 尝试匹配文件名中的日期
        patterns = [
            (re.compile(r"(\d{4}-\d{2}-\d{2})"), "%Y-%m-%d"),
            (re.compile(r"(\d{4}\d{2}\d{2})"), "%Y%m%d"),
        ]
        for pattern, fmt in patterns:
            m = pattern.search(filename)
            if m:
                try:
                    return datetime.strptime(m.group(1), fmt)
                except ValueError:
                    continue
        return None
