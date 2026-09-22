<template>
  <!--
    ② 实时视频监控页
    业务：设备树选路 → 多分栏画布 → 风险掩码叠加 → 右侧实时告警
  -->
  <div class="monitor-page">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <a-space>
        <span class="page-title" style="margin: 0">实时视频监控</span>
        <a-radio-group v-model:value="grid" button-style="solid" size="small">
          <a-radio-button :value="4">4 分栏</a-radio-button>
          <a-radio-button :value="9">9 分栏</a-radio-button>
          <a-radio-button :value="16">16 分栏</a-radio-button>
        </a-radio-group>
        <a-button size="small" @click="loadData">刷新</a-button>
        <a-button v-if="isAdmin" size="small" @click="openSources">视频源接入与任务控制</a-button>
      </a-space>
    </div>

    <div class="body">
      <!-- 左侧设备树 -->
      <div class="left-tree">
        <div class="panel-title">设备树</div>
        <a-tree
          v-if="treeData.length"
          :tree-data="treeData"
          default-expand-all
          @select="onSelect"
        >
          <template #title="{ title, online, isLeaf }">
            <span>
              <a-badge v-if="isLeaf" :status="online === false ? 'default' : 'success'" />
              {{ title }}
            </span>
          </template>
        </a-tree>
      </div>

      <!-- 中间视频画布 -->
      <div class="center-grid" :style="gridStyle">
        <div
          v-for="(cam, idx) in displayCams"
          :key="cam?.id || 'empty-' + idx"
          class="grid-cell"
          :class="{ active: selectedCamId === cam?.id }"
          @click="cam && (selectedCamId = cam.id)"
        >
          <VideoPlayer
            v-if="cam"
            :name="cam.name"
            :stream-url="cam.streamUrl"
            :online="cam.online"
            :masks="cam.masks"
          />
          <div v-else class="empty-cell">空闲窗口</div>
        </div>
      </div>

      <!-- 右侧告警侧边栏 -->
      <div class="right-alarm">
        <div class="panel-title">实时告警</div>
        <div v-if="!alarms.length" class="alarm-empty">暂无告警</div>
        <div
          v-for="a in alarms"
          :key="a.id"
          class="alarm-item"
          @click="focusCamera(a.camera)"
        >
          <div class="alarm-title">
            <span class="lv" :class="'lv-' + a.level">{{ levelText(a.level) }}</span>
            {{ a.title }}
          </div>
          <div class="alarm-meta">{{ a.camera }} · {{ a.time }} · {{ statusText(a.status) }}</div>
        </div>
      </div>
    </div>
    <a-modal v-model:open="sourceOpen" title="RTSP/视频源接入" width="760px" :footer="null">
      <a-form layout="vertical" :model="sourceForm">
        <a-row :gutter="12">
          <a-col :span="8"><a-form-item label="设备ID"><a-input v-model:value="sourceForm.id" /></a-form-item></a-col>
          <a-col :span="8"><a-form-item label="名称"><a-input v-model:value="sourceForm.name" /></a-form-item></a-col>
          <a-col :span="8"><a-form-item label="全图审核"><a-select v-model:value="sourceForm.audit_minutes"><a-select-option :value="30">30分钟</a-select-option><a-select-option :value="120">2小时</a-select-option></a-select></a-form-item></a-col>
        </a-row>
        <a-form-item label="RTSP/视频文件地址"><a-input v-model:value="sourceForm.stream_url" placeholder="rtsp://... 或本地视频绝对路径" /></a-form-item>
        <a-form-item label="窗口预览地址（可选）"><a-input v-model:value="sourceForm.preview_url" placeholder="http(s) FLV/MP4/WebM；RTSP需转预览流，预览不参与检测" /></a-form-item>
        <a-row :gutter="12"><a-col :span="8"><a-form-item label="现场ID"><a-input v-model:value="sourceForm.site_id" /></a-form-item></a-col><a-col :span="8"><a-form-item label="检测配置"><a-select v-model:value="sourceForm.profile"><a-select-option value="offline">本地离线</a-select-option><a-select-option value="standard">云端增强</a-select-option></a-select></a-form-item></a-col><a-col :span="8"><a-form-item label="初筛间隔（秒）"><a-input-number v-model:value="sourceForm.interval_seconds" :min="0.5" :max="300" style="width:100%" /></a-form-item></a-col></a-row>
        <a-space><a-button type="primary" @click="saveSource">保存配置</a-button><a-button @click="resetSourceForm">清空</a-button></a-space>
      </a-form>
      <a-divider>已配置视频源</a-divider>
      <a-list bordered :data-source="sources">
        <template #renderItem="{ item }"><a-list-item>
          <a-list-item-meta :title="`${item.name}（${item.id}）`" :description="item.stream_url" />
          <a-space><a-tag :color="item.worker_running ? 'green' : 'default'">{{ item.worker_running ? `监测中 PID ${item.worker_pid}` : '未启动' }}</a-tag>
            <a-button size="small" @click="editSource(item)">编辑</a-button>
            <a-button size="small" type="primary" :disabled="item.worker_running" @click="toggleSource(item, true)">启动</a-button>
            <a-button size="small" danger :disabled="!item.worker_running" @click="toggleSource(item, false)">停止</a-button>
            <a-button size="small" @click="showLog(item)">日志</a-button>
            <a-popconfirm title="删除该视频源配置？运行任务会先停止。" @confirm="removeSource(item)"><a-button size="small" danger>删除</a-button></a-popconfirm></a-space>
        </a-list-item></template>
      </a-list>
    </a-modal>
    <a-modal v-model:open="logOpen" title="持续监测日志" width="820px" :footer="null"><pre class="source-log">{{ sourceLog || '暂无日志' }}</pre></a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import VideoPlayer from '@/components/VideoPlayer/index.vue'
