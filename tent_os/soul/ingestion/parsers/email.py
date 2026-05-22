"""邮件解析器

支持 .eml（单封邮件）和 .mbox（邮件集合）格式
使用 Python 标准库 email 模块解析
"""

import email
import email.policy
import mailbox
import re
from datetime import datetime
from email.message import EmailMessage
from email.utils import parsedate_to_datetime, getaddresses
from pathlib import Path
from typing import List, Optional

from tent_os.soul.ingestion.parsers.base import BaseParser, ParsedMessage, ParseResult
from tent_os.logging_config import get_logger

logger = get_logger()


class EmailParser(BaseParser):
    """邮件解析器"""
    
    NAME = "email"
    SUPPORTED_EXTENSIONS = [".eml", ".mbox"]
    
    def parse(self, file_path: Path, target_speaker: Optional[str] = None) -> ParseResult:
        suffix = file_path.suffix.lower()
        
        if suffix == ".eml":
            try:
                with open(file_path, "rb") as f:
                    msg = email.message_from_binary_file(f, policy=email.policy.default)
                return self._parse_single_email(msg, filename=file_path.name, target_speaker=target_speaker)
            except Exception as e:
                logger.error(f"[EmailParser] 解析 .eml 失败 {file_path}: {e}")
                return ParseResult(messages=[], warnings=[f"解析 .eml 失败: {e}"])
        
        elif suffix == ".mbox":
            return self._parse_mbox(file_path, target_speaker=target_speaker)
        
        else:
            return ParseResult(messages=[], warnings=[f"不支持的格式: {suffix}"])
    
    def parse_text(self, text: str, filename: str = "", target_speaker: Optional[str] = None) -> ParseResult:
        """Email 不支持纯文本直接解析，尝试按 .eml 格式解析"""
        try:
            msg = email.message_from_string(text, policy=email.policy.default)
            return self._parse_single_email(msg, filename=filename, target_speaker=target_speaker)
        except Exception as e:
            logger.error(f"[EmailParser] 从文本解析邮件失败: {e}")
            return ParseResult(messages=[], warnings=[f"从文本解析邮件失败: {e}"])
    
    def _parse_mbox(self, file_path: Path, target_speaker: Optional[str] = None) -> ParseResult:
        """解析 mbox 文件"""
        messages: List[ParsedMessage] = []
        warnings = []
        total = 0
        
        try:
            mbox = mailbox.mbox(str(file_path))
            for msg in mbox:
                total += 1
                try:
                    result = self._parse_single_email(msg, filename=file_path.name, target_speaker=target_speaker)
                    messages.extend(result.messages)
                except Exception as e:
                    warnings.append(f"解析第 {total} 封邮件失败: {e}")
            mbox.close()
        except Exception as e:
            logger.error(f"[EmailParser] 解析 mbox 失败 {file_path}: {e}")
            warnings.append(f"解析 mbox 失败: {e}")
        
        speakers = sorted(list(set(m.speaker for m in messages if m.speaker)))
        
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
            total_lines=total,
            parsed_messages=len(messages),
            skipped_lines=0,
            speakers=speakers,
            earliest_time=earliest,
            latest_time=latest,
            warnings=warnings,
        )
    
    def _parse_single_email(self, msg: EmailMessage, filename: str = "", target_speaker: Optional[str] = None) -> ParseResult:
        """解析单封邮件"""
        
        # 提取发件人
        from_addr = msg.get("From", "")
        from_name = ""
        from_email = ""
        if from_addr:
            addresses = getaddresses([from_addr])
            if addresses:
                from_name, from_email = addresses[0]
        
        speaker = from_name or from_email or "未知发件人"
        
        # 提取时间
        timestamp = None
        date_header = msg.get("Date")
        if date_header:
            try:
                timestamp = parsedate_to_datetime(date_header)
            except Exception:
                pass
        
        # 提取主题
        subject = msg.get("Subject", "") or ""
        
        # 提取正文
        body = self._extract_body(msg)
        
        # 过滤目标说话者
        if target_speaker:
            # 检查发件人是否匹配
            target_lower = target_speaker.lower()
            if target_lower not in speaker.lower() and target_lower not in from_email.lower():
                # 不匹配，返回空
                return ParseResult(messages=[])
        
        if not body or not body.strip():
            return ParseResult(messages=[])
        
        # 构建内容：主题 + 正文
        content = body.strip()
        if subject:
            content = f"【主题：{subject}】\n\n{content}"
        
        parsed_msg = ParsedMessage(
            content=content,
            speaker=speaker,
            timestamp=timestamp,
            msg_type="email",
            metadata={
                "source": "email",
                "filename": filename,
                "from_email": from_email,
                "from_name": from_name,
                "subject": subject,
                "parser": self.NAME,
            },
            raw_text=body,
        )
        
        return ParseResult(
            messages=[parsed_msg],
            parsed_messages=1,
            speakers=[speaker] if speaker else [],
            earliest_time=timestamp,
            latest_time=timestamp,
        )
    
    def _extract_body(self, msg: EmailMessage) -> str:
        """提取邮件正文（优先 text/plain，其次 text/html 转纯文本）"""
        body_parts = []
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        text = part.get_content()
                        if text:
                            body_parts.append(text)
                    except Exception:
                        pass
                elif content_type == "text/html" and not body_parts:
                    # 如果没有 text/plain，尝试提取 html
                    try:
                        html = part.get_content()
                        if html:
                            body_parts.append(self._html_to_text(html))
                    except Exception:
                        pass
        else:
            content_type = msg.get_content_type()
            try:
                text = msg.get_content()
                if text:
                    if content_type == "text/html":
                        body_parts.append(self._html_to_text(text))
                    else:
                        body_parts.append(text)
            except Exception:
                pass
        
        return "\n\n".join(body_parts)
    
    def _html_to_text(self, html: str) -> str:
        """简单 HTML 转纯文本"""
        # 移除 script 和 style
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        
        # 替换常见标签为换行
        html = re.sub(r"<br\s*/?>|</p>|</div>|</h[1-6]>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"<li>", "\n- ", html, flags=re.IGNORECASE)
        
        # 移除所有标签
        html = re.sub(r"<[^>]+>", "", html)
        
        # 解码 HTML 实体
        import html as html_module
        html = html_module.unescape(html)
        
        # 清理多余空白
        lines = [line.strip() for line in html.split("\n")]
        html = "\n".join(line for line in lines if line)
        
        return html
