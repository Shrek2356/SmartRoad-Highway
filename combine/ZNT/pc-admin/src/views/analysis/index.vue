<template>
  <!--
    ④ 智能复盘分析页
    业务：隐患趋势 / 区域热力 / 处置单位事件 → 报告导出 PDF
  -->
  <div class="page-card">
    <div class="head">
      <div class="page-title" style="margin: 0">智能复盘分析</div>
      <a-space wrap>
        <a-range-picker
          v-model:value="dateRange"
          format="YYYY-MM-DD"
          :allow-clear="true"
          :presets="rangePresets"
        />
        <a-button type="primary" :loading="loading" @click="loadData">查询</a-button>
        <a-button :loading="exporting" :disabled="loading || !!loadError || analysisEmpty || !rangeLabel" @click="onExport">导出报告</a-button>
      </a-space>
    </div>
    <a-alert v-if="loadError" type="error" show-icon :message="loadError" description="保留的图表不是本次查询结果，请重新查询；恢复前暂停报告导出。" style="margin-bottom:16px" />
    <div v-if="rangeLabel" class="range-tip">
      当前统计区间：{{ rangeLabel }}（共 {{ rangeDays }} 天）
      <a-tag v-if="analysisPresentation" color="cyan">演示复盘数据</a-tag>
      <a-tag v-else color="green">真实业务统计</a-tag>
    </div>

    <a-alert
      v-if="analysisPresentation"
      class="empty-tip"
      type="warning"
      show-icon
      message="当前区间没有真实事件，已保留演示复盘图表"
      :description="sourceNote"
    />

    <a-alert
      v-else-if="analysisEmpty"
      class="empty-tip"
      type="info"
      show-icon
      message="当前日期范围暂无复盘数据"
      description="请切换到包含历史检测事件的日期，或选择“近30天”后重新查询。"
    />

    <div ref="reportRef" class="report-capture">
      <a-row :gutter="16">
        <a-col :span="12">
          <div class="chart-panel">
            <div ref="trendRef" class="chart" />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="chart-panel">
            <div ref="heatRef" class="chart" />
          </div>
        </a-col>
        <a-col :span="24" style="margin-top: 16px">
          <div class="chart-panel">
            <div ref="teamRef" class="chart" style="height: 320px" />
          </div>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import { exportAnalysisReport, fetchAnalysisData } from '@/api/analysis'
import { colorTheme } from '@/utils/theme'
import { fontPercent } from '@/utils/displayPreferences'
import { chartTheme } from '@/utils/designTokens'
import { useUserStore } from '@/stores/user'
import { createRequestGate } from '@/utils/requestGate'
import { saveFile } from '@/utils/saveFile'

const dateRange = ref([dayjs().subtract(6, 'day'), dayjs()])
const loading = ref(false)
const loadError = ref('')
const requests = createRequestGate()
const exporting = ref(false)
const rangeMeta = ref({ start: '', end: '', days: 7 })
const analysisEmpty = ref(false)
const analysisPresentation = ref(false)
const sourceNote = ref('')
const trendRef = ref(null)
const heatRef = ref(null)
const teamRef = ref(null)
const reportRef = ref(null)
let charts = []
let lastData = null
const userStore = useUserStore()

const rangePresets = [
  { label: '近7天', value: [dayjs().subtract(6, 'day'), dayjs()] },
  { label: '近14天', value: [dayjs().subtract(13, 'day'), dayjs()] },
  { label: '近30天', value: [dayjs().subtract(29, 'day'), dayjs()] },
]

const rangeLabel = computed(() => {
  if (!rangeMeta.value.start) return ''
  return `${rangeMeta.value.start} ~ ${rangeMeta.value.end}`
})
const rangeDays = computed(() => rangeMeta.value.days || 0)

function queryParams() {
  const [s, e] = dateRange.value || []
  return {
    startDate: s ? dayjs(s).format('YYYY-MM-DD') : undefined,
    endDate: e ? dayjs(e).format('YYYY-MM-DD') : undefined,
    projectId: userStore.project?.id || undefined,
  }
}

async function loadData() {
  const ticket = requests.begin()
  const params = queryParams()
  loading.value = true
  loadError.value = ''
  try {
    const res = await fetchAnalysisData(params)
    if (!requests.current(ticket)) return
    const { trend, areaHeat, teamViolation, range } = res.data
    lastData = res.data
    analysisPresentation.value = Boolean(res.data.presentationAsset)
    sourceNote.value = res.data.sourceNote || ''
    const total = [
      ...(trend?.red || []),
      ...(trend?.orange || []),
      ...(trend?.yellow || []),
      ...(areaHeat || []).map((item) => item.value),
      ...(teamViolation || []).map((item) => item.count),
    ].reduce((sum, value) => sum + (Number(value) || 0), 0)
    analysisEmpty.value = total === 0
    rangeMeta.value = range || {
      start: params.startDate || '',
      end: params.endDate || '',
      days: trend?.dates?.length || 0,
    }
    await nextTick()
    if (requests.current(ticket)) renderCharts()
  } catch (error) {
    if (requests.current(ticket)) loadError.value = error?.response?.data?.detail || '复盘数据读取失败，请检查连接后重试'
  } finally {
    if (requests.current(ticket)) loading.value = false
  }
}

