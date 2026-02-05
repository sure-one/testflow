<template>
  <el-dialog
    v-model="visible"
    title="任务日志"
    width="700px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 过滤器 -->
    <div class="flex items-center gap-4 mb-4">
      <el-select
        v-model="levelFilter"
        placeholder="日志级别"
        clearable
        style="width: 120px"
      >
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
          <div class="flex items-start gap-2">
            <el-tag :type="getLogTagType(log.level)" size="small">
              {{ getLogLevelLabel(log.level) }}
            </el-tag>
            <span class="log-message">{{ log.message }}</span>
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
import { Refresh } from '@element-plus/icons-vue'
import { taskApi, type TaskLogItem } from '@/api/task'
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
const levelFilter = ref<string | null>(null)

const filteredLogs = computed(() => {
  if (!levelFilter.value) {
    return logs.value
  }
  return logs.value.filter(log => log.level === levelFilter.value)
})

const fetchLogs = async () => {
  if (!props.taskId) return

  loading.value = true
  try {
    const response = await taskApi.getTaskLogs(props.taskId)
    logs.value = response.logs
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
    info: '信息',
    warning: '警告',
    error: '错误'
  }
  return labels[level] || level
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
  max-height: 400px;
  overflow-y: auto;
}

.log-message {
  word-break: break-word;
  line-height: 1.5;
}

:deep(.el-timeline-item__timestamp) {
  font-size: 12px;
}
</style>
