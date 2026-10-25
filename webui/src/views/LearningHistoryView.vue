<template>
  <section class="history-page" aria-labelledby="history-title">
    <header class="page-heading">
      <div>
        <h1 id="history-title">学习记录</h1>
        <p class="secondary">查看机器人记住了什么、依据哪段交流，以及每次修正前后的内容。</p>
      </div>
      <n-button secondary :loading="loading" :disabled="undoing" @click="loadData">
        <template #icon><Icon icon="lucide:refresh-cw" aria-hidden="true" /></template>
        刷新记录
      </n-button>
    </header>

    <n-card embedded>
      <div class="filters">
        <n-form-item label="来源范围" :show-feedback="false">
          <n-select
            v-model:value="scope"
            :options="scopeOptions"
            clearable
            filterable
            placeholder="全部范围"
            aria-label="筛选学习记录的来源范围"
            :disabled="undoing"
            @update:value="resetPage"
          />
        </n-form-item>
        <n-form-item label="每页显示" :show-feedback="false">
          <n-select
            v-model:value="pageSize"
            :options="pageSizeOptions"
            aria-label="每页学习记录条数"
            :disabled="undoing"
            @update:value="resetPage"
          />
        </n-form-item>
      </div>
      <p class="filter-hint secondary">仅记录启用此功能后的学习变更。撤销始终作用于选定记录的原始范围。</p>
    </n-card>

    <n-alert v-if="loadError" type="error" title="学习记录读取失败" :bordered="false" role="alert">
      {{ loadError }}
      <div class="error-actions"><n-button size="small" @click="loadData">重新读取</n-button></div>
    </n-alert>
    <n-alert v-else-if="loadNote" type="info" :bordered="false" role="status">{{ loadNote }}</n-alert>

    <div class="result-heading" role="status" aria-live="polite">
      <span>{{ loading ? '正在读取学习记录…' : `共 ${total} 条记录` }}</span>
      <span v-if="!loading && items.length" class="secondary">按学习时间倒序排列</span>
    </div>

    <n-spin :show="loading">
      <div class="history-list" :aria-busy="loading">
        <n-card v-if="!items.length && !loading && !loadError" embedded>
          <n-empty description="这个范围还没有学习变更记录">
            <template #extra><span class="secondary">新的学习保存后，可在这里查看来源与前后对比。</span></template>
          </n-empty>
        </n-card>

        <n-card v-for="item in items" :key="item.id" embedded class="history-card">
          <div class="record-heading">
            <div class="record-meta">
              <n-tag :type="actionType(item.action)" :bordered="false">{{ actionText(item.action) }}</n-tag>
              <span class="record-id">#{{ item.id }}</span>
              <time :datetime="isoTime(item.created_at)">{{ formatTime(item.created_at) }}</time>
            </div>
            <n-tag :type="statusType(item)" :bordered="false">{{ statusText(item) }}</n-tag>
          </div>
          <p class="record-summary">{{ summaryText(item) }}</p>
          <p class="record-scope secondary"><span>范围</span><code>{{ item.memory_scope }}</code></p>

          <n-alert v-if="recordErrors[item.id]" type="error" :bordered="false" class="record-error" role="alert">
            {{ recordErrors[item.id] }}
          </n-alert>
          <n-alert v-if="item.status === 'undone' && item.index_sync === 'pending'" type="warning" :bordered="false" class="record-error">
            记忆内容已撤销，检索索引尚未同步完成。可重试同步，使后续回忆采用恢复后的内容。
            <p v-if="item.index_error" class="index-error">上次同步失败：{{ item.index_error }}</p>
          </n-alert>

          <details class="record-details">
            <summary>查看来源与变更</summary>
            <div class="source-block">
              <h2>学习来源</h2>
              <dl class="source-meta">
                <template v-if="item.source?.kind"><dt>方式</dt><dd>{{ sourceText(item.source.kind) }}</dd></template>
                <template v-if="item.source?.session_id"><dt>会话</dt><dd>{{ item.source.session_id }}</dd></template>
                <template v-if="item.source?.message_ids?.length"><dt>消息</dt><dd>{{ item.source.message_ids.join('、') }}</dd></template>
              </dl>
              <blockquote v-if="item.source?.excerpt" class="source-excerpt">{{ item.source.excerpt }}</blockquote>
              <p v-else class="secondary">来源原文未记录。</p>
            </div>

            <div class="snapshot-grid">
              <section v-for="side in snapshotSides(item)" :key="side.key" class="snapshot" :class="side.key">
                <h2>{{ side.label }}<span class="secondary">{{ side.memories.length }} 条</span></h2>
                <p v-if="!side.memories.length" class="secondary">{{ side.key === 'before' ? '本次学习前没有对应记忆。' : '本次没有写入新内容。' }}</p>
                <article v-for="memory in side.memories" :key="memory.id" class="memory-content">
                  <p class="memory-judgment">{{ memory.judgment || '（无论断）' }}</p>
                  <p v-if="memory.reasoning" class="memory-reasoning">{{ memory.reasoning }}</p>
                  <div v-if="memoryTags(memory).length" class="tag-list">
                    <n-tag v-for="tag in memoryTags(memory)" :key="tag" :bordered="false" size="small">{{ tag }}</n-tag>
                  </div>
                  <p class="memory-meta secondary">
                    <span>ID {{ memory.id }}</span>
                    <span v-if="memory.memory_type">{{ memory.memory_type }}</span>
                    <span v-if="memory.strength !== undefined">强度 {{ memory.strength }}</span>
                    <span>{{ memory.is_active ? '主动记忆' : '被动记忆' }}</span>
                  </p>
                </article>
              </section>
            </div>
          </details>

          <footer class="record-footer">
            <span v-if="item.undone_at" class="secondary">撤销于 {{ formatTime(item.undone_at) }}</span>
            <span v-else class="secondary">原有 {{ item.before.length }} 条 → 本次写入 {{ item.after.length }} 条</span>
            <n-button
              v-if="item.status === 'committed'"
              secondary
              :disabled="undoing"
              :aria-label="`查看并撤销学习记录 ${item.id}`"
              @click="confirmUndo(item)"
            >
              <template #icon><Icon icon="lucide:undo-2" aria-hidden="true" /></template>
              撤销本次学习
            </n-button>
            <n-button
              v-else-if="item.index_sync === 'pending'"
              secondary
              :loading="undoing && activeUndoId === item.id"
              :disabled="undoing && activeUndoId !== item.id"
              :aria-label="`重试同步学习记录 ${item.id} 的检索索引`"
              @click="undoRecord(item)"
            >重试同步</n-button>
          </footer>
        </n-card>
      </div>
    </n-spin>

    <n-pagination
      v-if="total > pageSize"
      v-model:page="page"
      :page-size="pageSize"
      :item-count="total"
      :page-slot="5"
      :disabled="loading || undoing"
      class="history-pagination"
      @update:page="loadData"
    />

    <n-modal
      v-model:show="undoDialog"
      preset="card"
      title="撤销这次学习？"
      class="learning-undo-dialog"
      :bordered="false"
      :mask-closable="!undoing"
      :closable="!undoing"
      :close-on-esc="!undoing"
      @after-leave="clearUndoDialog"
    >
      <template v-if="undoTarget">
        <p class="confirm-record">记录 #{{ undoTarget.id }} · {{ actionText(undoTarget.action) }} · {{ formatTime(undoTarget.created_at) }}</p>
        <p class="record-scope"><span>范围</span><code>{{ undoTarget.memory_scope }}</code></p>
        <blockquote class="confirm-preview">{{ summaryText(undoTarget) }}</blockquote>
        <p>将移除本次写入的 <strong>{{ undoTarget.after.length }}</strong> 条记忆，并恢复学习前的 <strong>{{ undoTarget.before.length }}</strong> 条记忆。</p>
        <p class="secondary">如果这些记忆后来又被修改，系统会停止撤销并保留现有内容。</p>
        <n-alert v-if="undoError" type="error" :bordered="false" class="record-error" role="alert">{{ undoError }}</n-alert>
        <n-checkbox v-model:checked="undoAcknowledged" :disabled="undoing || undoConflict" class="undo-checkbox">
          我已核对范围与变更内容，确认撤销这条学习记录。
        </n-checkbox>
        <div class="dialog-actions">
          <n-button :disabled="undoing" @click="undoDialog = false; undoConflict && loadData()">{{ undoConflict ? '关闭并刷新记录' : '保留这次学习' }}</n-button>
          <n-button type="error" :loading="undoing" :disabled="!undoAcknowledged || undoConflict" @click="undoRecord(undoTarget)">确认撤销</n-button>
        </div>
      </template>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  NAlert, NButton, NCard, NCheckbox, NEmpty, NFormItem, NModal,
  NPagination, NSelect, NSpin, NTag, useMessage,
} from 'naive-ui'
import { Icon } from '@iconify/vue'
import { useBridge } from '@/composables/useBridge'
import { formatTime, parseTags } from '@/utils/format'

