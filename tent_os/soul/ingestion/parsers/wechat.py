"""微信聊天记录解析器

支持微信导出的 txt 格式（最常见）：
  昵称 2024-01-15 14:32:10
  消息内容
  
  昵称 2024-01-15 14:33:05
  消息内容

也支持 HTML 导出格式（简化处理，提取文本节点）
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from tent_os.soul.ingestion.parsers.base import BaseParser, ParsedMessage, ParseResult
from tent_os.logging_config import get_logger

logger = get_logger()


class WeChatParser(BaseParser):
    """微信聊天记录解析器"""
    
    NAME = "wechat"
    SUPPORTED_EXTENSIONS = [".txt", ".html", ".htm"]
    
    # 微信 txt 导出格式的正则
    # 格式1: 昵称 2024-01-15 14:32:10
    # 格式2: 昵称 2024/01/15 14:32:10
    # 格式3: 2024-01-15 14:32:10 昵称
    # 格式4: [昵称] 2024-01-15 14:32:10
    PATTERNS = [
        # 标准格式: 昵称 YYYY-MM-DD HH:MM:SS
        re.compile(r"^(.*?)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})$"),
        # 斜杠格式: 昵称 YYYY/MM/DD HH:MM:SS
        re.compile(r"^(.*?)\s+(\d{4}/\d{2}/\d{2})\s+(\d{2}:\d{2}:\d{2})$"),
        # 方括号格式: [昵称] YYYY-MM-DD HH:MM:SS
        re.compile(r"^\[(.*?)\]\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})$"),
        # 时间在前: YYYY-MM-DD HH:MM:SS 昵称
        re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(.*?)$"),
        # 只有时间: HH:MM:SS 昵称（同一天的后续消息）
        re.compile(r"^(\d{2}:\d{2}:\d{2})\s+(.*?)$"),
    ]
    
    # 系统消息过滤
    SYSTEM_KEYWORDS = [
        "撤回了一条消息", "消息已发出但被对方拒收", "开启了朋友验证",
        "拍了拍", "加入了群聊", "移出了群聊", "修改群名为", "系统提示",
        "以下是", "的聊天记录", "微信团队", "微信安全中心",
    ]
    
    def parse(self, file_path: Path, target_speaker: Optional[str] = None) -> ParseResult:
        encoding = self._detect_encoding(file_path)
        try:
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                text = f.read()
        except Exception as e:
            logger.error(f"[WeChatParser] 读取文件失败 {file_path}: {e}")
            return ParseResult(messages=[], warnings=[f"读取文件失败: {e}"])
        
        return self.parse_text(text, filename=file_path.name, target_speaker=target_speaker)
    
    def parse_text(self, text: str, filename: str = "", target_speaker: Optional[str] = None) -> ParseResult:
        lines = text.split("\n")
        messages: List[ParsedMessage] = []
        speakers_set = set()
        warnings = []
        
        current_speaker = ""
        current_timestamp: Optional[datetime] = None
        current_content_lines: List[str] = []
        current_date = None
        
        total_lines = len(lines)
        skipped = 0
        
        def _flush_message():
            nonlocal messages, current_speaker, current_timestamp, current_content_lines
            if current_speaker and current_content_lines:
                content = "\n".join(current_content_lines).strip()
                if content and len(content) > 0:
                    # 过滤系统消息
                    if any(kw in content for kw in self.SYSTEM_KEYWORDS):
                        return
                    
                    # 过滤转账、红包等纯数字/符号消息
                    if re.match(r"^\s*[￥¥$€]?\s*[\d.,]+\s*$", content):
                        return
                    
                    msg = ParsedMessage(
                        content=content,
                        speaker=current_speaker,
                        timestamp=current_timestamp,
                        msg_type="chat",
                        metadata={
                            "source": "wechat",
                            "filename": filename,
                            "parser": self.NAME,
                        },
                        raw_text=content,
                    )
                    
                    # 如果指定了 target_speaker，只保留匹配的消息
                    if target_speaker:
                        # 支持模糊匹配：target_speaker 是昵称的一部分即可
                        if target_speaker.lower() not in current_speaker.lower() and \
                           current_speaker.lower() not in target_speaker.lower():
                            return
                    
                    messages.append(msg)
                    speakers_set.add(current_speaker)
            
            current_speaker = ""
            current_timestamp = None
            current_content_lines = []
        
        for line in lines:
            line = line.rstrip("\r")
            
            # 跳过空行
            if not line.strip():
                # 空行可能分隔两条消息
                if current_speaker and current_content_lines:
                    _flush_message()
                continue
            
            # 跳过文件头
            if line.strip().startswith("以下是") and "聊天记录" in line:
                skipped += 1
                continue
            
            # 尝试匹配消息头
            header_match = self._match_header(line, current_date)
            
            if header_match:
                # 先 flush 上一条消息
                _flush_message()
                
                speaker, timestamp, date = header_match
                current_speaker = speaker
                current_timestamp = timestamp
                if date:
                    current_date = date
            else:
                # 这是消息内容
                current_content_lines.append(line)
        
        # 最后 flush
        _flush_message()
        
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
            speakers=sorted(list(speakers_set)),
            earliest_time=earliest,
            latest_time=latest,
            warnings=warnings,
        )
    
    def _match_header(self, line: str, current_date: Optional[datetime]) -> Optional[Tuple[str, Optional[datetime], Optional[datetime]]]:
        """匹配消息头，返回 (speaker, timestamp, date)
        
        Returns:
            (speaker, timestamp, date) 或 None
        """
        line = line.strip()
        
        # 尝试模式1: 昵称 YYYY-MM-DD HH:MM:SS
        m = self.PATTERNS[0].match(line)
        if m:
            speaker = m.group(1).strip()
            date_str = m.group(2)
            time_str = m.group(3)
            ts = self._parse_datetime(date_str, time_str)
            return (speaker, ts, ts)
        
        # 尝试模式2: 昵称 YYYY/MM/DD HH:MM:SS
        m = self.PATTERNS[1].match(line)
        if m:
            speaker = m.group(1).strip()
            date_str = m.group(2).replace("/", "-")
            time_str = m.group(3)
            ts = self._parse_datetime(date_str, time_str)
            return (speaker, ts, ts)
        
        # 尝试模式3: [昵称] YYYY-MM-DD HH:MM:SS
        m = self.PATTERNS[2].match(line)
        if m:
            speaker = m.group(1).strip()
            date_str = m.group(2)
            time_str = m.group(3)
            ts = self._parse_datetime(date_str, time_str)
            return (speaker, ts, ts)
        
        # 尝试模式4: YYYY-MM-DD HH:MM:SS 昵称
        m = self.PATTERNS[3].match(line)
        if m:
            date_str = m.group(1)
            time_str = m.group(2)
            speaker = m.group(3).strip()
            ts = self._parse_datetime(date_str, time_str)
            return (speaker, ts, ts)
        
        # 尝试模式5: HH:MM:SS 昵称（同一天）
        if current_date:
            m = self.PATTERNS[4].match(line)
            if m:
                time_str = m.group(1)
                speaker = m.group(2).strip()
                date_str = current_date.strftime("%Y-%m-%d")
                ts = self._parse_datetime(date_str, time_str)
                return (speaker, ts, current_date)
        
        return None
    
    def _parse_datetime(self, date_str: str, time_str: str) -> Optional[datetime]:
        """解析日期时间字符串"""
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            except ValueError:
                return None
