<template>
  <main class="highway-dashboard">
    <header class="overview-heading">
      <div><p class="eyebrow">SMARTROAD-HIGHWAY <span>/</span> CORRIDOR OVERVIEW</p><h1>高速公路运行概况<span class="demo-pill">演示模式</span></h1><p class="heading-sub">乐西高速 · 山区桥隧路段 <span>感知设备 / 路况风险 / 空间定位</span></p></div>
      <div class="heading-actions"><a-button @click="$router.push('/task-center')">历史检测档案</a-button><a-button type="primary" @click="$router.push('/realtime-detect')"><RadarChartOutlined /> 新建真实检测</a-button></div>
    </header>
    <div class="demo-notice"><InfoCircleOutlined /><span>{{ corridor.notice }} 以下数值仅为演示，不计入真实检测统计。</span><a :href="corridor.reference" target="_blank" rel="noopener noreferrer">路线背景 ↗</a></div>
    <section class="overview-metrics" aria-label="演示概况指标">
      <article v-for="m in metrics" :key="m.label" :class="m.color"><div class="metric-icon"><component :is="m.icon" /></div><div><span>{{ m.label }}</span><strong>{{ String(m.value).padStart(2,'0') }}<small>{{ m.unit }}</small></strong></div><b class="metric-note">{{ m.note }}</b></article>
    </section>
    <div class="overview-filters"><div class="layer-controls"><span class="filter-label">地图图层</span><button :aria-pressed="layers.devices" @click="layers.devices=!layers.devices">{{ layers.devices ? '✓' : '−' }} 设备点位</button><button :aria-pressed="layers.risks" @click="layers.risks=!layers.risks">{{ layers.risks ? '✓' : '−' }} 路况事件</button></div><div class="severity-filter"><span class="filter-label">路况筛选</span><button v-for="f in filters" :key="f.key" :aria-pressed="severity===f.key" @click="severity=f.key">{{ f.name }}</button></div></div>
    <section class="spatial-workspace">
      <HighwayScene ref="scene" :selected-id="selectedId" :layers="layers" :severity="severity" @select="selectPoint" />
      <aside class="detail-panel" aria-label="选中点位详情">
        <header class="panel-heading"><span class="section-index">02 /</span><strong>点位详情</strong><span class="panel-count">虚构示例</span></header>
        <div class="detail-body" aria-live="polite">
          <template v-if="selectedReport">
            <div class="detail-meta"><span class="severity-tag" :class="selectedReport.severity">{{ severityLabels[selectedReport.severity] }}</span><span>{{ selectedReport.id }}</span></div>
            <h2>{{ selectedReport.title }}</h2><div class="detail-location"><EnvironmentOutlined /> {{ selectedReport.chainage }} <span>示意桩号</span></div>
            <dl class="detail-facts"><div><dt>模拟时刻</dt><dd>{{ selectedReport.time }}</dd></div><div><dt>事件类别</dt><dd>{{ selectedReport.category }}</dd></div><div><dt>示例状态</dt><dd class="text-amber">{{ selectedReport.status }}</dd></div></dl>
            <section class="report-excerpt"><h3>观察与影响</h3><p>{{ selectedReport.observation }}</p><p>{{ selectedReport.impact }}</p></section>
            <section class="report-excerpt"><h3>处置建议 · 示例</h3><p>{{ selectedReport.action }}</p></section>
            <div class="boundary-note"><CheckCircleOutlined />{{ selectedReport.boundary }}</div>
            <button class="linked-device" @click="selectPoint(selectedReport.deviceId)"><VideoCameraOutlined /> {{ linkedDevice?.name }} <span>↗</span></button>
            <div class="detail-actions"><a-button size="small" @click="locateSelected"><AimOutlined /> 定位</a-button><a-button size="small" type="primary" @click="exportReport"><DownloadOutlined /> 导出演示报告</a-button></div>
            <p class="evidence-note">无现场原图或推理证据；不写入历史检测档案。</p>
          </template>
          <template v-else-if="selectedDevice">
            <div class="detail-meta"><span class="device-status" :class="selectedDevice.state">{{ deviceStateLabels[selectedDevice.state] }}</span><span>{{ selectedDevice.short }}</span></div>
            <h2>{{ selectedDevice.name }}</h2><div class="detail-location"><EnvironmentOutlined /> {{ selectedDevice.chainage }} <span>示意桩号</span></div>
            <div class="device-diagram" aria-hidden="true"><VideoCameraOutlined v-if="selectedDevice.type==='视频感知'"/><DeploymentUnitOutlined v-else/><span>{{ selectedDevice.type }}</span></div>
            <dl class="detail-facts"><div><dt>设备编号</dt><dd>{{ selectedDevice.id }}</dd></div><div><dt>示例规格</dt><dd>{{ selectedDevice.spec }}</dd></div><div><dt>模拟状态</dt><dd>{{ selectedDevice.metric }}</dd></div></dl>
            <section class="report-excerpt"><h3>监测用途</h3><p>{{ selectedDevice.detail }}</p></section>
            <section class="report-excerpt"><h3>关联演示报告</h3><button v-for="r in relatedReports" :key="r.id" class="related-report" @click="selectPoint(r.id)">{{ r.title }} ↗</button><p v-if="!relatedReports.length">该演示点位暂无关联报告。</p></section>
            <a-button v-if="cameraMonitorLocation(selectedDevice.id)" size="small" type="primary" block @click="openCamera(selectedDevice.id)"><VideoCameraOutlined /> 查看监控示例</a-button>
            <a-button size="small" block style="margin-top:8px" @click="locateSelected"><AimOutlined /> 在模型中定位</a-button><p class="evidence-note">设备、状态与参数均为虚构，未连接摄像头或雷达。</p>
          </template>
          <div v-else class="detail-empty"><AimOutlined /><p>选择模型上的点位，或从下方列表查看详情。</p></div>
        </div>
      </aside>
    </section>
    <section class="records-grid">
      <section class="record-panel"><header class="panel-heading"><span class="section-index">03 /</span><strong>路况报告</strong><span class="panel-count">{{ filteredReports.length }} 份演示</span></header>
        <div class="report-list"><button v-for="r in filteredReports" :key="r.id" class="report-row" :class="{ selected:selectedId===r.id }" :aria-pressed="selectedId===r.id" @click="selectPoint(r.id)"><span class="severity-tag" :class="r.severity">{{ severityLabels[r.severity] }}</span><span class="report-row-copy"><b>{{ r.title }}</b><small>{{ r.chainage }} · 示意桩号 · {{ r.status }}</small></span><time>{{ r.time }}</time><span class="row-arrow">↗</span></button></div>
        <div class="normal-note"><CheckCircleOutlined /><div><strong>{{ normalSection.name }}</strong><span>{{ normalSection.description }}</span></div></div>
      </section>
      <section class="record-panel"><header class="panel-heading"><span class="section-index">04 /</span><strong>沿线设备台账</strong><span class="panel-count">{{ devices.length }} 台演示</span></header>
        <p class="device-list-hint">摄像头名称：单击看详情，双击打开监控示例；键盘按 Enter 打开。</p>
        <div class="device-table-wrap"><table class="device-table"><thead><tr><th>设备 / 点位</th><th>示意桩号</th><th>模拟状态</th><th><span class="sr-only">操作</span></th></tr></thead><tbody><tr v-for="d in devices" :key="d.id" :class="{ selected:selectedId===d.id }"><td><button :title="cameraMonitorLocation(d.id) ? '双击打开此摄像头的监控示例' : '查看设备详情'" @click="selectPoint(d.id)" @dblclick="openCamera(d.id)" @keydown.enter.prevent="cameraMonitorLocation(d.id) ? openCamera(d.id) : selectPoint(d.id)"><span class="device-code">{{ d.short }}</span>{{ d.name }}</button></td><td>{{ d.chainage }}</td><td><span class="device-status" :class="d.state">{{ deviceStateLabels[d.state] }}</span></td><td><button :aria-label="`定位${d.name}`" @click="selectPoint(d.id); locateSelected()">⌖</button></td></tr></tbody></table></div>
      </section>
    </section>
    <footer class="overview-footer"><span>LABORATORY PROTOTYPE <i>/</i> 演示与真实检测分开记录</span><router-link to="/help-center">使用与支持 →</router-link></footer>
  </main>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { cameraMonitorLocation } from '@/data/lexiCameras.js'
