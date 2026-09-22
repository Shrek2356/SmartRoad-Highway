<template>
  <!--
    ③ 风险工单处置页
    业务：多条件筛选 → 表格 → 详情弹窗（抓拍对比/规范/流转）→ 批量导出
  -->
  <div class="page-card">
    <div class="page-title-row">
      <div class="page-title">风险工单处置</div>
      <div class="mood-legend">
        <span><img :src="JR.yes" alt="" />待处理</span>
        <span><img :src="JR.emergent" alt="" />紧急事项</span>
        <span><img :src="JR.no" alt="" />正常</span>
      </div>
    </div>

    <!-- 状态快捷筛选 -->
    <a-tabs v-model:activeKey="statusTab" class="status-tabs" @change="onStatusTabChange">
      <a-tab-pane key="all" :tab="`全部 (${stats.all})`" />
      <a-tab-pane key="pending" :tab="`待处理 (${stats.pending})`" />
      <a-tab-pane key="processing" :tab="`处理中 (${stats.processing})`" />
      <a-tab-pane key="done" :tab="`已完成 (${stats.done})`" />
    </a-tabs>

    <!-- 筛选栏 -->
    <a-form layout="inline" :model="query" class="filter-bar">
      <a-form-item label="关键词">
        <a-input v-model:value="query.keyword" placeholder="工单号/标题/区域" allow-clear style="width: 180px" />
      </a-form-item>
      <a-form-item label="风险等级">
        <a-select
          v-model:value="query.level"
          allow-clear
          placeholder="全部"
          style="width: 120px"
          @change="onFilterChange"
        >
          <a-select-option value="red">高危</a-select-option>
          <a-select-option value="orange">中危</a-select-option>
          <a-select-option value="yellow">低危</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="状态">
        <a-select
          v-model:value="query.status"
          allow-clear
          placeholder="全部"
          style="width: 120px"
          @change="onFilterChange"
        >
          <a-select-option value="pending">待处理</a-select-option>
          <a-select-option value="processing">处理中</a-select-option>
          <a-select-option value="done">已完成</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item>
        <a-space>
          <a-button type="primary" @click="loadList">查询</a-button>
          <a-button @click="resetFilters">重置</a-button>
          <a-button @click="onExport">批量导出</a-button>
        </a-space>
      </a-form-item>
    </a-form>

    <a-table
      row-key="id"
      :columns="columns"
      :data-source="list"
      :loading="loading"
      :pagination="pagination"
      :row-selection="{ selectedRowKeys, onChange: onSelectChange }"
      @change="onTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'level'">
          <a-tag :color="levelColor(record.level)">{{ levelText(record.level) }}</a-tag>
        </template>
        <template v-else-if="column.key === 'source'">
          <a-tag :color="record.presentationAsset ? 'orange' : 'green'">
            {{ record.presentationAsset ? '演示运行' : '真实工单' }}
          </a-tag>
        </template>
        <template v-else-if="column.key === 'status'">
          <span class="status-with-mood">
            <a-tooltip :title="workOrderMood(record).tip">
              <img class="mood" :src="workOrderMood(record).src" :alt="workOrderMood(record).label" />
            </a-tooltip>
            <a-tag>{{ statusText(record.status) }}</a-tag>
          </span>
        </template>
        <template v-else-if="column.key === 'action'">
          <a-button type="link" @click="openDetail(record)">详情处置</a-button>
        </template>
      </template>
    </a-table>

    <!-- 工单详情弹窗 -->
    <a-modal
      v-model:open="detailOpen"
      title="工单详情处置"
      width="820px"
      :footer="null"
      destroy-on-close
    >
      <template v-if="current">
        <div class="detail-mood">
          <img :src="workOrderMood(current).src" :alt="workOrderMood(current).label" />
          <div>
            <div class="mood-label">{{ workOrderMood(current).label }}</div>
            <div class="mood-tip">{{ workOrderMood(current).tip }}</div>
          </div>
        </div>
        <a-descriptions bordered size="small" :column="2">
          <a-descriptions-item label="工单号">{{ current.id }}</a-descriptions-item>
          <a-descriptions-item label="数据来源">
            <a-tag :color="current.presentationAsset ? 'orange' : 'green'">
              {{ current.presentationAsset ? '演示运行，不写入业务库' : '真实业务工单' }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="风险等级">
            <a-tag :color="levelColor(current.level)">{{ levelText(current.level) }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="区域">{{ current.area }}</a-descriptions-item>
          <a-descriptions-item label="处置单位">{{ current.team }}</a-descriptions-item>
          <a-descriptions-item label="责任人">{{ current.assignee }}</a-descriptions-item>
          <a-descriptions-item label="截止时间">{{ current.deadline }}</a-descriptions-item>
          <a-descriptions-item label="规范条文" :span="2">{{ current.regulation }}</a-descriptions-item>
        </a-descriptions>

        <!-- 抓拍图 + 掩码/标注对比（来自实时检测） -->
        <div class="compare">
          <div class="compare-item">
            <div class="label">原始抓拍</div>
            <div class="snap-box">
              <img v-if="current.snapUrl" :src="mediaUrl(current.snapUrl)" alt="原始抓拍" @error="onImgError" />
              <span v-else>暂无抓拍图</span>
            </div>
          </div>
          <div class="compare-item">
            <div class="label">AI 掩码标注</div>
            <div class="snap-box mask">
              <img
                v-if="current.maskUrl || current.overlayUrl"
                :src="mediaUrl(current.maskUrl || current.overlayUrl)"
                alt="AI标注"
                @error="onImgError"
              />
              <span v-else>暂无标注图</span>
            </div>
          </div>
        </div>

        <div v-if="current.evidenceImages?.length" class="evidence-list">
          <div class="label">整改复核证据</div>
          <img v-for="url in current.evidenceImages" :key="url" :src="mediaUrl(url)" alt="整改复核证据" />
        </div>

        <div v-if="canOperate" class="actions">
          <a-space>
            <a-button
              type="primary"
              :disabled="current.status === 'processing' || current.status === 'done'"
              @click="doAction('accept')"
            >接单处理</a-button>
            <a-button
              v-if="current.rawStatus === 'rectifying'"
              @click="pickEvidence"
            >上传整改证据</a-button>
            <a-button
              :disabled="current.status === 'done' || !['rectified'].includes(current.rawStatus)"
              @click="doAction('complete')"
            >复核通过并关闭</a-button>
            <a-button
              danger
              :disabled="current.rawStatus !== 'pending_confirmation'"
              @click="doAction('reject')"
            >驳回重检</a-button>
          </a-space>
        </div>

        <a-divider>流转日志</a-divider>
        <a-timeline>
          <a-timeline-item v-for="(log, i) in current.logs" :key="i">
            <span class="log-time">{{ log.time }}</span>
            {{ log.action }}
            <span class="log-user">（{{ log.user }}）</span>
          </a-timeline-item>
        </a-timeline>
      </template>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { exportWorkOrders, fetchWorkOrderStats, fetchWorkOrders, updateWorkOrderStatus, uploadWorkOrderEvidence } from '@/api/workorder'
import { fetchDetectJob } from '@/api/detect'
import { syncDetectJobToWorkOrders, patchDetectWorkOrder } from '@/utils/detectWorkOrders'
import { exportCsv } from '@/utils/export'
import { JR, workOrderMood } from '@/utils/jr'
import { subscribeModules } from '@/utils/moduleBus'
import { resolveBusinessMediaUrl, resolveDetectMediaUrl } from '@/utils/endpoints'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const userStore = useUserStore()
const canOperate = computed(() => ['admin', 'safety'].includes(userStore.role))
const loading = ref(false)
const list = ref([])
const selectedRowKeys = ref([])
const detailOpen = ref(false)
const current = ref(null)
const statusTab = ref('all')
const stats = reactive({ all: 0, pending: 0, processing: 0, done: 0 })

const query = reactive({
  keyword: '',
  level: undefined,
  status: undefined,
  page: 1,
  pageSize: 10,
})

/** 从路由带入筛选（仅首次进入） */
function applyRouteQuery() {
  const q = route.query.status
  if (q === 'pending' || q === 'processing' || q === 'done') {
    query.status = String(q)
    statusTab.value = String(q)
  } else if (q === 'all' || q === '') {
    query.status = undefined
    statusTab.value = 'all'
  }
  if (route.query.level) query.level = String(route.query.level)
  if (route.query.keyword) query.keyword = String(route.query.keyword)
}

function syncStatusTab() {
  statusTab.value = query.status || 'all'
}

function onStatusTabChange(key) {
  query.status = key === 'all' ? undefined : key
  pagination.current = 1
  loadList()
}

function onFilterChange() {
  syncStatusTab()
  pagination.current = 1
  loadList()
}

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
  showTotal: (t) => `共 ${t} 条`,
})

