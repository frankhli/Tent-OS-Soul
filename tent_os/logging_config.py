"""Tent OS 统一日志配置

原则：
- 所有进程使用统一的日志格式
- 支持结构化输出（JSON 或人类可读）
- 支持 trace_id 追踪跨进程消息流
- 分级：DEBUG < INFO < WARNING < ERROR
- 进程名标识：memory | governance | scheduler | api | webhook
"""

import logging
import sys
import os
from typing import Optional


class TentLogFormatter(logging.Formatter):
    """Tent OS 统一日志格式
    
    格式: [timestamp] [LEVEL] [process] [trace_id] message
    """
    
    def __init__(self, process_name: str = "tent-os"):
        super().__init__()
        self.process_name = process_name
    
    def format(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, "trace_id", "-")
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        return (
            f"[{timestamp}] [{record.levelname:8s}] [{self.process_name:12s}] "
            f"[{trace_id:16s}] {record.getMessage()}"
        )


class JSONLogFormatter(logging.Formatter):
    """JSON 结构化日志格式——供日志收集系统解析"""
    
    def __init__(self, process_name: str = "tent-os"):
        super().__init__()
        self.process_name = process_name
    
    def format(self, record: logging.LogRecord) -> str:
        import json
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "process": self.process_name,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(
    process_name: str = "tent-os",
    level: str = "INFO",
    json_format: bool = False,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """配置 Tent OS 日志
    
    Args:
        process_name: 进程标识，如 "memory", "governance", "scheduler", "api"
        level: 日志级别 DEBUG/INFO/WARNING/ERROR
        json_format: 是否使用 JSON 格式（生产环境推荐）
        log_file: 日志文件路径（为 None 则使用环境变量 TENT_LOG_FILE 或默认 /tmp/tent_os.log）

    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger("tent_os")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # 避免重复添加 handler
    if logger.handlers:
        logger.handlers.clear()
    
    if json_format or os.environ.get("TENT_LOG_JSON", "0") == "1":
        formatter = JSONLogFormatter(process_name)
    else:
        formatter = TentLogFormatter(process_name)
    
    # stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)
    
    # file handler（所有进程写入同一文件，供前端日志 UI 读取）
    file_path = log_file or os.environ.get("TENT_LOG_FILE", "/tmp/tent_os.log")
    if file_path:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            file_path, maxBytes=10*1024*1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # 确保子 logger 也使用这个 handler
    logger.propagate = False
    
    return logger


def get_logger(name: str = "tent_os") -> logging.Logger:
    """获取 Tent OS 日志记录器"""
    return logging.getLogger(name)


def log_with_trace(
    logger: logging.Logger,
    level: str,
    message: str,
    trace_id: Optional[str] = None,
    extra: Optional[dict] = None
):
    """带 trace_id 的日志记录
    
    用于追踪跨进程消息流：
    - governance.request → memory.inject → governance.resume → scheduler.submit → governance.response
    """
    extra_dict = extra or {}
    if trace_id:
        extra_dict["trace_id"] = trace_id
    
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(message, extra=extra_dict)
