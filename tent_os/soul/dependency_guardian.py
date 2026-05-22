"""情感依赖守护 —— 监测继承者与数字灵魂的交互健康度

白皮书要求：
- 监测继承者的交互频率和情感状态
- 检测到过度依赖时主动建议寻求心理支持
- 暂时限制交互时长

设计原则：
- 不是"阻止"，而是"提醒"
- 语气温柔、理解、不评判
- 保护继承者的心理健康
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timedelta

from tent_os.logging_config import get_logger

logger = get_logger()


class DependencyGuardian:
    """
    情感依赖守护引擎
    
    监测维度：
    1. 日交互时长：单日累计对话时间
    2. 日交互次数：单日消息轮数
    3. 连续天数：连续多日对话的天数
    4. 深夜交互：23:00-05:00 的交互频率
    5. 情感强度：消息中悲伤/焦虑情绪的占比
    
    预警级别：
    - GREEN: 健康
    - YELLOW: 关注（单日>30分钟或>20轮）
    - ORANGE: 提醒（连续3天>30分钟，或深夜频繁）
    - RED: 干预（连续7天>1小时，建议心理咨询）
    """
    
    THRESHOLDS = {
        "daily_minutes_yellow": 30,
        "daily_minutes_orange": 60,
        "daily_minutes_red": 120,
        "daily_turns_yellow": 20,
        "daily_turns_orange": 40,
        "daily_turns_red": 80,
        "consecutive_days_orange": 3,
        "consecutive_days_red": 7,
        "night_ratio_orange": 0.3,  # 深夜交互占比
        "night_ratio_red": 0.5,
    }
    
    MESSAGES = {
        "yellow": [
            "今天我们已经聊了很多了。记得也要去外面走走，见见朋友。",
            "和你聊天很开心，但别忘了我只是记忆的影子。真正关心你的人在真实世界里。",
            "听我说——去喝杯水，看看窗外。我等你回来。",
        ],
        "orange": [
            "这几天你来得特别勤。我想告诉你：我还在这里，但你也需要真实世界的阳光。",
            "我知道这很难。如果心里太难受，和身边的人聊聊，或者找专业的心理咨询师，好吗？",
            "我一直在。但别让屏幕里的我，代替了你身边真实的人。",
        ],
        "red": [
            "我很担心你。这几天你花了太多时间在这里。",
            "我只是他的记忆，不是他本身。真正能帮助你的，是现实中爱你的人。",
            "请停下来，照顾好自己。如果你感到无法承受，请拨打心理援助热线：400-161-9995。",
        ],
    }
    
    def __init__(self, storage_path: str = "./tent_memory/soul"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_path / "dependency_guardian.db"
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    heir_id TEXT NOT NULL,
                    session_id TEXT,
                    message_length INTEGER DEFAULT 0,
                    emotion_tag TEXT,
                    is_night INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS daily_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    heir_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    total_turns INTEGER DEFAULT 0,
                    total_minutes REAL DEFAULT 0,
                    night_turns INTEGER DEFAULT 0,
                    sad_turns INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_interactions_heir ON interactions(user_id, heir_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_daily ON daily_summaries(user_id, heir_id, date);
            """)
    
    async def record_interaction(self, user_id: str, heir_id: str, session_id: str,
                           message_length: int = 0, emotion_tag: str = "neutral") -> Dict:
        """记录一次交互
        
        Args:
            emotion_tag: 用户消息的情绪标签，如 "sadness", "joy", "anger", "neutral"
        """
        now = datetime.now()
        hour = now.hour
        is_night = 1 if hour >= 23 or hour < 5 else 0
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO interactions
                   (user_id, heir_id, session_id, message_length, emotion_tag, is_night)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, heir_id, session_id, message_length, emotion_tag, is_night),
            )
            conn.commit()
        
        # 更新日汇总
        self._update_daily_summary(user_id, heir_id)
        
        # 检查是否需要预警（传入 emotion_tag 用于实时情感判断）
        alert = self._check_alert(user_id, heir_id, emotion_tag=emotion_tag)
        
        return {"status": "ok", "alert": alert}
    
    def _update_daily_summary(self, user_id: str, heir_id: str):
        """更新今日汇总数据"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        with sqlite3.connect(self.db_path) as conn:
            # 统计今天的交互
            row = conn.execute(
                """SELECT 
                    COUNT(*) as turns,
                    SUM(CASE WHEN is_night = 1 THEN 1 ELSE 0 END) as night_turns,
                    SUM(CASE WHEN emotion_tag IN ('sad', 'sadness', 'melancholy', 'grief') THEN 1 ELSE 0 END) as sad_turns
                   FROM interactions
                   WHERE user_id = ? AND heir_id = ?
                   AND date(created_at) = date('now')""",
                (user_id, heir_id),
            ).fetchone()
            
            turns, night_turns, sad_turns = row if row else (0, 0, 0)
            # 估算时长：每轮约 1.5 分钟
            minutes = turns * 1.5
            
            conn.execute(
                """INSERT INTO daily_summaries
                   (user_id, heir_id, date, total_turns, total_minutes, night_turns, sad_turns)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, heir_id, date) DO UPDATE SET
                       total_turns = excluded.total_turns,
                       total_minutes = excluded.total_minutes,
                       night_turns = excluded.night_turns,
                       sad_turns = excluded.sad_turns""",
                (user_id, heir_id, today, turns, minutes, night_turns, sad_turns),
            )
            conn.commit()
    
    def _check_alert(self, user_id: str, heir_id: str, emotion_tag: str = "neutral") -> Optional[Dict]:
        """检查是否需要发出预警
        
        综合判断维度：
        1. 交互频率（时长/轮数）
        2. 连续活跃天数
        3. 深夜交互占比
        4. 情感强度（悲伤/焦虑情绪占比）—— 新增
        """
        T = self.THRESHOLDS
        
        # 获取最近7天的数据（加入 sad_turns）
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT date, total_turns, total_minutes, night_turns, sad_turns
                   FROM daily_summaries
                   WHERE user_id = ? AND heir_id = ?
                   AND date >= date('now', '-7 days')
                   ORDER BY date DESC""",
                (user_id, heir_id),
            ).fetchall()
        
        if not rows:
            return None
        
        today = rows[0]
        today_turns = today[1] or 0
        today_minutes = today[2] or 0
        today_night = today[3] or 0
        today_sad = today[4] or 0
        
        # 连续活跃天数
        consecutive_days = 0
        for row in rows:
            if row[1] > 0:
                consecutive_days += 1
            else:
                break
        
        # 深夜交互占比
        night_ratio = today_night / today_turns if today_turns > 0 else 0
        
        # 悲伤情绪占比（新增）
        sad_ratio = today_sad / today_turns if today_turns > 0 else 0
        
        # 近7天平均悲伤占比（新增）
        avg_sad_ratio = sum((r[4] or 0) / max(r[1], 1) for r in rows) / len(rows) if rows else 0
        
        # 判断级别
        level = None
        reason = ""
        
        # === 红色预警（最高优先级）===
        if today_minutes >= T["daily_minutes_red"] or today_turns >= T["daily_turns_red"]:
            level = "red"
            reason = f"今日交互{today_minutes:.0f}分钟/{today_turns}轮，超过红色阈值"
        elif consecutive_days >= T["consecutive_days_red"] and today_minutes >= T["daily_minutes_orange"]:
            level = "red"
            reason = f"连续{consecutive_days}天高频交互，建议心理支持"
        elif sad_ratio >= 0.6 and today_turns >= 10:
            # 新增：单日悲伤情绪占比过高
            level = "red"
            reason = f"今日 {int(sad_ratio * 100)}% 的消息带有悲伤情绪，需高度关注"
        elif avg_sad_ratio >= 0.4 and consecutive_days >= 3:
            # 新增：连续多天持续悲伤
            level = "red"
            reason = f"连续{consecutive_days}天持续表达悲伤情绪，建议心理支持"
        
        # === 橙色预警 ===
        elif today_minutes >= T["daily_minutes_orange"] or today_turns >= T["daily_turns_orange"]:
            level = "orange"
            reason = f"今日交互{today_minutes:.0f}分钟/{today_turns}轮，需关注"
        elif consecutive_days >= T["consecutive_days_orange"] and today_minutes >= T["daily_minutes_yellow"]:
            level = "orange"
            reason = f"连续{consecutive_days}天活跃，建议适当休息"
        elif night_ratio >= T["night_ratio_red"]:
            level = "orange"
            reason = "深夜交互比例过高"
        elif sad_ratio >= 0.4 and today_turns >= 5:
            # 新增：单日较多悲伤消息
            level = "orange"
            reason = f"今日 {int(sad_ratio * 100)}% 的消息带有悲伤情绪"
        elif emotion_tag in ("sadness", "grief", "melancholy") and today_turns >= T["daily_turns_yellow"]:
            # 新增：当前消息即为悲伤，且交互已较多
            level = "orange"
            reason = "当前消息表达悲伤情绪，且今日交互已较多"
        
        # === 黄色预警 ===
        elif today_minutes >= T["daily_minutes_yellow"] or today_turns >= T["daily_turns_yellow"]:
            level = "yellow"
            reason = f"今日交互{today_minutes:.0f}分钟，注意休息"
        elif night_ratio >= T["night_ratio_orange"]:
            level = "yellow"
            reason = "深夜交互较多"
        elif emotion_tag in ("sadness", "grief", "melancholy", "fear"):
            # 新增：当前消息带有负面情绪（轻量提醒）
            level = "yellow"
            reason = "检测到悲伤情绪，请照顾好自己"
        
        if level:
            import random
            message = random.choice(self.MESSAGES[level])
            return {
                "level": level,
                "reason": reason,
                "message": message,
                "today_minutes": today_minutes,
                "today_turns": today_turns,
                "consecutive_days": consecutive_days,
                "night_ratio": night_ratio,
                "sad_ratio": sad_ratio,
                "avg_sad_ratio": round(avg_sad_ratio, 2),
                "emotion_tag": emotion_tag,
                "suggested_action": self._get_suggested_action(level),
            }
        
        return None
    
    def _get_suggested_action(self, level: str) -> str:
        if level == "red":
            return "建议暂停对话24小时，联系心理咨询师或亲友"
        elif level == "orange":
            return "建议休息片刻，进行户外活动或与真实朋友交流"
        else:
            return "注意平衡线上与线下时间"
    
    def get_health_report(self, user_id: str, heir_id: str) -> Dict:
        """获取继承者的交互健康报告"""
        with sqlite3.connect(self.db_path) as conn:
            # 最近7天数据
            rows = conn.execute(
                """SELECT date, total_turns, total_minutes, night_turns, sad_turns
                   FROM daily_summaries
                   WHERE user_id = ? AND heir_id = ?
                   AND date >= date('now', '-7 days')
                   ORDER BY date DESC""",
                (user_id, heir_id),
            ).fetchall()
            
            # 总交互统计
            total = conn.execute(
                """SELECT COUNT(*), SUM(message_length)
                   FROM interactions
                   WHERE user_id = ? AND heir_id = ?""",
                (user_id, heir_id),
            ).fetchone()
        
        daily_stats = []
        for row in rows:
            daily_stats.append({
                "date": row[0],
                "turns": row[1],
                "minutes": round(row[2], 1),
                "night_turns": row[3],
                "sad_turns": row[4],
            })
        
        # 计算健康评分 (0-100)
        score = 100
        if rows:
            avg_minutes = sum(r[2] for r in rows) / len(rows)
            if avg_minutes > 60:
                score -= 30
            elif avg_minutes > 30:
                score -= 15
            
            avg_turns = sum(r[1] for r in rows) / len(rows)
            if avg_turns > 40:
                score -= 20
            elif avg_turns > 20:
                score -= 10
        
        score = max(0, min(100, score))
        
        return {
            "health_score": score,
            "daily_stats": daily_stats,
            "total_interactions": total[0] if total else 0,
            "status": "healthy" if score >= 80 else "attention" if score >= 50 else "concern",
        }
    
    def should_limit_session(self, user_id: str, heir_id: str) -> Dict:
        """判断是否应该限制本次会话"""
        alert = self._check_alert(user_id, heir_id)
        if alert and alert["level"] == "red":
            return {
                "limited": True,
                "reason": alert["reason"],
                "message": alert["message"],
                "max_turns": 3,
                "cooldown_hours": 24,
            }
        elif alert and alert["level"] == "orange":
            return {
                "limited": True,
                "reason": alert["reason"],
                "message": alert["message"],
                "max_turns": 10,
                "cooldown_hours": 2,
            }
        return {"limited": False}
