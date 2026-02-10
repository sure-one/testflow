<template>
  <div class="h-full flex flex-col p-6">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h2 class="text-2xl font-bold text-gray-800">异步任务管理</h2>
      <p class="text-gray-500 mt-1">实时监控和管理系统中的所有异步任务</p>
    </div>

    <!-- 统计卡片 -->
    <div class="grid grid-cols-5 gap-4 mb-6">
      <div class="glass-card rounded-xl p-4 border-l-4 border-blue-500">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">等待中</p>
            <p class="text-2xl font-bold text-gray-800">{{ stats.pending }}</p>
          </div>
          <el-icon class="text-gray-400 text-3xl"><Clock /></el-icon>
        </div>
      </div>

      <div class="glass-card rounded-xl p-4 border-l-4 border-blue-600">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">运行中</p>
            <p class="text-2xl font-bold text-blue-600">{{ stats.running }}</p>
          </div>
          <el-icon class="text-blue-600 text-3xl"><Loading /></el-icon>
        </div>
      </div>

      <div class="glass-card rounded-xl p-4 border-l-4 border-green-500">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">已完成</p>
            <p class="text-2xl font-bold text-green-600">{{ stats.completed }}</p>
          </div>
          <el-icon class="text-green-600 text-3xl"><CircleCheck /></el-icon>
        </div>
      </div>

      <div class="glass-card rounded-xl p-4 border-l-4 border-red-500">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">失败</p>
            <p class="text-2xl font-bold text-red-600">{{ stats.failed }}</p>
          </div>
          <el-icon class="text-red-600 text-3xl"><CircleClose /></el-icon>
        </div>
      </div>

      <div class="glass-card rounded-xl p-4 border-l-4 border-gray-400">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">总任务</p>
            <p class="text-2xl font-bold text-gray-800">{{ stats.total }}</p>
          </div>
          <el-icon class="text-gray-600 text-3xl"><List /></el-icon>
        </div>
      </div>
    </div>

    <!-- 主内容区域 -->
    <div class="glass-card rounded-3xl p-6 flex-1">
      <el-tabs v-model="activeTab" class="task-tabs">
        <el-tab-pane label="全部任务" name="all">
          <TaskList :status="null" @edit-result="handleEditResult" />
        </el-tab-pane>
        <el-tab-pane label="等待中" name="pending">
          <TaskList status="pending" @edit-result="handleEditResult" />
        </el-tab-pane>
        <el-tab-pane label="运行中" name="running">
          <TaskList status="running" @edit-result="handleEditResult" />
        </el-tab-pane>
        <el-tab-pane label="已完成" name="completed">
          <TaskList status="completed" @edit-result="handleEditResult" />
        </el-tab-pane>
        <el-tab-pane label="已失败" name="failed">
          <TaskList status="failed" @edit-result="handleEditResult" />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 需求点编辑对话框 -->
    <RequirementPointsEditDialog
      v-model:visible="showEditDialog"
      :taskResult="currentTaskResult"
      :projectId="currentProjectId"
      :moduleId="currentModuleId"
      :fileId="currentFileId"
      @saved="handlePointsSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Clock, Loading, CircleCheck, CircleClose, List } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import TaskList from '@/components/task/TaskList.vue'
import RequirementPointsEditDialog from '@/components/task/RequirementPointsEditDialog.vue'
import { useTaskStore } from '@/stores/task'

const taskStore = useTaskStore()
const activeTab = ref('all')

const stats = computed(() => taskStore.stats)

// 需求点编辑对话框状态
const showEditDialog = ref(false)
const currentTaskResult = ref<any>(null)
const currentProjectId = ref<number>(0)
const currentModuleId = ref<number>(0)
const currentFileId = ref<number>(0)

// 处理编辑结果
const handleEditResult = async (task: any) => {
  try {
    // 从任务结果中获取项目、模块、文件信息
    const params = task.request_params || {}
    currentTaskResult.value = task.result
    currentProjectId.value = params.project_id || 1
    currentModuleId.value = params.module_id || 1
    currentFileId.value = params.file_id || 1
    showEditDialog.value = true
  } catch (error: any) {
    ElMessage.error('获取任务结果失败')
  }
}

// 处理保存成功
const handlePointsSaved = () => {
  ElMessage.success('需求点保存成功')
  // 刷新任务列表
  taskStore.fetchTasks()
}

onMounted(() => {
  taskStore.fetchTasks()
})
</script>

<style scoped>
.task-tabs :deep(.el-tabs__content) {
  height: 100%;
}

.task-tabs :deep(.el-tab-pane) {
  height: 100%;
}
</style>
