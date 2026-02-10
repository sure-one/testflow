"""
异步任务管理器
用于管理后台异步任务，支持并发处理和状态轮询
支持从系统设置加载并发配置
支持数据库持久化任务状态
"""
import asyncio
import uuid
from typing import Dict, Any, Optional, List, Callable, TYPE_CHECKING
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class AsyncTaskStatus(str, Enum):
    """异步任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class AsyncTask:
    """异步任务数据类"""
    task_id: str
    task_type: str
    status: AsyncTaskStatus = AsyncTaskStatus.PENDING
    progress: int = 0
    total_batches: int = 0
    completed_batches: int = 0
    result: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None  # 进度消息
    request_params: Optional[Dict[str, Any]] = None  # 原始请求参数，用于重试
    user_id: Optional[int] = None  # 用户 ID
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "progress": self.progress,
            "total_batches": self.total_batches,
            "completed_batches": self.completed_batches,
            "result": self.result,
            "error": self.error,
            "message": self.message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class AsyncTaskManager:
    """异步任务管理器

    支持从系统设置加载并发配置，包括：
    - max_concurrent_tasks: 最大并发任务数
    - task_timeout: 任务超时时间（秒）
    - retry_count: 失败重试次数
    - queue_size: 任务队列大小
    """

    # 默认配置值
    DEFAULT_MAX_CONCURRENT_TASKS = 3
    DEFAULT_TASK_TIMEOUT = 300  # 秒（与 httpx 超时保持一致）
    DEFAULT_RETRY_COUNT = 3
    DEFAULT_QUEUE_SIZE = 100
    DEFAULT_LOG_LEVEL = "info"  # 默认日志级别

    # 批量日志配置
    _LOG_BATCH_SIZE = 10  # 批量写入大小
    _LOG_FLUSH_INTERVAL = 2.0  # 刷新间隔（秒）

    # 进度更新节流配置
    _PROGRESS_UPDATE_THRESHOLD = 5  # 进度变化阈值（百分比）
    _PROGRESS_UPDATE_INTERVAL = 3.0  # 时间间隔（秒）

    # 类级别的数据库写入锁，确保所有数据库操作串行化
    _db_write_lock = asyncio.Lock()

    def __init__(self):
        self._tasks: Dict[str, AsyncTask] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._pending_queue: List[str] = []  # 等待执行的任务队列

        # 并发配置（从系统设置加载）
        self._max_concurrent_tasks: int = self.DEFAULT_MAX_CONCURRENT_TASKS
        self._task_timeout: int = self.DEFAULT_TASK_TIMEOUT
        self._retry_count: int = self.DEFAULT_RETRY_COUNT
        self._queue_size: int = self.DEFAULT_QUEUE_SIZE
        self._log_level: str = self.DEFAULT_LOG_LEVEL  # 日志级别

        # 配置是否已加载
        self._config_loaded: bool = False

        # 数据库会话（用于持久化）
        self._db: Optional["Session"] = None

        # 用户 ID 缓存（task_id -> user_id 映射）
        self._task_user_ids: Dict[str, int] = {}

        # 数据库写入队列和锁（解决并发写入冲突问题）
        self._db_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)  # 数据库写入队列
        self._db_worker_task: Optional[asyncio.Task] = None  # 后台写入任务
        self._db_worker_lock = asyncio.Lock()  # 保护工作线程启动/停止
        self._shutdown_event = asyncio.Event()  # 关闭信号

        # 日志缓冲区（批量写入优化）
        self._log_buffer: List[tuple] = []  # (task_id, log_data) 列表
        self._log_buffer_lock = asyncio.Lock()  # 保护缓冲区
        self._log_flush_task: Optional[asyncio.Task] = None  # 定时刷新任务
        self._last_flush_time: float = 0  # 上次刷新时间

        # 进度更新缓存（节流优化）
        self._progress_cache: Dict[str, Dict] = {}  # {task_id: {last_progress, last_update_time, pending_message}}
    
    def load_config_from_db(self, db: "Session") -> None:
        """从数据库加载并发配置
        
        Args:
            db: 数据库会话
        """
        try:
            from app.services.settings_service import SettingsService
            
            config = SettingsService.get_concurrency_config(db)
            self._max_concurrent_tasks = config.max_concurrent_tasks
            self._task_timeout = config.task_timeout
            self._retry_count = config.retry_count
            self._queue_size = config.queue_size
            self._config_loaded = True
            
            print(f"[AsyncTaskManager] 已加载并发配置: "
                  f"max_concurrent_tasks={self._max_concurrent_tasks}, "
                  f"task_timeout={self._task_timeout}s, "
                  f"retry_count={self._retry_count}, "
                  f"queue_size={self._queue_size}")
        except Exception as e:
            print(f"[AsyncTaskManager] 加载并发配置失败，使用默认值: {e}")
            self._config_loaded = False
    
    def reload_config(self, db: "Session") -> None:
        """重新加载并发配置
        
        当系统设置更新时调用此方法刷新配置
        
        Args:
            db: 数据库会话
        """
        self.load_config_from_db(db)
    
    @property
    def max_concurrent_tasks(self) -> int:
        """获取最大并发任务数"""
        return self._max_concurrent_tasks
    
    @property
    def task_timeout(self) -> int:
        """获取任务超时时间（秒）"""
        return self._task_timeout
    
    @property
    def retry_count(self) -> int:
        """获取失败重试次数"""
        return self._retry_count
    
    @property
    def queue_size(self) -> int:
        """获取任务队列大小"""
        return self._queue_size
    
    @property
    def config_loaded(self) -> bool:
        """配置是否已从数据库加载"""
        return self._config_loaded

    def set_db_session(self, db: Optional["Session"]) -> None:
        """设置数据库会话（用于持久化）

        Args:
            db: 数据库会话
        """
        self._db = db

    def set_task_user_id(self, task_id: str, user_id: int) -> None:
        """设置任务的用户 ID

        Args:
            task_id: 任务 ID
            user_id: 用户 ID
        """
        self._task_user_ids[task_id] = user_id
        # 同时设置到任务对象中
        task = self.get_task(task_id)
        if task:
            task.user_id = user_id
            # 同步到数据库
            self._sync_to_db(task_id, task)

    def set_task_request_params(self, task_id: str, params: dict) -> None:
        """保存任务请求参数（用于重试）

        Args:
            task_id: 任务 ID
            params: 请求参数字典
        """
        task = self.get_task(task_id)
        if task:
            task.request_params = params
            # 同步到数据库
            self._sync_to_db(task_id, task)

    async def _start_db_worker(self) -> None:
        """启动数据库写入工作线程（如果未启动）"""
        async with self._db_worker_lock:
            if self._db_worker_task is None or self._db_worker_task.done():
                self._shutdown_event.clear()
                self._db_worker_task = asyncio.create_task(self._db_worker())
                print("[AsyncTaskManager] 数据库写入工作线程已启动")

        # 启动日志刷新任务
        await self._start_log_flusher()

    async def _start_log_flusher(self) -> None:
        """启动日志缓冲刷新定时任务"""
        if self._log_flush_task and not self._log_flush_task.done():
            return

        async def flush_loop():
            while not self._shutdown_event.is_set():
                try:
                    await asyncio.sleep(self._LOG_FLUSH_INTERVAL)
                    await self._flush_log_buffer()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"[AsyncTaskManager] 日志刷新错误: {e}")

        self._log_flush_task = asyncio.create_task(flush_loop())
        print("[AsyncTaskManager] 日志刷新任务已启动")

    async def _stop_db_worker(self) -> None:
        """停止数据库写入工作线程"""
        # 先停止日志刷新任务
        await self._stop_log_flusher()

        async with self._db_worker_lock:
            if self._db_worker_task and not self._db_worker_task.done():
                # 发送退出信号
                try:
                    self._db_queue.put_nowait((None, None))
                except asyncio.QueueFull:
                    pass
                self._shutdown_event.set()
                try:
                    await asyncio.wait_for(self._db_worker_task, timeout=5.0)
                except asyncio.TimeoutError:
                    print("[AsyncTaskManager] 等待数据库写入工作线程退出超时")
                    self._db_worker_task.cancel()
                    try:
                        await self._db_worker_task
                    except asyncio.CancelledError:
                        pass

    async def _stop_log_flusher(self) -> None:
        """停止日志刷新任务"""
        if self._log_flush_task and not self._log_flush_task.done():
            # 先刷新缓冲区
            await self._flush_log_buffer()
            # 停止任务
            self._log_flush_task.cancel()
            try:
                await self._log_flush_task
            except asyncio.CancelledError:
                pass
            print("[AsyncTaskManager] 日志刷新任务已停止")

    async def _db_worker(self) -> None:
        """后台数据库写入工作线程

        串行处理所有数据库写入请求，避免并发写入冲突
        """
        print("[AsyncTaskManager] 数据库写入工作线程开始运行")
        while not self._shutdown_event.is_set():
            try:
                # 等待队列中的任务，设置超时以便检查关闭信号
                task_id, data = await asyncio.wait_for(
                    self._db_queue.get(),
                    timeout=1.0
                )

                # 退出信号
                if task_id is None:
                    print("[AsyncTaskManager] 数据库写入工作线程收到退出信号")
                    break

                # 判断数据类型：AsyncTask 对象或日志数据字典
                if isinstance(data, dict) and data.get("type") == "log":
                    # 处理日志添加
                    await self._do_add_log(task_id, data)
                elif isinstance(data, AsyncTask):
                    # 处理任务状态同步
                    await self._do_sync_to_db(task_id, data)
                else:
                    print(f"[AsyncTaskManager] 警告: 未知的队列数据类型: {type(data)}")

            except asyncio.TimeoutError:
                # 超时检查关闭信号
                continue
            except asyncio.CancelledError:
                print("[AsyncTaskManager] 数据库写入工作线程被取消")
                break
            except Exception as e:
                print(f"[AsyncTaskManager] 数据库写入工作线程错误: {e}")

        print("[AsyncTaskManager] 数据库写入工作线程已结束")

    async def _do_sync_to_db(self, task_id: str, task: AsyncTask) -> None:
        """实际执行数据库同步（异步版本）

        使用类级别锁确保串行化写入，避免并发冲突。

        Args:
            task_id: 任务 ID
            task: 任务对象
        """
        from app.database import SessionLocal

        # 使用类级别的锁确保所有数据库写入操作串行化
        async with AsyncTaskManager._db_write_lock:
            db = SessionLocal()
            try:
                from app.models.task import AsyncTask as AsyncTaskModel

                db_task = db.query(AsyncTaskModel).filter(
                    AsyncTaskModel.task_id == task_id
                ).first()

                if db_task:
                    # 更新现有记录
                    db_task.status = AsyncTaskStatus(task.status.value)
                    db_task.progress = task.progress
                    db_task.total_batches = task.total_batches
                    db_task.completed_batches = task.completed_batches
                    db_task.message = task.message
                    db_task.result = task.result
                    db_task.error = task.error
                    db_task.started_at = task.started_at
                    db_task.completed_at = task.completed_at
                    db_task.request_params = task.request_params
                else:
                    # 创建新记录
                    # 优先从任务对象获取 user_id，如果没有则从字典获取
                    user_id = task.user_id or self._task_user_ids.get(task_id)
                    if not user_id:
                        print(f"[AsyncTaskManager] 警告: 任务 {task_id} 没有 user_id，跳过数据库写入")
                        return

                    db_task = AsyncTaskModel(
                        task_id=task_id,
                        task_type=task.task_type,
                        status=AsyncTaskStatus(task.status.value),
                        progress=task.progress,
                        total_batches=task.total_batches,
                        completed_batches=task.completed_batches,
                        message=task.message,
                        result=task.result,
                        error=task.error,
                        user_id=user_id,
                        request_params=task.request_params,
                        created_at=task.created_at,
                        started_at=task.started_at,
                        completed_at=task.completed_at
                    )
                    db.add(db_task)

                db.commit()
            except Exception as e:
                print(f"[AsyncTaskManager] 同步到数据库失败: {e}")
                db.rollback()
            finally:
                db.close()

    def _sync_to_db(self, task_id: str, task: AsyncTask) -> None:
        """同步任务状态到数据库（通过队列实现串行化写入）

        将同步请求放入队列，由后台工作线程串行处理，
        避免并发写入导致的 SQLite 数据库锁定问题。

        Args:
            task_id: 任务 ID
            task: 任务对象
        """
        try:
            # 确保工作线程已启动
            if self._db_worker_task is None or self._db_worker_task.done():
                # 使用 asyncio.create_task 启动工作线程
                # 注意：这需要在异步上下文中调用
                try:
                    loop = asyncio.get_running_loop()
                    worker_task = loop.create_task(self._start_db_worker())
                    # 添加回调以确保工作线程已启动
                    worker_task.add_done_callback(lambda t: print(f"[AsyncTaskManager] 工作线程启动完成"))
                except RuntimeError:
                    # 不在异步上下文中，跳过同步
                    print(f"[AsyncTaskManager] 警告: 不在异步上下文中，无法启动数据库工作线程")
                    return

            # 将同步请求放入队列（非阻塞）
            try:
                self._db_queue.put_nowait((task_id, task))
            except asyncio.QueueFull:
                print(f"[AsyncTaskManager] 警告: 数据库写入队列已满，跳过同步任务 {task_id}")
        except Exception as e:
            print(f"[AsyncTaskManager] 添加到同步队列失败: {e}")

    def _should_log(self, level: str) -> bool:
        """检查是否应该记录该级别的日志

        Args:
            level: 日志级别

        Returns:
            True 如果应该记录，False 否则
        """
        levels = {"debug": 0, "info": 1, "warning": 2, "error": 3}
        current_level = levels.get(self._log_level.lower(), 1)
        msg_level = levels.get(level.lower(), 1)
        return msg_level >= current_level

    def add_log(self, task_id: str, message: str, level: str = "info", **kwargs) -> None:
        """添加任务日志（异步方式，通过队列，支持扩展字段）

        Args:
            task_id: 任务 ID
            message: 日志消息
            level: 日志级别 (debug/info/warning/error)
            **kwargs: 扩展字段，包括:
                - step_name: 步骤名称
                - step_number: 步骤序号
                - total_steps: 总步骤数
                - duration_ms: 执行时长(毫秒)
                - agent_name: 智能体名称
                - agent_type: 智能体类型
                - model_name: 模型名称
                - provider: 提供商
                - estimated_tokens: Token数量
                - current_batch: 当前批次
                - total_batches: 总批次数
        """
        try:
            # 日志级别过滤
            if not self._should_log(level):
                return

            # 确保工作线程已启动
            if self._db_worker_task is None or self._db_worker_task.done():
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._start_db_worker())
                except RuntimeError:
                    print(f"[AsyncTaskManager] 警告: 不在异步上下文中，无法添加日志")
                    return

            # ERROR 和 WARNING 级别立即写入，INFO 和 DEBUG 进入缓冲区
            log_data = {"type": "log", "level": level, "message": message, **kwargs}

            if level in ("error", "warning"):
                # 重要日志立即写入
                try:
                    self._db_queue.put_nowait((task_id, log_data))
                except asyncio.QueueFull:
                    print(f"[AsyncTaskManager] 警告: 数据库写入队列已满，跳过日志记录")
            else:
                # INFO 和 DEBUG 日志进入缓冲区
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._add_to_log_buffer(task_id, log_data))
                except RuntimeError:
                    # 不在异步上下文中，直接放入队列
                    try:
                        self._db_queue.put_nowait((task_id, log_data))
                    except asyncio.QueueFull:
                        print(f"[AsyncTaskManager] 警告: 数据库写入队列已满，跳过日志记录")

        except Exception as e:
            print(f"[AsyncTaskManager] 添加日志到队列失败: {e}")

    async def _add_to_log_buffer(self, task_id: str, log_data: dict) -> None:
        """添加日志到缓冲区

        Args:
            task_id: 任务 ID
            log_data: 日志数据
        """
        async with self._log_buffer_lock:
            self._log_buffer.append((task_id, log_data))

            # 检查是否需要刷新
            if len(self._log_buffer) >= self._LOG_BATCH_SIZE:
                await self._flush_log_buffer()

    async def _flush_log_buffer(self) -> None:
        """刷新日志缓冲区到数据库

        批量写入缓冲区中的所有日志
        """
        async with self._log_buffer_lock:
            if not self._log_buffer:
                return

            log_batch = self._log_buffer.copy()
            self._log_buffer.clear()

        # 批量写入
        await self._do_add_log_batch(log_batch)
        self._last_flush_time = asyncio.get_event_loop().time()

    async def _do_add_log_batch(self, log_batch: List[tuple]) -> None:
        """批量添加日志到数据库

        Args:
            log_batch: 日志批次，格式为 [(task_id, log_data), ...]
        """
        from app.database import SessionLocal
        from app.models.task import AsyncTaskLog, TaskLogLevel

        if not log_batch:
            return

        async with AsyncTaskManager._db_write_lock:
            db = SessionLocal()
            try:
                log_entries = []
                for task_id, log_data in log_batch:
                    level = log_data.get("level", "info")
                    message = log_data.get("message", "")

                    # 验证日志级别
                    log_level = TaskLogLevel(level) if level in [e.value for e in TaskLogLevel] else TaskLogLevel.INFO

                    # 创建日志条目
                    log_entry = AsyncTaskLog(
                        task_id=task_id,
                        level=log_level,
                        message=message,
                        step_name=log_data.get("step_name"),
                        step_number=log_data.get("step_number"),
                        total_steps=log_data.get("total_steps"),
                        duration_ms=log_data.get("duration_ms"),
                        agent_name=log_data.get("agent_name"),
                        agent_type=log_data.get("agent_type"),
                        model_name=log_data.get("model_name"),
                        provider=log_data.get("provider"),
                        estimated_tokens=log_data.get("estimated_tokens"),
                        current_batch=log_data.get("current_batch"),
                        total_batches=log_data.get("total_batches"),
                    )
                    log_entries.append(log_entry)

                db.add_all(log_entries)
                db.commit()
                print(f"[AsyncTaskManager] 批量写入 {len(log_entries)} 条日志")
            except Exception as e:
                print(f"[AsyncTaskManager] 批量写入日志失败: {e}")
                db.rollback()
            finally:
                db.close()

    async def _do_add_log(self, task_id: str, log_data: dict) -> None:
        """实际执行日志添加（异步版本，支持扩展字段）

        使用类级别锁确保串行化写入，避免并发冲突。

        Args:
            task_id: 任务 ID
            log_data: 日志数据字典
        """
        from app.database import SessionLocal
        from app.models.task import AsyncTaskLog, TaskLogLevel

        # 使用类级别的锁确保所有数据库写入操作串行化
        async with AsyncTaskManager._db_write_lock:
            db = SessionLocal()
            try:
                level = log_data.get("level", "info")
                message = log_data.get("message", "")

                # 验证日志级别
                log_level = TaskLogLevel(level) if level in [e.value for e in TaskLogLevel] else TaskLogLevel.INFO

                # 创建日志条目（包含扩展字段）
                log_entry = AsyncTaskLog(
                    task_id=task_id,
                    level=log_level,
                    message=message,
                    # 扩展字段
                    step_name=log_data.get("step_name"),
                    step_number=log_data.get("step_number"),
                    total_steps=log_data.get("total_steps"),
                    duration_ms=log_data.get("duration_ms"),
                    agent_name=log_data.get("agent_name"),
                    agent_type=log_data.get("agent_type"),
                    model_name=log_data.get("model_name"),
                    provider=log_data.get("provider"),
                    estimated_tokens=log_data.get("estimated_tokens"),
                    current_batch=log_data.get("current_batch"),
                    total_batches=log_data.get("total_batches"),
                )
                db.add(log_entry)
                db.commit()
                print(f"[AsyncTaskManager] 任务 {task_id} 添加日志: [{level}] {message[:50]}...")
            except Exception as e:
                print(f"[AsyncTaskManager] 添加日志失败: {e}")
                db.rollback()
            finally:
                db.close()

    def get_running_task_count(self) -> int:
        """获取当前正在运行的任务数"""
        return sum(1 for task in self._tasks.values() 
                   if task.status == AsyncTaskStatus.RUNNING)
    
    def get_pending_task_count(self) -> int:
        """获取等待执行的任务数"""
        return len(self._pending_queue)
    
    def can_start_new_task(self) -> bool:
        """检查是否可以启动新任务
        
        基于当前运行的任务数和配置的最大并发数判断
        
        Returns:
            是否可以启动新任务
        """
        return self.get_running_task_count() < self._max_concurrent_tasks
    
    def is_queue_full(self) -> bool:
        """检查任务队列是否已满
        
        Returns:
            队列是否已满
        """
        return len(self._pending_queue) >= self._queue_size
    
    def create_task(self, task_type: str, total_batches: int = 1) -> str:
        """创建新任务，返回任务ID
        
        如果达到并发限制，任务将被加入等待队列
        
        Args:
            task_type: 任务类型
            total_batches: 总批次数
            
        Returns:
            任务ID
            
        Raises:
            ValueError: 当队列已满时抛出
        """
        # 检查队列是否已满
        if self.is_queue_full():
            raise ValueError(f"任务队列已满（最大{self._queue_size}个），请稍后重试")

        task_id = str(uuid.uuid4())
        task = AsyncTask(
            task_id=task_id,
            task_type=task_type,
            total_batches=total_batches
        )
        self._tasks[task_id] = task

        print(f"[AsyncTaskManager] ✓ 创建任务: {task_id[:8]}... | 类型: {task_type} | 总批次: {total_batches}")

        # 如果达到并发限制，加入等待队列
        if not self.can_start_new_task():
            self._pending_queue.append(task_id)
            print(f"[AsyncTaskManager] ⏳ 任务 {task_id[:8]}... 已加入等待队列 "
                  f"(当前运行: {self.get_running_task_count()}/{self._max_concurrent_tasks})")

        return task_id
    
    def get_task(self, task_id: str) -> Optional[AsyncTask]:
        """获取任务信息"""
        return self._tasks.get(task_id)
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        task = self._tasks.get(task_id)
        if task:
            status_dict = task.to_dict()
            # 添加队列位置信息
            if task_id in self._pending_queue:
                status_dict["queue_position"] = self._pending_queue.index(task_id) + 1
            return status_dict
        return None
    
    def update_task_progress(self, task_id: str, completed_batches: int):
        """更新任务进度（基于批次数）

        Args:
            task_id: 任务 ID
            completed_batches: 已完成批次数
        """
        task = self._tasks.get(task_id)
        if task:
            task.completed_batches = completed_batches
            if task.total_batches > 0:
                # 进度范围：5% ~ 95%（留5%给启动，5%给保存）
                raw_progress = (completed_batches / task.total_batches) * 90
                task.progress = int(5 + raw_progress)

            # 打印批次进度
            if task.total_batches > 1:
                print(f"[AsyncTaskManager] 📊 任务 {task_id[:8]}... 批次进度: {completed_batches}/{task.total_batches} ({task.progress}%)")

            # 同步到数据库
            self._sync_to_db(task_id, task)

    def update_progress(self, task_id: str, progress: int, message: str = None):
        """直接设置任务进度百分比（带节流优化）

        Args:
            task_id: 任务 ID
            progress: 进度百分比（0-100）
            message: 可选的进度消息
        """
        import time

        task = self._tasks.get(task_id)
        if not task:
            return

        # 更新任务对象
        task.progress = min(max(progress, 0), 100)
        if message:
            task.message = message

        # 获取或创建缓存
        cache = self._progress_cache.get(task_id, {
            "last_progress": -1,
            "last_update_time": 0,
            "pending_message": None
        })

        # 计算变化
        progress_delta = abs(task.progress - cache["last_progress"])
        time_delta = time.time() - cache["last_update_time"]

        # 判断是否需要更新数据库
        should_update = (
            progress == 0 or  # 任务开始
            progress == 100 or  # 任务结束
            cache["last_progress"] == -1 or  # 首次更新
            progress_delta >= self._PROGRESS_UPDATE_THRESHOLD or
            time_delta >= self._PROGRESS_UPDATE_INTERVAL
        )

        if should_update:
            # 同步到数据库
            self._sync_to_db(task_id, task)

            # 在关键节点打印日志
            if task.progress == 50:
                print(f"[AsyncTaskManager] 🔄 任务 {task_id[:8]}... 进度 50%{f' | {message}' if message else ''}")
            elif task.progress == 100:
                print(f"[AsyncTaskManager) ✔ 任务 {task_id[:8]}... 进度 100%{f' | {message}' if message else ''}")

            # 更新缓存
            cache["last_progress"] = task.progress
            cache["last_update_time"] = time.time()
            self._progress_cache[task_id] = cache
        else:
            # 只更新缓存中的 pending_message
            if message:
                cache["pending_message"] = message
                self._progress_cache[task_id] = cache

    def force_progress_update(self, task_id: str):
        """强制立即更新进度到数据库

        用于关键节点（任务完成/失败/超时）确保进度及时同步

        Args:
            task_id: 任务 ID
        """
        import time

        task = self._tasks.get(task_id)
        if task:
            # 同步到数据库
            self._sync_to_db(task_id, task)

            # 更新缓存
            if task_id in self._progress_cache:
                self._progress_cache[task_id]["last_progress"] = task.progress
                self._progress_cache[task_id]["last_update_time"] = time.time()

    def start_task(self, task_id: str) -> bool:
        """标记任务开始

        Args:
            task_id: 任务 ID

        Returns:
            是否成功启动（如果达到并发限制则返回 False）
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        # 检查是否可以启动
        if not self.can_start_new_task() and task_id not in self._pending_queue:
            # 如果不能启动且不在队列中，加入队列
            self._pending_queue.append(task_id)
            return False

        # 从等待队列中移除
        if task_id in self._pending_queue:
            self._pending_queue.remove(task_id)
            print(f"[AsyncTaskManager] 🚀 任务 {task_id[:8]}... 从等待队列中取出并启动")

        task.status = AsyncTaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        task.progress = 5  # 设置初始进度，表示任务已开始

        # 同步到数据库
        self._sync_to_db(task_id, task)

        # 记录日志
        self.add_log(task_id, "任务开始执行", "info")

        print(f"[AsyncTaskManager] ▶ 任务 {task_id[:8]}... 开始执行 | 类型: {task.task_type}")

        return True

    def complete_task(self, task_id: str, result: Any):
        """标记任务完成

        Args:
            task_id: 任务 ID
            result: 任务结果
        """
        # 先刷新日志缓冲区，确保所有日志都被写入
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._flush_log_buffer())
        except RuntimeError:
            pass

        task = self._tasks.get(task_id)
        if task:
            task.status = AsyncTaskStatus.COMPLETED
            task.progress = 100
            task.result = result
            task.completed_at = datetime.utcnow()

            # 强制同步到数据库
            self.force_progress_update(task_id)

            # 记录日志
            self.add_log(task_id, "任务执行完成", "info")

            # 计算执行时长
            if task.started_at:
                duration = (task.completed_at - task.started_at).total_seconds()
                print(f"[AsyncTaskManager] ✅ 任务 {task_id[:8]}... 执行完成 | "
                      f"类型: {task.task_type} | 耗时: {duration:.2f}秒")
            else:
                print(f"[AsyncTaskManager] ✅ 任务 {task_id[:8]}... 执行完成 | 类型: {task.task_type}")

        # 清理运行中的任务
        if task_id in self._running_tasks:
            del self._running_tasks[task_id]

        # 清理用户 ID 缓存
        if task_id in self._task_user_ids:
            del self._task_user_ids[task_id]

        # 清理进度缓存
        if task_id in self._progress_cache:
            del self._progress_cache[task_id]

        # 尝试启动等待队列中的下一个任务
        self._process_pending_queue()

    def fail_task(self, task_id: str, error: str):
        """标记任务失败

        Args:
            task_id: 任务 ID
            error: 错误信息
        """
        # 先刷新日志缓冲区，确保所有日志都被写入
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._flush_log_buffer())
        except RuntimeError:
            pass

        task = self._tasks.get(task_id)
        if task:
            task.status = AsyncTaskStatus.FAILED
            task.error = error
            task.completed_at = datetime.utcnow()

            # 强制同步到数据库
            self.force_progress_update(task_id)

            # 记录日志
            self.add_log(task_id, f"任务执行失败: {error}", "error")

            # 计算执行时长
            if task.started_at:
                duration = (task.completed_at - task.started_at).total_seconds()
                print(f"[AsyncTaskManager] ❌ 任务 {task_id[:8]}... 执行失败 | "
                      f"类型: {task.task_type} | 耗时: {duration:.2f}秒 | 错误: {error}")
            else:
                print(f"[AsyncTaskManager] ❌ 任务 {task_id[:8]}... 执行失败 | "
                      f"类型: {task.task_type} | 错误: {error}")

        # 清理运行中的任务
        if task_id in self._running_tasks:
            del self._running_tasks[task_id]

        # 清理用户 ID 缓存
        if task_id in self._task_user_ids:
            del self._task_user_ids[task_id]

        # 清理进度缓存
        if task_id in self._progress_cache:
            del self._progress_cache[task_id]

        # 尝试启动等待队列中的下一个任务
        self._process_pending_queue()

    def timeout_task(self, task_id: str):
        """标记任务超时

        当任务执行时间超过配置的超时时间时调用

        Args:
            task_id: 任务 ID
        """
        # 先刷新日志缓冲区，确保所有日志都被写入
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._flush_log_buffer())
        except RuntimeError:
            pass

        task = self._tasks.get(task_id)
        if task:
            task.status = AsyncTaskStatus.TIMEOUT
            task.error = f"任务执行超时（超过{self._task_timeout}秒）"
            task.completed_at = datetime.utcnow()

            # 强制同步到数据库
            self.force_progress_update(task_id)

            # 记录日志
            self.add_log(task_id, f"任务执行超时（超过{self._task_timeout}秒）", "error")

            # 添加控制台日志输出
            print(f"❌ [AsyncTaskManager] 任务 {task_id} 执行超时（超过{self._task_timeout}秒）")

        # 取消正在运行的 asyncio 任务
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]

        # 清理用户 ID 缓存
        if task_id in self._task_user_ids:
            del self._task_user_ids[task_id]

        # 清理进度缓存
        if task_id in self._progress_cache:
            del self._progress_cache[task_id]

        # 尝试启动等待队列中的下一个任务
        self._process_pending_queue()

    def cancel_task(self, task_id: str):
        """取消任务

        Args:
            task_id: 任务 ID
        """
        task = self._tasks.get(task_id)
        if task:
            task.status = AsyncTaskStatus.CANCELLED
            task.completed_at = datetime.utcnow()

            # 同步到数据库
            self._sync_to_db(task_id, task)

            # 记录日志
            self.add_log(task_id, "任务已取消", "warning")

        # 从等待队列中移除
        if task_id in self._pending_queue:
            self._pending_queue.remove(task_id)

        # 取消正在运行的 asyncio 任务
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]

        # 清理用户 ID 缓存
        if task_id in self._task_user_ids:
            del self._task_user_ids[task_id]

        # 尝试启动等待队列中的下一个任务
        self._process_pending_queue()

    def register_running_task(self, task_id: str, asyncio_task: asyncio.Task):
        """注册正在运行的 asyncio 任务

        Args:
            task_id: 任务 ID
            asyncio_task: asyncio 任务对象
        """
        self._running_tasks[task_id] = asyncio_task
    
    async def execute_with_timeout(self, task_id: str, coro) -> Any:
        """执行任务并应用超时限制
        
        Args:
            task_id: 任务ID
            coro: 要执行的协程
            
        Returns:
            协程的返回值
            
        Raises:
            asyncio.TimeoutError: 当任务超时时抛出
        """
        try:
            result = await asyncio.wait_for(coro, timeout=self._task_timeout)
            return result
        except asyncio.TimeoutError:
            self.timeout_task(task_id)
            raise
    
    def _process_pending_queue(self):
        """处理等待队列中的任务

        当有任务完成时调用，尝试启动等待队列中的下一个任务
        """
        while self._pending_queue and self.can_start_new_task():
            next_task_id = self._pending_queue[0]
            task = self._tasks.get(next_task_id)
            if task and task.status == AsyncTaskStatus.PENDING:
                # 任务仍在等待，可以启动
                self._pending_queue.pop(0)
                print(f"[AsyncTaskManager] ⏭️  从等待队列启动任务 {next_task_id[:8]}... | "
                      f"剩余队列: {len(self._pending_queue)}")
                # 注意：实际启动需要外部调用者处理
                break
            else:
                # 任务已被取消或状态改变，从队列移除
                self._pending_queue.pop(0)
    
    def get_next_pending_task(self) -> Optional[str]:
        """获取下一个等待执行的任务ID
        
        Returns:
            下一个等待执行的任务ID，如果队列为空或达到并发限制则返回None
        """
        if not self._pending_queue or not self.can_start_new_task():
            return None
        
        # 查找第一个仍在等待状态的任务
        for task_id in self._pending_queue:
            task = self._tasks.get(task_id)
            if task and task.status == AsyncTaskStatus.PENDING:
                return task_id
        
        return None
    
    def cleanup_completed_tasks(self):
        """清理所有已完成的任务（内存中）"""
        to_delete = []
        for task_id, task in self._tasks.items():
            if task.status in [
                AsyncTaskStatus.COMPLETED,
                AsyncTaskStatus.FAILED,
                AsyncTaskStatus.CANCELLED,
                AsyncTaskStatus.TIMEOUT
            ]:
                to_delete.append(task_id)

        for task_id in to_delete:
            del self._tasks[task_id]
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]
            if task_id in self._pending_queue:
                self._pending_queue.remove(task_id)

    async def shutdown(self) -> None:
        """优雅关闭任务管理器

        停止所有后台任务，取消正在运行的 AI 调用任务，
        并确保所有日志都被刷新到数据库。
        """
        print("[AsyncTaskManager] 开始关闭...")

        # 1. 取消所有正在运行的 AI 调用任务
        for task_id, asyncio_task in list(self._running_tasks.items()):
            print(f"[AsyncTaskManager] 取消任务: {task_id}")
            asyncio_task.cancel()
            try:
                await asyncio_task
            except asyncio.CancelledError:
                pass
        self._running_tasks.clear()

        # 2. 标记所有运行中的任务为取消状态
        for task_id, task in list(self._tasks.items()):
            if task.status == AsyncTaskStatus.RUNNING:
                task.status = AsyncTaskStatus.CANCELLED
                task.error = "服务关闭，任务被取消"
                task.completed_at = datetime.utcnow()
                # 同步到数据库（直接调用，不通过队列）
                await self._do_sync_to_db(task_id, task)

        # 3. 停止数据库写入工作线程（会先刷新日志缓冲区）
        await self._stop_db_worker()

        print("[AsyncTaskManager] 关闭完成")

    def add_step_log(
        self,
        task_id: str,
        step_name: str,
        step_number: int,
        total_steps: int,
        message: str,
        level: str = "info",
        duration_ms: int = None
    ) -> None:
        """记录步骤日志（便捷方法）

        Args:
            task_id: 任务 ID
            step_name: 步骤名称（如"需求拆分"、"测试点生成"）
            step_number: 步骤序号（从1开始）
            total_steps: 总步骤数
            message: 日志消息
            level: 日志级别
            duration_ms: 执行时长（毫秒）
        """
        self.add_log(
            task_id,
            message,
            level,
            step_name=step_name,
            step_number=step_number,
            total_steps=total_steps,
            duration_ms=duration_ms
        )

    def add_batch_log(
        self,
        task_id: str,
        current_batch: int,
        total_batches: int,
        message: str,
        level: str = "debug"
    ) -> None:
        """记录批次日志（便捷方法）

        Args:
            task_id: 任务 ID
            current_batch: 当前批次号（从1开始）
            total_batches: 总批次数
            message: 日志消息
            level: 日志级别（默认为 debug，可减少日志量）
        """
        self.add_log(
            task_id,
            message,
            level,
            current_batch=current_batch,
            total_batches=total_batches
        )

    def add_agent_log(
        self,
        task_id: str,
        agent_name: str,
        agent_type: str,
        model_name: str,
        provider: str,
        message: str,
        level: str = "info",
        estimated_tokens: int = None
    ) -> None:
        """记录智能体调用日志（便捷方法）

        Args:
            task_id: 任务 ID
            agent_name: 智能体名称（如"需求拆分 Agent"）
            agent_type: 智能体类型（如"REQUIREMENT_SPLITTER"）
            model_name: 模型名称（如"gpt-4-turbo-preview"）
            provider: 提供商（如"openai"、"anthropic"）
            message: 日志消息
            level: 日志级别
            estimated_tokens: 估算的 Token 数量
        """
        # 打印智能体调用日志
        print(f"[AsyncTaskManager] 🤖 任务 {task_id[:8]}... | "
              f"{agent_name}({agent_type}) | {model_name}@{provider} | {message}")

        self.add_log(
            task_id,
            message,
            level,
            agent_name=agent_name,
            agent_type=agent_type,
            model_name=model_name,
            provider=provider,
            estimated_tokens=estimated_tokens
        )

    def get_config_info(self) -> Dict[str, Any]:
        """获取当前配置信息
        
        Returns:
            配置信息字典
        """
        return {
            "max_concurrent_tasks": self._max_concurrent_tasks,
            "task_timeout": self._task_timeout,
            "retry_count": self._retry_count,
            "queue_size": self._queue_size,
            "config_loaded": self._config_loaded,
            "running_tasks": self.get_running_task_count(),
            "pending_tasks": self.get_pending_task_count()
        }


# 全局任务管理器实例
task_manager = AsyncTaskManager()