const columns = [
  { title: '工单号', dataIndex: 'id', key: 'id', width: 160 },
  { title: '标题', dataIndex: 'title', key: 'title' },
  { title: '来源', key: 'source', width: 110 },
  { title: '等级', key: 'level', width: 90 },
  { title: '类型', dataIndex: 'type', key: 'type', width: 120 },
  { title: '区域', dataIndex: 'area', key: 'area', width: 120 },
  { title: '处置单位', dataIndex: 'team', key: 'team', width: 110 },
  { title: '状态', key: 'status', width: 100 },
  { title: '创建时间', dataIndex: 'createTime', key: 'createTime', width: 170 },
  { title: '操作', key: 'action', width: 110 },
]

function levelColor(l) {
  return { red: 'red', orange: 'orange', yellow: 'gold' }[l]
}
function levelText(l) {
  return { red: '高危', orange: '中危', yellow: '低危' }[l]
}
function statusText(s) {
  return { pending: '待处理', processing: '处理中', done: '已完成' }[s]
}

/** 兼容检测桥接相对路径与 /detect-api 代理 */
function mediaUrl(url = '') {
  if (!url) return ''
  if (/^https?:\/\//i.test(url) || url.startsWith('blob:') || url.startsWith('data:')) return url
  if (url.startsWith('/detect-api/')) return url
  if (url.startsWith('/business-api/') || url.startsWith('/api/media-file')) return resolveBusinessMediaUrl(url)
  if (url.startsWith('/detect-api/') || url.startsWith('/api/detect/')) return resolveDetectMediaUrl(url)
  if (url.startsWith('/')) return url
  return `/detect-api/${url.replace(/^\//, '')}`
}

function onImgError(e) {
  e.target.style.display = 'none'
  const box = e.target.parentElement
  if (box && !box.querySelector('.img-fallback')) {
    const tip = document.createElement('span')
    tip.className = 'img-fallback'
    tip.textContent = '图片加载失败'
    box.appendChild(tip)
  }
}

async function loadList() {
  loading.value = true
  try {
    const res = await fetchWorkOrders({ ...query, page: pagination.current, pageSize: pagination.pageSize })
    list.value = res.data.list
    pagination.total = res.data.total
    const statRes = await fetchWorkOrderStats()
    Object.assign(stats, statRes.data)
    syncStatusTab()
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  query.keyword = ''
  query.level = undefined
  query.status = undefined
  statusTab.value = 'all'
  pagination.current = 1
  loadList()
}

function onTableChange(pag) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  loadList()
}

function onSelectChange(keys) {
  selectedRowKeys.value = keys
}

async function openDetail(record) {
  current.value = { ...record }
  detailOpen.value = true
  // 检测生成的工单若缺图，按任务号回填抓拍/标注
  if (record?.detectJobId?.startsWith('JOB-') && (!record.snapUrl || !record.maskUrl)) {
    try {
      const job = await fetchDetectJob(record.detectJobId)
      if (job?.status === 'done') {
        syncDetectJobToWorkOrders(job)
        const result = job.result || {}
        const snapUrl = mediaUrl(record.snapUrl || result.input_image || '')
        const maskUrl = mediaUrl(
          record.maskUrl ||
            record.overlayUrl ||
            result.overlays?.[0] ||
            result.masks?.[0] ||
            ''
        )
        if (snapUrl || maskUrl) {
          patchDetectWorkOrder(record.id, { snapUrl, maskUrl, overlayUrl: maskUrl })
          current.value = { ...current.value, snapUrl, maskUrl, overlayUrl: maskUrl }
        }
      }
    } catch {
      // 桥接离线时保持现有字段
    }
  } else if (current.value) {
    current.value = {
      ...current.value,
      snapUrl: mediaUrl(current.value.snapUrl),
      maskUrl: mediaUrl(current.value.maskUrl || current.value.overlayUrl),
    }
  }
}

async function doAction(action) {
  const res = await updateWorkOrderStatus({ id: current.value.id, action })
  const next = res.data?.status
  const label = { processing: '处理中', done: '已完成', pending: '待处理' }[next] || next
  message.success(label ? `操作成功，状态已更新为「${label}」` : '操作成功')
  const refreshed = (await fetchWorkOrders({ keyword: current.value.id, page: 1, pageSize: 1 })).data.list[0]
  if (refreshed) current.value = { ...refreshed }
  else if (next) current.value = { ...current.value, status: next }
  detailOpen.value = false
  await loadList()
}

function pickEvidence() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    await uploadWorkOrderEvidence({ id: current.value.id, file })
    message.success('整改证据已上传，工单进入待关闭状态')
    const refreshed = (await fetchWorkOrders({ keyword: current.value.id, page: 1, pageSize: 1 })).data.list[0]
    if (refreshed) current.value = { ...refreshed }
    await loadList()
  }
  input.click()
}