import { AimOutlined, CheckCircleOutlined, DeploymentUnitOutlined, DownloadOutlined, EnvironmentOutlined, FileTextOutlined, InfoCircleOutlined, RadarChartOutlined, VideoCameraOutlined, WarningOutlined } from '@ant-design/icons-vue'
import HighwayScene from '@/components/HighwayScene/index.vue'
import { corridor, devices, reports, normalSection, severityLabels, deviceStateLabels, demoSummary, selectReports, demoReportMarkdown } from '@/data/lexiDemo.js'
import { saveFile } from '@/utils/saveFile'
const summary=demoSummary(),layers=reactive({devices:true,risks:true}),severity=ref('all'),scene=ref(null)
const selectedId=ref(reports[0].id)
const router=useRouter()
function openCamera(id){const target=cameraMonitorLocation(id);if(target)router.push(target)}
const metrics=[
  {label:'演示设备总数',value:summary.devices,unit:'台',icon:DeploymentUnitOutlined,note:'沿线感知点位',color:'cyan'},
  {label:'模拟在线设备',value:summary.online,unit:`/ ${summary.devices}`,icon:CheckCircleOutlined,note:'1 离线 · 1 检修',color:'green'},
  {label:'严重路况示例',value:summary.critical,unit:'项',icon:WarningOutlined,note:'积水淹没 / 落石',color:'red'},
  {label:'待复核报告示例',value:summary.reports,unit:'份',icon:FileTextOutlined,note:'点击点位查看',color:'amber'},
]
const filters=[{key:'all',name:'全部'},{key:'critical',name:'严重'},{key:'warning',name:'关注'}]
const filteredReports=computed(()=>selectReports(severity.value))
const selectedReport=computed(()=>reports.find(r=>r.id===selectedId.value))
const selectedDevice=computed(()=>devices.find(d=>d.id===selectedId.value))
const linkedDevice=computed(()=>devices.find(d=>d.id===selectedReport.value?.deviceId))
const relatedReports=computed(()=>reports.filter(r=>r.deviceId===selectedId.value))
function selectPoint(id){
  if(reports.some(r=>r.id===id)){layers.risks=true;const r=reports.find(r=>r.id===id);if(severity.value!=='all'&&severity.value!==r.severity)severity.value='all'}
  else if(devices.some(d=>d.id===id))layers.devices=true
  else return
  selectedId.value=id
}
watch(severity,()=>{if(selectedReport.value&&!filteredReports.value.includes(selectedReport.value))selectedId.value=filteredReports.value[0]?.id||''})
function locateSelected(){scene.value?.focus(selectedId.value)}
async function exportReport(){
  if(!selectedReport.value)return
  try{await saveFile(new Blob([demoReportMarkdown(selectedReport.value)],{type:'text/markdown;charset=utf-8'}),`演示路况报告_${selectedReport.value.id}.md`)}
  catch{message.error('报告保存失败，请重试。')}
}
</script>

<style scoped src="./highway-overview.css"></style>
