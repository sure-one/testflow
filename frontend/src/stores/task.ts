/**
 * 异步任务管理 Store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { taskApi, type TaskListParams, type TaskItem } from '@/api/task'
import { ElMessage } from 'element-plus'

export const useTaskStore = defineStore('task', () => {
  // 状态
  const tasks = ref<TaskItem[]>([])
  const currentTask = ref<TaskItem | null>(null)
  const loading = ref(false)
  const total = ref(0)

  const filters = ref<TaskListParams>({
    status: undefined,
    task_type: undefined,
    user_id: undefined,
    page: 1,
    page_size: 20,
    sort_by: 'created_at',
    order: 'desc'
  })

  // 计算属性
  const stats = computed(() => {
    return {
      running: tasks.value.filter(t => t.status === 'running').length,
      completed: tasks.value.filter(t => t.status === 'completed').length,
      failed: tasks.value.filter(t => t.status === 'failed').length,
      cancelled: tasks.value.filter(t => t.status === 'cancelled').length,
      pending: tasks.value.filter(t => t.status === 'pending').length,
      total: total.value
    }
  })

  // 请求缓存
  const cache = ref<Map<string, { data: TaskListResponse; timestamp: number }>>(new Map())
  const CACHE_TTL = 5000  // 缓存5秒

  // 方法
  const fetchTasks = async (params?: TaskListParams, forceRefresh = false) => {
    // 生成缓存键
    const cacheKey = JSON.stringify({ ...filters.value, ...params })

    // 检查缓存
    if (!forceRefresh && cache.value.has(cacheKey)) {
      const cached = cache.value.get(cacheKey)
      if (Date.now() - cached.timestamp < CACHE_TTL) {
        tasks.value = cached.data.tasks
        total.value = cached.data.total
        return
      }
    }

    loading.value = true
    try {
      const response = await taskApi.getTasks({
        ...filters.value,
        ...params
      })

      tasks.value = response.tasks
      total.value = response.total

      // 更新缓存
      cache.value.set(cacheKey, {
        data: response,
        timestamp: Date.now()
      })

      if (params) {
        if (params.page !== undefined) filters.value.page = params.page
        if (params.page_size !== undefined) filters.value.page_size = params.page_size
        if (params.status !== undefined) filters.value.status = params.status
        if (params.task_type !== undefined) filters.value.task_type = params.task_type
        if (params.user_id !== undefined) filters.value.user_id = params.user_id
      }
    } catch (error) {
      ElMessage.error('获取任务列表失败')
      console.error(error)
    } finally {
      loading.value = false
    }
  }

  const fetchTaskDetail = async (taskId: string) => {
    loading.value = true
    try {
      const response = await taskApi.getTaskDetail(taskId)
      currentTask.value = response.task
      return response
    } catch (error) {
      ElMessage.error('获取任务详情失败')
      console.error(error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const cancelTask = async (taskId: string) => {
    try {
      await taskApi.cancelTask(taskId)

      // 乐观更新
      const task = tasks.value.find(t => t.task_id === taskId)
      if (task) {
        task.status = 'cancelled'
      }

      ElMessage.success('任务已取消')
      return true
    } catch (error) {
      ElMessage.error('取消任务失败')
      console.error(error)
      return false
    }
  }

  const batchCancelTasks = async (taskIds: string[]) => {
    try {
      const response = await taskApi.batchCancelTasks(taskIds)

      // 乐观更新
      taskIds.forEach(taskId => {
        const task = tasks.value.find(t => t.task_id === taskId)
        if (task) {
          task.status = 'cancelled'
        }
      })

      ElMessage.success(response.message)
      return response.cancelled_count
    } catch (error) {
      ElMessage.error('批量取消任务失败')
      console.error(error)
      return 0
    }
  }

  const cleanupTasks = async (maxAgeHours: number = 24) => {
    try {
      const response = await taskApi.cleanupTasks(maxAgeHours)
      ElMessage.success(response.message)
      await fetchTasks(undefined, true)  // 强制刷新并清除缓存
    } catch (error) {
      ElMessage.error('清理任务失败')
      console.error(error)
    }
  }

  const clearCache = () => {
    cache.value.clear()
  }

  const updateTask = (taskId: string, updates: Partial<TaskItem>) => {
    const index = tasks.value.findIndex(t => t.task_id === taskId)
    if (index !== -1) {
      tasks.value[index] = { ...tasks.value[index], ...updates }
    }

    if (currentTask.value?.task_id === taskId) {
      currentTask.value = { ...currentTask.value, ...updates }
    }
  }

  return {
    // 状态
    tasks,
    currentTask,
    loading,
    total,
    filters,

    // 计算属性
    stats,

    // 方法
    fetchTasks,
    fetchTaskDetail,
    cancelTask,
    batchCancelTasks,
    cleanupTasks,
    clearCache,
    updateTask
  }
})
