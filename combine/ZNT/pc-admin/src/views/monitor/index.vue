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
        <a-radio-group :value="isDemo ? 'demo' : 'live'" size="small" @change="changeSourceMode"><a-radio-button value="live">真实设备</a-radio-button><a-radio-button value="demo">乐西演示设备</a-radio-button></a-radio-group>
        <a-radio-group v-model:value="grid" button-style="solid" size="small">
          <a-radio-button :value="1">单画面</a-radio-button>
          <a-radio-button :value="4">4 分栏</a-radio-button>
          <a-radio-button :value="9">9 分栏</a-radio-button>
          <a-radio-button :value="16">16 分栏</a-radio-button>
        </a-radio-group>
        <a-button size="small" @click="loadData">刷新</a-button>
        <a-button v-if="isAdmin" size="small" @click="openSources">视频源接入与任务控制</a-button>
      </a-space>
    </div>
    <a-alert v-if="isDemo" type="info" show-icon message="正常道路静态示例 · 非实时视频"
      description="摄像头名称与示例图按设备 ID 固定匹配。图片来自既有道路测试样例，不是乐西高速实景；不代表首页演示事件的当前状态，不产生告警或检测记录。" />
    <a-alert v-if="loadError" type="warning" show-icon :message="loadError" />
    <div v-if="selectedCamera" class="selected-camera-title">当前画面：<strong>{{ selectedCamera.name }}</strong><span>{{ selectedCamera.id }}</span><span v-if="isDemo">示例 {{ selectedCamera.sample }}</span></div>

    <div class="body">
      <!-- 左侧设备树 -->
      <div class="left-tree">
        <div class="panel-title">{{ isDemo ? '演示摄像头' : '设备树' }}</div>
        <a-tree
          v-if="treeData.length"
          :tree-data="treeData"
          default-expand-all
          :selected-keys="selectedCamId ? [selectedCamId] : []"
          @select="onSelect"
        >
          <template #title="{ title, online, isLeaf, presentationAsset }">
            <span>
              <a-badge v-if="isLeaf" :status="presentationAsset || online === false ? 'default' : 'success'" />
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
            :example-image="isDemo && cam.source === 'demo' ? cam.exampleImage : ''"
            :example-source="isDemo && cam.source === 'demo' ? cam.exampleSource : ''"
          />
          <div v-else class="empty-cell">空闲窗口</div>
        </div>
      </div>

      <!-- 右侧告警侧边栏 -->
      <div class="right-alarm">
        <div class="panel-title">{{ isDemo ? '示例说明' : '实时告警' }}</div>
        <div v-if="isDemo" class="alarm-empty">当前展示正常道路参考图片，不进行实时检测。<p>湿润和反光本身不作为路面积水异常。</p><p>可从左侧切换摄像头，或使用分栏同时查看。</p></div>
        <div v-else-if="!alarms.length" class="alarm-empty">{{ loadError ? '告警未加载' : '暂无告警' }}</div>
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
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import VideoPlayer from '@/components/VideoPlayer/index.vue'
import { deleteStreamSource, fetchCameras, fetchDeviceTree, fetchRealtimeAlarms, fetchStreamSourceLog, fetchStreamSources, saveStreamSource, startStreamSource, stopStreamSource } from '@/api/monitor'
import { message } from 'ant-design-vue'
import { demoCameras, demoDeviceTree } from '@/data/lexiCameras.js'
import { visibleCameras } from '@/utils/monitorSelection.js'

const route = useRoute()
const router = useRouter()
const isDemo=computed(()=>route.query.source==='demo')
const store = useUserStore()
const isAdmin = computed(() => store.role === 'admin')
const grid = ref(4)
const treeData = ref([])
const cameras = ref([])
const alarms = ref([])
const selectedCamId = ref('')
const selectedIds = ref([])
const loadError=ref('')
const selectedCamera=computed(()=>cameras.value.find(c=>c.id===selectedCamId.value))
let loadGeneration=0,disposed=false
function changeSourceMode(event){router.push({path:'/monitor',query:event.target.value==='demo'?{source:'demo'}:{}})}
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

