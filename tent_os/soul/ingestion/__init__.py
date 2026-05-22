"""外部语料导入管道

将用户生前的外部数据（微信聊天记录、邮件、日记等）解析、提取人格特征，
并导入到 Tent OS 的记忆库和人格画像系统中。

使用流程：
1. 用户上传原始文件（微信导出 txt、.eml 邮件、日记 markdown）
2. 解析器将文件转为结构化消息/段落
3. 人格提取器调用 LLM 分析语料，提取人格特征
4. 记忆导入器将语料存入 TieredMemoryStore（L0/L1/L2）
5. 人格画像增量更新或全量重建
"""

from tent_os.soul.ingestion.pipeline import ExternalIngestionPipeline
from tent_os.soul.ingestion.parsers.wechat import WeChatParser
from tent_os.soul.ingestion.parsers.email import EmailParser
from tent_os.soul.ingestion.parsers.diary import DiaryParser

__all__ = [
    "ExternalIngestionPipeline",
    "WeChatParser",
    "EmailParser",
    "DiaryParser",
]