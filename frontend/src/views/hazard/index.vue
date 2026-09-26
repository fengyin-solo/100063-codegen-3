<template>
  <section class="page" data-module="hazard">
    <header class="page-head">
      <div>
        <h2>隐患整改管理</h2>
        <p class="page-desc">登记巡检发现的隐患并跟踪整改，同一隐患重复登记自动合并，未闭环的隐患不能归档。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出隐患整改清单</button>
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
        <span>隐患编号/位置</span>
        <input v-model="filters.keyword" placeholder="按隐患编号或位置检索" />
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
          <td :colspan="columns.length + 1" class="empty-state">
            暂无隐患记录：当前巡检未发现问题，新登记的隐患会汇总到这里并跟踪整改闭环
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条隐患整改记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/hazard'
const STATS_ENDPOINT = '/api/inspection/stats'
const columns = ["隐患编号", "关联任务", "隐患位置", "隐患描述", "整改责任人", "整改期限", "登记次数", "当前状态"]
const statuses = ["待整改", "整改中", "已闭环", "已归档"]

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

function rowActions(row: Row): string[] {
  switch (row['当前状态']) {
    case '待整改': return ['开始整改', '归档']
    case '整改中': return ['整改完成', '归档']
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

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error(payload?.message ?? payload?.detail ?? '隐患整改动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message ?? `已${action}`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '隐患整改操作失败'
  }
}

async function reloadStats() {
  try {
    const response = await request(STATS_ENDPOINT)
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
      throw new Error('隐患整改列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '隐患整改列表读取失败'
  }
}

onMounted(reload)
</script>