function renderCharts() {
    if (!lastData || !trendRef.value || !heatRef.value || !teamRef.value) return
    const { trend, areaHeat, teamViolation } = lastData
    charts.forEach((c) => c.dispose())
    charts = []

    const visual = chartTheme(colorTheme.value, fontPercent.value/100)
    const chartText = visual.text
    const chartGrid = visual.grid
    const titleStyle = { color: chartText, fontSize: Math.round(14*fontPercent.value/100), fontWeight: 600 }
    const axisLine = { lineStyle: { color: chartGrid } }
    const axisLabel = { color: chartText, fontSize:visual.fontSize }

    const t = echarts.init(trendRef.value)
    charts.push(t)
    t.setOption({
      backgroundColor: 'transparent',
      title: { text: `隐患趋势（${rangeMeta.value.days || trend.dates.length}天）`, textStyle: titleStyle },
      tooltip: { ...visual.tooltip, trigger: 'axis' },
      legend: { data: ['高危', '中危', '低危'], textStyle: { color: chartText, fontSize:visual.fontSize } },
      grid: { left: 40, right: 16, top: 48, bottom: 28 },
      xAxis: { type: 'category', data: trend.dates, axisLine, axisLabel },
      yAxis: { type: 'value', minInterval: 1, axisLine, axisLabel, splitLine: { lineStyle: { color: chartGrid } } },
      series: [
        { name: '高危', type: 'line', data: trend.red, itemStyle: { color: visual.danger } },
        { name: '中危', type: 'line', data: trend.orange, itemStyle: { color: visual.warning } },
        { name: '低危', type: 'line', data: trend.yellow, itemStyle: { color: visual.caution } },
      ],
    })

    const h = echarts.init(heatRef.value)
    charts.push(h)
    h.setOption({
      backgroundColor: 'transparent',
      title: { text: '区域隐患热力', textStyle: titleStyle },
      tooltip: visual.tooltip,
      grid: { left: 48, right: 72, top: 48, bottom: 56 },
      xAxis: { type: 'category', data: areaHeat.map((i) => i.name), axisLine, axisLabel: { ...axisLabel, rotate: 30 } },
      yAxis: { type: 'value', axisLine, axisLabel, splitLine: { lineStyle: { color: chartGrid } } },
      visualMap: {
        min: 0,
        max: Math.max(20, ...areaHeat.map((i) => i.value)),
        calculable: true,
        orient: 'vertical',
        right: 8,
        top: 'middle',
        itemWidth: 12,
        itemHeight: 100,
        text: ['高', '低'],
        textGap: 8,
        textStyle: { color: chartText },
        inRange: { color: [visual.caution, visual.warning, visual.danger] },
      },
      series: [{
        type: 'bar',
        data: areaHeat.map((i) => i.value),
        itemStyle: {
          color: (p) => {
            const v = p.value
            if (v >= 12) return visual.danger
            if (v >= 6) return visual.warning
            return visual.caution
          },
        },
      }],
    })

    const tm = echarts.init(teamRef.value)
    charts.push(tm)
    tm.setOption({
      backgroundColor: 'transparent',
      title: { text: '处置单位事件统计', textStyle: titleStyle },
      tooltip: visual.tooltip,
      grid: { left: 80, right: 24, top: 48, bottom: 28 },
      xAxis: { type: 'value', axisLine, axisLabel, splitLine: { lineStyle: { color: chartGrid } } },
      yAxis: { type: 'category', data: teamViolation.map((i) => i.name), axisLine, axisLabel },
      series: [{ type: 'bar', data: teamViolation.map((i) => i.count), barMaxWidth: 24, itemStyle: { color: visual.primary, borderRadius: [0, 4, 4, 0] } }],
    })

}

