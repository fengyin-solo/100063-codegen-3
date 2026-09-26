<template>
  <section class="page" data-module="inspection">
    <header class="page-head">
      <div>
        <h2>安全巡检管理</h2>
        <p class="page-desc">按巡检计划生成巡检任务，任务按待巡检、巡检中、待整改、已闭环流转，整改完成情况自动回写计划。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openPlanForm">登记巡检计划</button>
        <button class="btn" type="button" @click="exportRows">导出安全巡检清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>计划/任务编号</span>
        <input v-model="filters.keyword" placeholder="按计划或任务编号检索" />
      </label>
      <label class="filter-item">
        <span>当前状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] || '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in rowActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!rowActions(row).length" class="muted-text">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无安全巡检数据，可先登记巡检计划</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条安全巡检记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="planFormVisible" class="modal-mask" @click.self="planFormVisible = false">
      <form class="modal-card" @submit.prevent="submitPlan">
        <h3>登记巡检计划</h3>
        <label v-for="field in planFields" :key="field.name" class="modal-field">
          <span>{{ field.label }}</span>
          <input v-model="planForm[field.name]" :type="field.type" :placeholder="`请输入${field.label}`" />
        </label>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="planFormVisible = false">取消</button>
          <button class="btn primary" type="submit">保存计划</button>
        </div>
      </form>
    </div>

    <div v-if="hazardFormVisible" class="modal-mask" @click.self="hazardFormVisible = false">
      <form class="modal-card" @submit.prevent="submitHazard">
        <h3>登记巡检隐患（任务 {{ hazardForm.关联任务 }}）</h3>
        <label v-for="field in hazardFields" :key="field.name" class="modal-field">
          <span>{{ field.label }}</span>
          <input v-model="hazardForm[field.name]" :type="field.type" :placeholder="`请输入${field.label}`" />
        </label>
        <p class="modal-tip">同一隐患重复登记时会自动合并到已有整改单，不会重复建单。</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="hazardFormVisible = false">取消</button>
          <button class="btn primary" type="submit">保存隐患</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/inspection'
const HAZARD_ENDPOINT = '/api/hazard'
const columns = ["记录类型", "计划编号", "任务编号", "巡检区域", "巡检人员", "计划巡检日", "隐患数量", "已整改数量", "完成日期", "当前状态"]
const statuses = ["计划中", "执行中", "待巡检", "巡检中", "待整改", "已闭环", "已归档"]

const stats = ref<{ label: string; value: number }[]>([
  { label: '巡检计划', value: 0 },
  { label: '未闭环任务', value: 0 },
  { label: '待整改隐患', value: 0 },
  { label: '已闭环隐患', value: 0 },
])
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({ keyword: '', status: '' })

const planFormVisible = ref(false)
const planFields = [
  { name: '巡检区域', label: '巡检区域', type: 'text' },
  { name: '巡检人员', label: '巡检人员', type: 'text' },
  { name: '计划巡检日', label: '计划巡检日', type: 'date' },
]
const planForm = ref<Record<string, string>>({ 巡检区域: '', 巡检人员: '', 计划巡检日: '' })

const hazardFormVisible = ref(false)
const hazardFields = [
  { name: '隐患位置', label: '隐患位置', type: 'text' },
  { name: '隐患描述', label: '隐患描述', type: 'text' },
  { name: '整改责任人', label: '整改责任人', type: 'text' },
  { name: '整改期限', label: '整改期限', type: 'date' },
]
const hazardForm = ref<Record<string, string>>({ 关联任务: '', 隐患位置: '', 隐患描述: '', 整改责任人: '', 整改期限: '' })

function rowActions(row: Row): string[] {
  if (row['记录类型'] === '计划') {
    return row['当前状态'] === '已闭环' ? [] : ['生成巡检任务']
  }
  switch (row['当前状态']) {
    case '待巡检': return ['开始巡检']
    case '巡检中': return ['登记隐患', '巡检完成']
    case '待整改': return ['登记隐患', '整改闭环']
    case '已闭环': return ['归档']
    default: return []
  }
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openPlanForm() {
  planForm.value = { 巡检区域: '', 巡检人员: '', 计划巡检日: '' }
  planFormVisible.value = true
}

function openHazardForm(row: Row) {
  hazardForm.value = { 关联任务: String(row['任务编号'] ?? ''), 隐患位置: '', 隐患描述: '', 整改责任人: '', 整改期限: '' }
  hazardFormVisible.value = true
}

async function parseResult(response: Response, fallback: string) {
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload || payload.ok === false) {
    throw new Error(payload?.message ?? payload?.detail ?? fallback)
  }
  return payload
}

async function submitPlan() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: planForm.value }),
    })
    const payload = await parseResult(response, '巡检计划登记失败')
    planFormVisible.value = false
    noticeMessage.value = payload.message ?? '巡检计划已登记'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡检计划登记失败'
  }
}

async function submitHazard() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(HAZARD_ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: hazardForm.value }),
    })
    const payload = await parseResult(response, '隐患登记失败')
    hazardFormVisible.value = false
    noticeMessage.value = payload.message ?? '隐患已登记'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '隐患登记失败'
  }
}

async function runAction(action: string, row: Row) {
  if (action === '登记隐患') {
    openHazardForm(row)
    return
  }
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await parseResult(response, '安全巡检动作未生效，请稍后重试')
    noticeMessage.value = payload.message ?? `已${action}`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全巡检操作失败'
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (response.ok) {
      const payload = await response.json()
      stats.value = payload.cards ?? stats.value
    }
  } catch {
    // 统计卡片读取失败不阻断列表展示
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('安全巡检列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全巡检列表读取失败'
  }
}

onMounted(reload)
</script>
