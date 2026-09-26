<template>
  <section class="page" data-module="inspection">
    <header class="page-head">
      <div>
        <h2>安全巡检与隐患整改</h2>
        <p class="page-desc">
          按巡检计划生成巡检任务，登记巡检问题并跟踪整改；状态在待巡检 → 巡检中 → 待整改 → 已闭环之间流转，未闭环不可归档，重复隐患自动合并到已有整改单。
        </p>
      </div>
      <div class="page-actions">
        <button v-if="activeTab === 'plans'" class="btn primary" type="button" @click="openModal('createPlan')">
          新增巡检计划
        </button>
        <button v-else-if="activeTab === 'tasks'" class="btn primary" type="button" disabled title="请在巡检计划中选择计划生成任务">
          生成巡检任务
        </button>
      </div>
    </header>

    <!-- 统计卡片：与三张表同源，任何流转后随列表一起刷新 -->
    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <nav class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-item"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>关键词</span>
        <input v-model="filters.keyword" :placeholder="keywordPlaceholder" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="option in statusOptions" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <!-- 巡检计划 -->
    <table v-if="activeTab === 'plans'" class="data-table">
      <thead>
        <tr>
          <th v-for="column in planColumns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in planColumns" :key="column" :title="column === '完成情况' ? String(row[column] ?? '') : ''">
            {{ row[column] ?? '—' }}
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openModal('generateTask', row)">生成巡检任务</button>
            <button class="link" type="button" @click="goTask(row.最近任务编号)">查看当前任务</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="planColumns.length + 1" class="empty-state">暂无巡检计划，点击右上角“新增巡检计划”建立巡检台账</td>
        </tr>
      </tbody>
    </table>

    <!-- 巡检任务 -->
    <table v-else-if="activeTab === 'tasks'" class="data-table">
      <thead>
        <tr>
          <th v-for="column in taskColumns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ archived: row.已归档 }">
          <td v-for="column in taskColumns" :key="column" :title="column === '完成情况' ? String(row[column] ?? '') : ''">
            {{ row[column] ?? '—' }}
          </td>
          <td class="row-actions">
            <button v-if="!row.已归档 && row.status === '待巡检'" class="link" type="button" @click="act('start', row)">
              开始巡检
            </button>
            <button v-if="!row.已归档 && row.status === '巡检中'" class="link" type="button" @click="openModal('registerHazard', row)">
              登记隐患
            </button>
            <button v-if="!row.已归档 && row.status === '巡检中'" class="link" type="button" @click="openModal('closeClean', row)">
              无隐患闭环
            </button>
            <button v-if="!row.已归档 && row.status === '待整改'" class="link" type="button" @click="openModal('registerHazard', row)">
              补登隐患
            </button>
            <button v-if="!row.已归档 && row.status === '待整改'" class="link" type="button" @click="openModal('close', row)">
              整改验收闭环
            </button>
            <button
              v-if="!row.已归档 && row.status === '已闭环'"
              class="link"
              type="button"
              @click="act('archive', row)"
            >
              归档
            </button>
            <button v-if="row.已归档" class="link muted" type="button" disabled>已归档</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="taskColumns.length + 1" class="empty-state">暂无巡检任务，请在“巡检计划”页签按计划生成巡检任务</td>
        </tr>
      </tbody>
    </table>

    <!-- 隐患整改单 -->
    <table v-else class="data-table">
      <thead>
        <tr>
          <th v-for="column in hazardColumns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in hazardColumns" :key="column" :title="column === '隐患描述' || column === '整改措施' ? String(row[column] ?? '') : ''">
            {{ row[column] ?? '—' }}
          </td>
          <td class="row-actions">
            <button
              v-if="row.status === '待整改'"
              class="link"
              type="button"
              @click="openModal('rectify', row)"
            >
              登记整改
            </button>
            <button v-if="row.status === '已整改'" class="link muted" type="button" disabled>待验收闭环</button>
            <button v-if="row.status === '已闭环'" class="link muted" type="button" disabled>已闭环</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="hazardColumns.length + 1" class="empty-state">
            暂无隐患记录；巡检中未发现隐患时可直接闭环，发现问题后在此登记并跟踪整改
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ tabLabel }}记录</span>
      <span v-if="message" :class="messageOk ? 'ok-text' : 'error-text'">{{ message }}</span>
    </footer>

    <!-- 统一操作弹窗 -->
    <div v-if="modal.open" class="modal-mask" @click.self="closeModal">
      <div class="modal-card">
        <h3 class="modal-title">{{ modal.title }}</h3>
        <p v-if="modal.context" class="modal-context">{{ modal.context }}</p>
        <form @submit.prevent="submitModal">
          <label v-for="field in modal.fields" :key="field.name" class="modal-field">
            <span>{{ field.label }}<em v-if="field.required">*</em></span>
            <textarea
              v-if="field.textarea"
              v-model="form[field.name]"
              :rows="2"
              :placeholder="field.placeholder ?? ''"
            ></textarea>
            <input
              v-else
              v-model="form[field.name]"
              :type="field.type ?? 'text'"
              :placeholder="field.placeholder ?? ''"
            />
          </label>
          <div class="modal-actions">
            <button class="btn" type="button" @click="closeModal">取消</button>
            <button class="btn primary" type="submit" :disabled="submitting">
              {{ submitting ? '提交中…' : '确定' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

type TabKey = 'plans' | 'tasks' | 'hazards'
type ModalKind = 'createPlan' | 'generateTask' | 'registerHazard' | 'rectify' | 'close' | 'closeClean'

interface ModalField {
  name: string
  label: string
  required?: boolean
  type?: string
  textarea?: boolean
  placeholder?: string
}

const ENDPOINT = '/api/inspection'

const tabs: { key: TabKey; label: string }[] = [
  { key: 'plans', label: '巡检计划' },
  { key: 'tasks', label: '巡检任务' },
  { key: 'hazards', label: '隐患整改单' },
]
const planColumns = ['计划编号', '巡检区域', '巡检频次', '责任人', '计划巡检日', '巡检状态', '隐患总数', '待整改数', '已闭环数', '验收人', '闭环时间', '完成情况']
const taskColumns = ['任务编号', '计划编号', '巡检区域', '巡检人员', '计划巡检日', '开始时间', '任务状态', '隐患总数', '待整改数', '已整改数', '已闭环数', '验收人', '闭环时间', '完成情况']
const hazardColumns = ['隐患编号', '任务编号', '隐患位置', '隐患描述', '隐患级别', '登记人', '登记时间', '重复登记次数', '整改措施', '整改人', '整改时间', '隐患状态', '任务状态', '验收人', '闭环时间']

const TASK_STATUS_OPTIONS = ['待巡检', '巡检中', '待整改', '已闭环']
const HAZARD_STATUS_OPTIONS = ['待整改', '已整改', '已闭环']

const activeTab = ref<TabKey>('plans')
const rows = ref<Row[]>([])
const total = ref(0)
const message = ref('')
const messageOk = ref(false)
const submitting = ref(false)
const filters = reactive<{ keyword: string; status: string }>({ keyword: '', status: '' })
const stats = ref<Record<string, number | null>>({})

const tabLabel = computed(() => tabs.find((item) => item.key === activeTab.value)?.label ?? '')
const statusOptions = computed(() =>
  activeTab.value === 'hazards' ? HAZARD_STATUS_OPTIONS : TASK_STATUS_OPTIONS,
)
const keywordPlaceholder = computed(() => {
  if (activeTab.value === 'plans') return '按计划编号 / 巡检区域检索'
  if (activeTab.value === 'tasks') return '按任务编号 / 巡检区域检索'
  return '按隐患编号 / 位置 / 描述检索'
})
const statCards = computed(() => {
  const rate = stats.value['闭环率']
  return [
    { label: '巡检计划总数', value: stats.value['巡检计划总数'] ?? 0 },
    { label: '进行中任务', value: stats.value['进行中任务'] ?? 0 },
    { label: '待整改隐患', value: stats.value['待整改隐患'] ?? 0 },
    { label: '已闭环隐患', value: stats.value['已闭环隐患'] ?? 0 },
    { label: '隐患闭环率', value: rate === null || rate === undefined ? '—' : `${rate}%` },
  ]
})

// 弹窗字段配置：每种动作需要登记什么，在这里声明
const FIELD_DEFS: Record<ModalKind, ModalField[]> = {
  createPlan: [
    { name: '巡检区域', label: '巡检区域', required: true, placeholder: '如：理化分析室' },
    { name: '巡检频次', label: '巡检频次', required: true, placeholder: '如：每周 / 每月' },
    { name: '责任人', label: '责任人', required: true, placeholder: '负责巡检的人员' },
    { name: '计划巡检日', label: '计划巡检日', required: true, type: 'date' },
  ],
  generateTask: [
    { name: '巡检人员', label: '巡检人员', placeholder: '留空则默认计划责任人' },
  ],
  registerHazard: [
    { name: '隐患位置', label: '隐患位置', required: true, placeholder: '如：气瓶存放间-氧气钢瓶位' },
    { name: '隐患描述', label: '隐患描述', required: true, textarea: true, placeholder: '同一位置与描述重复登记将合并到已有整改单' },
    { name: '隐患级别', label: '隐患级别', placeholder: '一般 / 较大，默认一般' },
    { name: '登记人', label: '登记人', placeholder: '留空则默认巡检人员' },
  ],
  rectify: [
    { name: '整改措施', label: '整改措施', required: true, textarea: true, placeholder: '说明已采取的整改措施' },
    { name: '整改人', label: '整改人', required: true, placeholder: '负责整改的人员' },
  ],
  close: [
    { name: '验收人', label: '验收人', required: true, placeholder: '闭环验证的验收人' },
    { name: '验收意见', label: '验收意见', textarea: true, placeholder: '如：复查合格，默认“验收合格”' },
  ],
  closeClean: [
    { name: '验收人', label: '验收人', required: true, placeholder: '闭环验证的验收人' },
    { name: '验收意见', label: '验收意见', textarea: true, placeholder: '本次巡检未发现隐患' },
  ],
}

const modal = reactive<{
  open: boolean
  kind: ModalKind
  title: string
  context: string
  fields: ModalField[]
  target: Row | null
}>({ open: false, kind: 'createPlan', title: '', context: '', fields: [], target: null })
const form = reactive<Record<string, string>>({})

const MODAL_TITLES: Record<ModalKind, string> = {
  createPlan: '新增巡检计划',
  generateTask: '按计划生成巡检任务',
  registerHazard: '登记巡检隐患',
  rectify: '登记整改情况',
  close: '整改验收闭环',
  closeClean: '无隐患闭环',
}

function switchTab(key: TabKey) {
  activeTab.value = key
  filters.status = ''
  filters.keyword = ''
  void reload()
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function openModal(kind: ModalKind, row?: Row) {
  modal.open = true
  modal.kind = kind
  modal.title = MODAL_TITLES[kind]
  modal.fields = FIELD_DEFS[kind]
  modal.target = row ?? null
  modal.context = row ? describeTarget(kind, row) : ''
  Object.keys(form).forEach((key) => delete form[key])
  if (kind === 'generateTask' && row) {
    form['巡检人员'] = String(row['责任人'] ?? '')
  }
}

function closeModal() {
  modal.open = false
  modal.target = null
}

function describeTarget(kind: ModalKind, row: Row): string {
  if (kind === 'generateTask') return `计划 ${row['计划编号']} · ${row['巡检区域']} · 计划巡检日 ${row['计划巡检日']}`
  if (kind === 'registerHazard') return `任务 ${row['任务编号']} · ${row['巡检区域']} · 当前状态 ${row['status']}`
  if (kind === 'rectify') return `隐患 ${row['隐患编号']} · ${row['隐患位置']}`
  return `任务 ${row['任务编号']} · ${row['巡检区域']}`
}

async function submitModal() {
  const missing = modal.fields
    .filter((field) => field.required && !form[field.name]?.trim())
    .map((field) => field.label)
  if (missing.length) {
    flash(`请填写必填项：${missing.join('、')}`, false)
    return
  }
  const target = modal.target
  const kind = modal.kind
  let path = ''
  let method = 'POST'

  if (kind === 'createPlan') {
    path = `${ENDPOINT}/plans`
  } else if (target) {
    const id = String(target.id)
    if (kind === 'generateTask') path = `${ENDPOINT}/plans/${id}/tasks`
    if (kind === 'registerHazard') path = `${ENDPOINT}/tasks/${id}/hazards`
    if (kind === 'rectify') path = `${ENDPOINT}/hazards/${id}/rectify`
    if (kind === 'close') path = `${ENDPOINT}/tasks/${id}/close`
    if (kind === 'closeClean') path = `${ENDPOINT}/tasks/${id}/close-clean`
  }

  submitting.value = true
  try {
    const response = await request(path, { method, body: JSON.stringify({ values: { ...form } }) })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!payload.ok) {
      flash(payload.message, false)
      return
    }
    flash(payload.message, true)
    closeModal()
    await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : '操作失败，请稍后重试', false)
  } finally {
    submitting.value = false
  }
}

async function act(action: 'start' | 'archive', row: Row) {
  const path = `${ENDPOINT}/tasks/${String(row.id)}/${action}`
  try {
    const response = await request(path, { method: 'POST' })
    const payload = (await response.json()) as { ok: boolean; message: string }
    flash(payload.message, payload.ok)
    if (payload.ok) await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : '操作失败，请稍后重试', false)
  }
}

