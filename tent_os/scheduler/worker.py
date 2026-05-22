import asyncio
import json
import logging
import sqlite3
import uuid
from typing import Dict, Any, Optional

from tent_os.scheduler.router import SchedulerRouter, ExecutorStatus
from tent_os.scheduler.background_tasks import BackgroundTaskScheduler
from tent_os.scheduler.emergency_stop import KillSwitch
from tent_os.governance.policy_engine import PolicyEngine
from tent_os.autonomy.heartbeat import HeartbeatEngine

logger = logging.getLogger("tent_os.scheduler")


class SchedulerWorker:
    """调度进程——全异步，不阻塞等待执行"""
    
    def __init__(self, bus, router: SchedulerRouter, db_path: str = "./tent_scheduler.db",
                 heartbeat_path: str = "./HEARTBEAT.md", self_healing=None):
        self.bus = bus
        self.router = router
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self._init_db()
        self.background = BackgroundTaskScheduler(db_path=db_path, heartbeat_path=heartbeat_path)
        self.executors: Dict[str, Any] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.kill_switch = KillSwitch(bus, router, db_path)
        self.policy = PolicyEngine("./config/policies.yaml")
        self.heartbeat = HeartbeatEngine(bus, heartbeat_path)
        self.self_healing = self_healing
        # [SOUL] 视觉观察引擎与场景引擎已移除 —— 不再监控物理环境
    
    def _init_db(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                session_id TEXT,
                executor_id TEXT,
                action TEXT,
                params TEXT,
                reply_to TEXT,
                webhook TEXT,
                status TEXT DEFAULT 'submitted',
                result TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # 分布式AI：已连接设备表
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS connected_devices (
                device_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_type TEXT,
                device_name TEXT,
                capabilities TEXT,
                last_heartbeat TEXT,
                current_scene TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        self.db.commit()
    
    # FIX v5: 异步包装同步sqlite操作，避免阻塞事件循环
    async def _db_execute(self, sql: str, params=()):
        return await asyncio.to_thread(self.db.execute, sql, params)
    
    async def _db_commit(self):
        return await asyncio.to_thread(self.db.commit)
    
    async def _db_execute_fetchone(self, sql: str, params=()):
        def _exec():
            cursor = self.db.execute(sql, params)
            return cursor.fetchone()
        return await asyncio.to_thread(_exec)
    
    async def _db_execute_fetchall(self, sql: str, params=()):
        def _exec():
            cursor = self.db.execute(sql, params)
            return cursor.fetchall()
        return await asyncio.to_thread(_exec)
    
    def register_executor(self, executor_id: str, executor):
        self.executors[executor_id] = executor
    
    async def start(self):
        await self.bus.subscribe("scheduler.submit", "scheduler-submit", self._handle_submit)
        # [SOUL] 物理任务订阅已移除
        await self.kill_switch.start()
        # 启动心跳引擎（延迟 60 秒首次执行，避免启动时洪水）
        async def delayed_heartbeat():
            await asyncio.sleep(60)
            await self.heartbeat.start()
        asyncio.create_task(delayed_heartbeat())
        # [SOUL] 主动观察与场景引擎启动已移除
        # 启动后台任务调度
        asyncio.create_task(self.background.run(self.bus))
        # 恢复未完成的任务
        await self._recover_running_tasks()
    
    async def _submit_task_internal(self, task_id: str, session_id: Optional[str], executor_id: str,
                                     action: str, params: Dict, reply_to: str, webhook: Optional[str] = None,
                                     task_desc: str = "") -> bool:
        """内部任务提交逻辑——被 _handle_submit 和 _handle_physical_request 共享"""
        executor = self.executors.get(executor_id)
        # fallback: 如果 executor_id 找不到，尝试通过 action 路由查找
        if not executor:
            fallback_id = self.router.select_executor(action)
            if fallback_id:
                executor = self.executors.get(fallback_id)
                executor_id = fallback_id
        if not executor:
            await self.bus.publish(reply_to, json.dumps({
                "task_id": task_id, "session_id": session_id, "status": "failed", "error": f"执行者不存在: {executor_id}", "type": "step_completed"
            }).encode())
            return False
        
        # 幂等：检查任务是否已存在
        row = await self._db_execute_fetchone("SELECT status FROM tasks WHERE task_id = ?", (task_id,))
        if row:
            logger.info(f"任务已存在，忽略重复提交: {task_id}")
            return False
        
        # 检查全局紧急停止
        if self.kill_switch.is_global_stop_active():
            await self.bus.publish(reply_to, json.dumps({
                "task_id": task_id, "session_id": session_id, "status": "rejected",
                "error": "全局紧急停止已激活，所有物理任务被拒绝", "type": "step_completed"
            }).encode())
            return False
        
        # 策略引擎检查（微软 AGT 模式）
        from datetime import datetime
        executor_state = self.router.executors.get(executor_id)
        policy_ctx = {
            "task": task_desc,
            "action": action,
            "executor": {
                "authorized": True,
                "status": executor_state.status.value if executor_state else "unknown",
                "consecutive_failures": executor_state.consecutive_failures if executor_state else 0,
                "queue_depth": executor_state.queue_depth if executor_state else 0,
                "is_physical": executor_state.is_physical if executor_state else False,
            },
            "hour": datetime.now().hour,
        }
        policy_result = self.policy.evaluate(policy_ctx)
        
        if policy_result["decision"] == "deny":
            await self.bus.publish(reply_to, json.dumps({
                "task_id": task_id, "session_id": session_id, "status": "rejected",
                "error": f"策略拒绝: {policy_result.get('reason', '不符合策略规则')} [{policy_result['rule']}]", "type": "step_completed"
            }).encode())
            logger.warning(f"任务 {task_id} 被策略 '{policy_result['rule']}' 拒绝")
            return False
        
        if policy_result["decision"] == "require_approval":
            await self.bus.publish("governance.approval.request", json.dumps({
                "session_id": session_id or task_id,
                "plan": {"steps": [{"action": action, "executor": executor_id, "params": params}]},
                "reply_to": reply_to,
                "policy_rule": policy_result["rule"],
                "reason": policy_result.get("reason", ""),
            }).encode())
            logger.info(f"任务 {task_id} 需要审批（策略: {policy_result['rule']}）")
            return False
        
        # 记录执行者状态：IDLE → ASSIGNED
        self.router.record_assigned(executor_id, task_id, action)
        
        # 保存任务到数据库
        await self._db_execute("""
            INSERT INTO tasks (task_id, session_id, executor_id, action, params, reply_to, webhook, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'assigned')
        """, (task_id, session_id, executor_id, action, json.dumps(params), reply_to, webhook))
        await self._db_commit()
        
        # 立即返回 assigned
        await self.bus.publish(reply_to, json.dumps({
            "task_id": task_id, "session_id": session_id, "status": "assigned", "type": "step_completed"
        }).encode())
        
        # 启动后台监控协程
        task = asyncio.create_task(self._monitor_task(task_id, session_id, executor, action, params, reply_to, webhook, executor_id))
        self.active_tasks[task_id] = task
        return True

    async def _handle_submit(self, msg):
        """处理任务提交——立即返回，不等待执行"""
        data = json.loads(msg.data)
        await self._submit_task_internal(
            task_id=data["task_id"],
            session_id=data.get("session_id"),
            executor_id=data["executor_id"],
            action=data["action"],
            params=data["params"],
            reply_to=data["reply_to"],
            webhook=data.get("webhook"),
            task_desc=data.get("task", ""),
        )
    
    async def _handle_physical_request(self, msg):
        """处理物理世界任务请求"""
        try:
            data = json.loads(msg.data.decode() if isinstance(msg.data, bytes) else msg.data)
            task_id = data.get("task_id", f"phys_{uuid.uuid4().hex[:12]}")
            action = data.get("action", "deliver")
            target = data.get("target_location", "")
            item = data.get("item_description", "")
            provider = data.get("provider", "auto")
            priority = data.get("priority", "normal")
            
            # 确定执行者
            executor_id = provider
            if provider == "auto":
                # 选择第一个可用的 physical executor
                for eid, estate in self.router.executors.items():
                    if getattr(estate, 'is_physical', False) and eid in self.executors:
                        executor_id = eid
                        break
                if executor_id == "auto":
                    executor_id = "manual"  #  fallback 到人工
            
            # 构造任务描述和参数
            task_desc = f"{action}: {item} -> {target}"
            params = {
                "target_location": target,
                "item_description": item,
                "priority": priority,
                "action": action,
            }
            
            # 映射 action 到 executor 支持的 action
            if action == "deliver":
                exec_action = "move" if executor_id == "realman" else "deliver"
            elif action == "retrieve":
                exec_action = "pick" if executor_id == "realman" else "retrieve"
            elif action == "notify":
                exec_action = "notify"
            else:
                exec_action = action
            
            reply_to = f"scheduler.physical.reply.{task_id}"
            
            success = await self._submit_task_internal(
                task_id=task_id,
                session_id=None,
                executor_id=executor_id,
                action=exec_action,
                params=params,
                reply_to=reply_to,
                webhook=None,
                task_desc=task_desc,
            )
            
            if success:
                logger.info(f"[Physical] 任务 {task_id} 已提交到执行者 {executor_id}")
            else:
                logger.warning(f"[Physical] 任务 {task_id} 提交失败")
                
        except Exception as e:
            logger.error(f"[Physical] 处理物理任务请求失败: {e}")
    
    async def _monitor_task(self, task_id: str, session_id: str, executor, action: str, params: Dict,
                            reply_to: str, webhook: str = None, executor_id: str = None):
        """后台监控任务状态，完成后发布结果
        
        状态流转：ASSIGNED → EXECUTING → [COMPLETED/FAILED/TIMEOUT]
        """
        try:
            # 记录执行中状态
            if executor_id:
                self.router.record_executing(executor_id)
            await self._db_execute("UPDATE tasks SET status = 'executing' WHERE task_id = ?", (task_id,))
            await self._db_commit()
            
            result = await executor.execute(action, params)
            
            # 如果执行者返回pending，说明是异步外部任务（需等待回调）
            if result.get("status") == "pending":
                await self._db_execute("UPDATE tasks SET status = 'waiting_webhook', result = ? WHERE task_id = ?",
                               (json.dumps(result), task_id))
                await self._db_commit()
                return  # 不发布结果，等待Webhook Gateway回调
            
            # 同步任务（如机械臂），直接发布结果
            status = result.get("status", "completed")
            await self._db_execute("UPDATE tasks SET status = ?, result = ? WHERE task_id = ?",
                           (status, json.dumps(result), task_id))
            await self._db_commit()
            
            # 状态机更新 + 熔断机制
            if executor_id:
                if status == "completed":
                    self.router.record_success(executor_id)
                elif status == "failed":
                    tripped = self.router.record_failure(executor_id)
                    if tripped:
                        logger.warning(f"执行者 {executor_id} 已熔断（连续失败 {self.router.executors[executor_id].circuit_breaker_threshold} 次）")
            
            await self.bus.publish(reply_to, json.dumps({
                "task_id": task_id, "session_id": session_id, "status": status, "result": result, "type": "step_completed"
            }).encode())
            
            # FIX: 同步完成的任务已通过 reply_to 发布结果，不再额外发送 session.wake
            # session.wake 仅用于异步长时任务（waiting_webhook）的唤醒，避免 _on_task_completed 被重复触发
        except Exception as e:
            error_str = str(e)
            
            # FIX: SelfHealing 介入——尝试一次降级重试
            healed = False
            if self.self_healing and executor_id and executor_id in self.executors:
                try:
                    healing_result = await self.self_healing.handle_failure(
                        task_id, error_str, self.executors[executor_id].execute,
                        {"action": action, "params": params}
                    )
                    if healing_result.success:
                        healed = True
                        result = {"status": "completed", "result": healing_result.final_result}
                        await self._db_execute("UPDATE tasks SET status = ?, result = ? WHERE task_id = ?",
                                       ("completed", json.dumps(result), task_id))
                        await self._db_commit()
                        if executor_id:
                            self.router.record_success(executor_id)
                        await self.bus.publish(reply_to, json.dumps({
                            "task_id": task_id, "session_id": session_id, "status": "completed", "result": result, "type": "step_completed"
                        }).encode())
                        logger.info(f"[SCHED] SelfHealing 成功修复任务 {task_id}: {healing_result.action_taken}")
                except Exception as heal_err:
                    logger.warning(f"[SCHED] SelfHealing 修复失败: {heal_err}")
            
            if not healed:
                await self._db_execute("UPDATE tasks SET status = 'failed', result = ? WHERE task_id = ?",
                               (json.dumps({"error": error_str}), task_id))
                await self._db_commit()
                
                # 熔断机制：记录异常失败
                if executor_id:
                    tripped = self.router.record_failure(executor_id)
                    if tripped:
                        logger.warning(f"执行者 {executor_id} 已熔断（连续失败 {self.router.executors[executor_id].circuit_breaker_threshold} 次）")
                
                await self.bus.publish(reply_to, json.dumps({
                    "task_id": task_id, "session_id": session_id, "status": "failed", "error": error_str, "type": "step_completed"
                }).encode())
                
                if session_id:
                    await self.bus.publish("session.wake", json.dumps({
                        "session_id": session_id,
                        "task_id": task_id,
                        "result": {"error": error_str}
                    }).encode())
        finally:
            self.active_tasks.pop(task_id, None)
    
    async def _recover_running_tasks(self):
        """进程重启后，恢复进行中的任务监控"""
        rows = await self._db_execute_fetchall("SELECT * FROM tasks WHERE status IN ('assigned', 'executing', 'waiting_webhook')")
        if rows:
            columns = [desc[0] for desc in self.db.execute("SELECT * FROM tasks LIMIT 0").description]
        for row in rows:
            task = dict(zip(columns, row))
            status = task["status"]
            # waiting_webhook的任务不需要恢复监控，等Webhook Gateway回调即可
            if status == "waiting_webhook":
                continue
            executor = self.executors.get(task["executor_id"])
            if executor:
                params = json.loads(task["params"]) if task["params"] else {}
                t = asyncio.create_task(
                    self._monitor_task(task["task_id"], task.get("session_id"), executor, task["action"], params,
                                       task["reply_to"], task["webhook"], task["executor_id"])
                )
                self.active_tasks[task["task_id"]] = t