async function onExport() {
  try {
  const res = await exportWorkOrders({ ids: selectedRowKeys.value })
  if (!res.data?.length) { message.info('没有可导出的工单'); return }
  await exportCsv(res.data, '风险工单', [
    { key: 'id', title: '工单号' },
    { key: 'title', title: '标题' },
    { key: 'level', title: '等级' },
    { key: 'type', title: '类型' },
    { key: 'area', title: '区域' },
    { key: 'team', title: '处置单位' },
    { key: 'status', title: '状态' },
    { key: 'createTime', title: '创建时间' },
  ])
  } catch (error) { message.error(error.message || '工单导出失败') }
}

onMounted(() => {
  applyRouteQuery()
  loadList()
})

watch(
  () => [route.path, route.query.status, route.query.level, route.query.keyword, route.query.from],
  () => {
    if (route.path !== '/workorder') return
    applyRouteQuery()
    pagination.current = 1
    loadList()
  }
)

const unsub = subscribeModules((detail) => {
  if (detail?.type === 'workorders' || detail?.type === 'detect-results') {
    loadList()
  }
})
onBeforeUnmount(() => unsub())
</script>

<style scoped>
.page-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.page-title-row .page-title { margin-bottom: 0; }
.mood-legend {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: #8c8c8c;
}
.mood-legend span { display: inline-flex; align-items: center; gap: 4px; }
.mood-legend img { width: 28px; height: 28px; object-fit: contain; }
.status-with-mood {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.status-with-mood .mood {
  width: 32px;
  height: 32px;
  object-fit: contain;
}
.detail-mood {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fff7fb;
  border: 1px solid #ffd6e7;
}
.detail-mood img { width: 64px; height: 64px; object-fit: contain; }
.mood-label { font-weight: 600; color: #c41d7f; }
.mood-tip { font-size: 12px; color: #8c8c8c; }
.filter-bar { margin-bottom: 8px; }
.status-tabs { margin-bottom: 12px; }
.status-tabs :deep(.ant-tabs-nav) { margin-bottom: 0; }
.compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin: 16px 0;
}
.compare-item .label { margin-bottom: 6px; font-weight: 600; }
.snap-box {
  height: 200px;
  background: #f5f5f5;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8c8c8c;
  position: relative;
  overflow: hidden;
}
.snap-box.mask { background: #4e2c27; color: #ffd7bc; }
.snap-box img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  background: #4e2c27;
}
.img-fallback { color: #8c8c8c; font-size: 13px; }
.evidence-list { margin: 12px 0; }
.evidence-list .label { margin-bottom: 6px; font-weight: 600; }
.evidence-list img {
  width: 140px;
  height: 100px;
  object-fit: contain;
  margin-right: 8px;
  border-radius: 6px;
  background: #f5f5f5;
}
.actions { margin: 12px 0; }
.log-time { color: #8c8c8c; margin-right: 8px; }
.log-user { color: #8c8c8c; }
</style>