const displayCams = computed(() => visibleCameras(cameras.value,selectedCamId.value,selectedIds.value,grid.value))

function levelText(l) {
  return { red: '高危', orange: '中危', yellow: '低危' }[l]
}
function statusText(s) {
  return { pending: '待处置', processing: '处置中', done: '已关闭' }[s] || s
}

function onSelect(keys, { node }) {
  if (!node.isLeaf) return
  const id = keys[0] || node.key
  if(!cameras.value.some(c=>c.id===id))return
  selectedCamId.value = id
  if (!selectedIds.value.includes(id)) {
    selectedIds.value = [id, ...selectedIds.value].slice(0, grid.value)
  }
  router.replace({path:'/monitor',query:{...route.query,cameraId:id,layout:String(grid.value)}})
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
  const generation=++loadGeneration
  const mode=isDemo.value,requested=typeof route.query.cameraId==='string'?route.query.cameraId:''
  loadError.value='';treeData.value=[];cameras.value=[];alarms.value=[];selectedIds.value=[];selectedCamId.value=''
  const requestedGrid=Number(route.query.layout)
  if([1,4,9,16].includes(requestedGrid))grid.value=requestedGrid
  try{
    if(mode){treeData.value=demoDeviceTree;cameras.value=demoCameras}
    else{
      const [t,c,a]=await Promise.all([fetchDeviceTree(),fetchCameras(),fetchRealtimeAlarms()])
      if(disposed||generation!==loadGeneration)return
      treeData.value=t.data;cameras.value=c.data;alarms.value=a.data
    }
    const found=cameras.value.find(c=>c.id===requested)
    if(requested&&!found){loadError.value='未找到指定摄像头，请从左侧设备树选择。';return}
    selectedCamId.value=found?.id||cameras.value[0]?.id||''
    selectedIds.value=selectedCamId.value?[selectedCamId.value]:[]
  }catch{
    if(!disposed&&generation===loadGeneration)loadError.value='真实监控数据加载失败，请检查业务服务；未切换为演示画面。'
  }
}

watch(()=>[route.query.source,route.query.cameraId,route.query.layout],loadData,{immediate:true})
onBeforeUnmount(()=>{disposed=true;loadGeneration++})
</script>

<style scoped>
.monitor-page { display:flex;flex-direction:column;gap:12px;min-height:650px;height:calc(100vh - 200px); }
.toolbar :deep(.ant-space){flex-wrap:wrap}.selected-camera-title{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--text-secondary)}.selected-camera-title strong{color:var(--text-primary)}.selected-camera-title>span{font-size:10px;color:var(--text-muted)}
.toolbar {
  background: var(--surface);
  border-radius: 8px;
  padding: 10px 16px;
  border: 1px solid var(--border-color);
}
.body { flex: 1; display: flex; gap: 12px; min-height: 0; }
.left-tree, .right-alarm {
  width: 205px;flex-shrink:0;
  background: var(--surface);
  border-radius: 8px;
  padding: 12px;
  overflow: auto;
  border: 1px solid var(--border-color);
}
.panel-title { font-weight: 600; margin-bottom: 10px; color: var(--text-primary); }
.left-tree :deep(.ant-tree){font-size:12px}.left-tree :deep(.ant-tree-indent-unit){width:12px}.left-tree :deep(.ant-tree-switcher){width:16px;flex-basis:16px}
.center-grid {
  flex: 1;
  display: grid;
  gap: 6px;
  background: var(--media-bg);
  border-radius: 8px;
  padding: 6px;
  min-height: 0;min-width:0;
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
  color: var(--text-muted);
  background: var(--surface-2);
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
  color: var(--text-secondary);
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
@media(max-width:1400px){.right-alarm{width:170px}.left-tree{width:190px}}
@media(max-width:1100px){.body{flex-wrap:wrap}.right-alarm{width:100%;max-height:130px}.center-grid{min-height:340px}.monitor-page{height:auto;min-height:0}.selected-camera-title{flex-wrap:wrap}}
@media(max-width:650px){.left-tree{width:100%;max-height:180px}.center-grid{flex-basis:100%}.toolbar{padding:10px}}
</style>
