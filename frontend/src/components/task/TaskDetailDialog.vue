<template>
  <el-dialog
    v-model="visible"
    title="任务详情"
    width="700px"
    :close-on-click-modal="false"
  >
    <div v-loading="loading">
      <!-- 基本信息 -->
      <div class="detail-section">
        <h4 class="section-title">基本信息</h4>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务 ID">
            <el-text class="font-mono">{{ task?.task_id }}</el-text>
          </el-descriptions-item>
          <el-descriptions-item label="任务名称">
            {{ task?.task_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="任务类型">
            <el-tag :type="getTaskTypeColor(task?.task_type)">
              {{ getTaskTypeLabel(task?.task_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusColor(task?.status)">
              {{ getStatusLabel(task?.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="进度">
            <div class="flex items-center gap-2">
              <el-progress
                :percentage="task?.progress || 0"
                :status="getProgressStatus(task?.status)"
                :stroke-width="8"
                style="width: 120px"
              />
              <span class="text-sm">{{ task?.progress || 0 }}%</span>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="创建者">
            {{ task?.user?.username || '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 时间信息 -->
      <div class="detail-section">
        <h4 class="section-title">时间信息</h4>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="创建时间">
            {{ task?.created_at ? formatDateTime(task.created_at) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">
            {{ task?.started_at ? formatDateTime(task.started_at) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="完成时间">
            {{ task?.completed_at ? formatDateTime(task.completed_at) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="执行时长">
            {{ getExecutionDuration() }}
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 请求参数 -->
      <div class="detail-section">
        <h4 class="section-title">请求参数</h4>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="参数详情">
            <pre class="params-json">{{ JSON.stringify(task?.request_params, null, 2) }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 错误信息 -->
      <div v-if="task?.error" class="detail-section">
        <h4 class="section-title">错误信息</h4>
        <el-alert type="error" :closable="false">
          {{ task.error }}
        </el-alert>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleClose">关闭</el-button>
      <el-button type="primary" @click="handleViewLogs">
        <el-icon><Document /></el-icon>
        查看日志
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { taskApi, type TaskItem } from '@/api/task'
import { formatDateTime } from '@/utils/date'

interface Props {
  modelValue: boolean
  taskId: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'view-logs', taskId: string): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const loading = ref(false)
const task = ref<TaskItem | null>(null)

const fetchTaskDetail = async () => {
  if (!props.taskId) return

  loading.value = true
  try {
    const response = await taskApi.getTaskDetail(props.taskId)
    task.value = response.task
  } catch (error) {
    console.error('获取任务详情失败:', error)
  } finally {
    loading.value = false
  }
}

const getTaskTypeLabel = (type?: string) => {
  if (!type) return '-'
  const labels: Record<string, string> = {
    requirement_analysis: '需求点生成',
    test_point_generation: '测试点生成',
    test_case_design: '测试用例设计',
    test_case_optimization: '测试用例优化'
  }
  return labels[type] || type
}

const getTaskTypeColor = (type?: string) => {
  if (!type) return undefined
  const colors: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    requirement_analysis: 'info',
    test_point_generation: 'primary',
    test_case_design: 'success',
    test_case_optimization: 'warning'
  }
  return (colors[type] || 'info') as any
}

const getStatusLabel = (status?: string) => {
  if (!status) return '-'
  const labels: Record<string, string> = {
    pending: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    timeout: '超时'
  }
  return labels[status] || status
}

const getStatusColor = (status?: string) => {
  if (!status) return undefined
  const colors: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    pending: 'info',
    running: 'primary',
    completed: 'success',
    failed: 'danger',
    cancelled: 'warning',
    timeout: 'danger'
  }
  return (colors[status] || 'info') as any
}

const getProgressStatus = (status?: string) => {
  if (!status) return undefined
  if (status === 'completed') return 'success'
  if (['failed', 'cancelled', 'timeout'].includes(status)) return 'exception'
  return undefined
}

const getExecutionDuration = () => {
  if (!task.value?.started_at) return '-'
  const endTime = task.value.completed_at
    ? new Date(task.value.completed_at).getTime()
    : Date.now()
  const startTime = new Date(task.value.started_at).getTime()
  const duration = endTime - startTime

  if (duration < 60000) return `${Math.floor(duration / 1000)}秒`
  if (duration < 3600000) return `${Math.floor(duration / 60000)}分钟`
  const hours = Math.floor(duration / 3600000)
  const minutes = Math.floor((duration % 3600000) / 60000)
  return `${hours}小时${minutes}分钟`
}

const handleClose = () => {
  visible.value = false
  task.value = null
}

const handleViewLogs = () => {
  if (props.taskId) {
    emit('view-logs', props.taskId)
  }
}

watch(() => props.modelValue, (newValue) => {
  if (newValue && props.taskId) {
    fetchTaskDetail()
  }
})
</script>

<style scoped>
.detail-section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
}

.params-json {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 400px;
  overflow-y: auto;
  margin: 0;
  word-break: break-all;
  white-space: pre-wrap;
}

.font-mono {
  font-family: 'Courier New', monospace;
}
</style>
