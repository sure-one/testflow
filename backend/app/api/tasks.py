"""
异步任务管理 API
提供任务的列表查询、详情查看、批量操作等功能
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.database import get_db
from app.core.dependencies import get_current_admin_user
from app.models.user import User
from app.models.task import AsyncTask, AsyncTaskStatus, AsyncTaskLog
from app.services.async_task_manager import task_manager


router = APIRouter()


# ============ 请求/响应模型 ============

class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: List[dict]
    total: int
    page: int
    page_size: int


class TaskDetailResponse(BaseModel):
    """任务详情响应"""
    task: dict
    messages: List[dict]  # 预留给任务日志


class BatchCancelRequest(BaseModel):
    """批量取消请求"""
    task_ids: List[str]


class BatchCancelResponse(BaseModel):
    """批量取消响应"""
    success: bool
    cancelled_count: int
    message: str


class CleanupResponse(BaseModel):
    """清理任务响应"""
    success: bool
    deleted_count: int
    message: str


class TaskLogResponse(BaseModel):
    """任务日志响应"""
    logs: List[dict]
    total: int


# ============ API 端点 ============

@router.get("", response_model=TaskListResponse)
@router.get("/", response_model=TaskListResponse)
async def get_tasks(
    status: Optional[str] = Query(None, description="按状态过滤"),
    task_type: Optional[str] = Query(None, description="按任务类型过滤"),
    user_id: Optional[int] = Query(None, description="按用户 ID 过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    sort_by: str = Query("created_at", description="排序字段"),
    order: str = Query("desc", pattern="^(asc|desc)$", description="排序方向"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """获取任务列表（管理员专用）

    支持按状态、类型、用户过滤，支持排序和分页
    """
    # 构建查询
    query = db.query(AsyncTask)

    if status:
        try:
            status_enum = AsyncTaskStatus(status)
            query = query.filter(AsyncTask.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"无效的状态值: {status}"
            )

    if task_type:
        query = query.filter(AsyncTask.task_type == task_type)

    if user_id:
        query = query.filter(AsyncTask.user_id == user_id)

    # 排序
    order_column = getattr(AsyncTask, sort_by, AsyncTask.created_at)
    if order == "desc":
        query = query.order_by(order_column.desc())
    else:
        query = query.order_by(order_column.asc())

    # 分页
    total = query.count()
    offset = (page - 1) * page_size
    tasks = query.offset(offset).limit(page_size).all()

    return TaskListResponse(
        tasks=[task.to_dict_with_user() for task in tasks],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task_detail(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """获取任务详情（管理员专用）"""
    task = db.query(AsyncTask).filter(AsyncTask.task_id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}"
        )

    return TaskDetailResponse(
        task=task.to_dict_with_user(),
        messages=[]  # 预留：未来可以添加任务日志
    )


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """取消单个任务（管理员专用）

    取消指定任务（仅 PENDING 或 RUNNING 状态的任务可以被取消）
    """
    # 检查任务是否在内存中
    task = task_manager.get_task(task_id)
    if task and task.status in [
        AsyncTaskStatus.PENDING,
        AsyncTaskStatus.RUNNING
    ]:
        task_manager.cancel_task(task_id)
        db.commit()
        return {"success": True, "message": f"任务 {task_id} 已取消"}

    # 如果任务不在内存中，检查数据库
    db_task = db.query(AsyncTask).filter(
        AsyncTask.task_id == task_id
    ).first()

    if not db_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}"
        )

    if db_task.status in [
        AsyncTaskStatus.PENDING,
        AsyncTaskStatus.RUNNING
    ]:
        db_task.status = AsyncTaskStatus.CANCELLED
        db_task.completed_at = func.now()
        db.commit()
        return {"success": True, "message": f"任务 {task_id} 已取消"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务状态为 {db_task.status.value}，无法取消"
        )


@router.post("/batch-cancel", response_model=BatchCancelResponse)
async def batch_cancel_tasks(
    request: BatchCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """批量取消任务（管理员专用）

    取消所有处于 PENDING 或 RUNNING 状态的任务
    """
    cancelled_count = 0

    for task_id in request.task_ids:
        # 检查任务是否在内存中
        task = task_manager.get_task(task_id)
        if task and task.status in [
            AsyncTaskStatus.PENDING,
            AsyncTaskStatus.RUNNING
        ]:
            task_manager.cancel_task(task_id)
            cancelled_count += 1
        else:
            # 如果任务不在内存中，检查数据库
            db_task = db.query(AsyncTask).filter(
                AsyncTask.task_id == task_id
            ).first()
            if db_task and db_task.status in [
                AsyncTaskStatus.PENDING,
                AsyncTaskStatus.RUNNING
            ]:
                db_task.status = AsyncTaskStatus.CANCELLED
                db_task.completed_at = db_task.completed_at or db.func.now()
                cancelled_count += 1

    db.commit()

    return BatchCancelResponse(
        success=True,
        cancelled_count=cancelled_count,
        message=f"成功取消 {cancelled_count} 个任务"
    )


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_old_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """清理已完成任务（管理员专用）

    删除所有已完成、失败、取消、超时的任务
    """
    # 删除所有终态任务
    deleted_count = db.query(AsyncTask).filter(
        AsyncTask.status.in_([
            AsyncTaskStatus.COMPLETED,
            AsyncTaskStatus.FAILED,
            AsyncTaskStatus.CANCELLED,
            AsyncTaskStatus.TIMEOUT
        ])
    ).delete()

    db.commit()

    # 同时清理内存中的任务
    task_manager.cleanup_completed_tasks()

    return CleanupResponse(
        success=True,
        deleted_count=deleted_count,
        message=f"已清理 {deleted_count} 个任务"
    )


@router.get("/stats")
async def get_task_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """获取任务统计信息（管理员专用）"""
    from sqlalchemy import func

    stats = db.query(
        AsyncTask.status,
        func.count(AsyncTask.id).label('count')
    ).group_by(AsyncTask.status).all()

    return {
        "stats": {
            status.value: count for status, count in stats
        },
        "total": sum(count for _, count in stats)
    }


@router.get("/{task_id}/logs", response_model=TaskLogResponse)
async def get_task_logs(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """获取任务日志（管理员专用）

    返回指定任务的所有日志记录，按时间倒序排列
    """
    # 检查任务是否存在
    task = db.query(AsyncTask).filter(AsyncTask.task_id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}"
        )

    # 获取日志
    logs = db.query(AsyncTaskLog).filter(
        AsyncTaskLog.task_id == task_id
    ).order_by(AsyncTaskLog.timestamp.desc()).all()

    return TaskLogResponse(
        logs=[log.to_dict() for log in logs],
        total=len(logs)
    )
