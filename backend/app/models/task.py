"""
异步任务持久化模型
用于将异步任务状态持久化到数据库，解决服务重启任务丢失问题
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, Text, Enum as SQLEnum, Index, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class AsyncTaskStatus(str, Enum):
    """异步任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskLogLevel(str, Enum):
    """任务日志级别枚举

    级别顺序: DEBUG < INFO < WARNING < ERROR
    """
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AsyncTaskLog(Base):
    """异步任务日志模型

    用于记录异步任务执行过程中的日志信息
    """
    __tablename__ = "async_task_logs"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # 关联任务
    task_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("async_tasks.task_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 日志内容
    level: Mapped[TaskLogLevel] = mapped_column(
        SQLEnum(TaskLogLevel),
        default=TaskLogLevel.INFO
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # === 扩展字段：步骤信息 ===
    step_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="步骤名称")
    step_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="步骤序号(1-based)")
    total_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="总步骤数")

    # === 扩展字段：执行时长 ===
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="执行时长(毫秒)")

    # === 扩展字段：智能体和模型信息 ===
    agent_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="智能体名称")
    agent_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="智能体类型")
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="模型名称")
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="模型提供商")

    # === 扩展字段：Token 使用量 ===
    estimated_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="估算的Token数量")

    # === 扩展字段：批次处理进度 ===
    current_batch: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="当前批次号(1-based)")
    total_batches: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="总批次数")

    # 时间戳
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )

    # 关系
    task: Mapped["AsyncTask"] = relationship("AsyncTask", back_populates="logs")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（包含扩展字段）"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "level": self.level.value if isinstance(self.level, Enum) else self.level,
            "message": self.message,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            # 扩展字段
            "step_name": self.step_name,
            "step_number": self.step_number,
            "total_steps": self.total_steps,
            "duration_ms": self.duration_ms,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "model_name": self.model_name,
            "provider": self.provider,
            "estimated_tokens": self.estimated_tokens,
            "current_batch": self.current_batch,
            "total_batches": self.total_batches,
        }

    def __repr__(self) -> str:
        return f"<AsyncTaskLog(id={self.id}, task_id={self.task_id}, level={self.level})>"


class AsyncTask(Base):
    """异步任务持久化模型

    用于存储异步任务的状态、进度和结果信息
    """
    __tablename__ = "async_tasks"

    # 主键和基本字段
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[AsyncTaskStatus] = mapped_column(
        SQLEnum(AsyncTaskStatus),
        default=AsyncTaskStatus.PENDING,
        index=True
    )

    # 进度信息
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 进度百分比 (0-100)
    total_batches: Mapped[int] = mapped_column(Integer, default=1)  # 总批次数
    completed_batches: Mapped[int] = mapped_column(Integer, default=0)  # 已完成批次数
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 进度消息

    # 结果数据（JSON格式存储）
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 用户关联
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    creator: Mapped["User"] = relationship("User")

    # 日志关联
    logs: Mapped[List["AsyncTaskLog"]] = relationship(
        "AsyncTaskLog",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="AsyncTaskLog.timestamp.desc()"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 索引优化
    __table_args__ = (
        Index('idx_async_tasks_status_created', 'status', 'created_at'),
        Index('idx_async_tasks_user_status', 'user_id', 'status'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "progress": self.progress,
            "total_batches": self.total_batches,
            "completed_batches": self.completed_batches,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def to_dict_with_user(self) -> Dict[str, Any]:
        """转换为字典格式（包含用户信息）"""
        data = self.to_dict()
        data["user"] = {
            "id": self.creator.id,
            "username": self.creator.username,
            "email": self.creator.email
        }
        return data

    def __repr__(self) -> str:
        return f"<AsyncTask(id={self.id}, task_id={self.task_id}, status={self.status})>"
