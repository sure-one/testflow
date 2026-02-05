/**
 * 异步任务管理 API
 */
import request from './index'

export interface TaskListParams {
  status?: string
  task_type?: string
  user_id?: number
  page?: number
  page_size?: number
  sort_by?: string
  order?: 'asc' | 'desc'
}

export interface TaskListResponse {
  tasks: TaskItem[]
  total: number
  page: number
  page_size: number
}

export interface TaskItem {
  id: number
  task_id: string
  task_type: string
  status: string
  progress: number
  total_batches: number
  completed_batches: number
  message: string | null
  result: any
  error: string | null
  user_id: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  user?: {
    id: number
    username: string
    email: string
  }
}

export interface TaskDetailResponse {
  task: TaskItem
  messages: any[]
}

export interface TaskLogItem {
  id: number
  task_id: string
  level: 'info' | 'warning' | 'error'
  message: string
  timestamp: string

  // 扩展字段（可选）
  step_name?: string
  step_number?: number
  total_steps?: number
  duration_ms?: number
  agent_name?: string
  agent_type?: string
  model_name?: string
  provider?: string
  estimated_tokens?: number
  current_batch?: number
  total_batches?: number
}

export interface TaskLogResponse {
  logs: TaskLogItem[]
  total: number
}

export const taskApi = {
  /**
   * 获取任务列表
   */
  getTasks(params?: TaskListParams): Promise<TaskListResponse> {
    return request.get('/tasks', { params })
  },

  /**
   * 获取任务详情
   */
  getTaskDetail(taskId: string): Promise<TaskDetailResponse> {
    return request.get(`/tasks/${taskId}`)
  },

  /**
   * 取消任务
   */
  cancelTask(taskId: string): Promise<{ success: boolean; message: string }> {
    return request.post(`/tasks/${taskId}/cancel`)
  },

  /**
   * 批量取消任务
   */
  batchCancelTasks(taskIds: string[]): Promise<{ success: boolean; cancelled_count: number; message: string }> {
    return request.post('/tasks/batch-cancel', { task_ids: taskIds })
  },

  /**
   * 清理旧任务
   */
  cleanupTasks(maxAgeHours: number = 24): Promise<{ success: boolean; deleted_count: number; message: string }> {
    return request.post('/tasks/cleanup', null, { params: { max_age_hours: maxAgeHours } })
  },

  /**
   * 获取任务统计信息
   */
  getTaskStats(): Promise<{ stats: Record<string, number>; total: number }> {
    return request.get('/tasks/stats')
  },

  /**
   * 获取任务日志
   */
  getTaskLogs(taskId: string): Promise<TaskLogResponse> {
    return request.get(`/tasks/${taskId}/logs`)
  }
}

export default taskApi
