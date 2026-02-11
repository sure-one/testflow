<template>
  <el-dialog
    v-model="visible"
    title="任务日志"
    width="800px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 统计面板 -->
    <div v-if="statistics" class="statistics-panel mb-4 p-4 bg-gray-50 rounded-lg">
      <div class="grid grid-cols-4 gap-4">
        <div class="text-center">
          <div class="text-2xl font-bold text-gray-900">{{ statistics.totalSteps }}</div>
          <div class="text-xs text-gray-500">总步骤</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-bold text-gray-900">{{ formatNumber(statistics.totalTokens) }}</div>
          <div class="text-xs text-gray-500">总 Token</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-bold text-gray-900">{{ formatDuration(statistics.totalDuration) }}</div>
          <div class="text-xs text-gray-500">总时长</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-bold text-gray-900">{{ statistics.totalBatches }}</div>
          <div class="text-xs text-gray-500">总批次</div>
        </div>
      </div>
    </div>

    <!-- 过滤器 -->
    <div class="flex items-center gap-4 mb-4">
      <el-select
        v-model="levelFilter"
        placeholder="日志级别"
        clearable
        style="width: 120px"
      >
        <el-option label="调试" value="debug" />
        <el-option label="信息" value="info" />
        <el-option label="警告" value="warning" />
        <el-option label="错误" value="error" />
      </el-select>
      <span class="text-sm text-gray-500">
        共 {{ filteredLogs.length }} 条日志
      </span>
    </div>

    <!-- 日志列表 -->
    <div v-loading="loading" class="log-container">
      <el-empty v-if="filteredLogs.length === 0" description="暂无日志" />
      <el-timeline v-else>
        <el-timeline-item
          v-for="log in filteredLogs"
          :key="log.id"
          :type="getLogType(log.level)"
          :timestamp="formatDateTime(log.timestamp)"
          placement="top"
        >
          <!-- 增强的日志卡片 -->
          <div class="log-card">
            <!-- 基本信息 -->
            <div class="flex items-start gap-2 mb-2">
              <el-tag :type="getLogTagType(log.level)" size="small">
                {{ getLogLevelLabel(log.level) }}
              </el-tag>
              <span class="log-message flex-1">{{ log.message }}</span>
            </div>

            <!-- 扩展信息 -->
            <div v-if="hasExtendedInfo(log)" class="extended-info mt-2 pt-2 border-t border-gray-100">
              <!-- 步骤信息 -->
              <div v-if="log.step_name" class="flex items-center gap-2 text-xs text-gray-600 mb-1">
                <el-icon><Location /></el-icon>
                <span>步骤 {{ log.step_number }}/{{ log.total_steps }}：{{ log.step_name }}</span>
              </div>

              <!-- 智能体信息 -->
              <div v-if="log.agent_name" class="flex items-center gap-2 text-xs text-gray-600 mb-1">
                <el-icon><User /></el-icon>
                <span>{{ log.agent_name }}</span>
                <el-tag size="small" type="info">{{ log.model_name }}</el-tag>
                <span class="text-gray-400">({{ log.provider }})</span>
              </div>

              <!-- Token 信息 -->
              <div v-if="log.estimated_tokens" class="flex items-center gap-2 text-xs text-gray-600 mb-1">
                <el-icon><Coin /></el-icon>
                <span>约 {{ formatNumber(log.estimated_tokens) }} Token</span>
              </div>

              <!-- 批次信息 -->
              <div v-if="log.current_batch" class="flex items-center gap-2 text-xs text-gray-600 mb-1">
                <el-icon><Files /></el-icon>
                <span>批次 {{ log.current_batch }}/{{ log.total_batches }}</span>
              </div>

              <!-- 执行时长 -->
              <div v-if="log.duration_ms" class="flex items-center gap-2 text-xs text-gray-600">
                <el-icon><Clock /></el-icon>
                <span>{{ formatDuration(log.duration_ms) }}</span>
              </div>
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>
    </div>

    <template #footer>
      <el-button @click="handleClose">关闭</el-button>
      <el-button type="primary" @click="handleRefresh">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Refresh, Location, User, Coin, Files, Clock } from '@element-plus/icons-vue'