async function onExport() {
  if (!lastData || loading.value || loadError.value || exporting.value) {
    message.warning('请先查询数据')
    return
  }
  exporting.value = true
  const snapshot = lastData
  try {
    if (!analysisPresentation.value) {
      await exportAnalysisReport({ format: 'pdf', ...queryParams() })
    }
    const [{ jsPDF }, html2canvas] = await Promise.all([
      import('jspdf'),
      import('html2canvas'),
    ])
    const canvas = await html2canvas.default(reportRef.value, {
      scale: 2,
      backgroundColor: '#ffffff',
      useCORS: true,
    })
    if (snapshot !== lastData || loading.value || loadError.value) throw new Error('统计内容已变化，请查询完成后重新导出')
    const img = canvas.toDataURL('image/png')
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
    const pageW = pdf.internal.pageSize.getWidth()
    const pageH = pdf.internal.pageSize.getHeight()
    const margin = 10
    const contentW = pageW - margin * 2
    const imgH = (canvas.height * contentW) / canvas.width

    pdf.setFontSize(14)
    pdf.text('Site Safety Review Report', margin, 12)
    pdf.setFontSize(10)
    pdf.text(`Range: ${rangeLabel.value} (${rangeDays.value} days)`, margin, 18)
    pdf.text(`Exported: ${dayjs().format('YYYY-MM-DD HH:mm:ss')}`, margin, 23)
    pdf.text(`Data source: ${analysisPresentation.value ? 'presentation demo' : 'persisted business records'}`, margin, 28)

    let y = 33
    let remain = imgH
    let srcY = 0
    const pxPerMm = canvas.height / imgH

    while (remain > 0) {
      const fit = Math.min(remain, pageH - y - margin)
      const sliceHpx = fit * pxPerMm
      const sliceCanvas = document.createElement('canvas')
      sliceCanvas.width = canvas.width
      sliceCanvas.height = Math.max(1, Math.floor(sliceHpx))
      const ctx = sliceCanvas.getContext('2d')
      ctx.drawImage(
        canvas,
        0,
        Math.floor(srcY * pxPerMm),
        canvas.width,
        sliceCanvas.height,
        0,
        0,
        canvas.width,
        sliceCanvas.height
      )
      const sliceImg = sliceCanvas.toDataURL('image/png')
      pdf.addImage(sliceImg, 'PNG', margin, y, contentW, fit)
      remain -= fit
      srcY += fit
      if (remain > 0) {
        pdf.addPage()
        y = margin
      }
    }

    // 附数据摘要页
    pdf.addPage()
    pdf.setFontSize(12)
    pdf.text('Data Summary', margin, 16)
    pdf.setFontSize(10)
    let ty = 24
    const { trend, areaHeat, teamViolation } = lastData
    pdf.text(`Trend days: ${trend.dates.join(', ')}`, margin, ty)
    ty += 6
    pdf.text(`High-risk daily: ${trend.red.join(', ')}`, margin, ty)
    ty += 6
    pdf.text(`Medium-risk daily: ${trend.orange.join(', ')}`, margin, ty)
    ty += 6
    pdf.text(`Low-risk daily: ${trend.yellow.join(', ')}`, margin, ty)
    ty += 10
    pdf.text('Area heat:', margin, ty)
    ty += 6
    areaHeat.forEach((a) => {
      pdf.text(`- ${a.name}: ${a.value}`, margin + 2, ty)
      ty += 5
      if (ty > pageH - 15) {
        pdf.addPage()
        ty = 16
      }
    })
    ty += 4
    pdf.text('Team violations:', margin, ty)
    ty += 6
    teamViolation.forEach((t) => {
      pdf.text(`- ${t.name}: ${t.count}`, margin + 2, ty)
      ty += 5
      if (ty > pageH - 15) {
        pdf.addPage()
        ty = 16
      }
    })

    const prefix = analysisPresentation.value ? '演示复盘报告' : '复盘分析报告'
    const filename = `${prefix}_${rangeMeta.value.start || 'all'}_${rangeMeta.value.end || 'all'}.pdf`
    await saveFile(pdf.output('blob'), filename)
  } catch (e) {
    console.error(e)
    message.error(e.message || '导出失败，请重试')
  } finally {
    exporting.value = false
  }
}

let resizeObserver
onMounted(() => {
  loadData()
  if (typeof ResizeObserver !== 'undefined' && reportRef.value) {
    resizeObserver = new ResizeObserver(() => charts.forEach(c => c.resize()))
    resizeObserver.observe(reportRef.value)
  }
})
watch([colorTheme,fontPercent], () => {
  renderCharts()
})
watch(() => userStore.project?.id, () => loadData())
onBeforeUnmount(() => { requests.dispose(); resizeObserver?.disconnect(); charts.forEach(c => c.dispose()); charts = [] })
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  gap: 12px;
  flex-wrap: wrap;
}
.range-tip {
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--text-secondary);
}
.empty-tip {
  margin-bottom: 12px;
  border-color: var(--border-color);
  background: var(--surface-muted);
}
.empty-tip :deep(.ant-alert-message) { color: var(--text-primary); }
.empty-tip :deep(.ant-alert-description) { color: var(--text-secondary); }
.chart-panel {
  background: var(--surface-muted);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 8px;
}
.chart { height: 300px; }
.report-capture { background: var(--surface); }
</style>
