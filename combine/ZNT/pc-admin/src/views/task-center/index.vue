<template>
  <div class="page-card">
    <div class="task-heading"><div><h2>检测任务中心</h2><p>后台任务独立执行，离开页面不会停止检测。历史记录从检测桥读取，重启后仍可查询。</p></div><a-button type="primary" @click="router.push('/realtime-detect')">新建检测</a-button></div>
    <a-alert v-if="error" type="warning" show-icon :message="error" style="margin-bottom:16px"><template #description>列表暂时无法更新，原任务不会因为刷新失败而取消。<router-link to="/help-center?tab=diagnostics">查看连接诊断 →</router-link></template></a-alert>
    <a-space wrap style="margin-bottom:16px">
      <a-select v-model:value="status" style="width:140px" :disabled="loading" @change="resetPage"><a-select-option value="">全部状态</a-select-option><a-select-option v-for="(label, key) in labels" :key="key" :value="key">{{ label }}</a-select-option></a-select>
      <a-button :loading="loading" @click="load">刷新列表</a-button>
      <span>每 5 秒自动刷新 · 只取消尚未开始的任务</span>
    </a-space>
    <a-table :data-source="items" :columns="columns" row-key="job_id" :loading="loading" :pagination="false" :scroll="{ x: 950 }">
      <template #emptyText><a-empty :description="error ? '暂时无法读取任务，请先恢复连接' : status ? '这个状态下还没有任务' : '还没有检测任务，从一张图片开始吧'"><a-button v-if="!error && !status" @click="router.push('/realtime-detect')">新建检测</a-button><a-button v-else-if="status && !error" @click="status='';resetPage()">查看全部状态</a-button></a-empty></template>
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'"><a-tag :color="colors[record.status]">{{ labels[record.status] || record.status }}</a-tag></template>
        <template v-else-if="column.key === 'profile'">{{ { demo:'演示', offline:'本地离线', standard:'云端' }[record.profile] || record.profile }}</template>
        <template v-else-if="column.key === 'elapsed'">{{ record.elapsed_ms == null ? '—' : (record.elapsed_ms / 1000).toFixed(1) + ' s' }}</template>
        <template v-else-if="column.key === 'action'">
          <a-space>
            <a-button size="small" @click="router.push({ path:'/realtime-detect', query:{ job: record.job_id } })">过程与结果</a-button>
            <a-button v-if="canOperate && record.status === 'queued'" size="small" danger :loading="busy === record.job_id" @click="act(record, false)">取消排队</a-button>
            <a-popconfirm v-if="canOperate && ['error','cancelled'].includes(record.status)" title="将重新推理并生成新任务，是否继续？" @confirm="act(record, true)"><a-button size="small" :loading="busy === record.job_id">重新检测</a-button></a-popconfirm>
          </a-space>
        </template>
      </template>
      <template #expandedRowRender="{ record }"><span>{{ record.error || '无错误。查看过程与结果可获取阶段信息、原图和风险证据。' }}</span></template>
    </a-table>
    <a-space style="margin-top:16px"><a-button :disabled="page === 0 || loading" @click="page--; load()">上一页</a-button><span>第 {{ page + 1 }} 页</span><a-button :disabled="items.length < pageSize || loading" @click="page++; load()">下一页</a-button></a-space>
  </div>
</template>
<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useUserStore } from '@/stores/user'
import { fetchTaskPage, cancelDetectJob, retryDetectJob } from '@/api/detect'
const router = useRouter(), user = useUserStore()
const items = ref([]), status = ref(''), error = ref(''), loading = ref(false), busy = ref(''), page = ref(0)
const pageSize = 20, canOperate = computed(() => ['admin','safety'].includes(user.role))
const labels = { queued:'排队中', running:'执行中', done:'已完成', error:'失败', cancelled:'已取消' }
const colors = { queued:'gold', running:'blue', done:'green', error:'red', cancelled:'default' }
const columns = [
  { title:'任务编号', dataIndex:'job_id', width:255 }, { title:'状态', key:'status', width:100 },
  { title:'模式', key:'profile', width:100 }, { title:'设备', dataIndex:'device_id', width:120 },
  { title:'创建时间', dataIndex:'created_at', width:195 }, { title:'处理耗时', key:'elapsed', width:110 },
  { title:'操作', key:'action', width:240 },
]
let timer, disposed = false
async function load() {
  if (loading.value || disposed) return
  clearTimeout(timer); loading.value = true
  try { const data = await fetchTaskPage({ limit:pageSize, offset:page.value * pageSize, status:status.value }); if (!disposed) { items.value = data; error.value = '' } }
  catch (e) { if (!disposed) error.value = e.response?.data?.detail || e.message || '连接失败，稍后自动重试' }
  finally { loading.value = false; if (!disposed) timer = setTimeout(load, 5000) }
}
function resetPage() { page.value = 0; load() }
async function act(record, retry) {
  busy.value = record.job_id
  try {
    const result = await (retry ? retryDetectJob(record.job_id) : cancelDetectJob(record.job_id))
    message.success(retry ? `已创建 ${result.job_id}` : '排队任务已取消')
    await load()
  } catch (e) { message.error(e.response?.data?.detail || e.message) }
  finally { busy.value = '' }
}
onMounted(load)
onBeforeUnmount(() => { disposed = true; clearTimeout(timer) })
</script>
<style scoped>
.task-heading { display:flex; justify-content:space-between; align-items:center; gap:20px; margin-bottom:20px; }
h2 { color:var(--text-primary); margin:0 0 8px; } p,span { color:var(--text-secondary); }
</style>