import { deleteStreamSource, fetchCameras, fetchDeviceTree, fetchRealtimeAlarms, fetchStreamSourceLog, fetchStreamSources, saveStreamSource, startStreamSource, stopStreamSource } from '@/api/monitor'
import { message } from 'ant-design-vue'

const route = useRoute()
const store = useUserStore()
const isAdmin = computed(() => store.role === 'admin')
const grid = ref(4)
const treeData = ref([])
const cameras = ref([])
const alarms = ref([])
const selectedCamId = ref('')
const selectedIds = ref([])
const sourceOpen = ref(false)
const sources = ref([])
const sourceForm = ref({ id: 'CAM-RTSP-01', name: '现场摄像头', stream_url: '', preview_url: '', site_id: 'SITE-DEFAULT', profile: 'offline', interval_seconds: 2, audit_minutes: 30 })
const logOpen = ref(false), sourceLog = ref('')

function resetSourceForm() { sourceForm.value = { id: '', name: '', stream_url: '', preview_url: '', site_id: 'SITE-DEFAULT', profile: 'offline', interval_seconds: 2, audit_minutes: 30 } }
function editSource(item) { sourceForm.value = { ...item } }

async function openSources() {
  sources.value = (await fetchStreamSources()).data
  sourceOpen.value = true
}
async function saveSource() {
  if (!sourceForm.value.id || !sourceForm.value.stream_url) return message.warning('请填写设备ID与视频源地址')
  await saveStreamSource(sourceForm.value); message.success('视频源配置已保存'); await openSources(); await loadData()
}
async function toggleSource(item, start) {
  if (start) await startStreamSource(item.id); else await stopStreamSource(item.id)
  message.success(start ? '持续监测已启动' : '持续监测已停止'); await openSources(); await loadData()
}
async function removeSource(item) { await deleteStreamSource(item.id); message.success('视频源已删除'); await openSources(); await loadData() }
async function showLog(item) { const res = await fetchStreamSourceLog(item.id); sourceLog.value = (res.data.lines || []).join('\n'); logOpen.value = true }