import { taskApi, type TaskLogItem, type TaskItem } from '@/api/task'
import { formatDateTime } from '@/utils/date'

interface Props {
  modelValue: boolean
  taskId: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const loading = ref(false)
const logs = ref<TaskLogItem[]>([])
const taskDetail = ref<TaskItem | null>(null)
const levelFilter = ref<string | null>(null)

const filteredLogs = computed(() => {
  if (!levelFilter.value) {
    return logs.value
  }
  return logs.value.filter(log => log.level === levelFilter.value)
})

// 统计信息
const statistics = computed(() => {
  if (logs.value.length === 0) return null

  let totalTokens = 0
  let totalSteps = 0
  let totalBatches = 0

  logs.value.forEach(log => {
    if (log.estimated_tokens != null) totalTokens += log.estimated_tokens
    if (log.step_number != null) totalSteps = Math.max(totalSteps, log.step_number)
    if (log.total_batches != null) totalBatches = Math.max(totalBatches, log.total_batches)
  })

  // 使用任务的 started_at 和 completed_at 计算总时长
  // 如果任务失败（没有 completed_at），使用最后一条日志的时间戳
  let totalDuration = 0
  if (taskDetail.value?.started_at) {
    const start = new Date(taskDetail.value.started_at).getTime()
    let endTime: number

    if (taskDetail.value.completed_at) {
      // 任务正常完成
      endTime = new Date(taskDetail.value.completed_at).getTime()
    } else if (logs.value.length > 0) {
      // 任务失败或未完成，使用最后一条日志的时间戳
      endTime = new Date(logs.value[0].timestamp).getTime()
    } else {
      // 没有日志，无法计算
      endTime = Date.now()
    }

    totalDuration = endTime - start
  }

  return {
    totalSteps,
    totalTokens,
    totalDuration,
    totalBatches
  }
})

const fetchLogs = async () => {
  if (!props.taskId) return

  loading.value = true
  try {
    const [logsRes, taskRes] = await Promise.all([
      taskApi.getTaskLogs(props.taskId),
      taskApi.getTaskDetail(props.taskId)
    ])
    logs.value = logsRes.logs
    taskDetail.value = taskRes.task
  } catch (error) {
    console.error('获取任务日志失败:', error)
  } finally {
    loading.value = false
  }
}

const handleClose = () => {
  visible.value = false
  logs.value = []
  levelFilter.value = null
}

const handleRefresh = () => {
  fetchLogs()
}

const getLogType = (level: string) => {
  const types: Record<string, string> = {
    info: 'primary',
    warning: 'warning',
    error: 'danger'
  }
  return types[level] || 'primary'
}

const getLogTagType = (level: string) => {
  const types: Record<string, string> = {
    info: 'info',
    warning: 'warning',
    error: 'danger'
  }
  return types[level] || 'info'
}

const getLogLevelLabel = (level: string) => {
  const labels: Record<string, string> = {
    debug: '调试',
    info: '信息',
    warning: '警告',
    error: '错误'
  }
  return labels[level] || level
}

// 检查日志是否有扩展信息
const hasExtendedInfo = (log: TaskLogItem) => {
  return !!(
    log.step_name ||
    log.agent_name ||
    log.estimated_tokens ||
    log.current_batch ||
    log.duration_ms
  )
}

// 格式化数字
const formatNumber = (num: number) => {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return num.toString()
}

// 格式化时长
const formatDuration = (ms: number) => {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const minutes = Math.floor(ms / 60000)
  const seconds = Math.floor((ms % 60000) / 1000)
  return `${minutes}m ${seconds}s`
}

// 监听对话框打开
watch(() => props.modelValue, (newValue) => {
  if (newValue && props.taskId) {
    fetchLogs()
  }
})
</script>

<style scoped>
.log-container {
  max-height: 500px;
  overflow-y: auto;
}

.log-card {
  background: white;
  border-radius: 8px;
  padding: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.log-message {
  word-break: break-word;
  line-height: 1.5;
}

.extended-info {
  font-size: 12px;
}

.statistics-panel {
  border: 1px solid #e5e7eb;
}

:deep(.el-timeline-item__timestamp) {
  font-size: 12px;
}
</style>