function goTask(taskCode: string | number | boolean | null) {
  if (!taskCode) {
    flash('该计划还没有巡检任务，请先生成', false)
    return
  }
  activeTab.value = 'tasks'
  filters.status = ''
  filters.keyword = String(taskCode)
  void reload()
}

function flash(text: string, ok: boolean) {
  message.value = text
  messageOk.value = ok
}

async function reload() {
  const tabPath = activeTab.value === 'plans' ? 'plans' : activeTab.value
  const query = new URLSearchParams()
  if (filters.keyword.trim()) query.set('keyword', filters.keyword.trim())
  if (filters.status) query.set('status', filters.status)
  query.set('size', '100')
  try {
    const [listResp, statsResp] = await Promise.all([
      request(`${ENDPOINT}/${tabPath}?${query.toString()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResp.ok || !statsResp.ok) throw new Error('安全巡检数据读取失败')
    const payload = (await listResp.json()) as { items: Row[]; total: number }
    const statsPayload = (await statsResp.json()) as Record<string, number | null>
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    stats.value = statsPayload
  } catch (error) {
    flash(error instanceof Error ? error.message : '安全巡检数据读取失败', false)
  }
}

onMounted(reload)
</script>

<style scoped>
.tab-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.tab-item {
  border: none;
  background: none;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
  color: var(--muted);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tab-item.active {
  color: var(--brand);
  border-bottom-color: var(--brand);
  font-weight: 600;
}
.link.muted {
  color: var(--muted);
  cursor: default;
}
tr.archived td {
  color: var(--muted);
}
.ok-text {
  color: #067647;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal-card {
  width: 460px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
}
.modal-title {
  margin: 0 0 4px;
  font-size: 16px;
}
.modal-context {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--muted);
}
.modal-field {
  display: block;
  margin-bottom: 10px;
}
.modal-field span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.modal-field em {
  color: #b42318;
  font-style: normal;
  margin-left: 2px;
}
.modal-field input,
.modal-field textarea {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font: inherit;
  resize: vertical;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
</style>
