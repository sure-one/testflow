<template>
  <el-dialog
    v-model="dialogVisible"
    title="需求点结果编辑"
    width="900px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 元信息 -->
    <div class="mb-4 p-4 bg-gray-50 rounded-xl">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
          <span class="text-lg font-bold">共 {{ editablePoints.length }} 个需求点</span>
          <el-tag v-if="hasImages" type="info">
            包含 {{ imageCount }} 张图片分析
          </el-tag>
        </div>
        <div class="flex gap-2">
          <el-button size="small" @click="addPoint">添加需求点</el-button>
        </div>
      </div>
    </div>

    <!-- 需求点编辑列表 -->
    <div class="points-list mb-4" style="max-height: 400px; overflow-y: auto;">
      <div
        v-for="(point, index) in editablePoints"
        :key="index"
        class="point-item p-4 bg-white border rounded-lg mb-3"
      >
        <div class="flex items-start gap-4">
          <!-- 序号 -->
          <div class="flex-shrink-0 w-10 h-10 bg-blue-100 text-blue-600 rounded-lg flex items-center justify-center font-bold">
            {{ index + 1 }}
          </div>

          <!-- 编辑区域 -->
          <div class="flex-1 space-y-3">
            <el-input
              v-model="point.content"
              type="textarea"
              :rows="2"
              placeholder="需求点内容"
              resize="none"
            />

            <div class="flex items-center gap-3">
              <el-select v-model="point.priority" size="small" style="width: 120px">
                <el-option label="高优先级" value="high" />
                <el-option label="中优先级" value="medium" />
                <el-option label="低优先级" value="low" />
              </el-select>

              <el-button
                size="small"
                type="danger"
                link
                @click="removePoint(index)"
              >
                删除
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="editablePoints.length === 0" class="text-center py-8 text-gray-400">
        <p>暂无需求点，请添加</p>
      </div>
    </div>

    <!-- 保存中状态 -->
    <div v-if="saving" class="absolute inset-0 bg-white/80 flex items-center justify-center z-10 rounded-lg">
      <div class="text-center">
        <el-icon class="is-loading text-4xl text-blue-500 mb-4"><Loading /></el-icon>
        <p class="text-gray-600">正在保存需求点...</p>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-between items-center">
        <el-checkbox v-model="clearExisting">清空现有需求点</el-checkbox>
        <div class="flex gap-3">
          <el-button @click="handleCancel">取消</el-button>
          <el-button
            type="primary"
            @click="handleSave"
            :loading="saving"
            :disabled="editablePoints.length === 0"
          >
            保存需求点
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import api from '@/api'

interface RequirementPoint {
  content: string
  order_index: number
  priority?: string
  category?: string
}

const props = defineProps<{
  visible: boolean
  taskResult: any
  projectId: number
  moduleId: number
  fileId: number
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'saved'): void
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value)
})

const editablePoints = ref<RequirementPoint[]>([])
const saving = ref(false)
const clearExisting = ref(true)

// 元信息
const hasImages = computed(() => props.taskResult?.metadata?.has_images || false)
const imageCount = computed(() => props.taskResult?.metadata?.image_count || 0)

// 加载任务结果
watch(() => props.visible, (newVal) => {
  if (newVal && props.taskResult?.requirement_points) {
    editablePoints.value = [...props.taskResult.requirement_points]
  } else if (!newVal) {
    // 对话框关闭时重置
    editablePoints.value = []
  }
})

// 添加需求点
const addPoint = () => {
  editablePoints.value.push({
    content: '',
    order_index: editablePoints.value.length,
    priority: 'medium',
    category: 'functional'
  })
}

// 删除需求点
const removePoint = (index: number) => {
  editablePoints.value.splice(index, 1)
  // 更新序号
  editablePoints.value.forEach((p, i) => p.order_index = i)
}

// 保存需求点
const handleSave = async () => {
  if (editablePoints.value.length === 0) {
    ElMessage.warning('请至少保留一个需求点')
    return
  }

  saving.value = true

  try {
    await api.post(
      `/projects/${props.projectId}/modules/${props.moduleId}/requirements/files/${props.fileId}/points/batch`,
      {
        points: editablePoints.value.map((point, index) => ({
          content: point.content,
          order_index: point.order_index ?? index,
          priority: point.priority || 'medium',
          created_by_ai: true
        }))
      }
    )

    ElMessage.success(`成功保存 ${editablePoints.value.length} 个需求点`)
    emit('saved')
    emit('update:visible', false)
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '保存失败，请重试')
  } finally {
    saving.value = false
  }
}

const handleCancel = () => {
  emit('update:visible', false)
}

const handleClose = () => {
  if (saving.value) return
  emit('update:visible', false)
}
</script>

<style scoped>
.points-list::-webkit-scrollbar {
  width: 6px;
}

.points-list::-webkit-scrollbar-thumb {
  background-color: #e5e7eb;
  border-radius: 3px;
}

.points-list::-webkit-scrollbar-thumb:hover {
  background-color: #d1d5db;
}
</style>
