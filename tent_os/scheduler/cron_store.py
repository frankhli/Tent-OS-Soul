"""Cron 持久化存储 —— SQLite -backed 定时任务调度

功能：
- CRUD 定时任务
- 持久化到 SQLite（和 scheduler 共用数据库）
- 支持 CRON 表达式解析
- 记录执行历史
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False

from tent_os.logging_config import get_logger

logger = get_logger()


class CronTask:
    """定时任务"""
    def __init__(self, task_id: str, name: str, cron: str, command: str,
                 enabled: bool = True, last_run: str = None, next_run: str = None,
                 created_at: str = None, run_count: int = 0):
        self.task_id = task_id
        self.name = name
        self.cron = cron
        self.command = command
        self.enabled = enabled
        self.last_run = last_run
        self.next_run = next_run
        self.created_at = created_at or datetime.now().isoformat()
        self.run_count = run_count


class CronStore:
    """Cron 任务持久化存储"""
    
    def __init__(self, db_path: str = "./tent_scheduler.db"):
        self.db_path = Path(db_path)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            # Cron 任务表
            db.execute("""
                CREATE TABLE IF NOT EXISTS cron_tasks (
                    task_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    cron TEXT NOT NULL,
                    command TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    last_run TEXT,
                    next_run TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    run_count INTEGER DEFAULT 0
                )
            """)
            # 执行历史表
            db.execute("""
                CREATE TABLE IF NOT EXISTS cron_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    result TEXT,
                    started_at TEXT DEFAULT (datetime('now')),
                    finished_at TEXT,
                    FOREIGN KEY (task_id) REFERENCES cron_tasks(task_id)
                )
            """)
            db.commit()
    
    def add_task(self, name: str, cron: str, command: str) -> CronTask:
        """添加定时任务"""
        task_id = f"cron_{uuid.uuid4().hex[:12]}"
        next_run = self._calc_next_run(cron)
        
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT INTO cron_tasks (task_id, name, cron, command, next_run) VALUES (?, ?, ?, ?, ?)",
                (task_id, name, cron, command, next_run)
            )
            db.commit()
        
        logger.info(f"[CRON] 添加任务: {name} ({cron})")
        return CronTask(task_id, name, cron, command, next_run=next_run)
    
    def delete_task(self, task_id: str) -> bool:
        """删除定时任务"""
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute("DELETE FROM cron_tasks WHERE task_id = ?", (task_id,))
            db.commit()
            return cursor.rowcount > 0
    
    def update_task(self, task_id: str, **kwargs) -> bool:
        """更新任务字段"""
        allowed = {"name", "cron", "command", "enabled"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        
        if "cron" in updates:
            updates["next_run"] = self._calc_next_run(updates["cron"])
        
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(f"UPDATE cron_tasks SET {set_clause} WHERE task_id = ?", values)
            db.commit()
            return cursor.rowcount > 0
    
    def get_task(self, task_id: str) -> Optional[CronTask]:
        """获取单个任务"""
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM cron_tasks WHERE task_id = ?", (task_id,)).fetchone()
            if row:
                return self._row_to_task(row)
            return None
    
    def list_tasks(self, enabled_only: bool = False) -> List[CronTask]:
        """列出所有任务"""
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            if enabled_only:
                rows = db.execute("SELECT * FROM cron_tasks WHERE enabled = 1 ORDER BY created_at").fetchall()
            else:
                rows = db.execute("SELECT * FROM cron_tasks ORDER BY created_at").fetchall()
            return [self._row_to_task(row) for row in rows]
    
    def get_due_tasks(self) -> List[CronTask]:
        """获取到期的任务（next_run <= now）"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM cron_tasks WHERE enabled = 1 AND (next_run IS NULL OR next_run <= ?)",
                (now,)
            ).fetchall()
            return [self._row_to_task(row) for row in rows]
    
    def mark_executed(self, task_id: str, status: str = "completed", result: str = None):
        """标记任务已执行"""
        now = datetime.now().isoformat()
        task = self.get_task(task_id)
        next_run = self._calc_next_run(task.cron) if task else None
        
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "UPDATE cron_tasks SET last_run = ?, next_run = ?, run_count = run_count + 1 WHERE task_id = ?",
                (now, next_run, task_id)
            )
            db.execute(
                "INSERT INTO cron_runs (task_id, status, result, finished_at) VALUES (?, ?, ?, ?)",
                (task_id, status, result, now)
            )
            db.commit()
    
    def get_run_history(self, task_id: str = None, limit: int = 50) -> List[Dict]:
        """获取执行历史"""
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            if task_id:
                rows = db.execute(
                    "SELECT * FROM cron_runs WHERE task_id = ? ORDER BY started_at DESC LIMIT ?",
                    (task_id, limit)
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM cron_runs ORDER BY started_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(row) for row in rows]
    
    def _calc_next_run(self, cron: str) -> Optional[str]:
        """计算下次执行时间"""
        if not CRONITER_AVAILABLE:
            return None
        try:
            itr = croniter(cron, datetime.now())
            return itr.get_next(datetime).isoformat()
        except Exception:
            return None
    
    def _row_to_task(self, row) -> CronTask:
        return CronTask(
            task_id=row["task_id"],
            name=row["name"],
            cron=row["cron"],
            command=row["command"],
            enabled=bool(row["enabled"]),
            last_run=row["last_run"],
            next_run=row["next_run"],
            created_at=row["created_at"],
            run_count=row["run_count"],
        )