interface MemorySnapshot {
  id: string | number
  judgment?: string
  reasoning?: string
  tags?: string[] | string
  memory_type?: string
  strength?: number
  is_active?: boolean | number
}

interface HistoryItem {
  id: number
  action: string
  memory_scope: string
  source?: { kind?: string; session_id?: string; excerpt?: string; message_ids?: string[] }
  before: MemorySnapshot[]
  after: MemorySnapshot[]
  created_at: number
  status: string
  undone_at?: number | null
  index_sync?: string
  index_error?: string
}

interface HistoryResponse {
  ok: boolean
  items?: HistoryItem[]
  total?: number
  scopes?: string[]
  error?: string
  code?: string
  index_sync?: string
  note?: string
}

const { apiGet, apiPost } = useBridge()
const message = useMessage()
const route = useRoute()
const scope = ref<string | null>(typeof route.query.scope === 'string' ? route.query.scope : null)
const scopes = ref<string[]>([])
const scopeOptions = computed(() => scopes.value.map(value => ({ label: value, value })))
const pageSizeOptions = [10, 30, 50].map(value => ({ label: `${value} 条`, value }))
const pageSize = ref(30)
const page = ref(1)
const items = ref<HistoryItem[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref('')
const loadNote = ref('')
const recordErrors = ref<Record<number, string>>({})
const undoDialog = ref(false)
const undoTarget = ref<HistoryItem | null>(null)
const undoAcknowledged = ref(false)
const undoing = ref(false)
const activeUndoId = ref<number | null>(null)
const undoError = ref('')
const undoConflict = ref(false)
let requestRevision = 0

function actionText(action: string): string {
  return ({ create: '新增记忆', update: '修正记忆', merge: '合并记忆' } as Record<string, string>)[action] || action
}

function actionType(action: string): 'info' | 'warning' | 'success' {
  return action === 'create' ? 'success' : action === 'merge' ? 'warning' : 'info'
}

function statusText(item: HistoryItem): string {
  if (item.status === 'undone') return item.index_sync === 'pending' ? '已撤销 · 待同步' : '已撤销'
  return item.status === 'committed' ? '已保存' : item.status
}

function statusType(item: HistoryItem): 'default' | 'warning' | 'success' {
  if (item.index_sync === 'pending') return 'warning'
  return item.status === 'undone' ? 'default' : 'success'
}

function sourceText(kind: string): string {
  return ({ auto_learning: '对话自动学习', explicit_remember: '主动记忆', feedback: '对话自动学习', remember: '主动记忆', reflection: '对话反思',
    important: '重要信息即时学习', correction: '偏好修正' } as Record<string, string>)[kind] || kind
}

function summaryText(item: HistoryItem): string {
  return (item.after[0]?.judgment || item.before[0]?.judgment || '这次学习没有文字摘要').slice(0, 240)
}

function isoTime(timestamp: number): string {
  const value = new Date(Number(timestamp) * 1000)
  return Number.isNaN(value.getTime()) ? '' : value.toISOString()
}

function memoryTags(memory: MemorySnapshot): string[] {
  return Array.isArray(memory.tags) ? memory.tags : parseTags(memory.tags)
}

function snapshotSides(item: HistoryItem) {
  return [
    { key: 'before', label: '学习前', memories: item.before },
    { key: 'after', label: '本次写入', memories: item.after },
  ]
}

async function resetPage() {
  page.value = 1
  items.value = []
  total.value = 0
  await loadData()
}

async function loadData() {
  const revision = ++requestRevision
  loading.value = true
  loadError.value = ''
  loadNote.value = ''
  try {
    const data = await apiGet<HistoryResponse>('history', {
      memory_scope: scope.value || '', limit: pageSize.value, offset: (page.value - 1) * pageSize.value,
    })
    if (revision !== requestRevision) return
    if (!data.ok) throw new Error(data.error || '读取学习记录失败，请稍后重试。')
    items.value = (data.items || []).map(item => ({ ...item, before: item.before || [], after: item.after || [] }))
    total.value = data.total || 0
    scopes.value = data.scopes || []
    loadNote.value = data.note || ''
  } catch (error) {
    if (revision === requestRevision) loadError.value = (error as Error).message || '读取学习记录失败。'
  } finally {
    if (revision === requestRevision) loading.value = false
  }
}

function confirmUndo(item: HistoryItem) {
  undoTarget.value = item
  undoAcknowledged.value = false
  undoError.value = ''
  undoConflict.value = false
  undoDialog.value = true
}

function clearUndoDialog() {
  undoTarget.value = null
  undoAcknowledged.value = false
  undoError.value = ''
  undoConflict.value = false
}

async function undoRecord(item: HistoryItem) {
  if (undoing.value || (item.status === 'committed' && (!undoAcknowledged.value || undoTarget.value?.id !== item.id))) return
  undoing.value = true
  activeUndoId.value = item.id
  undoError.value = ''
  delete recordErrors.value[item.id]
  try {
    const data = await apiPost<HistoryResponse>('history/undo', { id: item.id, memory_scope: item.memory_scope })
    if (!data.ok) {
      undoConflict.value = data.code === 'conflict'
      throw new Error(data.error || '撤销失败，请刷新记录后重试。')
    }
    undoDialog.value = false
    if (data.index_sync === 'pending') message.warning('记忆内容已撤销，检索索引待同步。可在这条记录上重试。')
    else message.success(item.status === 'undone' ? '检索索引已同步。' : '已撤销这次学习。')
    await loadData()
  } catch (error) {
    const text = (error as Error).message || '操作失败，请稍后重试。'
    undoError.value = text
    undoConflict.value ||= /冲突|后续|已被?修改|无法安全撤销|conflict/i.test(text)
    recordErrors.value[item.id] = text
    if (!undoDialog.value) message.error(text)
  } finally {
    undoing.value = false
    activeUndoId.value = null
  }
}

onMounted(loadData)
</script>

<style scoped>
.history-page { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.page-heading, .record-heading, .result-heading, .record-footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
h1 { margin: 0 0 8px; font-size: 24px; line-height: 1.35; }
h2 { margin: 0 0 12px; font-size: 15px; line-height: 1.5; }
p { margin: 0; line-height: 1.65; }
.secondary { color: var(--text-2); }
.filters { display: grid; grid-template-columns: minmax(0, 1fr) 140px; gap: 16px; max-width: 700px; }
.filter-hint { margin-top: 12px; font-size: 13px; }
.history-list { display: flex; flex-direction: column; gap: 16px; min-height: 96px; }
.record-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.record-meta time, .record-id { color: var(--text-2); font-size: 13px; }
.history-card :deep(.n-tag__content) { color: var(--text-1); }
.record-summary { margin-top: 16px; font-size: 16px; font-weight: 600; overflow-wrap: anywhere; }
.record-scope { display: flex; align-items: baseline; gap: 8px; margin-top: 8px; min-width: 0; font-size: 13px; }
.record-scope span { flex-shrink: 0; }
.record-scope code { overflow-wrap: anywhere; font-size: inherit; }
.record-error { margin-top: 16px; }
.error-actions { margin-top: 12px; }
.index-error { margin-top: 8px; font-size: 13px; overflow-wrap: anywhere; }
.record-details { margin-top: 16px; border-top: 1px solid var(--glass-divider); }
.record-details summary { padding: 12px 0; min-height: 20px; color: var(--accent); cursor: pointer; line-height: 1.5; }
.record-details summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 4px; }
.source-block { padding: 12px 0 20px; }
.source-meta { display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: 8px; margin: 0 0 12px; font-size: 13px; }
.source-meta dt { color: var(--text-2); }
.source-meta dd { margin: 0; overflow-wrap: anywhere; }
.source-excerpt, .confirm-preview { white-space: pre-wrap; overflow-wrap: anywhere; border-left: 3px solid var(--glass-border); margin: 0; padding: 8px 12px; background: var(--bg-base); line-height: 1.65; }
.snapshot-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.snapshot { border: 1px solid var(--glass-border); border-radius: var(--radius-md); padding: 16px; min-width: 0; }
.snapshot.after { border-top: 3px solid var(--accent); }
.snapshot h2 { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.snapshot h2 span { font-size: 13px; font-weight: 400; }
.memory-content + .memory-content { border-top: 1px solid var(--glass-divider); padding-top: 16px; margin-top: 16px; }
.memory-judgment { font-weight: 600; white-space: pre-wrap; overflow-wrap: anywhere; }
.memory-reasoning { margin-top: 8px; white-space: pre-wrap; overflow-wrap: anywhere; }
.tag-list, .memory-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.tag-list :deep(.n-tag) { max-width: 100%; height: auto; min-height: 24px; white-space: normal; overflow-wrap: anywhere; }
.memory-meta { font-size: 12px; }
.record-footer { border-top: 1px solid var(--glass-divider); margin-top: 20px; padding-top: 16px; font-size: 13px; }
.history-pagination { align-self: flex-end; }
.history-page :deep(.n-button), :global(.learning-undo-dialog .n-button) { min-height: 44px; }
.history-page :deep(.n-base-selection) { min-height: 44px; align-items: center; }
:global(.learning-undo-dialog) { width: min(620px, calc(100vw - 32px)); max-height: calc(100dvh - 32px); overflow-y: auto; }
:global(.learning-undo-dialog p + p) { margin-top: 12px; }
.confirm-record { color: var(--text-2); }
.confirm-preview { margin: 16px 0; max-height: 180px; overflow: auto; }
.undo-checkbox { margin-top: 20px; min-height: 44px; align-items: center; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
@media (max-width: 680px) {
  .filters, .snapshot-grid { grid-template-columns: 1fr; }
  .page-heading { align-items: flex-start; }
  .record-footer { align-items: flex-start; }
  .record-footer > .n-button { width: 100%; }
  .history-pagination { align-self: center; }
}
@media (prefers-reduced-motion: reduce) {
  .history-page :deep(*), :global(.learning-undo-dialog *) { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
</style>
