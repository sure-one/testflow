<template>
  <div class="task-list h-full flex flex-col">
    <!-- 工具栏 -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-4">
        <el-select
          v-model="filters.taskType"
          placeholder="任务类型"
          clearable
          @change="handleFilterChange"
          style="width: 180px"
        >
          <el-option label="测试点生成" value="test_point_generation" />
          <el-option label="测试用例设计" value="test_case_design" />
          <el-option label="测试用例优化" value="test_case_optimization" />
        </el-select>

        <el-button type="primary" @click="handleRefresh">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>

        <el-button
          @click="handleCleanup"
          :disabled="!hasCompletedTasks"
          type="warning"
        >
          清理旧任务
        </el-button>
      </div>

      <div class="text-sm text-gray-500">
        共 {{ taskStore.total }} 个任务
      </div>
    </div>

    <!-- 任务表格 -->
    <div class="flex-1 overflow-hidden">
      <el-table
        v-loading="taskStore.loading"
        :data="taskStore.tasks"
        stripe
        height="100%"
        class="task-table"
      >
        <el-table-column prop="task_id" label="任务 ID" width="200">
          <template #default="{ row }">
            <el-text class="font-mono text-xs">{{ row.task_id.slice(0, 8) }}...</el-text>
          </template>
        </el-table-column>

        <el-table-column prop="task_type" label="类型" width="180">
          <template #default="{ row }">
            <el-tag :type="getTaskTypeColor(row.task_type)">
              {{ getTaskTypeLabel(row.task_type) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusColor(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="进度" width="200">
          <template #default="{ row }">
            <div class="flex items-center gap-2">
              <el-progress
                :percentage="row.progress"
                :status="getProgressStatus(row.status)"
                :stroke-width="8"
              />
              <span class="text-xs text-gray-500 w-8 text-right">{{ row.progress }}%</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="message" label="消息" min-width="250" show-overflow-tooltip />

        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column prop="user.username" label="创建者" width="120" />

        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              @click="handleViewLogs(row)"
            >
              <el-icon><Document /></el-icon>
              日志
            </el-button>
            <el-button
              v-if="canCancel(row.status)"
              link
              type="danger"
              size="small"
              @click="handleCancel(row)"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页 -->
    <div class="flex justify-end mt-4">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="taskStore.total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </div>

    <!-- 日志对话框 -->
    <TaskLogDialog
      v-model="logDialogVisible"
      :task-id="currentLogTaskId"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { Refresh, Document } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTaskStore } from '@/stores/task'
import { formatDateTime } from '@/utils/date'
import TaskLogDialog from './TaskLogDialog.vue'

interface Props {
  status?: string | null
}

const props = defineProps<Props>()
const taskStore = useTaskStore()

const filters = reactive({
  taskType: null as string | null,
  status: props.status
})

const pagination = reactive({
  page: 1,
  pageSize: 20
})

// 日志对话框状态
const logDialogVisible = ref(false)
const currentLogTaskId = ref<string | null>(null)

const hasCompletedTasks = computed(() => {
  return taskStore.tasks.some(t =>
    ['completed', 'failed', 'cancelled', 'timeout'].includes(t.status)
  )
})

const canCancel = (status: string) => {
  return ['pending', 'running'].includes(status)
}

const handleViewLogs = (row: any) => {
  currentLogTaskId.value = row.task_id
  logDialogVisible.value = true
}

const handleFilterChange = () => {
  pagination.page = 1
  taskStore.fetchTasks({
    ...filters,
    page: pagination.page,
    page_size: pagination.pageSize
  })
}

const handleRefresh = () => {
  taskStore.fetchTasks({
    ...filters,
    page: pagination.page,
    page_size: pagination.pageSize
  })
}

const handlePageChange = (page: number) => {
  taskStore.fetchTasks({
    ...filters,
    page,
    page_size: pagination.pageSize
  })
}

const handleSizeChange = (size: number) => {
  pagination.pageSize = size
  taskStore.fetchTasks({
    ...filters,
    page: 1,
    page_size: size
  })
}

const handleCancel = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要取消任务 "${row.task_id.slice(0, 8)}..." 吗？`,
      '取消任务',
      { type: 'warning' }
    )

    await taskStore.cancelTask(row.task_id)
  } catch (error) {
    // 用户取消操作
  }
}

const handleCleanup = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要清理所有已完成的任务吗？此操作不可恢复。',
      '清理任务',
      { type: 'warning' }
    )

    await taskStore.cleanupTasks(24)
    handleRefresh()
  } catch (error) {
    // 用户取消操作
  }
}

// 辅助函数
const getTaskTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    test_point_generation: '测试点生成',
    test_case_design: '测试用例设计',
    test_case_optimization: '测试用例优化'
  }
  return labels[type] || type
}

const getTaskTypeColor = (type: string) => {
  const colors: Record<string, string> = {
    test_point_generation: 'primary',
    test_case_design: 'success',
    test_case_optimization: 'warning'
  }
  return colors[type] || ''
}

const getStatusLabel = (status: string) => {
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

const getStatusColor = (status: string) => {
  const colors: Record<string, string> = {
    pending: 'info',
    running: 'primary',
    completed: 'success',
    failed: 'danger',
    cancelled: 'warning',
    timeout: 'danger'
  }
  return colors[status] || ''
}

const getProgressStatus = (status: string) => {
  if (status === 'completed') return 'success'
  if (['failed', 'cancelled', 'timeout'].includes(status)) return 'exception'
  return undefined
}

// 组件挂载时加载任务
onMounted(() => {
  taskStore.fetchTasks({
    ...filters,
    page: pagination.page,
    page_size: pagination.pageSize
  })
})
</script>

<style scoped>
.task-table :deep(.el-table__row) {
  cursor: pointer;
  transition: background-color 0.2s;
}

.task-table :deep(.el-table__row:hover) {
  background-color: #f5f5f5;
}

.task-table :deep(.el-table__cell) {
  padding: 8px 0;
}
</style>