const gridStyle = computed(() => {
  const n = Math.sqrt(grid.value)
  return {
    gridTemplateColumns: `repeat(${n}, 1fr)`,
    gridTemplateRows: `repeat(${n}, 1fr)`,
  }
})

const displayCams = computed(() => {
  const ids = selectedIds.value.length
    ? selectedIds.value
    : cameras.value.slice(0, grid.value).map((c) => c.id)
  const list = ids.slice(0, grid.value).map((id) => cameras.value.find((c) => c.id === id))
  while (list.length < grid.value) list.push(null)
  return list
})

function levelText(l) {
  return { red: '高危', orange: '中危', yellow: '低危' }[l]
}
function statusText(s) {
  return { pending: '待处置', processing: '处置中', done: '已关闭' }[s] || s
}

function onSelect(keys, { node }) {
  if (!node.isLeaf) return
  const id = keys[0]
  selectedCamId.value = id
  if (!selectedIds.value.includes(id)) {
    selectedIds.value = [id, ...selectedIds.value].slice(0, grid.value)
  }
}

function focusCamera(camLabel) {
  // CAM-04 → cam-04
  const id = camLabel.toLowerCase().replace('cam-', 'cam-')
  const found = cameras.value.find((c) => c.id === id || c.name.includes(camLabel))
  if (found) {
    selectedCamId.value = found.id
    selectedIds.value = [found.id, ...selectedIds.value.filter((x) => x !== found.id)].slice(0, grid.value)
  }
}

async function loadData() {
  const [t, c, a] = await Promise.all([
    fetchDeviceTree(),
    fetchCameras(),
    fetchRealtimeAlarms(),
  ])
  treeData.value = t.data
  cameras.value = c.data
  alarms.value = a.data

  // 支持从驾驶舱点位跳转
  if (route.query.cameraId) {
    selectedIds.value = [route.query.cameraId]
    selectedCamId.value = route.query.cameraId
  }
}

onMounted(loadData)
</script>

<style scoped>
.monitor-page { display: flex; flex-direction: column; gap: 12px; height: calc(100vh - 120px); }
.toolbar {
  background: var(--surface);
  border-radius: 8px;
  padding: 10px 16px;
  border: 1px solid var(--border-color);
}
.body { flex: 1; display: flex; gap: 12px; min-height: 0; }
.left-tree, .right-alarm {
  width: 240px;
  background: var(--surface);
  border-radius: 8px;
  padding: 12px;
  overflow: auto;
  border: 1px solid var(--border-color);
}
.panel-title { font-weight: 600; margin-bottom: 10px; color: var(--text-primary); }
.center-grid {
  flex: 1;
  display: grid;
  gap: 6px;
  background: #141414;
  border-radius: 8px;
  padding: 6px;
  min-height: 0;
}
.grid-cell {
  min-height: 0;
  border: 2px solid transparent;
  border-radius: 4px;
  overflow: hidden;
}
.grid-cell.active { border-color: var(--primary); }
.empty-cell {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8c8c8c;
  background: #1f1f1f;
}
.alarm-item {
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color);
  cursor: pointer;
}
.alarm-item:hover .alarm-title { color: var(--link); }
.alarm-item:last-child { border-bottom: none; }
.alarm-empty {
  padding: 16px 0;
  font-size: 12px;
  color: #bfbfbf;
}
.alarm-title {
  font-size: 13px;
  margin-bottom: 2px;
  color: var(--text-primary);
  line-height: 1.4;
}
.alarm-meta { font-size: 12px; color: var(--text-secondary); }
.lv {
  font-size: 12px;
  font-weight: 600;
  margin-right: 6px;
}
.lv-red { color: var(--danger); }
.lv-orange { color: var(--warning); }
.lv-yellow { color: var(--caution); }
.source-log { max-height: 560px; overflow: auto; white-space: pre-wrap; background: #101820; color: #dbe6ec; padding: 14px; border-radius: 6px; }
</style>
