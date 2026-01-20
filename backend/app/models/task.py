"""
异步任务持久化模型
用于将异步任务状态持久化到数据库，解决服务重启任务丢失问题
"""
from typing import Optional, Dict, Any
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
